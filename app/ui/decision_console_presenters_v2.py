from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.agents.evidence_pack_delivery_v2 import (
    EvidenceSufficiencyStatusV2,
)


def format_metric_name_v2(metric_name: str | None) -> str:
    if metric_name is None:
        return "-"
    mapping = {
        "gmv": "GMV",
        "roi": "ROI",
        "cac": "CAC",
    }
    return mapping.get(metric_name.lower(), metric_name.upper())


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


def build_display_rows_v2(
    rows: tuple[dict[str, Any], ...],
) -> list[dict[str, Any]]:
    key_mapping = {
        "channel_name": "渠道",
        "gmv": "GMV",
    }
    result: list[dict[str, Any]] = []

    for row in rows:
        result.append(
            {
                key_mapping.get(key, key): format_number_v2(value)
                for key, value in row.items()
            }
        )

    return result


def build_chart_rows_v2(
    rows: tuple[dict[str, Any], ...],
) -> list[dict[str, float | str]]:
    result: list[dict[str, float | str]] = []

    for row in rows:
        channel = row.get("channel_name")
        gmv = row.get("gmv")

        if channel is None or gmv is None:
            continue

        if isinstance(gmv, Decimal):
            gmv = float(gmv)

        result.append(
            {
                "渠道": str(channel),
                "GMV": float(gmv),
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
        metric_label: format_number_v2(summary_value),
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
    只消费 DecisionConsoleViewV2.contribution 已计算完成的可信结果。
    不重新计算 delta / contribution_rate。
    """

    return [
        {
            "渠道": member.member_label,
            "本期 GMV": format_number_v2(member.current_value),
            "上期 GMV": format_number_v2(member.reference_value),
            "变化额": format_number_v2(member.delta),
            "对整体变化贡献率": (
                format_percentage_v2(member.contribution_rate)
            ),
            "方向": format_contribution_direction_v2(
                member.direction.value
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
