from __future__ import annotations

from enum import Enum


class AnalysisModeV2(str, Enum):
    """
    用户业务问题希望得到的分析深度。

    注意：
    - 这是 Requested Analysis Mode，不等同于某一次 Query Delivery 的形态；
    - 单次 Governed Query 仍可以只形成 FACT Evidence；
    - 只有 DIAGNOSTIC / INVESTIGATION 允许进入 Agentic Investigation。
    """

    FACT = "fact"
    COMPOSITION = "composition"
    COMPARISON = "comparison"
    DIAGNOSTIC = "diagnostic"
    INVESTIGATION = "investigation"


AGENTIC_ANALYSIS_MODES_V2 = frozenset(
    {
        AnalysisModeV2.DIAGNOSTIC,
        AnalysisModeV2.INVESTIGATION,
    }
)


def analysis_mode_allows_agentic_v2(
    analysis_mode: AnalysisModeV2,
) -> bool:
    """
    返回当前 Requested Analysis Mode 是否允许进入 Agentic 调查。

    这是产品/运行时能力边界，不是权限边界。
    AccessContext / Governance 仍负责真正的数据访问授权。
    """

    return analysis_mode in AGENTIC_ANALYSIS_MODES_V2
