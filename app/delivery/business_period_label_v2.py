from __future__ import annotations

from calendar import monthrange

from app.semantic_layer.time_comparison_contract_v2 import (
    TimeWindowReferenceV2,
)


def format_business_period_label_v2(
    window: TimeWindowReferenceV2,
) -> str:
    """
    Business-facing period label.

    完整自然月显示为“2025年10月”；
    其他窗口保留明确日期范围，避免用“当前期 / 参考期”
    让用户再次做时间映射。
    """

    start = window.start_date
    end = window.end_date

    if (
        start.year == end.year
        and start.month == end.month
        and start.day == 1
        and end.day == monthrange(end.year, end.month)[1]
    ):
        return f"{start.year}年{start.month}月"

    if start == end:
        return start.isoformat()

    return f"{start.isoformat()} 至 {end.isoformat()}"
