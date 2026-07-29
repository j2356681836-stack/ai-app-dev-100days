from app.evaluation.generalization_cases_v2 import (
    LOCKED_HOLDOUT_CASES_V2,
    SEMANTIC_ADVERSARIAL_CASES_V2,
)
from app.evaluation.generalization_evaluator_v2 import (
    select_generalization_cases,
)


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(
            f"{message}\nExpected: {expected}\nActual: {actual}"
        )


def test_select_holdout_suite() -> None:
    assert_equal(
        select_generalization_cases("holdout"),
        LOCKED_HOLDOUT_CASES_V2,
        "holdout suite 选择错误。",
    )


def test_select_adversarial_suite() -> None:
    assert_equal(
        select_generalization_cases("adversarial"),
        SEMANTIC_ADVERSARIAL_CASES_V2,
        "adversarial suite 选择错误。",
    )


def test_select_all_suite() -> None:
    assert_equal(
        len(select_generalization_cases("all")),
        33,
        "all suite 应包含 19 Holdout + 14 Adversarial。",
    )


def test_unknown_suite_rejected() -> None:
    try:
        select_generalization_cases("unknown")
    except ValueError:
        return

    raise AssertionError(
        "Unknown Generalization Suite 必须被拒绝。"
    )


def run_tests() -> None:
    tests = [
        test_select_holdout_suite,
        test_select_adversarial_suite,
        test_select_all_suite,
        test_unknown_suite_rejected,
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
    print("Generalization Evaluator V2 Test Summary")
    print(f"Total: {len(tests)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    run_tests()
