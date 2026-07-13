from typing import Any, Literal

from app.db.sql_runner import run_sql
from app.text_to_sql.sql_cleaner import clean_sql
from app.text_to_sql.sql_validator import validate_sql
from app.text_to_sql.result_formatter import format_result, to_table

from app.text_to_sql.sql_repairer import repair_sql

def clean_sql_node(state: dict[str, Any]) -> dict[str, Any]:
    raw_sql = state.get("repaired_sql") or state.get("raw_sql") or ""
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
        "validation_error": None,
    }


def run_sql_node(state: dict[str, Any]) -> dict[str, Any]:
    sql = state.get("sql", "")

    try:
        rows = format_result(run_sql(sql))

        return {
        "rows": rows,
        "success": True,
        "status": "sql_executed",
        "message": None,
        "sql_error_type": None,
        "execution_error": None,
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


def evaluate_runtime_result_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    Runtime evaluation node V1。

    V1 只做确定性 runtime checks，不调用 LLM，不依赖 Golden Dataset。

    目标：
    - 将分散在 state 中的 SQL runtime 状态统一映射为 evaluation_result
    - 为后续 route_evaluation_result 提供结构化判断依据
    """

    sql_error_type = state.get("sql_error_type")
    generation_method = state.get("generation_method", "llm")
    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", 1)

    if sql_error_type == "validation_error":
        return {
            "evaluation_result": {
                "passed": False,
                "source": "sql_validation",
                "error_type": "validation_error",
                "retryable": False,
                "reason": "SQL validation failed. Forbidden operation is not retryable.",
            }
        }

    if sql_error_type == "empty_sql":
        return {
            "evaluation_result": {
                "passed": False,
                "source": "sql_cleaning",
                "error_type": "empty_sql",
                "retryable": False,
                "reason": "SQL is empty after cleaning.",
            }
        }

    if sql_error_type == "max_retries_exceeded":
        return {
            "evaluation_result": {
                "passed": False,
                "source": "retry_guard",
                "error_type": "max_retries_exceeded",
                "retryable": False,
                "reason": "SQL repair retry count has reached max_retries.",
            }
        }

    if sql_error_type == "template_sql_execution_error":
        return {
            "evaluation_result": {
                "passed": False,
                "source": "sql_execution",
                "error_type": "template_sql_execution_error",
                "retryable": False,
                "reason": "Template SQL execution failed. It should be fixed in template or query_plan.",
            }
        }

    if sql_error_type == "execution_error":
        if (
            generation_method == "llm"
            and retry_count >= max_retries
        ):
            return {
                "evaluation_result": {
                    "passed": False,
                    "source": "retry_guard",
                    "error_type": "max_retries_exceeded",
                    "retryable": False,
                    "reason": (
                        "SQL execution still failed after the "
                        "maximum repair attempts."
                    ),
                }
            }

        retryable = (
            generation_method == "llm"
            and retry_count < max_retries
        )

        return {
            "evaluation_result": {
                "passed": False,
                "source": "sql_execution",
                "error_type": "execution_error",
                "retryable": retryable,
                "reason": (
                    "LLM SQL execution failed and can enter SQL repair."
                    if retryable
                    else "SQL execution failed but is not retryable."
                ),
            }
        }

    if "rows" in state:
        rows = state.get("rows") or []

        if len(rows) == 0:
            return {
                "evaluation_result": {
                    "passed": False,
                    "source": "result_check",
                    "error_type": "empty_result",
                    "retryable": False,
                    "reason": "SQL executed successfully but returned no rows.",
                }
            }

        return {
            "evaluation_result": {
                "passed": True,
                "source": "result_check",
                "error_type": None,
                "retryable": False,
                "reason": None,
            }
        }

    return {
        "evaluation_result": {
            "passed": False,
            "source": "runtime_state",
            "error_type": "unknown_runtime_state",
            "retryable": False,
            "reason": "Runtime state has no sql_error_type and no rows.",
        }
    }


def route_evaluation_result(
    state: dict[str, Any],
) -> Literal["format_result", "repair_sql", "fail"]:
    evaluation_result = state.get("evaluation_result", {})

    if evaluation_result.get("passed") is True:
        return "format_result"

    if (
        evaluation_result.get("retryable") is True
        and evaluation_result.get("error_type") == "execution_error"
    ):
        return "repair_sql"

    return "fail"


def repair_sql_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    SQL repair node V1。

    V1 只处理：
    - generation_method = llm
    - sql_error_type = execution_error
    - retry_count < max_retries

    V1 不处理：
    - validation_error
    - template SQL
    """

    generation_method = state.get("generation_method", "llm")
    sql_error_type = state.get("sql_error_type")
    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", 1)
    repair_history = state.get("repair_history", [])

    if sql_error_type != "execution_error":
        return {
            "success": False,
            "status": "error",
            "message": "当前错误类型不允许进入 SQL 修复。",
            "sql_error_type": sql_error_type,
            "repair_history": repair_history,
        }

    if generation_method == "template":
        return {
            "success": False,
            "status": "error",
            "message": "Template SQL 执行失败，不交由 LLM 自动修复。",
            "sql_error_type": "template_sql_execution_error",
            "repair_history": repair_history,
        }

    if retry_count >= max_retries:
        return {
            "success": False,
            "status": "error",
            "message": "SQL 修复次数已达到上限。",
            "sql_error_type": "max_retries_exceeded",
            "repair_history": repair_history,
        }

    question = state.get("question", "")
    intent = state.get("intent")
    sql = state.get("sql", "")
    execution_error = state.get("execution_error", "")

    repair_context = state.get("repair_context")

    repaired_sql = repair_sql(
        question=question,
        intent=intent,
        sql=sql,
        error_message=execution_error,
        context=repair_context,
    )

    next_retry_count = retry_count + 1

    repair_record = {
        "attempt": next_retry_count,
        "source_sql": sql,
        "execution_error": execution_error,
        "repaired_sql": repaired_sql,
    }

    return {
        "raw_sql": repaired_sql,
        "repaired_sql": repaired_sql,
        "retry_count": next_retry_count,
        "repair_history": [
            *repair_history,
            repair_record,
        ],
        "success": None,
        "status": None,
        "message": None,
        "sql_valid": None,
        "validation_error": None,
        "sql_error_type": None,
        "execution_error": None,
    }