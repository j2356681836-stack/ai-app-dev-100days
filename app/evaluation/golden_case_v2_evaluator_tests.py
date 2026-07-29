from app.evaluation.golden_case_v2_evaluator import (
    build_summary,
    evaluate_case_v2,
    run_evaluation_v2,
)
from app.evaluation.golden_case_v2_models import (
    MetricDecisionStatus,
    PlanDecisionStatus,
)
from app.evaluation.golden_cases_v2 import (
    GOLDEN_CASES_V2,
)


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


def get_case(case_id: str):
    return next(
        case
        for case in GOLDEN_CASES_V2.cases
        if case.case_id == case_id
    )


def test_evaluator_runs_all_30_cases() -> None:
    results = run_evaluation_v2()

    assert_equal(
        len(results),
        30,
        "Evaluator 必须覆盖 Gate 3A 的 30 Cases。",
    )


def test_clarification_case_stops_downstream_scoring() -> None:
    case = get_case(
        "reg_new_customer_ambiguity_001"
    )

    result = evaluate_case_v2(case)

    assert_equal(
        case.expected_metric.status,
        MetricDecisionStatus.NEEDS_CLARIFICATION,
        "测试前提必须是 Clarification Case。",
    )

    assert_equal(
        result["layer_results"]["intent_passed"],
        None,
        "Clarification 后不应继续评分 Intent。",
    )

    assert_equal(
        result["layer_results"]["plan_passed"],
        None,
        "Clarification 后不应继续评分 Plan。",
    )


def test_unsupported_shape_is_scored_as_plan_behavior() -> None:
    case = get_case(
        "reg_roi_region_shape_001"
    )

    result = evaluate_case_v2(case)

    assert_equal(
        case.expected_plan.status,
        PlanDecisionStatus.UNSUPPORTED_SHAPE,
        "测试前提必须是 Unsupported Shape。",
    )

    assert_true(
        result["layer_results"]["metric_passed"]
        is not None,
        "Unsupported Shape 仍应评分 Metric。",
    )

    assert_true(
        result["layer_results"]["intent_passed"]
        is not None,
        "Unsupported Shape 仍应评分 Intent。",
    )

    assert_true(
        result["layer_results"]["plan_passed"]
        is not None,
        "Unsupported Shape 仍应评分 Plan。",
    )


def test_summary_has_required_metrics() -> None:
    summary = build_summary(
        run_evaluation_v2()
    )

    required = {
        "overall_pass_rate",
        "metric",
        "intent_shape",
        "grain",
        "plan",
        "clarification",
        "unsupported_shape",
        "failure_taxonomy",
        "splits",
    }

    assert_true(
        required.issubset(
            summary.keys()
        ),
        "Summary 缺少 Day74 要求的分层指标。",
    )


def test_summary_denominators_are_semantically_correct() -> None:
    results = run_evaluation_v2()
    summary = build_summary(results)

    matched_cases = [
        case
        for case in GOLDEN_CASES_V2.cases
        if (
            case.expected_metric.status
            == MetricDecisionStatus.MATCHED
        )
    ]

    clarification_cases = [
        case
        for case in GOLDEN_CASES_V2.cases
        if (
            case.expected_metric.status
            == MetricDecisionStatus.NEEDS_CLARIFICATION
        )
    ]

    unsupported_shape_cases = [
        case
        for case in GOLDEN_CASES_V2.cases
        if (
            case.expected_plan.status
            == PlanDecisionStatus.UNSUPPORTED_SHAPE
        )
    ]

    assert_equal(
        summary["metric"]["total"],
        30,
        "Metric Accuracy denominator 应为全部 30 Cases。",
    )

    assert_equal(
        summary["intent_shape"]["total"],
        len(matched_cases),
        "Intent denominator 应只包含 Expected Metric=matched Cases。",
    )

    assert_equal(
        summary["plan"]["total"],
        len(matched_cases),
        "Plan denominator 应只包含 Expected Metric=matched Cases。",
    )

    assert_equal(
        summary["clarification"]["total"],
        len(clarification_cases),
        "Clarification denominator 错误。",
    )

    assert_equal(
        summary["unsupported_shape"]["total"],
        len(unsupported_shape_cases),
        "Unsupported Shape denominator 错误。",
    )


def test_failure_taxonomy_matches_case_mismatches() -> None:
    results = run_evaluation_v2()
    summary = build_summary(results)

    mismatch_total = sum(
        len(item["mismatches"])
        for item in results
    )

    taxonomy_total = sum(
        summary["failure_taxonomy"].values()
    )

    assert_equal(
        taxonomy_total,
        mismatch_total,
        "Failure Taxonomy 必须完整覆盖所有 mismatch。",
    )


def test_split_summary_matches_19_plus_11() -> None:
    summary = build_summary(
        run_evaluation_v2()
    )

    assert_equal(
        summary["splits"]["development"]["total"],
        19,
        "Development denominator 应为 19。",
    )

    assert_equal(
        summary["splits"]["regression"]["total"],
        11,
        "Regression denominator 应为 11。",
    )


def test_evaluator_does_not_require_sql_outputs() -> None:
    result = evaluate_case_v2(
        get_case(
            "dev_gmv_channel_001"
        )
    )

    forbidden = {
        "sql",
        "table",
        "answer",
        "rows",
    }

    assert_true(
        forbidden.isdisjoint(
            result["actual"].keys()
        ),
        "Day74 Evaluator 不得依赖 SQL / DB / Answer。",
    )



def test_unspecified_optional_intent_fields_are_not_scored() -> None:
    case = get_case(
        "dev_gross_margin_overall_001"
    )

    assert_equal(
        case.expected_intent.ranking_type,
        None,
        "测试前提：Case 没有声明 ranking_type。",
    )

    result = evaluate_case_v2(case)

    fake_mismatches = [
        item
        for item in result["mismatches"]
        if item["type"] in {
            "ranking_type_mismatch",
            "sort_direction_mismatch",
            "limit_mismatch",
        }
    ]

    assert_equal(
        fake_mismatches,
        [],
        (
            "未声明的 Optional Intent 字段不得被当成 "
            "expected=None 强制比较。"
        ),
    )

def run_tests() -> None:
    tests = [
        test_evaluator_runs_all_30_cases,
        test_clarification_case_stops_downstream_scoring,
        test_unsupported_shape_is_scored_as_plan_behavior,
        test_summary_has_required_metrics,
        test_summary_denominators_are_semantically_correct,
        test_failure_taxonomy_matches_case_mismatches,
        test_split_summary_matches_19_plus_11,
        test_evaluator_does_not_require_sql_outputs,
        test_unspecified_optional_intent_fields_are_not_scored,
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
    print("Golden Case V2 Evaluator Test Summary")
    print(f"Total: {len(tests)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    run_tests()
