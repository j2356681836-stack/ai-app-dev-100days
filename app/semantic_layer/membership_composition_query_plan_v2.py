from app.semantic_layer.query_plan_v2_models import (
    QueryPlanV2,
)


def build_gmv_membership_level_plan() -> QueryPlanV2:
    """
    构建支付时会员等级 GMV 构成 Query Plan。

    业务语义：
    - 历史订单只能使用 fact_orders.member_level_at_order；
    - 该字段为空表示支付时不是会员；
    - 不使用当前会员等级或后续 tier history 回填历史交易；
    - 每一笔成功支付订单只能落入一个支付时会员层级，
      因而所有层级 GMV 应与同 Scope / Window 的 Overall GMV 对账。

    输出：
    - membership_segment
    - gmv
    """

    payload = {
        "name": "gmv_membership_level_v2",
        "metric": "gmv",
        "chinese_name": "支付时会员等级GMV",
        "query_type": "aggregate_metric",
        "result_grain": "membership_level",
        "description": (
            "按订单支付时会员等级拆分 GMV。"
            "member_level_at_order 为空时归入 NON_MEMBER；"
            "历史交易不会按客户后续会员状态重新分类。"
        ),
        "semantic_contract": {
            "date_attribution": "fact_orders.paid_at",
            "metric_expression": (
                "SUM(foi.item_paid_amount)"
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
            "group_by": [
                "fo.member_level_at_order",
            ],
            "outputs": [
                {
                    "field": "membership_segment",
                    "expression": (
                        "COALESCE("
                        "fo.member_level_at_order, "
                        "'NON_MEMBER'"
                        ")"
                    ),
                },
                {
                    "field": "gmv",
                    "expression": (
                        "SUM(foi.item_paid_amount)"
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
                        "distinct_buyers_per_payment_time_"
                        "membership_segment"
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
                    "target_id": (
                        "gmv_membership_level_v2_source"
                    ),
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
                    "output_field": "membership_segment",
                    "source_columns": [
                        "fact_orders.member_level_at_order",
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
            ],
            "minimum_group_size_required": True,
            "group_size_field": "__group_size",
        },
        "default_sort": {
            "field": "gmv",
            "direction": "desc",
        },
    }

    return QueryPlanV2.model_validate(payload)


if __name__ == "__main__":
    plan = build_gmv_membership_level_plan()

    print("GMV Membership Level Query Plan V2")
    print(f"Plan: {plan.name}")
    print(f"Metric: {plan.metric}")
    print(f"Grain: {plan.result_grain}")
