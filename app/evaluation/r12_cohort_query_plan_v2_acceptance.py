from __future__ import annotations

from datetime import date

from app.semantic_layer.r12_cohort_contract_v2 import (
    R12CohortHistoryStatusV2,
    build_r12_cohort_contract_v2,
)
from app.semantic_layer.r12_cohort_query_plan_v2 import (
    build_r12_cohort_metric_family_v2,
)
from app.semantic_layer.time_comparison_contract_v2 import (
    TimeWindowReferenceV2,
)
from app.semantic_layer.time_window_binding_v2 import (
    TimeApplicationModeV2,
    TimeBindingStatusV2,
    bind_time_window_v2,
)
from app.semantic_layer.time_window_resolver_v2 import (
    DEFAULT_TIME_WINDOW_POLICY_V2,
    TimeExpressionTypeV2,
    TimeWindowResolutionSourceV2,
    TimeWindowResolutionStatusV2,
    TimeWindowResolutionV2,
)


def _resolution(
    start_date: date,
    end_date: date,
) -> TimeWindowResolutionV2:
    policy = DEFAULT_TIME_WINDOW_POLICY_V2

    return TimeWindowResolutionV2(
        status=TimeWindowResolutionStatusV2.RESOLVED,
        source=TimeWindowResolutionSourceV2.EXPLICIT,
        expression_type=TimeExpressionTypeV2.EXPLICIT_DATE_RANGE,
        reference_date=end_date,
        requested_start_date=start_date,
        requested_end_date=end_date,
        effective_start_date=start_date,
        effective_end_date=end_date,
        policy_name=policy.policy_name,
        policy_version=policy.policy_version,
        evidence=(),
        adjustment_reasons=(),
        notice_required=False,
        user_notice=None,
        error=None,
    )


def test_r12_contract_for_2025_july() -> None:
    contract = build_r12_cohort_contract_v2(
        report_window=TimeWindowReferenceV2(
            start_date=date(2025, 7, 1),
            end_date=date(2025, 7, 31),
        )
    )

    assert contract.base_window.start_date == date(2024, 7, 1)
    assert contract.base_window.end_date == date(2025, 6, 30)
    assert (
        contract.history_status
        == R12CohortHistoryStatusV2.READY
    )


def test_r12_contract_fails_closed_for_2024() -> None:
    contract = build_r12_cohort_contract_v2(
        report_window=TimeWindowReferenceV2(
            start_date=date(2024, 12, 1),
            end_date=date(2024, 12, 31),
        )
    )

    assert contract.base_window.start_date == date(2023, 12, 1)
    assert (
        contract.history_status
        == R12CohortHistoryStatusV2.INSUFFICIENT_HISTORY
    )


def test_r12_family_has_five_independent_metrics() -> None:
    plans = build_r12_cohort_metric_family_v2()

    assert len(plans) == 5
    assert len({plan.name for plan in plans}) == 5
    assert len({plan.metric for plan in plans}) == 5

    assert {
        plan.metric
        for plan in plans
    } == {
        "r12_base_customer_count",
        "r12_repurchase_customer_count",
        "r12_repurchase_rate",
        "r12_repurchase_amount",
        "r12_repurchase_spending",
    }

    assert all(
        plan.scope_contract.scope_mode.value
        == "predicate_safe"
        for plan in plans
    )


def test_time_binding_only_places_report_window() -> None:
    plan = build_r12_cohort_metric_family_v2()[2]

    decision = bind_time_window_v2(
        plan=plan,
        resolution=_resolution(
            date(2025, 7, 1),
            date(2025, 7, 31),
        ),
    )

    assert decision.status == TimeBindingStatusV2.BOUND
    assert decision.allowed
    assert decision.contract is not None
    assert (
        decision.contract.application_mode
        == TimeApplicationModeV2.STAGED
    )

    stages = {
        item.stage_id
        for item in decision.contract.applications
    }

    # Base Stage 只消费 analysis_start_date 推导 R12，
    # 不应被 canonical current-window BETWEEN 绑定。
    assert "base_item_effective" not in stages
    assert "report_item_effective" in stages


def test_effective_purchase_contract_is_order_level_net_positive() -> None:
    plan = build_r12_cohort_metric_family_v2()[0]

    stages = {
        stage.stage_id: stage
        for stage in plan.query_logic.stages
    }

    base_order = stages["base_order_effective"]
    report_order = stages["report_order_effective"]

    assert any(
        "SUM(bie.item_effective_amount) > 0" in item
        for item in base_order.having
    )
    assert any(
        "SUM(rie.item_effective_amount) > 0" in item
        for item in report_order.having
    )


TESTS = (
    test_r12_contract_for_2025_july,
    test_r12_contract_fails_closed_for_2024,
    test_r12_family_has_five_independent_metrics,
    test_time_binding_only_places_report_window,
    test_effective_purchase_contract_is_order_level_net_positive,
)


def run_acceptance() -> None:
    passed = 0
    failed = 0

    print("=" * 88)
    print("Day93 B5B-1 R12 Cohort Contract / Query Plan Acceptance")
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
