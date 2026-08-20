from __future__ import annotations

import inspect

from app.ui import decision_console_app as app


def test_business_view_exposes_system_or_user_guided_start() -> None:
    source = inspect.getsource(
        app._render_agentic_business_section
    )

    assert "系统在受控动作中规划" in source
    assert "我先指定首个调查方向" in source
    assert "_submit_agentic_clarification_gate()" in source
    assert "_submit_agentic_investigation()" in source


def test_clarification_choices_come_from_server_contract() -> None:
    source = inspect.getsource(
        app._render_agentic_business_section
    )

    assert "pending.resolution_contract.choices" in source
    assert "item.choice_id" in source

    # display label 通过 choice_id -> contract choice 映射读取；
    # 不要求具体局部变量名或循环写法。
    assert "choice_by_id" in source
    assert ".display_label" in source

    # UI 不能把 region/category 当成硬编码授权来源。
    assert 'options=("region", "category")' not in source


def test_clarification_ui_has_no_free_text_response() -> None:
    source = inspect.getsource(
        app._render_agentic_business_section
    )

    assert "st.text_input(" not in source
    assert "st.text_area(" not in source
    assert "st.radio(" in source


def test_gate_uses_trusted_requirement_contract_and_deterministic_clarify() -> None:
    source = inspect.getsource(
        app._submit_agentic_clarification_gate
    )

    assert (
        "build_day89_direction_clarification_requirement_v2()"
        in source
    )
    assert (
        "build_day89_direction_resolution_contract_v2()"
        in source
    )
    assert "plan_day89_direction_clarification_v2" in source
    assert "build_day89_pending_clarification_state_v2(" in source


def test_gate_does_not_persist_runtime_internals() -> None:
    source = inspect.getsource(
        app._submit_agentic_clarification_gate
    )

    assert '"runtime_step"' not in source
    assert '"compiled"' not in source
    assert '"envelope"' not in source

    # 只验证安全 Pending State key 被写入；
    # 不依赖 session_state 下标是否换行排版。
    assert "agentic_pending_clarification" in source
    assert "pending" in source


def test_response_rejects_choice_not_in_current_contract() -> None:
    source = inspect.getsource(
        app._submit_agentic_clarification_response
    )

    assert "allowed_choice_ids" in source
    assert "pending.resolution_contract.choices" in source
    assert "if choice_id not in allowed_choice_ids:" in source


def test_response_uses_deterministic_resolver_runtime() -> None:
    source = inspect.getsource(
        app._submit_agentic_clarification_response
    )

    assert (
        "resume_day89_agentic_investigation_after_clarification_v2("
        in source
    )
    assert "ClarificationResponseV2(" in source
    assert "plan_day89_resolved_single_action_v2" in source
    assert (
        "build_resolved_clarification_step_delivery_v2("
        in source
    )


def test_pending_clarification_is_cleared_only_after_ready_delivery() -> None:
    source = inspect.getsource(
        app._submit_agentic_clarification_response
    )

    ready_pos = source.index(
        "delivered.status"
    )
    clear_pos = source.index(
        "_clear_agentic_hitl_state()"
    )

    assert ready_pos < clear_pos


def test_new_entry_clears_pending_clarification_state() -> None:
    source = inspect.getsource(
        app._clear_agentic_hitl_state
    )

    assert '"agentic_pending_clarification"' in source


def test_existing_explicit_continue_path_remains_available() -> None:
    source = inspect.getsource(
        app._render_agentic_business_section
    )

    assert "control.can_continue" in source
    assert '"继续调查（开启下一轮）"' in source
    assert "_submit_agentic_continuation()" in source


TESTS = (
    test_business_view_exposes_system_or_user_guided_start,
    test_clarification_choices_come_from_server_contract,
    test_clarification_ui_has_no_free_text_response,
    test_gate_uses_trusted_requirement_contract_and_deterministic_clarify,
    test_gate_does_not_persist_runtime_internals,
    test_response_rejects_choice_not_in_current_contract,
    test_response_uses_deterministic_resolver_runtime,
    test_pending_clarification_is_cleared_only_after_ready_delivery,
    test_new_entry_clears_pending_clarification_state,
    test_existing_explicit_continue_path_remains_available,
)


def run_acceptance() -> None:
    print("Day89 Runtime HITL Clarification UI Acceptance")

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
