from __future__ import annotations

from copy import deepcopy

from app.semantic_layer.query_plan_v2_models import (
    QueryPlanV2,
)
from app.semantic_layer.simple_query_plan_v2_builder import (
    SIMPLE_METRIC_SPECS,
    build_simple_query_plan,
)


def _gmv_spec():
    matches = tuple(
        spec
        for spec in SIMPLE_METRIC_SPECS
        if spec.metric == "gmv"
    )

    if len(matches) != 1:
        raise ValueError(
            "Exactly one GMV SimpleMetricSpec is required."
        )

    return matches[0]


def _base_gmv_region_payload_v2() -> dict:
    """
    Reuse the existing canonical GMV region plan as the trusted base.

    Geography Hierarchy plans only change:
    - result grain;
    - visible geography field;
    - group-by geography field;
    - minimal required geography columns;
    - target_id / business labels.

    Time, channel/region predicate-safe scope, GMV expression,
    Result Protection and hidden __group_size remain inherited.
    """
    return deepcopy(
        build_simple_query_plan(
            _gmv_spec(),
            "region",
        )
    )


def _build_gmv_geography_plan_v2(
    *,
    plan_name: str,
    chinese_name: str,
    result_grain: str,
    description: str,
    output_field: str,
    output_column: str,
    group_by: list[str],
) -> QueryPlanV2:
    payload = _base_gmv_region_payload_v2()

    payload["name"] = plan_name
    payload["chinese_name"] = chinese_name
    payload["result_grain"] = result_grain
    payload["description"] = description

    query_logic = payload["query_logic"]
    query_logic["group_by"] = list(group_by)
    query_logic["outputs"] = [
        {
            "field": output_field,
            "expression": f"dr.{output_column}",
        },
        {
            "field": "gmv",
            "expression": "SUM(foi.item_paid_amount)",
        },
    ]

    required_columns = set(
        payload["resource_contract"]["required_columns"]
    )

    # The inherited region plan declares region_name because it is used
    # in its visible output. Area / province must keep the minimal resource
    # closure rather than carrying unused columns.
    required_columns.discard(
        "dim_region.region_name"
    )
    required_columns.add(
        f"dim_region.{output_column}"
    )

    # City still groups by region_id for stable uniqueness.
    if result_grain == "city":
        required_columns.add(
            "dim_region.region_id"
        )

    payload["resource_contract"]["required_columns"] = sorted(
        required_columns
    )

    payload["scope_contract"]["targets"][0]["target_id"] = (
        f"{plan_name}_source"
    )

    payload["result_contract"]["field_bindings"] = [
        {
            "output_field": output_field,
            "source_columns": [
                f"dim_region.{output_column}",
            ],
            "category": "ordinary",
        },
        {
            "output_field": "gmv",
            "source_columns": [
                "fact_order_items.item_paid_amount",
            ],
            "category": "ordinary",
        },
    ]

    return QueryPlanV2.model_validate(
        payload
    )


def build_gmv_area_plan_v2() -> QueryPlanV2:
    return _build_gmv_geography_plan_v2(
        plan_name="gmv_area_v2",
        chinese_name="大区GMV",
        result_grain="area",
        description="按大区 Grain 计算 GMV。",
        output_field="region_group",
        output_column="region_group",
        group_by=[
            "dr.region_group",
        ],
    )


def build_gmv_province_plan_v2() -> QueryPlanV2:
    return _build_gmv_geography_plan_v2(
        plan_name="gmv_province_v2",
        chinese_name="省级GMV",
        result_grain="province",
        description="按省级 Grain 计算 GMV。",
        output_field="province_name",
        output_column="province_name",
        group_by=[
            "dr.province_name",
        ],
    )


def build_gmv_city_plan_v2() -> QueryPlanV2:
    return _build_gmv_geography_plan_v2(
        plan_name="gmv_city_v2",
        chinese_name="城市GMV",
        result_grain="city",
        description="按城市 Grain 计算 GMV。",
        output_field="region_name",
        output_column="region_name",
        group_by=[
            "dr.region_id",
            "dr.region_name",
        ],
    )


def build_gmv_geography_hierarchy_plans_v2(
) -> tuple[QueryPlanV2, QueryPlanV2, QueryPlanV2]:
    return (
        build_gmv_area_plan_v2(),
        build_gmv_province_plan_v2(),
        build_gmv_city_plan_v2(),
    )


if __name__ == "__main__":
    plans = build_gmv_geography_hierarchy_plans_v2()

    print("GMV Geography Hierarchy Query Plans V2")

    for plan in plans:
        print(
            f"{plan.name}: "
            f"grain={plan.result_grain}; "
            f"outputs="
            f"{tuple(item.field for item in plan.query_logic.outputs)}"
        )
