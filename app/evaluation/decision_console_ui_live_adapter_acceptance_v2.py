from __future__ import annotations

import inspect

import app.ui.decision_console_app as ui


def test_ui_does_not_import_evaluation_fixture() -> None:
    source = inspect.getsource(ui)

    assert "app.evaluation" not in source


def test_ui_uses_production_runtime_entry() -> None:
    source = inspect.getsource(ui)

    assert "run_day89_local_investigation_v2" in source


def test_ui_does_not_recalculate_comparison_or_contribution() -> None:
    source = inspect.getsource(ui)

    forbidden = (
        "compare_metric_values_v2",
        "analyze_additive_contribution_v2",
        "detect_anomaly_v2",
    )

    for token in forbidden:
        assert token not in source


def test_periodic_report_does_not_call_live_runtime_yet() -> None:
    source = inspect.getsource(
        ui._submit_periodic_report
    )

    assert "run_day89_local_investigation_v2" not in source


def test_engineering_view_uses_safe_runtime_result() -> None:
    source = inspect.getsource(
        ui._render_engineering_view
    )

    assert "safe_runtime_result" in source
    assert ".compiled" not in source
    assert ".finalization" not in source


TESTS = (
    test_ui_does_not_import_evaluation_fixture,
    test_ui_uses_production_runtime_entry,
    test_ui_does_not_recalculate_comparison_or_contribution,
    test_periodic_report_does_not_call_live_runtime_yet,
    test_engineering_view_uses_safe_runtime_result,
)


def run_acceptance() -> None:
    print("Day89 Streamlit Live Delivery Adapter Acceptance")

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
