from __future__ import annotations

from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from app.agents.clarification_resolution_v2 import (
    ClarificationResolutionStatusV2,
    ClarificationResponseV2,
    build_day89_direction_clarification_requirement_v2,
    build_day89_direction_resolution_contract_v2,
)
from app.agents.evidence_pack_v2 import EvidenceTypeV2
from app.agents.investigation_loop_v2 import (
    InvestigationBudgetPolicyV2,
    InvestigationSessionPolicyV2,
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
    build_investigation_step_delivery_v2,
    build_resolved_clarification_step_delivery_v2,
)
from app.delivery.investigation_runtime_v2 import (
    Day89InvestigationRuntimeStatusV2,
    build_day89_pending_clarification_state_v2,
    resume_day89_agentic_investigation_after_clarification_v2,
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
            "day89-clarification-token-secret-32chars"
        ),
        audit_secret=(
            "day89-clarification-audit-secret-32chars"
        ),
        audit_log_path=audit_path,
        create_parent_directory=True,
        fsync_enabled=True,
    )


def _clarify_planner(state: InvestigationStateV2):
    assert state.clarification_requirement is not None

    return validate_planner_proposal_v2(
        state=state,
        proposal=PlannerProposalV2(
            decision_type=PlannerDecisionTypeV2.CLARIFY,
            clarification_prompt=(
                "请选择先检查区域维度还是品类维度。"
            ),
            rationale=(
                "trusted investigation direction prerequisite "
                "尚未由用户解决。"
            ),
        ),
    )


def _select_only_available_action(
    state: InvestigationStateV2,
):
    assert state.clarification_requirement is None
    assert len(state.available_actions) == 1

    action = state.available_actions[0]
    supporting_id = state.insight.evidence[-1].evidence_id

    return validate_planner_proposal_v2(
        state=state,
        proposal=PlannerProposalV2(
            decision_type=PlannerDecisionTypeV2.SELECT_TOOL,
            action_id=action.action_id,
            rationale=(
                "用户已通过 deterministic resolver "
                "明确选择该受控调查方向。"
            ),
            supporting_evidence_ids=(supporting_id,),
        ),
    )


def test_real_postgresql_clarification_response_resumes_governed_tool() -> None:
    with TemporaryDirectory() as tmp:
        audit_path = (
            Path(tmp)
            / "day89_clarification_resume_audit.jsonl"
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

        requirement = (
            build_day89_direction_clarification_requirement_v2()
        )
        contract = (
            build_day89_direction_resolution_contract_v2()
        )

        clarification_step = (
            run_day89_agentic_investigation_step_v2(
                seed_result=seed,
                reference_date=date(2026, 8, 20),
                runtime_config=config,
                execution_policy=EXECUTION_POLICY,
                planner=_clarify_planner,
                clarification_requirement=requirement,
                include_category_action=True,
                budget_policy=InvestigationBudgetPolicyV2(
                    max_investigation_steps=2,
                    max_retries_per_action=0,
                ),
                session_policy=InvestigationSessionPolicyV2(
                    max_rounds=1,
                    max_total_investigation_steps=2,
                ),
            )
        )

        assert (
            clarification_step.status
            == Day89InvestigationRuntimeStatusV2
            .CLARIFICATION_REQUIRED
        )

        clarification_delivery = (
            build_investigation_step_delivery_v2(
                seed_result=seed,
                runtime_step=clarification_step,
                request_subject="2025 年 GMV clarification HITL",
            )
        )

        assert (
            clarification_delivery.status
            == InvestigationDeliveryStatusV2
            .CLARIFICATION_READY
        )
        assert clarification_delivery.console_view is not None
        assert (
            clarification_delivery.console_view.clarification
            is not None
        )

        pending = build_day89_pending_clarification_state_v2(
            runtime_step=clarification_step,
            resolution_contract=contract,
        )

        # 非法 choice：不得执行 Tool，也不得增加 Audit。
        unresolved = (
            resume_day89_agentic_investigation_after_clarification_v2(
                pending=pending,
                response=ClarificationResponseV2(
                    choice_id="invented"
                ),
                runtime_config=config,
                execution_policy=EXECUTION_POLICY,
                planner=_select_only_available_action,
            )
        )

        assert (
            unresolved.resolution.status
            == ClarificationResolutionStatusV2.UNRESOLVED
        )
        assert unresolved.runtime_step is None

        verification_before = verify_audit_log(audit_path)
        assert verification_before.success
        assert verification_before.record_count == 1

        still_blocked = (
            build_resolved_clarification_step_delivery_v2(
                previous_result=clarification_delivery,
                resume_result=unresolved,
                request_subject="2025 年 GMV clarification HITL",
            )
        )
        assert (
            still_blocked.status
            == InvestigationDeliveryStatusV2
            .CLARIFICATION_READY
        )
        assert still_blocked.console_view is not None
        assert still_blocked.console_view.clarification is not None

        # 合法 choice：resolver 收窄为 Category，然后真实 PostgreSQL。
        resumed = (
            resume_day89_agentic_investigation_after_clarification_v2(
                pending=pending,
                response=ClarificationResponseV2(
                    choice_id="category"
                ),
                runtime_config=config,
                execution_policy=EXECUTION_POLICY,
                planner=_select_only_available_action,
            )
        )

        assert (
            resumed.resolution.status
            == ClarificationResolutionStatusV2.RESOLVED
        )
        assert resumed.runtime_step is not None
        assert (
            resumed.runtime_step.planner_decision
            .selected_action.action_id
            == "drill_category"
        )

        final = build_resolved_clarification_step_delivery_v2(
            previous_result=clarification_delivery,
            resume_result=resumed,
            request_subject="2025 年 GMV clarification HITL",
        )

        assert (
            final.status
            == InvestigationDeliveryStatusV2.READY
        )
        assert final.delivery is not None
        assert final.console_view is not None
        assert final.console_view.clarification is None

        records = final.delivery.evidence_pack.evidence_records

        query_records = tuple(
            item
            for item in records
            if (
                item.evidence_type
                == EvidenceTypeV2.GOVERNED_QUERY_RESULT
            )
        )
        observation_records = tuple(
            item
            for item in records
            if (
                item.evidence_type
                == EvidenceTypeV2.INVESTIGATION_OBSERVATION
            )
        )

        # Seed Channel + selected Category.
        assert len(query_records) == 2
        assert len(observation_records) == 1

        trace = final.console_view.investigation_trace
        assert len(trace) == 1
        assert trace[0].selected_action_id == "drill_category"

        verification_after = verify_audit_log(audit_path)
        assert verification_after.success
        assert verification_after.record_count == 2


TESTS = (
    test_real_postgresql_clarification_response_resumes_governed_tool,
)


def run_acceptance() -> None:
    print(
        "Day89 Runtime HITL Clarification Resume "
        "PostgreSQL Integration"
    )

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
