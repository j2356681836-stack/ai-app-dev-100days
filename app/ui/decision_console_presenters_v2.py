from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.agents.evidence_pack_delivery_v2 import (
    EvidenceSufficiencyStatusV2,
)
from app.delivery.fact_composition_delivery_v2 import (
    FactCompositionResultV2,
)
from app.delivery.periodic_business_report_v2 import (
    PeriodicBusinessReportStatusV2,
    PeriodicMetricDisplayKindV2,
    PeriodicMetricSectionV2,
    PeriodicMetricSnapshotV2,
    PeriodicMetricStatusV2,
)


METRIC_DISPLAY_NAME_V2 = {
    "gmv": "GMV",
    "roi": "ROI",
    "cac": "CAC",
    "order_count": "订单数",
    "buyer_count": "购买人数",
    "refund_rate": "退款率",
    "refund_amount": "退款金额",
    "spending_per_buyer": "每客消费额",
    "purchase_frequency": "购买频次",
    "repeat_customer_rate": "复购率",
    "member_gmv_share": "会员GMV贡献率",
    "units_sold": "交易件数",
    "repeat_customer_count": "复购客户数",
    "multi_order_customer_count": "多订单客户数",
    "brand_paid_new_customer_count": "品牌付费新客数",
    "channel_paid_new_customer_count": "渠道付费新客数",
    "r12_base_customer_count": "R12 Base客户数",
    "r12_repurchase_customer_count": "R12回购客户数",
}


def format_metric_name_v2(metric_name: str | None) -> str:
    if metric_name is None:
        return "-"

    normalized = metric_name.strip().lower()
    return METRIC_DISPLAY_NAME_V2.get(
        normalized,
        metric_name,
    )


FACT_COUNT_METRIC_NAMES_V2 = frozenset(
    {
        "order_count",
        "buyer_count",
        "units_sold",
        "repeat_customer_count",
        "multi_order_customer_count",
        "brand_paid_new_customer_count",
        "channel_paid_new_customer_count",
        "r12_base_customer_count",
        "r12_repurchase_customer_count",
    }
)


def format_fact_metric_value_v2(
    metric_name: str,
    value: Any,
) -> Any:
    """
    Fact scalar 的 metric-aware 展示语义。

    COUNT 是离散业务量，不能因为底层统一使用 Decimal 就展示两位小数。
    其他 Metric 暂时保持既有数值格式，避免在本修复中重定义 ratio/money。
    """

    if metric_name.strip().lower() in FACT_COUNT_METRIC_NAMES_V2:
        if isinstance(value, (Decimal, int, float)):
            return f"{Decimal(str(value)):,.0f}"

    return format_number_v2(value)


def format_evidence_sufficiency_v2(
    value: EvidenceSufficiencyStatusV2 | str | None,
) -> str:
    if value is None:
        return "-"
    raw = value.value if hasattr(value, "value") else str(value)
    mapping = {
        "sufficient_for_current_scope": "当前范围证据充分",
        "partial": "部分充分",
        "insufficient": "证据不足",
        "no_data": "无数据",
        "unsupported": "暂不支持",
        "not_evaluated": "未评估",
    }
    return mapping.get(raw, raw)


def format_runtime_status_v2(value: str | None) -> str:
    if value is None:
        return "-"
    mapping = {
        "ready": "已生成交付结果",
        "graph_stopped": "流程停止",
        "invalid_runtime_state": "运行时状态无效",
        "evidence_build_failed": "证据构建失败",
    }
    return mapping.get(value, value)


def format_evidence_type_v2(value: str | None) -> str:
    if value is None:
        return "-"
    mapping = {
        "governed_query_result": "受治理查询结果",
        "anomaly_decision": "异常判断",
        "contribution_result": "贡献度分析",
        "investigation_observation": "调查观察结果",
    }
    return mapping.get(value, value)


def format_number_v2(value: Any) -> Any:
    if isinstance(value, Decimal):
        return f"{value:,.2f}"
    if isinstance(value, float):
        return f"{value:,.2f}"
    return value


def normalize_scope_summary_v2(
    scope_summary: str | None,
    *,
    preview_limit: int = 120,
) -> tuple[str | None, str | None]:
    if not scope_summary:
        return None, None

    text = " ".join(scope_summary.split())
    if len(text) <= preview_limit:
        return text, text

    return text[:preview_limit] + "...", text


def format_statement_v2(text: str) -> str:
    cleaned = " ".join(text.split())
    return cleaned.replace("；", "；  \n")


def _breakdown_business_column_label_v2(
    key: str,
) -> str:
    """
    把 Runtime / Protected Result 的内部字段名转换成业务展示名。

    这里只做展示投影，不改变 Protected Result 字段和业务真值。
    """
    dimension_mapping = {
        "channel_name": "渠道",
        "region_name": "地区",
        "category_name": "品类",
        "member_level": "会员层级",
        "membership_level": "会员层级",
    }

    if key in dimension_mapping:
        return dimension_mapping[key]

    normalized = key.strip().lower()

    if normalized in METRIC_DISPLAY_NAME_V2:
        return format_metric_name_v2(normalized)

    return key


def _format_breakdown_business_value_v2(
    *,
    key: str,
    value: Any,
) -> Any:
    normalized = key.strip().lower()

    if normalized in METRIC_DISPLAY_NAME_V2:
        return format_business_metric_value_v2(
            normalized,
            value,
        )

    return format_number_v2(value)


RATIO_METRIC_NAMES_V2 = frozenset(
    {
        "refund_rate",
        "repeat_customer_rate",
        "member_gmv_share",
        "gross_margin_rate",
        "r12_repurchase_rate",
    }
)


def format_business_metric_value_v2(
    metric_name: str,
    value: Any,
) -> Any:
    normalized = metric_name.strip().lower()

    if normalized in FACT_COUNT_METRIC_NAMES_V2:
        return format_fact_metric_value_v2(
            normalized,
            value,
        )

    if normalized in RATIO_METRIC_NAMES_V2:
        if isinstance(value, (Decimal, int, float)):
            return format_percentage_v2(
                Decimal(str(value))
            )

    return format_number_v2(value)


def format_result_grain_name_v2(
    result_grain: str | None,
) -> str:
    if result_grain is None:
        return "维度"

    return {
        "channel": "渠道",
        "region": "地区",
        "category": "品类",
        "membership_level": "会员层级",
        "overall": "整体",
    }.get(result_grain, result_grain)


def build_display_rows_v2(
    rows: tuple[dict[str, Any], ...],
) -> list[dict[str, Any]]:
    """
    Protected Breakdown 的业务展示投影。

    内部 identifier 继续保留在 Runtime Contract；
    Business View 统一显示中文业务名称。
    """
    result: list[dict[str, Any]] = []

    for row in rows:
        result.append(
            {
                _breakdown_business_column_label_v2(key): (
                    _format_breakdown_business_value_v2(
                        key=key,
                        value=value,
                    )
                )
                for key, value in row.items()
            }
        )

    return result


def build_chart_rows_v2(
    rows: tuple[dict[str, Any], ...],
) -> list[dict[str, float | str]]:
    """
    当前 Business Breakdown 的渠道图表投影。

    只支持已经明确注册的单一渠道指标；
    页面不重新计算聚合值。
    """
    if not rows:
        return []

    supported_metric_names = (
        "gmv",
        "order_count",
        "buyer_count",
    )

    metric_name = next(
        (
            name
            for name in supported_metric_names
            if name in rows[0]
        ),
        None,
    )

    if metric_name is None:
        return []

    metric_label = format_metric_name_v2(
        metric_name
    )

    result: list[dict[str, float | str]] = []

    for row in rows:
        channel = row.get("channel_name")
        value = row.get(metric_name)

        if channel is None or value is None:
            continue

        if isinstance(value, Decimal):
            value = float(value)

        result.append(
            {
                "渠道": str(channel),
                metric_label: float(value),
            }
        )

    return result



def format_percentage_v2(
    value: Decimal | None,
) -> str:
    """
    Decimal ratio -> percentage string，仅做展示格式转换。
    """
    if value is None:
        return "未定义"

    return f"{value * Decimal('100'):,.2f}%"


def append_trusted_summary_row_v2(
    *,
    display_rows: list[dict[str, Any]],
    metric_name: str,
    summary_value: Decimal,
) -> list[dict[str, Any]]:
    """
    把 server-trusted Overall value 作为“汇总”展示行追加到表格。

    不对 display_rows 做 sum / average。
    """

    if not display_rows:
        return display_rows

    metric_label = format_metric_name_v2(metric_name)
    columns = tuple(display_rows[0].keys())

    dimension_columns = tuple(
        column
        for column in columns
        if column != metric_label
    )

    if len(dimension_columns) != 1:
        return display_rows

    summary_row = {
        dimension_columns[0]: "汇总",
        metric_label: format_fact_metric_value_v2(
            metric_name,
            summary_value,
        ),
    }

    return [*display_rows, summary_row]


def format_investigation_action_v2(value: str | None) -> str:
    if value is None:
        return "-"
    mapping = {
        "drill_channel": "检查渠道维度",
        "drill_region": "检查区域维度",
    }
    return mapping.get(value, value)


def format_observation_status_v2(value: str | None) -> str:
    if value is None:
        return "-"
    mapping = {
        "evidence": "已获得新证据",
        "no_data": "当前范围无数据",
        "failure": "执行失败",
    }
    return mapping.get(value, value)


def format_loop_directive_v2(value: str | None) -> str:
    if value is None:
        return "-"
    mapping = {
        "retry": "重试当前动作",
        "replan": "重新规划下一步",
        "recover": "切换合法替代路径",
        "stop": "停止本轮调查",
    }
    return mapping.get(value, value)


def format_stop_reason_v2(value: str | None) -> str:
    if value is None:
        return "-"
    mapping = {
        "evidence_sufficient": "当前范围证据已充分",
        "investigation_budget_exhausted": "本轮调查预算已耗尽",
        "no_legal_action": "当前没有剩余合法调查动作",
        "retry_budget_exhausted": "当前动作重试预算已耗尽",
        "non_retryable_failure": "发生不可重试失败",
    }
    return mapping.get(value, value)


def format_contribution_direction_v2(value: str | None) -> str:
    if value is None:
        return "-"
    mapping = {
        "negative": "负向",
        "neutral": "持平",
        "positive": "正向",
    }
    return mapping.get(value, value)


def format_reconciliation_status_v2(value: str | None) -> str:
    if value is None:
        return "-"
    mapping = {
        "reconciled": "已对账",
        "not_reconciled": "未完全对账",
    }
    return mapping.get(value, value)


def build_contribution_display_rows_v2(
    contribution,
) -> list[dict[str, Any]]:
    """
    只展示 Contribution 的业务必要字段。

    正负方向已经由变化额 / 贡献率符号表达，
    不再单独投影 direction，避免重复信息和横向空间浪费。
    """

    return [
        {
            "渠道": member.member_label,
            "参考期 GMV": format_number_v2(member.reference_value),
            "当前期 GMV": format_number_v2(member.current_value),
            "变化额": format_number_v2(member.delta),
            "占整体GMV增量": (
                format_percentage_v2(member.contribution_rate)
            ),
        }
        for member in contribution.members
    ]


def build_contribution_chart_rows_v2(
    contribution,
) -> list[dict[str, float | str]]:
    """
    Chart 直接使用 Day84 ContributionMemberViewV2.delta。
    UI 不从 current/reference 重新做减法。
    """

    return [
        {
            "渠道": member.member_label,
            "GMV变化额": float(member.delta),
        }
        for member in contribution.members
        if member.delta != 0
    ]


def format_periodic_report_status_v2(
    status: PeriodicBusinessReportStatusV2 | str,
) -> str:
    raw = status.value if hasattr(status, "value") else str(status)

    return {
        "ready": "全部指标已就绪",
        "partial_ready": "核心指标已就绪，部分扩展指标不可释放",
        "not_ready": "核心指标未就绪",
    }.get(raw, raw)


def format_periodic_section_v2(
    section: PeriodicMetricSectionV2 | str,
) -> str:
    raw = section.value if hasattr(section, "value") else str(section)

    return {
        "overview": "经营概览",
        "sales_driver": "销售驱动",
        "customer_health": "客户健康",
    }.get(raw, raw)


def format_periodic_metric_value_v2(
    snapshot: PeriodicMetricSnapshotV2,
    *,
    reference: bool = False,
) -> str:
    """
    只格式化 PeriodicMetricSnapshotV2 已释放的可信数值。

    NOT_READY 不使用 0 / '-' 冒充业务真值，而是明确显示不可释放。
    """

    if snapshot.status != PeriodicMetricStatusV2.READY:
        return "不可释放"

    value = (
        snapshot.reference_value
        if reference
        else snapshot.current_value
    )

    if value is None:
        return "不可释放"

    kind = snapshot.spec.display_kind

    if kind == PeriodicMetricDisplayKindV2.RATIO:
        return format_percentage_v2(value)

    if kind == PeriodicMetricDisplayKindV2.COUNT:
        return f"{value:,.0f}"

    if kind == PeriodicMetricDisplayKindV2.MONEY:
        return format_number_v2(value)

    return f"{value:,.2f}"


def format_periodic_metric_delta_v2(
    snapshot: PeriodicMetricSnapshotV2,
) -> str | None:
    """
    KPI Card 的参考期变化标签。

    Ratio 用 percentage point，避免把百分点变化与相对变化率混淆。
    其他指标使用 relative_change。
    """

    if snapshot.status != PeriodicMetricStatusV2.READY:
        return None

    if (
        snapshot.spec.display_kind
        == PeriodicMetricDisplayKindV2.RATIO
    ):
        pp = snapshot.percentage_point_change

        if pp is None:
            return None

        sign = "+" if pp > 0 else ""
        return f"{sign}{pp:,.2f} pp vs 参考期"

    relative = snapshot.relative_change

    if relative is None:
        return None

    sign = "+" if relative > 0 else ""
    return f"{sign}{relative * Decimal('100'):,.2f}% vs 参考期"



def format_periodic_metric_delta_inline_v2(
    snapshot: PeriodicMetricSnapshotV2,
) -> str | None:
    """
    Periodic KPI Card 的紧凑变化幅度。

    只消费 Delivery 已经提供的 relative_change /
    percentage_point_change，不在 UI 重新计算业务变化。
    """

    if snapshot.status != PeriodicMetricStatusV2.READY:
        return None

    if (
        snapshot.spec.display_kind
        == PeriodicMetricDisplayKindV2.RATIO
    ):
        pp = snapshot.percentage_point_change

        if pp is None:
            return None

        arrow = "↑" if pp > 0 else "↓" if pp < 0 else "→"
        return f"{arrow} {abs(pp):,.2f} pp"

    relative = snapshot.relative_change

    if relative is None:
        return None

    percent = relative * Decimal("100")
    arrow = "↑" if percent > 0 else "↓" if percent < 0 else "→"
    return f"{arrow} {abs(percent):,.2f}%"


def periodic_metric_delta_direction_v2(
    snapshot: PeriodicMetricSnapshotV2,
) -> str:
    """
    仅返回数学方向：up / down / neutral / unavailable。

    不把“上升”解释成业务利好，也不把“下降”解释成业务利空。
    """

    if snapshot.status != PeriodicMetricStatusV2.READY:
        return "unavailable"

    if (
        snapshot.spec.display_kind
        == PeriodicMetricDisplayKindV2.RATIO
    ):
        value = snapshot.percentage_point_change
    else:
        value = snapshot.relative_change

    if value is None or value == 0:
        return "neutral"

    return "up" if value > 0 else "down"

def build_periodic_metric_comparison_rows_v2(
    metrics: tuple[PeriodicMetricSnapshotV2, ...],
) -> list[dict[str, Any]]:
    """
    用于 Trust/Verification 展示。

    不在 UI 重新计算 delta / relative change。
    """

    rows: list[dict[str, Any]] = []

    for snapshot in metrics:
        if snapshot.status == PeriodicMetricStatusV2.READY:
            if (
                snapshot.spec.display_kind
                == PeriodicMetricDisplayKindV2.RATIO
            ):
                change = (
                    f"{snapshot.percentage_point_change:,.2f} pp"
                    if snapshot.percentage_point_change is not None
                    else "未定义"
                )
            else:
                change = (
                    format_percentage_v2(snapshot.relative_change)
                    if snapshot.relative_change is not None
                    else "未定义"
                )
        else:
            change = "不可释放"

        rows.append(
            {
                "模块": format_periodic_section_v2(
                    snapshot.spec.section
                ),
                "指标": snapshot.spec.chinese_name,
                "参考期": format_periodic_metric_value_v2(
                    snapshot,
                    reference=True,
                ),
                "当前期": format_periodic_metric_value_v2(snapshot),
                "变化": change,
                "状态": (
                    "已就绪"
                    if snapshot.status
                    == PeriodicMetricStatusV2.READY
                    else "不可释放"
                ),
            }
        )

    return rows


R12_PERIODIC_METRIC_NAMES_V2: tuple[str, ...] = (
    "r12_base_customer_count",
    "r12_repurchase_customer_count",
    "r12_repurchase_rate",
    "r12_repurchase_amount",
    "r12_repurchase_spending",
)


def format_periodic_r12_runtime_status_v2(
    value: str | None,
) -> str:
    if value is None:
        return "-"

    return {
        "ready": "5 个 R12 客户指标均已就绪",
        "partial_ready": "部分 R12 客户指标已就绪",
        "not_ready": "R12 客户指标当前不可计算",
    }.get(value, value)


def format_periodic_r12_readiness_status_v2(
    value: str | None,
) -> str:
    if value is None:
        return "-"

    return {
        "ready": "历史与退款观察均完整",
        "insufficient_history": "R12 历史不足",
        "outside_business_window": "超出正式业务数据窗口",
        "refund_observation_incomplete": "退款观察窗口尚未完整",
        "invalid_dataset_contract": "数据集观察合同未准备好",
    }.get(value, value)


def format_periodic_r12_reconciliation_status_v2(
    value: str | None,
) -> str:
    if value is None:
        return "-"

    return {
        "reconciled": "已对账",
        "not_reconciled": "未完全对账",
        "not_available": "当前不可验证",
    }.get(value, value)


def build_periodic_r12_readiness_rows_v2(
    report,
) -> list[dict[str, Any]]:
    """
    R12 Readiness 的纯展示投影。

    只消费 PeriodicBusinessReportV2.r12_customer_health，
    不重新计算 Base Window 或 Refund Observation。
    """

    trust = getattr(
        report,
        "r12_customer_health",
        None,
    )

    if trust is None:
        return []

    return [
        {
            "窗口": "当前期",
            "报表窗口": (
                f"{trust.current_readiness.report_window.start_date}"
                " → "
                f"{trust.current_readiness.report_window.end_date}"
            ),
            "R12 Base": (
                f"{trust.current_readiness.base_window.start_date}"
                " → "
                f"{trust.current_readiness.base_window.end_date}"
            ),
            "Readiness": (
                format_periodic_r12_readiness_status_v2(
                    trust.current_readiness.status.value
                )
            ),
        },
        {
            "窗口": "参考期",
            "报表窗口": (
                f"{trust.reference_readiness.report_window.start_date}"
                " → "
                f"{trust.reference_readiness.report_window.end_date}"
            ),
            "R12 Base": (
                f"{trust.reference_readiness.base_window.start_date}"
                " → "
                f"{trust.reference_readiness.base_window.end_date}"
            ),
            "Readiness": (
                format_periodic_r12_readiness_status_v2(
                    trust.reference_readiness.status.value
                )
            ),
        },
    ]


def build_periodic_r12_reconciliation_rows_v2(
    report,
) -> list[dict[str, Any]]:
    """
    R12 deterministic reconciliation 的纯展示投影。

    remainder 仅格式化已有可信值；不在 UI 重新计算 identity。
    """

    trust = getattr(
        report,
        "r12_customer_health",
        None,
    )

    if trust is None:
        return []

    return [
        {
            "验证关系": item.relationship,
            "状态": (
                format_periodic_r12_reconciliation_status_v2(
                    item.status.value
                )
            ),
            "差额": (
                format_number_v2(item.remainder)
                if item.remainder is not None
                else "不可验证"
            ),
        }
        for item in trust.reconciliations
    ]


def _fact_composition_member_label_v2(
    *,
    result: FactCompositionResultV2,
    raw_label: str,
) -> str:
    payment_membership_mapping = {
        "NON_MEMBER": "非会员",
        "Bronze": "青铜会员",
        "Silver": "白银会员",
        "Gold": "黄金会员",
        "Platinum": "铂金会员",
        "bronze": "青铜会员",
        "silver": "白银会员",
        "gold": "黄金会员",
        "platinum": "铂金会员",
    }

    order_customer_mapping = {
        "OLD_PLATINUM": "老客｜铂金会员",
        "OLD_GOLD": "老客｜黄金会员",
        "OLD_SILVER": "老客｜白银会员",
        "OLD_BRONZE": "老客｜青铜会员",
        "OLD_NON_MEMBER": "老客｜非会员",
        "NEW_CUSTOMER": "新客",
    }

    if (
        result.metric_name == "order_count"
        and result.dimension.value == "membership_level"
    ):
        return order_customer_mapping.get(
            raw_label,
            raw_label,
        )

    if result.dimension.value == "membership_level":
        return payment_membership_mapping.get(
            raw_label,
            raw_label,
        )

    return raw_label


def build_fact_composition_display_rows_v2(
    result: FactCompositionResultV2,
) -> list[dict[str, Any]]:
    """
    只格式化 Delivery 已经计算完成的 Composition。

    成员行来自 Protected Result；
    最后一行“汇总”直接使用 Delivery 的 Trusted Overall，
    不对可见成员行重新求和。
    """

    dimension_label = {
        "membership_level": (
            "客户构成"
            if result.metric_name == "order_count"
            else "会员层级"
        ),
        "channel": "渠道",
        "region": "地区",
        "category": "品类",
    }[result.dimension.value]

    metric_label = format_metric_name_v2(
        result.metric_name
    )

    rows = [
        {
            "排名": member.rank,
            dimension_label: (
                _fact_composition_member_label_v2(
                    result=result,
                    raw_label=member.member_label,
                )
            ),
            metric_label: format_fact_metric_value_v2(
                result.metric_name,
                member.value,
            ),
            "构成占比": format_percentage_v2(member.share),
        }
        for member in result.members
    ]

    if result.overall_value is not None:
        rows.append(
            {
                "排名": "",
                dimension_label: "汇总",
                metric_label: format_fact_metric_value_v2(
                    result.metric_name,
                    result.overall_value,
                ),
                "构成占比": (
                    "100.00%"
                    if result.overall_value != 0
                    else "未定义"
                ),
            }
        )

    return rows


def build_fact_composition_chart_rows_v2(
    result: FactCompositionResultV2,
) -> list[dict[str, float | str]]:
    """
    图表只消费 Composition Member 的可信 value。
    Trusted Overall 汇总行不会进入图表。
    """

    metric_label = format_metric_name_v2(
        result.metric_name
    )

    return [
        {
            "成员": (
                _fact_composition_member_label_v2(
                    result=result,
                    raw_label=member.member_label,
                )
            ),
            metric_label: float(member.value),
        }
        for member in result.members
    ]
