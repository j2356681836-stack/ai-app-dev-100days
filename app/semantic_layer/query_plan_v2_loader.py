from functools import lru_cache
from pathlib import Path

import yaml

from app.semantic_layer.query_plan_v2_models import (
    QueryPlanCatalogV2,
    QueryPlanV2,
)


def _query_plan_v2_path() -> Path:
    """
    返回 Dataset V2 Query Plan 元数据文件路径。

    V2 与 V1 Metadata 物理隔离，避免修改 Day60 Stable Baseline。
    """
    project_root = Path(__file__).resolve().parents[2]

    return (
        project_root
        / "metadata"
        / "beauty_bi_v2"
        / "query_plans.yaml"
    )


@lru_cache(maxsize=1)
def load_query_plan_v2_catalog() -> QueryPlanCatalogV2:
    """
    加载并验证 Dataset V2 Query Plan Catalog。

    约束：
    - 只读取 metadata/beauty_bi_v2/query_plans.yaml；
    - 不回退到 V1 metadata/query_plans.yaml；
    - YAML 解析错误直接暴露；
    - Pydantic Contract 校验错误直接暴露；
    - 成功后返回不可变 QueryPlanCatalogV2；
    - 进程内只解析一次，避免每次 lookup 重读并重验整份 Catalog。
    """
    query_plans_path = _query_plan_v2_path()

    with query_plans_path.open(
        "r",
        encoding="utf-8",
    ) as f:
        data = yaml.safe_load(f)

    return QueryPlanCatalogV2.model_validate(data)



def clear_query_plan_v2_catalog_cache() -> None:
    """
    显式清理进程内 Query Plan Catalog 缓存。

    生产运行中 metadata/beauty_bi_v2/query_plans.yaml 应视为
    server-owned immutable contract；正常请求不需要清理缓存。

    仅在开发 / 测试流程中重新生成 query_plans.yaml 后，
    如同一 Python 进程仍需读取新版本，才调用本函数。
    """
    load_query_plan_v2_catalog.cache_clear()

def get_query_plan_v2_by_name(
    plan_name: str,
) -> QueryPlanV2 | None:
    """
    根据 Query Plan 技术名查找单个 V2 Plan。
    """
    catalog = load_query_plan_v2_catalog()

    for plan in catalog.query_plans:
        if plan.name == plan_name:
            return plan

    return None


def get_query_plans_v2_by_metric(
    metric_name: str,
) -> tuple[QueryPlanV2, ...]:
    """
    根据 metric name 返回全部 V2 Query Plan。

    与 V1 的关键区别：
    - V1 假设一个 metric 对应一个 Query Plan；
    - V2 允许同一 metric 对应多个 result grain /
      governed query shape。

    例如：
    gmv
    ├─ gmv_channel_v2
    ├─ gmv_region_v2
    └─ gmv_category_v2

    找不到时返回空 tuple，而不是 None。
    """
    catalog = load_query_plan_v2_catalog()

    return tuple(
        plan
        for plan in catalog.query_plans
        if plan.metric == metric_name
    )


def has_query_plan_v2(metric_name: str) -> bool:
    """
    判断某个 metric 是否至少存在一个 V2 Query Plan。
    """
    return bool(
        get_query_plans_v2_by_metric(metric_name)
    )


if __name__ == "__main__":
    catalog = load_query_plan_v2_catalog()

    print("Query Plan V2 Catalog")
    print(f"Version: {catalog.query_plan_version}")
    print(f"Dataset: {catalog.dataset_name}")
    print(f"Plans: {len(catalog.query_plans)}")

    for plan in catalog.query_plans:
        print(
            "-",
            plan.name,
            "| metric:",
            plan.metric,
            "| grain:",
            plan.result_grain,
        )
