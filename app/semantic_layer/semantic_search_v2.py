from sentence_transformers import util
from app.semantic_layer.embedding_service import embed_text
from app.semantic_layer.vector_store import load_metric_vectors

from typing import Any, AbstractSet

TOP1_THRESHOLD = 0.50
GAP_THRESHOLD = 0.08

def check_confidence(
    results: list[dict[str, Any]],
) -> tuple[bool, str | None]:
    if not results:
        return False, "no_result"

    if len(results) == 1:
        if results[0]["score"] >= TOP1_THRESHOLD:
            return True, None
        return False, "low_score"

    top1 = results[0]
    top2 = results[1]

    if top1["score"] < TOP1_THRESHOLD:
        return False, "low_score"
    elif top1["score"] - top2["score"] < GAP_THRESHOLD:
        return False, "low_gap"
    
    return True, None

def search_metric_by_embedding(
    question: str,
    allowed_metric_names: AbstractSet[str] | None = None,
) -> dict[str, Any]:
    metric_vectors = load_metric_vectors()

    authorized_vectors = [
        metric
        for metric in metric_vectors
        if (
            allowed_metric_names is None
            or metric["name"] in allowed_metric_names
        )
    ]

    if not authorized_vectors:
        return {
            "status": "no_candidates",
            "reason": "no_authorized_metric_vectors",
            "method": "embedding",
            "question": question,
            "top_metric": None,
            "candidates": [],
            "is_confident": False,
        }

    query_vector = embed_text(question)
    results = []

    for metric in authorized_vectors:
        score = util.cos_sim(
            query_vector,
            metric["vector"],
        )

        results.append(
            {
                "name": metric["name"],
                "chinese_name": metric["chinese_name"],
                "score": float(score),
            }
        )

    results.sort(
        key=lambda item: item["score"],
        reverse=True,
    )

    confident, reason = check_confidence(results)

    return {
        "status": (
            "matched"
            if confident
            else "needs_clarification"
        ),
        "reason": reason,
        "method": "embedding",
        "question": question,
        "top_metric": results[0],
        "candidates": results[:6],
        "is_confident": confident,
    }


if __name__ == "__main__":
    questions = [
        "哪个品类卖得最好",
        "哪个品类退得最厉害",
        "卖爆了",
        "最赚钱",
        "订单最多",
        "订单量最高",
        "成交最多",
        "销量最高",
        "卖出最多件",
    ]

    for question in questions:
        result = search_metric_by_embedding(question)

        print("=" * 60)
        print("Question:")
        print(result["question"])

        print("Status:")
        print(result["status"])

        print("Is confident:")
        print(result["is_confident"])

        print("Candidates:")
        for item in result["candidates"]:
            print(
                item["chinese_name"],
                round(item["score"], 4),
            )