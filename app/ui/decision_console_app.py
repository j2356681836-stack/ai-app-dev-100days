from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pandas as pd
import streamlit as st
from pydantic import ValidationError

from app.delivery.decision_console_entry_v2 import (
    DecisionConsoleEntryModeV2,
    DecisionConsoleEntryRequestV2,
    PeriodicReportCadenceV2,
)
from app.delivery.decision_console_runtime_v2 import (
    run_day89_breakdown_summary_v2,
    run_day89_local_investigation_v2,
)
from app.delivery.monthly_contribution_delivery_v2 import (
    MonthlyContributionDeliveryResultV2,
    MonthlyContributionDeliveryStatusV2,
    run_day89_periodic_gmv_channel_contribution_v2,
)
from app.delivery.breakdown_trusted_summary_v2 import (
    TrustedBreakdownSummaryResultV2,
    TrustedBreakdownSummaryStatusV2,
)
from app.delivery.investigation_delivery_adapter_v2 import (
    InvestigationDeliveryResultV2,
    InvestigationDeliveryStatusV2,
    build_continued_investigation_step_delivery_v2,
    build_investigation_step_delivery_v2,
    build_resolved_clarification_step_delivery_v2,
)
from app.delivery.investigation_runtime_v2 import (
    Day89InvestigationContinuationStateV2,
    Day89PendingClarificationStateV2,
    build_day89_continuation_state_v2,
    build_day89_pending_clarification_state_v2,
    continue_day89_agentic_investigation_step_v2,
    resume_day89_agentic_investigation_after_clarification_v2,
    run_day89_agentic_investigation_step_v2,
)
from app.agents.clarification_resolution_v2 import (
    ClarificationResponseV2,
    build_day89_direction_clarification_requirement_v2,
    build_day89_direction_resolution_contract_v2,
    plan_day89_direction_clarification_v2,
    plan_day89_resolved_single_action_v2,
)
from app.agents.investigation_loop_v2 import (
    InvestigationBudgetPolicyV2,
    InvestigationSessionPolicyV2,
    InvestigationStopStatusV2,
)
from app.delivery.runtime_delivery_bridge_v2 import (
    RuntimeDeliveryBridgeResultV2,
    RuntimeDeliveryBridgeStatusV2,
)
from app.governance.governance_runtime import (
    GovernanceConfigurationError,
)
from app.ui.decision_console_presenters_v2 import (
    append_trusted_summary_row_v2,
    build_chart_rows_v2,
    build_contribution_chart_rows_v2,
    build_contribution_display_rows_v2,
    build_display_rows_v2,
    format_evidence_sufficiency_v2,
    format_contribution_direction_v2,
    format_evidence_type_v2,
    format_investigation_action_v2,
    format_loop_directive_v2,
    format_metric_name_v2,
    format_observation_status_v2,
    format_stop_reason_v2,
    format_number_v2,
    format_percentage_v2,
    format_reconciliation_status_v2,
    format_runtime_status_v2,
    format_statement_v2,
    normalize_scope_summary_v2,
)


APP_TITLE = "AI Data Analyst · Decision Console"


def _build_investigation_request(
    question: str,
) -> DecisionConsoleEntryRequestV2:
    return DecisionConsoleEntryRequestV2(
        entry_mode=DecisionConsoleEntryModeV2.INVESTIGATION,
        question=question,
    )


def _build_periodic_report_request(
    *,
    cadence: str,
    anchor_date: date,
) -> DecisionConsoleEntryRequestV2:
    return DecisionConsoleEntryRequestV2(
        entry_mode=DecisionConsoleEntryModeV2.PERIODIC_REPORT,
        report_cadence=PeriodicReportCadenceV2(cadence),
        report_anchor_date=anchor_date,
    )


def _runtime_result() -> RuntimeDeliveryBridgeResultV2 | None:
    value = st.session_state.get("runtime_delivery")
    if isinstance(value, RuntimeDeliveryBridgeResultV2):
        return value
    return None



def _periodic_result() -> MonthlyContributionDeliveryResultV2 | None:
    value = st.session_state.get("periodic_runtime_delivery")
    matched = isinstance(
        value,
        MonthlyContributionDeliveryResultV2,
    )

    _update_periodic_runtime_trace_v2(
        render_session_has_delivery=(
            "periodic_runtime_delivery" in st.session_state
        ),
        render_session_value_type=(
            type(value).__name__
            if value is not None
            else None
        ),
        render_isinstance_match=matched,
    )

    if matched:
        return value
    return None


def _periodic_runtime_failure() -> dict[str, str] | None:
    """
    读取 Periodic Runtime 的安全失败摘要。

    这里只保存允许公开到 UI 的诊断字段：
    - failure_stage
    - exception_type
    - diagnostic_id

    不保存 SQL、parameters、rows、数据库 URL 或 secret。
    """

    value = st.session_state.get("periodic_runtime_failure")

    if not isinstance(value, dict):
        return None

    required_keys = {
        "failure_stage",
        "exception_type",
        "diagnostic_id",
    }

    if not required_keys.issubset(value):
        return None

    if not all(
        isinstance(value[key], str) and value[key].strip()
        for key in required_keys
    ):
        return None

    return {
        key: value[key]
        for key in (
            "failure_stage",
            "exception_type",
            "diagnostic_id",
        )
    }


def _periodic_anchor_state_key_v2(cadence: str) -> str:
    """
    为每一种报表周期建立独立的 Streamlit widget state。

    Daily / Weekly / Monthly 分开保存，避免切换 cadence 或 rerun 时
    把用户已经确认的历史 anchor 静默重置为默认 completed period。
    """

    return f"periodic_anchor_date::{cadence}"


def _update_periodic_runtime_trace_v2(
    **fields: object,
) -> None:
    """
    更新 Day93 Periodic Lifecycle Trace。

    Trace 只记录控制流与类型级信息，不记录：
    - SQL / parameters；
    - raw rows；
    - 数据库连接信息；
    - secret；
    - exception message。
    """

    current = st.session_state.get(
        "periodic_runtime_trace",
        {},
    )

    if not isinstance(current, dict):
        current = {}

    updated = dict(current)

    for key, value in fields.items():
        if value is None:
            updated[key] = None
        elif isinstance(value, (str, int, float, bool)):
            updated[key] = value
        elif isinstance(value, date):
            updated[key] = value.isoformat()
        else:
            updated[key] = str(value)

    st.session_state["periodic_runtime_trace"] = updated


def _periodic_runtime_trace_v2() -> dict[str, object] | None:
    value = st.session_state.get("periodic_runtime_trace")

    if not isinstance(value, dict) or not value:
        return None

    return dict(value)


def _log_periodic_lifecycle_v2(
    *,
    submit_id: str,
    event: str,
    anchor_date: date | None = None,
    cadence: str | None = None,
    result_type: str | None = None,
    result_status: str | None = None,
    exception_type: str | None = None,
    diagnostic_id: str | None = None,
) -> None:
    """
    输出 Day93 Periodic server-side lifecycle 日志。

    仅记录控制流与类型级信息；禁止记录：
    - SQL / parameters；
    - raw rows；
    - database URL；
    - secret；
    - exception message。
    """

    fields = {
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "submit_id": submit_id,
        "event": event,
        "anchor": (
            anchor_date.isoformat()
            if isinstance(anchor_date, date)
            else None
        ),
        "cadence": cadence,
        "result_type": result_type,
        "result_status": result_status,
        "exception_type": exception_type,
        "diagnostic_id": diagnostic_id,
    }

    payload = " ".join(
        f"{key}={value}"
        for key, value in fields.items()
        if value is not None
    )

    print(
        f"[D93_PERIODIC] {payload}",
        flush=True,
    )


def _render_periodic_runtime_trace_v2() -> None:
    trace = _periodic_runtime_trace_v2()

    if trace is None:
        st.caption("当前没有 Day93 Periodic Lifecycle Trace。")
        return

    with st.expander(
        "Day93 诊断｜Periodic Lifecycle Trace",
        expanded=True,
    ):
        st.json(trace)

    st.caption(
        "Trace 仅包含 widget / request / runtime / session-state "
        "生命周期信息；不包含 SQL、parameters、raw rows 或 secret。"
    )


def _breakdown_summary_result(
) -> TrustedBreakdownSummaryResultV2 | None:
    value = st.session_state.get("breakdown_summary")
    if isinstance(value, TrustedBreakdownSummaryResultV2):
        return value
    return None


def _agentic_result() -> InvestigationDeliveryResultV2 | None:
    value = st.session_state.get("agentic_delivery")
    if isinstance(value, InvestigationDeliveryResultV2):
        return value
    return None


def _continuation_state() -> (
    Day89InvestigationContinuationStateV2 | None
):
    value = st.session_state.get(
        "agentic_continuation_state"
    )
    if isinstance(
        value,
        Day89InvestigationContinuationStateV2,
    ):
        return value
    return None


def _prior_continuation_stop_statuses() -> tuple[
    InvestigationStopStatusV2, ...
]:
    value = st.session_state.get(
        "agentic_prior_continuation_stop_statuses",
        (),
    )

    if not isinstance(value, tuple):
        return ()

    if not all(
        isinstance(item, InvestigationStopStatusV2)
        for item in value
    ):
        return ()

    return value


def _pending_clarification_state() -> (
    Day89PendingClarificationStateV2 | None
):
    value = st.session_state.get(
        "agentic_pending_clarification"
    )

    if isinstance(
        value,
        Day89PendingClarificationStateV2,
    ):
        return value

    return None


def _clear_agentic_hitl_state() -> None:
    st.session_state.pop(
        "agentic_continuation_state",
        None,
    )
    st.session_state.pop(
        "agentic_prior_continuation_stop_statuses",
        None,
    )
    st.session_state.pop(
        "agentic_pending_clarification",
        None,
    )


def _previous_completed_day_anchor() -> date:
    return date.today() - timedelta(days=1)


def _previous_completed_week_anchor() -> date:
    """
    返回最近一个已经结束的自然周 Sunday。

    weekday(): Monday=0 ... Sunday=6。
    """
    today = date.today()
    current_week_start = (
        today - timedelta(days=today.weekday())
    )
    return current_week_start - timedelta(days=1)


def _periodic_anchor_ui_v2(
    cadence: str,
) -> tuple[str, date, date, str]:
    """
    UI 只允许选择已经完成的 Period。

    返回：
    label, default_value, max_value, help_text
    """

    cadence_enum = PeriodicReportCadenceV2(cadence)

    if cadence_enum == PeriodicReportCadenceV2.DAILY:
        anchor = _previous_completed_day_anchor()
        return (
            "报表日期",
            anchor,
            anchor,
            (
                "Daily 使用完整自然日：所选日期 vs 前一日（DOD）。"
                "最多选择昨天，避免把尚未完成的今天当成完整日报。"
            ),
        )

    if cadence_enum == PeriodicReportCadenceV2.WEEKLY:
        anchor = _previous_completed_week_anchor()
        return (
            "报表周定位日期",
            anchor,
            anchor,
            (
                "Weekly 按所选日期定位自然周（周一至周日），"
                "并与前一个完整自然周比较（WOW）。"
                "最多选择最近一个已结束自然周内的日期。"
            ),
        )

    anchor = _previous_completed_month_anchor()
    return (
        "报表月份",
        anchor,
        anchor,
        (
            "Monthly 按所选日期定位完整自然月，"
            "并与前一个完整自然月比较（MOM）。"
        ),
    )


def _periodic_cadence_label_v2(
    cadence: PeriodicReportCadenceV2,
) -> str:
    return {
        PeriodicReportCadenceV2.DAILY: "日报",
        PeriodicReportCadenceV2.WEEKLY: "周报",
        PeriodicReportCadenceV2.MONTHLY: "月报",
    }[cadence]


def _comparison_change_label_v2(comparison_type: str) -> str:
    return {
        "dod": "日环比",
        "wow": "周环比",
        "mom": "月环比",
        "yoy": "同比",
    }.get(comparison_type, "比较")


def _previous_completed_month_anchor() -> date:
    first_day_this_month = date.today().replace(day=1)
    return first_day_this_month - timedelta(days=1)


def _render_page_style() -> None:
    st.markdown(
        """
        <style>
        .block-container {
            padding-top: 1.5rem;
            padding-bottom: 2rem;
        }
        .dc-muted {
            color: #6b7280;
            font-size: 0.95rem;
        }
        .dc-section {
            padding-top: 0.25rem;
            padding-bottom: 0.5rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_entry_summary(
    request: DecisionConsoleEntryRequestV2,
) -> None:
    st.success("入口请求已通过 Decision Console Entry Contract 校验。")

    if request.entry_mode == DecisionConsoleEntryModeV2.INVESTIGATION:
        st.markdown("### 本次调查")
        st.write(request.question)
        return

    st.markdown("### 本次周期报表")
    left, right = st.columns(2)

    with left:
        st.metric("周期", request.report_cadence.value.upper())

    with right:
        st.metric("锚点日期", request.report_anchor_date.isoformat())


def _render_scope_summary(scope_summary: str | None) -> None:
    preview, full = normalize_scope_summary_v2(scope_summary)

    if preview is None:
        return

    st.caption(f"有效范围：{preview}")

    if full != preview:
        with st.expander("查看完整有效范围"):
            st.write(full)


def _render_runtime_failure(
    result: RuntimeDeliveryBridgeResultV2,
) -> None:
    st.warning("真实 Governed Runtime 已执行，但当前请求没有形成可释放的业务交付。")
    st.write(result.message)
    st.caption("这是 fail-closed 结果；页面不会用占位数字或未受保护数据补齐。")


def _render_key_findings(
    result: RuntimeDeliveryBridgeResultV2,
) -> None:
    brief = result.executive_brief
    if brief is None:
        return

    st.markdown("### 关键结论")

    if not brief.key_findings:
        st.info("当前没有可释放的 evidence-backed 关键结论。")
        return

    for idx, finding in enumerate(brief.key_findings, start=1):
        with st.container():
            st.markdown(f"**{idx}.** {format_statement_v2(finding.summary)}")


def _render_breakdown(
    result: RuntimeDeliveryBridgeResultV2,
) -> None:
    view = result.console_view
    if view is None or view.breakdown is None:
        return

    st.markdown("### 受保护业务明细")

    left, right = st.columns((1.05, 1.2))

    display_rows = build_display_rows_v2(view.breakdown.rows)
    chart_rows = build_chart_rows_v2(view.breakdown.rows)

    summary_result = _breakdown_summary_result()
    summary = (
        summary_result.summary
        if (
            summary_result is not None
            and summary_result.status
            == TrustedBreakdownSummaryStatusV2.READY
            and summary_result.summary is not None
            and summary_result.summary.metric_name
            == view.breakdown.metric_name
        )
        else None
    )

    if summary is not None:
        display_rows = append_trusted_summary_row_v2(
            display_rows=display_rows,
            metric_name=view.breakdown.metric_name,
            summary_value=summary.value,
        )

    with left:
        st.dataframe(
            display_rows,
            use_container_width=True,
            hide_index=True,
        )

        if summary is not None:
            st.caption(
                "“汇总”来自独立 Overall Governed Evidence，"
                "不是对当前可见明细行求和。"
            )

    with right:
        if chart_rows:
            chart_df = pd.DataFrame(chart_rows).set_index("渠道")
            st.bar_chart(chart_df)
        else:
            st.info("当前明细结果不支持生成图表。")

    st.caption(
        "以上数据来自 Result Protection 之后的 ProtectedResultV2；"
        "Streamlit 不重新聚合业务真值。"
    )


def _render_brief(
    result: RuntimeDeliveryBridgeResultV2,
) -> None:
    brief = result.executive_brief
    if brief is None:
        return

    st.markdown("### 管理层决策摘要预览")

    if brief.confirmed_facts:
        st.markdown("**已确认事实**")
        for item in brief.confirmed_facts:
            st.markdown(f"- {format_statement_v2(item)}")

    if brief.unknowns:
        st.markdown("**当前未知**")
        for item in brief.unknowns:
            st.markdown(f"- {format_statement_v2(item)}")

    if brief.recommended_checks:
        st.markdown("**建议继续检查**")
        for item in brief.recommended_checks:
            st.markdown(f"- {format_statement_v2(item)}")

    if brief.limitations:
        st.markdown("**当前限制**")
        for item in brief.limitations:
            st.markdown(
                f"- **{item.code.value}**：{format_statement_v2(item.detail)}"
            )


def _render_fact_delivery_business(
    result: RuntimeDeliveryBridgeResultV2,
) -> None:
    view = result.console_view
    brief = result.executive_brief

    if view is None or brief is None:
        st.error("READY Runtime 缺少 Console View / Executive Brief。")
        return

    if view.fact_metric is not None:
        st.markdown("### 核心 KPI")
        st.metric(
            format_metric_name_v2(
                view.fact_metric.metric_name
            ),
            format_number_v2(
                view.fact_metric.value
            ),
        )
        st.caption(
            "分析窗口："
            f"{view.fact_metric.analysis_window.start_date} → "
            f"{view.fact_metric.analysis_window.end_date} ｜ "
            "该数值直接来自已释放的 Governed Evidence，"
            "页面不重新计算。"
        )

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("指标", format_metric_name_v2(view.metric_name))
    with c2:
        st.metric(
            "证据充分性",
            format_evidence_sufficiency_v2(
                view.evidence_sufficiency
            ),
        )
    with c3:
        st.metric("交付类型", "事实型")

    _render_scope_summary(view.scope_summary)
    _render_key_findings(result)

    if (
        view.comparison is None
        and view.fact_metric is None
    ):
        st.caption(
            "当前为事实型交付，但没有满足安全单值投影合同的 KPI；"
            "页面仅展示 evidence-backed 文字结论。"
        )

    _render_breakdown(result)
    _render_brief(result)


def _contribution_member_by_key(
    contribution,
) -> dict[str, object]:
    return {
        member.member_key: member
        for member in contribution.members
    }


def _render_contribution_business_summary(view) -> None:
    contribution = view.contribution

    st.markdown("### 渠道变化贡献")

    if contribution is None:
        st.info("当前 Delivery 没有受支持的渠道 Contribution Result。")
        return

    by_key = _contribution_member_by_key(contribution)

    left, right = st.columns(2)

    with left:
        st.markdown("**全部负向变化渠道**")
        if not contribution.negative_change_ranking:
            st.caption("当前没有负向变化渠道。")
        else:
            for key in contribution.negative_change_ranking:
                member = by_key[key]
                st.write(
                    f"{member.member_label}："
                    f"{format_number_v2(member.delta)} "
                    f"（贡献率 "
                    f"{format_percentage_v2(member.contribution_rate)}）"
                )

    with right:
        st.markdown("**全部正向变化渠道**")
        if not contribution.positive_change_ranking:
            st.caption("当前没有正向变化渠道。")
        else:
            for key in contribution.positive_change_ranking:
                member = by_key[key]
                st.write(
                    f"{member.member_label}："
                    f"+{format_number_v2(member.delta)} "
                    f"（贡献率 "
                    f"{format_percentage_v2(member.contribution_rate)}）"
                )

    status = format_reconciliation_status_v2(
        contribution.reconciliation_status.value
    )

    if contribution.reconciliation_status.value == "reconciled":
        st.success(
            "渠道变化额与 Overall GMV 变化额已完成 reconciliation。"
        )
    else:
        st.warning(
            "渠道变化额与 Overall GMV 变化额未完全 reconciliation；"
            "不可把可见渠道贡献当成完整解释。"
        )

    st.caption(
        f"Reconciliation：{status} ｜ "
        f"整体变化额={format_number_v2(contribution.overall_delta)} ｜ "
        f"渠道变化额合计={format_number_v2(contribution.sum_member_delta)} ｜ "
        f"未解释差额={format_number_v2(contribution.unexplained_remainder)}"
    )

    st.caption(
        "Contribution Rate 是“该渠道变化额 / Overall 变化额”的算术贡献；"
        "由于渠道之间可能互相抵消，单个贡献率可以超过 100% 或为负，"
        "它不等于因果解释。"
    )


def _render_contribution_analysis(view) -> None:
    contribution = view.contribution

    if contribution is None:
        return

    st.markdown("### Contribution Analysis")

    rows = build_contribution_display_rows_v2(contribution)
    chart_rows = build_contribution_chart_rows_v2(contribution)

    left, right = st.columns((1.35, 1.0))

    with left:
        st.dataframe(
            rows,
            use_container_width=True,
            hide_index=True,
        )

    with right:
        if chart_rows:
            chart_df = pd.DataFrame(chart_rows).set_index("渠道")
            st.bar_chart(chart_df)
        else:
            st.info("当前没有非零渠道变化额可用于绘图。")

    c1, c2, c3 = st.columns(3)

    with c1:
        st.metric(
            "整体变化额",
            format_number_v2(contribution.overall_delta),
        )
    with c2:
        st.metric(
            "渠道变化额合计",
            format_number_v2(contribution.sum_member_delta),
        )
    with c3:
        st.metric(
            "未解释差额",
            format_number_v2(contribution.unexplained_remainder),
        )

    if contribution.reconciliation_status.value == "reconciled":
        st.success("Contribution Reconciliation：已对账。")
    else:
        st.warning(
            "Contribution Reconciliation：未完全对账；"
            "请同时查看 Evidence Pack 中保留的 Unknown。"
        )

    st.caption(
        "表格与图表直接消费 Day84 Contribution Result；"
        "Streamlit 不重新计算 member delta / contribution rate。"
    )


def _render_anomaly_boundary(view) -> None:
    st.markdown("### 异常状态")

    if view.anomaly is None:
        st.info(
            "未评估 / 未激活：当前 Delivery 没有 Active Anomaly Evidence，"
            "因此页面不展示异常标记。"
        )
        return

    if view.anomaly.show_anomaly_marker:
        st.warning("当前存在已通过确定性 Policy Gate 的异常 Evidence。")
    else:
        st.info(
            "当前 Anomaly Decision 未达到可展示异常标记的状态。"
        )


def _render_periodic_comparison_business(
    result: MonthlyContributionDeliveryResultV2,
    *,
    cadence: PeriodicReportCadenceV2,
) -> None:
    if (
        result.status
        not in {
            MonthlyContributionDeliveryStatusV2.READY,
            MonthlyContributionDeliveryStatusV2.PARTIAL_READY,
        }
        or result.console_view is None
        or result.console_view.comparison is None
    ):
        st.warning(
            f"{_periodic_cadence_label_v2(cadence)} Runtime "
            "未形成可释放的 Overall Comparison Delivery。"
        )
        st.write(result.message)
        return

    view = result.console_view
    comparison = view.comparison
    comparison_label = _comparison_change_label_v2(
        result.comparison.comparison_type.value
        if result.comparison is not None
        else ""
    )

    st.markdown(
        f"### {_periodic_cadence_label_v2(cadence)} KPI"
    )

    if (
        result.status
        == MonthlyContributionDeliveryStatusV2.PARTIAL_READY
    ):
        st.warning(
            "本期 Overall KPI / Comparison 已通过治理并可验证；"
            "但渠道 Breakdown 因 Result Protection 无法安全释放，"
            "因此本期渠道 Contribution 不可用。"
        )
        st.caption(result.message)

    # 金额可能达到百万级。使用 2x2 KPI 布局给每张卡更宽空间，
    # 避免 Streamlit 在 4 等分列中把可信数值显示为省略号。
    c1, c2 = st.columns(2)

    with c1:
        st.metric(
            "本期 GMV",
            format_number_v2(comparison.current_value),
        )
    with c2:
        st.metric(
            "上期 GMV",
            format_number_v2(comparison.reference_value),
        )

    c3, c4 = st.columns(2)

    with c3:
        st.metric(
            f"{comparison_label}变化额",
            format_number_v2(comparison.absolute_change),
        )
    with c4:
        st.metric(
            f"{comparison_label}变化率",
            format_percentage_v2(comparison.relative_change),
        )

    st.caption(
        "本期："
        f"{comparison.current_window.start_date} → "
        f"{comparison.current_window.end_date} ｜ "
        "上期："
        f"{comparison.reference_window.start_date} → "
        f"{comparison.reference_window.end_date}"
    )

    _render_scope_summary(view.scope_summary)

    _render_anomaly_boundary(view)

    if (
        result.status
        == MonthlyContributionDeliveryStatusV2.PARTIAL_READY
    ):
        st.markdown("### 渠道变化贡献")
        st.info(
            "当前周期的渠道聚合结果触发 Result Protection。"
            "系统不会读取被阻断的明细，也不会据此计算 Contribution。"
        )
    else:
        _render_contribution_business_summary(view)

    if result.executive_brief is not None:
        st.markdown("### 管理层决策摘要预览")
        for item in result.executive_brief.confirmed_facts:
            st.markdown(f"- {format_statement_v2(item)}")

    if view.breakdown is not None:
        st.markdown("### 本期渠道受保护明细")

        breakdown_rows = build_display_rows_v2(
            view.breakdown.rows
        )
        breakdown_chart_rows = build_chart_rows_v2(
            view.breakdown.rows
        )

        left, right = st.columns((1.05, 1.2))

        with left:
            st.dataframe(
                breakdown_rows,
                use_container_width=True,
                hide_index=True,
            )

        with right:
            if breakdown_chart_rows:
                chart_df = pd.DataFrame(
                    breakdown_chart_rows
                ).set_index("渠道")
                st.bar_chart(chart_df)

        st.caption(
            "这里只展示本期 Channel ProtectedResult；"
            "Overall KPI 来自独立 Overall Governed Evidence，"
            "页面不对明细自行求和。"
        )

    if view.verification is not None:
        with st.expander("数据验证｜查看本期 / 上期 Overall Evidence"):
            verification = view.verification
            metric = verification.metric_definition

            st.write("指标定义：", metric.chinese_name)
            st.write("定义：", metric.definition)
            st.write("公式：", metric.formula)

            st.markdown("**本期 Evidence**")
            st.write(
                "时间窗口：",
                (
                    f"{verification.current_evidence.analysis_window.start_date}"
                    " → "
                    f"{verification.current_evidence.analysis_window.end_date}"
                ),
            )
            st.write(
                "Audit Event：",
                verification.current_evidence.audit_event_id,
            )

            st.markdown("**上期 Evidence**")
            st.write(
                "时间窗口：",
                (
                    f"{verification.reference_evidence.analysis_window.start_date}"
                    " → "
                    f"{verification.reference_evidence.analysis_window.end_date}"
                ),
            )
            st.write(
                "Audit Event：",
                verification.reference_evidence.audit_event_id,
            )


def _render_business_view() -> None:
    st.markdown("## 业务决策视图")

    request = st.session_state.get("entry_request")
    if request is None:
        st.info("请先从上方入口提交一个 Investigation 或 Periodic Report 请求。")
        return

    _render_entry_summary(request)

    if request.entry_mode == DecisionConsoleEntryModeV2.PERIODIC_REPORT:
        result = _periodic_result()
        if result is None:
            failure = _periodic_runtime_failure()

            if failure is None:
                st.info(
                    "当前还没有真实 Periodic Runtime Delivery。"
                )
            else:
                st.error(
                    "Periodic Runtime 未形成可交付结果；"
                    "安全诊断摘要已保留，可用于定位而不泄露敏感数据。"
                )
                st.write(
                    "失败阶段：",
                    failure["failure_stage"],
                )
                st.write(
                    "异常类型：",
                    failure["exception_type"],
                )
                st.caption(
                    "诊断 ID："
                    f'{failure["diagnostic_id"]}'
                )
            _render_periodic_runtime_trace_v2()
            return

        _render_periodic_comparison_business(
            result,
            cadence=request.report_cadence,
        )
        _render_periodic_runtime_trace_v2()
        return

    result = _runtime_result()
    if result is None:
        st.info("当前还没有真实 Runtime Delivery。")
        return

    if result.status != RuntimeDeliveryBridgeStatusV2.READY:
        _render_runtime_failure(result)
        return

    _render_fact_delivery_business(result)
    _render_agentic_business_section()


def _render_agentic_business_section() -> None:
    """
    Business View 只展示调查状态与结论边界。
    具体 action / evidence lineage 放在 Analyst View。
    """

    agentic = _agentic_result()

    st.markdown("### 受控深入调查")

    if agentic is None:
        st.caption(
            "当前 Seed Evidence 已形成。进一步调查不会自动发生。"
            "你可以让系统在批准动作中规划，也可以先明确指定首个方向。"
        )

        start_mode = st.radio(
            "调查启动方式",
            options=(
                "系统在受控动作中规划",
                "我先指定首个调查方向",
            ),
            horizontal=True,
            key="agentic_start_mode",
        )

        if st.button(
            "执行受控深入调查",
            key="run_agentic_investigation",
            type="secondary",
        ):
            if start_mode == "我先指定首个调查方向":
                _submit_agentic_clarification_gate()
            else:
                _submit_agentic_investigation()

            if _agentic_result() is not None:
                st.rerun()
        return

    if agentic.status not in {
        InvestigationDeliveryStatusV2.READY,
        InvestigationDeliveryStatusV2.CLARIFICATION_READY,
    }:
        st.warning("受控深入调查没有形成可释放 Delivery。")
        st.write(agentic.message)
        return

    view = agentic.console_view
    if view is None:
        st.error("Agentic Delivery 缺少 Decision Console View。")
        return

    if view.clarification is not None:
        st.warning("调查需要用户澄清，当前 Tool Execution 已阻断。")
        st.write(view.clarification.clarification_prompt)

        pending = _pending_clarification_state()

        if pending is None:
            st.error(
                "当前 Clarification Delivery 缺少安全 Pending State；"
                "不能接受用户回答。"
            )
            return

        choices = pending.resolution_contract.choices
        choice_by_id = {
            item.choice_id: item
            for item in choices
        }

        selected_choice_id = st.radio(
            "请选择首个调查方向",
            options=tuple(
                item.choice_id
                for item in choices
            ),
            format_func=lambda value: (
                choice_by_id[value].display_label
            ),
            key="agentic_clarification_choice",
        )

        st.caption(
            "这些选项来自 server-owned Resolution Contract；"
            "页面不能新增调查方向，也不能用自由文本绕过 prerequisite。"
        )

        if st.button(
            "确认方向并继续调查",
            key="resolve_agentic_clarification",
            type="primary",
        ):
            _submit_agentic_clarification_response(
                selected_choice_id
            )
            st.rerun()
        return

    c1, c2 = st.columns(2)
    with c1:
        st.metric(
            "调查证据充分性",
            format_evidence_sufficiency_v2(
                view.evidence_sufficiency
            ),
        )
    with c2:
        st.metric(
            "已执行调查步骤",
            len(view.investigation_trace),
        )

    if view.runtime_control is not None:
        control = view.runtime_control
        st.info(format_stop_reason_v2(control.stop_reason.value))
        st.write(control.detail)

        if not control.evidence_sufficient:
            st.caption(
                "停止只代表达到当前受控边界，不代表业务原因已经被证明。"
            )

        if control.can_continue:
            st.warning(
                "当前 Session 仍有未调查的合法方向。"
                "系统不会自动续预算；只有你明确点击后才会开启下一轮。"
            )

            remaining_labels = [
                format_investigation_action_v2(action_id)
                for action_id
                in control.uninvestigated_action_ids
            ]
            st.write(
                "尚未调查：",
                remaining_labels,
            )

            if st.button(
                "继续调查（开启下一轮）",
                key="continue_agentic_investigation",
                type="primary",
            ):
                _submit_agentic_continuation()
                st.rerun()

    if view.unknowns:
        with st.expander("查看当前仍未解决的边界"):
            for item in view.unknowns:
                st.markdown(f"- {format_statement_v2(item)}")


def _render_investigation_trace(view) -> None:
    st.markdown("### Investigation Trace")

    if not view.investigation_trace:
        if view.clarification is not None:
            st.info("当前停在 Clarification Gate，尚未执行 Investigation Tool。")
        else:
            st.caption("当前还没有已执行的 Agentic Investigation Step。")
        return

    for step in view.investigation_trace:
        title = (
            f"步骤 {step.sequence_number}｜"
            f"{format_investigation_action_v2(step.selected_action_id)}"
        )

        with st.expander(title, expanded=True):
            st.write(
                "执行结果：",
                format_observation_status_v2(
                    step.observation_status.value
                ),
            )
            st.write("Observation：", step.summary)
            st.write(
                "下一步控制：",
                format_loop_directive_v2(
                    step.next_directive.value
                ),
            )

            if step.failure_code is not None:
                st.write("失败代码：", step.failure_code)

            if step.produced_evidence_ids:
                st.write(
                    "产生 Evidence：",
                    list(step.produced_evidence_ids),
                )

            st.write(
                "Observation Evidence：",
                step.observation_evidence_id,
            )

            if step.stop_reason is not None:
                st.write(
                    "停止原因：",
                    format_stop_reason_v2(
                        step.stop_reason.value
                    ),
                )


def _render_runtime_control(view) -> None:
    control = view.runtime_control
    if control is None:
        return

    st.markdown("### Runtime Control")

    left, middle, right = st.columns(3)
    with left:
        st.metric(
            "停止原因",
            format_stop_reason_v2(control.stop_reason.value),
        )
    with middle:
        st.metric(
            "证据是否充分",
            "是" if control.evidence_sufficient else "否",
        )
    with right:
        st.metric(
            "允许继续下一轮",
            "是" if control.can_continue else "否",
        )

    st.caption(
        f"Round {control.current_round}/{control.max_rounds} ｜ "
        f"累计步骤 {control.total_steps_used}/"
        f"{control.max_total_investigation_steps}"
    )
    st.write(control.detail)

    if control.can_continue:
        st.info(
            "当前允许用户显式开启下一 Round；"
            "系统不会自动 continuation。请在业务决策视图点击“继续调查”。"
        )


def _render_runtime_clarification(view) -> None:
    clarification = view.clarification
    if clarification is None:
        return

    st.markdown("### Runtime Clarification")
    st.warning(clarification.clarification_prompt)
    st.write("为什么需要澄清：", clarification.requirement_reason)
    st.write("Planner 说明：", clarification.rationale)
    st.caption(
        "requires_user_response=True；tool_execution_blocked=True。"
        "请在业务决策视图使用 server-owned 选项完成澄清。"
    )


def _render_analyst_view() -> None:
    st.markdown("## 分析视图")

    request = st.session_state.get("entry_request")

    if (
        request is not None
        and request.entry_mode
        == DecisionConsoleEntryModeV2.PERIODIC_REPORT
    ):
        periodic = _periodic_result()
        if (
            periodic is None
            or periodic.status
            not in {
                MonthlyContributionDeliveryStatusV2.READY,
                MonthlyContributionDeliveryStatusV2.PARTIAL_READY,
            }
            or periodic.console_view is None
        ):
            st.info("当前没有可展示的分析交付结果。")
            return

        if (
            periodic.status
            == MonthlyContributionDeliveryStatusV2.PARTIAL_READY
        ):
            st.info(
                "当前 Periodic Delivery 为 PARTIAL_READY："
                "Overall Evidence 可展示；受保护的 Channel Breakdown "
                "与 Contribution 不会进入分析视图。"
            )

        view = periodic.console_view
    else:
        agentic = _agentic_result()
        if (
            agentic is not None
            and agentic.status
            in {
                InvestigationDeliveryStatusV2.READY,
                InvestigationDeliveryStatusV2.CLARIFICATION_READY,
            }
            and agentic.console_view is not None
        ):
            view = agentic.console_view
        else:
            result = _runtime_result()
            if (
                result is None
                or result.status != RuntimeDeliveryBridgeStatusV2.READY
                or result.console_view is None
            ):
                st.info("当前没有可展示的分析交付结果。")
                return
            view = result.console_view

    top1, top2 = st.columns(2)
    with top1:
        st.metric("证据充分性", format_evidence_sufficiency_v2(view.evidence_drawer.sufficiency_status))
    with top2:
        st.metric("证据记录数", len(view.evidence_drawer.records))

    st.markdown("### Evidence Drawer")

    for idx, record in enumerate(view.evidence_drawer.records, start=1):
        title = f"{idx}. {format_evidence_type_v2(record.evidence_type.value)}｜{record.evidence_id}"
        with st.expander(title):
            st.write("来源：", record.source)
            st.write("指标：", format_metric_name_v2(record.metric_name))
            st.write("粒度：", record.result_grain)

            if record.analysis_window is not None:
                st.write(
                    "时间窗口：",
                    f"{record.analysis_window.start_date} → {record.analysis_window.end_date}",
                )

            st.write("计划名：", record.plan_name)
            st.write(
                "工具：",
                (
                    f"{record.tool_name}@{record.tool_version}"
                    if record.tool_name
                    else "-"
                ),
            )
            st.write("审计事件：", record.audit_event_id or "-")
            st.write("已释放字段：", list(record.released_field_names))
            st.write("已释放行数：", record.released_row_count)

            if record.parent_evidence_ids:
                st.write(
                    "Parent Evidence：",
                    list(record.parent_evidence_ids),
                )

            if record.observation_action_id is not None:
                st.write(
                    "Observation Action：",
                    format_investigation_action_v2(
                        record.observation_action_id
                    ),
                )
                st.write(
                    "Observation Status：",
                    format_observation_status_v2(
                        record.observation_status
                    ),
                )
                st.write(
                    "Observation Summary：",
                    record.observation_summary,
                )

    _render_investigation_trace(view)
    _render_runtime_control(view)
    _render_runtime_clarification(view)
    _render_contribution_analysis(view)

    if view.contribution is None:
        st.caption(
            "当前 Delivery 没有受支持的 Contribution Result，因此不展示贡献度可视化。"
        )


def _render_engineering_view() -> None:
    st.markdown("## 工程视图")

    request = st.session_state.get("entry_request")
    if request is not None:
        with st.expander("查看入口合同 Payload"):
            st.json(request.model_dump(mode="json"))

    if (
        request is not None
        and request.entry_mode
        == DecisionConsoleEntryModeV2.PERIODIC_REPORT
    ):
        periodic = _periodic_result()
        if periodic is None:
            failure = _periodic_runtime_failure()

            if failure is None:
                st.info("当前还没有 Periodic Runtime Result。")
            else:
                st.error("Periodic Runtime Failure（安全摘要）")
                st.json(failure)
                st.caption(
                    "只保留 failure stage / exception type / diagnostic id；"
                    "不显示 raw SQL、parameters、rows、URL 或 secret。"
                )
            _render_periodic_runtime_trace_v2()
            return

        st.metric("运行时交付状态", periodic.status.value)
        _render_periodic_runtime_trace_v2()

        with st.expander("查看本期 Channel Safe Runtime Result"):
            st.json(
                periodic.current_channel_safe_runtime_result
                or {}
            )

        with st.expander("查看上期 Channel Safe Runtime Result"):
            st.json(
                periodic.reference_channel_safe_runtime_result
                or {}
            )

        if periodic.console_view is not None:
            contribution = periodic.console_view.contribution

            with st.expander("查看 Contribution 安全摘要"):
                st.json(
                    {
                        "comparison_type": (
                            periodic.comparison.comparison_type.value
                            if periodic.comparison is not None
                            else None
                        ),
                        "contribution_available": (
                            contribution is not None
                        ),
                        "reconciliation_status": (
                            contribution.reconciliation_status.value
                            if contribution is not None
                            else None
                        ),
                        "evidence_record_count": len(
                            periodic.console_view
                            .evidence_drawer.records
                        ),
                    }
                )

        st.caption(
            "工程视图只显示 safe public summary / Evidence projection；"
            "不显示 raw SQL、SQL parameters 或 raw database rows。"
        )
        return

    agentic = _agentic_result()
    if (
        agentic is not None
        and agentic.console_view is not None
    ):
        with st.expander("查看 Agentic Delivery 安全摘要"):
            control = agentic.console_view.runtime_control
            clarification = agentic.console_view.clarification

            st.json(
                {
                    "delivery_status": agentic.status.value,
                    "evidence_record_count": len(
                        agentic.console_view.evidence_drawer.records
                    ),
                    "trace_step_count": len(
                        agentic.console_view.investigation_trace
                    ),
                    "stop_reason": (
                        control.stop_reason.value
                        if control is not None
                        else None
                    ),
                    "can_continue": (
                        control.can_continue
                        if control is not None
                        else None
                    ),
                    "clarification_required": (
                        clarification is not None
                    ),
                }
            )

        st.caption(
            "这里只展示 InvestigationDeliveryResultV2 的安全投影；"
            "server-internal envelope / compiled SQL / parameters "
            "不会写入页面状态或工程视图。"
        )

    result = _runtime_result()
    if result is None:
        st.info("当前还没有 Runtime Result。")
        return

    st.metric("运行时交付状态", format_runtime_status_v2(result.status.value))

    with st.expander("查看 Safe Runtime Result"):
        st.json(result.safe_runtime_result)

    st.caption(
        "工程视图只显示 Governed Graph 的 safe public summary；"
        "不显示 raw SQL、SQL parameters 或 raw database rows。"
    )


def _submit_investigation(question: str) -> None:
    try:
        request = _build_investigation_request(question)
    except ValidationError as exc:
        st.error("入口请求未通过合同校验。")
        st.code(str(exc))
        return

    st.session_state["entry_request"] = request
    st.session_state.pop("runtime_delivery", None)
    st.session_state.pop("agentic_delivery", None)
    _clear_agentic_hitl_state()

    with st.spinner("正在执行 Governed Analytics → Result Protection → Evidence Delivery..."):
        try:
            result = run_day89_local_investigation_v2(
                question=request.question,
                reference_date=date.today(),
            )
        except GovernanceConfigurationError as exc:
            st.error("Governance Runtime 配置未准备好。")
            st.code(str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            st.error("真实 Runtime 调用发生未预期错误；没有生成或展示替代业务结果。")
            st.code(f"{type(exc).__name__}: {exc}")
            return

    st.session_state["runtime_delivery"] = result
    st.session_state.pop("periodic_runtime_delivery", None)
    st.session_state.pop("periodic_runtime_failure", None)
    st.session_state.pop("breakdown_summary", None)

    if (
        result.status == RuntimeDeliveryBridgeStatusV2.READY
        and result.console_view is not None
        and result.console_view.breakdown is not None
    ):
        try:
            summary_result = run_day89_breakdown_summary_v2(
                primary_result=result,
                reference_date=date.today(),
            )
        except Exception as exc:  # noqa: BLE001
            st.warning(
                "主查询已成功，但可信汇总查询未完成；"
                "页面不会改用明细行自行求和。"
            )
            st.code(f"{type(exc).__name__}: {exc}")
        else:
            st.session_state["breakdown_summary"] = summary_result


def _submit_agentic_investigation() -> None:
    """
    用户显式触发一次 bounded Agentic Investigation Step。

    只把最终安全 InvestigationDeliveryResultV2 保存到 session_state。
    Runtime Step 包含 server-internal trusted execution context，
    因此只作为当前函数局部变量存在。
    """

    seed = _runtime_result()
    request = st.session_state.get("entry_request")

    if (
        seed is None
        or seed.status != RuntimeDeliveryBridgeStatusV2.READY
        or seed.delivery is None
    ):
        st.warning("当前没有 READY Seed Delivery，不能启动受控深入调查。")
        return

    if (
        request is None
        or request.entry_mode
        != DecisionConsoleEntryModeV2.INVESTIGATION
    ):
        st.warning("当前入口不是 Investigation，不能启动 Agentic Step。")
        return

    with st.spinner(
        "Planner 正在从受控动作集合中选择一步 → "
        "Governed Tool → Observation → Evidence Delivery..."
    ):
        try:
            runtime_step = run_day89_agentic_investigation_step_v2(
                seed_result=seed,
                reference_date=date.today(),
                include_category_action=True,
                budget_policy=InvestigationBudgetPolicyV2(
                    max_investigation_steps=1,
                    max_retries_per_action=0,
                ),
                session_policy=InvestigationSessionPolicyV2(
                    max_rounds=2,
                    max_total_investigation_steps=2,
                ),
            )

            delivered = build_investigation_step_delivery_v2(
                seed_result=seed,
                runtime_step=runtime_step,
                request_subject=request.question,
            )
        except GovernanceConfigurationError as exc:
            st.error("Governance Runtime 配置未准备好。")
            st.code(str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            st.error(
                "受控深入调查发生未预期错误；"
                "Seed Delivery 保持不变，不生成替代调查结果。"
            )
            st.code(f"{type(exc).__name__}: {exc}")
            return

    # 只保存安全 Delivery / safe continuation state；
    # 不持久化 runtime_step / compiled / SQL context。
    st.session_state["agentic_delivery"] = delivered
    _clear_agentic_hitl_state()

    if (
        runtime_step.stop_status is not None
        and runtime_step.stop_status.can_continue
    ):
        continuation = build_day89_continuation_state_v2(
            runtime_step=runtime_step,
        )
        st.session_state[
            "agentic_continuation_state"
        ] = continuation
        st.session_state[
            "agentic_prior_continuation_stop_statuses"
        ] = (
            runtime_step.stop_status,
        )


def _submit_agentic_clarification_gate() -> None:
    """
    用户选择“我先指定首个调查方向”后，先建立真实 CLARIFY Gate。

    此阶段：
    - 不执行 Investigation Tool；
    - 不新增 Tool Audit；
    - 只保存 CLARIFICATION_READY Delivery
      + safe PendingClarificationState。
    """

    seed = _runtime_result()
    request = st.session_state.get("entry_request")

    if (
        seed is None
        or seed.status != RuntimeDeliveryBridgeStatusV2.READY
        or seed.delivery is None
    ):
        st.warning(
            "当前没有 READY Seed Delivery，不能建立 Clarification Gate。"
        )
        return

    if (
        request is None
        or request.entry_mode
        != DecisionConsoleEntryModeV2.INVESTIGATION
    ):
        st.warning(
            "当前入口不是 Investigation，不能建立 Clarification Gate。"
        )
        return

    requirement = (
        build_day89_direction_clarification_requirement_v2()
    )
    contract = (
        build_day89_direction_resolution_contract_v2()
    )

    with st.spinner(
        "正在建立受控 Clarification Gate；"
        "当前不会执行 Investigation Tool..."
    ):
        try:
            runtime_step = (
                run_day89_agentic_investigation_step_v2(
                    seed_result=seed,
                    reference_date=date.today(),
                    planner=(
                        plan_day89_direction_clarification_v2
                    ),
                    clarification_requirement=requirement,
                    include_category_action=True,
                    budget_policy=InvestigationBudgetPolicyV2(
                        max_investigation_steps=1,
                        max_retries_per_action=0,
                    ),
                    session_policy=InvestigationSessionPolicyV2(
                        max_rounds=1,
                        max_total_investigation_steps=1,
                    ),
                )
            )

            delivered = build_investigation_step_delivery_v2(
                seed_result=seed,
                runtime_step=runtime_step,
                request_subject=request.question,
            )

            pending = (
                build_day89_pending_clarification_state_v2(
                    runtime_step=runtime_step,
                    resolution_contract=contract,
                )
            )
        except GovernanceConfigurationError as exc:
            st.error("Governance Runtime 配置未准备好。")
            st.code(str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            st.error(
                "Clarification Gate 建立失败；"
                "Seed Delivery 保持不变。"
            )
            st.code(f"{type(exc).__name__}: {exc}")
            return

    _clear_agentic_hitl_state()
    st.session_state["agentic_delivery"] = delivered
    st.session_state[
        "agentic_pending_clarification"
    ] = pending


def _submit_agentic_clarification_response(
    choice_id: str,
) -> None:
    """
    用户只能提交 server-owned choice_id。

    Resolver 成功前不会执行 Tool；
    成功后用户选择的已有合法 Action 才进入 Governed Runtime。
    """

    previous = _agentic_result()
    pending = _pending_clarification_state()
    request = st.session_state.get("entry_request")

    if (
        previous is None
        or previous.status
        != InvestigationDeliveryStatusV2
        .CLARIFICATION_READY
        or previous.delivery is None
    ):
        st.warning(
            "当前没有 CLARIFICATION_READY Delivery。"
        )
        return

    if pending is None:
        st.warning(
            "当前没有可用的安全 Pending Clarification State。"
        )
        return

    if (
        request is None
        or request.entry_mode
        != DecisionConsoleEntryModeV2.INVESTIGATION
    ):
        st.warning(
            "当前入口不是 Investigation，不能提交 Clarification。"
        )
        return

    allowed_choice_ids = {
        item.choice_id
        for item in pending.resolution_contract.choices
    }

    if choice_id not in allowed_choice_ids:
        st.warning(
            "该 choice_id 不属于当前 server-owned Resolution Contract。"
        )
        return

    with st.spinner(
        "正在确定性解析用户选择 → "
        "恢复受控 Runtime → Governed Tool → Evidence..."
    ):
        try:
            resumed = (
                resume_day89_agentic_investigation_after_clarification_v2(
                    pending=pending,
                    response=ClarificationResponseV2(
                        choice_id=choice_id
                    ),
                    planner=(
                        plan_day89_resolved_single_action_v2
                    ),
                )
            )

            delivered = (
                build_resolved_clarification_step_delivery_v2(
                    previous_result=previous,
                    resume_result=resumed,
                    request_subject=request.question,
                )
            )
        except GovernanceConfigurationError as exc:
            st.error("Governance Runtime 配置未准备好。")
            st.code(str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            st.error(
                "Clarification Resume 发生未预期错误；"
                "原 CLARIFICATION_READY Delivery 保持不变。"
            )
            st.code(f"{type(exc).__name__}: {exc}")
            return

    st.session_state["agentic_delivery"] = delivered

    if (
        delivered.status
        == InvestigationDeliveryStatusV2.READY
    ):
        _clear_agentic_hitl_state()


def _submit_agentic_continuation() -> None:
    """
    用户明确点击 Continue 后，才恢复下一 Round。

    浏览器 Session 只持有：
    - safe Investigation Delivery；
    - Day89InvestigationContinuationStateV2；
    - 历史 InvestigationStopStatusV2。

    server-internal envelope / compiled SQL / parameters
    每个新请求都在服务器重新构建。
    """

    previous = _agentic_result()
    continuation = _continuation_state()
    prior_stop_statuses = (
        _prior_continuation_stop_statuses()
    )
    request = st.session_state.get("entry_request")

    if (
        previous is None
        or previous.status
        != InvestigationDeliveryStatusV2.READY
        or previous.delivery is None
    ):
        st.warning(
            "当前没有 READY Agentic Delivery，不能继续下一轮。"
        )
        return

    if continuation is None:
        st.warning(
            "当前没有可用的安全 Continuation State。"
        )
        return

    if (
        request is None
        or request.entry_mode
        != DecisionConsoleEntryModeV2.INVESTIGATION
    ):
        st.warning(
            "当前入口不是 Investigation，不能继续下一轮。"
        )
        return

    with st.spinner(
        "已收到用户明确 Continue → "
        "恢复受控 Session → Planner → Governed Tool → Evidence..."
    ):
        try:
            runtime_step = (
                continue_day89_agentic_investigation_step_v2(
                    delivery=previous.delivery,
                    continuation_state=continuation,
                    user_requested_continue=True,
                )
            )

            delivered = (
                build_continued_investigation_step_delivery_v2(
                    previous_result=previous,
                    runtime_step=runtime_step,
                    prior_transitions=(
                        continuation.prior_transitions
                    ),
                    prior_continuation_stop_statuses=(
                        prior_stop_statuses
                    ),
                    request_subject=request.question,
                )
            )
        except GovernanceConfigurationError as exc:
            st.error("Governance Runtime 配置未准备好。")
            st.code(str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            st.error(
                "Continuation Runtime 发生未预期错误；"
                "上一轮安全 Delivery 保持不变。"
            )
            st.code(
                f"{type(exc).__name__}: {exc}"
            )
            return

    st.session_state["agentic_delivery"] = delivered

    # 当前 Round 结束后，只有 can_continue=True 才继续保留安全状态。
    _clear_agentic_hitl_state()

    if (
        runtime_step.stop_status is not None
        and runtime_step.stop_status.can_continue
    ):
        next_continuation = (
            build_day89_continuation_state_v2(
                runtime_step=runtime_step,
                prior_transitions=(
                    continuation.prior_transitions
                ),
            )
        )

        st.session_state[
            "agentic_continuation_state"
        ] = next_continuation
        st.session_state[
            "agentic_prior_continuation_stop_statuses"
        ] = (
            *prior_stop_statuses,
            runtime_step.stop_status,
        )


def _submit_periodic_report(
    *,
    cadence: str,
    anchor_date: date,
    widget_state_value: date | None = None,
) -> None:
    submit_id = f"d93-submit-{uuid4().hex[:12]}"

    st.session_state["periodic_runtime_trace"] = {
        "submit_id": submit_id,
        "stage": "submit_received",
        "cadence": cadence,
        "widget_return_anchor": anchor_date.isoformat(),
        "widget_session_anchor": (
            widget_state_value.isoformat()
            if isinstance(widget_state_value, date)
            else None
        ),
    }

    _log_periodic_lifecycle_v2(
        submit_id=submit_id,
        event="submit_received",
        anchor_date=anchor_date,
        cadence=cadence,
    )

    try:
        request = _build_periodic_report_request(
            cadence=cadence,
            anchor_date=anchor_date,
        )
    except (ValidationError, ValueError) as exc:
        _update_periodic_runtime_trace_v2(
            stage="entry_validation_failed",
            exception_type=type(exc).__name__,
        )
        _log_periodic_lifecycle_v2(
            submit_id=submit_id,
            event="entry_validation_failed",
            anchor_date=anchor_date,
            cadence=cadence,
            exception_type=type(exc).__name__,
        )
        st.error("入口请求未通过合同校验。")
        st.code(str(exc))
        return

    _update_periodic_runtime_trace_v2(
        stage="request_built",
        request_anchor=request.report_anchor_date,
        request_cadence=request.report_cadence.value,
    )

    _log_periodic_lifecycle_v2(
        submit_id=submit_id,
        event="request_built",
        anchor_date=request.report_anchor_date,
        cadence=request.report_cadence.value,
    )

    st.session_state["entry_request"] = request
    st.session_state.pop("runtime_delivery", None)
    st.session_state.pop("breakdown_summary", None)
    st.session_state.pop("periodic_runtime_delivery", None)
    st.session_state.pop("periodic_runtime_failure", None)
    st.session_state.pop("agentic_delivery", None)
    _clear_agentic_hitl_state()

    _update_periodic_runtime_trace_v2(
        stage="runtime_call_starting",
        entry_request_in_session=(
            "entry_request" in st.session_state
        ),
        delivery_present_before_runtime=(
            "periodic_runtime_delivery" in st.session_state
        ),
    )

    with st.spinner(
        "正在执行 Overall / Channel Governed Query → "
        "Result Protection → Evidence → Periodic Comparison "
        "→ Contribution（如允许）..."
    ):
        try:
            _update_periodic_runtime_trace_v2(
                stage="runtime_call_started",
            )
            _log_periodic_lifecycle_v2(
                submit_id=submit_id,
                event="runtime_start",
                anchor_date=request.report_anchor_date,
                cadence=request.report_cadence.value,
            )
            result = (
                run_day89_periodic_gmv_channel_contribution_v2(
                    cadence=request.report_cadence,
                    anchor_date=request.report_anchor_date,
                )
            )
        except GovernanceConfigurationError as exc:
            diagnostic_id = f"d93-periodic-{uuid4().hex[:12]}"
            _update_periodic_runtime_trace_v2(
                stage="runtime_exception",
                exception_type=type(exc).__name__,
                diagnostic_id=diagnostic_id,
            )
            _log_periodic_lifecycle_v2(
                submit_id=submit_id,
                event="runtime_exception",
                anchor_date=request.report_anchor_date,
                cadence=request.report_cadence.value,
                exception_type=type(exc).__name__,
                diagnostic_id=diagnostic_id,
            )
            st.session_state["periodic_runtime_failure"] = {
                "failure_stage": "governance_configuration",
                "exception_type": type(exc).__name__,
                "diagnostic_id": diagnostic_id,
            }
            st.error("Governance Runtime 配置未准备好。")
            st.caption(f"诊断 ID：{diagnostic_id}")
            return
        except Exception as exc:  # noqa: BLE001
            diagnostic_id = f"d93-periodic-{uuid4().hex[:12]}"
            _update_periodic_runtime_trace_v2(
                stage="runtime_exception",
                exception_type=type(exc).__name__,
                diagnostic_id=diagnostic_id,
            )
            _log_periodic_lifecycle_v2(
                submit_id=submit_id,
                event="runtime_exception",
                anchor_date=request.report_anchor_date,
                cadence=request.report_cadence.value,
                exception_type=type(exc).__name__,
                diagnostic_id=diagnostic_id,
            )
            st.session_state["periodic_runtime_failure"] = {
                "failure_stage": "periodic_runtime_call",
                "exception_type": type(exc).__name__,
                "diagnostic_id": diagnostic_id,
            }
            st.error(
                "Periodic Runtime 调用发生未预期错误；"
                "没有生成替代报表。"
            )
            st.write("异常类型：", type(exc).__name__)
            st.caption(f"诊断 ID：{diagnostic_id}")
            return

    result_status = (
        result.status.value
        if hasattr(result, "status")
        else None
    )

    _update_periodic_runtime_trace_v2(
        stage="runtime_returned",
        runtime_result_type=type(result).__name__,
        runtime_result_status=result_status,
    )

    _log_periodic_lifecycle_v2(
        submit_id=submit_id,
        event="runtime_return",
        anchor_date=request.report_anchor_date,
        cadence=request.report_cadence.value,
        result_type=type(result).__name__,
        result_status=result_status,
    )

    st.session_state["periodic_runtime_delivery"] = result

    stored = st.session_state.get(
        "periodic_runtime_delivery"
    )

    _update_periodic_runtime_trace_v2(
        stage="session_written",
        session_has_delivery_after_write=(
            "periodic_runtime_delivery" in st.session_state
        ),
        session_value_type_after_write=(
            type(stored).__name__
            if stored is not None
            else None
        ),
        session_isinstance_after_write=isinstance(
            stored,
            MonthlyContributionDeliveryResultV2,
        ),
    )

    _log_periodic_lifecycle_v2(
        submit_id=submit_id,
        event="session_written",
        anchor_date=request.report_anchor_date,
        cadence=request.report_cadence.value,
        result_type=(
            type(stored).__name__
            if stored is not None
            else None
        ),
        result_status=(
            stored.status.value
            if (
                stored is not None
                and hasattr(stored, "status")
            )
            else None
        ),
    )

    st.session_state.pop("periodic_runtime_failure", None)


def main() -> None:
    st.set_page_config(
        page_title=APP_TITLE,
        page_icon="📊",
        layout="wide",
    )

    _render_page_style()

    st.title(APP_TITLE)
    st.caption("业务问题 / 报表定义 → 受治理证据 → 决策交付")

    st.info("Day89 当前接通：Investigation 渠道 GMV + 可信 Overall 汇总 + 多 Round 受控 Agentic Investigation（显式 Continue / Clarification Choice）；Periodic Report 支持 Daily DOD / Weekly WOW / Monthly MOM，并在 Result Protection 阻断细分时进行可信降级。")

    entry_mode_label = st.radio(
        "入口类型",
        options=("Investigation", "Periodic Report"),
        horizontal=True,
    )

    if entry_mode_label == "Investigation":
        with st.form("investigation_entry_form"):
            question = st.text_area(
                "业务问题",
                placeholder="例如：2025年各渠道GMV是多少？",
                height=100,
            )
            submitted = st.form_submit_button(
                "开始调查",
                type="primary",
            )

        if submitted:
            _submit_investigation(question)

    else:
        with st.form("periodic_report_entry_form"):
            cadence = st.selectbox(
                "报表周期",
                options=tuple(item.value for item in PeriodicReportCadenceV2),
                format_func=lambda value: {
                    "daily": "Daily",
                    "weekly": "Weekly",
                    "monthly": "Monthly",
                }[value],
            )

            (
                anchor_label,
                default_anchor,
                max_anchor,
                anchor_help,
            ) = _periodic_anchor_ui_v2(cadence)

            anchor_state_key = (
                _periodic_anchor_state_key_v2(cadence)
            )

            if anchor_state_key not in st.session_state:
                st.session_state[anchor_state_key] = (
                    default_anchor
                )
            elif (
                st.session_state[anchor_state_key]
                > max_anchor
            ):
                # 防止系统日期推进后残留一个超出当前允许范围的值。
                st.session_state[anchor_state_key] = (
                    max_anchor
                )

            anchor_date = st.date_input(
                anchor_label,
                max_value=max_anchor,
                help=anchor_help,
                key=anchor_state_key,
            )

            submitted = st.form_submit_button(
                "生成周期报表请求",
                type="primary",
            )

        if submitted:
            widget_state_value = st.session_state.get(
                anchor_state_key
            )

            _submit_periodic_report(
                cadence=cadence,
                anchor_date=anchor_date,
                widget_state_value=(
                    widget_state_value
                    if isinstance(widget_state_value, date)
                    else None
                ),
            )

    st.divider()

    business_tab, analyst_tab, engineering_tab = st.tabs(
        ("业务决策", "分析视图", "工程视图")
    )

    with business_tab:
        _render_business_view()

    with analyst_tab:
        _render_analyst_view()

    with engineering_tab:
        _render_engineering_view()


if __name__ == "__main__":
    main()
