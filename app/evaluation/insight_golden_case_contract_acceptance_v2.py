from __future__ import annotations

from pydantic import ValidationError

from app.agents.evidence_pack_delivery_v2 import (
    EvidenceSufficiencyStatusV2,
)
from app.agents.investigation_contracts_v2 import (
    AnalysisModeV2,
)
from app.evaluation.business_decision_evaluation_contract_v2 import (
    BusinessDecisionOverallStatusV2,
    EvaluationScoreV2,
)
from app.evaluation.insight_golden_case_contract_v2 import (
    BusinessDecisionScoreFloorV2,
    BusinessInsightThemeV2,
    EvaluationEvidenceClassV2,
    ForbiddenBusinessClaimV2,
    InsightGoldenCaseCatalogV2,
    InsightGoldenCaseV2,
    InsightSectionV2,
)


PASS_FLOOR = BusinessDecisionScoreFloorV2(
    factual_correctness=EvaluationScoreV2.PASS,
    diagnostic_relevance=EvaluationScoreV2.PASS,
    prioritization=EvaluationScoreV2.PASS,
    actionability=EvaluationScoreV2.PASS,
    epistemic_discipline=EvaluationScoreV2.PASS,
    evidence_sufficiency=EvaluationScoreV2.PASS,
)

PARTIAL_FLOOR = BusinessDecisionScoreFloorV2(
    factual_correctness=EvaluationScoreV2.PASS,
    diagnostic_relevance=EvaluationScoreV2.PARTIAL,
    prioritization=EvaluationScoreV2.PARTIAL,
    actionability=EvaluationScoreV2.PARTIAL,
    epistemic_discipline=EvaluationScoreV2.PASS,
    evidence_sufficiency=EvaluationScoreV2.PARTIAL,
)


def _case(
    **updates,
) -> InsightGoldenCaseV2:
    payload = {
        "case_id": "INS-001",
        "question": "为什么 GMV 同比下降，我应该先查什么？",
        "theme": BusinessInsightThemeV2.ACTIVITY_REVIEW,
        "evidence_class": (
            EvaluationEvidenceClassV2.REGRESSION
        ),
        "previously_observed": True,
        "used_for_development": True,
        "metric_name": "gmv",
        "expected_analysis_mode": AnalysisModeV2.INVESTIGATION,
        "expected_sufficiency": (
            EvidenceSufficiencyStatusV2.PARTIAL
        ),
        "expected_overall_status": (
            BusinessDecisionOverallStatusV2.PARTIAL
        ),
        "score_floor": PARTIAL_FLOOR,
        "required_sections": (
            InsightSectionV2.CONFIRMED_FACT,
            InsightSectionV2.DIMENSION_CONTRIBUTION,
            InsightSectionV2.RECOMMENDED_CHECK,
        ),
        "forbidden_sections": (),
        "forbidden_claims": (
            ForbiddenBusinessClaimV2.CAUSAL_ATTRIBUTION,
            ForbiddenBusinessClaimV2.UNSUPPORTED_FACT,
            ForbiddenBusinessClaimV2.ZERO_FROM_NO_DATA,
        ),
        "rationale": (
            "已经有事实和贡献证据，但仍需保持原因边界并给出下一步调查方向。"
        ),
        "tags": (
            "gmv",
            "yoy",
            "diagnostic",
        ),
    }
    payload.update(updates)
    return InsightGoldenCaseV2(**payload)


def test_valid_regression_case_passes() -> None:
    case = _case()

    assert (
        case.evidence_class
        == EvaluationEvidenceClassV2.REGRESSION
    )
    assert case.previously_observed
    assert case.used_for_development


def test_regression_case_must_be_observed() -> None:
    try:
        _case(
            previously_observed=False,
        )
    except ValidationError:
        return

    raise AssertionError(
        "Regression Case 必须已经被观察。"
    )


def test_valid_holdout_case_passes() -> None:
    case = _case(
        case_id="INS-H-001",
        evidence_class=EvaluationEvidenceClassV2.HOLDOUT,
        previously_observed=False,
        used_for_development=False,
    )

    assert (
        case.evidence_class
        == EvaluationEvidenceClassV2.HOLDOUT
    )


def test_holdout_cannot_be_used_for_development() -> None:
    try:
        _case(
            case_id="INS-H-002",
            evidence_class=EvaluationEvidenceClassV2.HOLDOUT,
            previously_observed=True,
            used_for_development=True,
        )
    except ValidationError:
        return

    raise AssertionError(
        "已经用于开发的 Case 不能继续标记为 Holdout。"
    )


def test_valid_fresh_generalization_case_passes() -> None:
    case = _case(
        case_id="INS-F-001",
        evidence_class=(
            EvaluationEvidenceClassV2.FRESH_GENERALIZATION
        ),
        previously_observed=False,
        used_for_development=False,
    )

    assert not case.previously_observed
    assert not case.used_for_development


def test_fresh_case_cannot_be_previously_observed() -> None:
    try:
        _case(
            case_id="INS-F-002",
            evidence_class=(
                EvaluationEvidenceClassV2.FRESH_GENERALIZATION
            ),
            previously_observed=True,
            used_for_development=False,
        )
    except ValidationError:
        return

    raise AssertionError(
        "已经观察过的 Case 不能冒充 Fresh Generalization。"
    )


def test_fresh_case_cannot_be_used_for_development() -> None:
    try:
        _case(
            case_id="INS-F-003",
            evidence_class=(
                EvaluationEvidenceClassV2.FRESH_GENERALIZATION
            ),
            previously_observed=False,
            used_for_development=True,
        )
    except ValidationError:
        return

    raise AssertionError(
        "用于开发调优的 Case 不能冒充 Fresh Generalization。"
    )


def test_required_and_forbidden_sections_cannot_overlap() -> None:
    try:
        _case(
            forbidden_sections=(
                InsightSectionV2.CONFIRMED_FACT,
            ),
        )
    except ValidationError:
        return

    raise AssertionError(
        "同一个 Section 不能同时 required / forbidden。"
    )


def test_duplicate_tags_fail_closed() -> None:
    try:
        _case(
            tags=("gmv", "gmv"),
        )
    except ValidationError:
        return

    raise AssertionError(
        "重复 tag 必须 fail-closed。"
    )


def test_expected_pass_requires_all_pass_floors() -> None:
    try:
        _case(
            expected_sufficiency=(
                EvidenceSufficiencyStatusV2
                .SUFFICIENT_FOR_CURRENT_SCOPE
            ),
            expected_overall_status=(
                BusinessDecisionOverallStatusV2.PASS
            ),
            score_floor=PARTIAL_FLOOR,
        )
    except ValidationError:
        return

    raise AssertionError(
        "期望 Overall PASS 时，六维 floor 必须全部 PASS。"
    )


def test_valid_all_pass_case_passes() -> None:
    case = _case(
        case_id="INS-002",
        expected_sufficiency=(
            EvidenceSufficiencyStatusV2
            .SUFFICIENT_FOR_CURRENT_SCOPE
        ),
        expected_overall_status=(
            BusinessDecisionOverallStatusV2.PASS
        ),
        score_floor=PASS_FLOOR,
        required_sections=(
            InsightSectionV2.CONFIRMED_FACT,
        ),
    )

    assert (
        case.expected_overall_status
        == BusinessDecisionOverallStatusV2.PASS
    )


def test_duplicate_case_id_in_catalog_fails() -> None:
    first = _case()
    second = _case()

    try:
        InsightGoldenCaseCatalogV2(
            cases=(first, second),
        )
    except ValidationError:
        return

    raise AssertionError(
        "Catalog 中重复 case_id 必须 fail-closed。"
    )


TESTS = (
    test_valid_regression_case_passes,
    test_regression_case_must_be_observed,
    test_valid_holdout_case_passes,
    test_holdout_cannot_be_used_for_development,
    test_valid_fresh_generalization_case_passes,
    test_fresh_case_cannot_be_previously_observed,
    test_fresh_case_cannot_be_used_for_development,
    test_required_and_forbidden_sections_cannot_overlap,
    test_duplicate_tags_fail_closed,
    test_expected_pass_requires_all_pass_floors,
    test_valid_all_pass_case_passes,
    test_duplicate_case_id_in_catalog_fails,
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
        "Day88 Insight Golden Case Contract V2 "
        "Acceptance Summary"
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
