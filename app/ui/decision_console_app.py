from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from html import escape
from hashlib import sha256
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
    run_day93_business_clarification_continuation_v1,
)
from app.delivery.monthly_contribution_delivery_v2 import (
    MonthlyContributionDeliveryResultV2,
    MonthlyContributionDeliveryStatusV2,
    run_day89_periodic_gmv_channel_contribution_v2,
)
from app.delivery.periodic_business_report_v2 import (
    PeriodicBusinessReportStatusV2,
    PeriodicBusinessReportV2,
    PeriodicDriverReconciliationStatusV2,
    PeriodicMetricSectionV2,
    PeriodicMetricStatusV2,
    run_day93_periodic_business_report_v2,
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
from app.delivery.investigation_focus_scope_v1 import (
    InvestigationFocusScopeV1,
    build_contribution_investigation_focus_scope_v1,
)
from app.delivery.focused_change_breakdown_delivery_v2 import (
    ChangeBreakdownScopeKindV2,
    FocusedChangeBreakdownDeliveryV2,
)
from app.agents.focused_change_breakdown_v2 import (
    FocusedChangeDimensionV2,
)
from app.delivery.investigation_runtime_v2 import (
    Day89InvestigationContinuationStateV2,
    Day89PendingClarificationStateV2,
    build_day89_continuation_state_v2,
    build_day89_pending_clarification_state_v2,
    continue_day89_agentic_investigation_step_v2,
    resume_day89_agentic_investigation_after_clarification_v2,
    run_day89_agentic_investigation_step_v2,
    run_day93_geography_exploration_v2,
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
from app.agents.investigation_evidence_sufficiency_v2 import (
    InvestigationBudgetExtensionPolicyV2,
    InvestigationEvidenceSufficiencyV2,
    assess_investigation_evidence_sufficiency_v2,
)
from app.agents.geography_branch_decision_v2 import (
    GeographyBranchDecisionTypeV2,
    GeographyBranchDecisionV2,
    build_geography_branch_decision_v2,
)
from app.agents.investigation_route_v2 import (
    GeographyLevelV2,
)
from app.agents.user_investigation_intent_v2 import (
    UserInvestigationCapabilityResolutionV2,
    UserInvestigationCapabilityStatusV2,
    UserInvestigationDomainV2,
    UserInvestigationIntentV2,
    resolve_user_investigation_intent_v2,
)
from app.agents.user_investigation_planner_v2 import (
    plan_user_selected_investigation_action_v2,
)
from app.agents.analytical_path_contract_v2 import (
    AnalyticalGrainV2,
    AnalyticalOperationV2,
    AnalyticalPathNodeV2,
)
from app.agents.business_analytical_intent_v2 import (
    BusinessAnalyticalIntentRequestV2,
    BusinessAnalyticalIntentResolutionV2,
    BusinessAnalyticalIntentStatusV2,
    BusinessAnalyticalIntentTargetV2,
    materialize_analytical_path_node_v2,
    resolve_business_analytical_intent_v2,
)
from app.agents.analytical_capability_registry_v2 import (
    AnalyticalCapabilityResolutionV2,
    AnalyticalCapabilityStatusV2,
    resolve_analytical_capability_v2,
)
from app.agents.user_analytical_path_decision_v2 import (
    UserAnalyticalExecutionModeV2,
    UserAnalyticalPathDecisionV2,
    decide_user_analytical_path_v2,
)
from app.ui.analytical_ui_projection_v2 import (
    analytical_grain_label_v2,
    analytical_target_business_label_v2,
    business_safe_breakdown_row_v2,
    explicit_grain_options_v2,
)
from app.delivery.business_period_label_v2 import (
    format_business_period_label_v2,
)
from app.delivery.business_scope_projection_v2 import (
    build_business_scope_projection_v2,
)
from app.delivery.runtime_delivery_bridge_v2 import (
    RuntimeDeliveryBridgeResultV2,
    RuntimeDeliveryBridgeStatusV2,
)
from app.delivery.analysis_session_history_v1 import (
    AnalysisHistoryItemV1,
    AnalysisSessionHistoryV1,
    activate_analysis_history_item_v1,
    append_analysis_history_item_v1,
    build_analysis_history_item_v1,
    clear_active_analysis_history_v1,
    empty_analysis_session_history_v1,
    get_analysis_history_item_v1,
    update_analysis_history_snapshots_v1,
)
from app.delivery.analysis_investigation_snapshot_v1 import (
    AnalysisInvestigationSnapshotV1,
    build_analysis_evidence_lineage_v1,
    empty_analysis_investigation_snapshot_v1,
)
from app.delivery.investigation_report_v2 import (
    InvestigationReportV2,
    build_investigation_report_v2,
)
from app.delivery.report_export_v2 import (
    render_investigation_report_markdown_v2,
    render_periodic_report_markdown_v2,
)
from app.delivery.business_document_export_v2 import (
    render_investigation_business_docx_v2,
    render_periodic_business_docx_v2,
)
from app.delivery.business_workbook_export_v2 import (
    render_investigation_business_xlsx_v2,
    render_periodic_business_xlsx_v2,
)
from app.delivery.business_clarification_continuation_v1 import (
    BusinessClarificationResolutionV1,
    PendingBusinessClarificationV1,
    build_pending_business_clarification_v1,
    resolve_business_clarification_v1,
)
from app.delivery.fact_composition_delivery_v2 import (
    FactCompositionDimensionV2,
    FactCompositionReconciliationStatusV2,
    FactCompositionResultV2,
    FactCompositionStatusV2,
    fact_composition_available_dimensions_v2,
    run_day93_fact_composition_v2,
)
from app.governance.governance_runtime import (
    GovernanceConfigurationError,
)
from app.semantic_layer.analysis_mode_contract_v2 import (
    AnalysisModeV2,
    analysis_mode_allows_agentic_v2,
)
from app.ui.decision_console_presenters_v2 import (
    append_trusted_summary_row_v2,
    build_chart_rows_v2,
    build_contribution_chart_rows_v2,
    build_contribution_display_rows_v2,
    build_display_rows_v2,
    build_fact_composition_chart_rows_v2,
    build_fact_composition_display_rows_v2,
    format_evidence_sufficiency_v2,
    format_contribution_direction_v2,
    format_evidence_type_v2,
    format_investigation_action_v2,
    format_loop_directive_v2,
    format_metric_name_v2,
    format_fact_metric_value_v2,
    format_business_metric_value_v2,
    format_result_grain_name_v2,
    format_observation_status_v2,
    format_stop_reason_v2,
    format_number_v2,
    format_percentage_v2,
    format_reconciliation_status_v2,
    format_runtime_status_v2,
    format_statement_v2,
    normalize_scope_summary_v2,
    build_periodic_metric_comparison_rows_v2,
    build_periodic_r12_readiness_rows_v2,
    build_periodic_r12_reconciliation_rows_v2,
    format_periodic_metric_delta_v2,
    format_periodic_metric_delta_inline_v2,
    format_periodic_metric_value_v2,
    format_periodic_report_status_v2,
    format_periodic_r12_readiness_status_v2,
    format_periodic_r12_reconciliation_status_v2,
    format_periodic_r12_runtime_status_v2,
    periodic_metric_delta_direction_v2,
    R12_PERIODIC_METRIC_NAMES_V2,
)


APP_TITLE = "AI Data Analyst · Decision Console"

# Day93 P0-1G:
# 每次用户点击仍最多产生 1 个 Planner-selected Investigation Action。
# 对 F02 comparison-bearing Focus，category / geography Action 可由服务器
# 追加 1 次同 Scope 的 reference companion read，用于两期变化分解；
# companion read 不是新的 Planner 决策，也不扩 Action Space。
# 整个 Session 最多允许覆盖当前已注册的
# channel / category + Geography Hierarchy 调查方向。
AGENTIC_MAX_STEPS_PER_ROUND_V2 = 1
AGENTIC_SOFT_BUDGET_STEPS_V2 = 2
AGENTIC_MAX_ROUNDS_V2 = 5
AGENTIC_MAX_TOTAL_STEPS_V2 = 5


def _analysis_mode_label_v2(
    analysis_mode: AnalysisModeV2,
) -> str:
    return {
        AnalysisModeV2.FACT: "事实查询",
        AnalysisModeV2.COMPOSITION: "构成分析",
        AnalysisModeV2.COMPARISON: "比较分析",
        AnalysisModeV2.DIAGNOSTIC: "诊断分析",
        AnalysisModeV2.INVESTIGATION: "决策调查",
    }[analysis_mode]


def _investigation_action_label_v1(action_id: str) -> str:
    """Business-facing Investigation Action 名称。"""

    labels = {
        "drill_channel": "渠道变化",
        "drill_category": "品类变化",
        "drill_area": "大区变化",
        "drill_province": "省级变化",
        "drill_city": "城市变化",
        "drill_campaign": "活动实例变化",
        "drill_region": "城市变化（旧路径）",
    }

    return labels.get(
        action_id,
        format_investigation_action_v2(action_id),
    )


def _build_seed_investigation_focus_scope_v1(
    seed: RuntimeDeliveryBridgeResultV2,
) -> InvestigationFocusScopeV1 | None:
    """
    根据 F02 Route Policy 决定是否建立单一 Channel Focus。

    - KEEP_REQUESTED_SCOPE：明确不建立 Focus；
    - FOCUS_MEMBER：继续使用旧 Recommendation 作为可信
      channel code + reference/current/delta binding。

    这样 Near-Tie 不会因为 Top1 排名而偷偷锁定京东。
    """

    view = seed.console_view
    if view is None:
        return None

    route_recommendation = (
        view.contribution_investigation_route_recommendation
    )
    recommendation = (
        view.contribution_investigation_recommendation
    )

    if route_recommendation is not None:
        strategy = (
            route_recommendation.route.scope_strategy.value
        )

        if strategy == "keep_requested_scope":
            return None

        if strategy == "focus_member":
            if recommendation is None:
                raise ValueError(
                    "FOCUS_MEMBER Route 缺少可信 legacy focus binding。"
                )
            return build_contribution_investigation_focus_scope_v1(
                recommendation
            )

        raise ValueError(
            f"Unsupported Investigation Scope Strategy: {strategy}"
        )

    # 非 F02 / 旧兼容路径。
    if recommendation is None:
        return None

    return build_contribution_investigation_focus_scope_v1(
        recommendation
    )


def _agentic_budget_policy_v2() -> InvestigationBudgetPolicyV2:
    """
    每个用户确认的 Round 最多执行一个调查动作。

    保持 HITL：
    一个 Round 结束后，只有用户明确 Continue 才能开启下一 Round。
    """

    return InvestigationBudgetPolicyV2(
        max_investigation_steps=(
            AGENTIC_MAX_STEPS_PER_ROUND_V2
        ),
        max_retries_per_action=0,
    )


def _agentic_session_policy_v2() -> InvestigationSessionPolicyV2:
    """
    当前 Production Action Catalog 包含：
    channel / category，以及按 Evidence 逐层解锁的
    area → province → city Geography Hierarchy。

    Session Budget 只允许覆盖这些已注册动作，
    不扩展 Tool、Permission 或 Scope。
    """

    return InvestigationSessionPolicyV2(
        max_rounds=AGENTIC_MAX_ROUNDS_V2,
        max_total_investigation_steps=(
            AGENTIC_MAX_TOTAL_STEPS_V2
        ),
    )


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




def _analysis_session_history_v1(
) -> AnalysisSessionHistoryV1:
    value = st.session_state.get(
        "analysis_session_history_v1"
    )

    if isinstance(value, AnalysisSessionHistoryV1):
        return value

    history = empty_analysis_session_history_v1()
    st.session_state["analysis_session_history_v1"] = history
    return history


def _store_analysis_session_history_v1(
    history: AnalysisSessionHistoryV1,
) -> None:
    st.session_state["analysis_session_history_v1"] = history

    snapshots = st.session_state.get(
        "analysis_investigation_snapshots_v1",
        {},
    )
    if not isinstance(snapshots, dict):
        snapshots = {}

    retained_ids = {item.history_id for item in history.items}
    st.session_state[
        "analysis_investigation_snapshots_v1"
    ] = {
        key: value
        for key, value in snapshots.items()
        if (
            key in retained_ids
            and isinstance(value, AnalysisInvestigationSnapshotV1)
        )
    }


def _analysis_investigation_snapshots_v1(
) -> dict[str, AnalysisInvestigationSnapshotV1]:
    value = st.session_state.get(
        "analysis_investigation_snapshots_v1",
        {},
    )
    if not isinstance(value, dict):
        return {}
    return {
        key: item
        for key, item in value.items()
        if (
            isinstance(key, str)
            and isinstance(item, AnalysisInvestigationSnapshotV1)
        )
    }


def _analysis_investigation_snapshot_for_history_v1(
    history_id: str,
) -> AnalysisInvestigationSnapshotV1 | None:
    return _analysis_investigation_snapshots_v1().get(history_id)


def _sync_active_history_investigation_snapshot_v1() -> None:
    """同步 safe Agentic / Exploration 状态，不保存 SQL context。"""
    history = _analysis_session_history_v1()
    history_id = history.active_history_id
    if history_id is None:
        return

    snapshot = AnalysisInvestigationSnapshotV1(
        agentic_delivery_snapshot=_agentic_result(),
        focused_change_snapshots=_focused_change_results_v2(),
        geography_exploration_snapshots=(
            _geography_exploration_results_v2()
        ),
        completed_analytical_nodes=(
            _stored_completed_analytical_nodes_v2()
        ),
        continuation_state_snapshot=_continuation_state(),
        prior_stop_status_snapshots=(
            _prior_continuation_stop_statuses()
        ),
        pending_clarification_snapshot=(
            _pending_clarification_state()
        ),
        initial_decision_owner=(
            _agentic_initial_decision_owner_v2()
        ),
        user_selected_action=(
            _agentic_user_selected_action_v2()
        ),
    )

    snapshots = _analysis_investigation_snapshots_v1()
    snapshots[history_id] = snapshot
    st.session_state[
        "analysis_investigation_snapshots_v1"
    ] = snapshots


def _restore_history_investigation_snapshot_v1(
    history_id: str,
) -> None:
    snapshot = _analysis_investigation_snapshot_for_history_v1(
        history_id
    )
    if snapshot is None:
        snapshot = empty_analysis_investigation_snapshot_v1()

    if snapshot.agentic_delivery_snapshot is not None:
        st.session_state["agentic_delivery"] = (
            snapshot.agentic_delivery_snapshot
        )
    else:
        st.session_state.pop("agentic_delivery", None)

    st.session_state[
        "agentic_focused_change_results_v2"
    ] = snapshot.focused_change_snapshots
    st.session_state[
        "geography_exploration_results_v2"
    ] = snapshot.geography_exploration_snapshots
    st.session_state[
        "user_completed_analytical_nodes_v2"
    ] = snapshot.completed_analytical_nodes

    if snapshot.continuation_state_snapshot is not None:
        st.session_state[
            "agentic_continuation_state"
        ] = snapshot.continuation_state_snapshot
    else:
        st.session_state.pop("agentic_continuation_state", None)

    if snapshot.prior_stop_status_snapshots:
        st.session_state[
            "agentic_prior_continuation_stop_statuses"
        ] = snapshot.prior_stop_status_snapshots
    else:
        st.session_state.pop(
            "agentic_prior_continuation_stop_statuses", None
        )

    if snapshot.pending_clarification_snapshot is not None:
        st.session_state[
            "agentic_pending_clarification"
        ] = snapshot.pending_clarification_snapshot
    else:
        st.session_state.pop("agentic_pending_clarification", None)

    if snapshot.initial_decision_owner is not None:
        st.session_state[
            "agentic_initial_decision_owner_v2"
        ] = snapshot.initial_decision_owner
    if snapshot.user_selected_action is not None:
        st.session_state[
            "agentic_user_selected_action_v2"
        ] = snapshot.user_selected_action


def _render_active_analysis_evidence_lineage_v1() -> None:
    item = _active_analysis_history_item_v1()
    if item is None:
        return

    lineage = build_analysis_evidence_lineage_v1(
        seed_evidence_ids=item.evidence_ids,
        snapshot=_analysis_investigation_snapshot_for_history_v1(
            item.history_id
        ),
    )
    if not lineage:
        return

    with st.expander("查看本次分析证据链", expanded=False):
        st.caption(
            "这里只展示 Result Protection 之后的 Evidence / Plan / "
            "Audit 标识与对账状态；不展示 SQL、parameters 或 raw rows。"
        )
        stage_labels = {
            "seed": "Seed",
            "agentic_pack": "受控调查",
            "investigation_change": "两期变化分解",
            "user_exploration": "用户探索",
        }
        rows = [
            {
                "顺序": record.sequence_number,
                "阶段": stage_labels.get(
                    record.stage.value, record.stage.value
                ),
                "分析对象": record.business_label,
                "Evidence": "、".join(record.evidence_ids),
                "Query Plan": "、".join(record.plan_names) or "—",
                "对账": record.reconciliation_status or "—",
            }
            for record in lineage
        ]
        st.dataframe(rows, use_container_width=True, hide_index=True)


def _pending_business_clarification_v1(
) -> PendingBusinessClarificationV1 | None:
    value = st.session_state.get(
        "pending_business_clarification_v1"
    )

    if isinstance(
        value,
        PendingBusinessClarificationV1,
    ):
        return value

    return None


def _clear_pending_business_clarification_v1() -> None:
    st.session_state.pop(
        "pending_business_clarification_v1",
        None,
    )


def _deactivate_analysis_history_v1() -> None:
    history = _analysis_session_history_v1()

    if history.active_history_id is None:
        return

    _store_analysis_session_history_v1(
        clear_active_analysis_history_v1(
            session=history
        )
    )


def _active_analysis_history_item_v1(
) -> AnalysisHistoryItemV1 | None:
    history = _analysis_session_history_v1()

    if history.active_history_id is None:
        return None

    return get_analysis_history_item_v1(
        session=history,
        history_id=history.active_history_id,
    )


def _sync_active_history_auxiliary_snapshots_v1() -> None:
    history = _analysis_session_history_v1()

    if history.active_history_id is None:
        return

    compositions = tuple(
        _fact_composition_results_v2().values()
    )

    try:
        updated = update_analysis_history_snapshots_v1(
            session=history,
            history_id=history.active_history_id,
            breakdown_summary=_breakdown_summary_result(),
            fact_compositions=compositions,
        )
    except ValueError:
        return

    _store_analysis_session_history_v1(updated)
    _sync_active_history_investigation_snapshot_v1()


def _restore_analysis_history_item_v1(
    item: AnalysisHistoryItemV1,
) -> None:
    """
    只恢复 Session Snapshot，不重新查询数据库。
    """
    st.session_state["entry_request"] = (
        _build_investigation_request(
            item.original_question
        )
    )
    st.session_state["entry_display_question"] = (
        item.original_question
    )

    if item.resolution_note:
        st.session_state["entry_resolution_note"] = (
            item.resolution_note
        )
    else:
        st.session_state.pop(
            "entry_resolution_note",
            None,
        )

    st.session_state["runtime_delivery"] = (
        item.runtime_delivery_snapshot
    )

    if item.breakdown_summary_snapshot is not None:
        st.session_state["breakdown_summary"] = (
            item.breakdown_summary_snapshot
        )
    else:
        st.session_state.pop(
            "breakdown_summary",
            None,
        )

    st.session_state["fact_composition_results"] = {
        result.dimension.value: result
        for result in item.fact_composition_snapshots
    }

    st.session_state.pop("periodic_business_report", None)
    st.session_state.pop("periodic_business_report_failure", None)
    st.session_state.pop("periodic_runtime_delivery", None)
    st.session_state.pop("periodic_runtime_failure", None)
    st.session_state.pop("agentic_delivery", None)
    _clear_focused_change_results_v2()
    _clear_agentic_hitl_state()
    _clear_agentic_decision_context_v2()
    _clear_pending_business_clarification_v1()

    _restore_history_investigation_snapshot_v1(item.history_id)

    history = _analysis_session_history_v1()
    _store_analysis_session_history_v1(
        activate_analysis_history_item_v1(
            session=history,
            history_id=item.history_id,
        )
    )


def _render_analysis_session_history_v1() -> None:
    history = _analysis_session_history_v1()

    with st.sidebar:
        with st.expander(
            f"最近分析（{len(history.items)}/10）",
            expanded=False,
        ):
            if not history.items:
                st.caption(
                    "当前 Session 还没有可回看的 READY 分析。"
                )
                return

            for index, item in enumerate(
                history.items,
                start=1,
            ):
                active = (
                    item.history_id
                    == history.active_history_id
                )

                marker = "● " if active else ""
                st.markdown(
                    f"**{marker}{index}. {item.original_question}**"
                )
                st.caption(
                    f"{format_metric_name_v2(item.metric_name)} ｜ "
                    f"{item.analysis_window.start_date} → "
                    f"{item.analysis_window.end_date} ｜ "
                    f"{item.result_grain}"
                )
                st.caption(
                    "生成于 "
                    f"{item.created_at_utc.astimezone().strftime('%H:%M:%S')}"
                )

                deep_snapshot = (
                    _analysis_investigation_snapshot_for_history_v1(
                        item.history_id
                    )
                )
                if deep_snapshot is not None:
                    st.caption(
                        "深入调查 "
                        f"{len(deep_snapshot.focused_change_snapshots)} 步 ｜ "
                        "探索 "
                        f"{len(deep_snapshot.geography_exploration_snapshots)} 步"
                    )

                if st.button(
                    "回到此分析",
                    key=(
                        "analysis_history_restore::"
                        f"{item.history_id}"
                    ),
                    width="stretch",
                    disabled=active,
                ):
                    _restore_analysis_history_item_v1(item)
                    st.rerun()

                if index != len(history.items):
                    st.divider()


def _active_investigation_report_payload_v2(
) -> InvestigationReportV2 | None:
    """
    当前 Business Console 的 Final Investigation Report Payload。

    只从 active READY Analysis History + safe Investigation Snapshot
    构造，不重新查询、不调用 LLM、不重新计算业务结论。
    """
    history_item = _active_analysis_history_item_v1()

    if history_item is None:
        return None

    snapshot = (
        _analysis_investigation_snapshot_for_history_v1(
            history_item.history_id
        )
    )

    return build_investigation_report_v2(
        history_item=history_item,
        investigation_snapshot=snapshot,
    )


def _render_investigation_report_export_v2() -> None:
    """
    Mode-aware Business Artifact Export。

    Word / Excel / Markdown 继续消费同一个结构化 Report Payload；
    这里只根据已冻结 analysis_mode 选择业务展示名称与文件名，
    不重新查询、不调用 LLM、不重新计算业务结论。
    """

    report_payload = (
        _active_investigation_report_payload_v2()
    )

    if report_payload is None:
        st.info(
            "当前 READY 分析尚未形成可导出的 Final Report Payload。"
        )
        return

    docx_artifact = (
        render_investigation_business_docx_v2(
            report_payload
        )
    )
    xlsx_artifact = (
        render_investigation_business_xlsx_v2(
            report_payload
        )
    )
    markdown_artifact = (
        render_investigation_report_markdown_v2(
            report_payload
        )
    )

    if report_payload.analysis_mode in {
        AnalysisModeV2.FACT,
        AnalysisModeV2.COMPOSITION,
    }:
        report_label = "事实分析"
        base_prefix = "fact_analysis_report"
    elif (
        report_payload.analysis_mode
        == AnalysisModeV2.COMPARISON
    ):
        report_label = "对比分析"
        base_prefix = "comparison_report"
    else:
        report_label = "业务调查"
        base_prefix = "investigation_report"

    st.markdown("### 报告导出")
    st.caption(
        f"当前导出类型：{report_label}。"
        "Word 与 Excel 共同消费同一个结构化 Report Payload；"
        "导出层不会重新查询、调用 LLM 或重新计算业务结论。"
    )

    brief = report_payload.executive_brief

    with st.expander(
        "查看报告摘要",
        expanded=False,
    ):
        st.write(
            "业务问题：",
            report_payload.original_question,
        )
        st.write(
            "分析模式：",
            _analysis_mode_label_v2(
                report_payload.analysis_mode
            ),
        )
        st.write(
            "指标：",
            report_payload.metric_definition.chinese_name,
        )
        st.write(
            "分析窗口：",
            (
                f"{report_payload.analysis_window.start_date}"
                " → "
                f"{report_payload.analysis_window.end_date}"
            ),
        )
        st.write(
            "证据状态：",
            format_evidence_sufficiency_v2(
                brief.evidence_sufficiency
            ),
        )

        if brief.key_findings:
            st.markdown("**关键发现**")
            for item in brief.key_findings:
                st.write(
                    f"- {format_statement_v2(item.summary)}"
                )

        if brief.limitations:
            st.markdown("**必要限制**")
            for item in brief.limitations:
                st.write(
                    f"- {format_statement_v2(item.detail)}"
                )

    base_name = (
        f"{base_prefix}_{report_payload.history_id}"
    )

    left, right = st.columns(2)

    with left:
        st.download_button(
            "下载 Word 业务报告",
            data=docx_artifact,
            file_name=f"{base_name}.docx",
            mime=(
                "application/vnd.openxmlformats-officedocument."
                "wordprocessingml.document"
            ),
            key=(
                "download_investigation_docx::"
                f"{report_payload.history_id}"
            ),
            width="stretch",
        )

    with right:
        st.download_button(
            "下载 Excel 数据附件",
            data=xlsx_artifact,
            file_name=f"{base_name}.xlsx",
            mime=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
            key=(
                "download_investigation_xlsx::"
                f"{report_payload.history_id}"
            ),
            width="stretch",
        )

    with st.expander(
        "更多格式",
        expanded=False,
    ):
        st.download_button(
            "下载 Markdown（技术 / Portfolio）",
            data=markdown_artifact,
            file_name=f"{base_name}.md",
            mime="text/markdown; charset=utf-8",
            key=(
                "download_investigation_markdown::"
                f"{report_payload.history_id}"
            ),
            width="stretch",
        )



def _render_periodic_report_export_v2(
    report: PeriodicBusinessReportV2,
) -> None:
    # Day94 Periodic Business Artifact Export:
    # 页面主报表、DOCX、XLSX、Markdown 都消费
    # 同一个 PeriodicBusinessReportV2。
    docx_artifact = (
        render_periodic_business_docx_v2(
            report
        )
    )
    xlsx_artifact = (
        render_periodic_business_xlsx_v2(
            report
        )
    )
    markdown_artifact = (
        render_periodic_report_markdown_v2(
            report
        )
    )

    st.markdown("### 报表导出")
    st.caption(
        "Word 经营报告与 Excel 数据附件共同消费同一个 "
        "PeriodicBusinessReportV2；导出层不重新计算 KPI、"
        "Ratio、Delta 或 Reconciliation。"
    )

    base_name = (
        f"{report.cadence.value}_business_report_"
        f"{report.anchor_date.isoformat()}"
    )

    left, right = st.columns(2)

    with left:
        st.download_button(
            "下载 Word 经营报告",
            data=docx_artifact,
            file_name=f"{base_name}.docx",
            mime=(
                "application/vnd.openxmlformats-officedocument."
                "wordprocessingml.document"
            ),
            key=(
                "download_periodic_docx::"
                f"{report.cadence.value}::"
                f"{report.anchor_date.isoformat()}"
            ),
            width="stretch",
        )

    with right:
        st.download_button(
            "下载 Excel 数据附件",
            data=xlsx_artifact,
            file_name=f"{base_name}.xlsx",
            mime=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
            key=(
                "download_periodic_xlsx::"
                f"{report.cadence.value}::"
                f"{report.anchor_date.isoformat()}"
            ),
            width="stretch",
        )

    with st.expander(
        "更多格式",
        expanded=False,
    ):
        st.download_button(
            "下载 Markdown（技术 / Portfolio）",
            data=markdown_artifact,
            file_name=f"{base_name}.md",
            mime="text/markdown; charset=utf-8",
            key=(
                "download_periodic_markdown::"
                f"{report.cadence.value}::"
                f"{report.anchor_date.isoformat()}"
            ),
            width="stretch",
        )


def _periodic_business_report_result_v2(
) -> PeriodicBusinessReportV2 | None:
    value = st.session_state.get(
        "periodic_business_report"
    )

    if isinstance(value, PeriodicBusinessReportV2):
        return value

    return None


def _periodic_business_report_failure_v2(
) -> dict[str, str] | None:
    value = st.session_state.get(
        "periodic_business_report_failure"
    )

    if not isinstance(value, dict):
        return None

    required = {
        "failure_stage",
        "exception_type",
        "diagnostic_id",
    }

    if not required.issubset(value):
        return None

    if not all(
        isinstance(value[key], str) and value[key].strip()
        for key in required
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
    Daily / Weekly / Monthly 共享同一个用户选择的 anchor date。

    业务用户通常会用同一个历史日期横向查看日报 / 周报 / 月报，
    因此 cadence 切换不应让日期静默回到各自默认值。

    现有 main() 仍保留每个 cadence 的 max_anchor 保护：
    如果共享日期超过所选周期允许的完整周期上限，
    才会安全截断到该 cadence 的 max_anchor。
    """

    _ = cadence
    return "periodic_anchor_date::shared"

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


def _fact_composition_results_v2(
) -> dict[str, FactCompositionResultV2]:
    value = st.session_state.get(
        "fact_composition_results",
        {},
    )

    if not isinstance(value, dict):
        return {}

    return {
        key: item
        for key, item in value.items()
        if (
            isinstance(key, str)
            and isinstance(item, FactCompositionResultV2)
        )
    }


def _clear_fact_composition_state_v2() -> None:
    st.session_state.pop(
        "fact_composition_results",
        None,
    )


def _agentic_result() -> InvestigationDeliveryResultV2 | None:
    value = st.session_state.get("agentic_delivery")
    if isinstance(value, InvestigationDeliveryResultV2):
        return value
    return None


def _focused_change_results_v2(
) -> tuple[FocusedChangeBreakdownDeliveryV2, ...]:
    """
    当前页面 Session 中已经完成的安全 Focused Change 结果。

    这里只保存 deterministic Delivery；
    不保存 envelope / compiled SQL / parameters。
    """

    value = st.session_state.get(
        "agentic_focused_change_results_v2",
        (),
    )

    if not isinstance(value, tuple):
        return ()

    if not all(
        isinstance(item, FocusedChangeBreakdownDeliveryV2)
        for item in value
    ):
        return ()

    return value


def _clear_focused_change_results_v2() -> None:
    st.session_state.pop(
        "agentic_focused_change_results_v2",
        None,
    )


def _store_focused_change_result_v2(
    result: FocusedChangeBreakdownDeliveryV2 | None,
) -> None:
    if result is None:
        return

    current = list(_focused_change_results_v2())
    dimension = result.result.dimension_name

    # 同一 Investigation Action 当前只允许执行一次。
    # 若 Streamlit 生命周期导致同一维度重新写入，则以最新安全结果替换，
    # 避免侧边栏/页面重复显示。
    current = [
        item
        for item in current
        if item.result.dimension_name != dimension
    ]
    current.append(result)

    st.session_state[
        "agentic_focused_change_results_v2"
    ] = tuple(current)


def _focused_change_result_for_action_v2(
    action_id: str,
) -> FocusedChangeBreakdownDeliveryV2 | None:
    expected_dimension = {
        "drill_channel": "channel",
        "drill_category": "category",
        "drill_region": "region",
        "drill_area": "area",
        "drill_province": "province",
        "drill_city": "city",
        "drill_campaign": "campaign",
    }.get(action_id)

    if expected_dimension is None:
        return None

    for item in _focused_change_results_v2():
        if item.result.dimension_name.value == expected_dimension:
            return item

    return None


def _agentic_initial_decision_owner_v2() -> str | None:
    value = st.session_state.get(
        "agentic_initial_decision_owner_v2"
    )
    return value if value in {"system", "user"} else None


def _agentic_user_selected_action_v2() -> str | None:
    value = st.session_state.get(
        "agentic_user_selected_action_v2"
    )
    return value if isinstance(value, str) and value.strip() else None


def _clear_agentic_decision_context_v2() -> None:
    st.session_state.pop(
        "agentic_initial_decision_owner_v2",
        None,
    )
    st.session_state.pop(
        "agentic_user_selected_action_v2",
        None,
    )
    _clear_user_investigation_intent_state_v2()


def _set_agentic_initial_decision_owner_v2(
    owner: str,
) -> None:
    if owner not in {"system", "user"}:
        raise ValueError("Unsupported decision owner.")
    st.session_state[
        "agentic_initial_decision_owner_v2"
    ] = owner



def _user_investigation_capability_resolution_v2(
) -> UserInvestigationCapabilityResolutionV2 | None:
    value = st.session_state.get(
        "user_investigation_capability_resolution_v2"
    )
    if isinstance(
        value,
        UserInvestigationCapabilityResolutionV2,
    ):
        return value
    return None


def _clear_user_investigation_intent_state_v2() -> None:
    # Legacy state retained only for compatibility with older snapshots.
    st.session_state.pop(
        "user_investigation_capability_resolution_v2",
        None,
    )

    for key in (
        "user_investigation_hypothesis_v2",
        "user_analytical_intent_resolution_v2",
        "user_analytical_capability_resolution_v2",
        "user_analytical_path_decision_v2",
        "user_analytical_target_node_v2",
        "user_analytical_submitted_domain_v2",
        "user_analytical_execution_completed_v2",
        "user_completed_analytical_nodes_v2",
    ):
        st.session_state.pop(key, None)

    _clear_geography_branch_ui_state_v2()


def _business_period_pair_v2(
    comparison,
) -> tuple[str, str]:
    return (
        format_business_period_label_v2(
            comparison.reference_window
        ),
        format_business_period_label_v2(
            comparison.current_window
        ),
    )


def _agentic_budget_extension_policy_v2(
) -> InvestigationBudgetExtensionPolicyV2:
    return InvestigationBudgetExtensionPolicyV2(
        soft_budget_steps=AGENTIC_SOFT_BUDGET_STEPS_V2,
        hard_cap_steps=AGENTIC_MAX_TOTAL_STEPS_V2,
        extension_chunk_steps=2,
    )


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

        /* Periodic Business Report KPI Cards */
        .dc-kpi-card {
            min-height: 132px;
            padding: 0.95rem 1rem 0.85rem 1rem;
            border: 1px solid rgba(31, 41, 55, 0.10);
            border-radius: 14px;
            background: rgba(255, 255, 255, 0.72);
            box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
            margin-bottom: 0.75rem;
        }
        .dc-kpi-label {
            font-size: 0.80rem;
            font-weight: 600;
            color: #4b5563;
            margin-bottom: 0.42rem;
            letter-spacing: 0.01em;
        }
        .dc-kpi-current-row {
            display: flex;
            align-items: baseline;
            flex-wrap: wrap;
            gap: 0.55rem;
            min-height: 2.35rem;
        }
        .dc-kpi-current {
            font-size: 1.78rem;
            line-height: 1.15;
            font-weight: 650;
            color: #111827;
            letter-spacing: -0.025em;
        }
        .dc-kpi-delta {
            display: inline-flex;
            align-items: center;
            border-radius: 999px;
            padding: 0.18rem 0.48rem;
            font-size: 0.76rem;
            font-weight: 600;
            white-space: nowrap;
        }
        .dc-kpi-delta-up {
            color: #1d4ed8;
            background: rgba(59, 130, 246, 0.09);
        }
        .dc-kpi-delta-down {
            color: #b45309;
            background: rgba(245, 158, 11, 0.10);
        }
        .dc-kpi-delta-neutral {
            color: #6b7280;
            background: rgba(107, 114, 128, 0.09);
        }
        .dc-kpi-reference {
            margin-top: 0.58rem;
            font-size: 0.78rem;
            color: #9ca3af;
            line-height: 1.35;
        }
        .dc-kpi-reference-value {
            color: #7c8798;
            font-weight: 500;
        }
        .dc-kpi-unavailable .dc-kpi-current {
            font-size: 1.45rem;
            color: #6b7280;
        }
        .dc-kpi-note {
            margin-top: 0.42rem;
            font-size: 0.72rem;
            color: #9ca3af;
            line-height: 1.35;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_entry_summary(
    request: DecisionConsoleEntryRequestV2,
) -> None:
    st.caption("✓ 请求已通过入口合同校验")

    if request.entry_mode == DecisionConsoleEntryModeV2.INVESTIGATION:
        st.markdown("### 本次业务问题")

        display_question = st.session_state.get(
            "entry_display_question"
        )

        st.write(
            display_question
            if (
                isinstance(display_question, str)
                and display_question.strip()
            )
            else request.question
        )

        resolution_note = st.session_state.get(
            "entry_resolution_note"
        )

        if (
            isinstance(resolution_note, str)
            and resolution_note.strip()
        ):
            st.caption(
                f"已补充澄清：{resolution_note}"
            )

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
    """
    把内部 Runtime stop_stage 翻译成业务用户能理解的停止原因。

    Business View 不暴露 Query Plan / Graph / Result Protection 等
    工程术语；详细 reason_code 仍保留在 Engineering View。
    """
    public = result.safe_runtime_result
    stop_stage = (
        public.get("stop_stage")
        if isinstance(public, dict)
        else None
    )
    reason_code = (
        public.get("reason_code")
        if isinstance(public, dict)
        else None
    )

    if stop_stage == "business_request_preflight":
        if reason_code == "ambiguous_performance_metric":
            st.info("需要补充一个评价指标后才能继续分析。")
        else:
            st.info("当前问题超出已启用的分析能力范围。")
    elif stop_stage == "dataset_availability":
        st.info("请求超出当前数据覆盖范围。")
    elif stop_stage == "analytics_planning":
        st.info("这个问题还需要补充信息后才能继续分析。")
    elif stop_stage == "finalization":
        st.warning("查询已执行，但当前结果没有形成可安全释放的业务交付。")
    else:
        st.warning("本次请求已安全停止，没有生成业务结果。")

    st.write(result.message)
    st.caption(
        "系统不会用占位数字、猜测结果或未受保护数据补齐答案。"
    )

    _render_business_clarification_v1()


def _submit_business_clarification_choice_v1(
    *,
    pending: PendingBusinessClarificationV1,
    choice_id: str,
) -> None:
    resolution = resolve_business_clarification_v1(
        pending=pending,
        choice_id=choice_id,
    )

    _clear_pending_business_clarification_v1()

    _submit_investigation(
        resolution.resolved_question,
        original_question=(
            resolution.original_question
        ),
        resolution_note=(
            f"评价指标："
            f"{resolution.selected_display_label}"
        ),
        clarification_resolution=resolution,
    )


def _render_business_clarification_v1() -> None:
    pending = _pending_business_clarification_v1()

    if pending is None:
        return

    st.markdown("#### 选择评价指标")
    st.caption(
        "选择只补齐本次问题缺失的指标口径；"
        "随后仍会重新进入完整受治理查询链。"
    )

    columns = st.columns(
        len(pending.choices)
    )

    for column, choice in zip(
        columns,
        pending.choices,
        strict=True,
    ):
        with column:
            if st.button(
                choice.display_label,
                key=(
                    "business_clarification::"
                    f"{choice.choice_id}"
                ),
                type="secondary",
                width="stretch",
            ):
                _submit_business_clarification_choice_v1(
                    pending=pending,
                    choice_id=choice.choice_id,
                )
                st.rerun()


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


def _render_priority_assessment_v1(
    result: RuntimeDeliveryBridgeResultV2,
) -> None:
    """
    展示 Delivery 已经形成的 F03 调查优先候选。

    页面不从 Breakdown rows 自行做业务优先级判断。
    """
    view = result.console_view

    if (
        view is None
        or view.priority_assessment is None
    ):
        return

    priority = view.priority_assessment
    metric_label = format_metric_name_v2(
        priority.metric_name
    )
    value_label = format_business_metric_value_v2(
        priority.metric_name,
        priority.candidate_value,
    )
    members = "、".join(
        priority.candidate_member_labels
    )

    st.markdown("### 核心判断")

    if priority.is_tie:
        st.success(
            "按当前已批准的退款率异常筛查规则，"
            f"优先调查候选并列为 **{members}**，"
            f"{metric_label}均为 **{value_label}**。"
        )
    else:
        st.success(
            "按当前已批准的退款率异常筛查规则，"
            f"优先调查候选是 **{members}**，"
            f"{metric_label}为 **{value_label}**。"
        )

    st.caption(
        "这里给出的是“调查优先候选”，不是最终业务优先级；"
        "结论直接绑定当前 Protected Result Evidence。"
    )

    left, right = st.columns(2)

    with left:
        st.markdown("#### 目前可以确认")
        for item in priority.can_confirm:
            st.markdown(
                f"- {format_statement_v2(item)}"
            )

    with right:
        st.markdown("#### 目前不能确认")
        for item in priority.cannot_confirm:
            st.markdown(
                f"- {format_statement_v2(item)}"
            )

    st.markdown("#### 下一步需要补充的证据")
    for item in priority.next_evidence_needed:
        st.markdown(
            f"- {format_statement_v2(item)}"
        )

    st.caption(
        "证据状态：部分充分。调查优先候选来自已注册的"
        "确定性筛查规则；工程级标识保留在工程视图。"
    )


def _render_ranking_conclusion_v1(
    result: RuntimeDeliveryBridgeResultV2,
) -> None:
    """
    只展示 Delivery 已经形成的 Ranking Conclusion。

    Streamlit 不从 Breakdown rows 自己做 max/min。
    """
    view = result.console_view

    if view is None or view.ranking_conclusion is None:
        return

    ranking = view.ranking_conclusion
    metric_label = format_metric_name_v2(
        ranking.metric_name
    )
    grain_label = format_result_grain_name_v2(
        ranking.result_grain
    )
    value_label = format_business_metric_value_v2(
        ranking.metric_name,
        ranking.winning_value,
    )

    intent_label = {
        "best": "表现最好",
        "worst": "表现最弱",
        "highest": f"{metric_label}最高",
        "lowest": f"{metric_label}最低",
    }[ranking.ranking_intent.value]

    members = "、".join(
        ranking.winning_member_labels
    )

    if ranking.is_tie:
        sentence = (
            f"按 {metric_label} 看，在当前已释放的受保护{grain_label}"
            f"结果中，{intent_label}的{grain_label}并列为 "
            f"**{members}**，{metric_label}均为 **{value_label}**。"
        )
    else:
        sentence = (
            f"按 {metric_label} 看，在当前已释放的受保护{grain_label}"
            f"结果中，{intent_label}的{grain_label}是 "
            f"**{members}**，{metric_label}为 **{value_label}**。"
        )

    st.markdown("### 核心结论")
    st.success(sentence)
    st.caption(
        "该结论直接绑定当前 Protected Result Evidence；"
        "页面没有重新查询数据库，也没有自行重算排名。"
    )


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


def _render_fact_verification_v2(
    result: RuntimeDeliveryBridgeResultV2,
) -> None:
    """
    FACT / Comparison Seed 的业务验证入口统一使用 Dialog。

    Business View 不直接展示 Evidence ID / Query Plan / Audit Event；
    工程级 Provenance 保留在工程视图。
    """

    view = result.console_view
    if view is None:
        return

    if view.comparison is not None:
        target = "comparison"
        label = (
            "验证整体比较基线"
            if result.requested_analysis_mode
            == AnalysisModeV2.INVESTIGATION
            else "验证这次比较"
        )
    else:
        target = "fact"
        label = "验证这个数字"

    if st.button(
        label,
        key=(
            "open_primary_business_verification::"
            f"{result.requested_analysis_mode.value}"
        ),
        type="secondary",
    ):
        _render_business_verification_dialog_v2(
            target
        )



def _render_fact_delivery_business(
    result: RuntimeDeliveryBridgeResultV2,
) -> None:
    """
    Fact Business View 只回答“事实是什么”。

    不在默认页面重复渲染：
    - Executive Brief confirmed facts；
    - Key Findings；
    - 完整 Effective Scope；
    - 工程型 Evidence 元数据。

    分析结论留给 Composition / Comparison / Diagnostic；
    Trust 细节集中进入“验证这个数字”。
    """

    view = result.console_view

    if view is None:
        st.error("READY Runtime 缺少 Console View。")
        return

    if view.fact_metric is not None:
        st.markdown("### 核心答案")
        st.metric(
            format_metric_name_v2(
                view.fact_metric.metric_name
            ),
            format_business_metric_value_v2(
                view.fact_metric.metric_name,
                view.fact_metric.value,
            ),
        )
        st.caption(
            "分析窗口："
            f"{view.fact_metric.analysis_window.start_date} → "
            f"{view.fact_metric.analysis_window.end_date}"
        )

    if view.priority_assessment is not None:
        _render_priority_assessment_v1(result)
    else:
        _render_ranking_conclusion_v1(result)

    if (
        view.comparison is None
        and view.fact_metric is None
        and view.ranking_conclusion is None
        and view.priority_assessment is None
    ):
        st.info(
            "当前事实型交付没有满足安全单值投影合同的 KPI；"
            "仅展示已释放的受保护业务明细。"
        )

    _render_breakdown(result)
    _render_fact_verification_v2(result)


def _render_comparison_seed_business_v2(
    result: RuntimeDeliveryBridgeResultV2,
) -> None:
    """
    Generic Comparison Seed 的业务交付。

    Runtime 已经形成可信 Overall Comparison；
    UI 必须先把 reference/current/delta/time window 展示出来，
    再进入后续 Agentic Investigation。
    """

    view = result.console_view

    if (
        view is None
        or view.comparison is None
    ):
        st.error(
            "Comparison Seed 已标记 READY，"
            "但缺少可展示的 Comparison View。"
        )
        return

    comparison = view.comparison
    metric_label = format_metric_name_v2(
        comparison.metric_name
    )
    reference_label, current_label = (
        _business_period_pair_v2(comparison)
    )

    if comparison.absolute_change > 0:
        direction_label = "增长"
    elif comparison.absolute_change < 0:
        direction_label = "下降"
    else:
        direction_label = "持平"

    relative = format_percentage_v2(
        comparison.relative_change
    )

    st.markdown("### 核心结论")

    st.success(
        f"**{current_label}** {metric_label} 为 "
        f"**{format_number_v2(comparison.current_value)}**，"
        f"**{reference_label}** 为 "
        f"**{format_number_v2(comparison.reference_value)}**；"
        f"{current_label}较{reference_label}"
        f"{direction_label} "
        f"**{format_number_v2(abs(comparison.absolute_change))}**"
        + (
            f"（{relative}）"
            if relative is not None
            else ""
        )
        + "。"
    )

    st.caption(
        "参考期："
        f"{comparison.reference_window.start_date} → "
        f"{comparison.reference_window.end_date} ｜ "
        "当前期："
        f"{comparison.current_window.start_date} → "
        f"{comparison.current_window.end_date}"
    )

    left, right = st.columns(2)

    with left:
        st.metric(
            f"{reference_label} {metric_label}",
            format_number_v2(
                comparison.reference_value
            ),
        )

    with right:
        st.metric(
            f"{current_label} {metric_label}",
            format_number_v2(
                comparison.current_value
            ),
        )

    left, right = st.columns(2)

    with left:
        st.metric(
            "变化额",
            format_number_v2(
                comparison.absolute_change
            ),
        )

    with right:
        st.metric(
            "变化率",
            relative if relative is not None else "未定义",
        )

    if (
        result.requested_analysis_mode
        == AnalysisModeV2.INVESTIGATION
    ):
        st.info(
            "以上是本次深入调查的可信整体比较基线。"
            "后续调查必须继承这组参考期 / 当前期，"
            "不能用单期拆分替代原问题答案。"
        )
    else:
        st.info(
            "以上是本次比较分析的可信整体结果。"
            "当前请求不会被静默升级为深入调查。"
        )

    _render_fact_verification_v2(result)

def _contribution_member_by_key(
    contribution,
) -> dict[str, object]:
    return {
        member.member_key: member
        for member in contribution.members
    }


def _render_contribution_business_summary(view) -> None:
    contribution = view.contribution

    st.markdown("### 渠道变化贡献与验证")

    if contribution is None:
        st.info("当前没有可展示的渠道变化贡献结果。")
        return

    comparison = view.comparison
    if comparison is not None:
        reference_label, current_label = (
            _business_period_pair_v2(comparison)
        )
        st.caption(
            f"比较周期：{reference_label} → {current_label}"
        )

    rows = build_contribution_display_rows_v2(contribution)
    chart_rows = build_contribution_chart_rows_v2(contribution)

    left, right = st.columns((1.55, 1.0))

    with left:
        st.dataframe(
            rows,
            width="stretch",
            hide_index=True,
        )

    with right:
        if chart_rows:
            chart_df = pd.DataFrame(chart_rows).set_index("渠道")
            st.bar_chart(
                chart_df,
                width="stretch",
            )
        else:
            st.info("当前没有非零渠道变化额可用于绘图。")

    by_key = _contribution_member_by_key(contribution)

    findings: list[str] = []

    if contribution.negative_change_ranking:
        key = contribution.negative_change_ranking[0]
        member = by_key[key]
        findings.append(
            "最大负向变化渠道："
            f"{member.member_label}，"
            f"变化 {format_number_v2(member.delta)}，"
            "占整体 GMV 净变化 "
            f"{format_percentage_v2(member.contribution_rate)}。"
        )

    if contribution.positive_change_ranking:
        key = contribution.positive_change_ranking[0]
        member = by_key[key]
        findings.append(
            "最大正向变化渠道："
            f"{member.member_label}，"
            f"变化 +{format_number_v2(member.delta)}，"
            "占整体 GMV 净变化 "
            f"{format_percentage_v2(member.contribution_rate)}。"
        )

    if findings:
        st.markdown("**变化摘要**")
        for item in findings:
            st.write(item)

    if contribution.reconciliation_status.value == "reconciled":
        st.success(
            "各渠道变化额合计与整体 GMV 变化额一致。"
        )
    else:
        st.warning(
            "各渠道变化额合计与整体 GMV 变化额尚未完全一致；"
            "当前渠道结果不能视为完整数值解释。"
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




def _render_f02_compound_comparison_business_v1(
    result: RuntimeDeliveryBridgeResultV2,
) -> None:
    """F02 Business View：比较结果 → 调查建议 → 渠道变化验证。"""
    view = result.console_view

    if (
        view is None
        or view.comparison is None
        or view.contribution is None
    ):
        st.error(
            "F02 READY Delivery 缺少 Comparison / Contribution View。"
        )
        return

    comparison = view.comparison

    st.markdown("### 核心结论")

    if comparison.absolute_change < 0:
        direction_label = "下降"
    elif comparison.absolute_change > 0:
        direction_label = "增长"
    else:
        direction_label = "持平"

    relative = format_percentage_v2(
        comparison.relative_change
    )

    reference_label, current_label = (
        _business_period_pair_v2(comparison)
    )

    st.success(
        f"**{current_label}** GMV 为 "
        f"**{format_number_v2(comparison.current_value)}**，"
        f"**{reference_label}** 为 "
        f"**{format_number_v2(comparison.reference_value)}**；"
        f"{current_label}较{reference_label}"
        f"{direction_label} "
        f"**{format_number_v2(abs(comparison.absolute_change))}**"
        + (
            f"（{relative}）"
            if relative is not None
            else ""
        )
        + "。"
    )

    st.caption(
        f"比较周期：{reference_label} → {current_label}"
    )

    recommendation = (
        view.contribution_investigation_recommendation
    )
    route_recommendation = (
        view.contribution_investigation_route_recommendation
    )

    st.markdown("### 继续调查建议")

    if route_recommendation is not None:
        assessment = route_recommendation.pattern_assessment
        route = route_recommendation.route

        st.info(route_recommendation.recommendation_summary)

        scope_label = (
            "保持当前分析范围"
            if route.scope_strategy.value == "keep_requested_scope"
            else f"收窄到 {route.focus_member_label}"
        )
        next_dimension_label = {
            "category": "品类变化",
            "geography": "地区变化",
        }[route.next_dimension.value]

        st.write(
            f"**系统推荐路径：** {scope_label} → {next_dimension_label}"
        )

        left, right = st.columns(2)

        with left:
            st.markdown("#### 当前可以确认")
            for item in route_recommendation.can_confirm:
                st.markdown(
                    f"- {format_statement_v2(item)}"
                )

        with right:
            st.markdown("#### 当前不能确认")
            for item in route_recommendation.cannot_confirm:
                st.markdown(
                    f"- {format_statement_v2(item)}"
                )

    elif recommendation is None:
        st.info(
            "当前比较与渠道变化已经形成，"
            "但现有证据不足以安全生成下一步调查建议。"
        )
    else:
        st.info(
            "当前仍使用兼容调查建议："
            f"{recommendation.member_label}。"
        )

    _render_contribution_business_summary(view)

    if view.verification is not None:
        if st.button(
            "验证本次分析",
            key="open_f02_verification",
            type="secondary",
        ):
            _render_business_verification_dialog_v2(
                "comparison"
            )


def _periodic_metric_lookup_v2(
    report: PeriodicBusinessReportV2,
) -> dict[str, object]:
    return {
        item.spec.metric_name: item
        for item in report.metrics
    }


def _render_periodic_metric_card_v2(
    *,
    snapshot,
) -> None:
    """
    Periodic KPI 的双周期卡片。

    信息层级：
    1. 当前期可信值；
    2. 当前值右侧显示变化幅度；
    3. 下一行以更弱视觉层级显示参考期；
    4. NOT_READY 明确显示不可释放，不补 0。
    """

    current_value = format_periodic_metric_value_v2(snapshot)
    reference_value = format_periodic_metric_value_v2(
        snapshot,
        reference=True,
    )
    delta = format_periodic_metric_delta_inline_v2(snapshot)
    direction = periodic_metric_delta_direction_v2(snapshot)

    delta_class = {
        "up": "dc-kpi-delta-up",
        "down": "dc-kpi-delta-down",
        "neutral": "dc-kpi-delta-neutral",
        "unavailable": "dc-kpi-delta-neutral",
    }[direction]

    unavailable_class = (
        " dc-kpi-unavailable"
        if snapshot.status != PeriodicMetricStatusV2.READY
        else ""
    )

    delta_html = (
        (
            '<span class="dc-kpi-delta '
            f'{delta_class}">{escape(delta)}</span>'
        )
        if delta is not None
        else ""
    )

    note_html = ""

    if snapshot.status != PeriodicMetricStatusV2.READY:
        note_html = (
            '<div class="dc-kpi-note">'
            "受治理结果当前不可安全释放"
            "</div>"
        )

    card_html = (
        f'<div class="dc-kpi-card{unavailable_class}">'
        f'<div class="dc-kpi-label">'
        f'{escape(snapshot.spec.chinese_name)}'
        "</div>"
        '<div class="dc-kpi-current-row">'
        f'<span class="dc-kpi-current">{escape(str(current_value))}</span>'
        f"{delta_html}"
        "</div>"
        '<div class="dc-kpi-reference">'
        "参考期&nbsp;&nbsp;"
        f'<span class="dc-kpi-reference-value">'
        f'{escape(str(reference_value))}'
        "</span>"
        "</div>"
        f"{note_html}"
        "</div>"
    )

    st.markdown(
        card_html,
        unsafe_allow_html=True,
    )


def _render_periodic_business_report_v2(
    report: PeriodicBusinessReportV2,
    *,
    cadence: PeriodicReportCadenceV2,
) -> None:
    """
    B5A Multi-KPI Periodic Business Report 主业务视图。

    UI 只消费 PeriodicBusinessReportV2 已经完成的可信投影，
    不重算 KPI、delta、ratio 或 driver reconciliation。
    """

    st.markdown(
        f"### {_periodic_cadence_label_v2(cadence)}经营概览"
    )

    st.caption(
        "参考期："
        f"{report.comparison.reference_window.start_date} → "
        f"{report.comparison.reference_window.end_date} ｜ "
        "当前期："
        f"{report.comparison.current_window.start_date} → "
        f"{report.comparison.current_window.end_date}"
    )

    if report.status == PeriodicBusinessReportStatusV2.NOT_READY:
        st.error(report.message)
    elif (
        report.status
        == PeriodicBusinessReportStatusV2.PARTIAL_READY
    ):
        st.warning(
            "核心经营指标已形成可信交付；"
            "部分扩展指标当前不可交付。"
            "具体原因请查看对应指标或模块的状态说明。"
        )
    else:
        st.success("本期已注册经营指标全部形成可信交付。")

    st.caption(
        "报表状态："
        f"{format_periodic_report_status_v2(report.status)}"
    )

    lookup = _periodic_metric_lookup_v2(report)

    overview_names = (
        "gmv",
        "buyer_count",
        "spending_per_buyer",
        "refund_rate",
    )
    overview_columns = st.columns(4)

    for column, metric_name in zip(
        overview_columns,
        overview_names,
        strict=True,
    ):
        snapshot = lookup.get(metric_name)
        if snapshot is None:
            continue

        with column:
            _render_periodic_metric_card_v2(
                snapshot=snapshot
            )

    failed_optional = [
        item
        for item in report.metrics
        if (
            item.status != PeriodicMetricStatusV2.READY
            and not item.spec.required
            and item.spec.metric_name
            not in R12_PERIODIC_METRIC_NAMES_V2
        )
    ]

    if failed_optional:
        with st.expander(
            "查看本期不可释放的扩展指标",
            expanded=False,
        ):
            for item in failed_optional:
                st.write(
                    f"**{item.spec.chinese_name}**："
                    f"{item.message}"
                )

    st.markdown("### 销售驱动")

    sales_names = (
        "order_count",
        "units_sold",
        "aus",
        "purchase_frequency",
        "ipt",
    )

    first_row = st.columns(3)

    for column, metric_name in zip(
        first_row,
        sales_names[:3],
        strict=True,
    ):
        snapshot = lookup.get(metric_name)
        if snapshot is None:
            continue
        with column:
            _render_periodic_metric_card_v2(
                snapshot=snapshot
            )

    second_row = st.columns(2)

    for column, metric_name in zip(
        second_row,
        sales_names[3:],
        strict=True,
    ):
        snapshot = lookup.get(metric_name)
        if snapshot is None:
            continue
        with column:
            _render_periodic_metric_card_v2(
                snapshot=snapshot
            )

    st.markdown("#### 驱动关系验证")

    for reconciliation in report.driver_reconciliations:
        if (
            reconciliation.status
            == PeriodicDriverReconciliationStatusV2.RECONCILED
        ):
            st.success(
                f"{reconciliation.relationship}｜已对账"
            )
        elif (
            reconciliation.status
            == PeriodicDriverReconciliationStatusV2.NOT_RECONCILED
        ):
            st.warning(
                f"{reconciliation.relationship}｜未完全对账"
            )
        else:
            st.info(
                f"{reconciliation.relationship}｜当前不可验证"
            )

    st.caption(
        "这些关系是确定性算术核对，不代表因果解释。"
    )

    st.markdown("### 客户健康")

    st.markdown("#### 本期客户行为")

    customer_names = (
        "repeat_customer_rate",
        "member_gmv_share",
    )
    customer_columns = st.columns(2)

    for column, metric_name in zip(
        customer_columns,
        customer_names,
        strict=True,
    ):
        snapshot = lookup.get(metric_name)
        if snapshot is None:
            continue

        with column:
            _render_periodic_metric_card_v2(
                snapshot=snapshot
            )

    st.caption(
        "“窗口内跨日复购率”只描述当前报表窗口内的跨日重复购买；"
        "“会员 GMV 贡献率”使用支付时点会员身份。"
        "它们与下面的 R12 Cohort 指标不是同一个业务定义。"
    )

    st.markdown("#### R12 客户留存")

    r12_trust = report.r12_customer_health

    if r12_trust is None:
        st.info(
            "当前 Periodic Report 合同没有 R12 Customer Health "
            "Trust Projection；页面不会自行计算 R12 Base。"
        )
    else:
        r12_status_text = (
            format_periodic_r12_runtime_status_v2(
                r12_trust.status.value
            )
        )

        if r12_trust.status.value == "ready":
            st.success(r12_status_text)
        elif r12_trust.status.value == "partial_ready":
            st.warning(r12_status_text)
        else:
            st.info(r12_status_text)

        st.caption(
            "R12 回购率 = 报表期前完整 12 个日历月 Base 客户中，"
            "在当前报表窗口再次发生 Effective Purchase 的客户占比。"
            "它不是“窗口内跨日复购率”。"
        )

        r12_names = (
            "r12_base_customer_count",
            "r12_repurchase_customer_count",
            "r12_repurchase_rate",
            "r12_repurchase_amount",
            "r12_repurchase_spending",
        )

        first_r12_row = st.columns(3)

        for column, metric_name in zip(
            first_r12_row,
            r12_names[:3],
            strict=True,
        ):
            snapshot = lookup.get(metric_name)
            if snapshot is None:
                continue

            with column:
                _render_periodic_metric_card_v2(
                    snapshot=snapshot
                )

        second_r12_row = st.columns(2)

        for column, metric_name in zip(
            second_r12_row,
            r12_names[3:],
            strict=True,
        ):
            snapshot = lookup.get(metric_name)
            if snapshot is None:
                continue

            with column:
                _render_periodic_metric_card_v2(
                    snapshot=snapshot
                )

        if r12_trust.status.value != "ready":
            st.caption(
                "R12 指标不可用时不会用较短历史、未完成退款观察"
                "或占位数字补齐。"
            )

        if st.button(
            "验证 R12 客户指标",
            key="open_periodic_r12_verification",
            type="secondary",
        ):
            _render_business_verification_dialog_v2(
                "periodic_r12"
            )

    if st.button(
        "验证这份周期报表",
        key="open_periodic_report_verification",
        type="secondary",
    ):
        _render_business_verification_dialog_v2(
            "periodic"
        )


def _render_periodic_channel_extension_v2(
    result: MonthlyContributionDeliveryResultV2,
    *,
    cadence: PeriodicReportCadenceV2,
) -> None:
    """
    B4 渠道变化贡献作为 Multi-KPI Periodic Report 的扩展模块。

    不再重复渲染 Overall GMV KPI，避免页面出现两套主答案。
    """

    st.markdown("### 渠道变化贡献")

    if (
        result.status
        not in {
            MonthlyContributionDeliveryStatusV2.READY,
            MonthlyContributionDeliveryStatusV2.PARTIAL_READY,
        }
        or result.console_view is None
        or result.console_view.comparison is None
    ):
        st.info(
            "本期渠道变化贡献没有形成可释放 Delivery。"
        )
        return

    view = result.console_view

    if (
        result.status
        == MonthlyContributionDeliveryStatusV2.PARTIAL_READY
    ):
        st.info(
            "Overall 比较已形成，但渠道 Breakdown 触发 Result Protection；"
            "系统不会据此生成不完整的 Contribution。"
        )
        return

    _render_contribution_business_summary(view)


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
            "当前期 GMV",
            format_number_v2(comparison.current_value),
        )
    with c2:
        st.metric(
            "参考期 GMV",
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
        "参考期："
        f"{comparison.reference_window.start_date} → "
        f"{comparison.reference_window.end_date} ｜ "
        "当前期："
        f"{comparison.current_window.start_date} → "
        f"{comparison.current_window.end_date}"
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

    if view.breakdown is not None:
        with st.expander("查看当前期渠道 Protected Result"):
            breakdown_rows = build_display_rows_v2(
                view.breakdown.rows
            )
            st.dataframe(
                breakdown_rows,
                width="stretch",
                hide_index=True,
            )
            st.caption(
                "这是当前期 Channel ProtectedResult 的安全投影；"
                "主要业务比较请以上方参考期 / 当前期 Contribution 表为准。"
            )

    if view.verification is not None:
        if st.button(
            "验证这次周期比较",
            key="open_periodic_contribution_verification",
            type="secondary",
        ):
            _render_business_verification_dialog_v2(
                "periodic_contribution"
            )


def _composition_dimension_label_v2(
    dimension: FactCompositionDimensionV2,
    *,
    metric_name: str | None = None,
) -> str:
    """
    Business-facing Composition labels.

    “人 / 货 / 场”只属于架构讨论；正式产品统一使用业务名称。
    PEOPLE 当前不在 Business View 公开释放，但保留稳定标签，
    避免历史技术快照被误读。
    """

    return {
        FactCompositionDimensionV2.PEOPLE: "人群构成",
        FactCompositionDimensionV2.CATEGORY: "品类构成",
        FactCompositionDimensionV2.CHANNEL: "渠道构成",
        FactCompositionDimensionV2.REGION: "地区构成",
    }[dimension]



def _render_fact_composition_result_v2(
    result: FactCompositionResultV2,
) -> None:
    st.markdown(
        f"#### {_composition_dimension_label_v2(result.dimension, metric_name=result.metric_name)}"
    )

    if result.status != FactCompositionStatusV2.READY:
        st.warning(result.message)
        return

    rows = build_fact_composition_display_rows_v2(result)
    chart_rows = build_fact_composition_chart_rows_v2(result)

    left, right = st.columns((1.25, 1.0))

    with left:
        st.dataframe(
            rows,
            width="stretch",
            hide_index=True,
        )

    with right:
        if chart_rows:
            chart_df = pd.DataFrame(
                chart_rows
            ).set_index("成员")
            st.bar_chart(
                chart_df,
                width="stretch",
            )

    metric_label = format_metric_name_v2(
        result.metric_name
    )

    if result.members and result.ranking_summary_enabled:
        top = result.members[0]
        top_share = (
            format_percentage_v2(top.share)
            if top.share is not None
            else "未定义"
        )
        top_n_share = (
            format_percentage_v2(result.top_n_share)
            if result.top_n_share is not None
            else "未定义"
        )

        st.write(
            f"最大构成成员：**{top.member_label}**，"
            f"{metric_label} "
            f"{format_fact_metric_value_v2(result.metric_name, top.value)}，"
            f"占 Overall {top_share}。"
        )
        st.write(
            f"Top {result.top_n} 合计占比："
            f"**{top_n_share}**。"
        )
    elif (
        result.members
        and result.metric_name == "order_count"
        and result.dimension == FactCompositionDimensionV2.PEOPLE
    ):
        st.caption(
            "客户构成按固定业务层级展示："
            "老客铂金 → 黄金 → 白银 → 青铜 → 非会员 → 新客；"
            "不按订单数动态排序。"
        )

    if (
        result.reconciliation_status
        == FactCompositionReconciliationStatusV2.RECONCILED
    ):
        st.success(
            f"构成合计与可信 Overall {metric_label} "
            "已完成 Reconciliation。"
        )
    else:
        st.warning(
            f"构成合计与可信 Overall {metric_label} 未完全对账；"
            "不能把当前可见构成视为完整解释。"
        )

    st.caption(
        f"可信 Overall {metric_label}："
        f"{format_fact_metric_value_v2(result.metric_name, result.overall_value)} ｜ "
        "构成合计："
        f"{format_fact_metric_value_v2(result.metric_name, result.member_sum)} ｜ "
        "未解释差额："
        f"{format_fact_metric_value_v2(result.metric_name, result.unexplained_remainder)}"
    )

    st.caption(
        "完整成员列表来自 Result Protection 后的 Protected Result；"
        "Share 与 Reconciliation 在 Delivery 层基于可信 Overall 计算，"
        "Streamlit 不重新求和。"
    )


def _render_fact_composition_cross_check_v2(
    results: dict[str, FactCompositionResultV2],
) -> None:
    """
    Business cross-dimensional verification。

    PEOPLE 的正式业务语义仍在校准，因此不进入公开业务核对。
    技术快照可以继续保留在内部合同中。
    """

    ready = [
        result
        for result in results.values()
        if (
            result.status
            == FactCompositionStatusV2.READY
            and result.dimension
            != FactCompositionDimensionV2.PEOPLE
        )
    ]

    if len(ready) < 2:
        return

    st.markdown("#### 跨维度验证")

    verification_rows = [
        {
            "验证路径": _composition_dimension_label_v2(
                result.dimension,
                metric_name=result.metric_name,
            ),
            "指标": format_metric_name_v2(
                result.metric_name
            ),
            "构成合计": format_fact_metric_value_v2(
                result.metric_name,
                result.member_sum,
            ),
            "可信 Overall": format_fact_metric_value_v2(
                result.metric_name,
                result.overall_value,
            ),
            "状态": (
                "已对账"
                if (
                    result.reconciliation_status
                    == FactCompositionReconciliationStatusV2.RECONCILED
                )
                else "未完全对账"
            ),
        }
        for result in ready
    ]

    st.dataframe(
        verification_rows,
        width="stretch",
        hide_index=True,
    )

    if all(
        result.reconciliation_status
        == FactCompositionReconciliationStatusV2.RECONCILED
        for result in ready
    ):
        st.success(
            "当前已从多个独立、可加业务维度反向验证同一个 Overall 指标。"
        )



def _render_fact_composition_section_v2(
    seed: RuntimeDeliveryBridgeResultV2,
) -> None:
    """
    Business-facing Composition capability surface.

    底层 registry 可以保留 legacy PEOPLE capability，
    但在 Customer Lifecycle × Pre-window Membership Snapshot
    业务合同完成前，PEOPLE 不进入公开产品。
    """

    available = tuple(
        dimension
        for dimension in (
            fact_composition_available_dimensions_v2(
                seed
            )
        )
        if (
            dimension
            != FactCompositionDimensionV2.PEOPLE
        )
    )

    if not available:
        return

    st.markdown("### 进一步了解｜构成与验证")

    seed_metric_name = (
        seed.console_view.fact_metric.metric_name
        if (
            seed.console_view is not None
            and seed.console_view.fact_metric is not None
        )
        else None
    )

    st.caption(
        "这里只展示已经通过业务语义验收、"
        "且可以加总回可信 Overall 的构成维度。"
        "人群构成仍在口径校准中，当前暂不提供。"
    )

    columns = st.columns(len(available))

    for column, dimension in zip(
        columns,
        available,
        strict=True,
    ):
        with column:
            if st.button(
                (
                    "查看"
                    f"{_composition_dimension_label_v2(dimension, metric_name=seed_metric_name)}"
                ),
                key=f"fact_composition::{dimension.value}",
                type="secondary",
                width="stretch",
            ):
                _submit_fact_composition_v2(
                    dimension=dimension
                )
                st.rerun()

    results = _fact_composition_results_v2()

    for dimension in available:
        result = results.get(
            dimension.value
        )
        if result is not None:
            _render_fact_composition_result_v2(
                result
            )

    _render_fact_composition_cross_check_v2(
        results
    )



def _render_business_view() -> None:
    st.markdown("## 业务决策视图")

    request = st.session_state.get("entry_request")
    if request is None:
        st.info("请先从上方入口提交一个业务问题或周期报表请求。")
        return

    _render_entry_summary(request)

    if request.entry_mode == DecisionConsoleEntryModeV2.PERIODIC_REPORT:
        report = _periodic_business_report_result_v2()

        if report is None:
            failure = _periodic_business_report_failure_v2()

            if failure is None:
                st.info(
                    "当前还没有 Multi-KPI Periodic Business Report。"
                )
            else:
                st.error(
                    "周期经营报表未形成可交付结果；"
                    "页面不会用旧单指标结果冒充完整经营报表。"
                )
                st.write("失败阶段：", failure["failure_stage"])
                st.write("异常类型：", failure["exception_type"])
                st.caption(
                    "诊断 ID："
                    f'{failure["diagnostic_id"]}'
                )
            return

        _render_periodic_business_report_v2(
            report,
            cadence=request.report_cadence,
        )


        _render_periodic_report_export_v2(report)
        return

    result = _runtime_result()
    if result is None:
        st.info("当前还没有真实 Runtime Delivery。")
        return

    if result.status != RuntimeDeliveryBridgeStatusV2.READY:
        _render_runtime_failure(result)
        return

    if (
        result.requested_analysis_mode
        != AnalysisModeV2.FACT
    ):
        st.caption(
            "请求分析模式："
            f"{_analysis_mode_label_v2(result.requested_analysis_mode)}"
        )

    if (
        result.console_view is not None
        and result.console_view.comparison is not None
        and result.console_view.contribution is not None
    ):
        _render_f02_compound_comparison_business_v1(
            result
        )

        if analysis_mode_allows_agentic_v2(
            result.requested_analysis_mode
        ):
            _render_agentic_business_section()

        _render_investigation_report_export_v2()
        return

    if (
        isinstance(result.safe_runtime_result, dict)
        and result.safe_runtime_result.get("orchestration")
        == "comparison_seed_then_investigation_v2"
    ):
        _render_comparison_seed_business_v2(
            result
        )

        if analysis_mode_allows_agentic_v2(
            result.requested_analysis_mode
        ):
            _render_agentic_business_section()

        _render_investigation_report_export_v2()
        return

    _render_fact_delivery_business(result)

    if (
        result.requested_analysis_mode
        == AnalysisModeV2.FACT
    ):
        _render_fact_composition_section_v2(result)
    elif analysis_mode_allows_agentic_v2(
        result.requested_analysis_mode
    ):
        _render_agentic_business_section()
    else:
        st.caption(
            "当前请求不会被静默升级为 Agentic Investigation。"
        )

    _render_investigation_report_export_v2()



def _render_business_scope_projection_v2(
    delivery: FocusedChangeBreakdownDeliveryV2,
) -> None:
    scope = delivery.business_scope

    if scope is None:
        return

    st.markdown("**分析范围**")
    st.caption(
        f"渠道范围：{scope.channel_summary}"
    )
    st.caption(
        f"地区范围：{scope.geography_summary}"
    )
    st.caption(
        "详细成员放在独立验证弹窗中，主业务页面不再平铺完整范围。"
    )


def _render_focused_change_breakdown_v2(
    delivery: FocusedChangeBreakdownDeliveryV2,
    *,
    show_assessment: bool = True,
) -> None:
    """
    Business View 的两期 Change Breakdown。

    结论与 Scope Projection 均由 Delivery 层提供；
    Streamlit 不重新计算 concentration，也不解析 scope codes。
    """

    result = delivery.result

    dimension_label = {
        "channel": "渠道",
        "category": "品类",
        "region": "城市",
        "area": "大区",
        "province": "省级地区",
        "city": "城市",
        "campaign": "活动实例",
    }[result.dimension_name.value]

    is_overall = (
        delivery.scope_kind == ChangeBreakdownScopeKindV2.OVERALL
    )

    if is_overall:
        st.markdown(
            f"**全局｜{dimension_label}变化分解**"
        )
        share_label = "占整体GMV增量"
    else:
        st.markdown(
            f"**{result.focus_member_label}｜{dimension_label}变化分解**"
        )
        share_label = "占焦点GMV增量"

    seed = _runtime_result()
    if (
        seed is not None
        and seed.console_view is not None
        and seed.console_view.comparison is not None
    ):
        comparison = seed.console_view.comparison
        st.caption(
            "参考期："
            f"{comparison.reference_window.start_date} → "
            f"{comparison.reference_window.end_date} ｜ "
            "当前期："
            f"{comparison.current_window.start_date} → "
            f"{comparison.current_window.end_date}"
        )

    _render_business_scope_projection_v2(delivery)

    focus_change_word = (
        "减少"
        if result.focus_delta < 0
        else "增加"
    )

    if is_overall:
        st.write(
            "整体 GMV 从 "
            f"**{format_number_v2(result.reference_focus_value)}** "
            "变为 "
            f"**{format_number_v2(result.current_focus_value)}**，"
            f"{focus_change_word} "
            f"**{format_number_v2(abs(result.focus_delta))}**。"
            f"下面展示各{dimension_label}对整体变化额的数值贡献。"
        )
    else:
        st.write(
            f"{result.focus_member_label} GMV 从 "
            f"**{format_number_v2(result.reference_focus_value)}** "
            "变为 "
            f"**{format_number_v2(result.current_focus_value)}**，"
            f"{focus_change_word} "
            f"**{format_number_v2(abs(result.focus_delta))}**。"
            f"下面展示各{dimension_label}对该变化额的数值贡献。"
        )

    by_key = {
        member.member_key: member
        for member in result.members
    }

    if result.focus_delta < 0:
        ranked_keys = (
            *result.negative_change_ranking,
            *result.positive_change_ranking,
        )
    else:
        ranked_keys = (
            *result.positive_change_ranking,
            *result.negative_change_ranking,
        )

    ranked_key_set = set(ranked_keys)
    neutral_keys = tuple(
        member.member_key
        for member in result.members
        if member.member_key not in ranked_key_set
    )

    ordered_members = tuple(
        by_key[key]
        for key in (
            *ranked_keys,
            *neutral_keys,
        )
    )

    rows = [
        {
            dimension_label: member.member_label,
            "参考期 GMV": format_number_v2(
                member.reference_value
            ),
            "当前期 GMV": format_number_v2(
                member.current_value
            ),
            "变化额": format_number_v2(
                member.delta
            ),
            share_label: (
                format_percentage_v2(
                    member.share_of_focus_delta
                )
                if member.share_of_focus_delta is not None
                else "未定义"
            ),
        }
        for member in ordered_members
    ]

    st.dataframe(
        rows,
        width="stretch",
        hide_index=True,
    )

    reconciliation_subject = (
        "整体 GMV"
        if is_overall
        else f"{result.focus_member_label} GMV"
    )

    if result.reconciliation_status.value == "reconciled":
        st.success(
            f"{dimension_label}变化额合计与"
            f"{reconciliation_subject}变化额一致。"
        )
    else:
        st.warning(
            f"{dimension_label}变化额合计与"
            f"{reconciliation_subject}变化额尚未完全一致；"
            "当前结果不能视为完整数值解释。"
        )

    assessment = delivery.assessment
    if show_assessment and assessment is not None:
        st.markdown("#### 本轮结论")
        st.success(assessment.conclusion)

        left, right = st.columns(2)
        with left:
            st.markdown("**可以确认**")
            for item in assessment.can_confirm:
                st.markdown(f"- {item}")
        with right:
            st.markdown("**仍不能确认**")
            for item in assessment.cannot_confirm:
                st.markdown(f"- {item}")

    st.caption(
        f"“{share_label}”描述数值变化来源，不等于业务因果原因。"
    )


def _investigation_step_source_label_v2(
    sequence_number: int,
) -> str:
    if (
        sequence_number == 1
        and _agentic_initial_decision_owner_v2() == "user"
    ):
        return "你选择的方向"
    return "系统规划的方向"


def _render_agentic_business_results(view) -> None:
    """Business View 只展示业务结果、结论与可验证数据。"""

    if not view.investigation_results:
        return

    st.markdown("#### 调查结果")

    column_labels = {
        "channel_name": "渠道",
        "region_group": "大区",
        "province_name": "省级地区",
        "region_name": "城市",
        "category_name": "品类",
        "category": "品类",
        "gmv": "GMV",
        "order_count": "订单数",
        "refund_rate": "退款率",
        "roi": "ROI",
    }

    for result in view.investigation_results:
        action_label = _investigation_action_label_v1(
            result.selected_action_id
        )

        st.markdown(
            f"**第 {result.sequence_number} 步｜{action_label}**"
        )
        st.caption(
            f"方向来源：{_investigation_step_source_label_v2(result.sequence_number)}"
        )

        breakdown = result.breakdown
        focused_change = (
            _focused_change_result_for_action_v2(
                result.selected_action_id
            )
        )

        if focused_change is not None:
            _render_focused_change_breakdown_v2(
                focused_change
            )

            if breakdown is not None:
                if st.button(
                    "验证本轮数据",
                    key=(
                        "open_step_verification::"
                        f"{result.sequence_number}::"
                        f"{result.selected_action_id}"
                    ),
                    type="secondary",
                ):
                    _render_business_verification_dialog_v2(
                        f"step::{result.selected_action_id}"
                    )
            continue

        if breakdown is None:
            st.info("本步骤没有可展示的业务结果。")
            continue

        rows = [
            {
                column_labels.get(key, key): value
                for key, value in (
                    business_safe_breakdown_row_v2(
                        dict(row)
                    ).items()
                )
            }
            for row in breakdown.rows
        ]

        if rows:
            st.dataframe(
                rows,
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("本步骤没有可展示的数据行。")


def _system_route_business_label_v2(
    route_recommendation,
) -> str | None:
    if route_recommendation is None:
        return None

    route = route_recommendation.route
    scope_label = (
        "保持当前分析范围"
        if route.scope_strategy.value == "keep_requested_scope"
        else f"收窄到 {route.focus_member_label}"
    )
    dimension_label = {
        "category": "品类变化",
        "geography": "地区变化",
    }[route.next_dimension.value]
    return f"{scope_label} → {dimension_label}"


def _latest_step_assessment_v2():
    results = _focused_change_results_v2()
    if not results:
        return None
    return results[-1].assessment



def _latest_geography_change_v2() -> FocusedChangeBreakdownDeliveryV2 | None:
    for item in reversed(_focused_change_results_v2()):
        if item.result.dimension_name.value in {"area", "province", "city"}:
            return item
    return None


def _geography_level_from_change_v2(
    change: FocusedChangeBreakdownDeliveryV2,
) -> GeographyLevelV2:
    return {
        "area": GeographyLevelV2.AREA,
        "province": GeographyLevelV2.PROVINCE,
        "city": GeographyLevelV2.CITY,
    }[change.result.dimension_name.value]


def _geography_branch_decision_v2() -> GeographyBranchDecisionV2 | None:
    value = st.session_state.get("geography_branch_decision_v2")
    return value if isinstance(value, GeographyBranchDecisionV2) else None


def _geography_exploration_results_v2(
) -> tuple[FocusedChangeBreakdownDeliveryV2, ...]:
    """
    USER-owned Geography Exploration 的页面顺序历史。

    例如：
        PROVINCE -> CITY

    不能只保存 latest result，否则用户进入城市后会失去省级上下文。
    同一粒度若因页面生命周期被安全重写，则只保留最新一份，
    但不同粒度保持用户实际操作顺序。
    """

    value = st.session_state.get(
        "geography_exploration_results_v2",
        (),
    )

    if (
        isinstance(value, tuple)
        and all(
            isinstance(
                item,
                FocusedChangeBreakdownDeliveryV2,
            )
            for item in value
        )
    ):
        return value

    # 兼容此前只保存 latest result 的页面 Session。
    legacy = st.session_state.get(
        "geography_exploration_result_v2"
    )
    if isinstance(
        legacy,
        FocusedChangeBreakdownDeliveryV2,
    ):
        return (legacy,)

    return ()


def _geography_exploration_result_v2(
) -> FocusedChangeBreakdownDeliveryV2 | None:
    results = _geography_exploration_results_v2()
    return results[-1] if results else None


def _store_geography_exploration_result_v2(
    result: FocusedChangeBreakdownDeliveryV2,
) -> None:
    current = list(
        _geography_exploration_results_v2()
    )
    dimension = result.result.dimension_name

    current = [
        item
        for item in current
        if item.result.dimension_name != dimension
    ]
    current.append(result)

    st.session_state[
        "geography_exploration_results_v2"
    ] = tuple(current)

    # 新代码不再依赖 legacy single-result key。
    st.session_state.pop(
        "geography_exploration_result_v2",
        None,
    )


def _clear_geography_branch_ui_state_v2() -> None:
    st.session_state.pop("geography_branch_decision_v2", None)
    st.session_state.pop("geography_exploration_result_v2", None)
    st.session_state.pop("geography_exploration_results_v2", None)



def _user_investigation_domain_label_v2(
    domain: UserInvestigationDomainV2,
) -> str:
    return {
        UserInvestigationDomainV2.CATEGORY_PRODUCT: "商品 / 品类",
        UserInvestigationDomainV2.CHANNEL: "渠道",
        UserInvestigationDomainV2.GEOGRAPHY: "地区",
        UserInvestigationDomainV2.ACTIVITY_PROMOTION: "活动 / 促销",
        UserInvestigationDomainV2.AUDIENCE: "客户 / 人群",
        UserInvestigationDomainV2.MARKETING: "营销投入",
        UserInvestigationDomainV2.OTHER: "其他业务问题",
    }[domain]


def _user_analytical_intent_resolution_v2(
) -> BusinessAnalyticalIntentResolutionV2 | None:
    value = st.session_state.get(
        "user_analytical_intent_resolution_v2"
    )
    return (
        value
        if isinstance(
            value,
            BusinessAnalyticalIntentResolutionV2,
        )
        else None
    )


def _user_analytical_capability_resolution_v2(
) -> AnalyticalCapabilityResolutionV2 | None:
    value = st.session_state.get(
        "user_analytical_capability_resolution_v2"
    )
    return (
        value
        if isinstance(
            value,
            AnalyticalCapabilityResolutionV2,
        )
        else None
    )


def _user_analytical_path_decision_v2(
) -> UserAnalyticalPathDecisionV2 | None:
    value = st.session_state.get(
        "user_analytical_path_decision_v2"
    )
    return (
        value
        if isinstance(
            value,
            UserAnalyticalPathDecisionV2,
        )
        else None
    )


def _user_analytical_target_node_v2(
) -> AnalyticalPathNodeV2 | None:
    value = st.session_state.get(
        "user_analytical_target_node_v2"
    )
    return (
        value
        if isinstance(value, AnalyticalPathNodeV2)
        else None
    )


def _stored_completed_analytical_nodes_v2(
) -> tuple[AnalyticalPathNodeV2, ...]:
    value = st.session_state.get(
        "user_completed_analytical_nodes_v2",
        (),
    )

    if not isinstance(value, tuple):
        return ()

    if not all(
        isinstance(item, AnalyticalPathNodeV2)
        for item in value
    ):
        return ()

    return value


def _store_completed_analytical_node_v2(
    node: AnalyticalPathNodeV2,
) -> None:
    current = list(
        _stored_completed_analytical_nodes_v2()
    )

    signature = node.semantic_signature()

    current = [
        item
        for item in current
        if item.semantic_signature() != signature
    ]
    current.append(node)

    st.session_state[
        "user_completed_analytical_nodes_v2"
    ] = tuple(current)


def _analytical_comparison_key_v2(
    seed: RuntimeDeliveryBridgeResultV2,
) -> str | None:
    if (
        seed.delivery is None
        or seed.delivery.evidence_pack.analysis_scope.comparison
        is None
    ):
        return None

    comparison = (
        seed.delivery.evidence_pack.analysis_scope
        .comparison
    )

    return (
        f"{comparison.reference_window.start_date.isoformat()}"
        f"__{comparison.reference_window.end_date.isoformat()}"
        "__to__"
        f"{comparison.current_window.start_date.isoformat()}"
        f"__{comparison.current_window.end_date.isoformat()}"
    )


def _analytical_scope_fingerprint_v2(
    seed: RuntimeDeliveryBridgeResultV2,
) -> str:
    parts: list[str] = []

    if seed.delivery is not None:
        parts.append(
            seed.delivery.evidence_pack.analysis_scope
            .scope_summary
            or ""
        )

    if seed.requested_scope is not None:
        parts.append(
            seed.requested_scope.model_dump_json()
        )

    payload = "|".join(parts)

    return sha256(
        payload.encode("utf-8")
    ).hexdigest()[:20]


def _analytical_node_from_change_v2(
    *,
    change: FocusedChangeBreakdownDeliveryV2,
    seed: RuntimeDeliveryBridgeResultV2,
    node_id: str,
) -> AnalyticalPathNodeV2 | None:
    # 当前通用历史投影只自动登记 Overall 路径。
    # Member Focus 需要明确 source-grain contract，不能猜。
    if (
        change.scope_kind
        != ChangeBreakdownScopeKindV2.OVERALL
    ):
        return None

    mapping = {
        "channel": (
            UserInvestigationDomainV2.CHANNEL,
            AnalyticalGrainV2.CHANNEL,
        ),
        "category": (
            UserInvestigationDomainV2.CATEGORY_PRODUCT,
            AnalyticalGrainV2.CATEGORY,
        ),
        "area": (
            UserInvestigationDomainV2.GEOGRAPHY,
            AnalyticalGrainV2.AREA,
        ),
        "province": (
            UserInvestigationDomainV2.GEOGRAPHY,
            AnalyticalGrainV2.PROVINCE,
        ),
        "city": (
            UserInvestigationDomainV2.GEOGRAPHY,
            AnalyticalGrainV2.CITY,
        ),
        "campaign": (
            UserInvestigationDomainV2.ACTIVITY_PROMOTION,
            AnalyticalGrainV2.CAMPAIGN,
        ),
    }

    spec = mapping.get(
        change.result.dimension_name.value
    )

    if spec is None:
        return None

    return AnalyticalPathNodeV2(
        node_id=node_id,
        metric_name="gmv",
        domain=spec[0],
        operation=(
            AnalyticalOperationV2.CHANGE_BREAKDOWN
        ),
        grain=spec[1],
        comparison_key=(
            _analytical_comparison_key_v2(seed)
        ),
        scope_fingerprint=(
            _analytical_scope_fingerprint_v2(seed)
        ),
    )


def _completed_analytical_path_nodes_v2(
    seed: RuntimeDeliveryBridgeResultV2,
) -> tuple[AnalyticalPathNodeV2, ...]:
    """
    Build a safe semantic history from:
    - trusted Seed contribution;
    - completed Overall Focused Change;
    - explicit user-owned completed target nodes.

    This is not SQL lineage. It is only an Analytical Path semantic history.
    """

    nodes: list[AnalyticalPathNodeV2] = list(
        _stored_completed_analytical_nodes_v2()
    )

    comparison_key = _analytical_comparison_key_v2(
        seed
    )
    scope_fingerprint = (
        _analytical_scope_fingerprint_v2(seed)
    )

    if (
        seed.console_view is not None
        and seed.console_view.contribution is not None
    ):
        nodes.append(
            AnalyticalPathNodeV2(
                node_id="seed-channel-contribution",
                metric_name="gmv",
                domain=UserInvestigationDomainV2.CHANNEL,
                operation=(
                    AnalyticalOperationV2.CHANGE_BREAKDOWN
                ),
                grain=AnalyticalGrainV2.CHANNEL,
                comparison_key=comparison_key,
                scope_fingerprint=scope_fingerprint,
            )
        )

    for index, change in enumerate(
        _focused_change_results_v2(),
        start=1,
    ):
        node = _analytical_node_from_change_v2(
            change=change,
            seed=seed,
            node_id=f"focused-change-{index}",
        )
        if node is not None:
            nodes.append(node)

    exploration = _geography_exploration_result_v2()
    if exploration is not None:
        node = _analytical_node_from_change_v2(
            change=exploration,
            seed=seed,
            node_id="latest-geography-exploration",
        )
        if node is not None:
            nodes.append(node)

    unique: dict[
        tuple[object, ...],
        AnalyticalPathNodeV2,
    ] = {}

    for node in nodes:
        unique[node.semantic_signature()] = node

    return tuple(unique.values())


def _analytical_grain_to_geography_level_v2(
    grain: AnalyticalGrainV2,
) -> GeographyLevelV2:
    return {
        AnalyticalGrainV2.AREA: GeographyLevelV2.AREA,
        AnalyticalGrainV2.PROVINCE: GeographyLevelV2.PROVINCE,
        AnalyticalGrainV2.CITY: GeographyLevelV2.CITY,
    }[grain]


def _execute_user_analytical_investigation_v2(
    *,
    seed: RuntimeDeliveryBridgeResultV2,
    request,
    target_node: AnalyticalPathNodeV2,
    decision: UserAnalyticalPathDecisionV2,
) -> None:
    """
    Execute a USER-owned registered top-level analytical direction.

    若页面已经存在同一个 Investigation Session 且当前 STOP
    允许 continuation，则必须沿原 Session 继续，不能从 Seed
    重新开一个“新第 1 步”。

    这样同时保证：
    - 页面步骤顺序 = 用户真实操作顺序；
    - 已有 Evidence / completed actions / budget 不被重置；
    - 新选择仍由 server-owned available_actions 校验。
    """

    assert decision.action_id is not None

    def user_planner(state):
        return plan_user_selected_investigation_action_v2(
            state=state,
            action_id=decision.action_id,
            rationale=(
                "用户明确提出新的已注册 Analytical Target；"
                "系统只在 trusted available_actions 中执行该动作。"
            ),
        )

    previous = _agentic_result()
    continuation = _continuation_state()
    prior_stop_statuses = (
        _prior_continuation_stop_statuses()
    )

    with st.spinner(
        "正在验证分析路径并执行受治理查询..."
    ):
        try:
            if (
                previous is not None
                and previous.status
                == InvestigationDeliveryStatusV2.READY
                and previous.delivery is not None
                and continuation is not None
            ):
                runtime_step = (
                    continue_day89_agentic_investigation_step_v2(
                        delivery=previous.delivery,
                        continuation_state=continuation,
                        user_requested_continue=True,
                        planner=user_planner,
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
            else:
                runtime_step = (
                    run_day89_agentic_investigation_step_v2(
                        seed_result=seed,
                        reference_date=date.today(),
                        investigation_focus_scope=None,
                        investigation_route=None,
                        planner=user_planner,
                        include_category_action=True,
                        budget_policy=_agentic_budget_policy_v2(),
                        session_policy=_agentic_session_policy_v2(),
                    )
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
                "该 Analytical Target 当前无法沿现有受治理路径安全执行；"
                "系统不会重置已有调查，也不会自动改写成其他方向。"
            )
            st.code(f"{type(exc).__name__}: {exc}")
            return

    _clear_agentic_hitl_state()

    # 不再把后续 USER SWITCH 重写成新的“首轮”。
    # 若此前已有 Agentic Delivery，就保留原首轮来源；
    # 只有真正从 Seed 新开时才设置 owner。
    if previous is None:
        _set_agentic_initial_decision_owner_v2(
            "user"
        )

    st.session_state[
        "agentic_user_selected_action_v2"
    ] = decision.action_id
    st.session_state["agentic_delivery"] = delivered

    _store_focused_change_result_v2(
        runtime_step.focused_change_breakdown
    )
    _store_completed_analytical_node_v2(
        target_node
    )
    st.session_state[
        "user_analytical_execution_completed_v2"
    ] = target_node.node_id

    _clear_agentic_hitl_state()

    if (
        runtime_step.stop_status is not None
        and runtime_step.stop_status.can_continue
    ):
        continuation_kwargs = {
            "runtime_step": runtime_step,
        }

        if continuation is not None:
            continuation_kwargs[
                "prior_transitions"
            ] = continuation.prior_transitions

        next_continuation = (
            build_day89_continuation_state_v2(
                **continuation_kwargs
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
    else:
        st.session_state.pop(
            "agentic_continuation_state",
            None,
        )
        st.session_state.pop(
            "agentic_prior_continuation_stop_statuses",
            None,
        )

    _sync_active_history_investigation_snapshot_v1()

def _execute_user_geography_exploration_v2(
    *,
    seed: RuntimeDeliveryBridgeResultV2,
    target_node: AnalyticalPathNodeV2,
) -> None:
    level = _analytical_grain_to_geography_level_v2(
        target_node.grain
    )

    if level == GeographyLevelV2.AREA:
        raise ValueError(
            "AREA 是顶层 Investigation target，"
            "不应走 deeper Geography Exploration。"
        )

    with st.spinner(
        "正在执行用户主动探索（不计入调查预算）..."
    ):
        try:
            result = run_day93_geography_exploration_v2(
                seed_result=seed,
                level=level,
            )
        except GovernanceConfigurationError as exc:
            st.error("Governance Runtime 配置未准备好。")
            st.code(str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            st.error(
                "探索性地理查询未能安全完成；"
                "Investigation 结果与预算保持不变。"
            )
            st.code(f"{type(exc).__name__}: {exc}")
            return

    _store_geography_exploration_result_v2(
        result
    )
    _store_completed_analytical_node_v2(
        target_node
    )
    st.session_state[
        "user_analytical_execution_completed_v2"
    ] = target_node.node_id
    _sync_active_history_investigation_snapshot_v1()


def _submit_user_investigation_intent_v2(
    *,
    domain: UserInvestigationDomainV2,
    hypothesis: str | None,
    explicit_grain: AnalyticalGrainV2 | None = None,
) -> None:
    """
    USER intent production path:

    Business Semantic Intent
    -> Analytical Path Relation
    -> Capability
    -> Investigation / Exploration / Boundary / No-New-Evidence.

    Domain 本身不再直接等价于 action_id。
    """

    seed = _runtime_result()
    request = st.session_state.get(
        "entry_request"
    )

    if (
        seed is None
        or seed.status
        != RuntimeDeliveryBridgeStatusV2.READY
        or seed.delivery is None
    ):
        st.warning(
            "当前没有 READY Seed Delivery，不能启动自定义调查。"
        )
        return

    if (
        request is None
        or request.entry_mode
        != DecisionConsoleEntryModeV2.INVESTIGATION
    ):
        st.warning("当前入口不是 Investigation。")
        return

    clean_hypothesis = (
        hypothesis.strip()
        if isinstance(hypothesis, str)
        and hypothesis.strip()
        else None
    )

    # 修复 stale hypothesis：
    # 新提交为空时必须明确清除上一轮文本。
    if clean_hypothesis is None:
        st.session_state.pop(
            "user_investigation_hypothesis_v2",
            None,
        )
    else:
        st.session_state[
            "user_investigation_hypothesis_v2"
        ] = clean_hypothesis

    st.session_state[
        "user_analytical_submitted_domain_v2"
    ] = domain.value
    st.session_state.pop(
        "user_analytical_execution_completed_v2",
        None,
    )

    resolution = (
        resolve_business_analytical_intent_v2(
            BusinessAnalyticalIntentRequestV2(
                domain=domain,
                hypothesis=clean_hypothesis,
                explicit_grain=explicit_grain,
            )
        )
    )

    st.session_state[
        "user_analytical_intent_resolution_v2"
    ] = resolution

    for key in (
        "user_analytical_capability_resolution_v2",
        "user_analytical_path_decision_v2",
        "user_analytical_target_node_v2",
    ):
        st.session_state.pop(key, None)

    if (
        resolution.status
        != BusinessAnalyticalIntentStatusV2.RESOLVED
        or resolution.target is None
    ):
        return

    target = resolution.target

    target_node = materialize_analytical_path_node_v2(
        target=target,
        metric_name="gmv",
        comparison_key=(
            _analytical_comparison_key_v2(seed)
        ),
        scope_fingerprint=(
            _analytical_scope_fingerprint_v2(seed)
        ),
    )

    capability = resolve_analytical_capability_v2(
        target,
        metric_name="gmv",
    )

    decision = decide_user_analytical_path_v2(
        target=target_node,
        completed=(
            _completed_analytical_path_nodes_v2(
                seed
            )
        ),
        capability=capability,
    )

    st.session_state[
        "user_analytical_capability_resolution_v2"
    ] = capability
    st.session_state[
        "user_analytical_path_decision_v2"
    ] = decision
    st.session_state[
        "user_analytical_target_node_v2"
    ] = target_node

    if decision.execution_mode in {
        UserAnalyticalExecutionModeV2.NO_NEW_EVIDENCE,
        UserAnalyticalExecutionModeV2.HIERARCHY_STEP_REQUIRED,
        UserAnalyticalExecutionModeV2.CAPABILITY_BOUNDARY,
        UserAnalyticalExecutionModeV2.UNSUPPORTED,
    }:
        return

    if (
        decision.execution_mode
        == UserAnalyticalExecutionModeV2.INVESTIGATION
    ):
        _clear_geography_branch_ui_state_v2()
        _execute_user_analytical_investigation_v2(
            seed=seed,
            request=request,
            target_node=target_node,
            decision=decision,
        )
        return

    if (
        decision.execution_mode
        == UserAnalyticalExecutionModeV2.EXPLORATION
    ):
        if (
            target.domain
            != UserInvestigationDomainV2.GEOGRAPHY
        ):
            raise ValueError(
                "当前已注册 USER Exploration Runtime "
                "只支持 Geography deeper grain。"
            )

        _execute_user_geography_exploration_v2(
            seed=seed,
            target_node=target_node,
        )
        return

    raise ValueError(
        "Unsupported User Analytical Execution Mode: "
        f"{decision.execution_mode.value}"
    )


def _render_user_analytical_intent_result_v2(
    *,
    current_domain: UserInvestigationDomainV2,
) -> None:
    submitted = st.session_state.get(
        "user_analytical_submitted_domain_v2"
    )

    if (
        isinstance(submitted, str)
        and submitted != current_domain.value
    ):
        st.caption(
            "你已经切换了业务方向。请提交当前选择后，"
            "系统再判断新的分析意图；不会沿用上一方向的结果。"
        )
        return

    resolution = (
        _user_analytical_intent_resolution_v2()
    )

    if resolution is None:
        return

    st.markdown("**系统对本轮分析意图的理解**")

    hypothesis = st.session_state.get(
        "user_investigation_hypothesis_v2"
    )
    if (
        isinstance(hypothesis, str)
        and hypothesis.strip()
    ):
        st.write(hypothesis)

    if (
        resolution.status
        == BusinessAnalyticalIntentStatusV2.NEEDS_CLARIFICATION
    ):
        st.warning(resolution.message)
        st.caption(
            "请选择上方明确的分析层级 / 对象后重新提交："
        )
        st.write(
            "、".join(
                analytical_grain_label_v2(item)
                for item in resolution.clarification_grains
            )
        )
        return

    if (
        resolution.status
        == BusinessAnalyticalIntentStatusV2.DOMAIN_CONFLICT
    ):
        st.warning(resolution.message)

        if resolution.detected_domains:
            st.caption(
                "业务判断更接近："
                + "、".join(
                    _user_investigation_domain_label_v2(
                        item
                    )
                    for item in resolution.detected_domains
                )
            )

        st.caption(
            "系统不会偷偷切换 Tool。请确认本轮真正要验证的业务方向。"
        )
        return

    if (
        resolution.status
        == BusinessAnalyticalIntentStatusV2.UNSUPPORTED
        or resolution.target is None
    ):
        st.warning(resolution.message)
        return

    target = resolution.target
    st.success(
        "已理解为："
        f"**{analytical_target_business_label_v2(target)}**"
    )

    capability = (
        _user_analytical_capability_resolution_v2()
    )
    decision = _user_analytical_path_decision_v2()
    target_node = _user_analytical_target_node_v2()

    if capability is None or decision is None:
        return

    mode = decision.execution_mode

    if mode == UserAnalyticalExecutionModeV2.NO_NEW_EVIDENCE:
        st.info(
            "这次请求与已经完成的分析在指标、操作、粒度、"
            "Focus、比较周期和范围上完全相同。"
            "重复执行不会增加新证据，因此没有重新查询。"
        )
        return

    if (
        mode
        == UserAnalyticalExecutionModeV2.HIERARCHY_STEP_REQUIRED
    ):
        assert decision.next_required_grain is not None

        next_label = analytical_grain_label_v2(
            decision.next_required_grain
        )

        st.warning(
            "你要求的是合法的更细层级，但当前分析路径不能跳级。"
            f"下一层需要先查看 **{next_label}**。"
        )

        if st.button(
            f"先查看{next_label}（探索性）",
            key=(
                "analytical_required_step::"
                f"{decision.next_required_grain.value}"
            ),
            type="secondary",
        ):
            _submit_user_investigation_intent_v2(
                domain=UserInvestigationDomainV2.GEOGRAPHY,
                hypothesis=None,
                explicit_grain=(
                    decision.next_required_grain
                ),
            )
            st.rerun()

        return

    if (
        mode
        == UserAnalyticalExecutionModeV2.CAPABILITY_BOUNDARY
    ):
        st.warning(
            "系统已经理解你真正想看的分析对象，"
            "但当前对应的受治理执行能力尚未正式注册。"
        )
        st.caption(
            "不会因为现有能力里有相近 Query Plan，"
            "就自动降级成品类、地区或其他查询。"
        )
        return

    if mode == UserAnalyticalExecutionModeV2.UNSUPPORTED:
        st.warning(decision.detail)
        return

    execution_completed = (
        target_node is not None
        and st.session_state.get(
            "user_analytical_execution_completed_v2"
        )
        == target_node.node_id
    )

    if mode == UserAnalyticalExecutionModeV2.INVESTIGATION:
        if execution_completed:
            st.success(
                "已作为用户明确选择的新调查方向执行。"
            )
        st.caption(
            "这是 USER-owned bounded Investigation；"
            "它不是系统自动选择的根因方向。"
        )
        return

    if mode == UserAnalyticalExecutionModeV2.EXPLORATION:
        if execution_completed:
            st.warning(
                "以下结果属于用户主动探索，不代表系统推荐，"
                "也没有消耗 Investigation Budget。"
            )

        explorations = (
            _geography_exploration_results_v2()
        )

        if target_node is not None and explorations:
            current_dimension = (
                target_node.grain.value
            )

            for item in explorations:
                item_dimension = (
                    item.result.dimension_name.value
                )
                item_label = {
                    "province": "省级",
                    "city": "城市",
                }.get(
                    item_dimension,
                    item_dimension,
                )

                if item_dimension == current_dimension:
                    _render_focused_change_breakdown_v2(
                        item,
                        show_assessment=False,
                    )
                else:
                    with st.expander(
                        f"上一级探索结果｜{item_label}",
                        expanded=False,
                    ):
                        _render_focused_change_breakdown_v2(
                            item,
                            show_assessment=False,
                        )

            if (
                target_node.grain
                == AnalyticalGrainV2.PROVINCE
            ):
                st.markdown("**下一层：城市**")
                st.caption(
                    "省级之后可以继续探索城市；"
                    "进入城市后，省级结果仍会保留为可展开的上一级上下文。"
                )

                if st.button(
                    "继续探索城市",
                    key="analytical_explore_city",
                    type="secondary",
                ):
                    _submit_user_investigation_intent_v2(
                        domain=(
                            UserInvestigationDomainV2.GEOGRAPHY
                        ),
                        hypothesis=None,
                        explicit_grain=(
                            AnalyticalGrainV2.CITY
                        ),
                    )
                    st.rerun()

            elif (
                target_node.grain
                == AnalyticalGrainV2.CITY
            ):
                st.info(
                    "城市已经是当前 Geography Hierarchy 的叶子层级。"
                    "省级上下文仍保留在上方；"
                    "如需继续，请切换到品类、活动、客户或营销等业务方向。"
                )

        return


def _render_user_investigation_intent_controls_v2(
    *,
    key_prefix: str,
) -> None:
    domain = st.selectbox(
        "你想从哪个业务角度继续调查？",
        options=tuple(UserInvestigationDomainV2),
        format_func=_user_investigation_domain_label_v2,
        key=f"{key_prefix}::domain",
    )

    explicit_options = explicit_grain_options_v2(
        domain
    )

    explicit_grain = None

    if explicit_options:
        selection = st.selectbox(
            "本轮想看的分析层级 / 对象",
            options=(None, *explicit_options),
            format_func=(
                lambda item: (
                    "根据下方业务判断自动识别（需填写）"
                    if item is None
                    else analytical_grain_label_v2(item)
                )
            ),
            key=f"{key_prefix}::grain::{domain.value}",
        )
        explicit_grain = selection

    hypothesis = st.text_area(
        "你的业务判断 / 假设（可选）",
        placeholder=(
            "例如：我想看具体商品；"
            "我想看省级变化；"
            "我想比较新客和老客；"
            "我想看老客中的会员等级。"
        ),
        height=80,
        key=f"{key_prefix}::hypothesis",
    )

    semantic_hint_required = (
        bool(explicit_options)
        and explicit_grain is None
        and not hypothesis.strip()
    )

    if explicit_options and explicit_grain is None:
        st.caption(
            "当前选择的是“自动识别”。请在业务判断中说明你真正想看的"
            "对象，例如“我想看省级变化”。填写后可以直接点击提交，"
            "无需先按 Ctrl+Enter。系统不会仅凭“地区 / 商品 / 客户”等"
            "大类自行猜测分析粒度。"
        )

    # 不动态 disabled：
    # Streamlit 的 text_area 在输入尚未 commit 时，页面端 disabled 状态
    # 可能仍基于上一轮空值，导致用户已经输入文本却无法点击提交。
    # 让按钮始终可点，在 click 时使用本轮最新 widget value 做 fail-closed
    # 校验，既保留语义安全，又避免 Ctrl+Enter 的额外交互要求。
    if st.button(
        "提交我的调查意图",
        key=f"{key_prefix}::submit",
        type="secondary",
    ):
        if semantic_hint_required:
            st.warning(
                "当前使用自动识别，请先填写具体业务判断，"
                "例如“我想看省级变化”。"
            )
        else:
            _submit_user_investigation_intent_v2(
                domain=domain,
                hypothesis=hypothesis,
                explicit_grain=explicit_grain,
            )
            st.rerun()

    _render_user_analytical_intent_result_v2(
        current_domain=domain
    )

@st.dialog("验证分析", width="large")
def _render_business_verification_dialog_v2(
    target: str,
) -> None:
    """
    统一 Business Verification Dialog。

    业务用户只看时间 / Scope / Metric Definition /
    Evidence Sufficiency / Reconciliation 等可解释结果。
    Evidence identity / Query Plan / Audit Event 等工程级 Provenance
    留在工程视图。
    """

    if target == "fact":
        seed = _runtime_result()

        if seed is None or seed.console_view is None:
            st.info("当前没有可验证的事实结果。")
            return

        view = seed.console_view
        fact_metric = view.fact_metric

        st.markdown("#### 本次事实结果")

        if fact_metric is not None:
            st.metric(
                format_metric_name_v2(
                    fact_metric.metric_name
                ),
                format_business_metric_value_v2(
                    fact_metric.metric_name,
                    fact_metric.value,
                ),
            )
            st.write(
                "分析窗口：",
                (
                    f"{fact_metric.analysis_window.start_date}"
                    " → "
                    f"{fact_metric.analysis_window.end_date}"
                ),
            )

        metric = (
            seed.delivery.metric_definition
            if seed.delivery is not None
            else None
        )

        if metric is not None:
            st.markdown("#### 指标口径")
            st.write("指标：", metric.chinese_name)
            st.write("定义：", metric.definition)
            st.write("公式：", metric.formula)

        scope = build_business_scope_projection_v2(
            view.scope_summary
        )

        st.markdown("#### 分析范围")
        st.write("渠道：", scope.channel_summary)
        if scope.channel_member_labels:
            st.caption(
                "、".join(scope.channel_member_labels)
            )

        st.write("地区：", scope.geography_summary)
        if scope.geography_member_labels:
            st.caption(
                "、".join(scope.geography_member_labels)
            )

        st.write(
            "证据状态：",
            format_evidence_sufficiency_v2(
                view.evidence_sufficiency
            ),
        )

        compositions = tuple(
            item
            for item in (
                _fact_composition_results_v2().values()
            )
            if (
                item.dimension
                != FactCompositionDimensionV2.PEOPLE
            )
        )

        if compositions:
            st.markdown("#### 构成核对")

            rows = [
                {
                    "验证路径": _composition_dimension_label_v2(
                        item.dimension,
                        metric_name=item.metric_name,
                    ),
                    "构成合计": format_fact_metric_value_v2(
                        item.metric_name,
                        item.member_sum,
                    ),
                    "可信 Overall": format_fact_metric_value_v2(
                        item.metric_name,
                        item.overall_value,
                    ),
                    "未解释差额": format_fact_metric_value_v2(
                        item.metric_name,
                        item.unexplained_remainder,
                    ),
                    "状态": (
                        "已对账"
                        if (
                            item.reconciliation_status
                            == FactCompositionReconciliationStatusV2.RECONCILED
                        )
                        else "未完全对账"
                    ),
                }
                for item in compositions
            ]

            st.dataframe(
                rows,
                width="stretch",
                hide_index=True,
            )

        st.caption(
            "工程级 Provenance 标识保留在工程视图；"
            "业务验证窗口不展示内部标识或 raw data。"
        )
        return

    if target == "comparison":
        seed = _runtime_result()
        if (
            seed is None
            or seed.console_view is None
            or seed.console_view.comparison is None
        ):
            st.info("当前没有可验证的比较结果。")
            return

        view = seed.console_view
        comparison = view.comparison
        reference_label, current_label = (
            _business_period_pair_v2(comparison)
        )

        st.markdown("#### 本次比较")
        st.write(
            f"比较周期：{reference_label} → {current_label}"
        )

        metric = (
            seed.delivery.metric_definition
            if seed.delivery is not None
            else None
        )

        if metric is not None:
            st.write("指标：", metric.chinese_name)
            st.write("定义：", metric.definition)
            st.write("公式：", metric.formula)
        else:
            st.write(
                "指标：",
                format_metric_name_v2(
                    comparison.metric_name
                ),
            )

        left, right = st.columns(2)

        with left:
            st.metric(
                reference_label,
                format_number_v2(
                    comparison.reference_value
                ),
            )
            st.metric(
                "变化额",
                format_number_v2(
                    comparison.absolute_change
                ),
            )

        with right:
            st.metric(
                current_label,
                format_number_v2(
                    comparison.current_value
                ),
            )
            st.metric(
                "变化率",
                (
                    format_percentage_v2(
                        comparison.relative_change
                    )
                    or "未定义"
                ),
            )

        if view.contribution is not None:
            contribution = view.contribution

            st.markdown("#### 数值核对")
            left, right = st.columns(2)

            with left:
                st.metric(
                    "整体变化额",
                    format_number_v2(
                        contribution.overall_delta
                    ),
                )
                st.metric(
                    "未解释差额",
                    format_number_v2(
                        contribution.unexplained_remainder
                    ),
                )

            with right:
                st.metric(
                    "成员变化额合计",
                    format_number_v2(
                        contribution.sum_member_delta
                    ),
                )
                st.metric(
                    "核对状态",
                    (
                        "已对账"
                        if contribution.reconciliation_status.value
                        == "reconciled"
                        else "未完全对账"
                    ),
                )

        scope = build_business_scope_projection_v2(
            view.scope_summary
        )
        st.markdown("#### 分析范围")
        st.write("渠道：", scope.channel_summary)
        if scope.channel_member_labels:
            st.caption(
                "、".join(scope.channel_member_labels)
            )

        st.write("地区：", scope.geography_summary)
        if scope.geography_member_labels:
            st.caption(
                "、".join(scope.geography_member_labels)
            )

        st.write(
            "证据状态：",
            format_evidence_sufficiency_v2(
                view.evidence_sufficiency
            ),
        )

        st.caption(
            "工程级 Provenance 标识保留在工程视图；"
            "业务验证窗口只展示可解释的业务核对结果。"
        )
        return

    if target == "periodic":
        report = _periodic_business_report_result_v2()

        if report is None:
            st.info("当前没有可验证的周期经营报表。")
            return

        st.markdown("#### 本次周期报表")
        st.write(
            "周期：",
            _periodic_cadence_label_v2(
                report.cadence
            ),
        )
        st.write(
            "参考期：",
            (
                f"{report.comparison.reference_window.start_date}"
                " → "
                f"{report.comparison.reference_window.end_date}"
            ),
        )
        st.write(
            "当前期：",
            (
                f"{report.comparison.current_window.start_date}"
                " → "
                f"{report.comparison.current_window.end_date}"
            ),
        )

        rows = build_periodic_metric_comparison_rows_v2(
            report.metrics
        )
        st.dataframe(
            rows,
            width="stretch",
            hide_index=True,
        )

        if report.driver_reconciliations:
            st.markdown("#### 驱动关系核对")

            verification_rows = [
                {
                    "关系": item.relationship,
                    "状态": (
                        "已对账"
                        if (
                            item.status
                            == PeriodicDriverReconciliationStatusV2.RECONCILED
                        )
                        else (
                            "未完全对账"
                            if (
                                item.status
                                == PeriodicDriverReconciliationStatusV2.NOT_RECONCILED
                            )
                            else "当前不可验证"
                        )
                    ),
                    "未解释差额": (
                        str(item.remainder)
                        if item.remainder is not None
                        else "—"
                    ),
                }
                for item in report.driver_reconciliations
            ]

            st.dataframe(
                verification_rows,
                width="stretch",
                hide_index=True,
            )

        st.caption(
            "周期报表验证只展示业务指标与确定性核对；"
            "工程级 Provenance 标识保留在工程视图。"
        )
        return

    if target == "periodic_r12":
        report = _periodic_business_report_result_v2()

        if (
            report is None
            or report.r12_customer_health is None
        ):
            st.info("当前没有可验证的 R12 客户指标。")
            return

        r12_trust = report.r12_customer_health

        st.markdown("#### R12 Base / Readiness")

        readiness_rows = (
            build_periodic_r12_readiness_rows_v2(
                report
            )
        )

        if readiness_rows:
            st.dataframe(
                readiness_rows,
                width="stretch",
                hide_index=True,
            )

        st.write(
            "Current Readiness：",
            format_periodic_r12_readiness_status_v2(
                r12_trust.current_readiness.status.value
            ),
        )
        st.write(
            "Reference Readiness：",
            format_periodic_r12_readiness_status_v2(
                r12_trust.reference_readiness.status.value
            ),
        )

        reconciliation_rows = (
            build_periodic_r12_reconciliation_rows_v2(
                report
            )
        )

        st.markdown("#### 确定性关系验证")

        if reconciliation_rows:
            st.dataframe(
                reconciliation_rows,
                width="stretch",
                hide_index=True,
            )
        else:
            st.info(
                "当前没有可释放的 R12 Reconciliation。"
            )

        failed_r12 = [
            item
            for item in report.metrics
            if (
                item.spec.metric_name
                in R12_PERIODIC_METRIC_NAMES_V2
                and item.status
                != PeriodicMetricStatusV2.READY
            )
        ]

        if failed_r12:
            st.markdown("#### 当前不可交付的 R12 指标")
            for item in failed_r12:
                st.write(
                    f"{item.spec.chinese_name}："
                    f"{item.message}"
                )

        st.caption(
            "R12 Base、Readiness 与 Reconciliation "
            "直接来自 Runtime / Delivery Contract；"
            "页面不重新推导 Cohort。"
        )
        return

    if target == "periodic_contribution":
        periodic = _periodic_result()

        if (
            periodic is None
            or periodic.console_view is None
            or periodic.console_view.comparison is None
        ):
            st.info("当前没有可验证的周期渠道比较。")
            return

        view = periodic.console_view
        comparison = view.comparison

        st.markdown("#### 周期渠道比较")
        st.write(
            "参考期：",
            (
                f"{comparison.reference_window.start_date}"
                " → "
                f"{comparison.reference_window.end_date}"
            ),
        )
        st.write(
            "当前期：",
            (
                f"{comparison.current_window.start_date}"
                " → "
                f"{comparison.current_window.end_date}"
            ),
        )

        if view.contribution is not None:
            contribution = view.contribution

            left, right = st.columns(2)
            with left:
                st.metric(
                    "整体变化额",
                    format_number_v2(
                        contribution.overall_delta
                    ),
                )
                st.metric(
                    "未解释差额",
                    format_number_v2(
                        contribution.unexplained_remainder
                    ),
                )

            with right:
                st.metric(
                    "渠道变化额合计",
                    format_number_v2(
                        contribution.sum_member_delta
                    ),
                )
                st.metric(
                    "核对状态",
                    (
                        "已对账"
                        if contribution.reconciliation_status.value
                        == "reconciled"
                        else "未完全对账"
                    ),
                )

        st.caption(
            "工程级 Provenance 标识保留在工程视图。"
        )
        return

    if target.startswith("step::"):
        action_id = target.split("::", 1)[1]
        change = _focused_change_result_for_action_v2(
            action_id
        )

        if change is None:
            st.info("当前步骤没有可验证的两期变化结果。")
            return

        result = change.result
        st.markdown("#### 本轮数值核对")

        left, right = st.columns(2)

        with left:
            st.metric(
                "基准变化额",
                format_number_v2(result.focus_delta),
            )
            st.metric(
                "未解释差额",
                format_number_v2(result.unexplained_remainder),
            )

        with right:
            st.metric(
                "成员变化额合计",
                format_number_v2(result.sum_member_delta),
            )
            st.metric(
                "核对状态",
                (
                    "已对账"
                    if result.reconciliation_status.value
                    == "reconciled"
                    else "未完全对账"
                ),
            )

        scope = change.business_scope
        if scope is not None:
            st.markdown("#### 分析范围")
            st.write("渠道：", scope.channel_summary)
            if scope.channel_member_labels:
                st.caption(
                    "、".join(scope.channel_member_labels)
                )

            st.write("地区：", scope.geography_summary)
            if scope.geography_member_labels:
                st.caption(
                    "、".join(scope.geography_member_labels)
                )

        agentic = _agentic_result()
        if (
            agentic is not None
            and agentic.console_view is not None
        ):
            for item in agentic.console_view.investigation_results:
                if item.selected_action_id != action_id:
                    continue
                if item.breakdown is None:
                    break

                column_labels = {
                    "channel_name": "渠道",
                    "region_group": "大区",
                    "province_name": "省级地区",
                    "region_name": "城市",
                    "category_name": "品类",
                    "category": "品类",
                    "gmv": "GMV",
                }
                rows = [
                    {
                        column_labels.get(key, key): value
                        for key, value in (
                            business_safe_breakdown_row_v2(
                                dict(row)
                            ).items()
                        )
                    }
                    for row in item.breakdown.rows
                ]

                if rows:
                    st.markdown("#### 当前期受保护结果")
                    st.dataframe(
                        rows,
                        width="stretch",
                        hide_index=True,
                    )
                break

        return

    st.info("当前没有匹配的业务验证目标。")



def _render_agentic_business_section() -> None:
    """Business View：系统建议、用户调查意图、证据状态与 HITL。"""

    agentic = _agentic_result()

    st.markdown("### 受控深入调查")

    seed = _runtime_result()
    route_recommendation = None

    if seed is not None and seed.console_view is not None:
        route_recommendation = (
            seed.console_view
            .contribution_investigation_route_recommendation
        )

    if agentic is None:
        if route_recommendation is not None:
            route_label = _system_route_business_label_v2(
                route_recommendation
            )
            st.info(
                "系统建议："
                f"**{route_label}**。"
            )

        start_mode = st.radio(
            "你希望如何继续？",
            options=(
                "按系统建议继续调查",
                "我有自己的调查想法",
            ),
            horizontal=True,
            key="agentic_start_mode",
        )

        if start_mode == "我有自己的调查想法":
            st.caption(
                "你的业务意图不再受系统推荐 Action 列表限制；"
                "系统会单独判断当前是否存在对应的受治理能力。"
            )
            _render_user_investigation_intent_controls_v2(
                key_prefix="initial_user_intent"
            )
            return

        st.caption(
            "系统会在已注册、授权且与当前证据一致的调查路线中"
            "执行一步；不会自动连续消耗预算。"
        )

        if st.button(
            "按系统建议开始",
            key="run_agentic_investigation",
            type="secondary",
        ):
            _submit_agentic_investigation()

            if _agentic_result() is not None:
                st.rerun()
        return

    if agentic.status not in {
        InvestigationDeliveryStatusV2.READY,
        InvestigationDeliveryStatusV2.CLARIFICATION_READY,
    }:
        st.warning("深入调查没有形成可展示结果。")
        st.write(agentic.message)
        return

    view = agentic.console_view
    if view is None:
        st.error("深入调查缺少可展示结果。")
        return

    # 旧 Clarification Delivery 仅保留兼容恢复能力；
    # 新 Business UI 不再把它作为“用户自定义调查”的默认入口。
    if view.clarification is not None:
        st.warning(
            "当前存在旧版受控澄清状态。"
            "请完成该状态后再继续，或重新提交业务问题。"
        )
        return

    owner = _agentic_initial_decision_owner_v2()
    system_route_label = _system_route_business_label_v2(
        route_recommendation
    )

    if owner == "user":
        selected_action = _agentic_user_selected_action_v2()
        selected_label = (
            _investigation_action_label_v1(selected_action)
            if selected_action is not None
            else "用户业务调查意图"
        )

        st.caption(
            f"首轮方向来源：用户｜{selected_label}"
        )
        if system_route_label is not None:
            st.caption(
                f"系统原建议：{system_route_label}"
            )
    elif system_route_label is not None:
        st.caption(
            f"首轮方向来源：系统｜{system_route_label}"
        )

    st.caption(
        f"已完成调查步骤：{len(view.investigation_trace)}"
    )

    _render_agentic_business_results(view)
    st.caption(
        "完整技术证据链可在工程视图中查看。"
    )

    control = view.runtime_control
    assessment = _latest_step_assessment_v2()

    evidence_status = assess_investigation_evidence_sufficiency_v2(
        steps_used=len(view.investigation_trace),
        assessment=assessment,
        has_legal_next_action=(
            control.can_continue
            if control is not None
            else False
        ),
        explicit_evidence_sufficient=(
            control.evidence_sufficient
            if control is not None
            else False
        ),
        policy=_agentic_budget_extension_policy_v2(),
    )

    if evidence_status.status == InvestigationEvidenceSufficiencyV2.CONCLUSIVE:
        st.success("当前证据已经满足本次调查结论标准。")
    elif evidence_status.status == InvestigationEvidenceSufficiencyV2.DIRECTIONAL:
        # Day93 Human Calibration：
        # “数值变化结构已经很清楚”与“业务因果已经得到证明”
        # 是两个不同结论层级，不能用一个“方向性”句子混在一起。
        if assessment is not None:
            st.success(
                "数值分解层面已经形成较明确的方向："
                "本轮变化额已完成核对，并识别出主要数值变化来源。"
            )

        if (
            assessment is not None
            and assessment.dimension_name
            == FocusedChangeDimensionV2.CAMPAIGN
        ):
            st.warning(
                "业务原因层面仍未确认：当前结果说明 GMV 净变化"
                "主要集中在双十一等活动归因订单中，"
                "但没有反事实或实验对照，不能据此认定活动"
                "造成了对应增量。"
            )
        else:
            st.warning(
                "业务原因层面仍未确认：当前结果说明变化主要发生"
                "在哪个业务切面，不等于已经证明为什么发生。"
            )
    elif (
        evidence_status.status
        == InvestigationEvidenceSufficiencyV2.INCONCLUSIVE_ACTIONABLE
    ):
        st.warning(
            "当前数值变化结构还不足以形成稳定调查结论，"
            "但已有可继续验证的受治理方向。"
        )
    else:
        st.warning(
            "当前受治理调查能力无法继续形成新的证据。"
        )

    if evidence_status.next_action_recommendation is not None:
        st.markdown("#### 下一步建议")
        st.info(evidence_status.next_action_recommendation)

    if (
        control is not None
        and control.can_continue
    ):
        remaining_labels = [
            _investigation_action_label_v1(action_id)
            for action_id in control.uninvestigated_action_ids
        ]

        if remaining_labels:
            st.caption(
                "当前已注册的剩余方向："
                + "、".join(remaining_labels)
            )

        button_label = "继续调查"
        if evidence_status.extension_recommended:
            button_label = (
                "继续调查"
                f"（建议最多再追加 "
                f"{evidence_status.suggested_additional_steps} 步）"
            )

        if st.button(
            button_label,
            key="continue_agentic_investigation",
            type="primary",
        ):
            _submit_agentic_continuation()
            st.rerun()
    else:
        if evidence_status.status != InvestigationEvidenceSufficiencyV2.CONCLUSIVE:
            st.caption(
                "当前已注册的自动调查步骤已用完；"
                "这不等于业务原因已经得到证明。"
            )

    with st.expander(
        "我还有自己的调查想法",
        expanded=False,
    ):
        st.caption(
            "你可以提出活动、客户、人群、营销等业务假设。"
            "如果当前能力尚未注册，系统会明确说明，而不会"
            "自动改写成已有的品类 / 地区查询。"
        )
        _render_user_investigation_intent_controls_v2(
            key_prefix="followup_user_intent"
        )


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
            f"{_investigation_action_label_v1(step.selected_action_id)}"
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
                    _investigation_action_label_v1(
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
        entry_label = (
            "周期报表"
            if request.entry_mode
            == DecisionConsoleEntryModeV2.PERIODIC_REPORT
            else "业务问题"
        )
        st.caption(f"入口类型：{entry_label}")
        with st.expander("查看内部入口合同 Payload"):
            st.json(request.model_dump(mode="json"))

    if (
        request is not None
        and request.entry_mode
        == DecisionConsoleEntryModeV2.PERIODIC_REPORT
    ):
        business_report = _periodic_business_report_result_v2()

        if business_report is not None:
            st.metric(
                "Multi-KPI 报表状态",
                business_report.status.value,
            )
            st.caption(
                f"READY={business_report.ready_metric_count} ｜ "
                f"FAILED={business_report.failed_metric_count}"
            )

            with st.expander("查看 Multi-KPI 安全摘要"):
                st.json(
                    {
                        "contract_version": (
                            business_report.contract_version
                        ),
                        "cadence": business_report.cadence.value,
                        "anchor_date": (
                            business_report.anchor_date.isoformat()
                        ),
                        "ready_metric_count": (
                            business_report.ready_metric_count
                        ),
                        "failed_metric_count": (
                            business_report.failed_metric_count
                        ),
                        "required_failed_metric_names": list(
                            business_report.required_failed_metric_names
                        ),
                        "driver_reconciliations": [
                            {
                                "relationship": item.relationship,
                                "status": item.status.value,
                            }
                            for item in (
                                business_report.driver_reconciliations
                            )
                        ],
                        "r12_customer_health": (
                            {
                                "status": (
                                    business_report
                                    .r12_customer_health.status.value
                                ),
                                "ready_metric_count": (
                                    business_report
                                    .r12_customer_health
                                    .ready_metric_count
                                ),
                                "failed_metric_count": (
                                    business_report
                                    .r12_customer_health
                                    .failed_metric_count
                                ),
                                "current_readiness": (
                                    business_report
                                    .r12_customer_health
                                    .current_readiness.status.value
                                ),
                                "reference_readiness": (
                                    business_report
                                    .r12_customer_health
                                    .reference_readiness.status.value
                                ),
                                "reconciliations": [
                                    {
                                        "relationship": item.relationship,
                                        "status": item.status.value,
                                    }
                                    for item in (
                                        business_report
                                        .r12_customer_health
                                        .reconciliations
                                    )
                                ],
                            }
                            if (
                                business_report.r12_customer_health
                                is not None
                            )
                            else None
                        ),
                    }
                )

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

            if business_report is not None:
                st.caption(
                    "Multi-KPI 主报表已形成；"
                    "当前仅缺少 B4 Contribution 扩展。"
                )
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

    status_col, mode_col = st.columns(2)

    with status_col:
        st.metric(
            "运行时交付状态",
            format_runtime_status_v2(result.status.value),
        )

    with mode_col:
        st.metric(
            "请求分析模式",
            _analysis_mode_label_v2(
                result.requested_analysis_mode
            ),
        )

    with st.expander("查看 Safe Runtime Result"):
        st.json(result.safe_runtime_result)

    _render_active_analysis_evidence_lineage_v1()

    st.caption(
        "工程视图只显示 Governed Graph 的 safe public summary；"
        "不显示 raw SQL、SQL parameters 或 raw database rows。"
    )


def _submit_fact_composition_v2(
    *,
    dimension: FactCompositionDimensionV2,
) -> None:
    seed = _runtime_result()

    if seed is None:
        st.warning("当前没有 READY Fact Seed。")
        return

    with st.spinner(
        "正在沿用可信时间窗与 Requested Scope "
        "执行 Governed Composition Query..."
    ):
        try:
            result = run_day93_fact_composition_v2(
                seed_result=seed,
                dimension=dimension,
            )
        except GovernanceConfigurationError as exc:
            st.error("Governance Runtime 配置未准备好。")
            st.code(str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            st.error(
                "构成查询发生未预期错误；"
                "原 Fact Delivery 保持不变。"
            )
            st.code(f"{type(exc).__name__}: {exc}")
            return

    current = _fact_composition_results_v2()
    current[dimension.value] = result
    st.session_state["fact_composition_results"] = current
    _sync_active_history_auxiliary_snapshots_v1()


def _submit_investigation(
    question: str,
    *,
    original_question: str | None = None,
    resolution_note: str | None = None,
    parent_history_id: str | None = None,
    clarification_resolution: (
        BusinessClarificationResolutionV1 | None
    ) = None,
) -> None:
    try:
        request = _build_investigation_request(question)
    except ValidationError as exc:
        st.error("入口请求未通过合同校验。")
        st.code(str(exc))
        return

    display_question = (
        original_question
        if (
            isinstance(original_question, str)
            and original_question.strip()
        )
        else request.question
    )

    st.session_state["entry_request"] = request
    st.session_state["entry_display_question"] = display_question

    if (
        isinstance(resolution_note, str)
        and resolution_note.strip()
    ):
        st.session_state["entry_resolution_note"] = resolution_note
    else:
        st.session_state.pop(
            "entry_resolution_note",
            None,
        )

    st.session_state.pop("runtime_delivery", None)
    st.session_state.pop("agentic_delivery", None)
    _clear_focused_change_results_v2()
    _clear_fact_composition_state_v2()
    _clear_agentic_hitl_state()
    _clear_agentic_decision_context_v2()
    _clear_pending_business_clarification_v1()
    _deactivate_analysis_history_v1()

    with st.spinner("正在执行 Governed Analytics → Result Protection → Evidence Delivery..."):
        try:
            if clarification_resolution is not None:
                result = (
                    run_day93_business_clarification_continuation_v1(
                        resolution=clarification_resolution,
                    )
                )
            else:
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
    st.session_state.pop("periodic_business_report", None)
    st.session_state.pop("periodic_business_report_failure", None)
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

    if result.status != RuntimeDeliveryBridgeStatusV2.READY:
        pending = build_pending_business_clarification_v1(
            original_question=display_question,
            runtime_result=result,
            reference_date=date.today(),
        )

        if pending is not None:
            st.session_state[
                "pending_business_clarification_v1"
            ] = pending

        return

    history_item = build_analysis_history_item_v1(
        original_question=display_question,
        resolved_question=(
            request.question
            if request.question != display_question
            else None
        ),
        resolution_note=resolution_note,
        parent_history_id=parent_history_id,
        runtime_delivery=result,
        breakdown_summary=_breakdown_summary_result(),
        fact_compositions=tuple(
            _fact_composition_results_v2().values()
        ),
    )

    history = _analysis_session_history_v1()

    appended_history = append_analysis_history_item_v1(
        session=history,
        item=history_item,
    )
    active_history = activate_analysis_history_item_v1(
        session=appended_history,
        history_id=history_item.history_id,
    )

    # 新 READY 分析必须立即成为 active history。
    # 否则上一条历史仍保持 active：
    # - 旧条目的“回到此分析”会错误禁用；
    # - 更严重的是下面的 Investigation Snapshot 可能写到旧 history_id。
    _store_analysis_session_history_v1(
        active_history
    )
    _sync_active_history_investigation_snapshot_v1()

    # Sidebar History 在当前脚本 run 中先于入口表单渲染。
    # 如果这里不主动 rerun，本轮页面仍显示提交前的 active_history，
    # 看起来就会像“旧分析仍然不可回到”，直到下一次交互触发重跑。
    st.rerun()


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

    if not analysis_mode_allows_agentic_v2(
        seed.requested_analysis_mode
    ):
        st.warning(
            "当前问题没有被识别为诊断或决策调查，"
            "不会启动 Agentic Investigation。"
        )
        return

    try:
        investigation_focus_scope = (
            _build_seed_investigation_focus_scope_v1(seed)
        )
    except ValueError as exc:
        st.error(
            "系统已经给出渠道调查建议，但无法把该建议安全绑定到"
            "唯一渠道代码；为避免退回全渠道，本次深入调查已停止。"
        )
        st.code(f"{type(exc).__name__}: {exc}")
        return

    with st.spinner(
        "正在根据当前证据执行下一步调查..."
    ):
        try:
            route_recommendation = (
                seed.console_view
                .contribution_investigation_route_recommendation
                if seed.console_view is not None
                else None
            )

            runtime_step = run_day89_agentic_investigation_step_v2(
                seed_result=seed,
                reference_date=date.today(),
                investigation_focus_scope=investigation_focus_scope,
                investigation_route=(
                    route_recommendation.route
                    if route_recommendation is not None
                    else None
                ),
                include_category_action=True,
                budget_policy=_agentic_budget_policy_v2(),
                session_policy=_agentic_session_policy_v2(),
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
    _set_agentic_initial_decision_owner_v2("system")
    st.session_state["agentic_delivery"] = delivered
    _store_focused_change_result_v2(
        runtime_step.focused_change_breakdown
    )
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

    _sync_active_history_investigation_snapshot_v1()


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

    if not analysis_mode_allows_agentic_v2(
        seed.requested_analysis_mode
    ):
        st.warning(
            "当前问题没有被识别为诊断或决策调查，"
            "不会建立 Agentic Clarification Gate。"
        )
        return

    try:
        investigation_focus_scope = (
            _build_seed_investigation_focus_scope_v1(seed)
        )
    except ValueError as exc:
        st.error(
            "系统已经给出渠道调查建议，但无法把该建议安全绑定到"
            "唯一渠道代码；为避免退回全渠道，本次深入调查已停止。"
        )
        st.code(f"{type(exc).__name__}: {exc}")
        return

    requirement = (
        build_day89_direction_clarification_requirement_v2()
    )

    with st.spinner(
        "正在准备可选调查方向..."
    ):
        try:
            runtime_step = (
                run_day89_agentic_investigation_step_v2(
                    seed_result=seed,
                    reference_date=date.today(),
                    investigation_focus_scope=investigation_focus_scope,
                    planner=(
                        plan_day89_direction_clarification_v2
                    ),
                    clarification_requirement=requirement,
                    include_category_action=True,
                    budget_policy=_agentic_budget_policy_v2(),
                    session_policy=_agentic_session_policy_v2(),
                )
            )

            delivered = build_investigation_step_delivery_v2(
                seed_result=seed,
                runtime_step=runtime_step,
                request_subject=request.question,
            )

            contract = (
                build_day89_direction_resolution_contract_v2()
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
    _set_agentic_initial_decision_owner_v2("user")
    st.session_state["agentic_delivery"] = delivered
    st.session_state[
        "agentic_pending_clarification"
    ] = pending
    _sync_active_history_investigation_snapshot_v1()


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

    selected_choice = next(
        item
        for item in pending.resolution_contract.choices
        if item.choice_id == choice_id
    )

    with st.spinner(
        "正在执行你选择的调查方向..."
    ):
        try:
            resumed = (
                resume_day89_agentic_investigation_after_clarification_v2(
                    pending=pending,
                    response=ClarificationResponseV2(
                        choice_id=choice_id
                    ),
                    seed_result=_runtime_result(),
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

    if delivered.status == InvestigationDeliveryStatusV2.READY:
        st.session_state[
            "agentic_user_selected_action_v2"
        ] = selected_choice.selected_action_id

    if resumed.runtime_step is not None:
        _store_focused_change_result_v2(
            resumed.runtime_step.focused_change_breakdown
        )

    if (
        delivered.status
        == InvestigationDeliveryStatusV2.READY
    ):
        _clear_agentic_hitl_state()

        runtime_step = resumed.runtime_step
        if (
            runtime_step is not None
            and runtime_step.stop_status is not None
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

    _sync_active_history_investigation_snapshot_v1()


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
        "正在执行下一步调查..."
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
    _store_focused_change_result_v2(
        runtime_step.focused_change_breakdown
    )

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

    _sync_active_history_investigation_snapshot_v1()


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
    st.session_state.pop("periodic_business_report", None)
    st.session_state.pop("periodic_business_report_failure", None)
    st.session_state.pop("periodic_runtime_delivery", None)
    st.session_state.pop("periodic_runtime_failure", None)
    st.session_state.pop("agentic_delivery", None)
    _clear_focused_change_results_v2()
    _clear_fact_composition_state_v2()
    _clear_agentic_hitl_state()
    _clear_agentic_decision_context_v2()

    _update_periodic_runtime_trace_v2(
        stage="runtime_call_starting",
        entry_request_in_session=(
            "entry_request" in st.session_state
        ),
        delivery_present_before_runtime=(
            "periodic_runtime_delivery" in st.session_state
        ),
    )

    # B5A Multi-KPI 是 Periodic Business Report 的主交付。
    with st.spinner(
        "正在生成 Multi-KPI 周期经营报表 → "
        "Governed Query → Evidence → Driver Reconciliation..."
    ):
        try:
            _update_periodic_runtime_trace_v2(
                stage="business_report_runtime_started",
            )

            business_report = run_day93_periodic_business_report_v2(
                cadence=request.report_cadence,
                anchor_date=request.report_anchor_date,
            )
        except GovernanceConfigurationError as exc:
            diagnostic_id = f"d93-business-report-{uuid4().hex[:12]}"
            st.session_state["periodic_business_report_failure"] = {
                "failure_stage": "governance_configuration",
                "exception_type": type(exc).__name__,
                "diagnostic_id": diagnostic_id,
            }
            st.error("Governance Runtime 配置未准备好。")
            st.caption(f"诊断 ID：{diagnostic_id}")
            return
        except Exception as exc:  # noqa: BLE001
            diagnostic_id = f"d93-business-report-{uuid4().hex[:12]}"
            st.session_state["periodic_business_report_failure"] = {
                "failure_stage": "periodic_business_report_runtime",
                "exception_type": type(exc).__name__,
                "diagnostic_id": diagnostic_id,
            }
            st.error(
                "Multi-KPI Periodic Business Report 调用发生未预期错误；"
                "没有生成替代经营报表。"
            )
            st.write("异常类型：", type(exc).__name__)
            st.caption(f"诊断 ID：{diagnostic_id}")
            return

    st.session_state["periodic_business_report"] = (
        business_report
    )
    st.session_state.pop(
        "periodic_business_report_failure",
        None,
    )

    # B4 Contribution 作为扩展模块。
    # 它失败时不能反向抹掉已经形成的 Multi-KPI 主报表。
    with st.spinner(
        "正在补充渠道变化贡献与验证..."
    ):
        try:
            result = (
                run_day89_periodic_gmv_channel_contribution_v2(
                    cadence=request.report_cadence,
                    anchor_date=request.report_anchor_date,
                )
            )
        except Exception as exc:  # noqa: BLE001
            diagnostic_id = f"d93-periodic-{uuid4().hex[:12]}"
            st.session_state["periodic_runtime_failure"] = {
                "failure_stage": "periodic_contribution_extension",
                "exception_type": type(exc).__name__,
                "diagnostic_id": diagnostic_id,
            }
            _update_periodic_runtime_trace_v2(
                stage="contribution_extension_failed",
                exception_type=type(exc).__name__,
                diagnostic_id=diagnostic_id,
                business_report_status=business_report.status.value,
            )
            st.warning(
                "Multi-KPI 报表已生成，但渠道 Contribution 扩展失败；"
                "主报表保持可用。"
            )
            result = None

    result_status = (
        result.status.value
        if (
            result is not None
            and hasattr(result, "status")
        )
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

    if result is not None:
        st.session_state["periodic_runtime_delivery"] = result
        st.session_state.pop("periodic_runtime_failure", None)
    else:
        st.session_state.pop("periodic_runtime_delivery", None)

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

    if result is not None:
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

    st.caption(
        "当前支持：事实查询、主动构成分析、受控调查与周期报表。"
    )

    _render_analysis_session_history_v1()

    entry_mode_label = st.radio(
        "入口类型",
        options=("Investigation", "Periodic Report"),
        format_func=lambda value: {
            "Investigation": "业务问题",
            "Periodic Report": "周期报表",
        }[value],
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
                "开始分析",
                type="primary",
            )

        if submitted:
            _submit_investigation(question)

    else:
        # Periodic controls intentionally live outside st.form.
        #
        # Streamlit form widgets only commit their browser-side values on
        # form submission. For date_input this created a race where a user
        # could visually enter a historical anchor, click Submit immediately,
        # and the submitted Python value/session state still contained the
        # previous default completed-period anchor.
        #
        # Outside a form, cadence/date changes trigger a normal rerun first,
        # so the chosen anchor is committed to session state before the
        # Generate button can invoke Periodic Runtime.
        cadence = st.selectbox(
            "报表周期",
            options=tuple(item.value for item in PeriodicReportCadenceV2),
            format_func=lambda value: {
                "daily": "Daily",
                "weekly": "Weekly",
                "monthly": "Monthly",
            }[value],
            key="periodic_report_cadence",
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

        submitted = st.button(
            "生成周期报表请求",
            type="primary",
            key="periodic_report_submit",
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
