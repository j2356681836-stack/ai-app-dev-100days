from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Sequence

from app.semantic_layer.embedding_service import (
    embed_texts,
    resolve_embedding_model,
    resolve_embedding_provider,
)
from app.semantic_layer.metric_text_builder_v2 import (
    build_all_metric_texts_v2,
    metric_semantic_corpus_fingerprint_v2,
)


EmbedFn = Callable[[str], Any]
EmbedBatchFn = Callable[[Sequence[str]], Sequence[Any]]


@dataclass(frozen=True)
class MetricVectorCacheV2:
    """
    Metric Vector Cache identity。

    corpus fingerprint 只能说明“被 embedding 的文本是否变化”；
    provider + model 进一步说明“这些文本位于哪个向量空间”。

    三者任意一个变化，都必须重建 vectors。
    """

    fingerprint: str
    embedding_provider: str
    embedding_model: str
    vectors: tuple[dict[str, Any], ...]


_metric_vector_cache_v2: (
    MetricVectorCacheV2 | None
) = None


def _normalize_batch_vectors_v2(
    vectors: Sequence[Any],
    *,
    expected_count: int,
) -> tuple[Any, ...]:
    normalized = tuple(
        vectors
    )

    if len(normalized) != expected_count:
        raise RuntimeError(
            "Metric embedding vector count does not match "
            "semantic corpus count."
        )

    return normalized


def build_metric_vectors_v2(
    *,
    embed_fn: EmbedFn | None = None,
    embed_batch_fn: EmbedBatchFn | None = None,
    embedding_provider: str | None = None,
    embedding_model: str | None = None,
) -> tuple[dict[str, Any], ...]:
    """
    构建 Dataset V2 Metric vectors。

    默认运行时使用 batch Embedding：
    - Local Provider: 一次 model.encode(list[str])
    - Remote Provider: 一次 embeddings API batch request

    embed_fn 保留为向后兼容的单文本依赖注入入口，
    现有测试 / Evaluation 可以继续显式注入。

    embed_fn 与 embed_batch_fn 不能同时提供。
    """

    if (
        embed_fn is not None
        and embed_batch_fn is not None
    ):
        raise ValueError(
            "Provide either embed_fn or embed_batch_fn, not both."
        )

    metric_texts = tuple(
        build_all_metric_texts_v2()
    )
    texts = tuple(
        item["text"]
        for item in metric_texts
    )

    if embed_fn is not None:
        vectors = tuple(
            embed_fn(
                text
            )
            for text in texts
        )
    else:
        if embed_batch_fn is not None:
            raw_vectors = embed_batch_fn(
                texts
            )
        else:
            actual_provider = (
                resolve_embedding_provider(
                    embedding_provider
                )
            )
            actual_model = (
                resolve_embedding_model(
                    provider=actual_provider,
                    model=embedding_model,
                )
            )

            raw_vectors = embed_texts(
                texts,
                provider=actual_provider,
                model=actual_model,
            )

        vectors = _normalize_batch_vectors_v2(
            raw_vectors,
            expected_count=len(
                metric_texts
            ),
        )

    return tuple(
        {
            "name": item["name"],
            "chinese_name": item[
                "chinese_name"
            ],
            "text": item["text"],
            "vector": vector,
        }
        for item, vector in zip(
            metric_texts,
            vectors,
            strict=True,
        )
    )


def clear_metric_vector_cache_v2() -> None:
    global _metric_vector_cache_v2
    _metric_vector_cache_v2 = None


def get_metric_vector_cache_state_v2(
) -> dict[str, Any]:
    """
    只暴露安全的 Cache metadata，不暴露 vectors。

    为保持现有调用 contract，这里继续返回原有三个字段；
    provider / model 只参与内部 cache identity。
    """

    if _metric_vector_cache_v2 is None:
        return {
            "loaded": False,
            "fingerprint": None,
            "count": 0,
        }

    return {
        "loaded": True,
        "fingerprint": (
            _metric_vector_cache_v2.fingerprint
        ),
        "count": len(
            _metric_vector_cache_v2.vectors
        ),
    }


def load_metric_vectors_v2(
    *,
    embed_fn: EmbedFn | None = None,
    embed_batch_fn: EmbedBatchFn | None = None,
    embedding_provider: str | None = None,
    embedding_model: str | None = None,
) -> tuple[dict[str, Any], ...]:
    """
    fingerprint + provider + model aware Metric Vector Cache。

    - semantic corpus changed -> rebuild
    - embedding provider changed -> rebuild
    - embedding model changed -> rebuild
    - identity unchanged -> reuse

    这样不会把不同 Embedding Space 的 metric/question vectors
    错误地放在一起计算 cosine similarity。
    """

    global _metric_vector_cache_v2

    actual_provider = resolve_embedding_provider(
        embedding_provider
    )
    actual_model = resolve_embedding_model(
        provider=actual_provider,
        model=embedding_model,
    )
    current_fingerprint = (
        metric_semantic_corpus_fingerprint_v2()
    )

    cache_matches = (
        _metric_vector_cache_v2 is not None
        and (
            _metric_vector_cache_v2.fingerprint
            == current_fingerprint
        )
        and (
            _metric_vector_cache_v2.embedding_provider
            == actual_provider
        )
        and (
            _metric_vector_cache_v2.embedding_model
            == actual_model
        )
    )

    if not cache_matches:
        _metric_vector_cache_v2 = (
            MetricVectorCacheV2(
                fingerprint=(
                    current_fingerprint
                ),
                embedding_provider=(
                    actual_provider
                ),
                embedding_model=(
                    actual_model
                ),
                vectors=(
                    build_metric_vectors_v2(
                        embed_fn=embed_fn,
                        embed_batch_fn=(
                            embed_batch_fn
                        ),
                        embedding_provider=(
                            actual_provider
                        ),
                        embedding_model=(
                            actual_model
                        ),
                    )
                ),
            )
        )

    return _metric_vector_cache_v2.vectors


if __name__ == "__main__":
    vectors = load_metric_vectors_v2()

    print(
        get_metric_vector_cache_state_v2()
    )

    for item in vectors:
        print("=" * 80)
        print(item["name"])
        print(item["chinese_name"])
        print(type(item["vector"]))
