from __future__ import annotations

from pydantic import BaseModel, ConfigDict, model_validator

from app.agents.evidence_pack_delivery_v2 import (
    MetricDefinitionSnapshotV2,
)
from app.delivery.analysis_investigation_snapshot_v1 import (
    AnalysisEvidenceLineageRecordV1,
    AnalysisInvestigationSnapshotV1,
    build_analysis_evidence_lineage_v1,
)
from app.delivery.analysis_session_history_v1 import (
    AnalysisHistoryItemV1,
)
from app.delivery.breakdown_trusted_summary_v2 import (
    TrustedBreakdownSummaryResultV2,
)
from app.delivery.decision_console_view_v2 import (
    MetricComparisonViewV2,
)
from app.delivery.executive_decision_brief_v2 import (
    ExecutiveDecisionBriefPreviewV2,
)
from app.delivery.fact_composition_delivery_v2 import (
    FactCompositionResultV2,
)
from app.delivery.focused_change_breakdown_delivery_v2 import (
    FocusedChangeBreakdownDeliveryV2,
)
from app.semantic_layer.analysis_mode_contract_v2 import (
    AnalysisModeV2,
)
from app.semantic_layer.requested_scope_resolution_v2 import (
    RequestedScopeResolutionV2,
)
from app.semantic_layer.time_comparison_contract_v2 import (
    TimeWindowReferenceV2,
)


INVESTIGATION_REPORT_VERSION = "investigation_report_v2_3"


class InvestigationReportV2(BaseModel):
    """
    Day94 Final Investigation Report structured payload.

    这是最终交付投影合同，不是新的分析 / 推理层。

    只允许继承已经经过保护的 Delivery / History / Investigation
    Snapshot：
    - 不重新执行 SQL；
    - 不调用 LLM；
    - 不重新计算 KPI / Contribution / Composition；
    - 不重新解释 Scope / Time；
    - 不生成新的业务原因；
    - 不保存 runtime state / compiled SQL / parameters / raw rows。

    comparison_summary 显式保留“最初可信时间比较 Seed”。
    即使后续 Agentic Brief 聚焦调查步骤而不再携带 KPI Comparison，
    最终报告也不会丢失 reference/current 整体比较。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        arbitrary_types_allowed=True,
    )

    contract_version: str = INVESTIGATION_REPORT_VERSION

    history_id: str
    original_question: str
    resolved_question: str | None = None
    resolution_note: str | None = None
    answer_snapshot: str
    analysis_mode: AnalysisModeV2 = AnalysisModeV2.FACT

    metric_name: str
    metric_definition: MetricDefinitionSnapshotV2
    analysis_window: TimeWindowReferenceV2
    requested_scope: RequestedScopeResolutionV2 | None = None
    result_grain: str

    comparison_summary: MetricComparisonViewV2 | None = None
    executive_brief: ExecutiveDecisionBriefPreviewV2

    breakdown_summary: TrustedBreakdownSummaryResultV2 | None = None
    fact_compositions: tuple[
        FactCompositionResultV2,
        ...,
    ] = ()

    investigation_steps: tuple[
        FocusedChangeBreakdownDeliveryV2,
        ...,
    ] = ()

    user_exploration_steps: tuple[
        FocusedChangeBreakdownDeliveryV2,
        ...,
    ] = ()

    evidence_lineage: tuple[
        AnalysisEvidenceLineageRecordV1,
        ...,
    ] = ()

    @model_validator(mode="after")
    def validate_report(
        self,
    ) -> "InvestigationReportV2":
        text_fields = (
            self.history_id,
            self.original_question,
            self.answer_snapshot,
            self.metric_name,
            self.result_grain,
        )

        if any(not value.strip() for value in text_fields):
            raise ValueError(
                "Investigation Report 必填文本字段不能为空。"
            )

        if self.metric_definition.metric_name != self.metric_name:
            raise ValueError(
                "Investigation Report metric 与 Metric Definition 不一致。"
            )

        if self.executive_brief.metric_name != self.metric_name:
            raise ValueError(
                "Investigation Report metric 与 Executive Brief 不一致。"
            )

        if (
            self.executive_brief.analysis_window
            != self.analysis_window
        ):
            raise ValueError(
                "Investigation Report analysis_window "
                "与 Executive Brief 不一致。"
            )

        if (
            self.comparison_summary is not None
            and self.comparison_summary.metric_name
            != self.metric_name
        ):
            raise ValueError(
                "Investigation Report Comparison metric 不一致。"
            )

        if not self.evidence_lineage:
            raise ValueError(
                "Investigation Report 必须保留 Evidence Lineage。"
            )

        return self


def _latest_executive_brief_v2(
    *,
    history_item: AnalysisHistoryItemV1,
    investigation_snapshot: (
        AnalysisInvestigationSnapshotV1 | None
    ),
) -> ExecutiveDecisionBriefPreviewV2:
    """
    Final Report 优先使用当前 Session 中最新的安全 Agentic Brief。

    如果没有发生深入调查，则使用 History 主 Runtime Delivery
    已经冻结的 Executive Brief。
    """

    if (
        investigation_snapshot is not None
        and investigation_snapshot.agentic_delivery_snapshot
        is not None
        and investigation_snapshot.agentic_delivery_snapshot
        .executive_brief is not None
    ):
        return (
            investigation_snapshot.agentic_delivery_snapshot
            .executive_brief
        )

    brief = history_item.runtime_delivery_snapshot.executive_brief

    if brief is None:
        raise ValueError(
            "READY Analysis History 缺少 Executive Brief。"
        )

    return brief


def _metric_definition_v2(
    history_item: AnalysisHistoryItemV1,
) -> MetricDefinitionSnapshotV2:
    delivery = history_item.runtime_delivery_snapshot.delivery

    if delivery is None:
        raise ValueError(
            "READY Analysis History 缺少 Evidence Delivery。"
        )

    return delivery.metric_definition


def _comparison_summary_v2(
    history_item: AnalysisHistoryItemV1,
) -> MetricComparisonViewV2 | None:
    """
    只读取 seed READY Runtime 的 Console Comparison。

    不从 Agentic Investigation 重新生成 Comparison，
    不从自然语言 finding 反解析数值。
    """

    view = history_item.runtime_delivery_snapshot.console_view

    if view is None:
        return None

    return view.comparison


def build_investigation_report_v2(
    *,
    history_item: AnalysisHistoryItemV1,
    investigation_snapshot: (
        AnalysisInvestigationSnapshotV1 | None
    ) = None,
) -> InvestigationReportV2:
    """
    READY Analysis History + safe Investigation Snapshot
    -> Final Investigation Report Payload。

    Builder 只做结构化投影，不做业务重算。
    """

    brief = _latest_executive_brief_v2(
        history_item=history_item,
        investigation_snapshot=investigation_snapshot,
    )

    lineage = build_analysis_evidence_lineage_v1(
        seed_evidence_ids=history_item.evidence_ids,
        snapshot=investigation_snapshot,
    )

    investigation_steps = (
        investigation_snapshot.focused_change_snapshots
        if investigation_snapshot is not None
        else ()
    )
    user_exploration_steps = (
        investigation_snapshot.geography_exploration_snapshots
        if investigation_snapshot is not None
        else ()
    )

    return InvestigationReportV2(
        history_id=history_item.history_id,
        original_question=history_item.original_question,
        resolved_question=history_item.resolved_question,
        resolution_note=history_item.resolution_note,
        answer_snapshot=history_item.answer_snapshot,
        analysis_mode=(
            history_item.runtime_delivery_snapshot
            .requested_analysis_mode
        ),
        metric_name=history_item.metric_name,
        metric_definition=_metric_definition_v2(history_item),
        analysis_window=history_item.analysis_window,
        requested_scope=history_item.requested_scope,
        result_grain=history_item.result_grain,
        comparison_summary=_comparison_summary_v2(history_item),
        executive_brief=brief,
        breakdown_summary=(
            history_item.breakdown_summary_snapshot
        ),
        fact_compositions=(
            history_item.fact_composition_snapshots
        ),
        investigation_steps=investigation_steps,
        user_exploration_steps=user_exploration_steps,
        evidence_lineage=lineage,
    )
