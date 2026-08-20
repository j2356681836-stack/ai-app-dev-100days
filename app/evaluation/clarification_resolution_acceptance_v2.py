from __future__ import annotations

from datetime import date

from app.agents.clarification_resolution_v2 import (
    ClarificationResolutionStatusV2,
    ClarificationResponseV2,
    build_day89_direction_clarification_requirement_v2,
    build_day89_direction_resolution_contract_v2,
    plan_day89_direction_clarification_v2,
    plan_day89_resolved_single_action_v2,
    resolve_clarification_response_v2,
)
from app.agents.investigation_contracts_v2 import (
    AnalysisModeV2,
    AnalysisScopeV2,
    EvidenceReferenceV2,
    InsightContractV2,
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
    TimeWindowReferenceV2,
)


def _tool(name: str) -> ToolContractV2:
    return ToolContractV2(
        identity=ToolIdentityV2(
            name=name,
            version="dataset_v2",
            purpose=f"Trusted test tool {name}.",
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
    *,
    action_id: str,
    plan_name: str,
    grain: str,
) -> AvailableInvestigationActionV2:
    return AvailableInvestigationActionV2(
        action_id=action_id,
        tool_contract=_tool(f"governed_gmv_{grain}_query"),
        arguments=(
            BoundToolArgumentV2(
                name="metric_name",
                value="gmv",
            ),
            BoundToolArgumentV2(
                name="query_plan_name",
                value=plan_name,
            ),
            BoundToolArgumentV2(
                name="result_grain",
                value=grain,
            ),
        ),
    )


def _state(
    requirement: ClarificationRequirementV2 | None = None,
) -> InvestigationStateV2:
    insight = InsightContractV2(
        analysis_mode=AnalysisModeV2.INVESTIGATION,
        analysis_scope=AnalysisScopeV2(
            metric_name="gmv",
            analysis_window=TimeWindowReferenceV2(
                start_date=date(2025, 1, 1),
                end_date=date(2025, 12, 31),
            ),
            result_grain=None,
            scope_summary="trusted test scope",
        ),
        evidence=(
            EvidenceReferenceV2(
                evidence_id="ev_seed",
                source="tool:governed_gmv_channel_query@dataset_v2",
            ),
        ),
    )

    return InvestigationStateV2(
        insight=insight,
        completed_action_ids=("drill_channel",),
        available_actions=(
            _action(
                action_id="drill_region",
                plan_name="gmv_region_v2",
                grain="region",
            ),
            _action(
                action_id="drill_category",
                plan_name="gmv_category_v2",
                grain="category",
            ),
        ),
        clarification_requirement=requirement,
    )


def test_unresolved_requirement_still_forces_clarify() -> None:
    state = _state(
        build_day89_direction_clarification_requirement_v2()
    )

    try:
        validate_planner_proposal_v2(
            state=state,
            proposal=PlannerProposalV2(
                decision_type=PlannerDecisionTypeV2.SELECT_TOOL,
                action_id="drill_region",
                rationale="不能跳过 trusted prerequisite。",
                supporting_evidence_ids=("ev_seed",),
            ),
        )
    except ValueError:
        return

    raise AssertionError(
        "Unresolved clarification 必须继续阻断 Tool selection。"
    )


def test_valid_region_choice_resolves_and_filters_actions() -> None:
    state = _state(
        build_day89_direction_clarification_requirement_v2()
    )
    contract = build_day89_direction_resolution_contract_v2()

    result = resolve_clarification_response_v2(
        state=state,
        contract=contract,
        response=ClarificationResponseV2(
            choice_id="region"
        ),
    )

    assert result.status == ClarificationResolutionStatusV2.RESOLVED
    assert result.resolved_state is not None
    assert result.resolved_state.clarification_requirement is None
    assert tuple(
        item.action_id
        for item in result.resolved_state.available_actions
    ) == ("drill_region",)


def test_resolved_state_preserves_exact_prebound_action() -> None:
    state = _state(
        build_day89_direction_clarification_requirement_v2()
    )
    original_region = state.available_actions[0]

    result = resolve_clarification_response_v2(
        state=state,
        contract=build_day89_direction_resolution_contract_v2(),
        response=ClarificationResponseV2(choice_id="region"),
    )

    assert result.resolved_state is not None
    assert result.resolved_state.available_actions == (
        original_region,
    )


def test_resolved_state_allows_planner_only_selected_action() -> None:
    state = _state(
        build_day89_direction_clarification_requirement_v2()
    )

    resolution = resolve_clarification_response_v2(
        state=state,
        contract=build_day89_direction_resolution_contract_v2(),
        response=ClarificationResponseV2(choice_id="category"),
    )
    assert resolution.resolved_state is not None

    decision = validate_planner_proposal_v2(
        state=resolution.resolved_state,
        proposal=PlannerProposalV2(
            decision_type=PlannerDecisionTypeV2.SELECT_TOOL,
            action_id="drill_category",
            rationale="用户明确选择了品类调查方向。",
            supporting_evidence_ids=("ev_seed",),
        ),
    )

    assert decision.selected_action is not None
    assert decision.selected_action.action_id == "drill_category"


def test_invalid_choice_remains_unresolved_without_state_mutation() -> None:
    state = _state(
        build_day89_direction_clarification_requirement_v2()
    )

    result = resolve_clarification_response_v2(
        state=state,
        contract=build_day89_direction_resolution_contract_v2(),
        response=ClarificationResponseV2(
            choice_id="invented_dimension"
        ),
    )

    assert result.status == ClarificationResolutionStatusV2.UNRESOLVED
    assert result.resolved_state is None
    assert state.clarification_requirement is not None
    assert len(state.available_actions) == 2


def test_semantic_ambiguity_is_not_falsely_resolved() -> None:
    state = _state(
        ClarificationRequirementV2(
            source="semantic_decision_v2",
            reason="metric ambiguity remains unresolved",
        )
    )

    result = resolve_clarification_response_v2(
        state=state,
        contract=build_day89_direction_resolution_contract_v2(),
        response=ClarificationResponseV2(choice_id="region"),
    )

    assert (
        result.status
        == ClarificationResolutionStatusV2.CONTRACT_MISMATCH
    )
    assert result.resolved_state is None


def test_contract_cannot_expand_to_action_missing_from_state() -> None:
    state = _state(
        build_day89_direction_clarification_requirement_v2()
    ).model_copy(
        update={
            "available_actions": (
                _state().available_actions[0],
            )
        }
    )

    result = resolve_clarification_response_v2(
        state=state,
        contract=build_day89_direction_resolution_contract_v2(),
        response=ClarificationResponseV2(choice_id="category"),
    )

    assert (
        result.status
        == ClarificationResolutionStatusV2.CONTRACT_MISMATCH
    )
    assert result.resolved_state is None


def test_free_text_is_not_an_accepted_resolution_payload() -> None:
    try:
        ClarificationResponseV2(
            choice_id="",
            free_text="我想看看区域",  # type: ignore[call-arg]
        )
    except Exception:
        return

    raise AssertionError(
        "Day89 first resolver 不应该接受任意 free_text payload。"
    )


def test_direction_gate_planner_is_deterministic_clarify() -> None:
    state = _state(
        build_day89_direction_clarification_requirement_v2()
    )

    decision = plan_day89_direction_clarification_v2(state)

    assert (
        decision.decision_type
        == PlannerDecisionTypeV2.CLARIFY
    )
    assert decision.selected_action is None
    assert decision.clarification_prompt is not None


def test_resolved_single_action_planner_honors_user_choice() -> None:
    state = _state(
        build_day89_direction_clarification_requirement_v2()
    )

    resolution = resolve_clarification_response_v2(
        state=state,
        contract=build_day89_direction_resolution_contract_v2(),
        response=ClarificationResponseV2(choice_id="category"),
    )

    assert resolution.resolved_state is not None

    decision = plan_day89_resolved_single_action_v2(
        resolution.resolved_state
    )

    assert decision.selected_action is not None
    assert decision.selected_action.action_id == "drill_category"


TESTS = (
    test_unresolved_requirement_still_forces_clarify,
    test_valid_region_choice_resolves_and_filters_actions,
    test_resolved_state_preserves_exact_prebound_action,
    test_resolved_state_allows_planner_only_selected_action,
    test_invalid_choice_remains_unresolved_without_state_mutation,
    test_semantic_ambiguity_is_not_falsely_resolved,
    test_contract_cannot_expand_to_action_missing_from_state,
    test_free_text_is_not_an_accepted_resolution_payload,
    test_direction_gate_planner_is_deterministic_clarify,
    test_resolved_single_action_planner_honors_user_choice,
)


def run_acceptance() -> None:
    print("Day89 Runtime HITL Clarification Resolution Acceptance")

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
