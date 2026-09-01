from __future__ import annotations

from enum import Enum
from typing import AbstractSet, Callable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.semantic_layer.analysis_mode_resolution_v2 import (
    AnalysisModeResolutionV2,
    resolve_analysis_mode_v2,
)
from app.semantic_layer.candidate_decision_ranking_v2 import (
    EmbeddingRankerV2,
)
from app.semantic_layer.query_plan_selector_v2 import (
    QueryPlanSelectionResultV2,
    QueryPlanSelectionStatusV2,
    select_query_plan_v2,
)
from app.semantic_layer.question_semantic_parser_v2 import (
    LLMCall,
)
from app.semantic_layer.result_grain_resolver_v2 import (
    ResultGrainResolutionV2,
    apply_seed_overall_fallback_v2,
    resolve_result_grain_v2,
)
from app.semantic_layer.requested_scope_resolution_v2 import (
    RequestedScopeResolutionStatusV2,
    RequestedScopeResolutionV2,
    resolve_requested_scope_v2,
)
from app.semantic_layer.semantic_decision_service_v2 import (
    SemanticDecisionResultV2,
    SemanticDecisionStatusV2,
    resolve_semantic_decision_v2,
)


class AnalyticsPlanningStatusV2(str, Enum):
    PLANNED_SINGLE = "planned_single"
    PLANNED_MULTIPLE = "planned_multiple"

    NEEDS_METRIC_CLARIFICATION = (
        "needs_metric_clarification"
    )
    NEEDS_SCOPE_CLARIFICATION = (
        "needs_scope_clarification"
    )
    UNSUPPORTED_METRIC = "unsupported_metric"
    MULTIPLE_INTENTS = "multiple_intents"
    PARSE_FAILED = "parse_failed"
    EVIDENCE_CONFLICT = "evidence_conflict"

    MISSING_GRAIN = "missing_grain"
    AMBIGUOUS_GRAIN = "ambiguous_grain"
    UNSUPPORTED_GRAIN = "unsupported_grain"
    METRIC_NOT_FOUND = "metric_not_found"
    CATALOG_CONFLICT = "catalog_conflict"


class AnalyticsPlanningResultV2(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        arbitrary_types_allowed=True,
    )

    status: AnalyticsPlanningStatusV2
    question: str

    semantic_decision: SemanticDecisionResultV2
    requested_scope_resolution: RequestedScopeResolutionV2
    analysis_mode_resolution: AnalysisModeResolutionV2 = Field(
        default_factory=lambda: AnalysisModeResolutionV2(
            analysis_mode="fact",
        ),
        exclude=True,
    )
    grain_resolution: ResultGrainResolutionV2 | None = None
    plan_selection: QueryPlanSelectionResultV2 | None = None

    metric_name: str | None = None
    plan_names: tuple[str, ...] = ()
    detail: str | None = None

    @model_validator(mode="after")
    def validate_planning_result(
        self,
    ) -> "AnalyticsPlanningResultV2":
        semantic_matched = (
            self.semantic_decision.status
            == SemanticDecisionStatusV2.MATCHED
        )

        if (
            self.status
            == AnalyticsPlanningStatusV2
            .NEEDS_SCOPE_CLARIFICATION
        ):
            if (
                self.requested_scope_resolution.status
                != RequestedScopeResolutionStatusV2
                .UNRESOLVED_EXPLICIT_SCOPE
            ):
                raise ValueError(
                    "NEEDS_SCOPE_CLARIFICATION requires an "
                    "unresolved explicit Requested Scope."
                )

            if self.grain_resolution is not None:
                raise ValueError(
                    "Scope clarification stop must not resolve grain."
                )

            if self.plan_selection is not None:
                raise ValueError(
                    "Scope clarification stop must not select a plan."
                )

            if self.plan_names:
                raise ValueError(
                    "Scope clarification stop must not expose plans."
                )

            if semantic_matched:
                if (
                    self.metric_name
                    != self.semantic_decision.metric_name
                ):
                    raise ValueError(
                        "Scope clarification must preserve matched "
                        "metric_name."
                    )
            elif self.metric_name is not None:
                raise ValueError(
                    "Unmatched semantic scope stop must not expose "
                    "metric_name."
                )

            return self

        if not semantic_matched:
            if self.grain_resolution is not None:
                raise ValueError(
                    "Semantic stop result must not resolve grain."
                )

            if self.plan_selection is not None:
                raise ValueError(
                    "Semantic stop result must not select a plan."
                )

            if self.metric_name is not None:
                raise ValueError(
                    "Semantic stop result must not expose metric_name."
                )

            if self.plan_names:
                raise ValueError(
                    "Semantic stop result must not expose plan_names."
                )

            return self

        if self.semantic_decision.metric_name is None:
            raise ValueError(
                "MATCHED Semantic Decision requires metric_name."
            )

        if self.metric_name != self.semantic_decision.metric_name:
            raise ValueError(
                "Planning metric_name must equal Semantic Decision "
                "metric_name."
            )

        if self.grain_resolution is None:
            raise ValueError(
                "MATCHED Semantic Decision requires grain resolution."
            )

        if self.plan_selection is None:
            raise ValueError(
                "MATCHED Semantic Decision requires plan selection."
            )

        if (
            self.status
            == AnalyticsPlanningStatusV2.PLANNED_SINGLE
        ):
            if (
                self.plan_selection.status
                != QueryPlanSelectionStatusV2.MATCHED
            ):
                raise ValueError(
                    "PLANNED_SINGLE requires MATCHED plan selection."
                )

            if len(self.plan_names) != 1:
                raise ValueError(
                    "PLANNED_SINGLE requires exactly one plan."
                )

        if (
            self.status
            == AnalyticsPlanningStatusV2.PLANNED_MULTIPLE
        ):
            if (
                self.plan_selection.status
                != QueryPlanSelectionStatusV2.MATCHED_MULTIPLE
            ):
                raise ValueError(
                    "PLANNED_MULTIPLE requires MATCHED_MULTIPLE "
                    "plan selection."
                )

            if len(self.plan_names) < 2:
                raise ValueError(
                    "PLANNED_MULTIPLE requires at least two plans."
                )

        return self


SemanticResolverV2 = Callable[..., SemanticDecisionResultV2]
RequestedScopeResolverV2 = Callable[
    [str],
    RequestedScopeResolutionV2,
]
AnalysisModeResolverV2 = Callable[
    [str],
    AnalysisModeResolutionV2,
]
GrainResolverV2 = Callable[[str], ResultGrainResolutionV2]
PlanSelectorV2 = Callable[..., QueryPlanSelectionResultV2]


_SEMANTIC_STOP_STATUS_MAP = {
    SemanticDecisionStatusV2.NEEDS_CLARIFICATION:
        AnalyticsPlanningStatusV2
        .NEEDS_METRIC_CLARIFICATION,
    SemanticDecisionStatusV2.UNSUPPORTED:
        AnalyticsPlanningStatusV2
        .UNSUPPORTED_METRIC,
    SemanticDecisionStatusV2.MULTIPLE_INTENTS:
        AnalyticsPlanningStatusV2
        .MULTIPLE_INTENTS,
    SemanticDecisionStatusV2.PARSE_FAILED:
        AnalyticsPlanningStatusV2
        .PARSE_FAILED,
    SemanticDecisionStatusV2.EVIDENCE_CONFLICT:
        AnalyticsPlanningStatusV2
        .EVIDENCE_CONFLICT,
}


_PLAN_STATUS_MAP = {
    QueryPlanSelectionStatusV2.MATCHED:
        AnalyticsPlanningStatusV2.PLANNED_SINGLE,
    QueryPlanSelectionStatusV2.MATCHED_MULTIPLE:
        AnalyticsPlanningStatusV2.PLANNED_MULTIPLE,
    QueryPlanSelectionStatusV2.MISSING_GRAIN:
        AnalyticsPlanningStatusV2.MISSING_GRAIN,
    QueryPlanSelectionStatusV2.AMBIGUOUS_GRAIN:
        AnalyticsPlanningStatusV2.AMBIGUOUS_GRAIN,
    QueryPlanSelectionStatusV2.UNSUPPORTED_GRAIN:
        AnalyticsPlanningStatusV2.UNSUPPORTED_GRAIN,
    QueryPlanSelectionStatusV2.METRIC_NOT_FOUND:
        AnalyticsPlanningStatusV2.METRIC_NOT_FOUND,
    QueryPlanSelectionStatusV2.CATALOG_CONFLICT:
        AnalyticsPlanningStatusV2.CATALOG_CONFLICT,
}


def resolve_analytics_planning_v2(
    *,
    question: str,
    allowed_metric_names: AbstractSet[str] | None = None,
    llm_call: LLMCall | None = None,
    ranker: EmbeddingRankerV2 | None = None,
    semantic_resolver: SemanticResolverV2 = (
        resolve_semantic_decision_v2
    ),
    requested_scope_resolver: RequestedScopeResolverV2 = (
        resolve_requested_scope_v2
    ),
    analysis_mode_resolver: AnalysisModeResolverV2 = (
        resolve_analysis_mode_v2
    ),
    grain_resolver: GrainResolverV2 = (
        resolve_result_grain_v2
    ),
    plan_selector: PlanSelectorV2 = (
        select_query_plan_v2
    ),
) -> AnalyticsPlanningResultV2:
    """
    Unified governed planning entry point.

    Order:
    Question
    -> Semantic Decision
    -> Requested Scope Resolution
    -> Analysis Mode Resolution
    -> stop unless Metric is MATCHED
    -> Result Grain Resolution
    -> Query Plan Selection

    Important:
    - Semantic Decision is invoked exactly once.
    - Requested Scope Resolution is invoked exactly once.
    - Analysis Mode Resolution is invoked exactly once.
    - Requested Analysis Mode does not authorize data access and does
      not imply that a comparison/diagnostic delivery already exists.
    - Requested Scope is descriptive only at this layer;
      it does not authorize or apply Row Scope.
    - Result Grain does not change Row Scope.
    - At this layer Grain describes the trusted Seed Query output shape,
      not the later Investigation Target Grain.
    - FACT / COMPARISON / DIAGNOSTIC / INVESTIGATION may promote only an
      UNSPECIFIED, evidence-free Seed Grain to Overall.
    - Explicit / ambiguous / multi-plan Grain semantics are never
      overwritten.
    - COMPOSITION intentionally does not receive this fallback.
    - Query Plan selection does not generate or execute SQL.
    """
    semantic = semantic_resolver(
        question=question,
        allowed_metric_names=allowed_metric_names,
        llm_call=llm_call,
        ranker=ranker,
    )

    requested_scope = requested_scope_resolver(
        question
    )

    analysis_mode = analysis_mode_resolver(
        question
    )

    if (
        requested_scope.status
        == RequestedScopeResolutionStatusV2
        .UNRESOLVED_EXPLICIT_SCOPE
    ):
        unresolved = ", ".join(
            sorted(
                dimension.value
                for dimension
                in requested_scope.unresolved_dimensions
            )
        )

        return AnalyticsPlanningResultV2(
            status=(
                AnalyticsPlanningStatusV2
                .NEEDS_SCOPE_CLARIFICATION
            ),
            question=question,
            semantic_decision=semantic,
            requested_scope_resolution=requested_scope,
            analysis_mode_resolution=analysis_mode,
            grain_resolution=None,
            plan_selection=None,
            metric_name=(
                semantic.metric_name
                if (
                    semantic.status
                    == SemanticDecisionStatusV2.MATCHED
                )
                else None
            ),
            plan_names=(),
            detail=(
                "存在无法解析的显式数据范围"
                f"（{unresolved}）。"
                "请使用当前数据集中可识别的地区或渠道名称。"
            ),
        )

    if semantic.status != SemanticDecisionStatusV2.MATCHED:
        planning_status = _SEMANTIC_STOP_STATUS_MAP.get(
            semantic.status
        )

        if planning_status is None:
            raise RuntimeError(
                "Unmapped Semantic Decision status: "
                f"{semantic.status}"
            )

        return AnalyticsPlanningResultV2(
            status=planning_status,
            question=question,
            semantic_decision=semantic,
            requested_scope_resolution=requested_scope,
            analysis_mode_resolution=analysis_mode,
            grain_resolution=None,
            plan_selection=None,
            metric_name=None,
            plan_names=(),
            detail=(
                semantic.parser_error
                or (
                    ", ".join(
                        semantic.parser_conflicts
                    )
                    if semantic.parser_conflicts
                    else None
                )
            ),
        )

    metric_name = semantic.metric_name

    if metric_name is None:
        raise RuntimeError(
            "MATCHED Semantic Decision must expose metric_name."
        )

    grain = grain_resolver(
        question
    )

    grain = apply_seed_overall_fallback_v2(
        resolution=grain,
        analysis_mode=analysis_mode.analysis_mode.value,
    )

    selection = plan_selector(
        metric_name=metric_name,
        grain_resolution=grain,
    )

    planning_status = _PLAN_STATUS_MAP.get(
        selection.status
    )

    if planning_status is None:
        raise RuntimeError(
            "Unmapped Query Plan Selection status: "
            f"{selection.status}"
        )

    return AnalyticsPlanningResultV2(
        status=planning_status,
        question=question,
        semantic_decision=semantic,
        requested_scope_resolution=requested_scope,
        analysis_mode_resolution=analysis_mode,
        grain_resolution=grain,
        plan_selection=selection,
        metric_name=metric_name,
        plan_names=selection.plan_names,
        detail=selection.detail,
    )


if __name__ == "__main__":
    samples = (
        "本月GMV是多少？",
        "按渠道和地区交叉看GMV",
        "分别按渠道和地区看GMV",
        "各渠道和各地区的GMV",
    )

    for sample in samples:
        print("=" * 80)
        print(sample)
        result = resolve_analytics_planning_v2(
            question=sample
        )
        print(
            result.model_dump(
                mode="json",
                exclude={
                    "plan_selection": {
                        "plan",
                        "plans",
                    },
                },
            )
        )
