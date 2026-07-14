from contextlib import contextmanager
from typing import Any

import app.agents.analyst_graph as analyst_graph


def assert_equal(actual, expected, message: str):
    if actual != expected:
        raise AssertionError(
            f"{message}\nExpected: {expected}\nActual: {actual}"
        )


def build_test_intent(question: str) -> dict[str, Any]:
    """
    为 Graph 路由测试提供稳定的最小 intent。

    测试重点是 Graph routing，而不是重复测试 Intent Parser。
    """
    return {
        "question": question,
        "limit": None,
        "ranking_type": "unknown",
        "sort_hint": None,
        "dimension": None,
    }


def build_matched_metric_result(metric_name: str) -> dict[str, Any]:
    return {
        "status": "matched",
        "metrics": [
            {
                "name": metric_name,
            }
        ],
    }


@contextmanager
def patch_graph_dependencies(**replacements):
    """
    临时替换 analyst_graph 模块中的依赖。

    离开 with 代码块后，无论测试成功还是失败，
    都会恢复原函数，避免测试之间相互污染。
    """
    originals = {}

    try:
        for name, replacement in replacements.items():
            originals[name] = getattr(analyst_graph, name)
            setattr(analyst_graph, name, replacement)

        yield

    finally:
        for name, original in originals.items():
            setattr(analyst_graph, name, original)


def test_llm_metric_path():
    """
    普通指标正常路径：

    matched
    → select_metric
    → load_query_plan
    → resolve_intent
    → generate_sql（LLM）
    → clean
    → validate
    → run
    → evaluate
    → format
    → answer
    → finish
    """
    result = analyst_graph.ask_with_graph("哪个渠道销售额最高")

    assert_equal(
        result.get("success"),
        True,
        "普通指标路径应该成功",
    )

    assert_equal(
        result.get("status"),
        "completed",
        "普通指标路径状态应该是 completed",
    )

    assert_equal(
        result.get("generation_method"),
        "llm",
        "渠道销售额当前应走 LLM SQL 路径",
    )

    assert result.get("answer"), "普通指标路径应该返回 answer"


def test_matched_without_metric_routes_to_metric_fail():
    """
    防御路径：

    metric_result.status = matched
    但 metrics 为空
    → select_metric
    → metric_fail
    → END

    不应继续加载 Query Plan 或生成 SQL。
    """

    def fake_search_metric(question: str) -> dict[str, Any]:
        return {
            "status": "matched",
            "metrics": [],
        }

    def fail_if_query_plan_loaded(metric_name: str):
        raise AssertionError(
            "没有有效 metric_name 时不应该加载 Query Plan"
        )

    with patch_graph_dependencies(
        parse_intent=build_test_intent,
        search_metric=fake_search_metric,
        get_query_plan_by_metric=fail_if_query_plan_loaded,
    ):
        result = analyst_graph.ask_with_graph(
            "触发 matched but empty metrics"
        )

    assert_equal(
        result.get("success"),
        False,
        "没有有效指标时不应该成功",
    )

    assert_equal(
        result.get("status"),
        "error",
        "没有有效指标时状态应该是 error",
    )

    assert_equal(
        result.get("message"),
        "未识别到业务指标",
        "应该返回明确的指标识别失败信息",
    )


def test_template_metric_path():
    """
    Template 指标正常路径：

    ROI
    → Template SQL
    → runtime evaluation passed
    → finish
    """
    result = analyst_graph.ask_with_graph("各渠道ROI排名")

    assert_equal(
        result.get("success"),
        True,
        "ROI 路径应该成功",
    )

    assert_equal(
        result.get("status"),
        "completed",
        "ROI 路径状态应该是 completed",
    )

    assert_equal(
        result.get("generation_method"),
        "template",
        "ROI 当前应走 Template SQL 路径",
    )

    assert result.get("answer"), "ROI 路径应该返回 answer"


def test_clarification_path():
    """
    歧义问题路径：

    needs_clarification
    → clarification
    → END
    """
    result = analyst_graph.ask_with_graph("最赚钱")

    assert_equal(
        result.get("success"),
        False,
        "歧义问题不应该直接成功",
    )

    assert_equal(
        result.get("status"),
        "needs_clarification",
        "歧义问题应该进入 clarification 分支",
    )

    assert result.get("message"), "clarification 分支应该返回 message"

    suggestions = result.get("suggestions", [])
    assert suggestions, "clarification 分支应该返回候选指标 suggestions"


def test_validation_error_routes_to_sql_fail():
    """
    非安全 SQL：

    generate_sql
    → validate_sql 失败
    → evaluate_runtime_result
    → sql_fail
    """
    def fake_search_metric(question: str) -> dict[str, Any]:
        return build_matched_metric_result(
            "channel_sales_amount"
        )

    def fake_generate_template_sql(
        metric_name: str,
        intent: dict,
    ) -> None:
        return None

    def fake_generate_sql(
        question: str,
        intent: dict,
    ) -> str:
        return "DROP TABLE fact_orders;"

    with patch_graph_dependencies(
        parse_intent=build_test_intent,
        search_metric=fake_search_metric,
        generate_template_sql_from_intent=fake_generate_template_sql,
        generate_sql=fake_generate_sql,
    ):
        result = analyst_graph.ask_with_graph(
            "触发 SQL validation error"
        )

    assert_equal(
        result.get("success"),
        False,
        "validation error 不应该成功",
    )

    assert_equal(
        result.get("status"),
        "error",
        "validation error 最终状态应该是 error",
    )

    evaluation_result = result.get("evaluation_result", {})

    assert_equal(
        evaluation_result.get("error_type"),
        "validation_error",
        "应该识别为 validation_error",
    )

    assert_equal(
        evaluation_result.get("retryable"),
        False,
        "validation_error 不允许 retry",
    )

    assert_equal(
        result.get("retry_count"),
        0,
        "validation_error 不应增加 retry_count",
    )

    assert_equal(
        result.get("repair_history"),
        [],
        "validation_error 不应产生 repair_history",
    )


def test_llm_execution_error_repairs_and_finishes():
    """
    LLM SQL 第一次执行失败：

    execution_error
    → evaluation retryable
    → fake repair
    → clean
    → validate
    → run success
    → finish
    """
    repaired_sql = (
        "SELECT COUNT(*) AS order_count "
        "FROM fact_orders;"
    )

    def fake_search_metric(question: str) -> dict[str, Any]:
        return build_matched_metric_result(
            "channel_sales_amount"
        )

    def fake_generate_template_sql(
        metric_name: str,
        intent: dict,
    ) -> None:
        return None

    def fake_generate_sql(
        question: str,
        intent: dict,
    ) -> str:
        return (
            "SELECT not_exist_column "
            "FROM fact_orders;"
        )

    def fake_repair_sql_node(
        state: analyst_graph.AnalystState,
    ) -> analyst_graph.AnalystState:
        retry_count = state.get("retry_count", 0) + 1
        repair_history = list(
            state.get("repair_history", [])
        )

        repair_history.append(
            {
                "attempt": retry_count,
                "original_sql": state.get("sql"),
                "error": state.get("execution_error"),
                "repaired_sql": repaired_sql,
            }
        )

        return {
            "repaired_sql": repaired_sql,
            "retry_count": retry_count,
            "repair_history": repair_history,
            "execution_error": None,
            "validation_error": None,
            "sql_error_type": None,
        }

    def fake_generate_answer(
        question: str,
        table: dict,
        intent: dict,
    ) -> str:
        return "SQL 修复成功，订单数查询已完成。"

    with patch_graph_dependencies(
        parse_intent=build_test_intent,
        search_metric=fake_search_metric,
        generate_template_sql_from_intent=fake_generate_template_sql,
        generate_sql=fake_generate_sql,
        repair_sql_node=fake_repair_sql_node,
        generate_answer=fake_generate_answer,
    ):
        result = analyst_graph.ask_with_graph(
            "触发 LLM SQL execution error"
        )

    assert_equal(
        result.get("success"),
        True,
        "LLM SQL 修复后应该成功",
    )

    assert_equal(
        result.get("status"),
        "completed",
        "修复成功后状态应该是 completed",
    )

    assert_equal(
        result.get("generation_method"),
        "llm",
        "该路径应该保持 generation_method=llm",
    )

    assert_equal(
        result.get("retry_count"),
        1,
        "修复成功后 retry_count 应该为 1",
    )

    repair_history = result.get("repair_history", [])

    assert_equal(
        len(repair_history),
        1,
        "修复成功后应记录一次 repair_history",
    )

    assert_equal(
        repair_history[0].get("repaired_sql"),
        repaired_sql,
        "repair_history 应记录修复后的 SQL",
    )

    assert_equal(
        result.get("sql"),
        repaired_sql,
        "最终执行的 SQL 应该是 repaired_sql",
    )

    assert_equal(
        result.get("answer"),
        "SQL 修复成功，订单数查询已完成。",
        "修复成功后应该进入 answer 与 finish 节点",
    )


def test_template_execution_error_does_not_repair():
    """
    Template SQL 执行失败：

    execution_error
    → retryable=False
    → sql_fail

    不能进入 LLM repair。
    """
    def fake_search_metric(question: str) -> dict[str, Any]:
        return build_matched_metric_result("roi")

    def fake_generate_template_sql(
        metric_name: str,
        intent: dict,
    ) -> str:
        return (
            "SELECT not_exist_column "
            "FROM fact_orders;"
        )

    def fail_if_generate_sql_called(
        question: str,
        intent: dict,
    ) -> str:
        raise AssertionError(
            "Template 路径不应该调用 generate_sql"
        )

    def fail_if_repair_called(
        state: analyst_graph.AnalystState,
    ) -> analyst_graph.AnalystState:
        raise AssertionError(
            "Template execution error 不应该进入 repair_sql"
        )

    with patch_graph_dependencies(
        parse_intent=build_test_intent,
        search_metric=fake_search_metric,
        generate_template_sql_from_intent=fake_generate_template_sql,
        generate_sql=fail_if_generate_sql_called,
        repair_sql_node=fail_if_repair_called,
    ):
        result = analyst_graph.ask_with_graph(
            "触发 Template SQL execution error"
        )

    assert_equal(
        result.get("success"),
        False,
        "Template execution error 不应该成功",
    )

    assert_equal(
        result.get("status"),
        "error",
        "Template execution error 最终状态应该是 error",
    )

    assert_equal(
        result.get("generation_method"),
        "template",
        "该路径应该保持 generation_method=template",
    )

    evaluation_result = result.get("evaluation_result", {})

    assert_equal(
        evaluation_result.get("error_type"),
        "execution_error",
        "应该识别为 execution_error",
    )

    assert_equal(
        evaluation_result.get("retryable"),
        False,
        "Template execution error 不允许 retry",
    )

    assert_equal(
        result.get("retry_count"),
        0,
        "Template execution error 不应增加 retry_count",
    )

    assert_equal(
        result.get("repair_history"),
        [],
        "Template execution error 不应产生 repair_history",
    )


def test_empty_result_routes_to_sql_fail():
    """
    SQL 执行成功但没有返回数据：

    run_sql
    → rows=[]
    → evaluation_result.error_type=empty_result
    → sql_fail

    当前 V1 不自动 retry。
    """
    def fake_search_metric(question: str) -> dict[str, Any]:
        return build_matched_metric_result(
            "channel_sales_amount"
        )

    def fake_generate_template_sql(
        metric_name: str,
        intent: dict,
    ) -> None:
        return None

    def fake_generate_sql(
        question: str,
        intent: dict,
    ) -> str:
        return (
            "SELECT order_id "
            "FROM fact_orders "
            "WHERE 1 = 0;"
        )

    def fail_if_repair_called(
        state: analyst_graph.AnalystState,
    ) -> analyst_graph.AnalystState:
        raise AssertionError(
            "empty_result 当前不应该进入 repair_sql"
        )

    with patch_graph_dependencies(
        parse_intent=build_test_intent,
        search_metric=fake_search_metric,
        generate_template_sql_from_intent=fake_generate_template_sql,
        generate_sql=fake_generate_sql,
        repair_sql_node=fail_if_repair_called,
    ):
        result = analyst_graph.ask_with_graph(
            "触发 empty result"
        )

    assert_equal(
        result.get("success"),
        False,
        "empty_result 不应该被视为成功",
    )

    assert_equal(
        result.get("status"),
        "error",
        "empty_result 最终状态应该是 error",
    )

    evaluation_result = result.get(
        "evaluation_result",
        {},
    )

    assert_equal(
        evaluation_result.get("error_type"),
        "empty_result",
        "应该识别为 empty_result",
    )

    assert_equal(
        evaluation_result.get("retryable"),
        False,
        "empty_result 当前不允许 retry",
    )

    assert_equal(
        result.get("retry_count"),
        0,
        "empty_result 不应增加 retry_count",
    )

    assert_equal(
        result.get("repair_history"),
        [],
        "empty_result 不应产生 repair_history",
    )


def test_repair_loop_stops_at_max_retries():
    """
    第一次 LLM SQL 执行失败后进入 repair。

    repair 后的 SQL仍然执行失败：
    → retry_count 达到 max_retries
    → max_retries_exceeded
    → sql_fail

    用于证明正式 Graph 不会无限循环。
    """
    first_bad_sql = (
        "SELECT first_not_exist_column "
        "FROM fact_orders;"
    )

    second_bad_sql = (
        "SELECT second_not_exist_column "
        "FROM fact_orders;"
    )

    def fake_search_metric(question: str) -> dict[str, Any]:
        return build_matched_metric_result(
            "channel_sales_amount"
        )

    def fake_generate_template_sql(
        metric_name: str,
        intent: dict,
    ) -> None:
        return None

    def fake_generate_sql(
        question: str,
        intent: dict,
    ) -> str:
        return first_bad_sql

    def fake_failed_repair_node(
        state: analyst_graph.AnalystState,
    ) -> analyst_graph.AnalystState:
        retry_count = state.get("retry_count", 0) + 1
        repair_history = list(
            state.get("repair_history", [])
        )

        repair_history.append(
            {
                "attempt": retry_count,
                "original_sql": state.get("sql"),
                "error": state.get("execution_error"),
                "repaired_sql": second_bad_sql,
            }
        )

        return {
            "repaired_sql": second_bad_sql,
            "retry_count": retry_count,
            "repair_history": repair_history,
            "execution_error": None,
            "validation_error": None,
            "sql_error_type": None,
        }

    with patch_graph_dependencies(
        parse_intent=build_test_intent,
        search_metric=fake_search_metric,
        generate_template_sql_from_intent=fake_generate_template_sql,
        generate_sql=fake_generate_sql,
        repair_sql_node=fake_failed_repair_node,
    ):
        result = analyst_graph.ask_with_graph(
            "触发 max retries"
        )

    assert_equal(
        result.get("success"),
        False,
        "达到最大重试次数后不应该成功",
    )

    assert_equal(
        result.get("status"),
        "error",
        "达到最大重试次数后状态应该是 error",
    )

    evaluation_result = result.get(
        "evaluation_result",
        {},
    )

    assert_equal(
        evaluation_result.get("error_type"),
        "max_retries_exceeded",
        "应该识别为 max_retries_exceeded",
    )

    assert_equal(
        evaluation_result.get("retryable"),
        False,
        "达到最大重试次数后不能继续 retry",
    )

    assert_equal(
        result.get("retry_count"),
        1,
        "当前 max_retries=1，因此只允许修复一次",
    )

    repair_history = result.get(
        "repair_history",
        [],
    )

    assert_equal(
        len(repair_history),
        1,
        "应该只记录一次 repair",
    )

    assert_equal(
        repair_history[0].get("repaired_sql"),
        second_bad_sql,
        "repair_history 应记录第二条错误 SQL",
    )

    assert_equal(
        evaluation_result.get("source"),
        "retry_guard",
        "达到最大重试次数后应该由 retry_guard 终止流程",
    )


def run_tests():
    tests = [
        test_llm_metric_path,
        test_template_metric_path,
        test_clarification_path,
        test_matched_without_metric_routes_to_metric_fail,
        test_validation_error_routes_to_sql_fail,
        test_llm_execution_error_repairs_and_finishes,
        test_template_execution_error_does_not_repair,
        test_empty_result_routes_to_sql_fail,
        test_repair_loop_stops_at_max_retries,
    ]

    passed = 0
    failed = 0

    for test in tests:
        print("=" * 80)
        print(f"Running: {test.__name__}")

        try:
            test()
            passed += 1
            print("✅ PASSED")
        except Exception as e:
            failed += 1
            print("❌ FAILED")
            print(e)

    print("=" * 80)
    print("Analyst Graph Test Summary")
    print(f"Total: {len(tests)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    run_tests()