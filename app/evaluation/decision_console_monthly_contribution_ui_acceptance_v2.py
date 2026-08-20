from __future__ import annotations

import inspect

from app.ui import decision_console_app as app
from app.ui import decision_console_presenters_v2 as presenters


def test_periodic_submit_uses_real_contribution_runtime() -> None:
    source = inspect.getsource(app._submit_periodic_report)

    # Streamlit 现在走统一 Periodic Runtime；
    # cadence 分流属于 Delivery 层，而不是 UI 层。
    assert (
        "run_day89_periodic_gmv_channel_contribution_v2("
        in source
    )
    assert "cadence=request.report_cadence" in source

    # UI 不应重新退回 Monthly-only 直连。
    assert (
        "run_day89_monthly_gmv_channel_contribution_v2("
        not in source
    )
    assert "run_day89_monthly_gmv_report_v2(" not in source


def test_periodic_session_stores_safe_contribution_delivery_only() -> None:
    source = inspect.getsource(app._submit_periodic_report)

    assert 'st.session_state["periodic_runtime_delivery"] = result' in source
    assert 'st.session_state["compiled"]' not in source
    assert 'st.session_state["raw_rows"]' not in source


def test_business_view_renders_structured_contribution_result() -> None:
    source = inspect.getsource(
        app._render_contribution_business_summary
    )

    assert "view.contribution" in source
    assert "negative_change_ranking" in source
    assert "positive_change_ranking" in source
    assert "reconciliation_status" in source


def test_ui_does_not_recalculate_contribution_math() -> None:
    app_source = inspect.getsource(
        app._render_contribution_analysis
    )
    presenter_source = inspect.getsource(
        presenters.build_contribution_display_rows_v2
    )

    assert "analyze_additive_contribution_v2" not in app_source
    assert "member.current_value - member.reference_value" not in app_source
    assert "member.current_value - member.reference_value" not in presenter_source
    assert "member.delta" in presenter_source
    assert "member.contribution_rate" in presenter_source


def test_current_breakdown_does_not_sum_visible_rows() -> None:
    source = inspect.getsource(
        app._render_periodic_comparison_business
    )

    assert "view.breakdown.rows" in source
    assert ".sum(" not in source
    assert "sum(" not in source
    assert "页面不对明细自行求和" in source


def test_anomaly_absence_is_not_rendered_as_anomaly() -> None:
    source = inspect.getsource(app._render_anomaly_boundary)

    assert "view.anomaly is None" in source
    assert "未评估 / 未激活" in source
    assert "不展示异常标记" in source
    assert "show_anomaly_marker" in source


def test_analyst_view_renders_full_contribution_and_evidence() -> None:
    source = inspect.getsource(app._render_analyst_view)

    assert "_render_contribution_analysis(view)" in source
    assert "view.evidence_drawer.records" in source


def test_contribution_chart_uses_trusted_member_delta() -> None:
    source = inspect.getsource(
        presenters.build_contribution_chart_rows_v2
    )

    assert "member.delta" in source
    assert "current_value" not in source
    assert "reference_value" not in source


def test_engineering_view_exposes_only_safe_monthly_projection() -> None:
    source = inspect.getsource(app._render_engineering_view)

    assert "current_channel_safe_runtime_result" in source
    assert "reference_channel_safe_runtime_result" in source
    assert "reconciliation_status" in source
    assert "raw SQL" in source
    assert "SQL parameters" in source


def test_presenters_format_reconciliation_and_direction() -> None:
    assert (
        presenters.format_reconciliation_status_v2(
            "reconciled"
        )
        == "已对账"
    )
    assert (
        presenters.format_contribution_direction_v2(
            "negative"
        )
        == "负向"
    )


TESTS = (
    test_periodic_submit_uses_real_contribution_runtime,
    test_periodic_session_stores_safe_contribution_delivery_only,
    test_business_view_renders_structured_contribution_result,
    test_ui_does_not_recalculate_contribution_math,
    test_current_breakdown_does_not_sum_visible_rows,
    test_anomaly_absence_is_not_rendered_as_anomaly,
    test_analyst_view_renders_full_contribution_and_evidence,
    test_contribution_chart_uses_trusted_member_delta,
    test_engineering_view_exposes_only_safe_monthly_projection,
    test_presenters_format_reconciliation_and_direction,
)


def run_acceptance() -> None:
    print("Day89 Monthly Contribution UI Acceptance")

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
