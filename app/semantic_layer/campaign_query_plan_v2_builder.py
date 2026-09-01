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


def build_gmv_campaign_plan_v2() -> QueryPlanV2:
    """
    GMV × Campaign breakdown.

    Design:
    - reuse canonical GMV Overall semantics;
    - paid_at remains the time attribution;
    - channel / region predicate-safe scope remains inherited;
    - LEFT JOIN dim_campaign preserves orders whose campaign_id is NULL;
    - NULL campaign is projected as “非活动订单” so member deltas can
      still reconcile to trusted Overall GMV;
    - Campaign contribution is numerical association, not causality.

    Promotion is intentionally NOT included here:
    promotion_id lives at fact_order_items grain and is a different
    analytical object / contract.
    """

    payload = deepcopy(
        build_simple_query_plan(
            _gmv_spec(),
            "overall",
        )
    )

    payload["name"] = "gmv_campaign_v2"
    payload["chinese_name"] = "活动实例GMV"
    payload["result_grain"] = "campaign"
    payload["description"] = (
        "按活动实例 Campaign Grain 分解 GMV；"
        "非活动订单保留为独立业务桶。"
    )

    query_logic = payload["query_logic"]
    query_logic["joins"].append(
        {
            "table": "dim_campaign",
            "alias": "dca",
            "join_type": "left",
            "conditions": [
                {
                    "left": "fo.campaign_id",
                    "right": "dca.campaign_id",
                },
            ],
        }
    )
    query_logic["group_by"] = [
        "dca.campaign_id",
        "dca.campaign_name",
    ]
    query_logic["outputs"] = [
        {
            "field": "campaign_name",
            "expression": (
                "COALESCE("
                "dca.campaign_name, "
                "'非活动订单'"
                ")"
            ),
        },
        {
            "field": "gmv",
            "expression": "SUM(foi.item_paid_amount)",
        },
    ]
    query_logic["hidden_control_fields"] = [
        {
            "field": "__group_size",
            "expression": (
                "COUNT(DISTINCT fo.customer_id)"
            ),
            "semantics": (
                "distinct_buyers_per_campaign_bucket"
            ),
        },
    ]

    required_tables = set(
        payload["resource_contract"]["required_tables"]
    )
    required_tables.add("dim_campaign")
    payload["resource_contract"]["required_tables"] = sorted(
        required_tables
    )

    required_columns = set(
        payload["resource_contract"]["required_columns"]
    )
    required_columns.update(
        {
            "fact_orders.campaign_id",
            "dim_campaign.campaign_id",
            "dim_campaign.campaign_name",
        }
    )
    payload["resource_contract"]["required_columns"] = sorted(
        required_columns
    )

    payload["scope_contract"]["targets"][0]["target_id"] = (
        "gmv_campaign_v2_source"
    )

    payload["result_contract"]["field_bindings"] = [
        {
            "output_field": "campaign_name",
            "source_columns": [
                "fact_orders.campaign_id",
                "dim_campaign.campaign_name",
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

    payload["default_sort"] = {
        "field": "gmv",
        "direction": "desc",
    }

    return QueryPlanV2.model_validate(
        payload
    )


if __name__ == "__main__":
    plan = build_gmv_campaign_plan_v2()

    print("GMV Campaign Query Plan V2")
    print(
        f"name={plan.name}; "
        f"grain={plan.result_grain}; "
        f"outputs="
        f"{tuple(item.field for item in plan.query_logic.outputs)}"
    )
