from enum import Enum
from pathlib import Path

import yaml

from app.semantic_layer.brand_new_customer_query_plan_v2 import (
    build_brand_paid_new_customer_count_overall_plan,
)
from app.semantic_layer.cac_query_plan_v2 import (
    build_cac_channel_plan,
)
from app.semantic_layer.channel_new_customer_query_plan_v2 import (
    build_channel_paid_new_customer_count_channel_plan,
)
from app.semantic_layer.composite_query_plan_v2_builder import (
    build_gmv_channel_region_plan,
)
from app.semantic_layer.member_query_plan_v2 import (
    build_member_gmv_share_overall_plan,
)
from app.semantic_layer.query_plan_v2_models import (
    QueryLogic,
    QueryPlanCatalogV2,
    ScopeMode,
    StagedQueryLogic,
)
from app.semantic_layer.refund_query_plan_v2 import (
    build_refund_rate_overall_plan,
)
from app.semantic_layer.repeat_query_plan_v2_family import (
    build_repeat_metric_family,
)
from app.semantic_layer.roi_query_plan_v2 import (
    build_roi_channel_plan,
)
from app.semantic_layer.simple_query_plan_v2_builder import (
    build_simple_query_plan_catalog,
)


QUERY_PLAN_VERSION = "beauty_bi_query_plan_v2_0"
DATASET_NAME = "beauty_bi_v2"
METADATA_VERSION = "beauty_bi_metadata_v2_0"
TARGET_SCHEMA = "beauty_bi_v2"
CATALOG_STATUS = "draft"


def _normalize_for_yaml(value):
    """
    Convert immutable contract containers into deterministic YAML-safe data.

    Sets / frozensets are sorted so repeated generation does not create
    meaningless Git diffs. Tuple/list order remains contract-significant.
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


def build_query_plan_v2_catalog() -> QueryPlanCatalogV2:
    """
    Build the complete Day73 V2 static Query Plan catalog.

    Families:
    - 39 Simple Query Plans
    - 3 Repeat Staged Query Plans
    - 1 Member GMV Share Query Plan
    - 1 Refund Rate Query Plan
    - 1 ROI Query Plan
    - 1 CAC Query Plan
    - 1 Brand Paid New Customer Query Plan
    - 1 Channel Paid New Customer Query Plan
    - 1 GMV Channel × Region Composite Query Plan

    Total:
    - 49 plans
    - 19 metrics
    - 41 QueryLogic
    - 8 StagedQueryLogic

    Important:
    Catalog inclusion means the business/query contract is defined.
    It does NOT mean every plan is executable under every AccessContext.
    Governance remains responsible for fail-closed decisions.
    """
    simple_catalog = (
        build_simple_query_plan_catalog()
    )

    repeat_plans = (
        build_repeat_metric_family()
    )

    member_plan = (
        build_member_gmv_share_overall_plan()
    )

    refund_plan = (
        build_refund_rate_overall_plan()
    )

    roi_plan = (
        build_roi_channel_plan()
    )

    cac_plan = (
        build_cac_channel_plan()
    )

    brand_new_plan = (
        build_brand_paid_new_customer_count_overall_plan()
    )

    channel_new_plan = (
        build_channel_paid_new_customer_count_channel_plan()
    )

    composite_gmv_plan = (
        build_gmv_channel_region_plan()
    )

    all_plans = (
        tuple(simple_catalog.query_plans)
        + tuple(repeat_plans)
        + (
            member_plan,
            refund_plan,
            roi_plan,
            cac_plan,
            brand_new_plan,
            channel_new_plan,
            composite_gmv_plan,
        )
    )

    payload = {
        "query_plan_version": QUERY_PLAN_VERSION,
        "dataset_name": DATASET_NAME,
        "metadata_version": METADATA_VERSION,
        "target_schema": TARGET_SCHEMA,
        "status": CATALOG_STATUS,
        "query_plans": [
            plan.model_dump(
                mode="python"
            )
            for plan in all_plans
        ],
    }

    return QueryPlanCatalogV2.model_validate(
        payload
    )


def write_query_plan_v2_catalog(
    output_path: Path,
) -> QueryPlanCatalogV2:
    """
    Write the complete static V2 Query Plan catalog.

    This is the sole production writer for:
    metadata/beauty_bi_v2/query_plans.yaml
    """
    catalog = build_query_plan_v2_catalog()

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
    output_path = project_query_plan_v2_path()

    catalog = write_query_plan_v2_catalog(
        output_path
    )

    query_logic_count = sum(
        isinstance(
            plan.query_logic,
            QueryLogic,
        )
        for plan in catalog.query_plans
    )

    staged_logic_count = sum(
        isinstance(
            plan.query_logic,
            StagedQueryLogic,
        )
        for plan in catalog.query_plans
    )

    global_history_count = sum(
        plan.scope_contract.scope_mode
        == ScopeMode.GLOBAL_HISTORY_REQUIRED
        for plan in catalog.query_plans
    )

    print("Query Plan V2 Catalog Builder")
    print(f"Generated: {output_path}")
    print(f"Plans: {len(catalog.query_plans)}")
    print(
        "Metrics:",
        len(
            {
                plan.metric
                for plan in catalog.query_plans
            }
        ),
    )
    print(f"QueryLogic Plans: {query_logic_count}")
    print(
        f"StagedQueryLogic Plans: {staged_logic_count}"
    )
    print(
        f"Global History Plans: {global_history_count}"
    )
