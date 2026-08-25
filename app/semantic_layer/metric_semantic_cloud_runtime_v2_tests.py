from __future__ import annotations

import sys

import app.semantic_layer.metric_semantic_search_v2 as search
import app.semantic_layer.vector_store_v2 as vector_store


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


def _fake_batch_embed(
    texts,
):
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


def test_metric_vector_builder_supports_one_batch_call() -> None:
    calls = {
        "count": 0,
        "sizes": [],
    }

    def counting_batch(
        texts,
    ):
        calls["count"] += 1
        calls["sizes"].append(
            len(
                texts
            )
        )

        return _fake_batch_embed(
            texts
        )

    vectors = (
        vector_store
        .build_metric_vectors_v2(
            embed_batch_fn=counting_batch,
            embedding_provider="local",
            embedding_model="test-model",
        )
    )

    assert_equal(
        len(vectors),
        19,
        "Batch Vector Builder 仍必须生成 19 个 Metric vectors。",
    )
    assert_equal(
        calls["count"],
        1,
        "19 个 Metric texts 应支持一次 batch embedding。",
    )
    assert_equal(
        calls["sizes"],
        [
            19,
        ],
        "Batch input 应包含完整 19 个 Metric texts。",
    )


def test_cache_identity_includes_embedding_model() -> None:
    vector_store.clear_metric_vector_cache_v2()

    calls = {
        "count": 0,
    }

    def counting_batch(
        texts,
    ):
        calls["count"] += 1
        return _fake_batch_embed(
            texts
        )

    try:
        first = (
            vector_store
            .load_metric_vectors_v2(
                embed_batch_fn=counting_batch,
                embedding_provider="local",
                embedding_model="model-a",
            )
        )

        second = (
            vector_store
            .load_metric_vectors_v2(
                embed_batch_fn=counting_batch,
                embedding_provider="local",
                embedding_model="model-b",
            )
        )

        assert_equal(
            calls["count"],
            2,
            "Embedding model 改变后必须重建 Metric vectors。",
        )
        assert_true(
            first is not second,
            "不同模型不得复用旧 Metric Vector Cache。",
        )
    finally:
        vector_store.clear_metric_vector_cache_v2()


def test_cache_identity_includes_embedding_provider() -> None:
    vector_store.clear_metric_vector_cache_v2()

    calls = {
        "count": 0,
    }

    def counting_batch(
        texts,
    ):
        calls["count"] += 1
        return _fake_batch_embed(
            texts
        )

    try:
        first = (
            vector_store
            .load_metric_vectors_v2(
                embed_batch_fn=counting_batch,
                embedding_provider="local",
                embedding_model="same-model",
            )
        )

        second = (
            vector_store
            .load_metric_vectors_v2(
                embed_batch_fn=counting_batch,
                embedding_provider="openai_compatible",
                embedding_model="same-model",
            )
        )

        assert_equal(
            calls["count"],
            2,
            "Embedding provider 改变后必须重建 Metric vectors。",
        )
        assert_true(
            first is not second,
            "不同 Provider 不得复用旧 Metric Vector Cache。",
        )
    finally:
        vector_store.clear_metric_vector_cache_v2()


def test_lightweight_cosine_matches_expected_value() -> None:
    score = (
        search
        ._cosine_similarity_v2(
            (
                1.0,
                0.0,
            ),
            (
                0.8,
                0.2,
            ),
        )
    )

    expected = (
        0.8
        / (
            (
                0.8 ** 2
                + 0.2 ** 2
            )
            ** 0.5
        )
    )

    assert_true(
        abs(
            score
            - expected
        )
        < 1e-12,
        "轻量 Cosine Similarity 计算错误。",
    )


def test_search_import_does_not_load_sentence_transformers() -> None:
    assert_true(
        "sentence_transformers"
        not in sys.modules,
        (
            "Cloud Retrieval import path 不应加载 "
            "sentence-transformers / PyTorch。"
        ),
    )


def run_tests() -> None:
    tests = [
        test_metric_vector_builder_supports_one_batch_call,
        test_cache_identity_includes_embedding_model,
        test_cache_identity_includes_embedding_provider,
        test_lightweight_cosine_matches_expected_value,
        test_search_import_does_not_load_sentence_transformers,
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
        "Metric Semantic Cloud Runtime Test Summary"
    )
    print(f"Total: {len(tests)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    run_tests()
