from __future__ import annotations

from datetime import date

from app.delivery.decision_console_entry_v2 import (
    PeriodicReportCadenceV2,
)
from app.delivery.periodic_business_report_v2 import (
    PeriodicBusinessReportStatusV2,
    PeriodicMetricStatusV2,
    run_day93_periodic_business_report_v2,
)
from app.delivery.r12_cohort_runtime_v2 import (
    R12CohortRuntimeStatusV2,
    R12ReconciliationStatusV2,
)


def main() -> None:
    print("=" * 100)
    print("Day93 B5B-3A Periodic Business Report + R12 PostgreSQL Integration")

    report = run_day93_periodic_business_report_v2(
        cadence=PeriodicReportCadenceV2.MONTHLY,
        anchor_date=date(2025, 7, 31),
    )

    print("Report version:", report.contract_version)
    print("Report status:", report.status.value)
    print("Ready metrics:", report.ready_metric_count)
    print("Failed metrics:", report.failed_metric_count)
    print(
        "Required failed:",
        report.required_failed_metric_names,
    )

    assert report.status != PeriodicBusinessReportStatusV2.NOT_READY
    assert not report.required_failed_metric_names
    assert len(report.metrics) == 16
    assert report.r12_customer_health is not None

    r12 = report.r12_customer_health

    print("-" * 100)
    print("R12 status:", r12.status.value)
    print(
        "R12 current readiness:",
        r12.current_readiness.status.value,
        r12.current_readiness.base_window,
    )
    print(
        "R12 reference readiness:",
        r12.reference_readiness.status.value,
        r12.reference_readiness.base_window,
    )
    print(
        "R12 metric readiness:",
        f"{r12.ready_metric_count}/5",
    )

    assert r12.status == R12CohortRuntimeStatusV2.READY
    assert r12.ready_metric_count == 5
    assert r12.failed_metric_count == 0

    r12_names = {
        "r12_base_customer_count",
        "r12_repurchase_customer_count",
        "r12_repurchase_rate",
        "r12_repurchase_amount",
        "r12_repurchase_spending",
    }

    r12_metrics = {
        item.spec.metric_name: item
        for item in report.metrics
        if item.spec.metric_name in r12_names
    }

    assert set(r12_metrics) == r12_names

    for name in (
        "r12_base_customer_count",
        "r12_repurchase_customer_count",
        "r12_repurchase_rate",
        "r12_repurchase_amount",
        "r12_repurchase_spending",
    ):
        item = r12_metrics[name]
        print(
            f"{name}: status={item.status.value}; "
            f"current={item.current_value}; "
            f"reference={item.reference_value}; "
            f"absolute_change={item.absolute_change}; "
            f"relative_change={item.relative_change}"
        )
        assert item.status == PeriodicMetricStatusV2.READY

    print("-" * 100)
    for item in r12.reconciliations:
        print(
            f"R12 reconcile: {item.relationship}; "
            f"status={item.status.value}; "
            f"remainder={item.remainder}"
        )

    assert len(r12.reconciliations) == 6
    assert not [
        item
        for item in r12.reconciliations
        if item.status == R12ReconciliationStatusV2.NOT_RECONCILED
    ]

    metric_names = {
        item.spec.metric_name
        for item in report.metrics
    }
    assert "repeat_customer_rate" in metric_names
    assert "r12_repurchase_rate" in metric_names

    print("=" * 100)
    print("B5B-3A PostgreSQL Integration completed.")


if __name__ == "__main__":
    main()
