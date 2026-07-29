from pathlib import Path

import yaml

from app.evaluation.generalization_cases_v2 import (
    LOCKED_HOLDOUT_CASES_V2,
    LOCKED_HOLDOUT_FINGERPRINT,
    SEMANTIC_ADVERSARIAL_CASES_V2,
    compute_locked_holdout_fingerprint,
)
from app.evaluation.golden_case_v2_models import (
    GoldenCaseSplit,
    MetricDecisionStatus,
    PlanDecisionStatus,
)
from app.evaluation.golden_cases_v2 import GOLDEN_CASES_V2


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


def normalize(text: str) -> str:
    return "".join(text.casefold().split())


def load_metadata_training_phrases() -> set[str]:
    path = (
        project_root()
        / "metadata"
        / "beauty_bi_v2"
        / "business_metrics.yaml"
    )
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    phrases = set()

    for metric in data["metrics"]:
        for key in ("name", "chinese_name"):
            value = metric.get(key)
            if value:
                phrases.add(normalize(str(value)))

        for key in (
            "aliases",
            "examples",
            "negative_examples",
        ):
            for value in metric.get(key, []):
                if value:
                    phrases.add(normalize(str(value)))

    return phrases


def load_plan_matrix() -> dict[tuple[str, str], str]:
    path = (
        project_root()
        / "metadata"
        / "beauty_bi_v2"
        / "query_plans.yaml"
    )
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    matrix = {}

    for plan in data["query_plans"]:
        key = (
            plan["metric"],
            plan["result_grain"],
        )
        if key in matrix:
            raise AssertionError(
                f"Duplicate plan shape: {key}"
            )
        matrix[key] = plan["name"]

    return matrix


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(
            f"{message}\nExpected: {expected}\nActual: {actual}"
        )


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_holdout_has_exactly_one_case_per_metric() -> None:
    assert_equal(
        len(LOCKED_HOLDOUT_CASES_V2),
        19,
        "Locked Holdout 应固定为 19 Cases。",
    )

    metrics = {
        case.expected_metric.metric_name
        for case in LOCKED_HOLDOUT_CASES_V2
    }

    assert_equal(
        metrics,
        EXPECTED_METRICS,
        "Locked Holdout 应精确覆盖 19 Metrics。",
    )

    assert_true(
        all(
            case.split
            == GoldenCaseSplit.LOCKED_HOLDOUT
            for case in LOCKED_HOLDOUT_CASES_V2
        ),
        "Holdout split 必须全部为 locked_holdout。",
    )


def test_holdout_fingerprint_is_frozen() -> None:
    assert_equal(
        compute_locked_holdout_fingerprint(),
        LOCKED_HOLDOUT_FINGERPRINT,
        (
            "Locked Holdout 已发生内容漂移。"
            "如需升级，应新建版本而不是覆盖 Day74 首次 Holdout。"
        ),
    )


def test_holdout_questions_do_not_duplicate_visible_cases() -> None:
    visible = {
        normalize(case.question)
        for case in GOLDEN_CASES_V2.cases
    }

    holdout = {
        normalize(case.question)
        for case in LOCKED_HOLDOUT_CASES_V2
    }

    assert_true(
        visible.isdisjoint(holdout),
        "Locked Holdout 不得复制 Development / Regression 问题。",
    )


def test_holdout_questions_are_not_exact_metadata_phrases() -> None:
    training = load_metadata_training_phrases()

    duplicates = [
        case.question
        for case in LOCKED_HOLDOUT_CASES_V2
        if normalize(case.question) in training
    ]

    assert_equal(
        duplicates,
        [],
        (
            "Locked Holdout 不能直接复制 Metadata "
            "name / chinese_name / aliases / examples / negative_examples。"
        ),
    )


def test_holdout_selected_plans_match_static_catalog() -> None:
    matrix = load_plan_matrix()

    for case in LOCKED_HOLDOUT_CASES_V2:
        key = (
            case.expected_metric.metric_name,
            case.expected_intent.result_grain.value,
        )

        assert_true(
            key in matrix,
            f"Holdout 引用了不存在的 Query Shape: {key}",
        )

        assert_equal(
            case.expected_plan.plan_name,
            matrix[key],
            f"{case.case_id} Plan Name 与静态 Catalog 不一致。",
        )


def test_adversarial_case_count_and_split() -> None:
    assert_equal(
        len(SEMANTIC_ADVERSARIAL_CASES_V2),
        14,
        "Semantic Adversarial 应固定为 14 Cases。",
    )

    assert_true(
        all(
            case.split == GoldenCaseSplit.ADVERSARIAL
            for case in SEMANTIC_ADVERSARIAL_CASES_V2
        ),
        "Adversarial split 发生污染。",
    )


def test_adversarial_contains_expected_failure_modes() -> None:
    statuses = {
        case.expected_metric.status
        for case in SEMANTIC_ADVERSARIAL_CASES_V2
    }

    assert_true(
        MetricDecisionStatus.NEEDS_CLARIFICATION in statuses,
        "Adversarial 必须覆盖 Clarification。",
    )

    assert_true(
        MetricDecisionStatus.UNSUPPORTED in statuses,
        "Adversarial 必须覆盖 Unsupported Metric。",
    )

    assert_true(
        any(
            case.expected_plan.status
            == PlanDecisionStatus.UNSUPPORTED_SHAPE
            for case in SEMANTIC_ADVERSARIAL_CASES_V2
        ),
        "Adversarial 必须覆盖 Unsupported Query Shape。",
    )


def test_adversarial_unsupported_shapes_are_really_absent() -> None:
    matrix = load_plan_matrix()

    for case in SEMANTIC_ADVERSARIAL_CASES_V2:
        if (
            case.expected_plan.status
            != PlanDecisionStatus.UNSUPPORTED_SHAPE
        ):
            continue

        key = (
            case.expected_metric.metric_name,
            case.expected_intent.result_grain.value,
        )

        assert_true(
            key not in matrix,
            (
                f"{case.case_id} 标记 unsupported_shape，"
                f"但 Catalog 已存在 {key}。"
            ),
        )


def test_all_generalization_case_ids_and_questions_are_unique() -> None:
    cases = (
        *LOCKED_HOLDOUT_CASES_V2,
        *SEMANTIC_ADVERSARIAL_CASES_V2,
    )

    ids = [case.case_id for case in cases]
    questions = [
        normalize(case.question)
        for case in cases
    ]

    assert_equal(
        len(ids),
        len(set(ids)),
        "Generalization case_id 必须唯一。",
    )

    assert_equal(
        len(questions),
        len(set(questions)),
        "Generalization question 必须唯一。",
    )


def run_tests() -> None:
    tests = [
        test_holdout_has_exactly_one_case_per_metric,
        test_holdout_fingerprint_is_frozen,
        test_holdout_questions_do_not_duplicate_visible_cases,
        test_holdout_questions_are_not_exact_metadata_phrases,
        test_holdout_selected_plans_match_static_catalog,
        test_adversarial_case_count_and_split,
        test_adversarial_contains_expected_failure_modes,
        test_adversarial_unsupported_shapes_are_really_absent,
        test_all_generalization_case_ids_and_questions_are_unique,
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
    print("Generalization Cases V2 Static Test Summary")
    print(f"Total: {len(tests)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print("Locked Holdout Fingerprint:", LOCKED_HOLDOUT_FINGERPRINT)

    if failed > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    run_tests()
