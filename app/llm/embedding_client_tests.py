from __future__ import annotations

from types import SimpleNamespace

from app.llm.embedding_client import (
    EmbeddingTransportError,
    create_embeddings,
)


class FakeEmbeddings:
    def __init__(
        self,
        *,
        data=None,
    ):
        self.calls = []
        self.data = (
            data
            if data is not None
            else [
                SimpleNamespace(
                    index=0,
                    embedding=[
                        0.1,
                        0.2,
                    ],
                ),
                SimpleNamespace(
                    index=1,
                    embedding=[
                        0.3,
                        0.4,
                    ],
                ),
            ]
        )

    def create(
        self,
        *,
        model,
        input,
    ):
        self.calls.append(
            {
                "model": model,
                "input": input,
            }
        )

        return SimpleNamespace(
            data=self.data
        )


class FakeClient:
    def __init__(
        self,
        *,
        data=None,
    ):
        self.embeddings = FakeEmbeddings(
            data=data
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


def assert_raises(
    expected_error,
    fn,
    message: str,
) -> None:
    try:
        fn()
    except expected_error:
        return

    raise AssertionError(
        message
    )


def test_create_embeddings_uses_injected_client() -> None:
    client = FakeClient()

    vectors = create_embeddings(
        texts=[
            "指标A",
            "指标B",
        ],
        model="test-embedding-model",
        client=client,
    )

    assert_equal(
        vectors,
        [
            [0.1, 0.2],
            [0.3, 0.4],
        ],
        "Transport 应返回普通 Python float vectors。",
    )

    assert_equal(
        len(
            client.embeddings.calls
        ),
        1,
        "Batch Embedding 应只调用一次 injected client。",
    )


def test_create_embeddings_preserves_model_and_batch_input() -> None:
    client = FakeClient()

    create_embeddings(
        texts=[
            "metric-1",
            "metric-2",
        ],
        model="test-model",
        client=client,
    )

    call = client.embeddings.calls[0]

    assert_equal(
        call["model"],
        "test-model",
        "Model 应透传。",
    )

    assert_equal(
        call["input"],
        [
            "metric-1",
            "metric-2",
        ],
        "多个文本应作为一次 batch input 透传。",
    )


def test_create_embeddings_restores_index_order() -> None:
    client = FakeClient(
        data=[
            SimpleNamespace(
                index=1,
                embedding=[
                    0.3,
                    0.4,
                ],
            ),
            SimpleNamespace(
                index=0,
                embedding=[
                    0.1,
                    0.2,
                ],
            ),
        ]
    )

    vectors = create_embeddings(
        texts=[
            "A",
            "B",
        ],
        model="test-model",
        client=client,
    )

    assert_equal(
        vectors,
        [
            [0.1, 0.2],
            [0.3, 0.4],
        ],
        "Transport 应按 response index 恢复 input 顺序。",
    )


def test_create_embeddings_rejects_empty_input() -> None:
    assert_raises(
        EmbeddingTransportError,
        lambda: create_embeddings(
            texts=[],
            model="test-model",
            client=FakeClient(),
        ),
        "空 batch 必须 fail closed。",
    )

    assert_raises(
        EmbeddingTransportError,
        lambda: create_embeddings(
            texts=[
                "valid",
                "   ",
            ],
            model="test-model",
            client=FakeClient(),
        ),
        "空字符串必须 fail closed。",
    )


def test_create_embeddings_rejects_response_count_mismatch() -> None:
    client = FakeClient(
        data=[
            SimpleNamespace(
                index=0,
                embedding=[
                    0.1,
                    0.2,
                ],
            ),
        ]
    )

    assert_raises(
        EmbeddingTransportError,
        lambda: create_embeddings(
            texts=[
                "A",
                "B",
            ],
            model="test-model",
            client=client,
        ),
        "Response count 与 input count 不一致时必须 fail closed。",
    )


def test_create_embeddings_rejects_inconsistent_dimensions() -> None:
    client = FakeClient(
        data=[
            SimpleNamespace(
                index=0,
                embedding=[
                    0.1,
                    0.2,
                ],
            ),
            SimpleNamespace(
                index=1,
                embedding=[
                    0.3,
                    0.4,
                    0.5,
                ],
            ),
        ]
    )

    assert_raises(
        EmbeddingTransportError,
        lambda: create_embeddings(
            texts=[
                "A",
                "B",
            ],
            model="test-model",
            client=client,
        ),
        "不同维度的 vectors 必须 fail closed。",
    )


def run_tests() -> None:
    tests = [
        test_create_embeddings_uses_injected_client,
        test_create_embeddings_preserves_model_and_batch_input,
        test_create_embeddings_restores_index_order,
        test_create_embeddings_rejects_empty_input,
        test_create_embeddings_rejects_response_count_mismatch,
        test_create_embeddings_rejects_inconsistent_dimensions,
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
        "Embedding Shared Client Test Summary"
    )
    print(f"Total: {len(tests)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    run_tests()
