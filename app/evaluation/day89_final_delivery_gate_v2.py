from __future__ import annotations

import inspect
from collections.abc import Callable

from app.delivery.investigation_delivery_adapter_v2 import (
    InvestigationDeliveryResultV2,
)
from app.delivery.investigation_runtime_v2 import (
    Day89InvestigationContinuationStateV2,
    Day89PendingClarificationStateV2,
)
from app.ui import decision_console_app as ui

from app.evaluation import (
    clarification_resolution_acceptance_v2,
    decision_console_clarification_ui_acceptance_v2,
    decision_console_hitl_continue_ui_acceptance_v2,
    decision_console_monthly_contribution_ui_acceptance_v2,
    investigation_clarification_resume_acceptance_v2,
    investigation_hitl_continue_acceptance_v2,
    periodic_daily_weekly_runtime_acceptance_v2,
    periodic_daily_weekly_ui_acceptance_v2,
    periodic_ui_trusted_summary_acceptance_v2,
)


Suite = tuple[str, tuple[Callable[[], None], ...]]


EXISTING_SUITES: tuple[Suite, ...] = (
    (
        "Clarification Resolution",
        clarification_resolution_acceptance_v2.TESTS,
    ),
    (
        "Clarification Resume",
        investigation_clarification_resume_acceptance_v2.TESTS,
    ),
    (
        "Explicit Continue",
        investigation_hitl_continue_acceptance_v2.TESTS,
    ),
    (
        "Clarification UI",
        decision_console_clarification_ui_acceptance_v2.TESTS,
    ),
    (
        "Explicit Continue UI",
        decision_console_hitl_continue_ui_acceptance_v2.TESTS,
    ),
    (
        "Daily / Weekly Runtime",
        periodic_daily_weekly_runtime_acceptance_v2.TESTS,
    ),
    (
        "Daily / Weekly / Monthly UI",
        periodic_daily_weekly_ui_acceptance_v2.TESTS,
    ),
    (
        "Monthly Contribution UI",
        decision_console_monthly_contribution_ui_acceptance_v2.TESTS,
    ),
    (
        "Periodic Trusted Summary",
        periodic_ui_trusted_summary_acceptance_v2.TESTS,
    ),
)


def test_safe_investigation_delivery_has_no_server_execution_context() -> None:
    fields = set(
        InvestigationDeliveryResultV2.model_fields
    )

    assert fields == {
        "contract_version",
        "status",
        "message",
        "delivery",
        "console_view",
        "executive_brief",
    }

    forbidden = {
        "governed_query_context",
        "compiled",
        "sql",
        "sql_parameters",
        "parameters",
        "envelope",
        "finalization",
    }

    assert fields.isdisjoint(forbidden)


def test_safe_continuation_state_has_no_sql_or_executor_context() -> None:
    fields = set(
        Day89InvestigationContinuationStateV2.model_fields
    )

    assert fields == {
        "session_before_stop",
        "stopped_transition",
        "stop_status",
        "prior_transitions",
    }


def test_safe_pending_clarification_state_has_no_sql_context() -> None:
    fields = set(
        Day89PendingClarificationStateV2.model_fields
    )

    assert fields == {
        "session",
        "resolution_contract",
    }


def test_business_surface_does_not_render_engineering_internals() -> None:
    renderers = (
        ui._render_business_view,
        ui._render_fact_delivery_business,
        ui._render_periodic_comparison_business,
        ui._render_agentic_business_section,
    )

    source = "\n".join(
        inspect.getsource(item)
        for item in renderers
    ).lower()

    forbidden = (
        "query_plan_name",
        "scope_binding_fingerprint",
        "hmac",
        "sql_parameters",
        "compiled_sql",
        "raw database rows",
    )

    for token in forbidden:
        assert token not in source


def test_engineering_surface_explicitly_preserves_safe_projection_boundary() -> None:
    source = inspect.getsource(
        ui._render_engineering_view
    )

    assert "safe public summary" in source
    assert "不显示 raw SQL" in source
    assert "SQL parameters" in source
    assert "raw database rows" in source


def test_anomaly_ui_never_invents_marker_without_active_evidence() -> None:
    source = inspect.getsource(
        ui._render_anomaly_boundary
    )

    assert "if view.anomaly is None:" in source
    assert "没有 Active Anomaly Evidence" in source
    assert "不展示异常标记" in source
    assert "view.anomaly.show_anomaly_marker" in source


def test_periodic_submit_uses_governed_delivery_not_ui_side_sql() -> None:
    source = inspect.getsource(
        ui._submit_periodic_report
    )

    assert (
        "run_day89_periodic_gmv_channel_contribution_v2("
        in source
    )

    forbidden = (
        "SELECT ",
        "sqlalchemy",
        "engine.execute",
        "session.execute",
        "raw_rows",
    )

    for token in forbidden:
        assert token not in source


def test_hitl_ui_persists_only_safe_structured_state() -> None:
    source = "\n".join(
        (
            inspect.getsource(
                ui._submit_agentic_continuation
            ),
            inspect.getsource(
                ui._submit_agentic_clarification_gate
            ),
            inspect.getsource(
                ui._submit_agentic_clarification_response
            ),
        )
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

    assert "agentic_continuation_state" in source
    assert "agentic_pending_clarification" in source


CROSS_CUTTING_TESTS: tuple[Callable[[], None], ...] = (
    test_safe_investigation_delivery_has_no_server_execution_context,
    test_safe_continuation_state_has_no_sql_or_executor_context,
    test_safe_pending_clarification_state_has_no_sql_context,
    test_business_surface_does_not_render_engineering_internals,
    test_engineering_surface_explicitly_preserves_safe_projection_boundary,
    test_anomaly_ui_never_invents_marker_without_active_evidence,
    test_periodic_submit_uses_governed_delivery_not_ui_side_sql,
    test_hitl_ui_persists_only_safe_structured_state,
)


def _run_tests(
    *,
    suite_name: str,
    tests: tuple[Callable[[], None], ...],
) -> tuple[int, list[str]]:
    passed = 0
    failures: list[str] = []

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as exc:  # noqa: BLE001
            failures.append(
                f"{suite_name}::{test.__name__}: "
                f"{type(exc).__name__}: {exc}"
            )

    return passed, failures


def run_acceptance() -> None:
    print("Day89 Final Delivery Gate V2")
    print("=" * 72)

    total = 0
    passed = 0
    failures: list[str] = []

    for suite_name, tests in EXISTING_SUITES:
        suite_passed, suite_failures = _run_tests(
            suite_name=suite_name,
            tests=tests,
        )

        total += len(tests)
        passed += suite_passed
        failures.extend(suite_failures)

        print(
            f"{suite_name}: "
            f"{suite_passed}/{len(tests)}"
        )

    cross_passed, cross_failures = _run_tests(
        suite_name="Cross-cutting Delivery Safety",
        tests=CROSS_CUTTING_TESTS,
    )

    total += len(CROSS_CUTTING_TESTS)
    passed += cross_passed
    failures.extend(cross_failures)

    print(
        "Cross-cutting Delivery Safety: "
        f"{cross_passed}/{len(CROSS_CUTTING_TESTS)}"
    )

    print("-" * 72)
    print(f"Total: {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {len(failures)}")

    for failure in failures:
        print(f"- {failure}")

    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    run_acceptance()
