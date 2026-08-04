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


def build_gmv_channel_region_plan() -> QueryPlanV2:
    """
    Build the canonical GMV × Channel × Region Query Plan V2.

    The plan is derived from the governed channel-grain GMV plan and
    explicitly adds Region as a second result dimension. It remains a
    single deterministic QueryLogic plan, not a staged or UNION query.
    """
    payload = deepcopy(
        build_simple_query_plan(
            _gmv_spec(),
            "channel",
        )
    )

    payload["name"] = "gmv_channel_region_v2"
    payload["chinese_name"] = "渠道×地区GMV"
    payload["result_grain"] = "channel_region"
    payload["description"] = (
        "按渠道与地区复合 Grain 计算 GMV。"
    )

    query_logic = payload["query_logic"]

    query_logic["joins"].append(
        {
            "table": "dim_region",
            "alias": "dr",
            "join_type": "inner",
            "conditions": [
                {
                    "left": "fo.shipping_region_id",
                    "right": "dr.region_id",
                }
            ],
        }
    )

    query_logic["group_by"] = [
        "dc.channel_id",
        "dc.channel_name",
        "dr.region_id",
        "dr.region_name",
    ]

    query_logic["outputs"] = [
        {
            "field": "channel_name",
            "expression": "dc.channel_name",
        },
        {
            "field": "region_name",
            "expression": "dr.region_name",
        },
        {
            "field": "gmv",
            "expression": (
                "SUM(foi.item_paid_amount)"
            ),
        },
    ]

    required_columns = set(
        payload[
            "resource_contract"
        ][
            "required_columns"
        ]
    )
    required_columns.add(
        "dim_region.region_name"
    )
    payload[
        "resource_contract"
    ][
        "required_columns"
    ] = sorted(
        required_columns
    )

    payload[
        "scope_contract"
    ][
        "targets"
    ][0][
        "target_id"
    ] = "gmv_channel_region_v2_source"

    payload[
        "result_contract"
    ][
        "field_bindings"
    ] = [
        {
            "output_field": "channel_name",
            "source_columns": [
                "dim_channel.channel_name",
            ],
            "category": "ordinary",
        },
        {
            "output_field": "region_name",
            "source_columns": [
                "dim_region.region_name",
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
