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
    format_periodic_metric_delta_inline_v2,
    format_periodic_metric_value_v2,
    periodic_metric_delta_direction_v2,
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
        purpose="ui acceptance",
    )


def test_money_card_has_current_reference_and_compact_delta() -> None:
    snapshot = PeriodicMetricSnapshotV2(
        spec=_spec(
            metric_name="gmv",
            kind=PeriodicMetricDisplayKindV2.MONEY,
        ),
        status=PeriodicMetricStatusV2.READY,
        message="ready",
        reference_value=Decimal("1257216.31"),
        current_value=Decimal("719931.12"),
        absolute_change=Decimal("-537285.19"),
        relative_change=Decimal("-0.4273609765"),
        current_evidence_id="current",
        reference_evidence_id="reference",
    )

    assert format_periodic_metric_value_v2(snapshot) == "719,931.12"
    assert (
        format_periodic_metric_value_v2(
            snapshot,
            reference=True,
        )
        == "1,257,216.31"
    )
    assert (
        format_periodic_metric_delta_inline_v2(snapshot)
        == "↓ 42.74%"
    )
    assert periodic_metric_delta_direction_v2(snapshot) == "down"


def test_ratio_card_uses_pp_and_reference_value() -> None:
    snapshot = PeriodicMetricSnapshotV2(
        spec=_spec(
            metric_name="repeat_customer_rate",
            kind=PeriodicMetricDisplayKindV2.RATIO,
        ),
        status=PeriodicMetricStatusV2.READY,
        message="ready",
        reference_value=Decimal("0.354719309"),
        current_value=Decimal("0.246865959"),
        absolute_change=Decimal("-0.10785335"),
        relative_change=Decimal("-0.30405266"),
        percentage_point_change=Decimal("-10.785335"),
        current_evidence_id="current",
        reference_evidence_id="reference",
    )

    assert format_periodic_metric_value_v2(snapshot) == "24.69%"
    assert (
        format_periodic_metric_value_v2(
            snapshot,
            reference=True,
        )
        == "35.47%"
    )
    assert (
        format_periodic_metric_delta_inline_v2(snapshot)
        == "↓ 10.79 pp"
    )


def test_positive_delta_only_means_mathematical_up() -> None:
    snapshot = PeriodicMetricSnapshotV2(
        spec=_spec(
            metric_name="member_gmv_share",
            kind=PeriodicMetricDisplayKindV2.RATIO,
        ),
        status=PeriodicMetricStatusV2.READY,
        message="ready",
        reference_value=Decimal("0.47"),
        current_value=Decimal("0.53"),
        absolute_change=Decimal("0.06"),
        relative_change=Decimal("0.13"),
        percentage_point_change=Decimal("6.31"),
        current_evidence_id="current",
        reference_evidence_id="reference",
    )

    assert (
        format_periodic_metric_delta_inline_v2(snapshot)
        == "↑ 6.31 pp"
    )
    assert periodic_metric_delta_direction_v2(snapshot) == "up"


def test_not_ready_never_invents_reference_value() -> None:
    snapshot = PeriodicMetricSnapshotV2(
        spec=_spec(
            metric_name="refund_rate",
            kind=PeriodicMetricDisplayKindV2.RATIO,
        ),
        status=PeriodicMetricStatusV2.NOT_READY,
        message="result protection blocked",
    )

    assert format_periodic_metric_value_v2(snapshot) == "不可释放"
    assert (
        format_periodic_metric_value_v2(
            snapshot,
            reference=True,
        )
        == "不可释放"
    )
    assert format_periodic_metric_delta_inline_v2(snapshot) is None
    assert (
        periodic_metric_delta_direction_v2(snapshot)
        == "unavailable"
    )


TESTS = (
    test_money_card_has_current_reference_and_compact_delta,
    test_ratio_card_uses_pp_and_reference_value,
    test_positive_delta_only_means_mathematical_up,
    test_not_ready_never_invents_reference_value,
)


def run_acceptance() -> None:
    passed = 0
    failed = 0

    print("=" * 80)
    print("Day93 Periodic KPI Card UI Acceptance")
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
    print("Day93 Periodic KPI Card UI Acceptance Summary")
    print(f"Total: {len(TESTS)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    run_acceptance()
