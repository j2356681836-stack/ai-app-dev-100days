from datetime import date
from decimal import Decimal

from app.agents.anomaly_detection_v2 import (
    AnomalyChangeTypeV2,
    AnomalyDecisionStatusV2,
    AnomalyDirectionV2,
    AnomalyPolicyV2,
    detect_anomaly_v2,
)
from app.agents.anomaly_insight_adapter_v2 import (
    attach_anomaly_decision_to_insight_v2,
    build_detected_anomaly_material_v2,
)
from app.agents.investigation_contracts_v2 import (
    AnalysisModeV2,
    AnalysisScopeV2,
    EvidenceReferenceV2,
    InsightContractV2,
)
from app.semantic_layer.time_comparison_contract_v2 import (
    AlignmentModeV2,
    ComparisonTypeV2,
    PeriodModeV2,
    TimeComparisonContractV2,
    TimeWindowReferenceV2,
)


def _window(
    start_date: date,
    end_date: date,
) -> TimeWindowReferenceV2:
    return TimeWindowReferenceV2(
        start_date=start_date,
        end_date=end_date,
    )


def _yoy() -> TimeComparisonContractV2:
    return TimeComparisonContractV2(
        comparison_type=ComparisonTypeV2.YOY,
        period_mode=PeriodModeV2.COMPLETED_PERIOD,
        alignment_mode=AlignmentModeV2.CALENDAR_ALIGNED,
        current_window=_window(
            date(2025, 7, 1),
            date(2025, 7, 31),
        ),
        reference_window=_window(
            date(2024, 7, 1),
            date(2024, 7, 31),
        ),
    )


def _mom() -> TimeComparisonContractV2:
    return TimeComparisonContractV2(
        comparison_type=ComparisonTypeV2.MOM,
        period_mode=PeriodModeV2.COMPLETED_PERIOD,
        alignment_mode=AlignmentModeV2.CALENDAR_ALIGNED,
        current_window=_window(
            date(2025, 7, 1),
            date(2025, 7, 31),
        ),
        reference_window=_window(
            date(2025, 6, 1),
            date(2025, 6, 30),
        ),
    )


def _policy() -> AnomalyPolicyV2:
    # Acceptance fixture only.
    return AnomalyPolicyV2(
        metric_name="gmv",
        comparison_type=ComparisonTypeV2.YOY,
        change_type=AnomalyChangeTypeV2.RELATIVE,
        direction=AnomalyDirectionV2.DECREASE,
        threshold_value=Decimal("0.10"),
        sample_metric_name="order_count",
        minimum_sample_value=Decimal("100"),
        policy_version="acceptance_fixture_v2",
    )


def _anomaly_decision():
    return detect_anomaly_v2(
        evidence_id="anomaly-evidence-001",
        metric_name="gmv",
        comparison=_yoy(),
        current_value=Decimal("80"),
        reference_value=Decimal("100"),
        current_sample_value=Decimal("500"),
        reference_sample_value=Decimal("480"),
        policy=_policy(),
    )


def _normal_decision():
    return detect_anomaly_v2(
        evidence_id="anomaly-evidence-002",
        metric_name="gmv",
        comparison=_yoy(),
        current_value=Decimal("95"),
        reference_value=Decimal("100"),
        current_sample_value=Decimal("500"),
        reference_sample_value=Decimal("480"),
        policy=_policy(),
    )


def _diagnostic_insight(
    *,
    metric_name: str = "gmv",
    comparison=None,
) -> InsightContractV2:
    comparison = comparison or _yoy()

    return InsightContractV2(
        analysis_mode=AnalysisModeV2.DIAGNOSTIC,
        analysis_scope=AnalysisScopeV2(
            metric_name=metric_name,
            analysis_window=comparison.current_window,
            comparison=comparison,
        ),
    )


def test_anomaly_material_uses_decision_evidence_id() -> None:
    decision = _anomaly_decision()

    statement, evidence = (
        build_detected_anomaly_material_v2(
            decision
        )
    )

    assert statement.evidence_ids == (
        decision.evidence_id,
    )
    assert evidence.evidence_id == decision.evidence_id
    assert (
        evidence.source
        == "deterministic_anomaly_detector_v2"
    )


def test_anomaly_attaches_to_diagnostic_insight() -> None:
    result = attach_anomaly_decision_to_insight_v2(
        insight=_diagnostic_insight(),
        decision=_anomaly_decision(),
    )

    assert len(result.detected_anomalies) == 1
    assert len(result.evidence) == 1

    assert (
        result.detected_anomalies[0].evidence_ids
        == (result.evidence[0].evidence_id,)
    )


def test_normal_cannot_populate_detected_anomalies() -> None:
    decision = _normal_decision()

    assert (
        decision.status
        == AnomalyDecisionStatusV2.NORMAL
    )

    try:
        build_detected_anomaly_material_v2(
            decision
        )
    except ValueError:
        return

    raise AssertionError(
        "NORMAL must not enter detected_anomalies."
    )


def test_metric_mismatch_fails() -> None:
    try:
        attach_anomaly_decision_to_insight_v2(
            insight=_diagnostic_insight(
                metric_name="order_count"
            ),
            decision=_anomaly_decision(),
        )
    except ValueError:
        return

    raise AssertionError(
        "Metric mismatch must fail."
    )


def test_comparison_mismatch_fails() -> None:
    try:
        attach_anomaly_decision_to_insight_v2(
            insight=_diagnostic_insight(
                comparison=_mom()
            ),
            decision=_anomaly_decision(),
        )
    except ValueError:
        return

    raise AssertionError(
        "Comparison mismatch must fail."
    )


def test_comparison_mode_cannot_silently_escalate() -> None:
    comparison = _yoy()

    insight = InsightContractV2(
        analysis_mode=AnalysisModeV2.COMPARISON,
        analysis_scope=AnalysisScopeV2(
            metric_name="gmv",
            analysis_window=comparison.current_window,
            comparison=comparison,
        ),
    )

    try:
        attach_anomaly_decision_to_insight_v2(
            insight=insight,
            decision=_anomaly_decision(),
        )
    except ValueError:
        return

    raise AssertionError(
        "COMPARISON mode must not silently become diagnostic."
    )


def test_duplicate_evidence_id_fails() -> None:
    decision = _anomaly_decision()

    comparison = _yoy()
    insight = InsightContractV2(
        analysis_mode=AnalysisModeV2.DIAGNOSTIC,
        analysis_scope=AnalysisScopeV2(
            metric_name="gmv",
            analysis_window=comparison.current_window,
            comparison=comparison,
        ),
        evidence=(
            EvidenceReferenceV2(
                evidence_id=decision.evidence_id,
                source="existing_evidence",
            ),
        ),
    )

    try:
        attach_anomaly_decision_to_insight_v2(
            insight=insight,
            decision=decision,
        )
    except ValueError:
        return

    raise AssertionError(
        "Duplicate evidence_id must fail."
    )


def test_statement_does_not_claim_cause() -> None:
    statement, _ = (
        build_detected_anomaly_material_v2(
            _anomaly_decision()
        )
    )

    lowered = statement.statement.lower()

    for forbidden in (
        "because",
        "caused by",
        "due to",
    ):
        assert forbidden not in lowered


TESTS = (
    test_anomaly_material_uses_decision_evidence_id,
    test_anomaly_attaches_to_diagnostic_insight,
    test_normal_cannot_populate_detected_anomalies,
    test_metric_mismatch_fails,
    test_comparison_mismatch_fails,
    test_comparison_mode_cannot_silently_escalate,
    test_duplicate_evidence_id_fails,
    test_statement_does_not_claim_cause,
)


def run_acceptance() -> None:
    passed = 0
    failed = 0

    print("=" * 80)
    print("Anomaly Insight Adapter V2 Acceptance")
    print(f"Cases: {len(TESTS)}")

    for test in TESTS:
        print("=" * 80)
        print(test.__name__)

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
        "Anomaly Insight Adapter V2 "
        "Acceptance Summary"
    )
    print(f"Total: {len(TESTS)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    run_acceptance()
