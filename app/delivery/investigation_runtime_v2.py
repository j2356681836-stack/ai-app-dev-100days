from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from hashlib import sha256
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, model_validator

from app.agents.evidence_pack_delivery_v2 import (
    EvidencePackDeliveryV2,
)
from app.agents.focused_change_breakdown_v2 import (
    FocusedChangeDimensionV2,
)
from app.agents.clarification_resolution_v2 import (
    ClarificationResolutionContractV2,
    ClarificationResolutionResultV2,
    ClarificationResolutionStatusV2,
    ClarificationResponseV2,
    resolve_clarification_response_v2,
)
from app.agents.investigation_contracts_v2 import (
    AnalysisModeV2,
    AnalysisScopeV2,
    InsightContractV2,
    ToolContractV2,
    ToolFailureCodeV2,
    ToolIdentityV2,
)
from app.agents.investigation_loop_v2 import (
    InvestigationBudgetPolicyV2,
    InvestigationLoopStateV2,
    InvestigationLoopTransitionV2,
    InvestigationSessionPolicyV2,
    InvestigationSessionStateV2,
    InvestigationStopStatusV2,
    LoopDirectiveV2,
    build_investigation_stop_status_v2,
    continue_investigation_session_v2,
    advance_investigation_loop_v2,
    replan_after_transition_v2,
)
from app.agents.investigation_planner_llm_v2 import (
    plan_next_investigation_step_v2,
)
from app.agents.investigation_planner_v2 import (
    AvailableInvestigationActionV2,
    BoundToolArgumentV2,
    ClarificationRequirementV2,
    InvestigationStateV2,
    PlannerDecisionTypeV2,
    PlannerDecisionV2,
)
from app.agents.investigation_route_v2 import (
    GeographyLevelV2,
    InvestigationDecisionOwnerV2,
    InvestigationNextDimensionV2,
    InvestigationRouteV2,
    InvestigationScopeStrategyV2,
)
from app.agents.geography_hierarchy_v2 import (
    GeographyFocusScopeV2,
    build_geography_focus_scope_v2,
    get_geography_member_v2,
    merge_requested_scope_with_geography_focus_v2,
    next_geography_level_v2,
)
from app.agents.investigation_step_assessment_v2 import (
    ChangeConcentrationPatternV2,
)
from app.agents.investigation_tool_executor_v2 import (
    InvestigationToolExecutionResultV2,
    TrustedToolExecutionBindingV2,
    execute_investigation_tool_v2,
)
from app.delivery.decision_console_runtime_v2 import (
    build_day89_local_access_context_v2,
)
from app.delivery.runtime_delivery_bridge_v2 import (
    RuntimeDeliveryBridgeResultV2,
    RuntimeDeliveryBridgeStatusV2,
)
from app.governance.access_context import AccessContext
from app.governance.execution_policy import (
    GovernedExecutionPolicy,
)
from app.governance.governance_runtime import (
    GovernanceRuntimeConfig,
    load_governance_runtime_config,
)
from app.governance.governed_planning_envelope_v2 import (
    GovernedPlanningEnvelopeV2,
    GovernedPlanningStatusV2,
    build_governed_planning_envelope_v2,
)
from app.governance.governed_finalization import (
    FinalizationOutcome,
    GovernedFinalizationResult,
)
from app.governance.governed_query_execution_v2 import (
    execute_governed_query_v2,
)
from app.observability.langfuse_observability_v2 import (
    build_safe_metadata_v2,
    start_safe_span_v2,
)
from app.semantic_layer.query_plan_compiler_v2 import (
    CompiledQueryPlanContractV2,
    QueryPlanCompileStatusV2,
    compile_governed_query_plan_v2,
)
from app.semantic_layer.query_plan_v2_loader import (
    get_query_plan_v2_by_name,
)
from app.semantic_layer.requested_scope_resolution_v2 import (
    RequestedScopeResolutionV2,
)
from app.delivery.investigation_focus_scope_v1 import (
    InvestigationFocusScopeV1,
    merge_requested_scope_with_investigation_focus_v1,
)
from app.delivery.focused_change_breakdown_delivery_v2 import (
    FocusedChangeBreakdownDeliveryV2,
    build_focused_change_breakdown_delivery_v2,
    build_geography_focused_change_breakdown_delivery_v2,
    build_global_change_breakdown_delivery_v2,
)
from app.delivery.decision_console_view_v2 import (
    ProtectedBreakdownViewV2,
)
from app.semantic_layer.time_comparison_contract_v2 import (
    TimeComparisonContractV2,
    TimeWindowReferenceV2,
)
from app.semantic_layer.time_window_resolver_v2 import (
    DEFAULT_TIME_WINDOW_POLICY_V2,
    TimeExpressionTypeV2,
    TimeWindowResolutionSourceV2,
    TimeWindowResolutionStatusV2,
    TimeWindowResolutionV2,
)


DAY89_INVESTIGATION_RUNTIME_VERSION = (
    "day89_investigation_runtime_v2_0"
)

PlannerInvokerV2 = Callable[
    [InvestigationStateV2],
    PlannerDecisionV2,
]


class Day89InvestigationRuntimeStatusV2(str, Enum):
    CLARIFICATION_REQUIRED = "clarification_required"
    STEP_EXECUTED = "step_executed"
    STOPPED = "stopped"


class Day89GovernedQueryEvidenceContextV2(BaseModel):
    """
    仅供 server-side Evidence Delivery Adapter 使用的可信执行上下文。

    compiled 内部包含 SQL / parameters，因此本对象绝不能直接返回 UI。
    它只用于让 Day87 Evidence Builder 重新验证
    envelope / compiled / finalization 链。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        arbitrary_types_allowed=True,
    )

    action_id: str
    tool_contract: ToolContractV2
    envelope: GovernedPlanningEnvelopeV2
    compiled: CompiledQueryPlanContractV2
    finalization: GovernedFinalizationResult

    @model_validator(mode="after")
    def validate_context(
        self,
    ) -> "Day89GovernedQueryEvidenceContextV2":
        if not self.action_id.strip():
            raise ValueError("action_id 不能为空。")

        if self.envelope.plan_name != self.compiled.plan_name:
            raise ValueError(
                "Governed Evidence Context 的 envelope / compiled "
                "plan_name 不一致。"
            )

        if (
            self.envelope.envelope_fingerprint
            != self.compiled.envelope_fingerprint
        ):
            raise ValueError(
                "Governed Evidence Context 的 envelope fingerprint "
                "与 compiled binding 不一致。"
            )

        return self


class Day89InvestigationRuntimeStepResultV2(BaseModel):
    """
    Day89 第一版生产 Investigation Step。

    这是 server-internal orchestration result，不是最终 UI contract。
    released_rows 若存在，也只能来自 Governed Finalization 后的
    protected rows。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        arbitrary_types_allowed=True,
    )

    contract_version: str = (
        DAY89_INVESTIGATION_RUNTIME_VERSION
    )

    status: Day89InvestigationRuntimeStatusV2

    session_before: InvestigationSessionStateV2
    planner_decision: PlannerDecisionV2

    execution_result: (
        InvestigationToolExecutionResultV2 | None
    ) = None
    transition: InvestigationLoopTransitionV2 | None = None

    session_after: InvestigationSessionStateV2

    next_planner_decision: PlannerDecisionV2 | None = None
    stop_status: InvestigationStopStatusV2 | None = None

    # 仅 high-level production entry 会附加。
    # generic run_one_investigation_step_v2 可继续用于隔离 Loop 测试。
    governed_query_context: (
        Day89GovernedQueryEvidenceContextV2 | None
    ) = None

    # 由 Seed / Continuation / Clarification Resume 继承的
    # server-trusted Requested Scope。不能从 UI 文本反向解析。
    requested_scope: RequestedScopeResolutionV2 | None = None

    # 受治理 Evidence 推荐并经后续调查动作确认的结构化焦点。
    # 与用户原始 Requested Scope 分离保存。
    investigation_focus_scope: InvestigationFocusScopeV1 | None = None

    # Geography Focus is separate from Channel Investigation Focus.
    geography_focus_scope: GeographyFocusScopeV2 | None = None

    # Day93 F02:
    # Planner 仍只选择一个 investigation action；
    # 对 comparison-bearing Focus，Runtime 可追加一次 server-owned
    # reference companion read，形成安全的两期变化分解。
    # 这里只保存安全 Delivery，不包含 SQL / parameters。
    focused_change_breakdown: (
        FocusedChangeBreakdownDeliveryV2 | None
    ) = None

    @model_validator(mode="after")
    def validate_result(
        self,
    ) -> "Day89InvestigationRuntimeStepResultV2":
        if (
            self.status
            == Day89InvestigationRuntimeStatusV2
            .CLARIFICATION_REQUIRED
        ):
            if (
                self.planner_decision.decision_type
                != PlannerDecisionTypeV2.CLARIFY
            ):
                raise ValueError(
                    "CLARIFICATION_REQUIRED 必须对应 CLARIFY。"
                )

            if any(
                item is not None
                for item in (
                    self.execution_result,
                    self.transition,
                    self.next_planner_decision,
                    self.stop_status,
                    self.governed_query_context,
                    self.focused_change_breakdown,
                )
            ):
                raise ValueError(
                    "Clarification 状态不能执行 Tool 或产生 Loop Transition。"
                )

            if self.session_after != self.session_before:
                raise ValueError(
                    "Clarification 前不能静默推进 Investigation State。"
                )

            return self

        if self.execution_result is None:
            raise ValueError(
                "执行型 Investigation Step 必须包含 execution_result。"
            )

        if self.transition is None:
            raise ValueError(
                "执行型 Investigation Step 必须包含 transition。"
            )

        directive = self.transition.control_decision.directive

        if (
            self.status
            == Day89InvestigationRuntimeStatusV2.STOPPED
        ):
            if directive != LoopDirectiveV2.STOP:
                raise ValueError(
                    "STOPPED 必须来自 STOP transition。"
                )

            if self.stop_status is None:
                raise ValueError(
                    "STOPPED 必须包含 InvestigationStopStatusV2。"
                )

            if self.next_planner_decision is not None:
                raise ValueError(
                    "STOP 后不能继续调用 Planner。"
                )

            return self

        if directive == LoopDirectiveV2.STOP:
            raise ValueError(
                "STOP transition 必须使用 STOPPED runtime status。"
            )

        if directive in {
            LoopDirectiveV2.REPLAN,
            LoopDirectiveV2.RECOVER,
        }:
            if self.next_planner_decision is None:
                raise ValueError(
                    "REPLAN / RECOVER 后必须给出新 State 上的 "
                    "next Planner Decision。"
                )

        if (
            directive == LoopDirectiveV2.RETRY
            and self.next_planner_decision is not None
        ):
            raise ValueError(
                "RETRY 不允许 Planner 偷换调查方向。"
            )

        if self.stop_status is not None:
            raise ValueError(
                "非 STOP runtime step 不能携带 stop_status。"
            )

        return self



class Day89PendingClarificationStateV2(BaseModel):
    """
    可安全保存于同页 Session 的待解决 Clarification 状态。

    只包含：
    - Day86 structured Investigation Session；
    - server-owned Resolution Contract；
    - server-trusted Requested Scope。

    不包含 governed_query_context / compiled SQL / parameters / secrets。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    session: InvestigationSessionStateV2
    resolution_contract: ClarificationResolutionContractV2
    requested_scope: RequestedScopeResolutionV2 | None = None
    investigation_focus_scope: InvestigationFocusScopeV1 | None = None
    geography_focus_scope: GeographyFocusScopeV2 | None = None

    @model_validator(mode="after")
    def validate_state(
        self,
    ) -> "Day89PendingClarificationStateV2":
        requirement = (
            self.session.loop_state.planner_state
            .clarification_requirement
        )

        if requirement is None:
            raise ValueError(
                "Pending Clarification State 必须包含 unresolved requirement。"
            )

        if (
            requirement.source
            != self.resolution_contract.requirement_source
            or requirement.reason
            != self.resolution_contract.requirement_reason
        ):
            raise ValueError(
                "Pending Clarification State 与 Resolution Contract "
                "source/reason 不匹配。"
            )

        return self


class Day89ClarificationResumeResultV2(BaseModel):
    """
    Clarification Response → Resolution → Runtime Step 的 server result。

    非 RESOLVED：
    - 不运行 Planner；
    - 不执行 Tool；
    - runtime_step=None。

    RESOLVED：
    - resolver 先收窄 trusted available_actions；
    - 再执行恰好一个 bounded Investigation Step。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        arbitrary_types_allowed=True,
    )

    resolution: ClarificationResolutionResultV2
    runtime_step: (
        Day89InvestigationRuntimeStepResultV2 | None
    ) = None

    @model_validator(mode="after")
    def validate_result(
        self,
    ) -> "Day89ClarificationResumeResultV2":
        if (
            self.resolution.status
            == ClarificationResolutionStatusV2.RESOLVED
        ):
            if self.runtime_step is None:
                raise ValueError(
                    "RESOLVED clarification 必须产生 Runtime Step。"
                )
            if (
                self.runtime_step.status
                == Day89InvestigationRuntimeStatusV2
                .CLARIFICATION_REQUIRED
            ):
                raise ValueError(
                    "已解决 clarification 后不能再次返回同一 CLARIFY。"
                )
        elif self.runtime_step is not None:
            raise ValueError(
                "非 RESOLVED clarification 不得执行 Runtime Step。"
            )

        return self


def build_day89_pending_clarification_state_v2(
    *,
    runtime_step: Day89InvestigationRuntimeStepResultV2,
    resolution_contract: ClarificationResolutionContractV2,
) -> Day89PendingClarificationStateV2:
    if (
        runtime_step.status
        != Day89InvestigationRuntimeStatusV2
        .CLARIFICATION_REQUIRED
    ):
        raise ValueError(
            "只有 CLARIFICATION_REQUIRED Step "
            "才能生成 Pending Clarification State。"
        )

    return Day89PendingClarificationStateV2(
        session=runtime_step.session_before,
        resolution_contract=resolution_contract,
        requested_scope=runtime_step.requested_scope,
        investigation_focus_scope=runtime_step.investigation_focus_scope,
        geography_focus_scope=runtime_step.geography_focus_scope,
    )



class Day89InvestigationContinuationStateV2(BaseModel):
    """
    可安全保存在同一页面 Session 中的 continuation 状态。

    不包含：
    - GovernedPlanningEnvelope；
    - Compiled SQL；
    - SQL parameters；
    - Executor closure；
    - Governance secret。

    保存 Day86 已定义的结构化 Session / STOP / Transition，
    并携带 server-trusted Requested Scope，
    供用户明确点击 Continue 后恢复下一轮。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    session_before_stop: InvestigationSessionStateV2
    stopped_transition: InvestigationLoopTransitionV2
    stop_status: InvestigationStopStatusV2
    prior_transitions: tuple[
        InvestigationLoopTransitionV2, ...
    ]
    requested_scope: RequestedScopeResolutionV2 | None = None
    investigation_focus_scope: InvestigationFocusScopeV1 | None = None
    geography_focus_scope: GeographyFocusScopeV2 | None = None

    @model_validator(mode="after")
    def validate_state(
        self,
    ) -> "Day89InvestigationContinuationStateV2":
        if (
            self.stopped_transition.control_decision.directive
            != LoopDirectiveV2.STOP
        ):
            raise ValueError(
                "Continuation State 必须来自 STOP transition。"
            )

        if not self.stop_status.can_continue:
            raise ValueError(
                "Continuation State 只能保存 can_continue=True 的停止状态。"
            )

        if not self.prior_transitions:
            raise ValueError(
                "Continuation State 必须保留至少一条历史 transition。"
            )

        if (
            self.prior_transitions[-1]
            != self.stopped_transition
        ):
            raise ValueError(
                "prior_transitions 最后一条必须是当前 STOP transition。"
            )

        return self


def build_day89_continuation_state_v2(
    *,
    runtime_step: Day89InvestigationRuntimeStepResultV2,
    prior_transitions: tuple[
        InvestigationLoopTransitionV2, ...
    ] = (),
) -> Day89InvestigationContinuationStateV2:
    """
    仅当本轮 STOP 且 can_continue=True 时生成安全 continuation state。
    """

    if (
        runtime_step.status
        != Day89InvestigationRuntimeStatusV2.STOPPED
        or runtime_step.transition is None
        or runtime_step.stop_status is None
    ):
        raise ValueError(
            "只有 STOPPED Runtime Step 才能生成 continuation state。"
        )

    if not runtime_step.stop_status.can_continue:
        raise ValueError(
            "当前 STOP 不允许 continuation。"
        )

    transitions = (
        *prior_transitions,
        runtime_step.transition,
    )

    return Day89InvestigationContinuationStateV2(
        session_before_stop=runtime_step.session_before,
        stopped_transition=runtime_step.transition,
        stop_status=runtime_step.stop_status,
        prior_transitions=transitions,
        requested_scope=runtime_step.requested_scope,
        investigation_focus_scope=runtime_step.investigation_focus_scope,
        geography_focus_scope=runtime_step.geography_focus_scope,
    )



def build_investigation_insight_from_delivery_v2(
    delivery: EvidencePackDeliveryV2,
) -> InsightContractV2:
    """
    将已经可信的 Delivery 作为 Investigation 的起始 Evidence。

    不重新定义：
    - metric；
    - time comparison；
    - effective scope；
    - 已确认事实 / Evidence identity。

    Investigation scope 的 result_grain 设为 None，
    因为后续受控动作可以合法切换 channel / region 等调查粒度。
    """

    source = delivery.evidence_pack.insight
    source_scope = delivery.evidence_pack.analysis_scope

    investigation_scope = AnalysisScopeV2(
        metric_name=source_scope.metric_name,
        analysis_window=source_scope.analysis_window,
        comparison=source_scope.comparison,
        result_grain=None,
        scope_summary=source_scope.scope_summary,
    )

    return InsightContractV2(
        analysis_mode=AnalysisModeV2.INVESTIGATION,
        analysis_scope=investigation_scope,
        confirmed_facts=source.confirmed_facts,
        detected_anomalies=source.detected_anomalies,
        dimension_contributions=source.dimension_contributions,
        candidate_explanations=source.candidate_explanations,
        unknowns=source.unknowns,
        recommended_checks=source.recommended_checks,
        evidence=source.evidence,
    )


def build_investigation_session_from_delivery_v2(
    *,
    delivery: EvidencePackDeliveryV2,
    available_actions: tuple[
        AvailableInvestigationActionV2, ...
    ],
    clarification_requirement: (
        ClarificationRequirementV2 | None
    ) = None,
    budget_policy: InvestigationBudgetPolicyV2,
    session_policy: InvestigationSessionPolicyV2,
) -> InvestigationSessionStateV2:
    insight = build_investigation_insight_from_delivery_v2(
        delivery
    )

    planner_state = InvestigationStateV2(
        insight=insight,
        completed_action_ids=(),
        available_actions=available_actions,
        clarification_requirement=clarification_requirement,
    )

    loop_state = InvestigationLoopStateV2(
        planner_state=planner_state,
        budget_policy=budget_policy,
        investigation_steps_used=0,
        observation_history=(),
    )

    return InvestigationSessionStateV2(
        loop_state=loop_state,
        session_policy=session_policy,
        round_number=1,
        completed_round_steps_used=0,
    )


def _session_with_resolved_planner_state_v2(
    *,
    session: InvestigationSessionStateV2,
    resolved_state: InvestigationStateV2,
) -> InvestigationSessionStateV2:
    """
    Clarification Resolution 只替换 planner_state。

    Budget / observation history / round / completed round usage
    必须原样保留；不能通过澄清偷偷重置预算。
    """

    original_loop = session.loop_state

    loop_state = InvestigationLoopStateV2(
        planner_state=resolved_state,
        budget_policy=original_loop.budget_policy,
        investigation_steps_used=(
            original_loop.investigation_steps_used
        ),
        observation_history=(
            original_loop.observation_history
        ),
    )

    return InvestigationSessionStateV2(
        loop_state=loop_state,
        session_policy=session.session_policy,
        round_number=session.round_number,
        completed_round_steps_used=(
            session.completed_round_steps_used
        ),
    )



def _append_execution_evidence_v2(
    *,
    insight: InsightContractV2,
    execution_result: InvestigationToolExecutionResultV2,
) -> InsightContractV2:
    evidence = execution_result.evidence_reference

    if evidence is None:
        return insight

    if any(
        item.evidence_id == evidence.evidence_id
        for item in insight.evidence
    ):
        raise ValueError(
            "Investigation Tool 不能重复写入同一 evidence_id。"
        )

    return InsightContractV2(
        analysis_mode=insight.analysis_mode,
        analysis_scope=insight.analysis_scope,
        confirmed_facts=insight.confirmed_facts,
        detected_anomalies=insight.detected_anomalies,
        dimension_contributions=insight.dimension_contributions,
        candidate_explanations=insight.candidate_explanations,
        unknowns=insight.unknowns,
        recommended_checks=insight.recommended_checks,
        evidence=(
            *insight.evidence,
            evidence,
        ),
    )


def _session_after_transition_v2(
    *,
    session: InvestigationSessionStateV2,
    transition: InvestigationLoopTransitionV2,
) -> InvestigationSessionStateV2:
    return InvestigationSessionStateV2(
        loop_state=transition.next_state,
        session_policy=session.session_policy,
        round_number=session.round_number,
        completed_round_steps_used=(
            session.completed_round_steps_used
        ),
    )


def run_one_investigation_step_v2(
    *,
    session: InvestigationSessionStateV2,
    bindings: Mapping[
        str,
        TrustedToolExecutionBindingV2,
    ],
    planner: PlannerInvokerV2,
    evidence_sufficient_after_step: bool = False,
    trusted_remaining_actions_after_selected: tuple[
        AvailableInvestigationActionV2, ...
    ] | None = None,
) -> Day89InvestigationRuntimeStepResultV2:
    """
    执行恰好一个 Tool Step。

    允许：
    Planner → Tool Execute → Observe → State Update
    → REPLAN / RECOVER / STOP

    不允许：
    - 在同一次调用里自动执行第二个 Tool；
    - STOP 后重新调用 Planner；
    - RETRY 时让 Planner 偷换 action；
    - 自动 continuation / 自动扩 Session Budget。
    """

    planner_state = session.loop_state.planner_state

    first_decision = planner(planner_state)

    if first_decision.decision_type == PlannerDecisionTypeV2.CLARIFY:
        return Day89InvestigationRuntimeStepResultV2(
            status=(
                Day89InvestigationRuntimeStatusV2
                .CLARIFICATION_REQUIRED
            ),
            session_before=session,
            planner_decision=first_decision,
            execution_result=None,
            transition=None,
            session_after=session,
            next_planner_decision=None,
            stop_status=None,
        )

    execution_result = execute_investigation_tool_v2(
        decision=first_decision,
        attempt_number=1,
        bindings=bindings,
    )

    evidence_before = len(
        planner_state.insight.evidence
    )

    with start_safe_span_v2(
        name="evidence_update",
        stage="evidence_update",
        action_id=execution_result.observation.action_id,
    ) as evidence_span:
        refreshed_insight = _append_execution_evidence_v2(
            insight=planner_state.insight,
            execution_result=execution_result,
        )

        evidence_after = len(
            refreshed_insight.evidence
        )

        if evidence_span is not None:
            evidence_span.update(
                metadata=build_safe_metadata_v2(
                    status=(
                        "evidence_added"
                        if evidence_after > evidence_before
                        else "no_new_evidence"
                    ),
                    action_id=(
                        execution_result.observation.action_id
                    ),
                    evidence_count=evidence_after,
                )
            )

    selected_action = first_decision.selected_action
    assert selected_action is not None

    if trusted_remaining_actions_after_selected is None:
        remaining_actions = tuple(
            action
            for action in planner_state.available_actions
            if action.action_id != selected_action.action_id
        )
    else:
        # Clarification Resume 的执行 State 会被 deterministic resolver
        # 临时收窄到用户明确选择的一个 Action。
        # 但“本轮只能执行该 Action”不等于用户放弃 Session 中
        # 原本剩余的其他合法调查方向。
        #
        # 这个 override 只允许在本动作执行后必然触发本轮 Budget STOP
        # 时使用，避免把尚未建立 trusted bindings 的动作带入同一轮
        # 自动 REPLAN。
        next_steps_used = (
            session.loop_state.investigation_steps_used + 1
        )
        if (
            next_steps_used
            < session.loop_state.budget_policy.max_investigation_steps
        ):
            raise ValueError(
                "trusted_remaining_actions_after_selected 只能用于"
                "当前动作后必然耗尽本轮 Investigation Budget 的路径。"
            )

        remaining_ids = tuple(
            action.action_id
            for action in trusted_remaining_actions_after_selected
        )

        if len(set(remaining_ids)) != len(remaining_ids):
            raise ValueError(
                "Clarification Resume remaining actions 不能重复。"
            )

        if selected_action.action_id in set(remaining_ids):
            raise ValueError(
                "用户已经执行的 Action 不能继续留在 Session remaining actions。"
            )

        completed_ids = set(
            planner_state.completed_action_ids
        )
        leaked_completed = completed_ids.intersection(
            remaining_ids
        )
        if leaked_completed:
            raise ValueError(
                "Clarification Resume 不能重新开放已完成 Action："
                f"{sorted(leaked_completed)}"
            )

        remaining_actions = (
            trusted_remaining_actions_after_selected
        )

    with start_safe_span_v2(
        name="loop_control",
        stage="loop_control",
        action_id=execution_result.observation.action_id,
    ) as loop_span:
        transition = advance_investigation_loop_v2(
            state=session.loop_state,
            observation=execution_result.observation,
            refreshed_insight=refreshed_insight,
            refreshed_available_actions=remaining_actions,
            evidence_sufficient=evidence_sufficient_after_step,
        )

        if loop_span is not None:
            loop_span.update(
                metadata=build_safe_metadata_v2(
                    status=execution_result.observation.status,
                    action_id=(
                        execution_result.observation.action_id
                    ),
                    directive=(
                        transition.control_decision.directive
                    ),
                    stop_reason=(
                        transition.control_decision.stop_reason
                    ),
                )
            )

    session_after = _session_after_transition_v2(
        session=session,
        transition=transition,
    )

    directive = transition.control_decision.directive

    if directive == LoopDirectiveV2.STOP:
        stop_status = build_investigation_stop_status_v2(
            session=session,
            transition=transition,
            evidence_sufficient=evidence_sufficient_after_step,
        )

        return Day89InvestigationRuntimeStepResultV2(
            status=(
                Day89InvestigationRuntimeStatusV2.STOPPED
            ),
            session_before=session,
            planner_decision=first_decision,
            execution_result=execution_result,
            transition=transition,
            session_after=session_after,
            next_planner_decision=None,
            stop_status=stop_status,
        )

    next_decision = None

    if directive in {
        LoopDirectiveV2.REPLAN,
        LoopDirectiveV2.RECOVER,
    }:
        next_decision = replan_after_transition_v2(
            transition=transition,
            planner=planner,
        ).planner_decision

    return Day89InvestigationRuntimeStepResultV2(
        status=(
            Day89InvestigationRuntimeStatusV2
            .STEP_EXECUTED
        ),
        session_before=session,
        planner_decision=first_decision,
        execution_result=execution_result,
        transition=transition,
        session_after=session_after,
        next_planner_decision=next_decision,
        stop_status=None,
    )


def _day89_tool_contract_v2(
    *,
    result_grain: str,
) -> ToolContractV2:
    return ToolContractV2(
        identity=ToolIdentityV2(
            name=f"governed_gmv_{result_grain}_query",
            version="dataset_v2",
            purpose=(
                "在既有 Governance Boundary 内查询 "
                f"{result_grain} 粒度 GMV。"
            ),
        ),
        input_schema_name="GovernedInvestigationInputV2",
        output_schema_name="GovernedFinalizationResult",
        required_permissions=(
            "metric_access",
            "data_scope",
        ),
        execution_policy_reference=(
            "governed_execution_policy_v2"
        ),
        failure_semantics=(
            ToolFailureCodeV2.INVALID_INPUT,
            ToolFailureCodeV2.UNAUTHORIZED,
            ToolFailureCodeV2.UNSUPPORTED,
            ToolFailureCodeV2.TIMEOUT,
            ToolFailureCodeV2.NO_DATA,
            ToolFailureCodeV2.EXECUTION_FAILURE,
        ),
        executor_binding="execute_governed_query_v2",
    )



def _day93_gmv_action_v2(
    *, action_id: str, plan_name: str, result_grain: str,
) -> AvailableInvestigationActionV2:
    return AvailableInvestigationActionV2(
        action_id=action_id,
        tool_contract=_day89_tool_contract_v2(result_grain=result_grain),
        arguments=(
            BoundToolArgumentV2(name="metric_name", value="gmv"),
            BoundToolArgumentV2(name="query_plan_name", value=plan_name),
            BoundToolArgumentV2(name="result_grain", value=result_grain),
        ),
    )


def _day93_geography_action_v2(
    level: GeographyLevelV2,
) -> AvailableInvestigationActionV2:
    action_id, plan_name, grain = {
        GeographyLevelV2.AREA: ("drill_area", "gmv_area_v2", "area"),
        GeographyLevelV2.PROVINCE: ("drill_province", "gmv_province_v2", "province"),
        GeographyLevelV2.CITY: ("drill_city", "gmv_city_v2", "city"),
    }[level]
    return _day93_gmv_action_v2(
        action_id=action_id, plan_name=plan_name, result_grain=grain
    )




def _day93_planner_for_action_id_v2(
    action_id: str,
    *,
    rationale: str,
) -> PlannerInvokerV2:
    def planner(state: InvestigationStateV2) -> PlannerDecisionV2:
        action = next(
            (item for item in state.available_actions if item.action_id == action_id),
            None,
        )
        if action is None:
            raise ValueError(
                f"Preferred Geography action 不在当前合法 Action Space：{action_id}"
            )
        if not state.insight.evidence:
            raise ValueError("Preferred Geography action 需要 trusted evidence。")

        return PlannerDecisionV2(
            decision_type=PlannerDecisionTypeV2.SELECT_TOOL,
            selected_action=action,
            clarification_prompt=None,
            rationale=rationale,
            supporting_evidence_ids=(state.insight.evidence[-1].evidence_id,),
        )

    return planner


def build_day89_gmv_investigation_actions_v2(
    *,
    delivery: EvidencePackDeliveryV2,
    requested_scope: RequestedScopeResolutionV2 | None = None,
    include_category: bool = False,
    include_legacy_region: bool = False,
) -> tuple[AvailableInvestigationActionV2, ...]:
    """Initial production space: channel + area + optional category.

    Province / City are NOT initial actions. They are dynamically unlocked only
    by a reconciled DOMINANT parent Geography step. Legacy drill_region remains
    opt-in only for the old clarification compatibility path.
    """
    scope = delivery.evidence_pack.analysis_scope
    if scope.metric_name != "gmv":
        raise ValueError("Day93 Agentic Runtime 当前只注册 GMV Investigation Actions。")

    specs = [
        ("drill_channel", "gmv_channel_v2", "channel"),
        ("drill_area", "gmv_area_v2", "area"),
        ("drill_campaign", "gmv_campaign_v2", "campaign"),
    ]
    if include_legacy_region:
        specs.append(("drill_region", "gmv_region_v2", "region"))
    if include_category:
        specs.append(("drill_category", "gmv_category_v2", "category"))

    region_locked = bool(requested_scope is not None and requested_scope.region_codes)
    channel_locked = bool(requested_scope is not None and requested_scope.channel_codes)

    actions = []
    for action_id, plan_name, grain in specs:
        if scope.result_grain == grain:
            continue
        if action_id in {"drill_area", "drill_region"} and region_locked:
            continue
        if action_id == "drill_channel" and channel_locked:
            continue
        actions.append(_day93_gmv_action_v2(
            action_id=action_id, plan_name=plan_name, result_grain=grain
        ))
    return tuple(actions)


def _day93_action_id_from_route_v2(
    route: InvestigationRouteV2,
) -> str:
    if route.next_dimension == InvestigationNextDimensionV2.CATEGORY:
        return "drill_category"

    if route.next_dimension == InvestigationNextDimensionV2.GEOGRAPHY:
        level = route.geography_level or GeographyLevelV2.AREA
        if level != GeographyLevelV2.AREA:
            raise ValueError(
                "Seed Geography Route 必须从 AREA 开始；Province / City "
                "只能由上一层 Evidence 动态解锁。"
            )
        return "drill_area"

    raise ValueError(f"Unsupported route dimension: {route.next_dimension}")


def _day93_planner_for_route_v2(
    route: InvestigationRouteV2,
) -> PlannerInvokerV2:
    action_id = _day93_action_id_from_route_v2(route)

    def planner(
        state: InvestigationStateV2,
    ) -> PlannerDecisionV2:
        action = next(
            (
                item
                for item in state.available_actions
                if item.action_id == action_id
            ),
            None,
        )

        if action is None:
            raise ValueError(
                "Investigation Route 指向的 Action "
                f"不在当前合法 Action Space：{action_id}"
            )

        available_evidence_ids = {
            item.evidence_id
            for item in state.insight.evidence
        }
        missing = (
            set(route.supporting_evidence_ids)
            - available_evidence_ids
        )

        if missing:
            raise ValueError(
                "Investigation Route supporting evidence "
                "不在当前 Insight："
                f"{sorted(missing)}"
            )

        return PlannerDecisionV2(
            decision_type=PlannerDecisionTypeV2.SELECT_TOOL,
            selected_action=action,
            clarification_prompt=None,
            rationale=route.rationale,
            supporting_evidence_ids=(
                route.supporting_evidence_ids
            ),
        )

    return planner


def _validate_day93_route_focus_binding_v2(
    *,
    route: InvestigationRouteV2,
    investigation_focus_scope: InvestigationFocusScopeV1 | None,
) -> None:
    if route.decision_owner != InvestigationDecisionOwnerV2.SYSTEM:
        raise ValueError(
            "Production system-route entry 当前只接受 SYSTEM Route。"
        )

    if (
        route.scope_strategy
        == InvestigationScopeStrategyV2.KEEP_REQUESTED_SCOPE
    ):
        if investigation_focus_scope is not None:
            raise ValueError(
                "KEEP_REQUESTED_SCOPE Route 不能同时携带 Member Focus。"
            )
        return

    if investigation_focus_scope is None:
        raise ValueError(
            "FOCUS_MEMBER Route 必须绑定 server-trusted Investigation Focus。"
        )

    if (
        route.focus_member_key != investigation_focus_scope.member_key
        or route.focus_member_label != investigation_focus_scope.member_label
    ):
        raise ValueError(
            "Investigation Route Focus 与 server-trusted Focus Scope 不一致。"
        )


def _structured_time_resolution_v2(
    window: TimeWindowReferenceV2,
) -> TimeWindowResolutionV2:
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


def _action_argument_v2(
    *,
    action: AvailableInvestigationActionV2,
    name: str,
) -> str:
    values = {
        item.name: item.value
        for item in action.arguments
    }

    value = values.get(name)
    if value is None:
        raise ValueError(
            f"Investigation Action 缺少可信预绑定参数：{name}"
        )

    return value


@dataclass
class _FinalizationCaptureV2:
    finalization: GovernedFinalizationResult | None = None


@dataclass(frozen=True)
class _PreparedInvestigationBindingV2:
    binding: TrustedToolExecutionBindingV2
    action_id: str
    tool_contract: ToolContractV2
    envelope: GovernedPlanningEnvelopeV2
    compiled: CompiledQueryPlanContractV2
    capture: _FinalizationCaptureV2


def _prepare_day89_trusted_binding_v2(
    *,
    action: AvailableInvestigationActionV2,
    context: AccessContext,
    analysis_window: TimeWindowReferenceV2,
    runtime_config: GovernanceRuntimeConfig,
    execution_policy: GovernedExecutionPolicy | None,
    event_id: str,
    requested_scope: RequestedScopeResolutionV2 | None = None,
) -> _PreparedInvestigationBindingV2:
    """
    准备 server-trusted Tool Binding，同时保留 Evidence Builder
    后续需要的内部可信对象；这些对象不会释放给 UI。
    """

    plan_name = _action_argument_v2(
        action=action,
        name="query_plan_name",
    )

    plan = get_query_plan_v2_by_name(plan_name)

    if plan is None:
        raise ValueError(
            f"Investigation Query Plan 不存在：{plan_name}"
        )

    planning = build_governed_planning_envelope_v2(
        context=context,
        plan=plan,
        time_resolution=_structured_time_resolution_v2(
            analysis_window
        ),
        requested_scope=requested_scope,
    )

    if (
        planning.status
        != GovernedPlanningStatusV2.READY_FOR_COMPILATION
        or planning.envelope is None
    ):
        raise ValueError(
            "Investigation Action 未通过 Governed Planning："
            f"action={action.action_id}; "
            f"status={planning.status.value}; "
            f"detail={planning.detail or ''}"
        )

    compilation = compile_governed_query_plan_v2(
        planning.envelope
    )

    if (
        compilation.status
        != QueryPlanCompileStatusV2.COMPILED
        or compilation.contract is None
    ):
        raise ValueError(
            "Investigation Action 编译失败："
            f"action={action.action_id}; "
            f"status={compilation.status.value}; "
            f"detail={compilation.detail or ''}"
        )

    envelope = planning.envelope
    compiled = compilation.contract
    capture = _FinalizationCaptureV2()

    question = (
        "Day89 bounded investigation action: "
        f"{action.action_id}"
    )

    def governed_executor():
        finalization = execute_governed_query_v2(
            context=context,
            question=question,
            envelope=envelope,
            compiled=compiled,
            runtime_config=runtime_config,
            execution_policy=execution_policy,
            event_id=event_id,
        )
        capture.finalization = finalization
        return finalization

    binding = TrustedToolExecutionBindingV2(
        action_id=action.action_id,
        executor_binding=(
            action.tool_contract.executor_binding
        ),
        executor=governed_executor,
    )

    return _PreparedInvestigationBindingV2(
        binding=binding,
        action_id=action.action_id,
        tool_contract=action.tool_contract,
        envelope=envelope,
        compiled=compiled,
        capture=capture,
    )



def _day93_scope_summary_from_envelope_v2(
    envelope: GovernedPlanningEnvelopeV2,
) -> str | None:
    """
    从实际 Governed Scope Binding 生成安全范围摘要。

    Current / Reference companion read 必须得到同一摘要，
    Focused Change Delivery 才允许继续计算。
    """

    scoped = envelope.scope_binding.scoped_query_contract
    parameter_values = {
        parameter.name: str(parameter.value)
        for parameter in scoped.parameters
    }

    collected: dict[str, set[str]] = {}

    for predicate in scoped.predicates:
        dimension = predicate.dimension.value
        values = collected.setdefault(dimension, set())

        for name in predicate.parameter_names:
            if name not in parameter_values:
                raise ValueError(
                    "Scope predicate references a missing parameter: "
                    f"{name}"
                )
            values.add(parameter_values[name])

    regions = tuple(sorted(collected.get("region", set())))
    channels = tuple(sorted(collected.get("channel", set())))

    parts: list[str] = []

    if regions:
        parts.append("地区代码：" + "、".join(regions))

    if channels:
        parts.append("渠道代码：" + "、".join(channels))

    return "；".join(parts) if parts else None


def _day93_query_evidence_id_v2(
    *,
    action_id: str,
    finalization: GovernedFinalizationResult,
) -> str:
    """
    与 Investigation Tool Executor 使用相同的安全 evidence-id 规则：
    action_id + persisted audit fingerprint。
    """

    fingerprint = finalization.audit_event_fingerprint

    if fingerprint is None:
        raise ValueError(
            "Focused Change Query 必须存在 audit_event_fingerprint。"
        )

    digest = sha256(
        f"{action_id}|{fingerprint}".encode("utf-8")
    ).hexdigest()[:16]

    return f"ev_tool_{digest}"


def _day93_protected_breakdown_from_prepared_v2(
    *,
    prepared: _PreparedInvestigationBindingV2,
    analysis_window: TimeWindowReferenceV2,
) -> ProtectedBreakdownViewV2:
    """
    将一次已经成功 Finalization 的 Governed Query
    投影成 Focused Change Core 可消费的安全 Protected Breakdown。

    不读取 raw executor rows；这里只读取 Finalization 已允许释放的 rows。
    """

    finalization = prepared.capture.finalization

    if finalization is None:
        raise ValueError(
            "Focused Change Query 没有捕获 GovernedFinalizationResult。"
        )

    if (
        finalization.outcome != FinalizationOutcome.SUCCEEDED
        or not finalization.success
    ):
        raise ValueError(
            "Focused Change companion query 未形成可释放结果："
            f"outcome={finalization.outcome.value}; "
            f"reason={finalization.reason_code.value}"
        )

    if finalization.row_count == 0:
        raise ValueError(
            "Focused Change companion query 没有可释放数据，"
            "不能伪造两期变化分解。"
        )

    if finalization.audit_event_id is None:
        raise ValueError(
            "Focused Change Query 缺少 persisted audit_event_id。"
        )

    expected_fields = prepared.compiled.visible_output_fields
    expected_field_set = set(expected_fields)

    for index, row in enumerate(finalization.rows):
        if set(row) != expected_field_set:
            raise ValueError(
                "Focused Change Finalization row 与 visible output "
                "contract 不一致："
                f"row_index={index}"
            )

    evidence_id = _day93_query_evidence_id_v2(
        action_id=prepared.action_id,
        finalization=finalization,
    )

    return ProtectedBreakdownViewV2(
        evidence_id=evidence_id,
        metric_name=prepared.envelope.metric_name,
        result_grain=prepared.envelope.result_grain,
        analysis_window=analysis_window,
        scope_summary=_day93_scope_summary_from_envelope_v2(
            prepared.envelope
        ),
        field_names=expected_fields,
        rows=tuple(
            dict(row)
            for row in finalization.rows
        ),
        row_count=finalization.row_count,
        dataset_name=prepared.envelope.dataset_name,
        plan_name=prepared.envelope.plan_name,
        tool_name=prepared.tool_contract.identity.name,
        tool_version=prepared.tool_contract.identity.version,
        audit_event_id=finalization.audit_event_id,
    )


def _day93_focused_dimension_for_action_v2(
    action_id: str,
) -> FocusedChangeDimensionV2 | None:
    return {
        "drill_channel": FocusedChangeDimensionV2.CHANNEL,
        "drill_category": FocusedChangeDimensionV2.CATEGORY,
        "drill_region": FocusedChangeDimensionV2.REGION,
        "drill_area": FocusedChangeDimensionV2.AREA,
        "drill_province": FocusedChangeDimensionV2.PROVINCE,
        "drill_city": FocusedChangeDimensionV2.CITY,
        "drill_campaign": FocusedChangeDimensionV2.CAMPAIGN,
    }.get(action_id)


def _day93_overall_gmv_values_from_delivery_v2(
    *,
    delivery: EvidencePackDeliveryV2,
    comparison: TimeComparisonContractV2 | None,
) -> tuple[Decimal, Decimal] | None:
    """
    从 Evidence Pack 的两侧 Overall Governed Result 恢复可信 GMV。

    返回 (reference, current)。
    任一侧不是唯一、受保护、单值 Overall GMV 时 fail closed 为 None。
    """

    if comparison is None:
        return None

    def value_for(window: TimeWindowReferenceV2) -> Decimal | None:
        matches = []

        for record in delivery.evidence_pack.evidence_records:
            provenance = record.provenance
            protected = record.protected_result

            if provenance is None or protected is None:
                continue

            if (
                provenance.metric_name != "gmv"
                or provenance.result_grain != "overall"
                or provenance.analysis_window != window
            ):
                continue

            if (
                protected.field_names != ("gmv",)
                or protected.row_count != 1
                or len(protected.rows) != 1
                or set(protected.rows[0]) != {"gmv"}
            ):
                continue

            raw = protected.rows[0].get("gmv")
            if raw is None or isinstance(raw, bool):
                continue

            try:
                matches.append(Decimal(str(raw)))
            except Exception:
                continue

        if len(matches) != 1:
            return None

        return matches[0]

    reference_value = value_for(comparison.reference_window)
    current_value = value_for(comparison.current_window)

    if reference_value is None or current_value is None:
        return None

    return reference_value, current_value


def _build_day93_focused_change_companion_v2(
    *,
    selected_action: AvailableInvestigationActionV2,
    current_prepared: _PreparedInvestigationBindingV2,
    current_execution: InvestigationToolExecutionResultV2,
    context: AccessContext,
    comparison: TimeComparisonContractV2 | None,
    investigation_focus_scope: InvestigationFocusScopeV1 | None,
    geography_focus_scope: GeographyFocusScopeV2 | None = None,
    overall_reference_value: Decimal | None = None,
    overall_current_value: Decimal | None = None,
    runtime_config: GovernanceRuntimeConfig,
    execution_policy: GovernedExecutionPolicy | None,
    request_id: str,
    requested_scope: RequestedScopeResolutionV2 | None,
) -> FocusedChangeBreakdownDeliveryV2 | None:
    """
    F02 Focused Change 的 deterministic companion read。

    Planner 仍只选择一个 action（category / region）。
    只有满足以下条件才追加 reference read：
    - Seed 本身有 comparison；
    - Investigation Focus 已锁定且带可信两期值；
    - 当前 Tool 已真实产生可释放 Evidence。

    reference read 使用：
    - 同一个 Action / Query Plan；
    - 同一个 Authorized + Requested + Focus effective scope；
    - comparison.reference_window。

    它不是新的 Planner 决策，也不开放新的 Action Space。
    """

    dimension = _day93_focused_dimension_for_action_v2(
        selected_action.action_id
    )

    if dimension is None or comparison is None:
        return None

    channel_reference_value = getattr(investigation_focus_scope, "reference_value", None)
    channel_current_value = getattr(investigation_focus_scope, "current_value", None)
    channel_delta = getattr(investigation_focus_scope, "delta", None)

    has_channel_focus_values = (
        investigation_focus_scope is not None
        and channel_reference_value is not None
        and channel_current_value is not None
        and channel_delta is not None
    )
    has_geography_focus_values = (
        geography_focus_scope is not None
        and geography_focus_scope.reference_value is not None
        and geography_focus_scope.current_value is not None
        and geography_focus_scope.delta is not None
    )
    has_overall_values = (
        investigation_focus_scope is None
        and geography_focus_scope is None
        and overall_reference_value is not None
        and overall_current_value is not None
    )

    if not (has_channel_focus_values or has_geography_focus_values or has_overall_values):
        return None

    if current_execution.evidence_reference is None:
        # 当前期本身没有可释放 Evidence 时，不执行 reference companion。
        return None

    current_breakdown = (
        _day93_protected_breakdown_from_prepared_v2(
            prepared=current_prepared,
            analysis_window=comparison.current_window,
        )
    )

    if (
        current_breakdown.evidence_id
        != current_execution.evidence_reference.evidence_id
    ):
        raise ValueError(
            "Focused Change current evidence identity "
            "与 Investigation Tool Evidence 不一致。"
        )

    reference_prepared = _prepare_day89_trusted_binding_v2(
        action=selected_action,
        context=context,
        analysis_window=comparison.reference_window,
        runtime_config=runtime_config,
        execution_policy=execution_policy,
        event_id=(
            f"{request_id}-{selected_action.action_id}-reference"
        ),
        requested_scope=requested_scope,
    )

    # server-owned deterministic companion read：
    # 不经过 Planner，也不消耗一个新的 Investigation Action。
    reference_finalization = reference_prepared.binding.executor()

    if not isinstance(
        reference_finalization,
        GovernedFinalizationResult,
    ):
        raise TypeError(
            "Focused Change reference executor "
            "必须返回 GovernedFinalizationResult。"
        )

    reference_breakdown = (
        _day93_protected_breakdown_from_prepared_v2(
            prepared=reference_prepared,
            analysis_window=comparison.reference_window,
        )
    )

    if has_geography_focus_values:
        assert geography_focus_scope is not None
        return build_geography_focused_change_breakdown_delivery_v2(
            current_breakdown=current_breakdown,
            reference_breakdown=reference_breakdown,
            focus_scope=geography_focus_scope,
            comparison=comparison,
            dimension=dimension,
        )

    if has_channel_focus_values:
        assert investigation_focus_scope is not None
        return build_focused_change_breakdown_delivery_v2(
            current_breakdown=current_breakdown,
            reference_breakdown=reference_breakdown,
            focus_scope=investigation_focus_scope,
            comparison=comparison,
            dimension=dimension,
        )

    assert overall_reference_value is not None
    assert overall_current_value is not None

    return build_global_change_breakdown_delivery_v2(
        current_breakdown=current_breakdown,
        reference_breakdown=reference_breakdown,
        comparison=comparison,
        overall_reference_value=overall_reference_value,
        overall_current_value=overall_current_value,
        dimension=dimension,
    )


def _build_day89_trusted_binding_v2(
    *,
    action: AvailableInvestigationActionV2,
    context: AccessContext,
    analysis_window: TimeWindowReferenceV2,
    runtime_config: GovernanceRuntimeConfig,
    execution_policy: GovernedExecutionPolicy | None,
    event_id: str,
    requested_scope: RequestedScopeResolutionV2 | None = None,
) -> TrustedToolExecutionBindingV2:
    return _prepare_day89_trusted_binding_v2(
        action=action,
        context=context,
        analysis_window=analysis_window,
        runtime_config=runtime_config,
        execution_policy=execution_policy,
        event_id=event_id,
        requested_scope=requested_scope,
    ).binding


def build_day89_gmv_investigation_bindings_v2(
    *,
    actions: tuple[AvailableInvestigationActionV2, ...],
    context: AccessContext,
    analysis_window: TimeWindowReferenceV2,
    runtime_config: GovernanceRuntimeConfig,
    execution_policy: GovernedExecutionPolicy | None,
    request_id: str,
    requested_scope: RequestedScopeResolutionV2 | None = None,
) -> dict[str, TrustedToolExecutionBindingV2]:
    return {
        action.action_id: _build_day89_trusted_binding_v2(
            action=action,
            context=context,
            analysis_window=analysis_window,
            runtime_config=runtime_config,
            execution_policy=execution_policy,
            event_id=(
                f"{request_id}-{action.action_id}"
            ),
            requested_scope=requested_scope,
        )
        for action in actions
    }


def _prepare_day89_gmv_investigation_bindings_v2(
    *,
    actions: tuple[AvailableInvestigationActionV2, ...],
    context: AccessContext,
    analysis_window: TimeWindowReferenceV2,
    runtime_config: GovernanceRuntimeConfig,
    execution_policy: GovernedExecutionPolicy | None,
    request_id: str,
    requested_scope: RequestedScopeResolutionV2 | None = None,
) -> dict[str, _PreparedInvestigationBindingV2]:
    return {
        action.action_id: _prepare_day89_trusted_binding_v2(
            action=action,
            context=context,
            analysis_window=analysis_window,
            runtime_config=runtime_config,
            execution_policy=execution_policy,
            event_id=(
                f"{request_id}-{action.action_id}"
            ),
            requested_scope=requested_scope,
        )
        for action in actions
    }



def _day93_geography_level_for_action_v2(action_id: str) -> GeographyLevelV2 | None:
    return {
        "drill_area": GeographyLevelV2.AREA,
        "drill_province": GeographyLevelV2.PROVINCE,
        "drill_city": GeographyLevelV2.CITY,
    }.get(action_id)


def _day93_parent_geography_member_v2(
    focus: GeographyFocusScopeV2 | None,
):
    if focus is None:
        return None
    return get_geography_member_v2(
        level=focus.level, member_key=focus.member_key
    )


def _day93_promote_geography_focus_v2(
    *,
    focused_change: FocusedChangeBreakdownDeliveryV2 | None,
    selected_action_id: str,
    current_geography_focus: GeographyFocusScopeV2 | None,
) -> tuple[GeographyFocusScopeV2 | None, AvailableInvestigationActionV2 | None]:
    level = _day93_geography_level_for_action_v2(selected_action_id)
    if level is None or focused_change is None:
        return current_geography_focus, None

    assessment = focused_change.assessment
    if (
        assessment is None
        or assessment.pattern != ChangeConcentrationPatternV2.DOMINANT
        or assessment.leader_member_key is None
    ):
        return current_geography_focus, None

    # CITY is the Geography leaf. We do not need to promote another focus,
    # and region_name is intentionally not treated as a fabricated region_code.
    if level == GeographyLevelV2.CITY:
        return current_geography_focus, None

    leader = next(
        (item for item in focused_change.result.members
         if item.member_key == assessment.leader_member_key),
        None,
    )
    if leader is None:
        raise ValueError("DOMINANT Geography leader 不存在于可信 Change Breakdown。")

    parent = None
    if level != GeographyLevelV2.AREA:
        parent = _day93_parent_geography_member_v2(current_geography_focus)
        if parent is None:
            raise ValueError("Province / City promotion 缺少上一层 Geography Focus。")
        if next_geography_level_v2(parent.level) != level:
            raise ValueError("Geography promotion 不能跳层。")

    member = get_geography_member_v2(
        level=level, member_key=leader.member_key, parent=parent
    )
    promoted = build_geography_focus_scope_v2(
        member=member,
        source_evidence_id=focused_change.current_evidence_id,
        reference_value=leader.reference_value,
        current_value=leader.current_value,
        delta=leader.delta,
    )
    next_level = next_geography_level_v2(level)
    next_action = _day93_geography_action_v2(next_level) if next_level is not None else None
    return promoted, next_action


def _day93_append_unlocked_action_to_step_v2(
    *,
    step: Day89InvestigationRuntimeStepResultV2,
    action: AvailableInvestigationActionV2 | None,
) -> Day89InvestigationRuntimeStepResultV2:
    if action is None:
        return step
    if step.transition is None:
        raise ValueError("无法向没有 transition 的 Runtime Step 解锁 Geography Action。")

    planner_state = step.transition.next_state.planner_state
    if action.action_id in set(planner_state.completed_action_ids):
        raise ValueError("已完成的 Geography Action 不能重新解锁。")

    existing = {item.action_id: item for item in planner_state.available_actions}
    if action.action_id in existing:
        if existing[action.action_id] != action:
            raise ValueError("同一 action_id 的 trusted Action Contract 不一致。")
        return step

    next_planner = planner_state.model_copy(
        update={"available_actions": (*planner_state.available_actions, action)}
    )
    next_loop = step.transition.next_state.model_copy(
        update={"planner_state": next_planner}
    )
    next_transition = step.transition.model_copy(update={"next_state": next_loop})
    next_session_after = step.session_after.model_copy(update={"loop_state": next_loop})

    stop_status = step.stop_status
    if stop_status is not None:
        remaining_ids = tuple(item.action_id for item in next_planner.available_actions)
        can_continue = (
            not stop_status.evidence_sufficient
            and bool(remaining_ids)
            and stop_status.current_round < stop_status.max_rounds
            and stop_status.total_steps_used < stop_status.max_total_investigation_steps
        )
        stop_status = stop_status.model_copy(update={
            "uninvestigated_action_ids": remaining_ids,
            "can_continue": can_continue,
            "detail": (
                "本轮 Budget 已停止；上一层 Geography Evidence 已安全解锁下一层，"
                "只有用户明确继续下一轮才会执行。"
            ),
        })

    return step.model_copy(update={
        "transition": next_transition,
        "session_after": next_session_after,
        "stop_status": stop_status,
    })


def run_day93_geography_exploration_v2(
    *,
    seed_result: RuntimeDeliveryBridgeResultV2,
    level: GeographyLevelV2,
    runtime_config: GovernanceRuntimeConfig | None = None,
    execution_policy: GovernedExecutionPolicy | None = None,
) -> FocusedChangeBreakdownDeliveryV2:
    """
    Geography Exploration escape hatch。

    与 Investigation 严格分离：
    - 不创建 / 推进 InvestigationSession；
    - 不消耗 Investigation Step Budget；
    - 不使用上一层 Top1 作为隐式 Focus；
    - 只在原 Requested Scope 内执行用户明确要求的更细层级；
    - 仍完整经过 Governed Planning / Compilation / Execution /
      Result Protection / Audit；
    - 返回两期 Global Change Breakdown，明确只是探索性查看。
    """

    if level not in {
        GeographyLevelV2.PROVINCE,
        GeographyLevelV2.CITY,
    }:
        raise ValueError(
            "Geography Exploration escape hatch 当前只允许 Province / City。"
        )

    if (
        seed_result.status != RuntimeDeliveryBridgeStatusV2.READY
        or seed_result.delivery is None
    ):
        raise ValueError(
            "Geography Exploration 必须从 READY trusted Delivery 启动。"
        )

    delivery = seed_result.delivery
    scope = delivery.evidence_pack.analysis_scope
    comparison = scope.comparison

    if scope.metric_name != "gmv" or comparison is None:
        raise ValueError(
            "Geography Exploration 当前需要带两期 Comparison 的 GMV Seed。"
        )

    overall_values = _day93_overall_gmv_values_from_delivery_v2(
        delivery=delivery,
        comparison=comparison,
    )
    if overall_values is None:
        raise ValueError(
            "Geography Exploration 缺少唯一可信的两期 Overall GMV。"
        )

    action = _day93_geography_action_v2(level)
    dimension = _day93_focused_dimension_for_action_v2(action.action_id)
    if dimension is None:
        raise ValueError("Geography Exploration Action 缺少 dimension mapping。")

    active_config = (
        runtime_config
        if runtime_config is not None
        else load_governance_runtime_config()
    )

    request_id = f"day93-geography-explore-{uuid4().hex}"
    context = build_day89_local_access_context_v2(
        request_id=request_id,
    )

    # 只继承原 Requested Scope；故意不继承上一层 Geography Top1 Focus。
    requested_scope = seed_result.requested_scope

    current_prepared = _prepare_day89_trusted_binding_v2(
        action=action,
        context=context,
        analysis_window=comparison.current_window,
        runtime_config=active_config,
        execution_policy=execution_policy,
        event_id=f"{request_id}-{action.action_id}-current",
        requested_scope=requested_scope,
    )
    current_finalization = current_prepared.binding.executor()
    if not isinstance(current_finalization, GovernedFinalizationResult):
        raise TypeError(
            "Geography Exploration current executor 必须返回 GovernedFinalizationResult。"
        )

    reference_prepared = _prepare_day89_trusted_binding_v2(
        action=action,
        context=context,
        analysis_window=comparison.reference_window,
        runtime_config=active_config,
        execution_policy=execution_policy,
        event_id=f"{request_id}-{action.action_id}-reference",
        requested_scope=requested_scope,
    )
    reference_finalization = reference_prepared.binding.executor()
    if not isinstance(reference_finalization, GovernedFinalizationResult):
        raise TypeError(
            "Geography Exploration reference executor 必须返回 GovernedFinalizationResult。"
        )

    current_breakdown = _day93_protected_breakdown_from_prepared_v2(
        prepared=current_prepared,
        analysis_window=comparison.current_window,
    )
    reference_breakdown = _day93_protected_breakdown_from_prepared_v2(
        prepared=reference_prepared,
        analysis_window=comparison.reference_window,
    )

    reference_value, current_value = overall_values

    return build_global_change_breakdown_delivery_v2(
        current_breakdown=current_breakdown,
        reference_breakdown=reference_breakdown,
        comparison=comparison,
        overall_reference_value=reference_value,
        overall_current_value=current_value,
        dimension=dimension,
    )

def run_day89_agentic_investigation_step_v2(
    *,
    seed_result: RuntimeDeliveryBridgeResultV2,
    reference_date: date,
    runtime_config: GovernanceRuntimeConfig | None = None,
    execution_policy: GovernedExecutionPolicy | None = None,
    planner: PlannerInvokerV2 | None = None,
    planner_model: str | None = None,
    planner_client=None,
    investigation_focus_scope: InvestigationFocusScopeV1 | None = None,
    geography_focus_scope: GeographyFocusScopeV2 | None = None,
    investigation_route: InvestigationRouteV2 | None = None,
    clarification_requirement: (
        ClarificationRequirementV2 | None
    ) = None,
    include_category_action: bool = False,
    budget_policy: InvestigationBudgetPolicyV2 | None = None,
    session_policy: InvestigationSessionPolicyV2 | None = None,
) -> Day89InvestigationRuntimeStepResultV2:
    """
    Day89 第一版 server-side Agentic Investigation entry。

    输入必须是已经 READY 的可信 Delivery。
    当前每次调用最多执行一个 Tool Action。

    默认 Planner：
    DeepSeek proposal -> strict parse -> deterministic Day85 validator。

    测试 / Integration 可以注入 deterministic planner，
    避免把 Loop correctness 与 live model stability 混在一起。
    """

    _ = reference_date  # 保留 API 位置；可信 action time 来自 seed Delivery。

    if (
        seed_result.status
        != RuntimeDeliveryBridgeStatusV2.READY
        or seed_result.delivery is None
    ):
        raise ValueError(
            "Agentic Investigation 必须从 READY trusted Delivery 启动。"
        )

    active_config = (
        runtime_config
        if runtime_config is not None
        else load_governance_runtime_config()
    )

    request_id = (
        f"day89-agentic-{uuid4().hex}"
    )

    context = build_day89_local_access_context_v2(
        request_id=request_id,
    )
    requested_scope = seed_result.requested_scope
    if investigation_route is not None:
        _validate_day93_route_focus_binding_v2(
            route=investigation_route,
            investigation_focus_scope=investigation_focus_scope,
        )

    effective_investigation_scope = (
        merge_requested_scope_with_investigation_focus_v1(
            requested_scope=requested_scope,
            investigation_focus=investigation_focus_scope,
        )
    )
    effective_investigation_scope = (
        merge_requested_scope_with_geography_focus_v2(
            requested_scope=effective_investigation_scope,
            geography_focus=geography_focus_scope,
        )
    )

    actions = build_day89_gmv_investigation_actions_v2(
        delivery=seed_result.delivery,
        requested_scope=effective_investigation_scope,
        include_category=include_category_action,
        include_legacy_region=(clarification_requirement is not None),
    )

    if (
        clarification_requirement is None
        and not actions
    ):
        raise ValueError(
            "当前可信 Delivery 没有剩余已注册 Investigation Action。"
        )

    active_budget = (
        budget_policy
        if budget_policy is not None
        else InvestigationBudgetPolicyV2(
            max_investigation_steps=2,
            max_retries_per_action=0,
        )
    )

    active_session_policy = (
        session_policy
        if session_policy is not None
        else InvestigationSessionPolicyV2(
            max_rounds=2,
            max_total_investigation_steps=4,
        )
    )

    session = build_investigation_session_from_delivery_v2(
        delivery=seed_result.delivery,
        available_actions=actions,
        clarification_requirement=clarification_requirement,
        budget_policy=active_budget,
        session_policy=active_session_policy,
    )

    with start_safe_span_v2(
        name="investigation_round",
        stage="investigation_round",
        request_id=request_id,
        round_number=session.round_number,
    ) as round_span:
        prepared_bindings = (
            _prepare_day89_gmv_investigation_bindings_v2(
                actions=actions,
                context=context,
                analysis_window=(
                    seed_result.delivery.evidence_pack
                    .analysis_scope.analysis_window
                ),
                runtime_config=active_config,
                execution_policy=execution_policy,
                request_id=request_id,
                requested_scope=effective_investigation_scope,
            )
        )

        bindings = {
            action_id: prepared.binding
            for action_id, prepared in prepared_bindings.items()
        }

        if investigation_route is not None:
            if planner is not None:
                raise ValueError(
                    "System Investigation Route 与 injected planner "
                    "不能同时提供。"
                )
            active_planner = _day93_planner_for_route_v2(
                investigation_route
            )
        elif planner is None:
            def active_planner(
                state: InvestigationStateV2,
            ) -> PlannerDecisionV2:
                return plan_next_investigation_step_v2(
                    state=state,
                    model=planner_model,
                    client=planner_client,
                )
        else:
            active_planner = planner

        with start_safe_span_v2(
            name="investigation_step",
            stage="investigation_step",
            request_id=request_id,
            round_number=session.round_number,
        ) as step_span:
            step = run_one_investigation_step_v2(
                session=session,
                bindings=bindings,
                planner=active_planner,
                evidence_sufficient_after_step=False,
            )

            selected_action = (
                step.planner_decision.selected_action
            )
            directive = (
                step.transition.control_decision.directive
                if step.transition is not None
                else None
            )
            stop_reason = (
                step.stop_status.stop_reason
                if step.stop_status is not None
                else None
            )

            if step_span is not None:
                step_span.update(
                    metadata=build_safe_metadata_v2(
                        status=step.status,
                        action_id=(
                            selected_action.action_id
                            if selected_action is not None
                            else None
                        ),
                        directive=directive,
                        stop_reason=stop_reason,
                    )
                )

        if round_span is not None:
            round_span.update(
                metadata=build_safe_metadata_v2(
                    status=step.status,
                    action_id=(
                        selected_action.action_id
                        if selected_action is not None
                        else None
                    ),
                    directive=directive,
                    stop_reason=stop_reason,
                )
            )

        if (
            step.status
            == Day89InvestigationRuntimeStatusV2
            .CLARIFICATION_REQUIRED
        ):
            return step.model_copy(
                update={
                    "requested_scope": requested_scope,
                    "investigation_focus_scope": investigation_focus_scope,
                    "geography_focus_scope": geography_focus_scope,
                }
            )

        if selected_action is None:
            raise ValueError(
                "执行型 Investigation Step 缺少 selected_action。"
            )

        prepared = prepared_bindings.get(
            selected_action.action_id
        )
        if prepared is None:
            raise ValueError(
                "执行型 Investigation Step 缺少 server-trusted binding context。"
            )

        finalization = prepared.capture.finalization
        if finalization is None:
            raise ValueError(
                "Tool 已执行但未捕获 GovernedFinalizationResult；"
                "不能进入 Evidence Delivery。"
            )

        governed_context = Day89GovernedQueryEvidenceContextV2(
            action_id=selected_action.action_id,
            tool_contract=prepared.tool_contract,
            envelope=prepared.envelope,
            compiled=prepared.compiled,
            finalization=finalization,
        )

        overall_values = _day93_overall_gmv_values_from_delivery_v2(
            delivery=seed_result.delivery,
            comparison=(
                seed_result.delivery.evidence_pack
                .analysis_scope.comparison
            ),
        )

        focused_change_breakdown = (
            _build_day93_focused_change_companion_v2(
                selected_action=selected_action,
                current_prepared=prepared,
                current_execution=step.execution_result,
                context=context,
                comparison=(
                    seed_result.delivery.evidence_pack
                    .analysis_scope.comparison
                ),
                investigation_focus_scope=investigation_focus_scope,
                geography_focus_scope=geography_focus_scope,
                overall_reference_value=(
                    overall_values[0]
                    if overall_values is not None
                    else None
                ),
                overall_current_value=(
                    overall_values[1]
                    if overall_values is not None
                    else None
                ),
                runtime_config=active_config,
                execution_policy=execution_policy,
                request_id=request_id,
                requested_scope=effective_investigation_scope,
            )
        )

        promoted_geography_focus, unlocked_action = _day93_promote_geography_focus_v2(
            focused_change=focused_change_breakdown,
            selected_action_id=selected_action.action_id,
            current_geography_focus=geography_focus_scope,
        )
        step = _day93_append_unlocked_action_to_step_v2(
            step=step, action=unlocked_action
        )

        return step.model_copy(
            update={
                "governed_query_context": governed_context,
                "requested_scope": requested_scope,
                "investigation_focus_scope": investigation_focus_scope,
                "geography_focus_scope": promoted_geography_focus,
                "focused_change_breakdown": focused_change_breakdown,
            }
        )

def continue_day89_agentic_investigation_step_v2(
    *,
    delivery: EvidencePackDeliveryV2,
    continuation_state: Day89InvestigationContinuationStateV2,
    user_requested_continue: bool,
    runtime_config: GovernanceRuntimeConfig | None = None,
    execution_policy: GovernedExecutionPolicy | None = None,
    planner: PlannerInvokerV2 | None = None,
    planner_model: str | None = None,
    planner_client=None,
) -> Day89InvestigationRuntimeStepResultV2:
    """
    用户明确 Continue 后恢复同一个 Investigation Session。

    关键边界：
    - continuation 必须来自 Day86 can_continue=True；
    - user_requested_continue 必须显式为 True；
    - 复用上一轮 remaining available_actions；
    - 不重新开放 completed action；
    - 每次调用仍最多执行一个 Tool；
    - server-trusted binding / envelope / compiled 在本次请求内重建，
      不从浏览器 Session 恢复。
    """

    session = continue_investigation_session_v2(
        session=continuation_state.session_before_stop,
        stop_status=continuation_state.stop_status,
        transition=continuation_state.stopped_transition,
        user_requested_continue=user_requested_continue,
    )

    delivery_scope = delivery.evidence_pack.analysis_scope
    session_scope = (
        session.loop_state.planner_state.insight.analysis_scope
    )

    if (
        delivery_scope.metric_name != session_scope.metric_name
        or delivery_scope.analysis_window
        != session_scope.analysis_window
        or delivery_scope.comparison != session_scope.comparison
    ):
        raise ValueError(
            "Continuation Delivery 与 Session analysis scope 不一致。"
        )

    delivery_evidence_ids = {
        item.reference.evidence_id
        for item in delivery.evidence_pack.evidence_records
    }
    session_evidence_ids = {
        item.evidence_id
        for item in session.loop_state.planner_state.insight.evidence
    }

    missing = session_evidence_ids - delivery_evidence_ids
    if missing:
        raise ValueError(
            "Continuation Delivery 缺少 Session 已知 Evidence："
            f"{sorted(missing)}"
        )

    actions = (
        session.loop_state.planner_state.available_actions
    )
    if not actions:
        raise ValueError(
            "Continuation Session 没有剩余合法 Investigation Action。"
        )

    active_config = (
        runtime_config
        if runtime_config is not None
        else load_governance_runtime_config()
    )

    request_id = (
        f"day89-agentic-continue-{uuid4().hex}"
    )
    context = build_day89_local_access_context_v2(
        request_id=request_id,
    )
    requested_scope = continuation_state.requested_scope
    investigation_focus_scope = continuation_state.investigation_focus_scope
    geography_focus_scope = continuation_state.geography_focus_scope
    effective_investigation_scope = (
        merge_requested_scope_with_investigation_focus_v1(
            requested_scope=requested_scope,
            investigation_focus=investigation_focus_scope,
        )
    )
    effective_investigation_scope = (
        merge_requested_scope_with_geography_focus_v2(
            requested_scope=effective_investigation_scope,
            geography_focus=geography_focus_scope,
        )
    )

    prepared_bindings = (
        _prepare_day89_gmv_investigation_bindings_v2(
            actions=actions,
            context=context,
            analysis_window=delivery_scope.analysis_window,
            runtime_config=active_config,
            execution_policy=execution_policy,
            request_id=request_id,
            requested_scope=effective_investigation_scope,
        )
    )

    bindings = {
        action_id: prepared.binding
        for action_id, prepared in prepared_bindings.items()
    }

    preferred_geography_action_id = None
    if geography_focus_scope is not None:
        next_level = next_geography_level_v2(
            geography_focus_scope.level
        )
        if next_level is not None:
            candidate = _day93_geography_action_v2(next_level)
            if candidate.action_id in {item.action_id for item in actions}:
                preferred_geography_action_id = candidate.action_id

    if planner is None and preferred_geography_action_id is not None:
        active_planner = _day93_planner_for_action_id_v2(
            preferred_geography_action_id,
            rationale=(
                "上一层 Geography Change Evidence 已达到 DOMINANT，"
                "因此只沿已解锁的下一层 Geography Action 继续。"
            ),
        )
    elif planner is None:
        def active_planner(
            state: InvestigationStateV2,
        ) -> PlannerDecisionV2:
            return plan_next_investigation_step_v2(
                state=state,
                model=planner_model,
                client=planner_client,
            )
    else:
        active_planner = planner

    step = run_one_investigation_step_v2(
        session=session,
        bindings=bindings,
        planner=active_planner,
        evidence_sufficient_after_step=False,
    )

    if (
        step.status
        == Day89InvestigationRuntimeStatusV2
        .CLARIFICATION_REQUIRED
    ):
        return step.model_copy(
            update={
                "requested_scope": requested_scope,
                "investigation_focus_scope": investigation_focus_scope,
                "geography_focus_scope": geography_focus_scope,
            }
        )

    selected_action = step.planner_decision.selected_action
    if selected_action is None:
        raise ValueError(
            "Continuation 执行型 Step 缺少 selected_action。"
        )

    prepared = prepared_bindings.get(
        selected_action.action_id
    )
    if prepared is None:
        raise ValueError(
            "Continuation Step 缺少 server-trusted binding context。"
        )

    finalization = prepared.capture.finalization
    if finalization is None:
        raise ValueError(
            "Continuation Tool 已执行但未捕获 GovernedFinalizationResult。"
        )

    context_record = Day89GovernedQueryEvidenceContextV2(
        action_id=selected_action.action_id,
        tool_contract=prepared.tool_contract,
        envelope=prepared.envelope,
        compiled=prepared.compiled,
        finalization=finalization,
    )

    overall_values = _day93_overall_gmv_values_from_delivery_v2(
        delivery=delivery,
        comparison=delivery_scope.comparison,
    )

    focused_change_breakdown = (
        _build_day93_focused_change_companion_v2(
            selected_action=selected_action,
            current_prepared=prepared,
            current_execution=step.execution_result,
            context=context,
            comparison=delivery_scope.comparison,
            investigation_focus_scope=investigation_focus_scope,
            geography_focus_scope=geography_focus_scope,
            overall_reference_value=(
                overall_values[0]
                if overall_values is not None
                else None
            ),
            overall_current_value=(
                overall_values[1]
                if overall_values is not None
                else None
            ),
            runtime_config=active_config,
            execution_policy=execution_policy,
            request_id=request_id,
            requested_scope=effective_investigation_scope,
        )
    )

    promoted_geography_focus, unlocked_action = _day93_promote_geography_focus_v2(
        focused_change=focused_change_breakdown,
        selected_action_id=selected_action.action_id,
        current_geography_focus=geography_focus_scope,
    )
    step = _day93_append_unlocked_action_to_step_v2(
        step=step, action=unlocked_action
    )

    return step.model_copy(
        update={
            "governed_query_context": context_record,
            "requested_scope": requested_scope,
            "investigation_focus_scope": investigation_focus_scope,
            "geography_focus_scope": promoted_geography_focus,
            "focused_change_breakdown": focused_change_breakdown,
        }
    )

def resume_day89_agentic_investigation_after_clarification_v2(
    *,
    pending: Day89PendingClarificationStateV2,
    response: ClarificationResponseV2,
    seed_result: RuntimeDeliveryBridgeResultV2 | None = None,
    runtime_config: GovernanceRuntimeConfig | None = None,
    execution_policy: GovernedExecutionPolicy | None = None,
    planner: PlannerInvokerV2 | None = None,
    planner_model: str | None = None,
    planner_client=None,
) -> Day89ClarificationResumeResultV2:
    """
    用户回答 Clarification 后恢复同一个 bounded Investigation。

    顺序严格固定：
    1. deterministic resolver；
    2. 只有 RESOLVED 才构造新 Session；
    3. 只对 resolver 保留下来的已有合法 Action 建 trusted binding；
    4. Planner 再运行；
    5. 最多执行一个 Governed Tool。

    UNRESOLVED / CONTRACT_MISMATCH 时绝不执行 Tool。
    """

    planner_state = (
        pending.session.loop_state.planner_state
    )

    resolution = resolve_clarification_response_v2(
        state=planner_state,
        contract=pending.resolution_contract,
        response=response,
    )

    if (
        resolution.status
        != ClarificationResolutionStatusV2.RESOLVED
    ):
        return Day89ClarificationResumeResultV2(
            resolution=resolution,
            runtime_step=None,
        )

    resolved_state = resolution.resolved_state
    assert resolved_state is not None

    # Resolver 的职责只是把“本轮执行选择”收窄到一个 Action。
    # Pending Session 仍然是 server-trusted 的完整调查空间；
    # 用户选择一个首轮方向不应被解释为放弃其余合法方向。
    original_actions = planner_state.available_actions

    actions = resolved_state.available_actions
    if len(actions) != 1:
        raise ValueError(
            "Day89 Direction Clarification Resolution "
            "必须收窄到恰好一个合法 Action。"
        )

    selected_for_execution = actions[0]
    original_by_id = {
        action.action_id: action
        for action in original_actions
    }
    original_selected = original_by_id.get(
        selected_for_execution.action_id
    )

    if original_selected is None:
        raise ValueError(
            "Clarification Resolver 选择的 Action "
            "必须来自原 Pending Session available_actions。"
        )

    if original_selected != selected_for_execution:
        raise ValueError(
            "Clarification Resolver 不能修改原 Action 的 "
            "Tool Contract 或 trusted arguments。"
        )

    completed_ids = set(
        planner_state.completed_action_ids
    )
    remaining_session_actions = tuple(
        action
        for action in original_actions
        if (
            action.action_id != selected_for_execution.action_id
            and action.action_id not in completed_ids
        )
    )

    session = _session_with_resolved_planner_state_v2(
        session=pending.session,
        resolved_state=resolved_state,
    )

    active_config = (
        runtime_config
        if runtime_config is not None
        else load_governance_runtime_config()
    )

    request_id = (
        f"day89-agentic-clarification-resume-{uuid4().hex}"
    )
    context = build_day89_local_access_context_v2(
        request_id=request_id,
    )
    requested_scope = pending.requested_scope
    investigation_focus_scope = pending.investigation_focus_scope
    geography_focus_scope = pending.geography_focus_scope
    effective_investigation_scope = (
        merge_requested_scope_with_investigation_focus_v1(
            requested_scope=requested_scope,
            investigation_focus=investigation_focus_scope,
        )
    )
    effective_investigation_scope = (
        merge_requested_scope_with_geography_focus_v2(
            requested_scope=effective_investigation_scope,
            geography_focus=geography_focus_scope,
        )
    )

    prepared_bindings = (
        _prepare_day89_gmv_investigation_bindings_v2(
            actions=actions,
            context=context,
            analysis_window=(
                resolved_state.insight.analysis_scope
                .analysis_window
            ),
            runtime_config=active_config,
            execution_policy=execution_policy,
            request_id=request_id,
            requested_scope=effective_investigation_scope,
        )
    )

    bindings = {
        action_id: prepared.binding
        for action_id, prepared
        in prepared_bindings.items()
    }

    if planner is None:
        def active_planner(
            state: InvestigationStateV2,
        ) -> PlannerDecisionV2:
            return plan_next_investigation_step_v2(
                state=state,
                model=planner_model,
                client=planner_client,
            )
    else:
        active_planner = planner

    step = run_one_investigation_step_v2(
        session=session,
        bindings=bindings,
        planner=active_planner,
        evidence_sufficient_after_step=False,
        trusted_remaining_actions_after_selected=(
            remaining_session_actions
        ),
    )

    if (
        step.status
        == Day89InvestigationRuntimeStatusV2
        .CLARIFICATION_REQUIRED
    ):
        raise ValueError(
            "Resolution 已清除 trusted prerequisite，"
            "Planner 不得再次无依据 CLARIFY。"
        )

    selected_action = step.planner_decision.selected_action
    if selected_action is None:
        raise ValueError(
            "Clarification Resume 执行型 Step 缺少 selected_action。"
        )

    prepared = prepared_bindings.get(
        selected_action.action_id
    )
    if prepared is None:
        raise ValueError(
            "Clarification Resume 缺少 server-trusted binding context。"
        )

    finalization = prepared.capture.finalization
    if finalization is None:
        raise ValueError(
            "Clarification Resume Tool 已执行，"
            "但未捕获 GovernedFinalizationResult。"
        )

    governed_context = Day89GovernedQueryEvidenceContextV2(
        action_id=selected_action.action_id,
        tool_contract=prepared.tool_contract,
        envelope=prepared.envelope,
        compiled=prepared.compiled,
        finalization=finalization,
    )

    overall_values = None
    if (
        seed_result is not None
        and seed_result.status == RuntimeDeliveryBridgeStatusV2.READY
        and seed_result.delivery is not None
    ):
        overall_values = _day93_overall_gmv_values_from_delivery_v2(
            delivery=seed_result.delivery,
            comparison=(
                resolved_state.insight.analysis_scope.comparison
            ),
        )

    focused_change_breakdown = (
        _build_day93_focused_change_companion_v2(
            selected_action=selected_action,
            current_prepared=prepared,
            current_execution=step.execution_result,
            context=context,
            comparison=(
                resolved_state.insight.analysis_scope.comparison
            ),
            investigation_focus_scope=investigation_focus_scope,
            geography_focus_scope=geography_focus_scope,
            overall_reference_value=(
                overall_values[0]
                if overall_values is not None
                else None
            ),
            overall_current_value=(
                overall_values[1]
                if overall_values is not None
                else None
            ),
            runtime_config=active_config,
            execution_policy=execution_policy,
            request_id=request_id,
            requested_scope=effective_investigation_scope,
        )
    )

    promoted_geography_focus, unlocked_action = _day93_promote_geography_focus_v2(
        focused_change=focused_change_breakdown,
        selected_action_id=selected_action.action_id,
        current_geography_focus=geography_focus_scope,
    )
    step = _day93_append_unlocked_action_to_step_v2(
        step=step, action=unlocked_action
    )

    step_with_context = step.model_copy(
        update={
            "governed_query_context": governed_context,
            "requested_scope": requested_scope,
            "investigation_focus_scope": investigation_focus_scope,
            "geography_focus_scope": promoted_geography_focus,
            "focused_change_breakdown": focused_change_breakdown,
        }
    )

    return Day89ClarificationResumeResultV2(
        resolution=resolution,
        runtime_step=step_with_context,
    )
