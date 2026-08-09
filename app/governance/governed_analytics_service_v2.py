from __future__ import annotations

from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict
from sqlalchemy.engine import Engine

from app.governance.access_context import AccessContext
from app.governance.execution_budget import ExecutionBudgetState
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


class GovernedAnalyticsOutcomeV2(str, Enum):
    ANSWERED = "answered"
    NO_DATA = "no_data"
    NEEDS_CLARIFICATION = "needs_clarification"
    UNSUPPORTED = "unsupported"
    MULTIPLE_INTENTS = "multiple_intents"
    BLOCKED = "blocked"
    FAILED = "failed"


class GovernedAnalyticsStopStageV2(str, Enum):
    ANALYTICS_PLANNING = "analytics_planning"
    GOVERNED_PLANNING = "governed_planning"
    COMPILATION = "compilation"
    FINALIZATION = "finalization"


class GovernedAnalyticsResultV2(BaseModel):
    """
    Service-level V2 AI-chain result.

    It exposes stage evidence and fingerprints, but not raw SQL or raw
    database rows.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    outcome: GovernedAnalyticsOutcomeV2
    question: str
    user_message: str

    stop_stage: GovernedAnalyticsStopStageV2 | None = None
    detail: str | None = None

    analytics_planning_status: AnalyticsPlanningStatusV2
    candidates: tuple[str, ...] = ()

    metric_name: str | None = None
    plan_name: str | None = None

    governed_planning_status: GovernedPlanningStatusV2 | None = None
    compilation_status: QueryPlanCompileStatusV2 | None = None

    envelope_fingerprint: str | None = None
    compiled_contract_fingerprint: str | None = None
    sql_fingerprint: str | None = None

    finalization_outcome: str | None = None
    final_answer_status: FinalAnswerStatusV2 | None = None
    scope_summary: str | None = None


_ANALYTICS_STOP_OUTCOME = {
    AnalyticsPlanningStatusV2.NEEDS_METRIC_CLARIFICATION:
        GovernedAnalyticsOutcomeV2.NEEDS_CLARIFICATION,
    AnalyticsPlanningStatusV2.UNSUPPORTED_METRIC:
        GovernedAnalyticsOutcomeV2.UNSUPPORTED,
    AnalyticsPlanningStatusV2.MULTIPLE_INTENTS:
        GovernedAnalyticsOutcomeV2.MULTIPLE_INTENTS,
    AnalyticsPlanningStatusV2.UNSUPPORTED_GRAIN:
        GovernedAnalyticsOutcomeV2.UNSUPPORTED,
    AnalyticsPlanningStatusV2.METRIC_NOT_FOUND:
        GovernedAnalyticsOutcomeV2.UNSUPPORTED,
}


def _analytics_stop_message(
    status: AnalyticsPlanningStatusV2,
    *,
    candidates: tuple[str, ...],
) -> str:
    if status == AnalyticsPlanningStatusV2.NEEDS_METRIC_CLARIFICATION:
        if candidates:
            return (
                "当前问题需要进一步明确业务指标。"
                "可选指标："
                + "、".join(candidates)
                + "。"
            )
        return "当前问题需要进一步明确业务指标。"

    if status == AnalyticsPlanningStatusV2.MULTIPLE_INTENTS:
        return (
            "当前问题包含多个独立分析意图，"
            "请拆分后分别查询。"
        )

    if status == AnalyticsPlanningStatusV2.PLANNED_MULTIPLE:
        return (
            "当前服务级 V2 链路暂不执行多 Query Plan 请求。"
        )

    if status in {
        AnalyticsPlanningStatusV2.UNSUPPORTED_METRIC,
        AnalyticsPlanningStatusV2.UNSUPPORTED_GRAIN,
        AnalyticsPlanningStatusV2.METRIC_NOT_FOUND,
    }:
        return "当前 Dataset V2 暂不支持该分析请求。"

    return "当前问题未能形成可执行的分析计划。"


def execute_governed_analytics_v2(
    *,
    context: AccessContext,
    question: str,
    reference_date: date,
    runtime_config: GovernanceRuntimeConfig,
    llm_call: LLMCall | None = None,
    execution_policy: GovernedExecutionPolicy | None = None,
    engine_override: Engine | None = None,
    budget: ExecutionBudgetState | None = None,
    event_id: str | None = None,
    occurred_at_utc: datetime | None = None,
    written_at_utc: datetime | None = None,
) -> GovernedAnalyticsResultV2:
    """
    Dataset V2 service-level AI-chain.

    Question
    -> Analytics Planning
    -> Query Plan load
    -> Time Resolution
    -> Governed Planning Envelope
    -> Deterministic Compilation
    -> Governed Execution / AST / Finalization
    -> Final Answer V2
    """
    if not isinstance(context, AccessContext):
        raise TypeError("context must be AccessContext.")

    if not isinstance(question, str):
        raise TypeError("question must be a string.")

    if not isinstance(reference_date, date):
        raise TypeError("reference_date must be date.")

    if not isinstance(runtime_config, GovernanceRuntimeConfig):
        raise TypeError(
            "runtime_config must be GovernanceRuntimeConfig."
        )

    analytics = resolve_analytics_planning_v2(
        question=question,
        allowed_metric_names=context.allowed_metrics,
        llm_call=llm_call,
    )

    candidates = analytics.semantic_decision.candidates

    if analytics.status != AnalyticsPlanningStatusV2.PLANNED_SINGLE:
        if analytics.status == AnalyticsPlanningStatusV2.PLANNED_MULTIPLE:
            outcome = GovernedAnalyticsOutcomeV2.UNSUPPORTED
        else:
            outcome = _ANALYTICS_STOP_OUTCOME.get(
                analytics.status,
                GovernedAnalyticsOutcomeV2.FAILED,
            )

        return GovernedAnalyticsResultV2(
            outcome=outcome,
            question=question,
            user_message=_analytics_stop_message(
                analytics.status,
                candidates=candidates,
            ),
            stop_stage=(
                GovernedAnalyticsStopStageV2.ANALYTICS_PLANNING
            ),
            detail=analytics.detail,
            analytics_planning_status=analytics.status,
            candidates=candidates,
            metric_name=analytics.metric_name,
            plan_name=(
                analytics.plan_names[0]
                if len(analytics.plan_names) == 1
                else None
            ),
        )

    if len(analytics.plan_names) != 1:
        return GovernedAnalyticsResultV2(
            outcome=GovernedAnalyticsOutcomeV2.FAILED,
            question=question,
            user_message="分析计划合同异常，未进入数据库执行。",
            stop_stage=(
                GovernedAnalyticsStopStageV2.ANALYTICS_PLANNING
            ),
            detail=(
                "PLANNED_SINGLE must expose exactly one plan_name."
            ),
            analytics_planning_status=analytics.status,
            candidates=candidates,
            metric_name=analytics.metric_name,
        )

    plan_name = analytics.plan_names[0]
    plan = get_query_plan_v2_by_name(plan_name)

    if plan is None:
        return GovernedAnalyticsResultV2(
            outcome=GovernedAnalyticsOutcomeV2.FAILED,
            question=question,
            user_message="查询计划不存在，未进入数据库执行。",
            stop_stage=(
                GovernedAnalyticsStopStageV2.ANALYTICS_PLANNING
            ),
            detail=f"Missing Query Plan: {plan_name}",
            analytics_planning_status=analytics.status,
            candidates=candidates,
            metric_name=analytics.metric_name,
            plan_name=plan_name,
        )

    time_resolution = resolve_time_window_v2(
        question,
        reference_date=reference_date,
    )

    governed = build_governed_planning_envelope_v2(
        context=context,
        plan=plan,
        time_resolution=time_resolution,
    )

    if (
        governed.status
        != GovernedPlanningStatusV2.READY_FOR_COMPILATION
        or not governed.ready
        or governed.envelope is None
    ):
        return GovernedAnalyticsResultV2(
            outcome=GovernedAnalyticsOutcomeV2.BLOCKED,
            question=question,
            user_message=(
                "当前请求未通过执行前治理检查，"
                "因此没有进入数据库执行。"
            ),
            stop_stage=(
                GovernedAnalyticsStopStageV2.GOVERNED_PLANNING
            ),
            detail=governed.detail,
            analytics_planning_status=analytics.status,
            candidates=candidates,
            metric_name=analytics.metric_name,
            plan_name=plan_name,
            governed_planning_status=governed.status,
        )

    envelope = governed.envelope

    compilation = compile_governed_query_plan_v2(
        envelope
    )

    if (
        compilation.status
        != QueryPlanCompileStatusV2.COMPILED
        or compilation.contract is None
    ):
        return GovernedAnalyticsResultV2(
            outcome=GovernedAnalyticsOutcomeV2.FAILED,
            question=question,
            user_message=(
                "查询计划未能安全编译，因此没有进入数据库执行。"
            ),
            stop_stage=(
                GovernedAnalyticsStopStageV2.COMPILATION
            ),
            detail=compilation.detail,
            analytics_planning_status=analytics.status,
            candidates=candidates,
            metric_name=analytics.metric_name,
            plan_name=plan_name,
            governed_planning_status=governed.status,
            compilation_status=compilation.status,
            envelope_fingerprint=envelope.envelope_fingerprint,
        )

    compiled = compilation.contract

    finalization = execute_governed_query_v2(
        context=context,
        question=question,
        envelope=envelope,
        compiled=compiled,
        runtime_config=runtime_config,
        execution_policy=execution_policy,
        engine_override=engine_override,
        budget=budget,
        event_id=event_id,
        occurred_at_utc=occurred_at_utc,
        written_at_utc=written_at_utc,
    )

    final_answer = generate_final_answer_v2(
        envelope=envelope,
        finalization=finalization,
    )

    if final_answer.status == FinalAnswerStatusV2.ANSWERED:
        outcome = GovernedAnalyticsOutcomeV2.ANSWERED
        stop_stage = None
    elif final_answer.status == FinalAnswerStatusV2.NO_DATA:
        outcome = GovernedAnalyticsOutcomeV2.NO_DATA
        stop_stage = None
    elif final_answer.status == FinalAnswerStatusV2.BLOCKED:
        outcome = GovernedAnalyticsOutcomeV2.BLOCKED
        stop_stage = GovernedAnalyticsStopStageV2.FINALIZATION
    else:
        outcome = GovernedAnalyticsOutcomeV2.FAILED
        stop_stage = GovernedAnalyticsStopStageV2.FINALIZATION

    scope_summary = (
        final_answer.scope_disclosure.summary
        if final_answer.scope_disclosure is not None
        else None
    )

    return GovernedAnalyticsResultV2(
        outcome=outcome,
        question=question,
        user_message=final_answer.answer,
        stop_stage=stop_stage,
        detail=finalization.message,
        analytics_planning_status=analytics.status,
        candidates=candidates,
        metric_name=envelope.metric_name,
        plan_name=envelope.plan_name,
        governed_planning_status=governed.status,
        compilation_status=compilation.status,
        envelope_fingerprint=envelope.envelope_fingerprint,
        compiled_contract_fingerprint=(
            compiled.contract_fingerprint
        ),
        sql_fingerprint=compiled.sql_fingerprint,
        finalization_outcome=finalization.outcome.value,
        final_answer_status=final_answer.status,
        scope_summary=scope_summary,
    )
