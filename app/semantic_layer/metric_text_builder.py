from app.semantic_layer.metric_loader import load_metrics


def build_metric_text(metric: dict) -> str:
    """
    将单个业务指标转换为适合 Embedding 的文本。
    """

    aliases = metric.get("aliases", [])
    aliases_text = "\n".join([f"- {alias}" for alias in aliases])

    tables = metric.get("tables", [])
    tables_text = "\n".join([f"- {table}" for table in tables])

    filters = metric.get("filters", [])
    filters_text = "\n".join([f"- {item}" for item in filters])

    examples = metric.get("examples", [])
    examples_text = "\n".join([f"- {item}" for item in examples])

    negative_examples = metric.get("negative_examples", [])
    negative_examples_text = "\n".join([f"- {item}" for item in negative_examples])

    return f"""
指标名称：
{metric.get("chinese_name", "")}
技术名称：
{metric.get("name", "")}
定义：
{metric.get("definition", "")}
公式：
{metric.get("formula", "")}
常见说法：
{aliases_text}
适用问题：
{examples_text}
不适用问题：
{negative_examples_text}
相关数据表：
{tables_text}
过滤条件：
{filters_text}
""".strip()


def build_all_metric_texts() -> list[dict]:
    """
    构建所有指标的 Embedding 文本。
    """

    metrics = load_metrics()
    results = []

    for metric in metrics:
        results.append(
            {
                "name": metric.get("name", ""),
                "chinese_name": metric.get("chinese_name", ""),
                "text": build_metric_text(metric),
            }
        )

    return results


if __name__ == "__main__":
    metric_texts = build_all_metric_texts()

    for item in metric_texts:
        print("=" * 60)
        print(item["name"])
        print("-" * 60)
        print(item["text"])