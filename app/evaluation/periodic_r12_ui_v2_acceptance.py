from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from app.delivery.decision_console_entry_v2 import (
    PeriodicReportCadenceV2,
)
from app.delivery.decision_console_runtime_v2 import (
    build_monthly_mom_comparison_v2,
)
from app.delivery.periodic_business_report_v2 import (
    PERIODIC_METRIC_REGISTRY_V2,
    PERIODIC_R12_METRIC_SPECS_V2,
    PeriodicMetricDisplayKindV2,
    PeriodicMetricSnapshotV2,
    PeriodicMetricStatusV2,
    PeriodicR12CustomerHealthV2,
    assemble_periodic_business_report_v2,
)
from app.delivery.r12_cohort_runtime_v2 import (
    R12CohortRuntimeStatusV2,
    R12ReconciliationStatusV2,
    R12ReconciliationV2,
    R12RuntimeReadinessStatusV2,
    R12RuntimeReadinessV2,
)
from app.semantic_layer.time_comparison_contract_v2 import (
    TimeWindowReferenceV2,
)
from app.ui.decision_console_presenters_v2 import (
    R12_PERIODIC_METRIC_NAMES_V2,
    build_periodic_r12_readiness_rows_v2,
    build_periodic_r12_reconciliation_rows_v2,
    format_periodic_r12_readiness_status_v2,
    format_periodic_r12_runtime_status_v2,
)


ANCHOR = date(2025, 7, 31)


def _readiness(
    *,
    report,
    base,
    status=R12RuntimeReadinessStatusV2.READY,
):
    return R12RuntimeReadinessV2(
        status=status,
        ready=(status == R12RuntimeReadinessStatusV2.READY),
        message=status.value,
        report_window=report,
        base_window=base,
        dataset_business_start_date=date(2024, 1, 1),
        dataset_business_end_date=date(2025, 12, 31),
        event_observation_end_date=date(2026, 1, 31),
        maximum_observation_delay_seconds=100,
        latest_required_observation_ts=datetime(2025, 8, 1),
        available_observation_end_ts=datetime(2026, 1, 31),
    )


def _snapshot(spec, value=Decimal("100")):
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
        current_evidence_id=f"current-{spec.metric_name}",
        reference_evidence_id=f"reference-{spec.metric_name}",
    )


def _report():
    comparison = build_monthly_mom_comparison_v2(
        anchor_date=ANCHOR
    )

    current = _readiness(
        report=comparison.current_window,
        base=TimeWindowReferenceV2(
            start_date=date(2024, 7, 1),
            end_date=date(2025, 6, 30),
        ),
    )
    reference = _readiness(
        report=comparison.reference_window,
        base=TimeWindowReferenceV2(
            start_date=date(2024, 6, 1),
            end_date=date(2025, 5, 31),
        ),
    )

    reconciliations = tuple(
        R12ReconciliationV2(
            relationship=f"identity-{index}",
            status=R12ReconciliationStatusV2.RECONCILED,
            remainder=Decimal("0"),
            message="reconciled",
        )
        for index in range(6)
    )

    trust = PeriodicR12CustomerHealthV2(
        status=R12CohortRuntimeStatusV2.READY,
        message="ready",
        current_readiness=current,
        reference_readiness=reference,
        ready_metric_count=5,
        failed_metric_count=0,
        reconciliations=reconciliations,
    )

    metrics = tuple(
        _snapshot(spec)
        for spec in (
            *PERIODIC_METRIC_REGISTRY_V2,
            *PERIODIC_R12_METRIC_SPECS_V2,
        )
    )

    return assemble_periodic_business_report_v2(
        cadence=PeriodicReportCadenceV2.MONTHLY,
        anchor_date=ANCHOR,
        comparison=comparison,
        metrics=metrics,
        r12_customer_health=trust,
    )


def test_r12_metric_layout_contract_is_explicit() -> None:
    assert R12_PERIODIC_METRIC_NAMES_V2 == (
        "r12_base_customer_count",
        "r12_repurchase_customer_count",
        "r12_repurchase_rate",
        "r12_repurchase_amount",
        "r12_repurchase_spending",
    )


def test_readiness_rows_use_runtime_windows() -> None:
    report = _report()
    rows = build_periodic_r12_readiness_rows_v2(report)

    assert len(rows) == 2
    assert rows[0]["窗口"] == "当前期"
    assert rows[0]["R12 Base"] == "2024-07-01 → 2025-06-30"
    assert rows[1]["R12 Base"] == "2024-06-01 → 2025-05-31"


def test_reconciliation_rows_do_not_recalculate() -> None:
    report = _report()
    rows = build_periodic_r12_reconciliation_rows_v2(
        report
    )

    assert len(rows) == 6
    assert all(row["状态"] == "已对账" for row in rows)


def test_readiness_labels_are_business_readable() -> None:
    assert (
        format_periodic_r12_readiness_status_v2(
            "insufficient_history"
        )
        == "R12 历史不足"
    )
    assert (
        format_periodic_r12_readiness_status_v2(
            "refund_observation_incomplete"
        )
        == "退款观察窗口尚未完整"
    )
    assert (
        format_periodic_r12_runtime_status_v2("ready")
        == "5 个 R12 客户指标均已就绪"
    )


def test_ui_source_keeps_two_repeat_rate_definitions_distinct() -> None:
    app_path = (
        Path(__file__).resolve().parents[1]
        / "ui"
        / "decision_console_app.py"
    )
    source = app_path.read_text(encoding="utf-8")

    assert "#### 本期客户行为" in source
    assert "#### R12 客户留存" in source
    assert "它不是“窗口内跨日复购率”" in source


def test_ui_source_has_r12_trust_drawer() -> None:
    app_path = (
        Path(__file__).resolve().parents[1]
        / "ui"
        / "decision_console_app.py"
    )
    source = app_path.read_text(encoding="utf-8")

    assert "验证 R12 客户指标" in source
    assert "build_periodic_r12_readiness_rows_v2" in source
    assert "build_periodic_r12_reconciliation_rows_v2" in source


def test_ui_does_not_claim_all_partial_failures_are_governance() -> None:
    app_path = (
        Path(__file__).resolve().parents[1]
        / "ui"
        / "decision_console_app.py"
    )
    source = app_path.read_text(encoding="utf-8")

    assert "部分扩展指标当前不可交付" in source
    assert (
        "部分扩展指标因治理边界不可释放"
        not in source
    )


TESTS = (
    test_r12_metric_layout_contract_is_explicit,
    test_readiness_rows_use_runtime_windows,
    test_reconciliation_rows_do_not_recalculate,
    test_readiness_labels_are_business_readable,
    test_ui_source_keeps_two_repeat_rate_definitions_distinct,
    test_ui_source_has_r12_trust_drawer,
    test_ui_does_not_claim_all_partial_failures_are_governance,
)


def run_acceptance() -> None:
    passed = 0
    failed = 0

    print("=" * 88)
    print("Day93 B5B-3B Periodic R12 UI Acceptance")
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
