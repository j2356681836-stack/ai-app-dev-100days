from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from app.evaluation.golden_case_v2_models import (
    MetricDecisionStatus,
    PlanDecisionStatus,
)
from app.evaluation.golden_cases_v2 import GOLDEN_CASES_V2
from app.semantic_layer.decision_resolver_v2 import (
    MetricResolutionStatus,
    PlanResolutionStatus,
    resolve_decision_v2,
)


def _enum_value(value):
    if value is None:
        return None

    return getattr(value, "value", value)


def _append_mismatch(
    mismatches: list[dict],
    *,
    mismatch_type: str,
    layer: str,
    expected,
    actual,
) -> None:
    mismatches.append(
        {
            "type": mismatch_type,
            "layer": layer,
            "expected": expected,
            "actual": actual,
        }
    )


def evaluate_case_v2(case) -> dict:
    """
    评估单个 Day74 Golden Case。

    Evaluation 顺序：
        Metric
        → Intent Shape（仅 matched）
        → Plan（仅 matched）

    Clarification / Unsupported Metric 在 Metric 层结束，
    不继续用后续层制造伪失败。
    """
    actual = resolve_decision_v2(case.question)

    metric_mismatches: list[dict] = []
    intent_mismatches: list[dict] = []
    plan_mismatches: list[dict] = []

    expected_metric_status = case.expected_metric.status.value
    actual_metric_status = actual.metric.status.value

    if expected_metric_status != actual_metric_status:
        _append_mismatch(
            metric_mismatches,
            mismatch_type="metric_status_mismatch",
            layer="metric",
            expected=expected_metric_status,
            actual=actual_metric_status,
        )

    expected_metric_name = case.expected_metric.metric_name
    actual_metric_name = actual.metric.metric_name

    if (
        case.expected_metric.status
        == MetricDecisionStatus.MATCHED
    ):
        if expected_metric_name != actual_metric_name:
            _append_mismatch(
                metric_mismatches,
                mismatch_type="metric_name_mismatch",
                layer="metric",
                expected=expected_metric_name,
                actual=actual_metric_name,
            )

    if (
        case.expected_metric.status
        == MetricDecisionStatus.NEEDS_CLARIFICATION
    ):
        expected_candidates = set(
            case.expected_metric.acceptable_candidates
        )
        actual_candidates = set(actual.metric.candidates)

        if expected_candidates != actual_candidates:
            _append_mismatch(
                metric_mismatches,
                mismatch_type="clarification_candidates_mismatch",
                layer="metric",
                expected=sorted(expected_candidates),
                actual=sorted(actual_candidates),
            )

    metric_passed = len(metric_mismatches) == 0

    # 非 matched Case 在 Metric 层终止。
    downstream_applicable = (
        case.expected_metric.status
        == MetricDecisionStatus.MATCHED
    )

    if downstream_applicable:
        expected_intent = case.expected_intent
        actual_intent = actual.intent

        # result_grain 是 matched Case 的核心业务形状，
        # 因此始终评分。
        expected_grain = _enum_value(
            expected_intent.result_grain
        )
        actual_grain = _enum_value(
            actual_intent.result_grain
        )

        if expected_grain != actual_grain:
            _append_mismatch(
                intent_mismatches,
                mismatch_type="result_grain_mismatch",
                layer="intent",
                expected=expected_grain,
                actual=actual_grain,
            )

        # Optional expectation semantics:
        #
        # Case 未声明 ranking_type / sort_direction，
        # 表示该字段本 Case 不参与评分，
        # 不是要求 Runtime 必须返回 None。
        if expected_intent.ranking_type is not None:
            expected_ranking = _enum_value(
                expected_intent.ranking_type
            )
            actual_ranking = _enum_value(
                actual_intent.ranking_type
            )

            if expected_ranking != actual_ranking:
                _append_mismatch(
                    intent_mismatches,
                    mismatch_type="ranking_type_mismatch",
                    layer="intent",
                    expected=expected_ranking,
                    actual=actual_ranking,
                )

        if expected_intent.sort_direction is not None:
            expected_sort = _enum_value(
                expected_intent.sort_direction
            )
            actual_sort = _enum_value(
                actual_intent.sort_direction
            )

            if expected_sort != actual_sort:
                _append_mismatch(
                    intent_mismatches,
                    mismatch_type="sort_direction_mismatch",
                    layer="intent",
                    expected=expected_sort,
                    actual=actual_sort,
                )

        # limit 只有在 Case 显式声明数量，
        # 或 ranking_type 本身要求“无 LIMIT”时参与评分。
        should_check_limit = (
            expected_intent.limit is not None
            or (
                expected_intent.ranking_type is not None
                and expected_intent.ranking_type.value
                == "ranking"
            )
        )

        if (
            should_check_limit
            and expected_intent.limit != actual_intent.limit
        ):
            _append_mismatch(
                intent_mismatches,
                mismatch_type="limit_mismatch",
                layer="intent",
                expected=expected_intent.limit,
                actual=actual_intent.limit,
            )

        expected_plan_status = case.expected_plan.status.value
        actual_plan_status = actual.plan.status.value

        if expected_plan_status != actual_plan_status:
            _append_mismatch(
                plan_mismatches,
                mismatch_type="plan_status_mismatch",
                layer="plan",
                expected=expected_plan_status,
                actual=actual_plan_status,
            )

        if (
            case.expected_plan.status
            == PlanDecisionStatus.SELECTED
        ):
            if case.expected_plan.plan_name != actual.plan.plan_name:
                _append_mismatch(
                    plan_mismatches,
                    mismatch_type="plan_name_mismatch",
                    layer="plan",
                    expected=case.expected_plan.plan_name,
                    actual=actual.plan.plan_name,
                )

    intent_passed = (
        None
        if not downstream_applicable
        else len(intent_mismatches) == 0
    )

    plan_passed = (
        None
        if not downstream_applicable
        else len(plan_mismatches) == 0
    )

    passed = (
        metric_passed
        and (
            not downstream_applicable
            or (
                intent_passed is True
                and plan_passed is True
            )
        )
    )

    return {
        "case_id": case.case_id,
        "split": case.split.value,
        "category": case.category.value,
        "question": case.question,
        "description": case.description,
        "passed": passed,
        "layer_results": {
            "metric_passed": metric_passed,
            "intent_passed": intent_passed,
            "plan_passed": plan_passed,
        },
        "mismatches": [
            *metric_mismatches,
            *intent_mismatches,
            *plan_mismatches,
        ],
        "expected": {
            "metric": case.expected_metric.model_dump(
                mode="json"
            ),
            "intent": case.expected_intent.model_dump(
                mode="json"
            ),
            "plan": case.expected_plan.model_dump(
                mode="json"
            ),
        },
        "actual": actual.model_dump(
            mode="json"
        ),
    }


def _accuracy(
    passed: int,
    total: int,
) -> float | None:
    if total == 0:
        return None

    return round(
        passed / total * 100,
        2,
    )


def build_summary(results: list[dict]) -> dict:
    total = len(results)
    overall_passed = sum(
        1
        for item in results
        if item["passed"]
    )

    metric_total = total
    metric_passed = sum(
        1
        for item in results
        if item["layer_results"]["metric_passed"]
    )

    intent_items = [
        item
        for item in results
        if item["layer_results"]["intent_passed"]
        is not None
    ]
    intent_passed = sum(
        1
        for item in intent_items
        if item["layer_results"]["intent_passed"]
    )

    grain_passed = 0

    for item in intent_items:
        grain_failed = any(
            mismatch["type"]
            == "result_grain_mismatch"
            for mismatch in item["mismatches"]
        )

        if not grain_failed:
            grain_passed += 1

    plan_items = [
        item
        for item in results
        if item["layer_results"]["plan_passed"]
        is not None
    ]
    plan_passed = sum(
        1
        for item in plan_items
        if item["layer_results"]["plan_passed"]
    )

    clarification_items = [
        item
        for item in results
        if (
            item["expected"]["metric"]["status"]
            == MetricDecisionStatus.NEEDS_CLARIFICATION.value
        )
    ]
    clarification_passed = sum(
        1
        for item in clarification_items
        if item["layer_results"]["metric_passed"]
    )

    unsupported_shape_items = [
        item
        for item in results
        if (
            item["expected"]["plan"]["status"]
            == PlanDecisionStatus.UNSUPPORTED_SHAPE.value
        )
    ]
    unsupported_shape_passed = sum(
        1
        for item in unsupported_shape_items
        if (
            item["layer_results"]["metric_passed"]
            and item["layer_results"]["intent_passed"]
            and item["layer_results"]["plan_passed"]
        )
    )

    failures = Counter()

    for item in results:
        for mismatch in item["mismatches"]:
            failures[mismatch["type"]] += 1

    split_summary = {}

    for split in sorted(
        {
            item["split"]
            for item in results
        }
    ):
        split_items = [
            item
            for item in results
            if item["split"] == split
        ]

        split_passed = sum(
            1
            for item in split_items
            if item["passed"]
        )

        split_summary[split] = {
            "total": len(split_items),
            "passed": split_passed,
            "failed": len(split_items) - split_passed,
            "pass_rate": _accuracy(
                split_passed,
                len(split_items),
            ),
        }

    return {
        "total": total,
        "passed": overall_passed,
        "failed": total - overall_passed,
        "overall_pass_rate": _accuracy(
            overall_passed,
            total,
        ),
        "metric": {
            "total": metric_total,
            "passed": metric_passed,
            "accuracy": _accuracy(
                metric_passed,
                metric_total,
            ),
        },
        "intent_shape": {
            "total": len(intent_items),
            "passed": intent_passed,
            "accuracy": _accuracy(
                intent_passed,
                len(intent_items),
            ),
        },
        "grain": {
            "total": len(intent_items),
            "passed": grain_passed,
            "accuracy": _accuracy(
                grain_passed,
                len(intent_items),
            ),
        },
        "plan": {
            "total": len(plan_items),
            "passed": plan_passed,
            "accuracy": _accuracy(
                plan_passed,
                len(plan_items),
            ),
        },
        "clarification": {
            "total": len(clarification_items),
            "passed": clarification_passed,
            "accuracy": _accuracy(
                clarification_passed,
                len(clarification_items),
            ),
        },
        "unsupported_shape": {
            "total": len(unsupported_shape_items),
            "passed": unsupported_shape_passed,
            "accuracy": _accuracy(
                unsupported_shape_passed,
                len(unsupported_shape_items),
            ),
        },
        "failure_taxonomy": dict(
            sorted(
                failures.items()
            )
        ),
        "splits": split_summary,
    }


def run_evaluation_v2() -> list[dict]:
    return [
        evaluate_case_v2(case)
        for case in GOLDEN_CASES_V2.cases
    ]


def save_report(
    results: list[dict],
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

    output_path = (
        output_dir
        / f"golden_case_v2_eval_{timestamp}.json"
    )

    report = {
        "timestamp": timestamp,
        "evaluation": "day74_v2_decision_baseline",
        "summary": build_summary(results),
        "results": results,
    }

    with output_path.open(
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            report,
            f,
            ensure_ascii=False,
            indent=2,
        )

    return output_path


def print_results(
    results: list[dict],
) -> None:
    for item in results:
        print("=" * 80)

        status = (
            "PASS"
            if item["passed"]
            else "FAIL"
        )

        print(
            f"[{status}] "
            f"{item['case_id']} "
            f"({item['split']})"
        )
        print(
            f"Question: {item['question']}"
        )

        if not item["passed"]:
            for mismatch in item["mismatches"]:
                print(
                    "-",
                    mismatch["layer"],
                    mismatch["type"],
                    "| expected:",
                    mismatch["expected"],
                    "| actual:",
                    mismatch["actual"],
                )


def print_summary(
    summary: dict,
) -> None:
    print("=" * 80)
    print("Golden Case V2 Decision Baseline")
    print(f"Total: {summary['total']}")
    print(f"Passed: {summary['passed']}")
    print(f"Failed: {summary['failed']}")
    print(
        "Overall Pass Rate:",
        f"{summary['overall_pass_rate']}%",
    )

    print()
    print(
        "Metric Accuracy:",
        f"{summary['metric']['passed']}"
        f"/{summary['metric']['total']}",
        f"({summary['metric']['accuracy']}%)",
    )

    print(
        "Intent Shape Accuracy:",
        f"{summary['intent_shape']['passed']}"
        f"/{summary['intent_shape']['total']}",
        f"({summary['intent_shape']['accuracy']}%)",
    )

    print(
        "Grain Accuracy:",
        f"{summary['grain']['passed']}"
        f"/{summary['grain']['total']}",
        f"({summary['grain']['accuracy']}%)",
    )

    print(
        "Plan Accuracy:",
        f"{summary['plan']['passed']}"
        f"/{summary['plan']['total']}",
        f"({summary['plan']['accuracy']}%)",
    )

    print(
        "Clarification Accuracy:",
        f"{summary['clarification']['passed']}"
        f"/{summary['clarification']['total']}",
        f"({summary['clarification']['accuracy']}%)",
    )

    print(
        "Unsupported-shape Accuracy:",
        f"{summary['unsupported_shape']['passed']}"
        f"/{summary['unsupported_shape']['total']}",
        f"({summary['unsupported_shape']['accuracy']}%)",
    )

    print()
    print(
        "Failure Taxonomy:",
        summary["failure_taxonomy"],
    )

    print()
    print(
        "Split Summary:",
        summary["splits"],
    )


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--strict",
        action="store_true",
        help=(
            "Exit 1 if any Golden Case fails. "
            "Default baseline mode records failures "
            "without failing the process."
        ),
    )

    args = parser.parse_args()

    results = run_evaluation_v2()
    summary = build_summary(results)

    print_results(results)
    print_summary(summary)

    output_path = save_report(results)

    print()
    print(
        f"Saved to: {output_path}"
    )

    if args.strict and summary["failed"] > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
