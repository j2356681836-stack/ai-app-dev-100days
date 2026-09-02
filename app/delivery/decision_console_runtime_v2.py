from __future__ import annotations

import calendar
import re
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
from app.delivery.business_clarification_continuation_v1 import (
    BusinessClarificationResolutionV1,
)
from app.delivery.breakdown_trusted_summary_v2 import (
    TrustedBreakdownSummaryResultV2,
    TrustedBreakdownSummaryStatusV2,
    build_trusted_breakdown_summary_v2,
)
from app.delivery.decision_console_view_v2 import (
    build_decision_console_view_v2,
)
from app.delivery.contribution_investigation_recommendation_v1 import (
    build_contribution_investigation_recommendation_v1,
)
from app.delivery.contribution_investigation_route_v2 import (
    build_contribution_investigation_route_v2,
)
from app.agents.investigation_route_v2 import (
    InvestigationScopeStrategyV2,
)
from app.delivery.ranking_answer_delivery_v1 import (
    build_priority_assessment_v1,
)
from app.delivery.runtime_comparison_delivery_v2 import (
    RuntimeComparisonDeliveryResultV2,
    build_runtime_comparison_delivery_v2,
)
from app.delivery.runtime_delivery_bridge_v2 import (
    ApprovedGovernedQueryToolBindingV2,
    RuntimeDeliveryBridgeResultV2,
    RuntimeDeliveryBridgeStatusV2,
    _select_approved_tool_binding_for_plan_v2,
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
from app.semantic_layer.analysis_mode_contract_v2 import (
    AnalysisModeV2,
)
from app.semantic_layer.analysis_mode_resolution_v2 import (
    resolve_analysis_mode_v2,
)
from app.semantic_layer.comparison_intent_semantic_v2 import (
    ComparisonIntentSemanticStatusV2,
    resolve_gmv_adjacent_month_comparison_intent_v2,
)
from app.semantic_layer.question_semantic_parser_v2 import (
    LLMCall,
)
from app.semantic_layer.dataset_availability_contract_v2 import (
    DatasetAvailabilityOutcomeV2,
    evaluate_dataset_availability_v2,
)
from app.semantic_layer.query_plan_selector_v2 import (
    QueryPlanSelectionStatusV2,
    select_query_plan_v2,
)
from app.semantic_layer.query_plan_v2_loader import (
    load_query_plan_v2_catalog,
)
from app.semantic_layer.channel_applicability_v2 import (
    ChannelBusinessRoleV2,
    channel_codes_for_role_v2,
)
from app.semantic_layer.requested_scope_resolution_v2 import (
    RequestedScopeResolutionStatusV2,
    resolve_requested_scope_v2,
)
from app.semantic_layer.result_grain_resolver_v2 import (
    ResultGrainResolutionStatusV2,
    resolve_result_grain_v2,
)
from app.semantic_layer.time_comparison_contract_v2 import (
    AlignmentModeV2,
    ComparisonTypeV2,
    PeriodModeV2,
    TimeComparisonContractV2,
    TimeWindowReferenceV2,
)
from app.semantic_layer.time_window_resolver_v2 import (
    TimeWindowResolutionStatusV2,
    resolve_time_window_v2,
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
    allow_aggregated_business_metrics: bool = False,
    channel_role: ChannelBusinessRoleV2 = ChannelBusinessRoleV2.SALES,
) -> AccessContext:
    """
    Day89 local single-user Decision Console context.

    UI 只提供业务输入；资源 allowlist 与 Scope 由 server-owned
    composition root 构造。
    """

    metrics, tables, columns = _catalog_resources_v2()

    business_applicable_channels = (
        DAY89_LOCAL_CHANNEL_CODES
        & channel_codes_for_role_v2(channel_role)
    )

    if not business_applicable_channels:
        raise ValueError(
            "当前 AccessContext 与业务渠道适用范围没有交集。"
        )

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
        allowed_channel_codes=business_applicable_channels,
        sensitive_data_policy=SensitiveDataPolicy(
            allow_aggregated_business_metrics=(
                allow_aggregated_business_metrics
            ),
        ),
        policy_version="day89_local_console_policy_v2",
        scope_source=(
            "day89_local_single_user_mvp:"
            f"{channel_role.value}_channel_scope"
        ),
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


def build_day89_overall_order_count_tool_binding_v2(
) -> ApprovedGovernedQueryToolBindingV2:
    """
    Day93 Blind Regression 首次正式注册非 GMV 的 Business Question Tool。

    这是显式 server-owned approval：
    - plan_name 固定为 order_count_overall_v2；
    - Tool identity 固定；
    - permissions / executor 继续使用既有 Governed Query contract；
    - 不从用户问题或 Catalog 动态创建 Tool。
    """

    return ApprovedGovernedQueryToolBindingV2(
        plan_name="order_count_overall_v2",
        tool_contract=_governed_query_tool_contract_v2(
            name="governed_order_count_overall_query",
            purpose="查询授权范围内的成功支付订单数。",
        ),
    )


def build_day89_channel_order_count_tool_binding_v2(
) -> ApprovedGovernedQueryToolBindingV2:
    """
    F04 Clarification Continuation 的显式渠道订单数批准项。
    """
    return ApprovedGovernedQueryToolBindingV2(
        plan_name="order_count_channel_v2",
        tool_contract=_governed_query_tool_contract_v2(
            name="governed_order_count_channel_query",
            purpose="查询授权范围内的渠道订单数。",
        ),
    )


def build_day89_channel_buyer_count_tool_binding_v2(
) -> ApprovedGovernedQueryToolBindingV2:
    """
    F04 Clarification Continuation 的显式渠道购买人数批准项。
    """
    return ApprovedGovernedQueryToolBindingV2(
        plan_name="buyer_count_channel_v2",
        tool_contract=_governed_query_tool_contract_v2(
            name="governed_buyer_count_channel_query",
            purpose="查询授权范围内的渠道购买人数。",
        ),
    )


def _build_day93_refund_rate_tool_binding_v2(
    *,
    grain: str,
) -> ApprovedGovernedQueryToolBindingV2:
    supported = {
        "overall": "整体",
        "channel": "渠道",
        "region": "地区",
        "category": "品类",
    }

    if grain not in supported:
        raise ValueError(
            f"Unsupported refund-rate binding grain: {grain}"
        )

    return ApprovedGovernedQueryToolBindingV2(
        plan_name=f"refund_rate_{grain}_v2",
        tool_contract=_governed_query_tool_contract_v2(
            name=f"governed_refund_rate_{grain}_query",
            purpose=(
                f"查询授权范围内的{supported[grain]}退款率。"
            ),
        ),
    )


def build_day93_overall_refund_rate_tool_binding_v2(
) -> ApprovedGovernedQueryToolBindingV2:
    return _build_day93_refund_rate_tool_binding_v2(
        grain="overall"
    )


def build_day93_channel_refund_rate_tool_binding_v2(
) -> ApprovedGovernedQueryToolBindingV2:
    return _build_day93_refund_rate_tool_binding_v2(
        grain="channel"
    )


def build_day93_region_refund_rate_tool_binding_v2(
) -> ApprovedGovernedQueryToolBindingV2:
    return _build_day93_refund_rate_tool_binding_v2(
        grain="region"
    )


def build_day93_category_refund_rate_tool_binding_v2(
) -> ApprovedGovernedQueryToolBindingV2:
    return _build_day93_refund_rate_tool_binding_v2(
        grain="category"
    )


def build_day89_business_question_tool_binding_registry_v2(
) -> tuple[ApprovedGovernedQueryToolBindingV2, ...]:
    """
    Business Question Runtime 的 server-owned 静态 Approved Registry。

    这里列出的每一项都代表一次显式产品/治理批准。
    新 Query Plan 不会因为加入 Catalog 就自动获得 Tool Binding。

    primary gmv_channel_v2 为向后兼容继续单独传入；
    本 Registry 只保存 additional approved bindings。
    """

    registry = (
        build_day89_overall_gmv_tool_binding_v2(),
        build_day89_overall_order_count_tool_binding_v2(),
        build_day89_channel_order_count_tool_binding_v2(),
        build_day89_channel_buyer_count_tool_binding_v2(),
        build_day93_overall_refund_rate_tool_binding_v2(),
        build_day93_channel_refund_rate_tool_binding_v2(),
        build_day93_region_refund_rate_tool_binding_v2(),
        build_day93_category_refund_rate_tool_binding_v2(),
    )

    plan_names = tuple(
        binding.plan_name
        for binding in registry
    )

    if len(plan_names) != len(set(plan_names)):
        raise ValueError(
            "Day89 Business Question Approved Binding Registry "
            f"contains duplicate plan_name values: {plan_names}"
        )

    return registry



def _is_day93_f02_compound_gmv_channel_question_v1(
    question: str,
) -> bool:
    """
    F02 的窄 server-owned compound question contract。

    当前 V1 只识别：
    - GMV；
    - 明确的“相比 / 比”时间比较；
    - 渠道；
    - 明确的继续调查 / 优先查看意图。

    它不是通用 multi-intent parser。
    未命中时继续交给既有 Governed Graph。
    """
    text = re.sub(
        r"\s+",
        "",
        question,
    ).casefold()

    has_gmv = "gmv" in text
    has_comparison = bool(
        re.search(r"(?:相比|比较|比)", text)
    )
    has_channel = "渠道" in text
    has_investigation = bool(
        re.search(
            (
                r"(?:继续|进一步)?(?:调查|分析|排查)"
                r".{0,12}(?:先|优先|最值得)"
                r".{0,8}(?:看|调查|关注)"
                r".{0,6}(?:哪个|哪一个)?渠道"
                r"|"
                r"(?:最值得|优先|首先)"
                r".{0,8}(?:看|调查|关注)"
                r".{0,6}(?:哪个|哪一个)?渠道"
                r"|"
                r"(?:先|优先)(?:看|调查|关注)"
                r"(?:哪个|哪一个)渠道"
            ),
            text,
        )
    )

    return (
        has_gmv
        and has_comparison
        and has_channel
        and has_investigation
    )


def _extract_day93_f02_adjacent_months_v1(
    question: str,
) -> tuple[date, date] | None:
    """
    从 F02 V1 中提取 Current Month / Reference Month。

    仅接受“显式当前年月 + 相邻前月”的月环比。
    例如：
      2025年10月 ... 相比9月 ...
      2026年1月 ... 相比2025年12月 ...

    返回：
      (current_anchor_date, reference_anchor_date)

    非相邻月份 / 非明确年月 -> None，禁止静默改写比较合同。
    """
    text = re.sub(
        r"\s+",
        "",
        question,
    )

    match = re.search(
        (
            r"(?P<current_year>20\d{2})年"
            r"(?P<current_month>\d{1,2})月"
            r".{0,40}?"
            r"(?:相比|比较|比)"
            r".{0,12}?"
            r"(?:(?P<reference_year>20\d{2})年)?"
            r"(?P<reference_month>\d{1,2})月"
        ),
        text,
        flags=re.IGNORECASE,
    )

    if match is None:
        return None

    current_year = int(match.group("current_year"))
    current_month = int(match.group("current_month"))
    reference_month = int(match.group("reference_month"))

    if not (
        1 <= current_month <= 12
        and 1 <= reference_month <= 12
    ):
        return None

    if current_month == 1:
        expected_reference_year = current_year - 1
        expected_reference_month = 12
    else:
        expected_reference_year = current_year
        expected_reference_month = current_month - 1

    raw_reference_year = match.group("reference_year")

    reference_year = (
        int(raw_reference_year)
        if raw_reference_year is not None
        else expected_reference_year
    )

    if (
        reference_year != expected_reference_year
        or reference_month != expected_reference_month
    ):
        return None

    current_end_day = calendar.monthrange(
        current_year,
        current_month,
    )[1]
    reference_end_day = calendar.monthrange(
        reference_year,
        reference_month,
    )[1]

    return (
        date(
            current_year,
            current_month,
            current_end_day,
        ),
        date(
            reference_year,
            reference_month,
            reference_end_day,
        ),
    )



def _resolve_day93_gmv_comparison_seed_investigation_v2(
    question: str,
) -> tuple[date, date, object] | None:
    """
    Resolve a comparison-bearing Investigation with a clear GMV Seed
    but no explicit Seed Result Grain.

    Example:
        “2025年8月GMV相比7月表现怎么样？
         如果继续调查，最值得优先看哪个方向？”

    Contract:
    - requested analysis mode = INVESTIGATION;
    - Day93 registration currently supports explicit GMV only;
    - raw Result Grain remains UNSPECIFIED with no dimension evidence;
    - time comparison is an explicit adjacent natural-month MoM;
    - unresolved explicit Requested Scope fails closed.

    This resolves only the trusted Seed Comparison.
    It does NOT choose the later Investigation Target Grain.
    """

    text = str(question).strip()

    if "gmv" not in text.casefold():
        return None

    analysis_mode = resolve_analysis_mode_v2(
        text
    )

    if (
        analysis_mode.analysis_mode
        != AnalysisModeV2.INVESTIGATION
    ):
        return None

    raw_grain = resolve_result_grain_v2(
        text
    )

    if (
        raw_grain.status
        != ResultGrainResolutionStatusV2.UNSPECIFIED
        or raw_grain.dimensions
        or raw_grain.evidence
    ):
        return None

    months = _extract_day93_f02_adjacent_months_v1(
        text
    )

    if months is None:
        return None

    requested_scope = resolve_requested_scope_v2(
        text
    )

    if (
        requested_scope.status
        == RequestedScopeResolutionStatusV2
        .UNRESOLVED_EXPLICIT_SCOPE
    ):
        return None

    current_anchor, reference_anchor = months

    return (
        current_anchor,
        reference_anchor,
        requested_scope,
    )


def _resolve_day94_gmv_comparison_seed_v2(
    question: str,
    *,
    comparison_intent_llm_call: LLMCall | None = None,
) -> tuple[
    date,
    date,
    object,
    AnalysisModeV2,
    str,
] | None:
    """
    Day94 Hybrid Comparison Intent Boundary。

    Fast path：
    - 保留 Day93 已验收的高置信度 deterministic Investigation；
    - 不给已经稳定的表达增加额外 LLM latency。

    Semantic fallback：
    - 当原 deterministic contract 未命中时，
      仅让 LLM 归一化 current/reference 月份语义角色与
      COMPARISON / INVESTIGATION 深度；
    - LLM 结果必须经过 comparison_intent_semantic_v2 的
      deterministic validation；
    - Requested Scope / Seed Grain 仍由既有 server-owned resolver
      决定，LLM 不参与权限或 Query Plan 选择。

    最终返回：
      current_anchor
      reference_anchor
      requested_scope
      requested_analysis_mode
      route_source
    """

    text = str(question).strip()

    if "gmv" not in text.casefold():
        return None

    deterministic = (
        _resolve_day93_gmv_comparison_seed_investigation_v2(
            text
        )
    )

    if deterministic is not None:
        (
            current_anchor,
            reference_anchor,
            requested_scope,
        ) = deterministic

        return (
            current_anchor,
            reference_anchor,
            requested_scope,
            AnalysisModeV2.INVESTIGATION,
            "day93_deterministic_fast_path",
        )

    raw_grain = resolve_result_grain_v2(
        text
    )

    if (
        raw_grain.status
        != ResultGrainResolutionStatusV2.UNSPECIFIED
        or raw_grain.dimensions
        or raw_grain.evidence
    ):
        return None

    requested_scope = resolve_requested_scope_v2(
        text
    )

    if (
        requested_scope.status
        == RequestedScopeResolutionStatusV2
        .UNRESOLVED_EXPLICIT_SCOPE
    ):
        return None

    if comparison_intent_llm_call is None:
        semantic = (
            resolve_gmv_adjacent_month_comparison_intent_v2(
                text
            )
        )
    else:
        semantic = (
            resolve_gmv_adjacent_month_comparison_intent_v2(
                text,
                llm_call=comparison_intent_llm_call,
            )
        )

    if (
        semantic.status
        != ComparisonIntentSemanticStatusV2.READY
        or semantic.analysis_mode is None
        or semantic.current_anchor_date is None
        or semantic.reference_anchor_date is None
    ):
        deterministic_months = (
            _extract_day93_f02_adjacent_months_v1(
                text
            )
        )

        deterministic_mode = resolve_analysis_mode_v2(
            text
        )

        if (
            deterministic_months is None
            or deterministic_mode.analysis_mode
            != AnalysisModeV2.COMPARISON
        ):
            return None

        current_anchor, reference_anchor = (
            deterministic_months
        )

        return (
            current_anchor,
            reference_anchor,
            requested_scope,
            AnalysisModeV2.COMPARISON,
            "day94_deterministic_comparison_fallback",
        )

    return (
        semantic.current_anchor_date,
        semantic.reference_anchor_date,
        requested_scope,
        semantic.analysis_mode,
        semantic.source,
    )


def _run_day93_gmv_comparison_seed_investigation_v2(
    *,
    question: str,
    runtime_config: GovernanceRuntimeConfig,
    execution_policy: GovernedExecutionPolicy | None,
    comparison_intent_llm_call: LLMCall | None = None,
) -> RuntimeDeliveryBridgeResultV2 | None:
    """
    Generic Comparison Seed -> bounded Investigation.

    F02 remains the richer special orchestration:
        Overall Comparison -> Channel Contribution -> Route.

    This generic path does:
        Overall Comparison Seed
        -> release trusted current/reference/delta first
        -> preserve requested_analysis_mode=INVESTIGATION
        -> later Agentic Investigation chooses a registered direction.

    The Seed Evidence remains COMPARISON evidence.
    The user's deeper requested mode remains INVESTIGATION.
    """

    resolved = (
        _resolve_day94_gmv_comparison_seed_v2(
            question,
            comparison_intent_llm_call=(
                comparison_intent_llm_call
            ),
        )
    )

    if resolved is None:
        return None

    (
        current_anchor,
        reference_anchor,
        requested_scope,
        requested_analysis_mode,
        semantic_route_source,
    ) = resolved

    comparison = build_monthly_mom_comparison_v2(
        anchor_date=current_anchor
    )

    # Defense in depth: parser and deterministic comparison builder
    # must agree on the exact reference month.
    if (
        comparison.reference_window.end_date
        != reference_anchor
    ):
        return RuntimeDeliveryBridgeResultV2(
            status=RuntimeDeliveryBridgeStatusV2.GRAPH_STOPPED,
            message=(
                "比较时间合同无法稳定对齐，"
                "本次不执行替代查询。"
            ),
            safe_runtime_result={
                "success": False,
                "outcome": "stopped",
                "stop_stage": (
                    "comparison_seed_time_contract"
                ),
                "reason_code": (
                    "reference_window_mismatch"
                ),
                "question": question,
            },
            requested_scope=requested_scope,
            requested_analysis_mode=(
                requested_analysis_mode
            ),
        )

    binding = (
        build_day89_overall_gmv_tool_binding_v2()
    )

    base_request_id = (
        "day93-comparison-seed-"
        f"{current_anchor.isoformat()}-"
        f"{uuid4().hex}"
    )

    current_request_id = (
        f"{base_request_id}-current"
    )
    current_result = invoke_governed_plan_delivery_v2(
        context=build_day89_local_access_context_v2(
            request_id=current_request_id,
        ),
        plan_name=binding.plan_name,
        analysis_window=comparison.current_window,
        question=_monthly_overall_gmv_question_v2(
            comparison.current_window
        ),
        runtime_config=runtime_config,
        approved_tool_binding=binding,
        requested_scope=requested_scope,
        execution_policy=execution_policy,
        event_id=current_request_id,
    )

    reference_request_id = (
        f"{base_request_id}-reference"
    )
    reference_result = invoke_governed_plan_delivery_v2(
        context=build_day89_local_access_context_v2(
            request_id=reference_request_id,
        ),
        plan_name=binding.plan_name,
        analysis_window=(
            comparison.reference_window
        ),
        question=_monthly_overall_gmv_question_v2(
            comparison.reference_window
        ),
        runtime_config=runtime_config,
        approved_tool_binding=binding,
        requested_scope=requested_scope,
        execution_policy=execution_policy,
        event_id=reference_request_id,
    )

    comparison_delivery = (
        build_runtime_comparison_delivery_v2(
            current_result=current_result,
            reference_result=reference_result,
            comparison=comparison,
            request_subject=question,
        )
    )

    if (
        comparison_delivery.status.value
        != "ready"
        or comparison_delivery.delivery is None
        or comparison_delivery.console_view is None
        or comparison_delivery.executive_brief is None
        or comparison_delivery.metric_comparison_result
        is None
    ):
        return RuntimeDeliveryBridgeResultV2(
            status=RuntimeDeliveryBridgeStatusV2.GRAPH_STOPPED,
            message=(
                "整体比较 Seed 没有形成完整的可释放证据，"
                "因此暂不进入后续调查。"
            ),
            safe_runtime_result={
                "success": False,
                "outcome": "stopped",
                "stop_stage": (
                    "comparison_seed_delivery"
                ),
                "reason_code": (
                    "comparison_delivery_not_ready"
                ),
                "comparison_status": (
                    comparison_delivery.status.value
                ),
                "question": question,
                "current_window": {
                    "start_date": (
                        comparison.current_window
                        .start_date.isoformat()
                    ),
                    "end_date": (
                        comparison.current_window
                        .end_date.isoformat()
                    ),
                },
                "reference_window": {
                    "start_date": (
                        comparison.reference_window
                        .start_date.isoformat()
                    ),
                    "end_date": (
                        comparison.reference_window
                        .end_date.isoformat()
                    ),
                },
            },
            requested_scope=requested_scope,
            requested_analysis_mode=(
                requested_analysis_mode
            ),
        )

    return RuntimeDeliveryBridgeResultV2(
        status=RuntimeDeliveryBridgeStatusV2.READY,
        message=(
            (
                "整体时间比较 Seed 已形成受治理交付；"
                "后续调查方向尚未由 Seed Grain 预先指定。"
            )
            if requested_analysis_mode
            == AnalysisModeV2.INVESTIGATION
            else "整体时间比较已形成受治理交付。"
        ),
        safe_runtime_result={
            "success": True,
            "outcome": "ready",
            "orchestration": (
                "comparison_seed_then_investigation_v2"
            ),
            "question": question,
            "seed_metric": "gmv",
            "seed_grain": "overall",
            "investigation_target_grain": None,
            "semantic_route_source": semantic_route_source,
            "requested_analysis_mode": (
                requested_analysis_mode.value
            ),
            "current_window": {
                "start_date": (
                    comparison.current_window
                    .start_date.isoformat()
                ),
                "end_date": (
                    comparison.current_window
                    .end_date.isoformat()
                ),
            },
            "reference_window": {
                "start_date": (
                    comparison.reference_window
                    .start_date.isoformat()
                ),
                "end_date": (
                    comparison.reference_window
                    .end_date.isoformat()
                ),
            },
        },
        requested_scope=requested_scope,
        requested_analysis_mode=(
            requested_analysis_mode
        ),
        delivery=comparison_delivery.delivery,
        console_view=(
            comparison_delivery.console_view
        ),
        executive_brief=(
            comparison_delivery.executive_brief
        ),
    )


def _run_day93_f02_compound_comparison_v1(
    *,
    question: str,
    runtime_config: GovernanceRuntimeConfig,
    execution_policy: GovernedExecutionPolicy | None,
) -> RuntimeDeliveryBridgeResultV2 | None:
    """
    F02：Overall Comparison -> Channel Contribution
    -> Investigation Recommendation。

    这里只编排既有可信能力，不重新实现：
    - GMV Query Plan；
    - Monthly Comparison；
    - Channel Breakdown；
    - Contribution Core；
    - Result Protection / Evidence / Audit。

    当前 V1 只支持无显式 Row Scope 的相邻自然月 GMV 比较。
    有显式 Region / Channel Scope 时交回原 Graph，避免专用 Runtime
    忽略 Requested Scope。
    """
    if not _is_day93_f02_compound_gmv_channel_question_v1(
        question
    ):
        return None

    months = _extract_day93_f02_adjacent_months_v1(
        question
    )

    if months is None:
        return None

    current_anchor, reference_anchor = months

    requested_scope = resolve_requested_scope_v2(
        question
    )

    if (
        requested_scope.status
        != RequestedScopeResolutionStatusV2.NO_EXPLICIT_SCOPE
    ):
        return None

    # Local import 避免 decision_console_runtime_v2 与
    # monthly_contribution_delivery_v2 的模块级循环依赖。
    from app.delivery.monthly_contribution_delivery_v2 import (
        MonthlyContributionDeliveryStatusV2,
        run_day89_monthly_gmv_channel_contribution_v2,
    )

    compound = run_day89_monthly_gmv_channel_contribution_v2(
        anchor_date=current_anchor,
        runtime_config=runtime_config,
        execution_policy=execution_policy,
    )

    if (
        compound.status
        != MonthlyContributionDeliveryStatusV2.READY
        or compound.delivery is None
        or compound.console_view is None
        or compound.metric_comparison_result is None
        or compound.contribution_result is None
        or compound.executive_brief is None
        or compound.console_view.contribution is None
    ):
        return RuntimeDeliveryBridgeResultV2(
            status=RuntimeDeliveryBridgeStatusV2.GRAPH_STOPPED,
            message=(
                "整体月度比较或渠道变化贡献没有形成完整的"
                "可释放证据，因此暂不生成优先调查建议。"
            ),
            safe_runtime_result={
                "success": False,
                "outcome": "stopped",
                "stop_stage": "f02_compound_orchestration",
                "reason_code": (
                    "comparison_or_contribution_not_ready"
                ),
                "compound_status": compound.status.value,
                "question": question,
                "current_anchor_date": (
                    current_anchor.isoformat()
                ),
                "reference_anchor_date": (
                    reference_anchor.isoformat()
                ),
            },
            requested_scope=requested_scope,
            requested_analysis_mode=AnalysisModeV2.DIAGNOSTIC,
        )

    contribution_evidence_id = (
        compound.console_view.contribution.evidence_id
    )

    route_recommendation = (
        build_contribution_investigation_route_v2(
            contribution=compound.contribution_result,
            contribution_evidence_id=(
                contribution_evidence_id
            ),
        )
    )

    # 旧的单一 Channel Recommendation 仅在新 Routing Policy
    # 明确允许 Member Focus 时保留，用于兼容现有 Channel Focus
    # code/value binding。Near-Tie / Distributed 不再生成 Top1 Focus。
    recommendation = None

    if (
        route_recommendation is not None
        and route_recommendation.route.scope_strategy
        == InvestigationScopeStrategyV2.FOCUS_MEMBER
    ):
        recommendation = (
            build_contribution_investigation_recommendation_v1(
                contribution=compound.contribution_result,
                contribution_evidence_id=(
                    contribution_evidence_id
                ),
            )
        )

    breakdown_evidence_id = (
        compound.console_view.breakdown.evidence_id
        if compound.console_view.breakdown is not None
        else None
    )

    rebuilt_view = build_decision_console_view_v2(
        delivery=compound.delivery,
        metric_comparison_result=(
            compound.metric_comparison_result
        ),
        contribution_result=compound.contribution_result,
        contribution_evidence_id=(
            contribution_evidence_id
        ),
        breakdown_evidence_id=breakdown_evidence_id,
        contribution_investigation_recommendation=(
            recommendation
        ),
        contribution_investigation_route_recommendation=(
            route_recommendation
        ),
    )

    comparison = compound.metric_comparison_result

    return RuntimeDeliveryBridgeResultV2(
        status=RuntimeDeliveryBridgeStatusV2.READY,
        message=(
            "GMV 月环比、渠道变化贡献与下一步调查建议"
            "已形成受治理业务交付。"
        ),
        safe_runtime_result={
            "success": True,
            "outcome": "ready",
            "orchestration": (
                "f02_monthly_comparison_channel_contribution_v1"
            ),
            "question": question,
            "current_window": {
                "start_date": (
                    comparison.comparison.current_window
                    .start_date.isoformat()
                ),
                "end_date": (
                    comparison.comparison.current_window
                    .end_date.isoformat()
                ),
            },
            "reference_window": {
                "start_date": (
                    comparison.comparison.reference_window
                    .start_date.isoformat()
                ),
                "end_date": (
                    comparison.comparison.reference_window
                    .end_date.isoformat()
                ),
            },
            "recommendation_available": (
                route_recommendation is not None
            ),
            "legacy_member_focus_available": (
                recommendation is not None
            ),
            "route_pattern": (
                route_recommendation.pattern_assessment.pattern.value
                if route_recommendation is not None
                else None
            ),
            "route_scope_strategy": (
                route_recommendation.route.scope_strategy.value
                if route_recommendation is not None
                else None
            ),
            "route_next_dimension": (
                route_recommendation.route.next_dimension.value
                if route_recommendation is not None
                else None
            ),
            "contribution_reconciliation_status": (
                compound.contribution_result
                .reconciliation_status.value
            ),
        },
        requested_scope=requested_scope,
        requested_analysis_mode=AnalysisModeV2.DIAGNOSTIC,
        delivery=compound.delivery,
        console_view=rebuilt_view,
        executive_brief=compound.executive_brief,
    )


def _is_day93_refund_category_priority_question_v1(
    question: str,
) -> bool:
    """
    F03 的窄 server-owned compound question contract。

    必须同时出现：
    - 品类粒度；
    - 退款率；
    - 明确的优先关注 / 调查 / 排查 / 处理意图。

    “哪个品类退款率最高”仍走普通 Fact Ranking，
    不会被升级成 Priority Assessment。
    """
    text = re.sub(
        r"\s+",
        "",
        question,
    ).casefold()

    has_category = bool(
        re.search(
            r"(?:各|哪个|哪一个)?(?:品类|类别)",
            text,
        )
    )
    has_refund_rate = "退款率" in text
    has_priority = bool(
        re.search(
            (
                r"(?:最值得|应该|应当)?"
                r"(?:优先|首先)"
                r"(?:关注|调查|排查|处理)"
                r"|"
                r"最值得(?:关注|调查|排查|处理)"
            ),
            text,
        )
    )

    return (
        has_category
        and has_refund_rate
        and has_priority
    )


def _attach_day93_priority_assessment_v1(
    *,
    result: RuntimeDeliveryBridgeResultV2,
    question: str,
) -> RuntimeDeliveryBridgeResultV2:
    if (
        result.status
        != RuntimeDeliveryBridgeStatusV2.READY
        or result.delivery is None
        or result.console_view is None
        or result.console_view.breakdown is None
    ):
        return result

    breakdown_id = (
        result.console_view.breakdown.evidence_id
    )

    priority = build_priority_assessment_v1(
        delivery=result.delivery,
        question=question,
        breakdown_evidence_id=breakdown_id,
    )

    if priority is None:
        return result

    rebuilt_view = build_decision_console_view_v2(
        delivery=result.delivery,
        breakdown_evidence_id=breakdown_id,
        ranking_conclusion=(
            result.console_view.ranking_conclusion
        ),
        priority_assessment=priority,
    )

    return result.model_copy(
        update={
            "console_view": rebuilt_view,
        }
    )


def _run_day93_refund_category_priority_v1(
    *,
    question: str,
    reference_date: date,
    runtime_config: GovernanceRuntimeConfig,
    execution_policy: GovernedExecutionPolicy | None,
) -> RuntimeDeliveryBridgeResultV2 | None:
    """
    F03 的结构化单证据执行入口。

    它只绕过容易把 compound question 判成 MULTIPLE_INTENTS 的
    Natural-language Metric / Grain Planning。

    不绕过：
    - Requested Scope Resolution；
    - Dataset Availability；
    - AccessContext；
    - Governed Planning；
    - SQL Compilation；
    - AST / Execution Policy；
    - Result Protection；
    - Audit / Evidence Delivery。

    当前 V1 只批准 refund_rate_category_v2。
    """
    if not _is_day93_refund_category_priority_question_v1(
        question
    ):
        return None

    requested_scope = resolve_requested_scope_v2(
        question
    )

    if (
        requested_scope.status
        == RequestedScopeResolutionStatusV2
        .UNRESOLVED_EXPLICIT_SCOPE
    ):
        # 交还普通 Graph，让既有 Scope Clarification fail closed。
        return None

    time_resolution = resolve_time_window_v2(
        question,
        reference_date=reference_date,
    )

    if (
        time_resolution.status
        != TimeWindowResolutionStatusV2.RESOLVED
        or time_resolution.effective_start_date is None
        or time_resolution.effective_end_date is None
    ):
        # 时间不明确时不发明 window，继续使用原 Graph 的安全停止逻辑。
        return None

    availability = evaluate_dataset_availability_v2(
        time_resolution=time_resolution
    )

    if (
        availability.outcome
        != DatasetAvailabilityOutcomeV2.AVAILABLE
    ):
        # 交回原 Graph，保持统一 Dataset Boundary 文案。
        return None

    request_id = (
        "day93-f03-priority-"
        f"{uuid4().hex}"
    )

    binding = (
        build_day93_category_refund_rate_tool_binding_v2()
    )

    analysis_window = TimeWindowReferenceV2(
        start_date=time_resolution.effective_start_date,
        end_date=time_resolution.effective_end_date,
    )

    result = invoke_governed_plan_delivery_v2(
        context=build_day89_local_access_context_v2(
            request_id=request_id,
            allow_aggregated_business_metrics=True,
        ),
        plan_name=binding.plan_name,
        analysis_window=analysis_window,
        question=question,
        runtime_config=runtime_config,
        approved_tool_binding=binding,
        requested_scope=requested_scope,
        execution_policy=execution_policy,
        event_id=request_id,
    )

    return _attach_day93_priority_assessment_v1(
        result=result,
        question=question,
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

    f02_result = _run_day93_f02_compound_comparison_v1(
        question=question,
        runtime_config=active_config,
        execution_policy=execution_policy,
    )

    if f02_result is not None:
        return f02_result

    comparison_seed_result = (
        _run_day93_gmv_comparison_seed_investigation_v2(
            question=question,
            runtime_config=active_config,
            execution_policy=execution_policy,
        )
    )

    if comparison_seed_result is not None:
        return comparison_seed_result

    priority_result = (
        _run_day93_refund_category_priority_v1(
            question=question,
            reference_date=reference_date,
            runtime_config=active_config,
            execution_policy=execution_policy,
        )
    )

    if priority_result is not None:
        return priority_result

    request_id = f"day89-console-{uuid4().hex}"

    context = build_day89_local_access_context_v2(
        request_id=request_id,
        allow_aggregated_business_metrics=True,
    )

    channel_binding = build_day89_channel_tool_binding_v2()
    approved_registry = (
        build_day89_business_question_tool_binding_registry_v2()
    )

    return invoke_governed_graph_delivery_v2(
        context=context,
        question=question,
        reference_date=reference_date,
        runtime_config=active_config,
        approved_tool_binding=channel_binding,
        approved_tool_binding_registry=approved_registry,
        execution_policy=execution_policy,
        event_id=request_id,
    )


def _clarification_runtime_stop_v1(
    *,
    resolution: BusinessClarificationResolutionV1,
    stop_stage: str,
    message: str,
    reason_code: str,
) -> RuntimeDeliveryBridgeResultV2:
    """
    Structured Clarification continuation 的安全停止结果。
    """
    grain = resolution.preserved_grain_resolution
    time_resolution = resolution.preserved_time_resolution

    return RuntimeDeliveryBridgeResultV2(
        status=RuntimeDeliveryBridgeStatusV2.GRAPH_STOPPED,
        message=message,
        safe_runtime_result={
            "success": False,
            "outcome": "stopped",
            "stop_stage": stop_stage,
            "message": message,
            "reason_code": reason_code,
            "planning_source": (
                "business_clarification_structured_context"
            ),
            "selected_metric_name": (
                resolution.selected_metric_name
            ),
            "preserved_grain_key": grain.grain_key,
            "preserved_start_date": (
                time_resolution.requested_start_date.isoformat()
                if time_resolution.requested_start_date is not None
                else None
            ),
            "preserved_end_date": (
                time_resolution.requested_end_date.isoformat()
                if time_resolution.requested_end_date is not None
                else None
            ),
        },
    )


def run_day93_business_clarification_continuation_v1(
    *,
    resolution: BusinessClarificationResolutionV1,
    runtime_config: GovernanceRuntimeConfig | None = None,
    execution_policy: GovernedExecutionPolicy | None = None,
) -> RuntimeDeliveryBridgeResultV2:
    """
    普通业务澄清后的结构化恢复 Runtime。

    只补用户选择的 Metric，复用第一次 Clarification Stop 时冻结的：
    - Time Resolution；
    - Requested Scope；
    - Result Grain。

    不再从 resolved_question 重跑 Semantic / Grain / Time NLP。

    仍完整经过：
    Query Plan Selection
    -> Approved Tool Binding
    -> Governed Planning
    -> Compilation
    -> AST recheck
    -> SQL Execution
    -> Result Protection
    -> Audit / Evidence / Delivery
    """
    time_resolution = resolution.preserved_time_resolution

    if (
        time_resolution.status
        != TimeWindowResolutionStatusV2.RESOLVED
        or time_resolution.effective_start_date is None
        or time_resolution.effective_end_date is None
    ):
        return _clarification_runtime_stop_v1(
            resolution=resolution,
            stop_stage="time_resolution",
            reason_code="clarification_time_not_resolved",
            message=(
                "评价指标已经确认，但原问题的时间范围仍不够明确。"
                "请补充具体时间后再继续。"
            ),
        )

    availability = evaluate_dataset_availability_v2(
        time_resolution=time_resolution
    )

    if (
        availability.outcome
        != DatasetAvailabilityOutcomeV2.AVAILABLE
    ):
        return _clarification_runtime_stop_v1(
            resolution=resolution,
            stop_stage="dataset_availability",
            reason_code=(
                availability.reason_code
                or "clarification_dataset_unavailable"
            ),
            message=(
                availability.user_message
                or "原问题的时间范围当前没有可查询数据。"
            ),
        )

    selection = select_query_plan_v2(
        metric_name=resolution.selected_metric_name,
        grain_resolution=(
            resolution.preserved_grain_resolution
        ),
    )

    if (
        selection.status
        != QueryPlanSelectionStatusV2.MATCHED
        or len(selection.plan_names) != 1
    ):
        return _clarification_runtime_stop_v1(
            resolution=resolution,
            stop_stage="structured_plan_preflight",
            reason_code="clarification_plan_not_unique",
            message=(
                "评价指标已经确认，但当前 Metric / 维度组合"
                "还没有唯一可执行的查询计划。"
            ),
        )

    plan_name = selection.plan_names[0]

    primary_binding = build_day89_channel_tool_binding_v2()
    registry = (
        build_day89_business_question_tool_binding_registry_v2()
    )

    approved_binding = _select_approved_tool_binding_for_plan_v2(
        actual_plan_name=plan_name,
        primary_binding=primary_binding,
        approved_tool_binding_registry=registry,
    )

    if approved_binding is None:
        return _clarification_runtime_stop_v1(
            resolution=resolution,
            stop_stage="approved_tool_binding",
            reason_code="clarification_plan_not_approved",
            message=(
                "这个指标与分析维度已经识别，但当前还没有"
                "正式批准对应的受治理查询能力。"
            ),
        )

    active_config = (
        runtime_config
        if runtime_config is not None
        else load_governance_runtime_config()
    )

    request_id = (
        "day93-business-clarification-"
        f"{uuid4().hex}"
    )

    analysis_window = TimeWindowReferenceV2(
        start_date=time_resolution.effective_start_date,
        end_date=time_resolution.effective_end_date,
    )

    return invoke_governed_plan_delivery_v2(
        context=build_day89_local_access_context_v2(
            request_id=request_id,
            allow_aggregated_business_metrics=True,
        ),
        plan_name=plan_name,
        analysis_window=analysis_window,
        question=resolution.resolved_question,
        runtime_config=active_config,
        approved_tool_binding=approved_binding,
        requested_scope=(
            resolution.preserved_requested_scope
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
        requested_scope=primary_result.requested_scope,
        execution_policy=execution_policy,
        event_id=request_id,
    )

    return build_trusted_breakdown_summary_v2(
        primary_result=primary_result,
        overall_result=overall_result,
    )
