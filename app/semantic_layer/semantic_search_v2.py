from sentence_transformers import util
from app.semantic_layer.metric_text_builder import (build_all_metric_texts,)
from app.semantic_layer.embedding_service import (embed_text,)
from app.semantic_layer.vector_store import load_metric_vectors

TOP1_THRESHOLD = 0.40
GAP_THRESHOLD = 0.06


def is_confident(results: list[dict]) -> bool:
    if not results:
        return False

    if len(results) == 1:
        return results[0]["score"] >= TOP1_THRESHOLD

    top1 = results[0]
    top2 = results[1]

    return (
        top1["score"] >= TOP1_THRESHOLD
        and top1["score"] - top2["score"] >= GAP_THRESHOLD
    )


def search_metric_by_embedding(question: str,):
    query_vector = embed_text(question) #转译向量
    results = []
    metric_vectors = load_metric_vectors()  #加载vector cache

    for metric in metric_vectors:
        score = util.cos_sim(
            query_vector,
            metric["vector"]
        )     # 计算问题和指标之间的相似度

        results.append(
            {
                "name": metric["name"],
                "chinese_name": metric["chinese_name"],
                "score": float(score),
            }
        )

    results.sort(
        key=lambda x: x["score"],
        reverse=True,
    )

    confident = is_confident(results)

    return {
        "status": "matched" if confident else "needs_clarification",
        "method": "embedding",
        "question": question,
        "top_metric": results[0] if results else None,
        "candidates": results[:3],
        "is_confident": confident,
    }


if __name__ == "__main__":
    questions = [
        "哪个品类卖得最好",
        "哪个品类退得最厉害",
        "卖爆了",
        "最赚钱",
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