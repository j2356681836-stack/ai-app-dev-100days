from __future__ import annotations

from typing import AbstractSet, Any

from sentence_transformers import util

from app.semantic_layer.embedding_service import (
    embed_text,
)
from app.semantic_layer.vector_store_v2 import (
    load_metric_vectors_v2,
)


def rank_metric_candidates_by_embedding_v2(
    question: str,
    *,
    allowed_metric_names: (
        AbstractSet[str] | None
    ) = None,
    top_k: int = 6,
) -> dict[str, Any]:
    """
    Dataset V2 Semantic Candidate Generator。

    只输出 raw semantic ranking，不决定：
    matched / clarification / unsupported / confidence。
    """
    if top_k < 1:
        raise ValueError(
            "top_k must be >= 1."
        )

    metric_vectors = (
        load_metric_vectors_v2()
    )

    authorized_vectors = tuple(
        metric
        for metric in metric_vectors
        if (
            allowed_metric_names is None
            or metric["name"]
            in allowed_metric_names
        )
    )

    if not authorized_vectors:
        return {
            "retrieval_status": (
                "no_candidates"
            ),
            "reason": (
                "no_authorized_metric_vectors"
            ),
            "method": "embedding_v2",
            "question": question,
            "candidate_count": 0,
            "candidates": [],
        }

    query_vector = embed_text(
        question
    )

    results: list[dict[str, Any]] = []

    for metric in authorized_vectors:
        score = util.cos_sim(
            query_vector,
            metric["vector"],
        )

        results.append(
            {
                "name": metric["name"],
                "chinese_name": metric[
                    "chinese_name"
                ],
                "score": float(score),
            }
        )

    results.sort(
        key=lambda item: item["score"],
        reverse=True,
    )

    return {
        "retrieval_status": "ok",
        "reason": None,
        "method": "embedding_v2",
        "question": question,
        "candidate_count": len(
            authorized_vectors
        ),
        "candidates": results[:top_k],
    }


if __name__ == "__main__":
    questions = [
        "商品销售收入减商品成本后还剩多少？",
        "每1元投放费用带来的成交金额回报是多少？",
        "平均花多少投放费才能获得一个首次付款客户？",
        "今年净利润率是多少？",
        "退款订单数占支付订单数的比例是多少？",
        "按当前会员身份计算会员GMV占比",
    ]

    for question in questions:
        print("=" * 80)
        result = (
            rank_metric_candidates_by_embedding_v2(
                question
            )
        )

        print(question)

        for candidate in result[
            "candidates"
        ]:
            print(
                candidate["name"],
                round(
                    candidate["score"],
                    4,
                ),
            )
