from __future__ import annotations

from app.evaluation.question_signature_adversarial_cases_v2 import (
    QUESTION_SIGNATURE_ADVERSARIAL_CASES_V2,
)
from app.evaluation.question_signature_adversarial_eval_v2 import (
    evaluate_question_signature_adversarial_case_v2,
    run_question_signature_adversarial_eval_v2,
)
from app.semantic_layer.metric_signature_v2 import (
    SemanticOperand,
)
from app.semantic_layer.question_signature_v2 import (
    QuestionOperator,
    QuestionSemanticSignatureV2,
)


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(
            f"{message}\nExpected: {expected}\nActual: {actual}"
        )


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_evaluator_accepts_injected_extractor() -> None:
    case = QUESTION_SIGNATURE_ADVERSARIAL_CASES_V2[
        38
    ]

    def fake_extractor(
        question: str,
    ) -> QuestionSemanticSignatureV2:
        return QuestionSemanticSignatureV2(
            operator=QuestionOperator.DIVIDE,
            left_operand=SemanticOperand.PAID_AMOUNT,
            right_operand=SemanticOperand.PAID_UNITS,
        )

    result = evaluate_question_signature_adversarial_case_v2(
        case,
        extractor=fake_extractor,
    )

    assert_true(
        result["core_exact"],
        "Injected extractor exact match 应通过。",
    )


def test_false_evidence_is_separate_from_missing_evidence() -> None:
    case = QUESTION_SIGNATURE_ADVERSARIAL_CASES_V2[
        46
    ]

    def empty_extractor(
        question: str,
    ) -> QuestionSemanticSignatureV2:
        return QuestionSemanticSignatureV2()

    result = evaluate_question_signature_adversarial_case_v2(
        case,
        extractor=empty_extractor,
    )

    assert_true(
        not result[
            "core_exact"
        ],
        "Missing expected operator 应导致 core not exact。",
    )

    assert_equal(
        result[
            "false_core_fields"
        ],
        [],
        "Missing evidence 不应误报为 false evidence。",
    )


def test_partial_case_penalizes_over_inference() -> None:
    case = QUESTION_SIGNATURE_ADVERSARIAL_CASES_V2[
        47
    ]

    def over_infer(
        question: str,
    ) -> QuestionSemanticSignatureV2:
        return QuestionSemanticSignatureV2(
            operator=QuestionOperator.DIVIDE,
            left_operand=SemanticOperand.PAID_AMOUNT,
            right_operand=SemanticOperand.PAID_BUYER,
        )

    result = evaluate_question_signature_adversarial_case_v2(
        case,
        extractor=over_infer,
    )

    assert_true(
        "operator"
        in result[
            "false_core_fields"
        ],
        "Partial case over-inference 必须记为 false operator evidence。",
    )

    assert_true(
        "left_operand"
        in result[
            "false_core_fields"
        ],
        "Partial case over-inference 必须记为 false left evidence。",
    )


def test_full_runner_can_use_fake_empty_extractor_without_real_fresh_run() -> None:
    def empty_extractor(
        question: str,
    ) -> QuestionSemanticSignatureV2:
        return QuestionSemanticSignatureV2()

    report = (
        run_question_signature_adversarial_eval_v2(
            extractor=empty_extractor
        )
    )

    assert_equal(
        report[
            "case_count"
        ],
        60,
        "Runner 应覆盖全部 60 cases。",
    )

    assert_equal(
        report[
            "dataset_role"
        ],
        "fresh_adversarial_first_run_only",
        "Fresh dataset role 不得漂移。",
    )

    assert_true(
        not report[
            "runtime_integration"
        ],
        "Fresh evaluator 不得接 Runtime。",
    )

    assert_true(
        not report[
            "candidate_decision"
        ],
        "Fresh evaluator 不得提前做 Candidate Decision。",
    )


def run_tests() -> None:
    tests = [
        test_evaluator_accepts_injected_extractor,
        test_false_evidence_is_separate_from_missing_evidence,
        test_partial_case_penalizes_over_inference,
        test_full_runner_can_use_fake_empty_extractor_without_real_fresh_run,
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
    print(
        "Question Signature Fresh Adversarial Eval V2 Test Summary"
    )
    print(f"Total: {len(tests)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(
        "IMPORTANT: real extractor was not executed on fresh cases."
    )

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    run_tests()
