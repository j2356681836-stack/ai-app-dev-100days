from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from app.evaluation.semantic_fallback_calibration_cases_v2 import (
    SEMANTIC_FALLBACK_POSITIVE_CASES_V2,
)
from app.semantic_layer.metric_multiview_v2 import (
    metric_multiview_corpus_fingerprint_v2,
    rank_metric_candidates_multiview_v2,
)
from app.semantic_layer.metric_semantic_search_v2 import (
    rank_metric_candidates_by_embedding_v2,
)
from app.semantic_layer.metric_text_builder_v2 import (
    metric_semantic_corpus_fingerprint_v2,
)


RANK_CUTOFFS = (
    1,
    2,
    3,
    4,
    5,
    6,
    9,
    12,
    15,
    19,
)


def _rank_of_metric(
    candidates: list[dict[str, Any]],
    expected_metric: str,
) -> int | None:
    for index, candidate in enumerate(
        candidates,
        start=1,
    ):
        if candidate["name"] == expected_metric:
            return index

    return None


def evaluate_retrieval_method_v2(
    *,
    method_name: str,
    rank_fn: Callable[
        [str],
        dict[str, Any],
    ],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    for case in SEMANTIC_FALLBACK_POSITIVE_CASES_V2:
        retrieval = rank_fn(
            case.question
        )

        candidates = retrieval[
            "candidates"
        ]

        rank = _rank_of_metric(
            candidates,
            case.metric_name,
        )

        expected_candidate = (
            None
            if rank is None
            else candidates[
                rank - 1
            ]
        )

        top1 = (
            None
            if not candidates
            else candidates[0]
        )

        results.append(
            {
                "case_id": case.case_id,
                "metric_name": case.metric_name,
                "question": case.question,
                "method": method_name,
                "rank": rank,
                "reciprocal_rank": (
                    0.0
                    if rank is None
                    else 1.0 / rank
                ),
                "top1_metric": (
                    None
                    if top1 is None
                    else top1["name"]
                ),
                "top1_score": (
                    None
                    if top1 is None
                    else top1["score"]
                ),
                "expected_metric_score": (
                    None
                    if expected_candidate is None
                    else expected_candidate[
                        "score"
                    ]
                ),
                "expected_metric_winning_view_type": (
                    None
                    if expected_candidate is None
                    else expected_candidate.get(
                        "winning_view_type"
                    )
                ),
                "expected_metric_winning_view_id": (
                    None
                    if expected_candidate is None
                    else expected_candidate.get(
                        "winning_view_id"
                    )
                ),
                "candidate_count": len(
                    candidates
                ),
                "candidates": candidates,
            }
        )

    return results


def summarize_rank_results_v2(
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    ranks = [
        item["rank"]
        for item in results
        if item["rank"] is not None
    ]

    total = len(results)

    recalls = {}

    for cutoff in RANK_CUTOFFS:
        hit = sum(
            1
            for rank in ranks
            if rank <= cutoff
        )

        recalls[
            f"recall_at_{cutoff}"
        ] = {
            "hit": hit,
            "total": total,
            "rate": (
                None
                if total == 0
                else round(
                    hit
                    / total
                    * 100,
                    2,
                )
            ),
        }

    by_metric: dict[
        str,
        list[int | None],
    ] = defaultdict(list)

    for item in results:
        by_metric[
            item["metric_name"]
        ].append(
            item["rank"]
        )

    per_metric = {}

    for metric_name in sorted(
        by_metric
    ):
        metric_ranks = by_metric[
            metric_name
        ]

        present_ranks = [
            rank
            for rank in metric_ranks
            if rank is not None
        ]

        per_metric[
            metric_name
        ] = {
            "ranks": metric_ranks,
            "average_rank": (
                None
                if not present_ranks
                else round(
                    sum(
                        present_ranks
                    )
                    / len(
                        present_ranks
                    ),
                    4,
                )
            ),
            "worst_rank": (
                None
                if not present_ranks
                else max(
                    present_ranks
                )
            ),
            "top1_correct": sum(
                1
                for rank in metric_ranks
                if rank == 1
            ),
        }

    reciprocal_ranks = [
        item["reciprocal_rank"]
        for item in results
    ]

    return {
        "total": total,
        "recall": recalls,
        "mrr": (
            None
            if not reciprocal_ranks
            else round(
                sum(
                    reciprocal_ranks
                )
                / len(
                    reciprocal_ranks
                ),
                6,
            )
        ),
        "average_rank": (
            None
            if not ranks
            else round(
                sum(ranks)
                / len(ranks),
                6,
            )
        ),
        "median_rank": (
            None
            if not ranks
            else float(
                statistics.median(
                    ranks
                )
            )
        ),
        "worst_rank": (
            None
            if not ranks
            else max(
                ranks
            )
        ),
        "missing_from_candidate_pool": (
            total - len(ranks)
        ),
        "per_metric": per_metric,
    }


def build_comparison_v2(
    baseline_summary: dict[str, Any],
    multiview_summary: dict[str, Any],
) -> dict[str, Any]:
    comparison = {
        "mrr_delta": round(
            multiview_summary["mrr"]
            - baseline_summary["mrr"],
            6,
        ),
        "average_rank_delta": round(
            multiview_summary[
                "average_rank"
            ]
            - baseline_summary[
                "average_rank"
            ],
            6,
        ),
    }

    for cutoff in RANK_CUTOFFS:
        key = f"recall_at_{cutoff}"
        comparison[
            f"{key}_rate_delta"
        ] = round(
            multiview_summary[
                "recall"
            ][
                key
            ][
                "rate"
            ]
            - baseline_summary[
                "recall"
            ][
                key
            ][
                "rate"
            ],
            2,
        )

    return comparison


def run_semantic_multiview_benchmark_v2(
) -> dict[str, Any]:
    baseline_results = (
        evaluate_retrieval_method_v2(
            method_name=(
                "single_document"
            ),
            rank_fn=lambda question: (
                rank_metric_candidates_by_embedding_v2(
                    question,
                    top_k=19,
                )
            ),
        )
    )

    multiview_results = (
        evaluate_retrieval_method_v2(
            method_name=(
                "multiview_max"
            ),
            rank_fn=lambda question: (
                rank_metric_candidates_multiview_v2(
                    question,
                    top_k=None,
                )
            ),
        )
    )

    baseline_summary = (
        summarize_rank_results_v2(
            baseline_results
        )
    )

    multiview_summary = (
        summarize_rank_results_v2(
            multiview_results
        )
    )

    return {
        "evaluation": (
            "day74_gate5da_multiview_semantic_representation"
        ),
        "case_count": len(
            SEMANTIC_FALLBACK_POSITIVE_CASES_V2
        ),
        "single_document_corpus_fingerprint": (
            metric_semantic_corpus_fingerprint_v2()
        ),
        "multiview_corpus_fingerprint": (
            metric_multiview_corpus_fingerprint_v2()
        ),
        "baseline": {
            "summary": baseline_summary,
            "results": baseline_results,
        },
        "multiview_max": {
            "summary": multiview_summary,
            "results": multiview_results,
        },
        "comparison": build_comparison_v2(
            baseline_summary,
            multiview_summary,
        ),
        "threshold_policy": None,
        "gap_policy": None,
        "runtime_integration": False,
    }


def save_semantic_multiview_benchmark_v2(
    report: dict[str, Any],
) -> Path:
    output_dir = Path(
        "docs/evaluation"
    )
    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    path = (
        output_dir
        / (
            "semantic_multiview_benchmark_v2_"
            f"{timestamp}.json"
        )
    )

    payload = {
        "timestamp": timestamp,
        **report,
    }

    with path.open(
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            payload,
            f,
            ensure_ascii=False,
            indent=2,
        )

    return path


def _print_method_summary(
    name: str,
    summary: dict[str, Any],
) -> None:
    print("-" * 80)
    print(name)
    print(
        "Recall@1:",
        summary["recall"][
            "recall_at_1"
        ],
    )
    print(
        "Recall@3:",
        summary["recall"][
            "recall_at_3"
        ],
    )
    print(
        "Recall@6:",
        summary["recall"][
            "recall_at_6"
        ],
    )
    print(
        "Recall@12:",
        summary["recall"][
            "recall_at_12"
        ],
    )
    print(
        "Recall@19:",
        summary["recall"][
            "recall_at_19"
        ],
    )
    print(
        "MRR:",
        summary["mrr"],
    )
    print(
        "Average Rank:",
        summary["average_rank"],
    )
    print(
        "Median Rank:",
        summary["median_rank"],
    )
    print(
        "Worst Rank:",
        summary["worst_rank"],
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.parse_args()

    report = (
        run_semantic_multiview_benchmark_v2()
    )

    print("=" * 80)
    print(
        "Semantic Multi-view Benchmark V2"
    )
    print(
        "Cases:",
        report["case_count"],
    )

    _print_method_summary(
        "Single-document Baseline",
        report["baseline"][
            "summary"
        ],
    )

    _print_method_summary(
        "Multi-view Max",
        report["multiview_max"][
            "summary"
        ],
    )

    print("-" * 80)
    print(
        "Comparison:",
        report["comparison"],
    )
    print(
        "Threshold Policy:",
        report["threshold_policy"],
    )
    print(
        "Gap Policy:",
        report["gap_policy"],
    )
    print(
        "Runtime Integration:",
        report["runtime_integration"],
    )

    path = (
        save_semantic_multiview_benchmark_v2(
            report
        )
    )

    print(
        "Saved to:",
        path,
    )


if __name__ == "__main__":
    main()
