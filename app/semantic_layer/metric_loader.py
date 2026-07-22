from pathlib import Path
from typing import Any, AbstractSet

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

def search_metrics(
    query: str,
    allowed_metric_names: AbstractSet[str] | None = None,
) -> list[dict[str, Any]]:
    """
    根据用户问题搜索业务指标。

    allowed_metric_names:
    - None：兼容旧调用，搜索全部指标；
    - 空集合：没有任何指标候选；
    - 非空集合：只搜索集合内的指标技术名。
    """

    metrics = load_metrics()
    results = []

    for metric in metrics:
        metric_name = metric.get("name")

        if (
            allowed_metric_names is not None
            and metric_name not in allowed_metric_names
        ):
            continue

        matched = False
        match_type = None
        matched_text = ""
        match_score = 0

        searchable_items = [
            metric.get("name", ""),
            metric.get("chinese_name", ""),
            metric.get("definition", ""),
            metric.get("formula", ""),
        ]

        aliases = metric.get("aliases", [])
        searchable_items.extend(aliases)

        for item in searchable_items:
            if item and item in query:
                matched = True
                match_type = "alias"
                matched_text = item
                match_score = len(item)
                break

        if not matched:
            keyword_groups = metric.get("keyword_groups", [])

            for group in keyword_groups:
                if all(keyword in query for keyword in group):
                    matched = True
                    match_type = "keyword_group"
                    matched_text = "+".join(group)
                    match_score = sum(len(keyword) for keyword in group)
                    break

        if matched:
            matched_metric = metric.copy()
            matched_metric["_match_type"] = match_type
            matched_metric["_matched_text"] = matched_text
            matched_metric["_match_score"] = match_score
            results.append(matched_metric)

    if len(results) <= 1:
        return results

    max_score = max(
        metric["_match_score"]
        for metric in results
    )

    return [
        metric
        for metric in results
        if metric["_match_score"] == max_score
    ]

if __name__ == "__main__":
    results = search_metrics("退款")

    for metric in results:
        print(metric["name"], "-", metric["chinese_name"])