from __future__ import annotations

import app.semantic_layer.metric_multiview_v2 as multiview
from app.semantic_layer.metric_multiview_v2 import (
    build_all_metric_semantic_views_v2,
    build_metric_semantic_views_v2,
    canonical_metric_multiview_corpus_v2,
    metric_multiview_corpus_fingerprint_v2,
    rank_metric_candidates_multiview_v2,
)


EXPECTED_METRICS = 19
EXPECTED_EXAMPLES_PER_METRIC = 4
EXPECTED_VIEWS_PER_METRIC = 7
EXPECTED_TOTAL_VIEWS = (
    EXPECTED_METRICS
    * EXPECTED_VIEWS_PER_METRIC
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
):
    return (
        float(len(text)),
        float(
            sum(ord(ch) for ch in text)
            % 997
        ),
        1.0,
    )


def test_multiview_has_expected_view_count() -> None:
    views = build_all_metric_semantic_views_v2()

    assert_equal(
        len(views),
        EXPECTED_TOTAL_VIEWS,
        "19 Metrics × 7 Views 应得到 133 Views。",
    )

    counts = {}
    for view in views:
        counts[view.metric_name] = (
            counts.get(
                view.metric_name,
                0,
            )
            + 1
        )

    assert_equal(
        len(counts),
        EXPECTED_METRICS,
        "Multiview 必须覆盖 19 Metrics。",
    )

    assert_true(
        all(
            count
            == EXPECTED_VIEWS_PER_METRIC
            for count in counts.values()
        ),
        (
            "当前 V2 每个 Metric 应有 "
            "Identity + Definition + Formula + 4 Examples。"
        ),
    )


def test_view_types_are_structurally_separated() -> None:
    views = build_all_metric_semantic_views_v2()

    by_metric = {}

    for view in views:
        by_metric.setdefault(
            view.metric_name,
            [],
        ).append(view)

    for metric_name, metric_views in by_metric.items():
        types = [
            view.view_type
            for view in metric_views
        ]

        assert_equal(
            types.count("identity"),
            1,
            f"{metric_name} 应有 1 Identity View。",
        )
        assert_equal(
            types.count("definition"),
            1,
            f"{metric_name} 应有 1 Definition View。",
        )
        assert_equal(
            types.count("formula"),
            1,
            f"{metric_name} 应有 1 Formula View。",
        )
        assert_equal(
            types.count("example"),
            EXPECTED_EXAMPLES_PER_METRIC,
            f"{metric_name} 应有 4 Example Views。",
        )


def test_negative_and_technical_fields_do_not_enter_views() -> None:
    sentinel_negative = "__NEGATIVE_ONLY__"
    sentinel_table = "__TABLE_ONLY__"
    sentinel_filter = "__FILTER_ONLY__"

    metric = {
        "name": "synthetic_metric",
        "chinese_name": "合成指标",
        "aliases": ["正向别名"],
        "definition": "正向定义",
        "formula": "A / B",
        "examples": ["正向示例"],
        "negative_examples": [
            sentinel_negative
        ],
        "tables": [
            sentinel_table
        ],
        "filters": [
            sentinel_filter
        ],
    }

    rendered = "\n".join(
        view.text
        for view in build_metric_semantic_views_v2(
            metric
        )
    )

    for forbidden in (
        sentinel_negative,
        sentinel_table,
        sentinel_filter,
    ):
        assert_true(
            forbidden not in rendered,
            f"{forbidden} 不得进入 Multiview Corpus。",
        )


def test_multiview_fingerprint_is_deterministic() -> None:
    assert_equal(
        canonical_metric_multiview_corpus_v2(),
        canonical_metric_multiview_corpus_v2(),
        "Canonical Multiview Corpus 必须 deterministic。",
    )

    fingerprint_a = (
        metric_multiview_corpus_fingerprint_v2()
    )
    fingerprint_b = (
        metric_multiview_corpus_fingerprint_v2()
    )

    assert_equal(
        fingerprint_a,
        fingerprint_b,
        "Multiview fingerprint 必须 deterministic。",
    )

    assert_equal(
        len(fingerprint_a),
        64,
        "SHA-256 fingerprint 应为 64 hex chars。",
    )


def test_multiview_vector_cache_reuses_and_rebuilds() -> None:
    multiview.clear_metric_multiview_cache_v2()

    original_fp = (
        multiview.metric_multiview_corpus_fingerprint_v2
    )

    calls = {
        "count": 0,
    }

    def counting_embed(
        text: str,
    ):
        calls["count"] += 1
        return fake_embed(text)

    try:
        multiview.metric_multiview_corpus_fingerprint_v2 = (
            lambda: "a" * 64
        )

        first = (
            multiview.load_metric_multiview_vectors_v2(
                embed_fn=counting_embed
            )
        )

        second = (
            multiview.load_metric_multiview_vectors_v2(
                embed_fn=counting_embed
            )
        )

        assert_equal(
            calls["count"],
            EXPECTED_TOTAL_VIEWS,
            "相同 fingerprint 不得重复 embedding。",
        )

        assert_true(
            first is second,
            "相同 fingerprint 应复用 cache。",
        )

        multiview.metric_multiview_corpus_fingerprint_v2 = (
            lambda: "b" * 64
        )

        third = (
            multiview.load_metric_multiview_vectors_v2(
                embed_fn=counting_embed
            )
        )

        assert_equal(
            calls["count"],
            EXPECTED_TOTAL_VIEWS * 2,
            "fingerprint 改变后必须重建全部 Views。",
        )

        assert_true(
            third is not first,
            "新 fingerprint 不得复用旧 vectors tuple。",
        )

    finally:
        multiview.metric_multiview_corpus_fingerprint_v2 = (
            original_fp
        )
        multiview.clear_metric_multiview_cache_v2()


def _install_fake_search_runtime():
    original_load = (
        multiview.load_metric_multiview_vectors_v2
    )
    original_embed = multiview.embed_text
    original_cos = multiview.util.cos_sim

    fake_vectors = (
        {
            "metric_name": "metric_a",
            "chinese_name": "指标A",
            "view_id": "identity",
            "view_type": "identity",
            "text": "A identity",
            "vector": (0.0,),
        },
        {
            "metric_name": "metric_a",
            "chinese_name": "指标A",
            "view_id": "formula",
            "view_type": "formula",
            "text": "A formula",
            "vector": (1.0,),
        },
        {
            "metric_name": "metric_b",
            "chinese_name": "指标B",
            "view_id": "identity",
            "view_type": "identity",
            "text": "B identity",
            "vector": (2.0,),
        },
        {
            "metric_name": "metric_b",
            "chinese_name": "指标B",
            "view_id": "definition",
            "view_type": "definition",
            "text": "B definition",
            "vector": (3.0,),
        },
    )

    multiview.load_metric_multiview_vectors_v2 = (
        lambda: fake_vectors
    )
    multiview.embed_text = (
        lambda question: (99.0,)
    )

    def fake_cos(
        query,
        vector,
    ):
        return {
            0.0: 0.10,
            1.0: 0.90,
            2.0: 0.70,
            3.0: 0.60,
        }[
            float(vector[0])
        ]

    multiview.util.cos_sim = fake_cos

    return (
        original_load,
        original_embed,
        original_cos,
    )


def test_metric_score_uses_max_view() -> None:
    (
        original_load,
        original_embed,
        original_cos,
    ) = _install_fake_search_runtime()

    try:
        result = (
            rank_metric_candidates_multiview_v2(
                "测试问题"
            )
        )

        candidates = result["candidates"]

        assert_equal(
            [
                item["name"]
                for item in candidates
            ],
            [
                "metric_a",
                "metric_b",
            ],
            "Metric 应按 max-view score 排序。",
        )

        assert_equal(
            candidates[0]["score"],
            0.90,
            "metric_a 应由 Formula View 的 0.90 得分。",
        )

        assert_equal(
            candidates[0][
                "winning_view_type"
            ],
            "formula",
            "应记录实际 winning view。",
        )

    finally:
        multiview.load_metric_multiview_vectors_v2 = (
            original_load
        )
        multiview.embed_text = original_embed
        multiview.util.cos_sim = original_cos


def test_authorization_filters_before_view_scoring() -> None:
    (
        original_load,
        original_embed,
        original_cos,
    ) = _install_fake_search_runtime()

    seen = []

    def recording_cos(
        query,
        vector,
    ):
        seen.append(
            float(vector[0])
        )
        return 0.5

    multiview.util.cos_sim = recording_cos

    try:
        result = (
            rank_metric_candidates_multiview_v2(
                "测试",
                allowed_metric_names={
                    "metric_b"
                },
            )
        )

        assert_equal(
            [
                item["name"]
                for item in result["candidates"]
            ],
            [
                "metric_b"
            ],
            "未授权 Metric 不得进入 candidates。",
        )

        assert_equal(
            seen,
            [
                2.0,
                3.0,
            ],
            "未授权 Metric Views 不得参与 cosine scoring。",
        )

    finally:
        multiview.load_metric_multiview_vectors_v2 = (
            original_load
        )
        multiview.embed_text = original_embed
        multiview.util.cos_sim = original_cos


def test_empty_authorization_fails_closed_before_query_embedding() -> None:
    original_load = (
        multiview.load_metric_multiview_vectors_v2
    )
    original_embed = multiview.embed_text

    multiview.load_metric_multiview_vectors_v2 = (
        lambda: (
            {
                "metric_name": "metric_a",
                "chinese_name": "指标A",
                "view_id": "identity",
                "view_type": "identity",
                "text": "A",
                "vector": (1.0,),
            },
        )
    )

    calls = {
        "count": 0,
    }

    def forbidden_embed(
        question: str,
    ):
        calls["count"] += 1
        raise AssertionError(
            "空授权集不应生成 query embedding。"
        )

    multiview.embed_text = forbidden_embed

    try:
        result = (
            rank_metric_candidates_multiview_v2(
                "测试",
                allowed_metric_names=set(),
            )
        )

        assert_equal(
            result["retrieval_status"],
            "no_candidates",
            "空授权集必须 fail closed。",
        )

        assert_equal(
            calls["count"],
            0,
            "空授权集不得调用 query embedding。",
        )

    finally:
        multiview.load_metric_multiview_vectors_v2 = (
            original_load
        )
        multiview.embed_text = original_embed


def run_tests() -> None:
    tests = [
        test_multiview_has_expected_view_count,
        test_view_types_are_structurally_separated,
        test_negative_and_technical_fields_do_not_enter_views,
        test_multiview_fingerprint_is_deterministic,
        test_multiview_vector_cache_reuses_and_rebuilds,
        test_metric_score_uses_max_view,
        test_authorization_filters_before_view_scoring,
        test_empty_authorization_fails_closed_before_query_embedding,
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
    print("Metric Multi-view V2 Test Summary")
    print(f"Total: {len(tests)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(
        "Expected View Count:",
        EXPECTED_TOTAL_VIEWS,
    )

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    run_tests()
