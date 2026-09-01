from __future__ import annotations

from decimal import Decimal

from app.delivery.periodic_business_report_v2 import (
    PeriodicMetricDisplayKindV2,
    PeriodicMetricSectionV2,
    PeriodicMetricSnapshotV2,
    PeriodicMetricSpecV2,
    PeriodicMetricStatusV2,
)
from app.ui.decision_console_presenters_v2 import (
    build_periodic_metric_comparison_rows_v2,
    format_periodic_metric_delta_v2,
    format_periodic_metric_value_v2,
)


def _spec(
    *,
    metric_name: str,
    kind: PeriodicMetricDisplayKindV2,
) -> PeriodicMetricSpecV2:
    return PeriodicMetricSpecV2(
        metric_name=metric_name,
        plan_name=f"{metric_name}_overall_v2",
        chinese_name=metric_name,
        section=PeriodicMetricSectionV2.OVERVIEW,
        display_kind=kind,
        required=False,
        tool_name=f"tool_{metric_name}",
        purpose="acceptance",
    )


def test_ratio_uses_percentage_points() -> None:
    snapshot = PeriodicMetricSnapshotV2(
        spec=_spec(
            metric_name="ratio_metric",
            kind=PeriodicMetricDisplayKindV2.RATIO,
        ),
        status=PeriodicMetricStatusV2.READY,
        message="ready",
        reference_value=Decimal("0.35"),
        current_value=Decimal("0.25"),
        absolute_change=Decimal("-0.10"),
        relative_change=Decimal("-0.285714"),
        percentage_point_change=Decimal("-10.00"),
        current_evidence_id="ev-current",
        reference_evidence_id="ev-reference",
    )

    assert format_periodic_metric_value_v2(snapshot) == "25.00%"
    assert (
        format_periodic_metric_delta_v2(snapshot)
        == "-10.00 pp vs 参考期"
    )


def test_money_uses_relative_change_for_card_delta() -> None:
    snapshot = PeriodicMetricSnapshotV2(
        spec=_spec(
            metric_name="gmv",
            kind=PeriodicMetricDisplayKindV2.MONEY,
        ),
        status=PeriodicMetricStatusV2.READY,
        message="ready",
        reference_value=Decimal("100"),
        current_value=Decimal("80"),
        absolute_change=Decimal("-20"),
        relative_change=Decimal("-0.20"),
        current_evidence_id="ev-current",
        reference_evidence_id="ev-reference",
    )

    assert format_periodic_metric_value_v2(snapshot) == "80.00"
    assert (
        format_periodic_metric_delta_v2(snapshot)
        == "-20.00% vs 参考期"
    )


def test_not_ready_is_not_rendered_as_zero() -> None:
    snapshot = PeriodicMetricSnapshotV2(
        spec=_spec(
            metric_name="refund_rate",
            kind=PeriodicMetricDisplayKindV2.RATIO,
        ),
        status=PeriodicMetricStatusV2.NOT_READY,
        message="result protection blocked",
    )

    assert format_periodic_metric_value_v2(snapshot) == "不可释放"
    assert format_periodic_metric_delta_v2(snapshot) is None


def test_comparison_rows_preserve_not_ready_boundary() -> None:
    ready = PeriodicMetricSnapshotV2(
        spec=_spec(
            metric_name="buyer_count",
            kind=PeriodicMetricDisplayKindV2.COUNT,
        ),
        status=PeriodicMetricStatusV2.READY,
        message="ready",
        reference_value=Decimal("100"),
        current_value=Decimal("80"),
        absolute_change=Decimal("-20"),
        relative_change=Decimal("-0.20"),
        current_evidence_id="ev-current",
        reference_evidence_id="ev-reference",
    )
    blocked = PeriodicMetricSnapshotV2(
        spec=_spec(
            metric_name="refund_rate",
            kind=PeriodicMetricDisplayKindV2.RATIO,
        ),
        status=PeriodicMetricStatusV2.NOT_READY,
        message="blocked",
    )

    rows = build_periodic_metric_comparison_rows_v2(
        (ready, blocked)
    )

    assert rows[0]["当前期"] == "80"
    assert rows[0]["变化"] == "-20.00%"
    assert rows[1]["当前期"] == "不可释放"
    assert rows[1]["变化"] == "不可释放"


TESTS = (
    test_ratio_uses_percentage_points,
    test_money_uses_relative_change_for_card_delta,
    test_not_ready_is_not_rendered_as_zero,
    test_comparison_rows_preserve_not_ready_boundary,
)


def run_acceptance() -> None:
    passed = 0
    failed = 0

    print("=" * 80)
    print("Day93 Periodic Business Report UI Acceptance")
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

    print("=" * 80)
    print("Day93 Periodic Business Report UI Acceptance Summary")
    print(f"Total: {len(TESTS)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    run_acceptance()
