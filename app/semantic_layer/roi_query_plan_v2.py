from app.semantic_layer.query_plan_v2_models import (
    QueryPlanV2,
)


def build_roi_channel_plan() -> QueryPlanV2:
    """
    Channel ROI candidate contract.

    ROI = same-window channel GMV / same-window channel marketing spend.

    Governance boundary:
    fact_marketing_spend has Channel Scope but no Region Scope.
    Therefore the plan deliberately declares Region + Channel as required
    dimensions and must fail closed for the current scoped execution model.
    """
    payload = {
        "name": "roi_channel_v2",
        "metric": "roi",
        "chinese_name": "渠道ROI",
        "query_type": "cross_fact_staged_metric",
        "result_grain": "channel",
        "description": (
            "按渠道计算同一分析时间窗内的 GMV / 营销投放金额。"
            "ROI 为倍数，不乘以 100。"
            "仅比较同时具备销售和营销能力的启用渠道。"
        ),
        "semantic_contract": {
            "date_attribution": "fact_orders.paid_at",
            "time_window_columns": [
                "fact_orders.paid_at",
                "fact_marketing_spend.spend_date",
            ],
            "metric_expression": (
                "channel_gmv / marketing_spend_amount"
            ),
            "base_filters": [
                (
                    "the same analysis_start_date and "
                    "analysis_end_date apply to paid_at and spend_date"
                ),
                "dim_channel.is_active = TRUE",
                "dim_channel.is_sales_channel = TRUE",
                "dim_channel.is_marketing_channel = TRUE",
            ],
        },
        "query_logic": {
            "stages": [
                {
                    "stage_id": "channel_sales",
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
                    ],
                    "filters": [
                        "fo.paid_at IS NOT NULL",
                        (
                            "CAST(fo.paid_at AS DATE) "
                            "BETWEEN :analysis_start_date "
                            "AND :analysis_end_date"
                        ),
                    ],
                    "group_by": [
                        "fo.channel_id",
                    ],
                    "outputs": [
                        {
                            "field": "channel_id",
                            "expression": "fo.channel_id",
                        },
                        {
                            "field": "channel_gmv",
                            "expression": (
                                "SUM(foi.item_paid_amount)"
                            ),
                        },
                        {
                            "field": "buyer_count",
                            "expression": (
                                "COUNT(DISTINCT fo.customer_id)"
                            ),
                        },
                    ],
                    "hidden_control_fields": [],
                },
                {
                    "stage_id": "channel_spend",
                    "stage_type": "aggregate",
                    "source": {
                        "table": "fact_marketing_spend",
                        "alias": "fms",
                    },
                    "filters": [
                        (
                            "fms.spend_date "
                            "BETWEEN :analysis_start_date "
                            "AND :analysis_end_date"
                        ),
                    ],
                    "group_by": [
                        "fms.channel_id",
                    ],
                    "outputs": [
                        {
                            "field": "channel_id",
                            "expression": "fms.channel_id",
                        },
                        {
                            "field": "marketing_spend_amount",
                            "expression": (
                                "SUM(fms.spend_amount)"
                            ),
                        },
                    ],
                    "hidden_control_fields": [],
                },
                {
                    "stage_id": "final",
                    "stage_type": "project",
                    "source": {
                        "stage_id": "channel_sales",
                        "alias": "cs",
                    },
                    "joins": [
                        {
                            "stage_id": "channel_spend",
                            "alias": "csp",
                            "join_type": "inner",
                            "conditions": [
                                {
                                    "left": "cs.channel_id",
                                    "right": "csp.channel_id",
                                },
                            ],
                        },
                        {
                            "table": "dim_channel",
                            "alias": "dc",
                            "join_type": "inner",
                            "conditions": [
                                {
                                    "left": "cs.channel_id",
                                    "right": "dc.channel_id",
                                },
                            ],
                        },
                    ],
                    "filters": [
                        "dc.is_active = TRUE",
                        "dc.is_sales_channel = TRUE",
                        "dc.is_marketing_channel = TRUE",
                    ],
                    "outputs": [
                        {
                            "field": "channel_name",
                            "expression": "dc.channel_name",
                        },
                        {
                            "field": "roi",
                            "expression": (
                                "cs.channel_gmv "
                                "/ NULLIF("
                                "csp.marketing_spend_amount, 0)"
                            ),
                        },
                    ],
                    "hidden_control_fields": [
                        {
                            "field": "__group_size",
                            "expression": "cs.buyer_count",
                            "semantics": (
                                "distinct_buyers_per_channel"
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
                "fact_marketing_spend",
                "dim_channel",
                "dim_region",
            ],
            "required_columns": [
                "fact_order_items.order_id",
                "fact_order_items.item_paid_amount",
                "fact_orders.order_id",
                "fact_orders.customer_id",
                "fact_orders.paid_at",
                "fact_orders.channel_id",
                "fact_orders.shipping_region_id",
                "fact_marketing_spend.spend_date",
                "fact_marketing_spend.channel_id",
                "fact_marketing_spend.spend_amount",
                "dim_channel.channel_id",
                "dim_channel.channel_code",
                "dim_channel.channel_name",
                "dim_channel.is_sales_channel",
                "dim_channel.is_marketing_channel",
                "dim_channel.is_active",
                "dim_region.region_id",
                "dim_region.region_code",
            ],
        },
        "scope_contract": {
            "scope_mode": "predicate_safe",
            "source_tables": [
                "fact_order_items",
                "fact_marketing_spend",
            ],
            "required_dimensions": [
                "region",
                "channel",
            ],
            "targets": [
                {
                    "target_id": "roi_channel_sales",
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
                {
                    "target_id": "roi_channel_spend",
                    "source_table": "fact_marketing_spend",
                    "table_aliases": [
                        {
                            "table_name": "fact_marketing_spend",
                            "alias": "fms",
                        },
                    ],
                },
            ],
        },
        "result_contract": {
            "result_shape": "aggregate",
            "field_bindings": [
                {
                    "output_field": "channel_name",
                    "source_columns": [
                        "dim_channel.channel_name",
                    ],
                    "category": "ordinary",
                },
                {
                    "output_field": "roi",
                    "source_columns": [
                        "fact_order_items.item_paid_amount",
                        "fact_marketing_spend.spend_amount",
                    ],
                    "category": "business_confidential",
                },
            ],
            "minimum_group_size_required": True,
            "group_size_field": "__group_size",
        },
        "default_sort": {
            "field": "roi",
            "direction": "desc",
        },
    }

    return QueryPlanV2.model_validate(payload)


if __name__ == "__main__":
    plan = build_roi_channel_plan()

    print("ROI Query Plan V2")
    print(f"Plan: {plan.name}")
    print(f"Metric: {plan.metric}")
    print(f"Stages: {len(plan.query_logic.stages)}")
    print(f"Grain: {plan.result_grain}")
