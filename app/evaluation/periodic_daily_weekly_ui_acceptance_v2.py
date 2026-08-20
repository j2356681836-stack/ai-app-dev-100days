from __future__ import annotations

import inspect
from datetime import date, timedelta

from app.delivery.decision_console_entry_v2 import (
    PeriodicReportCadenceV2,
)
from app.delivery.monthly_contribution_delivery_v2 import (
    MonthlyContributionDeliveryStatusV2,
)
from app.ui import decision_console_app as app


def test_periodic_submit_has_no_monthly_only_early_return() -> None:
    source = inspect.getsource(
        app._submit_periodic_report
    )

    assert (
        "request.report_cadence != "
        "PeriodicReportCadenceV2.MONTHLY"
        not in source
    )
    assert (
        "run_day89_periodic_gmv_channel_contribution_v2("
        in source
    )
    assert "cadence=request.report_cadence" in source


def test_business_route_has_no_daily_weekly_placeholder() -> None:
    source = inspect.getsource(
        app._render_business_view
    )

    assert "Daily / Weekly 尚未接入真实 Runtime" not in source
    assert "_render_periodic_comparison_business(" in source
    assert "cadence=request.report_cadence" in source


def test_business_renderer_accepts_ready_and_partial_ready() -> None:
    source = inspect.getsource(
        app._render_periodic_comparison_business
    )

    assert "MonthlyContributionDeliveryStatusV2.READY" in source
    assert "MonthlyContributionDeliveryStatusV2.PARTIAL_READY" in source


def test_partial_ready_never_claims_channel_contribution() -> None:
    source = inspect.getsource(
        app._render_periodic_comparison_business
    )

    assert "Result Protection" in source
    assert "不会读取被阻断的明细" in source
    assert "不会据此计算 Contribution" in source


def test_analyst_can_show_overall_evidence_for_partial_ready() -> None:
    source = inspect.getsource(
        app._render_analyst_view
    )

    assert "PARTIAL_READY" in source
    assert "Overall Evidence 可展示" in source
    assert "Channel Breakdown" in source


def test_daily_anchor_is_completed_day() -> None:
    label, default_value, max_value, help_text = (
        app._periodic_anchor_ui_v2("daily")
    )

    expected = date.today() - timedelta(days=1)
    assert label == "报表日期"
    assert default_value == expected
    assert max_value == expected
    assert "DOD" in help_text


def test_weekly_anchor_is_previous_completed_sunday() -> None:
    label, default_value, max_value, help_text = (
        app._periodic_anchor_ui_v2("weekly")
    )

    today = date.today()
    current_monday = (
        today - timedelta(days=today.weekday())
    )
    expected = current_monday - timedelta(days=1)

    assert label == "报表周定位日期"
    assert default_value == expected
    assert max_value == expected
    assert expected.weekday() == 6
    assert "WOW" in help_text


def test_monthly_anchor_preserves_existing_completed_month_rule() -> None:
    label, default_value, max_value, help_text = (
        app._periodic_anchor_ui_v2("monthly")
    )

    expected = app._previous_completed_month_anchor()

    assert label == "报表月份"
    assert default_value == expected
    assert max_value == expected
    assert "MOM" in help_text


def test_comparison_labels_are_semantically_correct() -> None:
    assert app._comparison_change_label_v2("dod") == "日环比"
    assert app._comparison_change_label_v2("wow") == "周环比"
    assert app._comparison_change_label_v2("mom") == "月环比"


def test_periodic_cadence_labels_cover_all_entry_contract_values() -> None:
    assert (
        app._periodic_cadence_label_v2(
            PeriodicReportCadenceV2.DAILY
        )
        == "日报"
    )
    assert (
        app._periodic_cadence_label_v2(
            PeriodicReportCadenceV2.WEEKLY
        )
        == "周报"
    )
    assert (
        app._periodic_cadence_label_v2(
            PeriodicReportCadenceV2.MONTHLY
        )
        == "月报"
    )


def test_periodic_ui_never_recomputes_contribution_from_rows() -> None:
    source = inspect.getsource(
        app._render_periodic_comparison_business
    )

    forbidden = (
        "sum(",
        "current_value - reference_value",
        "delta /",
        "raw_rows",
    )
    for token in forbidden:
        assert token not in source


def test_engineering_view_remains_safe_summary_only() -> None:
    source = inspect.getsource(
        app._render_engineering_view
    )

    assert "safe public summary" in source
    assert "raw SQL" in source
    assert "raw database rows" in source


TESTS = (
    test_periodic_submit_has_no_monthly_only_early_return,
    test_business_route_has_no_daily_weekly_placeholder,
    test_business_renderer_accepts_ready_and_partial_ready,
    test_partial_ready_never_claims_channel_contribution,
    test_analyst_can_show_overall_evidence_for_partial_ready,
    test_daily_anchor_is_completed_day,
    test_weekly_anchor_is_previous_completed_sunday,
    test_monthly_anchor_preserves_existing_completed_month_rule,
    test_comparison_labels_are_semantically_correct,
    test_periodic_cadence_labels_cover_all_entry_contract_values,
    test_periodic_ui_never_recomputes_contribution_from_rows,
    test_engineering_view_remains_safe_summary_only,
)


def run_acceptance() -> None:
    print("Day89 Daily / Weekly / Monthly Periodic UI Acceptance")

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
