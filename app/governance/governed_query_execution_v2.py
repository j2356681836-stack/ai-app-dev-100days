from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.engine import Engine

from app.db.governed_sql_runner import run_governed_sql
from app.governance.access_context import AccessContext
from app.governance.compiled_sql_ast_enforcer_v2 import (
    CompiledSqlAstStatusV2,
    enforce_compiled_sql_ast_v2,
)
from app.governance.execution_budget import ExecutionBudgetState
from app.governance.execution_policy import (
    GovernedExecutionPolicy,
)
from app.governance.governance_runtime import (
    GovernanceRuntimeConfig,
)
from app.governance.governed_finalization import (
    FinalizationOutcome,
    FinalizationReason,
    GovernedFinalizationResult,
    finalize_governed_request,
)
from app.governance.governed_planning_envelope_v2 import (
    GovernedPlanningEnvelopeV2,
)
from app.semantic_layer.query_plan_compiler_v2 import (
    CompiledQueryPlanContractV2,
)


def _fail_before_execution(
    message: str,
) -> GovernedFinalizationResult:
    """
    Fail closed before SQL execution.

    Pre-execution contract failures do not contain trustworthy database
    execution evidence, so they cannot be represented as an audited
    execution/protection block by the current Audit Event V2 schema.
    They return no rows and claim no audit persistence.
    """
    return GovernedFinalizationResult(
        success=False,
        outcome=FinalizationOutcome.FAILED,
        reason_code=(
            FinalizationReason.INVALID_FINALIZATION_INPUT
        ),
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


def _validate_context_envelope_linkage(
    *,
    context: AccessContext,
    envelope: GovernedPlanningEnvelopeV2,
    policy: GovernedExecutionPolicy,
) -> str | None:
    comparisons: dict[
        str,
        tuple[Any, Any],
    ] = {
        "request_id": (
            context.request_id,
            envelope.request_id,
        ),
        "actor_id": (
            context.actor_id,
            envelope.actor_id,
        ),
        "dataset_name": (
            context.dataset_name,
            envelope.dataset_name,
        ),
        "target_schema": (
            context.target_schema,
            envelope.target_schema,
        ),
        "authorization_policy_version": (
            context.policy_version,
            envelope.authorization_policy_version,
        ),
        "execution_policy_target_schema": (
            policy.target_schema,
            envelope.target_schema,
        ),
    }

    mismatches = {
        field: {
            "context_or_policy": expected,
            "envelope": actual,
        }
        for field, (
            expected,
            actual,
        ) in comparisons.items()
        if expected != actual
    }

    if mismatches:
        return (
            "Access Context, execution policy and governed "
            "envelope linkage failed. "
            f"mismatches={mismatches}"
        )

    if not envelope.metric_authorization.allowed:
        return (
            "Governed envelope does not contain allowed metric "
            "authorization."
        )

    if not envelope.resource_authorization.allowed:
        return (
            "Governed envelope does not contain allowed resource "
            "authorization."
        )

    return None


def execute_governed_query_v2(
    *,
    context: AccessContext,
    question: str,
    envelope: GovernedPlanningEnvelopeV2,
    compiled: CompiledQueryPlanContractV2,
    runtime_config: GovernanceRuntimeConfig,
    execution_policy: GovernedExecutionPolicy | None = None,
    engine_override: Engine | None = None,
    budget: ExecutionBudgetState | None = None,
    event_id: str | None = None,
    occurred_at_utc: datetime | None = None,
    written_at_utc: datetime | None = None,
) -> GovernedFinalizationResult:
    """
    Execute and finalize one Query Plan V2 request.

    Security boundary:
    - accepts no raw SQL argument;
    - re-runs PostgreSQL AST enforcement immediately before execution;
    - executes only compiled.sql with compiled.parameter_mapping();
    - never returns GovernedExecutionResult to the caller;
    - releases rows only through GovernedFinalizationResult after
      Result Protection and Audit Persistence both succeed.

    Current non-goals:
    - no SQL Repair;
    - no LangGraph integration;
    - no automatic retry;
    - no pre-execution AST failure audit schema extension.
    """
    if not isinstance(
        context,
        AccessContext,
    ):
        raise TypeError(
            "context must be AccessContext."
        )

    if not isinstance(
        envelope,
        GovernedPlanningEnvelopeV2,
    ):
        raise TypeError(
            "envelope must be GovernedPlanningEnvelopeV2."
        )

    if not isinstance(
        compiled,
        CompiledQueryPlanContractV2,
    ):
        raise TypeError(
            "compiled must be CompiledQueryPlanContractV2."
        )

    if not isinstance(
        runtime_config,
        GovernanceRuntimeConfig,
    ):
        raise TypeError(
            "runtime_config must be GovernanceRuntimeConfig."
        )

    if not isinstance(
        question,
        str,
    ):
        return _fail_before_execution(
            "question must be a string."
        )

    active_policy = (
        execution_policy
        if execution_policy is not None
        else GovernedExecutionPolicy()
    )

    linkage_error = (
        _validate_context_envelope_linkage(
            context=context,
            envelope=envelope,
            policy=active_policy,
        )
    )

    if linkage_error is not None:
        return _fail_before_execution(
            linkage_error
        )

    ast_decision = enforce_compiled_sql_ast_v2(
        envelope=envelope,
        compiled=compiled,
    )

    if (
        not ast_decision.success
        or ast_decision.status
        != CompiledSqlAstStatusV2.ENFORCED
        or ast_decision.contract is None
    ):
        return _fail_before_execution(
            "Compiled SQL failed the mandatory pre-execution "
            "PostgreSQL AST gate. "
            f"status={ast_decision.status.value}"
        )

    ast_contract = ast_decision.contract

    if (
        ast_contract.compiled_contract_fingerprint
        != compiled.contract_fingerprint
        or ast_contract.sql_fingerprint
        != compiled.sql_fingerprint
        or ast_contract.envelope_fingerprint
        != envelope.envelope_fingerprint
    ):
        return _fail_before_execution(
            "AST enforcement evidence does not match the "
            "governed envelope and compiled SQL contract."
        )

    execution = run_governed_sql(
        sql=compiled.sql,
        parameters=compiled.parameter_mapping(),
        policy=active_policy,
        engine_override=engine_override,
    )

    # The raw execution rows remain inside this function. Only the
    # finalization result may cross the governance boundary.
    return finalize_governed_request(
        context=context,
        question=question,
        authorization=(
            envelope.resource_authorization
        ),
        runtime_config=runtime_config,
        required_tables=tuple(
            sorted(
                envelope.required_tables
            )
        ),
        required_columns=tuple(
            sorted(
                envelope.required_columns
            )
        ),
        metric_name=envelope.metric_name,
        generated_sql=compiled.sql,
        executed_sql=compiled.sql,
        execution=execution,
        protection_contract=(
            envelope.result_protection_contract
        ),
        budget=budget,
        repair_history=(),
        event_id=event_id,
        occurred_at_utc=occurred_at_utc,
        written_at_utc=written_at_utc,
    )
