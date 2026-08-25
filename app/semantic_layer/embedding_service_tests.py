from __future__ import annotations

import os

from app.semantic_layer.embedding_service import (
    DEFAULT_LOCAL_EMBEDDING_MODEL,
    EmbeddingServiceError,
    LOCAL_EMBEDDING_PROVIDER,
    OPENAI_COMPATIBLE_EMBEDDING_PROVIDER,
    embed_text,
    embed_texts,
    resolve_embedding_model,
    resolve_embedding_provider,
)


class FakeLocalModel:
    def __init__(self):
        self.calls = []

    def encode(
        self,
        texts,
    ):
        self.calls.append(
            list(
                texts
            )
        )

        return [
            [
                float(index),
                float(index + 1),
            ]
            for index, _ in enumerate(
                texts,
                start=1,
            )
        ]


class FakeRemoteEmbedder:
    def __init__(self):
        self.calls = []

    def __call__(
        self,
        *,
        texts,
        model,
    ):
        self.calls.append(
            {
                "texts": tuple(
                    texts
                ),
                "model": model,
            }
        )

        return [
            [
                0.1,
                0.2,
            ]
            for _ in texts
        ]


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


def _with_env(
    updates: dict[str, str | None],
    fn,
):
    original = {
        key: os.environ.get(
            key
        )
        for key in updates
    }

    try:
        for key, value in updates.items():
            if value is None:
                os.environ.pop(
                    key,
                    None,
                )
            else:
                os.environ[
                    key
                ] = value

        return fn()
    finally:
        for key, value in original.items():
            if value is None:
                os.environ.pop(
                    key,
                    None,
                )
            else:
                os.environ[
                    key
                ] = value


def test_default_provider_remains_local() -> None:
    result = _with_env(
        {
            "AI_EMBEDDING_PROVIDER": None,
        },
        lambda: resolve_embedding_provider(),
    )

    assert_equal(
        result,
        LOCAL_EMBEDDING_PROVIDER,
        "未配置 Provider 时必须保持现有 local 行为。",
    )


def test_invalid_provider_fails_closed() -> None:
    assert_raises(
        EmbeddingServiceError,
        lambda: resolve_embedding_provider(
            "unknown"
        ),
        "未知 Provider 必须 fail closed。",
    )


def test_local_default_model_remains_bge_small() -> None:
    result = _with_env(
        {
            "AI_EMBEDDING_MODEL": None,
        },
        lambda: resolve_embedding_model(
            provider=LOCAL_EMBEDDING_PROVIDER,
        ),
    )

    assert_equal(
        result,
        DEFAULT_LOCAL_EMBEDDING_MODEL,
        "Local 未显式配置模型时应保持 BGE-small 默认值。",
    )


def test_local_batch_uses_one_model_encode() -> None:
    model = FakeLocalModel()

    vectors = embed_texts(
        [
            "A",
            "B",
        ],
        provider=LOCAL_EMBEDDING_PROVIDER,
        local_model=model,
    )

    assert_equal(
        len(
            model.calls
        ),
        1,
        "Local batch 应只调用一次 model.encode。",
    )

    assert_equal(
        model.calls[0],
        [
            "A",
            "B",
        ],
        "Local batch 应完整透传 texts。",
    )

    assert_equal(
        vectors,
        [
            [1.0, 2.0],
            [2.0, 3.0],
        ],
        "Local vectors 应统一为普通 Python float vectors。",
    )


def test_remote_batch_uses_remote_embedder_and_model() -> None:
    remote = FakeRemoteEmbedder()

    vectors = embed_texts(
        [
            "指标A",
            "指标B",
        ],
        provider=OPENAI_COMPATIBLE_EMBEDDING_PROVIDER,
        model="remote-test-model",
        remote_embedder=remote,
    )

    assert_equal(
        remote.calls,
        [
            {
                "texts": (
                    "指标A",
                    "指标B",
                ),
                "model": "remote-test-model",
            }
        ],
        "Remote Provider 应一次 batch 调用并透传 model。",
    )

    assert_equal(
        vectors,
        [
            [0.1, 0.2],
            [0.1, 0.2],
        ],
        "Remote vectors 应保持 provider-neutral 格式。",
    )


def test_embed_text_preserves_single_text_entry() -> None:
    model = FakeLocalModel()

    vector = embed_text(
        "单个问题",
        provider=LOCAL_EMBEDDING_PROVIDER,
        local_model=model,
    )

    assert_equal(
        vector,
        [
            1.0,
            2.0,
        ],
        "现有 embed_text(text) 单文本入口必须继续可用。",
    )


def test_remote_provider_requires_model() -> None:
    assert_raises(
        EmbeddingServiceError,
        lambda: _with_env(
            {
                "AI_EMBEDDING_MODEL": None,
            },
            lambda: embed_texts(
                [
                    "A",
                ],
                provider=(
                    OPENAI_COMPATIBLE_EMBEDDING_PROVIDER
                ),
                remote_embedder=FakeRemoteEmbedder(),
            ),
        ),
        "Remote Provider 缺少 model 时必须 fail closed。",
    )


def run_tests() -> None:
    tests = [
        test_default_provider_remains_local,
        test_invalid_provider_fails_closed,
        test_local_default_model_remains_bge_small,
        test_local_batch_uses_one_model_encode,
        test_remote_batch_uses_remote_embedder_and_model,
        test_embed_text_preserves_single_text_entry,
        test_remote_provider_requires_model,
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
        "Embedding Service Test Summary"
    )
    print(f"Total: {len(tests)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    run_tests()
