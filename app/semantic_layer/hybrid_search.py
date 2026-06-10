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
