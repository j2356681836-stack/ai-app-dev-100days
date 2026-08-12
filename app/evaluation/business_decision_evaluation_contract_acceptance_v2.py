from pydantic import ValidationError

from app.evaluation.business_decision_evaluation_contract_v2 import (
    BusinessDecisionEvaluationResultV2,
    BusinessDecisionOverallStatusV2,
    EvaluationDimensionResultV2,
    EvaluationScoreV2,
    derive_overall_status_v2,
)


def _dimension(
    score: EvaluationScoreV2,
    reason: str = "Acceptance fixture.",
) -> EvaluationDimensionResultV2:
    return EvaluationDimensionResultV2(
        score=score,
        reason=reason,
    )


def _build_result(
    *,
    factual: EvaluationScoreV2 = EvaluationScoreV2.PASS,
    relevance: EvaluationScoreV2 = EvaluationScoreV2.PASS,
    prioritization: EvaluationScoreV2 = EvaluationScoreV2.PASS,
    actionability: EvaluationScoreV2 = EvaluationScoreV2.PASS,
    epistemic: EvaluationScoreV2 = EvaluationScoreV2.PASS,
    evidence: EvaluationScoreV2 = EvaluationScoreV2.PASS,
) -> BusinessDecisionEvaluationResultV2:
    values = {
        "factual_correctness": _dimension(factual),
        "diagnostic_relevance": _dimension(relevance),
        "prioritization": _dimension(prioritization),
        "actionability": _dimension(actionability),
        "epistemic_discipline": _dimension(epistemic),
        "evidence_sufficiency": _dimension(evidence),
    }

    overall = derive_overall_status_v2(
        **values
    )

    return BusinessDecisionEvaluationResultV2(
        **values,
        overall_status=overall,
    )


def test_all_passes_yields_pass() -> None:
    result = _build_result()

    assert (
        result.overall_status
        == BusinessDecisionOverallStatusV2.PASS
    )


def test_factual_fail_is_hard_fail() -> None:
    result = _build_result(
        factual=EvaluationScoreV2.FAIL,
    )

    assert (
        result.overall_status
        == BusinessDecisionOverallStatusV2.FAIL
    )


def test_epistemic_fail_is_hard_fail() -> None:
    result = _build_result(
        epistemic=EvaluationScoreV2.FAIL,
    )

    assert (
        result.overall_status
        == BusinessDecisionOverallStatusV2.FAIL
    )


def test_evidence_fail_prevents_full_pass() -> None:
    result = _build_result(
        evidence=EvaluationScoreV2.FAIL,
    )

    assert (
        result.overall_status
        == BusinessDecisionOverallStatusV2.PARTIAL
    )


def test_non_hard_partial_yields_partial() -> None:
    result = _build_result(
        actionability=EvaluationScoreV2.PARTIAL,
    )

    assert (
        result.overall_status
        == BusinessDecisionOverallStatusV2.PARTIAL
    )


def test_wrong_overall_status_is_rejected() -> None:
    try:
        BusinessDecisionEvaluationResultV2(
            factual_correctness=_dimension(
                EvaluationScoreV2.FAIL
            ),
            diagnostic_relevance=_dimension(
                EvaluationScoreV2.PASS
            ),
            prioritization=_dimension(
                EvaluationScoreV2.PASS
            ),
            actionability=_dimension(
                EvaluationScoreV2.PASS
            ),
            epistemic_discipline=_dimension(
                EvaluationScoreV2.PASS
            ),
            evidence_sufficiency=_dimension(
                EvaluationScoreV2.PASS
            ),
            overall_status=(
                BusinessDecisionOverallStatusV2.PASS
            ),
        )
    except ValidationError:
        return

    raise AssertionError(
        "Mismatched overall_status must fail."
    )


def test_dimension_requires_reason() -> None:
    try:
        EvaluationDimensionResultV2(
            score=EvaluationScoreV2.PASS,
            reason="   ",
        )
    except ValidationError:
        return

    raise AssertionError(
        "Evaluation dimension without reason must fail."
    )


TESTS = (
    test_all_passes_yields_pass,
    test_factual_fail_is_hard_fail,
    test_epistemic_fail_is_hard_fail,
    test_evidence_fail_prevents_full_pass,
    test_non_hard_partial_yields_partial,
    test_wrong_overall_status_is_rejected,
    test_dimension_requires_reason,
)


def run_acceptance() -> None:
    passed = 0
    failed = 0

    print("=" * 80)
    print(
        "Business Decision Evaluation Contract V2 Acceptance"
    )
    print(
        f"Cases: {len(TESTS)}"
    )

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
        "Business Decision Evaluation Contract V2 "
        "Acceptance Summary"
    )
    print(
        f"Total: {len(TESTS)}"
    )
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    run_acceptance()
