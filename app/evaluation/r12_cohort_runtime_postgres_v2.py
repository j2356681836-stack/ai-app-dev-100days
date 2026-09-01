from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.delivery.decision_console_entry_v2 import (
    PeriodicReportCadenceV2,
)
from app.delivery.r12_cohort_runtime_v2 import (
    R12CohortRuntimeStatusV2,
    R12MetricRuntimeStatusV2,
    R12ReconciliationStatusV2,
    build_r12_runtime_readiness_v2,
    run_r12_cohort_periodic_runtime_v2,
)
from app.db.beauty_bi_v2.manifest_loader import (
    load_and_validate_day66_manifest,
)
from app.semantic_layer.time_comparison_contract_v2 import (
    TimeWindowReferenceV2,
)


def _fmt(value: Decimal | None) -> str:
    return "None" if value is None else str(value)


def main() -> None:
    manifest = load_and_validate_day66_manifest()

    print("=" * 96)
    print("Day93 B5B-2 R12 Cohort PostgreSQL Truth Test")

    # Boundary 1: historical insufficiency must fail closed before SQL.
    old_readiness = build_r12_runtime_readiness_v2(
        report_window=TimeWindowReferenceV2(
            start_date=date(2024, 12, 1),
            end_date=date(2024, 12, 31),
        ),
        manifest=manifest,
    )
    print(
        "2024-12 readiness:",
        old_readiness.status.value,
        old_readiness.base_window.start_date,
        "->",
        old_readiness.base_window.end_date,
    )
    assert not old_readiness.ready

    # Boundary 2: late-2025 refund observation tail.
    late_readiness = build_r12_runtime_readiness_v2(
        report_window=TimeWindowReferenceV2(
            start_date=date(2025, 12, 1),
            end_date=date(2025, 12, 31),
        ),
        manifest=manifest,
    )
    print(
        "2025-12 readiness:",
        late_readiness.status.value,
        "required_observation=",
        late_readiness.latest_required_observation_ts,
        "available=",
        late_readiness.available_observation_end_ts,
    )
    assert not late_readiness.ready

    # Main Truth Test: Monthly 2025-07-31.
    result = run_r12_cohort_periodic_runtime_v2(
        cadence=PeriodicReportCadenceV2.MONTHLY,
        anchor_date=date(2025, 7, 31),
        manifest=manifest,
    )

    print("-" * 96)
    print("Runtime status:", result.status.value)
    print("Current window:", result.comparison.current_window)
    print("Current base:", result.current_readiness.base_window)
    print("Reference window:", result.comparison.reference_window)
    print("Reference base:", result.reference_readiness.base_window)
    print(
        "Current readiness:",
        result.current_readiness.status.value,
    )
    print(
        "Reference readiness:",
        result.reference_readiness.status.value,
    )

    assert result.current_readiness.ready
    assert result.reference_readiness.ready

    # Current / Reference 必须使用不同 Base。
    assert (
        result.current_readiness.base_window
        != result.reference_readiness.base_window
    )

    ready_count = 0

    for metric in result.metrics:
        print(
            f"{metric.metric_name}: "
            f"status={metric.status.value}; "
            f"current={_fmt(metric.current_value)}; "
            f"reference={_fmt(metric.reference_value)}; "
            f"message={metric.message}"
        )

        if metric.status == R12MetricRuntimeStatusV2.READY:
            ready_count += 1

    print("Ready metrics:", f"{ready_count}/5")

    for item in result.reconciliations:
        print(
            f"reconcile: {item.relationship}; "
            f"status={item.status.value}; "
            f"remainder={_fmt(item.remainder)}"
        )

    if result.status == R12CohortRuntimeStatusV2.READY:
        assert ready_count == 5
        assert all(
            item.status
            in {
                R12ReconciliationStatusV2.RECONCILED,
                R12ReconciliationStatusV2.NOT_AVAILABLE,
            }
            for item in result.reconciliations
        )

        failed_reconciliation = [
            item
            for item in result.reconciliations
            if (
                item.status
                == R12ReconciliationStatusV2.NOT_RECONCILED
            )
        ]

        assert not failed_reconciliation, (
            "R12 deterministic reconciliation failed: "
            f"{failed_reconciliation}"
        )

    print("=" * 96)
    print("PostgreSQL Truth Test completed.")


if __name__ == "__main__":
    main()
