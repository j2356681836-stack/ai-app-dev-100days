from app.agents import sql_graph_nodes as nodes


BAD_SQL = """
SELECT
    dp.category,
    COUNT(fo.not_exist_column) AS order_count
FROM fact_orders fo
JOIN fact_order_items foi ON fo.order_id = foi.order_id
JOIN dim_product dp ON foi.product_id = dp.product_id
GROUP BY dp.category
ORDER BY order_count DESC
LIMIT 1
"""


FIXED_SQL = """
SELECT
    dp.category,
    COUNT(DISTINCT fo.order_id) AS order_count
FROM fact_orders fo
JOIN fact_order_items foi ON fo.order_id = foi.order_id
JOIN dim_product dp ON foi.product_id = dp.product_id
WHERE fo.order_status = 'paid'
GROUP BY dp.category
ORDER BY order_count DESC
LIMIT 1
"""


def fake_repair_sql(
    question: str,
    intent: dict | None,
    sql: str,
    error_message: str,
    context: str | None = None,
) -> str:
    return FIXED_SQL


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(
            f"{message}\nExpected: {expected}\nActual: {actual}"
        )


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_llm_execution_error_can_repair() -> None:
    original_repair_sql = nodes.repair_sql
    nodes.repair_sql = fake_repair_sql

    try:
        state = {
            "question": "哪个品类订单最多？",
            "intent": {
                "dimension": "category",
                "ranking_type": "top1",
                "limit": 1,
                "sort_hint": "desc",
                "final_sort_direction": "desc",
                "sort_field": "order_count",
            },
            "generation_method": "llm",
            "raw_sql": BAD_SQL,
            "retry_count": 0,
            "max_retries": 1,
            "repair_history": [],
        }

        state.update(nodes.clean_sql_node(state))
        state.update(nodes.validate_sql_node(state))
        state.update(nodes.run_sql_node(state))

        assert_equal(
            state.get("sql_error_type"),
            "execution_error",
            "第一次执行应捕获 execution_error。",
        )

        evaluation_update = nodes.evaluate_runtime_result_node(state)
        state.update(evaluation_update)

        assert_equal(
            nodes.route_evaluation_result(state),
            "repair_sql",
            "retryable execution_error 应路由到 repair_sql。",
        )

        state.update(nodes.repair_sql_node(state))

        assert_equal(
            state.get("retry_count"),
            1,
            "repair 后 retry_count 应增加到 1。",
        )

        assert_equal(
            len(state.get("repair_history", [])),
            1,
            "repair_history 应记录 1 次修复。",
        )

        assert_true(
            state.get("repaired_sql") is not None,
            "repair 后应生成 repaired_sql。",
        )

        state.update(nodes.clean_sql_node(state))
        state.update(nodes.validate_sql_node(state))
        state.update(nodes.run_sql_node(state))

        assert_equal(
            state.get("success"),
            True,
            "修复后的 SQL 应执行成功。",
        )

        assert_equal(
            state.get("status"),
            "sql_executed",
            "修复后的 SQL 执行成功后 status 应为 sql_executed。",
        )

        assert_equal(
            state.get("sql_error_type"),
            None,
            "修复成功后 sql_error_type 应清空。",
        )

        assert_true(
            len(state.get("rows", [])) > 0,
            "修复成功后应返回 rows。",
        )

    finally:
        nodes.repair_sql = original_repair_sql


def test_validation_error_cannot_repair() -> None:
    state = {
        "question": "哪个品类订单最多？",
        "intent": {},
        "generation_method": "llm",
        "raw_sql": "DROP TABLE fact_orders",
        "retry_count": 0,
        "max_retries": 1,
        "repair_history": [],
    }

    state.update(nodes.clean_sql_node(state))
    state.update(nodes.validate_sql_node(state))

    assert_equal(
        state.get("sql_error_type"),
        "validation_error",
        "危险 SQL 应在 validation 阶段被拦截。",
    )

    result = nodes.repair_sql_node(state)

    assert_equal(
        result.get("success"),
        False,
        "validation_error 不应进入 repair。",
    )

    assert_equal(
        result.get("sql_error_type"),
        "validation_error",
        "validation_error 被拒绝 repair 后应保留错误类型。",
    )


def test_template_sql_execution_error_cannot_repair() -> None:
    state = {
        "question": "各渠道ROI排名",
        "intent": {},
        "generation_method": "template",
        "sql": "SELECT bad_column FROM fact_orders",
        "sql_error_type": "execution_error",
        "execution_error": "column bad_column does not exist",
        "retry_count": 0,
        "max_retries": 1,
        "repair_history": [],
    }

    result = nodes.repair_sql_node(state)

    assert_equal(
        result.get("success"),
        False,
        "template SQL execution_error 不应交给 LLM repair。",
    )

    assert_equal(
        result.get("sql_error_type"),
        "template_sql_execution_error",
        "template SQL repair 应返回 template_sql_execution_error。",
    )


def test_max_retries_exceeded() -> None:
    state = {
        "question": "哪个品类订单最多？",
        "intent": {},
        "generation_method": "llm",
        "sql": "SELECT bad_column FROM fact_orders",
        "sql_error_type": "execution_error",
        "execution_error": "column bad_column does not exist",
        "retry_count": 1,
        "max_retries": 1,
        "repair_history": [],
    }

    result = nodes.repair_sql_node(state)

    assert_equal(
        result.get("success"),
        False,
        "retry_count 达到 max_retries 后不应继续 repair。",
    )

    assert_equal(
        result.get("sql_error_type"),
        "max_retries_exceeded",
        "超过最大修复次数后应返回 max_retries_exceeded。",
    )


def test_evaluation_result_validation_error_non_retryable() -> None:
    state = {
        "sql_error_type": "validation_error",
        "generation_method": "llm",
        "retry_count": 0,
        "max_retries": 1,
    }

    state.update(nodes.evaluate_runtime_result_node(state))

    evaluation_result = state.get("evaluation_result", {})

    assert_equal(
        evaluation_result.get("passed"),
        False,
        "validation_error 的 evaluation_result.passed 应为 False。",
    )

    assert_equal(
        evaluation_result.get("retryable"),
        False,
        "validation_error 不应 retry。",
    )

    assert_equal(
        nodes.route_evaluation_result(state),
        "fail",
        "validation_error 应路由到 fail。",
    )


def test_evaluation_result_llm_execution_error_retryable() -> None:
    state = {
        "sql_error_type": "execution_error",
        "generation_method": "llm",
        "retry_count": 0,
        "max_retries": 1,
    }

    state.update(nodes.evaluate_runtime_result_node(state))

    evaluation_result = state.get("evaluation_result", {})

    assert_equal(
        evaluation_result.get("passed"),
        False,
        "execution_error 的 evaluation_result.passed 应为 False。",
    )

    assert_equal(
        evaluation_result.get("retryable"),
        True,
        "LLM SQL execution_error 且 retry_count 未超限时应允许 retry。",
    )

    assert_equal(
        nodes.route_evaluation_result(state),
        "repair_sql",
        "可 retry 的 execution_error 应路由到 repair_sql。",
    )


def test_evaluation_result_template_execution_error_non_retryable() -> None:
    state = {
        "sql_error_type": "execution_error",
        "generation_method": "template",
        "retry_count": 0,
        "max_retries": 1,
    }

    state.update(nodes.evaluate_runtime_result_node(state))

    evaluation_result = state.get("evaluation_result", {})

    assert_equal(
        evaluation_result.get("passed"),
        False,
        "template execution_error 的 evaluation_result.passed 应为 False。",
    )

    assert_equal(
        evaluation_result.get("retryable"),
        False,
        "template SQL execution_error 不应 retry。",
    )

    assert_equal(
        nodes.route_evaluation_result(state),
        "fail",
        "template SQL execution_error 应路由到 fail。",
    )


def test_evaluation_result_empty_rows_non_retryable() -> None:
    state = {
        "rows": [],
        "sql_error_type": None,
        "generation_method": "llm",
        "retry_count": 0,
        "max_retries": 1,
    }

    state.update(nodes.evaluate_runtime_result_node(state))

    evaluation_result = state.get("evaluation_result", {})

    assert_equal(
        evaluation_result.get("passed"),
        False,
        "empty rows 的 evaluation_result.passed 应为 False。",
    )

    assert_equal(
        evaluation_result.get("error_type"),
        "empty_result",
        "empty rows 应映射为 empty_result。",
    )

    assert_equal(
        evaluation_result.get("retryable"),
        False,
        "empty_result 暂不自动 retry。",
    )

    assert_equal(
        nodes.route_evaluation_result(state),
        "fail",
        "empty_result 应路由到 fail。",
    )


def test_evaluation_result_rows_exists_passed() -> None:
    state = {
        "rows": [
            {
                "category": "防晒",
                "order_count": 5157,
            }
        ],
        "sql_error_type": None,
        "generation_method": "llm",
        "retry_count": 0,
        "max_retries": 1,
    }

    state.update(nodes.evaluate_runtime_result_node(state))

    evaluation_result = state.get("evaluation_result", {})

    assert_equal(
        evaluation_result.get("passed"),
        True,
        "rows 存在时 evaluation_result.passed 应为 True。",
    )

    assert_equal(
        evaluation_result.get("retryable"),
        False,
        "成功结果不需要 retry。",
    )

    assert_equal(
        nodes.route_evaluation_result(state),
        "format_result",
        "rows 存在时应路由到 format_result。",
    )


def main() -> None:
    tests = [
        test_llm_execution_error_can_repair,
        test_validation_error_cannot_repair,
        test_template_sql_execution_error_cannot_repair,
        test_max_retries_exceeded,
        test_evaluation_result_validation_error_non_retryable,
        test_evaluation_result_llm_execution_error_retryable,
        test_evaluation_result_template_execution_error_non_retryable,
        test_evaluation_result_empty_rows_non_retryable,
        test_evaluation_result_rows_exists_passed,
    ]

    passed = 0

    for test in tests:
        test()
        passed += 1
        print(f"[PASS] {test.__name__}")

    print(f"\nSQL repair graph tests: {passed}/{len(tests)} PASS")


if __name__ == "__main__":
    main()