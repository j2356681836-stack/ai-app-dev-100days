from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def _metrics_v2_path() -> Path:
    """
    Dataset V2 Metadata 的固定物理路径。

    不回退到 V1 metadata/business_metrics.yaml，
    避免 Day74 Candidate Evaluation 改变 Day60 Stable Retrieval。
    """
    project_root = Path(__file__).resolve().parents[2]

    return (
        project_root
        / "metadata"
        / "beauty_bi_v2"
        / "business_metrics.yaml"
    )


def load_metrics_v2() -> tuple[dict[str, Any], ...]:
    """
    加载 Dataset V2 业务指标。

    返回 tuple，避免调用方增删 Catalog 容器。
    单个 metric 仍是普通 dict，因为当前 YAML Contract
    已在 Day73 通过独立 Metadata / Query Plan Gate 验证。
    """
    path = _metrics_v2_path()

    with path.open(
        "r",
        encoding="utf-8",
    ) as f:
        data = yaml.safe_load(f)

    metrics = data.get("metrics", [])

    if not isinstance(metrics, list):
        raise ValueError(
            "metadata/beauty_bi_v2/business_metrics.yaml "
            "must contain a metrics list."
        )

    return tuple(metrics)


def get_metric_v2_by_name(
    metric_name: str,
) -> dict[str, Any] | None:
    """
    按 V2 技术名查找指标。
    """
    for metric in load_metrics_v2():
        if metric.get("name") == metric_name:
            return metric

    return None


def _normalize_text(text: str) -> str:
    """
    Rule Baseline 只做最小规范化：
    - casefold 兼容 ROI / roi；
    - 去除空白，兼容 “Top 3” 一类表达。

    不做同义词扩写，避免把 Resolver 变成新的 Prompt/Rule 仓库。
    """
    return "".join(
        text.casefold().split()
    )


def _search_terms(
    metric: dict[str, Any],
) -> tuple[tuple[str, str], ...]:
    """
    返回可用于确定性匹配的正式词汇。

    deliberately NOT included:
    - definition
    - formula
    - examples
    - negative_examples

    原因：
    Development / Holdout Evaluation 不能通过直接匹配
    Metadata 示例句获得虚假的泛化分数。
    """
    terms: list[tuple[str, str]] = []

    name = metric.get("name")
    chinese_name = metric.get("chinese_name")

    if name:
        terms.append((str(name), "name"))

    if chinese_name:
        terms.append((str(chinese_name), "chinese_name"))

    for alias in metric.get("aliases", []):
        if alias:
            terms.append((str(alias), "alias"))

    unique_terms: list[tuple[str, str]] = []
    seen: set[str] = set()

    for term, source in terms:
        normalized = _normalize_text(term)

        if not normalized or normalized in seen:
            continue

        seen.add(normalized)
        unique_terms.append((term, source))

    return tuple(unique_terms)


def search_metric_candidates_v2(
    query: str,
) -> tuple[dict[str, Any], ...]:
    """
    Dataset V2 确定性 Metric Rule Baseline。

    评分原则：
    1. 只匹配正式 name / chinese_name / aliases；
    2. 更长、更具体的命中优先；
    3. chinese_name 略高于 alias；
    4. name 用于技术问法，不额外放大权重。

    返回最高分的并列候选。
    如果没有正式词汇命中，返回空 tuple。
    """
    normalized_query = _normalize_text(query)

    matches: list[dict[str, Any]] = []

    source_bonus = {
        "name": 0,
        "alias": 1,
        "chinese_name": 2,
    }

    for metric in load_metrics_v2():
        best: dict[str, Any] | None = None

        for term, source in _search_terms(metric):
            normalized_term = _normalize_text(term)

            if normalized_term not in normalized_query:
                continue

            score = (
                len(normalized_term) * 10
                + source_bonus[source]
            )

            candidate = {
                "name": metric["name"],
                "chinese_name": metric["chinese_name"],
                "matched_text": term,
                "match_source": source,
                "score": score,
            }

            if (
                best is None
                or candidate["score"] > best["score"]
            ):
                best = candidate

        if best is not None:
            matches.append(best)

    if not matches:
        return ()

    max_score = max(
        item["score"]
        for item in matches
    )

    top = [
        item
        for item in matches
        if item["score"] == max_score
    ]

    top.sort(
        key=lambda item: item["name"]
    )

    return tuple(top)
