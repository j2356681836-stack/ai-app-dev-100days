from datetime import datetime
from pathlib import Path
import json

from app.semantic_layer.intent_parser import (
    parse_intent,
    enrich_intent_with_query_plan,
)
from app.semantic_layer.query_plan_loader import get_query_plan_by_metric


TEST_CASES = [
    {
        "metric_name": "roi",
        "question": "各渠道ROI排名",
        "expected": {
            "sort_hint": None,
            "final_sort_direction": "desc",
            "sort_field": "roi",
            "limit": None,
            "ranking_type": "ranking",
        },
    },
    {
        "metric_name": "roi",
        "question": "渠道ROI从低到高排名",
        "expected": {
            "sort_hint": "asc",
            "final_sort_direction": "asc",
            "sort_field": "roi",
            "limit": None,
            "ranking_type": "ranking",
        },
    },
    {
        "metric_name": "cac",
        "question": "各渠道获客成本排名",
        "expected": {
            "sort_hint": None,
            "final_sort_direction": "asc",
            "sort_field": "cac",
            "limit": None,
            "ranking_type": "ranking",
        },
    },
    {
        "metric_name": "cac",
        "question": "获客成本最低的三个渠道",
        "expected": {
            "sort_hint": "asc",
            "final_sort_direction": "asc",
            "sort_field": "cac",
            "limit": 3,
            "ranking_type": "topn",
        },
    },
    {
        "metric_name": "channel_sales_amount",
        "question": "哪个渠道销售额最高",
        "expected": {
            "sort_hint": "desc",
            "final_sort_direction": "desc",
            "sort_field": None,
            "limit": 1,
            "ranking_type": "top1",
        },
    },
]


def check_intent(actual: dict, expected: dict) -> list[dict]:
    mismatches = []

    for field, expected_value in expected.items():
        actual_value = actual.get(field)

        if actual_value != expected_value:
            mismatches.append(
                {
                    "field": field,
                    "expected": expected_value,
                    "actual": actual_value,
                }
            )

    return mismatches


def run_tests() -> list[dict]:
    results = []

    for case in TEST_CASES:
        intent = parse_intent(case["question"])
        query_plan = get_query_plan_by_metric(case["metric_name"])

        enriched_intent = enrich_intent_with_query_plan(
            intent=intent,
            query_plan=query_plan,
        )

        mismatches = check_intent(
            actual=enriched_intent,
            expected=case["expected"],
        )

        results.append(
            {
                "metric_name": case["metric_name"],
                "question": case["question"],
                "passed": len(mismatches) == 0,
                "actual": enriched_intent,
                "expected": case["expected"],
                "mismatches": mismatches,
            }
        )

    return results


def print_results(results: list[dict]) -> None:
    print()
    print("=" * 80)
    print("Intent Resolver Tests")
    print("=" * 80)

    for result in results:
        status = "✅ PASSED" if result["passed"] else "❌ FAILED"
        print(f"{status} - {result['question']}")

        if not result["passed"]:
            print("Expected:", result["expected"])
            print("Actual:", result["actual"])
            print("Mismatches:", result["mismatches"])

    total = len(results)
    passed = sum(1 for item in results if item["passed"])

    print()
    print(f"Total: {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {total - passed}")


def save_report(results: list[dict]) -> Path:
    project_root = Path(__file__).resolve().parents[2]
    output_dir = project_root / "docs" / "evaluation"
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"intent_resolver_tests_{timestamp}.json"

    total = len(results)
    passed = sum(1 for item in results if item["passed"])
    failed = total - passed
    pass_rate = round(passed / total * 100, 2) if total > 0 else 0

    report = {
        "test_suite": "intent_resolver_tests",
        "timestamp": timestamp,
        "summary": {
            "total": total,
            "passed": passed,
            "failed": failed,
            "pass_rate": pass_rate,
        },
        "results": results,
    }

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    return output_path


if __name__ == "__main__":
    results = run_tests()
    print_results(results)

    output_path = save_report(results)
    print()
    print(f"Saved to: {output_path}")

    if any(not result["passed"] for result in results):
        raise SystemExit(1)