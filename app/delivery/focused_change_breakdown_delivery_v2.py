from __future__ import annotations

from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict

from app.agents.focused_change_breakdown_v2 import (
    FocusedChangeBreakdownResultV2,
    FocusedChangeDimensionV2,
    FocusedChangeObservationV2,
    analyze_focused_change_breakdown_v2,
)
from app.agents.investigation_step_assessment_v2 import (
    InvestigationStepAssessmentV2,
    assess_investigation_step_v2,
)
from app.delivery.business_scope_projection_v2 import (
    BusinessScopeProjectionV2,
    build_business_scope_projection_v2,
)
from app.delivery.decision_console_view_v2 import (
    ProtectedBreakdownViewV2,
)
from app.delivery.investigation_focus_scope_v1 import (
    InvestigationFocusScopeV1,
)
from app.agents.geography_hierarchy_v2 import (
    AREA_DISPLAY_LABELS_V2,
    GeographyFocusScopeV2,
)
from app.semantic_layer.time_comparison_contract_v2 import (
    TimeComparisonContractV2,
)


class ChangeBreakdownScopeKindV2(str, Enum):
    OVERALL = "overall"
    MEMBER_FOCUS = "member_focus"


class FocusedChangeBreakdownDeliveryV2(BaseModel):
    """
    Dataset V2 candidate path：
    两侧 Governed + Protected Breakdown
    -> deterministic Change Breakdown。

    为保持 Day93 已有调用兼容，类名暂不迁移。
    scope_kind 明确区分：
    - MEMBER_FOCUS：例如京东内部品类变化；
    - OVERALL：保持 Requested Scope 的全局品类变化。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    scope_kind: ChangeBreakdownScopeKindV2 = (
        ChangeBreakdownScopeKindV2.MEMBER_FOCUS
    )
    result: FocusedChangeBreakdownResultV2
    current_evidence_id: str
    reference_evidence_id: str
    current_plan_name: str
    reference_plan_name: str
    current_audit_event_id: str
    reference_audit_event_id: str
    scope_summary: str | None = None

    # Day93 Business Projection：由 Delivery 层确定性生成。
    # UI 不重新解析 scope，也不重新计算 concentration / conclusion。
    business_scope: BusinessScopeProjectionV2 | None = None
    assessment: InvestigationStepAssessmentV2 | None = None


def _expected_member_field_v2(
    dimension: FocusedChangeDimensionV2,
) -> str:
    return {
        FocusedChangeDimensionV2.CHANNEL: "channel_name",
        FocusedChangeDimensionV2.CATEGORY: "category",
        FocusedChangeDimensionV2.REGION: "region_name",
        FocusedChangeDimensionV2.AREA: "region_group",
        FocusedChangeDimensionV2.PROVINCE: "province_name",
        FocusedChangeDimensionV2.CITY: "region_name",
        FocusedChangeDimensionV2.CAMPAIGN: "campaign_name",
    }[dimension]


def _to_observations_v2(
    *,
    breakdown: ProtectedBreakdownViewV2,
    dimension: FocusedChangeDimensionV2,
) -> tuple[FocusedChangeObservationV2, ...]:
    member_field = _expected_member_field_v2(dimension)
    expected_fields = {member_field, "gmv"}

    if set(breakdown.field_names) != expected_fields:
        raise ValueError(
            "Focused Change Breakdown 的 Protected Result "
            "字段形状不符合预期："
            f"expected={sorted(expected_fields)}; "
            f"actual={sorted(breakdown.field_names)}"
        )

    observations: list[FocusedChangeObservationV2] = []

    for index, row in enumerate(breakdown.rows):
        if set(row) != expected_fields:
            raise ValueError(
                "Focused Change Breakdown row 字段不符合预期："
                f"row_index={index}; "
                f"expected={sorted(expected_fields)}; "
                f"actual={sorted(row)}"
            )

        raw_label = row.get(member_field)
        raw_value = row.get("gmv")

        if raw_label is None or not str(raw_label).strip():
            raise ValueError(
                f"Focused Change member label 不能为空：row={index}"
            )

        if raw_value is None or isinstance(raw_value, bool):
            raise ValueError(
                f"Focused Change GMV 不能为空：row={index}"
            )

        key = str(raw_label).strip()
        label = (
            AREA_DISPLAY_LABELS_V2.get(key, key)
            if dimension == FocusedChangeDimensionV2.AREA
            else key
        )

        observations.append(
            FocusedChangeObservationV2(
                member_key=key,
                member_label=label,
                value=Decimal(str(raw_value)),
            )
        )

    return tuple(observations)


def build_focused_change_breakdown_delivery_v2(
    *,
    current_breakdown: ProtectedBreakdownViewV2,
    reference_breakdown: ProtectedBreakdownViewV2,
    focus_scope: InvestigationFocusScopeV1,
    comparison: TimeComparisonContractV2,
    dimension: FocusedChangeDimensionV2,
) -> FocusedChangeBreakdownDeliveryV2:
    reference_value = getattr(focus_scope, "reference_value", None)
    current_value = getattr(focus_scope, "current_value", None)
    delta = getattr(focus_scope, "delta", None)

    if (
        reference_value is None
        or current_value is None
        or delta is None
    ):
        raise ValueError(
            "Focused Change Delivery 需要带 comparison values "
            "的 Investigation Focus。"
        )

    expected_grain = dimension.value

    if (
        current_breakdown.metric_name != "gmv"
        or reference_breakdown.metric_name != "gmv"
    ):
        raise ValueError(
            "Focused Change 当前只支持 GMV Breakdown。"
        )

    if (
        current_breakdown.result_grain != expected_grain
        or reference_breakdown.result_grain != expected_grain
    ):
        raise ValueError(
            "Focused Change grain 与 dimension 不一致。"
        )

    if (
        current_breakdown.analysis_window
        != comparison.current_window
    ):
        raise ValueError(
            "Current Breakdown window 与 comparison.current_window "
            "不一致。"
        )

    if (
        reference_breakdown.analysis_window
        != comparison.reference_window
    ):
        raise ValueError(
            "Reference Breakdown window 与 comparison.reference_window "
            "不一致。"
        )

    if (
        current_breakdown.dataset_name
        != reference_breakdown.dataset_name
    ):
        raise ValueError(
            "Current / Reference Breakdown dataset 不一致。"
        )

    if (
        current_breakdown.scope_summary
        != reference_breakdown.scope_summary
    ):
        raise ValueError(
            "Current / Reference Breakdown effective scope 不一致，"
            "禁止做 Focused Change 分解。"
        )

    current_observations = _to_observations_v2(
        breakdown=current_breakdown,
        dimension=dimension,
    )
    reference_observations = _to_observations_v2(
        breakdown=reference_breakdown,
        dimension=dimension,
    )

    result = analyze_focused_change_breakdown_v2(
        dimension_name=dimension,
        focus_member_key=focus_scope.member_key,
        focus_member_label=focus_scope.member_label,
        reference_focus_value=reference_value,
        current_focus_value=current_value,
        reference_members=reference_observations,
        current_members=current_observations,
    )

    if result.focus_delta != delta:
        raise ValueError(
            "Focused Change result delta 与 Investigation Focus "
            "可信 delta 不一致。"
        )

    return FocusedChangeBreakdownDeliveryV2(
        scope_kind=ChangeBreakdownScopeKindV2.MEMBER_FOCUS,
        result=result,
        current_evidence_id=current_breakdown.evidence_id,
        reference_evidence_id=reference_breakdown.evidence_id,
        current_plan_name=current_breakdown.plan_name,
        reference_plan_name=reference_breakdown.plan_name,
        current_audit_event_id=current_breakdown.audit_event_id,
        reference_audit_event_id=reference_breakdown.audit_event_id,
        scope_summary=current_breakdown.scope_summary,
        business_scope=build_business_scope_projection_v2(
            current_breakdown.scope_summary
        ),
        assessment=assess_investigation_step_v2(
            result=result,
            is_overall_scope=False,
        ),
    )


def build_geography_focused_change_breakdown_delivery_v2(
    *,
    current_breakdown: ProtectedBreakdownViewV2,
    reference_breakdown: ProtectedBreakdownViewV2,
    focus_scope: GeographyFocusScopeV2,
    comparison: TimeComparisonContractV2,
    dimension: FocusedChangeDimensionV2,
) -> FocusedChangeBreakdownDeliveryV2:
    """Use parent Geography Focus values as the next-level reconciliation baseline."""

    if (
        focus_scope.reference_value is None
        or focus_scope.current_value is None
        or focus_scope.delta is None
    ):
        raise ValueError(
            "Geography Focused Change 需要可信两期 focus values。"
        )

    expected_grain = dimension.value

    if current_breakdown.metric_name != "gmv" or reference_breakdown.metric_name != "gmv":
        raise ValueError("Geography Focused Change 当前只支持 GMV Breakdown。")

    if (
        current_breakdown.result_grain != expected_grain
        or reference_breakdown.result_grain != expected_grain
    ):
        raise ValueError("Geography Focused Change grain 与 dimension 不一致。")

    if current_breakdown.analysis_window != comparison.current_window:
        raise ValueError("Current Breakdown window 与 comparison.current_window 不一致。")
    if reference_breakdown.analysis_window != comparison.reference_window:
        raise ValueError("Reference Breakdown window 与 comparison.reference_window 不一致。")
    if current_breakdown.dataset_name != reference_breakdown.dataset_name:
        raise ValueError("Current / Reference Breakdown dataset 不一致。")
    if current_breakdown.scope_summary != reference_breakdown.scope_summary:
        raise ValueError("Current / Reference Geography effective scope 不一致。")

    current_observations = _to_observations_v2(
        breakdown=current_breakdown, dimension=dimension
    )
    reference_observations = _to_observations_v2(
        breakdown=reference_breakdown, dimension=dimension
    )

    result = analyze_focused_change_breakdown_v2(
        dimension_name=dimension,
        focus_member_key=focus_scope.member_key,
        focus_member_label=focus_scope.member_label,
        reference_focus_value=focus_scope.reference_value,
        current_focus_value=focus_scope.current_value,
        reference_members=reference_observations,
        current_members=current_observations,
    )

    if result.focus_delta != focus_scope.delta:
        raise ValueError(
            "Geography Focused Change result delta 与可信 Geography Focus 不一致。"
        )

    return FocusedChangeBreakdownDeliveryV2(
        scope_kind=ChangeBreakdownScopeKindV2.MEMBER_FOCUS,
        result=result,
        current_evidence_id=current_breakdown.evidence_id,
        reference_evidence_id=reference_breakdown.evidence_id,
        current_plan_name=current_breakdown.plan_name,
        reference_plan_name=reference_breakdown.plan_name,
        current_audit_event_id=current_breakdown.audit_event_id,
        reference_audit_event_id=reference_breakdown.audit_event_id,
        scope_summary=current_breakdown.scope_summary,
        business_scope=build_business_scope_projection_v2(current_breakdown.scope_summary),
        assessment=assess_investigation_step_v2(result=result, is_overall_scope=False),
    )

def build_global_change_breakdown_delivery_v2(
    *,
    current_breakdown: ProtectedBreakdownViewV2,
    reference_breakdown: ProtectedBreakdownViewV2,
    comparison: TimeComparisonContractV2,
    overall_reference_value: Decimal,
    overall_current_value: Decimal,
    dimension: FocusedChangeDimensionV2,
) -> FocusedChangeBreakdownDeliveryV2:
    """
    保持原 Requested Scope 的两期全局变化分解。

    与 Member Focus 路径使用同一个 deterministic arithmetic core，
    唯一区别是 reconciliation baseline 来自已确认的 Overall
    Comparison，而不是单一渠道 Focus。
    """

    expected_grain = dimension.value

    if (
        current_breakdown.metric_name != "gmv"
        or reference_breakdown.metric_name != "gmv"
    ):
        raise ValueError(
            "Global Change 当前只支持 GMV Breakdown。"
        )

    if (
        current_breakdown.result_grain != expected_grain
        or reference_breakdown.result_grain != expected_grain
    ):
        raise ValueError(
            "Global Change grain 与 dimension 不一致。"
        )

    if current_breakdown.analysis_window != comparison.current_window:
        raise ValueError(
            "Current Breakdown window 与 comparison.current_window 不一致。"
        )

    if reference_breakdown.analysis_window != comparison.reference_window:
        raise ValueError(
            "Reference Breakdown window 与 comparison.reference_window 不一致。"
        )

    if current_breakdown.dataset_name != reference_breakdown.dataset_name:
        raise ValueError(
            "Current / Reference Breakdown dataset 不一致。"
        )

    if current_breakdown.scope_summary != reference_breakdown.scope_summary:
        raise ValueError(
            "Current / Reference Breakdown effective scope 不一致，"
            "禁止做 Global Change 分解。"
        )

    current_observations = _to_observations_v2(
        breakdown=current_breakdown,
        dimension=dimension,
    )
    reference_observations = _to_observations_v2(
        breakdown=reference_breakdown,
        dimension=dimension,
    )

    result = analyze_focused_change_breakdown_v2(
        dimension_name=dimension,
        focus_member_key="__overall__",
        focus_member_label="整体GMV",
        reference_focus_value=overall_reference_value,
        current_focus_value=overall_current_value,
        reference_members=reference_observations,
        current_members=current_observations,
    )

    expected_delta = overall_current_value - overall_reference_value

    if result.focus_delta != expected_delta:
        raise ValueError(
            "Global Change result delta 与 Overall Comparison delta 不一致。"
        )

    return FocusedChangeBreakdownDeliveryV2(
        scope_kind=ChangeBreakdownScopeKindV2.OVERALL,
        result=result,
        current_evidence_id=current_breakdown.evidence_id,
        reference_evidence_id=reference_breakdown.evidence_id,
        current_plan_name=current_breakdown.plan_name,
        reference_plan_name=reference_breakdown.plan_name,
        current_audit_event_id=current_breakdown.audit_event_id,
        reference_audit_event_id=reference_breakdown.audit_event_id,
        scope_summary=current_breakdown.scope_summary,
        business_scope=build_business_scope_projection_v2(
            current_breakdown.scope_summary
        ),
        assessment=assess_investigation_step_v2(
            result=result,
            is_overall_scope=True,
        ),
    )

