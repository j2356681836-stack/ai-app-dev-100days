from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any

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
from app.agents.investigation_planner_llm_v2 import (
    build_planner_context_v2,
    build_planner_messages_v2,
    parse_planner_proposal_v2,
    plan_next_investigation_step_v2,
)
from app.agents.investigation_planner_v2 import (
    AvailableInvestigationActionV2,
    BoundToolArgumentV2,
    ClarificationRequirementV2,
    InvestigationStateV2,
    PlannerDecisionTypeV2,
)
from app.semantic_layer.time_comparison_contract_v2 import (
    AlignmentModeV2,
    ComparisonTypeV2,
    PeriodModeV2,
    TimeComparisonContractV2,
    TimeWindowReferenceV2,
)


@dataclass
class _FakeMessage:
    content: str


@dataclass
class _FakeChoice:
    message: _FakeMessage


@dataclass
class _FakeResponse:
    choices: list[_FakeChoice]


class _FakeCompletions:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> _FakeResponse:
        self.calls.append(kwargs)
        return _FakeResponse(
            choices=[
                _FakeChoice(
                    message=_FakeMessage(content=self.content),
                )
            ]
        )


class _FakeChat:
    def __init__(self, content: str) -> None:
        self.completions = _FakeCompletions(content)


class _FakeClient:
    def __init__(self, content: str) -> None:
        self.chat = _FakeChat(content)


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
            scope_summary="authorized_scope_only",
        ),
        detected_anomalies=(
            SupportedInsightStatementV2(
                statement="GMV YoY is below the active anomaly threshold.",
                evidence_ids=("ev_anomaly",),
            ),
        ),
        dimension_contributions=(
            SupportedInsightStatementV2(
                statement=(
                    "Skincare is the strongest released negative category "
                    "contribution in the current decomposition."
                ),
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


def _select_json(
    *,
    action_id: str = "drill_product_within_skincare",
    evidence_id: str = "ev_contribution",
) -> str:
    return json.dumps(
        {
            "decision_type": "select_tool",
            "action_id": action_id,
            "clarification_prompt": None,
            "rationale": "护肤是当前已释放证据中最强的负向贡献，因此下一步应在护肤范围内继续按商品下钻。",
            "supporting_evidence_ids": [evidence_id],
        }
    )


def test_valid_llm_tool_selection_is_constrained() -> None:
    client = _FakeClient(_select_json())

    decision = plan_next_investigation_step_v2(
        state=_state(),
        model="planner-test-model",
        client=client,
    )

    assert decision.decision_type == PlannerDecisionTypeV2.SELECT_TOOL
    assert decision.selected_action is not None
    assert decision.selected_action.action_id == "drill_product_within_skincare"
    assert decision.selected_action.arguments[0].value == "skincare"


def test_transport_uses_temperature_zero_and_requested_model() -> None:
    client = _FakeClient(_select_json())

    plan_next_investigation_step_v2(
        state=_state(),
        model="planner-test-model",
        client=client,
    )

    call = client.chat.completions.calls[0]
    assert call["model"] == "planner-test-model"
    assert call["temperature"] == 0
    assert len(call["messages"]) == 2


def test_model_context_exposes_only_approved_actions() -> None:
    context = build_planner_context_v2(_state())
    actions = context["investigation_context"]["available_actions"]

    assert [action["action_id"] for action in actions] == [
        "drill_product_within_skincare",
        "drill_region",
    ]
    serialized = json.dumps(context)
    assert "unauthorized_product_detail" not in serialized


def test_model_context_does_not_expose_executor_or_permission_internals() -> None:
    serialized = json.dumps(build_planner_context_v2(_state()))

    assert "execute_governed_analytics_v2" not in serialized
    assert "governed_execution_policy_v2" not in serialized
    assert "metric_access" not in serialized
    assert "data_scope" not in serialized


def test_prompt_forbids_sql_formula_and_causal_claims() -> None:
    system_prompt = build_planner_messages_v2(_state())[0]["content"]

    assert "Never generate SQL" in system_prompt
    assert "metric formulas" in system_prompt
    assert "Do not claim causality" in system_prompt
    assert "Simplified Chinese" in system_prompt


def test_unknown_action_from_llm_fails_closed() -> None:
    client = _FakeClient(
        _select_json(action_id="unauthorized_product_detail")
    )

    try:
        plan_next_investigation_step_v2(
            state=_state(),
            client=client,
        )
    except ValueError:
        return
    raise AssertionError("Unknown LLM action must fail closed.")


def test_unknown_evidence_from_llm_fails_closed() -> None:
    client = _FakeClient(
        _select_json(evidence_id="ev_not_present")
    )

    try:
        plan_next_investigation_step_v2(
            state=_state(),
            client=client,
        )
    except ValueError:
        return
    raise AssertionError("Unknown LLM evidence id must fail closed.")


def test_malformed_json_fails_closed() -> None:
    client = _FakeClient("not-json")

    try:
        plan_next_investigation_step_v2(
            state=_state(),
            client=client,
        )
    except ValueError:
        return
    raise AssertionError("Malformed planner JSON must fail closed.")


def test_markdown_fenced_json_is_not_silently_repaired() -> None:
    client = _FakeClient(f"```json\n{_select_json()}\n```")

    try:
        plan_next_investigation_step_v2(
            state=_state(),
            client=client,
        )
    except ValueError:
        return
    raise AssertionError("Day85 must not silently repair fenced JSON.")


def test_extra_model_field_raw_sql_fails_closed() -> None:
    payload = json.loads(_select_json())
    payload["raw_sql"] = "SELECT * FROM anything"
    client = _FakeClient(json.dumps(payload))

    try:
        plan_next_investigation_step_v2(
            state=_state(),
            client=client,
        )
    except ValueError:
        return
    raise AssertionError("Extra raw_sql field must fail strict parsing.")


def test_empty_llm_response_fails_closed() -> None:
    client = _FakeClient("   ")

    try:
        plan_next_investigation_step_v2(
            state=_state(),
            client=client,
        )
    except ValueError:
        return
    raise AssertionError("Empty planner response must fail closed.")


def test_english_user_facing_rationale_fails_language_contract() -> None:
    payload = json.loads(_select_json())
    payload["rationale"] = (
        "Skincare is the strongest negative contributor, so drill down by product."
    )

    try:
        plan_next_investigation_step_v2(
            state=_state(),
            client=_FakeClient(json.dumps(payload)),
        )
    except ValueError:
        return
    raise AssertionError(
        "English-only user-facing rationale must fail the Chinese language contract."
    )


def test_clarification_requirement_allows_llm_clarify() -> None:
    state = InvestigationStateV2(
        insight=_insight(),
        available_actions=(_region_action(),),
        clarification_requirement=ClarificationRequirementV2(
            source="semantic_decision_v2",
            reason="metric ambiguity remains unresolved",
        ),
    )
    response = json.dumps(
        {
            "decision_type": "clarify",
            "action_id": None,
            "clarification_prompt": "你希望继续调查哪一个销售指标？",
            "rationale": "可信语义前置条件仍存在指标歧义，因此必须先由用户澄清。",
            "supporting_evidence_ids": [],
        }
    )

    decision = plan_next_investigation_step_v2(
        state=state,
        client=_FakeClient(response),
    )

    assert decision.decision_type == PlannerDecisionTypeV2.CLARIFY
    assert decision.selected_action is None


def test_llm_cannot_invent_clarification_without_requirement() -> None:
    response = json.dumps(
        {
            "decision_type": "clarify",
            "action_id": None,
            "clarification_prompt": "请澄清。",
            "rationale": "模型自行制造了并不存在的歧义。",
            "supporting_evidence_ids": [],
        }
    )

    try:
        plan_next_investigation_step_v2(
            state=_state(),
            client=_FakeClient(response),
        )
    except ValueError:
        return
    raise AssertionError("LLM must not invent clarification.")


def test_no_action_without_clarification_fails_before_llm_call() -> None:
    state = InvestigationStateV2(
        insight=_insight(),
        available_actions=(),
    )
    client = _FakeClient(_select_json())

    try:
        plan_next_investigation_step_v2(
            state=state,
            client=client,
        )
    except ValueError:
        assert not client.chat.completions.calls
        return
    raise AssertionError("No-action state must fail before model invocation.")


def test_parse_returns_strict_planner_proposal() -> None:
    proposal = parse_planner_proposal_v2(_select_json())

    assert proposal.decision_type == PlannerDecisionTypeV2.SELECT_TOOL
    assert proposal.action_id == "drill_product_within_skincare"


TESTS = (
    test_valid_llm_tool_selection_is_constrained,
    test_transport_uses_temperature_zero_and_requested_model,
    test_model_context_exposes_only_approved_actions,
    test_model_context_does_not_expose_executor_or_permission_internals,
    test_prompt_forbids_sql_formula_and_causal_claims,
    test_unknown_action_from_llm_fails_closed,
    test_unknown_evidence_from_llm_fails_closed,
    test_malformed_json_fails_closed,
    test_markdown_fenced_json_is_not_silently_repaired,
    test_extra_model_field_raw_sql_fails_closed,
    test_empty_llm_response_fails_closed,
    test_english_user_facing_rationale_fails_language_contract,
    test_clarification_requirement_allows_llm_clarify,
    test_llm_cannot_invent_clarification_without_requirement,
    test_no_action_without_clarification_fails_before_llm_call,
    test_parse_returns_strict_planner_proposal,
)


def run_acceptance() -> None:
    passed = 0
    failed = 0

    print("=" * 80)
    print("Day85 Investigation Planner LLM V2 Acceptance")

    for test in TESTS:
        try:
            test()
            passed += 1
            print(f"[PASS] {test.__name__}")
        except Exception as exc:
            failed += 1
            print(f"[FAIL] {test.__name__}: {exc}")

    print("-" * 80)
    print("Day85 Investigation Planner LLM V2 Acceptance Summary")
    print(f"Total: {len(TESTS)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    run_acceptance()
