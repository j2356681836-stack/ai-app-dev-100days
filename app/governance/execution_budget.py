import hashlib
import json
from enum import Enum

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)


class BudgetErrorType(str, Enum):
    EXECUTION_BUDGET_ERROR = "execution_budget_error"


class BudgetReason(str, Enum):
    ALLOWED = "allowed"
    INVALID_BUDGET_USAGE = "invalid_budget_usage"
    BUDGET_ALREADY_EXHAUSTED = "budget_already_exhausted"
    STEP_LIMIT_EXCEEDED = "step_limit_exceeded"
    RETRY_LIMIT_EXCEEDED = "retry_limit_exceeded"
    PROMPT_TOKEN_LIMIT_EXCEEDED = (
        "prompt_token_limit_exceeded"
    )
    COMPLETION_TOKEN_LIMIT_EXCEEDED = (
        "completion_token_limit_exceeded"
    )
    TOTAL_TOKEN_LIMIT_EXCEEDED = (
        "total_token_limit_exceeded"
    )
    RETRY_CONTRACT_MISMATCH = "retry_contract_mismatch"


class ExecutionBudgetPolicy(BaseModel):
    """
    单次 Agent 请求的最小执行预算合同。

    注意：
    - max_steps 是业务步骤预算，不等同于数据库连接池限制；
    - max_retries 只控制 SQL Repair；
    - Token Budget 只覆盖在线 LLM 调用；
    - 离线 Answer Judge / Ragas 不计入在线预算。
    """

    model_config = ConfigDict(frozen=True)

    max_steps: int = Field(default=25, ge=1, le=200)
    max_retries: int = Field(default=1, ge=0, le=5)

    max_prompt_tokens: int = Field(
        default=12_000,
        ge=1,
        le=200_000,
    )
    max_completion_tokens: int = Field(
        default=2_000,
        ge=1,
        le=50_000,
    )
    max_total_tokens: int = Field(
        default=14_000,
        ge=1,
        le=250_000,
    )

    max_completion_tokens_per_call: int = Field(
        default=1_000,
        ge=1,
        le=20_000,
    )

    policy_version: str = "agent_execution_budget_v1"

    @model_validator(mode="after")
    def validate_budget_policy(self):
        if self.max_total_tokens < max(
            self.max_prompt_tokens,
            self.max_completion_tokens,
        ):
            raise ValueError(
                "max_total_tokens must be at least as large as "
                "each individual token limit."
            )

        if (
            self.max_completion_tokens_per_call
            > self.max_completion_tokens
        ):
            raise ValueError(
                "max_completion_tokens_per_call cannot exceed "
                "max_completion_tokens."
            )

        if (
            not self.policy_version
            or not self.policy_version.strip()
        ):
            raise ValueError(
                "policy_version cannot be empty or whitespace."
            )

        return self


class TokenUsage(BaseModel):
    """
    单次在线 LLM 调用返回的 Token Usage。

    total_tokens 允许大于 prompt + completion，
    以兼容未来供应商可能加入的额外计费 Token；
    但不能小于二者之和。
    """

    model_config = ConfigDict(frozen=True)

    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_token_usage(self):
        if self.total_tokens < (
            self.prompt_tokens
            + self.completion_tokens
        ):
            raise ValueError(
                "total_tokens cannot be smaller than "
                "prompt_tokens + completion_tokens."
            )

        return self


class ExecutionBudgetState(BaseModel):
    """
    单次请求的累计预算状态。
    """

    model_config = ConfigDict(frozen=True)

    steps_used: int = Field(default=0, ge=0)
    retries_used: int = Field(default=0, ge=0)

    prompt_tokens_used: int = Field(default=0, ge=0)
    completion_tokens_used: int = Field(default=0, ge=0)
    total_tokens_used: int = Field(default=0, ge=0)

    exhausted: bool = False
    last_operation: str | None = None

    policy_version: str
    policy_fingerprint: str

    @model_validator(mode="after")
    def validate_budget_state(self):
        if self.total_tokens_used < (
            self.prompt_tokens_used
            + self.completion_tokens_used
        ):
            raise ValueError(
                "total_tokens_used cannot be smaller than "
                "prompt_tokens_used + completion_tokens_used."
            )

        if (
            not self.policy_fingerprint
            or not self.policy_fingerprint.strip()
        ):
            raise ValueError(
                "policy_fingerprint cannot be empty."
            )

        return self


class BudgetDecision(BaseModel):
    """
    统一预算决策。

    所有预算失败均：
    - error_type = execution_budget_error
    - retryable = false
    """

    model_config = ConfigDict(frozen=True)

    allowed: bool
    error_type: BudgetErrorType | None = None
    reason_code: BudgetReason
    message: str

    state: ExecutionBudgetState

    observed_value: int | None = Field(default=None, ge=0)
    limit_value: int | None = Field(default=None, ge=0)

    retryable: bool = False
    policy_version: str

    @model_validator(mode="after")
    def validate_decision(self):
        if self.allowed:
            if self.error_type is not None:
                raise ValueError(
                    "Allowed decision cannot contain error_type."
                )

            if self.reason_code != BudgetReason.ALLOWED:
                raise ValueError(
                    "Allowed decision must use reason_code=allowed."
                )
        else:
            if (
                self.error_type
                != BudgetErrorType.EXECUTION_BUDGET_ERROR
            ):
                raise ValueError(
                    "Denied decision must use "
                    "execution_budget_error."
                )

            if self.reason_code == BudgetReason.ALLOWED:
                raise ValueError(
                    "Denied decision cannot use allowed reason."
                )

        if self.retryable:
            raise ValueError(
                "Execution budget failures must not be retryable."
            )

        return self


def build_budget_policy_fingerprint(
    policy: ExecutionBudgetPolicy,
) -> str:
    payload = {
        "max_steps": policy.max_steps,
        "max_retries": policy.max_retries,
        "max_prompt_tokens": policy.max_prompt_tokens,
        "max_completion_tokens": (
            policy.max_completion_tokens
        ),
        "max_total_tokens": policy.max_total_tokens,
        "max_completion_tokens_per_call": (
            policy.max_completion_tokens_per_call
        ),
        "policy_version": policy.policy_version,
    }

    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )

    return hashlib.sha256(
        serialized.encode("utf-8")
    ).hexdigest()


def create_initial_budget_state(
    policy: ExecutionBudgetPolicy,
) -> ExecutionBudgetState:
    return ExecutionBudgetState(
        policy_version=policy.policy_version,
        policy_fingerprint=(
            build_budget_policy_fingerprint(policy)
        ),
    )


def _allowed(
    *,
    policy: ExecutionBudgetPolicy,
    state: ExecutionBudgetState,
    message: str,
) -> BudgetDecision:
    return BudgetDecision(
        allowed=True,
        error_type=None,
        reason_code=BudgetReason.ALLOWED,
        message=message,
        state=state,
        retryable=False,
        policy_version=policy.policy_version,
    )


def _denied(
    *,
    policy: ExecutionBudgetPolicy,
    state: ExecutionBudgetState,
    reason_code: BudgetReason,
    message: str,
    observed_value: int | None = None,
    limit_value: int | None = None,
) -> BudgetDecision:
    exhausted_state = state.model_copy(
        update={
            "exhausted": True,
        }
    )

    return BudgetDecision(
        allowed=False,
        error_type=(
            BudgetErrorType.EXECUTION_BUDGET_ERROR
        ),
        reason_code=reason_code,
        message=message,
        state=exhausted_state,
        observed_value=observed_value,
        limit_value=limit_value,
        retryable=False,
        policy_version=policy.policy_version,
    )


def _check_state_policy(
    *,
    policy: ExecutionBudgetPolicy,
    state: ExecutionBudgetState,
) -> BudgetDecision | None:
    expected_fingerprint = (
        build_budget_policy_fingerprint(policy)
    )

    if (
        state.policy_version != policy.policy_version
        or state.policy_fingerprint
        != expected_fingerprint
    ):
        return _denied(
            policy=policy,
            state=state,
            reason_code=(
                BudgetReason.INVALID_BUDGET_USAGE
            ),
            message=(
                "Budget state does not match the active policy."
            ),
        )

    if state.exhausted:
        return _denied(
            policy=policy,
            state=state,
            reason_code=(
                BudgetReason.BUDGET_ALREADY_EXHAUSTED
            ),
            message="Execution budget is already exhausted.",
        )

    return None


def consume_step(
    *,
    policy: ExecutionBudgetPolicy,
    state: ExecutionBudgetState,
    operation: str,
    steps: int = 1,
) -> BudgetDecision:
    invalid = _check_state_policy(
        policy=policy,
        state=state,
    )

    if invalid is not None:
        return invalid

    if steps <= 0:
        return _denied(
            policy=policy,
            state=state,
            reason_code=(
                BudgetReason.INVALID_BUDGET_USAGE
            ),
            message="steps must be greater than zero.",
        )

    observed = state.steps_used + steps

    if observed > policy.max_steps:
        return _denied(
            policy=policy,
            state=state,
            reason_code=(
                BudgetReason.STEP_LIMIT_EXCEEDED
            ),
            message="Agent step budget exceeded.",
            observed_value=observed,
            limit_value=policy.max_steps,
        )

    next_state = state.model_copy(
        update={
            "steps_used": observed,
            "last_operation": operation,
        }
    )

    return _allowed(
        policy=policy,
        state=next_state,
        message="Agent step budget consumed.",
    )


def consume_retry(
    *,
    policy: ExecutionBudgetPolicy,
    state: ExecutionBudgetState,
    operation: str = "sql_repair",
    retries: int = 1,
) -> BudgetDecision:
    invalid = _check_state_policy(
        policy=policy,
        state=state,
    )

    if invalid is not None:
        return invalid

    if retries <= 0:
        return _denied(
            policy=policy,
            state=state,
            reason_code=(
                BudgetReason.INVALID_BUDGET_USAGE
            ),
            message="retries must be greater than zero.",
        )

    observed = state.retries_used + retries

    if observed > policy.max_retries:
        return _denied(
            policy=policy,
            state=state,
            reason_code=(
                BudgetReason.RETRY_LIMIT_EXCEEDED
            ),
            message="SQL repair retry budget exceeded.",
            observed_value=observed,
            limit_value=policy.max_retries,
        )

    next_state = state.model_copy(
        update={
            "retries_used": observed,
            "last_operation": operation,
        }
    )

    return _allowed(
        policy=policy,
        state=next_state,
        message="SQL repair retry budget consumed.",
    )


def consume_token_usage(
    *,
    policy: ExecutionBudgetPolicy,
    state: ExecutionBudgetState,
    usage: TokenUsage,
    operation: str,
) -> BudgetDecision:
    invalid = _check_state_policy(
        policy=policy,
        state=state,
    )

    if invalid is not None:
        return invalid

    next_state = state.model_copy(
        update={
            "prompt_tokens_used": (
                state.prompt_tokens_used
                + usage.prompt_tokens
            ),
            "completion_tokens_used": (
                state.completion_tokens_used
                + usage.completion_tokens
            ),
            "total_tokens_used": (
                state.total_tokens_used
                + usage.total_tokens
            ),
            "last_operation": operation,
        }
    )

    checks = (
        (
            next_state.prompt_tokens_used,
            policy.max_prompt_tokens,
            BudgetReason.PROMPT_TOKEN_LIMIT_EXCEEDED,
            "Prompt token budget exceeded.",
        ),
        (
            next_state.completion_tokens_used,
            policy.max_completion_tokens,
            (
                BudgetReason
                .COMPLETION_TOKEN_LIMIT_EXCEEDED
            ),
            "Completion token budget exceeded.",
        ),
        (
            next_state.total_tokens_used,
            policy.max_total_tokens,
            BudgetReason.TOTAL_TOKEN_LIMIT_EXCEEDED,
            "Total token budget exceeded.",
        ),
    )

    for observed, limit, reason, message in checks:
        if observed > limit:
            return _denied(
                policy=policy,
                state=next_state,
                reason_code=reason,
                message=message,
                observed_value=observed,
                limit_value=limit,
            )

    return _allowed(
        policy=policy,
        state=next_state,
        message="LLM token usage recorded.",
    )


def remaining_completion_token_allowance(
    *,
    policy: ExecutionBudgetPolicy,
    state: ExecutionBudgetState,
) -> int:
    if state.exhausted:
        return 0

    remaining_completion = max(
        0,
        policy.max_completion_tokens
        - state.completion_tokens_used,
    )

    remaining_total = max(
        0,
        policy.max_total_tokens
        - state.total_tokens_used,
    )

    return min(
        policy.max_completion_tokens_per_call,
        remaining_completion,
        remaining_total,
    )


def validate_retry_contract(
    *,
    policy: ExecutionBudgetPolicy,
    graph_max_retries: int,
) -> BudgetDecision:
    state = create_initial_budget_state(policy)

    if graph_max_retries < 0:
        return _denied(
            policy=policy,
            state=state,
            reason_code=(
                BudgetReason.INVALID_BUDGET_USAGE
            ),
            message="graph_max_retries cannot be negative.",
        )

    if graph_max_retries > policy.max_retries:
        return _denied(
            policy=policy,
            state=state,
            reason_code=(
                BudgetReason.RETRY_CONTRACT_MISMATCH
            ),
            message=(
                "Graph retry limit exceeds the active "
                "execution budget."
            ),
            observed_value=graph_max_retries,
            limit_value=policy.max_retries,
        )

    return _allowed(
        policy=policy,
        state=state,
        message="Graph retry contract is compatible.",
    )
