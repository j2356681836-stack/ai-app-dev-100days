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


def _view(
    *,
    evidence_id: str,
    start: date,
    end: date,
    rows: tuple[dict[str, object], ...],
) -> ProtectedBreakdownViewV2:
    return ProtectedBreakdownViewV2(
        evidence_id=evidence_id,
        metric_name="gmv",
        result_grain="campaign",
        analysis_window=TimeWindowReferenceV2(
            start_date=start,
            end_date=end,
        ),
        scope_summary="scope=test",
        field_names=("campaign_name", "gmv"),
        rows=rows,
        row_count=len(rows),
        dataset_name="beauty_bi_v2",
        plan_name="gmv_campaign_v2",
        tool_name="governed_gmv_campaign_query",
        tool_version="dataset_v2",
        audit_event_id=f"audit-{evidence_id}",
    )


def test_campaign_change_reconciles_with_non_campaign_bucket() -> None:
    comparison = TimeComparisonContractV2(
        comparison_type=ComparisonTypeV2.MOM,
        period_mode=PeriodModeV2.COMPLETED_PERIOD,
        alignment_mode=AlignmentModeV2.CALENDAR_ALIGNED,
        reference_window=TimeWindowReferenceV2(
            start_date=date(2025, 9, 1),
            end_date=date(2025, 9, 30),
        ),
        current_window=TimeWindowReferenceV2(
            start_date=date(2025, 10, 1),
            end_date=date(2025, 10, 31),
        ),
        is_partial_period=False,
    )

    reference = _view(
        evidence_id="ref",
        start=date(2025, 9, 1),
        end=date(2025, 9, 30),
        rows=(
            {
                "campaign_name": "非活动订单",
                "gmv": Decimal("80"),
            },
            {
                "campaign_name": "九月活动",
                "gmv": Decimal("20"),
            },
        ),
    )
    current = _view(
        evidence_id="cur",
        start=date(2025, 10, 1),
        end=date(2025, 10, 31),
        rows=(
            {
                "campaign_name": "非活动订单",
                "gmv": Decimal("90"),
            },
            {
                "campaign_name": "2025 双十一",
                "gmv": Decimal("60"),
            },
        ),
    )

    result = build_global_change_breakdown_delivery_v2(
        current_breakdown=current,
        reference_breakdown=reference,
        comparison=comparison,
        overall_reference_value=Decimal("100"),
        overall_current_value=Decimal("150"),
        dimension=FocusedChangeDimensionV2.CAMPAIGN,
    )

    assert result.scope_kind == ChangeBreakdownScopeKindV2.OVERALL
    assert (
        result.result.reconciliation_status
        == FocusedChangeReconciliationStatusV2.RECONCILED
    )
    assert result.result.focus_delta == Decimal("50")
    assert result.result.sum_member_delta == Decimal("50")
    assert result.result.unexplained_remainder == Decimal("0")

    by_label = {
        item.member_label: item
        for item in result.result.members
    }

    assert (
        by_label["2025 双十一"].delta
        == Decimal("60")
    )
    assert (
        by_label["九月活动"].delta
        == Decimal("-20")
    )
    assert (
        by_label["非活动订单"].delta
        == Decimal("10")
    )

    assert result.assessment is not None
    assert "不能证明活动造成了对应增量" in (
        " ".join(result.assessment.cannot_confirm)
    )

    print(
        "PASS: "
        "test_campaign_change_reconciles_with_non_campaign_bucket"
    )


def main() -> None:
    test_campaign_change_reconciles_with_non_campaign_bucket()


if __name__ == "__main__":
    main()
