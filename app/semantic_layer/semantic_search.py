from app.semantic_layer.metric_loader import search_metrics
from app.semantic_layer.table_loader import search_tables


def semantic_search(query: str) -> dict:
    """
    Semantic Search V0:
    同时检索业务指标和数据表。
    """

    metrics = search_metrics(query)
    tables = search_tables(query)

    return {
        "query": query,
        "metrics": metrics,
        "tables": tables,
    }


if __name__ == "__main__":
    result = semantic_search("退款")

    print("Metrics:")
    for metric in result["metrics"]:
        print("-", metric["name"], metric["chinese_name"])

    print("\nTables:")
    for table in result["tables"]:
        print("-", table["name"], table["chinese_name"])