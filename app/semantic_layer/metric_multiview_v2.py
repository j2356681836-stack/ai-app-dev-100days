from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import AbstractSet, Any, Callable

from sentence_transformers import util

from app.semantic_layer.embedding_service import embed_text
from app.semantic_layer.metric_loader_v2 import load_metrics_v2


MULTIVIEW_CORPUS_VERSION = "beauty_bi_v2_metric_multiview_1"

EmbedFn = Callable[[str], Any]


@dataclass(frozen=True)
class MetricSemanticViewV2:
    metric_name: str
    chinese_name: str
    view_id: str
    view_type: str
    text: str


@dataclass(frozen=True)
class MetricMultiViewVectorCacheV2:
    fingerprint: str
    vectors: tuple[dict[str, Any], ...]


_metric_multiview_cache_v2: MetricMultiViewVectorCacheV2 | None = None


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _clean_sequence(
    values: list[Any] | tuple[Any, ...] | None,
) -> tuple[str, ...]:
    if not values:
        return ()

    return tuple(
        str(value).strip()
        for value in values
        if str(value).strip()
    )


def build_metric_semantic_views_v2(
    metric: dict[str, Any],
) -> tuple[MetricSemanticViewV2, ...]:
    """
    Build independent semantic views for one V2 Metric.

    Views:
    - identity
    - definition
    - formula
    - one vector per positive example

    Explicitly excluded:
    - negative_examples
    - tables
    - filters
    - Query Plan resource/scope contracts
    """
    name = _clean(metric.get("name"))
    chinese_name = _clean(metric.get("chinese_name"))
    aliases = _clean_sequence(metric.get("aliases"))
    definition = _clean(metric.get("definition"))
    formula = _clean(metric.get("formula"))
    examples = _clean_sequence(metric.get("examples"))

    if not name:
        raise ValueError("Metric semantic view requires metric name.")

    identity_lines = [
        f"技术名称：{name}",
        f"指标名称：{chinese_name}",
    ]

    if aliases:
        identity_lines.append(
            "常见说法：" + "；".join(aliases)
        )

    views: list[MetricSemanticViewV2] = [
        MetricSemanticViewV2(
            metric_name=name,
            chinese_name=chinese_name,
            view_id="identity",
            view_type="identity",
            text="\n".join(identity_lines),
        ),
    ]

    if definition:
        views.append(
            MetricSemanticViewV2(
                metric_name=name,
                chinese_name=chinese_name,
                view_id="definition",
                view_type="definition",
                text=f"业务定义：{definition}",
            )
        )

    if formula:
        views.append(
            MetricSemanticViewV2(
                metric_name=name,
                chinese_name=chinese_name,
                view_id="formula",
                view_type="formula",
                text=f"计算公式：{formula}",
            )
        )

    for index, example in enumerate(
        examples,
        start=1,
    ):
        views.append(
            MetricSemanticViewV2(
                metric_name=name,
                chinese_name=chinese_name,
                view_id=f"example_{index:02d}",
                view_type="example",
                text=f"适用问题示例：{example}",
            )
        )

    return tuple(views)


def build_all_metric_semantic_views_v2(
) -> tuple[MetricSemanticViewV2, ...]:
    metrics = load_metrics_v2()

    names = [
        str(metric.get("name"))
        for metric in metrics
    ]

    if len(names) != len(set(names)):
        raise ValueError(
            "Dataset V2 multiview corpus contains duplicate metric names."
        )

    return tuple(
        view
        for metric in metrics
        for view in build_metric_semantic_views_v2(
            metric
        )
    )


def canonical_metric_multiview_corpus_v2(
) -> bytes:
    payload = {
        "corpus_version": MULTIVIEW_CORPUS_VERSION,
        "views": [
            {
                "metric_name": view.metric_name,
                "chinese_name": view.chinese_name,
                "view_id": view.view_id,
                "view_type": view.view_type,
                "text": view.text,
            }
            for view in build_all_metric_semantic_views_v2()
        ],
    }

    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def metric_multiview_corpus_fingerprint_v2(
) -> str:
    return hashlib.sha256(
        canonical_metric_multiview_corpus_v2()
    ).hexdigest()


def build_metric_multiview_vectors_v2(
    *,
    embed_fn: EmbedFn = embed_text,
) -> tuple[dict[str, Any], ...]:
    return tuple(
        {
            "metric_name": view.metric_name,
            "chinese_name": view.chinese_name,
            "view_id": view.view_id,
            "view_type": view.view_type,
            "text": view.text,
            "vector": embed_fn(view.text),
        }
        for view in build_all_metric_semantic_views_v2()
    )


def clear_metric_multiview_cache_v2() -> None:
    global _metric_multiview_cache_v2
    _metric_multiview_cache_v2 = None


def get_metric_multiview_cache_state_v2(
) -> dict[str, Any]:
    if _metric_multiview_cache_v2 is None:
        return {
            "loaded": False,
            "fingerprint": None,
            "view_count": 0,
        }

    return {
        "loaded": True,
        "fingerprint": _metric_multiview_cache_v2.fingerprint,
        "view_count": len(
            _metric_multiview_cache_v2.vectors
        ),
    }


def load_metric_multiview_vectors_v2(
    *,
    embed_fn: EmbedFn = embed_text,
) -> tuple[dict[str, Any], ...]:
    global _metric_multiview_cache_v2

    current_fingerprint = (
        metric_multiview_corpus_fingerprint_v2()
    )

    if (
        _metric_multiview_cache_v2 is None
        or (
            _metric_multiview_cache_v2.fingerprint
            != current_fingerprint
        )
    ):
        _metric_multiview_cache_v2 = (
            MetricMultiViewVectorCacheV2(
                fingerprint=current_fingerprint,
                vectors=build_metric_multiview_vectors_v2(
                    embed_fn=embed_fn
                ),
            )
        )

    return _metric_multiview_cache_v2.vectors


def rank_metric_candidates_multiview_v2(
    question: str,
    *,
    allowed_metric_names: (
        AbstractSet[str] | None
    ) = None,
    top_k: int | None = None,
) -> dict[str, Any]:
    """
    Experimental max-view candidate ranking.

    metric_score = max(similarity(question, each metric view))

    This is deliberately NOT a runtime decision policy.
    It does not emit matched / clarification / unsupported.
    """
    if top_k is not None and top_k < 1:
        raise ValueError(
            "top_k must be >= 1 or None."
        )

    vectors = load_metric_multiview_vectors_v2()

    authorized_vectors = tuple(
        item
        for item in vectors
        if (
            allowed_metric_names is None
            or item["metric_name"]
            in allowed_metric_names
        )
    )

    if not authorized_vectors:
        return {
            "retrieval_status": "no_candidates",
            "reason": "no_authorized_metric_multiview_vectors",
            "method": "embedding_multiview_max_v2",
            "question": question,
            "candidate_count": 0,
            "view_count": 0,
            "candidates": [],
        }

    query_vector = embed_text(question)

    by_metric: dict[str, dict[str, Any]] = {}

    for item in authorized_vectors:
        score = float(
            util.cos_sim(
                query_vector,
                item["vector"],
            )
        )

        candidate = by_metric.get(
            item["metric_name"]
        )

        view_score = {
            "view_id": item["view_id"],
            "view_type": item["view_type"],
            "score": score,
        }

        if candidate is None:
            by_metric[item["metric_name"]] = {
                "name": item["metric_name"],
                "chinese_name": item["chinese_name"],
                "score": score,
                "winning_view_id": item["view_id"],
                "winning_view_type": item["view_type"],
                "view_scores": [view_score],
            }
            continue

        candidate["view_scores"].append(
            view_score
        )

        if score > candidate["score"]:
            candidate["score"] = score
            candidate["winning_view_id"] = item[
                "view_id"
            ]
            candidate["winning_view_type"] = item[
                "view_type"
            ]

    candidates = list(
        by_metric.values()
    )

    for candidate in candidates:
        candidate["view_scores"].sort(
            key=lambda row: row["score"],
            reverse=True,
        )

    candidates.sort(
        key=lambda row: row["score"],
        reverse=True,
    )

    if top_k is not None:
        visible_candidates = candidates[
            :top_k
        ]
    else:
        visible_candidates = candidates

    return {
        "retrieval_status": "ok",
        "reason": None,
        "method": "embedding_multiview_max_v2",
        "question": question,
        "candidate_count": len(
            candidates
        ),
        "view_count": len(
            authorized_vectors
        ),
        "candidates": visible_candidates,
    }


if __name__ == "__main__":
    questions = (
        "商品收入减成本后的金额，占商品实收金额的比例是多少？",
        "把分析期内所有已付款商品行的实收金额加在一起是多少？",
        "商品付款总金额平均摊到每个不同付款客户后是多少？",
    )

    for question in questions:
        print("=" * 80)
        print(question)

        result = rank_metric_candidates_multiview_v2(
            question,
            top_k=6,
        )

        for candidate in result[
            "candidates"
        ]:
            print(
                candidate["name"],
                round(
                    candidate["score"],
                    4,
                ),
                candidate[
                    "winning_view_type"
                ],
                candidate[
                    "winning_view_id"
                ],
            )
