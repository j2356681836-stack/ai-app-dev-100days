from __future__ import annotations

from collections import Counter

import app.evaluation.semantic_calibration_v2 as calibration
from app.evaluation.semantic_calibration_v2 import (
    CalibrationExpectationType,
    SEMANTIC_CALIBRATION_CASES_V2,
    build_calibration_summary_v2,
    evaluate_semantic_calibration_case_v2,
)
from app.semantic_layer.metric_boundary_v2 import BoundaryOutcome


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(
            f"{message}\nExpected: {expected}\nActual: {actual}"
        )


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def by_id(case_id: str):
    return next(
        case
        for case in SEMANTIC_CALIBRATION_CASES_V2
        if case.case_id == case_id
    )


def test_calibration_contains_five_sources() -> None:
    assert_equal(
        {case.source for case in SEMANTIC_CALIBRATION_CASES_V2},
        {
            "visible",
            "semantic_adversarial",
            "semantic_fallback_positive",
            "metadata_example",
            "metadata_negative",
        },
        "Calibration Sources 不完整。",
    )


def test_initial_locked_holdout_is_excluded() -> None:
    assert_true(
        all(
            "holdout" not in case.source
            and not case.case_id.startswith("holdout_")
            for case in SEMANTIC_CALIBRATION_CASES_V2
        ),
        "Initial Locked Holdout 不得进入 Calibration。",
    )


def test_repeat_metadata_examples_now_agree_with_boundary() -> None:
    repeat_examples = [
        case
        for case in SEMANTIC_CALIBRATION_CASES_V2
        if (
            case.source == "metadata_example"
            and case.expected_metric == "repeat_customer_count"
        )
    ]

    failures = []
    for case in repeat_examples:
        decision = calibration.evaluate_metric_boundary_v2(case.question)
        if decision.outcome != BoundaryOutcome.CONTINUE:
            failures.append(
                (case.question, decision.model_dump(mode="json"))
            )

    assert_equal(
        failures,
        [],
        "repeat_customer_count Metadata examples 必须与 Boundary 一致。",
    )


def test_brand_paid_new_example_is_not_ambiguous() -> None:
    case = by_id(
        "metadata_example__brand_paid_new_customer_count__01"
    )
    decision = calibration.evaluate_metric_boundary_v2(case.question)
    assert_equal(
        decision.outcome,
        BoundaryOutcome.CONTINUE,
        "品牌支付新客已经明确 Brand 口径。",
    )


def test_negative_other_metric_is_structured() -> None:
    case = by_id("metadata_negative__gmv__01")
    assert_equal(
        case.expectation_type,
        CalibrationExpectationType.NEGATIVE_OTHER_METRIC,
        "GMV negative 毛利额应为 other_metric。",
    )
    assert_equal(case.expected_metric, "gross_margin", "映射错误。")


def test_negative_unsupported_semantics_is_structured() -> None:
    case = by_id("metadata_negative__gmv__04")
    assert_equal(
        case.expectation_type,
        CalibrationExpectationType.NEGATIVE_UNSUPPORTED_SEMANTICS,
        "扣除退款后的销售额应是 unsupported semantics。",
    )


def test_negative_unsupported_shape_keeps_metric_correct() -> None:
    case = by_id("metadata_negative__roi__04")
    assert_equal(
        case.expectation_type,
        CalibrationExpectationType.NEGATIVE_UNSUPPORTED_SHAPE,
        "地区 ROI 应为 unsupported shape。",
    )
    assert_equal(case.expected_metric, "roi", "Metric 仍应为 roi。")
    assert_equal(case.result_grain, "region", "Grain 应为 region。")


def test_negative_ambiguity_is_structured() -> None:
    case = next(
        c
        for c in SEMANTIC_CALIBRATION_CASES_V2
        if c.expectation_type
        == CalibrationExpectationType.NEGATIVE_AMBIGUITY
    )
    assert_true(
        len(case.acceptable_candidates) >= 2,
        "Negative ambiguity 必须有候选。",
    )


def test_unclassified_negative_is_not_scored_as_top1_accuracy() -> None:
    case = next(
        c
        for c in SEMANTIC_CALIBRATION_CASES_V2
        if c.expectation_type
        == CalibrationExpectationType.NEGATIVE_UNCLASSIFIED
    )

    original_search = calibration.rank_metric_candidates_by_embedding_v2
    calibration.rank_metric_candidates_by_embedding_v2 = (
        lambda question, top_k=6: {
            "retrieval_status": "ok",
            "candidates": [
                {
                    "name": case.source_metric,
                    "chinese_name": "source",
                    "score": 0.9,
                },
                {
                    "name": "other",
                    "chinese_name": "other",
                    "score": 0.5,
                },
            ],
        }
    )

    try:
        result = evaluate_semantic_calibration_case_v2(case)
        assert_equal(
            result["top1_correct"],
            None,
            "Unclassified negative 不得进入 Top1 accuracy。",
        )
        assert_equal(
            result["source_metric_top1"],
            True,
            "应保留 source metric Top1 诊断。",
        )
    finally:
        calibration.rank_metric_candidates_by_embedding_v2 = original_search


def test_fallback_positive_is_scored_as_matched() -> None:
    case = next(
        c
        for c in SEMANTIC_CALIBRATION_CASES_V2
        if c.source == "semantic_fallback_positive"
    )
    assert_equal(
        case.expectation_type,
        CalibrationExpectationType.MATCHED,
        "Fallback Positive 应为 matched。",
    )


def test_summary_separates_fallback_and_unclassified() -> None:
    fake_results = [
        {
            "source": "semantic_fallback_positive",
            "expectation": {"expectation_type": "matched"},
            "top1_correct": True,
            "boundary_correct": True,
            "source_metric_top1": None,
        },
        {
            "source": "metadata_negative",
            "expectation": {
                "expectation_type": "negative_unclassified"
            },
            "top1_correct": None,
            "boundary_correct": None,
            "source_metric_top1": True,
        },
    ]

    summary = build_calibration_summary_v2(fake_results)
    assert_equal(
        summary["semantic_fallback_positive"]["total"],
        1,
        "Fallback summary 错误。",
    )
    assert_equal(
        summary["negative_unclassified_diagnostic"]["total"],
        1,
        "Unclassified diagnostic 错误。",
    )
    assert_equal(
        summary["raw_top1_labeled"]["total"],
        1,
        "Unclassified 不得进入 labeled accuracy。",
    )
    assert_equal(summary["threshold_policy"], None, "不得设 threshold。")
    assert_equal(summary["gap_policy"], None, "不得设 gap policy。")


def test_metadata_negative_relation_types_are_visible() -> None:
    types = Counter(
        case.expectation_type.value
        for case in SEMANTIC_CALIBRATION_CASES_V2
        if case.source == "metadata_negative"
    )

    required = {
        "negative_other_metric",
        "negative_unsupported_semantics",
        "negative_unsupported_shape",
        "negative_ambiguity",
        "negative_unclassified",
    }

    assert_true(
        required.issubset(types),
        f"Relation types 不完整：{dict(types)}",
    )


def run_tests() -> None:
    tests = [
        test_calibration_contains_five_sources,
        test_initial_locked_holdout_is_excluded,
        test_repeat_metadata_examples_now_agree_with_boundary,
        test_brand_paid_new_example_is_not_ambiguous,
        test_negative_other_metric_is_structured,
        test_negative_unsupported_semantics_is_structured,
        test_negative_unsupported_shape_keeps_metric_correct,
        test_negative_ambiguity_is_structured,
        test_unclassified_negative_is_not_scored_as_top1_accuracy,
        test_fallback_positive_is_scored_as_matched,
        test_summary_separates_fallback_and_unclassified,
        test_metadata_negative_relation_types_are_visible,
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
    print("Semantic Calibration V2 Gate 5C.1 Test Summary")
    print(f"Total: {len(tests)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Calibration Cases: {len(SEMANTIC_CALIBRATION_CASES_V2)}")

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    run_tests()
