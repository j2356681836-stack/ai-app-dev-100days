from __future__ import annotations

from pathlib import Path

import yaml

from app.evaluation.insight_golden_case_contract_v2 import (
    BusinessInsightThemeV2,
    EvaluationEvidenceClassV2,
    ForbiddenBusinessClaimV2,
    InsightSectionV2,
)
from app.evaluation.insight_golden_cases_v2 import (
    VISIBLE_REGRESSION_CATALOG_V2,
    VISIBLE_REGRESSION_CASES_V2,
)


EXPECTED_THEMES = {
    BusinessInsightThemeV2.ACTIVITY_REVIEW,
    BusinessInsightThemeV2.ROI,
    BusinessInsightThemeV2.MARGIN,
    BusinessInsightThemeV2.REFUND,
    BusinessInsightThemeV2.CAC,
    BusinessInsightThemeV2.REGION,
    BusinessInsightThemeV2.MEMBERSHIP,
    BusinessInsightThemeV2.PROMOTION,
}


def _load_v2_metric_names() -> set[str]:
    path = Path(
        "metadata/beauty_bi_v2/business_metrics.yaml"
    )

    if not path.exists():
        # 仅用于隔离 acceptance fixture。
        path = Path("business_metrics_v2.yaml")

    payload = yaml.safe_load(
        path.read_text(encoding="utf-8")
    )

    assert payload["dataset_name"] == "beauty_bi_v2"

    return {
        metric["name"]
        for metric in payload["metrics"]
    }


def test_catalog_contains_eight_visible_regression_cases() -> None:
    assert len(VISIBLE_REGRESSION_CASES_V2) == 8
    assert len(VISIBLE_REGRESSION_CATALOG_V2.cases) == 8


def test_all_required_business_themes_are_covered() -> None:
    actual = {
        case.theme
        for case in VISIBLE_REGRESSION_CASES_V2
    }

    assert actual == EXPECTED_THEMES


def test_all_cases_are_visible_regression_not_fresh() -> None:
    for case in VISIBLE_REGRESSION_CASES_V2:
        assert (
            case.evidence_class
            == EvaluationEvidenceClassV2.REGRESSION
        )
        assert case.previously_observed
        assert case.used_for_development


def test_no_fresh_generalization_case_is_exposed() -> None:
    assert all(
        case.evidence_class
        != EvaluationEvidenceClassV2.FRESH_GENERALIZATION
        for case in VISIBLE_REGRESSION_CASES_V2
    )


def test_all_metrics_exist_in_real_v2_metadata() -> None:
    metric_names = _load_v2_metric_names()

    for case in VISIBLE_REGRESSION_CASES_V2:
        assert case.metric_name in metric_names


def test_all_cases_forbid_causal_attribution() -> None:
    for case in VISIBLE_REGRESSION_CASES_V2:
        assert (
            ForbiddenBusinessClaimV2.CAUSAL_ATTRIBUTION
            in case.forbidden_claims
        )


def test_only_supported_gmv_channel_case_requires_contribution() -> None:
    requiring_contribution = [
        case.case_id
        for case in VISIBLE_REGRESSION_CASES_V2
        if (
            InsightSectionV2.DIMENSION_CONTRIBUTION
            in case.required_sections
        )
    ]

    assert requiring_contribution == ["INS-REG-001"]


def test_ratio_cases_do_not_require_additive_contribution() -> None:
    ratio_metric_names = {
        "roi",
        "gross_margin_rate",
        "refund_rate",
        "member_gmv_share",
    }

    for case in VISIBLE_REGRESSION_CASES_V2:
        if case.metric_name in ratio_metric_names:
            assert (
                InsightSectionV2.DIMENSION_CONTRIBUTION
                not in case.required_sections
            )


def test_cac_case_preserves_scope_boundary() -> None:
    case = next(
        item
        for item in VISIBLE_REGRESSION_CASES_V2
        if item.case_id == "INS-REG-005"
    )

    assert (
        InsightSectionV2.UNKNOWN
        in case.required_sections
    )
    assert (
        InsightSectionV2.RECOMMENDED_CHECK
        in case.required_sections
    )
    assert (
        ForbiddenBusinessClaimV2
        .UNAUTHORIZED_EXISTENCE_DISCLOSURE
        in case.forbidden_claims
    )


def test_promotion_case_does_not_fake_campaign_runtime() -> None:
    case = next(
        item
        for item in VISIBLE_REGRESSION_CASES_V2
        if item.case_id == "INS-REG-008"
    )

    assert (
        InsightSectionV2.UNKNOWN
        in case.required_sections
    )
    assert (
        InsightSectionV2.RECOMMENDED_CHECK
        in case.required_sections
    )


def test_case_ids_are_stable_and_ordered() -> None:
    assert [
        case.case_id
        for case in VISIBLE_REGRESSION_CASES_V2
    ] == [
        "INS-REG-001",
        "INS-REG-002",
        "INS-REG-003",
        "INS-REG-004",
        "INS-REG-005",
        "INS-REG-006",
        "INS-REG-007",
        "INS-REG-008",
    ]


def test_questions_are_unique() -> None:
    questions = [
        case.question
        for case in VISIBLE_REGRESSION_CASES_V2
    ]

    assert len(set(questions)) == len(questions)


TESTS = (
    test_catalog_contains_eight_visible_regression_cases,
    test_all_required_business_themes_are_covered,
    test_all_cases_are_visible_regression_not_fresh,
    test_no_fresh_generalization_case_is_exposed,
    test_all_metrics_exist_in_real_v2_metadata,
    test_all_cases_forbid_causal_attribution,
    test_only_supported_gmv_channel_case_requires_contribution,
    test_ratio_cases_do_not_require_additive_contribution,
    test_cac_case_preserves_scope_boundary,
    test_promotion_case_does_not_fake_campaign_runtime,
    test_case_ids_are_stable_and_ordered,
    test_questions_are_unique,
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
        "Day88 Visible Insight Golden Cases V2 "
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
