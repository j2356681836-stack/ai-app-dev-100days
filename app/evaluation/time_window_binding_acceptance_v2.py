from __future__ import annotations

from datetime import date

from app.semantic_layer.query_plan_v2_loader import (
    get_query_plan_v2_by_name,
    load_query_plan_v2_catalog,
)
from app.semantic_layer.time_window_binding_v2 import (
    TimeApplicationModeV2,
    TimeBindingStatusV2,
    bind_time_window_v2,
)
from app.semantic_layer.time_window_resolver_v2 import (
    resolve_time_window_v2,
)
from app.semantic_layer.time_window_resolver_v2 import (
    TimeWindowResolutionStatusV2,
    resolve_time_window_v2,
)

REFERENCE_DATE = date(
    2026,
    8,
    3,
)


def _require_plan(
    plan_name: str,
):
    plan = get_query_plan_v2_by_name(
        plan_name
    )

    if plan is None:
        raise AssertionError(
            f"Missing Query Plan: {plan_name}"
        )

    return plan


def _application_map(
    decision,
) -> dict[str | None, frozenset[str]]:
    if decision.contract is None:
        raise AssertionError(
            "Expected Time Binding contract."
        )

    return {
        application.stage_id: frozenset(
            application.query_references
        )
        for application in (
            decision.contract.applications
        )
    }


def test_simple_default_window() -> None:
    plan = _require_plan(
        "gmv_overall_v2"
    )
    resolution = resolve_time_window_v2(
        "GMV是多少？",
        reference_date=REFERENCE_DATE,
    )

    decision = bind_time_window_v2(
        plan=plan,
        resolution=resolution,
    )

    assert decision.allowed
    assert decision.status == TimeBindingStatusV2.BOUND
    assert decision.contract is not None

    contract = decision.contract

    assert (
        contract.application_mode
        == TimeApplicationModeV2.QUERY_LEVEL
    )
    assert contract.effective_start_date == date(
        2026,
        5,
        4,
    )
    assert contract.effective_end_date == REFERENCE_DATE
    assert contract.notice_required
    assert contract.user_notice == (
        "未检测到明确的时间范围。"
        "本次按默认策略查询最近3个月："
        "2026-05-04 至 2026-08-03。"
    )

    applications = _application_map(
        decision
    )

    assert applications == {
        None: frozenset(
            {
                "fo.paid_at",
            }
        )
    }


def test_cross_fact_declared_stage_binding() -> None:
    plan = _require_plan(
        "roi_channel_v2"
    )
    resolution = resolve_time_window_v2(
        "2026年7月各渠道ROI",
        reference_date=REFERENCE_DATE,
    )

    decision = bind_time_window_v2(
        plan=plan,
        resolution=resolution,
    )

    assert decision.allowed
    assert decision.contract is not None

    contract = decision.contract

    assert (
        contract.application_mode
        == TimeApplicationModeV2.STAGED
    )
    assert not contract.notice_required

    applications = _application_map(
        decision
    )

    assert applications == {
        "channel_sales": frozenset(
            {
                "fo.paid_at",
            }
        ),
        "channel_spend": frozenset(
            {
                "fms.spend_date",
            }
        ),
    }


def test_predicate_safe_inferred_stage_binding() -> None:
    plan = _require_plan(
        "refund_rate_overall_v2"
    )
    resolution = resolve_time_window_v2(
        "上月退款率",
        reference_date=REFERENCE_DATE,
    )

    decision = bind_time_window_v2(
        plan=plan,
        resolution=resolution,
    )

    assert decision.allowed
    assert decision.contract is not None

    contract = decision.contract

    assert (
        contract.application_mode
        == TimeApplicationModeV2.STAGED
    )

    applications = _application_map(
        decision
    )

    assert applications == {
        "item_refund_summary": frozenset(
            {
                "fo.paid_at",
            }
        )
    }


def test_global_history_stage_protection() -> None:
    plan = _require_plan(
        "cac_channel_v2"
    )
    resolution = resolve_time_window_v2(
        "最近三个月各渠道CAC",
        reference_date=REFERENCE_DATE,
    )

    decision = bind_time_window_v2(
        plan=plan,
        resolution=resolution,
    )

    assert decision.allowed
    assert decision.contract is not None

    contract = decision.contract

    assert (
        contract.application_mode
        == TimeApplicationModeV2.GLOBAL_HISTORY
    )
    assert (
        contract.protected_history_stage_id
        == "channel_first_paid_history"
    )
    assert (
        contract.analysis_window_stage_id
        == "windowed_channel_acquisition"
    )

    applications = _application_map(
        decision
    )

    assert (
        "channel_first_paid_history"
        not in applications
    )
    assert applications == {
        "channel_spend": frozenset(
            {
                "fms.spend_date",
            }
        ),
        "windowed_channel_acquisition": frozenset(
            {
                "cfp.first_channel_paid_at",
            }
        ),
    }


def test_brand_first_event_stage_protection() -> None:
    plan = _require_plan(
        "brand_paid_new_customer_count_overall_v2"
    )
    resolution = resolve_time_window_v2(
        "上月品牌支付新客数",
        reference_date=REFERENCE_DATE,
    )

    decision = bind_time_window_v2(
        plan=plan,
        resolution=resolution,
    )

    assert decision.allowed
    assert decision.contract is not None

    contract = decision.contract
    applications = _application_map(
        decision
    )

    assert (
        contract.protected_history_stage_id
        == "brand_order_sequence"
    )
    assert (
        contract.analysis_window_stage_id
        == "windowed_brand_acquisition"
    )
    assert "brand_order_sequence" not in applications
    assert applications == {
        "windowed_brand_acquisition": frozenset(
            {
                "bfp.first_paid_at",
            }
        )
    }


def test_unresolved_time_fails_closed() -> None:
    plan = _require_plan(
        "gmv_overall_v2"
    )
    resolution = resolve_time_window_v2(
        "本月和上月GMV",
        reference_date=REFERENCE_DATE,
    )

    decision = bind_time_window_v2(
        plan=plan,
        resolution=resolution,
    )

    assert not decision.allowed
    assert (
        decision.status
        == TimeBindingStatusV2.RESOLUTION_NOT_READY
    )
    assert decision.contract is None


def test_catalog_wide_default_binding() -> None:
    catalog = load_query_plan_v2_catalog()
    resolution = resolve_time_window_v2(
        "查看指标表现",
        reference_date=REFERENCE_DATE,
    )

    assert (
        resolution.status
        == TimeWindowResolutionStatusV2.RESOLVED
    ), (
        "Catalog-wide binding test requires a resolved "
        f"default window, actual={resolution.status.value}, "
        f"error={resolution.error}"
    )

    failures: list[str] = []

    for plan in catalog.query_plans:
        decision = bind_time_window_v2(
            plan=plan,
            resolution=resolution,
        )

        if not decision.allowed:
            failures.append(
                f"{plan.name}: "
                f"{decision.status.value}: "
                f"{decision.detail}"
            )

    assert not failures, "\n".join(
        failures
    )


TESTS = (
    test_simple_default_window,
    test_cross_fact_declared_stage_binding,
    test_predicate_safe_inferred_stage_binding,
    test_global_history_stage_protection,
    test_brand_first_event_stage_protection,
    test_unresolved_time_fails_closed,
    test_catalog_wide_default_binding,
)


def run_acceptance() -> None:
    passed = 0
    failed = 0

    print("=" * 80)
    print(
        "Time Window Binding V2 Acceptance"
    )
    print(
        f"Reference Date: {REFERENCE_DATE}"
    )
    print(
        f"Cases: {len(TESTS)}"
    )

    for test in TESTS:
        print("=" * 80)
        print(
            test.__name__
        )

        try:
            test()
        except Exception as exc:
            failed += 1
            print("[FAIL]")
            print(
                f"{type(exc).__name__}: {exc}"
            )
        else:
            passed += 1
            print("[PASS]")

    print("=" * 80)
    print(
        "Time Window Binding V2 "
        "Acceptance Summary"
    )
    print(
        f"Total: {len(TESTS)}"
    )
    print(
        f"Passed: {passed}"
    )
    print(
        f"Failed: {failed}"
    )

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    run_acceptance()
