from __future__ import annotations

from app.evaluation.question_semantic_parser_regression_v2 import (
    evaluate_parser_regression_case_v2,
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


class FakeRole:
    def __init__(
        self,
        value: str,
    ) -> None:
        self.value = value


class FakeCase:
    def __init__(
        self,
        *,
        case_id: str,
        role: str,
        question: str,
        expected: QuestionSemanticSignatureV2,
    ) -> None:
        self.case_id = case_id
        self.role = FakeRole(
            role
        )
        self.family = "acceptance_test"
        self.question = question
        self.expected = expected


def fake_exact_parsed_parser(
    question: str,
) -> QuestionSemanticParseResultV2:
    return QuestionSemanticParseResultV2(
        status=QuestionSemanticParseStatusV2.PARSED,
        signature=QuestionSemanticSignatureV2(),
        deterministic_evidence=DeterministicQuestionEvidenceV2(),
    )


def fake_multiple_intents_parser(
    question: str,
) -> QuestionSemanticParseResultV2:
    return QuestionSemanticParseResultV2(
        status=QuestionSemanticParseStatusV2.MULTIPLE_INTENTS,
        signature=None,
        deterministic_evidence=DeterministicQuestionEvidenceV2(),
    )


def fake_parse_failed_parser(
    question: str,
) -> QuestionSemanticParseResultV2:
    return QuestionSemanticParseResultV2(
        status=QuestionSemanticParseStatusV2.PARSE_FAILED,
        signature=None,
        deterministic_evidence=DeterministicQuestionEvidenceV2(),
        error="controlled_test_failure",
    )


def test_parsed_full_exact_passes_acceptance() -> None:
    case = FakeCase(
        case_id="ACCEPT-001",
        role="supported_rephrase",
        question="测试普通结构",
        expected=QuestionSemanticSignatureV2(),
    )

    row = evaluate_parser_regression_case_v2(
        case,
        parser=fake_exact_parsed_parser,
    )

    assert_equal(
        row[
            "full_exact"
        ],
        True,
        "普通 PARSED case 应保持 full exact。",
    )

    assert_equal(
        row[
            "acceptance_pass"
        ],
        True,
        "PARSED + full exact 应通过 behavioral acceptance。",
    )


def test_multiple_intents_can_pass_acceptance_without_full_exact() -> None:
    case = FakeCase(
        case_id="ACCEPT-002",
        role="collision",
        question="渠道投放既看产出，也看新客",
        expected=QuestionSemanticSignatureV2(
            intrinsic_partition="channel",
        ),
    )

    row = evaluate_parser_regression_case_v2(
        case,
        parser=fake_multiple_intents_parser,
    )

    assert_equal(
        row[
            "full_exact"
        ],
        False,
        "MULTIPLE_INTENTS 可以保留 structural diagnostic FAIL。",
    )

    assert_equal(
        row[
            "multi_intent_correct"
        ],
        True,
        "Collision 应正确识别为 MULTIPLE_INTENTS。",
    )

    assert_equal(
        row[
            "acceptance_pass"
        ],
        True,
        (
            "正确 fail-closed 的 MULTIPLE_INTENTS "
            "不得因 full_exact=False 而行为验收失败。"
        ),
    )


def test_parse_failed_non_collision_fails_acceptance() -> None:
    case = FakeCase(
        case_id="ACCEPT-003",
        role="supported_rephrase",
        question="测试解析失败",
        expected=QuestionSemanticSignatureV2(),
    )

    row = evaluate_parser_regression_case_v2(
        case,
        parser=fake_parse_failed_parser,
    )

    assert_equal(
        row[
            "multi_intent_correct"
        ],
        True,
        (
            "普通 case 的 PARSE_FAILED 仍可能得到 "
            "multi_intent_correct=True，"
            "因此该字段不能代表整体验收。"
        ),
    )

    assert_equal(
        row[
            "acceptance_pass"
        ],
        False,
        "普通 case PARSE_FAILED 必须 behavioral acceptance FAIL。",
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


def test_regression_keeps_normalized_source_fingerprint() -> None:
    report = run_question_semantic_parser_regression_v2(
        parser=fake_empty_parser
    )

    assert_equal(
        report[
            "source_adversarial_fingerprint"
        ],
        "9533ecc9c95172cd8565d6f3a8b925422e74048b188291c3c9f2f25745958bec",
        "Normalized adversarial fingerprint 不得漂移。",
    )

    assert_equal(
        report[
            "normalized_adversarial_fingerprint"
        ],
        "9533ecc9c95172cd8565d6f3a8b925422e74048b188291c3c9f2f25745958bec",
        "Regression 必须明确记录 normalized fingerprint。",
    )


def test_regression_preserves_pre_normalization_provenance() -> None:
    report = run_question_semantic_parser_regression_v2(
        parser=fake_empty_parser
    )

    assert_equal(
        report[
            "pre_normalization_adversarial_fingerprint"
        ],
        "eda72cdc4762054ba2bfaa007b56ee422f0c99cdc2145a1eaea54f65e739a929",
        "必须保留 Day74 pre-normalization observed evidence provenance。",
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
        test_regression_keeps_normalized_source_fingerprint,
        test_regression_preserves_pre_normalization_provenance,
        test_regression_contains_60_cases,
        test_parsed_full_exact_passes_acceptance,
        test_multiple_intents_can_pass_acceptance_without_full_exact,
        test_parse_failed_non_collision_fails_acceptance,
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
