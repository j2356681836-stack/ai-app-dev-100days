from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict


class SchemaReadinessStateV2(str, Enum):
    ABSENT = "absent"
    EXPECTED = "expected"
    DRIFTED = "drifted"


class DatasetPopulationStateV2(str, Enum):
    EMPTY = "empty"
    COMPLETE = "complete"
    PARTIAL_OR_DRIFTED = "partial_or_drifted"


class StartupReadinessStatusV2(str, Enum):
    DATABASE_UNAVAILABLE = "database_unavailable"
    INITIALIZATION_REQUIRED = "initialization_required"
    SEED_REQUIRED = "seed_required"
    INCONSISTENT = "inconsistent"
    VALIDATION_REQUIRED = "validation_required"
    STATISTICS_REQUIRED = "statistics_required"
    QUERY_RUNTIME_REQUIRED = "query_runtime_required"
    APPLICATION_RUNTIME_REQUIRED = "application_runtime_required"
    READY = "ready"


class StartupReadinessSnapshotV2(BaseModel):
    """
    启动探针提供给状态机的只读事实。

    Snapshot 只携带已验证事实，不携带密码、SQL 或 raw rows。
    本合同不执行初始化 / Seed / ANALYZE / Role Provisioning。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    database_reachable: bool
    schema_state: SchemaReadinessStateV2
    dataset_population_state: DatasetPopulationStateV2

    formal_dataset_acceptance_passed: bool
    planner_statistics_ready: bool
    governed_query_runtime_ready: bool
    application_dependency_contract_ready: bool


class StartupReadinessReportV2(BaseModel):
    """
    对外发布的安全启动判断结果。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    contract_version: str = "startup_readiness_v2"
    status: StartupReadinessStatusV2
    message: str
    next_action: str
    automatic_repair_allowed: bool = False


def _contradictory_snapshot(
    snapshot: StartupReadinessSnapshotV2,
) -> bool:
    """
    矛盾状态必须 fail closed，不允许猜测并继续初始化。
    """

    if (
        snapshot.schema_state
        == SchemaReadinessStateV2.ABSENT
        and snapshot.dataset_population_state
        != DatasetPopulationStateV2.EMPTY
    ):
        return True

    if (
        snapshot.dataset_population_state
        != DatasetPopulationStateV2.COMPLETE
        and (
            snapshot.formal_dataset_acceptance_passed
            or snapshot.planner_statistics_ready
            or snapshot.governed_query_runtime_ready
        )
    ):
        return True

    return False


def classify_startup_readiness_v2(
    snapshot: StartupReadinessSnapshotV2,
) -> StartupReadinessReportV2:
    """
    Database
    → Schema
    → Dataset
    → Formal Acceptance
    → Planner Statistics
    → Governed Query Runtime
    → Application Dependency Contract
    → READY

    本函数只分类，不执行任何修复动作。
    """

    if not snapshot.database_reachable:
        return StartupReadinessReportV2(
            status=StartupReadinessStatusV2.DATABASE_UNAVAILABLE,
            message=(
                "PostgreSQL 当前不可达，不能继续判断 "
                "Dataset / Query Runtime readiness。"
            ),
            next_action="等待数据库 healthcheck 通过后重新探测。",
        )

    if _contradictory_snapshot(snapshot):
        return StartupReadinessReportV2(
            status=StartupReadinessStatusV2.INCONSISTENT,
            message=(
                "启动证据存在矛盾，不能安全解释为一个"
                "正常的新环境或已完成环境。"
            ),
            next_action=(
                "停止自动初始化，人工检查 Schema / Dataset "
                "状态与最近一次 Bootstrap 记录。"
            ),
        )

    if (
        snapshot.schema_state == SchemaReadinessStateV2.DRIFTED
        or snapshot.dataset_population_state
        == DatasetPopulationStateV2.PARTIAL_OR_DRIFTED
    ):
        return StartupReadinessReportV2(
            status=StartupReadinessStatusV2.INCONSISTENT,
            message=(
                "检测到部分初始化或结构 / 数据漂移。"
                "自动继续 Seed 可能造成混合版本数据。"
            ),
            next_action="Fail closed；人工诊断后决定恢复、重建或回滚。",
        )

    if snapshot.schema_state == SchemaReadinessStateV2.ABSENT:
        return StartupReadinessReportV2(
            status=StartupReadinessStatusV2.INITIALIZATION_REQUIRED,
            message="目标 Dataset V2 Schema 尚未初始化。",
            next_action=(
                "执行受控 Schema Initialization；"
                "完成后重新探测，不直接假定 Seed 成功。"
            ),
        )

    if (
        snapshot.dataset_population_state
        == DatasetPopulationStateV2.EMPTY
    ):
        return StartupReadinessReportV2(
            status=StartupReadinessStatusV2.SEED_REQUIRED,
            message="Schema 已存在，但 Dataset 尚未填充。",
            next_action="执行确定性 Seed；完成后重新探测 Dataset 状态。",
        )

    if not snapshot.formal_dataset_acceptance_passed:
        return StartupReadinessReportV2(
            status=StartupReadinessStatusV2.VALIDATION_REQUIRED,
            message=(
                "Dataset 已填充，但尚无本次启动链的"
                " Formal Acceptance PASS 证据。"
            ),
            next_action=(
                "运行 Manifest-driven Formal Acceptance；"
                "失败时停止，不进入 ANALYZE / Application Ready。"
            ),
        )

    if not snapshot.planner_statistics_ready:
        return StartupReadinessReportV2(
            status=StartupReadinessStatusV2.STATISTICS_REQUIRED,
            message=(
                "Dataset 已通过正式验收，但 Planner Statistics "
                "尚未确认 Ready。"
            ),
            next_action="运行 Dataset V2 ANALYZE，并验证统计信息。",
        )

    if not snapshot.governed_query_runtime_ready:
        return StartupReadinessReportV2(
            status=StartupReadinessStatusV2.QUERY_RUNTIME_REQUIRED,
            message=(
                "Dataset / Statistics 已 Ready，但 Governed "
                "Query Runtime 尚未通过只读执行边界验证。"
            ),
            next_action=(
                "验证或按需 Provision AI Query Role；"
                "不得回退复用 Owner / Seed 账户。"
            ),
        )

    if not snapshot.application_dependency_contract_ready:
        return StartupReadinessReportV2(
            status=StartupReadinessStatusV2.APPLICATION_RUNTIME_REQUIRED,
            message=(
                "数据库与 Governed Runtime 已 Ready，"
                "但应用依赖合同尚未确认可复现。"
            ),
            next_action="修复 requirements / lock 并通过 dependency check。",
        )

    return StartupReadinessReportV2(
        status=StartupReadinessStatusV2.READY,
        message=(
            "数据库、Dataset、Formal Acceptance、Planner Statistics、"
            "Governed Query Runtime 与应用依赖合同均已 Ready。"
        ),
        next_action=(
            "允许启动 Decision Console；"
            "启动流程不需要重新 Seed 或自动 Provision。"
        ),
    )
