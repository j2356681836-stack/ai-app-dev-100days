from app.semantic_layer.embedding_service import embed_text
from app.semantic_layer.metric_text_builder import build_all_metric_texts


_metric_vectors = None


def build_metric_vectors() -> list[dict]:
    """
    为所有业务指标生成向量。
    """
    metric_texts = build_all_metric_texts()

    results = []

    for metric in metric_texts:
        vector = embed_text(metric["text"])

        results.append(
            {
                "name": metric["name"],
                "chinese_name": metric["chinese_name"],
                "text": metric["text"],
                "vector": vector,
            }
        )

    return results


def load_metric_vectors() -> list[dict]:
    """
    加载指标向量缓存。
    当前是内存缓存版本。
    """
    global _metric_vectors

    if _metric_vectors is None:
        _metric_vectors = build_metric_vectors()

    return _metric_vectors


if __name__ == "__main__":
    vectors = load_metric_vectors()

    for item in vectors:
        print("=" * 60)
        print(item["name"])
        print(item["chinese_name"])
        print(type(item["vector"]))
        print(len(item["vector"]))