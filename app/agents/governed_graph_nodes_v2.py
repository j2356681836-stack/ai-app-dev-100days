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
from app.semantic_layer.business_request_preflight_v2 import (
    BusinessRequestPreflightDecisionV2,
    BusinessRequestPreflightOutcomeV2,
    evaluate_business_request_preflight_v2,
)
from app.semantic_layer.dataset_availability_contract_v2 import (
    DatasetAvailabilityDecisionV2,
    DatasetAvailabilityOutcomeV2,
    evaluate_dataset_availability_v2,
    evaluate_explicit_dataset_availability_preflight_v2,
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

    business_preflight: BusinessRequestPreflightDecisionV2
    analytics: Any
    plan: Any
    time_resolution: Any
    dataset_availability: DatasetAvailabilityDecisionV2
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


def business_request_preflight_node(
    state: GovernedAnalystStateV2,
) -> GovernedAnalystStateV2:
    """
    SQL / Semantic Planning 之前的确定性业务能力边界。

    不消耗 Governed Tool / SQL Budget；它只读取用户问题和
    server-owned semantic metadata。
    """
    decision = evaluate_business_request_preflight_v2(
        state["question"]
    )

    return {
        "business_preflight": decision,
        "graph_error": None,
    }


def route_business_request_preflight(
    state: GovernedAnalystStateV2,
) -> Literal[
    "dataset_availability_fast_preflight",
    "business_preflight_stop",
]:
    decision = state["business_preflight"]

    if (
        decision.outcome
        == BusinessRequestPreflightOutcomeV2.CONTINUE
    ):
        return "dataset_availability_fast_preflight"

    return "business_preflight_stop"


def dataset_availability_fast_preflight_node(
    state: GovernedAnalystStateV2,
) -> GovernedAnalystStateV2:
    """
    Semantic / LLM Planning 之前的显式时间 Dataset Availability 快检。

    该节点不消耗 Governed Tool / SQL Budget，也不调用 LLM。
    只有“单一、显式、确定性时间窗”才会在这里做提前判断；
    其余情况继续交给原 Analytics Planning 与正式 Time Resolution。
    """
    decision = evaluate_explicit_dataset_availability_preflight_v2(
        question=state["question"],
        reference_date=state["reference_date"],
    )

    return {
        "dataset_availability": decision,
    }


def route_dataset_availability_fast_preflight(
    state: GovernedAnalystStateV2,
) -> Literal[
    "analytics_planning",
    "dataset_availability_stop",
]:
    decision = state["dataset_availability"]

    if decision.outcome in {
        DatasetAvailabilityOutcomeV2.OUTSIDE_BUSINESS_WINDOW,
        DatasetAvailabilityOutcomeV2.PARTIAL_OVERLAP,
    }:
        return "dataset_availability_stop"

    return "analytics_planning"


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
    "dataset_availability",
    "budget_stop",
]:
    if _budget_denied(
        state
    ):
        return "budget_stop"

    return "dataset_availability"


def dataset_availability_node(
    state: GovernedAnalystStateV2,
) -> GovernedAnalystStateV2:
    """
    Time Resolver 之后、Governance / SQL 之前的数据覆盖检查。

    这里不把超出范围的日期静默截断到 Dataset Window。
    完全越界或部分越界都明确停止，让用户知道可查询范围。
    """
    decision = evaluate_dataset_availability_v2(
        time_resolution=state["time_resolution"]
    )

    return {
        "dataset_availability": decision,
    }


def route_dataset_availability(
    state: GovernedAnalystStateV2,
) -> Literal[
    "governed_planning",
    "dataset_availability_stop",
]:
    decision = state["dataset_availability"]

    if decision.outcome in {
        DatasetAvailabilityOutcomeV2.AVAILABLE,
        DatasetAvailabilityOutcomeV2.NOT_APPLICABLE,
    }:
        return "governed_planning"

    return "dataset_availability_stop"


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

    analytics = state["analytics"]

    decision = build_governed_planning_envelope_v2(
        context=state["context"],
        plan=state["plan"],
        time_resolution=state["time_resolution"],
        requested_scope=(
            analytics.requested_scope_resolution
        ),
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
    business_preflight = state.get("business_preflight")
    analytics = state.get("analytics")
    dataset_availability = state.get("dataset_availability")
    envelope = state.get("envelope")
    compiled = state.get("compiled")
    ast_decision = state.get("ast_decision")

    budget_state = state.get(
        "budget_state"
    )

    return {
        "question": state["question"],
        "business_preflight_outcome": (
            business_preflight.outcome.value
            if business_preflight is not None
            else None
        ),
        "business_preflight_reason_code": (
            business_preflight.reason_code
            if business_preflight is not None
            else None
        ),
        "dataset_availability_outcome": (
            dataset_availability.outcome.value
            if dataset_availability is not None
            else None
        ),
        "dataset_availability_reason_code": (
            dataset_availability.reason_code
            if dataset_availability is not None
            else None
        ),
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
        "requested_region_codes": (
            sorted(
                analytics.requested_scope_resolution.region_codes
            )
            if analytics is not None
            else []
        ),
        "requested_channel_codes": (
            sorted(
                analytics.requested_scope_resolution.channel_codes
            )
            if analytics is not None
            else []
        ),
        "requested_scope_status": (
            analytics.requested_scope_resolution.status.value
            if analytics is not None
            else None
        ),
        "unresolved_scope_dimensions": (
            sorted(
                dimension.value
                for dimension
                in analytics.requested_scope_resolution
                .unresolved_dimensions
            )
            if analytics is not None
            else []
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


def business_preflight_stop_node(
    state: GovernedAnalystStateV2,
) -> GovernedAnalystStateV2:
    decision = state["business_preflight"]

    result = {
        "success": False,
        "outcome": "stopped",
        "stop_stage": "business_request_preflight",
        "message": (
            decision.user_message
            or "这个问题暂时不能安全查询。"
        ),
        "reason_code": decision.reason_code,
        **_safe_common_evidence(state),
    }

    return {
        "result": result,
    }


def dataset_availability_stop_node(
    state: GovernedAnalystStateV2,
) -> GovernedAnalystStateV2:
    decision = state["dataset_availability"]

    result = {
        "success": False,
        "outcome": "no_data",
        "stop_stage": "dataset_availability",
        "message": (
            decision.user_message
            or "当前请求的时间范围没有可查询的业务数据。"
        ),
        "reason_code": decision.reason_code,
        "dataset_business_start_date": (
            decision.business_window.start_date.isoformat()
        ),
        "dataset_business_end_date": (
            decision.business_window.end_date.isoformat()
        ),
        **_safe_common_evidence(state),
    }

    return {
        "result": result,
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


def _analytics_stop_business_message_v2(
    analytics,
) -> str:
    status = analytics.status

    if (
        status
        == AnalyticsPlanningStatusV2.NEEDS_SCOPE_CLARIFICATION
    ):
        return (
            "我识别到了你指定的地区或渠道，"
            "但暂时无法可靠映射到当前数据范围。"
            "请换用系统中已有的地区或渠道名称后再试。"
        )

    if (
        status
        == AnalyticsPlanningStatusV2.NEEDS_METRIC_CLARIFICATION
    ):
        return (
            "这个问题还需要确认指标口径后才能查询。"
            "请补充你具体想看的业务指标。"
        )

    if status == AnalyticsPlanningStatusV2.UNSUPPORTED_METRIC:
        return (
            "这个问题暂不支持查询。"
            "当前系统还没有找到可安全执行的指标口径。"
        )

    if status == AnalyticsPlanningStatusV2.MULTIPLE_INTENTS:
        return (
            "这个问题包含多个分析目标，"
            "当前还不能一次安全完成。"
            "你可以先拆成一个问题查询；"
            "系统不会为了给出结果而混合不同分析口径。"
        )

    if status in {
        AnalyticsPlanningStatusV2.MISSING_GRAIN,
        AnalyticsPlanningStatusV2.AMBIGUOUS_GRAIN,
    }:
        return (
            "这个问题还需要确认你希望按什么维度查看，"
            "例如整体、渠道、地区或品类。"
        )

    if status == AnalyticsPlanningStatusV2.UNSUPPORTED_GRAIN:
        return (
            "这个问题的分析维度暂不支持直接查询。"
            "请改用当前已支持的整体、渠道、地区或品类维度。"
        )

    if status == AnalyticsPlanningStatusV2.EVIDENCE_CONFLICT:
        return (
            "系统对这个问题的指标理解存在冲突，"
            "为了避免返回错误数据，本次没有继续查询。"
            "请把指标或分析范围说得更明确一些。"
        )

    if status == AnalyticsPlanningStatusV2.PARSE_FAILED:
        return (
            "暂时没能可靠理解这个问题。"
            "请换一种更明确的业务表达后再试。"
        )

    if status == AnalyticsPlanningStatusV2.CATALOG_CONFLICT:
        return (
            "当前查询配置存在冲突，暂时无法安全执行。"
            "这不是数据本身的问题。"
        )

    if status == AnalyticsPlanningStatusV2.METRIC_NOT_FOUND:
        return (
            "这个问题暂时没有可用的查询指标。"
            "请换一个已定义的业务指标后再试。"
        )

    if status == AnalyticsPlanningStatusV2.PLANNED_MULTIPLE:
        return (
            "这个问题需要多个分析步骤，"
            "当前版本还不能一次完成。"
            "你可以先拆成单个问题查询。"
        )

    return (
        "这个问题目前还不能安全形成查询。"
        "请补充更明确的指标、时间或分析维度后再试。"
    )


def analytics_stop_node(
    state: GovernedAnalystStateV2,
) -> GovernedAnalystStateV2:
    analytics = state["analytics"]

    result = {
        "success": False,
        "outcome": "stopped",
        "stop_stage": "analytics_planning",
        "message": _analytics_stop_business_message_v2(analytics),
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
