from app.semantic_layer.query_plan_v2_models import (
    QueryPlanV2,
)


def build_repeat_customer_count_overall_plan() -> QueryPlanV2:
    """
    Build the first Staged Query Plan V2 sample.

    Business semantics:
    - Analysis-period repeat customer.
    - Same customer, same paid date, multiple orders count as one purchase day.
    - A repeat customer has at least two distinct paid dates.
    - This is NOT a 30d/90d cohort repurchase metric.
    """
    payload = {
        "name": "repeat_customer_count_overall_v2",
        "metric": "repeat_customer_count",
        "chinese_name": "整体跨日复购人数",
        "query_type": "staged_aggregate_metric",
        "result_grain": "overall",
        "description": (
            "在指定分析范围内，统计至少在两个不同支付日期"
            "完成成功购买的 customer 数量。"
        ),
        "semantic_contract": {
            "date_attribution": "fact_orders.paid_at",
            "metric_expression": (
                "COUNT(customers with at least two distinct paid dates)"
            ),
            "base_filters": [
                "fact_orders.paid_at IS NOT NULL",
            ],
        },
        "query_logic": {
            "stages": [
                {
                    "stage_id": "customer_purchase_summary",
                    "stage_type": "aggregate",
                    "source": {
                        "table": "fact_orders",
                        "alias": "fo",
                    },
                    "filters": [
                        "fo.paid_at IS NOT NULL",
                    ],
                    "group_by": [
                        "fo.customer_id",
                    ],
                    "outputs": [
                        {
                            "field": "customer_id",
                            "expression": "fo.customer_id",
                        },
                        {
                            "field": "purchase_day_count",
                            "expression": (
                                "COUNT(DISTINCT CAST(fo.paid_at AS DATE))"
                            ),
                        },
                    ],
                    "hidden_control_fields": [],
                },
                {
                    "stage_id": "final",
                    "stage_type": "aggregate",
                    "source": {
                        "stage_id": "customer_purchase_summary",
                        "alias": "cps",
                    },
                    "outputs": [
                        {
                            "field": "repeat_customer_count",
                            "expression": (
                                "COUNT(*) FILTER "
                                "(WHERE cps.purchase_day_count >= 2)"
                            ),
                        },
                    ],
                    "hidden_control_fields": [
                        {
                            "field": "__group_size",
                            "expression": "COUNT(*)",
                            "semantics": (
                                "distinct_buyers_in_analysis_period"
                            ),
                        },
                    ],
                },
            ],
            "final_stage": "final",
        },
        "resource_contract": {
            "required_tables": [
                "fact_orders",
                "dim_region",
                "dim_channel",
            ],
            "required_columns": [
                "fact_orders.customer_id",
                "fact_orders.paid_at",
                "fact_orders.shipping_region_id",
                "fact_orders.channel_id",
                "dim_region.region_id",
                "dim_region.region_code",
                "dim_channel.channel_id",
                "dim_channel.channel_code",
            ],
        },
        "scope_contract": {
            "scope_mode": "predicate_safe",
            "source_tables": [
                "fact_orders",
            ],
            "required_dimensions": [
                "region",
                "channel",
            ],
            "targets": [
                {
                    "target_id": "repeat_orders",
                    "source_table": "fact_orders",
                    "table_aliases": [
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
                    "output_field": "repeat_customer_count",
                    "source_columns": [
                        "fact_orders.customer_id",
                        "fact_orders.paid_at",
                    ],
                    "category": "ordinary",
                },
            ],
            "minimum_group_size_required": True,
            "group_size_field": "__group_size",
        },
        "default_sort": {
            "field": "repeat_customer_count",
            "direction": "desc",
        },
    }

    return QueryPlanV2.model_validate(payload)


if __name__ == "__main__":
    plan = build_repeat_customer_count_overall_plan()

    print("Staged Query Plan V2 Sample")
    print(f"Plan: {plan.name}")
    print(f"Metric: {plan.metric}")
    print(f"Stages: {len(plan.query_logic.stages)}")
    print(f"Final stage: {plan.query_logic.final_stage}")
