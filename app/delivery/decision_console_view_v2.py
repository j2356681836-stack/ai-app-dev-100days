from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.agents.anomaly_detection_v2 import (
    AnomalyChangeTypeV2,
    AnomalyDecisionReasonV2,
    AnomalyDecisionStatusV2,
    AnomalyDecisionV2,
    AnomalyDirectionV2,
)
from app.agents.contribution_analysis_v2 import (
    ContributionAnalysisResultV2,
    ContributionDirectionV2,
    ContributionReconciliationStatusV2,
)
from app.agents.evidence_pack_delivery_v2 import (
    EvidencePackDeliveryV2,
    EvidenceSufficiencyStatusV2,
    MetricDefinitionSnapshotV2,
)
from app.agents.metric_comparison_v2 import (
    MetricComparisonResultV2,
    RelativeChangeStatusV2,
)
from app.agents.investigation_loop_v2 import (
    InvestigationLoopTransitionV2,
    InvestigationStopReasonV2,
    InvestigationStopStatusV2,
    LoopDirectiveV2,
    ToolObservationStatusV2,
)
from app.agents.investigation_planner_v2 import (
    InvestigationStateV2,
    PlannerDecisionTypeV2,
    PlannerDecisionV2,
)
from app.semantic_layer.time_comparison_contract_v2 import (
    ComparisonTypeV2,
    TimeWindowReferenceV2,
)
from app.agents.evidence_pack_v2 import EvidenceTypeV2


VIEW_CONTRACT_VERSION = "day89_decision_console_view_v2_7"


class VerificationEvidenceViewV2(BaseModel):
    """
    Day89 Data Verification 中一条 Governed Evidence 的安全投影。

    不暴露 raw SQL / raw parameters / blocked rows。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    evidence_id: str
    dataset_name: str
    metric_name: str
    result_grain: str
    analysis_window: TimeWindowReferenceV2
    scope_summary: str | None

    plan_name: str
    tool_name: str
    tool_version: str
    audit_event_id: str

    field_names: tuple[str, ...]
    row_count: int


class MetricComparisonViewV2(BaseModel):
    """
    Day89 KPI / Comparison Card 的只读投影。

    absolute_change / relative_change 完全继承 MetricComparisonResultV2。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    metric_name: str
    comparison_type: ComparisonTypeV2

    current_window: TimeWindowReferenceV2
    reference_window: TimeWindowReferenceV2

    current_value: Decimal
    reference_value: Decimal
    absolute_change: Decimal
    relative_change: Decimal | None
    relative_change_status: RelativeChangeStatusV2

    current_evidence_id: str
    reference_evidence_id: str


class DataVerificationViewV2(BaseModel):
    """
    Day89 Data Verification 的第一版。

    UI 可以从 KPI 追到 Metric Definition 与两侧 Governed Evidence。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    metric_definition: MetricDefinitionSnapshotV2
    current_evidence: VerificationEvidenceViewV2
    reference_evidence: VerificationEvidenceViewV2


class ProtectedBreakdownViewV2(BaseModel):
    """
    Day89 Protected Business Breakdown Table 的只读投影。

    rows 必须已经来自 Day87 ProtectedResultV2。
    本层不查询数据库、不重新聚合、不补行、不排序业务结果。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    evidence_id: str
    metric_name: str
    result_grain: str
    analysis_window: TimeWindowReferenceV2
    scope_summary: str | None

    field_names: tuple[str, ...]
    rows: tuple[dict[str, Any], ...]
    row_count: int

    dataset_name: str
    plan_name: str
    tool_name: str
    tool_version: str
    audit_event_id: str


class InvestigationTraceStepViewV2(BaseModel):
    """
    Day89 Investigation Trace 的一条业务可见步骤。

    它来自 Day86 已发生的 Tool Observation + deterministic
    Loop Control Decision，不重新推断 Planner 意图。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    sequence_number: int
    selected_action_id: str
    attempt_number: int

    observation_status: ToolObservationStatusV2
    failure_code: str | None
    retryable: bool
    produced_evidence_ids: tuple[str, ...]
    observation_evidence_id: str
    summary: str

    next_directive: LoopDirectiveV2
    stop_reason: InvestigationStopReasonV2 | None


class InvestigationRuntimeControlViewV2(BaseModel):
    """
    Day89 Runtime HITL 的第一版停止 / continuation 投影。

    can_continue=False：
    UI 不得提供“继续调查”执行入口。

    can_continue=True：
    只表示用户可以显式请求下一轮；
    绝不表示系统可以自动续轮。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    stop_reason: InvestigationStopReasonV2
    evidence_sufficient: bool
    uninvestigated_action_ids: tuple[str, ...]
    can_continue: bool

    current_round: int
    max_rounds: int
    total_steps_used: int
    max_total_investigation_steps: int

    detail: str


class RuntimeClarificationViewV2(BaseModel):
    """
    Day89 Runtime Clarification HITL 的 UI 投影。

    requirement_source / requirement_reason：
    来自上游可信 ClarificationRequirementV2。

    clarification_prompt：
    来自已经通过 Day85 deterministic validator 的
    PlannerDecisionV2.CLARIFY。

    requires_user_response=True 表示：
    当前不能继续执行 Tool，必须先由用户明确回答。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    requirement_source: str
    requirement_reason: str
    clarification_prompt: str
    rationale: str

    requires_user_response: bool = True
    tool_execution_blocked: bool = True


class EvidenceDrawerRecordViewV2(BaseModel):
    """
    Day89 Evidence Drawer 中的一条安全证据摘要。

    Business / Analyst View 只暴露验证所需元数据：
    - Evidence identity / type / lineage；
    - safe provenance summary；
    - released result schema / row_count；
    - investigation observation summary。

    不暴露：
    - raw SQL；
    - SQL parameters；
    - blocked/raw rows；
    - authorization 内部对象。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    evidence_id: str
    evidence_type: EvidenceTypeV2
    source: str
    description: str | None
    parent_evidence_ids: tuple[str, ...]

    dataset_name: str | None = None
    metric_name: str | None = None
    result_grain: str | None = None
    analysis_window: TimeWindowReferenceV2 | None = None
    scope_summary: str | None = None

    plan_name: str | None = None
    tool_name: str | None = None
    tool_version: str | None = None
    audit_event_id: str | None = None

    released_field_names: tuple[str, ...] = ()
    released_row_count: int | None = None

    observation_action_id: str | None = None
    observation_status: str | None = None
    observation_summary: str | None = None


class EvidenceDrawerViewV2(BaseModel):
    """
    Day89 Evidence Drawer 的统一安全投影。

    Metric Definition 与 Evidence Sufficiency 直接继承
    EvidencePackDeliveryV2，不由 UI 重建。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    metric_definition: MetricDefinitionSnapshotV2
    sufficiency_status: EvidenceSufficiencyStatusV2
    confidence_level: str
    sufficiency_basis: tuple[str, ...]

    records: tuple[EvidenceDrawerRecordViewV2, ...]


class ContributionMemberViewV2(BaseModel):
    """
    Day89 Contribution 的 UI 投影。

    这里只复制 Day84 已经计算完成的可信结果，
    不重新计算 delta / contribution_rate。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    member_key: str
    member_label: str
    current_value: Decimal
    reference_value: Decimal
    delta: Decimal
    contribution_rate: Decimal | None
    direction: ContributionDirectionV2


class ContributionViewV2(BaseModel):
    """
    Day89 Contribution Visualization 的结构化输入。

    reconciliation 结果完全继承 Day84 Contribution Core，
    Delivery Layer 不重新计算。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    evidence_id: str

    metric_name: str
    dimension_name: str

    current_overall_value: Decimal
    reference_overall_value: Decimal
    overall_delta: Decimal

    members: tuple[ContributionMemberViewV2, ...]

    negative_change_ranking: tuple[str, ...]
    positive_change_ranking: tuple[str, ...]

    sum_member_delta: Decimal
    unexplained_remainder: Decimal
    reconciliation_status: ContributionReconciliationStatusV2


class AnomalyPolicyViewV2(BaseModel):
    """
    Day89 Anomaly Policy 的只读投影。

    这些字段全部来自 Day83 已经使用的 deterministic policy。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    change_type: AnomalyChangeTypeV2
    direction: AnomalyDirectionV2
    threshold_value: Decimal
    sample_metric_name: str
    minimum_sample_value: Decimal
    policy_version: str


class AnomalyViewV2(BaseModel):
    """
    Day89 Anomaly Evaluation 的结构化投影。

    注意：
    - status 是 Day83 Detector 的 verdict；
    - show_anomaly_marker 只由 status == ANOMALY 映射；
    - 非 ANOMALY 状态不能被 UI 包装成 detected anomaly；
    - POLICY_NOT_FOUND 不伪造 policy。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    evidence_id: str | None = None

    metric_name: str
    status: AnomalyDecisionStatusV2
    reason_code: AnomalyDecisionReasonV2

    current_value: Decimal
    reference_value: Decimal
    absolute_change: Decimal
    relative_change: Decimal | None

    current_sample_value: Decimal
    reference_sample_value: Decimal

    policy: AnomalyPolicyViewV2 | None = None

    show_anomaly_marker: bool
    published_as_detected_anomaly: bool


class DecisionConsoleViewV2(BaseModel):
    """
    Day89 Decision Console 的 Business Delivery View。

    它负责 projection，不负责新的业务分析。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    contract_version: str = VIEW_CONTRACT_VERSION

    metric_name: str
    result_grain: str | None
    scope_summary: str | None

    evidence_sufficiency: EvidenceSufficiencyStatusV2
    evidence_drawer: EvidenceDrawerViewV2

    confirmed_facts: tuple[str, ...]
    candidate_hypotheses: tuple[str, ...]
    unknowns: tuple[str, ...]
    recommended_checks: tuple[str, ...]

    comparison: MetricComparisonViewV2 | None = None
    verification: DataVerificationViewV2 | None = None
    breakdown: ProtectedBreakdownViewV2 | None = None
    investigation_trace: tuple[InvestigationTraceStepViewV2, ...] = ()
    runtime_control: InvestigationRuntimeControlViewV2 | None = None
    clarification: RuntimeClarificationViewV2 | None = None
    contribution: ContributionViewV2 | None = None
    anomaly: AnomalyViewV2 | None = None


def _evidence_record_by_id(
    *,
    delivery: EvidencePackDeliveryV2,
    evidence_id: str,
):
    records = {
        record.reference.evidence_id: record
        for record in delivery.evidence_pack.evidence_records
    }
    return records.get(evidence_id)


def _build_verification_evidence_view_v2(
    *,
    delivery: EvidencePackDeliveryV2,
    evidence_id: str,
    expected_window: TimeWindowReferenceV2,
) -> VerificationEvidenceViewV2:
    record = _evidence_record_by_id(
        delivery=delivery,
        evidence_id=evidence_id,
    )

    if record is None:
        raise ValueError(
            "Metric Comparison Evidence 不存在于当前 Evidence Pack。"
        )

    if (
        record.evidence_type
        != EvidenceTypeV2.GOVERNED_QUERY_RESULT
    ):
        raise ValueError(
            "Metric Comparison 只能绑定 GOVERNED_QUERY_RESULT。"
        )

    if (
        record.provenance is None
        or record.protected_result is None
    ):
        raise ValueError(
            "Governed Query Evidence 必须包含 provenance "
            "与 protected_result。"
        )

    if record.provenance.analysis_window != expected_window:
        raise ValueError(
            "Metric Comparison Evidence 的 analysis_window "
            "与 current/reference window 不一致。"
        )

    return VerificationEvidenceViewV2(
        evidence_id=evidence_id,
        dataset_name=record.provenance.dataset_name,
        metric_name=record.provenance.metric_name,
        result_grain=record.provenance.result_grain,
        analysis_window=record.provenance.analysis_window,
        scope_summary=record.provenance.scope_summary,
        plan_name=record.provenance.plan_name,
        tool_name=record.provenance.tool_name,
        tool_version=record.provenance.tool_version,
        audit_event_id=record.provenance.audit_event_id,
        field_names=record.protected_result.field_names,
        row_count=record.protected_result.row_count,
    )


def _build_metric_comparison_projection_v2(
    *,
    delivery: EvidencePackDeliveryV2,
    result: MetricComparisonResultV2,
) -> tuple[
    MetricComparisonViewV2,
    DataVerificationViewV2,
]:
    scope = delivery.evidence_pack.analysis_scope

    if result.metric_name != scope.metric_name:
        raise ValueError(
            "Metric Comparison metric 与 Delivery metric 不一致。"
        )

    if (
        scope.comparison is None
        or result.comparison != scope.comparison
    ):
        raise ValueError(
            "Metric Comparison contract 与 Delivery comparison 不一致。"
        )

    if result.current_evidence_id == result.reference_evidence_id:
        raise ValueError(
            "current/reference comparison evidence 不能使用同一 evidence_id。"
        )

    current_evidence = _build_verification_evidence_view_v2(
        delivery=delivery,
        evidence_id=result.current_evidence_id,
        expected_window=result.comparison.current_window,
    )
    reference_evidence = _build_verification_evidence_view_v2(
        delivery=delivery,
        evidence_id=result.reference_evidence_id,
        expected_window=result.comparison.reference_window,
    )

    if (
        current_evidence.metric_name != result.metric_name
        or reference_evidence.metric_name != result.metric_name
    ):
        raise ValueError(
            "Metric Comparison Evidence metric 与结果 metric 不一致。"
        )

    comparison_view = MetricComparisonViewV2(
        metric_name=result.metric_name,
        comparison_type=result.comparison.comparison_type,
        current_window=result.comparison.current_window,
        reference_window=result.comparison.reference_window,
        current_value=result.current_value,
        reference_value=result.reference_value,
        absolute_change=result.absolute_change,
        relative_change=result.relative_change,
        relative_change_status=result.relative_change_status,
        current_evidence_id=result.current_evidence_id,
        reference_evidence_id=result.reference_evidence_id,
    )

    verification_view = DataVerificationViewV2(
        metric_definition=delivery.metric_definition,
        current_evidence=current_evidence,
        reference_evidence=reference_evidence,
    )

    return comparison_view, verification_view


def _build_protected_breakdown_view_v2(
    *,
    delivery: EvidencePackDeliveryV2,
    breakdown_evidence_id: str,
) -> ProtectedBreakdownViewV2:
    """
    将当前 analysis window 的受保护业务分解结果投影给 UI。

    这里只接受 Evidence Pack 中已经释放的 GOVERNED_QUERY_RESULT。
    """

    evidence_id = breakdown_evidence_id.strip()
    if not evidence_id:
        raise ValueError(
            "breakdown_evidence_id 不能为空。"
        )

    record = _evidence_record_by_id(
        delivery=delivery,
        evidence_id=evidence_id,
    )

    if record is None:
        raise ValueError(
            "Breakdown Evidence 不存在于当前 Evidence Pack。"
        )

    if (
        record.evidence_type
        != EvidenceTypeV2.GOVERNED_QUERY_RESULT
    ):
        raise ValueError(
            "Breakdown 只能绑定 GOVERNED_QUERY_RESULT。"
        )

    if (
        record.provenance is None
        or record.protected_result is None
    ):
        raise ValueError(
            "Breakdown Governed Evidence 必须包含 provenance "
            "与 protected_result。"
        )

    scope = delivery.evidence_pack.analysis_scope

    if record.provenance.metric_name != scope.metric_name:
        raise ValueError(
            "Breakdown Evidence metric 与 Delivery metric 不一致。"
        )

    if (
        record.provenance.analysis_window
        != scope.analysis_window
    ):
        raise ValueError(
            "Day89 第一版 Breakdown 只展示当前 analysis_window "
            "的受保护结果。"
        )

    if (
        scope.result_grain is not None
        and record.provenance.result_grain
        != scope.result_grain
    ):
        raise ValueError(
            "Breakdown Evidence result_grain "
            "与 Delivery result_grain 不一致。"
        )

    protected = record.protected_result
    provenance = record.provenance

    return ProtectedBreakdownViewV2(
        evidence_id=evidence_id,
        metric_name=provenance.metric_name,
        result_grain=provenance.result_grain,
        analysis_window=provenance.analysis_window,
        scope_summary=provenance.scope_summary,
        field_names=protected.field_names,
        rows=tuple(
            dict(row)
            for row in protected.rows
        ),
        row_count=protected.row_count,
        dataset_name=provenance.dataset_name,
        plan_name=provenance.plan_name,
        tool_name=provenance.tool_name,
        tool_version=provenance.tool_version,
        audit_event_id=provenance.audit_event_id,
    )


def _find_matching_observation_record_v2(
    *,
    delivery: EvidencePackDeliveryV2,
    action_id: str,
    attempt_number: int,
    status: ToolObservationStatusV2,
    failure_code: str | None,
    retryable: bool,
    produced_evidence_ids: tuple[str, ...],
    summary: str,
) -> str:
    """
    把 Day86 ToolObservation 与 Day87 Investigation Observation
    Evidence Record 做 fail-closed linkage。
    """

    matches = []

    for record in delivery.evidence_pack.evidence_records:
        if (
            record.evidence_type
            != EvidenceTypeV2.INVESTIGATION_OBSERVATION
            or record.investigation_observation is None
        ):
            continue

        snapshot = record.investigation_observation

        if (
            snapshot.action_id == action_id
            and snapshot.attempt_number == attempt_number
        ):
            matches.append(record)

    if len(matches) != 1:
        raise ValueError(
            "每个 Trace Observation 必须唯一绑定一条 "
            "INVESTIGATION_OBSERVATION Evidence。"
        )

    record = matches[0]
    snapshot = record.investigation_observation
    assert snapshot is not None

    if (
        snapshot.status != status.value
        or snapshot.failure_code != failure_code
        or snapshot.retryable != retryable
        or snapshot.summary != summary
    ):
        raise ValueError(
            "Trace Observation 与 Evidence Pack 中的 "
            "Investigation Observation 内容不一致。"
        )

    if status == ToolObservationStatusV2.EVIDENCE:
        available_ids = {
            item.reference.evidence_id
            for item in delivery.evidence_pack.evidence_records
        }

        missing = set(produced_evidence_ids) - available_ids
        if missing:
            raise ValueError(
                "Trace produced Evidence 必须真实存在于 Evidence Pack："
                f"{sorted(missing)}"
            )

        if (
            tuple(record.parent_evidence_ids)
            != tuple(produced_evidence_ids)
        ):
            raise ValueError(
                "Investigation Observation parent lineage "
                "必须与 produced_evidence_ids 一致。"
            )

    elif record.parent_evidence_ids:
        raise ValueError(
            "NO_DATA / FAILURE Trace 不能伪造 produced Evidence lineage。"
        )

    return record.reference.evidence_id


def _build_investigation_trace_v2(
    *,
    delivery: EvidencePackDeliveryV2,
    transitions: tuple[InvestigationLoopTransitionV2, ...],
    stop_status: InvestigationStopStatusV2 | None,
    prior_continuation_stop_statuses: tuple[
        InvestigationStopStatusV2, ...
    ] = (),
) -> tuple[
    tuple[InvestigationTraceStepViewV2, ...],
    InvestigationRuntimeControlViewV2 | None,
]:
    if not transitions:
        if stop_status is not None:
            raise ValueError(
                "没有 Investigation transitions 时不能单独提供 stop_status。"
            )
        return (), None

    previous_history = ()
    steps: list[InvestigationTraceStepViewV2] = []

    for index, transition in enumerate(transitions):
        history = transition.next_state.observation_history

        if len(history) != len(previous_history) + 1:
            raise ValueError(
                "Investigation Trace 必须从完整且连续的 "
                "observation_history 构建。"
            )

        if tuple(history[:-1]) != tuple(previous_history):
            raise ValueError(
                "Investigation transitions 的 observation_history "
                "不是连续前缀。"
            )

        if (
            index < len(transitions) - 1
            and transition.control_decision.directive
            == LoopDirectiveV2.STOP
        ):
            # Day86 的 STOP 可以是 round-level boundary。
            # 只有存在对应的历史 Stop Status，且明确
            # can_continue=True，才允许后续 transition。
            prior_stop_index = sum(
                1
                for prior_transition
                in transitions[:index]
                if (
                    prior_transition.control_decision.directive
                    == LoopDirectiveV2.STOP
                )
            )

            if (
                prior_stop_index
                >= len(prior_continuation_stop_statuses)
            ):
                raise ValueError(
                    "中间 STOP 后存在后续 transition，"
                    "但缺少对应的 continuation Stop Status。"
                )

            prior_stop = (
                prior_continuation_stop_statuses[
                    prior_stop_index
                ]
            )

            if not prior_stop.can_continue:
                raise ValueError(
                    "只有 can_continue=True 的中间 STOP "
                    "才能在用户明确 continuation 后追加 transition。"
                )

            if (
                prior_stop.stop_reason
                != transition.control_decision.stop_reason
            ):
                raise ValueError(
                    "中间 STOP transition 与历史 Stop Status "
                    "的 stop_reason 不一致。"
                )

            next_history = (
                transitions[index + 1]
                .next_state.observation_history
            )
            if not next_history:
                raise ValueError(
                    "Continuation 后的 transition 必须包含 "
                    "新的 Tool Observation。"
                )

            next_action_id = next_history[-1].action_id

            if (
                next_action_id
                not in prior_stop.uninvestigated_action_ids
            ):
                raise ValueError(
                    "Continuation 后执行的 Action 必须属于 "
                    "前一轮 Stop Status 的 uninvestigated_action_ids。"
                )

        observation = history[-1]
        failure_code = (
            observation.failure_code.value
            if observation.failure_code is not None
            else None
        )

        observation_evidence_id = (
            _find_matching_observation_record_v2(
                delivery=delivery,
                action_id=observation.action_id,
                attempt_number=observation.attempt_number,
                status=observation.status,
                failure_code=failure_code,
                retryable=observation.retryable,
                produced_evidence_ids=(
                    observation.produced_evidence_ids
                ),
                summary=observation.summary,
            )
        )

        steps.append(
            InvestigationTraceStepViewV2(
                sequence_number=index + 1,
                selected_action_id=observation.action_id,
                attempt_number=observation.attempt_number,
                observation_status=observation.status,
                failure_code=failure_code,
                retryable=observation.retryable,
                produced_evidence_ids=(
                    observation.produced_evidence_ids
                ),
                observation_evidence_id=(
                    observation_evidence_id
                ),
                summary=observation.summary,
                next_directive=(
                    transition.control_decision.directive
                ),
                stop_reason=(
                    transition.control_decision.stop_reason
                ),
            )
        )

        previous_history = history

    intermediate_stop_count = sum(
        1
        for transition in transitions[:-1]
        if (
            transition.control_decision.directive
            == LoopDirectiveV2.STOP
        )
    )

    if (
        len(prior_continuation_stop_statuses)
        != intermediate_stop_count
    ):
        raise ValueError(
            "prior_continuation_stop_statuses 数量必须与 "
            "非最终 STOP transition 数量完全一致。"
        )

    final_transition = transitions[-1]
    final_is_stop = (
        final_transition.control_decision.directive
        == LoopDirectiveV2.STOP
    )

    if final_is_stop and stop_status is None:
        raise ValueError(
            "最终 transition 已 STOP 时必须提供 "
            "InvestigationStopStatusV2。"
        )

    if not final_is_stop and stop_status is not None:
        raise ValueError(
            "只有最终 transition 为 STOP 时才能提供 stop_status。"
        )

    runtime_control = None

    if stop_status is not None:
        if (
            final_transition.control_decision.stop_reason
            != stop_status.stop_reason
        ):
            raise ValueError(
                "Stop Status 与最终 Loop transition "
                "的 stop_reason 不一致。"
            )

        runtime_control = InvestigationRuntimeControlViewV2(
            stop_reason=stop_status.stop_reason,
            evidence_sufficient=stop_status.evidence_sufficient,
            uninvestigated_action_ids=(
                stop_status.uninvestigated_action_ids
            ),
            can_continue=stop_status.can_continue,
            current_round=stop_status.current_round,
            max_rounds=stop_status.max_rounds,
            total_steps_used=stop_status.total_steps_used,
            max_total_investigation_steps=(
                stop_status.max_total_investigation_steps
            ),
            detail=stop_status.detail,
        )

    return tuple(steps), runtime_control


def _build_runtime_clarification_view_v2(
    *,
    planner_state: InvestigationStateV2 | None,
    planner_decision: PlannerDecisionV2 | None,
) -> RuntimeClarificationViewV2 | None:
    """
    将 trusted clarification prerequisite + validated planner decision
    投影给 Day89 UI。

    这里不判断语义是否真的模糊，也不生成 clarification prompt。
    """

    if planner_state is None and planner_decision is None:
        return None

    if planner_state is None or planner_decision is None:
        raise ValueError(
            "Runtime Clarification 必须同时提供 "
            "planner_state 与 planner_decision。"
        )

    requirement = planner_state.clarification_requirement

    if requirement is None:
        if (
            planner_decision.decision_type
            == PlannerDecisionTypeV2.CLARIFY
        ):
            raise ValueError(
                "没有 trusted clarification requirement 时，"
                "Decision Console 不能接受 CLARIFY。"
            )

        return None

    if (
        planner_decision.decision_type
        != PlannerDecisionTypeV2.CLARIFY
    ):
        raise ValueError(
            "存在 unresolved clarification requirement 时，"
            "Tool selection 必须保持 blocked。"
        )

    if planner_decision.selected_action is not None:
        raise ValueError(
            "CLARIFY 状态不能同时暴露 selected_action。"
        )

    if (
        planner_decision.clarification_prompt is None
        or not planner_decision.clarification_prompt.strip()
    ):
        raise ValueError(
            "CLARIFY decision 必须包含 clarification_prompt。"
        )

    return RuntimeClarificationViewV2(
        requirement_source=requirement.source,
        requirement_reason=requirement.reason,
        clarification_prompt=(
            planner_decision.clarification_prompt
        ),
        rationale=planner_decision.rationale,
        requires_user_response=True,
        tool_execution_blocked=True,
    )


def _build_evidence_drawer_view_v2(
    *,
    delivery: EvidencePackDeliveryV2,
) -> EvidenceDrawerViewV2:
    """
    将 Day87 Evidence Delivery 投影成 Day89 安全 Evidence Drawer。

    这里不读取或解析 raw SQL，也不复制 ProtectedResult rows。
    """

    records: list[EvidenceDrawerRecordViewV2] = []

    for record in delivery.evidence_pack.evidence_records:
        provenance = record.provenance
        protected = record.protected_result
        observation = record.investigation_observation

        records.append(
            EvidenceDrawerRecordViewV2(
                evidence_id=record.reference.evidence_id,
                evidence_type=record.evidence_type,
                source=record.reference.source,
                description=record.reference.description,
                parent_evidence_ids=record.parent_evidence_ids,
                dataset_name=(
                    provenance.dataset_name
                    if provenance is not None
                    else None
                ),
                metric_name=(
                    provenance.metric_name
                    if provenance is not None
                    else None
                ),
                result_grain=(
                    provenance.result_grain
                    if provenance is not None
                    else None
                ),
                analysis_window=(
                    provenance.analysis_window
                    if provenance is not None
                    else None
                ),
                scope_summary=(
                    provenance.scope_summary
                    if provenance is not None
                    else None
                ),
                plan_name=(
                    provenance.plan_name
                    if provenance is not None
                    else None
                ),
                tool_name=(
                    provenance.tool_name
                    if provenance is not None
                    else None
                ),
                tool_version=(
                    provenance.tool_version
                    if provenance is not None
                    else None
                ),
                audit_event_id=(
                    provenance.audit_event_id
                    if provenance is not None
                    else None
                ),
                released_field_names=(
                    protected.field_names
                    if protected is not None
                    else ()
                ),
                released_row_count=(
                    protected.row_count
                    if protected is not None
                    else None
                ),
                observation_action_id=(
                    observation.action_id
                    if observation is not None
                    else None
                ),
                observation_status=(
                    observation.status
                    if observation is not None
                    else None
                ),
                observation_summary=(
                    observation.summary
                    if observation is not None
                    else None
                ),
            )
        )

    return EvidenceDrawerViewV2(
        metric_definition=delivery.metric_definition,
        sufficiency_status=delivery.sufficiency.status,
        confidence_level=delivery.sufficiency.confidence_level.value,
        sufficiency_basis=delivery.sufficiency.basis,
        records=tuple(records),
    )


def _validate_contribution_evidence_binding(
    *,
    delivery: EvidencePackDeliveryV2,
    contribution_evidence_id: str,
) -> None:
    evidence_id = contribution_evidence_id.strip()
    if not evidence_id:
        raise ValueError(
            "contribution_evidence_id 不能为空。"
        )

    record = _evidence_record_by_id(
        delivery=delivery,
        evidence_id=evidence_id,
    )
    if record is None:
        raise ValueError(
            "Contribution Evidence 不存在于当前 Evidence Pack。"
        )

    if record.evidence_type != EvidenceTypeV2.CONTRIBUTION_RESULT:
        raise ValueError(
            "contribution_evidence_id 必须指向 CONTRIBUTION_RESULT。"
        )

    published_contribution_ids = {
        evidence_id
        for statement
        in delivery.evidence_pack.insight.dimension_contributions
        for evidence_id in statement.evidence_ids
    }

    if evidence_id not in published_contribution_ids:
        raise ValueError(
            "Contribution Evidence 尚未被当前 Insight 发布，"
            "不能直接进入 Decision Console。"
        )


def _validate_anomaly_evidence_binding(
    *,
    delivery: EvidencePackDeliveryV2,
    anomaly_evidence_id: str,
    require_published: bool,
) -> bool:
    evidence_id = anomaly_evidence_id.strip()
    if not evidence_id:
        raise ValueError(
            "anomaly_evidence_id 不能为空。"
        )

    record = _evidence_record_by_id(
        delivery=delivery,
        evidence_id=evidence_id,
    )
    if record is None:
        raise ValueError(
            "Anomaly Evidence 不存在于当前 Evidence Pack。"
        )

    if record.evidence_type != EvidenceTypeV2.ANOMALY_DECISION:
        raise ValueError(
            "anomaly_evidence_id 必须指向 ANOMALY_DECISION。"
        )

    published_ids = {
        evidence_id
        for statement
        in delivery.evidence_pack.insight.detected_anomalies
        for evidence_id in statement.evidence_ids
    }

    is_published = evidence_id in published_ids

    if require_published and not is_published:
        raise ValueError(
            "ANOMALY verdict 必须已经作为 detected_anomaly "
            "发布到当前 Insight。"
        )

    return is_published


def _build_anomaly_view_v2(
    *,
    delivery: EvidencePackDeliveryV2,
    decision: AnomalyDecisionV2,
    anomaly_evidence_id: str | None,
) -> AnomalyViewV2:
    scope = delivery.evidence_pack.analysis_scope

    if decision.metric_name != scope.metric_name:
        raise ValueError(
            "Anomaly metric 与 Delivery metric 不一致。"
        )

    if (
        scope.comparison is None
        or decision.comparison != scope.comparison
    ):
        raise ValueError(
            "Anomaly comparison 与 Delivery comparison 不一致。"
        )

    is_anomaly = (
        decision.status == AnomalyDecisionStatusV2.ANOMALY
    )

    if is_anomaly and anomaly_evidence_id is None:
        raise ValueError(
            "ANOMALY verdict 必须显式绑定 anomaly_evidence_id。"
        )

    published = False

    if anomaly_evidence_id is not None:
        published = _validate_anomaly_evidence_binding(
            delivery=delivery,
            anomaly_evidence_id=anomaly_evidence_id,
            require_published=is_anomaly,
        )

        if not is_anomaly and published:
            raise ValueError(
                "非 ANOMALY verdict 不能被发布为 detected_anomaly。"
            )

    policy_view = None
    if decision.policy is not None:
        policy_view = AnomalyPolicyViewV2(
            change_type=decision.policy.change_type,
            direction=decision.policy.direction,
            threshold_value=decision.policy.threshold_value,
            sample_metric_name=decision.policy.sample_metric_name,
            minimum_sample_value=(
                decision.policy.minimum_sample_value
            ),
            policy_version=decision.policy.policy_version,
        )

    return AnomalyViewV2(
        evidence_id=anomaly_evidence_id,
        metric_name=decision.metric_name,
        status=decision.status,
        reason_code=decision.reason_code,
        current_value=decision.current_value,
        reference_value=decision.reference_value,
        absolute_change=decision.absolute_change,
        relative_change=decision.relative_change,
        current_sample_value=decision.current_sample_value,
        reference_sample_value=decision.reference_sample_value,
        policy=policy_view,
        show_anomaly_marker=is_anomaly,
        published_as_detected_anomaly=published,
    )


def build_decision_console_view_v2(
    *,
    delivery: EvidencePackDeliveryV2,
    contribution_result: ContributionAnalysisResultV2 | None = None,
    contribution_evidence_id: str | None = None,
    anomaly_decision: AnomalyDecisionV2 | None = None,
    anomaly_evidence_id: str | None = None,
    metric_comparison_result: MetricComparisonResultV2 | None = None,
    breakdown_evidence_id: str | None = None,
    investigation_transitions: tuple[
        InvestigationLoopTransitionV2, ...
    ] = (),
    investigation_stop_status: InvestigationStopStatusV2 | None = None,
    investigation_prior_continuation_stop_statuses: tuple[
        InvestigationStopStatusV2, ...
    ] = (),
    clarification_planner_state: InvestigationStateV2 | None = None,
    clarification_planner_decision: PlannerDecisionV2 | None = None,
) -> DecisionConsoleViewV2:
    """
    将已经可信的 Day87 Delivery、Day84 Contribution、
    Day83 Anomaly Decision 投影成 Day89 Console 所需结构。

    这里不重新计算业务指标、Contribution 或 Anomaly verdict。
    """

    scope = delivery.evidence_pack.analysis_scope
    insight = delivery.evidence_pack.insight

    if (
        contribution_result is None
        and contribution_evidence_id is not None
    ):
        raise ValueError(
            "没有 Contribution Result 时不能单独提供 evidence_id。"
        )

    if (
        contribution_result is not None
        and contribution_evidence_id is None
    ):
        raise ValueError(
            "提供 Contribution Result 时必须显式绑定 contribution_evidence_id。"
        )

    if (
        anomaly_decision is None
        and anomaly_evidence_id is not None
    ):
        raise ValueError(
            "没有 Anomaly Decision 时不能单独提供 anomaly_evidence_id。"
        )

    evidence_drawer = _build_evidence_drawer_view_v2(
        delivery=delivery,
    )

    comparison_view = None
    verification_view = None

    if metric_comparison_result is not None:
        (
            comparison_view,
            verification_view,
        ) = _build_metric_comparison_projection_v2(
            delivery=delivery,
            result=metric_comparison_result,
        )

    breakdown_view = None

    if breakdown_evidence_id is not None:
        breakdown_view = _build_protected_breakdown_view_v2(
            delivery=delivery,
            breakdown_evidence_id=breakdown_evidence_id,
        )

    (
        investigation_trace,
        runtime_control,
    ) = _build_investigation_trace_v2(
        delivery=delivery,
        transitions=investigation_transitions,
        stop_status=investigation_stop_status,
        prior_continuation_stop_statuses=(
            investigation_prior_continuation_stop_statuses
        ),
    )

    clarification_view = _build_runtime_clarification_view_v2(
        planner_state=clarification_planner_state,
        planner_decision=clarification_planner_decision,
    )

    contribution_view = None

    if contribution_result is not None:
        assert contribution_evidence_id is not None

        _validate_contribution_evidence_binding(
            delivery=delivery,
            contribution_evidence_id=contribution_evidence_id,
        )

        if contribution_result.metric_name != scope.metric_name:
            raise ValueError(
                "Contribution metric 与 Delivery metric 不一致。"
            )

        if (
            scope.comparison is None
            or contribution_result.comparison != scope.comparison
        ):
            raise ValueError(
                "Contribution comparison 与 Delivery comparison 不一致。"
            )

        if (
            scope.result_grain is not None
            and contribution_result.dimension_name
            != scope.result_grain
        ):
            raise ValueError(
                "Contribution dimension 与 Delivery result_grain 不一致。"
            )

        contribution_view = ContributionViewV2(
            evidence_id=contribution_evidence_id,
            metric_name=contribution_result.metric_name,
            dimension_name=contribution_result.dimension_name,
            current_overall_value=(
                contribution_result.current_overall_value
            ),
            reference_overall_value=(
                contribution_result.reference_overall_value
            ),
            overall_delta=contribution_result.overall_delta,
            members=tuple(
                ContributionMemberViewV2(
                    member_key=member.member_key,
                    member_label=member.member_label,
                    current_value=member.current_value,
                    reference_value=member.reference_value,
                    delta=member.delta,
                    contribution_rate=member.contribution_rate,
                    direction=member.direction,
                )
                for member in contribution_result.members
            ),
            negative_change_ranking=(
                contribution_result.negative_change_ranking
            ),
            positive_change_ranking=(
                contribution_result.positive_change_ranking
            ),
            sum_member_delta=contribution_result.sum_member_delta,
            unexplained_remainder=(
                contribution_result.unexplained_remainder
            ),
            reconciliation_status=(
                contribution_result.reconciliation_status
            ),
        )

    anomaly_view = None

    if anomaly_decision is not None:
        anomaly_view = _build_anomaly_view_v2(
            delivery=delivery,
            decision=anomaly_decision,
            anomaly_evidence_id=anomaly_evidence_id,
        )

    return DecisionConsoleViewV2(
        metric_name=scope.metric_name,
        result_grain=scope.result_grain,
        scope_summary=scope.scope_summary,
        evidence_sufficiency=delivery.sufficiency.status,
        evidence_drawer=evidence_drawer,
        confirmed_facts=tuple(
            item.statement
            for item in insight.confirmed_facts
        ),
        candidate_hypotheses=tuple(
            item.explanation
            for item in insight.candidate_explanations
        ),
        unknowns=tuple(
            item.description
            for item in insight.unknowns
        ),
        recommended_checks=tuple(
            item.check
            for item in insight.recommended_checks
        ),
        comparison=comparison_view,
        verification=verification_view,
        breakdown=breakdown_view,
        investigation_trace=investigation_trace,
        runtime_control=runtime_control,
        clarification=clarification_view,
        contribution=contribution_view,
        anomaly=anomaly_view,
    )
