from __future__ import annotations

from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from app.agents.investigation_planner_v2 import (
    InvestigationStateV2,
    PlannerDecisionTypeV2,
    PlannerProposalV2,
    validate_planner_proposal_v2,
)
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
from app.governance.audit_sink import verify_audit_log
from app.governance.execution_policy import GovernedExecutionPolicy
from app.governance.governance_runtime import GovernanceRuntimeConfig
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
            "day89-agentic-tokenization-secret-32-chars"
        ),
        audit_secret=(
            "day89-agentic-audit-secret-32-characters"
        ),
        audit_log_path=audit_path,
        create_parent_directory=True,
        fsync_enabled=True,
    )


def test_real_postgresql_one_agentic_step_from_channel_seed() -> None:
    """
    真实路径：

    Structured channel Seed
    → READY Evidence Delivery
    → Investigation State
    → deterministic test Planner 选择剩余 region action
    → Trusted Tool Binding
    → governed PostgreSQL region query
    → protected EvidenceReference
    → Observation
    → State Update
    → STOP(NO_LEGAL_ACTION, evidence_sufficient=False)

    本测试故意不使用 live LLM，
    避免把 Day89 Orchestrator correctness 与模型稳定性混在一起。
    """

    with TemporaryDirectory() as tmp:
        audit_path = (
            Path(tmp)
            / "day89_agentic_step_audit.jsonl"
        )
        config = _runtime_config(audit_path)

        seed_request_id = "day89-agentic-seed-channel"
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

        def planner(state: InvestigationStateV2):
            action_ids = tuple(
                action.action_id
                for action in state.available_actions
            )

            assert action_ids == ("drill_region",)

            supporting_id = (
                state.insight.evidence[-1].evidence_id
            )

            return validate_planner_proposal_v2(
                state=state,
                proposal=PlannerProposalV2(
                    decision_type=(
                        PlannerDecisionTypeV2.SELECT_TOOL
                    ),
                    action_id="drill_region",
                    rationale=(
                        "渠道结果已经存在，继续从区域方向补充调查。"
                    ),
                    supporting_evidence_ids=(
                        supporting_id,
                    ),
                ),
            )

        result = run_day89_agentic_investigation_step_v2(
            seed_result=seed,
            reference_date=date(2026, 8, 19),
            runtime_config=config,
            execution_policy=EXECUTION_POLICY,
            planner=planner,
        )

        assert (
            result.status
            == Day89InvestigationRuntimeStatusV2.STOPPED
        )
        assert result.execution_result is not None
        assert result.execution_result.evidence_reference is not None
        assert result.execution_result.released_rows

        for row in result.execution_result.released_rows:
            assert set(row) == {
                "region_name",
                "gmv",
            }
            assert "__group_size" not in row

        assert result.transition is not None
        observation = (
            result.transition.next_state
            .observation_history[-1]
        )
        assert observation.action_id == "drill_region"
        assert observation.status.value == "evidence"

        assert result.stop_status is not None
        assert (
            result.stop_status.evidence_sufficient
            is False
        )
        assert (
            result.stop_status.stop_reason.value
            == "no_legal_action"
        )

        evidence_ids = {
            item.evidence_id
            for item
            in result.session_after.loop_state
            .planner_state.insight.evidence
        }

        assert (
            seed.delivery.evidence_pack
            .evidence_records[0]
            .reference.evidence_id
            in evidence_ids
        )
        assert (
            result.execution_result
            .evidence_reference.evidence_id
            in evidence_ids
        )

        verification = verify_audit_log(audit_path)
        assert verification.success
        assert verification.record_count == 2


TESTS = (
    test_real_postgresql_one_agentic_step_from_channel_seed,
)


def run_acceptance() -> None:
    print("Day89 Investigation Runtime PostgreSQL Integration")

    passed = 0
    failures: list[str] = []

    for test in TESTS:
        try:
            test()
            passed += 1
        except Exception as exc:  # noqa: BLE001
            failures.append(
                f"{test.__name__}: "
                f"{type(exc).__name__}: {exc}"
            )

    print(f"Total: {len(TESTS)}")
    print(f"Passed: {passed}")
    print(f"Failed: {len(failures)}")

    for failure in failures:
        print(f"- {failure}")

    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    run_acceptance()
