from __future__ import annotations

import hashlib
import json
from typing import Any

from app.semantic_layer.metric_loader_v2 import load_metrics_v2


SEMANTIC_CORPUS_VERSION = "beauty_bi_v2_metric_semantic_corpus_1"


def _normalize_sequence(
    values: list[Any] | tuple[Any, ...] | None,
) -> tuple[str, ...]:
    if not values:
        return ()

    return tuple(
        str(value).strip()
        for value in values
        if str(value).strip()
    )


def build_metric_semantic_document_v2(
    metric: dict[str, Any],
) -> dict[str, Any]:
    """
    将单个 Dataset V2 Metric 转成纯业务语义文档。

    进入：
    name / chinese_name / aliases / definition / formula / examples

    不进入：
    negative_examples / tables / filters /
    Query Plan resource/scope contracts
    """
    return {
        "name": str(
            metric.get("name", "")
        ).strip(),
        "chinese_name": str(
            metric.get("chinese_name", "")
        ).strip(),
        "aliases": _normalize_sequence(
            metric.get("aliases")
        ),
        "definition": str(
            metric.get("definition", "")
        ).strip(),
        "formula": str(
            metric.get("formula", "")
        ).strip(),
        "examples": _normalize_sequence(
            metric.get("examples")
        ),
    }


def render_metric_semantic_text_v2(
    document: dict[str, Any],
) -> str:
    aliases_text = "\n".join(
        f"- {item}"
        for item in document["aliases"]
    )

    examples_text = "\n".join(
        f"- {item}"
        for item in document["examples"]
    )

    return f"""
指标名称：
{document["chinese_name"]}

技术名称：
{document["name"]}

业务定义：
{document["definition"]}

计算公式：
{document["formula"]}

常见说法：
{aliases_text}

适用问题：
{examples_text}
""".strip()


def build_all_metric_semantic_documents_v2(
) -> tuple[dict[str, Any], ...]:
    documents = tuple(
        build_metric_semantic_document_v2(
            metric
        )
        for metric in load_metrics_v2()
    )

    names = [
        document["name"]
        for document in documents
    ]

    if len(names) != len(set(names)):
        raise ValueError(
            "Dataset V2 semantic corpus contains "
            "duplicate metric names."
        )

    return documents


def build_all_metric_texts_v2(
) -> tuple[dict[str, str], ...]:
    return tuple(
        {
            "name": document["name"],
            "chinese_name": document[
                "chinese_name"
            ],
            "text": (
                render_metric_semantic_text_v2(
                    document
                )
            ),
        }
        for document
        in build_all_metric_semantic_documents_v2()
    )


def canonical_metric_semantic_corpus_v2(
) -> bytes:
    payload = {
        "corpus_version": (
            SEMANTIC_CORPUS_VERSION
        ),
        "documents": list(
            build_all_metric_semantic_documents_v2()
        ),
    }

    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def metric_semantic_corpus_fingerprint_v2(
) -> str:
    return hashlib.sha256(
        canonical_metric_semantic_corpus_v2()
    ).hexdigest()


if __name__ == "__main__":
    print(
        "Semantic Corpus Fingerprint:",
        metric_semantic_corpus_fingerprint_v2(),
    )

    for item in build_all_metric_texts_v2():
        print("=" * 80)
        print(item["name"])
        print(item["text"])
