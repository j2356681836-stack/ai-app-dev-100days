from __future__ import annotations

from pathlib import Path


TARGET = (
    Path(__file__).resolve().parents[1]
    / "ui"
    / "decision_console_app.py"
)


def _source() -> str:
    return TARGET.read_text(encoding="utf-8")


def test_final_report_and_export_imports_are_wired() -> None:
    source = _source()

    required = (
        "from app.delivery.investigation_report_v2 import (",
        "build_investigation_report_v2,",
        "from app.delivery.report_export_v2 import (",
        "render_investigation_report_markdown_v2,",
        "render_periodic_report_markdown_v2,",
        "from app.delivery.business_document_export_v2 import (",
        "render_investigation_business_docx_v2,",
        "render_periodic_business_docx_v2,",
        "from app.delivery.business_workbook_export_v2 import (",
        "render_investigation_business_xlsx_v2,",
        "render_periodic_business_xlsx_v2,",
    )

    for token in required:
        assert token in source

    # HTML may remain as a renderer elsewhere, but it is no longer
    # part of the Business Console export wiring contract.
    assert "render_investigation_report_html_v2," not in source
    assert "render_periodic_report_html_v2," not in source



def test_investigation_console_and_exports_share_one_payload_variable() -> None:
    source = _source()

    start = source.index(
        "def _render_investigation_report_export_v2()"
    )
    end = source.index(
        "def _render_periodic_report_export_v2(",
        start,
    )
    function_source = source[start:end]

    assert "report_payload = (" in function_source

    for token in (
        "render_investigation_business_docx_v2(\n"
        "            report_payload",
        "render_investigation_business_xlsx_v2(\n"
        "            report_payload",
        "render_investigation_report_markdown_v2(\n"
        "            report_payload",
        "brief = report_payload.executive_brief",
    ):
        assert token in function_source

    # Evidence / Provenance presentation is owned by the unified
    # Verification / Engineering views. Export wiring only proves that
    # all artifacts consume the same frozen InvestigationReportV2 payload.
    assert "render_investigation_report_html_v2(" not in function_source




def test_periodic_console_and_exports_share_periodic_report_contract() -> None:
    source = _source()

    start = source.index(
        "def _render_periodic_report_export_v2("
    )
    end = source.index(
        "def _periodic_business_report_result_v2(",
        start,
    )
    function_source = source[start:end]

    assert (
        "report: PeriodicBusinessReportV2"
        in function_source
    )

    for token in (
        "render_periodic_business_docx_v2(\n"
        "            report",
        "render_periodic_business_xlsx_v2(\n"
        "            report",
        "render_periodic_report_markdown_v2(\n"
        "            report",
    ):
        assert token in function_source

    assert "render_periodic_report_html_v2(" not in function_source

    assert (
        "_render_periodic_business_report_v2(\n"
        "            report,"
        in source
    )
    assert (
        "_render_periodic_report_export_v2(report)"
        in source
    )



def test_all_ready_investigation_business_paths_expose_final_report() -> None:
    source = _source()

    assert (
        source.count(
            "_render_investigation_report_export_v2()"
        )
        == 4
    )
    # 1 definition + 3 READY rendering paths.


def test_download_buttons_exist_for_both_formats_and_report_types() -> None:
    source = _source()

    required_tokens = (
        "download_investigation_docx::",
        "download_investigation_xlsx::",
        "download_investigation_markdown::",
        "download_periodic_docx::",
        "download_periodic_xlsx::",
        "download_periodic_markdown::",
        "下载 Word 业务报告",
        "下载 Word 经营报告",
        "下载 Excel 数据附件",
        "下载 Markdown（技术 / Portfolio）",
        'mime="text/markdown; charset=utf-8"',
        "application/vnd.openxmlformats-officedocument.",
    )

    for token in required_tokens:
        assert token in source

    for stale_token in (
        "download_investigation_html::",
        "download_periodic_html::",
        'mime="text/html; charset=utf-8"',
    ):
        assert stale_token not in source



def test_ui_wiring_does_not_add_sql_or_llm_execution_calls() -> None:
    source = _source()

    start = source.index(
        "def _active_investigation_report_payload_v2("
    )
    end = source.index(
        "def _periodic_business_report_result_v2(",
        start,
    )
    added_source = source[start:end]

    forbidden = (
        "execute_governed_query_v2(",
        "invoke_governed_graph_delivery_v2(",
        "run_day89_local_investigation_v2(",
        "run_day93_periodic_business_report_v2(",
        "llm_call(",
        "generate_sql(",
    )

    for token in forbidden:
        assert token not in added_source


TESTS = (
    test_final_report_and_export_imports_are_wired,
    test_investigation_console_and_exports_share_one_payload_variable,
    test_periodic_console_and_exports_share_periodic_report_contract,
    test_all_ready_investigation_business_paths_expose_final_report,
    test_download_buttons_exist_for_both_formats_and_report_types,
    test_ui_wiring_does_not_add_sql_or_llm_execution_calls,
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

    print("Day94 Decision Console Export Wiring Acceptance Summary")
    print(f"Total: {len(TESTS)}")
    print(f"Passed: {passed}")
    print(f"Failed: {len(failures)}")

    for failure in failures:
        print(f"- {failure}")

    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    run_acceptance()
