from __future__ import annotations

from datetime import date

from pydantic import ValidationError

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
from app.agents.investigation_planner_v2 import (
    AvailableInvestigationActionV2,
    BoundToolArgumentV2,
    ClarificationRequirementV2,
    InvestigationStateV2,
    PlannerDecisionTypeV2,
    PlannerProposalV2,
    validate_planner_proposal_v2,
)
from app.semantic_layer.time_comparison_contract_v2 import (
    AlignmentModeV2,
    ComparisonTypeV2,
    PeriodModeV2,
    TimeComparisonContractV2,
    TimeWindowReferenceV2,
)


def _comparison() -> TimeComparisonContractV2:
    return TimeComparisonContractV2(
        comparison_type=ComparisonTypeV2.YOY,
        period_mode=PeriodModeV2.COMPLETED_PERIOD,
        alignment_mode=AlignmentModeV2.CALENDAR_ALIGNED,
        current_window=TimeWindowReferenceV2(
            start_date=date(2025, 1, 1),
            end_date=date(2025, 12, 31),
        ),
        reference_window=TimeWindowReferenceV2(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
        ),
    )


def _insight() -> InsightContractV2:
    comparison = _comparison()
    return InsightContractV2(
        analysis_mode=AnalysisModeV2.INVESTIGATION,
        analysis_scope=AnalysisScopeV2(
            metric_name="gmv",
            analysis_window=comparison.current_window,
            comparison=comparison,
            result_grain="channel",
            scope_summary="authorized beauty_bi_v2 scope",
        ),
        detected_anomalies=(
            SupportedInsightStatementV2(
                statement="GMV YoY met the active anomaly policy.",
                evidence_ids=("ev_anomaly",),
            ),
        ),
        dimension_contributions=(
            SupportedInsightStatementV2(
                statement="Tmall is the largest negative channel contributor.",
                evidence_ids=("ev_contribution",),
            ),
        ),
        evidence=(
            EvidenceReferenceV2(
                evidence_id="ev_anomaly",
                source="deterministic_anomaly_detector_v2",
            ),
            EvidenceReferenceV2(
                evidence_id="ev_contribution",
                source="deterministic_contribution_analysis_v2",
            ),
        ),
    )


def _tool(name: str, purpose: str) -> ToolContractV2:
    return ToolContractV2(
        identity=ToolIdentityV2(
            name=name,
            version="dataset_v2",
            purpose=purpose,
        ),
        input_schema_name=f"{name.title().replace('_', '')}InputV2",
        output_schema_name=f"{name.title().replace('_', '')}ResultV2",
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
        executor_binding="execute_governed_analytics_v2",
    )


def _product_action() -> AvailableInvestigationActionV2:
    return AvailableInvestigationActionV2(
        action_id="drill_product_within_skincare",
        tool_contract=_tool(
            "drill_down_by_product",
            "Decompose a governed metric by product within an approved scope.",
        ),
        arguments=(
            BoundToolArgumentV2(
                name="category",
                value="skincare",
            ),
        ),
    )


def _region_action() -> AvailableInvestigationActionV2:
    return AvailableInvestigationActionV2(
        action_id="drill_region",
        tool_contract=_tool(
            "drill_down_by_region",
            "Decompose a governed metric by region.",
        ),
    )


def _state() -> InvestigationStateV2:
    return InvestigationStateV2(
        insight=_insight(),
        completed_action_ids=(
            "overall_gmv",
            "channel_contribution",
            "category_contribution",
        ),
        available_actions=(
            _product_action(),
            _region_action(),
        ),
    )


def test_valid_tool_selection_passes() -> None:
    decision = validate_planner_proposal_v2(
        state=_state(),
        proposal=PlannerProposalV2(
            decision_type=PlannerDecisionTypeV2.SELECT_TOOL,
            action_id="drill_product_within_skincare",
            rationale=(
                "The strongest current evidence is concentrated in skincare; "
                "product drill-down is the next untested bounded action."
            ),
            supporting_evidence_ids=("ev_contribution",),
        ),
    )

    assert decision.decision_type == PlannerDecisionTypeV2.SELECT_TOOL
    assert decision.selected_action is not None
    assert decision.selected_action.action_id == "drill_product_within_skincare"
    assert decision.selected_action.arguments[0].value == "skincare"


def test_model_cannot_supply_tool_arguments() -> None:
    try:
        PlannerProposalV2(
            decision_type=PlannerDecisionTypeV2.SELECT_TOOL,
            action_id="drill_product_within_skincare",
            rationale="Try to override arguments.",
            supporting_evidence_ids=("ev_contribution",),
            arguments={"category": "anything"},  # type: ignore[call-arg]
        )
    except ValidationError:
        return
    raise AssertionError("PlannerProposalV2 must forbid extra tool arguments.")


def test_unknown_action_fails_closed() -> None:
    try:
        validate_planner_proposal_v2(
            state=_state(),
            proposal=PlannerProposalV2(
                decision_type=PlannerDecisionTypeV2.SELECT_TOOL,
                action_id="unauthorized_product_detail",
                rationale="Invent a tool action.",
                supporting_evidence_ids=("ev_contribution",),
            ),
        )
    except ValueError:
        return
    raise AssertionError("Unknown action selection must fail closed.")


def test_completed_action_cannot_remain_available() -> None:
    try:
        InvestigationStateV2(
            insight=_insight(),
            completed_action_ids=("drill_region",),
            available_actions=(_region_action(),),
        )
    except ValidationError:
        return
    raise AssertionError("Completed action must not remain available.")


def test_duplicate_available_action_ids_fail() -> None:
    try:
        InvestigationStateV2(
            insight=_insight(),
            available_actions=(_region_action(), _region_action()),
        )
    except ValidationError:
        return
    raise AssertionError("Duplicate available action ids must fail.")


def test_duplicate_completed_action_ids_fail() -> None:
    try:
        InvestigationStateV2(
            insight=_insight(),
            completed_action_ids=("overall_gmv", "overall_gmv"),
            available_actions=(_region_action(),),
        )
    except ValidationError:
        return
    raise AssertionError("Duplicate completed action ids must fail.")


def test_select_tool_requires_evidence() -> None:
    try:
        PlannerProposalV2(
            decision_type=PlannerDecisionTypeV2.SELECT_TOOL,
            action_id="drill_region",
            rationale="No evidence supplied.",
        )
    except ValidationError:
        return
    raise AssertionError("SELECT_TOOL without evidence must fail.")


def test_unknown_evidence_reference_fails_closed() -> None:
    try:
        validate_planner_proposal_v2(
            state=_state(),
            proposal=PlannerProposalV2(
                decision_type=PlannerDecisionTypeV2.SELECT_TOOL,
                action_id="drill_region",
                rationale="Use nonexistent evidence.",
                supporting_evidence_ids=("ev_missing",),
            ),
        )
    except ValueError:
        return
    raise AssertionError("Unknown evidence reference must fail closed.")


def test_clarification_requirement_forces_clarify() -> None:
    state = InvestigationStateV2(
        insight=_insight(),
        available_actions=(_region_action(),),
        clarification_requirement=ClarificationRequirementV2(
            source="semantic_decision_v2",
            reason="metric ambiguity remains unresolved",
        ),
    )

    try:
        validate_planner_proposal_v2(
            state=state,
            proposal=PlannerProposalV2(
                decision_type=PlannerDecisionTypeV2.SELECT_TOOL,
                action_id="drill_region",
                rationale="Ignore the unresolved prerequisite.",
                supporting_evidence_ids=("ev_contribution",),
            ),
        )
    except ValueError:
        return
    raise AssertionError("Unresolved prerequisite must block tool selection.")


def test_clarify_passes_when_required() -> None:
    state = InvestigationStateV2(
        insight=_insight(),
        available_actions=(_region_action(),),
        clarification_requirement=ClarificationRequirementV2(
            source="semantic_decision_v2",
            reason="metric ambiguity remains unresolved",
        ),
    )

    decision = validate_planner_proposal_v2(
        state=state,
        proposal=PlannerProposalV2(
            decision_type=PlannerDecisionTypeV2.CLARIFY,
            clarification_prompt="Which sales metric do you want to investigate?",
            rationale="Semantic Decision reports unresolved metric ambiguity.",
        ),
    )

    assert decision.decision_type == PlannerDecisionTypeV2.CLARIFY
    assert decision.selected_action is None


def test_planner_cannot_invent_clarification() -> None:
    try:
        validate_planner_proposal_v2(
            state=_state(),
            proposal=PlannerProposalV2(
                decision_type=PlannerDecisionTypeV2.CLARIFY,
                clarification_prompt="Please clarify anyway.",
                rationale="Invent a clarification route.",
            ),
        )
    except ValueError:
        return
    raise AssertionError("Planner must not invent clarification requirements.")


def test_select_tool_cannot_carry_clarification_prompt() -> None:
    try:
        PlannerProposalV2(
            decision_type=PlannerDecisionTypeV2.SELECT_TOOL,
            action_id="drill_region",
            clarification_prompt="Also clarify this.",
            rationale="Mixed decision.",
            supporting_evidence_ids=("ev_contribution",),
        )
    except ValidationError:
        return
    raise AssertionError("Mixed SELECT_TOOL/CLARIFY proposal must fail.")


def test_clarify_cannot_carry_action_id() -> None:
    try:
        PlannerProposalV2(
            decision_type=PlannerDecisionTypeV2.CLARIFY,
            action_id="drill_region",
            clarification_prompt="Which metric?",
            rationale="Mixed decision.",
        )
    except ValidationError:
        return
    raise AssertionError("CLARIFY proposal with action_id must fail.")


def test_fact_mode_cannot_be_planner_state() -> None:
    comparison = _comparison()
    fact_insight = InsightContractV2(
        analysis_mode=AnalysisModeV2.FACT,
        analysis_scope=AnalysisScopeV2(
            metric_name="gmv",
            analysis_window=comparison.current_window,
        ),
    )

    try:
        InvestigationStateV2(
            insight=fact_insight,
            available_actions=(_region_action(),),
        )
    except ValidationError:
        return
    raise AssertionError("FACT mode must not enter investigation planner state.")


def test_action_argument_names_must_be_unique() -> None:
    try:
        AvailableInvestigationActionV2(
            action_id="bad_action",
            tool_contract=_tool("drill_down_by_product", "Test tool."),
            arguments=(
                BoundToolArgumentV2(name="category", value="skincare"),
                BoundToolArgumentV2(name="category", value="makeup"),
            ),
        )
    except ValidationError:
        return
    raise AssertionError("Duplicate bound argument names must fail.")


TESTS = (
    test_valid_tool_selection_passes,
    test_model_cannot_supply_tool_arguments,
    test_unknown_action_fails_closed,
    test_completed_action_cannot_remain_available,
    test_duplicate_available_action_ids_fail,
    test_duplicate_completed_action_ids_fail,
    test_select_tool_requires_evidence,
    test_unknown_evidence_reference_fails_closed,
    test_clarification_requirement_forces_clarify,
    test_clarify_passes_when_required,
    test_planner_cannot_invent_clarification,
    test_select_tool_cannot_carry_clarification_prompt,
    test_clarify_cannot_carry_action_id,
    test_fact_mode_cannot_be_planner_state,
    test_action_argument_names_must_be_unique,
)


def run_acceptance() -> None:
    passed = 0
    failed = 0

    print("=" * 80)
    print("Day85 Investigation Planner V2 Acceptance")

    for test in TESTS:
        try:
            test()
            passed += 1
            print(f"[PASS] {test.__name__}")
        except Exception as exc:
            failed += 1
            print(f"[FAIL] {test.__name__}: {exc}")

    print("=" * 80)
    print("Day85 Investigation Planner V2 Acceptance Summary")
    print(f"Total: {len(TESTS)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    run_acceptance()
