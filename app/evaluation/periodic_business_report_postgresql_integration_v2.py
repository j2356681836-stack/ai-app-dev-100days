from __future__ import annotations

from datetime import date
from time import perf_counter

from app.delivery.decision_console_entry_v2 import (
    PeriodicReportCadenceV2,
)
from app.delivery.periodic_business_report_v2 import (
    PeriodicBusinessReportStatusV2,
    PeriodicDriverReconciliationStatusV2,
    PeriodicMetricStatusV2,
    run_day93_periodic_business_report_v2,
)


ANCHOR_DATE = date(2025, 7, 31)


def _format_value(value) -> str:
    if value is None:
        return "-"
    return str(value)


def run_integration() -> None:
    print("=" * 100)
    print("Day93 Periodic Business Report V2 PostgreSQL Integration")
    print(f"Cadence: monthly")
    print(f"Anchor: {ANCHOR_DATE.isoformat()}")
    print("Expected governed query count: up to 22")
    print("=" * 100)

    started = perf_counter()

    report = run_day93_periodic_business_report_v2(
        cadence=PeriodicReportCadenceV2.MONTHLY,
        anchor_date=ANCHOR_DATE,
    )

    elapsed = perf_counter() - started

    print()
    print("REPORT")
    print(f"status={report.status.value}")
    print(f"message={report.message}")
    print(
        "current_window="
        f"{report.comparison.current_window.start_date}"
        " -> "
        f"{report.comparison.current_window.end_date}"
    )
    print(
        "reference_window="
        f"{report.comparison.reference_window.start_date}"
        " -> "
        f"{report.comparison.reference_window.end_date}"
    )
    print(
        f"ready_metrics={report.ready_metric_count}; "
        f"failed_metrics={report.failed_metric_count}"
    )
    print(
        "required_failed="
        f"{list(report.required_failed_metric_names)}"
    )
    print(f"elapsed_seconds={elapsed:.3f}")

    print()
    print("METRICS")
    for item in report.metrics:
        print("-" * 100)
        print(
            f"{item.spec.metric_name} | "
            f"{item.spec.chinese_name} | "
            f"section={item.spec.section.value} | "
            f"status={item.status.value}"
        )

        if item.status == PeriodicMetricStatusV2.READY:
            print(
                "reference="
                f"{_format_value(item.reference_value)}; "
                "current="
                f"{_format_value(item.current_value)}"
            )
            print(
                "delta="
                f"{_format_value(item.absolute_change)}; "
                "relative_change="
                f"{_format_value(item.relative_change)}"
            )

            if item.percentage_point_change is not None:
                print(
                    "percentage_point_change="
                    f"{item.percentage_point_change}"
                )

            print(
                "evidence_ids="
                f"{item.reference_evidence_id} -> "
                f"{item.current_evidence_id}"
            )
        else:
            print(f"message={item.message}")

    print()
    print("DRIVER RECONCILIATION")
    for item in report.driver_reconciliations:
        print("-" * 100)
        print(
            f"{item.relationship} | "
            f"status={item.status.value}"
        )

        if (
            item.status
            != PeriodicDriverReconciliationStatusV2.NOT_AVAILABLE
        ):
            print(
                "observed="
                f"{_format_value(item.observed_value)}; "
                "reconstructed="
                f"{_format_value(item.reconstructed_value)}; "
                "remainder="
                f"{_format_value(item.remainder)}"
            )

        print(f"message={item.message}")

    print("=" * 100)

    # Integration Gate:
    # 核心指标失败时直接失败；
    # 可选指标失败允许 PARTIAL_READY，交给下一步评估原因。
    if report.status == PeriodicBusinessReportStatusV2.NOT_READY:
        raise SystemExit(1)

    if report.ready_metric_count < 3:
        raise SystemExit(
            "Integration failed: fewer than 3 metrics are READY."
        )

    print(
        "Integration gate passed: core Periodic Business Report "
        "formed a safe deliverable."
    )


if __name__ == "__main__":
    run_integration()
