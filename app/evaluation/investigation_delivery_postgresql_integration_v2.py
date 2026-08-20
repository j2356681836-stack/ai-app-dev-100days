from __future__ import annotations

from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from app.agents.evidence_pack_delivery_v2 import (
    EvidenceSufficiencyStatusV2,
)
from app.agents.evidence_pack_v2 import EvidenceTypeV2
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
from app.delivery.investigation_delivery_adapter_v2 import (
    InvestigationDeliveryStatusV2,
    build_investigation_step_delivery_v2,
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
            "day89-investigation-delivery-token-secret-32"
        ),
        audit_secret=(
            "day89-investigation-delivery-audit-secret-32"
        ),
        audit_log_path=audit_path,
        create_parent_directory=True,
        fsync_enabled=True,
    )


def test_real_agentic_step_closes_evidence_delivery_and_trace() -> None:
    """
    Real PostgreSQL:

    channel Seed Evidence
    -> bounded Planner selects region
    -> Governed region execution
    -> Region Query Evidence
    -> Investigation Observation Evidence(parent=region)
    -> EvidencePackDelivery(PARTIAL)
    -> Decision Console Trace + Runtime Control

    Region result 不自动升级成新的 business fact。
    """

    with TemporaryDirectory() as tmp:
        audit_path = (
            Path(tmp)
            / "day89_investigation_delivery_audit.jsonl"
        )
        config = _runtime_config(audit_path)

        seed_request_id = "day89-investigation-delivery-seed"
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

        seed_fact_count = len(
            seed.delivery.evidence_pack.insight.confirmed_facts
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
                        "渠道 Evidence 已存在，继续从区域方向补充调查。"
                    ),
                    supporting_evidence_ids=(supporting_id,),
                ),
            )

        runtime_step = (
            run_day89_agentic_investigation_step_v2(
                seed_result=seed,
                reference_date=date(2026, 8, 19),
                runtime_config=config,
                execution_policy=EXECUTION_POLICY,
                planner=planner,
            )
        )

        assert (
            runtime_step.status
            == Day89InvestigationRuntimeStatusV2.STOPPED
        )
        assert runtime_step.governed_query_context is not None
        assert runtime_step.execution_result is not None
        assert (
            runtime_step.execution_result.evidence_reference
            is not None
        )

        delivered = build_investigation_step_delivery_v2(
            seed_result=seed,
            runtime_step=runtime_step,
            request_subject=(
                "2025 年 GMV bounded investigation"
            ),
        )

        assert (
            delivered.status
            == InvestigationDeliveryStatusV2.READY
        )
        assert delivered.delivery is not None
        assert delivered.console_view is not None
        assert delivered.executive_brief is not None

        records = (
            delivered.delivery.evidence_pack.evidence_records
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

        assert len(query_records) == 2
        assert len(observation_records) == 1

        region_evidence_id = (
            runtime_step.execution_result
            .evidence_reference.evidence_id
        )
        observation_record = observation_records[0]

        assert (
            observation_record.parent_evidence_ids
            == (region_evidence_id,)
        )

        assert (
            delivered.delivery.sufficiency.status
            == EvidenceSufficiencyStatusV2.PARTIAL
        )
        assert (
            delivered.delivery.evidence_pack.insight.unknowns
        )

        assert (
            len(
                delivered.delivery.evidence_pack
                .insight.confirmed_facts
            )
            == seed_fact_count
        )

        trace = delivered.console_view.investigation_trace
        assert len(trace) == 1
        assert trace[0].selected_action_id == "drill_region"
        assert trace[0].produced_evidence_ids == (
            region_evidence_id,
        )
        assert (
            trace[0].observation_evidence_id
            == observation_record.reference.evidence_id
        )
        assert trace[0].next_directive.value == "stop"
        assert trace[0].stop_reason is not None
        assert (
            trace[0].stop_reason.value
            == "no_legal_action"
        )

        control = delivered.console_view.runtime_control
        assert control is not None
        assert control.evidence_sufficient is False
        assert control.can_continue is False

        # Business/Analyst projection 不得暴露 server-internal SQL。
        console_json = (
            delivered.console_view
            .model_dump_json()
            .lower()
        )
        assert '"sql"' not in console_json
        assert "sql_fingerprint" not in console_json
        assert "parameters" not in console_json

        verification = verify_audit_log(audit_path)
        assert verification.success
        assert verification.record_count == 2


TESTS = (
    test_real_agentic_step_closes_evidence_delivery_and_trace,
)


def run_acceptance() -> None:
    print("Day89 Investigation Delivery PostgreSQL Integration")

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
