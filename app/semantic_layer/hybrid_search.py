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
        }

    embedding_result = search_metric_by_embedding(query)

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
            "candidates": embedding_result["candidates"],
        }

    return build_clarification(embedding_result)

if __name__ == "__main__":

    questions = [
        "退款率最高",
        "哪个品类卖得最好",
        "卖爆了",
        "最赚钱",
    ]

    for question in questions:

        result = search_metric(question)

        print("=" * 60)

        print("Question:")
        print(question)

        print()

        print(result)