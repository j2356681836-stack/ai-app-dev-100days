from app.semantic_layer.query_plan_v2_models import (
    QueryPlanV2,
)


def _base_repeat_payload(
    *,
    name: str,
    metric: str,
    chinese_name: str,
    description: str,
    final_expression: str,
) -> dict:
    """
    Shared trusted staged contract for analysis-period repeat metrics.

    Stage 1 freezes the customer-period grain:
    - one row per customer
    - distinct purchase-day count
    - distinct paid-order count

    Final stage derives the requested repeat metric.
    """
    return {
        "name": name,
        "metric": metric,
        "chinese_name": chinese_name,
        "query_type": "staged_aggregate_metric",
        "result_grain": "overall",
        "description": description,
        "semantic_contract": {
            "date_attribution": "fact_orders.paid_at",
            "metric_expression": final_expression,
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
                        {
                            "field": "paid_order_count",
                            "expression": (
                                "COUNT(DISTINCT fo.order_id)"
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
                            "field": metric,
                            "expression": final_expression,
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
                "fact_orders.order_id",
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
                    "target_id": f"{name}_orders",
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
                    "output_field": metric,
                    "source_columns": [
                        "fact_orders.order_id",
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
            "field": metric,
            "direction": "desc",
        },
    }


def build_repeat_customer_count_overall_plan() -> QueryPlanV2:
    payload = _base_repeat_payload(
        name="repeat_customer_count_overall_v2",
        metric="repeat_customer_count",
        chinese_name="整体跨日复购人数",
        description=(
            "在指定分析范围内，统计至少在两个不同支付日期"
            "完成成功购买的 customer 数量。"
            "同一 customer 同日多单只视为一个购买日。"
        ),
        final_expression=(
            "COUNT(*) FILTER "
            "(WHERE cps.purchase_day_count >= 2)"
        ),
    )

    return QueryPlanV2.model_validate(payload)


def build_multi_order_customer_count_overall_plan() -> QueryPlanV2:
    payload = _base_repeat_payload(
        name="multi_order_customer_count_overall_v2",
        metric="multi_order_customer_count",
        chinese_name="整体两单及以上购买人数",
        description=(
            "在指定分析范围内，统计产生至少两张成功支付订单的"
            " customer 数量。"
            "同一 customer 同日多单仍分别计入订单数量。"
        ),
        final_expression=(
            "COUNT(*) FILTER "
            "(WHERE cps.paid_order_count >= 2)"
        ),
    )

    return QueryPlanV2.model_validate(payload)


def build_repeat_customer_rate_overall_plan() -> QueryPlanV2:
    payload = _base_repeat_payload(
        name="repeat_customer_rate_overall_v2",
        metric="repeat_customer_rate",
        chinese_name="整体跨日复购率",
        description=(
            "在指定分析范围内，跨日复购客户数占同期所有"
            "成功支付购买客户数的比例。"
        ),
        final_expression=(
            "CAST("
            "COUNT(*) FILTER "
            "(WHERE cps.purchase_day_count >= 2) "
            "AS NUMERIC"
            ") / NULLIF(COUNT(*), 0)"
        ),
    )

    return QueryPlanV2.model_validate(payload)


def build_repeat_metric_family() -> tuple[QueryPlanV2, ...]:
    return (
        build_repeat_customer_count_overall_plan(),
        build_multi_order_customer_count_overall_plan(),
        build_repeat_customer_rate_overall_plan(),
    )


if __name__ == "__main__":
    plans = build_repeat_metric_family()

    print("Repeat Metric Query Plan V2 Family")
    print(f"Plans: {len(plans)}")

    for plan in plans:
        print(
            "-",
            plan.name,
            "| metric:",
            plan.metric,
            "| stages:",
            len(plan.query_logic.stages),
        )
