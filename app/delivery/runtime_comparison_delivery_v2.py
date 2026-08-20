from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator

from app.agents.evidence_pack_delivery_v2 import (
    EvidencePackDeliveryV2,
    assemble_evidence_pack_delivery_v2,
)
from app.agents.evidence_pack_v2 import (
    EvidencePackV2,
    EvidenceTypeV2,
)
from app.agents.investigation_contracts_v2 import (
    AnalysisModeV2,
    AnalysisScopeV2,
    InsightContractV2,
    SupportedInsightStatementV2,
)
from app.agents.metric_comparison_v2 import (
    MetricComparisonResultV2,
    compare_metric_values_v2,
)
from app.delivery.decision_console_view_v2 import (
    DecisionConsoleViewV2,
    build_decision_console_view_v2,
)
from app.delivery.executive_decision_brief_v2 import (
    ExecutiveDecisionBriefPreviewV2,
    build_executive_decision_brief_preview_v2,
)
from app.delivery.runtime_delivery_bridge_v2 import (
    RuntimeDeliveryBridgeResultV2,
    RuntimeDeliveryBridgeStatusV2,
)
from app.semantic_layer.time_comparison_contract_v2 import (
    TimeComparisonContractV2,
)


RUNTIME_COMPARISON_DELIVERY_VERSION = (
    "runtime_comparison_delivery_v2_0"
)


class RuntimeComparisonDeliveryStatusV2(str, Enum):
    READY = "ready"
    CURRENT_NOT_READY = "current_not_ready"
    REFERENCE_NOT_READY = "reference_not_ready"
    TRUST_LINKAGE_MISMATCH = "trust_linkage_mismatch"
    RESULT_SHAPE_MISMATCH = "result_shape_mismatch"


class RuntimeComparisonDeliveryResultV2(BaseModel):
    """
    两个已经完成 Governance + Result Protection + Evidence Build 的
   单次 Runtime Delivery，合并成一个 Comparison Delivery。

    本合同不会把 Graph internal state、raw SQL 或 raw DB rows
    暴露给上层。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        arbitrary_types_allowed=True,
    )

    contract_version: str = RUNTIME_COMPARISON_DELIVERY_VERSION
    status: RuntimeComparisonDeliveryStatusV2
    message: str

    comparison: TimeComparisonContractV2

    current_safe_runtime_result: dict[str, Any]
    reference_safe_runtime_result: dict[str, Any]

    metric_comparison_result: MetricComparisonResultV2 | None = None
    delivery: EvidencePackDeliveryV2 | None = None
    console_view: DecisionConsoleViewV2 | None = None
    executive_brief: ExecutiveDecisionBriefPreviewV2 | None = None

    @model_validator(mode="after")
    def validate_result(
        self,
    ) -> "RuntimeComparisonDeliveryResultV2":
        if not self.message.strip():
            raise ValueError("Comparison Delivery message 不能为空。")

        artifacts = (
            self.metric_comparison_result,
            self.delivery,
            self.console_view,
            self.executive_brief,
        )

        if self.status == RuntimeComparisonDeliveryStatusV2.READY:
            if any(item is None for item in artifacts):
                raise ValueError(
                    "READY 必须完整返回 Comparison / Delivery / "
                    "Console / Brief。"
                )
        else:
            if any(item is not None for item in artifacts):
                raise ValueError(
                    "非 READY 不得释放半成品 Comparison artifacts。"
                )

        return self


def _failed(
    *,
    status: RuntimeComparisonDeliveryStatusV2,
    message: str,
    comparison: TimeComparisonContractV2,
    current_result: RuntimeDeliveryBridgeResultV2,
    reference_result: RuntimeDeliveryBridgeResultV2,
) -> RuntimeComparisonDeliveryResultV2:
    return RuntimeComparisonDeliveryResultV2(
        status=status,
        message=message,
        comparison=comparison,
        current_safe_runtime_result=dict(
            current_result.safe_runtime_result
        ),
        reference_safe_runtime_result=dict(
            reference_result.safe_runtime_result
        ),
    )


def _single_governed_query_record(
    delivery: EvidencePackDeliveryV2,
):
    records = tuple(
        record
        for record in delivery.evidence_pack.evidence_records
        if record.evidence_type
        == EvidenceTypeV2.GOVERNED_QUERY_RESULT
    )

    if len(records) != 1:
        raise ValueError(
            "Monthly Comparison 每一侧必须恰好包含一条 "
            "GOVERNED_QUERY_RESULT。"
        )

    return records[0]


def _overall_metric_value(
    *,
    record,
    metric_name: str,
) -> Decimal:
    provenance = record.provenance
    protected = record.protected_result

    if provenance is None or protected is None:
        raise ValueError(
            "Comparison Query Evidence 必须包含 provenance "
            "与 protected_result。"
        )

    if provenance.metric_name != metric_name:
        raise ValueError(
            "Comparison Evidence metric 不一致。"
        )

    if provenance.result_grain != "overall":
        raise ValueError(
            "Day89 Monthly KPI Comparison 只接受 overall grain。"
        )

    if protected.field_names != (metric_name,):
        raise ValueError(
            "Overall KPI Evidence 必须只释放目标 metric field。"
        )

    if (
        protected.row_count != 1
        or len(protected.rows) != 1
    ):
        raise ValueError(
            "Overall KPI Evidence 必须恰好释放一行。"
        )

    value = protected.rows[0].get(metric_name)

    if value is None:
        raise ValueError(
            "Overall KPI Evidence 的 metric value 不能为 None。"
        )

    return Decimal(str(value))


def build_runtime_comparison_delivery_v2(
    *,
    current_result: RuntimeDeliveryBridgeResultV2,
    reference_result: RuntimeDeliveryBridgeResultV2,
    comparison: TimeComparisonContractV2,
    request_subject: str,
) -> RuntimeComparisonDeliveryResultV2:
    """
    Day89 Comparison Orchestration。

    只消费两侧已经可信的 Runtime Delivery：
    Governed Query Evidence(current)
      + Governed Query Evidence(reference)
      + TimeComparisonContractV2
      -> MetricComparisonResultV2
      -> EvidencePackDeliveryV2
      -> DecisionConsoleViewV2
      -> Executive Brief

    不重新执行 SQL，不重新解释时间，不在 UI 计算差值。
    """

    if (
        current_result.status
        != RuntimeDeliveryBridgeStatusV2.READY
        or current_result.delivery is None
    ):
        return _failed(
            status=(
                RuntimeComparisonDeliveryStatusV2
                .CURRENT_NOT_READY
            ),
            message=(
                "Current window 没有形成可释放的 Governed Delivery。 "
                f"{current_result.message}"
            ),
            comparison=comparison,
            current_result=current_result,
            reference_result=reference_result,
        )

    if (
        reference_result.status
        != RuntimeDeliveryBridgeStatusV2.READY
        or reference_result.delivery is None
    ):
        return _failed(
            status=(
                RuntimeComparisonDeliveryStatusV2
                .REFERENCE_NOT_READY
            ),
            message=(
                "Reference window 没有形成可释放的 Governed Delivery。 "
                f"{reference_result.message}"
            ),
            comparison=comparison,
            current_result=current_result,
            reference_result=reference_result,
        )

    current_delivery = current_result.delivery
    reference_delivery = reference_result.delivery

    current_scope = current_delivery.evidence_pack.analysis_scope
    reference_scope = reference_delivery.evidence_pack.analysis_scope

    if (
        current_scope.metric_name
        != reference_scope.metric_name
        or current_scope.result_grain
        != reference_scope.result_grain
        or current_scope.result_grain != "overall"
    ):
        return _failed(
            status=(
                RuntimeComparisonDeliveryStatusV2
                .TRUST_LINKAGE_MISMATCH
            ),
            message=(
                "Current / Reference metric 或 result_grain 不一致。"
            ),
            comparison=comparison,
            current_result=current_result,
            reference_result=reference_result,
        )

    if (
        current_scope.analysis_window
        != comparison.current_window
        or reference_scope.analysis_window
        != comparison.reference_window
    ):
        return _failed(
            status=(
                RuntimeComparisonDeliveryStatusV2
                .TRUST_LINKAGE_MISMATCH
            ),
            message=(
                "Current / Reference Evidence window "
                "与 Comparison Contract 不一致。"
            ),
            comparison=comparison,
            current_result=current_result,
            reference_result=reference_result,
        )

    if (
        current_delivery.metric_definition
        != reference_delivery.metric_definition
    ):
        return _failed(
            status=(
                RuntimeComparisonDeliveryStatusV2
                .TRUST_LINKAGE_MISMATCH
            ),
            message=(
                "Current / Reference Metric Definition Snapshot 不一致。"
            ),
            comparison=comparison,
            current_result=current_result,
            reference_result=reference_result,
        )

    try:
        current_record = _single_governed_query_record(
            current_delivery
        )
        reference_record = _single_governed_query_record(
            reference_delivery
        )

        current_provenance = current_record.provenance
        reference_provenance = reference_record.provenance

        if (
            current_provenance is None
            or reference_provenance is None
        ):
            raise ValueError(
                "Current / Reference Evidence 缺少 provenance。"
            )

        if (
            current_provenance.dataset_name
            != reference_provenance.dataset_name
            or current_provenance.target_schema
            != reference_provenance.target_schema
            or current_provenance.scope_summary
            != reference_provenance.scope_summary
        ):
            raise ValueError(
                "Current / Reference dataset / schema / effective scope "
                "不一致。"
            )

        if (
            current_record.reference.evidence_id
            == reference_record.reference.evidence_id
        ):
            raise ValueError(
                "Current / Reference Evidence ID 不能相同。"
            )

        metric_name = current_scope.metric_name

        current_value = _overall_metric_value(
            record=current_record,
            metric_name=metric_name,
        )
        reference_value = _overall_metric_value(
            record=reference_record,
            metric_name=metric_name,
        )
    except ValueError as exc:
        return _failed(
            status=(
                RuntimeComparisonDeliveryStatusV2
                .RESULT_SHAPE_MISMATCH
            ),
            message=str(exc),
            comparison=comparison,
            current_result=current_result,
            reference_result=reference_result,
        )

    comparison_result = compare_metric_values_v2(
        metric_name=metric_name,
        comparison=comparison,
        current_evidence_id=(
            current_record.reference.evidence_id
        ),
        reference_evidence_id=(
            reference_record.reference.evidence_id
        ),
        current_value=current_value,
        reference_value=reference_value,
    )

    scope = AnalysisScopeV2(
        metric_name=metric_name,
        analysis_window=comparison.current_window,
        comparison=comparison,
        result_grain="overall",
        scope_summary=current_provenance.scope_summary,
    )

    fact = SupportedInsightStatementV2(
        statement=(
            f"当前窗口 {comparison.current_window.start_date} 至 "
            f"{comparison.current_window.end_date}，"
            f"{metric_name.upper()}={current_value}；"
            f"参考窗口 {comparison.reference_window.start_date} 至 "
            f"{comparison.reference_window.end_date}，"
            f"{metric_name.upper()}={reference_value}。"
        ),
        evidence_ids=(
            current_record.reference.evidence_id,
            reference_record.reference.evidence_id,
        ),
    )

    insight = InsightContractV2(
        analysis_mode=AnalysisModeV2.COMPARISON,
        analysis_scope=scope,
        confirmed_facts=(fact,),
        evidence=(
            current_record.reference,
            reference_record.reference,
        ),
    )

    pack = EvidencePackV2(
        pack_id=(
            "pack-comparison-"
            f"{current_record.reference.evidence_id}-"
            f"{reference_record.reference.evidence_id}"
        ),
        analysis_scope=scope,
        insight=insight,
        evidence_records=(
            current_record,
            reference_record,
        ),
    )

    delivery = assemble_evidence_pack_delivery_v2(
        evidence_pack=pack,
        metric_definition=current_delivery.metric_definition,
    )

    console_view = build_decision_console_view_v2(
        delivery=delivery,
        metric_comparison_result=comparison_result,
    )

    brief = build_executive_decision_brief_preview_v2(
        request_subject=request_subject,
        delivery=delivery,
        console_view=console_view,
    )

    return RuntimeComparisonDeliveryResultV2(
        status=RuntimeComparisonDeliveryStatusV2.READY,
        message="Monthly GMV MoM Comparison Delivery 已生成。",
        comparison=comparison,
        current_safe_runtime_result=dict(
            current_result.safe_runtime_result
        ),
        reference_safe_runtime_result=dict(
            reference_result.safe_runtime_result
        ),
        metric_comparison_result=comparison_result,
        delivery=delivery,
        console_view=console_view,
        executive_brief=brief,
    )
