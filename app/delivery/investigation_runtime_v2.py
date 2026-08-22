from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, model_validator

from app.agents.evidence_pack_delivery_v2 import (
    EvidencePackDeliveryV2,
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
    - server-owned Resolution Contract。

    不包含 governed_query_context / compiled SQL / parameters / secrets。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    session: InvestigationSessionStateV2
    resolution_contract: ClarificationResolutionContractV2

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

    只保存 Day86 已定义的结构化 Session / STOP / Transition，
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

    remaining_actions = tuple(
        action
        for action in planner_state.available_actions
        if action.action_id != selected_action.action_id
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


def build_day89_gmv_investigation_actions_v2(
    *,
    delivery: EvidencePackDeliveryV2,
    include_category: bool = False,
) -> tuple[AvailableInvestigationActionV2, ...]:
    """
    Day89 第一版生产 Action Catalog。

    只开放已经在 Day86 PostgreSQL Loop 中验证过的：
    - drill_channel -> gmv_channel_v2
    - drill_region  -> gmv_region_v2

    若 Seed Delivery 已经是某个 grain，则不重复开放相同方向。
    """

    scope = delivery.evidence_pack.analysis_scope

    if scope.metric_name != "gmv":
        raise ValueError(
            "Day89 Agentic Runtime v2_0 只注册 GMV Investigation Actions。"
        )

    specs = [
        ("drill_channel", "gmv_channel_v2", "channel"),
        ("drill_region", "gmv_region_v2", "region"),
    ]

    if include_category:
        # HITL production path 显式开放已经存在于
        # Dataset V2 Query Plan Catalog 的 GMV Category drill-down。
        # 默认仍为 False，避免改变既有 one-step production contract。
        specs.append(
            ("drill_category", "gmv_category_v2", "category")
        )

    actions: list[AvailableInvestigationActionV2] = []

    for action_id, plan_name, result_grain in specs:
        if scope.result_grain == result_grain:
            continue

        actions.append(
            AvailableInvestigationActionV2(
                action_id=action_id,
                tool_contract=_day89_tool_contract_v2(
                    result_grain=result_grain,
                ),
                arguments=(
                    BoundToolArgumentV2(
                        name="metric_name",
                        value="gmv",
                    ),
                    BoundToolArgumentV2(
                        name="query_plan_name",
                        value=plan_name,
                    ),
                    BoundToolArgumentV2(
                        name="result_grain",
                        value=result_grain,
                    ),
                ),
            )
        )

    return tuple(actions)


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


def _build_day89_trusted_binding_v2(
    *,
    action: AvailableInvestigationActionV2,
    context: AccessContext,
    analysis_window: TimeWindowReferenceV2,
    runtime_config: GovernanceRuntimeConfig,
    execution_policy: GovernedExecutionPolicy | None,
    event_id: str,
) -> TrustedToolExecutionBindingV2:
    return _prepare_day89_trusted_binding_v2(
        action=action,
        context=context,
        analysis_window=analysis_window,
        runtime_config=runtime_config,
        execution_policy=execution_policy,
        event_id=event_id,
    ).binding


def build_day89_gmv_investigation_bindings_v2(
    *,
    actions: tuple[AvailableInvestigationActionV2, ...],
    context: AccessContext,
    analysis_window: TimeWindowReferenceV2,
    runtime_config: GovernanceRuntimeConfig,
    execution_policy: GovernedExecutionPolicy | None,
    request_id: str,
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
        )
        for action in actions
    }


def run_day89_agentic_investigation_step_v2(
    *,
    seed_result: RuntimeDeliveryBridgeResultV2,
    reference_date: date,
    runtime_config: GovernanceRuntimeConfig | None = None,
    execution_policy: GovernedExecutionPolicy | None = None,
    planner: PlannerInvokerV2 | None = None,
    planner_model: str | None = None,
    planner_client=None,
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

    actions = build_day89_gmv_investigation_actions_v2(
        delivery=seed_result.delivery,
        include_category=include_category_action,
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
            )
        )

        bindings = {
            action_id: prepared.binding
            for action_id, prepared in prepared_bindings.items()
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
            return step

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

        return step.model_copy(
            update={
                "governed_query_context": governed_context,
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

    prepared_bindings = (
        _prepare_day89_gmv_investigation_bindings_v2(
            actions=actions,
            context=context,
            analysis_window=delivery_scope.analysis_window,
            runtime_config=active_config,
            execution_policy=execution_policy,
            request_id=request_id,
        )
    )

    bindings = {
        action_id: prepared.binding
        for action_id, prepared in prepared_bindings.items()
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
    )

    if (
        step.status
        == Day89InvestigationRuntimeStatusV2
        .CLARIFICATION_REQUIRED
    ):
        return step

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

    return step.model_copy(
        update={
            "governed_query_context": context_record,
        }
    )

def resume_day89_agentic_investigation_after_clarification_v2(
    *,
    pending: Day89PendingClarificationStateV2,
    response: ClarificationResponseV2,
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

    session = _session_with_resolved_planner_state_v2(
        session=pending.session,
        resolved_state=resolved_state,
    )

    actions = resolved_state.available_actions
    if len(actions) != 1:
        raise ValueError(
            "Day89 Direction Clarification Resolution "
            "必须收窄到恰好一个合法 Action。"
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

    step_with_context = step.model_copy(
        update={
            "governed_query_context": governed_context,
        }
    )

    return Day89ClarificationResumeResultV2(
        resolution=resolution,
        runtime_step=step_with_context,
    )
