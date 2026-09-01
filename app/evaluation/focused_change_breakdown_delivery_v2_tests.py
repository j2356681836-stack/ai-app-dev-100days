from datetime import date
from decimal import Decimal

from app.agents.focused_change_breakdown_v2 import (
    FocusedChangeDimensionV2,
    FocusedChangeReconciliationStatusV2,
)
from app.delivery.decision_console_view_v2 import (
    ProtectedBreakdownViewV2,
)
from app.delivery.focused_change_breakdown_delivery_v2 import (
    build_focused_change_breakdown_delivery_v2,
)
from app.delivery.investigation_focus_scope_v1 import (
    InvestigationFocusDimensionV1,
    InvestigationFocusScopeV1,
)
from app.semantic_layer.time_comparison_contract_v2 import (
    AlignmentModeV2,
    ComparisonTypeV2,
    PeriodModeV2,
    TimeComparisonContractV2,
    TimeWindowReferenceV2,
)


def _window(
    start: date,
    end: date,
) -> TimeWindowReferenceV2:
    return TimeWindowReferenceV2(
        start_date=start,
        end_date=end,
    )


def _breakdown(
    *,
    evidence_id: str,
    window: TimeWindowReferenceV2,
    rows: tuple[dict, ...],
) -> ProtectedBreakdownViewV2:
    return ProtectedBreakdownViewV2(
        evidence_id=evidence_id,
        metric_name="gmv",
        result_grain="category",
        analysis_window=window,
        scope_summary="渠道代码：JD",
        field_names=("category", "gmv"),
        rows=rows,
        row_count=len(rows),
        dataset_name="beauty_bi_v2",
        plan_name="gmv_category_v2",
        tool_name="governed_gmv_category_query",
        tool_version="dataset_v2",
        audit_event_id=f"audit-{evidence_id}",
    )


def test_protected_two_window_breakdowns_build_focused_change() -> None:
    reference_window = _window(
        date(2025, 9, 1),
        date(2025, 9, 30),
    )
    current_window = _window(
        date(2025, 10, 1),
        date(2025, 10, 31),
    )

    comparison = TimeComparisonContractV2(
        comparison_type=ComparisonTypeV2.MOM,
        period_mode=PeriodModeV2.COMPLETED_PERIOD,
        alignment_mode=AlignmentModeV2.CALENDAR_ALIGNED,
        current_window=current_window,
        reference_window=reference_window,
    )

    focus = InvestigationFocusScopeV1(
        dimension=InvestigationFocusDimensionV1.CHANNEL,
        member_key="京东旗舰店",
        member_label="京东旗舰店",
        channel_codes=frozenset({"JD"}),
        source_evidence_id="ev_contrib_fixture",
        reference_value=Decimal("139004.92"),
        current_value=Decimal("243351.20"),
        delta=Decimal("104346.28"),
    )

    reference = _breakdown(
        evidence_id="ev-ref",
        window=reference_window,
        rows=(
            {"category": "护肤", "gmv": Decimal("80000.00")},
            {"category": "香氛", "gmv": Decimal("30000.00")},
            {"category": "彩妆", "gmv": Decimal("20000.00")},
            {"category": "防晒", "gmv": Decimal("9004.92")},
        ),
    )

    current = _breakdown(
        evidence_id="ev-cur",
        window=current_window,
        rows=(
            {"category": "护肤", "gmv": Decimal("114141.80")},
            {"category": "香氛", "gmv": Decimal("54250.54")},
            {"category": "彩妆", "gmv": Decimal("45486.60")},
            {"category": "防晒", "gmv": Decimal("29472.26")},
        ),
    )

    delivery = build_focused_change_breakdown_delivery_v2(
        current_breakdown=current,
        reference_breakdown=reference,
        focus_scope=focus,
        comparison=comparison,
        dimension=FocusedChangeDimensionV2.CATEGORY,
    )

    result = delivery.result

    assert result.focus_delta == Decimal("104346.28")
    assert result.sum_member_delta == Decimal("104346.28")
    assert result.unexplained_remainder == Decimal("0.00")
    assert (
        result.reconciliation_status
        == FocusedChangeReconciliationStatusV2.RECONCILED
    )
    assert delivery.scope_summary == "渠道代码：JD"
    assert delivery.current_evidence_id == "ev-cur"
    assert delivery.reference_evidence_id == "ev-ref"

    print(
        "PASS: "
        "test_protected_two_window_breakdowns_build_focused_change"
    )
    print("PASS: current/reference scope = JD")
    print("PASS: protected lineage preserved")
    print("PASS: reconciliation = reconciled")


if __name__ == "__main__":
    test_protected_two_window_breakdowns_build_focused_change()
