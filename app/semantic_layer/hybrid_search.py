from app.semantic_layer.metric_loader import (search_metrics,)
from app.semantic_layer.semantic_search_v2 import (search_metric_by_embedding,)
from app.semantic_layer.clarification import (build_clarification,)
from app.semantic_layer.clarification_reranker import rerank_candidates_for_clarification

from typing import AbstractSet

def search_metric(
    query: str,
    allowed_metric_names: AbstractSet[str] | None = None,
) -> dict:
    """
    Hybrid Search V1

    Alias Search
    ↓
    Embedding Search
    ↓
    Clarification
    """

    if (
        allowed_metric_names is not None
        and len(allowed_metric_names) == 0
    ):
        return {
            "status": "access_denied",
            "method": "authorization",
            "question": query,
            "message": "当前访问上下文没有可用的业务指标。",
            "error_type": "authorization_error",
            "reason_code": "no_authorized_metrics",
            "retryable": False,
            "metrics": [],
            "options": [],
            "trace": {
                "search_type": "authorization",
                "candidate_count": 0,
            },
        }

    alias_results = search_metrics(
        query,
        allowed_metric_names=allowed_metric_names,
    )

    if alias_results:
        return {
            "status": "matched",
            "method": "rule",
            "question": query,
            "metrics": [
                {
                    "name": metric["name"],
                    "chinese_name": metric["chinese_name"],
                    "score": None
                }
                for metric in alias_results
            ],
            "trace": [
                {
                    "search_type": metric.get("_match_type"),
                    "matched_alias": metric["aliases"],
                    "candidate_count": 1
                }
                for metric in alias_results
            ],
        }

    embedding_result = search_metric_by_embedding(
        query,
        allowed_metric_names=allowed_metric_names,
    )

    candidates = embedding_result.get("candidates", [])

    if not candidates:
        return {
            "status": "error",
            "method": "embedding",
            "question": query,
            "message": "授权指标缺少可用的向量候选。",
            "error_type": "metric_vector_consistency_error",
            "reason_code": embedding_result.get(
                "reason",
                "no_authorized_metric_vectors",
            ),
            "retryable": False,
            "metrics": [],
            "options": [],
            "trace": {
                "search_type": "embedding",
                "candidate_count": 0,
            },
        }

    top1 = candidates[0]
    top2 = candidates[1] if len(candidates) > 1 else None
    gap = (
        top1["score"] - top2["score"]
        if top2 is not None
        else None
    )
    reason = embedding_result["reason"]

    if embedding_result["status"] == "matched":
        top_metric = embedding_result["top_metric"]
        return {
            "status": "matched",
            "method": "embedding",
            "question": query,
            "metrics": [
                {
                    "name": top_metric["name"],
                    "chinese_name": top_metric["chinese_name"],
                    "score": top_metric["score"],
                }
            ],
            "trace":{
                "search_type": "embedding",
                "top1": top1["chinese_name"],
                "top1_score": round(top1["score"],4),
                "top2": top2["chinese_name"] if top2 else None,
                "top2_score": (
                    round(top2["score"], 4)
                    if top2 else None
                ),
                "gap": (
                    round(gap, 4)
                    if gap is not None else None
                ),
                "threshold": {
                    "top1": 0.50,
                    "gap": 0.08
                }
            }
        }

    reranked_candidates = rerank_candidates_for_clarification(
        query=query,
        candidates=candidates,
        top_k=3,
    )

    reranked_embedding_result = {
        **embedding_result,
        "candidates": reranked_candidates,
    }

    rerank_top1 = reranked_candidates[0] if len(reranked_candidates) > 0 else None
    rerank_top2 = reranked_candidates[1] if len(reranked_candidates) > 1 else None

    rerank_gap = None
    if rerank_top1 and rerank_top2:
        rerank_gap = (
            rerank_top1.get("rerank_score", rerank_top1.get("score", 0))
            -
            rerank_top2.get("rerank_score", rerank_top2.get("score", 0))
        )

    clarification_result = build_clarification(reranked_embedding_result)
    
    status = clarification_result["status"]
    message = clarification_result["message"]
    options = clarification_result["suggestions"]
    return {
        "status": status,
        "message": message,
        "options": options,
        "trace": {
            "search_type": "embedding",
            "confidence_source": "embedding_score",
            "suggestion_source": "rerank_score",

            "embedding": {
                "top1": top1["chinese_name"],
                "top1_score": round(top1["score"], 4),
                "top2": (
                    top2["chinese_name"]
                    if top2 else None
                ),
                "top2_score": (
                    round(top2["score"], 4)
                    if top2 else None
                ),
                "gap": (
                    round(gap, 4)
                    if gap is not None else None
                ),
                "reason": reason,
                "threshold": {
                    "top1": 0.50,
                    "gap": 0.08,
                },
            },

            "rerank": {
                "top1": rerank_top1["chinese_name"] if rerank_top1 else None,
                "top1_score": round(
                    rerank_top1.get("rerank_score", rerank_top1.get("score", 0)),
                    4,
                ) if rerank_top1 else None,
                "top2": rerank_top2["chinese_name"] if rerank_top2 else None,
                "top2_score": round(
                    rerank_top2.get("rerank_score", rerank_top2.get("score", 0)),
                    4,
                ) if rerank_top2 else None,
                "gap": round(rerank_gap, 4) if rerank_gap is not None else None,
                "candidates": [
                    {
                        "name": item["name"],
                        "chinese_name": item["chinese_name"],
                        "embedding_score": round(
                            item.get("original_score", item.get("score", 0)),
                            4,
                        ),
                        "rerank_score": round(
                            item.get("rerank_score", item.get("score", 0)),
                            4,
                        ),
                    }
                    for item in reranked_candidates
                ],
            },
        }
    }

if __name__ == "__main__":

    questions = [
        "哪个品类销售额最高",
        "哪个订单支付金额最高",
        "哪个品类销量最高",
        "哪个品类订单最多",
        "销售额Top5品类",
        "销售额Top10品类",
        "哪个品类销售额最高",
    ]

    for question in questions:

        result = search_metric(question)

        print("=" * 60)

        print("Question:")
        print(question)

        print()

        print(result)
