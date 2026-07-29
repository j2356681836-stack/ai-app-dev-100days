from __future__ import annotations

from app.evaluation.question_semantic_parser_regression_v2 import (
    run_question_semantic_parser_regression_v2,
)
from app.semantic_layer.question_semantic_parser_v2 import (
    DeterministicQuestionEvidenceV2,
    QuestionSemanticParseResultV2,
    QuestionSemanticParseStatusV2,
)
from app.semantic_layer.question_signature_v2 import (
    QuestionSemanticSignatureV2,
)


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(
            f"{message}\n"
            f"Expected: {expected}\n"
            f"Actual: {actual}"
        )


def fake_empty_parser(
    question: str,
) -> QuestionSemanticParseResultV2:
    return QuestionSemanticParseResultV2(
        status=QuestionSemanticParseStatusV2.PARSED,
        signature=QuestionSemanticSignatureV2(),
        deterministic_evidence=DeterministicQuestionEvidenceV2(),
    )


def test_regression_uses_observed_role_not_fresh_role() -> None:
    report = run_question_semantic_parser_regression_v2(
        parser=fake_empty_parser
    )

    assert_equal(
        report[
            "dataset_role"
        ],
        "observed_adversarial_regression_not_fresh_generalization",
        "Gate 5E-B2 observed set 不得重新标 fresh。",
    )

    assert_equal(
        report[
            "fresh_generalization_claim"
        ],
        False,
        "Regression 不得宣称 fresh generalization。",
    )


def test_regression_keeps_frozen_source_fingerprint() -> None:
    report = run_question_semantic_parser_regression_v2(
        parser=fake_empty_parser
    )

    assert_equal(
        report[
            "source_adversarial_fingerprint"
        ],
        "eda72cdc4762054ba2bfaa007b56ee422f0c99cdc2145a1eaea54f65e739a929",
        "Observed adversarial fingerprint 不得漂移。",
    )


def test_regression_contains_60_cases() -> None:
    report = run_question_semantic_parser_regression_v2(
        parser=fake_empty_parser
    )

    assert_equal(
        report[
            "case_count"
        ],
        60,
        "Regression 必须覆盖 frozen 60 cases。",
    )


def run_tests() -> None:
    tests = [
        test_regression_uses_observed_role_not_fresh_role,
        test_regression_keeps_frozen_source_fingerprint,
        test_regression_contains_60_cases,
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
        "Question Semantic Parser Regression V2 Test Summary"
    )
    print(f"Total: {len(tests)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    run_tests()
