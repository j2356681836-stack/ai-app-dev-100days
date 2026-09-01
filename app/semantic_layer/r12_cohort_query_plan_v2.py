from __future__ import annotations

from dataclasses import dataclass

from app.semantic_layer.query_plan_v2_models import (
    QueryPlanV2,
)


@dataclass(frozen=True)
class R12MetricPlanSpecV2:
    metric_name: str
    chinese_name: str
    metric_expression: str
    result_category: str
    group_size_expression: str
    group_size_semantics: str
    description: str


_R12_METRIC_SPECS: tuple[R12MetricPlanSpecV2, ...] = (
    R12MetricPlanSpecV2(
        metric_name="r12_base_customer_count",
        chinese_name="R12 Base客户数",
        metric_expression=(
            "COUNT(DISTINCT bc.customer_id)"
        ),
        result_category="ordinary",
        group_size_expression=(
            "COUNT(DISTINCT bc.customer_id)"
        ),
        group_size_semantics="r12_base_customer_count",
        description=(
            "报表开始日前连续 12 个日历月内，"
            "至少发生一次 Effective Purchase 的去重客户数。"
        ),
    ),
    R12MetricPlanSpecV2(
        metric_name="r12_repurchase_customer_count",
        chinese_name="R12回购客户数",
        metric_expression=(
            "COUNT(DISTINCT rc.customer_id)"
        ),
        result_category="ordinary",
        group_size_expression=(
            "COUNT(DISTINCT bc.customer_id)"
        ),
        group_size_semantics="r12_base_customer_count",
        description=(
            "R12 Base 客户中，在当前报表窗口再次发生 "
            "Effective Purchase 的去重客户数。"
        ),
    ),
    R12MetricPlanSpecV2(
        metric_name="r12_repurchase_rate",
        chinese_name="R12回购率",
        metric_expression=(
            "CAST(COUNT(DISTINCT rc.customer_id) AS NUMERIC) "
            "/ NULLIF(COUNT(DISTINCT bc.customer_id), 0)"
        ),
        result_category="ordinary",
        group_size_expression=(
            "COUNT(DISTINCT bc.customer_id)"
        ),
        group_size_semantics="r12_base_customer_count",
        description=(
            "R12回购客户数 / R12 Base客户数。"
        ),
    ),
    R12MetricPlanSpecV2(
        metric_name="r12_repurchase_amount",
        chinese_name="R12回购有效消费金额",
        metric_expression=(
            "SUM(COALESCE(rc.report_effective_amount, 0))"
        ),
        result_category="aggregated_business_confidential",
        group_size_expression=(
            "COUNT(DISTINCT rc.customer_id)"
        ),
        group_size_semantics="r12_repurchase_customer_count",
        description=(
            "R12回购客户在当前报表窗口的净有效消费金额。"
            "它不是 GMV；completed refund 会回溯扣减。"
        ),
    ),
    R12MetricPlanSpecV2(
        metric_name="r12_repurchase_spending",
        chinese_name="R12回购客单客户消费",
        metric_expression=(
            "SUM(COALESCE(rc.report_effective_amount, 0)) "
            "/ NULLIF(COUNT(DISTINCT rc.customer_id), 0)"
        ),
        result_category="aggregated_business_confidential",
        group_size_expression=(
            "COUNT(DISTINCT rc.customer_id)"
        ),
        group_size_semantics="r12_repurchase_customer_count",
        description=(
            "R12回购有效消费金额 / R12回购客户数。"
        ),
    ),
)


def _build_r12_plan_v2(
    spec: R12MetricPlanSpecV2,
) -> QueryPlanV2:
    """
    R12 Cohort V1 使用 Predicate-Safe Staged Query。

    Time semantics:
    - Base Stage:
      [analysis_start_date - 12 calendar months, analysis_start_date)
    - Report Stage:
      [analysis_start_date, analysis_end_date]（由既有 Time Binding 绑定）

    Base Stage 只消费 trusted analysis_start_date；
    Report Stage 显式声明 analysis_start_date + analysis_end_date，
    因此既有 Time Binding 只会把 canonical report-window predicate
    应用到 Report physical stage，不会把 Base 错裁成当前窗口。

    Scope semantics:
    Base 与 Report 各自声明独立 ScopeTarget，
    两者都必须服从相同 Effective Scope / Authorization。
    “all-channel Base”只表示不按渠道拆 Base，
    不表示可以绕过授权范围。
    """

    metric = spec.metric_name

    payload = {
        "name": f"{metric}_overall_v2",
        "metric": metric,
        "chinese_name": f"整体{spec.chinese_name}",
        "query_type": "r12_cohort_staged_metric",
        "result_grain": "overall",
        "description": spec.description,
        "semantic_contract": {
            "date_attribution": "fact_orders.paid_at",
            "metric_expression": spec.metric_expression,
            "base_filters": [
                "fact_orders.paid_at IS NOT NULL",
                (
                    "effective_purchase = "
                    "order paid item amount - completed refund amount > 0"
                ),
                (
                    "R12 Base uses the 12 calendar months immediately "
                    "before analysis_start_date"
                ),
            ],
            "time_window_columns": [
                "fact_orders.paid_at",
            ],
        },
        "query_logic": {
            "stages": [
                {
                    "stage_id": "base_item_effective",
                    "stage_type": "aggregate",
                    "source": {
                        "table": "fact_order_items",
                        "alias": "bfoi",
                    },
                    "joins": [
                        {
                            "table": "fact_orders",
                            "alias": "bfo",
                            "join_type": "inner",
                            "conditions": [
                                {
                                    "left": "bfoi.order_id",
                                    "right": "bfo.order_id",
                                },
                            ],
                        },
                        {
                            "table": "fact_refunds",
                            "alias": "bfr",
                            "join_type": "left",
                            "conditions": [
                                {
                                    "left": "bfoi.order_item_id",
                                    "right": "bfr.order_item_id",
                                },
                                {
                                    "left": "bfoi.order_id",
                                    "right": "bfr.order_id",
                                },
                            ],
                        },
                    ],
                    "filters": [
                        "bfo.paid_at IS NOT NULL",
                        (
                            "CAST(bfo.paid_at AS DATE) >= "
                            "(CAST(:analysis_start_date AS DATE) "
                            "- INTERVAL '12 months')"
                        ),
                        (
                            "CAST(bfo.paid_at AS DATE) "
                            "< CAST(:analysis_start_date AS DATE)"
                        ),
                    ],
                    "group_by": [
                        "bfoi.order_item_id",
                        "bfoi.order_id",
                        "bfoi.item_paid_amount",
                        "bfo.customer_id",
                        "bfo.paid_at",
                    ],
                    "outputs": [
                        {
                            "field": "order_item_id",
                            "expression": "bfoi.order_item_id",
                        },
                        {
                            "field": "order_id",
                            "expression": "bfoi.order_id",
                        },
                        {
                            "field": "customer_id",
                            "expression": "bfo.customer_id",
                        },
                        {
                            "field": "paid_date",
                            "expression": "CAST(bfo.paid_at AS DATE)",
                        },
                        {
                            "field": "item_effective_amount",
                            "expression": (
                                "bfoi.item_paid_amount - COALESCE("
                                "SUM(bfr.refund_amount) FILTER "
                                "(WHERE bfr.refund_status = 'completed'), "
                                "0)"
                            ),
                        },
                    ],
                    "hidden_control_fields": [],
                },
                {
                    "stage_id": "base_order_effective",
                    "stage_type": "aggregate",
                    "source": {
                        "stage_id": "base_item_effective",
                        "alias": "bie",
                    },
                    "group_by": [
                        "bie.customer_id",
                        "bie.order_id",
                        "bie.paid_date",
                    ],
                    "having": [
                        "SUM(bie.item_effective_amount) > 0",
                    ],
                    "outputs": [
                        {
                            "field": "customer_id",
                            "expression": "bie.customer_id",
                        },
                        {
                            "field": "order_id",
                            "expression": "bie.order_id",
                        },
                        {
                            "field": "paid_date",
                            "expression": "bie.paid_date",
                        },
                        {
                            "field": "order_effective_amount",
                            "expression": (
                                "SUM(bie.item_effective_amount)"
                            ),
                        },
                    ],
                    "hidden_control_fields": [],
                },
                {
                    "stage_id": "base_customer",
                    "stage_type": "aggregate",
                    "source": {
                        "stage_id": "base_order_effective",
                        "alias": "boe",
                    },
                    "group_by": [
                        "boe.customer_id",
                    ],
                    "outputs": [
                        {
                            "field": "customer_id",
                            "expression": "boe.customer_id",
                        },
                        {
                            "field": "base_effective_amount",
                            "expression": (
                                "SUM(boe.order_effective_amount)"
                            ),
                        },
                    ],
                    "hidden_control_fields": [],
                },
                {
                    "stage_id": "report_item_effective",
                    "stage_type": "aggregate",
                    "source": {
                        "table": "fact_order_items",
                        "alias": "rfoi",
                    },
                    "joins": [
                        {
                            "table": "fact_orders",
                            "alias": "rfo",
                            "join_type": "inner",
                            "conditions": [
                                {
                                    "left": "rfoi.order_id",
                                    "right": "rfo.order_id",
                                },
                            ],
                        },
                        {
                            "table": "fact_refunds",
                            "alias": "rfr",
                            "join_type": "left",
                            "conditions": [
                                {
                                    "left": "rfoi.order_item_id",
                                    "right": "rfr.order_item_id",
                                },
                                {
                                    "left": "rfoi.order_id",
                                    "right": "rfr.order_id",
                                },
                            ],
                        },
                    ],
                    "filters": [
                        "rfo.paid_at IS NOT NULL",
                        (
                            "CAST(rfo.paid_at AS DATE) BETWEEN "
                            ":analysis_start_date AND :analysis_end_date"
                        ),
                    ],
                    "group_by": [
                        "rfoi.order_item_id",
                        "rfoi.order_id",
                        "rfoi.item_paid_amount",
                        "rfo.customer_id",
                        "rfo.paid_at",
                    ],
                    "outputs": [
                        {
                            "field": "order_item_id",
                            "expression": "rfoi.order_item_id",
                        },
                        {
                            "field": "order_id",
                            "expression": "rfoi.order_id",
                        },
                        {
                            "field": "customer_id",
                            "expression": "rfo.customer_id",
                        },
                        {
                            "field": "paid_date",
                            "expression": "CAST(rfo.paid_at AS DATE)",
                        },
                        {
                            "field": "item_effective_amount",
                            "expression": (
                                "rfoi.item_paid_amount - COALESCE("
                                "SUM(rfr.refund_amount) FILTER "
                                "(WHERE rfr.refund_status = 'completed'), "
                                "0)"
                            ),
                        },
                    ],
                    "hidden_control_fields": [],
                },
                {
                    "stage_id": "report_order_effective",
                    "stage_type": "aggregate",
                    "source": {
                        "stage_id": "report_item_effective",
                        "alias": "rie",
                    },
                    "group_by": [
                        "rie.customer_id",
                        "rie.order_id",
                        "rie.paid_date",
                    ],
                    "having": [
                        "SUM(rie.item_effective_amount) > 0",
                    ],
                    "outputs": [
                        {
                            "field": "customer_id",
                            "expression": "rie.customer_id",
                        },
                        {
                            "field": "order_id",
                            "expression": "rie.order_id",
                        },
                        {
                            "field": "paid_date",
                            "expression": "rie.paid_date",
                        },
                        {
                            "field": "order_effective_amount",
                            "expression": (
                                "SUM(rie.item_effective_amount)"
                            ),
                        },
                    ],
                    "hidden_control_fields": [],
                },
                {
                    "stage_id": "report_customer",
                    "stage_type": "aggregate",
                    "source": {
                        "stage_id": "report_order_effective",
                        "alias": "roe",
                    },
                    "group_by": [
                        "roe.customer_id",
                    ],
                    "outputs": [
                        {
                            "field": "customer_id",
                            "expression": "roe.customer_id",
                        },
                        {
                            "field": "report_effective_amount",
                            "expression": (
                                "SUM(roe.order_effective_amount)"
                            ),
                        },
                    ],
                    "hidden_control_fields": [],
                },
                {
                    "stage_id": "final",
                    "stage_type": "aggregate",
                    "source": {
                        "stage_id": "base_customer",
                        "alias": "bc",
                    },
                    "joins": [
                        {
                            "stage_id": "report_customer",
                            "alias": "rc",
                            "join_type": "left",
                            "conditions": [
                                {
                                    "left": "bc.customer_id",
                                    "right": "rc.customer_id",
                                },
                            ],
                        },
                    ],
                    "outputs": [
                        {
                            "field": metric,
                            "expression": spec.metric_expression,
                        },
                    ],
                    "hidden_control_fields": [
                        {
                            "field": "__group_size",
                            "expression": spec.group_size_expression,
                            "semantics": spec.group_size_semantics,
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
                    "target_id": "r12_base_source",
                    "source_table": "fact_order_items",
                    "table_aliases": [
                        {
                            "table_name": "fact_order_items",
                            "alias": "bfoi",
                        },
                        {
                            "table_name": "fact_orders",
                            "alias": "bfo",
                        },
                    ],
                },
                {
                    "target_id": "r12_report_source",
                    "source_table": "fact_order_items",
                    "table_aliases": [
                        {
                            "table_name": "fact_order_items",
                            "alias": "rfoi",
                        },
                        {
                            "table_name": "fact_orders",
                            "alias": "rfo",
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
                        "fact_orders.customer_id",
                        "fact_orders.paid_at",
                        "fact_order_items.item_paid_amount",
                        "fact_refunds.refund_amount",
                        "fact_refunds.refund_status",
                    ],
                    "category": spec.result_category,
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

    return QueryPlanV2.model_validate(payload)


def build_r12_cohort_metric_family_v2(
) -> tuple[QueryPlanV2, ...]:
    return tuple(
        _build_r12_plan_v2(spec)
        for spec in _R12_METRIC_SPECS
    )


if __name__ == "__main__":
    plans = build_r12_cohort_metric_family_v2()

    print("R12 Cohort Query Plan V2")
    print(f"Plans: {len(plans)}")

    for plan in plans:
        print(
            f"- {plan.name} | "
            f"metric={plan.metric} | "
            f"grain={plan.result_grain}"
        )
