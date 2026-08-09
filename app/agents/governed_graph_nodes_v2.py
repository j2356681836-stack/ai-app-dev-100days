from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal, TypedDict

from sqlalchemy.engine import Engine

from app.governance.access_context import AccessContext
from app.governance.compiled_sql_ast_enforcer_v2 import (
    CompiledSqlAstStatusV2,
    enforce_compiled_sql_ast_v2,
)
from app.governance.execution_budget import (
    BudgetDecision,
    ExecutionBudgetPolicy,
    ExecutionBudgetState,
    consume_step,
)
from app.governance.execution_policy import GovernedExecutionPolicy
from app.governance.governance_runtime import GovernanceRuntimeConfig
from app.governance.governed_planning_envelope_v2 import (
    GovernedPlanningStatusV2,
    build_governed_planning_envelope_v2,
)
from app.governance.governed_query_execution_v2 import (
    execute_governed_query_v2,
)
from app.semantic_layer.analytics_planning_service_v2 import (
    AnalyticsPlanningStatusV2,
    resolve_analytics_planning_v2,
)
from app.semantic_layer.query_plan_compiler_v2 import (
    QueryPlanCompileStatusV2,
    compile_governed_query_plan_v2,
)
from app.semantic_layer.query_plan_v2_loader import (
    get_query_plan_v2_by_name,
)
from app.semantic_layer.question_semantic_parser_v2 import LLMCall
from app.semantic_layer.time_window_resolver_v2 import (
    resolve_time_window_v2,
)
from app.text_to_sql.final_answer_v2 import (
    FinalAnswerStatusV2,
    generate_final_answer_v2,
)


class GovernedAnalystStateV2(TypedDict, total=False):
    """
    Dataset V2 candidate Graph state.

    SQL contracts may exist inside Graph state, but the final public
    result must not expose raw SQL or raw database rows.

    SQL Repair is intentionally not part of Day80 Step 1.
    """

    question: str
    context: AccessContext
    reference_date: date
    runtime_config: GovernanceRuntimeConfig
    llm_call: LLMCall | None
    execution_policy: GovernedExecutionPolicy | None
    engine_override: Engine | None
    budget_policy: ExecutionBudgetPolicy
    budget_state: ExecutionBudgetState
    budget_decision: BudgetDecision
    event_id: str | None
    occurred_at_utc: datetime | None
    written_at_utc: datetime | None

    analytics: Any
    plan: Any
    time_resolution: Any
    governed_decision: Any
    envelope: Any
    compilation_decision: Any
    compiled: Any
    ast_decision: Any
    finalization: Any
    final_answer: Any

    graph_error: str | None
    result: dict[str, Any]


def _consume_graph_step(
    state: GovernedAnalystStateV2,
    *,
    operation: str,
) -> BudgetDecision:
    return consume_step(
        policy=state["budget_policy"],
        state=state["budget_state"],
        operation=operation,
    )


def _budget_update(
    decision: BudgetDecision,
) -> GovernedAnalystStateV2:
    return {
        "budget_decision": decision,
        "budget_state": decision.state,
    }


def _budget_denied(
    state: GovernedAnalystStateV2,
) -> bool:
    decision = state.get(
        "budget_decision"
    )

    return (
        decision is not None
        and not decision.allowed
    )


def analytics_planning_node(
    state: GovernedAnalystStateV2,
) -> GovernedAnalystStateV2:
    budget = _consume_graph_step(
        state,
        operation="analytics_planning",
    )

    if not budget.allowed:
        return _budget_update(
            budget
        )

    context = state["context"]

    analytics = resolve_analytics_planning_v2(
        question=state["question"],
        allowed_metric_names=context.allowed_metrics,
        llm_call=state.get("llm_call"),
    )

    return {
        "analytics": analytics,
        "graph_error": None,
        **_budget_update(
            budget
        ),
    }


def route_analytics_planning(
    state: GovernedAnalystStateV2,
) -> Literal[
    "load_query_plan",
    "analytics_stop",
    "budget_stop",
]:
    if _budget_denied(
        state
    ):
        return "budget_stop"

    analytics = state["analytics"]

    if analytics.status == AnalyticsPlanningStatusV2.PLANNED_SINGLE:
        return "load_query_plan"

    return "analytics_stop"


def load_query_plan_node(
    state: GovernedAnalystStateV2,
) -> GovernedAnalystStateV2:
    budget = _consume_graph_step(
        state,
        operation="load_query_plan",
    )

    if not budget.allowed:
        return _budget_update(
            budget
        )

    analytics = state["analytics"]

    if len(analytics.plan_names) != 1:
        return {
            "graph_error": (
                "PLANNED_SINGLE must expose exactly one plan_name."
            ),
            **_budget_update(
                budget
            ),
        }

    plan_name = analytics.plan_names[0]
    plan = get_query_plan_v2_by_name(plan_name)

    if plan is None:
        return {
            "graph_error": (
                f"Missing Query Plan: {plan_name}"
            ),
            **_budget_update(
                budget
            ),
        }

    return {
        "plan": plan,
        "graph_error": None,
        **_budget_update(
            budget
        ),
    }


def route_plan_load(
    state: GovernedAnalystStateV2,
) -> Literal[
    "resolve_time",
    "planning_contract_stop",
    "budget_stop",
]:
    if _budget_denied(
        state
    ):
        return "budget_stop"

    if state.get("graph_error"):
        return "planning_contract_stop"

    if state.get("plan") is None:
        return "planning_contract_stop"

    return "resolve_time"


def resolve_time_node(
    state: GovernedAnalystStateV2,
) -> GovernedAnalystStateV2:
    budget = _consume_graph_step(
        state,
        operation="resolve_time",
    )

    if not budget.allowed:
        return _budget_update(
            budget
        )

    resolution = resolve_time_window_v2(
        state["question"],
        reference_date=state["reference_date"],
    )

    return {
        "time_resolution": resolution,
        **_budget_update(
            budget
        ),
    }


def route_time_resolution(
    state: GovernedAnalystStateV2,
) -> Literal[
    "governed_planning",
    "budget_stop",
]:
    if _budget_denied(
        state
    ):
        return "budget_stop"

    return "governed_planning"


def governed_planning_node(
    state: GovernedAnalystStateV2,
) -> GovernedAnalystStateV2:
    budget = _consume_graph_step(
        state,
        operation="governed_planning",
    )

    if not budget.allowed:
        return _budget_update(
            budget
        )

    decision = build_governed_planning_envelope_v2(
        context=state["context"],
        plan=state["plan"],
        time_resolution=state["time_resolution"],
    )

    update: GovernedAnalystStateV2 = {
        "governed_decision": decision,
        **_budget_update(
            budget
        ),
    }

    if (
        decision.ready
        and decision.status
        == GovernedPlanningStatusV2.READY_FOR_COMPILATION
        and decision.envelope is not None
    ):
        update["envelope"] = decision.envelope

    return update


def route_governed_planning(
    state: GovernedAnalystStateV2,
) -> Literal[
    "compile_query_plan",
    "governed_planning_stop",
    "budget_stop",
]:
    if _budget_denied(
        state
    ):
        return "budget_stop"

    decision = state["governed_decision"]

    if (
        decision.ready
        and decision.status
        == GovernedPlanningStatusV2.READY_FOR_COMPILATION
        and decision.envelope is not None
    ):
        return "compile_query_plan"

    return "governed_planning_stop"


def compile_query_plan_node(
    state: GovernedAnalystStateV2,
) -> GovernedAnalystStateV2:
    budget = _consume_graph_step(
        state,
        operation="compile_query_plan",
    )

    if not budget.allowed:
        return _budget_update(
            budget
        )

    decision = compile_governed_query_plan_v2(
        state["envelope"]
    )

    update: GovernedAnalystStateV2 = {
        "compilation_decision": decision,
        **_budget_update(
            budget
        ),
    }

    if (
        decision.success
        and decision.status
        == QueryPlanCompileStatusV2.COMPILED
        and decision.contract is not None
    ):
        update["compiled"] = decision.contract

    return update


def route_compilation(
    state: GovernedAnalystStateV2,
) -> Literal[
    "runtime_ast_gate",
    "compilation_stop",
    "budget_stop",
]:
    if _budget_denied(
        state
    ):
        return "budget_stop"

    decision = state["compilation_decision"]

    if (
        decision.success
        and decision.status
        == QueryPlanCompileStatusV2.COMPILED
        and decision.contract is not None
    ):
        return "runtime_ast_gate"

    return "compilation_stop"


def runtime_ast_gate_node(
    state: GovernedAnalystStateV2,
) -> GovernedAnalystStateV2:
    budget = _consume_graph_step(
        state,
        operation="runtime_ast_gate",
    )

    if not budget.allowed:
        return _budget_update(
            budget
        )

    decision = enforce_compiled_sql_ast_v2(
        envelope=state["envelope"],
        compiled=state["compiled"],
    )

    return {
        "ast_decision": decision,
        **_budget_update(
            budget
        ),
    }


def route_runtime_ast_gate(
    state: GovernedAnalystStateV2,
) -> Literal[
    "governed_execute",
    "ast_stop",
    "budget_stop",
]:
    if _budget_denied(
        state
    ):
        return "budget_stop"

    decision = state["ast_decision"]

    if (
        decision.success
        and decision.status
        == CompiledSqlAstStatusV2.ENFORCED
        and decision.contract is not None
    ):
        return "governed_execute"

    return "ast_stop"


def governed_execute_node(
    state: GovernedAnalystStateV2,
) -> GovernedAnalystStateV2:
    """
    execute_governed_query_v2() re-runs AST enforcement immediately
    before PostgreSQL execution. The Graph-level AST node gives visible
    workflow evidence; the service-level recheck prevents bypass.
    """
    budget = _consume_graph_step(
        state,
        operation="governed_execute",
    )

    if not budget.allowed:
        return _budget_update(
            budget
        )

    finalization = execute_governed_query_v2(
        context=state["context"],
        question=state["question"],
        envelope=state["envelope"],
        compiled=state["compiled"],
        runtime_config=state["runtime_config"],
        execution_policy=state.get("execution_policy"),
        engine_override=state.get("engine_override"),
        budget=budget.state,
        event_id=state.get("event_id"),
        occurred_at_utc=state.get("occurred_at_utc"),
        written_at_utc=state.get("written_at_utc"),
    )

    return {
        "finalization": finalization,
        **_budget_update(
            budget
        ),
    }


def route_governed_execution(
    state: GovernedAnalystStateV2,
) -> Literal[
    "final_answer",
    "budget_stop",
]:
    if _budget_denied(
        state
    ):
        return "budget_stop"

    return "final_answer"


def final_answer_node(
    state: GovernedAnalystStateV2,
) -> GovernedAnalystStateV2:
    answer = generate_final_answer_v2(
        envelope=state["envelope"],
        finalization=state["finalization"],
    )

    return {
        "final_answer": answer,
    }


def _safe_common_evidence(
    state: GovernedAnalystStateV2,
) -> dict[str, Any]:
    analytics = state.get("analytics")
    envelope = state.get("envelope")
    compiled = state.get("compiled")
    ast_decision = state.get("ast_decision")

    budget_state = state.get(
        "budget_state"
    )

    return {
        "question": state["question"],
        "budget_steps_used": (
            budget_state.steps_used
            if budget_state is not None
            else None
        ),
        "budget_exhausted": (
            budget_state.exhausted
            if budget_state is not None
            else None
        ),
        "analytics_planning_status": (
            analytics.status.value
            if analytics is not None
            else None
        ),
        "metric_name": (
            envelope.metric_name
            if envelope is not None
            else (
                analytics.metric_name
                if analytics is not None
                else None
            )
        ),
        "plan_name": (
            envelope.plan_name
            if envelope is not None
            else (
                analytics.plan_names[0]
                if (
                    analytics is not None
                    and len(analytics.plan_names) == 1
                )
                else None
            )
        ),
        "envelope_fingerprint": (
            envelope.envelope_fingerprint
            if envelope is not None
            else None
        ),
        "compiled_contract_fingerprint": (
            compiled.contract_fingerprint
            if compiled is not None
            else None
        ),
        "sql_fingerprint": (
            compiled.sql_fingerprint
            if compiled is not None
            else None
        ),
        "ast_status": (
            ast_decision.status.value
            if ast_decision is not None
            else None
        ),
    }


def budget_stop_node(
    state: GovernedAnalystStateV2,
) -> GovernedAnalystStateV2:
    decision = state["budget_decision"]

    result = {
        "success": False,
        "outcome": "blocked",
        "stop_stage": "execution_budget",
        "message": decision.message,
        "budget_reason": (
            decision.reason_code.value
        ),
        "budget_retryable": (
            decision.retryable
        ),
        **_safe_common_evidence(
            state
        ),
    }

    return {
        "result": result,
    }


def analytics_stop_node(
    state: GovernedAnalystStateV2,
) -> GovernedAnalystStateV2:
    result = {
        "success": False,
        "outcome": "stopped",
        "stop_stage": "analytics_planning",
        "message": (
            "当前请求未形成单一可执行 Query Plan，"
            "因此未进入治理执行链。"
        ),
        **_safe_common_evidence(state),
    }

    return {
        "result": result,
    }


def planning_contract_stop_node(
    state: GovernedAnalystStateV2,
) -> GovernedAnalystStateV2:
    result = {
        "success": False,
        "outcome": "failed",
        "stop_stage": "analytics_planning",
        "message": (
            state.get("graph_error")
            or "Analytics Planning contract is invalid."
        ),
        **_safe_common_evidence(state),
    }

    return {
        "result": result,
    }


def governed_planning_stop_node(
    state: GovernedAnalystStateV2,
) -> GovernedAnalystStateV2:
    decision = state["governed_decision"]

    result = {
        "success": False,
        "outcome": "blocked",
        "stop_stage": "governed_planning",
        "message": (
            "当前请求未通过执行前治理检查，"
            "因此没有进入 SQL 编译或数据库执行。"
        ),
        "detail": decision.detail,
        "governed_planning_status": decision.status.value,
        **_safe_common_evidence(state),
    }

    return {
        "result": result,
    }


def compilation_stop_node(
    state: GovernedAnalystStateV2,
) -> GovernedAnalystStateV2:
    decision = state["compilation_decision"]

    result = {
        "success": False,
        "outcome": "failed",
        "stop_stage": "compilation",
        "message": (
            "查询计划未能安全编译，因此没有进入数据库执行。"
        ),
        "detail": decision.detail,
        "compilation_status": decision.status.value,
        **_safe_common_evidence(state),
    }

    return {
        "result": result,
    }


def ast_stop_node(
    state: GovernedAnalystStateV2,
) -> GovernedAnalystStateV2:
    decision = state["ast_decision"]

    result = {
        "success": False,
        "outcome": "blocked",
        "stop_stage": "runtime_ast_enforcement",
        "message": (
            "最终 SQL 未通过 Graph Runtime AST Governance Gate，"
            "因此没有进入 PostgreSQL 执行。"
        ),
        "detail": decision.detail,
        **_safe_common_evidence(state),
    }

    return {
        "result": result,
    }


def finish_node(
    state: GovernedAnalystStateV2,
) -> GovernedAnalystStateV2:
    finalization = state["finalization"]
    answer = state["final_answer"]

    if answer.status == FinalAnswerStatusV2.ANSWERED:
        outcome = "answered"
        success = True
        stop_stage = None
    elif answer.status == FinalAnswerStatusV2.NO_DATA:
        outcome = "no_data"
        success = True
        stop_stage = None
    elif answer.status == FinalAnswerStatusV2.BLOCKED:
        outcome = "blocked"
        success = False
        stop_stage = "finalization"
    else:
        outcome = "failed"
        success = False
        stop_stage = "finalization"

    scope_summary = (
        answer.scope_disclosure.summary
        if answer.scope_disclosure is not None
        else None
    )

    result = {
        "success": success,
        "outcome": outcome,
        "stop_stage": stop_stage,
        "message": answer.answer,
        "finalization_outcome": finalization.outcome.value,
        "final_answer_status": answer.status.value,
        "scope_summary": scope_summary,
        **_safe_common_evidence(state),
    }

    return {
        "result": result,
    }
