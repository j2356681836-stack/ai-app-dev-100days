from datetime import date

from app.agents.clarification_resolution_v2 import (
    ClarificationResponseV2,
    build_day89_direction_clarification_requirement_v2,
    build_day89_direction_resolution_contract_v2,
    plan_day89_direction_clarification_v2,
    plan_day89_resolved_single_action_v2,
)
from app.agents.investigation_loop_v2 import (
    InvestigationBudgetPolicyV2,
    InvestigationSessionPolicyV2,
    continue_investigation_session_v2,
)
from app.delivery.decision_console_runtime_v2 import (
    run_day89_local_investigation_v2,
)
from app.delivery.investigation_runtime_v2 import (
    Day89InvestigationRuntimeStatusV2,
    build_day89_continuation_state_v2,
    build_day89_pending_clarification_state_v2,
    resume_day89_agentic_investigation_after_clarification_v2,
    run_day89_agentic_investigation_step_v2,
)
from app.delivery.runtime_delivery_bridge_v2 import (
    RuntimeDeliveryBridgeStatusV2,
)


QUESTION = (
    "2025年10月GMV相比9月表现怎么样？"
    "如果我要继续调查，最值得先看哪个渠道？"
)
REFERENCE_DATE = date(2026, 8, 30)


def test_user_selected_category_preserves_other_session_actions() -> None:
    seed = run_day89_local_investigation_v2(
        question=QUESTION,
        reference_date=REFERENCE_DATE,
    )

    assert seed.status == RuntimeDeliveryBridgeStatusV2.READY

    requirement = (
        build_day89_direction_clarification_requirement_v2()
    )

    clarification_step = run_day89_agentic_investigation_step_v2(
        seed_result=seed,
        reference_date=REFERENCE_DATE,
        investigation_focus_scope=None,
        planner=plan_day89_direction_clarification_v2,
        clarification_requirement=requirement,
        include_category_action=True,
        budget_policy=InvestigationBudgetPolicyV2(
            max_investigation_steps=1,
            max_retries_per_action=0,
        ),
        session_policy=InvestigationSessionPolicyV2(
            max_rounds=3,
            max_total_investigation_steps=3,
        ),
    )

    assert (
        clarification_step.status
        == Day89InvestigationRuntimeStatusV2.CLARIFICATION_REQUIRED
    )

    contract = build_day89_direction_resolution_contract_v2()
    pending = build_day89_pending_clarification_state_v2(
        runtime_step=clarification_step,
        resolution_contract=contract,
    )

    original_action_ids = {
        action.action_id
        for action in (
            pending.session.loop_state.planner_state.available_actions
        )
    }
    assert "drill_category" in original_action_ids
    assert "drill_region" in original_action_ids

    category_choice = next(
        choice
        for choice in contract.choices
        if choice.selected_action_id == "drill_category"
    )

    resumed = (
        resume_day89_agentic_investigation_after_clarification_v2(
            pending=pending,
            response=ClarificationResponseV2(
                choice_id=category_choice.choice_id
            ),
            seed_result=seed,
            planner=plan_day89_resolved_single_action_v2,
        )
    )

    step = resumed.runtime_step
    assert step is not None

    selected = step.planner_decision.selected_action
    assert selected is not None
    assert selected.action_id == "drill_category"

    # 用户选择只约束本轮执行动作，不应删除 Session 中其他合法方向。
    remaining_ids = tuple(
        action.action_id
        for action in (
            step.transition.next_state.planner_state.available_actions
        )
    )

    assert "drill_category" not in remaining_ids
    assert "drill_region" in remaining_ids
    assert set(remaining_ids) == (
        original_action_ids - {"drill_category"}
    )

    assert step.stop_status is not None
    assert step.stop_status.can_continue is True
    assert set(step.stop_status.uninvestigated_action_ids) == set(
        remaining_ids
    )

    # UI 使用的 safe continuation state 现在应该能正常建立。
    continuation = build_day89_continuation_state_v2(
        runtime_step=step,
    )

    next_session = continue_investigation_session_v2(
        session=continuation.session_before_stop,
        stop_status=continuation.stop_status,
        transition=continuation.stopped_transition,
        user_requested_continue=True,
    )

    next_action_ids = {
        action.action_id
        for action in (
            next_session.loop_state.planner_state.available_actions
        )
    }

    assert next_session.round_number == 2
    assert next_action_ids == set(remaining_ids)

    print(
        "PASS: "
        "test_user_selected_category_preserves_other_session_actions"
    )
    print("PASS: user-selected action = drill_category")
    print("PASS: unselected legal actions remain in session")
    print("PASS: stop_status.can_continue = true")
    print("PASS: safe continuation state can open round 2")


if __name__ == "__main__":
    test_user_selected_category_preserves_other_session_actions()
