from datetime import datetime
from enum import Enum
from typing import Any, Mapping, Sequence

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from app.governance.access_context import AccessContext
from app.governance.audit_event import build_audit_event
from app.governance.audit_sink import append_audit_event
from app.governance.authorization import AuthorizationDecision
from app.governance.execution_budget import ExecutionBudgetState
from app.governance.execution_policy import GovernedExecutionResult
from app.governance.governance_runtime import (
    GovernanceRuntimeConfig,
)
from app.governance.sensitive_data import (
    ResultProtectionContract,
    protect_result_rows,
)


class FinalizationOutcome(str, Enum):
    SUCCEEDED = "succeeded"
    BLOCKED = "blocked"
    FAILED = "failed"


class FinalizationReason(str, Enum):
    ALLOWED = "allowed"
    AUTHORIZATION_BLOCKED = "authorization_blocked"
    EXECUTION_BLOCKED = "execution_blocked"
    RESULT_PROTECTION_BLOCKED = (
        "result_protection_blocked"
    )
    INVALID_FINALIZATION_INPUT = (
        "invalid_finalization_input"
    )
    AUDIT_BUILD_FAILED = "audit_build_failed"
    AUDIT_PERSISTENCE_FAILED = (
        "audit_persistence_failed"
    )


class GovernedFinalizationResult(BaseModel):
    """
    请求离开治理边界前的最终结果。

    success=True 的唯一含义：
    - Authorization 允许；
    - SQL Execution 成功；
    - Result Protection 成功；
    - Audit Event 构建成功；
    - Audit Sink 持久化成功；
    - 当前 rows 才可以交给 Result Formatter / Answer Layer。
    """

    model_config = ConfigDict(frozen=True)

    success: bool
    outcome: FinalizationOutcome
    reason_code: FinalizationReason
    message: str

    rows: tuple[dict[str, Any], ...] = ()
    row_count: int = Field(default=0, ge=0)

    blocked_stage: str | None = None
    blocked_reason: str | None = None

    audit_persisted: bool = False
    audit_event_id: str | None = None
    audit_event_fingerprint: str | None = None
    audit_sequence_number: int | None = Field(
        default=None,
        ge=1,
    )
    audit_record_hash: str | None = None

    error_type: str | None = None
    retryable: bool = False
    contract_version: str = "governed_finalization_v1"

    @model_validator(mode="after")
    def validate_result(self):
        if self.retryable:
            raise ValueError(
                "Governed finalization results are non-retryable."
            )

        if self.row_count != len(self.rows):
            raise ValueError(
                "row_count must equal len(rows)."
            )

        audit_fields = (
            self.audit_event_id,
            self.audit_event_fingerprint,
            self.audit_sequence_number,
            self.audit_record_hash,
        )

        if self.audit_persisted:
            if any(value is None for value in audit_fields):
                raise ValueError(
                    "Persisted audit evidence requires all audit "
                    "identifiers."
                )
        elif any(value is not None for value in audit_fields):
            raise ValueError(
                "Unpersisted result cannot contain audit "
                "persistence identifiers."
            )

        if self.outcome == FinalizationOutcome.SUCCEEDED:
            if not self.success:
                raise ValueError(
                    "Succeeded outcome requires success=True."
                )

            if self.reason_code != FinalizationReason.ALLOWED:
                raise ValueError(
                    "Succeeded outcome must use reason=allowed."
                )

            if not self.audit_persisted:
                raise ValueError(
                    "Rows cannot be released before audit "
                    "persistence succeeds."
                )

            if self.error_type is not None:
                raise ValueError(
                    "Succeeded outcome cannot contain error_type."
                )

            if (
                self.blocked_stage is not None
                or self.blocked_reason is not None
            ):
                raise ValueError(
                    "Succeeded outcome cannot contain block details."
                )

        elif self.outcome == FinalizationOutcome.BLOCKED:
            if self.success:
                raise ValueError(
                    "Blocked outcome requires success=False."
                )

            if self.rows or self.row_count != 0:
                raise ValueError(
                    "Blocked outcome cannot release rows."
                )

            if not self.audit_persisted:
                raise ValueError(
                    "Blocked outcome requires persisted audit "
                    "evidence."
                )

            if self.error_type != "governance_blocked":
                raise ValueError(
                    "Blocked outcome must use governance_blocked."
                )

            if (
                self.blocked_stage is None
                or self.blocked_reason is None
            ):
                raise ValueError(
                    "Blocked outcome requires block details."
                )

        else:
            if self.success:
                raise ValueError(
                    "Failed outcome requires success=False."
                )

            if self.rows or self.row_count != 0:
                raise ValueError(
                    "Failed finalization cannot release rows."
                )

            if self.audit_persisted:
                raise ValueError(
                    "Failed finalization cannot claim persisted "
                    "audit evidence."
                )

            if self.error_type != "governance_finalization_error":
                raise ValueError(
                    "Failed outcome must use "
                    "governance_finalization_error."
                )

        return self


def _failed(
    *,
    reason_code: FinalizationReason,
    message: str,
) -> GovernedFinalizationResult:
    return GovernedFinalizationResult(
        success=False,
        outcome=FinalizationOutcome.FAILED,
        reason_code=reason_code,
        message=message,
        rows=(),
        row_count=0,
        blocked_stage=None,
        blocked_reason=None,
        audit_persisted=False,
        audit_event_id=None,
        audit_event_fingerprint=None,
        audit_sequence_number=None,
        audit_record_hash=None,
        error_type="governance_finalization_error",
        retryable=False,
    )


def _persisted_result(
    *,
    event,
    sink_result,
    rows: tuple[dict[str, Any], ...],
) -> GovernedFinalizationResult:
    if event.outcome.value == "succeeded":
        return GovernedFinalizationResult(
            success=True,
            outcome=FinalizationOutcome.SUCCEEDED,
            reason_code=FinalizationReason.ALLOWED,
            message=(
                "Governed request finalized and rows released."
            ),
            rows=rows,
            row_count=len(rows),
            blocked_stage=None,
            blocked_reason=None,
            audit_persisted=True,
            audit_event_id=event.event_id,
            audit_event_fingerprint=(
                event.event_fingerprint
            ),
            audit_sequence_number=(
                sink_result.sequence_number
            ),
            audit_record_hash=sink_result.record_hash,
            error_type=None,
            retryable=False,
        )

    stage = (
        event.blocked_stage.value
        if event.blocked_stage is not None
        else "unknown"
    )
    reason = event.blocked_reason or "unknown"

    reason_map = {
        "authorization": (
            FinalizationReason.AUTHORIZATION_BLOCKED
        ),
        "sql_execution": (
            FinalizationReason.EXECUTION_BLOCKED
        ),
        "result_protection": (
            FinalizationReason.RESULT_PROTECTION_BLOCKED
        ),
    }

    return GovernedFinalizationResult(
        success=False,
        outcome=FinalizationOutcome.BLOCKED,
        reason_code=reason_map.get(
            stage,
            FinalizationReason.INVALID_FINALIZATION_INPUT,
        ),
        message="Governed request was blocked.",
        rows=(),
        row_count=0,
        blocked_stage=stage,
        blocked_reason=reason,
        audit_persisted=True,
        audit_event_id=event.event_id,
        audit_event_fingerprint=event.event_fingerprint,
        audit_sequence_number=sink_result.sequence_number,
        audit_record_hash=sink_result.record_hash,
        error_type="governance_blocked",
        retryable=False,
    )


def finalize_governed_request(
    *,
    context: AccessContext,
    question: str,
    authorization: AuthorizationDecision,
    runtime_config: GovernanceRuntimeConfig,
    required_tables: Sequence[str] = (),
    required_columns: Sequence[str] = (),
    metric_name: str | None = None,
    generated_sql: str | None = None,
    executed_sql: str | None = None,
    execution: GovernedExecutionResult | None = None,
    protection_contract: (
        ResultProtectionContract | None
    ) = None,
    budget: ExecutionBudgetState | None = None,
    repair_history: Sequence[Mapping[str, Any]] = (),
    event_id: str | None = None,
    occurred_at_utc: datetime | None = None,
    written_at_utc: datetime | None = None,
) -> GovernedFinalizationResult:
    """
    以 fail-closed 顺序完成结果保护、审计构建和审计持久化。

    任何成功返回的 rows 都已经通过 Result Protection，且对应
    AuditEvent 已经 fsync 到 Append-only JSONL Sink。
    """

    if not isinstance(question, str):
        return _failed(
            reason_code=(
                FinalizationReason.INVALID_FINALIZATION_INPUT
            ),
            message="question must be a string.",
        )

    if not authorization.allowed:
        if (
            execution is not None
            or generated_sql is not None
            or executed_sql is not None
        ):
            return _failed(
                reason_code=(
                    FinalizationReason
                    .INVALID_FINALIZATION_INPUT
                ),
                message=(
                    "Authorization-denied requests must not "
                    "contain SQL or execution evidence."
                ),
            )

        protection_result = None

    else:
        if execution is None:
            return _failed(
                reason_code=(
                    FinalizationReason
                    .INVALID_FINALIZATION_INPUT
                ),
                message=(
                    "Authorized requests require execution "
                    "evidence."
                ),
            )

        if (
            generated_sql is None
            or not generated_sql.strip()
            or executed_sql is None
            or not executed_sql.strip()
        ):
            return _failed(
                reason_code=(
                    FinalizationReason
                    .INVALID_FINALIZATION_INPUT
                ),
                message=(
                    "Executed requests require generated and "
                    "executed SQL evidence."
                ),
            )

        if execution.success:
            if protection_contract is None:
                return _failed(
                    reason_code=(
                        FinalizationReason
                        .INVALID_FINALIZATION_INPUT
                    ),
                    message=(
                        "Successful execution requires a result "
                        "protection contract."
                    ),
                )

            protection_result = protect_result_rows(
                context=context,
                rows=execution.rows,
                contract=protection_contract,
                tokenization_secret=(
                    runtime_config
                    .result_tokenization_secret
                    .get_secret_value()
                ),
            )
        else:
            protection_result = None

    audit_build = build_audit_event(
        context=context,
        question=question,
        authorization=authorization,
        required_tables=required_tables,
        required_columns=required_columns,
        metric_name=metric_name,
        generated_sql=generated_sql,
        executed_sql=executed_sql,
        execution=execution,
        budget=budget,
        protection=protection_result,
        repair_history=repair_history,
        audit_secret=(
            runtime_config.audit_secret.get_secret_value()
        ),
        event_id=event_id,
        occurred_at_utc=occurred_at_utc,
    )

    if not audit_build.success or audit_build.event is None:
        return _failed(
            reason_code=FinalizationReason.AUDIT_BUILD_FAILED,
            message=audit_build.message,
        )

    sink_result = append_audit_event(
        event=audit_build.event,
        config=runtime_config,
        written_at_utc=written_at_utc,
    )

    if not sink_result.success:
        return _failed(
            reason_code=(
                FinalizationReason.AUDIT_PERSISTENCE_FAILED
            ),
            message=sink_result.message,
        )

    safe_rows = (
        protection_result.rows
        if (
            protection_result is not None
            and protection_result.success
        )
        else ()
    )

    return _persisted_result(
        event=audit_build.event,
        sink_result=sink_result,
        rows=safe_rows,
    )
