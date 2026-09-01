from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.agents.investigation_loop_v2 import (
    InvestigationBudgetPolicyV2,
    InvestigationSessionPolicyV2,
)
from app.agents.investigation_planner_v2 import (
    InvestigationStateV2,
    PlannerDecisionTypeV2,
    PlannerDecisionV2,
)
from app.delivery.contribution_investigation_recommendation_v1 import (
    ContributionInvestigationRecommendationV1,
)
from app.delivery.decision_console_runtime_v2 import (
    run_day89_local_investigation_v2,
)
from app.delivery.investigation_delivery_adapter_v2 import (
    InvestigationDeliveryStatusV2,
    build_investigation_step_delivery_v2,
)
from app.delivery.investigation_focus_scope_v1 import (
    build_contribution_investigation_focus_scope_v1,
    merge_requested_scope_with_investigation_focus_v1,
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
from app.semantic_layer.requested_scope_resolution_v2 import (
    RequestedScopeResolutionStatusV2,
    RequestedScopeResolutionV2,
)


QUESTION = (
    "2025年10月GMV相比9月表现怎么样？"
    "如果我要继续调查，最值得先看哪个渠道？"
)
REFERENCE_DATE = date(2026, 8, 29)


def _planner_for(action_id: str):
    def planner(
        state: InvestigationStateV2,
    ) -> PlannerDecisionV2:
        action = next(
            (
                item
                for item in state.available_actions
                if item.action_id == action_id
            ),
            None,
        )
        if action is None:
            raise AssertionError(
                f"当前合法 Action 中不存在：{action_id}"
            )

        return PlannerDecisionV2(
            decision_type=PlannerDecisionTypeV2.SELECT_TOOL,
            selected_action=action,
            clarification_prompt=None,
            rationale="Day93 Investigation Focus deterministic acceptance.",
            supporting_evidence_ids=tuple(
                item.evidence_id
                for item in state.insight.evidence
            ),
        )

    return planner


def _scope_parameter_values(
    envelope,
    *,
    dimension: str,
) -> frozenset[str]:
    contract = envelope.scope_binding.scoped_query_contract

    parameter_map = {
        parameter.name: str(parameter.value)
        for parameter in contract.parameters
    }

    selected_parameter_names = {
        parameter_name
        for predicate in contract.predicates
        if predicate.dimension.value == dimension
        for parameter_name in predicate.parameter_names
    }

    return frozenset(
        parameter_map[parameter_name]
        for parameter_name in selected_parameter_names
    )


def _manual_jd_recommendation() -> ContributionInvestigationRecommendationV1:
    return ContributionInvestigationRecommendationV1(
        metric_name="gmv",
        dimension_name="channel",
        member_key="京东旗舰店",
        member_label="京东旗舰店",
        reference_value=Decimal("139004.92"),
        current_value=Decimal("243351.20"),
        delta=Decimal("104346.28"),
        contribution_rate=Decimal("0.2720"),
        overall_delta=Decimal("383605.84"),
        direction="positive",
        rationale="可信渠道变化额最大，作为下一步调查入口。",
        can_confirm=("当前为受治理渠道贡献证据。",),
        cannot_confirm=("不能证明因果。",),
        contribution_evidence_id="ev_contrib_acceptance",
    )


def test_recommendation_maps_to_unique_jd_code() -> None:
    focus = build_contribution_investigation_focus_scope_v1(
        _manual_jd_recommendation()
    )
    assert focus.channel_codes == frozenset({"JD"})
    assert focus.member_label == "京东旗舰店"


def test_focus_merges_without_rewriting_original_requested_scope() -> None:
    original = RequestedScopeResolutionV2(
        status=RequestedScopeResolutionStatusV2.NO_EXPLICIT_SCOPE,
    )
    focus = build_contribution_investigation_focus_scope_v1(
        _manual_jd_recommendation()
    )

    effective = merge_requested_scope_with_investigation_focus_v1(
        requested_scope=original,
        investigation_focus=focus,
    )

    assert original.status == RequestedScopeResolutionStatusV2.NO_EXPLICIT_SCOPE
    assert original.channel_codes == frozenset()
    assert effective is not None
    assert effective.status == RequestedScopeResolutionStatusV2.RESOLVED
    assert effective.channel_codes == frozenset({"JD"})


def test_conflicting_requested_channel_fails_closed() -> None:
    original = RequestedScopeResolutionV2(
        status=RequestedScopeResolutionStatusV2.RESOLVED,
        channel_codes=frozenset({"TMALL"}),
        matched_channel_terms=("天猫旗舰店",),
    )
    focus = build_contribution_investigation_focus_scope_v1(
        _manual_jd_recommendation()
    )

    try:
        merge_requested_scope_with_investigation_focus_v1(
            requested_scope=original,
            investigation_focus=focus,
        )
    except ValueError:
        return

    raise AssertionError(
        "Requested Channel 与 Focus Channel 冲突时必须 fail closed。"
    )


def test_real_f02_focus_survives_category_and_city_rounds() -> None:
    seed = run_day89_local_investigation_v2(
        question=QUESTION,
        reference_date=REFERENCE_DATE,
    )

    assert seed.status == RuntimeDeliveryBridgeStatusV2.READY, seed.message
    assert seed.console_view is not None

    recommendation = (
        seed.console_view.contribution_investigation_recommendation
    )
    assert recommendation is not None

    focus = build_contribution_investigation_focus_scope_v1(
        recommendation
    )
    assert focus.channel_codes == frozenset({"JD"})

    first = run_day89_agentic_investigation_step_v2(
        seed_result=seed,
        reference_date=REFERENCE_DATE,
        investigation_focus_scope=focus,
        planner=_planner_for("drill_category"),
        include_category_action=True,
        budget_policy=InvestigationBudgetPolicyV2(
            max_investigation_steps=1,
            max_retries_per_action=0,
        ),
        session_policy=InvestigationSessionPolicyV2(
            max_rounds=2,
            max_total_investigation_steps=2,
        ),
    )

    action_ids = {
        item.action_id
        for item in first.session_before.loop_state.planner_state.available_actions
    }
    assert "drill_channel" not in action_ids
    assert "drill_category" in action_ids
    assert "drill_region" in action_ids

    assert first.investigation_focus_scope == focus
    assert first.requested_scope == seed.requested_scope
    assert first.governed_query_context is not None
    assert _scope_parameter_values(
        first.governed_query_context.envelope,
        dimension="channel",
    ) == frozenset({"JD"})

    assert first.status == Day89InvestigationRuntimeStatusV2.STOPPED
    assert first.stop_status is not None
    assert first.stop_status.can_continue

    first_delivery = build_investigation_step_delivery_v2(
        seed_result=seed,
        runtime_step=first,
        request_subject=QUESTION,
    )
    assert first_delivery.status == InvestigationDeliveryStatusV2.READY
    assert first_delivery.delivery is not None
    assert first_delivery.console_view is not None
    assert first_delivery.console_view.investigation_results

    first_breakdown = (
        first_delivery.console_view
        .investigation_results[0]
        .breakdown
    )
    assert first_breakdown is not None
    assert first_breakdown.scope_summary is not None
    assert "渠道代码：JD" in first_breakdown.scope_summary
    assert "TMALL" not in first_breakdown.scope_summary

    continuation = build_day89_continuation_state_v2(
        runtime_step=first,
    )
    assert continuation.investigation_focus_scope == focus

    second = continue_day89_agentic_investigation_step_v2(
        delivery=first_delivery.delivery,
        continuation_state=continuation,
        user_requested_continue=True,
        planner=_planner_for("drill_region"),
    )

    assert second.investigation_focus_scope == focus
    assert second.requested_scope == seed.requested_scope
    assert second.governed_query_context is not None
    assert _scope_parameter_values(
        second.governed_query_context.envelope,
        dimension="channel",
    ) == frozenset({"JD"})


TESTS = (
    test_recommendation_maps_to_unique_jd_code,
    test_focus_merges_without_rewriting_original_requested_scope,
    test_conflicting_requested_channel_fails_closed,
    test_real_f02_focus_survives_category_and_city_rounds,
)


def main() -> None:
    passed = 0

    for test in TESTS:
        test()
        passed += 1
        print(f"[PASS] {test.__name__}")

    print("=" * 72)
    print(
        "Day93 Investigation Focus Scope V1 Acceptance: "
        f"{passed}/{len(TESTS)} PASS"
    )


if __name__ == "__main__":
    main()
