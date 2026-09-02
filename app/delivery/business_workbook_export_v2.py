from __future__ import annotations

from io import BytesIO

import xlsxwriter

from app.delivery.investigation_report_v2 import (
    InvestigationReportV2,
)
from app.semantic_layer.analysis_mode_contract_v2 import (
    AnalysisModeV2,
)
from app.delivery.periodic_business_report_v2 import (
    PeriodicBusinessReportV2,
    PeriodicMetricDisplayKindV2,
    PeriodicMetricStatusV2,
)


BUSINESS_WORKBOOK_EXPORT_VERSION = (
    "business_workbook_export_v2_1"
)


def _workbook_formats(workbook):
    header = workbook.add_format(
        {
            "bold": True,
            "bg_color": "#E5E7EB",
            "border": 1,
            "align": "center",
            "valign": "vcenter",
        }
    )
    label = workbook.add_format(
        {
            "bold": True,
            "border": 1,
            "valign": "top",
        }
    )
    text = workbook.add_format(
        {
            "border": 1,
            "text_wrap": True,
            "valign": "top",
        }
    )
    money = workbook.add_format(
        {
            "border": 1,
            "num_format": "#,##0.00",
        }
    )
    count = workbook.add_format(
        {
            "border": 1,
            "num_format": "#,##0",
        }
    )
    percentage = workbook.add_format(
        {
            "border": 1,
            "num_format": "0.00%",
        }
    )
    decimal = workbook.add_format(
        {
            "border": 1,
            "num_format": "0.00",
        }
    )
    good = workbook.add_format(
        {
            "border": 1,
            "text_wrap": True,
            "bg_color": "#ECFDF5",
        }
    )
    warning = workbook.add_format(
        {
            "border": 1,
            "text_wrap": True,
            "bg_color": "#FFF7ED",
        }
    )

    return {
        "header": header,
        "label": label,
        "text": text,
        "money": money,
        "count": count,
        "percentage": percentage,
        "decimal": decimal,
        "good": good,
        "warning": warning,
    }


def _comparison_change_labels(comparison_type) -> tuple[str, str]:
    value = comparison_type.value

    if value == "mom":
        return "环比增长额", "环比增长率"
    if value == "yoy":
        return "同比增长额", "同比增长率"
    if value == "wow":
        return "周环比增长额", "周环比增长率"
    if value == "dod":
        return "日环比增长额", "日环比增长率"

    return "变化额", "变化率"


def _period_label(window) -> str:
    start = window.start_date
    end = window.end_date

    if (
        start.year == end.year
        and start.month == end.month
        and start.day == 1
        and end.day >= 28
    ):
        return f"{start.year}年{start.month}月"

    if start == end:
        return str(start)

    return f"{start} 至 {end}"



def _report_mode_group_v2(
    report: InvestigationReportV2,
) -> str:
    if report.analysis_mode in {
        AnalysisModeV2.FACT,
        AnalysisModeV2.COMPOSITION,
    }:
        return "fact"

    if (
        report.analysis_mode
        == AnalysisModeV2.COMPARISON
    ):
        return "comparison"

    return "investigation"


def _evidence_sufficiency_label_v2(
    value,
) -> str:
    raw = (
        value.value
        if hasattr(value, "value")
        else str(value)
    )

    return {
        "sufficient_for_current_scope": "当前范围证据充分",
        "partial": "部分充分",
        "insufficient": "证据不足",
    }.get(
        raw,
        raw,
    )


def _write_core_result_v2(
    workbook,
    *,
    report: InvestigationReportV2,
    formats,
    sheet_name: str = "01_核心结果",
) -> None:
    worksheet = workbook.add_worksheet(
        sheet_name
    )

    rows = (
        (
            "业务问题",
            report.original_question,
        ),
        (
            "指标",
            (
                f"{report.metric_definition.chinese_name}"
                f"（{report.metric_name}）"
            ),
        ),
        (
            "分析窗口",
            (
                f"{report.analysis_window.start_date} 至 "
                f"{report.analysis_window.end_date}"
            ),
        ),
        (
            "核心结果",
            report.answer_snapshot,
        ),
    )

    worksheet.write(
        0,
        0,
        "项目",
        formats["header"],
    )
    worksheet.write(
        0,
        1,
        "内容",
        formats["header"],
    )

    for row_index, (label, value) in enumerate(
        rows,
        start=1,
    ):
        worksheet.write(
            row_index,
            0,
            label,
            formats["label"],
        )
        worksheet.write(
            row_index,
            1,
            value,
            formats["text"],
        )

    worksheet.set_column(
        "A:A",
        18,
    )
    worksheet.set_column(
        "B:B",
        80,
    )


def _write_investigation_core_comparison(
    workbook,
    *,
    report: InvestigationReportV2,
    formats,
    sheet_name: str = "01_核心对比",
) -> None:
    worksheet = workbook.add_worksheet(
        sheet_name
    )

    comparison = report.comparison_summary

    if comparison is None:
        worksheet.write(
            0,
            0,
            "说明",
            formats["header"],
        )
        worksheet.write(
            1,
            0,
            "当前报告没有独立的整体时间比较结果。",
            formats["warning"],
        )
        worksheet.set_column(
            "A:A",
            55,
        )
        return

    change_label, rate_label = (
        _comparison_change_labels(
            comparison.comparison_type
        )
    )

    headers = (
        "指标",
        _period_label(
            comparison.reference_window
        ),
        _period_label(
            comparison.current_window
        ),
        change_label,
        rate_label,
    )

    for col, header in enumerate(
        headers
    ):
        worksheet.write(
            0,
            col,
            header,
            formats["header"],
        )

    worksheet.write(
        1,
        0,
        report.metric_definition.chinese_name,
        formats["label"],
    )
    worksheet.write_number(
        1,
        1,
        float(
            comparison.reference_value
        ),
        formats["money"],
    )
    worksheet.write_number(
        1,
        2,
        float(
            comparison.current_value
        ),
        formats["money"],
    )
    worksheet.write_number(
        1,
        3,
        float(
            comparison.absolute_change
        ),
        formats["money"],
    )

    if comparison.relative_change is None:
        worksheet.write(
            1,
            4,
            "不可定义",
            formats["warning"],
        )
    else:
        worksheet.write_number(
            1,
            4,
            float(
                comparison.relative_change
            ),
            formats["percentage"],
        )

    worksheet.freeze_panes(
        1,
        1,
    )
    worksheet.set_column(
        "A:A",
        18,
    )
    worksheet.set_column(
        "B:E",
        20,
    )




def _investigation_dimension_label_v2(
    value: str,
) -> str:
    return {
        "channel": "渠道",
        "category": "品类",
        "region": "城市",
        "area": "大区",
        "province": "省级地区",
        "city": "城市",
        "campaign": "活动实例",
    }.get(value, value)


def _xlsx_dedupe_text_v2(
    values,
) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()

    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)

    return tuple(result)


def _xlsx_investigation_all_steps_v2(
    report: InvestigationReportV2,
):
    return (
        *report.investigation_steps,
        *report.user_exploration_steps,
    )


def _xlsx_investigation_next_steps_v2(
    report: InvestigationReportV2,
) -> tuple[str, ...]:
    values: list[str] = list(
        report.executive_brief.recommended_checks
    )

    for step in _xlsx_investigation_all_steps_v2(
        report
    ):
        if step.assessment is None:
            continue
        values.append(
            step.assessment.next_step_recommendation
        )

    return _xlsx_dedupe_text_v2(
        values
    )


def _write_investigation_decision_summary_v2(
    workbook,
    *,
    report: InvestigationReportV2,
    formats,
) -> None:
    worksheet = workbook.add_worksheet(
        "01_决策摘要"
    )

    worksheet.write(
        0,
        0,
        "决策摘要",
        formats["header"],
    )
    worksheet.write(
        0,
        1,
        "内容",
        formats["header"],
    )

    row_index = 1

    worksheet.write(
        row_index,
        0,
        "业务问题",
        formats["label"],
    )
    worksheet.write(
        row_index,
        1,
        report.original_question,
        formats["text"],
    )
    row_index += 1

    comparison = report.comparison_summary

    if comparison is not None:
        _, rate_label = _comparison_change_labels(
            comparison.comparison_type
        )

        worksheet.write(
            row_index,
            0,
            "整体变化",
            formats["label"],
        )
        worksheet.write(
            row_index,
            1,
            (
                f"{_period_label(comparison.current_window)}较"
                f"{_period_label(comparison.reference_window)}"
                f"变化 {comparison.absolute_change:,.2f}；"
                f"{rate_label} "
                f"{comparison.relative_change * 100:.2f}%"
                if comparison.relative_change is not None
                else (
                    f"{_period_label(comparison.current_window)}较"
                    f"{_period_label(comparison.reference_window)}"
                    f"变化 {comparison.absolute_change:,.2f}；"
                    f"{rate_label} 不可定义"
                )
            ),
            formats["text"],
        )
        row_index += 1

    worksheet.write(
        row_index,
        0,
        "证据状态",
        formats["label"],
    )
    worksheet.write(
        row_index,
        1,
        _evidence_sufficiency_label_v2(
            report.executive_brief.evidence_sufficiency
        ),
        formats["good"],
    )
    row_index += 1

    finding_index = 0
    for step in _xlsx_investigation_all_steps_v2(
        report
    ):
        if (
            step.assessment is None
            or not step.assessment.conclusion.strip()
        ):
            continue

        finding_index += 1
        worksheet.write(
            row_index,
            0,
            f"调查发现 {finding_index}",
            formats["label"],
        )
        worksheet.write(
            row_index,
            1,
            step.assessment.conclusion,
            formats["text"],
        )
        row_index += 1

    next_steps = _xlsx_investigation_next_steps_v2(
        report
    )

    if next_steps:
        worksheet.write(
            row_index,
            0,
            "优先下一步",
            formats["label"],
        )
        worksheet.write(
            row_index,
            1,
            next_steps[0],
            formats["text"],
        )

    worksheet.set_column(
        "A:A",
        18,
    )
    worksheet.set_column(
        "B:B",
        90,
    )

def _write_investigation_detail(
    workbook,
    *,
    report: InvestigationReportV2,
    formats,
    sheet_name: str = "02_调查明细",
) -> None:
    """
    Investigation detail uses one visual block per investigation step.
    """

    worksheet = workbook.add_worksheet(
        sheet_name
    )

    row_index = 0
    sequence = 0

    for source_label, steps in (
        (
            "受控调查",
            report.investigation_steps,
        ),
        (
            "用户主动探索",
            report.user_exploration_steps,
        ),
    ):
        for step in steps:
            sequence += 1
            result = step.result
            dimension_label = (
                _investigation_dimension_label_v2(
                    result.dimension_name.value
                )
            )
            conclusion = (
                step.assessment.conclusion
                if step.assessment is not None
                else ""
            )

            worksheet.merge_range(
                row_index,
                0,
                row_index,
                4,
                (
                    f"调查步骤 {sequence}｜"
                    f"{dimension_label}变化"
                ),
                formats["header"],
            )
            row_index += 1

            worksheet.write(
                row_index,
                0,
                "方向来源",
                formats["label"],
            )
            worksheet.merge_range(
                row_index,
                1,
                row_index,
                4,
                source_label,
                formats["text"],
            )
            row_index += 1

            if conclusion:
                worksheet.write(
                    row_index,
                    0,
                    "本轮结论",
                    formats["label"],
                )
                worksheet.merge_range(
                    row_index,
                    1,
                    row_index,
                    4,
                    conclusion,
                    formats["text"],
                )
                row_index += 1

            headers = (
                "成员",
                "参考期",
                "当前期",
                "变化额",
                "占本轮变化",
            )

            for col, header in enumerate(
                headers
            ):
                worksheet.write(
                    row_index,
                    col,
                    header,
                    formats["header"],
                )

            row_index += 1

            for member in result.members:
                worksheet.write(
                    row_index,
                    0,
                    member.member_label,
                    formats["text"],
                )
                worksheet.write_number(
                    row_index,
                    1,
                    float(member.reference_value),
                    formats["money"],
                )
                worksheet.write_number(
                    row_index,
                    2,
                    float(member.current_value),
                    formats["money"],
                )
                worksheet.write_number(
                    row_index,
                    3,
                    float(member.delta),
                    formats["money"],
                )

                if member.share_of_focus_delta is None:
                    worksheet.write_blank(
                        row_index,
                        4,
                        None,
                        formats["percentage"],
                    )
                else:
                    worksheet.write_number(
                        row_index,
                        4,
                        float(
                            member.share_of_focus_delta
                        ),
                        formats["percentage"],
                    )

                row_index += 1

            worksheet.write(
                row_index,
                0,
                "汇总",
                formats["label"],
            )
            worksheet.write_number(
                row_index,
                1,
                float(result.reference_focus_value),
                formats["money"],
            )
            worksheet.write_number(
                row_index,
                2,
                float(result.current_focus_value),
                formats["money"],
            )
            worksheet.write_number(
                row_index,
                3,
                float(result.focus_delta),
                formats["money"],
            )

            if (
                result.focus_delta != 0
                and result.reconciliation_status.value
                == "reconciled"
            ):
                worksheet.write_number(
                    row_index,
                    4,
                    1.0,
                    formats["percentage"],
                )
            else:
                worksheet.write_blank(
                    row_index,
                    4,
                    None,
                    formats["percentage"],
                )

            row_index += 1

            worksheet.write(
                row_index,
                0,
                "核对状态",
                formats["label"],
            )
            worksheet.write(
                row_index,
                1,
                _reconciliation_label(
                    result.reconciliation_status
                ),
                formats["good"]
                if (
                    result.reconciliation_status.value
                    == "reconciled"
                )
                else formats["warning"],
            )
            worksheet.write(
                row_index,
                2,
                "未解释差额",
                formats["label"],
            )
            worksheet.write_number(
                row_index,
                3,
                float(result.unexplained_remainder),
                formats["money"],
            )

            row_index += 3

    worksheet.set_column(
        "A:A",
        24,
    )
    worksheet.set_column(
        "B:D",
        18,
    )
    worksheet.set_column(
        "E:E",
        18,
    )




def _is_public_fact_composition_v2(
    result,
) -> bool:
    return result.dimension.value != "membership_level"


def _public_fact_compositions_v2(
    report: InvestigationReportV2,
):
    return tuple(
        result
        for result in report.fact_compositions
        if _is_public_fact_composition_v2(
            result
        )
    )


def _composition_business_label_v2(
    value: str,
) -> str:
    return {
        "membership_level": "人群构成",
        "channel": "渠道构成",
        "category": "品类构成",
        "region": "地区构成",
    }.get(
        value,
        value,
    )

def _write_composition(
    workbook,
    *,
    report: InvestigationReportV2,
    formats,
    sheet_name: str,
) -> None:
    """
    Business XLSX Composition。

    所有公开维度保留在同一 Sheet，但每个维度使用独立区块，
    不再把不同维度挤成一张连续明细表。
    每个区块最后一行“汇总”直接使用 trusted Overall。
    """

    worksheet = workbook.add_worksheet(
        sheet_name
    )

    row_index = 0

    for result in _public_fact_compositions_v2(
        report
    ):
        title = _composition_business_label_v2(
            result.dimension.value
        )

        worksheet.merge_range(
            row_index,
            0,
            row_index,
            3,
            title,
            formats["header"],
        )
        row_index += 1

        headers = (
            "排名",
            "成员",
            report.metric_definition.chinese_name,
            "构成占比",
        )

        for col, header in enumerate(
            headers
        ):
            worksheet.write(
                row_index,
                col,
                header,
                formats["header"],
            )

        row_index += 1

        for member in result.members:
            worksheet.write_number(
                row_index,
                0,
                member.rank,
                formats["count"],
            )
            worksheet.write(
                row_index,
                1,
                member.member_label,
                formats["text"],
            )
            worksheet.write_number(
                row_index,
                2,
                float(member.value),
                formats["money"],
            )

            if member.share is None:
                worksheet.write_blank(
                    row_index,
                    3,
                    None,
                    formats["percentage"],
                )
            else:
                worksheet.write_number(
                    row_index,
                    3,
                    float(member.share),
                    formats["percentage"],
                )

            row_index += 1

        worksheet.write(
            row_index,
            0,
            "",
            formats["label"],
        )
        worksheet.write(
            row_index,
            1,
            "汇总",
            formats["label"],
        )

        if result.overall_value is None:
            worksheet.write_blank(
                row_index,
                2,
                None,
                formats["money"],
            )
            worksheet.write(
                row_index,
                3,
                "未定义",
                formats["label"],
            )
        else:
            worksheet.write_number(
                row_index,
                2,
                float(result.overall_value),
                formats["money"],
            )

            if result.overall_value == 0:
                worksheet.write(
                    row_index,
                    3,
                    "未定义",
                    formats["label"],
                )
            else:
                worksheet.write_number(
                    row_index,
                    3,
                    1.0,
                    formats["percentage"],
                )

        row_index += 2

    worksheet.set_column(
        "A:A",
        10,
    )
    worksheet.set_column(
        "B:B",
        28,
    )
    worksheet.set_column(
        "C:C",
        18,
    )
    worksheet.set_column(
        "D:D",
        16,
    )



def _write_business_trust(
    workbook,
    *,
    report: InvestigationReportV2,
    formats,
    sheet_name: str,
) -> None:
    worksheet = workbook.add_worksheet(
        sheet_name
    )

    worksheet.write(
        0,
        0,
        "业务口径",
        formats["header"],
    )
    worksheet.write(
        0,
        1,
        "内容",
        formats["header"],
    )

    metric_rows = (
        (
            "指标",
            (
                f"{report.metric_definition.chinese_name}"
                f"（{report.metric_name}）"
            ),
        ),
        (
            "定义",
            report.metric_definition.definition,
        ),
        (
            "公式",
            report.metric_definition.formula,
        ),
        (
            "基础粒度",
            report.metric_definition.grain,
        ),
        (
            "过滤条件",
            (
                "；".join(
                    report.metric_definition.filters
                )
                if report.metric_definition.filters
                else "无额外过滤条件"
            ),
        ),
        (
            "证据充分性",
            _evidence_sufficiency_label_v2(
                report.executive_brief.evidence_sufficiency
            ),
        ),
    )

    for row_index, (
        label,
        value,
    ) in enumerate(
        metric_rows,
        start=1,
    ):
        worksheet.write(
            row_index,
            0,
            label,
            formats["label"],
        )
        worksheet.write(
            row_index,
            1,
            value,
            formats["text"],
        )

    start_row = len(metric_rows) + 3

    trust_headers = (
        "可信核对项",
        "状态",
        "业务说明",
    )

    for col, header in enumerate(
        trust_headers
    ):
        worksheet.write(
            start_row,
            col,
            header,
            formats["header"],
        )

    trust_row = start_row + 1
    wrote_trust_row = False

    if report.comparison_summary is not None:
        worksheet.write(
            trust_row,
            0,
            "整体时间比较",
            formats["text"],
        )
        worksheet.write(
            trust_row,
            1,
            "已验证",
            formats["good"],
        )
        worksheet.write(
            trust_row,
            2,
            "参考期与当前期均来自受治理的可信指标结果。",
            formats["text"],
        )
        trust_row += 1
        wrote_trust_row = True

    for result in _public_fact_compositions_v2(report):
        status = _reconciliation_label(
            result.reconciliation_status
        )

        worksheet.write(
            trust_row,
            0,
            (
                "构成核对｜"
                f"{result.dimension.value}"
            ),
            formats["text"],
        )
        worksheet.write(
            trust_row,
            1,
            status,
            (
                formats["good"]
                if status == "已对账"
                else formats["warning"]
            ),
        )
        worksheet.write(
            trust_row,
            2,
            (
                f"构成合计={result.member_sum}；"
                f"可信 Overall={result.overall_value}；"
                f"未解释差额={result.unexplained_remainder}"
            ),
            formats["text"],
        )
        trust_row += 1
        wrote_trust_row = True

    if (
        _report_mode_group_v2(report)
        == "investigation"
    ):
        for index, step in enumerate(
            (
                *report.investigation_steps,
                *report.user_exploration_steps,
            ),
            start=1,
        ):
            result = step.result
            status = _reconciliation_label(
                result.reconciliation_status
            )

            worksheet.write(
                trust_row,
                0,
                f"调查步骤 {index} 对账",
                formats["text"],
            )
            worksheet.write(
                trust_row,
                1,
                status,
                (
                    formats["good"]
                    if status == "已对账"
                    else formats["warning"]
                ),
            )
            worksheet.write(
                trust_row,
                2,
                (
                    "未解释差额："
                    f"{result.unexplained_remainder}"
                ),
                formats["text"],
            )
            trust_row += 1
            wrote_trust_row = True

        worksheet.write(
            trust_row,
            0,
            "因果结论",
            formats["text"],
        )
        worksheet.write(
            trust_row,
            1,
            "未证明",
            formats["warning"],
        )
        worksheet.write(
            trust_row,
            2,
            "当前数值分解只能定位变化主要发生在哪里，不能单独证明业务因果。",
            formats["text"],
        )
        trust_row += 1
        wrote_trust_row = True

    if not wrote_trust_row:
        worksheet.write(
            trust_row,
            0,
            "指标口径",
            formats["text"],
        )
        worksheet.write(
            trust_row,
            1,
            "已记录",
            formats["good"],
        )
        worksheet.write(
            trust_row,
            2,
            "本次业务结果与指标定义、分析窗口及受治理交付保持一致。",
            formats["text"],
        )

    worksheet.set_column(
        "A:A",
        24,
    )
    worksheet.set_column(
        "B:B",
        20,
    )
    worksheet.set_column(
        "C:C",
        72,
    )



def render_investigation_business_xlsx_v2(
    report: InvestigationReportV2,
) -> bytes:
    """
    Mode-aware business-facing XLSX.

    Investigation:
    01 决策摘要
    02 核心对比 / 核心结果
    03 调查明细
    后续可选构成与业务口径。
    """

    buffer = BytesIO()
    workbook = xlsxwriter.Workbook(
        buffer,
        {"in_memory": True},
    )
    formats = _workbook_formats(
        workbook
    )

    mode_group = _report_mode_group_v2(
        report
    )

    if mode_group == "investigation":
        _write_investigation_decision_summary_v2(
            workbook,
            report=report,
            formats=formats,
        )

        if report.comparison_summary is not None:
            _write_investigation_core_comparison(
                workbook,
                report=report,
                formats=formats,
                sheet_name="02_核心对比",
            )
        else:
            _write_core_result_v2(
                workbook,
                report=report,
                formats=formats,
                sheet_name="02_核心结果",
            )

        next_index = 3

        if (
            report.investigation_steps
            or report.user_exploration_steps
        ):
            _write_investigation_detail(
                workbook,
                report=report,
                formats=formats,
                sheet_name="03_调查明细",
            )
            next_index = 4

    else:
        if (
            mode_group == "comparison"
            and report.comparison_summary is not None
        ):
            _write_investigation_core_comparison(
                workbook,
                report=report,
                formats=formats,
            )
        else:
            _write_core_result_v2(
                workbook,
                report=report,
                formats=formats,
            )

        next_index = 2

    if _public_fact_compositions_v2(report):
        _write_composition(
            workbook,
            report=report,
            formats=formats,
            sheet_name=(
                f"{next_index:02d}_构成分析"
            ),
        )
        next_index += 1

    _write_business_trust(
        workbook,
        report=report,
        formats=formats,
        sheet_name=(
            f"{next_index:02d}_业务口径与可信核对"
        ),
    )

    workbook.close()
    return buffer.getvalue()




def _periodic_number_format(
    snapshot,
    formats,
):
    kind = snapshot.spec.display_kind

    if kind == PeriodicMetricDisplayKindV2.MONEY:
        return formats["money"]

    if kind == PeriodicMetricDisplayKindV2.COUNT:
        return formats["count"]

    if kind == PeriodicMetricDisplayKindV2.RATIO:
        return formats["percentage"]

    return formats["decimal"]


def _reconciliation_label(status) -> str:
    """
    Business-facing deterministic label for reconciliation status.

    只做显示映射，不改变 reconciliation 结果本身。
    """

    raw = (
        status.value
        if hasattr(status, "value")
        else str(status)
    )

    return {
        "reconciled": "已对账",
        "not_reconciled": "未完全对账",
        "not_applicable": "当前不可验证",
        "failed": "未对账",
    }.get(
        raw,
        raw,
    )



def _periodic_business_metric_lookup_v2(
    report: PeriodicBusinessReportV2,
) -> dict[str, object]:
    return {
        item.spec.metric_name: item
        for item in report.metrics
    }


def _periodic_business_observation_v2(
    snapshot,
) -> str | None:
    if snapshot.status != PeriodicMetricStatusV2.READY:
        return None

    name = snapshot.spec.chinese_name

    if (
        snapshot.spec.display_kind
        == PeriodicMetricDisplayKindV2.RATIO
        and snapshot.percentage_point_change is not None
    ):
        value = snapshot.percentage_point_change

        if value == 0:
            return f"{name}较参考期持平。"

        direction = (
            "提升"
            if value > 0
            else "下降"
        )

        return (
            f"{name}较参考期{direction}"
            f"{abs(value):.2f} 个百分点。"
        )

    change = snapshot.relative_change

    if change is None:
        return None

    if change == 0:
        return f"{name}较参考期持平。"

    direction = (
        "上升"
        if change > 0
        else "下降"
    )

    return (
        f"{name}较参考期{direction}"
        f"{abs(change) * 100:.2f}%。"
    )


def _periodic_business_summary_lines_v2(
    report: PeriodicBusinessReportV2,
) -> tuple[str, ...]:
    lookup = _periodic_business_metric_lookup_v2(
        report
    )
    result: list[str] = []

    for metric_name in (
        "gmv",
        "buyer_count",
        "order_count",
        "spending_per_buyer",
        "aus",
        "r12_repurchase_rate",
    ):
        snapshot = lookup.get(metric_name)
        if snapshot is None:
            continue

        text = _periodic_business_observation_v2(
            snapshot
        )
        if text is not None:
            result.append(text)

    failed = tuple(
        item.spec.chinese_name
        for item in report.metrics
        if item.status != PeriodicMetricStatusV2.READY
    )

    if failed:
        result.append(
            "当前不可释放指标："
            + "、".join(failed)
            + "；请结合业务口径与可信核对页查看限制。"
        )

    return tuple(result)


def _write_periodic_summary_sheet_v2(
    workbook,
    *,
    report: PeriodicBusinessReportV2,
    formats,
) -> None:
    worksheet = workbook.add_worksheet(
        "01_经营摘要"
    )

    cadence_label = {
        "daily": "日报",
        "weekly": "周报",
        "monthly": "月报",
    }.get(
        report.cadence.value,
        report.cadence.value,
    )

    reference_window = (
        report.comparison.reference_window
    )
    current_window = (
        report.comparison.current_window
    )

    metadata = (
        ("报表周期", cadence_label),
        ("锚点日期", str(report.anchor_date)),
        (
            "参考期",
            f"{reference_window.start_date} 至 "
            f"{reference_window.end_date}",
        ),
        (
            "当前期",
            f"{current_window.start_date} 至 "
            f"{current_window.end_date}",
        ),
    )

    row_index = 0

    for label, value in metadata:
        worksheet.write(
            row_index,
            0,
            label,
            formats["label"],
        )
        worksheet.merge_range(
            row_index,
            1,
            row_index,
            4,
            value,
            formats["text"],
        )
        row_index += 1

    row_index += 1

    headers = (
        "重点指标",
        "当前期",
        "变化",
        "变化率",
    )

    for col, header in enumerate(headers):
        worksheet.write(
            row_index,
            col,
            header,
            formats["header"],
        )

    row_index += 1

    lookup = _periodic_business_metric_lookup_v2(
        report
    )

    for metric_name in (
        "gmv",
        "buyer_count",
        "order_count",
        "r12_repurchase_rate",
    ):
        snapshot = lookup.get(metric_name)

        if (
            snapshot is None
            or snapshot.status
            != PeriodicMetricStatusV2.READY
        ):
            continue

        worksheet.write(
            row_index,
            0,
            snapshot.spec.chinese_name,
            formats["text"],
        )

        value_format = _periodic_number_format(
            snapshot,
            formats,
        )

        worksheet.write_number(
            row_index,
            1,
            float(snapshot.current_value),
            value_format,
        )

        change_format = (
            formats["percentage"]
            if (
                snapshot.spec.display_kind
                == PeriodicMetricDisplayKindV2.RATIO
            )
            else value_format
        )

        worksheet.write_number(
            row_index,
            2,
            float(snapshot.absolute_change),
            change_format,
        )

        if snapshot.relative_change is None:
            worksheet.write_blank(
                row_index,
                3,
                None,
                formats["percentage"],
            )
        else:
            worksheet.write_number(
                row_index,
                3,
                float(snapshot.relative_change),
                formats["percentage"],
            )

        row_index += 1

    row_index += 1
    worksheet.write(
        row_index,
        0,
        "经营观察",
        formats["header"],
    )
    row_index += 1

    for line in _periodic_business_summary_lines_v2(
        report
    ):
        worksheet.merge_range(
            row_index,
            0,
            row_index,
            4,
            line,
            formats["text"],
        )
        row_index += 1

    worksheet.set_column(
        "A:A",
        22,
    )
    worksheet.set_column(
        "B:D",
        20,
    )
    worksheet.set_column(
        "E:E",
        36,
    )


def _write_periodic_metric_section_sheet_v2(
    workbook,
    *,
    report: PeriodicBusinessReportV2,
    formats,
    section_value: str,
    sheet_name: str,
) -> None:
    worksheet = workbook.add_worksheet(
        sheet_name
    )

    reference_label = _period_label(
        report.comparison.reference_window
    )
    current_label = _period_label(
        report.comparison.current_window
    )

    headers = (
        "指标",
        "指标说明",
        "状态",
        f"参考期\n{reference_label}",
        f"当前期\n{current_label}",
        "变化",
        "变化率",
        "百分点变化",
    )

    for col, header in enumerate(headers):
        worksheet.write(
            0,
            col,
            header,
            formats["header"],
        )

    metrics = tuple(
        item
        for item in report.metrics
        if item.spec.section.value == section_value
    )

    for row_index, snapshot in enumerate(
        metrics,
        start=1,
    ):
        worksheet.write(
            row_index,
            0,
            snapshot.spec.chinese_name,
            formats["text"],
        )
        worksheet.write(
            row_index,
            1,
            snapshot.spec.purpose,
            formats["text"],
        )
        worksheet.write(
            row_index,
            2,
            (
                "可释放"
                if snapshot.status
                == PeriodicMetricStatusV2.READY
                else "不可释放"
            ),
            formats["text"],
        )

        if snapshot.status != PeriodicMetricStatusV2.READY:
            for col in range(3, 8):
                worksheet.write_blank(
                    row_index,
                    col,
                    None,
                    formats["warning"],
                )
            continue

        value_format = _periodic_number_format(
            snapshot,
            formats,
        )

        worksheet.write_number(
            row_index,
            3,
            float(snapshot.reference_value),
            value_format,
        )
        worksheet.write_number(
            row_index,
            4,
            float(snapshot.current_value),
            value_format,
        )

        change_format = (
            formats["percentage"]
            if (
                snapshot.spec.display_kind
                == PeriodicMetricDisplayKindV2.RATIO
            )
            else value_format
        )

        worksheet.write_number(
            row_index,
            5,
            float(snapshot.absolute_change),
            change_format,
        )

        if snapshot.relative_change is None:
            worksheet.write_blank(
                row_index,
                6,
                None,
                formats["percentage"],
            )
        else:
            worksheet.write_number(
                row_index,
                6,
                float(snapshot.relative_change),
                formats["percentage"],
            )

        if snapshot.percentage_point_change is None:
            worksheet.write_blank(
                row_index,
                7,
                None,
                formats["decimal"],
            )
        else:
            worksheet.write_number(
                row_index,
                7,
                float(snapshot.percentage_point_change),
                formats["decimal"],
            )

    worksheet.freeze_panes(
        1,
        0,
    )
    worksheet.set_column(
        "A:A",
        20,
    )
    worksheet.set_column(
        "B:B",
        52,
    )
    worksheet.set_column(
        "C:C",
        14,
    )
    worksheet.set_column(
        "D:H",
        20,
    )

def render_periodic_business_xlsx_v2(
    report: PeriodicBusinessReportV2,
) -> bytes:
    """
    PeriodicBusinessReportV2 -> business-facing XLSX.

    Sheet hierarchy:
    01 经营摘要
    02 经营概览
    03 销售驱动
    04 客户健康
    05 驱动核对（若存在）
    最后一页业务口径与可信核对。
    """

    buffer = BytesIO()
    workbook = xlsxwriter.Workbook(
        buffer,
        {"in_memory": True},
    )
    formats = _workbook_formats(
        workbook
    )

    _write_periodic_summary_sheet_v2(
        workbook,
        report=report,
        formats=formats,
    )

    _write_periodic_metric_section_sheet_v2(
        workbook,
        report=report,
        formats=formats,
        section_value="overview",
        sheet_name="02_经营概览",
    )
    _write_periodic_metric_section_sheet_v2(
        workbook,
        report=report,
        formats=formats,
        section_value="sales_driver",
        sheet_name="03_销售驱动",
    )
    _write_periodic_metric_section_sheet_v2(
        workbook,
        report=report,
        formats=formats,
        section_value="customer_health",
        sheet_name="04_客户健康",
    )

    next_index = 5

    if report.driver_reconciliations:
        driver = workbook.add_worksheet(
            "05_驱动核对"
        )
        next_index = 6

        driver_headers = (
            "关系",
            "状态",
            "Observed",
            "Reconstructed",
            "Remainder",
            "说明",
        )

        for col, header in enumerate(
            driver_headers
        ):
            driver.write(
                0,
                col,
                header,
                formats["header"],
            )

        for row_index, item in enumerate(
            report.driver_reconciliations,
            start=1,
        ):
            driver.write(
                row_index,
                0,
                item.relationship,
                formats["text"],
            )
            driver.write(
                row_index,
                1,
                _reconciliation_label(
                    item.status
                ),
                formats["text"],
            )

            for col, value in (
                (2, item.observed_value),
                (3, item.reconstructed_value),
                (4, item.remainder),
            ):
                if value is None:
                    driver.write_blank(
                        row_index,
                        col,
                        None,
                        formats["money"],
                    )
                else:
                    driver.write_number(
                        row_index,
                        col,
                        float(value),
                        formats["money"],
                    )

            driver.write(
                row_index,
                5,
                item.message,
                formats["text"],
            )

        driver.freeze_panes(
            1,
            0,
        )
        driver.set_column(
            "A:B",
            26,
        )
        driver.set_column(
            "C:E",
            18,
        )
        driver.set_column(
            "F:F",
            60,
        )

    trust = workbook.add_worksheet(
        f"{next_index:02d}_业务口径与可信核对"
    )

    headers = (
        "指标",
        "指标说明",
        "状态",
        "可信说明",
    )

    for col, header in enumerate(
        headers
    ):
        trust.write(
            0,
            col,
            header,
            formats["header"],
        )

    for row_index, snapshot in enumerate(
        report.metrics,
        start=1,
    ):
        trust.write(
            row_index,
            0,
            snapshot.spec.chinese_name,
            formats["text"],
        )
        trust.write(
            row_index,
            1,
            snapshot.spec.purpose,
            formats["text"],
        )
        trust.write(
            row_index,
            2,
            (
                "可释放"
                if snapshot.status
                == PeriodicMetricStatusV2.READY
                else "不可释放"
            ),
            formats["text"],
        )
        trust.write(
            row_index,
            3,
            snapshot.message,
            formats["text"],
        )

    trust.set_column(
        "A:A",
        20,
    )
    trust.set_column(
        "B:B",
        50,
    )
    trust.set_column(
        "C:C",
        16,
    )
    trust.set_column(
        "D:D",
        60,
    )

    workbook.close()
    return buffer.getvalue()
