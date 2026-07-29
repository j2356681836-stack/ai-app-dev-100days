from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from app.semantic_layer.embedding_service import (
    embed_text,
)
from app.semantic_layer.metric_text_builder_v2 import (
    build_all_metric_texts_v2,
    metric_semantic_corpus_fingerprint_v2,
)


EmbedFn = Callable[[str], Any]


@dataclass(frozen=True)
class MetricVectorCacheV2:
    fingerprint: str
    vectors: tuple[dict[str, Any], ...]


_metric_vector_cache_v2: (
    MetricVectorCacheV2 | None
) = None


def build_metric_vectors_v2(
    *,
    embed_fn: EmbedFn = embed_text,
) -> tuple[dict[str, Any], ...]:
    metric_texts = (
        build_all_metric_texts_v2()
    )

    return tuple(
        {
            "name": item["name"],
            "chinese_name": item[
                "chinese_name"
            ],
            "text": item["text"],
            "vector": embed_fn(
                item["text"]
            ),
        }
        for item in metric_texts
    )


def clear_metric_vector_cache_v2() -> None:
    global _metric_vector_cache_v2
    _metric_vector_cache_v2 = None


def get_metric_vector_cache_state_v2(
) -> dict[str, Any]:
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
    embed_fn: EmbedFn = embed_text,
) -> tuple[dict[str, Any], ...]:
    """
    fingerprint-aware V2 Metric Vector Cache。

    - empty -> build
    - same semantic corpus fingerprint -> reuse
    - changed fingerprint -> rebuild
    """
    global _metric_vector_cache_v2

    current_fingerprint = (
        metric_semantic_corpus_fingerprint_v2()
    )

    if (
        _metric_vector_cache_v2 is None
        or (
            _metric_vector_cache_v2.fingerprint
            != current_fingerprint
        )
    ):
        _metric_vector_cache_v2 = (
            MetricVectorCacheV2(
                fingerprint=(
                    current_fingerprint
                ),
                vectors=(
                    build_metric_vectors_v2(
                        embed_fn=embed_fn
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
