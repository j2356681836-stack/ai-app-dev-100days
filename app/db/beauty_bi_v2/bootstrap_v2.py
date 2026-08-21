from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from app.db.provision_query_role import provision_query_role
from app.db.beauty_bi_v2.analyze_dataset import analyze_dataset_v2
from app.db.beauty_bi_v2.init_schema import init_v2_schema
from app.db.beauty_bi_v2.manifest_loader import (
    load_and_validate_day64_manifest,
    load_and_validate_day65_manifest,
)
from app.db.beauty_bi_v2.seed_dimensions import (
    seed_bridge_customer_membership,
    seed_dim_campaign,
    seed_dim_channel,
    seed_dim_customer,
    seed_dim_date,
    seed_dim_membership_account,
    seed_dim_product,
    seed_dim_promotion,
    seed_dim_region,
    seed_membership_channel_binding,
)
from app.db.beauty_bi_v2.seed_transactions import (
    seed_marketing_spend,
    seed_transactions,
)
from app.db.beauty_bi_v2.startup_readiness_probe_v2 import (
    probe_startup_readiness_v2,
)
from app.db.beauty_bi_v2.startup_readiness_v2 import (
    StartupReadinessReportV2,
    StartupReadinessSnapshotV2,
    StartupReadinessStatusV2,
)


MAX_BOOTSTRAP_TRANSITIONS = 8


class BootstrapFailClosedError(RuntimeError):
    """
    当前状态不能被安全自动推进时抛出。

    这不是“尽量修复”异常，而是 Day90 Bootstrap 的安全边界。
    """


@dataclass(frozen=True)
class BootstrapDependenciesV2:
    probe: Callable[
        [],
        tuple[
            StartupReadinessSnapshotV2,
            StartupReadinessReportV2,
        ],
    ]
    initialize_schema: Callable[[], None]
    seed_dataset: Callable[[], None]
    analyze_dataset: Callable[[], None]
    provision_query_runtime: Callable[[], object]


def seed_dataset_v2() -> None:
    """
    只用于一个已经被 Probe 判定为 SEED_REQUIRED 的空 Dataset V2。

    顺序来自现有 FK / Day64-Day65 生成合同：

    固定维度 / 身份关系
    → marketing spend
    → 其余交易事实 + R12 tier history

    任一现有 Seed 函数失败时，本函数不吞异常。
    下一次 Probe 应把部分完成状态判为 INCONSISTENT，
    从而阻止自动续写混合版本 Dataset。
    """

    day64_manifest = load_and_validate_day64_manifest()

    dimension_steps = (
        ("dim_date", seed_dim_date),
        ("dim_region", seed_dim_region),
        ("dim_channel", seed_dim_channel),
        ("dim_product", seed_dim_product),
        ("dim_campaign", seed_dim_campaign),
        ("dim_promotion", seed_dim_promotion),
        ("dim_customer", seed_dim_customer),
        (
            "dim_membership_account",
            seed_dim_membership_account,
        ),
        (
            "bridge_customer_membership",
            seed_bridge_customer_membership,
        ),
        (
            "membership_channel_binding",
            seed_membership_channel_binding,
        ),
    )

    for step_name, step in dimension_steps:
        print(f"[BOOTSTRAP] Seed: {step_name}")
        step(day64_manifest)

    day65_manifest = load_and_validate_day65_manifest()

    print("[BOOTSTRAP] Seed: fact_marketing_spend")
    seed_marketing_spend(day65_manifest)

    print("[BOOTSTRAP] Seed: remaining transaction bundle")
    seed_transactions(day65_manifest)


def build_default_bootstrap_dependencies_v2(
) -> BootstrapDependenciesV2:
    return BootstrapDependenciesV2(
        probe=probe_startup_readiness_v2,
        initialize_schema=init_v2_schema,
        seed_dataset=seed_dataset_v2,
        analyze_dataset=analyze_dataset_v2,
        provision_query_runtime=provision_query_role,
    )


def _execute_allowed_transition_v2(
    status: StartupReadinessStatusV2,
    dependencies: BootstrapDependenciesV2,
) -> str:
    """
    每次只允许执行一个由 Readiness Contract 明确授权的动作。
    """

    if status == StartupReadinessStatusV2.INITIALIZATION_REQUIRED:
        dependencies.initialize_schema()
        return "initialize_schema"

    if status == StartupReadinessStatusV2.SEED_REQUIRED:
        dependencies.seed_dataset()
        return "seed_dataset"

    if status == StartupReadinessStatusV2.STATISTICS_REQUIRED:
        dependencies.analyze_dataset()
        return "analyze_dataset"

    if status == StartupReadinessStatusV2.QUERY_RUNTIME_REQUIRED:
        dependencies.provision_query_runtime()
        return "provision_query_runtime"

    raise BootstrapFailClosedError(
        "当前 Startup Status 不允许自动 mutation："
        f"{status.value}"
    )


def run_bootstrap_v2(
    dependencies: BootstrapDependenciesV2 | None = None,
) -> StartupReadinessReportV2:
    """
    Day90 Safe Bootstrap Orchestrator。

    关键性质：
    1. READY → no-op；
    2. 每次 mutation 后必须重新 Probe；
    3. INCONSISTENT / VALIDATION_REQUIRED /
       APPLICATION_RUNTIME_REQUIRED / DATABASE_UNAVAILABLE
       都 fail closed；
    4. 不允许无限循环。
    """

    deps = (
        dependencies
        if dependencies is not None
        else build_default_bootstrap_dependencies_v2()
    )

    executed_actions: list[str] = []

    for transition_number in range(
        1,
        MAX_BOOTSTRAP_TRANSITIONS + 1,
    ):
        snapshot, report = deps.probe()

        print("=" * 80)
        print(
            "Day90 Bootstrap Probe "
            f"{transition_number}/{MAX_BOOTSTRAP_TRANSITIONS}"
        )
        print(f"Status: {report.status.value}")
        print(f"Message: {report.message}")

        if report.status == StartupReadinessStatusV2.READY:
            print(
                "Bootstrap READY. "
                f"Executed actions: {executed_actions or ['none']}"
            )
            return report

        if report.status in {
            StartupReadinessStatusV2.DATABASE_UNAVAILABLE,
            StartupReadinessStatusV2.INCONSISTENT,
            StartupReadinessStatusV2.VALIDATION_REQUIRED,
            StartupReadinessStatusV2.APPLICATION_RUNTIME_REQUIRED,
        }:
            raise BootstrapFailClosedError(
                "Bootstrap fail closed："
                f"status={report.status.value}; "
                f"next_action={report.next_action}"
            )

        action = _execute_allowed_transition_v2(
            report.status,
            deps,
        )
        executed_actions.append(action)

    raise BootstrapFailClosedError(
        "Bootstrap 超过最大状态转换次数，"
        "拒绝继续自动执行。"
    )


def main() -> None:
    run_bootstrap_v2()


if __name__ == "__main__":
    main()
