from __future__ import annotations

from app.evaluation.semantic_fallback_calibration_cases_v2 import (
    SEMANTIC_FALLBACK_POSITIVE_CASES_V2,
)
from app.evaluation.semantic_multiview_benchmark_v2 import (
    build_comparison_v2,
    summarize_rank_results_v2,
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


def test_benchmark_uses_exactly_57_fallback_cases() -> None:
    assert_equal(
        len(
            SEMANTIC_FALLBACK_POSITIVE_CASES_V2
        ),
        57,
        "Gate 5D-A Benchmark 必须使用 57 Fallback Positives。",
    )


def test_rank_summary_calculation() -> None:
    results = [
        {
            "metric_name": "a",
            "rank": 1,
            "reciprocal_rank": 1.0,
        },
        {
            "metric_name": "a",
            "rank": 2,
            "reciprocal_rank": 0.5,
        },
        {
            "metric_name": "b",
            "rank": 4,
            "reciprocal_rank": 0.25,
        },
        {
            "metric_name": "b",
            "rank": None,
            "reciprocal_rank": 0.0,
        },
    ]

    summary = summarize_rank_results_v2(
        results
    )

    assert_equal(
        summary["recall"][
            "recall_at_1"
        ][
            "hit"
        ],
        1,
        "Recall@1 hit 错误。",
    )

    assert_equal(
        summary["recall"][
            "recall_at_2"
        ][
            "hit"
        ],
        2,
        "Recall@2 hit 错误。",
    )

    assert_equal(
        summary["recall"][
            "recall_at_6"
        ][
            "hit"
        ],
        3,
        "Recall@6 hit 错误。",
    )

    assert_equal(
        summary[
            "missing_from_candidate_pool"
        ],
        1,
        "Missing Candidate 统计错误。",
    )

    assert_true(
        abs(
            summary["mrr"]
            - 0.4375
        )
        < 1e-9,
        "MRR 计算错误。",
    )

    assert_true(
        abs(
            summary["average_rank"]
            - (
                7.0
                / 3.0
            )
        )
        < 1e-6,
        "Average Rank 计算错误。",
    )

    assert_equal(
        summary["median_rank"],
        2.0,
        "Median Rank 计算错误。",
    )

    assert_equal(
        summary["worst_rank"],
        4,
        "Worst Rank 计算错误。",
    )


def test_per_metric_summary_preserves_three_ranks() -> None:
    results = [
        {
            "metric_name": "gmv",
            "rank": 12,
            "reciprocal_rank": 1 / 12,
        },
        {
            "metric_name": "gmv",
            "rank": 1,
            "reciprocal_rank": 1.0,
        },
        {
            "metric_name": "gmv",
            "rank": 2,
            "reciprocal_rank": 0.5,
        },
    ]

    summary = summarize_rank_results_v2(
        results
    )

    assert_equal(
        summary["per_metric"][
            "gmv"
        ][
            "ranks"
        ],
        [
            12,
            1,
            2,
        ],
        "Per-metric 应保留原始 3 个 ranks。",
    )

    assert_equal(
        summary["per_metric"][
            "gmv"
        ][
            "worst_rank"
        ],
        12,
        "Per-metric worst rank 错误。",
    )


def test_comparison_reports_delta_without_policy() -> None:
    baseline = {
        "mrr": 0.50,
        "average_rank": 4.0,
        "recall": {
            f"recall_at_{cutoff}": {
                "rate": rate
            }
            for cutoff, rate in (
                (1, 40.0),
                (2, 60.0),
                (3, 70.0),
                (4, 75.0),
                (5, 80.0),
                (6, 85.0),
                (9, 90.0),
                (12, 95.0),
                (15, 100.0),
                (19, 100.0),
            )
        },
    }

    multiview = {
        "mrr": 0.70,
        "average_rank": 2.5,
        "recall": {
            f"recall_at_{cutoff}": {
                "rate": rate
            }
            for cutoff, rate in (
                (1, 60.0),
                (2, 75.0),
                (3, 85.0),
                (4, 90.0),
                (5, 92.0),
                (6, 95.0),
                (9, 98.0),
                (12, 100.0),
                (15, 100.0),
                (19, 100.0),
            )
        },
    }

    comparison = build_comparison_v2(
        baseline,
        multiview,
    )

    assert_equal(
        comparison["mrr_delta"],
        0.20,
        "MRR Delta 错误。",
    )

    assert_equal(
        comparison[
            "average_rank_delta"
        ],
        -1.5,
        "Average Rank Delta 错误。",
    )

    assert_equal(
        comparison[
            "recall_at_1_rate_delta"
        ],
        20.0,
        "Recall@1 Delta 错误。",
    )


def test_fallback_cases_have_three_per_metric() -> None:
    counts = {}

    for case in (
        SEMANTIC_FALLBACK_POSITIVE_CASES_V2
    ):
        counts[
            case.metric_name
        ] = counts.get(
            case.metric_name,
            0,
        ) + 1

    assert_equal(
        len(counts),
        19,
        "Benchmark 应覆盖 19 Metrics。",
    )

    assert_true(
        all(
            count == 3
            for count in counts.values()
        ),
        "Benchmark 每个 Metric 应恰好 3 条。",
    )


def run_tests() -> None:
    tests = [
        test_benchmark_uses_exactly_57_fallback_cases,
        test_rank_summary_calculation,
        test_per_metric_summary_preserves_three_ranks,
        test_comparison_reports_delta_without_policy,
        test_fallback_cases_have_three_per_metric,
    ]

    passed = 0
    failed = 0

    for test in tests:
        print("=" * 80)
        print(f"Running: {test.__name__}")

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
        "Semantic Multi-view Benchmark V2 Test Summary"
    )
    print(f"Total: {len(tests)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(
        "Benchmark Cases:",
        len(
            SEMANTIC_FALLBACK_POSITIVE_CASES_V2
        ),
    )

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    run_tests()
