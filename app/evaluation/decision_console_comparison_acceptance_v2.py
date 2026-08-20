from __future__ import annotations

import inspect
from datetime import date
from decimal import Decimal

import app.delivery.decision_console_view_v2 as console_view_module
from app.agents.evidence_pack_delivery_v2 import (
    MetricDefinitionSnapshotV2,
    assemble_evidence_pack_delivery_v2,
)
from app.agents.evidence_pack_v2 import (
    EvidencePackV2,
    EvidenceRecordV2,
    EvidenceTypeV2,
    GovernedEvidenceProvenanceV2,
    ProtectedResultV2,
)
from app.agents.investigation_contracts_v2 import (
    AnalysisModeV2,
    AnalysisScopeV2,
    InsightContractV2,
)
from app.agents.metric_comparison_v2 import (
    RelativeChangeStatusV2,
    compare_metric_values_v2,
)
from app.delivery.decision_console_view_v2 import (
    VIEW_CONTRACT_VERSION,
    build_decision_console_view_v2,
)
from app.semantic_layer.time_comparison_contract_v2 import (
    AlignmentModeV2,
    ComparisonTypeV2,
    PeriodModeV2,
    TimeComparisonContractV2,
    TimeWindowReferenceV2,
)


EXPECTED_VIEW_VERSION = "day89_decision_console_view_v2_7"
CURRENT_ID = "ev-current"
REFERENCE_ID = "ev-reference"


def _comparison() -> TimeComparisonContractV2:
    return TimeComparisonContractV2(
        comparison_type=ComparisonTypeV2.YOY,
        period_mode=PeriodModeV2.COMPLETED_PERIOD,
        alignment_mode=AlignmentModeV2.CALENDAR_ALIGNED,
        current_window=TimeWindowReferenceV2(
            start_date=date(2025, 7, 1),
            end_date=date(2025, 7, 31),
        ),
        reference_window=TimeWindowReferenceV2(
            start_date=date(2024, 7, 1),
            end_date=date(2024, 7, 31),
        ),
    )


def _metric_definition() -> MetricDefinitionSnapshotV2:
    return MetricDefinitionSnapshotV2(
        metadata_version="v2",
        dataset_name="beauty_bi_v2",
        metric_name="gmv",
        chinese_name="销售额",
        grain="paid_order_items",
        definition="测试用 GMV Definition。",
        formula="SUM(item_paid_amount)",
        filters=(),
        metric_fingerprint="metric-fingerprint",
    )


def _provenance(
    *,
    evidence_id: str,
    window: TimeWindowReferenceV2,
) -> GovernedEvidenceProvenanceV2:
    return GovernedEvidenceProvenanceV2(
        dataset_name="beauty_bi_v2",
        target_schema="analytics",
        metric_name="gmv",
        result_grain="overall",
        analysis_window=window,
        scope_summary="authorized_scope_only",
        plan_name="overall_gmv",
        query_plan_fingerprint=f"plan-{evidence_id}",
        envelope_fingerprint=f"envelope-{evidence_id}",
        compiled_contract_fingerprint=f"compiled-{evidence_id}",
        sql_fingerprint=f"sql-{evidence_id}",
        time_binding_fingerprint=f"time-{evidence_id}",
        scope_binding_fingerprint=f"scope-{evidence_id}",
        tool_name="governed_metric_query",
        tool_version="v2",
        audit_event_id=f"audit-{evidence_id}",
        audit_event_fingerprint=f"audit-fp-{evidence_id}",
        audit_record_hash=f"audit-hash-{evidence_id}",
        finalization_contract_version="v2",
    )


def _record(
    *,
    evidence_id: str,
    window: TimeWindowReferenceV2,
    value: str,
) -> EvidenceRecordV2:
    from app.agents.investigation_contracts_v2 import EvidenceReferenceV2

    return EvidenceRecordV2(
        reference=EvidenceReferenceV2(
            evidence_id=evidence_id,
            source="governed_query_result_v2",
            description="受保护 overall GMV Evidence。",
        ),
        evidence_type=EvidenceTypeV2.GOVERNED_QUERY_RESULT,
        provenance=_provenance(
            evidence_id=evidence_id,
            window=window,
        ),
        protected_result=ProtectedResultV2(
            field_names=("gmv",),
            rows=({"gmv": Decimal(value)},),
            row_count=1,
        ),
    )


def _delivery(
    *,
    swap_windows: bool = False,
):
    comparison = _comparison()
    scope = AnalysisScopeV2(
        metric_name="gmv",
        analysis_window=comparison.current_window,
        comparison=comparison,
        result_grain="overall",
        scope_summary="authorized_scope_only",
    )
    insight = InsightContractV2(
        analysis_mode=AnalysisModeV2.COMPARISON,
        analysis_scope=scope,
    )

    current_window = (
        comparison.reference_window
        if swap_windows
        else comparison.current_window
    )
    reference_window = (
        comparison.current_window
        if swap_windows
        else comparison.reference_window
    )

    pack = EvidencePackV2(
        pack_id="day89-kpi-pack",
        analysis_scope=scope,
        insight=insight,
        evidence_records=(
            _record(
                evidence_id=CURRENT_ID,
                window=current_window,
                value="120",
            ),
            _record(
                evidence_id=REFERENCE_ID,
                window=reference_window,
                value="100",
            ),
        ),
    )

    return assemble_evidence_pack_delivery_v2(
        evidence_pack=pack,
        metric_definition=_metric_definition(),
    )


def _result(
    *,
    current="120",
    reference="100",
):
    return compare_metric_values_v2(
        metric_name="gmv",
        comparison=_comparison(),
        current_evidence_id=CURRENT_ID,
        reference_evidence_id=REFERENCE_ID,
        current_value=Decimal(current),
        reference_value=Decimal(reference),
    )


def test_kpi_values_are_projected_without_recalculation() -> None:
    result = _result()

    view = build_decision_console_view_v2(
        delivery=_delivery(),
        metric_comparison_result=result,
    )

    assert view.comparison is not None
    assert view.comparison.current_value == result.current_value
    assert view.comparison.reference_value == result.reference_value
    assert view.comparison.absolute_change == result.absolute_change
    assert view.comparison.relative_change == result.relative_change


def test_verification_binds_metric_definition() -> None:
    delivery = _delivery()
    view = build_decision_console_view_v2(
        delivery=delivery,
        metric_comparison_result=_result(),
    )

    assert view.verification is not None
    assert (
        view.verification.metric_definition
        == delivery.metric_definition
    )


def test_verification_binds_current_reference_evidence() -> None:
    view = build_decision_console_view_v2(
        delivery=_delivery(),
        metric_comparison_result=_result(),
    )

    assert view.verification is not None
    assert (
        view.verification.current_evidence.evidence_id
        == CURRENT_ID
    )
    assert (
        view.verification.reference_evidence.evidence_id
        == REFERENCE_ID
    )
    assert (
        view.verification.current_evidence.analysis_window
        == _comparison().current_window
    )
    assert (
        view.verification.reference_evidence.analysis_window
        == _comparison().reference_window
    )


def test_reference_zero_remains_undefined() -> None:
    result = _result(
        current="100",
        reference="0",
    )

    view = build_decision_console_view_v2(
        delivery=_delivery(),
        metric_comparison_result=result,
    )

    assert view.comparison is not None
    assert view.comparison.relative_change is None
    assert (
        view.comparison.relative_change_status
        == RelativeChangeStatusV2.UNDEFINED_REFERENCE_ZERO
    )


def test_missing_current_evidence_fails_closed() -> None:
    bad = compare_metric_values_v2(
        metric_name="gmv",
        comparison=_comparison(),
        current_evidence_id="missing-current",
        reference_evidence_id=REFERENCE_ID,
        current_value=Decimal("120"),
        reference_value=Decimal("100"),
    )

    try:
        build_decision_console_view_v2(
            delivery=_delivery(),
            metric_comparison_result=bad,
        )
    except ValueError:
        return

    raise AssertionError(
        "不存在的 current Evidence 必须 fail-closed。"
    )


def test_swapped_evidence_windows_fail_closed() -> None:
    try:
        build_decision_console_view_v2(
            delivery=_delivery(swap_windows=True),
            metric_comparison_result=_result(),
        )
    except ValueError:
        return

    raise AssertionError(
        "current/reference Evidence window 交换后必须 fail-closed。"
    )


def test_wrong_comparison_contract_fails_closed() -> None:
    wrong = TimeComparisonContractV2(
        comparison_type=ComparisonTypeV2.MOM,
        period_mode=PeriodModeV2.COMPLETED_PERIOD,
        alignment_mode=AlignmentModeV2.CALENDAR_ALIGNED,
        current_window=TimeWindowReferenceV2(
            start_date=date(2025, 7, 1),
            end_date=date(2025, 7, 31),
        ),
        reference_window=TimeWindowReferenceV2(
            start_date=date(2025, 6, 1),
            end_date=date(2025, 6, 30),
        ),
    )

    result = compare_metric_values_v2(
        metric_name="gmv",
        comparison=wrong,
        current_evidence_id=CURRENT_ID,
        reference_evidence_id=REFERENCE_ID,
        current_value=Decimal("120"),
        reference_value=Decimal("100"),
    )

    try:
        build_decision_console_view_v2(
            delivery=_delivery(),
            metric_comparison_result=result,
        )
    except ValueError:
        return

    raise AssertionError(
        "Comparison Contract 不一致必须 fail-closed。"
    )


TESTS = (
    test_kpi_values_are_projected_without_recalculation,
    test_verification_binds_metric_definition,
    test_verification_binds_current_reference_evidence,
    test_reference_zero_remains_undefined,
    test_missing_current_evidence_fails_closed,
    test_swapped_evidence_windows_fail_closed,
    test_wrong_comparison_contract_fails_closed,
)


def run_acceptance() -> None:
    print("Day89 Decision Console KPI / Verification Preflight")
    print(f"Module: {console_view_module.__file__}")
    print(f"Version: {VIEW_CONTRACT_VERSION}")
    print(
        "Signature: "
        f"{inspect.signature(build_decision_console_view_v2)}"
    )

    if VIEW_CONTRACT_VERSION != EXPECTED_VIEW_VERSION:
        raise SystemExit(
            "Loaded Decision Console View version is stale: "
            f"expected={EXPECTED_VIEW_VERSION}; "
            f"actual={VIEW_CONTRACT_VERSION}"
        )

    passed = 0
    failures: list[str] = []

    for test in TESTS:
        try:
            test()
            passed += 1
        except Exception as exc:  # noqa: BLE001
            failures.append(
                f"{test.__name__}: "
                f"{type(exc).__name__}: {exc}"
            )

    print()
    print("Day89 Decision Console KPI / Verification Acceptance Summary")
    print(f"Total: {len(TESTS)}")
    print(f"Passed: {passed}")
    print(f"Failed: {len(failures)}")

    for failure in failures:
        print(f"- {failure}")

    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    run_acceptance()
