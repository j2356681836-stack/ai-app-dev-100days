from app.semantic_layer.query_plan_v2_models import (
    QueryPlanV2,
)


ORDER_COUNT_CUSTOMER_SEGMENT_ORDER_V2: tuple[str, ...] = (
    "OLD_PLATINUM",
    "OLD_GOLD",
    "OLD_SILVER",
    "OLD_BRONZE",
    "OLD_NON_MEMBER",
    "NEW_CUSTOMER",
)


def build_order_count_customer_lifecycle_membership_plan_v2(
) -> QueryPlanV2:
    """
    构建订单数的人群构成 Query Plan。

    Day93 Demo 口径：
    - Universe：当前 Effective Scope 内的成功支付订单；
    - 老客：analysis_start_date 之前，在同一 Effective Scope 内
      已存在成功支付历史的 customer；
    - 新客：analysis_start_date 之前没有成功支付历史，
      但当前窗口发生成功支付的 customer；
    - 老客订单按该笔订单支付时的 member_level_at_order 划分；
    - 新客不再按会员层级继续拆分；
    - 这是 scope-local observed lifecycle，不声称是跨 Scope 的
      absolute brand-first-customer contract。

    因为 History 与 Report 两个 physical stage 都绑定同一套
    Row Scope，所以不会为了判断“老客”读取越权 Scope。
    """

    payload = {
        "name": "order_count_customer_lifecycle_membership_v2",
        "metric": "order_count",
        "chinese_name": "客户生命周期与支付时会员订单构成",
        "query_type": (
            "scope_local_customer_lifecycle_membership_composition"
        ),
        "result_grain": "customer_lifecycle_membership",
        "description": (
            "把当前窗口成功支付订单划分为新客订单，以及老客在支付时"
            "铂金/黄金/白银/青铜/非会员五个互斥层级。"
            "新老客判断只使用当前 Effective Scope 内、analysis_start_date "
            "之前的可观察成功支付历史。"
        ),
        "semantic_contract": {
            "date_attribution": "fact_orders.paid_at",
            "time_window_columns": [
                "fact_orders.paid_at",
            ],
            "metric_expression": (
                "COUNT(DISTINCT report order_id) grouped by "
                "scope-local customer lifecycle and payment-time membership"
            ),
            "base_filters": [
                "fact_orders.paid_at IS NOT NULL",
                (
                    "old customer = same-scope customer with successful "
                    "payment before analysis_start_date"
                ),
                (
                    "new customer = no same-scope successful payment before "
                    "analysis_start_date and has successful payment in window"
                ),
                (
                    "old-customer membership uses "
                    "fact_orders.member_level_at_order"
                ),
            ],
        },
        "query_logic": {
            "stages": [
                {
                    "stage_id": "old_customer_history",
                    "stage_type": "aggregate",
                    "source": {
                        "table": "fact_orders",
                        "alias": "hist",
                    },
                    "filters": [
                        "hist.paid_at IS NOT NULL",
                        (
                            "CAST(hist.paid_at AS DATE) "
                            "< :analysis_start_date"
                        ),
                    ],
                    "group_by": [
                        "hist.customer_id",
                    ],
                    "outputs": [
                        {
                            "field": "customer_id",
                            "expression": "hist.customer_id",
                        },
                    ],
                    "hidden_control_fields": [],
                },
                {
                    "stage_id": "report_orders",
                    "stage_type": "project",
                    "source": {
                        "table": "fact_orders",
                        "alias": "ro",
                    },
                    "filters": [
                        "ro.paid_at IS NOT NULL",
                        (
                            "CAST(ro.paid_at AS DATE) "
                            "BETWEEN :analysis_start_date "
                            "AND :analysis_end_date"
                        ),
                    ],
                    "outputs": [
                        {
                            "field": "order_id",
                            "expression": "ro.order_id",
                        },
                        {
                            "field": "customer_id",
                            "expression": "ro.customer_id",
                        },
                        {
                            "field": "member_level_at_order",
                            "expression": "ro.member_level_at_order",
                        },
                    ],
                    "hidden_control_fields": [],
                },
                {
                    "stage_id": "classified_orders",
                    "stage_type": "project",
                    "source": {
                        "stage_id": "report_orders",
                        "alias": "r",
                    },
                    "joins": [
                        {
                            "stage_id": "old_customer_history",
                            "alias": "h",
                            "join_type": "left",
                            "conditions": [
                                {
                                    "left": "r.customer_id",
                                    "right": "h.customer_id",
                                },
                            ],
                        },
                    ],
                    "outputs": [
                        {
                            "field": "order_id",
                            "expression": "r.order_id",
                        },
                        {
                            "field": "customer_id",
                            "expression": "r.customer_id",
                        },
                        {
                            "field": "customer_segment",
                            "expression": (
                                "CASE "
                                "WHEN h.customer_id IS NULL "
                                "THEN 'NEW_CUSTOMER' "
                                "WHEN r.member_level_at_order = 'platinum' "
                                "THEN 'OLD_PLATINUM' "
                                "WHEN r.member_level_at_order = 'gold' "
                                "THEN 'OLD_GOLD' "
                                "WHEN r.member_level_at_order = 'silver' "
                                "THEN 'OLD_SILVER' "
                                "WHEN r.member_level_at_order = 'bronze' "
                                "THEN 'OLD_BRONZE' "
                                "WHEN r.member_level_at_order IS NULL "
                                "THEN 'OLD_NON_MEMBER' "
                                "ELSE 'OLD_UNKNOWN' "
                                "END"
                            ),
                        },
                    ],
                    "hidden_control_fields": [],
                },
                {
                    "stage_id": "final",
                    "stage_type": "aggregate",
                    "source": {
                        "stage_id": "classified_orders",
                        "alias": "co",
                    },
                    "group_by": [
                        "co.customer_segment",
                    ],
                    "outputs": [
                        {
                            "field": "customer_segment",
                            "expression": "co.customer_segment",
                        },
                        {
                            "field": "order_count",
                            "expression": (
                                "COUNT(DISTINCT co.order_id)"
                            ),
                        },
                    ],
                    "hidden_control_fields": [
                        {
                            "field": "__group_size",
                            "expression": (
                                "COUNT(DISTINCT co.customer_id)"
                            ),
                            "semantics": (
                                "distinct_customers_per_customer_segment"
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
                "fact_orders",
            ],
            "required_dimensions": [
                "region",
                "channel",
            ],
            "targets": [
                {
                    "target_id": "order_customer_history_source",
                    "source_table": "fact_orders",
                    "table_aliases": [
                        {
                            "table_name": "fact_orders",
                            "alias": "hist",
                        },
                    ],
                },
                {
                    "target_id": "order_customer_report_source",
                    "source_table": "fact_orders",
                    "table_aliases": [
                        {
                            "table_name": "fact_orders",
                            "alias": "ro",
                        },
                    ],
                },
            ],
        },
        "result_contract": {
            "result_shape": "aggregate",
            "field_bindings": [
                {
                    "output_field": "customer_segment",
                    "source_columns": [
                        "fact_orders.customer_id",
                        "fact_orders.paid_at",
                        "fact_orders.member_level_at_order",
                    ],
                    "category": "ordinary",
                },
                {
                    "output_field": "order_count",
                    "source_columns": [
                        "fact_orders.order_id",
                    ],
                    "category": "ordinary",
                },
            ],
            "minimum_group_size_required": True,
            "group_size_field": "__group_size",
        },
        "default_sort": {
            "field": "order_count",
            "direction": "desc",
        },
    }

    return QueryPlanV2.model_validate(payload)


if __name__ == "__main__":
    plan = (
        build_order_count_customer_lifecycle_membership_plan_v2()
    )

    print("Order Count Customer Lifecycle Membership Query Plan V2")
    print(f"Plan: {plan.name}")
    print(f"Metric: {plan.metric}")
    print(f"Grain: {plan.result_grain}")
    print(f"Stages: {len(plan.query_logic.stages)}")
