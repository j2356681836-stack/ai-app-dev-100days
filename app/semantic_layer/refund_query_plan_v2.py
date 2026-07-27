from app.semantic_layer.query_plan_v2_models import (
    QueryPlanV2,
)


def build_refund_rate_overall_plan() -> QueryPlanV2:
    """
    Build the V2 overall refund-rate contract.

    Semantics:
    - sales-cohort attribution uses fact_orders.paid_at
    - denominator is original paid item GMV
    - only completed refund events contribute to numerator
    - refund events are pre-aggregated to one row per order_item
      before the final ratio so multiple refund events cannot fan out GMV
    """
    payload = {
        "name": "refund_rate_overall_v2",
        "metric": "refund_rate",
        "chinese_name": "整体退款率",
        "query_type": "staged_aggregate_metric",
        "result_grain": "overall",
        "description": (
            "指定销售分析范围内，原订单支付 cohort 最终已完成退款金额 "
            "占对应原始支付 GMV 的比例。"
            "多次部分退款先按 order_item 汇总，避免重复销售分母。"
        ),
        "semantic_contract": {
            "date_attribution": "fact_orders.paid_at",
            "metric_expression": (
                "SUM(item_refund_summary.completed_refund_amount) "
                "/ NULLIF("
                "SUM(item_refund_summary.item_paid_amount), 0)"
            ),
            "base_filters": [
                "fact_orders.paid_at IS NOT NULL",
                (
                    "only fact_refunds.refund_status = 'completed' "
                    "contributes to completed_refund_amount"
                ),
            ],
        },
        "query_logic": {
            "stages": [
                {
                    "stage_id": "item_refund_summary",
                    "stage_type": "aggregate",
                    "source": {
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
                        {
                            "table": "fact_refunds",
                            "alias": "fr",
                            "join_type": "left",
                            "conditions": [
                                {
                                    "left": "foi.order_item_id",
                                    "right": "fr.order_item_id",
                                },
                                {
                                    "left": "foi.order_id",
                                    "right": "fr.order_id",
                                },
                            ],
                        },
                    ],
                    "filters": [
                        "fo.paid_at IS NOT NULL",
                    ],
                    "group_by": [
                        "foi.order_item_id",
                        "foi.item_paid_amount",
                        "fo.customer_id",
                    ],
                    "outputs": [
                        {
                            "field": "order_item_id",
                            "expression": "foi.order_item_id",
                        },
                        {
                            "field": "customer_id",
                            "expression": "fo.customer_id",
                        },
                        {
                            "field": "item_paid_amount",
                            "expression": "foi.item_paid_amount",
                        },
                        {
                            "field": "completed_refund_amount",
                            "expression": (
                                "COALESCE("
                                "SUM(fr.refund_amount) FILTER "
                                "(WHERE fr.refund_status = 'completed'), "
                                "0)"
                            ),
                        },
                    ],
                    "hidden_control_fields": [],
                },
                {
                    "stage_id": "final",
                    "stage_type": "aggregate",
                    "source": {
                        "stage_id": "item_refund_summary",
                        "alias": "irs",
                    },
                    "outputs": [
                        {
                            "field": "refund_rate",
                            "expression": (
                                "SUM(irs.completed_refund_amount) "
                                "/ NULLIF("
                                "SUM(irs.item_paid_amount), 0)"
                            ),
                        },
                    ],
                    "hidden_control_fields": [
                        {
                            "field": "__group_size",
                            "expression": (
                                "COUNT(DISTINCT irs.customer_id)"
                            ),
                            "semantics": (
                                "distinct_buyers_in_sales_cohort"
                            ),
                        },
                    ],
                },
            ],
            "final_stage": "final",
        },
        "resource_contract": {
            "required_tables": [
                "fact_order_items",
                "fact_orders",
                "fact_refunds",
                "dim_region",
                "dim_channel",
            ],
            "required_columns": [
                "fact_order_items.order_item_id",
                "fact_order_items.order_id",
                "fact_order_items.item_paid_amount",
                "fact_orders.order_id",
                "fact_orders.customer_id",
                "fact_orders.paid_at",
                "fact_orders.shipping_region_id",
                "fact_orders.channel_id",
                "fact_refunds.order_id",
                "fact_refunds.order_item_id",
                "fact_refunds.refund_status",
                "fact_refunds.refund_amount",
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
                    "target_id": "refund_rate_sales_items",
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
                    "output_field": "refund_rate",
                    "source_columns": [
                        "fact_order_items.item_paid_amount",
                        "fact_refunds.refund_amount",
                        "fact_refunds.refund_status",
                    ],
                    "category": "business_confidential",
                },
            ],
            "minimum_group_size_required": True,
            "group_size_field": "__group_size",
        },
        "default_sort": {
            "field": "refund_rate",
            "direction": "desc",
        },
    }

    return QueryPlanV2.model_validate(payload)


if __name__ == "__main__":
    plan = build_refund_rate_overall_plan()

    print("Refund Rate Query Plan V2")
    print(f"Plan: {plan.name}")
    print(f"Metric: {plan.metric}")
    print(f"Stages: {len(plan.query_logic.stages)}")
    print(f"Grain: {plan.result_grain}")
