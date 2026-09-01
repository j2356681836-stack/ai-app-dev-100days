from __future__ import annotations

from app.semantic_layer.query_plan_v2_models import (
    QueryPlanV2,
)


SUPPORTED_REFUND_RATE_GRAINS_V2 = (
    "overall",
    "channel",
    "region",
    "category",
)


def _refund_dimension_contract_v2(
    grain: str,
) -> dict:
    if grain == "overall":
        return {
            "grain_label": "整体",
            "stage1_group_by": (),
            "stage1_outputs": (),
            "final_joins": (),
            "final_group_by": (),
            "final_dimension_outputs": (),
            "dimension_field_bindings": (),
            "required_tables": (),
            "required_columns": (),
        }

    if grain == "channel":
        return {
            "grain_label": "渠道",
            "stage1_group_by": (
                "fo.channel_id",
            ),
            "stage1_outputs": (
                {
                    "field": "channel_id",
                    "expression": "fo.channel_id",
                },
            ),
            "final_joins": (
                {
                    "table": "dim_channel",
                    "alias": "dc",
                    "join_type": "inner",
                    "conditions": [
                        {
                            "left": "irs.channel_id",
                            "right": "dc.channel_id",
                        },
                    ],
                },
            ),
            "final_group_by": (
                "dc.channel_id",
                "dc.channel_name",
            ),
            "final_dimension_outputs": (
                {
                    "field": "channel_name",
                    "expression": "dc.channel_name",
                },
            ),
            "dimension_field_bindings": (
                {
                    "output_field": "channel_name",
                    "source_columns": [
                        "dim_channel.channel_name",
                    ],
                    "category": "ordinary",
                },
            ),
            "required_tables": (
                "dim_channel",
            ),
            "required_columns": (
                "dim_channel.channel_id",
                "dim_channel.channel_name",
            ),
        }

    if grain == "region":
        return {
            "grain_label": "地区",
            "stage1_group_by": (
                "fo.shipping_region_id",
            ),
            "stage1_outputs": (
                {
                    "field": "region_id",
                    "expression": "fo.shipping_region_id",
                },
            ),
            "final_joins": (
                {
                    "table": "dim_region",
                    "alias": "dr",
                    "join_type": "inner",
                    "conditions": [
                        {
                            "left": "irs.region_id",
                            "right": "dr.region_id",
                        },
                    ],
                },
            ),
            "final_group_by": (
                "dr.region_id",
                "dr.region_name",
            ),
            "final_dimension_outputs": (
                {
                    "field": "region_name",
                    "expression": "dr.region_name",
                },
            ),
            "dimension_field_bindings": (
                {
                    "output_field": "region_name",
                    "source_columns": [
                        "dim_region.region_name",
                    ],
                    "category": "ordinary",
                },
            ),
            "required_tables": (
                "dim_region",
            ),
            "required_columns": (
                "dim_region.region_id",
                "dim_region.region_name",
            ),
        }

    if grain == "category":
        return {
            "grain_label": "品类",
            "stage1_group_by": (
                "foi.product_id",
            ),
            "stage1_outputs": (
                {
                    "field": "product_id",
                    "expression": "foi.product_id",
                },
            ),
            "final_joins": (
                {
                    "table": "dim_product",
                    "alias": "dp",
                    "join_type": "inner",
                    "conditions": [
                        {
                            "left": "irs.product_id",
                            "right": "dp.product_id",
                        },
                    ],
                },
            ),
            "final_group_by": (
                "dp.category",
            ),
            "final_dimension_outputs": (
                {
                    "field": "category",
                    "expression": "dp.category",
                },
            ),
            "dimension_field_bindings": (
                {
                    "output_field": "category",
                    "source_columns": [
                        "dim_product.category",
                    ],
                    "category": "ordinary",
                },
            ),
            "required_tables": (
                "dim_product",
            ),
            "required_columns": (
                "fact_order_items.product_id",
                "dim_product.product_id",
                "dim_product.category",
            ),
        }

    raise ValueError(
        f"Unsupported refund-rate grain: {grain}"
    )


def build_refund_rate_plan(
    grain: str,
) -> QueryPlanV2:
    """
    Build one V2 refund-rate Query Plan.

    Shared semantics across all grains:
    - sales-cohort attribution uses fact_orders.paid_at;
    - denominator is original paid item GMV;
    - only completed refund events contribute to numerator;
    - refund events are pre-aggregated to one row per order_item before
      any dimension aggregation, so multiple refund events cannot fan
      out the sales denominator;
    - Region / Channel governance predicates are still placed on the
      sales-item stage before the final dimension projection;
    - refund_rate is an aggregated business-confidential metric:
      it may be released only with explicit aggregated-metric permission
      plus minimum-group-size proof.
    """
    if grain not in SUPPORTED_REFUND_RATE_GRAINS_V2:
        raise ValueError(
            f"Unsupported refund-rate grain: {grain}"
        )

    dimension = _refund_dimension_contract_v2(
        grain
    )

    first_stage_group_by = [
        "foi.order_item_id",
        "foi.item_paid_amount",
        "fo.customer_id",
        *dimension["stage1_group_by"],
    ]

    first_stage_outputs = [
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
        *dimension["stage1_outputs"],
        {
            "field": "completed_refund_amount",
            "expression": (
                "COALESCE("
                "SUM(fr.refund_amount) FILTER "
                "(WHERE fr.refund_status = 'completed'), "
                "0)"
            ),
        },
    ]

    final_outputs = [
        *dimension["final_dimension_outputs"],
        {
            "field": "refund_rate",
            "expression": (
                "SUM(irs.completed_refund_amount) "
                "/ NULLIF("
                "SUM(irs.item_paid_amount), 0)"
            ),
        },
    ]

    required_tables = {
        "fact_order_items",
        "fact_orders",
        "fact_refunds",
        # Region / Channel are always required by governed Row Scope.
        "dim_region",
        "dim_channel",
        *dimension["required_tables"],
    }

    required_columns = {
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
        *dimension["required_columns"],
    }

    plan_name = f"refund_rate_{grain}_v2"

    field_bindings = [
        *dimension["dimension_field_bindings"],
        {
            "output_field": "refund_rate",
            "source_columns": [
                "fact_order_items.item_paid_amount",
                "fact_refunds.refund_amount",
                "fact_refunds.refund_status",
            ],
            "category": (
                "aggregated_business_confidential"
            ),
        },
    ]

    payload = {
        "name": plan_name,
        "metric": "refund_rate",
        "chinese_name": (
            f"{dimension['grain_label']}退款率"
        ),
        "query_type": "staged_aggregate_metric",
        "result_grain": grain,
        "description": (
            f"按{dimension['grain_label']}计算指定销售分析范围内，"
            "原订单支付 cohort 最终已完成退款金额占对应原始支付 "
            "GMV 的比例。多次部分退款先按 order_item 汇总，"
            "避免重复销售分母。"
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
                    "group_by": first_stage_group_by,
                    "outputs": first_stage_outputs,
                    "hidden_control_fields": [],
                },
                {
                    "stage_id": "final",
                    "stage_type": "aggregate",
                    "source": {
                        "stage_id": "item_refund_summary",
                        "alias": "irs",
                    },
                    "joins": list(
                        dimension["final_joins"]
                    ),
                    "group_by": list(
                        dimension["final_group_by"]
                    ),
                    "outputs": final_outputs,
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
            "required_tables": sorted(
                required_tables
            ),
            "required_columns": sorted(
                required_columns
            ),
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
                        "refund_rate_sales_items"
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
            "field_bindings": field_bindings,
            "minimum_group_size_required": True,
            "group_size_field": "__group_size",
        },
        "default_sort": {
            # Risk / investigation views keep high refund rate first.
            # "best / worst" business interpretation is handled separately
            # by Ranking Answer Delivery and does not depend on this sort.
            "field": "refund_rate",
            "direction": "desc",
        },
    }

    return QueryPlanV2.model_validate(payload)


def build_refund_rate_plan_family(
) -> tuple[QueryPlanV2, ...]:
    return tuple(
        build_refund_rate_plan(grain)
        for grain in SUPPORTED_REFUND_RATE_GRAINS_V2
    )


def build_refund_rate_overall_plan() -> QueryPlanV2:
    """
    Backward-compatible named builder for callers/tests that still import
    the previous overall-only entry point.
    """
    return build_refund_rate_plan(
        "overall"
    )


if __name__ == "__main__":
    plans = build_refund_rate_plan_family()

    print("Refund Rate Query Plan V2 Family")
    print(f"Plans: {len(plans)}")
    for plan in plans:
        print(
            f"- {plan.name}: "
            f"grain={plan.result_grain}"
        )
