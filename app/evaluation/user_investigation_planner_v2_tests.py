from app.evaluation.investigation_planner_acceptance_v2 import (
    _state,
)
from app.agents.user_investigation_planner_v2 import (
    plan_user_selected_investigation_action_v2,
)


def test_user_owned_action_still_uses_trusted_available_action() -> None:
    state = _state()

    decision = plan_user_selected_investigation_action_v2(
        state=state,
        action_id="drill_region",
        rationale="用户明确希望先检查地区。",
    )

    assert decision.selected_action is not None
    assert decision.selected_action.action_id == "drill_region"
    assert decision.supporting_evidence_ids

    print(
        "PASS: "
        "test_user_owned_action_still_uses_trusted_available_action"
    )


def test_user_cannot_select_action_outside_catalog() -> None:
    state = _state()

    try:
        plan_user_selected_investigation_action_v2(
            state=state,
            action_id="user_invented_campaign_sql",
            rationale="用户提出活动假设。",
        )
    except ValueError:
        print("PASS: test_user_cannot_select_action_outside_catalog")
        return

    raise AssertionError(
        "User-selected intent must not bypass available_actions."
    )


def main() -> None:
    test_user_owned_action_still_uses_trusted_available_action()
    test_user_cannot_select_action_outside_catalog()


if __name__ == "__main__":
    main()
