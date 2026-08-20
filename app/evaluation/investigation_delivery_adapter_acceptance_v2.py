from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.agents.evidence_pack_delivery_v2 import (
    EvidenceSufficiencyStatusV2,
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
from app.agents.investigation_contracts_v2 import (
    AnalysisModeV2,
    AnalysisScopeV2,
    EvidenceReferenceV2,
    InsightContractV2,
    SupportedInsightStatementV2,
    ToolContractV2,
    ToolFailureCodeV2,
    ToolIdentityV2,
)
from app.agents.investigation_loop_v2 import (
    InvestigationBudgetPolicyV2,
    InvestigationSessionPolicyV2,
    InvestigationStopReasonV2,
)
from app.agents.investigation_planner_v2 import (
    AvailableInvestigationActionV2,
    BoundToolArgumentV2,
    ClarificationRequirementV2,
    InvestigationStateV2,
    PlannerDecisionTypeV2,
    PlannerProposalV2,
    validate_planner_proposal_v2,
)
from app.agents.investigation_tool_executor_v2 import (
    TrustedToolExecutionBindingV2,
)
from app.delivery.decision_console_runtime_v2 import (
    build_day89_local_access_context_v2,
)
from app.delivery.decision_console_view_v2 import (
    build_decision_console_view_v2,
)
from app.delivery.executive_decision_brief_v2 import (
    build_executive_decision_brief_preview_v2,
)
from app.delivery.investigation_delivery_adapter_v2 import (
    InvestigationDeliveryStatusV2,
    build_investigation_step_delivery_v2,
)
from app.delivery.investigation_runtime_v2 import (
    Day89GovernedQueryEvidenceContextV2,
    build_investigation_session_from_delivery_v2,
    run_one_investigation_step_v2,
)
from app.delivery.runtime_delivery_bridge_v2 import (
    RuntimeDeliveryBridgeResultV2,
    RuntimeDeliveryBridgeStatusV2,
)
from app.governance.governed_finalization import (
    FinalizationOutcome,
    FinalizationReason,
    GovernedFinalizationResult,
)
from app.governance.governed_planning_envelope_v2 import (
    GovernedPlanningStatusV2,
    build_governed_planning_envelope_v2,
)
from app.semantic_layer.query_plan_compiler_v2 import (
    QueryPlanCompileStatusV2,
    compile_governed_query_plan_v2,
)
from app.semantic_layer.query_plan_v2_loader import (
    get_query_plan_v2_by_name,
)
from app.semantic_layer.time_comparison_contract_v2 import (
    TimeWindowReferenceV2,
)
from app.semantic_layer.time_window_resolver_v2 import (
    resolve_time_window_v2,
)


WINDOW = TimeWindowReferenceV2(
    start_date=date(2025, 1, 1),
    end_date=date(2025, 12, 31),
)


def _seed_record() -> EvidenceRecordV2:
    return EvidenceRecordV2(
        reference=EvidenceReferenceV2(
            evidence_id="ev_seed_channel",
            source="tool:governed_gmv_channel_query@dataset_v2",
            description="Seed channel GMV evidence。",
        ),
        evidence_type=EvidenceTypeV2.GOVERNED_QUERY_RESULT,
        provenance=GovernedEvidenceProvenanceV2(
            dataset_name="beauty_bi_v2",
            target_schema="beauty_bi_v2",
            metric_name="gmv",
            result_grain="channel",
            analysis_window=WINDOW,
            scope_summary="acceptance authorized scope",
            plan_name="gmv_channel_v2",
            query_plan_fingerprint="seed-qpf",
            envelope_fingerprint="seed-env",
            compiled_contract_fingerprint="seed-compiled",
            sql_fingerprint="seed-sql",
            time_binding_fingerprint="seed-time",
            scope_binding_fingerprint="seed-scope",
            tool_name="governed_gmv_channel_query",
            tool_version="dataset_v2",
            audit_event_id="seed-audit",
            audit_event_fingerprint="seed-audit-fp",
            audit_record_hash="seed-audit-hash",
            finalization_contract_version="governed_finalization_v1",
        ),
        protected_result=ProtectedResultV2(
            field_names=("channel_name", "gmv"),
            rows=(
                {
                    "channel_name": "天猫",
                    "gmv": Decimal("100"),
                },
            ),
            row_count=1,
        ),
    )


def _metric_definition() -> MetricDefinitionSnapshotV2:
    return MetricDefinitionSnapshotV2(
        metadata_version="beauty_bi_v2",
        dataset_name="beauty_bi_v2",
        metric_name="gmv",
        chinese_name="销售额",
        grain="paid_order_items",
        definition="按 paid_at 归属的销售额。",
        formula="SUM(item_paid_amount)",
        filters=("paid_at IS NOT NULL",),
        metric_fingerprint="a" * 64,
    )


def _seed_result() -> RuntimeDeliveryBridgeResultV2:
    record = _seed_record()

    scope = AnalysisScopeV2(
        metric_name="gmv",
        analysis_window=WINDOW,
        result_grain="channel",
        scope_summary="acceptance authorized scope",
    )

    insight = InsightContractV2(
        analysis_mode=AnalysisModeV2.FACT,
        analysis_scope=scope,
        confirmed_facts=(
            SupportedInsightStatementV2(
                statement="2025 年渠道 GMV Seed 已形成可信 Evidence。",
                evidence_ids=(record.reference.evidence_id,),
            ),
        ),
        evidence=(record.reference,),
    )

    pack = EvidencePackV2(
        pack_id="seed-pack",
        analysis_scope=scope,
        insight=insight,
        evidence_records=(record,),
    )

    delivery = assemble_evidence_pack_delivery_v2(
        evidence_pack=pack,
        metric_definition=_metric_definition(),
    )

    console = build_decision_console_view_v2(
        delivery=delivery,
        breakdown_evidence_id=record.reference.evidence_id,
    )

    brief = build_executive_decision_brief_preview_v2(
        request_subject="seed",
        delivery=delivery,
        console_view=console,
    )

    return RuntimeDeliveryBridgeResultV2(
        status=RuntimeDeliveryBridgeStatusV2.READY,
        message="seed ready",
        safe_runtime_result={"success": True},
        delivery=delivery,
        console_view=console,
        executive_brief=brief,
    )


def _region_action() -> AvailableInvestigationActionV2:
    tool = ToolContractV2(
        identity=ToolIdentityV2(
            name="governed_gmv_region_query",
            version="dataset_v2",
            purpose="查询区域 GMV。",
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

    return AvailableInvestigationActionV2(
        action_id="drill_region",
        tool_contract=tool,
        arguments=(
            BoundToolArgumentV2(
                name="metric_name",
                value="gmv",
            ),
            BoundToolArgumentV2(
                name="query_plan_name",
                value="gmv_region_v2",
            ),
            BoundToolArgumentV2(
                name="result_grain",
                value="region",
            ),
        ),
    )


def _prepared_governed_context(
    action: AvailableInvestigationActionV2,
) -> Day89GovernedQueryEvidenceContextV2:
    plan = get_query_plan_v2_by_name("gmv_region_v2")
    assert plan is not None

    resolution = resolve_time_window_v2(
        "2025年各区域GMV是多少？",
        reference_date=date(2026, 8, 19),
    )

    context = build_day89_local_access_context_v2(
        request_id="day89-investigation-delivery-acceptance",
    )

    planning = build_governed_planning_envelope_v2(
        context=context,
        plan=plan,
        time_resolution=resolution,
    )

    assert (
        planning.status
        == GovernedPlanningStatusV2.READY_FOR_COMPILATION
    )
    assert planning.envelope is not None

    compilation = compile_governed_query_plan_v2(
        planning.envelope
    )

    assert (
        compilation.status
        == QueryPlanCompileStatusV2.COMPILED
    )
    assert compilation.contract is not None

    finalization = GovernedFinalizationResult(
        success=True,
        outcome=FinalizationOutcome.SUCCEEDED,
        reason_code=FinalizationReason.ALLOWED,
        message="released",
        rows=(
            {
                "region_name": "上海",
                "gmv": Decimal("50"),
            },
        ),
        row_count=1,
        audit_persisted=True,
        audit_event_id="region-audit",
        audit_event_fingerprint="region-audit-fp",
        audit_sequence_number=2,
        audit_record_hash="region-audit-hash",
    )

    return Day89GovernedQueryEvidenceContextV2(
        action_id=action.action_id,
        tool_contract=action.tool_contract,
        envelope=planning.envelope,
        compiled=compilation.contract,
        finalization=finalization,
    )


def _executed_step(*, with_context: bool = True):
    seed = _seed_result()
    assert seed.delivery is not None

    action = _region_action()
    session = build_investigation_session_from_delivery_v2(
        delivery=seed.delivery,
        available_actions=(action,),
        budget_policy=InvestigationBudgetPolicyV2(
            max_investigation_steps=2,
            max_retries_per_action=0,
        ),
        session_policy=InvestigationSessionPolicyV2(
            max_rounds=2,
            max_total_investigation_steps=4,
        ),
    )

    governed_context = _prepared_governed_context(action)

    binding = TrustedToolExecutionBindingV2(
        action_id=action.action_id,
        executor_binding=action.tool_contract.executor_binding,
        executor=lambda: governed_context.finalization,
    )

    def planner(state: InvestigationStateV2):
        supporting_id = state.insight.evidence[-1].evidence_id

        return validate_planner_proposal_v2(
            state=state,
            proposal=PlannerProposalV2(
                decision_type=PlannerDecisionTypeV2.SELECT_TOOL,
                action_id="drill_region",
                rationale="Use remaining legal region path。",
                supporting_evidence_ids=(supporting_id,),
            ),
        )

    step = run_one_investigation_step_v2(
        session=session,
        bindings={"drill_region": binding},
        planner=planner,
        evidence_sufficient_after_step=False,
    )

    if with_context:
        step = step.model_copy(
            update={
                "governed_query_context": governed_context,
            }
        )

    return seed, step


def _clarification_step():
    seed = _seed_result()
    assert seed.delivery is not None

    action = _region_action()

    session = build_investigation_session_from_delivery_v2(
        delivery=seed.delivery,
        available_actions=(action,),
        clarification_requirement=ClarificationRequirementV2(
            source="semantic_decision_v2",
            reason="需要用户先确认调查范围。",
        ),
        budget_policy=InvestigationBudgetPolicyV2(
            max_investigation_steps=2,
            max_retries_per_action=0,
        ),
        session_policy=InvestigationSessionPolicyV2(
            max_rounds=2,
            max_total_investigation_steps=4,
        ),
    )

    def planner(state: InvestigationStateV2):
        return validate_planner_proposal_v2(
            state=state,
            proposal=PlannerProposalV2(
                decision_type=PlannerDecisionTypeV2.CLARIFY,
                clarification_prompt="请确认是否继续调查区域维度？",
                rationale="可信前置条件尚未解决。",
            ),
        )

    step = run_one_investigation_step_v2(
        session=session,
        bindings={},
        planner=planner,
        evidence_sufficient_after_step=False,
    )

    return seed, step


def test_query_and_observation_evidence_are_both_delivered() -> None:
    seed, step = _executed_step()

    result = build_investigation_step_delivery_v2(
        seed_result=seed,
        runtime_step=step,
        request_subject="2025 年 GMV 调查",
    )

    assert result.status == InvestigationDeliveryStatusV2.READY
    assert result.delivery is not None

    types = [
        record.evidence_type
        for record in result.delivery.evidence_pack.evidence_records
    ]

    assert types.count(EvidenceTypeV2.GOVERNED_QUERY_RESULT) == 2
    assert (
        types.count(EvidenceTypeV2.INVESTIGATION_OBSERVATION)
        == 1
    )


def test_observation_parent_and_console_trace_are_linked() -> None:
    seed, step = _executed_step()

    result = build_investigation_step_delivery_v2(
        seed_result=seed,
        runtime_step=step,
        request_subject="2025 年 GMV 调查",
    )

    assert result.delivery is not None
    assert result.console_view is not None
    assert step.execution_result is not None
    assert step.execution_result.evidence_reference is not None

    query_id = step.execution_result.evidence_reference.evidence_id

    observation_record = next(
        record
        for record in result.delivery.evidence_pack.evidence_records
        if (
            record.evidence_type
            == EvidenceTypeV2.INVESTIGATION_OBSERVATION
        )
    )

    assert observation_record.parent_evidence_ids == (query_id,)

    assert len(result.console_view.investigation_trace) == 1
    trace = result.console_view.investigation_trace[0]
    assert trace.selected_action_id == "drill_region"
    assert (
        trace.observation_evidence_id
        == observation_record.reference.evidence_id
    )


def test_insufficient_stop_remains_partial() -> None:
    seed, step = _executed_step()

    result = build_investigation_step_delivery_v2(
        seed_result=seed,
        runtime_step=step,
        request_subject="2025 年 GMV 调查",
    )

    assert result.delivery is not None
    assert result.console_view is not None

    assert (
        result.delivery.sufficiency.status
        == EvidenceSufficiencyStatusV2.PARTIAL
    )
    assert result.delivery.evidence_pack.insight.unknowns

    control = result.console_view.runtime_control
    assert control is not None
    assert control.evidence_sufficient is False
    assert (
        control.stop_reason
        == InvestigationStopReasonV2.NO_LEGAL_ACTION
    )


def test_new_query_evidence_is_not_auto_promoted_to_fact() -> None:
    seed, step = _executed_step()

    result = build_investigation_step_delivery_v2(
        seed_result=seed,
        runtime_step=step,
        request_subject="2025 年 GMV 调查",
    )

    assert result.delivery is not None
    assert seed.delivery is not None

    assert (
        result.delivery.evidence_pack.insight.confirmed_facts
        == seed.delivery.evidence_pack.insight.confirmed_facts
    )


def test_clarification_builds_hitl_view_without_tool_evidence() -> None:
    seed, step = _clarification_step()

    result = build_investigation_step_delivery_v2(
        seed_result=seed,
        runtime_step=step,
        request_subject="2025 年 GMV 调查",
    )

    assert (
        result.status
        == InvestigationDeliveryStatusV2.CLARIFICATION_READY
    )
    assert result.delivery is not None
    assert result.console_view is not None

    assert len(result.delivery.evidence_pack.evidence_records) == 1
    assert result.console_view.clarification is not None
    assert result.console_view.clarification.requires_user_response
    assert result.console_view.clarification.tool_execution_blocked
    assert not result.console_view.investigation_trace


def test_missing_governed_context_fails_closed() -> None:
    seed, step = _executed_step(with_context=False)

    result = build_investigation_step_delivery_v2(
        seed_result=seed,
        runtime_step=step,
        request_subject="2025 年 GMV 调查",
    )

    assert (
        result.status
        == InvestigationDeliveryStatusV2.EVIDENCE_BUILD_FAILED
    )
    assert result.delivery is None
    assert result.console_view is None
    assert result.executive_brief is None


TESTS = (
    test_query_and_observation_evidence_are_both_delivered,
    test_observation_parent_and_console_trace_are_linked,
    test_insufficient_stop_remains_partial,
    test_new_query_evidence_is_not_auto_promoted_to_fact,
    test_clarification_builds_hitl_view_without_tool_evidence,
    test_missing_governed_context_fails_closed,
)


def run_acceptance() -> None:
    print("Day89 Investigation Delivery Adapter Acceptance")

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
