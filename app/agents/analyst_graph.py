from typing import Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from app.semantic_layer.intent_parser import parse_intent
from app.semantic_layer.hybrid_search import search_metric
from app.text_to_sql.query_service import ask_with_resolved_metric


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


def route_metric_status(
    state: AnalystState,
) -> Literal["continue_pipeline", "clarification", "fail"]:
    metric_result = state.get("metric_result", {})
    status = metric_result.get("status")

    if status == "matched":
        return "continue_pipeline"

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


def build_analyst_graph():
    graph = StateGraph(AnalystState)

    graph.add_node("parse_intent", parse_intent_node)
    graph.add_node("search_metric", search_metric_node)
    graph.add_node("continue_pipeline", continue_pipeline_node)
    graph.add_node("clarification", clarification_node)
    graph.add_node("fail", fail_node)

    graph.add_edge(START, "parse_intent")
    graph.add_edge("parse_intent", "search_metric")

    graph.add_conditional_edges(
        "search_metric",
        route_metric_status,
        {
            "continue_pipeline": "continue_pipeline",
            "clarification": "clarification",
            "fail": "fail",
        },
    )

    graph.add_edge("continue_pipeline", END)
    graph.add_edge("clarification", END)
    graph.add_edge("fail", END)

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