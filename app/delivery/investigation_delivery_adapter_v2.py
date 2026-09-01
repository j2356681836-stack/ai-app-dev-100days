from __future__ import annotations

import hashlib
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, model_validator

from app.agents.evidence_pack_builder_v2 import (
    EvidenceBuildStatusV2,
    build_governed_query_evidence_record_v2,
)
from app.agents.evidence_pack_delivery_v2 import (
    EvidencePackDeliveryV2,
    assemble_evidence_pack_delivery_v2,
)
from app.agents.evidence_pack_v2 import (
    EvidencePackV2,
    EvidenceRecordV2,
)
from app.agents.investigation_contracts_v2 import (
    EvidenceReferenceV2,
    InsightContractV2,
    UnknownV2,
)
from app.agents.investigation_loop_v2 import (
    InvestigationStopStatusV2,
)
from app.agents.investigation_observation_evidence_builder_v2 import (
    build_investigation_observation_evidence_v2,
)
from app.delivery.decision_console_view_v2 import (
    DecisionConsoleViewV2,
    build_decision_console_view_v2,
)
from app.delivery.executive_decision_brief_v2 import (
    ExecutiveDecisionBriefPreviewV2,
    build_executive_decision_brief_preview_v2,
)
from app.delivery.investigation_runtime_v2 import (
    Day89ClarificationResumeResultV2,
    Day89InvestigationRuntimeStatusV2,
    Day89InvestigationRuntimeStepResultV2,
)
from app.delivery.runtime_delivery_bridge_v2 import (
    RuntimeDeliveryBridgeResultV2,
    RuntimeDeliveryBridgeStatusV2,
)

from app.governance.governed_planning_envelope_v2 import (
    GovernedPlanningEnvelopeV2,
)


INVESTIGATION_DELIVERY_ADAPTER_VERSION = (
    "day89_investigation_delivery_adapter_v2_0"
)


class InvestigationDeliveryStatusV2(str, Enum):
    READY = "ready"
    CLARIFICATION_READY = "clarification_ready"
    INVALID_RUNTIME_STATE = "invalid_runtime_state"
    EVIDENCE_BUILD_FAILED = "evidence_build_failed"


class InvestigationDeliveryResultV2(BaseModel):
    """
    Day89 Agentic Runtime -> Evidence Delivery 的安全输出。

    不返回 server-internal governed_query_context，
    也不返回 raw SQL / SQL parameters。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    contract_version: str = (
        INVESTIGATION_DELIVERY_ADAPTER_VERSION
    )

    status: InvestigationDeliveryStatusV2
    message: str

    delivery: EvidencePackDeliveryV2 | None = None
    console_view: DecisionConsoleViewV2 | None = None
    executive_brief: (
        ExecutiveDecisionBriefPreviewV2 | None
    ) = None

    @model_validator(mode="after")
    def validate_result(
        self,
    ) -> "InvestigationDeliveryResultV2":
        if not self.message.strip():
            raise ValueError("Delivery Adapter message 不能为空。")

        artifacts = (
            self.delivery,
            self.console_view,
            self.executive_brief,
        )

        if self.status in {
            InvestigationDeliveryStatusV2.READY,
            InvestigationDeliveryStatusV2.CLARIFICATION_READY,
        }:
            if any(item is None for item in artifacts):
                raise ValueError(
                    "Ready 状态必须完整返回 Delivery / Console / Brief。"
                )
        elif any(item is not None for item in artifacts):
            raise ValueError(
                "失败状态不能释放半成品 Delivery artifacts。"
            )

        return self


def _failed(
    *,
    status: InvestigationDeliveryStatusV2,
    message: str,
) -> InvestigationDeliveryResultV2:
    return InvestigationDeliveryResultV2(
        status=status,
        message=message,
    )


def _seed_linkage_error(
    *,
    seed_result: RuntimeDeliveryBridgeResultV2,
    runtime_step: Day89InvestigationRuntimeStepResultV2,
) -> str | None:
    if (
        seed_result.status
        != RuntimeDeliveryBridgeStatusV2.READY
        or seed_result.delivery is None
    ):
        return "Investigation Delivery 必须绑定 READY seed Delivery。"

    seed_scope = seed_result.delivery.evidence_pack.analysis_scope
    runtime_scope = (
        runtime_step.session_before.loop_state
        .planner_state.insight.analysis_scope
    )

    if runtime_scope.metric_name != seed_scope.metric_name:
        return "Runtime metric 与 seed Delivery metric 不一致。"

    if runtime_scope.analysis_window != seed_scope.analysis_window:
        return "Runtime analysis_window 与 seed Delivery 不一致。"

    if runtime_scope.comparison != seed_scope.comparison:
        return "Runtime comparison contract 与 seed Delivery 不一致。"

    seed_ids = {
        item.evidence_id
        for item in seed_result.delivery.evidence_pack.insight.evidence
    }
    runtime_ids = {
        item.evidence_id
        for item in (
            runtime_step.session_before.loop_state
            .planner_state.insight.evidence
        )
    }

    if not seed_ids.issubset(runtime_ids):
        return "Runtime 起始 State 丢失 seed Evidence identity。"

    return None


def _with_unknown(
    *,
    insight: InsightContractV2,
    description: str,
) -> InsightContractV2:
    if any(
        item.description == description
        for item in insight.unknowns
    ):
        return insight

    return insight.model_copy(
        update={
            "unknowns": (
                *insight.unknowns,
                UnknownV2(description=description),
            ),
        }
    )


def _apply_runtime_epistemic_boundary(
    *,
    insight: InsightContractV2,
    runtime_step: Day89InvestigationRuntimeStepResultV2,
) -> InsightContractV2:
    """
    Loop 的 evidence_sufficient=False 必须真实反映进 Evidence Pack。

    Sufficiency 不能由 Adapter 手工赋值；这里只保留真实 Unknown，
    再让 EvidencePackDeliveryV2 自己确定性计算 PARTIAL / SUFFICIENT。
    """

    if (
        runtime_step.status
        == Day89InvestigationRuntimeStatusV2
        .CLARIFICATION_REQUIRED
    ):
        return _with_unknown(
            insight=insight,
            description=(
                "当前存在未解决的用户澄清前置条件；"
                "在用户明确回答前，Investigation 尚未继续。"
            ),
        )

    if runtime_step.stop_status is not None:
        if not runtime_step.stop_status.evidence_sufficient:
            return _with_unknown(
                insight=insight,
                description=(
                    "当前 Investigation 已停止，但现有 Evidence "
                    "仍不足以确认业务原因。"
                ),
            )
        return insight

    return _with_unknown(
        insight=insight,
        description=(
            "当前 Investigation 尚未结束；新 Evidence 已进入状态，"
            "但仍存在未完成的合法调查路径。"
        ),
    )


def _observation_reference_v2(
    runtime_step: Day89InvestigationRuntimeStepResultV2,
) -> EvidenceReferenceV2:
    execution = runtime_step.execution_result
    transition = runtime_step.transition

    if execution is None or transition is None:
        raise ValueError(
            "Observation Evidence 需要真实 execution + transition。"
        )

    observation = execution.observation

    fingerprint_basis = "|".join(
        (
            observation.action_id,
            str(observation.attempt_number),
            observation.status.value,
            execution.audit_event_fingerprint or "",
            (
                observation.failure_code.value
                if observation.failure_code is not None
                else ""
            ),
            ",".join(observation.produced_evidence_ids),
            observation.summary,
        )
    )

    digest = hashlib.sha256(
        fingerprint_basis.encode("utf-8")
    ).hexdigest()[:20]

    return EvidenceReferenceV2(
        evidence_id=f"ev_obs_{digest}",
        source="investigation_loop_v2",
        description=(
            "Day89 bounded investigation observation："
            f"action={observation.action_id}; "
            f"attempt={observation.attempt_number}; "
            f"status={observation.status.value}"
        ),
    )


def _scope_summary_from_governed_envelope_v1(
    envelope: GovernedPlanningEnvelopeV2,
) -> str | None:
    """
    从本次实际 Governed Scope Binding 恢复安全范围摘要。

    Investigation 的 seed AnalysisScope 可能比后续 Focus Scope 更宽；
    Query Evidence Provenance 必须记录本次 SQL 真正绑定的范围，
    不能继续沿用 seed 的全局 scope_summary。
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


def _build_query_record(
    *,
    runtime_step: Day89InvestigationRuntimeStepResultV2,
    insight: InsightContractV2,
) -> tuple[EvidenceRecordV2 | None, str | None]:
    execution = runtime_step.execution_result

    if execution is None:
        return None, "执行型 Runtime Step 缺少 execution_result。"

    # NO_DATA / FAILURE 没有 produced query evidence；
    # 这两种状态只进入 Observation Evidence。
    if execution.evidence_reference is None:
        return None, None

    context = runtime_step.governed_query_context
    if context is None:
        return (
            None,
            "Runtime 声称产生 Query Evidence，"
            "但缺少 server-trusted governed_query_context。",
        )

    selected_action = runtime_step.planner_decision.selected_action
    if selected_action is None:
        return None, "执行型 Runtime Step 缺少 selected_action。"

    if context.action_id != selected_action.action_id:
        return (
            None,
            "Governed Query Context action 与 Planner selected_action 不一致。",
        )

    if context.tool_contract != selected_action.tool_contract:
        return (
            None,
            "Governed Query Context Tool Contract 与 selected_action 不一致。",
        )

    if (
        context.finalization.audit_event_fingerprint
        != execution.audit_event_fingerprint
    ):
        return (
            None,
            "Governed Finalization audit fingerprint "
            "与 Tool Execution Result 不一致。",
        )

    query_analysis_scope = insight.analysis_scope.model_copy(
        update={
            "scope_summary": (
                _scope_summary_from_governed_envelope_v1(
                    context.envelope
                )
            )
        }
    )

    build = build_governed_query_evidence_record_v2(
        analysis_scope=query_analysis_scope,
        evidence_reference=execution.evidence_reference,
        tool_contract=context.tool_contract,
        envelope=context.envelope,
        compiled=context.compiled,
        finalization=context.finalization,
    )

    if (
        not build.success
        or build.status != EvidenceBuildStatusV2.BUILT
        or build.record is None
    ):
        return (
            None,
            build.detail
            or "Governed Query Evidence Build failed。",
        )

    return build.record, None


def _assemble_artifacts(
    *,
    seed_result: RuntimeDeliveryBridgeResultV2,
    runtime_step: Day89InvestigationRuntimeStepResultV2,
    insight: InsightContractV2,
    records: tuple[EvidenceRecordV2, ...],
    request_subject: str,
    clarification: bool,
) -> InvestigationDeliveryResultV2:
    assert seed_result.delivery is not None

    pack = EvidencePackV2(
        pack_id=f"pack_day89_inv_{uuid4().hex}",
        analysis_scope=insight.analysis_scope,
        insight=insight,
        evidence_records=records,
    )

    delivery = assemble_evidence_pack_delivery_v2(
        evidence_pack=pack,
        metric_definition=seed_result.delivery.metric_definition,
    )

    if clarification:
        console = build_decision_console_view_v2(
            delivery=delivery,
            clarification_planner_state=(
                runtime_step.session_before.loop_state
                .planner_state
            ),
            clarification_planner_decision=(
                runtime_step.planner_decision
            ),
        )
        status = (
            InvestigationDeliveryStatusV2
            .CLARIFICATION_READY
        )
        message = (
            "Clarification 已进入安全 Delivery；"
            "当前没有执行任何 Investigation Tool。"
        )
    else:
        assert runtime_step.transition is not None

        console = build_decision_console_view_v2(
            delivery=delivery,
            investigation_transitions=(
                runtime_step.transition,
            ),
            investigation_stop_status=(
                runtime_step.stop_status
            ),
        )
        status = InvestigationDeliveryStatusV2.READY
        message = (
            "Investigation Tool Evidence、Observation Evidence "
            "与 Trace 已闭合。"
        )

    brief = build_executive_decision_brief_preview_v2(
        request_subject=request_subject,
        delivery=delivery,
        console_view=console,
    )

    return InvestigationDeliveryResultV2(
        status=status,
        message=message,
        delivery=delivery,
        console_view=console,
        executive_brief=brief,
    )


def build_investigation_step_delivery_v2(
    *,
    seed_result: RuntimeDeliveryBridgeResultV2,
    runtime_step: Day89InvestigationRuntimeStepResultV2,
    request_subject: str,
) -> InvestigationDeliveryResultV2:
    """
    把一次 bounded Agentic Investigation Step 闭合为 Day89 Delivery。

    EVIDENCE:
      Governed Query Result Evidence
      + Investigation Observation Evidence(parent=query evidence)
      + Runtime Transition / Stop Status
      -> EvidencePackDelivery
      -> Decision Console Trace / Runtime Control

    CLARIFY:
      不执行 Tool，不伪造 Observation，
      只把可信 clarification requirement / decision 投影给 UI。
    """

    if not request_subject.strip():
        return _failed(
            status=(
                InvestigationDeliveryStatusV2
                .INVALID_RUNTIME_STATE
            ),
            message="request_subject 不能为空。",
        )

    linkage_error = _seed_linkage_error(
        seed_result=seed_result,
        runtime_step=runtime_step,
    )
    if linkage_error is not None:
        return _failed(
            status=(
                InvestigationDeliveryStatusV2
                .INVALID_RUNTIME_STATE
            ),
            message=linkage_error,
        )

    assert seed_result.delivery is not None

    if (
        runtime_step.status
        == Day89InvestigationRuntimeStatusV2
        .CLARIFICATION_REQUIRED
    ):
        insight = _apply_runtime_epistemic_boundary(
            insight=(
                runtime_step.session_before.loop_state
                .planner_state.insight
            ),
            runtime_step=runtime_step,
        )

        return _assemble_artifacts(
            seed_result=seed_result,
            runtime_step=runtime_step,
            insight=insight,
            records=(
                seed_result.delivery.evidence_pack
                .evidence_records
            ),
            request_subject=request_subject,
            clarification=True,
        )

    if (
        runtime_step.execution_result is None
        or runtime_step.transition is None
    ):
        return _failed(
            status=(
                InvestigationDeliveryStatusV2
                .INVALID_RUNTIME_STATE
            ),
            message=(
                "执行型 Runtime Step 缺少 execution_result / transition。"
            ),
        )

    insight = (
        runtime_step.session_after.loop_state
        .planner_state.insight
    )
    insight = _apply_runtime_epistemic_boundary(
        insight=insight,
        runtime_step=runtime_step,
    )

    query_record, query_error = _build_query_record(
        runtime_step=runtime_step,
        insight=insight,
    )

    if query_error is not None:
        return _failed(
            status=(
                InvestigationDeliveryStatusV2
                .EVIDENCE_BUILD_FAILED
            ),
            message=query_error,
        )

    observation_reference = _observation_reference_v2(
        runtime_step
    )
    observation_build = (
        build_investigation_observation_evidence_v2(
            evidence_reference=observation_reference,
            observation=(
                runtime_step.execution_result.observation
            ),
        )
    )

    if (
        not observation_build.success
        or observation_build.record is None
    ):
        return _failed(
            status=(
                InvestigationDeliveryStatusV2
                .EVIDENCE_BUILD_FAILED
            ),
            message=(
                getattr(
                    observation_build,
                    "detail",
                    None,
                )
                or "Investigation Observation Evidence Build failed。"
            ),
        )

    new_records: list[EvidenceRecordV2] = list(
        seed_result.delivery.evidence_pack.evidence_records
    )

    if query_record is not None:
        new_records.append(query_record)

    new_records.append(observation_build.record)

    return _assemble_artifacts(
        seed_result=seed_result,
        runtime_step=runtime_step,
        insight=insight,
        records=tuple(new_records),
        request_subject=request_subject,
        clarification=False,
    )

def build_continued_investigation_step_delivery_v2(
    *,
    previous_result: InvestigationDeliveryResultV2,
    runtime_step: Day89InvestigationRuntimeStepResultV2,
    prior_transitions: tuple,
    prior_continuation_stop_statuses: tuple[
        InvestigationStopStatusV2, ...
    ],
    request_subject: str,
) -> InvestigationDeliveryResultV2:
    """
    把用户明确 Continue 后发生的新 Step 追加到已有安全 Delivery。

    previous_result 已经包含上一轮完整 Evidence Records；
    本函数只为当前新 Step 构建：
    - 新 Governed Query Evidence；
    - 新 Investigation Observation Evidence；
    然后用累计 transitions 重建 Trace / Runtime Control。

    不需要也不允许恢复上一轮 server-internal compiled SQL context。
    """

    if not request_subject.strip():
        return _failed(
            status=InvestigationDeliveryStatusV2.INVALID_RUNTIME_STATE,
            message="request_subject 不能为空。",
        )

    if (
        previous_result.status
        != InvestigationDeliveryStatusV2.READY
        or previous_result.delivery is None
    ):
        return _failed(
            status=InvestigationDeliveryStatusV2.INVALID_RUNTIME_STATE,
            message="Continuation 必须从 READY Investigation Delivery 继续。",
        )

    if (
        runtime_step.status
        == Day89InvestigationRuntimeStatusV2
        .CLARIFICATION_REQUIRED
    ):
        return _failed(
            status=InvestigationDeliveryStatusV2.INVALID_RUNTIME_STATE,
            message=(
                "Continuation Step 若进入 Clarification，"
                "必须走独立 Clarification Response 流程。"
            ),
        )

    if (
        runtime_step.execution_result is None
        or runtime_step.transition is None
    ):
        return _failed(
            status=InvestigationDeliveryStatusV2.INVALID_RUNTIME_STATE,
            message="Continuation 执行型 Step 缺少 execution / transition。",
        )

    previous_delivery = previous_result.delivery
    previous_scope = previous_delivery.evidence_pack.analysis_scope
    runtime_scope = (
        runtime_step.session_before.loop_state
        .planner_state.insight.analysis_scope
    )

    if (
        previous_scope.metric_name != runtime_scope.metric_name
        or previous_scope.analysis_window
        != runtime_scope.analysis_window
        or previous_scope.comparison != runtime_scope.comparison
    ):
        return _failed(
            status=InvestigationDeliveryStatusV2.INVALID_RUNTIME_STATE,
            message="Continuation Runtime Scope 与上一版 Delivery 不一致。",
        )

    insight = (
        runtime_step.session_after.loop_state
        .planner_state.insight
    )
    insight = _apply_runtime_epistemic_boundary(
        insight=insight,
        runtime_step=runtime_step,
    )

    query_record, query_error = _build_query_record(
        runtime_step=runtime_step,
        insight=insight,
    )
    if query_error is not None:
        return _failed(
            status=InvestigationDeliveryStatusV2.EVIDENCE_BUILD_FAILED,
            message=query_error,
        )

    observation_reference = _observation_reference_v2(
        runtime_step
    )
    observation_build = (
        build_investigation_observation_evidence_v2(
            evidence_reference=observation_reference,
            observation=runtime_step.execution_result.observation,
        )
    )

    if (
        not observation_build.success
        or observation_build.record is None
    ):
        return _failed(
            status=InvestigationDeliveryStatusV2.EVIDENCE_BUILD_FAILED,
            message=(
                observation_build.detail
                or "Continuation Observation Evidence Build failed。"
            ),
        )

    records = list(
        previous_delivery.evidence_pack.evidence_records
    )

    existing_ids = {
        record.reference.evidence_id
        for record in records
    }

    if query_record is not None:
        if query_record.reference.evidence_id in existing_ids:
            return _failed(
                status=InvestigationDeliveryStatusV2.INVALID_RUNTIME_STATE,
                message="Continuation Query Evidence ID 重复。",
            )
        records.append(query_record)
        existing_ids.add(
            query_record.reference.evidence_id
        )

    if (
        observation_build.record.reference.evidence_id
        in existing_ids
    ):
        return _failed(
            status=InvestigationDeliveryStatusV2.INVALID_RUNTIME_STATE,
            message="Continuation Observation Evidence ID 重复。",
        )

    records.append(observation_build.record)

    pack = EvidencePackV2(
        pack_id=f"pack_day89_inv_continue_{uuid4().hex}",
        analysis_scope=insight.analysis_scope,
        insight=insight,
        evidence_records=tuple(records),
    )

    delivery = assemble_evidence_pack_delivery_v2(
        evidence_pack=pack,
        metric_definition=previous_delivery.metric_definition,
    )

    transitions = (
        *prior_transitions,
        runtime_step.transition,
    )

    expected_prior_stop_count = sum(
        1
        for transition in prior_transitions
        if (
            transition.control_decision.directive.value
            == "stop"
        )
    )

    if (
        len(prior_continuation_stop_statuses)
        != expected_prior_stop_count
    ):
        return _failed(
            status=InvestigationDeliveryStatusV2.INVALID_RUNTIME_STATE,
            message=(
                "Continuation Delivery 的历史 Stop Status 数量 "
                "与 prior STOP transitions 不一致。"
            ),
        )

    console = build_decision_console_view_v2(
        delivery=delivery,
        investigation_transitions=transitions,
        investigation_stop_status=runtime_step.stop_status,
        investigation_prior_continuation_stop_statuses=(
            prior_continuation_stop_statuses
        ),
    )

    brief = build_executive_decision_brief_preview_v2(
        request_subject=request_subject,
        delivery=delivery,
        console_view=console,
    )

    return InvestigationDeliveryResultV2(
        status=InvestigationDeliveryStatusV2.READY,
        message=(
            "用户明确 continuation 后的新 Investigation Step "
            "已追加到 Evidence Delivery。"
        ),
        delivery=delivery,
        console_view=console,
        executive_brief=brief,
    )

def build_resolved_clarification_step_delivery_v2(
    *,
    previous_result: InvestigationDeliveryResultV2,
    resume_result: Day89ClarificationResumeResultV2,
    request_subject: str,
) -> InvestigationDeliveryResultV2:
    """
    Clarification-ready Delivery → resolved Tool Step → final safe Delivery。

    非 RESOLVED：
    - 保留上一版 CLARIFICATION_READY artifacts；
    - 只更新 message；
    - 不新增 Evidence / Trace。

    RESOLVED：
    - 追加新的 Query Evidence；
    - 追加 Observation Evidence；
    - 清除 Clarification projection；
    - 投影真实 Investigation Trace / Runtime Control。
    """

    if not request_subject.strip():
        return _failed(
            status=InvestigationDeliveryStatusV2.INVALID_RUNTIME_STATE,
            message="request_subject 不能为空。",
        )

    if (
        previous_result.status
        != InvestigationDeliveryStatusV2
        .CLARIFICATION_READY
        or previous_result.delivery is None
        or previous_result.console_view is None
        or previous_result.executive_brief is None
    ):
        return _failed(
            status=InvestigationDeliveryStatusV2.INVALID_RUNTIME_STATE,
            message=(
                "Clarification Resume 必须从 "
                "CLARIFICATION_READY Delivery 开始。"
            ),
        )

    if (
        resume_result.resolution.status.value
        != "resolved"
    ):
        return InvestigationDeliveryResultV2(
            status=(
                InvestigationDeliveryStatusV2
                .CLARIFICATION_READY
            ),
            message=resume_result.resolution.detail,
            delivery=previous_result.delivery,
            console_view=previous_result.console_view,
            executive_brief=previous_result.executive_brief,
        )

    runtime_step = resume_result.runtime_step
    if (
        runtime_step is None
        or runtime_step.execution_result is None
        or runtime_step.transition is None
    ):
        return _failed(
            status=InvestigationDeliveryStatusV2.INVALID_RUNTIME_STATE,
            message=(
                "RESOLVED Clarification 缺少真实 Runtime execution。"
            ),
        )

    previous_delivery = previous_result.delivery
    previous_scope = (
        previous_delivery.evidence_pack.analysis_scope
    )
    runtime_scope = (
        runtime_step.session_before.loop_state
        .planner_state.insight.analysis_scope
    )

    if (
        previous_scope.metric_name != runtime_scope.metric_name
        or previous_scope.analysis_window
        != runtime_scope.analysis_window
        or previous_scope.comparison
        != runtime_scope.comparison
    ):
        return _failed(
            status=InvestigationDeliveryStatusV2.INVALID_RUNTIME_STATE,
            message=(
                "Clarification Resume Runtime Scope "
                "与上一版 Delivery 不一致。"
            ),
        )

    insight = (
        runtime_step.session_after.loop_state
        .planner_state.insight
    )
    insight = _apply_runtime_epistemic_boundary(
        insight=insight,
        runtime_step=runtime_step,
    )

    query_record, query_error = _build_query_record(
        runtime_step=runtime_step,
        insight=insight,
    )
    if query_error is not None:
        return _failed(
            status=InvestigationDeliveryStatusV2.EVIDENCE_BUILD_FAILED,
            message=query_error,
        )

    observation_reference = _observation_reference_v2(
        runtime_step
    )
    observation_build = (
        build_investigation_observation_evidence_v2(
            evidence_reference=observation_reference,
            observation=runtime_step.execution_result.observation,
        )
    )

    if (
        not observation_build.success
        or observation_build.record is None
    ):
        return _failed(
            status=InvestigationDeliveryStatusV2.EVIDENCE_BUILD_FAILED,
            message=(
                observation_build.detail
                or "Clarification Resume Observation Build failed。"
            ),
        )

    records = list(
        previous_delivery.evidence_pack.evidence_records
    )
    existing_ids = {
        record.reference.evidence_id
        for record in records
    }

    if query_record is not None:
        if query_record.reference.evidence_id in existing_ids:
            return _failed(
                status=InvestigationDeliveryStatusV2.INVALID_RUNTIME_STATE,
                message="Clarification Resume Query Evidence ID 重复。",
            )
        records.append(query_record)
        existing_ids.add(
            query_record.reference.evidence_id
        )

    if (
        observation_build.record.reference.evidence_id
        in existing_ids
    ):
        return _failed(
            status=InvestigationDeliveryStatusV2.INVALID_RUNTIME_STATE,
            message=(
                "Clarification Resume Observation Evidence ID 重复。"
            ),
        )

    records.append(observation_build.record)

    pack = EvidencePackV2(
        pack_id=(
            f"pack_day89_inv_clarification_"
            f"{uuid4().hex}"
        ),
        analysis_scope=insight.analysis_scope,
        insight=insight,
        evidence_records=tuple(records),
    )

    delivery = assemble_evidence_pack_delivery_v2(
        evidence_pack=pack,
        metric_definition=previous_delivery.metric_definition,
    )

    console = build_decision_console_view_v2(
        delivery=delivery,
        investigation_transitions=(
            runtime_step.transition,
        ),
        investigation_stop_status=(
            runtime_step.stop_status
        ),
    )

    brief = build_executive_decision_brief_preview_v2(
        request_subject=request_subject,
        delivery=delivery,
        console_view=console,
    )

    return InvestigationDeliveryResultV2(
        status=InvestigationDeliveryStatusV2.READY,
        message=(
            "Clarification 已确定性解决；"
            "用户选择的合法调查方向已执行并进入 Evidence Delivery。"
        ),
        delivery=delivery,
        console_view=console,
        executive_brief=brief,
    )
