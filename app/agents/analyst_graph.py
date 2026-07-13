from typing import Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from app.semantic_layer.intent_parser import (parse_intent,enrich_intent_with_query_plan,)
from app.semantic_layer.hybrid_search import search_metric
from app.text_to_sql.query_service import ask_with_resolved_metric

from app.semantic_layer.query_plan_loader import get_query_plan_by_metric

from app.text_to_sql.sql_generator import generate_sql
from app.text_to_sql.template_sql_generator import (
    generate_template_sql_from_intent,
)

from app.text_to_sql.answer_generator import generate_answer

from app.agents.sql_graph_nodes import (
    clean_sql_node,
    evaluate_runtime_result_node,
    format_result_node,
    repair_sql_node,
    route_clean_sql,
    route_evaluation_result,
    route_validation,
    run_sql_node,
    validate_sql_node,
)


class AnalystState(TypedDict, total=False):
    """
    Phase3 LangGraph V1 状态。

    当前 prototype 只拆出：
    - intent parsing
    - metric search
    - clarification routing
    - matched 后复用 query_service 后半段
    """

    question: str

    intent: dict[str, Any]
    metric_result: dict[str, Any]
    metric_name: str
    query_plan: dict[str, Any] | None

    success: bool
    status: str
    message: str
    suggestions: list[dict[str, Any]]

    generation_method: str
    sql: str
    table: dict[str, Any]
    answer: str

    result: dict[str, Any]
    errors: list[str]

    raw_sql: str
    repaired_sql: str

    sql_valid: bool
    validation_error: str | None
    execution_error: str | None
    sql_error_type: str | None

    rows: list[dict[str, Any]]
    evaluation_result: dict[str, Any]

    retry_count: int
    max_retries: int
    repair_history: list[dict[str, Any]]
    repair_context: dict[str, Any] | None


def parse_intent_node(state: AnalystState) -> AnalystState:
    question = state["question"]
    intent = parse_intent(question)

    return {
        "intent": intent,
    }


def search_metric_node(state: AnalystState) -> AnalystState:
    question = state["question"]
    metric_result = search_metric(question)

    return {
        "metric_result": metric_result,
    }


def select_metric_node(state: AnalystState) -> AnalystState:
    metric_result = state.get("metric_result", {})
    metrics = metric_result.get("metrics", [])

    if not metrics:
        return {
            "success": False,
            "status": "error",
            "message": "未识别到业务指标",
        }

    first_metric = metrics[0]
    metric_name = first_metric.get("name")

    if not metric_name:
        return {
            "success": False,
            "status": "error",
            "message": "未识别到业务指标",
        }

    return {
        "metric_name": metric_name,
    }


def route_metric_selection(
    state: AnalystState,
) -> Literal["load_query_plan", "metric_fail"]:
    metric_name = state.get("metric_name")

    if metric_name:
        return "load_query_plan"

    return "metric_fail"


def load_query_plan_node(state: AnalystState) -> AnalystState:
    metric_name = state["metric_name"]
    query_plan = get_query_plan_by_metric(metric_name)

    return {
        "query_plan": query_plan,
    }


def resolve_intent_node(state: AnalystState) -> AnalystState:
    intent = state["intent"]
    query_plan = state.get("query_plan")

    enriched_intent = enrich_intent_with_query_plan(
        intent=intent,
        query_plan=query_plan,
    )

    return {
        "intent": enriched_intent,
    }


def route_metric_status(
    state: AnalystState,
) -> Literal["select_metric", "clarification", "fail"]:
    metric_result = state.get("metric_result", {})
    status = metric_result.get("status")

    if status == "matched":
        return "select_metric"

    if status == "needs_clarification":
        return "clarification"

    return "fail"


def clarification_node(state: AnalystState) -> AnalystState:
    metric_result = state.get("metric_result", {})

    suggestions = (
        metric_result.get("suggestions")
        or metric_result.get("options")
        or []
    )

    result = {
        "success": False,
        "status": metric_result.get("status", "needs_clarification"),
        "message": metric_result.get("message", "问题存在歧义，需要进一步澄清。"),
        "suggestions": suggestions,
        "trace": metric_result.get("trace"),
    }

    return {
        **result,
        "result": result,
    }
    

def continue_pipeline_node(state: AnalystState) -> AnalystState:
    question = state["question"]
    intent = state["intent"]
    metric_result = state["metric_result"]

    result = ask_with_resolved_metric(
        question=question,
        intent=intent,
        metric_result=metric_result,
    )

    return {
        "success": result.get("success", False),
        "status": result.get("status", "completed"),
        "generation_method": result.get("generation_method"),
        "sql": result.get("sql"),
        "table": result.get("table"),
        "answer": result.get("answer"),
        "result": result,
    }


def generate_sql_node(state: AnalystState) -> AnalystState:
    question = state["question"]
    intent = state["intent"]
    metric_name = state["metric_name"]
    query_plan = state.get("query_plan")

    template_sql = generate_template_sql_from_intent(
        metric_name=metric_name,
        intent=intent,
    )

    if template_sql:
        raw_sql = template_sql
        generation_method = "template"
    else:
        raw_sql = generate_sql(
            question,
            intent=intent,
        )
        generation_method = "llm"

    return {
        "raw_sql": raw_sql,
        "generation_method": generation_method,
        "retry_count": 0,
        "max_retries": 1,
        "repair_history": [],
        "repair_context": {
            "metric_name": metric_name,
            "query_plan": query_plan,
            "intent": intent,
        },
    }


def fail_node(state: AnalystState) -> AnalystState:
    metric_result = state.get("metric_result", {})

    result = {
        "success": False,
        "status": metric_result.get("status", "error"),
        "message": metric_result.get("message", "指标识别失败。"),
    }

    return {
        **result,
        "result": result,
    }


def generate_answer_node(state: AnalystState) -> AnalystState:
    question = state["question"]
    table = state["table"]
    intent = state["intent"]

    answer = generate_answer(
        question=question,
        table=table,
        intent=intent,
    )

    return {
        "answer": answer,
    }


def finish_node(state: AnalystState) -> AnalystState:
    result = {
        "success": True,
        "status": "completed",
        "question": state["question"],
        "generation_method": state.get("generation_method"),
        "intent": state.get("intent"),
        "sql": state.get("sql"),
        "table": state.get("table"),
        "answer": state.get("answer"),
        "retry_count": state.get("retry_count", 0),
        "repair_history": state.get("repair_history", []),
    }

    return {
        **result,
        "result": result,
    }


def metric_fail_node(state: AnalystState) -> AnalystState:
    result = {
        "success": False,
        "status": "error",
        "message": state.get(
            "message",
            "未识别到业务指标",
        ),
    }

    return {
        **result,
        "result": result,
    }


def sql_fail_node(state: AnalystState) -> AnalystState:
    evaluation_result = state.get("evaluation_result", {})

    message = (
        evaluation_result.get("reason")
        or state.get("validation_error")
        or state.get("execution_error")
        or state.get("message")
        or "SQL 处理失败。"
    )

    result = {
        "success": False,
        "status": "error",
        "message": message,
        "generation_method": state.get("generation_method"),
        "sql": state.get("sql"),
        "evaluation_result": evaluation_result,
        "retry_count": state.get("retry_count", 0),
        "repair_history": state.get("repair_history", []),
    }

    return {
        **result,
        "result": result,
    }


def build_analyst_graph():
    graph = StateGraph(AnalystState)

    # Intent 与指标识别
    graph.add_node("parse_intent", parse_intent_node)
    graph.add_node("search_metric", search_metric_node)
    graph.add_node("select_metric", select_metric_node)
    graph.add_node("load_query_plan", load_query_plan_node)
    graph.add_node("resolve_intent", resolve_intent_node)

    # SQL 生成与 Runtime
    graph.add_node("generate_sql", generate_sql_node)
    graph.add_node("clean_sql", clean_sql_node)
    graph.add_node("validate_sql", validate_sql_node)
    graph.add_node("run_sql", run_sql_node)
    graph.add_node(
        "evaluate_runtime_result",
        evaluate_runtime_result_node,
    )
    graph.add_node("repair_sql", repair_sql_node)
    graph.add_node("format_result", format_result_node)

    # Answer 与终点
    graph.add_node("generate_answer", generate_answer_node)
    graph.add_node("finish", finish_node)

    # Clarification 与失败
    graph.add_node("clarification", clarification_node)
    graph.add_node("fail", fail_node)
    graph.add_node("metric_fail", metric_fail_node)
    graph.add_node("sql_fail", sql_fail_node)

    # 起点
    graph.add_edge(START, "parse_intent")
    graph.add_edge("parse_intent", "search_metric")

    # 指标识别路由
    graph.add_conditional_edges(
        "search_metric",
        route_metric_status,
        {
            "select_metric": "select_metric",
            "clarification": "clarification",
            "fail": "fail",
        },
    )

    # 指标选择路由
    graph.add_conditional_edges(
        "select_metric",
        route_metric_selection,
        {
            "load_query_plan": "load_query_plan",
            "metric_fail": "metric_fail",
        },
    )

    # SQL 生成前固定路径
    graph.add_edge("load_query_plan", "resolve_intent")
    graph.add_edge("resolve_intent", "generate_sql")
    graph.add_edge("generate_sql", "clean_sql")

    # SQL Cleaning 路由
    graph.add_conditional_edges(
        "clean_sql",
        route_clean_sql,
        {
            "validate_sql": "validate_sql",
            "fail": "evaluate_runtime_result",
        },
    )

    # SQL Validation 路由
    graph.add_conditional_edges(
        "validate_sql",
        route_validation,
        {
            "run_sql": "run_sql",
            "fail": "evaluate_runtime_result",
        },
    )

    # SQL 执行结果统一进入 runtime evaluation
    graph.add_edge(
        "run_sql",
        "evaluate_runtime_result",
    )

    # Runtime Evaluation 路由
    graph.add_conditional_edges(
        "evaluate_runtime_result",
        route_evaluation_result,
        {
            "format_result": "format_result",
            "repair_sql": "repair_sql",
            "fail": "sql_fail",
        },
    )

    # Repair Loop
    graph.add_edge("repair_sql", "clean_sql")

    # 成功路径
    graph.add_edge("format_result", "generate_answer")
    graph.add_edge("generate_answer", "finish")
    graph.add_edge("finish", END)

    # 结束路径
    graph.add_edge("clarification", END)
    graph.add_edge("fail", END)
    graph.add_edge("metric_fail", END)
    graph.add_edge("sql_fail", END)

    return graph.compile()


def ask_with_graph(question: str) -> dict[str, Any]:
    app = build_analyst_graph()

    state = app.invoke(
        {
            "question": question,
        }
    )

    return state.get("result", state)


if __name__ == "__main__":
    questions = [
        "哪个渠道销售额最高",
        "各渠道ROI排名",
        "最赚钱",
    ]

    for question in questions:
        print("=" * 80)
        print("Question:")
        print(question)

        result = ask_with_graph(question)

        print()
        print("Status:")
        print(result.get("status"))

        if result.get("success"):
            print()
            print("Generation Method:")
            print(result.get("generation_method"))

            print()
            print("Answer:")
            print(result.get("answer"))
        else:
            print()
            print("Message:")
            print(result.get("message"))

            if result.get("suggestions"):
                print()
                print("Suggestions:")

                for item in result["suggestions"]:
                    print("-", item.get("metric_label"))