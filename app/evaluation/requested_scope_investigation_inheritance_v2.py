from __future__ import annotations

import inspect
from datetime import date

from app.agents.investigation_loop_v2 import (
    InvestigationBudgetPolicyV2,
    InvestigationSessionPolicyV2,
)
from app.agents.investigation_planner_v2 import (
    InvestigationStateV2,
    PlannerDecisionTypeV2,
    PlannerDecisionV2,
)
from app.delivery import decision_console_runtime_v2 as console_runtime
from app.delivery import runtime_delivery_bridge_v2 as bridge
from app.delivery.decision_console_runtime_v2 import (
    run_day89_local_investigation_v2,
)
from app.delivery.investigation_delivery_adapter_v2 import (
    InvestigationDeliveryStatusV2,
    build_investigation_step_delivery_v2,
)
from app.delivery.investigation_runtime_v2 import (
    Day89InvestigationRuntimeStatusV2,
    build_day89_continuation_state_v2,
    build_day89_gmv_investigation_actions_v2,
    continue_day89_agentic_investigation_step_v2,
    run_day89_agentic_investigation_step_v2,
)
from app.delivery.runtime_delivery_bridge_v2 import (
    RuntimeDeliveryBridgeStatusV2,
)


QUESTION = "2025年上海地区GMV是多少？"
REFERENCE_DATE = date(2026, 8, 28)


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

        evidence_ids = tuple(
            item.evidence_id
            for item in state.insight.evidence
        )

        return PlannerDecisionV2(
            decision_type=PlannerDecisionTypeV2.SELECT_TOOL,
            selected_action=action,
            clarification_prompt=None,
            rationale=(
                "Day93 Requested Scope inheritance "
                "deterministic acceptance."
            ),
            supporting_evidence_ids=evidence_ids,
        )

    return planner


def _scope_parameter_values(
    envelope,
    *,
    dimension: str,
) -> frozenset[str]:
    """
    通过 ScopedPredicate.dimension 识别维度，
    再按 predicate.parameter_names 读取对应参数值。

    不能通过 parameter.name 的字符串片段猜维度，
    因为 target_id 本身可能包含 region/channel 等词。
    """

    contract = (
        envelope.scope_binding
        .scoped_query_contract
    )

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


def _assert_shanghai_scope(envelope) -> None:
    requested_scope = envelope.requested_scope

    assert requested_scope is not None
    assert requested_scope.region_codes == frozenset(
        {"SHANGHAI"}
    )

    region_values = _scope_parameter_values(
        envelope,
        dimension="region",
    )

    assert region_values == frozenset(
        {"SHANGHAI"}
    ), (
        "Governed Scope Binding 已扩大或丢失 Requested Region。"
        f" actual={sorted(region_values)}"
    )


def test_structured_followup_contract_is_scope_aware() -> None:
    bridge_source = inspect.getsource(
        bridge.invoke_governed_plan_delivery_v2
    )
    summary_source = inspect.getsource(
        console_runtime.run_day89_breakdown_summary_v2
    )

    assert (
        "requested_scope: RequestedScopeResolutionV2 | None = None"
        in bridge_source
    )
    assert "requested_scope=requested_scope" in bridge_source
    assert (
        "requested_scope=primary_result.requested_scope"
        in summary_source
    )


def test_real_postgresql_scope_survives_agentic_rounds() -> None:
    seed = run_day89_local_investigation_v2(
        question=QUESTION,
        reference_date=REFERENCE_DATE,
    )

    assert (
        seed.status
        == RuntimeDeliveryBridgeStatusV2.READY
    ), seed.message
    assert seed.delivery is not None
    assert seed.requested_scope is not None
    assert seed.requested_scope.region_codes == frozenset(
        {"SHANGHAI"}
    )

    # Current contract:
    # Requested Region=SHANGHAI locks the region row scope.
    # Region is therefore NOT a new legal drill-down direction.
    # Channel / Category remain legal cross-dimension investigations.
    initial_actions = build_day89_gmv_investigation_actions_v2(
        delivery=seed.delivery,
        requested_scope=seed.requested_scope,
        include_category=True,
    )
    initial_action_ids = {
        action.action_id
        for action in initial_actions
    }

    assert "drill_region" not in initial_action_ids, (
        "Requested Region 已锁定为上海时，不应重新开放 drill_region。"
    )
    assert "drill_channel" in initial_action_ids
    assert "drill_category" in initial_action_ids

    first = run_day89_agentic_investigation_step_v2(
        seed_result=seed,
        reference_date=REFERENCE_DATE,
        planner=_planner_for("drill_channel"),
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

    assert first.requested_scope == seed.requested_scope
    assert first.governed_query_context is not None
    _assert_shanghai_scope(
        first.governed_query_context.envelope
    )

    assert (
        first.status
        == Day89InvestigationRuntimeStatusV2.STOPPED
    )
    assert first.stop_status is not None
    assert first.stop_status.can_continue

    continuation = build_day89_continuation_state_v2(
        runtime_step=first,
    )

    assert (
        continuation.requested_scope
        == seed.requested_scope
    )

    first_delivery = build_investigation_step_delivery_v2(
        seed_result=seed,
        runtime_step=first,
        request_subject=QUESTION,
    )

    assert (
        first_delivery.status
        == InvestigationDeliveryStatusV2.READY
    )
    assert first_delivery.delivery is not None

    # Second round must use a still-legal cross-dimension action.
    # Category is intentionally used here; region remains locked to SHANGHAI.
    second = continue_day89_agentic_investigation_step_v2(
        delivery=first_delivery.delivery,
        continuation_state=continuation,
        user_requested_continue=True,
        planner=_planner_for("drill_category"),
    )

    assert (
        second.requested_scope
        == seed.requested_scope
    )
    assert second.governed_query_context is not None
    _assert_shanghai_scope(
        second.governed_query_context.envelope
    )


TESTS = (
    test_structured_followup_contract_is_scope_aware,
    test_real_postgresql_scope_survives_agentic_rounds,
)


def main() -> None:
    passed = 0

    for test in TESTS:
        test()
        passed += 1
        print(f"PASS: {test.__name__}")

    print("=" * 72)
    print(
        "Day93 Requested Scope Inheritance Summary"
    )
    print(f"Passed: {passed}/{len(TESTS)}")


if __name__ == "__main__":
    main()
