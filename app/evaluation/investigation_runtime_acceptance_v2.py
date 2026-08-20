from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.agents.investigation_contracts_v2 import (
    AnalysisModeV2,
    AnalysisScopeV2,
    EvidenceReferenceV2,
    InsightContractV2,
    ToolContractV2,
    ToolFailureCodeV2,
    ToolIdentityV2,
)
from app.agents.investigation_loop_v2 import (
    InvestigationBudgetPolicyV2,
    InvestigationSessionPolicyV2,
    LoopDirectiveV2,
    InvestigationStopReasonV2,
)
from app.agents.investigation_planner_v2 import (
    AvailableInvestigationActionV2,
    ClarificationRequirementV2,
    InvestigationStateV2,
    PlannerDecisionTypeV2,
    PlannerProposalV2,
    validate_planner_proposal_v2,
)
from app.agents.investigation_tool_executor_v2 import (
    TrustedToolExecutionBindingV2,
)
from app.delivery.investigation_runtime_v2 import (
    Day89InvestigationRuntimeStatusV2,
    build_investigation_session_from_delivery_v2,
    run_one_investigation_step_v2,
)
from app.agents.evidence_pack_delivery_v2 import (
    MetricDefinitionSnapshotV2,
    assemble_evidence_pack_delivery_v2,
)
from app.agents.evidence_pack_v2 import (
    EvidencePackV2,
    EvidenceRecordV2,
    EvidenceTypeV2,
    GovernedEvidenceProvenanceV2,
    ProtectedResultV2,
)
from app.governance.governed_finalization import (
    FinalizationOutcome,
    FinalizationReason,
    GovernedFinalizationResult,
)
from app.semantic_layer.time_comparison_contract_v2 import (
    TimeWindowReferenceV2,
)


WINDOW = TimeWindowReferenceV2(
    start_date=date(2025, 1, 1),
    end_date=date(2025, 12, 31),
)


def _tool_contract(
    grain: str,
) -> ToolContractV2:
    return ToolContractV2(
        identity=ToolIdentityV2(
            name=f"governed_gmv_{grain}_query",
            version="dataset_v2",
            purpose=f"测试 {grain} GMV。",
        ),
        input_schema_name="GovernedInvestigationInputV2",
        output_schema_name="GovernedFinalizationResult",
        required_permissions=("metric_access", "data_scope"),
        execution_policy_reference="governed_execution_policy_v2",
        failure_semantics=(
            ToolFailureCodeV2.INVALID_INPUT,
            ToolFailureCodeV2.UNAUTHORIZED,
            ToolFailureCodeV2.UNSUPPORTED,
            ToolFailureCodeV2.TIMEOUT,
            ToolFailureCodeV2.NO_DATA,
            ToolFailureCodeV2.EXECUTION_FAILURE,
        ),
        executor_binding="execute_governed_query_v2",
    )


def _action(
    action_id: str,
    grain: str,
) -> AvailableInvestigationActionV2:
    return AvailableInvestigationActionV2(
        action_id=action_id,
        tool_contract=_tool_contract(grain),
    )


def _seed_delivery():
    reference = EvidenceReferenceV2(
        evidence_id="ev_seed",
        source="tool:governed_gmv_overall_query@dataset_v2",
        description="可信 Seed Evidence。",
    )

    scope = AnalysisScopeV2(
        metric_name="gmv",
        analysis_window=WINDOW,
        result_grain="overall",
        scope_summary="authorized scope",
    )

    insight = InsightContractV2(
        analysis_mode=AnalysisModeV2.FACT,
        analysis_scope=scope,
        evidence=(reference,),
    )

    record = EvidenceRecordV2(
        reference=reference,
        evidence_type=EvidenceTypeV2.GOVERNED_QUERY_RESULT,
        provenance=GovernedEvidenceProvenanceV2(
            dataset_name="beauty_bi_v2",
            target_schema="beauty_bi_v2",
            metric_name="gmv",
            result_grain="overall",
            analysis_window=WINDOW,
            scope_summary="authorized scope",
            plan_name="gmv_overall_v2",
            query_plan_fingerprint="qpf",
            envelope_fingerprint="env",
            compiled_contract_fingerprint="compiled",
            sql_fingerprint="sql",
            time_binding_fingerprint="time",
            scope_binding_fingerprint="scope",
            tool_name="governed_gmv_overall_query",
            tool_version="dataset_v2",
            audit_event_id="audit-seed",
            audit_event_fingerprint="audit-fp-seed",
            audit_record_hash="audit-hash-seed",
            finalization_contract_version="governed_finalization_v1",
        ),
        protected_result=ProtectedResultV2(
            field_names=("gmv",),
            rows=({"gmv": Decimal("100")},),
            row_count=1,
        ),
    )

    pack = EvidencePackV2(
        pack_id="seed-pack",
        analysis_scope=scope,
        insight=insight,
        evidence_records=(record,),
    )

    metric_definition = MetricDefinitionSnapshotV2(
        metadata_version="v2",
        dataset_name="beauty_bi_v2",
        metric_name="gmv",
        chinese_name="销售额",
        grain="paid_order_items",
        definition="测试 GMV。",
        formula="SUM(item_paid_amount)",
        filters=(),
        metric_fingerprint="metric-fp",
    )

    return assemble_evidence_pack_delivery_v2(
        evidence_pack=pack,
        metric_definition=metric_definition,
    )


def _finalization(
    *,
    value: str,
    event_id: str,
) -> GovernedFinalizationResult:
    return GovernedFinalizationResult(
        success=True,
        outcome=FinalizationOutcome.SUCCEEDED,
        reason_code=FinalizationReason.ALLOWED,
        message="ok",
        rows=(
            {
                "dimension_name": "A",
                "gmv": Decimal(value),
            },
        ),
        row_count=1,
        audit_persisted=True,
        audit_event_id=event_id,
        audit_event_fingerprint=f"fp-{event_id}",
        audit_sequence_number=1,
        audit_record_hash=f"hash-{event_id}",
        retryable=False,
    )


def _binding(
    action: AvailableInvestigationActionV2,
    *,
    value: str,
) -> TrustedToolExecutionBindingV2:
    return TrustedToolExecutionBindingV2(
        action_id=action.action_id,
        executor_binding="execute_governed_query_v2",
        executor=lambda: _finalization(
            value=value,
            event_id=f"audit-{action.action_id}",
        ),
    )


def _session(
    actions: tuple[AvailableInvestigationActionV2, ...],
    clarification_requirement=None,
):
    return build_investigation_session_from_delivery_v2(
        delivery=_seed_delivery(),
        available_actions=actions,
        clarification_requirement=clarification_requirement,
        budget_policy=InvestigationBudgetPolicyV2(
            max_investigation_steps=2,
            max_retries_per_action=0,
        ),
        session_policy=InvestigationSessionPolicyV2(
            max_rounds=2,
            max_total_investigation_steps=4,
        ),
    )


def test_one_action_executes_once_then_stops_without_fake_sufficiency() -> None:
    region = _action("drill_region", "region")
    session = _session((region,))

    def planner(state: InvestigationStateV2):
        return validate_planner_proposal_v2(
            state=state,
            proposal=PlannerProposalV2(
                decision_type=PlannerDecisionTypeV2.SELECT_TOOL,
                action_id="drill_region",
                rationale="继续检查区域分布。",
                supporting_evidence_ids=("ev_seed",),
            ),
        )

    result = run_one_investigation_step_v2(
        session=session,
        bindings={
            "drill_region": _binding(
                region,
                value="50",
            )
        },
        planner=planner,
        evidence_sufficient_after_step=False,
    )

    assert (
        result.status
        == Day89InvestigationRuntimeStatusV2.STOPPED
    )
    assert result.transition is not None
    assert (
        result.transition.control_decision.directive
        == LoopDirectiveV2.STOP
    )
    assert result.stop_status is not None
    assert (
        result.stop_status.stop_reason
        == InvestigationStopReasonV2.NO_LEGAL_ACTION
    )
    assert result.stop_status.evidence_sufficient is False
    assert len(
        result.session_after.loop_state.planner_state.insight.evidence
    ) == 2


def test_two_actions_executes_only_one_and_returns_replan_decision() -> None:
    channel = _action("drill_channel", "channel")
    region = _action("drill_region", "region")
    session = _session((channel, region))

    calls = {"count": 0}

    def planner(state: InvestigationStateV2):
        calls["count"] += 1

        if calls["count"] == 1:
            proposal = PlannerProposalV2(
                decision_type=PlannerDecisionTypeV2.SELECT_TOOL,
                action_id="drill_channel",
                rationale="先检查渠道。",
                supporting_evidence_ids=("ev_seed",),
            )
        else:
            newest = state.insight.evidence[-1].evidence_id
            proposal = PlannerProposalV2(
                decision_type=PlannerDecisionTypeV2.SELECT_TOOL,
                action_id="drill_region",
                rationale="基于新 Evidence 再检查区域。",
                supporting_evidence_ids=(newest,),
            )

        return validate_planner_proposal_v2(
            state=state,
            proposal=proposal,
        )

    executions = {"channel": 0, "region": 0}

    def channel_executor():
        executions["channel"] += 1
        return _finalization(
            value="60",
            event_id="audit-channel",
        )

    def region_executor():
        executions["region"] += 1
        return _finalization(
            value="40",
            event_id="audit-region",
        )

    result = run_one_investigation_step_v2(
        session=session,
        bindings={
            "drill_channel": TrustedToolExecutionBindingV2(
                action_id="drill_channel",
                executor_binding="execute_governed_query_v2",
                executor=channel_executor,
            ),
            "drill_region": TrustedToolExecutionBindingV2(
                action_id="drill_region",
                executor_binding="execute_governed_query_v2",
                executor=region_executor,
            ),
        },
        planner=planner,
        evidence_sufficient_after_step=False,
    )

    assert (
        result.status
        == Day89InvestigationRuntimeStatusV2.STEP_EXECUTED
    )
    assert result.transition is not None
    assert (
        result.transition.control_decision.directive
        == LoopDirectiveV2.REPLAN
    )
    assert result.next_planner_decision is not None
    assert (
        result.next_planner_decision.selected_action.action_id
        == "drill_region"
    )
    assert executions == {
        "channel": 1,
        "region": 0,
    }


def test_clarification_blocks_tool_execution() -> None:
    region = _action("drill_region", "region")
    requirement = ClarificationRequirementV2(
        source="trusted_precondition",
        reason="需要用户明确调查范围。",
    )
    session = _session(
        (region,),
        clarification_requirement=requirement,
    )

    executed = {"count": 0}

    def executor():
        executed["count"] += 1
        return _finalization(
            value="1",
            event_id="should-not-run",
        )

    def planner(state: InvestigationStateV2):
        return validate_planner_proposal_v2(
            state=state,
            proposal=PlannerProposalV2(
                decision_type=PlannerDecisionTypeV2.CLARIFY,
                action_id=None,
                clarification_prompt="请明确需要调查的范围。",
                rationale="可信前置条件要求先澄清。",
                supporting_evidence_ids=(),
            ),
        )

    result = run_one_investigation_step_v2(
        session=session,
        bindings={
            "drill_region": TrustedToolExecutionBindingV2(
                action_id="drill_region",
                executor_binding="execute_governed_query_v2",
                executor=executor,
            )
        },
        planner=planner,
    )

    assert (
        result.status
        == Day89InvestigationRuntimeStatusV2
        .CLARIFICATION_REQUIRED
    )
    assert executed["count"] == 0
    assert result.session_after == result.session_before


def test_seed_delivery_becomes_investigation_mode_without_changing_truth() -> None:
    delivery = _seed_delivery()
    region = _action("drill_region", "region")

    session = _session((region,))
    insight = session.loop_state.planner_state.insight

    assert insight.analysis_mode == AnalysisModeV2.INVESTIGATION
    assert insight.analysis_scope.metric_name == "gmv"
    assert insight.analysis_scope.analysis_window == WINDOW
    assert insight.analysis_scope.scope_summary == "authorized scope"
    assert insight.analysis_scope.result_grain is None
    assert insight.evidence == delivery.evidence_pack.insight.evidence


def test_runtime_does_not_auto_continue_session() -> None:
    import inspect
    from app.delivery import investigation_runtime_v2 as module

    source = inspect.getsource(
        module.run_one_investigation_step_v2
    )

    assert "continue_investigation_session_v2" not in source
    assert "user_requested_continue" not in source


TESTS = (
    test_one_action_executes_once_then_stops_without_fake_sufficiency,
    test_two_actions_executes_only_one_and_returns_replan_decision,
    test_clarification_blocks_tool_execution,
    test_seed_delivery_becomes_investigation_mode_without_changing_truth,
    test_runtime_does_not_auto_continue_session,
)


def run_acceptance() -> None:
    print("Day89 Investigation Runtime Orchestrator Acceptance")

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
