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
from app.semantic_layer.order_count_customer_composition_query_plan_v2 import (
    ORDER_COUNT_CUSTOMER_SEGMENT_ORDER_V2,
    build_order_count_customer_lifecycle_membership_plan_v2,
)
from app.semantic_layer.query_plan_v2_catalog_builder import (
    build_query_plan_v2_catalog,
)
from app.semantic_layer.query_plan_v2_models import (
    ScopeMode,
    StagedQueryLogic,
)
from app.semantic_layer.time_comparison_contract_v2 import (
    TimeWindowReferenceV2,
)
from app.ui.decision_console_presenters_v2 import (
    build_fact_composition_display_rows_v2,
)


def test_order_count_has_three_additive_dimensions() -> None:
    assert (
        fact_composition_registered_dimensions_for_metric_v2(
            "order_count"
        )
        == (
            FactCompositionDimensionV2.PEOPLE,
            FactCompositionDimensionV2.CHANNEL,
            FactCompositionDimensionV2.REGION,
        )
    )


def test_order_count_category_remains_breakdown_only() -> None:
    assert (
        fact_composition_registered_plan_name_v2(
            metric_name="order_count",
            dimension=FactCompositionDimensionV2.CATEGORY,
        )
        is None
    )


def test_customer_composition_plan_is_predicate_safe_staged() -> None:
    plan = (
        build_order_count_customer_lifecycle_membership_plan_v2()
    )

    assert plan.name == (
        "order_count_customer_lifecycle_membership_v2"
    )
    assert plan.metric == "order_count"
    assert plan.result_grain == (
        "customer_lifecycle_membership"
    )
    assert isinstance(
        plan.query_logic,
        StagedQueryLogic,
    )
    assert (
        plan.scope_contract.scope_mode
        == ScopeMode.PREDICATE_SAFE
    )
    assert len(plan.scope_contract.targets) == 2


def test_customer_plan_uses_same_scope_history_not_global_history() -> None:
    plan = (
        build_order_count_customer_lifecycle_membership_plan_v2()
    )

    history = plan.query_logic.stages[0]
    report = plan.query_logic.stages[1]

    assert (
        "CAST(hist.paid_at AS DATE) < :analysis_start_date"
        in history.filters
    )
    assert not any(
        ":analysis_end_date" in item
        for item in history.filters
    )
    assert any(
        (
            ":analysis_start_date" in item
            and ":analysis_end_date" in item
        )
        for item in report.filters
    )


def test_customer_business_order_is_frozen() -> None:
    assert ORDER_COUNT_CUSTOMER_SEGMENT_ORDER_V2 == (
        "OLD_PLATINUM",
        "OLD_GOLD",
        "OLD_SILVER",
        "OLD_BRONZE",
        "OLD_NON_MEMBER",
        "NEW_CUSTOMER",
    )


def test_customer_projection_uses_fixed_order_and_no_top3() -> None:
    result = build_fact_composition_projection_v2(
        dimension=FactCompositionDimensionV2.PEOPLE,
        metric_name="order_count",
        overall_value=Decimal("20548"),
        analysis_window=TimeWindowReferenceV2(
            start_date=date(2025, 1, 1),
            end_date=date(2025, 12, 31),
        ),
        scope_summary="test",
        rows=(
            {
                "customer_segment": "NEW_CUSTOMER",
                "order_count": Decimal("4000"),
            },
            {
                "customer_segment": "OLD_NON_MEMBER",
                "order_count": Decimal("5000"),
            },
            {
                "customer_segment": "OLD_BRONZE",
                "order_count": Decimal("4000"),
            },
            {
                "customer_segment": "OLD_SILVER",
                "order_count": Decimal("3000"),
            },
            {
                "customer_segment": "OLD_GOLD",
                "order_count": Decimal("2500"),
            },
            {
                "customer_segment": "OLD_PLATINUM",
                "order_count": Decimal("2048"),
            },
        ),
        evidence_id="ev-order-customer",
        plan_name="order_count_customer_lifecycle_membership_v2",
        audit_event_id="audit-order-customer",
    )

    assert [
        item.member_label
        for item in result.members
    ] == list(ORDER_COUNT_CUSTOMER_SEGMENT_ORDER_V2)

    assert result.ranking_summary_enabled is False
    assert result.top_n == 0
    assert result.top_n_share is None
    assert (
        result.reconciliation_status
        == FactCompositionReconciliationStatusV2.RECONCILED
    )


def test_presenter_appends_trusted_summary_row() -> None:
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
        evidence_id="ev-channel",
        plan_name="order_count_channel_v2",
        audit_event_id="audit-channel",
    )

    rows = build_fact_composition_display_rows_v2(result)

    assert rows[-1]["渠道"] == "汇总"
    assert rows[-1]["订单数"] == "20,548"
    assert rows[-1]["构成占比"] == "100.00%"


def test_catalog_expands_to_60_without_new_metric() -> None:
    catalog = build_query_plan_v2_catalog()

    assert len(catalog.query_plans) == 60
    assert len(
        {
            plan.metric
            for plan in catalog.query_plans
        }
    ) == 24

    match = [
        plan
        for plan in catalog.query_plans
        if plan.name
        == "order_count_customer_lifecycle_membership_v2"
    ]

    assert len(match) == 1


TESTS = (
    test_order_count_has_three_additive_dimensions,
    test_order_count_category_remains_breakdown_only,
    test_customer_composition_plan_is_predicate_safe_staged,
    test_customer_plan_uses_same_scope_history_not_global_history,
    test_customer_business_order_is_frozen,
    test_customer_projection_uses_fixed_order_and_no_top3,
    test_presenter_appends_trusted_summary_row,
    test_catalog_expands_to_60_without_new_metric,
)


def run_acceptance() -> None:
    passed = 0
    failed = 0

    print("=" * 88)
    print("Day93 F01 Full Composition Contract Acceptance")
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
