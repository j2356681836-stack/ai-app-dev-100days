from types import SimpleNamespace

from app.agents.governed_graph_nodes_v2 import (
    analytics_stop_node,
    route_analytics_planning,
)
from app.semantic_layer.analytics_planning_service_v2 import (
    AnalyticsPlanningStatusV2,
    resolve_analytics_planning_v2,
)
from app.semantic_layer.question_semantic_parser_v2 import (
    QuestionSemanticParseStatusV2,
)
from app.semantic_layer.semantic_decision_service_v2 import (
    SemanticDecisionResultV2,
    SemanticDecisionStatusV2,
)


def matched_gmv_semantic_resolver(
    **_,
) -> SemanticDecisionResultV2:
    return SemanticDecisionResultV2(
        status=SemanticDecisionStatusV2.MATCHED,
        parser_status=QuestionSemanticParseStatusV2.PARSED,
        metric_name="gmv",
    )


def check(name: str, condition: bool) -> None:
    if not condition:
        raise AssertionError(f"FAILED: {name}")
    print(f"PASS: {name}")


def main() -> None:
    analytics = resolve_analytics_planning_v2(
        question="2025年火星地区GMV是多少？",
        semantic_resolver=matched_gmv_semantic_resolver,
    )

    check(
        "Unknown explicit Region becomes NEEDS_SCOPE_CLARIFICATION",
        (
            analytics.status
            == AnalyticsPlanningStatusV2
            .NEEDS_SCOPE_CLARIFICATION
        ),
    )

    route = route_analytics_planning(
        {
            "analytics": analytics,
        }
    )

    check(
        "Graph routes unresolved Scope to analytics_stop",
        route == "analytics_stop",
    )

    result = analytics_stop_node(
        {
            "question": "2025年火星地区GMV是多少？",
            "analytics": analytics,
        }
    )["result"]

    check(
        "Public result is fail-closed before SQL",
        (
            result["success"] is False
            and result["outcome"] == "stopped"
            and result["stop_stage"]
            == "analytics_planning"
            and result["requested_scope_status"]
            == "unresolved_explicit_scope"
            and result["unresolved_scope_dimensions"]
            == ["region"]
            and "未进入 SQL 执行"
            in result["message"]
        ),
    )

    print("=" * 72)
    print(
        "Requested Scope Fail-Closed Acceptance V2 passed."
    )


if __name__ == "__main__":
    main()
