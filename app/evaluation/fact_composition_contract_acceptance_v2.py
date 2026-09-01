from __future__ import annotations

from decimal import Decimal
from datetime import date

from app.delivery.fact_composition_delivery_v2 import (
    FactCompositionDimensionV2,
    FactCompositionReconciliationStatusV2,
    build_fact_composition_projection_v2,
)
from app.semantic_layer.time_comparison_contract_v2 import (
    TimeWindowReferenceV2,
)


WINDOW = TimeWindowReferenceV2(
    start_date=date(2025, 1, 1),
    end_date=date(2025, 12, 31),
)


def test_full_member_list_and_top_n_summary() -> None:
    result = build_fact_composition_projection_v2(
        dimension=FactCompositionDimensionV2.CHANNEL,
        overall_value=Decimal("100"),
        analysis_window=WINDOW,
        scope_summary="SHANGHAI",
        rows=(
            {"channel_name": "A", "gmv": Decimal("40")},
            {"channel_name": "B", "gmv": Decimal("30")},
            {"channel_name": "C", "gmv": Decimal("20")},
            {"channel_name": "D", "gmv": Decimal("10")},
        ),
        evidence_id="ev-channel",
        plan_name="gmv_channel_v2",
        audit_event_id="audit-channel",
    )

    assert len(result.members) == 4
    assert result.released_row_count == 4
    assert result.top_n == 3
    assert result.top_n_share == Decimal("0.9")
    assert result.members[0].share == Decimal("0.4")
    assert (
        result.reconciliation_status
        == FactCompositionReconciliationStatusV2.RECONCILED
    )
    assert result.unexplained_remainder == 0


def test_partial_composition_is_not_reconciled() -> None:
    result = build_fact_composition_projection_v2(
        dimension=FactCompositionDimensionV2.CATEGORY,
        overall_value=Decimal("100"),
        analysis_window=WINDOW,
        scope_summary="SHANGHAI",
        rows=(
            {"category": "A", "gmv": Decimal("60")},
            {"category": "B", "gmv": Decimal("30")},
        ),
        evidence_id="ev-category",
        plan_name="gmv_category_v2",
        audit_event_id="audit-category",
    )

    assert (
        result.reconciliation_status
        == FactCompositionReconciliationStatusV2.NOT_RECONCILED
    )
    assert result.member_sum == Decimal("90")
    assert result.unexplained_remainder == Decimal("10")


def main() -> None:
    test_full_member_list_and_top_n_summary()
    print("PASS: 完整成员不被 Top-N 截断")

    test_partial_composition_is_not_reconciled()
    print("PASS: 未完整对账不会伪装成 100% 构成")

    print("=" * 72)
    print("Fact Composition Contract Acceptance passed.")


if __name__ == "__main__":
    main()
