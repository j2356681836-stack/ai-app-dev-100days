from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from app.delivery.decision_console_entry_v2 import (
    PeriodicReportCadenceV2,
)
from app.delivery.decision_console_runtime_v2 import (
    build_monthly_mom_comparison_v2,
)
from app.delivery.periodic_business_report_v2 import (
    PERIODIC_METRIC_REGISTRY_V2,
    PERIODIC_R12_METRIC_SPECS_V2,
    PeriodicBusinessReportStatusV2,
    PeriodicMetricDisplayKindV2,
    PeriodicMetricSnapshotV2,
    PeriodicMetricStatusV2,
    PeriodicR12CustomerHealthV2,
    assemble_periodic_business_report_v2,
    project_r12_customer_health_v2,
    validate_periodic_metric_registry_v2,
)
from app.delivery.r12_cohort_runtime_v2 import (
    R12CohortPeriodicRuntimeV2,
    R12CohortRuntimeStatusV2,
    R12MetricRuntimeSnapshotV2,
    R12MetricRuntimeStatusV2,
    R12ReconciliationStatusV2,
    R12ReconciliationV2,
    R12RuntimeReadinessStatusV2,
    R12RuntimeReadinessV2,
)
from app.semantic_layer.time_comparison_contract_v2 import (
    TimeWindowReferenceV2,
)


ANCHOR = date(2025, 7, 31)


def _readiness(
    *,
    report: TimeWindowReferenceV2,
    base: TimeWindowReferenceV2,
    status: R12RuntimeReadinessStatusV2 = (
        R12RuntimeReadinessStatusV2.READY
    ),
) -> R12RuntimeReadinessV2:
    return R12RuntimeReadinessV2(
        status=status,
        ready=(status == R12RuntimeReadinessStatusV2.READY),
        message=f"readiness={status.value}",
        report_window=report,
        base_window=base,
        dataset_business_start_date=date(2024, 1, 1),
        dataset_business_end_date=date(2025, 12, 31),
        event_observation_end_date=date(2026, 1, 31),
        maximum_observation_delay_seconds=100,
        latest_required_observation_ts=datetime(2025, 8, 1),
        available_observation_end_ts=datetime(2026, 1, 31),
    )


def _ready_r12_runtime() -> R12CohortPeriodicRuntimeV2:
    comparison = build_monthly_mom_comparison_v2(
        anchor_date=ANCHOR
    )

    current_readiness = _readiness(
        report=comparison.current_window,
        base=TimeWindowReferenceV2(
            start_date=date(2024, 7, 1),
            end_date=date(2025, 6, 30),
        ),
    )
    reference_readiness = _readiness(
        report=comparison.reference_window,
        base=TimeWindowReferenceV2(
            start_date=date(2024, 6, 1),
            end_date=date(2025, 5, 31),
        ),
    )

    values = {
        "r12_base_customer_count": (
            Decimal("3425"),
            Decimal("3292"),
        ),
        "r12_repurchase_customer_count": (
            Decimal("899"),
            Decimal("1392"),
        ),
        "r12_repurchase_rate": (
            Decimal("0.26248175182481751825"),
            Decimal("0.42284325637910085055"),
        ),
        "r12_repurchase_amount": (
            Decimal("598560.86"),
            Decimal("1054570.44"),
        ),
        "r12_repurchase_spending": (
            Decimal("665.8074082313681869"),
            Decimal("757.5937068965517241"),
        ),
    }

    metrics = []
    for name, (current, reference) in values.items():
        absolute = current - reference
        relative = (
            absolute / reference
            if reference != 0
            else None
        )

        metrics.append(
            R12MetricRuntimeSnapshotV2(
                metric_name=name,
                status=R12MetricRuntimeStatusV2.READY,
                message="trusted",
                current_value=current,
                reference_value=reference,
                absolute_change=absolute,
                relative_change=relative,
                current_evidence_id=f"ev-current-{name}",
                reference_evidence_id=f"ev-reference-{name}",
            )
        )

    reconciliations = tuple(
        R12ReconciliationV2(
            relationship=f"relationship-{index}",
            status=R12ReconciliationStatusV2.RECONCILED,
            remainder=Decimal("0"),
            message="reconciled",
        )
        for index in range(6)
    )

    return R12CohortPeriodicRuntimeV2(
        status=R12CohortRuntimeStatusV2.READY,
        message="5/5 READY",
        cadence=PeriodicReportCadenceV2.MONTHLY,
        anchor_date=ANCHOR,
        comparison=comparison,
        current_readiness=current_readiness,
        reference_readiness=reference_readiness,
        metrics=tuple(metrics),
        reconciliations=reconciliations,
    )


def _not_ready_r12_runtime() -> R12CohortPeriodicRuntimeV2:
    comparison = build_monthly_mom_comparison_v2(
        anchor_date=date(2024, 12, 31)
    )

    current = _readiness(
        report=comparison.current_window,
        base=TimeWindowReferenceV2(
            start_date=date(2023, 12, 1),
            end_date=date(2024, 11, 30),
        ),
        status=(
            R12RuntimeReadinessStatusV2.INSUFFICIENT_HISTORY
        ),
    )
    reference = _readiness(
        report=comparison.reference_window,
        base=TimeWindowReferenceV2(
            start_date=date(2023, 11, 1),
            end_date=date(2024, 10, 31),
        ),
        status=(
            R12RuntimeReadinessStatusV2.INSUFFICIENT_HISTORY
        ),
    )

    return R12CohortPeriodicRuntimeV2(
        status=R12CohortRuntimeStatusV2.NOT_READY,
        message="preflight blocked",
        cadence=PeriodicReportCadenceV2.MONTHLY,
        anchor_date=date(2024, 12, 31),
        comparison=comparison,
        current_readiness=current,
        reference_readiness=reference,
    )


def _ready_base_metric(
    spec,
    value: Decimal,
) -> PeriodicMetricSnapshotV2:
    return PeriodicMetricSnapshotV2(
        spec=spec,
        status=PeriodicMetricStatusV2.READY,
        message="ready",
        current_value=value,
        reference_value=value,
        absolute_change=Decimal("0"),
        relative_change=Decimal("0"),
        percentage_point_change=(
            Decimal("0")
            if spec.display_kind
            == PeriodicMetricDisplayKindV2.RATIO
            else None
        ),
        current_evidence_id=f"ev-current-{spec.metric_name}",
        reference_evidence_id=f"ev-reference-{spec.metric_name}",
    )


def test_combined_registry_is_valid_and_unique() -> None:
    validate_periodic_metric_registry_v2()

    base_names = {
        spec.metric_name
        for spec in PERIODIC_METRIC_REGISTRY_V2
    }
    r12_names = {
        spec.metric_name
        for spec in PERIODIC_R12_METRIC_SPECS_V2
    }

    assert len(PERIODIC_METRIC_REGISTRY_V2) == 11
    assert len(PERIODIC_R12_METRIC_SPECS_V2) == 5
    assert not (base_names & r12_names)


def test_ready_r12_projects_five_periodic_metrics() -> None:
    runtime = _ready_r12_runtime()

    metrics, trust = project_r12_customer_health_v2(
        r12_runtime=runtime,
        cadence=runtime.cadence,
        anchor_date=runtime.anchor_date,
        comparison=runtime.comparison,
    )

    assert len(metrics) == 5
    assert all(
        item.status == PeriodicMetricStatusV2.READY
        for item in metrics
    )
    assert trust.status == R12CohortRuntimeStatusV2.READY
    assert trust.ready_metric_count == 5
    assert trust.failed_metric_count == 0
    assert len(trust.reconciliations) == 6

    rate = {
        item.spec.metric_name: item
        for item in metrics
    }["r12_repurchase_rate"]

    assert rate.percentage_point_change is not None
    assert rate.current_value == Decimal(
        "0.26248175182481751825"
    )


def test_preflight_not_ready_projects_five_explicit_slots() -> None:
    runtime = _not_ready_r12_runtime()

    metrics, trust = project_r12_customer_health_v2(
        r12_runtime=runtime,
        cadence=runtime.cadence,
        anchor_date=runtime.anchor_date,
        comparison=runtime.comparison,
    )

    assert len(metrics) == 5
    assert all(
        item.status == PeriodicMetricStatusV2.NOT_READY
        for item in metrics
    )
    assert all(
        "insufficient_history" in item.message
        for item in metrics
    )
    assert trust.status == R12CohortRuntimeStatusV2.NOT_READY
    assert trust.ready_metric_count == 0
    assert trust.failed_metric_count == 5


def test_r12_projection_rejects_time_contract_mismatch() -> None:
    runtime = _ready_r12_runtime()
    wrong = build_monthly_mom_comparison_v2(
        anchor_date=date(2025, 8, 31)
    )

    try:
        project_r12_customer_health_v2(
            r12_runtime=runtime,
            cadence=runtime.cadence,
            anchor_date=runtime.anchor_date,
            comparison=wrong,
        )
    except ValueError:
        pass
    else:
        raise AssertionError(
            "R12 projection 必须拒绝 TimeComparisonContract mismatch。"
        )


def test_r12_unavailable_makes_optional_report_partial_not_blocked() -> None:
    runtime = _not_ready_r12_runtime()
    r12_metrics, trust = project_r12_customer_health_v2(
        r12_runtime=runtime,
        cadence=runtime.cadence,
        anchor_date=runtime.anchor_date,
        comparison=runtime.comparison,
    )

    base_metrics = tuple(
        _ready_base_metric(
            spec,
            Decimal("100"),
        )
        for spec in PERIODIC_METRIC_REGISTRY_V2
    )

    report = assemble_periodic_business_report_v2(
        cadence=runtime.cadence,
        anchor_date=runtime.anchor_date,
        comparison=runtime.comparison,
        metrics=(
            *base_metrics,
            *r12_metrics,
        ),
        r12_customer_health=trust,
    )

    assert report.status == PeriodicBusinessReportStatusV2.PARTIAL_READY
    assert report.ready_metric_count == 11
    assert report.failed_metric_count == 5
    assert not report.required_failed_metric_names


def test_window_repeat_and_r12_repurchase_rate_remain_distinct() -> None:
    names = {
        spec.metric_name
        for spec in (
            *PERIODIC_METRIC_REGISTRY_V2,
            *PERIODIC_R12_METRIC_SPECS_V2,
        )
    }

    assert "repeat_customer_rate" in names
    assert "r12_repurchase_rate" in names
    assert "repeat_customer_rate" != "r12_repurchase_rate"


def test_existing_assembler_can_still_operate_without_r12_projection() -> None:
    comparison = build_monthly_mom_comparison_v2(
        anchor_date=ANCHOR
    )
    base_metrics = tuple(
        _ready_base_metric(
            spec,
            Decimal("100"),
        )
        for spec in PERIODIC_METRIC_REGISTRY_V2
    )

    report = assemble_periodic_business_report_v2(
        cadence=PeriodicReportCadenceV2.MONTHLY,
        anchor_date=ANCHOR,
        comparison=comparison,
        metrics=base_metrics,
    )

    assert report.status == PeriodicBusinessReportStatusV2.READY
    assert report.r12_customer_health is None


TESTS = (
    test_combined_registry_is_valid_and_unique,
    test_ready_r12_projects_five_periodic_metrics,
    test_preflight_not_ready_projects_five_explicit_slots,
    test_r12_projection_rejects_time_contract_mismatch,
    test_r12_unavailable_makes_optional_report_partial_not_blocked,
    test_window_repeat_and_r12_repurchase_rate_remain_distinct,
    test_existing_assembler_can_still_operate_without_r12_projection,
)


def run_acceptance() -> None:
    passed = 0
    failed = 0

    print("=" * 88)
    print("Day93 B5B-3A Periodic Business Report R12 Integration Acceptance")
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
