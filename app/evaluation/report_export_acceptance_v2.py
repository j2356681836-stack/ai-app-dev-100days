from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from app.delivery.analysis_investigation_snapshot_v1 import (
    AnalysisInvestigationSnapshotV1,
)
from app.delivery.analysis_session_history_v1 import (
    build_analysis_history_item_v1,
)
from app.delivery.decision_console_entry_v2 import (
    PeriodicReportCadenceV2,
)
from app.delivery.executive_decision_brief_v2 import (
    build_executive_decision_brief_preview_v2,
)
from app.delivery.investigation_report_v2 import (
    build_investigation_report_v2,
)
from app.delivery.periodic_business_report_v2 import (
    PeriodicBusinessReportStatusV2,
    PeriodicBusinessReportV2,
    PeriodicMetricDisplayKindV2,
    PeriodicMetricSectionV2,
    PeriodicMetricSnapshotV2,
    PeriodicMetricSpecV2,
    PeriodicMetricStatusV2,
)
from app.delivery.report_export_v2 import (
    render_investigation_report_html_v2,
    render_investigation_report_markdown_v2,
    render_periodic_report_html_v2,
    render_periodic_report_markdown_v2,
)
from app.delivery.runtime_delivery_bridge_v2 import (
    RuntimeDeliveryBridgeResultV2,
    RuntimeDeliveryBridgeStatusV2,
)
from app.evaluation.executive_decision_brief_acceptance_v2 import (
    _comparison,
    _delivery,
    _view,
)
from app.agents.investigation_contracts_v2 import (
    AnalysisModeV2,
)


def _runtime_delivery(
    *,
    question: str = "为什么 <script>alert('x')</script> 7 月 GMV 同比变化？",
) -> RuntimeDeliveryBridgeResultV2:
    delivery = _delivery()
    view = _view()

    brief = build_executive_decision_brief_preview_v2(
        request_subject=question,
        delivery=delivery,
        console_view=view,
    )

    return RuntimeDeliveryBridgeResultV2(
        status=RuntimeDeliveryBridgeStatusV2.READY,
        message="当前 GMV 为 120。",
        safe_runtime_result={
            "success": True,
            "outcome": "answered",
        },
        requested_analysis_mode=AnalysisModeV2.INVESTIGATION,
        delivery=delivery,
        console_view=view,
        executive_brief=brief,
    )


def _investigation_report():
    runtime = _runtime_delivery()

    history = build_analysis_history_item_v1(
        original_question=(
            "为什么 <script>alert('x')</script> 7 月 GMV 同比变化？"
        ),
        runtime_delivery=runtime,
        history_id="history_day94_export",
        created_at_utc=datetime(
            2026,
            9,
            2,
            0,
            0,
            tzinfo=timezone.utc,
        ),
    )

    return build_investigation_report_v2(
        history_item=history,
        investigation_snapshot=(
            AnalysisInvestigationSnapshotV1()
        ),
    )


def _periodic_report() -> PeriodicBusinessReportV2:
    spec = PeriodicMetricSpecV2(
        metric_name="gmv",
        plan_name="gmv_overall_v2",
        chinese_name="GMV",
        section=PeriodicMetricSectionV2.OVERVIEW,
        display_kind=PeriodicMetricDisplayKindV2.MONEY,
        required=True,
        tool_name="governed_periodic_gmv_overall_query",
        purpose="测试周期经营报表导出。",
    )

    snapshot = PeriodicMetricSnapshotV2(
        spec=spec,
        status=PeriodicMetricStatusV2.READY,
        message="当前/参考窗口可信比较已形成。",
        current_value=Decimal("120"),
        reference_value=Decimal("100"),
        absolute_change=Decimal("20"),
        relative_change=Decimal("0.2"),
        current_evidence_id="ev-periodic-current",
        reference_evidence_id="ev-periodic-reference",
    )

    return PeriodicBusinessReportV2(
        status=PeriodicBusinessReportStatusV2.READY,
        message="周期经营报表全部已注册指标形成可信交付。",
        cadence=PeriodicReportCadenceV2.MONTHLY,
        anchor_date=date(2025, 7, 31),
        comparison=_comparison(),
        metrics=(snapshot,),
        ready_metric_count=1,
        failed_metric_count=0,
        required_failed_metric_names=(),
        driver_reconciliations=(),
        r12_customer_health=None,
    )


def test_investigation_markdown_and_html_share_payload_identity() -> None:
    report = _investigation_report()

    markdown = render_investigation_report_markdown_v2(
        report
    )
    html = render_investigation_report_html_v2(
        report
    )

    for token in (
        report.history_id,
        report.metric_name,
        str(report.analysis_window.start_date),
        str(report.analysis_window.end_date),
        report.evidence_lineage[0].evidence_ids[0],
    ):
        assert token in markdown
        assert token in html


def test_investigation_export_preserves_epistemic_limitations() -> None:
    report = _investigation_report()

    markdown = render_investigation_report_markdown_v2(
        report
    )

    for item in report.executive_brief.limitations:
        assert item.code.value in markdown
        assert item.detail in markdown


def test_investigation_html_escapes_business_text() -> None:
    report = _investigation_report()

    html = render_investigation_report_html_v2(
        report
    )

    assert "<script>alert('x')</script>" not in html
    assert "&lt;script&gt;" in html


def test_periodic_markdown_and_html_share_payload_identity() -> None:
    report = _periodic_report()

    markdown = render_periodic_report_markdown_v2(
        report
    )
    html = render_periodic_report_html_v2(
        report
    )

    snapshot = report.metrics[0]

    for token in (
        report.contract_version,
        report.cadence.value,
        snapshot.spec.metric_name,
        snapshot.current_evidence_id,
        snapshot.reference_evidence_id,
    ):
        assert token in markdown
        assert token in html


def test_periodic_export_uses_existing_ratio_and_delta_fields_only() -> None:
    report = _periodic_report()

    markdown = render_periodic_report_markdown_v2(
        report
    )

    snapshot = report.metrics[0]

    assert str(snapshot.current_value) in markdown
    assert str(snapshot.reference_value) in markdown
    assert str(snapshot.absolute_change) in markdown
    assert "20.0%" in markdown


def test_exports_are_deterministic_for_same_payload() -> None:
    investigation = _investigation_report()
    periodic = _periodic_report()

    assert (
        render_investigation_report_markdown_v2(
            investigation
        )
        == render_investigation_report_markdown_v2(
            investigation
        )
    )

    assert (
        render_investigation_report_html_v2(
            investigation
        )
        == render_investigation_report_html_v2(
            investigation
        )
    )

    assert (
        render_periodic_report_markdown_v2(periodic)
        == render_periodic_report_markdown_v2(periodic)
    )

    assert (
        render_periodic_report_html_v2(periodic)
        == render_periodic_report_html_v2(periodic)
    )


def test_export_module_does_not_release_forbidden_runtime_fields() -> None:
    report = _investigation_report()

    markdown = render_investigation_report_markdown_v2(
        report
    )
    html = render_investigation_report_html_v2(
        report
    )

    forbidden = (
        "compiled_sql",
        "sql_parameters",
        "governed_query_context",
        "raw_rows",
        "database_url",
    )

    lowered = (markdown + html).lower()

    assert not any(
        token in lowered
        for token in forbidden
    )


TESTS = (
    test_investigation_markdown_and_html_share_payload_identity,
    test_investigation_export_preserves_epistemic_limitations,
    test_investigation_html_escapes_business_text,
    test_periodic_markdown_and_html_share_payload_identity,
    test_periodic_export_uses_existing_ratio_and_delta_fields_only,
    test_exports_are_deterministic_for_same_payload,
    test_export_module_does_not_release_forbidden_runtime_fields,
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

    print("Day94 Report Export V2 Acceptance Summary")
    print(f"Total: {len(TESTS)}")
    print(f"Passed: {passed}")
    print(f"Failed: {len(failures)}")

    for failure in failures:
        print(f"- {failure}")

    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    run_acceptance()
