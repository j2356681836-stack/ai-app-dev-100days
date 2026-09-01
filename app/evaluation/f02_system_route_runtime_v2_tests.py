from datetime import date
from decimal import Decimal

from app.agents.focused_change_breakdown_v2 import (
    FocusedChangeReconciliationStatusV2,
)
from app.agents.investigation_loop_v2 import (
    InvestigationBudgetPolicyV2,
    InvestigationSessionPolicyV2,
)
from app.delivery.decision_console_runtime_v2 import (
    run_day89_local_investigation_v2,
)
from app.delivery.focused_change_breakdown_delivery_v2 import (
    ChangeBreakdownScopeKindV2,
)
from app.delivery.investigation_runtime_v2 import (
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


def test_f02_near_tie_system_route_runs_global_category_change() -> None:
    seed = run_day89_local_investigation_v2(
        question=QUESTION,
        reference_date=REFERENCE_DATE,
    )

    assert seed.status == RuntimeDeliveryBridgeStatusV2.READY
    assert seed.console_view is not None
    assert seed.console_view.comparison is not None

    view = seed.console_view
    route_rec = view.contribution_investigation_route_recommendation

    assert route_rec is not None
    assert route_rec.pattern_assessment.pattern.value == "near_tie"
    assert route_rec.route.scope_strategy.value == "keep_requested_scope"
    assert route_rec.route.next_dimension.value == "category"

    # Near-Tie 不再保留旧 Top1 Member Focus Recommendation。
    assert view.contribution_investigation_recommendation is None

    step = run_day89_agentic_investigation_step_v2(
        seed_result=seed,
        reference_date=REFERENCE_DATE,
        investigation_focus_scope=None,
        investigation_route=route_rec.route,
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

    selected = step.planner_decision.selected_action
    assert selected is not None
    assert selected.action_id == "drill_category"
    assert step.investigation_focus_scope is None

    change = step.focused_change_breakdown
    assert change is not None
    assert change.scope_kind == ChangeBreakdownScopeKindV2.OVERALL

    result = change.result
    comparison = view.comparison

    assert result.focus_member_key == "__overall__"
    assert result.reference_focus_value == comparison.reference_value
    assert result.current_focus_value == comparison.current_value
    assert result.focus_delta == comparison.absolute_change
    assert result.focus_delta == Decimal("383605.84")
    assert (
        result.reconciliation_status
        == FocusedChangeReconciliationStatusV2.RECONCILED
    )

    # Category 只消耗一个 Round；Channel / Region 仍是合法剩余方向。
    assert step.stop_status is not None
    assert step.stop_status.can_continue is True

    print(
        "PASS: "
        "test_f02_near_tie_system_route_runs_global_category_change"
    )
    print("PASS: legacy JD focus = none")
    print("PASS: system route = global category")
    print("PASS: overall delta = 383605.84")
    print("PASS: global category reconciliation = reconciled")
    print("PASS: continuation remains available")


if __name__ == "__main__":
    test_f02_near_tie_system_route_runs_global_category_change()
