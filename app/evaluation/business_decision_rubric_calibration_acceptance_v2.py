from __future__ import annotations

from app.evaluation.business_decision_evaluation_contract_v2 import (
    BusinessDecisionOverallStatusV2,
    EvaluationScoreV2,
)
from app.evaluation.business_decision_rubric_v2 import (
    BUSINESS_DECISION_RUBRIC_V1_0,
    BUSINESS_DECISION_RUBRIC_V2_0,
)
from app.evaluation.judge_human_calibration_evidence_v2 import (
    build_day88_observed_calibration_evidence_v2,
)
from app.evaluation.judge_human_calibration_v2 import (
    BusinessDecisionDimensionV2,
    JudgeHumanAgreementStatusV2,
)


def _rule_map(rubric):
    return {
        item.dimension: item
        for item in rubric.dimensions
    }


def test_both_rubric_versions_cover_six_dimensions() -> None:
    assert len(
        BUSINESS_DECISION_RUBRIC_V1_0.dimensions
    ) == 6
    assert len(
        BUSINESS_DECISION_RUBRIC_V2_0.dimensions
    ) == 6


def test_v2_supersedes_v1_without_overwriting_history() -> None:
    assert (
        BUSINESS_DECISION_RUBRIC_V2_0.supersedes
        == BUSINESS_DECISION_RUBRIC_V1_0.rubric_version
    )
    assert (
        BUSINESS_DECISION_RUBRIC_V2_0.rubric_version
        != BUSINESS_DECISION_RUBRIC_V1_0.rubric_version
    )


def test_prioritization_is_the_explicit_v2_change() -> None:
    v1 = _rule_map(
        BUSINESS_DECISION_RUBRIC_V1_0
    )
    v2 = _rule_map(
        BUSINESS_DECISION_RUBRIC_V2_0
    )

    for dimension in BusinessDecisionDimensionV2:
        if (
            dimension
            == BusinessDecisionDimensionV2.PRIORITIZATION
        ):
            assert (
                v1[dimension].pass_criteria
                != v2[dimension].pass_criteria
            )
            assert (
                "business objective"
                in v2[dimension].pass_criteria
            )
        else:
            assert (
                v1[dimension]
                == v2[dimension]
            )


def test_observed_evidence_keeps_original_rubric_version() -> None:
    evidence = (
        build_day88_observed_calibration_evidence_v2()
    )

    assert (
        evidence.provenance.rubric_version
        == BUSINESS_DECISION_RUBRIC_V1_0.rubric_version
    )
    assert (
        evidence.proposed_rubric_version
        == BUSINESS_DECISION_RUBRIC_V2_0.rubric_version
    )


def test_judge_pass_human_partial_is_preserved() -> None:
    evidence = (
        build_day88_observed_calibration_evidence_v2()
    )

    assert (
        evidence.judge_evaluation.prioritization.score
        == EvaluationScoreV2.PASS
    )
    assert (
        evidence.human_review.evaluation.prioritization.score
        == EvaluationScoreV2.PARTIAL
    )

    assert (
        evidence.judge_evaluation.overall_status
        == BusinessDecisionOverallStatusV2.PASS
    )
    assert (
        evidence.human_review.evaluation.overall_status
        == BusinessDecisionOverallStatusV2.PARTIAL
    )


def test_calibration_has_one_noncritical_disagreement() -> None:
    evidence = (
        build_day88_observed_calibration_evidence_v2()
    )
    result = evidence.calibration

    assert result.agreement_count == 5
    assert result.disagreement_count == 1
    assert not result.overall_status_agreement
    assert result.requires_calibration_review
    assert (
        result.critical_disagreement_dimensions
        == ()
    )

    disagreement = next(
        item
        for item in result.comparisons
        if (
            item.status
            == JudgeHumanAgreementStatusV2.DISAGREEMENT
        )
    )

    assert (
        disagreement.dimension
        == BusinessDecisionDimensionV2.PRIORITIZATION
    )


def test_observed_evidence_references_real_day88_evidence_id() -> None:
    evidence = (
        build_day88_observed_calibration_evidence_v2()
    )

    assert evidence.observed_evidence_ids == (
        "ev_day88_observed_channel_gmv",
    )


TESTS = (
    test_both_rubric_versions_cover_six_dimensions,
    test_v2_supersedes_v1_without_overwriting_history,
    test_prioritization_is_the_explicit_v2_change,
    test_observed_evidence_keeps_original_rubric_version,
    test_judge_pass_human_partial_is_preserved,
    test_calibration_has_one_noncritical_disagreement,
    test_observed_evidence_references_real_day88_evidence_id,
)


def run_acceptance() -> None:
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

    print(
        "Day88 Rubric Versioning + Observed Calibration "
        "Evidence V2 Acceptance Summary"
    )
    print(f"Total: {len(TESTS)}")
    print(f"Passed: {passed}")
    print(f"Failed: {len(failures)}")

    for failure in failures:
        print(f"- {failure}")

    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    run_acceptance()
