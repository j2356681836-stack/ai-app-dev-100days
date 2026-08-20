from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.agents.evidence_pack_v2 import EvidenceTypeV2
from app.delivery.runtime_delivery_bridge_v2 import (
    RuntimeDeliveryBridgeResultV2,
    RuntimeDeliveryBridgeStatusV2,
)
from app.semantic_layer.time_comparison_contract_v2 import (
    TimeWindowReferenceV2,
)


TRUSTED_BREAKDOWN_SUMMARY_VERSION = (
    "trusted_breakdown_summary_v2_0"
)


class TrustedBreakdownSummaryStatusV2(str, Enum):
    READY = "ready"
    PRIMARY_NOT_READY = "primary_not_ready"
    NOT_REGISTERED = "not_registered"
    OVERALL_NOT_READY = "overall_not_ready"
    TRUST_LINKAGE_MISMATCH = "trust_linkage_mismatch"
    RESULT_SHAPE_MISMATCH = "result_shape_mismatch"


class TrustedBreakdownSummaryV2(BaseModel):
    """
    Breakdown 列表对应的独立 Overall Governed Evidence。

    value 不是 visible breakdown rows 的 sum。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    metric_name: str
    value: Decimal

    evidence_id: str
    analysis_window: TimeWindowReferenceV2

    dataset_name: str
    target_schema: str
    scope_summary: str | None

    plan_name: str
    tool_name: str
    tool_version: str
    audit_event_id: str


class TrustedBreakdownSummaryResultV2(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    contract_version: str = TRUSTED_BREAKDOWN_SUMMARY_VERSION
    status: TrustedBreakdownSummaryStatusV2
    message: str

    summary: TrustedBreakdownSummaryV2 | None = None
    safe_overall_runtime_result: dict[str, Any] = Field(
        default_factory=dict
    )

    @model_validator(mode="after")
    def validate_result(
        self,
    ) -> "TrustedBreakdownSummaryResultV2":
        if not self.message.strip():
            raise ValueError("Summary result message 不能为空。")

        if self.status == TrustedBreakdownSummaryStatusV2.READY:
            if self.summary is None:
                raise ValueError(
                    "READY 必须返回 TrustedBreakdownSummaryV2。"
                )
        elif self.summary is not None:
            raise ValueError(
                "非 READY 状态不能释放 summary。"
            )

        return self


def _single_governed_record(
    result: RuntimeDeliveryBridgeResultV2,
):
    if result.delivery is None:
        raise ValueError("Runtime Delivery 缺失。")

    records = tuple(
        record
        for record in result.delivery.evidence_pack.evidence_records
        if record.evidence_type
        == EvidenceTypeV2.GOVERNED_QUERY_RESULT
    )

    if len(records) != 1:
        raise ValueError(
            "Trusted Summary 每一侧必须恰好有一条 "
            "GOVERNED_QUERY_RESULT。"
        )

    return records[0]


def build_trusted_breakdown_summary_v2(
    *,
    primary_result: RuntimeDeliveryBridgeResultV2,
    overall_result: RuntimeDeliveryBridgeResultV2,
) -> TrustedBreakdownSummaryResultV2:
    """
    将 Breakdown Delivery 与独立 Overall Delivery 做 fail-closed linkage。

    不做：
    - sum(breakdown rows)
    - ratio aggregation
    - UI-side recalculation
    """

    if (
        primary_result.status
        != RuntimeDeliveryBridgeStatusV2.READY
        or primary_result.delivery is None
        or primary_result.console_view is None
        or primary_result.console_view.breakdown is None
    ):
        return TrustedBreakdownSummaryResultV2(
            status=(
                TrustedBreakdownSummaryStatusV2
                .PRIMARY_NOT_READY
            ),
            message="Primary Breakdown Delivery 尚未 READY。",
        )

    if (
        overall_result.status
        != RuntimeDeliveryBridgeStatusV2.READY
        or overall_result.delivery is None
    ):
        return TrustedBreakdownSummaryResultV2(
            status=(
                TrustedBreakdownSummaryStatusV2
                .OVERALL_NOT_READY
            ),
            message=(
                "独立 Overall Governed Query 未形成可释放 Evidence。 "
                f"{overall_result.message}"
            ),
            safe_overall_runtime_result=dict(
                overall_result.safe_runtime_result
            ),
        )

    try:
        primary_record = _single_governed_record(
            primary_result
        )
        overall_record = _single_governed_record(
            overall_result
        )

        pp = primary_record.provenance
        op = overall_record.provenance
        protected = overall_record.protected_result

        if pp is None or op is None or protected is None:
            raise ValueError(
                "Breakdown / Overall Evidence 缺少可信 provenance "
                "或 protected result。"
            )

        if (
            pp.metric_name != op.metric_name
            or pp.analysis_window != op.analysis_window
            or pp.dataset_name != op.dataset_name
            or pp.target_schema != op.target_schema
            or pp.scope_summary != op.scope_summary
        ):
            raise ValueError(
                "Breakdown / Overall 的 metric、time window、dataset "
                "或 effective scope disclosure 不一致。"
            )

        if pp.result_grain == "overall":
            raise ValueError(
                "Primary Result 不是 breakdown grain。"
            )

        if op.result_grain != "overall":
            raise ValueError(
                "Summary Evidence 必须来自 overall grain。"
            )

        metric_name = pp.metric_name

        if protected.field_names != (metric_name,):
            raise ValueError(
                "Overall Evidence 必须只释放目标 metric 字段。"
            )

        if (
            protected.row_count != 1
            or len(protected.rows) != 1
        ):
            raise ValueError(
                "Overall Evidence 必须恰好释放一行。"
            )

        value = protected.rows[0].get(metric_name)

        if value is None:
            raise ValueError(
                "Overall Evidence metric value 不能为 None。"
            )

        summary = TrustedBreakdownSummaryV2(
            metric_name=metric_name,
            value=Decimal(str(value)),
            evidence_id=(
                overall_record.reference.evidence_id
            ),
            analysis_window=op.analysis_window,
            dataset_name=op.dataset_name,
            target_schema=op.target_schema,
            scope_summary=op.scope_summary,
            plan_name=op.plan_name,
            tool_name=op.tool_name,
            tool_version=op.tool_version,
            audit_event_id=op.audit_event_id,
        )

    except ValueError as exc:
        return TrustedBreakdownSummaryResultV2(
            status=(
                TrustedBreakdownSummaryStatusV2
                .TRUST_LINKAGE_MISMATCH
            ),
            message=str(exc),
            safe_overall_runtime_result=dict(
                overall_result.safe_runtime_result
            ),
        )

    return TrustedBreakdownSummaryResultV2(
        status=TrustedBreakdownSummaryStatusV2.READY,
        message=(
            "可信汇总来自独立 Overall Governed Evidence；"
            "未对可见 Breakdown rows 求和。"
        ),
        summary=summary,
        safe_overall_runtime_result=dict(
            overall_result.safe_runtime_result
        ),
    )
