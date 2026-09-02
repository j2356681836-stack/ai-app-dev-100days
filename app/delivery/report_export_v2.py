from __future__ import annotations

from html import escape

from app.delivery.investigation_report_v2 import (
    InvestigationReportV2,
)
from app.delivery.periodic_business_report_v2 import (
    PeriodicBusinessReportV2,
    PeriodicMetricDisplayKindV2,
    PeriodicMetricStatusV2,
)


REPORT_EXPORT_VERSION = "report_export_v2_0"


def _text(value: object | None) -> str:
    if value is None:
        return "—"
    return str(value)


def _decimal_text(value: object | None) -> str:
    if value is None:
        return "—"
    return str(value)


def _ratio_text(value: object | None) -> str:
    if value is None:
        return "—"
    return f"{value * 100}%"


def _periodic_value_text(
    *,
    value,
    display_kind: PeriodicMetricDisplayKindV2,
) -> str:
    if value is None:
        return "不可释放"

    if display_kind == PeriodicMetricDisplayKindV2.RATIO:
        return _ratio_text(value)

    return _decimal_text(value)


def render_investigation_report_markdown_v2(
    report: InvestigationReportV2,
) -> str:
    """
    InvestigationReportV2 -> deterministic Markdown.

    只读取 Final Report Payload；
    不执行 SQL、不调用 LLM、不重新计算业务指标或 Reconciliation。
    """

    brief = report.executive_brief

    lines: list[str] = [
        "# Investigation Report",
        "",
        f"- Contract: `{report.contract_version}`",
        f"- History ID: `{report.history_id}`",
        f"- Metric: `{report.metric_name}`",
        f"- Result Grain: `{report.result_grain}`",
        (
            "- Analysis Window: "
            f"`{report.analysis_window.start_date}` → "
            f"`{report.analysis_window.end_date}`"
        ),
        "",
        "## Business Question",
        "",
        report.original_question,
        "",
    ]

    if report.resolved_question:
        lines.extend(
            [
                "## Resolved Question",
                "",
                report.resolved_question,
                "",
            ]
        )

    if report.resolution_note:
        lines.extend(
            [
                "## Resolution Note",
                "",
                report.resolution_note,
                "",
            ]
        )

    lines.extend(
        [
            "## Executive Brief",
            "",
            f"- Evidence Sufficiency: `{brief.evidence_sufficiency.value}`",
            f"- Confidence: `{brief.evidence_confidence_level}`",
            "",
            "### Key Findings",
            "",
        ]
    )

    if brief.key_findings:
        for item in brief.key_findings:
            evidence = ", ".join(item.evidence_ids) or "—"
            lines.append(
                f"- {item.summary}  "
                f"(Evidence: `{evidence}`)"
            )
    else:
        lines.append("- 当前没有可释放的 evidence-backed finding。")

    lines.extend(["", "### Confirmed Facts", ""])
    if brief.confirmed_facts:
        lines.extend(f"- {item}" for item in brief.confirmed_facts)
    else:
        lines.append("- —")

    lines.extend(["", "### Candidate Hypotheses", ""])
    if brief.candidate_hypotheses:
        lines.extend(
            f"- {item}"
            for item in brief.candidate_hypotheses
        )
    else:
        lines.append("- —")

    lines.extend(["", "### Unknowns", ""])
    if brief.unknowns:
        lines.extend(f"- {item}" for item in brief.unknowns)
    else:
        lines.append("- —")

    lines.extend(["", "### Recommended Checks", ""])
    if brief.recommended_checks:
        lines.extend(
            f"- {item}"
            for item in brief.recommended_checks
        )
    else:
        lines.append("- —")

    lines.extend(["", "### Limitations", ""])
    if brief.limitations:
        lines.extend(
            (
                f"- `{item.code.value}`: "
                f"{item.detail}"
            )
            for item in brief.limitations
        )
    else:
        lines.append("- 当前没有额外 limitation。")

    lines.extend(["", "## Evidence Lineage", ""])

    for item in report.evidence_lineage:
        evidence = ", ".join(item.evidence_ids) or "—"
        plans = ", ".join(item.plan_names) or "—"
        audits = ", ".join(item.audit_event_ids) or "—"
        lines.extend(
            [
                (
                    f"### {item.sequence_number}. "
                    f"{item.business_label}"
                ),
                "",
                f"- Stage: `{item.stage.value}`",
                f"- Dimension: `{_text(item.dimension)}`",
                f"- Evidence IDs: `{evidence}`",
                f"- Query Plans: `{plans}`",
                f"- Audit Events: `{audits}`",
                f"- Scope: {_text(item.scope_summary)}",
                (
                    "- Reconciliation: "
                    f"`{_text(item.reconciliation_status)}`"
                ),
                "",
            ]
        )

    lines.extend(["## Fact Composition", ""])

    if report.fact_compositions:
        for item in report.fact_compositions:
            lines.extend(
                [
                    (
                        f"### {item.metric_name} × "
                        f"{item.dimension.value}"
                    ),
                    "",
                    f"- Status: `{item.status.value}`",
                    (
                        "- Reconciliation: "
                        f"`{item.reconciliation_status.value}`"
                    ),
                    (
                        "- Overall Value: "
                        f"`{_decimal_text(item.overall_value)}`"
                    ),
                    (
                        "- Member Sum: "
                        f"`{_decimal_text(item.member_sum)}`"
                    ),
                    (
                        "- Unexplained Remainder: "
                        f"`{_decimal_text(item.unexplained_remainder)}`"
                    ),
                    "",
                ]
            )
    else:
        lines.extend(["- —", ""])

    lines.extend(["## Investigation Steps", ""])

    if report.investigation_steps:
        for item in report.investigation_steps:
            result = item.result
            lines.extend(
                [
                    (
                        f"### {result.dimension_name.value}"
                    ),
                    "",
                    (
                        "- Focus Delta: "
                        f"`{_decimal_text(result.focus_delta)}`"
                    ),
                    (
                        "- Member Delta Sum: "
                        f"`{_decimal_text(result.sum_member_delta)}`"
                    ),
                    (
                        "- Unexplained Remainder: "
                        f"`{_decimal_text(result.unexplained_remainder)}`"
                    ),
                    (
                        "- Reconciliation: "
                        f"`{result.reconciliation_status.value}`"
                    ),
                    "",
                ]
            )
    else:
        lines.extend(["- —", ""])

    lines.extend(["## User Exploration Steps", ""])

    if report.user_exploration_steps:
        for item in report.user_exploration_steps:
            result = item.result
            lines.extend(
                [
                    (
                        f"- `{result.dimension_name.value}` | "
                        f"reconciliation="
                        f"`{result.reconciliation_status.value}` | "
                        f"unexplained_remainder="
                        f"`{_decimal_text(result.unexplained_remainder)}`"
                    )
                ]
            )
    else:
        lines.append("- —")

    lines.extend(
        [
            "",
            "## Trust Boundary",
            "",
            (
                "This artifact is a deterministic projection of the "
                "structured InvestigationReportV2 payload. "
                "It does not execute SQL, invoke an LLM, or regenerate "
                "business conclusions."
            ),
            "",
        ]
    )

    return "\n".join(lines)


def render_investigation_report_html_v2(
    report: InvestigationReportV2,
) -> str:
    """
    InvestigationReportV2 -> deterministic standalone HTML.

    所有业务文本均 HTML escape。
    """

    markdown_like = render_investigation_report_markdown_v2(
        report
    )

    # HTML 不通过 Markdown parser 二次解释；
    # 直接把同一 deterministic textual projection 安全包裹为 <pre>，
    # 避免新增第三方 renderer 与自由格式规则。
    safe_text = escape(markdown_like)

    return (
        "<!doctype html>\n"
        '<html lang="zh-CN">\n'
        "<head>\n"
        '  <meta charset="utf-8">\n'
        "  <title>Investigation Report</title>\n"
        "</head>\n"
        "<body>\n"
        "<main>\n"
        "<h1>Investigation Report</h1>\n"
        f"<pre>{safe_text}</pre>\n"
        "</main>\n"
        "</body>\n"
        "</html>\n"
    )


def render_periodic_report_markdown_v2(
    report: PeriodicBusinessReportV2,
) -> str:
    """
    PeriodicBusinessReportV2 -> deterministic Markdown.

    只消费 Report Runtime 已经提供的可信值。
    """

    lines: list[str] = [
        "# Periodic Business Report",
        "",
        f"- Contract: `{report.contract_version}`",
        f"- Status: `{report.status.value}`",
        f"- Cadence: `{report.cadence.value}`",
        f"- Anchor Date: `{report.anchor_date}`",
        (
            "- Reference Window: "
            f"`{report.comparison.reference_window.start_date}` → "
            f"`{report.comparison.reference_window.end_date}`"
        ),
        (
            "- Current Window: "
            f"`{report.comparison.current_window.start_date}` → "
            f"`{report.comparison.current_window.end_date}`"
        ),
        "",
        f"> {report.message}",
        "",
        "## KPI Snapshots",
        "",
    ]

    for item in report.metrics:
        lines.extend(
            [
                f"### {item.spec.chinese_name}",
                "",
                f"- Metric: `{item.spec.metric_name}`",
                f"- Section: `{item.spec.section.value}`",
                f"- Status: `{item.status.value}`",
            ]
        )

        if item.status == PeriodicMetricStatusV2.READY:
            lines.extend(
                [
                    (
                        "- Reference: "
                        f"`{_periodic_value_text(value=item.reference_value, display_kind=item.spec.display_kind)}`"
                    ),
                    (
                        "- Current: "
                        f"`{_periodic_value_text(value=item.current_value, display_kind=item.spec.display_kind)}`"
                    ),
                    (
                        "- Absolute Change: "
                        f"`{_decimal_text(item.absolute_change)}`"
                    ),
                    (
                        "- Relative Change: "
                        f"`{_ratio_text(item.relative_change)}`"
                    ),
                    (
                        "- Percentage Point Change: "
                        f"`{_decimal_text(item.percentage_point_change)}`"
                    ),
                    (
                        "- Reference Evidence: "
                        f"`{_text(item.reference_evidence_id)}`"
                    ),
                    (
                        "- Current Evidence: "
                        f"`{_text(item.current_evidence_id)}`"
                    ),
                ]
            )
        else:
            lines.append(
                f"- Release Message: {item.message}"
            )

        lines.append("")

    lines.extend(["## Driver Reconciliation", ""])

    if report.driver_reconciliations:
        for item in report.driver_reconciliations:
            lines.extend(
                [
                    f"### {item.relationship}",
                    "",
                    f"- Status: `{item.status.value}`",
                    (
                        "- Observed: "
                        f"`{_decimal_text(item.observed_value)}`"
                    ),
                    (
                        "- Reconstructed: "
                        f"`{_decimal_text(item.reconstructed_value)}`"
                    ),
                    (
                        "- Remainder: "
                        f"`{_decimal_text(item.remainder)}`"
                    ),
                    f"- Message: {item.message}",
                    "",
                ]
            )
    else:
        lines.extend(["- —", ""])

    lines.extend(["## R12 Customer Health", ""])

    trust = report.r12_customer_health

    if trust is None:
        lines.extend(["- —", ""])
    else:
        lines.extend(
            [
                f"- Status: `{trust.status.value}`",
                f"- Ready Metrics: `{trust.ready_metric_count}`",
                f"- Failed Metrics: `{trust.failed_metric_count}`",
                f"- Message: {trust.message}",
                "",
            ]
        )

        for item in trust.reconciliations:
            lines.append(
                (
                    f"- `{item.relationship}` | "
                    f"status=`{item.status.value}` | "
                    f"remainder=`{_decimal_text(item.remainder)}`"
                )
            )

        lines.append("")

    lines.extend(
        [
            "## Trust Boundary",
            "",
            (
                "This artifact is a deterministic projection of the "
                "structured PeriodicBusinessReportV2 payload. "
                "It does not execute SQL, invoke an LLM, or recompute "
                "KPI, ratio, delta, or reconciliation."
            ),
            "",
        ]
    )

    return "\n".join(lines)


def render_periodic_report_html_v2(
    report: PeriodicBusinessReportV2,
) -> str:
    """
    PeriodicBusinessReportV2 -> deterministic standalone HTML.
    """

    markdown_like = render_periodic_report_markdown_v2(
        report
    )

    safe_text = escape(markdown_like)

    return (
        "<!doctype html>\n"
        '<html lang="zh-CN">\n'
        "<head>\n"
        '  <meta charset="utf-8">\n'
        "  <title>Periodic Business Report</title>\n"
        "</head>\n"
        "<body>\n"
        "<main>\n"
        "<h1>Periodic Business Report</h1>\n"
        f"<pre>{safe_text}</pre>\n"
        "</main>\n"
        "</body>\n"
        "</html>\n"
    )
