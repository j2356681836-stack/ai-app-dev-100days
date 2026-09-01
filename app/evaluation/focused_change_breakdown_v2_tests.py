from decimal import Decimal

from app.agents.focused_change_breakdown_v2 import (
    FocusedChangeDimensionV2,
    FocusedChangeObservationV2,
    FocusedChangeReconciliationStatusV2,
    analyze_focused_change_breakdown_v2,
)


def test_reconciled_focused_category_change() -> None:
    result = analyze_focused_change_breakdown_v2(
        dimension_name=FocusedChangeDimensionV2.CATEGORY,
        focus_member_key="京东旗舰店",
        focus_member_label="京东旗舰店",
        reference_focus_value=Decimal("139004.92"),
        current_focus_value=Decimal("243351.20"),
        reference_members=(
            FocusedChangeObservationV2(
                member_key="护肤",
                member_label="护肤",
                value=Decimal("80000.00"),
            ),
            FocusedChangeObservationV2(
                member_key="香氛",
                member_label="香氛",
                value=Decimal("30000.00"),
            ),
            FocusedChangeObservationV2(
                member_key="彩妆",
                member_label="彩妆",
                value=Decimal("20000.00"),
            ),
            FocusedChangeObservationV2(
                member_key="防晒",
                member_label="防晒",
                value=Decimal("9004.92"),
            ),
        ),
        current_members=(
            FocusedChangeObservationV2(
                member_key="护肤",
                member_label="护肤",
                value=Decimal("114141.80"),
            ),
            FocusedChangeObservationV2(
                member_key="香氛",
                member_label="香氛",
                value=Decimal("54250.54"),
            ),
            FocusedChangeObservationV2(
                member_key="彩妆",
                member_label="彩妆",
                value=Decimal("45486.60"),
            ),
            FocusedChangeObservationV2(
                member_key="防晒",
                member_label="防晒",
                value=Decimal("29472.26"),
            ),
        ),
    )

    assert result.focus_delta == Decimal("104346.28")
    assert result.sum_member_delta == Decimal("104346.28")
    assert result.unexplained_remainder == Decimal("0.00")
    assert (
        result.reconciliation_status
        == FocusedChangeReconciliationStatusV2.RECONCILED
    )

    print("PASS: test_reconciled_focused_category_change")
    print("PASS: focus_delta = 104346.28")
    print("PASS: sum_member_delta = 104346.28")
    print("PASS: reconciliation = reconciled")


if __name__ == "__main__":
    test_reconciled_focused_category_change()
