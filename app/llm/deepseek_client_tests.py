from __future__ import annotations

from types import SimpleNamespace

from app.llm.deepseek_client import (
    DEEPSEEK_MODEL,
    chat_completion,
)


class FakeCompletions:
    def __init__(self):
        self.calls = []

    def create(
        self,
        *,
        model,
        messages,
        temperature,
    ):
        self.calls.append(
            {
                "model": model,
                "messages": messages,
                "temperature": temperature,
            }
        )

        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content="fake-response"
                    )
                )
            ]
        )


class FakeClient:
    def __init__(self):
        self.completions = FakeCompletions()
        self.chat = SimpleNamespace(
            completions=self.completions
        )


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(
            f"{message}\n"
            f"Expected: {expected}\n"
            f"Actual: {actual}"
        )


def test_chat_completion_uses_injected_client() -> None:
    client = FakeClient()

    result = chat_completion(
        messages=[
            {
                "role": "user",
                "content": "hello",
            }
        ],
        client=client,
    )

    assert_equal(
        result,
        "fake-response",
        "Transport 应返回 assistant raw text。",
    )

    assert_equal(
        len(
            client.completions.calls
        ),
        1,
        "Injected client 应只调用一次。",
    )


def test_chat_completion_preserves_model_messages_temperature() -> None:
    client = FakeClient()

    chat_completion(
        model="test-model",
        messages=[
            {
                "role": "system",
                "content": "s",
            },
            {
                "role": "user",
                "content": "u",
            },
        ],
        temperature=0,
        client=client,
    )

    call = client.completions.calls[0]

    assert_equal(
        call["model"],
        "test-model",
        "Model 应透传。",
    )

    assert_equal(
        call["temperature"],
        0,
        "Temperature 应透传。",
    )

    assert_equal(
        call["messages"][1]["content"],
        "u",
        "Messages 应透传。",
    )


def test_default_model_is_non_empty() -> None:
    if not DEEPSEEK_MODEL:
        raise AssertionError(
            "DEEPSEEK_MODEL must be non-empty."
        )


def run_tests() -> None:
    tests = [
        test_chat_completion_uses_injected_client,
        test_chat_completion_preserves_model_messages_temperature,
        test_default_model_is_non_empty,
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
    print("DeepSeek Shared Client Test Summary")
    print(f"Total: {len(tests)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    run_tests()
