from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, model_validator
from sqlalchemy.engine import Engine

from app.agents.evidence_pack_builder_v2 import (
    EvidenceBuildStatusV2,
    build_governed_query_evidence_record_v2,
)
from app.agents.evidence_pack_delivery_v2 import (
    EvidencePackDeliveryV2,
    assemble_evidence_pack_delivery_v2,
    build_metric_definition_snapshot_v2,
)
from app.agents.evidence_pack_v2 import EvidencePackV2
from app.agents.governed_analyst_graph_v2 import (
    build_governed_analyst_graph_v2,
)
from app.agents.governed_graph_nodes_v2 import GovernedAnalystStateV2
from app.agents.investigation_contracts_v2 import (
    AnalysisModeV2,
    AnalysisScopeV2,
    EvidenceReferenceV2,
    InsightContractV2,
    SupportedInsightStatementV2,
    ToolContractV2,
)
from app.delivery.decision_console_view_v2 import (
    DecisionConsoleViewV2,
    build_decision_console_view_v2,
)
from app.delivery.executive_decision_brief_v2 import (
    ExecutiveDecisionBriefPreviewV2,
    build_executive_decision_brief_preview_v2,
)
from app.governance.access_context import AccessContext
from app.governance.execution_budget import (
    ExecutionBudgetPolicy,
    ExecutionBudgetState,
    create_initial_budget_state,
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
from app.semantic_layer.query_plan_compiler_v2 import (
    QueryPlanCompileStatusV2,
    compile_governed_query_plan_v2,
)
from app.semantic_layer.query_plan_v2_loader import (
    get_query_plan_v2_by_name,
)
from app.semantic_layer.question_semantic_parser_v2 import LLMCall
from app.semantic_layer.time_comparison_contract_v2 import (
    TimeWindowReferenceV2,
)
from app.semantic_layer.time_window_resolver_v2 import (
    DEFAULT_TIME_WINDOW_POLICY_V2,
    TimeExpressionTypeV2,
    TimeWindowResolutionSourceV2,
    TimeWindowResolutionStatusV2,
    TimeWindowResolutionV2,
)
from app.text_to_sql.final_answer_v2 import (
    FinalAnswerStatusV2,
    generate_final_answer_v2,
)


RUNTIME_DELIVERY_BRIDGE_VERSION = "runtime_delivery_bridge_v2_0"


class RuntimeDeliveryBridgeStatusV2(str, Enum):
    READY = "ready"
    GRAPH_STOPPED = "graph_stopped"
    INVALID_RUNTIME_STATE = "invalid_runtime_state"
    EVIDENCE_BUILD_FAILED = "evidence_build_failed"


class ApprovedGovernedQueryToolBindingV2(BaseModel):
    """
    Server-trusted Query Plan -> Tool Contract binding.

    Day89 Bridge 不允许 UI 临时创造 Tool identity。
    调用方必须显式提供一个已经批准的静态绑定。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    plan_name: str
    tool_contract: ToolContractV2

    @model_validator(mode="after")
    def validate_binding(
        self,
    ) -> "ApprovedGovernedQueryToolBindingV2":
        if not self.plan_name.strip():
            raise ValueError("plan_name 不能为空。")

        if (
            self.tool_contract.executor_binding
            != "execute_governed_query_v2"
        ):
            raise ValueError(
                "Runtime Delivery Bridge 只接受 "
                "execute_governed_query_v2 Tool Contract。"
            )

        return self


class RuntimeDeliveryBridgeResultV2(BaseModel):
    """
    Day89 Trusted Runtime -> Business Delivery 的安全结果。

    不返回 GovernedAnalystStateV2，也不返回 raw SQL。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        arbitrary_types_allowed=True,
    )

    contract_version: str = RUNTIME_DELIVERY_BRIDGE_VERSION

    status: RuntimeDeliveryBridgeStatusV2
    message: str

    safe_runtime_result: dict[str, Any]

    delivery: EvidencePackDeliveryV2 | None = None
    console_view: DecisionConsoleViewV2 | None = None
    executive_brief: ExecutiveDecisionBriefPreviewV2 | None = None

    @model_validator(mode="after")
    def validate_result(
        self,
    ) -> "RuntimeDeliveryBridgeResultV2":
        if not self.message.strip():
            raise ValueError("Bridge message 不能为空。")

        artifacts = (
            self.delivery,
            self.console_view,
            self.executive_brief,
        )

        if self.status == RuntimeDeliveryBridgeStatusV2.READY:
            if any(item is None for item in artifacts):
                raise ValueError(
                    "READY 必须同时返回 Delivery / Console / Brief。"
                )
        else:
            if any(item is not None for item in artifacts):
                raise ValueError(
                    "非 READY 状态不能释放半成品 Delivery artifacts。"
                )

        return self


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_metric_definition_v2(
    metric_name: str,
):
    path = (
        _project_root()
        / "metadata"
        / "beauty_bi_v2"
        / "business_metrics.yaml"
    )

    payload = yaml.safe_load(
        path.read_text(encoding="utf-8")
    )

    return build_metric_definition_snapshot_v2(
        metadata_catalog=payload,
        metric_name=metric_name,
    )


def _compiled_window_v2(
    compiled,
) -> TimeWindowReferenceV2 | None:
    """
    从 Compiled Contract 恢复实际 SQL 使用的分析时间窗。

    不接受 UI / question 重新解释时间。
    """

    parameters = compiled.parameter_mapping()

    start = parameters.get("analysis_start_date")
    end = parameters.get("analysis_end_date")

    if isinstance(start, datetime):
        start = start.date()

    if isinstance(end, datetime):
        end = end.date()

    if not isinstance(start, date) or not isinstance(end, date):
        return None

    return TimeWindowReferenceV2(
        start_date=start,
        end_date=end,
    )


def _safe_public_result(
    state: GovernedAnalystStateV2,
) -> dict[str, Any]:
    result = state.get("result")

    if isinstance(result, dict):
        return dict(result)

    return {
        "success": False,
        "outcome": "failed",
        "stop_stage": "runtime_delivery_bridge",
        "message": "Governed Graph 没有产生安全 public result。",
    }


def _failed(
    *,
    status: RuntimeDeliveryBridgeStatusV2,
    message: str,
    state: GovernedAnalystStateV2,
) -> RuntimeDeliveryBridgeResultV2:
    return RuntimeDeliveryBridgeResultV2(
        status=status,
        message=message,
        safe_runtime_result=_safe_public_result(state),
    )


def build_runtime_delivery_from_governed_state_v2(
    *,
    state: GovernedAnalystStateV2,
    approved_tool_binding: ApprovedGovernedQueryToolBindingV2,
) -> RuntimeDeliveryBridgeResultV2:
    """
    将已经完成的 Governed Graph State 投影成 Day89 Delivery。

    当前 v2_0 只闭合“单次成功 Governed Query -> FACT Delivery”。

    不负责：
    - 重新执行 SQL；
    - 重新解析业务语义或时间；
    - Anomaly / Contribution 计算；
    - Agentic Investigation Loop；
    - Periodic Report 时间合同生成。
    """

    public = _safe_public_result(state)

    if not public.get("success"):
        return _failed(
            status=RuntimeDeliveryBridgeStatusV2.GRAPH_STOPPED,
            message=str(
                public.get("message")
                or "Governed Graph 未形成可释放业务结果。"
            ),
            state=state,
        )

    envelope = state.get("envelope")
    compiled = state.get("compiled")
    finalization = state.get("finalization")
    final_answer = state.get("final_answer")

    if (
        envelope is None
        or compiled is None
        or finalization is None
        or final_answer is None
    ):
        return _failed(
            status=(
                RuntimeDeliveryBridgeStatusV2.INVALID_RUNTIME_STATE
            ),
            message=(
                "Graph success result 缺少 envelope / compiled / "
                "finalization / final_answer 内部可信对象。"
            ),
            state=state,
        )

    if (
        final_answer.status
        != FinalAnswerStatusV2.ANSWERED
    ):
        return _failed(
            status=RuntimeDeliveryBridgeStatusV2.GRAPH_STOPPED,
            message=final_answer.answer,
            state=state,
        )

    if approved_tool_binding.plan_name != envelope.plan_name:
        return _failed(
            status=(
                RuntimeDeliveryBridgeStatusV2.INVALID_RUNTIME_STATE
            ),
            message=(
                "Approved Tool Binding 与实际 Query Plan 不一致："
                f"approved={approved_tool_binding.plan_name}; "
                f"actual={envelope.plan_name}"
            ),
            state=state,
        )

    actual_window = _compiled_window_v2(compiled)

    if actual_window is None:
        return _failed(
            status=(
                RuntimeDeliveryBridgeStatusV2.INVALID_RUNTIME_STATE
            ),
            message=(
                "Compiled Contract 缺少可恢复的实际 analysis window。"
            ),
            state=state,
        )

    scope_summary = (
        final_answer.scope_disclosure.summary
        if final_answer.scope_disclosure is not None
        else None
    )

    analysis_scope = AnalysisScopeV2(
        metric_name=envelope.metric_name,
        analysis_window=actual_window,
        result_grain=envelope.result_grain,
        scope_summary=scope_summary,
    )

    audit_event_id = finalization.audit_event_id

    if audit_event_id is None:
        return _failed(
            status=(
                RuntimeDeliveryBridgeStatusV2.INVALID_RUNTIME_STATE
            ),
            message="成功结果缺少 audit_event_id。",
            state=state,
        )

    tool = approved_tool_binding.tool_contract

    evidence_reference = EvidenceReferenceV2(
        evidence_id=f"ev_{audit_event_id}",
        source=(
            f"tool:{tool.identity.name}"
            f"@{tool.identity.version}"
        ),
        description=(
            f"{envelope.query_plan.chinese_name} "
            "真实 Governed Query Evidence。"
        ),
    )

    build = build_governed_query_evidence_record_v2(
        analysis_scope=analysis_scope,
        evidence_reference=evidence_reference,
        tool_contract=tool,
        envelope=envelope,
        compiled=compiled,
        finalization=finalization,
    )

    if (
        not build.success
        or build.status != EvidenceBuildStatusV2.BUILT
        or build.record is None
    ):
        return _failed(
            status=(
                RuntimeDeliveryBridgeStatusV2.EVIDENCE_BUILD_FAILED
            ),
            message=(
                build.detail
                or "Governed Query Evidence Build failed."
            ),
            state=state,
        )

    fact = SupportedInsightStatementV2(
        statement=final_answer.answer,
        evidence_ids=(evidence_reference.evidence_id,),
    )

    insight = InsightContractV2(
        analysis_mode=AnalysisModeV2.FACT,
        analysis_scope=analysis_scope,
        confirmed_facts=(fact,),
        evidence=(evidence_reference,),
    )

    pack = EvidencePackV2(
        pack_id=f"pack_{audit_event_id}",
        analysis_scope=analysis_scope,
        insight=insight,
        evidence_records=(build.record,),
    )

    delivery = assemble_evidence_pack_delivery_v2(
        evidence_pack=pack,
        metric_definition=_load_metric_definition_v2(
            envelope.metric_name
        ),
    )

    breakdown_id = (
        evidence_reference.evidence_id
        if envelope.result_grain != "overall"
        else None
    )

    console_view = build_decision_console_view_v2(
        delivery=delivery,
        breakdown_evidence_id=breakdown_id,
    )

    brief = build_executive_decision_brief_preview_v2(
        request_subject=state["question"],
        delivery=delivery,
        console_view=console_view,
    )

    return RuntimeDeliveryBridgeResultV2(
        status=RuntimeDeliveryBridgeStatusV2.READY,
        message=final_answer.answer,
        safe_runtime_result=public,
        delivery=delivery,
        console_view=console_view,
        executive_brief=brief,
    )




def _structured_time_resolution_v2(
    *,
    window: TimeWindowReferenceV2,
) -> TimeWindowResolutionV2:
    """
    将 server-trusted TimeWindowReferenceV2 直接投影成 Time Resolution。

    用于 Periodic Report / trusted server follow-up：
    - 不重新解析自然语言时间；
    - 不调用 LLM；
    - 仍继续进入正式 Time Binding / Governance。
    """

    policy = DEFAULT_TIME_WINDOW_POLICY_V2

    return TimeWindowResolutionV2(
        status=TimeWindowResolutionStatusV2.RESOLVED,
        source=TimeWindowResolutionSourceV2.EXPLICIT,
        expression_type=TimeExpressionTypeV2.EXPLICIT_DATE_RANGE,
        reference_date=window.end_date,
        requested_start_date=window.start_date,
        requested_end_date=window.end_date,
        effective_start_date=window.start_date,
        effective_end_date=window.end_date,
        policy_name=policy.policy_name,
        policy_version=policy.policy_version,
        evidence=(),
        adjustment_reasons=(),
        notice_required=False,
        user_notice=None,
        error=None,
    )


def invoke_governed_plan_delivery_v2(
    *,
    context: AccessContext,
    plan_name: str,
    analysis_window: TimeWindowReferenceV2,
    question: str,
    runtime_config: GovernanceRuntimeConfig,
    approved_tool_binding: ApprovedGovernedQueryToolBindingV2,
    execution_policy: GovernedExecutionPolicy | None = None,
    engine_override: Engine | None = None,
    event_id: str | None = None,
    occurred_at_utc: datetime | None = None,
    written_at_utc: datetime | None = None,
) -> RuntimeDeliveryBridgeResultV2:
    """
    Structured server-owned Query Plan -> Business Delivery。

    适用场景：
    - Periodic Report 已经结构化确定 metric / plan / window；
    - trusted follow-up（例如 Breakdown 对应的 Overall Summary）。

    它绕过的只有：
    - Natural-language Semantic Decision；
    - Result Grain NLP Resolution；
    - Query Plan NLP Selection；
    - Natural-language Time Parsing。

    它不会绕过：
    - AccessContext authorization；
    - Time / Scope Binding；
    - Governed Planning Envelope；
    - deterministic SQL Compilation；
    - execute_governed_query_v2 内的 AST recheck；
    - Result Protection；
    - Audit Persistence；
    - Evidence Builder。
    """

    safe_base = {
        "success": False,
        "outcome": "stopped",
        "stop_stage": "structured_plan_preflight",
        "message": "",
        "question": question,
        "planning_source": "server_structured_contract",
        "requested_plan_name": plan_name,
        "requested_start_date": analysis_window.start_date.isoformat(),
        "requested_end_date": analysis_window.end_date.isoformat(),
    }

    if approved_tool_binding.plan_name != plan_name:
        message = (
            "Approved Tool Binding 与 structured plan_name 不一致："
            f"approved={approved_tool_binding.plan_name}; "
            f"requested={plan_name}"
        )
        safe_base["message"] = message
        return RuntimeDeliveryBridgeResultV2(
            status=RuntimeDeliveryBridgeStatusV2.INVALID_RUNTIME_STATE,
            message=message,
            safe_runtime_result=safe_base,
        )

    plan = get_query_plan_v2_by_name(plan_name)

    if plan is None:
        message = f"Structured Query Plan 不存在：{plan_name}"
        safe_base["message"] = message
        return RuntimeDeliveryBridgeResultV2(
            status=RuntimeDeliveryBridgeStatusV2.INVALID_RUNTIME_STATE,
            message=message,
            safe_runtime_result=safe_base,
        )

    time_resolution = _structured_time_resolution_v2(
        window=analysis_window,
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
        message = (
            "Structured Query Plan 未通过 Governed Planning："
            f"{governed.status.value}; "
            f"{governed.detail or ''}"
        )
        safe_base.update(
            {
                "stop_stage": "governed_planning",
                "message": message,
                "metric_name": plan.metric,
                "plan_name": plan.name,
                "governed_planning_status": governed.status.value,
            }
        )
        return RuntimeDeliveryBridgeResultV2(
            status=RuntimeDeliveryBridgeStatusV2.GRAPH_STOPPED,
            message=message,
            safe_runtime_result=safe_base,
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
        message = (
            "Structured Query Plan 编译失败："
            f"{compilation.status.value}; "
            f"{compilation.detail or ''}"
        )
        safe_base.update(
            {
                "stop_stage": "compilation",
                "message": message,
                "metric_name": envelope.metric_name,
                "plan_name": envelope.plan_name,
                "governed_planning_status": governed.status.value,
                "compilation_status": compilation.status.value,
                "envelope_fingerprint": envelope.envelope_fingerprint,
            }
        )
        return RuntimeDeliveryBridgeResultV2(
            status=RuntimeDeliveryBridgeStatusV2.GRAPH_STOPPED,
            message=message,
            safe_runtime_result=safe_base,
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
        event_id=event_id,
        occurred_at_utc=occurred_at_utc,
        written_at_utc=written_at_utc,
    )

    final_answer = generate_final_answer_v2(
        envelope=envelope,
        finalization=finalization,
    )

    answered = (
        final_answer.status
        == FinalAnswerStatusV2.ANSWERED
    )

    safe_result = {
        "success": answered,
        "outcome": final_answer.status.value,
        "stop_stage": None if answered else "finalization",
        "message": final_answer.answer,
        "question": question,
        "planning_source": "server_structured_contract",
        "metric_name": envelope.metric_name,
        "plan_name": envelope.plan_name,
        "governed_planning_status": governed.status.value,
        "compilation_status": compilation.status.value,
        "envelope_fingerprint": envelope.envelope_fingerprint,
        "compiled_contract_fingerprint": compiled.contract_fingerprint,
        "sql_fingerprint": compiled.sql_fingerprint,
        "finalization_outcome": finalization.outcome.value,
        "final_answer_status": final_answer.status.value,
    }

    state: GovernedAnalystStateV2 = {
        "question": question,
        "context": context,
        "envelope": envelope,
        "compiled": compiled,
        "finalization": finalization,
        "final_answer": final_answer,
        "result": safe_result,
    }

    return build_runtime_delivery_from_governed_state_v2(
        state=state,
        approved_tool_binding=approved_tool_binding,
    )

def _select_approved_tool_binding_for_plan_v2(
    *,
    actual_plan_name: str | None,
    primary_binding: ApprovedGovernedQueryToolBindingV2,
    approved_tool_binding_registry: tuple[
        ApprovedGovernedQueryToolBindingV2,
        ...,
    ] = (),
) -> ApprovedGovernedQueryToolBindingV2 | None:
    """
    从 server-owned 静态 Approved Tool Binding Registry 中，
    为 Graph 已经真实产生的 Query Plan 选择唯一匹配 binding。

    安全边界：
    - 不根据 question 猜 Query Plan；
    - 不创建新的 Tool identity；
    - 不修改 Graph 的规划结果；
    - 不允许同一 plan_name 重复注册；
    - 没有批准项时返回 None，由原 mismatch gate fail closed。
    """
    if actual_plan_name is None:
        return None

    bindings = (
        primary_binding,
        *approved_tool_binding_registry,
    )

    plan_names = [
        binding.plan_name
        for binding in bindings
    ]

    if len(plan_names) != len(set(plan_names)):
        raise ValueError(
            "Approved Tool Binding Registry contains duplicate "
            f"plan_name values: {plan_names}"
        )

    matches = tuple(
        binding
        for binding in bindings
        if binding.plan_name == actual_plan_name
    )

    if len(matches) == 1:
        return matches[0]

    return None


def invoke_governed_graph_delivery_v2(
    *,
    context: AccessContext,
    question: str,
    reference_date: date,
    runtime_config: GovernanceRuntimeConfig,
    approved_tool_binding: ApprovedGovernedQueryToolBindingV2,
    approved_tool_binding_registry: tuple[
        ApprovedGovernedQueryToolBindingV2,
        ...,
    ] = (),
    llm_call: LLMCall | None = None,
    execution_policy: GovernedExecutionPolicy | None = None,
    engine_override: Engine | None = None,
    budget_policy: ExecutionBudgetPolicy | None = None,
    budget_state: ExecutionBudgetState | None = None,
    event_id: str | None = None,
    occurred_at_utc: datetime | None = None,
    written_at_utc: datetime | None = None,
) -> RuntimeDeliveryBridgeResultV2:
    """
    Trusted server-side invocation.

    这里直接调用 Graph internal state，是为了在 Governance Boundary
    内完成 Evidence Builder；完整 state 永远不会返回给 Streamlit。

    approved_tool_binding 是向后兼容的 primary binding。
    approved_tool_binding_registry 是 server-owned 静态批准表：
    - UI 不能指定或创建 Tool identity；
    - Graph 先独立产生真实 Query Plan；
    - Bridge 只允许从预先批准的 bindings 中选择与实际 plan_name
      完全一致的 binding；
    - 没有匹配项时继续保持 fail closed。
    """

    active_budget_policy = (
        budget_policy
        if budget_policy is not None
        else ExecutionBudgetPolicy()
    )

    active_budget_state = (
        budget_state
        if budget_state is not None
        else create_initial_budget_state(active_budget_policy)
    )

    app = build_governed_analyst_graph_v2()

    state = app.invoke(
        {
            "question": question,
            "context": context,
            "reference_date": reference_date,
            "runtime_config": runtime_config,
            "llm_call": llm_call,
            "execution_policy": execution_policy,
            "engine_override": engine_override,
            "budget_policy": active_budget_policy,
            "budget_state": active_budget_state,
            "event_id": event_id,
            "occurred_at_utc": occurred_at_utc,
            "written_at_utc": written_at_utc,
        }
    )

    selected_binding = _select_approved_tool_binding_for_plan_v2(
        actual_plan_name=(
            state["envelope"].plan_name
            if state.get("envelope") is not None
            else None
        ),
        primary_binding=approved_tool_binding,
        approved_tool_binding_registry=(
            approved_tool_binding_registry
        ),
    )

    return build_runtime_delivery_from_governed_state_v2(
        state=state,
        approved_tool_binding=(
            selected_binding
            if selected_binding is not None
            else approved_tool_binding
        ),
    )
