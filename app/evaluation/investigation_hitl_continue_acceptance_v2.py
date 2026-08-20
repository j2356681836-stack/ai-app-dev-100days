from __future__ import annotations

import inspect

from app.agents.investigation_loop_v2 import (
    InvestigationBudgetPolicyV2,
)
from app.delivery import investigation_runtime_v2 as runtime
from app.delivery import investigation_delivery_adapter_v2 as adapter


def test_existing_action_catalog_default_does_not_expand_scope() -> None:
    source = inspect.getsource(
        runtime.build_day89_gmv_investigation_actions_v2
    )

    assert "include_category: bool = False" in source
    assert '("drill_category", "gmv_category_v2", "category")' in source


def test_continuation_requires_day86_explicit_user_gate() -> None:
    source = inspect.getsource(
        runtime.continue_day89_agentic_investigation_step_v2
    )

    assert "continue_investigation_session_v2(" in source
    assert "user_requested_continue=user_requested_continue" in source
    assert "user_requested_continue=True" not in source


def test_safe_continuation_state_excludes_compiled_sql_context() -> None:
    fields = set(
        runtime.Day89InvestigationContinuationStateV2.model_fields
    )

    assert fields == {
        "session_before_stop",
        "stopped_transition",
        "stop_status",
        "prior_transitions",
    }

    source = inspect.getsource(
        runtime.Day89InvestigationContinuationStateV2
    ).lower()

    assert "governed_query_context:" not in source
    assert "compiled:" not in source
    assert "sql_parameters" not in source


def test_continuation_reuses_remaining_actions_only() -> None:
    source = inspect.getsource(
        runtime.continue_day89_agentic_investigation_step_v2
    )

    assert (
        "session.loop_state.planner_state.available_actions"
        in source
    )
    assert "build_day89_gmv_investigation_actions_v2(" not in source


def test_continued_delivery_appends_prior_evidence_and_trace() -> None:
    source = inspect.getsource(
        adapter.build_continued_investigation_step_delivery_v2
    )

    assert "previous_delivery.evidence_pack.evidence_records" in source
    assert "investigation_transitions=transitions" in source
    assert "metric_definition=previous_delivery.metric_definition" in source


def test_no_continuation_function_auto_called_by_initial_entry() -> None:
    source = inspect.getsource(
        runtime.run_day89_agentic_investigation_step_v2
    )

    assert "continue_day89_agentic_investigation_step_v2(" not in source
    assert "continue_investigation_session_v2(" not in source


def test_continued_delivery_requires_prior_stop_statuses() -> None:
    source = inspect.getsource(
        adapter.build_continued_investigation_step_delivery_v2
    )

    assert "prior_continuation_stop_statuses" in source
    assert "expected_prior_stop_count" in source
    assert (
        "investigation_prior_continuation_stop_statuses="
        in source
    )


def test_decision_console_allows_only_authorized_intermediate_stop() -> None:
    import app.delivery.decision_console_view_v2 as view

    source = inspect.getsource(
        view._build_investigation_trace_v2
    )

    assert "prior_continuation_stop_statuses" in source
    assert "prior_stop.can_continue" in source
    assert "prior_stop.uninvestigated_action_ids" in source
    assert "next_action_id" in source
    assert (
        "STOP 后不能继续追加 Investigation transition"
        not in source
    )


TESTS = (
    test_existing_action_catalog_default_does_not_expand_scope,
    test_continuation_requires_day86_explicit_user_gate,
    test_safe_continuation_state_excludes_compiled_sql_context,
    test_continuation_reuses_remaining_actions_only,
    test_continued_delivery_appends_prior_evidence_and_trace,
    test_no_continuation_function_auto_called_by_initial_entry,
    test_continued_delivery_requires_prior_stop_statuses,
    test_decision_console_allows_only_authorized_intermediate_stop,
)


def run_acceptance() -> None:
    print("Day89 Runtime HITL Explicit Continue Acceptance")

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
