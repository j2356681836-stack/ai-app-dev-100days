from app.semantic_layer.query_plan_v2_models import (
    QueryPlanV2,
)


def build_cac_channel_plan() -> QueryPlanV2:
    """
    Build the V2 channel CAC candidate contract.

    V2 semantics:
    - denominator is channel-paid-new-customer count
    - event identity is customer_id × channel_id
    - true channel-first-paid is determined from complete channel history
    - the analysis window is applied only after first-event sequencing
    - spend and acquisition use the same analysis date parameters

    Governance:
    - Channel Scope is safe before sequencing because channel_id is part
      of the first-event partition identity.
    - Region Scope is not safe before sequencing.
    - fact_marketing_spend has no Region Anchor.
    - therefore current Region+Channel scoped execution must fail closed.
    """
    payload = {
        "name": "cac_channel_v2",
        "metric": "cac",
        "chinese_name": "渠道CAC",
        "query_type": "global_history_cross_fact_metric",
        "result_grain": "channel",
        "description": (
            "按渠道计算同一分析时间窗内营销投放金额 "
            "除以渠道支付新客数。"
            "渠道支付新客以 customer × channel 的完整历史"
            "第一次成功支付为准。"
        ),
        "semantic_contract": {
            "date_attribution": "fact_orders.paid_at",
            "time_window_columns": [
                "fact_orders.paid_at",
                "fact_marketing_spend.spend_date",
            ],
            "metric_expression": (
                "marketing_spend_amount "
                "/ channel_paid_new_customer_count"
            ),
            "base_filters": [
                "fact_orders.paid_at IS NOT NULL",
                (
                    "channel first successful payment is determined "
                    "before the analysis date filter"
                ),
                (
                    "the same analysis_start_date and "
                    "analysis_end_date apply to first_channel_paid_at "
                    "and spend_date"
                ),
                "dim_channel.is_active = TRUE",
                "dim_channel.is_sales_channel = TRUE",
                "dim_channel.is_marketing_channel = TRUE",
            ],
        },
        "query_logic": {
            "stages": [
                {
                    "stage_id": "channel_first_paid_history",
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
                        "fo.channel_id",
                    ],
                    "outputs": [
                        {
                            "field": "customer_id",
                            "expression": "fo.customer_id",
                        },
                        {
                            "field": "channel_id",
                            "expression": "fo.channel_id",
                        },
                        {
                            "field": "first_channel_paid_at",
                            "expression": "MIN(fo.paid_at)",
                        },
                    ],
                    "hidden_control_fields": [],
                },
                {
                    "stage_id": "windowed_channel_acquisition",
                    "stage_type": "aggregate",
                    "source": {
                        "stage_id": "channel_first_paid_history",
                        "alias": "cfp",
                    },
                    "filters": [
                        (
                            "CAST(cfp.first_channel_paid_at AS DATE) "
                            "BETWEEN :analysis_start_date "
                            "AND :analysis_end_date"
                        ),
                    ],
                    "group_by": [
                        "cfp.channel_id",
                    ],
                    "outputs": [
                        {
                            "field": "channel_id",
                            "expression": "cfp.channel_id",
                        },
                        {
                            "field": "channel_paid_new_customer_count",
                            "expression": (
                                "COUNT(DISTINCT cfp.customer_id)"
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
                        "stage_id": "windowed_channel_acquisition",
                        "alias": "wca",
                    },
                    "joins": [
                        {
                            "stage_id": "channel_spend",
                            "alias": "csp",
                            "join_type": "inner",
                            "conditions": [
                                {
                                    "left": "wca.channel_id",
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
                                    "left": "wca.channel_id",
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
                            "field": "cac",
                            "expression": (
                                "csp.marketing_spend_amount "
                                "/ NULLIF("
                                "wca.channel_paid_new_customer_count, 0)"
                            ),
                        },
                    ],
                    "hidden_control_fields": [
                        {
                            "field": "__group_size",
                            "expression": (
                                "wca.channel_paid_new_customer_count"
                            ),
                            "semantics": (
                                "channel_paid_new_customers_per_channel"
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
                "fact_marketing_spend",
                "dim_channel",
                "dim_region",
            ],
            "required_columns": [
                "fact_orders.order_id",
                "fact_orders.customer_id",
                "fact_orders.channel_id",
                "fact_orders.shipping_region_id",
                "fact_orders.paid_at",
                "fact_marketing_spend.spend_date",
                "fact_marketing_spend.channel_id",
                "fact_marketing_spend.spend_amount",
                "dim_channel.channel_id",
                "dim_channel.channel_code",
                "dim_channel.channel_name",
                "dim_channel.is_active",
                "dim_channel.is_sales_channel",
                "dim_channel.is_marketing_channel",
                "dim_region.region_id",
                "dim_region.region_code",
            ],
        },
        "scope_contract": {
            "scope_mode": "global_history_required",
            "source_tables": [
                "fact_orders",
                "fact_marketing_spend",
            ],
            "required_dimensions": [
                "region",
                "channel",
            ],
            "targets": [
                {
                    "target_id": "cac_channel_acquisition",
                    "source_table": "fact_orders",
                    "table_aliases": [
                        {
                            "table_name": "fact_orders",
                            "alias": "fo",
                        },
                    ],
                },
                {
                    "target_id": "cac_channel_spend",
                    "source_table": "fact_marketing_spend",
                    "table_aliases": [
                        {
                            "table_name": "fact_marketing_spend",
                            "alias": "fms",
                        },
                    ],
                },
            ],
            "history_contract": {
                "history_stage_id": (
                    "channel_first_paid_history"
                ),
                "analysis_window_stage_id": (
                    "windowed_channel_acquisition"
                ),
                "history_source_tables": [
                    "fact_orders",
                ],
                "sequence_partition_by": [
                    "fo.customer_id",
                    "fo.channel_id",
                ],
                "sequence_order_by": [
                    "fo.paid_at",
                    "fo.order_id",
                ],
                "pre_sequence_scope_bindings": [
                    {
                        "dimension": "channel",
                        "partition_reference": "fo.channel_id",
                    },
                ],
                "post_sequence_scope_dimensions": [
                    "region",
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
                    "output_field": "channel_name",
                    "source_columns": [
                        "dim_channel.channel_name",
                    ],
                    "category": "ordinary",
                },
                {
                    "output_field": "cac",
                    "source_columns": [
                        "fact_orders.customer_id",
                        "fact_orders.channel_id",
                        "fact_orders.paid_at",
                        "fact_marketing_spend.spend_amount",
                    ],
                    "category": "business_confidential",
                },
            ],
            "minimum_group_size_required": True,
            "group_size_field": "__group_size",
        },
        "default_sort": {
            "field": "cac",
            "direction": "asc",
        },
    }

    return QueryPlanV2.model_validate(payload)


if __name__ == "__main__":
    plan = build_cac_channel_plan()

    print("CAC Query Plan V2")
    print(f"Plan: {plan.name}")
    print(f"Metric: {plan.metric}")
    print(f"Stages: {len(plan.query_logic.stages)}")
    print(f"Scope mode: {plan.scope_contract.scope_mode.value}")
