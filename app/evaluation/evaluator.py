import json
from datetime import datetime
from pathlib import Path
from app.evaluation.golden_questions import GOLDEN_QUESTIONS
from app.text_to_sql.query_service import ask


def check_expected_tables(sql: str, expected_tables: list[str]) -> list[str]:
    """
    检查生成的 SQL 是否包含预期的数据表。
    返回缺失的表名。
    """
    sql_lower = sql.lower()
    missing_tables = []

    for table in expected_tables:
        if table.lower() not in sql_lower:
            missing_tables.append(table)

    return missing_tables

def check_expected_columns(sql: str, expected_columns: list[str]) -> list[str]:
    """
    检查生成的 SQL 是否包含预期字段。
    返回缺失的字段名。
    """
    sql_lower = sql.lower()
    missing_columns = []

    for column in expected_columns:
        if column.lower() not in sql_lower:
            missing_columns.append(column)

    return missing_columns


def values_equal(actual, expected, tolerance: float = 0.01) -> bool:
    """
    比较实际值和预期值。
    - 数值类型允许一定误差
    - 字符串要求完全一致
    """
    if isinstance(expected, (int, float)):
        try:
            return abs(float(actual) - float(expected)) <= tolerance
        except (TypeError, ValueError):
            return False

    return actual == expected


def check_expected_result(
    table: dict,
    expected_result: dict,
    tolerance: float = 0.01,
) -> list[dict]:
    """
    检查结果表第一行是否符合预期。
    返回不匹配项。
    """
    mismatches = []

    rows = table.get("rows", [])

    if not rows:
        return [
            {
                "field": "__row__",
                "expected": expected_result,
                "actual": None,
                "reason": "no rows returned",
            }
        ]

    first_row = rows[0]

    for field, expected_value in expected_result.items():
        actual_value = first_row.get(field)

        if not values_equal(actual_value, expected_value, tolerance):
            mismatches.append(
                {
                    "field": field,
                    "expected": expected_value,
                    "actual": actual_value,
                }
            )

    return mismatches


def check_expected_order(
    table: dict,
    expected_order: dict,
) -> list[dict]:
    """
    检查结果表的排序是否符合预期。
    适用于排名类问题。
    """
    if not expected_order:
        return []

    rows = table.get("rows", [])
    field = expected_order.get("field")
    expected_values = expected_order.get("values", [])

    actual_values = [
        row.get(field)
        for row in rows[: len(expected_values)]
    ]

    if actual_values == expected_values:
        return []

    return [
        {
            "field": field,
            "expected": expected_values,
            "actual": actual_values,
            "reason": "order mismatch",
        }
    ]


def evaluate_case(case: dict) -> dict:
    """
    评估单个问题。
    """
    question = case["question"]

    try:
        result = ask(question)

        sql = result["sql"]
        table = result["table"]

        missing_tables = check_expected_tables(
            sql=sql,
            expected_tables=case.get("expected_tables", []),
        )
        
        missing_columns = check_expected_columns(
            sql=sql,
            expected_columns=case.get("expected_columns", []),
        )

        result_mismatches = check_expected_result(
            table=table,
            expected_result=case.get("expected_result", {}),
        )

        order_mismatches = check_expected_order(
            table=table,
            expected_order=case.get("expected_order", {}),
        )

        passed = (
            result["success"] is True
            and len(missing_tables) == 0
            and len(missing_columns) == 0
            and table["row_count"] >= 0
            and len(result_mismatches) == 0
        )

        return {
            "id": case["id"],
            "question": question,
            "passed": passed,
            "missing_tables": missing_tables,
            "missing_columns": missing_columns,
            "result_mismatches": result_mismatches,
            "order_mismatches": order_mismatches,
            "sql": sql,
            "row_count": table["row_count"],
            "error": None,
        }

    except Exception as e:
        return {
            "id": case["id"],
            "question": question,
            "passed": False,
            "missing_tables": case.get("expected_tables", []),
            "missing_columns": case.get("expected_columns", []),
            "result_mismatches": [],
            "order_mismatches": [],
            "sql": None,
            "row_count": 0,
            "error": str(e),
        }


def run_evaluation() -> list[dict]:
    """
    批量评估所有 golden questions。
    """
    results = []

    for case in GOLDEN_QUESTIONS:
        print(f"Evaluating: {case['id']} - {case['question']}")

        result = evaluate_case(case)
        results.append(result)

        if result["passed"]:
            print("✅ PASSED")
        else:
            print("❌ FAILED")
            print(f"Missing tables: {result['missing_tables']}")
            print(f"Missing columns: {result['missing_columns']}")
            print(f"Result mismatches: {result.get('result_mismatches', [])}")
            print(f"Order mismatches: {result.get('order_mismatches', [])}")
            print(f"Error: {result['error']}")

        print("-" * 60)

    return results


def save_evaluation_results(results: list[dict]) -> Path:
    """
    保存 Evaluation 结果，方便后续对比。
    """
    output_dir = Path("docs/evaluation")
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"evaluation_{timestamp}.json"

    total = len(results)
    passed = sum(1 for item in results if item["passed"])
    failed = total - passed
    pass_rate = round(passed / total * 100, 2) if total else 0

    report = {
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
    evaluation_results = run_evaluation()

    total = len(evaluation_results)
    passed = sum(1 for item in evaluation_results if item["passed"])
    failed = total - passed
    pass_rate = round(passed / total * 100, 2) if total else 0

    output_path = save_evaluation_results(evaluation_results)

    print("\nEvaluation Summary")
    print(f"Total: {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Pass Rate: {pass_rate}%")
    print(f"Saved to: {output_path}")