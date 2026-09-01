from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.agents.metric_comparison_v2 import (
    compare_metric_values_v2,
)
from app.delivery.decision_console_entry_v2 import (
    PeriodicReportCadenceV2,
)
from app.delivery.decision_console_runtime_v2 import (
    build_monthly_mom_comparison_v2,
)
from app.delivery.periodic_business_report_v2 import (
    PERIODIC_METRIC_REGISTRY_V2,
    PeriodicBusinessReportStatusV2,
    PeriodicDriverReconciliationStatusV2,
    PeriodicMetricDisplayKindV2,
    PeriodicMetricSnapshotV2,
    PeriodicMetricStatusV2,
    assemble_periodic_business_report_v2,
    build_driver_reconciliations_v2,
    project_metric_comparison_v2,
    validate_periodic_metric_registry_v2,
)


ANCHOR = date(2025, 7, 31)
COMPARISON = build_monthly_mom_comparison_v2(
    anchor_date=ANCHOR
)


def _spec(metric_name: str):
    return next(
        item
        for item in PERIODIC_METRIC_REGISTRY_V2
        if item.metric_name == metric_name
    )


def _ready(
    metric_name: str,
    current: str,
    reference: str,
) -> PeriodicMetricSnapshotV2:
    comparison = compare_metric_values_v2(
        metric_name=metric_name,
        comparison=COMPARISON,
        current_evidence_id=f"ev_current_{metric_name}",
        reference_evidence_id=f"ev_reference_{metric_name}",
        current_value=Decimal(current),
        reference_value=Decimal(reference),
    )

    return project_metric_comparison_v2(
        spec=_spec(metric_name),
        comparison_result=comparison,
    )


def _failed(metric_name: str) -> PeriodicMetricSnapshotV2:
    return PeriodicMetricSnapshotV2(
        spec=_spec(metric_name),
        status=PeriodicMetricStatusV2.NOT_READY,
        message="test failure",
    )


def test_registry_matches_canonical_catalog() -> None:
    validate_periodic_metric_registry_v2()

    metric_names = tuple(
        item.metric_name
        for item in PERIODIC_METRIC_REGISTRY_V2
    )

    assert len(metric_names) == 11
    assert len(metric_names) == len(set(metric_names))

    expected = {
        "gmv",
        "buyer_count",
        "spending_per_buyer",
        "refund_rate",
        "order_count",
        "units_sold",
        "aus",
        "purchase_frequency",
        "ipt",
        "repeat_customer_rate",
        "member_gmv_share",
    }

    assert set(metric_names) == expected


def test_ratio_uses_percentage_point_change() -> None:
    snapshot = _ready(
        "refund_rate",
        "0.12",
        "0.10",
    )

    assert snapshot.status == PeriodicMetricStatusV2.READY
    assert (
        snapshot.spec.display_kind
        == PeriodicMetricDisplayKindV2.RATIO
    )
    assert snapshot.absolute_change == Decimal("0.02")
    assert snapshot.relative_change == Decimal("0.2")
    assert snapshot.percentage_point_change == Decimal("2.00")


def test_reference_zero_keeps_relative_change_undefined() -> None:
    snapshot = _ready(
        "member_gmv_share",
        "0.30",
        "0",
    )

    assert snapshot.relative_change is None
    assert snapshot.percentage_point_change == Decimal("30.00")


def test_optional_failure_produces_partial_ready() -> None:
    metrics = tuple(
        (
            _failed(spec.metric_name)
            if spec.metric_name == "refund_rate"
            else _ready(
                spec.metric_name,
                "10",
                "9",
            )
        )
        for spec in PERIODIC_METRIC_REGISTRY_V2
    )

    report = assemble_periodic_business_report_v2(
        cadence=PeriodicReportCadenceV2.MONTHLY,
        anchor_date=ANCHOR,
        comparison=COMPARISON,
        metrics=metrics,
    )

    assert (
        report.status
        == PeriodicBusinessReportStatusV2.PARTIAL_READY
    )
    assert report.required_failed_metric_names == ()
    assert report.failed_metric_count == 1


def test_required_failure_produces_not_ready() -> None:
    metrics = tuple(
        (
            _failed(spec.metric_name)
            if spec.metric_name == "gmv"
            else _ready(
                spec.metric_name,
                "10",
                "9",
            )
        )
        for spec in PERIODIC_METRIC_REGISTRY_V2
    )

    report = assemble_periodic_business_report_v2(
        cadence=PeriodicReportCadenceV2.MONTHLY,
        anchor_date=ANCHOR,
        comparison=COMPARISON,
        metrics=metrics,
    )

    assert report.status == PeriodicBusinessReportStatusV2.NOT_READY
    assert report.required_failed_metric_names == ("gmv",)


def test_all_ready_produces_ready() -> None:
    metrics = tuple(
        _ready(
            spec.metric_name,
            "10",
            "9",
        )
        for spec in PERIODIC_METRIC_REGISTRY_V2
    )

    report = assemble_periodic_business_report_v2(
        cadence=PeriodicReportCadenceV2.MONTHLY,
        anchor_date=ANCHOR,
        comparison=COMPARISON,
        metrics=metrics,
    )

    assert report.status == PeriodicBusinessReportStatusV2.READY
    assert report.ready_metric_count == 11
    assert report.failed_metric_count == 0


def test_driver_tree_reconciles() -> None:
    metrics = (
        _ready("gmv", "1000", "900"),
        _ready("buyer_count", "10", "9"),
        _ready("spending_per_buyer", "100", "100"),
        _ready("aus", "50", "45"),
        _ready("purchase_frequency", "2", "2.2222222222"),
    )

    reconciliations = build_driver_reconciliations_v2(
        metrics
    )

    assert len(reconciliations) == 2

    gmv_relation = reconciliations[0]
    spending_relation = reconciliations[1]

    assert (
        gmv_relation.status
        == PeriodicDriverReconciliationStatusV2.RECONCILED
    )
    assert gmv_relation.remainder == Decimal("0")

    assert (
        spending_relation.status
        == PeriodicDriverReconciliationStatusV2.RECONCILED
    )
    assert spending_relation.remainder == Decimal("0")


def test_missing_driver_metric_is_explicit_not_available() -> None:
    metrics = (
        _ready("gmv", "1000", "900"),
        _ready("buyer_count", "10", "9"),
        _ready("spending_per_buyer", "100", "100"),
    )

    reconciliations = build_driver_reconciliations_v2(
        metrics
    )

    assert (
        reconciliations[0].status
        == PeriodicDriverReconciliationStatusV2.RECONCILED
    )
    assert (
        reconciliations[1].status
        == PeriodicDriverReconciliationStatusV2.NOT_AVAILABLE
    )


TESTS = (
    test_registry_matches_canonical_catalog,
    test_ratio_uses_percentage_point_change,
    test_reference_zero_keeps_relative_change_undefined,
    test_optional_failure_produces_partial_ready,
    test_required_failure_produces_not_ready,
    test_all_ready_produces_ready,
    test_driver_tree_reconciles,
    test_missing_driver_metric_is_explicit_not_available,
)


def run_acceptance() -> None:
    passed = 0
    failed = 0

    print("=" * 80)
    print("Day93 Periodic Business Report V2 Acceptance")
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
    print("Day93 Periodic Business Report V2 Acceptance Summary")
    print(f"Total: {len(TESTS)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    run_acceptance()
