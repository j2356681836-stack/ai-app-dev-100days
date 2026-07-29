from __future__ import annotations

from app.evaluation.generalization_cases_v2 import LOCKED_HOLDOUT_CASES_V2
from app.evaluation.golden_cases_v2 import GOLDEN_CASES_V2
from app.evaluation.semantic_fallback_calibration_cases_v2 import (
    SEMANTIC_FALLBACK_POSITIVE_CASES_V2,
)
from app.semantic_layer.metric_boundary_v2 import (
    BoundaryOutcome,
    evaluate_metric_boundary_v2,
)
from app.semantic_layer.metric_loader_v2 import (
    load_metrics_v2,
    search_metric_candidates_v2,
)


EXPECTED_METRICS = {
    "gmv", "gross_margin", "gross_margin_rate", "refund_rate", "roi", "cac",
    "brand_paid_new_customer_count", "channel_paid_new_customer_count",
    "repeat_customer_rate", "member_gmv_share", "buyer_count", "order_count",
    "units_sold", "spending_per_buyer", "ipt", "aus", "purchase_frequency",
    "repeat_customer_count", "multi_order_customer_count",
}


def normalize(text: str) -> str:
    return "".join(text.casefold().split())


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(
            f"{message}\nExpected: {expected}\nActual: {actual}"
        )


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_exactly_three_fallback_cases_per_metric() -> None:
    counts = {}
    for case in SEMANTIC_FALLBACK_POSITIVE_CASES_V2:
        counts[case.metric_name] = counts.get(case.metric_name, 0) + 1

    assert_equal(set(counts), EXPECTED_METRICS, "必须覆盖 19 Metrics。")
    assert_true(
        all(count == 3 for count in counts.values()),
        f"每 Metric 应 3 条，实际：{counts}",
    )
    assert_equal(
        len(SEMANTIC_FALLBACK_POSITIVE_CASES_V2),
        57,
        "总数必须为 57。",
    )


def test_fallback_cases_are_boundary_continue() -> None:
    failures = []
    for case in SEMANTIC_FALLBACK_POSITIVE_CASES_V2:
        decision = evaluate_metric_boundary_v2(case.question)
        if decision.outcome != BoundaryOutcome.CONTINUE:
            failures.append(
                (case.case_id, case.question, decision.model_dump(mode="json"))
            )
    assert_equal(failures, [], "Fallback Positive 不得被 Boundary short-circuit。")


def test_fallback_cases_miss_exact_v2_metric_matcher() -> None:
    failures = []
    for case in SEMANTIC_FALLBACK_POSITIVE_CASES_V2:
        candidates = search_metric_candidates_v2(case.question)
        if candidates:
            failures.append(
                (
                    case.case_id,
                    case.question,
                    [item.get("name") for item in candidates],
                )
            )
    assert_equal(
        failures,
        [],
        "Fallback Positive 必须 miss exact name/chinese_name/alias matcher。",
    )


def test_fallback_questions_do_not_copy_visible_or_initial_holdout() -> None:
    blocked = {
        normalize(case.question)
        for case in GOLDEN_CASES_V2.cases
    }
    blocked.update(
        normalize(case.question)
        for case in LOCKED_HOLDOUT_CASES_V2
    )
    duplicates = [
        case.question
        for case in SEMANTIC_FALLBACK_POSITIVE_CASES_V2
        if normalize(case.question) in blocked
    ]
    assert_equal(
        duplicates,
        [],
        "Fallback Positive 不得复制 Visible / Initial Holdout 原句。",
    )


def test_fallback_questions_do_not_copy_metadata_phrases() -> None:
    phrases = set()
    for metric in load_metrics_v2():
        for key in ("name", "chinese_name"):
            value = metric.get(key)
            if value:
                phrases.add(normalize(str(value)))
        for key in ("aliases", "examples", "negative_examples"):
            for value in metric.get(key, []):
                phrases.add(normalize(str(value)))

    duplicates = [
        case.question
        for case in SEMANTIC_FALLBACK_POSITIVE_CASES_V2
        if normalize(case.question) in phrases
    ]
    assert_equal(duplicates, [], "Fallback Positive 不得复制 Metadata 原句。")


def test_case_ids_and_questions_are_unique() -> None:
    ids = [case.case_id for case in SEMANTIC_FALLBACK_POSITIVE_CASES_V2]
    questions = [
        normalize(case.question)
        for case in SEMANTIC_FALLBACK_POSITIVE_CASES_V2
    ]
    assert_equal(len(ids), len(set(ids)), "case_id 必须唯一。")
    assert_equal(len(questions), len(set(questions)), "question 必须唯一。")


def run_tests() -> None:
    tests = [
        test_exactly_three_fallback_cases_per_metric,
        test_fallback_cases_are_boundary_continue,
        test_fallback_cases_miss_exact_v2_metric_matcher,
        test_fallback_questions_do_not_copy_visible_or_initial_holdout,
        test_fallback_questions_do_not_copy_metadata_phrases,
        test_case_ids_and_questions_are_unique,
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
    print("Semantic Fallback Calibration Cases V2 Test Summary")
    print(f"Total: {len(tests)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Cases: {len(SEMANTIC_FALLBACK_POSITIVE_CASES_V2)}")

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    run_tests()
