from __future__ import annotations

from collections import Counter

from app.evaluation.question_signature_adversarial_cases_v2 import (
    QUESTION_SIGNATURE_ADVERSARIAL_CASES_V2,
    QuestionSignatureCaseRoleV2,
    canonical_question_signature_adversarial_cases_v2,
    question_signature_adversarial_fingerprint_v2,
)


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(
            f"{message}\nExpected: {expected}\nActual: {actual}"
        )


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_case_set_has_exactly_60_cases() -> None:
    assert_equal(
        len(QUESTION_SIGNATURE_ADVERSARIAL_CASES_V2),
        60,
        "Fresh adversarial set 必须固定为 60 cases。",
    )


def test_case_ids_and_questions_are_unique() -> None:
    case_ids = [
        case.case_id
        for case in QUESTION_SIGNATURE_ADVERSARIAL_CASES_V2
    ]
    questions = [
        case.question
        for case in QUESTION_SIGNATURE_ADVERSARIAL_CASES_V2
    ]

    assert_equal(
        len(case_ids),
        len(set(case_ids)),
        "case_id 必须唯一。",
    )
    assert_equal(
        len(questions),
        len(set(questions)),
        "question 必须唯一。",
    )


def test_role_coverage_is_nontrivial() -> None:
    counts = Counter(
        case.role
        for case in QUESTION_SIGNATURE_ADVERSARIAL_CASES_V2
    )

    for role in QuestionSignatureCaseRoleV2:
        assert_true(
            counts[role] > 0,
            f"缺少 role: {role.value}",
        )

    assert_true(
        counts[
            QuestionSignatureCaseRoleV2.SUPPORTED_REPHRASE
        ] >= 40,
        "Supported/fresh phrasing coverage 太少。",
    )


def test_partial_and_collision_cases_do_not_smuggle_metric_ids() -> None:
    for case in QUESTION_SIGNATURE_ADVERSARIAL_CASES_V2:
        dumped = case.model_dump(
            mode="json"
        )

        assert_true(
            "metric_name"
            not in dumped,
            "Fresh case contract 不得依赖 expected metric id。",
        )


def test_fingerprint_is_deterministic() -> None:
    assert_equal(
        canonical_question_signature_adversarial_cases_v2(),
        canonical_question_signature_adversarial_cases_v2(),
        "Canonical payload 必须 deterministic。",
    )

    fp_a = question_signature_adversarial_fingerprint_v2()
    fp_b = question_signature_adversarial_fingerprint_v2()

    assert_equal(
        fp_a,
        fp_b,
        "Fresh adversarial fingerprint 必须 deterministic。",
    )
    assert_equal(
        len(fp_a),
        64,
        "SHA-256 fingerprint 应为 64 hex chars。",
    )


def run_tests() -> None:
    tests = [
        test_case_set_has_exactly_60_cases,
        test_case_ids_and_questions_are_unique,
        test_role_coverage_is_nontrivial,
        test_partial_and_collision_cases_do_not_smuggle_metric_ids,
        test_fingerprint_is_deterministic,
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
        "Question Signature Fresh Adversarial Cases V2 Test Summary"
    )
    print(f"Total: {len(tests)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(
        "Cases:",
        len(QUESTION_SIGNATURE_ADVERSARIAL_CASES_V2),
    )
    print(
        "Fingerprint:",
        question_signature_adversarial_fingerprint_v2(),
    )

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    run_tests()
