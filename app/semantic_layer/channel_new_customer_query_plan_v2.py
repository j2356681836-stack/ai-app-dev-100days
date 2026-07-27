from app.semantic_layer.query_plan_v2_models import (
    QueryPlanV2,
)


def build_channel_paid_new_customer_count_channel_plan(
) -> QueryPlanV2:
    """
    V2 channel-paid-new-customer candidate.

    Identity:
    customer_id × channel_id

    First event:
    the customer's first successful paid order in that channel,
    determined from complete channel history before the analysis window.

    Governance:
    - Channel Scope is safe before sequencing because channel_id is part
      of the first-event identity partition.
    - Region Scope is not safe before sequencing because region is not
      part of the identity and may differ across purchases in one channel.
    """
    payload = {
        "name": "channel_paid_new_customer_count_channel_v2",
        "metric": "channel_paid_new_customer_count",
        "chinese_name": "渠道支付新客数",
        "query_type": "global_history_first_event_metric",
        "result_grain": "channel",
        "description": (
            "按渠道统计 customer 在该 channel 的第一次成功支付事件。"
            "同一 customer 可以分别成为多个渠道的新客，"
            "但在同一 channel 中最多一次。"
        ),
        "semantic_contract": {
            "date_attribution": "fact_orders.paid_at",
            "time_window_columns": [
                "fact_orders.paid_at",
            ],
            "metric_expression": (
                "COUNT(customer-channel whose first_channel_paid_at "
                "falls within the analysis window)"
            ),
            "base_filters": [
                "fact_orders.paid_at IS NOT NULL",
                (
                    "channel first successful payment is determined "
                    "before the analysis date filter"
                ),
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
                    "stage_id": "final",
                    "stage_type": "project",
                    "source": {
                        "stage_id": "windowed_channel_acquisition",
                        "alias": "wca",
                    },
                    "joins": [
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
                    "outputs": [
                        {
                            "field": "channel_name",
                            "expression": "dc.channel_name",
                        },
                        {
                            "field": "channel_paid_new_customer_count",
                            "expression": (
                                "wca.channel_paid_new_customer_count"
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
                "dim_channel.channel_name",
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
                    "target_id": "channel_first_paid_orders",
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
                    "output_field": (
                        "channel_paid_new_customer_count"
                    ),
                    "source_columns": [
                        "fact_orders.customer_id",
                        "fact_orders.channel_id",
                        "fact_orders.paid_at",
                    ],
                    "category": "ordinary",
                },
            ],
            "minimum_group_size_required": True,
            "group_size_field": "__group_size",
        },
        "default_sort": {
            "field": "channel_paid_new_customer_count",
            "direction": "desc",
        },
    }

    return QueryPlanV2.model_validate(payload)


if __name__ == "__main__":
    plan = (
        build_channel_paid_new_customer_count_channel_plan()
    )

    print("Channel Paid New Customer Query Plan V2")
    print(f"Plan: {plan.name}")
    print(f"Metric: {plan.metric}")
    print(f"Stages: {len(plan.query_logic.stages)}")
    print(f"Scope mode: {plan.scope_contract.scope_mode.value}")
