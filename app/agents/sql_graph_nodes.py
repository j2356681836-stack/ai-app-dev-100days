from typing import Any

from app.db.sql_runner import run_sql
from app.text_to_sql.sql_cleaner import clean_sql
from app.text_to_sql.sql_validator import validate_sql
from app.text_to_sql.result_formatter import format_result, to_table


def clean_sql_node(state: dict[str, Any]) -> dict[str, Any]:
    raw_sql = state.get("raw_sql") or state.get("repaired_sql") or ""
    sql = clean_sql(raw_sql)

    if not sql:
        return {
            "sql": sql,
            "success": False,
            "status": "error",
            "message": "SQL 为空，无法执行。",
            "sql_error_type": "empty_sql",
        }

    return {
        "sql": sql,
    }


def validate_sql_node(state: dict[str, Any]) -> dict[str, Any]:
    sql = state.get("sql", "")
    sql_valid = validate_sql(sql)

    if not sql_valid:
        return {
            "sql_valid": False,
            "success": False,
            "status": "error",
            "message": "SQL 包含禁止操作，拒绝执行。",
            "sql_error_type": "validation_error",
            "validation_error": "SQL contains forbidden keyword.",
        }

    return {
        "sql_valid": True,
    }


def run_sql_node(state: dict[str, Any]) -> dict[str, Any]:
    sql = state.get("sql", "")

    try:
        rows = format_result(run_sql(sql))

        return {
            "rows": rows,
        }

    except Exception as e:
        return {
            "success": False,
            "status": "error",
            "message": "SQL 执行失败。",
            "sql_error_type": "execution_error",
            "execution_error": str(e),
        }


def format_result_node(state: dict[str, Any]) -> dict[str, Any]:
    rows = state.get("rows", [])
    table = to_table(rows)

    return {
        "table": table,
    }


def route_clean_sql(state: dict[str, Any]) -> str:
    if state.get("sql_error_type") == "empty_sql":
        return "fail"

    return "validate_sql"


def route_validation(state: dict[str, Any]) -> str:
    if state.get("sql_valid") is True:
        return "run_sql"

    return "fail"


def route_execution(state: dict[str, Any]) -> str:
    if state.get("sql_error_type") == "execution_error":
        return "retry_or_fail"

    return "format_result"


def retry_or_fail(state: dict[str, Any]) -> str:
    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", 1)

    if retry_count < max_retries:
        return "repair_sql"

    return "fail"