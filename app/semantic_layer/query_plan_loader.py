from pathlib import Path
from typing import Any

import yaml


def load_query_plans() -> list[dict[str, Any]]:
    """
    Load query plans from metadata/query_plans.yaml.
    """
    project_root = Path(__file__).resolve().parents[2]
    query_plans_path = project_root / "metadata" / "query_plans.yaml"

    with query_plans_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    return data.get("query_plans", [])


def get_query_plan_by_name(plan_name: str) -> dict[str, Any] | None:
    """
    根据 query plan name 查找 plan。
    例如：roi_channel_v1
    """
    query_plans = load_query_plans()

    for plan in query_plans:
        if plan.get("name") == plan_name:
            return plan

    return None


def get_query_plan_by_metric(metric_name: str) -> dict[str, Any] | None:
    """
    根据 metric name 查找 query plan。
    例如：roi / cac

    当前 V1 假设一个 metric 只对应一个 query plan。
    """
    query_plans = load_query_plans()

    for plan in query_plans:
        if plan.get("metric") == metric_name:
            return plan

    return None


def has_query_plan(metric_name: str) -> bool:
    """
    判断某个 metric 是否存在 query plan。
    """
    return get_query_plan_by_metric(metric_name) is not None


if __name__ == "__main__":
    plans = load_query_plans()

    print("Query Plans:")
    for plan in plans:
        print(
            "-",
            plan.get("name"),
            "| metric:",
            plan.get("metric"),
            "| type:",
            plan.get("query_type"),
        )

    print()
    print("ROI plan:")
    print(get_query_plan_by_metric("roi"))

    print()
    print("CAC plan:")
    print(get_query_plan_by_metric("cac"))