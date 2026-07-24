from pydantic import ValidationError
from sqlalchemy.exc import (
    DBAPIError,
    ResourceClosedError,
    TimeoutError as SQLAlchemyTimeoutError,
)

from app.db.governed_sql_runner import (
    classify_dbapi_error,
    run_governed_sql,
)
from app.governance.execution_policy import (
    ExecutionErrorType,
    GovernedExecutionPolicy,
)


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(
            f"{message}\nExpected: {expected}\nActual: {actual}"
        )


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


class FakeTransaction:
    def __init__(self):
        self.is_active = True
        self.rollback_count = 0

    def rollback(self):
        self.rollback_count += 1
        self.is_active = False


class FakeMappedResult:
    def __init__(self, rows):
        self.rows = rows

    def fetchmany(self, size):
        return self.rows[:size]


class FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return FakeMappedResult(self.rows)


class FakeConnection:
    def __init__(
        self,
        query_rows=None,
        query_error=None,
        result_closed=False,
    ):
        self.query_rows = query_rows or []
        self.query_error = query_error
        self.result_closed = result_closed

        self.executions = []
        self.transaction = FakeTransaction()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def begin(self):
        return self.transaction

    def execute(self, statement, parameters=None):
        sql_text = str(statement)
        bound = dict(parameters or {})

        self.executions.append(
            (sql_text, bound)
        )

        if sql_text.startswith("SET TRANSACTION"):
            return FakeResult([])

        if "set_config" in sql_text:
            return FakeResult([])

        if self.query_error is not None:
            raise self.query_error

        if self.result_closed:
            raise ResourceClosedError(
                "result does not return rows"
            )

        return FakeResult(self.query_rows)


class FakeEngine:
    def __init__(
        self,
        connection=None,
        connect_error=None,
    ):
        self.connection = connection
        self.connect_error = connect_error

    def connect(self):
        if self.connect_error is not None:
            raise self.connect_error

        return self.connection


def test_policy_is_immutable() -> None:
    policy = GovernedExecutionPolicy()

    try:
        policy.max_rows = 999
    except ValidationError:
        return

    raise AssertionError(
        "GovernedExecutionPolicy must be immutable."
    )


def test_policy_rejects_non_read_only_mode() -> None:
    try:
        GovernedExecutionPolicy(read_only=False)
    except ValidationError:
        return

    raise AssertionError(
        "Execution policy must reject read_only=False."
    )


def test_policy_rejects_non_v2_schema() -> None:
    try:
        GovernedExecutionPolicy(
            target_schema="public"
        )
    except ValidationError:
        return

    raise AssertionError(
        "Execution policy must reject public schema."
    )


def test_successful_query_is_parameterized_and_bounded() -> None:
    connection = FakeConnection(
        query_rows=[
            {"channel_name": "天猫", "gmv": 100},
            {"channel_name": "京东", "gmv": 80},
        ]
    )

    policy = GovernedExecutionPolicy(
        max_rows=2,
        statement_timeout_ms=1_500,
    )

    result = run_governed_sql(
        sql=(
            "SELECT channel_name, gmv "
            "FROM governed_view "
            "WHERE channel_code = :channel_code"
        ),
        parameters={"channel_code": "TMALL"},
        policy=policy,
        engine_override=FakeEngine(connection),
    )

    assert_equal(
        result.success,
        True,
        "Bounded SELECT should succeed.",
    )

    assert_equal(
        result.row_count,
        2,
        "Runner should return the exact row count.",
    )

    assert_equal(
        connection.transaction.rollback_count,
        1,
        "Successful governed execution must rollback.",
    )

    executed_sql = [
        item[0]
        for item in connection.executions
    ]

    assert_true(
        executed_sql[0] == "SET TRANSACTION READ ONLY",
        "READ ONLY must be the first transaction statement.",
    )

    assert_true(
        any(
            "statement_timeout" in sql
            for sql in executed_sql
        ),
        "Runner must configure statement_timeout.",
    )

    assert_true(
        any(
            "search_path" in sql
            for sql in executed_sql
        ),
        "Runner must configure transaction-local search_path.",
    )

    final_sql, final_parameters = (
        connection.executions[-1]
    )

    assert_true(
        "TMALL" not in final_sql,
        "Parameter values must not be interpolated into SQL.",
    )

    assert_equal(
        final_parameters,
        {"channel_code": "TMALL"},
        "Parameter dictionary must be passed separately.",
    )


def test_oversized_result_is_rejected_without_partial_rows() -> None:
    connection = FakeConnection(
        query_rows=[
            {"value": 1},
            {"value": 2},
            {"value": 3},
        ]
    )

    result = run_governed_sql(
        sql="SELECT value FROM governed_view",
        policy=GovernedExecutionPolicy(max_rows=2),
        engine_override=FakeEngine(connection),
    )

    assert_equal(
        result.success,
        False,
        "Oversized result must be rejected.",
    )

    assert_equal(
        result.error_type,
        ExecutionErrorType.RESULT_TOO_LARGE,
        "Oversized result must use result_too_large.",
    )

    assert_equal(
        result.rows,
        (),
        "Oversized result must not return partial rows.",
    )

    assert_equal(
        result.observed_row_count,
        3,
        "Runner should record max_rows + 1 observation.",
    )

    assert_equal(
        connection.transaction.rollback_count,
        1,
        "Oversized query must rollback.",
    )


def test_empty_sql_is_rejected_before_connect() -> None:
    result = run_governed_sql(
        sql="   ",
        engine_override=FakeEngine(
            connect_error=AssertionError(
                "Engine must not be used."
            )
        ),
    )

    assert_equal(
        result.error_type,
        ExecutionErrorType.INVALID_EXECUTION_REQUEST,
        "Empty SQL must be rejected as invalid request.",
    )


def test_parameter_count_is_bounded() -> None:
    policy = GovernedExecutionPolicy(
        max_parameters=2
    )

    result = run_governed_sql(
        sql="SELECT 1",
        parameters={
            "a": 1,
            "b": 2,
            "c": 3,
        },
        policy=policy,
        engine_override=FakeEngine(
            connect_error=AssertionError(
                "Engine must not be used."
            )
        ),
    )

    assert_equal(
        result.error_type,
        ExecutionErrorType.INVALID_EXECUTION_REQUEST,
        "Too many parameters must be rejected early.",
    )


def test_pool_timeout_is_non_retryable() -> None:
    result = run_governed_sql(
        sql="SELECT 1",
        engine_override=FakeEngine(
            connect_error=SQLAlchemyTimeoutError(
                "pool exhausted"
            )
        ),
    )

    assert_equal(
        result.error_type,
        ExecutionErrorType.POOL_TIMEOUT,
        "Pool timeout must have a stable error type.",
    )

    assert_equal(
        result.retryable,
        False,
        "Pool timeout must not enter SQL Repair.",
    )


def test_non_row_statement_is_rejected() -> None:
    connection = FakeConnection(
        result_closed=True
    )

    result = run_governed_sql(
        sql="SELECT governed_function()",
        engine_override=FakeEngine(connection),
    )

    assert_equal(
        result.error_type,
        ExecutionErrorType.RESULT_NOT_READABLE,
        "A non-readable result must fail closed.",
    )

    assert_equal(
        connection.transaction.rollback_count,
        1,
        "Non-readable result must rollback.",
    )


def make_dbapi_error(
    sqlstate: str,
    message: str,
) -> DBAPIError:
    original = Exception(message)
    original.sqlstate = sqlstate

    return DBAPIError.instance(
        statement="SELECT 1",
        params={},
        orig=original,
        dbapi_base_err=Exception,
    )


def test_statement_timeout_classification() -> None:
    error = make_dbapi_error(
        "57014",
        "canceling statement due to statement timeout",
    )

    assert_equal(
        classify_dbapi_error(error),
        ExecutionErrorType.STATEMENT_TIMEOUT,
        "SQLSTATE 57014 must map to statement_timeout.",
    )


def test_read_only_violation_classification() -> None:
    error = make_dbapi_error(
        "25006",
        "cannot execute INSERT in a read-only transaction",
    )

    assert_equal(
        classify_dbapi_error(error),
        ExecutionErrorType.READ_ONLY_VIOLATION,
        "SQLSTATE 25006 must map to read_only_violation.",
    )


def test_timeout_error_rolls_back_and_is_non_retryable() -> None:
    error = make_dbapi_error(
        "57014",
        "canceling statement due to statement timeout",
    )

    connection = FakeConnection(
        query_error=error
    )

    result = run_governed_sql(
        sql="SELECT pg_sleep(999)",
        engine_override=FakeEngine(connection),
    )

    assert_equal(
        result.error_type,
        ExecutionErrorType.STATEMENT_TIMEOUT,
        "Timeout must be returned structurally.",
    )

    assert_equal(
        result.retryable,
        False,
        "Timeout must not enter SQL Repair.",
    )

    assert_equal(
        connection.transaction.rollback_count,
        1,
        "Timeout must rollback the transaction.",
    )


def run_tests() -> None:
    tests = [
        test_policy_is_immutable,
        test_policy_rejects_non_read_only_mode,
        test_policy_rejects_non_v2_schema,
        test_successful_query_is_parameterized_and_bounded,
        test_oversized_result_is_rejected_without_partial_rows,
        test_empty_sql_is_rejected_before_connect,
        test_parameter_count_is_bounded,
        test_pool_timeout_is_non_retryable,
        test_non_row_statement_is_rejected,
        test_statement_timeout_classification,
        test_read_only_violation_classification,
        test_timeout_error_rolls_back_and_is_non_retryable,
    ]

    passed = 0
    failed = 0

    for test in tests:
        print("=" * 80)
        print(f"Running: {test.__name__}")

        try:
            test()
            passed += 1
            print("[PASS]")
        except Exception as exc:
            failed += 1
            print("[FAIL]")
            print(exc)

    print("=" * 80)
    print("Execution Governance Test Summary")
    print(f"Total: {len(tests)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    run_tests()
