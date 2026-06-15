import json

from datetime import datetime
from pathlib import Path

from app.text_to_sql.template_sql_generator import (
    parse_limit,
    generate_template_sql,
    generate_template_sql_from_intent
)

from app.semantic_layer.intent_parser import parse_intent


LIMIT_TEST_CASES = [
    {
        "question": "哪个渠道ROI最高",
        "expected": 1,
    },
    {
        "question": "各渠道ROI排名",
        "expected": None,
    },
    {
        "question": "渠道ROI Top3",
        "expected": 3,
    },
    {
        "question": "渠道ROI前3",
        "expected": 3,
    },
    {
        "question": "获客成本最低的三个渠道",
        "expected": 3,
    },
    {
        "question": "获客成本最低的3个渠道",
        "expected": 3,
    },
    {
        "question": "获客成本前五渠道",
        "expected": 5,
    },
]


TEMPLATE_ROUTING_CASES = [
    {
        "metric_name": "roi",
        "question": "哪个渠道ROI最高",
        "expected_contains": [
            "WITH date_window AS",
            "channel_sales AS",
            "channel_spend AS",
            "ORDER BY roi DESC",
            "LIMIT 1",
        ],
    },
    {
        "metric_name": "roi",
        "question": "渠道ROI Top3",
        "expected_contains": [
            "WITH date_window AS",
            "channel_sales AS",
            "channel_spend AS",
            "ORDER BY roi DESC",
            "LIMIT 3",
        ],
    },
    {
        "metric_name": "cac",
        "question": "哪个渠道获客成本最低",
        "expected_contains": [
            "WITH date_window AS",
            "first_paid_order AS",
            "acquired_customers AS",
            "channel_spend AS",
            "ORDER BY cac ASC",
            "LIMIT 1",
        ],
    },
    {
        "metric_name": "cac",
        "question": "获客成本最低的三个渠道",
        "expected_contains": [
            "WITH date_window AS",
            "first_paid_order AS",
            "acquired_customers AS",
            "channel_spend AS",
            "ORDER BY cac ASC",
            "LIMIT 3",
        ],
    },
    {
        "metric_name": "channel_sales_amount",
        "question": "哪个渠道销售额最高",
        "expected_none": True,
    },
]

INTENT_TEMPLATE_CASES = [
    {
        "metric_name": "roi",
        "question": "渠道ROI Top3",
        "expected_contains": [
            "ORDER BY roi DESC",
            "LIMIT 3",
        ],
    },
    {
        "metric_name": "cac",
        "question": "获客成本最低的三个渠道",
        "expected_contains": [
            "ORDER BY cac ASC",
            "LIMIT 3",
        ],
    },
]


def test_parse_limit() -> list[dict]:
    results = []

    for case in LIMIT_TEST_CASES:
        actual = parse_limit(case["question"])
        passed = actual == case["expected"]

        results.append(
            {
                "question": case["question"],
                "expected": case["expected"],
                "actual": actual,
                "passed": passed,
            }
        )

    return results


def test_template_routing() -> list[dict]:
    results = []

    for case in TEMPLATE_ROUTING_CASES:
        sql = generate_template_sql(
            metric_name=case["metric_name"],
            question=case["question"],
        )

        if case.get("expected_none"):
            passed = sql is None
            missing = []
        else:
            missing = [
                item
                for item in case["expected_contains"]
                if sql is None or item not in sql
            ]
            passed = len(missing) == 0

        results.append(
            {
                "metric_name": case["metric_name"],
                "question": case["question"],
                "passed": passed,
                "missing": missing,
            }
        )

    return results


def test_template_from_intent() -> list[dict]:
    results = []

    for case in INTENT_TEMPLATE_CASES:
        intent = parse_intent(case["question"])
        sql = generate_template_sql_from_intent(
            metric_name=case["metric_name"],
            intent=intent,
        )

        missing = [
            item
            for item in case["expected_contains"]
            if sql is None or item not in sql
        ]

        results.append(
            {
                "metric_name": case["metric_name"],
                "question": case["question"],
                "passed": len(missing) == 0,
                "missing": missing,
            }
        )

    return results


def print_results(title: str, results: list[dict]) -> None:
    print()
    print("=" * 80)
    print(title)
    print("=" * 80)

    for result in results:
        status = "✅ PASSED" if result["passed"] else "❌ FAILED"
        print(status, "-", result["question"])

        if not result["passed"]:
            print(result)

    total = len(results)
    passed = sum(1 for item in results if item["passed"])

    print()
    print(f"Total: {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {total - passed}")


def save_report(
    limit_results: list[dict],
    routing_results: list[dict],
    intent_results: list[dict],
) -> Path:
    """
    保存 Template SQL 测试报告。
    """
    project_root = Path(__file__).resolve().parents[2]
    output_dir = project_root / "docs" / "evaluation"
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"template_sql_tests_{timestamp}.json"

    all_results = limit_results + routing_results + intent_results
    total = len(all_results)
    passed = sum(1 for item in all_results if item["passed"])

    report = {
        "test_suite": "template_sql_tests",
        "timestamp": timestamp,
        "summary": {
            "total": total,
            "passed": passed,
            "failed": total - passed,
            "pass_rate": round(passed / total * 100, 2) if total > 0 else 0,
        },
        "sections": {
            "limit_tests": {
                "total": len(limit_results),
                "passed": sum(1 for item in limit_results if item["passed"]),
                "failed": len(limit_results)
                - sum(1 for item in limit_results if item["passed"]),
                "results": limit_results,
            },
            "routing_tests": {
                "total": len(routing_results),
                "passed": sum(1 for item in routing_results if item["passed"]),
                "failed": len(routing_results)
                - sum(1 for item in routing_results if item["passed"]),
                "results": routing_results,
            },
            "intent_template_tests": {
                "total": len(intent_results),
                "passed": sum(1 for item in intent_results if item["passed"]),
                "failed": len(intent_results)
                - sum(1 for item in intent_results if item["passed"]),
                "results": intent_results,
            },
        },
    }

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    return output_path


if __name__ == "__main__":
    limit_results = test_parse_limit()
    routing_results = test_template_routing()
    intent_results = test_template_from_intent()

    print_results("Parse Limit Tests", limit_results)
    print_results("Template Routing Tests", routing_results)
    print_results("Template From Intent Tests", intent_results)

    all_results = limit_results + routing_results + intent_results
    total = len(all_results)
    passed = sum(1 for item in all_results if item["passed"])

    print()
    print("=" * 80)
    print("Summary")
    print("=" * 80)
    print(f"Total: {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {total - passed}")

    output_path = save_report(limit_results, routing_results, intent_results)
    print()
    print(f"Saved to: {output_path}")

    if passed != total:
        raise SystemExit(1)