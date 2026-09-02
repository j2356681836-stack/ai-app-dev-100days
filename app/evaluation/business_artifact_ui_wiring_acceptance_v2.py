from __future__ import annotations

from pathlib import Path


TARGET = (
    Path(__file__).resolve().parents[1]
    / "ui"
    / "decision_console_app.py"
)


def _source() -> str:
    return TARGET.read_text(
        encoding="utf-8"
    )


def test_business_artifact_imports_are_wired() -> None:
    source = _source()

    required = (
        "render_investigation_business_docx_v2,",
        "render_periodic_business_docx_v2,",
        "render_investigation_business_xlsx_v2,",
        "render_periodic_business_xlsx_v2,",
    )

    for token in required:
        assert token in source


def test_investigation_business_buttons_exist() -> None:
    source = _source()

    for token in (
        "download_investigation_docx::",
        "download_investigation_xlsx::",
        "下载 Word 业务报告",
        "下载 Excel 数据附件",
    ):
        assert token in source


def test_periodic_business_buttons_exist() -> None:
    source = _source()

    for token in (
        "download_periodic_docx::",
        "download_periodic_xlsx::",
        "下载 Word 经营报告",
        "下载 Excel 数据附件",
    ):
        assert token in source


def test_html_is_no_longer_a_business_ui_download() -> None:
    source = _source()

    assert (
        "download_investigation_html::"
        not in source
    )
    assert (
        "download_periodic_html::"
        not in source
    )
    assert (
        "render_investigation_report_html_v2,"
        not in source
    )
    assert (
        "render_periodic_report_html_v2,"
        not in source
    )


def test_markdown_is_retained_as_optional_format() -> None:
    source = _source()

    assert (
        "下载 Markdown（技术 / Portfolio）"
        in source
    )
    assert (
        "download_investigation_markdown::"
        in source
    )
    assert (
        "download_periodic_markdown::"
        in source
    )


TESTS = (
    test_business_artifact_imports_are_wired,
    test_investigation_business_buttons_exist,
    test_periodic_business_buttons_exist,
    test_html_is_no_longer_a_business_ui_download,
    test_markdown_is_retained_as_optional_format,
)


def run_acceptance() -> None:
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

    print(
        "Day94 Business Artifact UI Wiring Acceptance Summary"
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
