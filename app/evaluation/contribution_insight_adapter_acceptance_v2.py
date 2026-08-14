from datetime import date
from decimal import Decimal

from app.agents.contribution_analysis_v2 import (
    ContributionObservationV2,
    ContributionReconciliationStatusV2,
    analyze_additive_contribution_v2,
)
from app.agents.contribution_insight_adapter_v2 import (
    attach_contribution_result_to_insight_v2,
    build_dimension_contribution_material_v2,
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


def _window(start_date: date, end_date: date) -> TimeWindowReferenceV2:
    return TimeWindowReferenceV2(
        start_date=start_date,
        end_date=end_date,
    )


def _yoy() -> TimeComparisonContractV2:
    return TimeComparisonContractV2(
        comparison_type=ComparisonTypeV2.YOY,
        period_mode=PeriodModeV2.COMPLETED_PERIOD,
        alignment_mode=AlignmentModeV2.CALENDAR_ALIGNED,
        current_window=_window(date(2025, 7, 1), date(2025, 7, 31)),
        reference_window=_window(date(2024, 7, 1), date(2024, 7, 31)),
    )


def _mom() -> TimeComparisonContractV2:
    return TimeComparisonContractV2(
        comparison_type=ComparisonTypeV2.MOM,
        period_mode=PeriodModeV2.COMPLETED_PERIOD,
        alignment_mode=AlignmentModeV2.CALENDAR_ALIGNED,
        current_window=_window(date(2025, 7, 1), date(2025, 7, 31)),
        reference_window=_window(date(2025, 6, 1), date(2025, 6, 30)),
    )


def _obs(key: str, label: str, value: str) -> ContributionObservationV2:
    return ContributionObservationV2(
        member_key=key,
        member_label=label,
        value=Decimal(value),
    )


def _result(*, comparison=None, mismatch=False):
    comparison = comparison or _yoy()
    return analyze_additive_contribution_v2(
        metric_name="gmv",
        dimension_name="channel",
        comparison=comparison,
        current_overall_value=Decimal("900" if not mismatch else "890"),
        reference_overall_value=Decimal("1000"),
        current_members=(
            _obs("tmall", "天猫", "350"),
            _obs("douyin", "抖音", "270"),
            _obs("jd", "京东", "180"),
            _obs("red", "小红书", "100"),
        ),
        reference_members=(
            _obs("tmall", "天猫", "500"),
            _obs("douyin", "抖音", "300"),
            _obs("jd", "京东", "150"),
            _obs("red", "小红书", "50"),
        ),
    )


def _insight(
    *,
    mode=AnalysisModeV2.DIAGNOSTIC,
    metric_name="gmv",
    comparison=None,
    result_grain="channel",
) -> InsightContractV2:
    comparison = comparison or _yoy()
    return InsightContractV2(
        analysis_mode=mode,
        analysis_scope=AnalysisScopeV2(
            metric_name=metric_name,
            analysis_window=comparison.current_window,
            comparison=comparison,
            result_grain=result_grain,
        ),
    )


def _expect_value_error(fn) -> None:
    try:
        fn()
    except ValueError:
        return
    raise AssertionError("Expected ValueError.")


def test_material_uses_one_deterministic_evidence_reference() -> None:
    result = _result()
    statements, evidence = build_dimension_contribution_material_v2(
        result=result,
        evidence_id="contribution-evidence-001",
    )

    assert statements
    assert all(
        item.evidence_ids == ("contribution-evidence-001",)
        for item in statements
    )
    assert evidence.evidence_id == "contribution-evidence-001"
    assert evidence.source == "deterministic_contribution_analysis_v2"


def test_member_statements_follow_negative_then_positive_rankings() -> None:
    statements, _ = build_dimension_contribution_material_v2(
        result=_result(),
        evidence_id="contribution-evidence-002",
    )

    text = [item.statement for item in statements]
    assert "channel=天猫" in text[0]
    assert "channel=抖音" in text[1]
    assert "channel=小红书" in text[2]
    assert "channel=京东" in text[3]


def test_contribution_attaches_to_diagnostic_insight() -> None:
    result = attach_contribution_result_to_insight_v2(
        insight=_insight(),
        result=_result(),
        evidence_id="contribution-evidence-003",
    )

    assert len(result.dimension_contributions) == 4
    assert len(result.evidence) == 1
    assert not result.unknowns


def test_investigation_mode_is_allowed() -> None:
    result = attach_contribution_result_to_insight_v2(
        insight=_insight(mode=AnalysisModeV2.INVESTIGATION),
        result=_result(),
        evidence_id="contribution-evidence-004",
    )
    assert len(result.dimension_contributions) == 4


def test_comparison_mode_cannot_silently_escalate() -> None:
    _expect_value_error(
        lambda: attach_contribution_result_to_insight_v2(
            insight=_insight(mode=AnalysisModeV2.COMPARISON),
            result=_result(),
            evidence_id="contribution-evidence-005",
        )
    )


def test_metric_mismatch_fails() -> None:
    _expect_value_error(
        lambda: attach_contribution_result_to_insight_v2(
            insight=_insight(metric_name="order_count"),
            result=_result(),
            evidence_id="contribution-evidence-006",
        )
    )


def test_comparison_mismatch_fails() -> None:
    _expect_value_error(
        lambda: attach_contribution_result_to_insight_v2(
            insight=_insight(comparison=_mom()),
            result=_result(comparison=_yoy()),
            evidence_id="contribution-evidence-007",
        )
    )


def test_result_grain_mismatch_fails() -> None:
    _expect_value_error(
        lambda: attach_contribution_result_to_insight_v2(
            insight=_insight(result_grain="region"),
            result=_result(),
            evidence_id="contribution-evidence-008",
        )
    )


def test_duplicate_evidence_id_fails() -> None:
    insight = _insight().model_copy(
        update={
            "evidence": (
                EvidenceReferenceV2(
                    evidence_id="contribution-evidence-009",
                    source="existing",
                ),
            )
        }
    )

    _expect_value_error(
        lambda: attach_contribution_result_to_insight_v2(
            insight=insight,
            result=_result(),
            evidence_id="contribution-evidence-009",
        )
    )


def test_non_reconciled_result_preserves_unknown_remainder() -> None:
    contribution = _result(mismatch=True)
    assert (
        contribution.reconciliation_status
        == ContributionReconciliationStatusV2.NOT_RECONCILED
    )

    result = attach_contribution_result_to_insight_v2(
        insight=_insight(),
        result=contribution,
        evidence_id="contribution-evidence-010",
    )

    assert len(result.unknowns) == 1
    assert "unexplained_remainder=-10" in result.unknowns[0].description
    assert "complete explanation" in result.unknowns[0].description


def test_statements_do_not_claim_cause_or_action() -> None:
    statements, _ = build_dimension_contribution_material_v2(
        result=_result(),
        evidence_id="contribution-evidence-011",
    )

    forbidden = (
        "because",
        "caused by",
        "due to",
        "should",
        "recommend",
    )

    for statement in statements:
        lowered = statement.statement.lower()
        assert all(token not in lowered for token in forbidden)


TESTS = (
    test_material_uses_one_deterministic_evidence_reference,
    test_member_statements_follow_negative_then_positive_rankings,
    test_contribution_attaches_to_diagnostic_insight,
    test_investigation_mode_is_allowed,
    test_comparison_mode_cannot_silently_escalate,
    test_metric_mismatch_fails,
    test_comparison_mismatch_fails,
    test_result_grain_mismatch_fails,
    test_duplicate_evidence_id_fails,
    test_non_reconciled_result_preserves_unknown_remainder,
    test_statements_do_not_claim_cause_or_action,
)


def run_acceptance() -> None:
    passed = 0
    failed = 0

    print("=" * 80)
    print("Contribution Insight Adapter V2 Acceptance")
    print(f"Cases: {len(TESTS)}")

    for test in TESTS:
        print("=" * 80)
        print(test.__name__)
        try:
            test()
        except Exception as exc:
            failed += 1
            print("[FAIL]")
            print(f"{type(exc).__name__}: {exc}")
        else:
            passed += 1
            print("[PASS]")

    print("=" * 80)
    print("Contribution Insight Adapter V2 Acceptance Summary")
    print(f"Total: {len(TESTS)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    run_acceptance()
