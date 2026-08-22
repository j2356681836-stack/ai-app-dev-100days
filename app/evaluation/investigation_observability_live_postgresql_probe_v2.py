from __future__ import annotations

from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from app.delivery.decision_console_runtime_v2 import (
    build_day89_channel_tool_binding_v2,
    build_day89_local_access_context_v2,
)
from app.delivery.investigation_runtime_v2 import (
    Day89InvestigationRuntimeStatusV2,
    run_day89_agentic_investigation_step_v2,
)
from app.delivery.runtime_delivery_bridge_v2 import (
    RuntimeDeliveryBridgeStatusV2,
    invoke_governed_plan_delivery_v2,
)
from app.governance.execution_policy import GovernedExecutionPolicy
from app.governance.governance_runtime import GovernanceRuntimeConfig
from app.observability.langfuse_observability_v2 import (
    flush_langfuse_v2,
    langfuse_observability_enabled_v2,
)
from app.semantic_layer.time_comparison_contract_v2 import (
    TimeWindowReferenceV2,
)


WINDOW = TimeWindowReferenceV2(
    start_date=date(2025, 1, 1),
    end_date=date(2025, 12, 31),
)

EXECUTION_POLICY = GovernedExecutionPolicy(
    statement_timeout_ms=30_000,
    max_rows=20,
)


def _runtime_config(
    audit_path: Path,
) -> GovernanceRuntimeConfig:
    return GovernanceRuntimeConfig(
        result_tokenization_secret=(
            "day91-live-tokenization-secret-32-chars"
        ),
        audit_secret=(
            "day91-live-audit-secret-32-characters"
        ),
        audit_log_path=audit_path,
        create_parent_directory=True,
        fsync_enabled=True,
    )


def run_live_observability_probe_v2() -> None:
    """
    Day91 live end-to-end observability probe.

    真实路径：
    Structured channel Seed
    → READY Evidence Delivery
    → Investigation State
    → default live DeepSeek Planner
    → Trusted Tool Binding
    → governed PostgreSQL region query
    → protected EvidenceReference
    → Observation / Evidence Update
    → Loop Control
    → STOP

    说明：
    - 这是 live model observed evidence，不是 deterministic regression；
    - 不向 Langfuse 上传 prompt / response / SQL / rows；
    - 依赖当前 shell 已显式开启 LANGFUSE_OBSERVABILITY_ENABLED=true。
    """

    if not langfuse_observability_enabled_v2():
        raise RuntimeError(
            "Langfuse Observability 未开启或配置不完整。"
            "请先设置 LANGFUSE_OBSERVABILITY_ENABLED=true。"
        )

    with TemporaryDirectory() as tmp:
        audit_path = (
            Path(tmp)
            / "day91_live_investigation_audit.jsonl"
        )
        config = _runtime_config(audit_path)

        seed_request_id = "day91-live-seed-channel"

        seed_context = build_day89_local_access_context_v2(
            request_id=seed_request_id,
        )

        seed_binding = build_day89_channel_tool_binding_v2()

        seed = invoke_governed_plan_delivery_v2(
            context=seed_context,
            plan_name=seed_binding.plan_name,
            analysis_window=WINDOW,
            question="2025年各渠道GMV是多少？",
            runtime_config=config,
            approved_tool_binding=seed_binding,
            execution_policy=EXECUTION_POLICY,
            event_id=seed_request_id,
        )

        assert (
            seed.status
            == RuntimeDeliveryBridgeStatusV2.READY
        )
        assert seed.delivery is not None
        assert (
            seed.delivery.evidence_pack.analysis_scope
            .result_grain
            == "channel"
        )

        # 关键差异：
        # 不注入 deterministic planner。
        # production entry 将调用默认的 live DeepSeek Planner。
        result = run_day89_agentic_investigation_step_v2(
            seed_result=seed,
            reference_date=date(2026, 8, 22),
            runtime_config=config,
            execution_policy=EXECUTION_POLICY,
        )

        assert (
            result.status
            == Day89InvestigationRuntimeStatusV2.STOPPED
        )
        assert result.execution_result is not None
        assert result.execution_result.evidence_reference is not None
        assert result.execution_result.released_rows

        selected_action = (
            result.planner_decision.selected_action
        )
        assert selected_action is not None
        assert selected_action.action_id == "drill_region"

        for row in result.execution_result.released_rows:
            assert set(row) == {
                "region_name",
                "gmv",
            }
            assert "__group_size" not in row

        assert result.transition is not None
        assert result.stop_status is not None

        print(
            "Day91 Live Investigation Observability Probe"
        )
        print("Status: PASS")
        print(
            "Planner action: "
            + selected_action.action_id
        )
        print(
            "Runtime status: "
            + result.status.value
        )
        print(
            "Stop reason: "
            + result.stop_status.stop_reason.value
        )
        print(
            "Released rows: "
            + str(
                len(
                    result.execution_result.released_rows
                )
            )
        )


def main() -> None:
    try:
        run_live_observability_probe_v2()
    finally:
        # 短生命周期 probe 必须显式 flush。
        # 不把 flush 放进 production request path。
        flush_langfuse_v2()

    print("LANGFUSE_FLUSH_OK")


if __name__ == "__main__":
    main()
