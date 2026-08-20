from __future__ import annotations

import inspect

from app.agents.clarification_resolution_v2 import (
    ClarificationResponseV2,
)
from app.delivery import investigation_runtime_v2 as runtime
from app.delivery import investigation_delivery_adapter_v2 as adapter


def test_pending_state_contains_only_session_and_resolution_contract() -> None:
    fields = set(
        runtime.Day89PendingClarificationStateV2.model_fields
    )

    assert fields == {
        "session",
        "resolution_contract",
    }


def test_pending_state_has_no_governed_execution_internals() -> None:
    source = inspect.getsource(
        runtime.Day89PendingClarificationStateV2
    ).lower()

    assert "governed_query_context:" not in source
    assert "compiled:" not in source
    assert "sql_parameters" not in source
    assert "finalization:" not in source


def test_resume_resolves_before_building_any_tool_binding() -> None:
    source = inspect.getsource(
        runtime.resume_day89_agentic_investigation_after_clarification_v2
    )

    resolution_pos = source.index(
        "resolve_clarification_response_v2("
    )
    binding_pos = source.index(
        "_prepare_day89_gmv_investigation_bindings_v2("
    )

    assert resolution_pos < binding_pos


def test_non_resolved_response_returns_before_tool_execution() -> None:
    source = inspect.getsource(
        runtime.resume_day89_agentic_investigation_after_clarification_v2
    )

    assert (
        "resolution.status"
        in source
    )
    assert (
        "return Day89ClarificationResumeResultV2("
        in source
    )
    assert "runtime_step=None" in source


def test_resolution_does_not_reset_loop_or_session_budget() -> None:
    source = inspect.getsource(
        runtime._session_with_resolved_planner_state_v2
    )

    assert "budget_policy=original_loop.budget_policy" in source
    assert (
        "investigation_steps_used=("
        in source
    )
    assert "session_policy=session.session_policy" in source
    assert "round_number=session.round_number" in source
    assert (
        "completed_round_steps_used=("
        in source
    )


def test_resume_only_builds_binding_for_resolved_available_actions() -> None:
    source = inspect.getsource(
        runtime.resume_day89_agentic_investigation_after_clarification_v2
    )

    assert "actions = resolved_state.available_actions" in source
    assert "if len(actions) != 1:" in source
    assert "actions=actions" in source


def test_adapter_keeps_clarification_ready_when_unresolved() -> None:
    source = inspect.getsource(
        adapter.build_resolved_clarification_step_delivery_v2
    )

    assert "CLARIFICATION_READY" in source
    assert "resume_result.resolution.detail" in source


def test_adapter_clears_clarification_projection_after_real_execution() -> None:
    source = inspect.getsource(
        adapter.build_resolved_clarification_step_delivery_v2
    )

    assert "investigation_transitions=(" in source
    assert "clarification_planner_state=" not in source
    assert "clarification_planner_decision=" not in source


TESTS = (
    test_pending_state_contains_only_session_and_resolution_contract,
    test_pending_state_has_no_governed_execution_internals,
    test_resume_resolves_before_building_any_tool_binding,
    test_non_resolved_response_returns_before_tool_execution,
    test_resolution_does_not_reset_loop_or_session_budget,
    test_resume_only_builds_binding_for_resolved_available_actions,
    test_adapter_keeps_clarification_ready_when_unresolved,
    test_adapter_clears_clarification_projection_after_real_execution,
)


def run_acceptance() -> None:
    print("Day89 Runtime HITL Clarification Resume Acceptance")

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
