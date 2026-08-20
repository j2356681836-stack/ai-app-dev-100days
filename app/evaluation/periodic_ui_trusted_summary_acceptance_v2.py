from __future__ import annotations

import inspect
from datetime import date
from decimal import Decimal

import app.delivery.decision_console_runtime_v2 as runtime
import app.ui.decision_console_app as ui
from app.delivery.runtime_delivery_bridge_v2 import (
    RuntimeDeliveryBridgeResultV2,
    RuntimeDeliveryBridgeStatusV2,
)
from app.ui.decision_console_presenters_v2 import (
    append_trusted_summary_row_v2,
)


def test_summary_row_uses_supplied_trusted_value() -> None:
    rows = [
        {"渠道": "A", "GMV": "10.00"},
        {"渠道": "B", "GMV": "20.00"},
    ]

    result = append_trusted_summary_row_v2(
        display_rows=rows,
        metric_name="gmv",
        summary_value=Decimal("99.00"),
    )

    assert result[-1] == {
        "渠道": "汇总",
        "GMV": "99.00",
    }


def test_presenter_does_not_sum_visible_rows() -> None:
    source = inspect.getsource(
        append_trusted_summary_row_v2
    )

    assert "sum(" not in source
    assert ".sum(" not in source


def test_breakdown_summary_uses_explicit_trusted_window() -> None:
    source = inspect.getsource(
        runtime.run_day89_breakdown_summary_v2
    )

    assert "_explicit_window_metric_question_v2" in source
    assert "build_day89_overall_gmv_tool_binding_v2" in source
    assert "invoke_governed_plan_delivery_v2" in source


def test_monthly_runtime_uses_structured_current_reference_windows() -> None:
    source = inspect.getsource(
        runtime.run_day89_monthly_gmv_report_v2
    )

    assert "analysis_window=comparison.current_window" in source
    assert "analysis_window=comparison.reference_window" in source
    assert source.count("invoke_governed_plan_delivery_v2(") == 2


def test_streamlit_periodic_branch_calls_real_runtime() -> None:
    source = inspect.getsource(
        ui._submit_periodic_report
    )

    # UI 已从 Monthly-only 升级为统一 Periodic Runtime。
    assert (
        "run_day89_periodic_gmv_channel_contribution_v2("
        in source
    )
    assert "cadence=request.report_cadence" in source

    # 不允许 UI 绕过统一 Periodic Delivery，
    # 直接调用旧 Monthly-only Runtime。
    assert "run_day89_monthly_gmv_report_v2(" not in source


def test_streamlit_breakdown_does_not_sum_rows() -> None:
    source = inspect.getsource(
        ui._render_breakdown
    )

    assert "sum(" not in source
    assert ".sum(" not in source
    assert "append_trusted_summary_row_v2" in source


def test_completed_month_default_is_not_current_partial_month() -> None:
    value = ui._previous_completed_month_anchor()

    assert value < date.today()
    assert value.day >= 28


def test_breakdown_summary_non_ready_path_executes_without_name_error() -> None:
    primary = RuntimeDeliveryBridgeResultV2(
        status=RuntimeDeliveryBridgeStatusV2.GRAPH_STOPPED,
        message="test graph stopped",
        safe_runtime_result={
            "success": False,
            "outcome": "stopped",
        },
    )

    result = runtime.run_day89_breakdown_summary_v2(
        primary_result=primary,
        reference_date=date(2026, 8, 19),
    )

    assert result.status.value == "primary_not_ready"


TESTS = (
    test_summary_row_uses_supplied_trusted_value,
    test_presenter_does_not_sum_visible_rows,
    test_breakdown_summary_uses_explicit_trusted_window,
    test_monthly_runtime_uses_structured_current_reference_windows,
    test_streamlit_periodic_branch_calls_real_runtime,
    test_streamlit_breakdown_does_not_sum_rows,
    test_completed_month_default_is_not_current_partial_month,
    test_breakdown_summary_non_ready_path_executes_without_name_error,
)


def run_acceptance() -> None:
    print("Day89 Periodic UI + Trusted Breakdown Summary Acceptance")

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
