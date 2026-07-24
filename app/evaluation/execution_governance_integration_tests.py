import os

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.db.governed_database import (
    get_governed_engine,
    load_governed_database_config,
)
from app.db.governed_sql_runner import (
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


def sqlstate_from_error(error: DBAPIError) -> str | None:
    original = getattr(error, "orig", None)

    return (
        getattr(original, "sqlstate", None)
        or getattr(original, "pgcode", None)
    )


def test_dedicated_query_credentials_are_used() -> None:
    config = load_governed_database_config()
    admin_user = os.getenv("POSTGRES_USER")

    assert_true(
        config.username != admin_user,
        "AI Query Runtime must not reuse POSTGRES_USER.",
    )


def test_role_security_attributes() -> None:
    config = load_governed_database_config()
    engine = get_governed_engine()

    with engine.connect() as connection:
        row = connection.execute(
            text(
                """
                SELECT
                    current_user AS current_user,
                    r.rolcanlogin,
                    r.rolsuper,
                    r.rolcreatedb,
                    r.rolcreaterole,
                    r.rolreplication,
                    r.rolinherit,
                    r.rolconnlimit,
                    current_setting(
                        'default_transaction_read_only'
                    ) AS default_read_only
                FROM pg_roles r
                WHERE r.rolname = current_user
                """
            )
        ).mappings().one()

    assert_equal(
        row["current_user"],
        config.username,
        "Governed Engine must use AI query role.",
    )

    assert_equal(
        row["rolcanlogin"],
        True,
        "AI query role must be able to log in.",
    )

    for field_name in (
        "rolsuper",
        "rolcreatedb",
        "rolcreaterole",
        "rolreplication",
        "rolinherit",
    ):
        assert_equal(
            row[field_name],
            False,
            f"{field_name} must remain false.",
        )

    assert_true(
        row["rolconnlimit"] > 0,
        "AI query role must have a positive connection limit.",
    )

    assert_equal(
        row["default_read_only"],
        "on",
        "Role default_transaction_read_only must be on.",
    )


def test_legal_v2_select_succeeds() -> None:
    result = run_governed_sql(
        sql=(
            "SELECT COUNT(*) AS order_count "
            "FROM beauty_bi_v2.fact_orders"
        ),
        policy=GovernedExecutionPolicy(
            max_rows=10,
        ),
    )

    assert_equal(
        result.success,
        True,
        "Authorized V2 SELECT should succeed.",
    )

    assert_equal(
        result.row_count,
        1,
        "COUNT query should return one row.",
    )

    assert_true(
        result.rows[0]["order_count"] > 0,
        "V2 fact_orders should be non-empty.",
    )


def test_parameterized_v2_select_succeeds() -> None:
    first = run_governed_sql(
        sql=(
            "SELECT channel_code "
            "FROM beauty_bi_v2.dim_channel "
            "ORDER BY channel_code "
            "LIMIT 1"
        ),
        policy=GovernedExecutionPolicy(max_rows=10),
    )

    assert_equal(
        first.success,
        True,
        "Channel lookup prerequisite should succeed.",
    )

    channel_code = first.rows[0]["channel_code"]

    result = run_governed_sql(
        sql=(
            "SELECT channel_code "
            "FROM beauty_bi_v2.dim_channel "
            "WHERE channel_code = :channel_code"
        ),
        parameters={
            "channel_code": channel_code,
        },
        policy=GovernedExecutionPolicy(max_rows=10),
    )

    assert_equal(
        result.success,
        True,
        "Parameterized SELECT should succeed.",
    )

    assert_equal(
        result.rows[0]["channel_code"],
        channel_code,
        "Bound parameter must preserve the expected value.",
    )


def test_real_row_limit_rejects_partial_result() -> None:
    result = run_governed_sql(
        sql=(
            "SELECT order_id "
            "FROM beauty_bi_v2.fact_orders "
            "ORDER BY order_id"
        ),
        policy=GovernedExecutionPolicy(
            max_rows=2,
        ),
    )

    assert_equal(
        result.success,
        False,
        "Large V2 result must be rejected.",
    )

    assert_equal(
        result.error_type,
        ExecutionErrorType.RESULT_TOO_LARGE,
        "Large result must use result_too_large.",
    )

    assert_equal(
        result.rows,
        (),
        "Large result must not return partial rows.",
    )

    assert_equal(
        result.observed_row_count,
        3,
        "Runner should observe max_rows + 1 rows.",
    )


def test_real_statement_timeout_is_enforced() -> None:
    result = run_governed_sql(
        sql="SELECT pg_sleep(0.25)",
        policy=GovernedExecutionPolicy(
            statement_timeout_ms=100,
            max_rows=10,
        ),
    )

    assert_equal(
        result.success,
        False,
        "Slow query must be canceled.",
    )

    assert_equal(
        result.error_type,
        ExecutionErrorType.STATEMENT_TIMEOUT,
        "Slow query must map to statement_timeout.",
    )

    assert_equal(
        result.retryable,
        False,
        "Timeout must not enter SQL Repair.",
    )


def test_role_cannot_write_even_in_read_write_transaction() -> None:
    engine = get_governed_engine()

    try:
        with engine.connect() as connection:
            transaction = connection.begin()

            try:
                # Role-level default read-only is only a default.
                # Switch to read-write to verify actual table grants.
                connection.execute(
                    text("SET TRANSACTION READ WRITE")
                )

                connection.execute(
                    text(
                        """
                        UPDATE beauty_bi_v2.dim_region
                        SET region_name = region_name
                        WHERE false
                        """
                    )
                )

            finally:
                if transaction.is_active:
                    transaction.rollback()

    except DBAPIError as error:
        assert_equal(
            sqlstate_from_error(error),
            "42501",
            "Write attempt should fail with insufficient_privilege.",
        )
        return

    raise AssertionError(
        "AI query role unexpectedly has UPDATE permission."
    )


def test_role_cannot_read_public_v1_tables() -> None:
    engine = get_governed_engine()

    try:
        with engine.connect() as connection:
            connection.execute(
                text(
                    """
                    SELECT order_id
                    FROM public.fact_orders
                    LIMIT 1
                    """
                )
            ).fetchone()

    except DBAPIError as error:
        state = sqlstate_from_error(error)

        assert_true(
            state in {"42501", "42P01"},
            "Public V1 access should fail with "
            "insufficient_privilege or undefined_table.",
        )
        return

    raise AssertionError(
        "AI query role unexpectedly read public.fact_orders."
    )


def test_transaction_local_settings_do_not_leak() -> None:
    engine = get_governed_engine()

    before = None

    with engine.connect() as connection:
        before = connection.execute(
            text(
                "SELECT current_setting('statement_timeout')"
            )
        ).scalar_one()

    result = run_governed_sql(
        sql="SELECT 1 AS value",
        policy=GovernedExecutionPolicy(
            statement_timeout_ms=1_234,
            max_rows=10,
        ),
    )

    assert_equal(
        result.success,
        True,
        "Control query should succeed.",
    )

    with engine.connect() as connection:
        after = connection.execute(
            text(
                "SELECT current_setting('statement_timeout')"
            )
        ).scalar_one()

    assert_equal(
        after,
        before,
        "Transaction-local timeout must not leak through pool.",
    )

    assert_true(
        after not in {"1234ms", "1.234s"},
        "Runner-specific timeout must be cleared after rollback.",
    )


def run_tests() -> None:
    tests = [
        test_dedicated_query_credentials_are_used,
        test_role_security_attributes,
        test_legal_v2_select_succeeds,
        test_parameterized_v2_select_succeeds,
        test_real_row_limit_rejects_partial_result,
        test_real_statement_timeout_is_enforced,
        test_role_cannot_write_even_in_read_write_transaction,
        test_role_cannot_read_public_v1_tables,
        test_transaction_local_settings_do_not_leak,
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
    print("Execution Governance Integration Summary")
    print(f"Total: {len(tests)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    run_tests()
