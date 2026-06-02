from pathlib import Path
from typing import Any

import yaml


def load_metrics() -> list[dict[str, Any]]:
    """
    Load business metrics from metadata/business_metrics.yaml.
    """
    project_root = Path(__file__).resolve().parents[2]
    metrics_path = project_root / "metadata" / "business_metrics.yaml"

    with metrics_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)    # .safe.load():将YAML → Python对象

    return data["metrics"]

def get_metric_by_name(metric_name: str) -> dict | None:
    """
    根据技术名或中文名查找指标
    """

    metrics = load_metrics()

    for metric in metrics:
        if metric["name"] == metric_name:
            return metric
        if metric["chinese_name"] == metric_name:
            return metric
    return None

def search_metrics(query: str) -> list[dict[str, Any]]:
    """
    根据关键词搜索指标。
    当前是 V0：基于 name、chinese_name、definition 的简单包含匹配。
    """

    metrics = load_metrics()
    results = []

    keywords = [
        "退款率",
        "退款",
        "退货",
        "销售额",
        "销售",
        "实付",
        "订单",
    ]

    for metric in metrics:
        searchable_text = " ".join([
            metric.get("name", ""),
            metric.get("chinese_name", ""),
            metric.get("definition", ""),
            metric.get("formula", ""),
        ])

        for keyword in keywords:
            if keyword in query and keyword in searchable_text:
                results.append(metric)
                break

    return results

if __name__ == "__main__":
    results = search_metrics("退款")

    for metric in results:
        print(metric["name"], "-", metric["chinese_name"])