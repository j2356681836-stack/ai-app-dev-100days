from time import perf_counter
from typing import Any, Mapping

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import (
    DBAPIError,
    ResourceClosedError,
    SQLAlchemyError,
    TimeoutError as SQLAlchemyTimeoutError,
)

from app.db.governed_database import get_governed_engine
from app.governance.execution_policy import (
    ExecutionErrorType,
    GovernedExecutionPolicy,
    GovernedExecutionResult,
)


def _elapsed_ms(started_at: float) -> float:
    return max(
        0.0,
        (perf_counter() - started_at) * 1_000,
    )


def _failure(
    *,
    policy: GovernedExecutionPolicy,
    started_at: float,
    error_type: ExecutionErrorType,
    message: str,
    observed_row_count: int = 0,
) -> GovernedExecutionResult:
    return GovernedExecutionResult(
        success=False,
        rows=(),
        row_count=0,
        observed_row_count=observed_row_count,
        error_type=error_type,
        message=message,
        retryable=False,
        execution_time_ms=_elapsed_ms(started_at),
        target_schema=policy.target_schema,
        statement_timeout_ms=policy.statement_timeout_ms,
        max_rows=policy.max_rows,
        policy_version=policy.policy_version,
    )


def classify_dbapi_error(
    error: DBAPIError,
) -> ExecutionErrorType:
    """
    将 PostgreSQL / DBAPI 错误映射为稳定错误类型。

    PostgreSQL SQLSTATE：
    - 57014：query_canceled，常见于 statement_timeout；
    - 25006：read_only_sql_transaction。
    """

    original = getattr(error, "orig", None)
    sqlstate = (
        getattr(original, "sqlstate", None)
        or getattr(original, "pgcode", None)
    )

    original_message = str(original or error).lower()

    if (
        sqlstate == "57014"
        or "statement timeout" in original_message
        or "canceling statement due to statement timeout"
        in original_message
    ):
        return ExecutionErrorType.STATEMENT_TIMEOUT

    if (
        sqlstate == "25006"
        or "read-only transaction" in original_message
    ):
        return ExecutionErrorType.READ_ONLY_VIOLATION

    return ExecutionErrorType.DATABASE_ERROR


def run_governed_sql(
    sql: str,
    parameters: Mapping[str, Any] | None = None,
    policy: GovernedExecutionPolicy | None = None,
    engine_override: Engine | None = None,
) -> GovernedExecutionResult:
    """
    在独立、只读、受限的数据库事务中执行参数化 SQL。

    执行顺序：
    1. 验证请求；
    2. 开启事务并设置 READ ONLY；
    3. 设置 transaction-local statement_timeout；
    4. 设置 transaction-local search_path；
    5. 参数化执行 SQL；
    6. 最多读取 max_rows + 1 行；
    7. 超过上限时拒绝，不返回部分结果；
    8. 无论成功或失败均 rollback，避免会话状态泄漏。

    注意：
    - 本函数不替代 SQL Safety / Authorization；
    - Query Plan / SQL AST Enforcement 仍属于后续集成；
    - 真正的最小权限还依赖 AI_QUERY_POSTGRES_USER 在
      PostgreSQL 中只拥有 beauty_bi_v2 的 SELECT 权限。
    """

    started_at = perf_counter()
    active_policy = (
        policy
        if policy is not None
        else GovernedExecutionPolicy()
    )
    bound_parameters = dict(parameters or {})

    if not isinstance(sql, str) or not sql.strip():
        return _failure(
            policy=active_policy,
            started_at=started_at,
            error_type=(
                ExecutionErrorType.INVALID_EXECUTION_REQUEST
            ),
            message="SQL cannot be empty or whitespace.",
        )

    if len(bound_parameters) > active_policy.max_parameters:
        return _failure(
            policy=active_policy,
            started_at=started_at,
            error_type=(
                ExecutionErrorType.INVALID_EXECUTION_REQUEST
            ),
            message=(
                "SQL parameter count exceeds the governed limit."
            ),
        )

    engine = (
        engine_override
        if engine_override is not None
        else get_governed_engine()
    )

    transaction = None

    try:
        with engine.connect() as connection:
            transaction = connection.begin()

            # 必须是事务内第一条语句。
            connection.execute(
                text("SET TRANSACTION READ ONLY")
            )

            connection.execute(
                text(
                    "SELECT set_config("
                    "'statement_timeout', "
                    ":statement_timeout, "
                    "true"
                    ")"
                ),
                {
                    "statement_timeout": (
                        f"{active_policy.statement_timeout_ms}ms"
                    ),
                },
            )

            connection.execute(
                text(
                    "SELECT set_config("
                    "'search_path', "
                    ":search_path, "
                    "true"
                    ")"
                ),
                {
                    "search_path": (
                        f"{active_policy.target_schema},pg_catalog"
                    ),
                },
            )

            result = connection.execute(
                text(sql),
                bound_parameters,
            )

            mapped_result = result.mappings()
            rows = mapped_result.fetchmany(
                active_policy.max_rows + 1
            )

            observed_row_count = len(rows)

            if observed_row_count > active_policy.max_rows:
                transaction.rollback()
                transaction = None

                return _failure(
                    policy=active_policy,
                    started_at=started_at,
                    error_type=(
                        ExecutionErrorType.RESULT_TOO_LARGE
                    ),
                    message=(
                        "Query result exceeded the governed row "
                        "limit and was rejected."
                    ),
                    observed_row_count=observed_row_count,
                )

            normalized_rows = tuple(
                dict(row)
                for row in rows
            )

            transaction.rollback()
            transaction = None

            return GovernedExecutionResult(
                success=True,
                rows=normalized_rows,
                row_count=len(normalized_rows),
                observed_row_count=len(normalized_rows),
                error_type=None,
                message=None,
                retryable=False,
                execution_time_ms=_elapsed_ms(started_at),
                target_schema=active_policy.target_schema,
                statement_timeout_ms=(
                    active_policy.statement_timeout_ms
                ),
                max_rows=active_policy.max_rows,
                policy_version=active_policy.policy_version,
            )

    except SQLAlchemyTimeoutError:
        return _failure(
            policy=active_policy,
            started_at=started_at,
            error_type=ExecutionErrorType.POOL_TIMEOUT,
            message=(
                "Database connection pool timeout."
            ),
        )

    except ResourceClosedError:
        return _failure(
            policy=active_policy,
            started_at=started_at,
            error_type=(
                ExecutionErrorType.RESULT_NOT_READABLE
            ),
            message=(
                "Executed statement did not produce a readable "
                "row result."
            ),
        )

    except DBAPIError as error:
        error_type = classify_dbapi_error(error)

        messages = {
            ExecutionErrorType.STATEMENT_TIMEOUT: (
                "SQL execution exceeded statement_timeout."
            ),
            ExecutionErrorType.READ_ONLY_VIOLATION: (
                "SQL attempted an operation forbidden in a "
                "read-only transaction."
            ),
            ExecutionErrorType.DATABASE_ERROR: (
                "Database execution failed."
            ),
        }

        return _failure(
            policy=active_policy,
            started_at=started_at,
            error_type=error_type,
            message=messages[error_type],
        )

    except SQLAlchemyError:
        return _failure(
            policy=active_policy,
            started_at=started_at,
            error_type=ExecutionErrorType.DATABASE_ERROR,
            message="Database execution failed.",
        )

    finally:
        if (
            transaction is not None
            and getattr(transaction, "is_active", False)
        ):
            transaction.rollback()
