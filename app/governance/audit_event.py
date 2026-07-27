import hashlib
import hmac
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping, Sequence
from uuid import uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from app.governance.access_context import AccessContext
from app.governance.authorization import AuthorizationDecision
from app.governance.execution_budget import ExecutionBudgetState
from app.governance.execution_policy import GovernedExecutionResult
from app.governance.sensitive_data import ResultProtectionResult


class AuditOutcome(str, Enum):
    SUCCEEDED = "succeeded"
    BLOCKED = "blocked"
    FAILED = "failed"


class AuditStage(str, Enum):
    AUTHORIZATION = "authorization"
    SQL_EXECUTION = "sql_execution"
    RESULT_PROTECTION = "result_protection"
    FINALIZATION = "finalization"


class AuditBuildReason(str, Enum):
    ALLOWED = "allowed"
    MISSING_AUDIT_SECRET = "missing_audit_secret"
    INVALID_AUDIT_INPUT = "invalid_audit_input"
    INCOMPLETE_AUDIT_EVIDENCE = (
        "incomplete_audit_evidence"
    )


class PolicyVersionSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    access_policy_version: str
    execution_policy_version: str | None = None
    budget_policy_version: str | None = None
    protection_policy_version: str | None = None

    @field_validator(
        "access_policy_version",
        "execution_policy_version",
        "budget_policy_version",
        "protection_policy_version",
    )
    @classmethod
    def validate_policy_version(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        if not value.strip():
            raise ValueError(
                "Policy version cannot be empty or whitespace."
            )

        return value


class ScopeAuditSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    role: str
    dataset_name: str
    target_schema: str
    operation_mode: str

    allowed_region_codes: tuple[str, ...]
    allowed_channel_codes: tuple[str, ...]

    metric_name: str | None = None
    required_tables: tuple[str, ...] = ()
    required_columns: tuple[str, ...] = ()


class AuthorizationAuditSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    allowed: bool
    error_type: str | None = None
    reason_code: str
    denied_metrics: tuple[str, ...] = ()
    denied_tables: tuple[str, ...] = ()
    denied_columns: tuple[str, ...] = ()
    explicitly_denied_columns: tuple[str, ...] = ()
    retryable: bool = False

    @model_validator(mode="after")
    def validate_summary(self):
        if self.retryable:
            raise ValueError(
                "Authorization audit summary cannot be retryable."
            )

        if self.allowed and self.error_type is not None:
            raise ValueError(
                "Allowed authorization cannot contain error_type."
            )

        if not self.allowed and self.error_type != "authorization_error":
            raise ValueError(
                "Denied authorization must use authorization_error."
            )

        return self


class ExecutionAuditSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    success: bool
    error_type: str | None = None

    execution_time_ms: float = Field(ge=0)
    row_count: int = Field(ge=0)
    observed_row_count: int = Field(ge=0)

    statement_timeout_ms: int = Field(ge=0)
    max_rows: int = Field(ge=0)
    retryable: bool = False

    @model_validator(mode="after")
    def validate_summary(self):
        if self.retryable:
            raise ValueError(
                "Execution governance audit cannot be retryable."
            )

        if self.success and self.error_type is not None:
            raise ValueError(
                "Successful execution cannot contain error_type."
            )

        if not self.success and self.error_type is None:
            raise ValueError(
                "Failed execution must contain error_type."
            )

        return self


class BudgetAuditSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    steps_used: int = Field(ge=0)
    retries_used: int = Field(ge=0)

    prompt_tokens_used: int = Field(ge=0)
    completion_tokens_used: int = Field(ge=0)
    total_tokens_used: int = Field(ge=0)

    exhausted: bool
    last_operation: str | None = None
    policy_fingerprint: str


class ProtectionAuditSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    success: bool
    error_type: str | None = None
    reason_code: str

    row_count: int = Field(ge=0)
    tokenized_fields: tuple[str, ...] = ()
    allowed_sensitive_fields: tuple[str, ...] = ()
    rejected_fields: tuple[str, ...] = ()

    minimum_group_size_checked: bool = False
    minimum_observed_group_size: int | None = Field(
        default=None,
        ge=0,
    )

    contract_fingerprint: str
    protection_fingerprint: str
    retryable: bool = False

    @model_validator(mode="after")
    def validate_summary(self):
        if self.retryable:
            raise ValueError(
                "Result protection audit cannot be retryable."
            )

        if self.success and self.error_type is not None:
            raise ValueError(
                "Successful protection cannot contain error_type."
            )

        if (
            not self.success
            and self.error_type != "result_protection_error"
        ):
            raise ValueError(
                "Failed protection must use "
                "result_protection_error."
            )

        return self


class RepairAttemptAudit(BaseModel):
    model_config = ConfigDict(frozen=True)

    attempt: int = Field(ge=1)
    source_sql_fingerprint: str
    repaired_sql_fingerprint: str
    execution_error_fingerprint: str


class RepairAuditSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    attempt_count: int = Field(ge=0)
    attempts: tuple[RepairAttemptAudit, ...] = ()

    @model_validator(mode="after")
    def validate_attempt_count(self):
        if self.attempt_count != len(self.attempts):
            raise ValueError(
                "attempt_count must equal len(attempts)."
            )

        return self


class AuditEvent(BaseModel):
    """
    单次请求的最终审计证据。

    安全约束：
    - 不保存原始问题；
    - 不保存原始 SQL；
    - 不保存 SQL 参数；
    - 不保存结果行；
    - 不保存 Tokenization / Audit Secret；
    - 不保存原始数据库错误或 Repair 错误。
    """

    model_config = ConfigDict(frozen=True)

    event_id: str
    request_id: str
    occurred_at_utc: datetime

    actor_ref: str
    scope: ScopeAuditSnapshot
    policies: PolicyVersionSnapshot

    question_fingerprint: str
    question_length: int = Field(ge=0)

    generated_sql_fingerprint: str | None = None
    executed_sql_fingerprint: str | None = None

    authorization: AuthorizationAuditSummary
    execution: ExecutionAuditSummary | None = None
    budget: BudgetAuditSummary | None = None
    protection: ProtectionAuditSummary | None = None
    repair: RepairAuditSummary

    outcome: AuditOutcome
    blocked_stage: AuditStage | None = None
    blocked_reason: str | None = None

    event_fingerprint: str
    retryable: bool = False
    audit_schema_version: str = "audit_event_v2"

    @field_validator("occurred_at_utc")
    @classmethod
    def validate_timestamp(
        cls,
        value: datetime,
    ) -> datetime:
        if value.tzinfo is None:
            raise ValueError(
                "occurred_at_utc must be timezone-aware."
            )

        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def validate_event(self):
        if self.retryable:
            raise ValueError(
                "Audit events cannot be retryable."
            )

        if not self.event_id.strip():
            raise ValueError("event_id cannot be empty.")

        if not self.request_id.strip():
            raise ValueError("request_id cannot be empty.")

        if not self.actor_ref.strip():
            raise ValueError("actor_ref cannot be empty.")

        if not self.event_fingerprint.strip():
            raise ValueError(
                "event_fingerprint cannot be empty."
            )

        if self.outcome == AuditOutcome.SUCCEEDED:
            if (
                self.blocked_stage is not None
                or self.blocked_reason is not None
            ):
                raise ValueError(
                    "Successful event cannot contain block details."
                )

            if self.execution is None or not self.execution.success:
                raise ValueError(
                    "Successful event requires successful execution."
                )

            if self.protection is None or not self.protection.success:
                raise ValueError(
                    "Successful event requires successful "
                    "result protection."
                )

        if self.outcome == AuditOutcome.BLOCKED:
            if (
                self.blocked_stage is None
                or not self.blocked_reason
            ):
                raise ValueError(
                    "Blocked event requires stage and reason."
                )

        return self


class AuditBuildResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    success: bool
    event: AuditEvent | None = None

    error_type: str | None = None
    reason_code: AuditBuildReason
    message: str
    retryable: bool = False

    @model_validator(mode="after")
    def validate_result(self):
        if self.retryable:
            raise ValueError(
                "Audit build failures must not be retryable."
            )

        if self.success:
            if self.event is None:
                raise ValueError(
                    "Successful audit build requires an event."
                )

            if self.error_type is not None:
                raise ValueError(
                    "Successful audit build cannot contain "
                    "error_type."
                )

            if self.reason_code != AuditBuildReason.ALLOWED:
                raise ValueError(
                    "Successful audit build must use allowed."
                )
        else:
            if self.event is not None:
                raise ValueError(
                    "Failed audit build cannot contain an event."
                )

            if self.error_type != "audit_error":
                raise ValueError(
                    "Failed audit build must use audit_error."
                )

            if self.reason_code == AuditBuildReason.ALLOWED:
                raise ValueError(
                    "Failed audit build cannot use allowed."
                )

        return self


def _canonicalize_text(value: str) -> str:
    return value.replace("\r\n", "\n").replace(
        "\r",
        "\n",
    ).strip()


def fingerprint_text(
    value: str,
    *,
    namespace: str,
    audit_secret: str,
) -> str:
    """
    对审计中的敏感文本生成 keyed fingerprint。

    目的：
    - 不保存原始 question / SQL / repair error；
    - 避免低熵文本的普通 SHA-256 fingerprint 被离线字典枚举；
    - 通过 namespace 做 domain separation。

    注意：
    - 这不是加密；Audit Secret 泄漏后仍可能被枚举；
    - Event Fingerprint 继续使用普通 SHA-256，因为其输入已经是
      受保护的结构化 Audit Event payload。
    """

    canonical = _canonicalize_text(value)
    payload = (
        f"audit_text_hmac_v1\x1f{namespace}\x1f{canonical}"
    ).encode("utf-8")

    return hmac.new(
        audit_secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()


def build_actor_ref(
    *,
    actor_id: str,
    audit_secret: str,
) -> str:
    message = f"actor\x1f{actor_id}".encode("utf-8")

    digest = hmac.new(
        audit_secret.encode("utf-8"),
        message,
        hashlib.sha256,
    ).hexdigest()

    return f"ACT_{digest[:24]}"


def _authorization_summary(
    decision: AuthorizationDecision,
) -> AuthorizationAuditSummary:
    return AuthorizationAuditSummary(
        allowed=decision.allowed,
        error_type=decision.error_type,
        reason_code=decision.reason_code.value,
        denied_metrics=tuple(
            sorted(decision.denied_metrics)
        ),
        denied_tables=tuple(
            sorted(decision.denied_tables)
        ),
        denied_columns=tuple(
            sorted(decision.denied_columns)
        ),
        explicitly_denied_columns=tuple(
            sorted(decision.explicitly_denied_columns)
        ),
        retryable=decision.retryable,
    )


def _execution_summary(
    result: GovernedExecutionResult | None,
) -> ExecutionAuditSummary | None:
    if result is None:
        return None

    return ExecutionAuditSummary(
        success=result.success,
        error_type=(
            result.error_type.value
            if result.error_type is not None
            else None
        ),
        execution_time_ms=result.execution_time_ms,
        row_count=result.row_count,
        observed_row_count=result.observed_row_count,
        statement_timeout_ms=result.statement_timeout_ms,
        max_rows=result.max_rows,
        retryable=result.retryable,
    )


def _budget_summary(
    state: ExecutionBudgetState | None,
) -> BudgetAuditSummary | None:
    if state is None:
        return None

    return BudgetAuditSummary(
        steps_used=state.steps_used,
        retries_used=state.retries_used,
        prompt_tokens_used=state.prompt_tokens_used,
        completion_tokens_used=(
            state.completion_tokens_used
        ),
        total_tokens_used=state.total_tokens_used,
        exhausted=state.exhausted,
        last_operation=state.last_operation,
        policy_fingerprint=state.policy_fingerprint,
    )


def _protection_summary(
    result: ResultProtectionResult | None,
) -> ProtectionAuditSummary | None:
    if result is None:
        return None

    tokenized_fields = []
    allowed_sensitive_fields = []

    for item in result.applied_protections:
        if item.action.value == "tokenize":
            tokenized_fields.append(item.output_field)
        elif (
            item.action.value == "allow"
            and item.category.value != "ordinary"
        ):
            allowed_sensitive_fields.append(
                item.output_field
            )

    return ProtectionAuditSummary(
        success=result.success,
        error_type=result.error_type,
        reason_code=result.reason_code.value,
        row_count=result.row_count,
        tokenized_fields=tuple(
            sorted(tokenized_fields)
        ),
        allowed_sensitive_fields=tuple(
            sorted(allowed_sensitive_fields)
        ),
        rejected_fields=tuple(
            sorted(result.rejected_fields)
        ),
        minimum_group_size_checked=(
            result.minimum_group_size_checked
        ),
        minimum_observed_group_size=(
            result.minimum_observed_group_size
        ),
        contract_fingerprint=(
            result.contract_fingerprint
        ),
        protection_fingerprint=(
            result.protection_fingerprint
        ),
        retryable=result.retryable,
    )


def _repair_summary(
    repair_history: Sequence[Mapping[str, Any]],
    *,
    audit_secret: str,
) -> RepairAuditSummary:
    attempts = []

    for index, record in enumerate(
        repair_history,
        start=1,
    ):
        attempt_value = record.get("attempt", index)

        if (
            isinstance(attempt_value, bool)
            or not isinstance(attempt_value, int)
            or attempt_value < 1
        ):
            raise ValueError(
                "Repair attempt must be a positive integer."
            )

        source_sql = str(record.get("source_sql", ""))
        repaired_sql = str(
            record.get("repaired_sql", "")
        )
        execution_error = str(
            record.get("execution_error", "")
        )

        attempts.append(
            RepairAttemptAudit(
                attempt=attempt_value,
                source_sql_fingerprint=fingerprint_text(
                    source_sql,
                    namespace="repair_source_sql",
                    audit_secret=audit_secret,
                ),
                repaired_sql_fingerprint=fingerprint_text(
                    repaired_sql,
                    namespace="repair_output_sql",
                    audit_secret=audit_secret,
                ),
                execution_error_fingerprint=(
                    fingerprint_text(
                        execution_error,
                        namespace="repair_execution_error",
                        audit_secret=audit_secret,
                    )
                ),
            )
        )

    return RepairAuditSummary(
        attempt_count=len(attempts),
        attempts=tuple(attempts),
    )


def _determine_outcome(
    *,
    authorization: AuthorizationDecision,
    execution: GovernedExecutionResult | None,
    protection: ResultProtectionResult | None,
) -> tuple[
    AuditOutcome,
    AuditStage | None,
    str | None,
]:
    if not authorization.allowed:
        return (
            AuditOutcome.BLOCKED,
            AuditStage.AUTHORIZATION,
            authorization.reason_code.value,
        )

    if execution is None:
        return (
            AuditOutcome.FAILED,
            AuditStage.FINALIZATION,
            "execution_evidence_missing",
        )

    if not execution.success:
        return (
            AuditOutcome.BLOCKED,
            AuditStage.SQL_EXECUTION,
            execution.error_type.value,
        )

    if protection is None:
        return (
            AuditOutcome.FAILED,
            AuditStage.FINALIZATION,
            "result_protection_evidence_missing",
        )

    if not protection.success:
        return (
            AuditOutcome.BLOCKED,
            AuditStage.RESULT_PROTECTION,
            protection.reason_code.value,
        )

    return (
        AuditOutcome.SUCCEEDED,
        None,
        None,
    )


def _event_payload_for_fingerprint(
    *,
    event_id: str,
    request_id: str,
    occurred_at_utc: datetime,
    actor_ref: str,
    scope: ScopeAuditSnapshot,
    policies: PolicyVersionSnapshot,
    question_fingerprint: str,
    question_length: int,
    generated_sql_fingerprint: str | None,
    executed_sql_fingerprint: str | None,
    authorization: AuthorizationAuditSummary,
    execution: ExecutionAuditSummary | None,
    budget: BudgetAuditSummary | None,
    protection: ProtectionAuditSummary | None,
    repair: RepairAuditSummary,
    outcome: AuditOutcome,
    blocked_stage: AuditStage | None,
    blocked_reason: str | None,
    audit_schema_version: str,
) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "request_id": request_id,
        "occurred_at_utc": (
            occurred_at_utc
            .astimezone(timezone.utc)
            .isoformat()
        ),
        "actor_ref": actor_ref,
        "scope": scope.model_dump(mode="json"),
        "policies": policies.model_dump(mode="json"),
        "question_fingerprint": question_fingerprint,
        "question_length": question_length,
        "generated_sql_fingerprint": (
            generated_sql_fingerprint
        ),
        "executed_sql_fingerprint": (
            executed_sql_fingerprint
        ),
        "authorization": (
            authorization.model_dump(mode="json")
        ),
        "execution": (
            execution.model_dump(mode="json")
            if execution is not None
            else None
        ),
        "budget": (
            budget.model_dump(mode="json")
            if budget is not None
            else None
        ),
        "protection": (
            protection.model_dump(mode="json")
            if protection is not None
            else None
        ),
        "repair": repair.model_dump(mode="json"),
        "outcome": outcome.value,
        "blocked_stage": (
            blocked_stage.value
            if blocked_stage is not None
            else None
        ),
        "blocked_reason": blocked_reason,
        "audit_schema_version": audit_schema_version,
    }


def build_audit_event(
    *,
    context: AccessContext,
    question: str,
    authorization: AuthorizationDecision,
    required_tables: Sequence[str] = (),
    required_columns: Sequence[str] = (),
    metric_name: str | None = None,
    generated_sql: str | None = None,
    executed_sql: str | None = None,
    execution: GovernedExecutionResult | None = None,
    budget: ExecutionBudgetState | None = None,
    protection: ResultProtectionResult | None = None,
    repair_history: Sequence[Mapping[str, Any]] = (),
    audit_secret: str | None = None,
    event_id: str | None = None,
    occurred_at_utc: datetime | None = None,
) -> AuditBuildResult:
    """
    构建单次请求的最终 Audit Event。

    原始 question、SQL、结果行、错误文本和 Secret
    都不会写入 AuditEvent。
    """

    if audit_secret is None or len(audit_secret) < 16:
        return AuditBuildResult(
            success=False,
            event=None,
            error_type="audit_error",
            reason_code=(
                AuditBuildReason.MISSING_AUDIT_SECRET
            ),
            message=(
                "An audit secret of at least 16 characters "
                "is required."
            ),
            retryable=False,
        )

    if not isinstance(question, str):
        return AuditBuildResult(
            success=False,
            event=None,
            error_type="audit_error",
            reason_code=AuditBuildReason.INVALID_AUDIT_INPUT,
            message="question must be a string.",
            retryable=False,
        )

    outcome, blocked_stage, blocked_reason = (
        _determine_outcome(
            authorization=authorization,
            execution=execution,
            protection=protection,
        )
    )

    if outcome == AuditOutcome.FAILED:
        return AuditBuildResult(
            success=False,
            event=None,
            error_type="audit_error",
            reason_code=(
                AuditBuildReason.INCOMPLETE_AUDIT_EVIDENCE
            ),
            message=(
                blocked_reason
                or "Audit evidence is incomplete."
            ),
            retryable=False,
        )

    try:
        current_event_id = event_id or str(uuid4())
        current_timestamp = (
            occurred_at_utc
            if occurred_at_utc is not None
            else datetime.now(timezone.utc)
        )

        if current_timestamp.tzinfo is None:
            raise ValueError(
                "occurred_at_utc must be timezone-aware."
            )

        current_timestamp = current_timestamp.astimezone(
            timezone.utc
        )

        scope = ScopeAuditSnapshot(
            role=context.role.value,
            dataset_name=context.dataset_name,
            target_schema=context.target_schema,
            operation_mode=(
                context.operation_mode.value
            ),
            allowed_region_codes=tuple(
                sorted(context.allowed_region_codes)
            ),
            allowed_channel_codes=tuple(
                sorted(context.allowed_channel_codes)
            ),
            metric_name=metric_name,
            required_tables=tuple(
                sorted(set(required_tables))
            ),
            required_columns=tuple(
                sorted(set(required_columns))
            ),
        )

        policies = PolicyVersionSnapshot(
            access_policy_version=(
                context.policy_version
            ),
            execution_policy_version=(
                execution.policy_version
                if execution is not None
                else None
            ),
            budget_policy_version=(
                budget.policy_version
                if budget is not None
                else None
            ),
            protection_policy_version=(
                protection.policy_version
                if protection is not None
                else None
            ),
        )

        actor_ref = build_actor_ref(
            actor_id=context.actor_id,
            audit_secret=audit_secret,
        )

        question_fingerprint = fingerprint_text(
            question,
            namespace="question",
            audit_secret=audit_secret,
        )

        generated_sql_fingerprint = (
            fingerprint_text(
                generated_sql,
                namespace="generated_sql",
                audit_secret=audit_secret,
            )
            if generated_sql is not None
            else None
        )

        executed_sql_fingerprint = (
            fingerprint_text(
                executed_sql,
                namespace="executed_sql",
                audit_secret=audit_secret,
            )
            if executed_sql is not None
            else None
        )

        authorization_summary = (
            _authorization_summary(authorization)
        )
        execution_summary = _execution_summary(execution)
        budget_summary = _budget_summary(budget)
        protection_summary = (
            _protection_summary(protection)
        )
        repair_summary = _repair_summary(
            repair_history,
            audit_secret=audit_secret,
        )

        audit_schema_version = "audit_event_v2"

        payload = _event_payload_for_fingerprint(
            event_id=current_event_id,
            request_id=context.request_id,
            occurred_at_utc=current_timestamp,
            actor_ref=actor_ref,
            scope=scope,
            policies=policies,
            question_fingerprint=(
                question_fingerprint
            ),
            question_length=len(question),
            generated_sql_fingerprint=(
                generated_sql_fingerprint
            ),
            executed_sql_fingerprint=(
                executed_sql_fingerprint
            ),
            authorization=authorization_summary,
            execution=execution_summary,
            budget=budget_summary,
            protection=protection_summary,
            repair=repair_summary,
            outcome=outcome,
            blocked_stage=blocked_stage,
            blocked_reason=blocked_reason,
            audit_schema_version=(
                audit_schema_version
            ),
        )

        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

        event_fingerprint = hashlib.sha256(
            serialized.encode("utf-8")
        ).hexdigest()

        event = AuditEvent(
            **payload,
            event_fingerprint=event_fingerprint,
            retryable=False,
        )

    except (
        ValidationError,
        TypeError,
        ValueError,
    ) as error:
        return AuditBuildResult(
            success=False,
            event=None,
            error_type="audit_error",
            reason_code=(
                AuditBuildReason.INVALID_AUDIT_INPUT
            ),
            message=(
                "Audit event input failed structural validation."
            ),
            retryable=False,
        )

    return AuditBuildResult(
        success=True,
        event=event,
        error_type=None,
        reason_code=AuditBuildReason.ALLOWED,
        message="Audit event built.",
        retryable=False,
    )


def serialize_audit_event(
    event: AuditEvent,
) -> str:
    """
    生成单行 JSON，供后续 append-only sink 使用。
    """

    return event.model_dump_json()
