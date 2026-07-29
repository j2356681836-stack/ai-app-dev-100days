from __future__ import annotations

from app.evaluation.semantic_fallback_calibration_cases_v2 import (
    SEMANTIC_FALLBACK_POSITIVE_CASES_V2,
)
from app.evaluation.question_signature_benchmark_v2 import (
    _expected_question_operator,
    evaluate_question_signature_case_v2,
)
from app.semantic_layer.metric_signature_v2 import (
    SignatureOperator,
    get_metric_signature_v2,
)
from app.semantic_layer.question_signature_v2 import (
    QuestionOperator,
)


def assert_equal(
    actual,
    expected,
    message: str,
) -> None:
    if actual != expected:
        raise AssertionError(
            f"{message}\n"
            f"Expected: {expected}\n"
            f"Actual: {actual}"
        )


def assert_true(
    condition: bool,
    message: str,
) -> None:
    if not condition:
        raise AssertionError(
            message
        )


def test_benchmark_uses_exactly_57_existing_fallback_cases() -> None:
    assert_equal(
        len(
            SEMANTIC_FALLBACK_POSITIVE_CASES_V2
        ),
        57,
        "Gate 5E-B 必须使用冻结的 57 Fallback Positive。",
    )


def test_metric_operator_mapping_is_structural_not_metric_specific() -> None:
    sum_signature = get_metric_signature_v2(
        "gmv"
    )
    count_signature = get_metric_signature_v2(
        "buyer_count"
    )
    divide_signature = get_metric_signature_v2(
        "aus"
    )

    assert_true(
        sum_signature is not None
        and count_signature is not None
        and divide_signature is not None,
        "Required signatures missing.",
    )

    assert_equal(
        sum_signature.operator,
        SignatureOperator.SUM,
        "GMV test setup wrong。",
    )

    assert_equal(
        _expected_question_operator(
            sum_signature
        ),
        QuestionOperator.SUM,
        "SUM operator mapping 错误。",
    )

    assert_equal(
        _expected_question_operator(
            count_signature
        ),
        QuestionOperator.COUNT,
        "COUNT operator mapping 错误。",
    )

    assert_equal(
        _expected_question_operator(
            divide_signature
        ),
        QuestionOperator.DIVIDE,
        "DIVIDE operator mapping 错误。",
    )


def test_case_evaluation_does_not_return_candidate_decision() -> None:
    result = (
        evaluate_question_signature_case_v2(
            SEMANTIC_FALLBACK_POSITIVE_CASES_V2[
                0
            ]
        )
    )

    assert_true(
        "matched_metric"
        not in result,
        "Gate 5E-B 不得提前输出 matched_metric。",
    )

    assert_true(
        "candidate_scores"
        not in result,
        "Gate 5E-B 不得提前做 Candidate Decision。",
    )


def test_all_19_metrics_are_present_three_times() -> None:
    counts = {}

    for case in (
        SEMANTIC_FALLBACK_POSITIVE_CASES_V2
    ):
        counts[
            case.metric_name
        ] = counts.get(
            case.metric_name,
            0,
        ) + 1

    assert_equal(
        len(counts),
        19,
        "Benchmark 应覆盖 19 Metrics。",
    )

    assert_true(
        all(
            count == 3
            for count in counts.values()
        ),
        "每个 Metric 应恰好 3 个 fallback cases。",
    )


def run_tests() -> None:
    tests = [
        test_benchmark_uses_exactly_57_existing_fallback_cases,
        test_metric_operator_mapping_is_structural_not_metric_specific,
        test_case_evaluation_does_not_return_candidate_decision,
        test_all_19_metrics_are_present_three_times,
    ]

    passed = 0
    failed = 0

    for test in tests:
        print("=" * 80)
        print(
            f"Running: {test.__name__}"
        )

        try:
            test()
            passed += 1
            print("[PASS]")
        except Exception as exc:
            failed += 1
            print("[FAIL]")
            print(exc)

    print("=" * 80)
    print(
        "Question Signature Benchmark V2 Test Summary"
    )
    print(
        f"Total: {len(tests)}"
    )
    print(
        f"Passed: {passed}"
    )
    print(
        f"Failed: {failed}"
    )
    print(
        "Benchmark Cases:",
        len(
            SEMANTIC_FALLBACK_POSITIVE_CASES_V2
        ),
    )

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    run_tests()
