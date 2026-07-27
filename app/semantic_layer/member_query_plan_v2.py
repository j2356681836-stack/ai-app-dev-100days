from app.semantic_layer.query_plan_v2_models import (
    QueryPlanV2,
)


def build_member_gmv_share_overall_plan() -> QueryPlanV2:
    """
    Build the overall Member GMV Share plan.

    Membership is determined exclusively by the payment-time order snapshot:
    fact_orders.member_level_at_order.

    This plan intentionally does not join membership history/current-state
    tables because historical transactions must not be reclassified using
    a customer's later membership state.
    """
    payload = {
        "name": "member_gmv_share_overall_v2",
        "metric": "member_gmv_share",
        "chinese_name": "整体会员GMV贡献率",
        "query_type": "aggregate_metric",
        "result_grain": "overall",
        "description": (
            "支付时点具有会员身份的订单 GMV "
            "占同期全部成功支付 GMV 的比例。"
        ),
        "semantic_contract": {
            "date_attribution": "fact_orders.paid_at",
            "metric_expression": (
                "SUM(CASE WHEN fo.member_level_at_order IS NOT NULL "
                "THEN foi.item_paid_amount ELSE 0 END) "
                "/ NULLIF(SUM(foi.item_paid_amount), 0)"
            ),
            "base_filters": [
                "fact_orders.paid_at IS NOT NULL",
            ],
        },
        "query_logic": {
            "base_source": {
                "table": "fact_order_items",
                "alias": "foi",
            },
            "joins": [
                {
                    "table": "fact_orders",
                    "alias": "fo",
                    "join_type": "inner",
                    "conditions": [
                        {
                            "left": "foi.order_id",
                            "right": "fo.order_id",
                        },
                    ],
                },
            ],
            "group_by": [],
            "outputs": [
                {
                    "field": "member_gmv_share",
                    "expression": (
                        "SUM(CASE WHEN "
                        "fo.member_level_at_order IS NOT NULL "
                        "THEN foi.item_paid_amount ELSE 0 END) "
                        "/ NULLIF("
                        "SUM(foi.item_paid_amount), 0)"
                    ),
                },
            ],
            "hidden_control_fields": [
                {
                    "field": "__group_size",
                    "expression": (
                        "COUNT(DISTINCT fo.customer_id)"
                    ),
                    "semantics": (
                        "distinct_buyers_in_analysis_period"
                    ),
                },
            ],
        },
        "resource_contract": {
            "required_tables": [
                "fact_order_items",
                "fact_orders",
                "dim_region",
                "dim_channel",
            ],
            "required_columns": [
                "fact_order_items.order_id",
                "fact_order_items.item_paid_amount",
                "fact_orders.order_id",
                "fact_orders.customer_id",
                "fact_orders.channel_id",
                "fact_orders.shipping_region_id",
                "fact_orders.paid_at",
                "fact_orders.member_level_at_order",
                "dim_region.region_id",
                "dim_region.region_code",
                "dim_channel.channel_id",
                "dim_channel.channel_code",
            ],
        },
        "scope_contract": {
            "scope_mode": "predicate_safe",
            "source_tables": [
                "fact_order_items",
            ],
            "required_dimensions": [
                "region",
                "channel",
            ],
            "targets": [
                {
                    "target_id": "member_gmv_share_items",
                    "source_table": "fact_order_items",
                    "table_aliases": [
                        {
                            "table_name": "fact_order_items",
                            "alias": "foi",
                        },
                        {
                            "table_name": "fact_orders",
                            "alias": "fo",
                        },
                    ],
                },
            ],
        },
        "result_contract": {
            "result_shape": "aggregate",
            "field_bindings": [
                {
                    "output_field": "member_gmv_share",
                    "source_columns": [
                        "fact_orders.member_level_at_order",
                        "fact_order_items.item_paid_amount",
                    ],
                    "category": "ordinary",
                },
            ],
            "minimum_group_size_required": True,
            "group_size_field": "__group_size",
        },
        "default_sort": {
            "field": "member_gmv_share",
            "direction": "desc",
        },
    }

    return QueryPlanV2.model_validate(payload)


if __name__ == "__main__":
    plan = build_member_gmv_share_overall_plan()

    print("Member GMV Share Query Plan V2")
    print(f"Plan: {plan.name}")
    print(f"Metric: {plan.metric}")
    print(f"Grain: {plan.result_grain}")
