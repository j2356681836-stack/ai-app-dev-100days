from __future__ import annotations

import calendar
from datetime import date, timedelta
from uuid import uuid4

from app.agents.investigation_contracts_v2 import (
    ToolContractV2,
    ToolFailureCodeV2,
    ToolIdentityV2,
)
from app.delivery.decision_console_entry_v2 import (
    PeriodicReportCadenceV2,
)
from app.delivery.breakdown_trusted_summary_v2 import (
    TrustedBreakdownSummaryResultV2,
    TrustedBreakdownSummaryStatusV2,
    build_trusted_breakdown_summary_v2,
)
from app.delivery.runtime_comparison_delivery_v2 import (
    RuntimeComparisonDeliveryResultV2,
    build_runtime_comparison_delivery_v2,
)
from app.delivery.runtime_delivery_bridge_v2 import (
    ApprovedGovernedQueryToolBindingV2,
    RuntimeDeliveryBridgeResultV2,
    RuntimeDeliveryBridgeStatusV2,
    invoke_governed_graph_delivery_v2,
    invoke_governed_plan_delivery_v2,
)
from app.governance.access_context import (
    AccessContext,
    AccessRole,
    OperationMode,
    SensitiveDataPolicy,
)
from app.governance.execution_policy import GovernedExecutionPolicy
from app.governance.governance_runtime import (
    GovernanceRuntimeConfig,
    load_governance_runtime_config,
)
from app.semantic_layer.query_plan_v2_loader import (
    load_query_plan_v2_catalog,
)
from app.semantic_layer.time_comparison_contract_v2 import (
    AlignmentModeV2,
    ComparisonTypeV2,
    PeriodModeV2,
    TimeComparisonContractV2,
    TimeWindowReferenceV2,
)


DAY89_RUNTIME_VERSION = "decision_console_runtime_v2_0"
MONTHLY_REPORT_RUNTIME_VERSION = "monthly_report_runtime_v2_0"


DAY89_LOCAL_CHANNEL_CODES = frozenset(
    {
        "DOUYIN",
        "JD",
        "OFFICIAL_MALL",
        "TMALL",
        "WECHAT_MINI_PROGRAM",
        "XIAOHONGSHU",
    }
)

DAY89_LOCAL_REGION_CODES = frozenset(
    {
        "BEIJING",
        "CHONGQING",
        "GUANGDONG_GUANGZHOU",
        "GUANGDONG_SHENZHEN",
        "GUANGXI_GUILIN",
        "HENAN_LUOYANG",
        "HUBEI_WUHAN",
        "JIANGSU_NANJING",
        "LIAONING_SHENYANG",
        "SHAANXI_XIAN",
        "SHANDONG_QINGDAO",
        "SHANGHAI",
        "SICHUAN_CHENGDU",
        "SICHUAN_MIANYANG",
        "ZHEJIANG_HANGZHOU",
        "ZHEJIANG_JINHUA",
    }
)


def _catalog_resources_v2() -> tuple[
    frozenset[str],
    frozenset[str],
    frozenset[str],
]:
    catalog = load_query_plan_v2_catalog()

    metrics = frozenset(
        plan.metric
        for plan in catalog.query_plans
    )
    tables = frozenset(
        table
        for plan in catalog.query_plans
        for table in plan.resource_contract.required_tables
    )
    columns = frozenset(
        column
        for plan in catalog.query_plans
        for column in plan.resource_contract.required_columns
    )

    return metrics, tables, columns


def build_day89_local_access_context_v2(
    *,
    request_id: str,
) -> AccessContext:
    """
    Day89 local single-user Decision Console context.

    UI 只提供业务输入；资源 allowlist 与 Scope 由 server-owned
    composition root 构造。
    """

    metrics, tables, columns = _catalog_resources_v2()

    return AccessContext(
        request_id=request_id,
        actor_id="day89-local-console-user",
        role=AccessRole.SCOPED_ANALYST,
        dataset_name="beauty_bi_v2",
        target_schema="beauty_bi_v2",
        operation_mode=OperationMode.OBSERVE_ADVISE,
        allowed_metrics=metrics,
        allowed_tables=tables,
        allowed_columns=columns,
        denied_columns=frozenset(),
        allowed_region_codes=DAY89_LOCAL_REGION_CODES,
        allowed_channel_codes=DAY89_LOCAL_CHANNEL_CODES,
        sensitive_data_policy=SensitiveDataPolicy(),
        policy_version="day89_local_console_policy_v1",
        scope_source="day89_local_single_user_mvp",
    )


def _governed_query_tool_contract_v2(
    *,
    name: str,
    purpose: str,
) -> ToolContractV2:
    return ToolContractV2(
        identity=ToolIdentityV2(
            name=name,
            version="dataset_v2",
            purpose=purpose,
        ),
        input_schema_name="GovernedInvestigationInputV2",
        output_schema_name="GovernedFinalizationResult",
        required_permissions=(
            "metric_access",
            "data_scope",
        ),
        execution_policy_reference=(
            "governed_execution_policy_v2"
        ),
        failure_semantics=(
            ToolFailureCodeV2.INVALID_INPUT,
            ToolFailureCodeV2.UNAUTHORIZED,
            ToolFailureCodeV2.UNSUPPORTED,
            ToolFailureCodeV2.TIMEOUT,
            ToolFailureCodeV2.NO_DATA,
            ToolFailureCodeV2.EXECUTION_FAILURE,
        ),
        executor_binding="execute_governed_query_v2",
    )


def build_day89_channel_tool_binding_v2(
) -> ApprovedGovernedQueryToolBindingV2:
    return ApprovedGovernedQueryToolBindingV2(
        plan_name="gmv_channel_v2",
        tool_contract=_governed_query_tool_contract_v2(
            name="governed_gmv_channel_query",
            purpose="查询授权范围内的渠道 GMV。",
        ),
    )


def build_day89_overall_gmv_tool_binding_v2(
) -> ApprovedGovernedQueryToolBindingV2:
    """
    Day89 Monthly Comparison 首次正式注册 overall GMV Evidence Tool。

    这是显式 production binding，不从 plan_name 动态发明 identity。
    """

    return ApprovedGovernedQueryToolBindingV2(
        plan_name="gmv_overall_v2",
        tool_contract=_governed_query_tool_contract_v2(
            name="governed_gmv_overall_query",
            purpose="查询授权范围内的整体 GMV。",
        ),
    )


def run_day89_local_investigation_v2(
    *,
    question: str,
    reference_date: date,
    runtime_config: GovernanceRuntimeConfig | None = None,
    execution_policy: GovernedExecutionPolicy | None = None,
) -> RuntimeDeliveryBridgeResultV2:
    active_config = (
        runtime_config
        if runtime_config is not None
        else load_governance_runtime_config()
    )

    request_id = f"day89-console-{uuid4().hex}"

    context = build_day89_local_access_context_v2(
        request_id=request_id,
    )

    return invoke_governed_graph_delivery_v2(
        context=context,
        question=question,
        reference_date=reference_date,
        runtime_config=active_config,
        approved_tool_binding=(
            build_day89_channel_tool_binding_v2()
        ),
        execution_policy=execution_policy,
        event_id=request_id,
    )


def _calendar_month_window_v2(
    *,
    year: int,
    month: int,
) -> TimeWindowReferenceV2:
    end_day = calendar.monthrange(year, month)[1]

    return TimeWindowReferenceV2(
        start_date=date(year, month, 1),
        end_date=date(year, month, end_day),
    )


def build_monthly_mom_comparison_v2(
    *,
    anchor_date: date,
) -> TimeComparisonContractV2:
    """
    anchor_date 表示用户选择的“报表月份”。

    Monthly 第一版采用完整自然月：
    selected month vs immediately previous month。
    TimeComparisonContract 不负责数据新鲜度判断。
    """

    current_window = _calendar_month_window_v2(
        year=anchor_date.year,
        month=anchor_date.month,
    )

    if anchor_date.month == 1:
        reference_year = anchor_date.year - 1
        reference_month = 12
    else:
        reference_year = anchor_date.year
        reference_month = anchor_date.month - 1

    reference_window = _calendar_month_window_v2(
        year=reference_year,
        month=reference_month,
    )

    return TimeComparisonContractV2(
        comparison_type=ComparisonTypeV2.MOM,
        period_mode=PeriodModeV2.COMPLETED_PERIOD,
        alignment_mode=AlignmentModeV2.CALENDAR_ALIGNED,
        current_window=current_window,
        reference_window=reference_window,
        is_partial_period=False,
    )



def build_daily_dod_comparison_v2(
    *,
    anchor_date: date,
) -> TimeComparisonContractV2:
    """
    Daily 报表使用完整自然日：
    selected day vs immediately previous day。
    """

    current_window = TimeWindowReferenceV2(
        start_date=anchor_date,
        end_date=anchor_date,
    )
    reference_date = anchor_date - timedelta(days=1)
    reference_window = TimeWindowReferenceV2(
        start_date=reference_date,
        end_date=reference_date,
    )

    return TimeComparisonContractV2(
        comparison_type=ComparisonTypeV2.DOD,
        period_mode=PeriodModeV2.COMPLETED_PERIOD,
        alignment_mode=AlignmentModeV2.CALENDAR_ALIGNED,
        current_window=current_window,
        reference_window=reference_window,
        is_partial_period=False,
    )


def build_weekly_wow_comparison_v2(
    *,
    anchor_date: date,
) -> TimeComparisonContractV2:
    """
    Weekly 报表采用 ISO-style 自然周边界：
    Monday -> Sunday。

    anchor_date 只用于定位用户选择的报表周；
    reference 是紧邻的前一个完整自然周。
    """

    current_start = (
        anchor_date
        - timedelta(days=anchor_date.weekday())
    )
    current_end = current_start + timedelta(days=6)

    reference_start = current_start - timedelta(days=7)
    reference_end = current_start - timedelta(days=1)

    return TimeComparisonContractV2(
        comparison_type=ComparisonTypeV2.WOW,
        period_mode=PeriodModeV2.COMPLETED_PERIOD,
        alignment_mode=AlignmentModeV2.CALENDAR_ALIGNED,
        current_window=TimeWindowReferenceV2(
            start_date=current_start,
            end_date=current_end,
        ),
        reference_window=TimeWindowReferenceV2(
            start_date=reference_start,
            end_date=reference_end,
        ),
        is_partial_period=False,
    )


def build_periodic_gmv_comparison_v2(
    *,
    cadence: PeriodicReportCadenceV2,
    anchor_date: date,
) -> TimeComparisonContractV2:
    """
    Day89 Periodic Report 的 server-owned cadence -> comparison mapping。

    UI 只提交 cadence / anchor_date；
    具体比较关系由 Runtime 确定性生成。
    """

    if cadence == PeriodicReportCadenceV2.DAILY:
        return build_daily_dod_comparison_v2(
            anchor_date=anchor_date
        )

    if cadence == PeriodicReportCadenceV2.WEEKLY:
        return build_weekly_wow_comparison_v2(
            anchor_date=anchor_date
        )

    if cadence == PeriodicReportCadenceV2.MONTHLY:
        return build_monthly_mom_comparison_v2(
            anchor_date=anchor_date
        )

    raise ValueError(
        f"Unsupported Periodic Report cadence: {cadence}"
    )


def _periodic_overall_gmv_question_v2(
    window: TimeWindowReferenceV2,
) -> str:
    """
    Query Plan / analysis_window 才是真实执行合同；
    question 只保留业务可读语义，不承担时间解析职责。
    """

    start = window.start_date
    end = window.end_date

    if start == end:
        return (
            f"{start.year}年{start.month}月{start.day}日"
            "GMV是多少？"
        )

    return (
        f"{start.year}年{start.month}月{start.day}日"
        f"至{end.year}年{end.month}月{end.day}日"
        "GMV是多少？"
    )


def _periodic_report_subject_v2(
    *,
    cadence: PeriodicReportCadenceV2,
    comparison: TimeComparisonContractV2,
) -> str:
    window = comparison.current_window

    if cadence == PeriodicReportCadenceV2.DAILY:
        return (
            f"{window.start_date:%Y年%m月%d日}"
            " GMV 日环比报表"
        )

    if cadence == PeriodicReportCadenceV2.WEEKLY:
        return (
            f"{window.start_date:%Y年%m月%d日}"
            f"—{window.end_date:%Y年%m月%d日}"
            " GMV 周环比报表"
        )

    return (
        f"{window.start_date:%Y年%m月}"
        " GMV 月度环比报表"
    )


def run_day89_periodic_gmv_report_v2(
    *,
    cadence: PeriodicReportCadenceV2,
    anchor_date: date,
    runtime_config: GovernanceRuntimeConfig | None = None,
    execution_policy: GovernedExecutionPolicy | None = None,
) -> RuntimeComparisonDeliveryResultV2:
    """
    Daily / Weekly / Monthly 的统一受治理 Overall Comparison Runtime。

    Monthly 保留原正式函数以降低回归风险；
    Daily / Weekly 使用同一 structured Query Plan 路径：
      deterministic comparison
      -> current governed plan delivery
      -> reference governed plan delivery
      -> Evidence / MetricComparison / Console / Brief
    """

    if cadence == PeriodicReportCadenceV2.MONTHLY:
        return run_day89_monthly_gmv_report_v2(
            anchor_date=anchor_date,
            runtime_config=runtime_config,
            execution_policy=execution_policy,
        )

    active_config = (
        runtime_config
        if runtime_config is not None
        else load_governance_runtime_config()
    )

    comparison = build_periodic_gmv_comparison_v2(
        cadence=cadence,
        anchor_date=anchor_date,
    )

    base_request_id = (
        f"day89-{cadence.value}-"
        f"{anchor_date.isoformat()}-{uuid4().hex}"
    )

    binding = build_day89_overall_gmv_tool_binding_v2()

    current_request_id = f"{base_request_id}-current"
    current_result = invoke_governed_plan_delivery_v2(
        context=build_day89_local_access_context_v2(
            request_id=current_request_id,
        ),
        plan_name=binding.plan_name,
        analysis_window=comparison.current_window,
        question=_periodic_overall_gmv_question_v2(
            comparison.current_window
        ),
        runtime_config=active_config,
        approved_tool_binding=binding,
        execution_policy=execution_policy,
        event_id=current_request_id,
    )

    reference_request_id = f"{base_request_id}-reference"
    reference_result = invoke_governed_plan_delivery_v2(
        context=build_day89_local_access_context_v2(
            request_id=reference_request_id,
        ),
        plan_name=binding.plan_name,
        analysis_window=comparison.reference_window,
        question=_periodic_overall_gmv_question_v2(
            comparison.reference_window
        ),
        runtime_config=active_config,
        approved_tool_binding=binding,
        execution_policy=execution_policy,
        event_id=reference_request_id,
    )

    return build_runtime_comparison_delivery_v2(
        current_result=current_result,
        reference_result=reference_result,
        comparison=comparison,
        request_subject=_periodic_report_subject_v2(
            cadence=cadence,
            comparison=comparison,
        ),
    )


def _monthly_overall_gmv_question_v2(
    window: TimeWindowReferenceV2,
) -> str:
    """
    给现有 Governed Graph 一个单窗口、单指标、单 grain 的明确请求。

    不把“本月和上月”同时送给 Time Resolver，避免触发已知的
    multi-window ambiguity。
    """

    return (
        f"{window.start_date.year}年"
        f"{window.start_date.month}月GMV是多少？"
    )


def run_day89_monthly_gmv_report_v2(
    *,
    anchor_date: date,
    runtime_config: GovernanceRuntimeConfig | None = None,
    execution_policy: GovernedExecutionPolicy | None = None,
) -> RuntimeComparisonDeliveryResultV2:
    """
    Day89 Periodic Report 第一条真实 Runtime：

    Monthly Report Definition
      -> deterministic MoM TimeComparisonContract
      -> current Governed Graph query
      -> reference Governed Graph query
      -> two protected Evidence Records
      -> MetricComparisonV2
      -> DecisionConsoleViewV2 / Executive Brief

    当前不支持 Daily / Weekly / YoY / Trend。
    """

    active_config = (
        runtime_config
        if runtime_config is not None
        else load_governance_runtime_config()
    )

    comparison = build_monthly_mom_comparison_v2(
        anchor_date=anchor_date
    )

    base_request_id = (
        f"day89-monthly-{anchor_date.isoformat()}-"
        f"{uuid4().hex}"
    )

    binding = build_day89_overall_gmv_tool_binding_v2()

    current_request_id = f"{base_request_id}-current"
    current_result = invoke_governed_plan_delivery_v2(
        context=build_day89_local_access_context_v2(
            request_id=current_request_id,
        ),
        plan_name=binding.plan_name,
        analysis_window=comparison.current_window,
        question=_monthly_overall_gmv_question_v2(
            comparison.current_window
        ),
        runtime_config=active_config,
        approved_tool_binding=binding,
        execution_policy=execution_policy,
        event_id=current_request_id,
    )

    reference_request_id = f"{base_request_id}-reference"
    reference_result = invoke_governed_plan_delivery_v2(
        context=build_day89_local_access_context_v2(
            request_id=reference_request_id,
        ),
        plan_name=binding.plan_name,
        analysis_window=comparison.reference_window,
        question=_monthly_overall_gmv_question_v2(
            comparison.reference_window
        ),
        runtime_config=active_config,
        approved_tool_binding=binding,
        execution_policy=execution_policy,
        event_id=reference_request_id,
    )

    subject = (
        f"{comparison.current_window.start_date:%Y年%m月}"
        " GMV 月度环比报表"
    )

    return build_runtime_comparison_delivery_v2(
        current_result=current_result,
        reference_result=reference_result,
        comparison=comparison,
        request_subject=subject,
    )



def _explicit_window_metric_question_v2(
    *,
    metric_name: str,
    window: TimeWindowReferenceV2,
) -> str:
    """
    用 Primary Evidence 已确认的时间窗构造单一显式日期范围请求。

    Time Resolver 会再次解析并由 Summary Builder 校验最终窗口，
    因此这里不能静默改变 trusted window。
    """

    start = window.start_date
    end = window.end_date

    return (
        f"{start.year}年{start.month}月{start.day}日"
        f"至{end.year}年{end.month}月{end.day}日"
        f"{metric_name.upper()}是多少？"
    )


def run_day89_breakdown_summary_v2(
    *,
    primary_result: RuntimeDeliveryBridgeResultV2,
    reference_date: date,
    runtime_config: GovernanceRuntimeConfig | None = None,
    execution_policy: GovernedExecutionPolicy | None = None,
) -> TrustedBreakdownSummaryResultV2:
    """
    为已经 READY 的 Breakdown Delivery 查询独立可信汇总。

    Day89 v1 注册：
    - gmv + channel -> gmv_overall_v2

    未来其他指标必须先显式注册 approved overall Tool Binding；
    不允许 UI 根据 rows 自行求和。
    """

    if (
        primary_result.status
        != RuntimeDeliveryBridgeStatusV2.READY
        or primary_result.delivery is None
        or primary_result.console_view is None
        or primary_result.console_view.breakdown is None
    ):
        return TrustedBreakdownSummaryResultV2(
            status=(
                TrustedBreakdownSummaryStatusV2
                .PRIMARY_NOT_READY
            ),
            message="当前结果不是可汇总的 READY Breakdown Delivery。",
        )

    scope = primary_result.delivery.evidence_pack.analysis_scope

    if not (
        scope.metric_name == "gmv"
        and scope.result_grain == "channel"
    ):
        return TrustedBreakdownSummaryResultV2(
            status=(
                TrustedBreakdownSummaryStatusV2
                .NOT_REGISTERED
            ),
            message=(
                "当前 metric / grain 尚未注册独立 Overall "
                "Governed Tool Binding；不会对明细行自行求和。"
            ),
        )

    active_config = (
        runtime_config
        if runtime_config is not None
        else load_governance_runtime_config()
    )

    request_id = (
        "day89-breakdown-summary-"
        f"{uuid4().hex}"
    )

    binding = build_day89_overall_gmv_tool_binding_v2()

    overall_result = invoke_governed_plan_delivery_v2(
        context=build_day89_local_access_context_v2(
            request_id=request_id,
        ),
        plan_name=binding.plan_name,
        analysis_window=scope.analysis_window,
        question=_explicit_window_metric_question_v2(
            metric_name=scope.metric_name,
            window=scope.analysis_window,
        ),
        runtime_config=active_config,
        approved_tool_binding=binding,
        execution_policy=execution_policy,
        event_id=request_id,
    )

    return build_trusted_breakdown_summary_v2(
        primary_result=primary_result,
        overall_result=overall_result,
    )
