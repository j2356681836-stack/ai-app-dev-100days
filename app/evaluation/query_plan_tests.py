# ------------query plan 配置做结构检查------------

import json

from datetime import datetime
from pathlib import Path

from app.semantic_layer.query_plan_loader import load_query_plans
from app.text_to_sql.template_sql_generator import generate_template_sql # 检查配置层和代码层一致性


REQUIRED_TOP_LEVEL_FIELDS = [
    "name",
    "metric",
    "query_type",
    "grain",
    "output",
    "default_sort",
]

REQUIRED_FORMULA_FIELDS = [
    "alias",
    "round",
    "multiply_by_100",
]

REQUIRED_DEFAULT_SORT_FIELDS = [
    "field",
    "direction",
]

VALID_SORT_DIRECTIONS = ["asc", "desc"]


def validate_template_implementation(plan: dict) -> list[str]:
    errors = []

    metric_name = plan.get("metric")

    if not metric_name:
        return ["missing metric, cannot validate template implementation"]

    sql = generate_template_sql(
        metric_name=metric_name,
        question=f"{metric_name} 测试问题",
    )

    if sql is None:
        errors.append(
            f"query plan metric has no template implementation: {metric_name}"
        )

    return errors
    

def validate_business_rules(plan: dict) -> list[str]:
    """
    校验 query plan 中与业务口径强相关的配置。
    当前先覆盖 ROI / CAC。
    """
    errors = []

    metric = plan.get("metric")
    formula = plan.get("output", {}).get("formula", {})
    default_sort = plan.get("default_sort", {})

    multiply_by_100 = formula.get("multiply_by_100")
    sort_direction = default_sort.get("direction")

    if metric == "roi":
        if multiply_by_100 is not False:
            errors.append("roi should not multiply by 100")

        if sort_direction != "desc":
            errors.append("roi should sort by desc")

    if metric == "cac":
        if multiply_by_100 is not False:
            errors.append("cac should not multiply by 100")

        if sort_direction != "asc":
            errors.append("cac should sort by asc")

    return errors


def validate_query_plan(plan: dict) -> list[str]:
    errors = []

    for field in REQUIRED_TOP_LEVEL_FIELDS:
        if field not in plan:
            errors.append(f"missing top-level field: {field}")

    output = plan.get("output", {})
    formula = output.get("formula", {})

    for field in REQUIRED_FORMULA_FIELDS:
        if field not in formula:
            errors.append(f"missing output.formula field: {field}")

    default_sort = plan.get("default_sort", {})

    for field in REQUIRED_DEFAULT_SORT_FIELDS:
        if field not in default_sort:
            errors.append(f"missing default_sort field: {field}")

    direction = default_sort.get("direction")

    if direction and direction not in VALID_SORT_DIRECTIONS:
        errors.append(f"invalid default_sort.direction: {direction}")

    alias = formula.get("alias")
    sort_field = default_sort.get("field")

    if alias and sort_field and alias != sort_field:
        errors.append(
            f"default_sort.field should match output.formula.alias: "
            f"alias={alias}, sort_field={sort_field}"
        )

    return errors


def run_tests() -> list[dict]:
    results = []

    query_plans = load_query_plans()

    for plan in query_plans:
        errors = []
        errors.extend(validate_query_plan(plan))
        errors.extend(validate_template_implementation(plan))
        errors.extend(validate_business_rules(plan))

        results.append(
            {
                "name": plan.get("name"),
                "metric": plan.get("metric"),
                "passed": len(errors) == 0,
                "errors": errors,
            }
        )

    return results


def print_results(results: list[dict]) -> None:
    print()
    print("=" * 80)
    print("Query Plan Config Tests")
    print("=" * 80)

    for result in results:
        status = "✅ PASSED" if result["passed"] else "❌ FAILED"
        print(f"{status} - {result['name']} ({result['metric']})")

        if not result["passed"]:
            for error in result["errors"]:
                print(f"  - {error}")

    total = len(results)
    passed = sum(1 for item in results if item["passed"])

    print()
    print(f"Total: {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {total - passed}")


def save_report(results: list[dict]) -> Path:
    """
    保存 Query Plan 测试报告。
    """
    project_root = Path(__file__).resolve().parents[2]
    output_dir = project_root / "docs" / "evaluation"
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"query_plan_tests_{timestamp}.json"

    total = len(results)
    passed = sum(1 for item in results if item["passed"])

    report = {
        "test_suite": "query_plan_tests",
        "timestamp": timestamp,
        "summary": {
            "total": total,
            "passed": passed,
            "failed": total - passed,
            "pass_rate": round(passed / total * 100, 2) if total > 0 else 0,
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