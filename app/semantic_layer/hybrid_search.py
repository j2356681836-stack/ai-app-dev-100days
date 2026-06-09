from app.semantic_layer.metric_loader import (search_metrics,)
from app.semantic_layer.semantic_search_v2 import (search_metric_by_embedding,)
from app.semantic_layer.clarification import (build_clarification,)


def search_metric(query: str) -> dict:
    """
    Hybrid Search V1

    Alias Search
    ↓
    Embedding Search
    ↓
    Clarification
    """

    alias_results = search_metrics(query)

    if alias_results:
        return {
            "status": "matched",
            "method": "alias",
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
                    "search_type": "alias",
                    "matched_alias": metric["aliases"],
                    "candidate_count": 1
                }
                for metric in alias_results
            ],
        }

    embedding_result = search_metric_by_embedding(query)
    candidates = embedding_result["candidates"]
    top1 = candidates[0]
    top2 = candidates[1]
    score = top1["score"]
    gap = top1["score"] - top2["score"]
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
                "top2": top2["chinese_name"],
                "top2_score": round(top2["score"],4),
                "gap": round(gap,4),
                "threshold": {
                    "top1": 0.50,
                    "gap": 0.08
                }
            }
        }

    clarification_result =  build_clarification(embedding_result)
    status = clarification_result["status"]
    message = clarification_result["message"]
    options = clarification_result["suggestions"]
    return {
        "status": status,
        "message": message,
        "options": options,
        "trace":{
            "search_type": "embedding",
            "top1": top1["chinese_name"],
            "top1_score": round(top1["score"],4),
            "top2": top2["chinese_name"],
            "top2_score": round(top2["score"],4),
            "gap": round(gap,4),
            "reason": reason
        }

    }

if __name__ == "__main__":

    questions = [
        "卖得最好",
        "最赚钱",
        "销售冠军",
        "退货最严重",
        "退款最多",
        "订单最多",
        "成交最多",
        "销量最高",
        "表现最差",
        "销售最差"
    ]

    for question in questions:

        result = search_metric(question)

        print("=" * 60)

        print("Question:")
        print(question)

        print()

        print(result)
