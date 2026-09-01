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
    ChangeBreakdownScopeKindV2,
    build_global_change_breakdown_delivery_v2,
)
from app.semantic_layer.time_comparison_contract_v2 import (
    AlignmentModeV2,
    ComparisonTypeV2,
    PeriodModeV2,
    TimeComparisonContractV2,
    TimeWindowReferenceV2,
)


def _window(start: date, end: date) -> TimeWindowReferenceV2:
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
        scope_summary=None,
        field_names=("category", "gmv"),
        rows=rows,
        row_count=len(rows),
        dataset_name="beauty_bi_v2",
        plan_name="gmv_category_v2",
        tool_name="governed_gmv_category_query",
        tool_version="dataset_v2",
        audit_event_id=f"audit-{evidence_id}",
    )


def test_global_category_change_reconciles_to_overall_delta() -> None:
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

    reference = _breakdown(
        evidence_id="ev-global-ref",
        window=reference_window,
        rows=(
            {"category": "护肤", "gmv": Decimal("400000.00")},
            {"category": "香氛", "gmv": Decimal("200000.00")},
            {"category": "彩妆", "gmv": Decimal("150000.00")},
            {"category": "防晒", "gmv": Decimal("97765.20")},
        ),
    )

    current = _breakdown(
        evidence_id="ev-global-cur",
        window=current_window,
        rows=(
            {"category": "护肤", "gmv": Decimal("580000.00")},
            {"category": "香氛", "gmv": Decimal("300000.00")},
            {"category": "彩妆", "gmv": Decimal("220000.00")},
            {"category": "防晒", "gmv": Decimal("131371.04")},
        ),
    )

    delivery = build_global_change_breakdown_delivery_v2(
        current_breakdown=current,
        reference_breakdown=reference,
        comparison=comparison,
        overall_reference_value=Decimal("847765.20"),
        overall_current_value=Decimal("1231371.04"),
        dimension=FocusedChangeDimensionV2.CATEGORY,
    )

    result = delivery.result

    assert delivery.scope_kind == ChangeBreakdownScopeKindV2.OVERALL
    assert result.focus_member_key == "__overall__"
    assert result.focus_delta == Decimal("383605.84")
    assert result.sum_member_delta == Decimal("383605.84")
    assert result.unexplained_remainder == Decimal("0.00")
    assert (
        result.reconciliation_status
        == FocusedChangeReconciliationStatusV2.RECONCILED
    )

    print("PASS: test_global_category_change_reconciles_to_overall_delta")
    print("PASS: scope kind = overall")
    print("PASS: overall delta = 383605.84")
    print("PASS: reconciliation = reconciled")


if __name__ == "__main__":
    test_global_category_change_reconciles_to_overall_delta()
