from app.semantic_layer.query_plan_v2_models import (
    QueryPlanV2,
)


def build_brand_paid_new_customer_count_overall_plan(
) -> QueryPlanV2:
    """
    Brand-paid-new-customer candidate.

    Identity:
    customer_id

    First event:
    the customer's first successful paid order in complete brand history.

    The first row is ranked by:
    paid_at, order_id

    The analysis window is applied only after the true brand-first order
    has been identified. Channel and Region scopes are therefore
    post-sequence dimensions for this metric.
    """
    payload = {
        "name": "brand_paid_new_customer_count_overall_v2",
        "metric": "brand_paid_new_customer_count",
        "chinese_name": "品牌支付新客数",
        "query_type": "global_history_first_event_metric",
        "result_grain": "overall",
        "description": (
            "统计真实品牌首单支付时间落入分析窗口的 customer 数量。"
            "品牌首单从完整成功支付历史中按 customer 确定，"
            "每个 customer 在品牌生命周期中最多成为一次品牌新客。"
        ),
        "semantic_contract": {
            "date_attribution": "fact_orders.paid_at",
            "time_window_columns": [
                "fact_orders.paid_at",
            ],
            "metric_expression": (
                "COUNT(DISTINCT customer_id whose true brand-first "
                "paid order falls within the analysis window)"
            ),
            "base_filters": [
                "fact_orders.paid_at IS NOT NULL",
                (
                    "brand first successful payment is determined "
                    "before the analysis date filter"
                ),
            ],
        },
        "query_logic": {
            "stages": [
                {
                    "stage_id": "brand_order_sequence",
                    "stage_type": "project",
                    "source": {
                        "table": "fact_orders",
                        "alias": "fo",
                    },
                    "filters": [
                        "fo.paid_at IS NOT NULL",
                    ],
                    "outputs": [
                        {
                            "field": "customer_id",
                            "expression": "fo.customer_id",
                        },
                        {
                            "field": "order_id",
                            "expression": "fo.order_id",
                        },
                        {
                            "field": "paid_at",
                            "expression": "fo.paid_at",
                        },
                        {
                            "field": "channel_id",
                            "expression": "fo.channel_id",
                        },
                        {
                            "field": "shipping_region_id",
                            "expression": "fo.shipping_region_id",
                        },
                        {
                            "field": "event_rank",
                            "expression": (
                                "ROW_NUMBER() OVER ("
                                "PARTITION BY fo.customer_id "
                                "ORDER BY fo.paid_at ASC, fo.order_id ASC)"
                            ),
                        },
                    ],
                    "hidden_control_fields": [],
                },
                {
                    "stage_id": "true_brand_first_paid",
                    "stage_type": "filter",
                    "source": {
                        "stage_id": "brand_order_sequence",
                        "alias": "bos",
                    },
                    "filters": [
                        "bos.event_rank = 1",
                    ],
                    "outputs": [
                        {
                            "field": "customer_id",
                            "expression": "bos.customer_id",
                        },
                        {
                            "field": "first_paid_at",
                            "expression": "bos.paid_at",
                        },
                        {
                            "field": "first_channel_id",
                            "expression": "bos.channel_id",
                        },
                        {
                            "field": "first_shipping_region_id",
                            "expression": "bos.shipping_region_id",
                        },
                    ],
                    "hidden_control_fields": [],
                },
                {
                    "stage_id": "windowed_brand_acquisition",
                    "stage_type": "aggregate",
                    "source": {
                        "stage_id": "true_brand_first_paid",
                        "alias": "bfp",
                    },
                    "filters": [
                        (
                            "CAST(bfp.first_paid_at AS DATE) "
                            "BETWEEN :analysis_start_date "
                            "AND :analysis_end_date"
                        ),
                    ],
                    "outputs": [
                        {
                            "field": "brand_paid_new_customer_count",
                            "expression": (
                                "COUNT(DISTINCT bfp.customer_id)"
                            ),
                        },
                    ],
                    "hidden_control_fields": [
                        {
                            "field": "__group_size",
                            "expression": (
                                "COUNT(DISTINCT bfp.customer_id)"
                            ),
                            "semantics": (
                                "brand_paid_new_customers_in_analysis_period"
                            ),
                        },
                    ],
                },
            ],
            "final_stage": "windowed_brand_acquisition",
        },
        "resource_contract": {
            "required_tables": [
                "fact_orders",
                "dim_channel",
                "dim_region",
            ],
            "required_columns": [
                "fact_orders.order_id",
                "fact_orders.customer_id",
                "fact_orders.channel_id",
                "fact_orders.shipping_region_id",
                "fact_orders.paid_at",
                "dim_channel.channel_id",
                "dim_channel.channel_code",
                "dim_region.region_id",
                "dim_region.region_code",
            ],
        },
        "scope_contract": {
            "scope_mode": "global_history_required",
            "source_tables": [
                "fact_orders",
            ],
            "required_dimensions": [
                "region",
                "channel",
            ],
            "targets": [
                {
                    "target_id": "brand_first_paid_orders",
                    "source_table": "fact_orders",
                    "table_aliases": [
                        {
                            "table_name": "fact_orders",
                            "alias": "fo",
                        },
                    ],
                },
            ],
            "history_contract": {
                "history_stage_id": "brand_order_sequence",
                "analysis_window_stage_id": (
                    "windowed_brand_acquisition"
                ),
                "history_source_tables": [
                    "fact_orders",
                ],
                "sequence_partition_by": [
                    "fo.customer_id",
                ],
                "sequence_order_by": [
                    "fo.paid_at",
                    "fo.order_id",
                ],
                "pre_sequence_scope_bindings": [],
                "post_sequence_scope_dimensions": [
                    "region",
                    "channel",
                ],
                "analysis_window_parameters": [
                    "analysis_start_date",
                    "analysis_end_date",
                ],
            },
        },
        "result_contract": {
            "result_shape": "aggregate",
            "field_bindings": [
                {
                    "output_field": (
                        "brand_paid_new_customer_count"
                    ),
                    "source_columns": [
                        "fact_orders.customer_id",
                        "fact_orders.paid_at",
                        "fact_orders.order_id",
                    ],
                    "category": "ordinary",
                },
            ],
            "minimum_group_size_required": True,
            "group_size_field": "__group_size",
        },
        "default_sort": {
            "field": "brand_paid_new_customer_count",
            "direction": "desc",
        },
    }

    return QueryPlanV2.model_validate(payload)


if __name__ == "__main__":
    plan = (
        build_brand_paid_new_customer_count_overall_plan()
    )

    print("Brand Paid New Customer Query Plan V2")
    print(f"Plan: {plan.name}")
    print(f"Metric: {plan.metric}")
    print(f"Stages: {len(plan.query_logic.stages)}")
    print(f"Scope mode: {plan.scope_contract.scope_mode.value}")
