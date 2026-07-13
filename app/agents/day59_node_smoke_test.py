from typing import Any

from app.agents.analyst_graph import (
    generate_sql_node,
    load_query_plan_node,
    resolve_intent_node,
    route_metric_selection,
    select_metric_node,
)

from app.semantic_layer.intent_parser import parse_intent

from app.agents.sql_graph_nodes import (
    clean_sql_node,
    evaluate_runtime_result_node,
    format_result_node,
    route_evaluation_result,
    run_sql_node,
    validate_sql_node,
)


from app.text_to_sql.sql_cleaner import clean_sql


def test_sql_cleaner_normalization() -> None:
    cases = [
        ("SELECT 1", "SELECT 1;"),
        ("SELECT 1;", "SELECT 1;"),
        ("SELECT 1;;", "SELECT 1;"),
        ("SELECT 1;;;", "SELECT 1;"),
        ("```sql\nSELECT 1;;\n```", "SELECT 1;"),
        ("   ", ""),
    ]

    print("\n===== SQL Cleaner Normalization =====")

    for raw_sql, expected_sql in cases:
        actual_sql = clean_sql(raw_sql)

        print({
            "raw": raw_sql,
            "actual": actual_sql,
            "expected": expected_sql,
        })

        assert actual_sql == expected_sql

def run_metric_case(
    case_name: str,
    question: str,
    metric_result: dict[str, Any],
    test_sql_generation: bool = False,
) -> None:
    print(f"\n===== {case_name} =====")

    # 1. 模拟 search_metric_node 已经生成 metric_result。
    initial_state = {
        "question": question,
        "metric_result": metric_result,
    }

    # 2. 从 metric_result 中选出 metric_name。
    selected_update = select_metric_node(initial_state)

    selected_state = {
        **initial_state,
        **selected_update,
    }

    print("select_metric_node:")
    print(selected_update)

    # 3. 判断下一步应该加载 Query Plan，还是进入失败节点。
    route = route_metric_selection(selected_state)

    print("route_metric_selection:")
    print(route)

    if route == "metric_fail":
        return

    # 4. 根据 metric_name 加载 Query Plan。
    query_plan_update = load_query_plan_node(selected_state)

    query_plan_state = {
        **selected_state,
        **query_plan_update,
    }

    print("load_query_plan_node:")
    print(query_plan_update)

    # 5. 使用当前案例自己的 question 解析 intent。
    parsed_intent = parse_intent(question)

    intent_state = {
        **query_plan_state,
        "intent": parsed_intent,
    }

    # 6. 将原始 intent 与 Query Plan 融合。
    resolved_update = resolve_intent_node(intent_state)

    resolved_state = {
        **intent_state,
        **resolved_update,
    }

    print("resolve_intent_node:")
    print(resolved_update)

    # 7. SQL 生成测试目前只用于 Template 路径。
    # 普通指标会调用真实 LLM，因此快速 smoke test 中先不运行。
    if test_sql_generation:
    # generate_sql_node 只产生原始 SQL。
        sql_update = generate_sql_node(resolved_state)

        generated_state = {
            **resolved_state,
            **sql_update,
        }

        print("generate_sql_node:")
        print("generation_method:", sql_update["generation_method"])
        print("retry_count:", sql_update["retry_count"])
        print("max_retries:", sql_update["max_retries"])
        print("raw_sql:")
        print(sql_update["raw_sql"])

        # clean_sql_node 将 raw_sql 转换为可校验、可执行的 sql。
        clean_update = clean_sql_node(generated_state)

        cleaned_state = {
            **generated_state,
            **clean_update,
        }

        print("clean_sql_node:")
        print("sql:")
        print(clean_update.get("sql"))
        print("sql_error_type:", clean_update.get("sql_error_type"))

        # clean 失败时也需要进入统一 runtime evaluation。
        if clean_update.get("sql_error_type") == "empty_sql":
            evaluation_update = evaluate_runtime_result_node(cleaned_state)

            evaluated_state = {
                **cleaned_state,
                **evaluation_update,
            }

            print("evaluate_runtime_result_node:")
            print(evaluation_update)

            print("route_evaluation_result:")
            print(route_evaluation_result(evaluated_state))

            return

        # 校验清洗后的 SQL。
        validation_update = validate_sql_node(cleaned_state)

        validated_state = {
            **cleaned_state,
            **validation_update,
        }

        print("validate_sql_node:")
        print(validation_update)

        # 校验失败时不能运行 SQL，直接进入 runtime evaluation。
        if validation_update.get("sql_valid") is not True:
            evaluation_update = evaluate_runtime_result_node(validated_state)

            evaluated_state = {
                **validated_state,
                **evaluation_update,
            }

            print("evaluate_runtime_result_node:")
            print(evaluation_update)

            print("route_evaluation_result:")
            print(route_evaluation_result(evaluated_state))

            return

        # SQL 校验通过后执行数据库查询。
        execution_update = run_sql_node(validated_state)

        executed_state = {
            **validated_state,
            **execution_update,
        }

        print("run_sql_node:")
        print("success:", execution_update.get("success"))
        print("status:", execution_update.get("status"))
        print("sql_error_type:", execution_update.get("sql_error_type"))
        print("rows:")
        print(execution_update.get("rows"))

        # 无论执行成功还是失败，都进入统一 runtime evaluation。
        evaluation_update = evaluate_runtime_result_node(executed_state)

        evaluated_state = {
            **executed_state,
            **evaluation_update,
        }

        print("evaluate_runtime_result_node:")
        print(evaluation_update)

        route = route_evaluation_result(evaluated_state)

        print("route_evaluation_result:")
        print(route)

        # 只有 runtime evaluation 通过后，才格式化为 table。
        if route == "format_result":
            table_update = format_result_node(evaluated_state)

            print("format_result_node:")
            print(table_update)


if __name__ == "__main__":
    test_sql_cleaner_normalization()
    
    run_metric_case(
        case_name="复杂指标 ROI",
        question="各渠道ROI排名",
        metric_result={
            "status": "matched",
            "metrics": [
                {
                    "name": "roi",
                }
            ],
        },
        test_sql_generation=True,
    )

    run_metric_case(
        case_name="普通指标渠道销售额",
        question="各渠道销售额排名",
        metric_result={
            "status": "matched",
            "metrics": [
                {
                    "name": "channel_sales_amount",
                }
            ],
        },
        test_sql_generation=False,
    )

    run_metric_case(
        case_name="指标列表为空",
        question="测试空指标",
        metric_result={
            "status": "matched",
            "metrics": [],
        },
        test_sql_generation=False,
    )