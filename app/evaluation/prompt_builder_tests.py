from datetime import datetime
from pathlib import Path
import json

from app.semantic_layer.intent_parser import (
    parse_intent,
    enrich_intent_with_query_plan,
)
from app.text_to_sql.prompt_builder import build_prompt


TEST_CASES = [
    {
        "question": "渠道销售额Top3",
        "expected_contains": [
            "结构化意图上下文",
            "dimension: channel",
            "ranking_type: topn",
            "limit: 3",
        ],
    },
    {
        "question": "渠道销售额从低到高排名",
        "expected_contains": [
            "结构化意图上下文",
            "dimension: channel",
            "ranking_type: ranking",
            "final_sort_direction: asc",
        ],
    },
]


def run_tests() -> list[dict]:
    results = []

    for case in TEST_CASES:
        intent = parse_intent(case["question"])
        intent = enrich_intent_with_query_plan(
            intent=intent,
            query_plan=None,
        )

        prompt = build_prompt(
            user_question=case["question"],
            intent=intent,
        )

        missing = [
            item
            for item in case["expected_contains"]
            if item not in prompt
        ]

        results.append(
            {
                "question": case["question"],
                "passed": len(missing) == 0,
                "missing": missing,
            }
        )

    return results


def print_results(results: list[dict]) -> None:
    print()
    print("=" * 80)
    print("Prompt Builder Tests")
    print("=" * 80)

    for result in results:
        status = "✅ PASSED" if result["passed"] else "❌ FAILED"
        print(f"{status} - {result['question']}")

        if not result["passed"]:
            print("Missing:", result["missing"])

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
    output_path = output_dir / f"prompt_builder_tests_{timestamp}.json"

    total = len(results)
    passed = sum(1 for item in results if item["passed"])
    failed = total - passed
    pass_rate = round(passed / total * 100, 2) if total > 0 else 0

    report = {
        "test_suite": "prompt_builder_tests",
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