from app.ui.decision_console_app import (
    AGENTIC_MAX_ROUNDS_V2,
    AGENTIC_MAX_STEPS_PER_ROUND_V2,
    AGENTIC_MAX_TOTAL_STEPS_V2,
    _agentic_budget_policy_v2,
    _agentic_session_policy_v2,
)


def main() -> None:
    budget = _agentic_budget_policy_v2()
    session = _agentic_session_policy_v2()

    assert AGENTIC_MAX_STEPS_PER_ROUND_V2 == 1
    assert AGENTIC_MAX_ROUNDS_V2 == 3
    assert AGENTIC_MAX_TOTAL_STEPS_V2 == 3

    assert budget.max_investigation_steps == 1
    assert budget.max_retries_per_action == 0

    assert session.max_rounds == 3
    assert session.max_total_investigation_steps == 3

    print("PASS: 每个 Round 最多执行 1 个 Governed Tool")
    print("PASS: Session 最多允许 3 个显式确认的调查 Round")
    print("PASS: Session 总调查步数上限为 3")
    print("=" * 72)
    print("Decision Console Agentic Budget Policy V2 passed.")


if __name__ == "__main__":
    main()
