from __future__ import annotations

import app.semantic_layer.metric_text_builder_v2 as text_builder
import app.semantic_layer.vector_store_v2 as vector_store
from app.semantic_layer.metric_semantic_search_v2 import (
    rank_metric_candidates_by_embedding_v2,
)
from app.semantic_layer.metric_text_builder_v2 import (
    build_all_metric_semantic_documents_v2,
    build_all_metric_texts_v2,
    build_metric_semantic_document_v2,
    canonical_metric_semantic_corpus_v2,
    metric_semantic_corpus_fingerprint_v2,
    render_metric_semantic_text_v2,
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


def assert_true(
    condition: bool,
    message: str,
) -> None:
    if not condition:
        raise AssertionError(message)


def fake_embed(
    text: str,
) -> tuple[float, float, float]:
    length = float(len(text))
    checksum = float(
        sum(ord(ch) for ch in text)
        % 997
    )

    return (
        length,
        checksum,
        1.0,
    )


def test_semantic_corpus_has_exact_19_metrics() -> None:
    assert_equal(
        len(
            build_all_metric_semantic_documents_v2()
        ),
        19,
        "V2 Semantic Corpus 应精确包含 19 Metrics。",
    )

    assert_equal(
        len(
            build_all_metric_texts_v2()
        ),
        19,
        "V2 Semantic Text 应精确包含 19 Metrics。",
    )


def test_semantic_document_has_only_allowed_fields() -> None:
    allowed_keys = {
        "name",
        "chinese_name",
        "aliases",
        "definition",
        "formula",
        "examples",
    }

    for document in (
        build_all_metric_semantic_documents_v2()
    ):
        assert_equal(
            set(document.keys()),
            allowed_keys,
            (
                f"{document['name']} Semantic Document "
                "字段发生污染。"
            ),
        )


def test_unique_negative_sentinel_is_excluded() -> None:
    sentinel = (
        "__NEGATIVE_ONLY_SENTINEL_74__"
    )

    metric = {
        "name": "synthetic_metric",
        "chinese_name": "合成指标",
        "aliases": ["正向别名"],
        "definition": "正向定义",
        "formula": "A / B",
        "examples": ["正向示例"],
        "negative_examples": [
            sentinel
        ],
        "tables": [
            "fact_should_not_enter"
        ],
        "filters": [
            "status = should_not_enter"
        ],
    }

    document = (
        build_metric_semantic_document_v2(
            metric
        )
    )

    rendered = (
        render_metric_semantic_text_v2(
            document
        )
    )

    assert_true(
        sentinel not in rendered,
        (
            "只存在于 negative_examples 的文本 "
            "不得进入 Embedding Corpus。"
        ),
    )

    assert_true(
        "fact_should_not_enter"
        not in rendered,
        "tables 不得进入 Embedding Corpus。",
    )

    assert_true(
        "status = should_not_enter"
        not in rendered,
        "filters 不得进入 Embedding Corpus。",
    )


def test_corpus_fingerprint_is_deterministic() -> None:
    bytes_a = (
        canonical_metric_semantic_corpus_v2()
    )
    bytes_b = (
        canonical_metric_semantic_corpus_v2()
    )

    fp_a = (
        metric_semantic_corpus_fingerprint_v2()
    )
    fp_b = (
        metric_semantic_corpus_fingerprint_v2()
    )

    assert_equal(
        bytes_a,
        bytes_b,
        "Canonical Semantic Corpus 必须 deterministic。",
    )

    assert_equal(
        fp_a,
        fp_b,
        "Semantic Corpus Fingerprint 必须 deterministic。",
    )

    assert_equal(
        len(fp_a),
        64,
        "SHA-256 fingerprint 应为 64 hex chars。",
    )


def test_vector_builder_builds_exact_19_vectors() -> None:
    vectors = vector_store.build_metric_vectors_v2(
        embed_fn=fake_embed
    )

    assert_equal(
        len(vectors),
        19,
        "V2 Vector Store 应构建 19 Metric vectors。",
    )


def test_vector_cache_reuses_same_fingerprint() -> None:
    vector_store.clear_metric_vector_cache_v2()

    calls = {
        "count": 0,
    }

    def counting_embed(text: str):
        calls["count"] += 1
        return fake_embed(text)

    first = vector_store.load_metric_vectors_v2(
        embed_fn=counting_embed
    )

    second = vector_store.load_metric_vectors_v2(
        embed_fn=counting_embed
    )

    assert_equal(
        calls["count"],
        19,
        "相同 fingerprint 不得重复 embedding。",
    )

    assert_true(
        first is second,
        "相同 fingerprint 应复用 cache tuple。",
    )


def test_vector_cache_rebuilds_after_fingerprint_change() -> None:
    vector_store.clear_metric_vector_cache_v2()

    original_fp_fn = (
        vector_store.metric_semantic_corpus_fingerprint_v2
    )

    calls = {
        "count": 0,
    }

    def counting_embed(text: str):
        calls["count"] += 1
        return fake_embed(text)

    try:
        vector_store.metric_semantic_corpus_fingerprint_v2 = (
            lambda: "a" * 64
        )

        first = (
            vector_store.load_metric_vectors_v2(
                embed_fn=counting_embed
            )
        )

        vector_store.metric_semantic_corpus_fingerprint_v2 = (
            lambda: "b" * 64
        )

        second = (
            vector_store.load_metric_vectors_v2(
                embed_fn=counting_embed
            )
        )

        assert_equal(
            calls["count"],
            38,
            "fingerprint 改变后必须重建全部 19 vectors。",
        )

        assert_true(
            first is not second,
            "fingerprint 改变后不得复用旧 cache tuple。",
        )

    finally:
        vector_store.metric_semantic_corpus_fingerprint_v2 = (
            original_fp_fn
        )
        vector_store.clear_metric_vector_cache_v2()


def test_cache_state_exposes_only_metadata() -> None:
    vector_store.clear_metric_vector_cache_v2()

    assert_equal(
        vector_store.get_metric_vector_cache_state_v2(),
        {
            "loaded": False,
            "fingerprint": None,
            "count": 0,
        },
        "空 Cache State 错误。",
    )

    vector_store.load_metric_vectors_v2(
        embed_fn=fake_embed
    )

    state = (
        vector_store.get_metric_vector_cache_state_v2()
    )

    assert_equal(
        state["count"],
        19,
        "Loaded Cache 应有 19 vectors。",
    )

    assert_true(
        "vectors" not in state,
        "Cache State 不应暴露 vectors。",
    )

    vector_store.clear_metric_vector_cache_v2()


def _install_fake_search_runtime():
    import app.semantic_layer.metric_semantic_search_v2 as search

    fake_vectors = (
        {
            "name": "gmv",
            "chinese_name": "GMV",
            "vector": (1.0, 0.0),
        },
        {
            "name": "roi",
            "chinese_name": "ROI",
            "vector": (0.8, 0.2),
        },
        {
            "name": "cac",
            "chinese_name": "CAC",
            "vector": (0.0, 1.0),
        },
    )

    original_load = (
        search.load_metric_vectors_v2
    )
    original_embed = search.embed_text
    original_cos = search.util.cos_sim

    search.load_metric_vectors_v2 = (
        lambda: fake_vectors
    )
    search.embed_text = (
        lambda question: (1.0, 0.0)
    )

    def fake_cos(
        query_vector,
        metric_vector,
    ):
        return {
            (1.0, 0.0): 0.90,
            (0.8, 0.2): 0.75,
            (0.0, 1.0): 0.20,
        }[
            tuple(metric_vector)
        ]

    search.util.cos_sim = fake_cos

    return (
        search,
        original_load,
        original_embed,
        original_cos,
    )


def test_semantic_search_returns_descending_raw_candidates() -> None:
    (
        search,
        original_load,
        original_embed,
        original_cos,
    ) = _install_fake_search_runtime()

    try:
        result = (
            rank_metric_candidates_by_embedding_v2(
                "测试问题",
                top_k=3,
            )
        )

        assert_equal(
            [
                item["name"]
                for item in result["candidates"]
            ],
            [
                "gmv",
                "roi",
                "cac",
            ],
            "Raw candidates 必须按 score 降序。",
        )

        assert_true(
            "status" not in result,
            (
                "Gate 5B 不得输出业务 matched/"
                "clarification/unsupported status。"
            ),
        )

        assert_true(
            "is_confident" not in result,
            "Gate 5B 不得提前做 Confidence Decision。",
        )

    finally:
        search.load_metric_vectors_v2 = (
            original_load
        )
        search.embed_text = original_embed
        search.util.cos_sim = original_cos


def test_authorization_filters_before_similarity_ranking() -> None:
    (
        search,
        original_load,
        original_embed,
        original_cos,
    ) = _install_fake_search_runtime()

    seen_vectors = []

    def recording_cos(
        query_vector,
        metric_vector,
    ):
        seen_vectors.append(
            tuple(metric_vector)
        )

        return {
            (1.0, 0.0): 0.90,
            (0.8, 0.2): 0.75,
            (0.0, 1.0): 0.20,
        }[
            tuple(metric_vector)
        ]

    search.util.cos_sim = recording_cos

    try:
        result = (
            rank_metric_candidates_by_embedding_v2(
                "测试问题",
                allowed_metric_names={
                    "roi",
                    "cac",
                },
                top_k=3,
            )
        )

        assert_equal(
            [
                item["name"]
                for item in result["candidates"]
            ],
            [
                "roi",
                "cac",
            ],
            "未授权 gmv 不得进入候选。",
        )

        assert_true(
            (1.0, 0.0)
            not in seen_vectors,
            (
                "未授权 vector 不得参与 similarity ranking。"
            ),
        )

    finally:
        search.load_metric_vectors_v2 = (
            original_load
        )
        search.embed_text = original_embed
        search.util.cos_sim = original_cos


def test_empty_authorized_set_fails_closed_before_query_embedding() -> None:
    import app.semantic_layer.metric_semantic_search_v2 as search

    original_load = (
        search.load_metric_vectors_v2
    )
    original_embed = search.embed_text

    search.load_metric_vectors_v2 = lambda: (
        {
            "name": "gmv",
            "chinese_name": "GMV",
            "vector": (1.0, 0.0),
        },
    )

    calls = {
        "count": 0,
    }

    def forbidden_embed(question: str):
        calls["count"] += 1
        raise AssertionError(
            "空授权集不应生成 query embedding。"
        )

    search.embed_text = forbidden_embed

    try:
        result = (
            rank_metric_candidates_by_embedding_v2(
                "任何问题",
                allowed_metric_names=set(),
            )
        )

        assert_equal(
            result["retrieval_status"],
            "no_candidates",
            "空授权集必须 fail closed。",
        )

        assert_equal(
            result["reason"],
            "no_authorized_metric_vectors",
            "空授权集 reason code 错误。",
        )

        assert_equal(
            calls["count"],
            0,
            "空授权集不得调用 query embedding。",
        )

    finally:
        search.load_metric_vectors_v2 = (
            original_load
        )
        search.embed_text = original_embed


def test_top_k_validation() -> None:
    try:
        rank_metric_candidates_by_embedding_v2(
            "测试",
            top_k=0,
        )
    except ValueError:
        return

    raise AssertionError(
        "top_k < 1 必须被拒绝。"
    )


def run_tests() -> None:
    tests = [
        test_semantic_corpus_has_exact_19_metrics,
        test_semantic_document_has_only_allowed_fields,
        test_unique_negative_sentinel_is_excluded,
        test_corpus_fingerprint_is_deterministic,
        test_vector_builder_builds_exact_19_vectors,
        test_vector_cache_reuses_same_fingerprint,
        test_vector_cache_rebuilds_after_fingerprint_change,
        test_cache_state_exposes_only_metadata,
        test_semantic_search_returns_descending_raw_candidates,
        test_authorization_filters_before_similarity_ranking,
        test_empty_authorized_set_fails_closed_before_query_embedding,
        test_top_k_validation,
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
    print("V2 Semantic Retrieval Infrastructure Test Summary")
    print(f"Total: {len(tests)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    run_tests()
