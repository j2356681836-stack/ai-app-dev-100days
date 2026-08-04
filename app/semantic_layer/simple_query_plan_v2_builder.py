from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Iterable

import yaml

from app.semantic_layer.query_plan_v2_models import (
    QueryPlanCatalogV2,
)


SUPPORTED_GRAINS = (
    "overall",
    "channel",
    "region",
    "category",
)


@dataclass(frozen=True)
class SimpleMetricSpec:
    metric: str
    chinese_name: str
    source_kind: str
    metric_expression: str
    source_columns: tuple[str, ...]
    result_category: str = "ordinary"
    supported_grains: tuple[str, ...] = SUPPORTED_GRAINS

    def __post_init__(self) -> None:
        if self.source_kind not in {"orders", "items"}:
            raise ValueError(
                "source_kind must be 'orders' or 'items'."
            )

        unsupported = (
            set(self.supported_grains)
            - set(SUPPORTED_GRAINS)
        )

        if unsupported:
            raise ValueError(
                "Unsupported result grains: "
                f"{sorted(unsupported)}"
            )

        if not self.metric_expression.strip():
            raise ValueError(
                "metric_expression cannot be empty."
            )

        if self.result_category not in {
            "ordinary",
            "business_confidential",
        }:
            raise ValueError(
                "Unsupported result_category: "
                f"{self.result_category}"
            )


SIMPLE_METRIC_SPECS: tuple[SimpleMetricSpec, ...] = (
    SimpleMetricSpec(
        metric="gmv",
        chinese_name="GMV",
        source_kind="items",
        metric_expression=(
            "SUM(foi.item_paid_amount)"
        ),
        source_columns=(
            "fact_order_items.item_paid_amount",
        ),
    ),
    SimpleMetricSpec(
        metric="gross_margin",
        chinese_name="毛利额",
        source_kind="items",
        metric_expression=(
            "SUM("
            "foi.item_paid_amount "
            "- foi.item_cost_amount"
            ")"
        ),
        source_columns=(
            "fact_order_items.item_paid_amount",
            "fact_order_items.item_cost_amount",
        ),
        result_category="business_confidential",
    ),
    SimpleMetricSpec(
        metric="gross_margin_rate",
        chinese_name="毛利率",
        source_kind="items",
        metric_expression=(
            "SUM("
            "foi.item_paid_amount "
            "- foi.item_cost_amount"
            ") "
            "/ NULLIF("
            "SUM(foi.item_paid_amount), 0"
            ")"
        ),
        source_columns=(
            "fact_order_items.item_paid_amount",
            "fact_order_items.item_cost_amount",
        ),
        result_category="business_confidential",
    ),
    SimpleMetricSpec(
        metric="buyer_count",
        chinese_name="购买人数",
        source_kind="orders",
        metric_expression=(
            "COUNT(DISTINCT fo.customer_id)"
        ),
        source_columns=(
            "fact_orders.customer_id",
        ),
    ),
    SimpleMetricSpec(
        metric="order_count",
        chinese_name="交易量",
        source_kind="orders",
        metric_expression=(
            "COUNT(DISTINCT fo.order_id)"
        ),
        source_columns=(
            "fact_orders.order_id",
        ),
    ),
    SimpleMetricSpec(
        metric="units_sold",
        chinese_name="交易件数",
        source_kind="items",
        metric_expression=(
            "SUM(foi.quantity)"
        ),
        source_columns=(
            "fact_order_items.quantity",
        ),
    ),
    SimpleMetricSpec(
        metric="spending_per_buyer",
        chinese_name="人均消费金额",
        source_kind="items",
        metric_expression=(
            "SUM(foi.item_paid_amount) "
            "/ NULLIF("
            "COUNT(DISTINCT fo.customer_id), 0"
            ")"
        ),
        source_columns=(
            "fact_order_items.item_paid_amount",
            "fact_orders.customer_id",
        ),
    ),
    SimpleMetricSpec(
        metric="ipt",
        chinese_name="IPT",
        source_kind="items",
        metric_expression=(
            "SUM(foi.quantity) "
            "/ NULLIF("
            "COUNT(DISTINCT fo.order_id), 0"
            ")"
        ),
        source_columns=(
            "fact_order_items.quantity",
            "fact_orders.order_id",
        ),
    ),
    SimpleMetricSpec(
        metric="aus",
        chinese_name="AUS",
        source_kind="items",
        metric_expression=(
            "SUM(foi.item_paid_amount) "
            "/ NULLIF("
            "COUNT(DISTINCT fo.order_id), 0"
            ")"
        ),
        source_columns=(
            "fact_order_items.item_paid_amount",
            "fact_orders.order_id",
        ),
        supported_grains=(
            "overall",
            "channel",
            "region",
        ),
    ),
    SimpleMetricSpec(
        metric="purchase_frequency",
        chinese_name="FREQ",
        source_kind="orders",
        metric_expression=(
            "COUNT(DISTINCT fo.order_id) "
            "/ NULLIF("
            "COUNT(DISTINCT fo.customer_id), 0"
            ")"
        ),
        source_columns=(
            "fact_orders.order_id",
            "fact_orders.customer_id",
        ),
    ),
)


def _dimension_contract(
    grain: str,
) -> dict:
    if grain == "overall":
        return {
            "result_grain": "overall",
            "output_field": None,
            "output_column": None,
            "dimension_table": None,
            "dimension_alias": None,
            "group_by": [],
        }

    if grain == "channel":
        return {
            "result_grain": "channel",
            "output_field": "channel_name",
            "output_column": "channel_name",
            "dimension_table": "dim_channel",
            "dimension_alias": "dc",
            "group_by": [
                "dc.channel_id",
                "dc.channel_name",
            ],
        }

    if grain == "region":
        return {
            "result_grain": "region",
            "output_field": "region_name",
            "output_column": "region_name",
            "dimension_table": "dim_region",
            "dimension_alias": "dr",
            "group_by": [
                "dr.region_id",
                "dr.region_name",
            ],
        }

    if grain == "category":
        return {
            "result_grain": "category",
            "output_field": "category",
            "output_column": "category",
            "dimension_table": "dim_product",
            "dimension_alias": "dp",
            "group_by": [
                "dp.category",
            ],
        }

    raise ValueError(
        f"Unsupported result grain: {grain}"
    )


def _base_query_contract(
    spec: SimpleMetricSpec,
    grain: str,
) -> dict:
    category_requires_items = (
        grain == "category"
    )

    use_items = (
        spec.source_kind == "items"
        or category_requires_items
    )

    if use_items:
        base_source = {
            "table": "fact_order_items",
            "alias": "foi",
        }

        joins = [
            {
                "table": "fact_orders",
                "alias": "fo",
                "join_type": "inner",
                "conditions": [
                    {
                        "left": "foi.order_id",
                        "right": "fo.order_id",
                    }
                ],
            }
        ]

        required_tables = {
            "fact_order_items",
            "fact_orders",
            "dim_region",
            "dim_channel",
        }

        required_columns = {
            "fact_order_items.order_id",
            "fact_orders.order_id",
            "fact_orders.customer_id",
            "fact_orders.channel_id",
            "fact_orders.shipping_region_id",
            "fact_orders.paid_at",
            "dim_region.region_id",
            "dim_region.region_code",
            "dim_channel.channel_id",
            "dim_channel.channel_code",
        }

        scope_source_table = "fact_order_items"
        scope_aliases = [
            {
                "table_name": "fact_order_items",
                "alias": "foi",
            },
            {
                "table_name": "fact_orders",
                "alias": "fo",
            },
        ]
    else:
        base_source = {
            "table": "fact_orders",
            "alias": "fo",
        }

        joins = []

        required_tables = {
            "fact_orders",
            "dim_region",
            "dim_channel",
        }

        required_columns = {
            # customer_id is required by the hidden __group_size
            # control field for every simple metric plan.
            #
            # order_id is intentionally not a universal orders-source
            # dependency. Metrics that actually use it, such as
            # order_count and purchase_frequency, add it through
            # spec.source_columns below.
            "fact_orders.customer_id",
            "fact_orders.channel_id",
            "fact_orders.shipping_region_id",
            "fact_orders.paid_at",
            "dim_region.region_id",
            "dim_region.region_code",
            "dim_channel.channel_id",
            "dim_channel.channel_code",
        }

        scope_source_table = "fact_orders"
        scope_aliases = [
            {
                "table_name": "fact_orders",
                "alias": "fo",
            }
        ]

    required_columns.update(
        spec.source_columns
    )

    return {
        "base_source": base_source,
        "joins": joins,
        "required_tables": required_tables,
        "required_columns": required_columns,
        "scope_source_table": scope_source_table,
        "scope_aliases": scope_aliases,
    }


def _add_dimension_join(
    *,
    grain: str,
    query: dict,
    dimension: dict,
) -> None:
    if grain == "overall":
        return

    if grain == "channel":
        query["joins"].append(
            {
                "table": "dim_channel",
                "alias": "dc",
                "join_type": "inner",
                "conditions": [
                    {
                        "left": "fo.channel_id",
                        "right": "dc.channel_id",
                    }
                ],
            }
        )

        query["required_columns"].add(
            "dim_channel.channel_name"
        )
        return

    if grain == "region":
        query["joins"].append(
            {
                "table": "dim_region",
                "alias": "dr",
                "join_type": "inner",
                "conditions": [
                    {
                        "left": "fo.shipping_region_id",
                        "right": "dr.region_id",
                    }
                ],
            }
        )

        query["required_columns"].add(
            "dim_region.region_name"
        )
        return

    if grain == "category":
        query["joins"].append(
            {
                "table": "dim_product",
                "alias": "dp",
                "join_type": "inner",
                "conditions": [
                    {
                        "left": "foi.product_id",
                        "right": "dp.product_id",
                    }
                ],
            }
        )

        query["required_tables"].add(
            "dim_product"
        )

        query["required_columns"].update(
            {
                "fact_order_items.product_id",
                "dim_product.product_id",
                "dim_product.category",
            }
        )
        return

    raise ValueError(
        f"Unsupported result grain: {grain}"
    )


def _metric_expression(
    spec: SimpleMetricSpec,
    grain: str,
) -> str:
    """
    首批简单指标的 Grain-specific 语义。

    category 下 buyer/order/frequency 必须对订单或客户去重，
    不能把 order_item 行数当成订单数。
    """
    if grain != "category":
        return spec.metric_expression

    if spec.metric == "buyer_count":
        return "COUNT(DISTINCT fo.customer_id)"

    if spec.metric == "order_count":
        return "COUNT(DISTINCT fo.order_id)"

    if spec.metric == "purchase_frequency":
        return (
            "COUNT(DISTINCT fo.order_id) "
            "/ NULLIF("
            "COUNT(DISTINCT fo.customer_id), 0"
            ")"
        )

    if spec.metric == "spending_per_buyer":
        return (
            "SUM(foi.item_paid_amount) "
            "/ NULLIF("
            "COUNT(DISTINCT fo.customer_id), 0"
            ")"
        )

    if spec.metric == "ipt":
        return (
            "SUM(foi.quantity) "
            "/ NULLIF("
            "COUNT(DISTINCT fo.order_id), 0"
            ")"
        )

    return spec.metric_expression


def build_simple_query_plan(
    spec: SimpleMetricSpec,
    grain: str,
) -> dict:
    if grain not in spec.supported_grains:
        raise ValueError(
            f"{spec.metric} does not support grain={grain}"
        )

    dimension = _dimension_contract(grain)
    query = _base_query_contract(
        spec,
        grain,
    )

    _add_dimension_join(
        grain=grain,
        query=query,
        dimension=dimension,
    )

    metric_expression = _metric_expression(
        spec,
        grain,
    )

    outputs = []

    field_bindings = []

    if dimension["output_field"] is not None:
        outputs.append(
            {
                "field": dimension["output_field"],
                "expression": (
                    f"{dimension['dimension_alias']}."
                    f"{dimension['output_column']}"
                ),
            }
        )

        field_bindings.append(
            {
                "output_field": dimension["output_field"],
                "source_columns": [
                    (
                        f"{dimension['dimension_table']}."
                        f"{dimension['output_column']}"
                    )
                ],
                "category": "ordinary",
            }
        )

    outputs.append(
        {
            "field": spec.metric,
            "expression": metric_expression,
        }
    )

    field_bindings.append(
        {
            "output_field": spec.metric,
            "source_columns": list(
                spec.source_columns
            ),
            "category": spec.result_category,
        }
    )

    plan_name = (
        f"{spec.metric}_{grain}_v2"
    )

    grain_label = {
        "overall": "整体",
        "channel": "渠道",
        "region": "地区",
        "category": "品类",
    }[grain]

    return {
        "name": plan_name,
        "metric": spec.metric,
        "chinese_name": (
            f"{grain_label}{spec.chinese_name}"
        ),
        "query_type": "aggregate_metric",
        "result_grain": grain,
        "description": (
            f"按 {grain_label} Grain 计算 "
            f"{spec.chinese_name}。"
        ),
        "semantic_contract": {
            "date_attribution": (
                "fact_orders.paid_at"
            ),
            "metric_expression": (
                metric_expression
            ),
            "base_filters": [
                "fact_orders.paid_at IS NOT NULL"
            ],
        },
        "query_logic": {
            "base_source": (
                query["base_source"]
            ),
            "joins": query["joins"],
            "group_by": (
                dimension["group_by"]
            ),
            "outputs": outputs,
            "hidden_control_fields": [
                {
                    "field": "__group_size",
                    "expression": (
                        "COUNT(DISTINCT "
                        "fo.customer_id)"
                    ),
                    "semantics": (
                        "distinct_buyers_per_result_group"
                    ),
                }
            ],
        },
        "resource_contract": {
            "required_tables": sorted(
                query["required_tables"]
            ),
            "required_columns": sorted(
                query["required_columns"]
            ),
        },
        "scope_contract": {
            "scope_mode": "predicate_safe",
            "source_tables": [
                query["scope_source_table"]
            ],
            "required_dimensions": [
                "region",
                "channel",
            ],
            "targets": [
                {
                    "target_id": (
                        f"{plan_name}_source"
                    ),
                    "source_table": (
                        query["scope_source_table"]
                    ),
                    "table_aliases": (
                        query["scope_aliases"]
                    ),
                }
            ],
        },
        "result_contract": {
            "result_shape": "aggregate",
            "field_bindings": field_bindings,
            "minimum_group_size_required": True,
            "group_size_field": "__group_size",
        },
        "default_sort": {
            "field": spec.metric,
            "direction": "desc",
        },
    }


def build_simple_query_plan_catalog(
    specs: Iterable[SimpleMetricSpec] = (
        SIMPLE_METRIC_SPECS
    ),
) -> QueryPlanCatalogV2:
    plans = []

    for spec in specs:
        for grain in spec.supported_grains:
            plans.append(
                build_simple_query_plan(
                    spec,
                    grain,
                )
            )

    payload = {
        "query_plan_version": (
            "beauty_bi_query_plan_v2_0"
        ),
        "dataset_name": "beauty_bi_v2",
        "metadata_version": (
            "beauty_bi_metadata_v2_0"
        ),
        "target_schema": "beauty_bi_v2",
        "status": "draft",
        "query_plans": plans,
    }

    return QueryPlanCatalogV2.model_validate(
        payload
    )



def _normalize_for_yaml(value):
    """
    Convert immutable Pydantic contract containers into a deterministic
    YAML-safe structure.

    Sets / frozensets are sorted because their iteration order is not part
    of the business contract and must not create noisy Git diffs.
    Tuples preserve their declared contract order.
    """
    if isinstance(value, Enum):
        return value.value

    if isinstance(value, dict):
        return {
            key: _normalize_for_yaml(item)
            for key, item in value.items()
        }

    if isinstance(value, (set, frozenset)):
        normalized = [
            _normalize_for_yaml(item)
            for item in value
        ]

        return sorted(
            normalized,
            key=lambda item: repr(item),
        )

    if isinstance(value, tuple):
        return [
            _normalize_for_yaml(item)
            for item in value
        ]

    if isinstance(value, list):
        return [
            _normalize_for_yaml(item)
            for item in value
        ]

    return value


def write_simple_query_plan_catalog(
    output_path: Path,
) -> QueryPlanCatalogV2:
    catalog = (
        build_simple_query_plan_catalog()
    )

    payload = _normalize_for_yaml(
        catalog.model_dump(
            mode="python"
        )
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path.write_text(
        yaml.safe_dump(
            payload,
            allow_unicode=True,
            sort_keys=False,
            width=1000,
        ),
        encoding="utf-8",
    )

    return catalog


def project_query_plan_v2_path() -> Path:
    project_root = (
        Path(__file__).resolve().parents[2]
    )

    return (
        project_root
        / "metadata"
        / "beauty_bi_v2"
        / "query_plans.yaml"
    )


if __name__ == "__main__":
    catalog = build_simple_query_plan_catalog()

    print("Simple Query Plan V2 Family Builder")
    print(f"Plans: {len(catalog.query_plans)}")
    print(
        "Family-only builder: production query_plans.yaml "
        "is NOT written."
    )
    print(
        "Use: python -m "
        "app.semantic_layer.query_plan_v2_catalog_builder"
    )
