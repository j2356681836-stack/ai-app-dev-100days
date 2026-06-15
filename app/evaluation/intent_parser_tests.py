import json

from datetime import datetime
from pathlib import Path

from app.semantic_layer.intent_parser import parse_intent


TEST_CASES = [
    {
        "question": "哪个渠道ROI最高",
        "expected": {
            "limit": 1,
            "ranking_type": "top1",
            "sort_hint": "desc",
            "dimension": "channel",
        },
    },
    {
        "question": "各渠道ROI排名",
        "expected": {
            "limit": None,
            "ranking_type": "ranking",
            "sort_hint": None,
            "dimension": "channel",
        },
    },
    {
        "question": "渠道ROI Top3",
        "expected": {
            "limit": 3,
            "ranking_type": "topn",
            "sort_hint": None,
            "dimension": "channel",
        },
    },
    {
        "question": "获客成本最低的三个渠道",
        "expected": {
            "limit": 3,
            "ranking_type": "topn",
            "sort_hint": "asc",
            "dimension": "channel",
        },
    },
    {
        "question": "各品类退款率排名",
        "expected": {
            "limit": None,
            "ranking_type": "ranking",
            "sort_hint": None,
            "dimension": "category",
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
        actual = parse_intent(case["question"])

        # 调用 check_intent(actual, case["expected"])
        # 得到 mismatches
        mismatches = check_intent(actual,case["expected"])

        # passed = len(mismatches) == 0
        passed = len(mismatches) == 0

        # append 测试结果到 results
        # 字段包括：
        # question
        # passed
        # actual
        # expected
        # mismatches
        results.append(
            {
                "question": case["question"],
                "passed": passed,
                "actual": actual,
                "expected": case["expected"],
                "mismatches": mismatches,
            }
        )

    return results


def print_results(results: list[dict]) -> None:
    print()
    print("=" * 80)
    print("Intent Parser Tests")
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
    """
    保存 Intent Parser 测试报告。
    """
    project_root = Path(__file__).resolve().parents[2]
    output_dir = project_root / "docs" / "evaluation"
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"intent_parser_tests_{timestamp}.json"

    total = len(results)
    passed = sum(1 for item in results if item["passed"])
    failed = total - passed
    pass_rate = round(passed / total * 100, 2) if total > 0 else 0

    report = {
        "test_suite": "intent_parser_tests",
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