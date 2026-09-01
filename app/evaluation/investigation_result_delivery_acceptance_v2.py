from __future__ import annotations

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
from app.delivery.decision_console_runtime_v2 import (
    run_day89_local_investigation_v2,
)
from app.delivery.investigation_delivery_adapter_v2 import (
    InvestigationDeliveryStatusV2,
    build_continued_investigation_step_delivery_v2,
    build_investigation_step_delivery_v2,
)
from app.delivery.investigation_runtime_v2 import (
    build_day89_continuation_state_v2,
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

        return PlannerDecisionV2(
            decision_type=PlannerDecisionTypeV2.SELECT_TOOL,
            selected_action=action,
            clarification_prompt=None,
            rationale=(
                "Day93 Investigation Result Delivery acceptance."
            ),
            supporting_evidence_ids=tuple(
                item.evidence_id
                for item in state.insight.evidence
            ),
        )

    return planner


def _assert_result(
    *,
    result,
    expected_count: int,
    expected_actions: tuple[str, ...],
) -> None:
    assert (
        result.status
        == InvestigationDeliveryStatusV2.READY
    )
    assert result.console_view is not None

    views = result.console_view.investigation_results

    assert len(views) == expected_count
    assert tuple(
        item.selected_action_id
        for item in views
    ) == expected_actions

    for item in views:
        assert item.breakdown is not None, (
            f"{item.selected_action_id}: 缺少 Protected Breakdown。"
        )

        breakdown = item.breakdown

        assert breakdown.row_count > 0, (
            f"{item.selected_action_id}: 没有业务结果行。"
        )

        assert (
            breakdown.row_count
            == len(breakdown.rows)
        )

        assert "SHANGHAI" in (
            breakdown.scope_summary or ""
        ), (
            f"{item.selected_action_id}: "
            "业务结果 Scope 未保留 SHANGHAI。"
        )


def main() -> None:
    seed = run_day89_local_investigation_v2(
        question=QUESTION,
        reference_date=REFERENCE_DATE,
    )

    assert (
        seed.status
        == RuntimeDeliveryBridgeStatusV2.READY
    ), seed.message
    assert seed.delivery is not None

    budget = InvestigationBudgetPolicyV2(
        max_investigation_steps=1,
        max_retries_per_action=0,
    )
    session_policy = InvestigationSessionPolicyV2(
        max_rounds=3,
        max_total_investigation_steps=3,
    )

    first = run_day89_agentic_investigation_step_v2(
        seed_result=seed,
        reference_date=REFERENCE_DATE,
        planner=_planner_for("drill_channel"),
        include_category_action=True,
        budget_policy=budget,
        session_policy=session_policy,
    )

    first_delivery = build_investigation_step_delivery_v2(
        seed_result=seed,
        runtime_step=first,
        request_subject=QUESTION,
    )

    _assert_result(
        result=first_delivery,
        expected_count=1,
        expected_actions=("drill_channel",),
    )

    continuation_1 = build_day89_continuation_state_v2(
        runtime_step=first,
    )

    second = continue_day89_agentic_investigation_step_v2(
        delivery=first_delivery.delivery,
        continuation_state=continuation_1,
        user_requested_continue=True,
        planner=_planner_for("drill_category"),
    )

    second_delivery = (
        build_continued_investigation_step_delivery_v2(
            previous_result=first_delivery,
            runtime_step=second,
            prior_transitions=(
                continuation_1.prior_transitions
            ),
            prior_continuation_stop_statuses=(
                first.stop_status,
            ),
            request_subject=QUESTION,
        )
    )

    _assert_result(
        result=second_delivery,
        expected_count=2,
        expected_actions=(
            "drill_channel",
            "drill_category",
        ),
    )

    continuation_2 = build_day89_continuation_state_v2(
        runtime_step=second,
        prior_transitions=(
            continuation_1.prior_transitions
        ),
    )

    third = continue_day89_agentic_investigation_step_v2(
        delivery=second_delivery.delivery,
        continuation_state=continuation_2,
        user_requested_continue=True,
        planner=_planner_for("drill_region"),
    )

    third_delivery = (
        build_continued_investigation_step_delivery_v2(
            previous_result=second_delivery,
            runtime_step=third,
            prior_transitions=(
                continuation_2.prior_transitions
            ),
            prior_continuation_stop_statuses=(
                first.stop_status,
                second.stop_status,
            ),
            request_subject=QUESTION,
        )
    )

    _assert_result(
        result=third_delivery,
        expected_count=3,
        expected_actions=(
            "drill_channel",
            "drill_category",
            "drill_region",
        ),
    )

    print("PASS: Round 1 Protected Business Result 可交付")
    print("PASS: Round 2 累计保留两轮 Protected Business Result")
    print("PASS: Round 3 累计保留三轮 Protected Business Result")
    print("PASS: 每轮业务结果 Scope 均保留 SHANGHAI")
    print("=" * 72)
    print(
        "Day93 Investigation Result Delivery Acceptance passed."
    )


if __name__ == "__main__":
    main()
