from __future__ import annotations

import inspect

from app.ui import decision_console_app as app


def test_initial_agentic_ui_enables_real_hitl_action_space() -> None:
    source = inspect.getsource(
        app._submit_agentic_investigation
    )

    assert "include_category_action=True" in source
    assert "max_investigation_steps=1" in source
    assert "max_rounds=2" in source
    assert "max_total_investigation_steps=2" in source


def test_initial_agentic_submit_saves_only_safe_continuation_state() -> None:
    source = inspect.getsource(
        app._submit_agentic_investigation
    )

    assert "build_day89_continuation_state_v2(" in source
    assert '"agentic_continuation_state"' in source
    assert (
        '"agentic_prior_continuation_stop_statuses"'
        in source
    )

    assert 'st.session_state["runtime_step"]' not in source
    assert 'st.session_state["compiled"]' not in source
    assert 'st.session_state["governed_query_context"]' not in source


def test_continue_button_is_guarded_by_can_continue() -> None:
    source = inspect.getsource(
        app._render_agentic_business_section
    )

    can_continue_pos = source.index(
        "if control.can_continue:"
    )
    button_pos = source.index(
        '"继续调查（开启下一轮）"'
    )
    submit_pos = source.index(
        "_submit_agentic_continuation()"
    )

    assert can_continue_pos < button_pos < submit_pos


def test_continuation_submit_requires_safe_previous_state() -> None:
    source = inspect.getsource(
        app._submit_agentic_continuation
    )

    assert "_agentic_result()" in source
    assert "_continuation_state()" in source
    assert "_prior_continuation_stop_statuses()" in source
    assert "previous.delivery" in source


def test_user_continue_is_explicit_in_button_handler_only() -> None:
    source = inspect.getsource(
        app._submit_agentic_continuation
    )

    assert (
        "continue_day89_agentic_investigation_step_v2("
        in source
    )
    assert "user_requested_continue=True" in source

    initial_source = inspect.getsource(
        app._submit_agentic_investigation
    )
    assert (
        "continue_day89_agentic_investigation_step_v2("
        not in initial_source
    )


def test_continued_delivery_receives_prior_stop_authorization() -> None:
    source = inspect.getsource(
        app._submit_agentic_continuation
    )

    assert "prior_transitions=(" in source
    assert "continuation.prior_transitions" in source
    assert "prior_continuation_stop_statuses=(" in source
    assert "prior_stop_statuses" in source


def test_safe_hitl_state_is_cleared_on_new_requests() -> None:
    investigation_source = inspect.getsource(
        app._submit_investigation
    )
    periodic_source = inspect.getsource(
        app._submit_periodic_report
    )

    assert "_clear_agentic_hitl_state()" in investigation_source
    assert "_clear_agentic_hitl_state()" in periodic_source


def test_no_server_internal_context_is_persisted_by_continue() -> None:
    source = inspect.getsource(
        app._submit_agentic_continuation
    )

    forbidden_session_keys = (
        'st.session_state["runtime_step"]',
        'st.session_state["compiled"]',
        'st.session_state["sql"]',
        'st.session_state["governed_query_context"]',
        'st.session_state["envelope"]',
    )

    for key in forbidden_session_keys:
        assert key not in source


def test_continue_state_is_removed_when_final_round_cannot_continue() -> None:
    source = inspect.getsource(
        app._submit_agentic_continuation
    )

    clear_pos = source.index(
        "_clear_agentic_hitl_state()"
    )
    can_continue_pos = source.index(
        "runtime_step.stop_status.can_continue"
    )

    assert clear_pos < can_continue_pos


TESTS = (
    test_initial_agentic_ui_enables_real_hitl_action_space,
    test_initial_agentic_submit_saves_only_safe_continuation_state,
    test_continue_button_is_guarded_by_can_continue,
    test_continuation_submit_requires_safe_previous_state,
    test_user_continue_is_explicit_in_button_handler_only,
    test_continued_delivery_receives_prior_stop_authorization,
    test_safe_hitl_state_is_cleared_on_new_requests,
    test_no_server_internal_context_is_persisted_by_continue,
    test_continue_state_is_removed_when_final_round_cannot_continue,
)


def run_acceptance() -> None:
    print("Day89 Runtime HITL Explicit Continue UI Acceptance")

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
