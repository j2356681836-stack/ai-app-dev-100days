from __future__ import annotations

from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from app.agents.evidence_pack_v2 import EvidenceTypeV2
from app.agents.investigation_loop_v2 import (
    InvestigationBudgetPolicyV2,
    InvestigationSessionPolicyV2,
    InvestigationStopReasonV2,
)
from app.agents.investigation_planner_v2 import (
    InvestigationStateV2,
    PlannerDecisionTypeV2,
    PlannerProposalV2,
    validate_planner_proposal_v2,
)
from app.delivery.decision_console_runtime_v2 import (
    run_day89_local_investigation_v2,
)
from app.delivery.investigation_delivery_adapter_v2 import (
    InvestigationDeliveryStatusV2,
    build_continued_investigation_step_delivery_v2,
    build_investigation_step_delivery_v2,
)
from app.delivery.investigation_runtime_v2 import (
    Day89InvestigationRuntimeStatusV2,
    build_day89_continuation_state_v2,
    continue_day89_agentic_investigation_step_v2,
    run_day89_agentic_investigation_step_v2,
)
from app.delivery.runtime_delivery_bridge_v2 import (
    RuntimeDeliveryBridgeStatusV2,
)
from app.governance.audit_sink import verify_audit_log
from app.governance.execution_policy import (
    GovernedExecutionPolicy,
)
from app.governance.governance_runtime import (
    GovernanceRuntimeConfig,
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
            "day89-hitl-token-secret-32-characters"
        ),
        audit_secret=(
            "day89-hitl-audit-secret-32-characters"
        ),
        audit_log_path=audit_path,
        create_parent_directory=True,
        fsync_enabled=True,
    )


def _select_action(action_id: str):
    def planner(state: InvestigationStateV2):
        available = {
            action.action_id
            for action in state.available_actions
        }
        assert action_id in available

        supporting_id = (
            state.insight.evidence[-1].evidence_id
        )

        return validate_planner_proposal_v2(
            state=state,
            proposal=PlannerProposalV2(
                decision_type=PlannerDecisionTypeV2.SELECT_TOOL,
                action_id=action_id,
                rationale=f"测试显式选择 {action_id}。",
                supporting_evidence_ids=(supporting_id,),
            ),
        )

    return planner


def test_real_postgresql_explicit_continue_requires_user_and_preserves_trace() -> None:
    with TemporaryDirectory() as tmp:
        audit_path = (
            Path(tmp)
            / "day89_hitl_continue_audit.jsonl"
        )
        config = _runtime_config(audit_path)

        seed = run_day89_local_investigation_v2(
            question="2025年各渠道GMV是多少？",
            reference_date=date(2026, 8, 20),
            runtime_config=config,
            execution_policy=EXECUTION_POLICY,
        )

        assert (
            seed.status
            == RuntimeDeliveryBridgeStatusV2.READY
        )
        assert seed.delivery is not None

        # 每轮最多一个调查 Tool，Session 允许两轮。
        round_budget = InvestigationBudgetPolicyV2(
            max_investigation_steps=1,
            max_retries_per_action=0,
        )
        session_policy = InvestigationSessionPolicyV2(
            max_rounds=2,
            max_total_investigation_steps=2,
        )

        first = run_day89_agentic_investigation_step_v2(
            seed_result=seed,
            reference_date=date(2026, 8, 20),
            runtime_config=config,
            execution_policy=EXECUTION_POLICY,
            planner=_select_action("drill_region"),
            include_category_action=True,
            budget_policy=round_budget,
            session_policy=session_policy,
        )

        assert (
            first.status
            == Day89InvestigationRuntimeStatusV2.STOPPED
        )
        assert first.stop_status is not None
        assert (
            first.stop_status.stop_reason
            == InvestigationStopReasonV2
            .INVESTIGATION_BUDGET_EXHAUSTED
        ), (
            "第一轮必须因 Round Budget 停止；"
            f"actual={first.stop_status.stop_reason.value}"
        )
        assert first.stop_status.can_continue is True, (
            "第一轮仍有 Category 且 Session Budget 充足，"
            "应允许用户显式 continuation；"
            f"remaining={first.stop_status.uninvestigated_action_ids}; "
            f"detail={first.stop_status.detail}"
        )
        assert first.stop_status.uninvestigated_action_ids == (
            "drill_category",
        ), (
            "Region 完成后应只剩 Category；"
            f"actual={first.stop_status.uninvestigated_action_ids}"
        )

        first_delivery = build_investigation_step_delivery_v2(
            seed_result=seed,
            runtime_step=first,
            request_subject="2025 年 GMV HITL 调查",
        )

        assert (
            first_delivery.status
            == InvestigationDeliveryStatusV2.READY
        )
        assert first_delivery.delivery is not None

        continuation = build_day89_continuation_state_v2(
            runtime_step=first,
        )

        # 没有用户明确 Continue 必须 fail closed。
        try:
            continue_day89_agentic_investigation_step_v2(
                delivery=first_delivery.delivery,
                continuation_state=continuation,
                user_requested_continue=False,
                runtime_config=config,
                execution_policy=EXECUTION_POLICY,
                planner=_select_action("drill_category"),
            )
        except ValueError:
            pass
        else:
            raise AssertionError(
                "user_requested_continue=False 必须阻止下一轮。"
            )

        second = continue_day89_agentic_investigation_step_v2(
            delivery=first_delivery.delivery,
            continuation_state=continuation,
            user_requested_continue=True,
            runtime_config=config,
            execution_policy=EXECUTION_POLICY,
            planner=_select_action("drill_category"),
        )

        assert (
            second.status
            == Day89InvestigationRuntimeStatusV2.STOPPED
        ), (
            "第二轮必须在执行一个受控 Tool 后 STOP；"
            f"actual={second.status.value}"
        )
        assert second.stop_status is not None

        # Day86 deterministic priority：
        # evidence_sufficient → round budget → failure/no-action。
        # 因此 max_investigation_steps=1 的第二轮执行 Category 后，
        # STOP trigger 仍然是 INVESTIGATION_BUDGET_EXHAUSTED。
        # 此时 remaining actions 已为空，所以 can_continue=False。
        assert (
            second.stop_status.stop_reason
            == InvestigationStopReasonV2
            .INVESTIGATION_BUDGET_EXHAUSTED
        ), (
            "第二轮 Stop Reason 应遵守 Day86 Budget-first 优先级；"
            f"actual={second.stop_status.stop_reason.value}; "
            f"remaining={second.stop_status.uninvestigated_action_ids}; "
            f"can_continue={second.stop_status.can_continue}"
        )
        assert second.stop_status.uninvestigated_action_ids == (), (
            "第二轮执行 Category 后不应再有剩余合法 Action；"
            f"actual={second.stop_status.uninvestigated_action_ids}"
        )
        assert second.stop_status.can_continue is False

        final_delivery = (
            build_continued_investigation_step_delivery_v2(
                previous_result=first_delivery,
                runtime_step=second,
                prior_transitions=(
                    continuation.prior_transitions
                ),
                prior_continuation_stop_statuses=(
                    continuation.stop_status,
                ),
                request_subject="2025 年 GMV HITL 调查",
            )
        )

        assert (
            final_delivery.status
            == InvestigationDeliveryStatusV2.READY
        )
        assert final_delivery.delivery is not None
        assert final_delivery.console_view is not None

        records = (
            final_delivery.delivery.evidence_pack
            .evidence_records
        )

        query_records = tuple(
            record
            for record in records
            if (
                record.evidence_type
                == EvidenceTypeV2.GOVERNED_QUERY_RESULT
            )
        )
        observation_records = tuple(
            record
            for record in records
            if (
                record.evidence_type
                == EvidenceTypeV2.INVESTIGATION_OBSERVATION
            )
        )

        # Seed Channel + Region + Category.
        assert len(query_records) == 3
        assert len(observation_records) == 2

        trace = final_delivery.console_view.investigation_trace
        assert len(trace) == 2, (
            f"累计 Trace 应为两步，actual={len(trace)}"
        )
        assert trace[0].selected_action_id == "drill_region", (
            f"step1={trace[0].selected_action_id}"
        )
        assert trace[0].next_directive.value == "stop"
        assert (
            trace[0].stop_reason
            == InvestigationStopReasonV2
            .INVESTIGATION_BUDGET_EXHAUSTED
        )

        assert trace[1].selected_action_id == "drill_category", (
            f"step2={trace[1].selected_action_id}"
        )
        assert trace[1].next_directive.value == "stop"

        control = final_delivery.console_view.runtime_control
        assert control is not None
        assert control.current_round == 2
        assert control.total_steps_used == 2
        assert control.can_continue is False

        verification = verify_audit_log(audit_path)
        assert verification.success
        assert verification.record_count == 3


TESTS = (
    test_real_postgresql_explicit_continue_requires_user_and_preserves_trace,
)


def run_acceptance() -> None:
    print("Day89 Runtime HITL Explicit Continue PostgreSQL Integration")

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
