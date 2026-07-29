from __future__ import annotations

from app.evaluation.semantic_view_ablation_benchmark_v2 import (
    REPRESENTATION_METHODS,
    build_method_comparison_v2,
    build_representation_rankings_v2,
    summarize_method_v2,
)


def assert_equal(
    actual,
    expected,
    message: str,
) -> None:
    if actual != expected:
        raise AssertionError(
            f"{message}\n"
            f"Expected: {expected}\n"
            f"Actual: {actual}"
        )


def assert_true(
    condition: bool,
    message: str,
) -> None:
    if not condition:
        raise AssertionError(message)


def fake_multiview_candidate(
    *,
    name: str,
    identity: float,
    definition: float,
    formula: float,
    examples: tuple[float, float],
):
    view_scores = [
        {
            "view_id": "identity",
            "view_type": "identity",
            "score": identity,
        },
        {
            "view_id": "definition",
            "view_type": "definition",
            "score": definition,
        },
        {
            "view_id": "formula",
            "view_type": "formula",
            "score": formula,
        },
        {
            "view_id": "example_01",
            "view_type": "example",
            "score": examples[0],
        },
        {
            "view_id": "example_02",
            "view_type": "example",
            "score": examples[1],
        },
    ]

    winner = max(
        view_scores,
        key=lambda row: row[
            "score"
        ],
    )

    return {
        "name": name,
        "chinese_name": name,
        "score": winner[
            "score"
        ],
        "winning_view_type": winner[
            "view_type"
        ],
        "winning_view_id": winner[
            "view_id"
        ],
        "view_scores": view_scores,
    }


def test_representation_methods_are_fixed_and_unweighted() -> None:
    assert_equal(
        REPRESENTATION_METHODS,
        (
            "single_document",
            "identity_only",
            "definition_only",
            "examples_only_max",
            "semantic_core_max",
            "single_definition_max",
            "multiview_max",
        ),
        "Gate 5D-B methods 不得漂移。",
    )


def test_representation_rankings_use_expected_evidence() -> None:
    single = [
        {
            "name": "a",
            "chinese_name": "A",
            "score": 0.60,
        },
        {
            "name": "b",
            "chinese_name": "B",
            "score": 0.55,
        },
    ]

    multiview = [
        fake_multiview_candidate(
            name="a",
            identity=0.20,
            definition=0.70,
            formula=0.30,
            examples=(
                0.40,
                0.50,
            ),
        ),
        fake_multiview_candidate(
            name="b",
            identity=0.80,
            definition=0.50,
            formula=0.65,
            examples=(
                0.90,
                0.45,
            ),
        ),
    ]

    rankings = (
        build_representation_rankings_v2(
            single_candidates=single,
            multiview_candidates=multiview,
        )
    )

    assert_equal(
        [
            row["name"]
            for row in rankings[
                "definition_only"
            ]
        ],
        [
            "a",
            "b",
        ],
        "Definition-only 排序错误。",
    )

    assert_equal(
        [
            row["name"]
            for row in rankings[
                "examples_only_max"
            ]
        ],
        [
            "b",
            "a",
        ],
        "Examples-only Max 排序错误。",
    )

    assert_equal(
        [
            row["name"]
            for row in rankings[
                "semantic_core_max"
            ]
        ],
        [
            "b",
            "a",
        ],
        "Semantic-core Max 排序错误。",
    )

    assert_equal(
        [
            row["name"]
            for row in rankings[
                "single_definition_max"
            ]
        ],
        [
            "a",
            "b",
        ],
        "Single+Definition Max 排序错误。",
    )

    assert_equal(
        rankings[
            "single_definition_max"
        ][0][
            "evidence_type"
        ],
        "definition",
        "A 应由 definition 0.70 赢过 single 0.60。",
    )

    assert_equal(
        rankings[
            "single_definition_max"
        ][1][
            "evidence_type"
        ],
        "single_document",
        "B 应由 single 0.55 赢过 definition 0.50。",
    )


def test_single_definition_fusion_has_no_manual_weight() -> None:
    single = [
        {
            "name": "a",
            "chinese_name": "A",
            "score": 0.51,
        },
    ]

    multiview = [
        fake_multiview_candidate(
            name="a",
            identity=0.20,
            definition=0.50,
            formula=0.99,
            examples=(
                0.99,
                0.99,
            ),
        ),
    ]

    rankings = (
        build_representation_rankings_v2(
            single_candidates=single,
            multiview_candidates=multiview,
        )
    )

    fused = rankings[
        "single_definition_max"
    ][0]

    assert_equal(
        fused["score"],
        0.51,
        "Fusion 必须只比较 single 与 definition，不得混入 formula/example。",
    )

    assert_equal(
        fused["evidence_type"],
        "single_document",
        "0.51 > 0.50 时应保留 single evidence。",
    )


def test_summary_calculates_rank_and_evidence_statistics() -> None:
    results = [
        {
            "case_id": "x1",
            "metric_name": "a",
            "question": "q1",
            "methods": {
                "definition_only": {
                    "rank": 1,
                    "reciprocal_rank": 1.0,
                    "top1_evidence_type": "definition",
                    "expected_metric_evidence_type": "definition",
                }
            },
        },
        {
            "case_id": "x2",
            "metric_name": "a",
            "question": "q2",
            "methods": {
                "definition_only": {
                    "rank": 2,
                    "reciprocal_rank": 0.5,
                    "top1_evidence_type": "definition",
                    "expected_metric_evidence_type": "definition",
                }
            },
        },
        {
            "case_id": "x3",
            "metric_name": "b",
            "question": "q3",
            "methods": {
                "definition_only": {
                    "rank": 4,
                    "reciprocal_rank": 0.25,
                    "top1_evidence_type": "definition",
                    "expected_metric_evidence_type": "definition",
                }
            },
        },
    ]

    summary = summarize_method_v2(
        results=results,
        method="definition_only",
    )

    assert_equal(
        summary["recall"][
            "recall_at_1"
        ][
            "hit"
        ],
        1,
        "Recall@1 错误。",
    )

    assert_equal(
        summary["recall"][
            "recall_at_3"
        ][
            "hit"
        ],
        2,
        "Recall@3 错误。",
    )

    assert_true(
        abs(
            summary["mrr"]
            - (
                1.75
                / 3
            )
        )
        < 1e-6,
        "MRR 错误。",
    )

    assert_equal(
        summary[
            "top1_evidence_counts"
        ][
            "definition"
        ],
        3,
        "Top1 evidence count 错误。",
    )

    assert_equal(
        summary[
            "top1_wrong_evidence_counts"
        ][
            "definition"
        ],
        2,
        "Wrong Top1 evidence count 错误。",
    )


def test_comparison_reports_baseline_deltas() -> None:
    def summary(
        *,
        mrr,
        avg,
        worst,
        recall1,
    ):
        return {
            "mrr": mrr,
            "average_rank": avg,
            "worst_rank": worst,
            "recall": {
                f"recall_at_{cutoff}": {
                    "rate": (
                        recall1
                        if cutoff == 1
                        else 100.0
                    )
                }
                for cutoff in (
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
            },
        }

    baseline = summary(
        mrr=0.50,
        avg=4.0,
        worst=14,
        recall1=40.0,
    )

    candidate = summary(
        mrr=0.62,
        avg=3.0,
        worst=10,
        recall1=55.0,
    )

    comparison = (
        build_method_comparison_v2(
            baseline=baseline,
            candidate=candidate,
        )
    )

    assert_equal(
        comparison[
            "mrr_delta"
        ],
        0.12,
        "MRR delta 错误。",
    )

    assert_equal(
        comparison[
            "average_rank_delta"
        ],
        -1.0,
        "Average Rank delta 错误。",
    )

    assert_equal(
        comparison[
            "worst_rank_delta"
        ],
        -4,
        "Worst Rank delta 错误。",
    )

    assert_equal(
        comparison[
            "recall_at_1_rate_delta"
        ],
        15.0,
        "Recall@1 delta 错误。",
    )


def run_tests() -> None:
    tests = [
        test_representation_methods_are_fixed_and_unweighted,
        test_representation_rankings_use_expected_evidence,
        test_single_definition_fusion_has_no_manual_weight,
        test_summary_calculates_rank_and_evidence_statistics,
        test_comparison_reports_baseline_deltas,
    ]

    passed = 0
    failed = 0

    for test in tests:
        print("=" * 80)
        print(
            f"Running: {test.__name__}"
        )

        try:
            test()
            passed += 1
            print("[PASS]")
        except Exception as exc:
            failed += 1
            print("[FAIL]")
            print(exc)

    print("=" * 80)
    print(
        "Semantic View Ablation Benchmark V2 Test Summary"
    )
    print(
        f"Total: {len(tests)}"
    )
    print(
        f"Passed: {passed}"
    )
    print(
        f"Failed: {failed}"
    )
    print(
        "Methods:",
        len(
            REPRESENTATION_METHODS
        ),
    )

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    run_tests()
