from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import text

from app.db.database import engine
from app.db.governed_database import (
    get_governed_engine,
    load_governed_database_config,
)
from app.db.beauty_bi_v2.startup_readiness_v2 import (
    DatasetPopulationStateV2,
    SchemaReadinessStateV2,
    StartupReadinessReportV2,
    StartupReadinessSnapshotV2,
    classify_startup_readiness_v2,
)


TARGET_SCHEMA = "beauty_bi_v2"

# Day67 起 Dataset V2 P0 Schema 已冻结。
# 这里使用 Formal Acceptance 同一组 16 张 P0 表作为启动合同。
EXPECTED_TABLES = frozenset(
    {
        "bridge_customer_membership",
        "dim_campaign",
        "dim_channel",
        "dim_customer",
        "dim_date",
        "dim_membership_account",
        "dim_product",
        "dim_promotion",
        "dim_region",
        "fact_marketing_spend",
        "fact_membership_channel_binding_history",
        "fact_membership_tier_history",
        "fact_order_items",
        "fact_orders",
        "fact_refunds",
        "fact_reviews",
    }
)


def classify_schema_state_v2(
    *,
    schema_exists: bool,
    actual_tables: set[str],
) -> SchemaReadinessStateV2:
    """
    只判断结构状态，不创建 Schema。

    Fresh environment:
        schema 不存在 → ABSENT

    已冻结结构：
        表集合完全一致 → EXPECTED

    其他情况：
        空 Schema / 缺表 / 多表 → DRIFTED
    """

    if not schema_exists:
        return SchemaReadinessStateV2.ABSENT

    if actual_tables == EXPECTED_TABLES:
        return SchemaReadinessStateV2.EXPECTED

    return SchemaReadinessStateV2.DRIFTED


def classify_dataset_population_v2(
    table_counts: Mapping[str, int],
) -> DatasetPopulationStateV2:
    """
    16 张 P0 表必须形成一致状态：

    全 0       → EMPTY
    全部 > 0   → COMPLETE
    其他       → PARTIAL_OR_DRIFTED

    不把“部分有数据”解释成可以自动继续 Seed。
    """

    if set(table_counts) != EXPECTED_TABLES:
        return DatasetPopulationStateV2.PARTIAL_OR_DRIFTED

    counts = tuple(table_counts.values())

    if all(count == 0 for count in counts):
        return DatasetPopulationStateV2.EMPTY

    if all(count > 0 for count in counts):
        return DatasetPopulationStateV2.COMPLETE

    return DatasetPopulationStateV2.PARTIAL_OR_DRIFTED


def planner_statistics_ready_v2(
    statistics_rows: Sequence[Mapping[str, Any]],
) -> bool:
    """
    Planner Statistics Ready 的最小条件：

    - 16 张表全部出现在 pg_stat_user_tables；
    - 每张表都有 last_analyze 或 last_autoanalyze；
    - n_mod_since_analyze == 0。

    这样可以避免“曾经 ANALYZE 过，但随后 Bulk Seed / 修改后
    statistics 已经陈旧”仍被错误标记为 Ready。
    """

    by_table = {
        str(row["relname"]): row
        for row in statistics_rows
    }

    if set(by_table) != EXPECTED_TABLES:
        return False

    for table_name in EXPECTED_TABLES:
        row = by_table[table_name]

        if (
            row.get("last_analyze") is None
            and row.get("last_autoanalyze") is None
        ):
            return False

        if int(row.get("n_mod_since_analyze") or 0) != 0:
            return False

    return True


def _probe_database_structure() -> tuple[
    bool,
    SchemaReadinessStateV2,
    DatasetPopulationStateV2,
    list[dict[str, Any]],
]:
    """
    使用 Maintenance / Owner Engine 做只读探测。

    返回：
    database_reachable,
    schema_state,
    population_state,
    planner_statistics_rows
    """

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))

            schema_exists = bool(
                connection.execute(
                    text(
                        """
                        SELECT EXISTS (
                            SELECT 1
                            FROM pg_namespace
                            WHERE nspname = :schema
                        )
                        """
                    ),
                    {"schema": TARGET_SCHEMA},
                ).scalar_one()
            )

            if not schema_exists:
                return (
                    True,
                    SchemaReadinessStateV2.ABSENT,
                    DatasetPopulationStateV2.EMPTY,
                    [],
                )

            actual_tables = set(
                connection.execute(
                    text(
                        """
                        SELECT tablename
                        FROM pg_tables
                        WHERE schemaname = :schema
                        ORDER BY tablename
                        """
                    ),
                    {"schema": TARGET_SCHEMA},
                ).scalars()
            )

            schema_state = classify_schema_state_v2(
                schema_exists=True,
                actual_tables=actual_tables,
            )

            if schema_state != SchemaReadinessStateV2.EXPECTED:
                return (
                    True,
                    schema_state,
                    DatasetPopulationStateV2.PARTIAL_OR_DRIFTED,
                    [],
                )

            table_counts: dict[str, int] = {}

            for table_name in sorted(EXPECTED_TABLES):
                # table_name 只来自 server-owned frozen constant。
                table_counts[table_name] = int(
                    connection.execute(
                        text(
                            f'SELECT COUNT(*) '
                            f'FROM "{TARGET_SCHEMA}"."{table_name}"'
                        )
                    ).scalar_one()
                )

            population_state = classify_dataset_population_v2(
                table_counts
            )

            statistics_rows = [
                dict(row)
                for row in connection.execute(
                    text(
                        """
                        SELECT
                            relname,
                            last_analyze,
                            last_autoanalyze,
                            n_mod_since_analyze
                        FROM pg_stat_user_tables
                        WHERE schemaname = :schema
                        ORDER BY relname
                        """
                    ),
                    {"schema": TARGET_SCHEMA},
                ).mappings().all()
            ]

        return (
            True,
            schema_state,
            population_state,
            statistics_rows,
        )

    except Exception:
        # Startup Probe 的公开结果不泄露连接串 / password / raw exception。
        return (
            False,
            SchemaReadinessStateV2.ABSENT,
            DatasetPopulationStateV2.EMPTY,
            [],
        )


def _run_formal_dataset_acceptance() -> bool:
    """
    复用现有 Day66 Formal Acceptance CLI 的 JSON 输出。

    不修改 acceptance_observer.py；
    不把历史 dataset_candidate_eligible 字段当成当前 Promotion Truth。
    这里只消费 business_pattern_acceptance_pass。
    """

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "app.db.beauty_bi_v2.acceptance_observer",
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    if completed.returncode != 0:
        return False

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return False

    return (
        payload.get("mode") == "formal_acceptance"
        and payload.get("target_schema") == TARGET_SCHEMA
        and payload.get("business_pattern_acceptance_pass") is True
    )


def _probe_governed_query_runtime() -> bool:
    """
    轻量、只读 Operational Probe。

    深层安全边界仍由 execution_governance_integration_tests
    在 Reproducibility / Security Gate 中验证。
    """

    try:
        config = load_governed_database_config()
        owner_user = os.getenv("POSTGRES_USER")

        if config.username == owner_user:
            return False

        governed_engine = get_governed_engine()

        with governed_engine.connect() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT
                        current_user AS current_user,
                        current_setting(
                            'default_transaction_read_only'
                        ) AS default_read_only,
                        has_schema_privilege(
                            current_user,
                            'beauty_bi_v2',
                            'USAGE'
                        ) AS schema_usage,
                        has_table_privilege(
                            current_user,
                            'beauty_bi_v2.fact_orders',
                            'SELECT'
                        ) AS can_select,
                        has_table_privilege(
                            current_user,
                            'beauty_bi_v2.fact_orders',
                            'INSERT'
                        ) AS can_insert,
                        has_table_privilege(
                            current_user,
                            'beauty_bi_v2.fact_orders',
                            'UPDATE'
                        ) AS can_update,
                        has_table_privilege(
                            current_user,
                            'beauty_bi_v2.fact_orders',
                            'DELETE'
                        ) AS can_delete
                    """
                )
            ).mappings().one()

        return (
            row["current_user"] == config.username
            and row["default_read_only"] == "on"
            and row["schema_usage"] is True
            and row["can_select"] is True
            and row["can_insert"] is False
            and row["can_update"] is False
            and row["can_delete"] is False
        )

    except Exception:
        return False


def _probe_dependency_contract() -> bool:
    """
    使用当前 Python 环境执行 pip check。

    Docker Fresh Build 最终仍需用 requirements-lock.txt
    从空环境重建；这里仅验证当前运行环境依赖关系无破损。
    """

    completed = subprocess.run(
        [sys.executable, "-m", "pip", "check"],
        capture_output=True,
        text=True,
        check=False,
    )

    return completed.returncode == 0


def probe_startup_readiness_v2() -> tuple[
    StartupReadinessSnapshotV2,
    StartupReadinessReportV2,
]:
    """
    Day90 Bootstrap Probe。

    它可以执行昂贵但只读的 Formal Dataset Acceptance，
    因此适合 bootstrap / reproducibility gate，
    不应直接作为高频 Docker healthcheck。
    """

    (
        database_reachable,
        schema_state,
        population_state,
        statistics_rows,
    ) = _probe_database_structure()

    formal_acceptance_passed = False
    planner_statistics_ready = False
    governed_query_runtime_ready = False

    dependency_contract_ready = (
        _probe_dependency_contract()
    )

    if (
        database_reachable
        and schema_state == SchemaReadinessStateV2.EXPECTED
        and population_state
        == DatasetPopulationStateV2.COMPLETE
    ):
        formal_acceptance_passed = (
            _run_formal_dataset_acceptance()
        )

        if formal_acceptance_passed:
            planner_statistics_ready = (
                planner_statistics_ready_v2(
                    statistics_rows
                )
            )

        if (
            formal_acceptance_passed
            and planner_statistics_ready
        ):
            governed_query_runtime_ready = (
                _probe_governed_query_runtime()
            )

    snapshot = StartupReadinessSnapshotV2(
        database_reachable=database_reachable,
        schema_state=schema_state,
        dataset_population_state=population_state,
        formal_dataset_acceptance_passed=(
            formal_acceptance_passed
        ),
        planner_statistics_ready=(
            planner_statistics_ready
        ),
        governed_query_runtime_ready=(
            governed_query_runtime_ready
        ),
        application_dependency_contract_ready=(
            dependency_contract_ready
        ),
    )

    return (
        snapshot,
        classify_startup_readiness_v2(snapshot),
    )


def main() -> None:
    snapshot, report = probe_startup_readiness_v2()

    print("=" * 80)
    print("Day90 Startup Readiness Probe V2")
    print("=" * 80)
    print(
        json.dumps(
            {
                "snapshot": snapshot.model_dump(
                    mode="json"
                ),
                "report": report.model_dump(
                    mode="json"
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    if report.status.value != "ready":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
