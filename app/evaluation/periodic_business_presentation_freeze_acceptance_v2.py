from __future__ import annotations

import inspect

from app.ui import decision_console_app as app


def test_periodic_business_view_hides_single_channel_extension() -> None:
    source = inspect.getsource(app._render_business_view)

    assert "_render_periodic_channel_extension_v2(" not in source
    assert 'st.markdown("### 渠道变化贡献")' not in source
    assert "本次渠道 Contribution 扩展没有可释放结果" not in source


def test_periodic_business_view_keeps_primary_report_and_export() -> None:
    source = inspect.getsource(app._render_business_view)

    assert "_render_periodic_business_report_v2(" in source
    assert "_render_periodic_report_export_v2(report)" in source


def test_channel_contribution_capability_is_still_registered() -> None:
    submit_source = inspect.getsource(app._submit_periodic_report)
    analyst_source = inspect.getsource(app._render_analyst_view)
    engineering_source = inspect.getsource(app._render_engineering_view)

    assert "run_day89_periodic_gmv_channel_contribution_v2(" in submit_source
    assert "_render_contribution_analysis(view)" in analyst_source
    assert "current_channel_safe_runtime_result" in engineering_source
    assert "reference_channel_safe_runtime_result" in engineering_source


TESTS = (
    test_periodic_business_view_hides_single_channel_extension,
    test_periodic_business_view_keeps_primary_report_and_export,
    test_channel_contribution_capability_is_still_registered,
)


def run_acceptance() -> None:
    passed = 0
    failures: list[str] = []

    print("Day94 Periodic Business Presentation Freeze Acceptance")

    for test in TESTS:
        try:
            test()
            passed += 1
            print(f"PASS: {test.__name__}")
        except Exception as exc:  # noqa: BLE001
            failures.append(
                f"{test.__name__}: {type(exc).__name__}: {exc}"
            )
            print(f"FAIL: {test.__name__}")

    print(f"Total: {len(TESTS)}")
    print(f"Passed: {passed}")
    print(f"Failed: {len(failures)}")

    for failure in failures:
        print(f"- {failure}")

    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    run_acceptance()
