from app.semantic_layer.analytics_planning_service_v2 import (
    AnalyticsPlanningStatusV2,
    resolve_analytics_planning_v2,
)
from app.semantic_layer.question_semantic_parser_v2 import (
    QuestionSemanticParseStatusV2,
)
from app.semantic_layer.requested_scope_resolution_v2 import (
    RequestedScopeResolutionStatusV2,
)
from app.semantic_layer.semantic_decision_service_v2 import (
    SemanticDecisionResultV2,
    SemanticDecisionStatusV2,
)


def check(name: str, condition: bool) -> None:
    if not condition:
        raise AssertionError(f"FAILED: {name}")
    print(f"PASS: {name}")


def matched_gmv_semantic_resolver(
    **_,
) -> SemanticDecisionResultV2:
    return SemanticDecisionResultV2(
        status=SemanticDecisionStatusV2.MATCHED,
        parser_status=QuestionSemanticParseStatusV2.PARSED,
        metric_name="gmv",
    )


def main() -> None:
    planned = resolve_analytics_planning_v2(
        question="2025年上海地区GMV是多少？",
        semantic_resolver=matched_gmv_semantic_resolver,
    )
    check(
        "上海 Requested Scope 穿过 Analytics Planning",
        (
            planned.status
            == AnalyticsPlanningStatusV2.PLANNED_SINGLE
            and planned.requested_scope_resolution.region_codes
            == frozenset({"SHANGHAI"})
        ),
    )

    unknown = resolve_analytics_planning_v2(
        question="2025年火星地区GMV是多少？",
        semantic_resolver=matched_gmv_semantic_resolver,
    )
    check(
        "未知显式 Scope 在 Query Plan 前停止",
        (
            unknown.status
            == AnalyticsPlanningStatusV2
            .NEEDS_SCOPE_CLARIFICATION
            and unknown.requested_scope_resolution.status
            == RequestedScopeResolutionStatusV2
            .UNRESOLVED_EXPLICIT_SCOPE
            and unknown.grain_resolution is None
            and unknown.plan_selection is None
            and not unknown.plan_names
        ),
    )

    no_scope = resolve_analytics_planning_v2(
        question="2025年GMV是多少？",
        semantic_resolver=matched_gmv_semantic_resolver,
    )
    check(
        "无显式 Scope 继续正常 Planning",
        (
            no_scope.status
            == AnalyticsPlanningStatusV2.PLANNED_SINGLE
            and no_scope.requested_scope_resolution.status
            == RequestedScopeResolutionStatusV2
            .NO_EXPLICIT_SCOPE
        ),
    )

    print("=" * 72)
    print(
        "Analytics Planning Requested Scope V2 tests passed."
    )


if __name__ == "__main__":
    main()
