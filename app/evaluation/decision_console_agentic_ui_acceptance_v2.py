from __future__ import annotations

import inspect

from app.ui import decision_console_app as app
from app.ui import decision_console_presenters_v2 as presenters


def test_seed_submit_does_not_auto_run_agentic_step() -> None:
    source = inspect.getsource(app._submit_investigation)
    assert "run_day89_agentic_investigation_step_v2" not in source
    assert "build_investigation_step_delivery_v2" not in source


def test_agentic_submit_uses_real_runtime_then_safe_adapter() -> None:
    source = inspect.getsource(app._submit_agentic_investigation)

    runtime_pos = source.index(
        "run_day89_agentic_investigation_step_v2"
    )
    delivery_pos = source.index(
        "build_investigation_step_delivery_v2"
    )

    assert runtime_pos < delivery_pos
    assert 'st.session_state["agentic_delivery"] = delivered' in source


def test_server_internal_runtime_step_is_not_saved_to_session_state() -> None:
    source = inspect.getsource(app._submit_agentic_investigation)

    assert 'st.session_state["runtime_step"]' not in source
    assert 'st.session_state["governed_query_context"]' not in source
    assert 'st.session_state["compiled"]' not in source


def test_analyst_view_prefers_safe_agentic_console_when_available() -> None:
    source = inspect.getsource(app._render_analyst_view)

    assert "_agentic_result()" in source
    assert "InvestigationDeliveryStatusV2.READY" in source
    assert "view = agentic.console_view" in source


def test_trace_renderer_uses_delivery_projection_only() -> None:
    source = inspect.getsource(app._render_investigation_trace)

    assert "investigation_trace" in source
    assert "observation_evidence_id" in source
    assert "produced_evidence_ids" in source
    assert "next_directive" in source
    assert "compiled" not in source.lower()
    assert "raw sql" not in source.lower()


def test_runtime_control_does_not_auto_continue() -> None:
    source = inspect.getsource(app._render_runtime_control)

    assert "control.can_continue" in source
    assert "continue_investigation_session_v2" not in source
    assert "run_one_investigation_step_v2" not in source


def test_clarification_renderer_keeps_tool_blocked_boundary_visible() -> None:
    source = inspect.getsource(app._render_runtime_clarification)

    assert "clarification_prompt" in source
    assert "requirement_reason" in source
    assert "tool_execution_blocked=True" in source


def test_presenters_cover_agentic_machine_statuses() -> None:
    assert presenters.format_investigation_action_v2(
        "drill_region"
    ) == "检查区域维度"
    assert presenters.format_observation_status_v2(
        "evidence"
    ) == "已获得新证据"
    assert presenters.format_loop_directive_v2(
        "stop"
    ) == "停止本轮调查"
    assert presenters.format_stop_reason_v2(
        "no_legal_action"
    ) == "当前没有剩余合法调查动作"


TESTS = (
    test_seed_submit_does_not_auto_run_agentic_step,
    test_agentic_submit_uses_real_runtime_then_safe_adapter,
    test_server_internal_runtime_step_is_not_saved_to_session_state,
    test_analyst_view_prefers_safe_agentic_console_when_available,
    test_trace_renderer_uses_delivery_projection_only,
    test_runtime_control_does_not_auto_continue,
    test_clarification_renderer_keeps_tool_blocked_boundary_visible,
    test_presenters_cover_agentic_machine_statuses,
)


def run_acceptance() -> None:
    print("Day89 Agentic Investigation UI Acceptance")

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
