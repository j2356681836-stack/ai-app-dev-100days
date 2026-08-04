from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict

from app.semantic_layer.query_plan_v2_loader import (
    get_query_plans_v2_by_metric,
)
from app.semantic_layer.query_plan_v2_models import (
    QueryPlanV2,
)
from app.semantic_layer.result_grain_resolver_v2 import (
    ResultDimensionV2,
    ResultGrainResolutionStatusV2,
    ResultGrainResolutionV2,
    resolve_result_grain_v2,
)


class QueryPlanSelectionStatusV2(str, Enum):
    MATCHED = "matched"
    MATCHED_MULTIPLE = "matched_multiple"
    METRIC_NOT_FOUND = "metric_not_found"
    MISSING_GRAIN = "missing_grain"
    AMBIGUOUS_GRAIN = "ambiguous_grain"
    UNSUPPORTED_GRAIN = "unsupported_grain"
    CATALOG_CONFLICT = "catalog_conflict"


class QueryPlanSelectionResultV2(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        arbitrary_types_allowed=True,
    )

    status: QueryPlanSelectionStatusV2
    metric_name: str

    requested_grain_keys: tuple[str, ...] = ()
    dimensions: tuple[ResultDimensionV2, ...] = ()
    available_grains: tuple[str, ...] = ()

    plan_name: str | None = None
    plan: QueryPlanV2 | None = None

    plan_names: tuple[str, ...] = ()
    plans: tuple[QueryPlanV2, ...] = ()

    detail: str | None = None


def _available_grains_v2(
    plans: tuple[QueryPlanV2, ...],
) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                plan.result_grain
                for plan in plans
            }
        )
    )


def _match_one_grain_v2(
    *,
    plans: tuple[QueryPlanV2, ...],
    grain_key: str,
) -> tuple[QueryPlanV2, ...]:
    return tuple(
        plan
        for plan in plans
        if plan.result_grain == grain_key
    )


def select_query_plan_v2(
    *,
    metric_name: str,
    grain_resolution: ResultGrainResolutionV2,
) -> QueryPlanSelectionResultV2:
    """
    Select one or more governed Query Plans.

    - RESOLVED single/composite grain -> exactly one Plan.
    - MULTI_PLAN_REQUEST -> one Plan per requested dimension.
    - AMBIGUOUS_REQUEST -> fail closed and request clarification.
    - YAML order is never treated as business intent.
    """
    plans = get_query_plans_v2_by_metric(
        metric_name
    )
    available_grains = (
        _available_grains_v2(
            plans
        )
    )

    if (
        grain_resolution.status
        == ResultGrainResolutionStatusV2
        .UNSPECIFIED
    ):
        return QueryPlanSelectionResultV2(
            status=(
                QueryPlanSelectionStatusV2
                .MISSING_GRAIN
            ),
            metric_name=metric_name,
            dimensions=(),
            available_grains=available_grains,
            detail=grain_resolution.error,
        )

    if (
        grain_resolution.status
        == ResultGrainResolutionStatusV2
        .AMBIGUOUS_REQUEST
    ):
        return QueryPlanSelectionResultV2(
            status=(
                QueryPlanSelectionStatusV2
                .AMBIGUOUS_GRAIN
            ),
            metric_name=metric_name,
            dimensions=grain_resolution.dimensions,
            available_grains=available_grains,
            detail=grain_resolution.error,
        )

    if not plans:
        requested = ()

        if grain_resolution.grain_key is not None:
            requested = (
                grain_resolution.grain_key,
            )
        elif grain_resolution.dimensions:
            requested = tuple(
                item.value
                for item in grain_resolution.dimensions
            )

        return QueryPlanSelectionResultV2(
            status=(
                QueryPlanSelectionStatusV2
                .METRIC_NOT_FOUND
            ),
            metric_name=metric_name,
            requested_grain_keys=requested,
            dimensions=grain_resolution.dimensions,
            available_grains=(),
            detail=(
                "No Query Plan V2 exists for the "
                "resolved Metric."
            ),
        )

    if (
        grain_resolution.status
        == ResultGrainResolutionStatusV2
        .MULTI_PLAN_REQUEST
    ):
        requested_keys = tuple(
            item.value
            for item in grain_resolution.dimensions
        )
        selected: list[
            QueryPlanV2
        ] = []

        for grain_key in requested_keys:
            matched = _match_one_grain_v2(
                plans=plans,
                grain_key=grain_key,
            )

            if not matched:
                return QueryPlanSelectionResultV2(
                    status=(
                        QueryPlanSelectionStatusV2
                        .UNSUPPORTED_GRAIN
                    ),
                    metric_name=metric_name,
                    requested_grain_keys=requested_keys,
                    dimensions=grain_resolution.dimensions,
                    available_grains=available_grains,
                    detail=(
                        "At least one requested separate "
                        "result grain is unsupported. "
                        f"missing={grain_key}"
                    ),
                )

            if len(matched) > 1:
                return QueryPlanSelectionResultV2(
                    status=(
                        QueryPlanSelectionStatusV2
                        .CATALOG_CONFLICT
                    ),
                    metric_name=metric_name,
                    requested_grain_keys=requested_keys,
                    dimensions=grain_resolution.dimensions,
                    available_grains=available_grains,
                    detail=(
                        "More than one Query Plan V2 "
                        "declares the same metric and grain. "
                        f"grain={grain_key}"
                    ),
                )

            selected.append(
                matched[0]
            )

        selected_tuple = tuple(
            selected
        )

        return QueryPlanSelectionResultV2(
            status=(
                QueryPlanSelectionStatusV2
                .MATCHED_MULTIPLE
            ),
            metric_name=metric_name,
            requested_grain_keys=requested_keys,
            dimensions=grain_resolution.dimensions,
            available_grains=available_grains,
            plan_names=tuple(
                plan.name
                for plan in selected_tuple
            ),
            plans=selected_tuple,
            detail=None,
        )

    grain_key = grain_resolution.grain_key

    if grain_key is None:
        raise RuntimeError(
            "RESOLVED grain result must expose grain_key."
        )

    matched = _match_one_grain_v2(
        plans=plans,
        grain_key=grain_key,
    )

    if not matched:
        return QueryPlanSelectionResultV2(
            status=(
                QueryPlanSelectionStatusV2
                .UNSUPPORTED_GRAIN
            ),
            metric_name=metric_name,
            requested_grain_keys=(
                grain_key,
            ),
            dimensions=grain_resolution.dimensions,
            available_grains=available_grains,
            detail=(
                "Metric exists, but the requested "
                "result grain has no Query Plan V2."
            ),
        )

    if len(matched) > 1:
        return QueryPlanSelectionResultV2(
            status=(
                QueryPlanSelectionStatusV2
                .CATALOG_CONFLICT
            ),
            metric_name=metric_name,
            requested_grain_keys=(
                grain_key,
            ),
            dimensions=grain_resolution.dimensions,
            available_grains=available_grains,
            detail=(
                "More than one Query Plan V2 declares "
                "the same metric and result grain."
            ),
        )

    plan = matched[0]

    return QueryPlanSelectionResultV2(
        status=(
            QueryPlanSelectionStatusV2
            .MATCHED
        ),
        metric_name=metric_name,
        requested_grain_keys=(
            grain_key,
        ),
        dimensions=grain_resolution.dimensions,
        available_grains=available_grains,
        plan_name=plan.name,
        plan=plan,
        plan_names=(
            plan.name,
        ),
        plans=(
            plan,
        ),
        detail=None,
    )


def resolve_and_select_query_plan_v2(
    *,
    question: str,
    metric_name: str,
) -> QueryPlanSelectionResultV2:
    return select_query_plan_v2(
        metric_name=metric_name,
        grain_resolution=(
            resolve_result_grain_v2(
                question
            )
        ),
    )


if __name__ == "__main__":
    samples = (
        (
            "本月GMV是多少？",
            "gmv",
        ),
        (
            "按渠道和地区交叉看GMV",
            "gmv",
        ),
        (
            "分别按渠道和地区看GMV",
            "gmv",
        ),
        (
            "各渠道和各地区的GMV",
            "gmv",
        ),
    )

    for question, metric_name in samples:
        print("=" * 80)
        print(question)
        print(
            resolve_and_select_query_plan_v2(
                question=question,
                metric_name=metric_name,
            ).model_dump(
                mode="json",
                exclude={
                    "plan",
                    "plans",
                },
            )
        )
