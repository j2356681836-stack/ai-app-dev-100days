from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.delivery.fact_composition_delivery_v2 import (
    FactCompositionDimensionV2,
    FactCompositionReconciliationStatusV2,
    build_fact_composition_projection_v2,
    fact_composition_registered_dimensions_for_metric_v2,
    fact_composition_registered_plan_name_v2,
)
from app.semantic_layer.query_plan_v2_loader import (
    load_query_plan_v2_catalog,
)
from app.semantic_layer.time_comparison_contract_v2 import (
    TimeWindowReferenceV2,
)
from app.ui.decision_console_presenters_v2 import (
    build_fact_composition_display_rows_v2,
    format_fact_metric_value_v2,
    format_metric_name_v2,
    format_number_v2,
)


def test_order_count_fact_formats_as_integer() -> None:
    assert (
        format_fact_metric_value_v2(
            "order_count",
            Decimal("20548"),
        )
        == "20,548"
    )

    # 通用 Decimal formatter 保持原行为，说明这不是全局去小数。
    assert format_number_v2(Decimal("20548")) == "20,548.00"


def test_order_count_has_business_label() -> None:
    assert format_metric_name_v2("order_count") == "订单数"


def test_order_count_channel_is_explicit_additive_composition() -> None:
    assert (
        fact_composition_registered_dimensions_for_metric_v2(
            "order_count"
        )
        == (FactCompositionDimensionV2.CHANNEL,)
    )

    assert (
        fact_composition_registered_plan_name_v2(
            metric_name="order_count",
            dimension=FactCompositionDimensionV2.CHANNEL,
        )
        == "order_count_channel_v2"
    )


def test_order_count_category_is_not_misclassified_as_composition() -> None:
    assert (
        fact_composition_registered_plan_name_v2(
            metric_name="order_count",
            dimension=FactCompositionDimensionV2.CATEGORY,
        )
        is None
    )


def test_gmv_existing_composition_capabilities_remain_registered() -> None:
    assert (
        fact_composition_registered_dimensions_for_metric_v2(
            "gmv"
        )
        == (
            FactCompositionDimensionV2.PEOPLE,
            FactCompositionDimensionV2.CHANNEL,
            FactCompositionDimensionV2.CATEGORY,
        )
    )


def test_order_count_channel_projection_reconciles() -> None:
    result = build_fact_composition_projection_v2(
        dimension=FactCompositionDimensionV2.CHANNEL,
        metric_name="order_count",
        overall_value=Decimal("20548"),
        analysis_window=TimeWindowReferenceV2(
            start_date=date(2025, 1, 1),
            end_date=date(2025, 12, 31),
        ),
        scope_summary="test",
        rows=(
            {
                "channel_name": "渠道A",
                "order_count": Decimal("12000"),
            },
            {
                "channel_name": "渠道B",
                "order_count": Decimal("8548"),
            },
        ),
        evidence_id="ev-order-channel",
        plan_name="order_count_channel_v2",
        audit_event_id="audit-order-channel",
    )

    assert result.metric_name == "order_count"
    assert result.member_sum == Decimal("20548")
    assert result.unexplained_remainder == Decimal("0")
    assert (
        result.reconciliation_status
        == FactCompositionReconciliationStatusV2.RECONCILED
    )

    rows = build_fact_composition_display_rows_v2(result)
    assert rows[0]["订单数"] == "12,000"
    assert rows[1]["订单数"] == "8,548"


def test_catalog_contains_governed_order_count_channel_plan() -> None:
    catalog = load_query_plan_v2_catalog()

    matches = tuple(
        plan
        for plan in catalog.query_plans
        if plan.name == "order_count_channel_v2"
    )

    assert len(matches) == 1

    plan = matches[0]
    assert plan.metric == "order_count"
    assert plan.result_grain == "channel"


TESTS = (
    test_order_count_fact_formats_as_integer,
    test_order_count_has_business_label,
    test_order_count_channel_is_explicit_additive_composition,
    test_order_count_category_is_not_misclassified_as_composition,
    test_gmv_existing_composition_capabilities_remain_registered,
    test_order_count_channel_projection_reconciles,
    test_catalog_contains_governed_order_count_channel_plan,
)


def run_acceptance() -> None:
    passed = 0
    failed = 0

    print("=" * 88)
    print("Day93 F01 Business Delivery Consistency Acceptance")
    print(f"Cases: {len(TESTS)}")

    for test in TESTS:
        try:
            test()
        except Exception as exc:
            failed += 1
            print(f"[FAIL] {test.__name__}")
            print(f"{type(exc).__name__}: {exc}")
        else:
            passed += 1
            print(f"[PASS] {test.__name__}")

    print("=" * 88)
    print("Summary")
    print(f"Total: {len(TESTS)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    run_acceptance()
