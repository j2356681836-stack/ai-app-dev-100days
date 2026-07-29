from pathlib import Path

import yaml

from app.evaluation.golden_case_v2_models import (
    GoldenCaseSplit,
    GovernanceOutcome,
    MetricDecisionStatus,
    PlanDecisionStatus,
)
from app.evaluation.golden_cases_v2 import (
    DEVELOPMENT_CASES_V2,
    GOLDEN_CASES_V2,
    REGRESSION_CASES_V2,
)


EXPECTED_METRICS = {
    "gmv",
    "gross_margin",
    "gross_margin_rate",
    "refund_rate",
    "roi",
    "cac",
    "brand_paid_new_customer_count",
    "channel_paid_new_customer_count",
    "repeat_customer_rate",
    "member_gmv_share",
    "buyer_count",
    "order_count",
    "units_sold",
    "spending_per_buyer",
    "ipt",
    "aus",
    "purchase_frequency",
    "repeat_customer_count",
    "multi_order_customer_count",
}


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_business_metric_names() -> set[str]:
    path = (
        project_root()
        / "metadata"
        / "beauty_bi_v2"
        / "business_metrics.yaml"
    )

    with path.open(
        "r",
        encoding="utf-8",
    ) as f:
        data = yaml.safe_load(f)

    return {
        item["name"]
        for item in data["metrics"]
    }


def load_plan_matrix() -> dict[tuple[str, str], str]:
    path = (
        project_root()
        / "metadata"
        / "beauty_bi_v2"
        / "query_plans.yaml"
    )

    with path.open(
        "r",
        encoding="utf-8",
    ) as f:
        data = yaml.safe_load(f)

    matrix = {}

    for plan in data["query_plans"]:
        key = (
            plan["metric"],
            plan["result_grain"],
        )

        if key in matrix:
            raise AssertionError(
                f"Duplicate metric/result_grain plan: {key}"
            )

        matrix[key] = plan["name"]

    return matrix


def assert_equal(
    actual,
    expected,
    message: str,
) -> None:
    if actual != expected:
        raise AssertionError(
            f"{message}\nExpected: {expected}\nActual: {actual}"
        )


def assert_true(
    condition: bool,
    message: str,
) -> None:
    if not condition:
        raise AssertionError(message)


def test_case_counts_and_splits() -> None:
    assert_equal(
        len(DEVELOPMENT_CASES_V2),
        19,
        "Gate 3 应有 19 个 Development Cases。",
    )

    assert_equal(
        len(REGRESSION_CASES_V2),
        11,
        "Gate 3 应有 11 个 Regression Cases。",
    )

    assert_equal(
        len(GOLDEN_CASES_V2.cases),
        30,
        "Gate 3 总 Case 数应为 30。",
    )

    assert_true(
        all(
            case.split == GoldenCaseSplit.DEVELOPMENT
            for case in DEVELOPMENT_CASES_V2
        ),
        "Development Set 不得混入其他 split。",
    )

    assert_true(
        all(
            case.split == GoldenCaseSplit.REGRESSION
            for case in REGRESSION_CASES_V2
        ),
        "Regression Set 不得混入其他 split。",
    )


def test_development_set_covers_exact_19_metrics() -> None:
    metrics = {
        case.expected_metric.metric_name
        for case in DEVELOPMENT_CASES_V2
    }

    assert_equal(
        metrics,
        EXPECTED_METRICS,
        "Development Set 应精确覆盖 19 个 V2 Metrics。",
    )


def test_all_metric_references_exist_in_metadata_v2() -> None:
    known_metrics = load_business_metric_names()

    assert_equal(
        known_metrics,
        EXPECTED_METRICS,
        "business_metrics.yaml 应保持冻结的 19 Metrics。",
    )

    for case in GOLDEN_CASES_V2.cases:
        decision = case.expected_metric

        if decision.status == MetricDecisionStatus.MATCHED:
            assert_true(
                decision.metric_name in known_metrics,
                f"{case.case_id} 引用了未知 metric。",
            )

        for candidate in decision.acceptable_candidates:
            assert_true(
                candidate in known_metrics,
                f"{case.case_id} clarification 引用了未知 metric。",
            )


def test_selected_plan_cases_match_static_catalog() -> None:
    matrix = load_plan_matrix()

    for case in GOLDEN_CASES_V2.cases:
        if (
            case.expected_plan.status
            != PlanDecisionStatus.SELECTED
        ):
            continue

        key = (
            case.expected_metric.metric_name,
            case.expected_intent.result_grain.value,
        )

        assert_true(
            key in matrix,
            (
                f"{case.case_id} 期望的 metric/result_grain "
                f"不存在于静态 Catalog：{key}"
            ),
        )

        assert_equal(
            case.expected_plan.plan_name,
            matrix[key],
            (
                f"{case.case_id} 的 Plan Name 必须与 "
                "query_plans.yaml 精确一致。"
            ),
        )


def test_unsupported_shape_cases_are_really_unsupported() -> None:
    matrix = load_plan_matrix()

    unsupported_cases = [
        case
        for case in GOLDEN_CASES_V2.cases
        if (
            case.expected_plan.status
            == PlanDecisionStatus.UNSUPPORTED_SHAPE
        )
    ]

    assert_equal(
        {
            case.case_id
            for case in unsupported_cases
        },
        {
            "reg_roi_region_shape_001",
            "reg_cac_region_shape_001",
            "reg_aus_category_shape_001",
            "reg_refund_rate_category_shape_001",
        },
        "Gate 3 Unsupported Shape Case 集合发生漂移。",
    )

    for case in unsupported_cases:
        key = (
            case.expected_metric.metric_name,
            case.expected_intent.result_grain.value,
        )

        assert_true(
            key not in matrix,
            (
                f"{case.case_id} 标记 unsupported，"
                f"但 Catalog 已存在 Plan：{key}"
            ),
        )


def test_new_customer_ambiguity_is_preserved() -> None:
    case = next(
        case
        for case in GOLDEN_CASES_V2.cases
        if case.case_id
        == "reg_new_customer_ambiguity_001"
    )

    assert_equal(
        case.expected_metric.status,
        MetricDecisionStatus.NEEDS_CLARIFICATION,
        "未限定的新客问题必须保持 clarification。",
    )

    assert_equal(
        set(
            case.expected_metric.acceptable_candidates
        ),
        {
            "brand_paid_new_customer_count",
            "channel_paid_new_customer_count",
        },
        "新客 clarification 候选必须保持品牌 / 渠道两个口径。",
    )

    assert_equal(
        case.expected_plan.status,
        PlanDecisionStatus.NOT_APPLICABLE,
        "新客未澄清前不得提前选择 Plan。",
    )


def test_business_confusion_pairs_are_distinct() -> None:
    expected = {
        "reg_aus_vs_spending_001": "aus",
        "reg_spending_vs_aus_001": "spending_per_buyer",
        "reg_ipt_vs_units_001": "ipt",
        "reg_frequency_vs_repeat_001": "purchase_frequency",
        "reg_repeat_vs_multi_order_001": "repeat_customer_count",
        "reg_multi_order_vs_repeat_001": "multi_order_customer_count",
    }

    actual = {
        case.case_id: case.expected_metric.metric_name
        for case in GOLDEN_CASES_V2.cases
        if case.case_id in expected
    }

    assert_equal(
        actual,
        expected,
        "关键易混淆指标对发生语义漂移。",
    )


def test_gate3_cases_do_not_claim_governance_results() -> None:
    assert_true(
        all(
            case.expected_governance.outcome
            == GovernanceOutcome.NOT_EVALUATED
            for case in GOLDEN_CASES_V2.cases
        ),
        (
            "Gate 3 是 Semantic Decision Baseline，"
            "在未绑定明确 AccessContext Fixture 前 "
            "不得伪造 allowed / denied。"
        ),
    )


def test_case_ids_and_questions_are_unique() -> None:
    cases = GOLDEN_CASES_V2.cases

    case_ids = [
        case.case_id
        for case in cases
    ]
    questions = [
        case.question
        for case in cases
    ]

    assert_equal(
        len(case_ids),
        len(set(case_ids)),
        "case_id 必须唯一。",
    )

    assert_equal(
        len(questions),
        len(set(questions)),
        "Gate 3 问题文本必须唯一。",
    )


def test_gate3_contains_no_holdout_or_adversarial_split() -> None:
    actual_splits = {
        case.split
        for case in GOLDEN_CASES_V2.cases
    }

    assert_equal(
        actual_splits,
        {
            GoldenCaseSplit.DEVELOPMENT,
            GoldenCaseSplit.REGRESSION,
        },
        (
            "Locked Holdout / Adversarial 必须留到后续 Gate，"
            "不能提前混入可见开发集。"
        ),
    )


def run_tests() -> None:
    tests = [
        test_case_counts_and_splits,
        test_development_set_covers_exact_19_metrics,
        test_all_metric_references_exist_in_metadata_v2,
        test_selected_plan_cases_match_static_catalog,
        test_unsupported_shape_cases_are_really_unsupported,
        test_new_customer_ambiguity_is_preserved,
        test_business_confusion_pairs_are_distinct,
        test_gate3_cases_do_not_claim_governance_results,
        test_case_ids_and_questions_are_unique,
        test_gate3_contains_no_holdout_or_adversarial_split,
    ]

    passed = 0
    failed = 0

    for test in tests:
        print("=" * 80)
        print(f"Running: {test.__name__}")

        try:
            test()
            passed += 1
            print("[PASS]")
        except Exception as exc:
            failed += 1
            print("[FAIL]")
            print(exc)

    print("=" * 80)
    print("Golden Cases V2 Gate 3 Test Summary")
    print(f"Total: {len(tests)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    run_tests()
