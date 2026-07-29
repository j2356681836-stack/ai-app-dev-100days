from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

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

REPRESENTATION_METHODS = (
    "single_document",
    "identity_only",
    "definition_only",
    "examples_only_max",
    "semantic_core_max",
    "single_definition_max",
    "multiview_max",
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


def _sorted_candidates(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return sorted(
        rows,
        key=lambda item: (
            -float(item["score"]),
            item["name"],
        ),
    )


def _select_view_score(
    candidate: dict[str, Any],
    *,
    allowed_view_types: set[str],
) -> tuple[float | None, str | None, str | None]:
    matching = [
        row
        for row in candidate.get(
            "view_scores",
            []
        )
        if row["view_type"]
        in allowed_view_types
    ]

    if not matching:
        return (
            None,
            None,
            None,
        )

    winner = max(
        matching,
        key=lambda row: (
            float(row["score"]),
            row["view_id"],
        ),
    )

    return (
        float(winner["score"]),
        winner["view_type"],
        winner["view_id"],
    )


def build_representation_rankings_v2(
    *,
    single_candidates: list[dict[str, Any]],
    multiview_candidates: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """
    Build comparable metric rankings from the same evidence.

    No learned/manual weights are used.

    identity_only:
        identity view only

    definition_only:
        definition view only

    examples_only_max:
        max(example_i)

    semantic_core_max:
        max(identity, definition, formula)

    single_definition_max:
        max(single-document score, definition score)

    multiview_max:
        original Gate 5D-A max over all views
    """
    single_by_metric = {
        item["name"]: item
        for item in single_candidates
    }

    multiview_by_metric = {
        item["name"]: item
        for item in multiview_candidates
    }

    names = set(
        single_by_metric
    ) | set(
        multiview_by_metric
    )

    rankings: dict[
        str,
        list[dict[str, Any]],
    ] = {
        method: []
        for method in REPRESENTATION_METHODS
    }

    for name in names:
        single = single_by_metric.get(
            name
        )
        multi = multiview_by_metric.get(
            name
        )

        chinese_name = (
            None
            if multi is None
            else multi.get(
                "chinese_name"
            )
        )

        if chinese_name is None and single is not None:
            chinese_name = single.get(
                "chinese_name"
            )

        if single is not None:
            rankings[
                "single_document"
            ].append(
                {
                    "name": name,
                    "chinese_name": chinese_name,
                    "score": float(
                        single["score"]
                    ),
                    "evidence_type": (
                        "single_document"
                    ),
                    "evidence_id": (
                        "single_document"
                    ),
                }
            )

        if multi is None:
            continue

        for method, allowed_types in (
            (
                "identity_only",
                {
                    "identity",
                },
            ),
            (
                "definition_only",
                {
                    "definition",
                },
            ),
            (
                "examples_only_max",
                {
                    "example",
                },
            ),
            (
                "semantic_core_max",
                {
                    "identity",
                    "definition",
                    "formula",
                },
            ),
        ):
            (
                score,
                view_type,
                view_id,
            ) = _select_view_score(
                multi,
                allowed_view_types=(
                    allowed_types
                ),
            )

            if score is not None:
                rankings[
                    method
                ].append(
                    {
                        "name": name,
                        "chinese_name": chinese_name,
                        "score": score,
                        "evidence_type": view_type,
                        "evidence_id": view_id,
                    }
                )

        definition_score, _, definition_id = (
            _select_view_score(
                multi,
                allowed_view_types={
                    "definition",
                },
            )
        )

        if (
            single is not None
            and definition_score is not None
        ):
            single_score = float(
                single["score"]
            )

            if single_score >= definition_score:
                fused_score = single_score
                evidence_type = (
                    "single_document"
                )
                evidence_id = (
                    "single_document"
                )
            else:
                fused_score = (
                    definition_score
                )
                evidence_type = (
                    "definition"
                )
                evidence_id = (
                    definition_id
                )

            rankings[
                "single_definition_max"
            ].append(
                {
                    "name": name,
                    "chinese_name": chinese_name,
                    "score": fused_score,
                    "evidence_type": evidence_type,
                    "evidence_id": evidence_id,
                }
            )

        rankings[
            "multiview_max"
        ].append(
            {
                "name": name,
                "chinese_name": chinese_name,
                "score": float(
                    multi["score"]
                ),
                "evidence_type": multi.get(
                    "winning_view_type"
                ),
                "evidence_id": multi.get(
                    "winning_view_id"
                ),
            }
        )

    return {
        method: _sorted_candidates(
            rankings[
                method
            ]
        )
        for method in REPRESENTATION_METHODS
    }


def evaluate_view_ablation_case_v2(
    *,
    case,
) -> dict[str, Any]:
    single = (
        rank_metric_candidates_by_embedding_v2(
            case.question,
            top_k=19,
        )
    )

    multiview = (
        rank_metric_candidates_multiview_v2(
            case.question,
            top_k=None,
        )
    )

    rankings = (
        build_representation_rankings_v2(
            single_candidates=single[
                "candidates"
            ],
            multiview_candidates=multiview[
                "candidates"
            ],
        )
    )

    methods = {}

    for method in REPRESENTATION_METHODS:
        candidates = rankings[
            method
        ]

        rank = _rank_of_metric(
            candidates,
            case.metric_name,
        )

        expected = (
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

        methods[
            method
        ] = {
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
            "top1_evidence_type": (
                None
                if top1 is None
                else top1[
                    "evidence_type"
                ]
            ),
            "top1_evidence_id": (
                None
                if top1 is None
                else top1[
                    "evidence_id"
                ]
            ),
            "expected_metric_score": (
                None
                if expected is None
                else expected[
                    "score"
                ]
            ),
            "expected_metric_evidence_type": (
                None
                if expected is None
                else expected[
                    "evidence_type"
                ]
            ),
            "expected_metric_evidence_id": (
                None
                if expected is None
                else expected[
                    "evidence_id"
                ]
            ),
            "candidate_count": len(
                candidates
            ),
        }

    return {
        "case_id": case.case_id,
        "metric_name": case.metric_name,
        "question": case.question,
        "methods": methods,
    }


def summarize_method_v2(
    *,
    results: list[dict[str, Any]],
    method: str,
) -> dict[str, Any]:
    method_rows = [
        {
            "case_id": item[
                "case_id"
            ],
            "metric_name": item[
                "metric_name"
            ],
            "question": item[
                "question"
            ],
            **item["methods"][
                method
            ],
        }
        for item in results
    ]

    ranks = [
        row["rank"]
        for row in method_rows
        if row["rank"] is not None
    ]

    total = len(
        method_rows
    )

    recall = {}

    for cutoff in RANK_CUTOFFS:
        hit = sum(
            1
            for rank in ranks
            if rank <= cutoff
        )

        recall[
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
        list[dict[str, Any]],
    ] = defaultdict(list)

    for row in method_rows:
        by_metric[
            row["metric_name"]
        ].append(
            row
        )

    per_metric = {}

    for metric_name in sorted(
        by_metric
    ):
        rows = by_metric[
            metric_name
        ]

        metric_ranks = [
            row["rank"]
            for row in rows
        ]

        present = [
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
                if not present
                else round(
                    sum(present)
                    / len(present),
                    4,
                )
            ),
            "worst_rank": (
                None
                if not present
                else max(
                    present
                )
            ),
            "top1_correct": sum(
                1
                for rank in metric_ranks
                if rank == 1
            ),
        }

    reciprocal = [
        row[
            "reciprocal_rank"
        ]
        for row in method_rows
    ]

    top1_evidence_counts: dict[
        str,
        int,
    ] = defaultdict(int)

    top1_wrong_evidence_counts: dict[
        str,
        int,
    ] = defaultdict(int)

    expected_evidence_counts: dict[
        str,
        int,
    ] = defaultdict(int)

    for row in method_rows:
        top1_type = row[
            "top1_evidence_type"
        ]

        expected_type = row[
            "expected_metric_evidence_type"
        ]

        if top1_type:
            top1_evidence_counts[
                top1_type
            ] += 1

            if row["rank"] != 1:
                top1_wrong_evidence_counts[
                    top1_type
                ] += 1

        if expected_type:
            expected_evidence_counts[
                expected_type
            ] += 1

    return {
        "total": total,
        "recall": recall,
        "mrr": (
            None
            if not reciprocal
            else round(
                sum(
                    reciprocal
                )
                / len(
                    reciprocal
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
            total
            - len(
                ranks
            )
        ),
        "top1_evidence_counts": dict(
            sorted(
                top1_evidence_counts.items()
            )
        ),
        "top1_wrong_evidence_counts": dict(
            sorted(
                top1_wrong_evidence_counts.items()
            )
        ),
        "expected_metric_evidence_counts": dict(
            sorted(
                expected_evidence_counts.items()
            )
        ),
        "per_metric": per_metric,
    }


def build_method_comparison_v2(
    *,
    baseline: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    comparison = {
        "mrr_delta": round(
            candidate["mrr"]
            - baseline["mrr"],
            6,
        ),
        "average_rank_delta": round(
            candidate[
                "average_rank"
            ]
            - baseline[
                "average_rank"
            ],
            6,
        ),
        "worst_rank_delta": (
            candidate[
                "worst_rank"
            ]
            - baseline[
                "worst_rank"
            ]
        ),
    }

    for cutoff in RANK_CUTOFFS:
        key = (
            f"recall_at_{cutoff}"
        )

        comparison[
            f"{key}_rate_delta"
        ] = round(
            candidate[
                "recall"
            ][
                key
            ][
                "rate"
            ]
            - baseline[
                "recall"
            ][
                key
            ][
                "rate"
            ],
            2,
        )

    return comparison


def run_view_ablation_benchmark_v2(
) -> dict[str, Any]:
    results = [
        evaluate_view_ablation_case_v2(
            case=case
        )
        for case in (
            SEMANTIC_FALLBACK_POSITIVE_CASES_V2
        )
    ]

    summaries = {
        method: summarize_method_v2(
            results=results,
            method=method,
        )
        for method in REPRESENTATION_METHODS
    }

    baseline = summaries[
        "single_document"
    ]

    comparisons = {
        method: build_method_comparison_v2(
            baseline=baseline,
            candidate=summaries[
                method
            ],
        )
        for method in REPRESENTATION_METHODS
        if method
        != "single_document"
    }

    return {
        "evaluation": (
            "day74_gate5db_view_ablation_fusion"
        ),
        "case_count": len(
            SEMANTIC_FALLBACK_POSITIVE_CASES_V2
        ),
        "methods": list(
            REPRESENTATION_METHODS
        ),
        "single_document_corpus_fingerprint": (
            metric_semantic_corpus_fingerprint_v2()
        ),
        "multiview_corpus_fingerprint": (
            metric_multiview_corpus_fingerprint_v2()
        ),
        "summaries": summaries,
        "comparisons_vs_single_document": (
            comparisons
        ),
        "results": results,
        "threshold_policy": None,
        "gap_policy": None,
        "manual_view_weights": None,
        "runtime_integration": False,
    }


def save_view_ablation_benchmark_v2(
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
            "semantic_view_ablation_benchmark_v2_"
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


def _print_summary(
    method: str,
    summary: dict[str, Any],
) -> None:
    print("-" * 80)
    print(method)

    for cutoff in (
        1,
        3,
        6,
        12,
        19,
    ):
        key = (
            f"recall_at_{cutoff}"
        )

        print(
            f"Recall@{cutoff}:",
            summary[
                "recall"
            ][
                key
            ],
        )

    print(
        "MRR:",
        summary[
            "mrr"
        ],
    )

    print(
        "Average Rank:",
        summary[
            "average_rank"
        ],
    )

    print(
        "Median Rank:",
        summary[
            "median_rank"
        ],
    )

    print(
        "Worst Rank:",
        summary[
            "worst_rank"
        ],
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.parse_args()

    report = (
        run_view_ablation_benchmark_v2()
    )

    print("=" * 80)
    print(
        "Semantic View Ablation Benchmark V2"
    )
    print(
        "Cases:",
        report[
            "case_count"
        ],
    )

    for method in REPRESENTATION_METHODS:
        _print_summary(
            method,
            report[
                "summaries"
            ][
                method
            ],
        )

    print("-" * 80)
    print(
        "Comparisons vs single_document:"
    )

    for method, comparison in report[
        "comparisons_vs_single_document"
    ].items():
        print(
            method,
            comparison,
        )

    print(
        "Threshold Policy:",
        report[
            "threshold_policy"
        ],
    )
    print(
        "Gap Policy:",
        report[
            "gap_policy"
        ],
    )
    print(
        "Manual View Weights:",
        report[
            "manual_view_weights"
        ],
    )
    print(
        "Runtime Integration:",
        report[
            "runtime_integration"
        ],
    )

    path = (
        save_view_ablation_benchmark_v2(
            report
        )
    )

    print(
        "Saved to:",
        path,
    )


if __name__ == "__main__":
    main()
