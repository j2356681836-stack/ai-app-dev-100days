from __future__ import annotations

import app.text_to_sql.sql_generator as sql_generator
import app.text_to_sql.sql_repairer as sql_repairer


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(
            f"{message}\n"
            f"Expected: {expected}\n"
            f"Actual: {actual}"
        )


def test_generate_sql_preserves_prompt_and_raw_text_contract() -> None:
    captured = {}

    original_build_prompt = sql_generator.build_prompt
    original_chat_completion = sql_generator.chat_completion

    try:
        sql_generator.build_prompt = (
            lambda question, intent=None:
            f"PROMPT::{question}::{intent}"
        )

        def fake_chat_completion(**kwargs):
            captured.update(kwargs)
            return "SELECT 1"

        sql_generator.chat_completion = fake_chat_completion

        result = sql_generator.generate_sql(
            "q",
            intent={
                "dimension": "channel",
            },
        )

        assert_equal(
            result,
            "SELECT 1",
            "generate_sql 仍应返回 raw LLM text。",
        )

        assert_equal(
            captured["temperature"],
            0,
            "generate_sql temperature 应保持 0。",
        )

        assert_equal(
            captured["messages"][0]["content"],
            "PROMPT::q::{'dimension': 'channel'}",
            "Prompt 应原样交给 shared transport。",
        )

    finally:
        sql_generator.build_prompt = original_build_prompt
        sql_generator.chat_completion = original_chat_completion


def test_repair_sql_preserves_repair_prompt_and_raw_text_contract() -> None:
    captured = {}

    original_chat_completion = sql_repairer.chat_completion

    try:
        def fake_chat_completion(**kwargs):
            captured.update(kwargs)
            return "SELECT repaired"

        sql_repairer.chat_completion = fake_chat_completion

        result = sql_repairer.repair_sql(
            question="q",
            intent=None,
            sql="SELECT broken",
            error_message="boom",
            context="CTX",
        )

        assert_equal(
            result,
            "SELECT repaired",
            "repair_sql 仍应返回 raw LLM text。",
        )

        assert_equal(
            captured["temperature"],
            0,
            "repair_sql temperature 应保持 0。",
        )

        prompt = captured[
            "messages"
        ][0][
            "content"
        ]

        if "SELECT broken" not in prompt:
            raise AssertionError(
                "Repair prompt 必须保留原 SQL。"
            )

        if "boom" not in prompt:
            raise AssertionError(
                "Repair prompt 必须保留数据库错误。"
            )

    finally:
        sql_repairer.chat_completion = original_chat_completion


def run_tests() -> None:
    tests = [
        test_generate_sql_preserves_prompt_and_raw_text_contract,
        test_repair_sql_preserves_repair_prompt_and_raw_text_contract,
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
    print("LLM Transport Migration Test Summary")
    print(f"Total: {len(tests)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    run_tests()
