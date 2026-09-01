from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict

from app.semantic_layer.analysis_mode_contract_v2 import (
    AnalysisModeV2,
)


ANALYSIS_MODE_RULE_VERSION_V2 = "analysis_mode_rules_v2_0"


class AnalysisModeResolutionV2(BaseModel):
    """
    对用户原始业务问题的高精度、确定性分析模式解析结果。

    这里只判断“用户希望系统做到哪一层分析”，不负责：
    - 指标识别；
    - Requested Scope 解析；
    - Grain / Query Plan 选择；
    - SQL 生成或执行；
    - 权限判断。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    analysis_mode: AnalysisModeV2
    matched_signals: tuple[str, ...] = ()
    rule_version: str = ANALYSIS_MODE_RULE_VERSION_V2


def _normalize_question_v2(question: str) -> str:
    return re.sub(
        r"\s+",
        "",
        str(question),
    ).casefold()


_INVESTIGATION_SIGNALS_V2 = (
    "最值得",
    "优先关注",
    "优先处理",
    "优先调查",
    "优先检查",
    "应该先",
    "先看哪个",
    "先查哪个",
    "先调查哪个",
    "下一步",
    "怎么处理",
    "如何处理",
    "应该怎么做",
    "表现最好",
    "表现最差",
    "最佳",
    "最优",
)

_DIAGNOSTIC_SIGNALS_V2 = (
    "为什么",
    "为何",
    "原因",
    "导致",
    "驱动",
    "拖累",
    "拉动",
    "变化贡献",
    "贡献了多少变化",
    "异常原因",
    "是否异常",
    "哪里异常",
)

_COMPARISON_SIGNALS_V2 = (
    "环比",
    "同比",
    "相比",
    "对比",
    "较上",
    "较前",
    "比上",
    "比前",
    "增长了多少",
    "下降了多少",
    "变化了多少",
)

_COMPOSITION_SIGNALS_V2 = (
    "构成",
    "组成",
    "主要来自",
    "来源于",
    "占比",
    "占多少",
    "结构",
    "集中度",
    "分布",
)


def _matched_signals_v2(
    normalized_question: str,
    signals: tuple[str, ...],
) -> tuple[str, ...]:
    return tuple(
        signal
        for signal in signals
        if signal in normalized_question
    )


def resolve_analysis_mode_v2(
    question: str,
) -> AnalysisModeResolutionV2:
    """
    用保守优先级识别 Requested Analysis Mode。

    优先级：
    INVESTIGATION > DIAGNOSTIC > COMPARISON > COMPOSITION > FACT。

    例如：
    - “上海 GMV 是多少” -> FACT；
    - “上海 GMV 主要来自哪些渠道” -> COMPOSITION；
    - “10 月相比 9 月怎么样” -> COMPARISON；
    - “为什么下降” -> DIAGNOSTIC；
    - “最值得先看哪个渠道” -> INVESTIGATION。

    规则只在有明确语言信号时升级分析深度；
    没有充分证据时默认 FACT，避免系统静默扩大任务。
    """

    normalized = _normalize_question_v2(question)

    for mode, signals in (
        (
            AnalysisModeV2.INVESTIGATION,
            _INVESTIGATION_SIGNALS_V2,
        ),
        (
            AnalysisModeV2.DIAGNOSTIC,
            _DIAGNOSTIC_SIGNALS_V2,
        ),
        (
            AnalysisModeV2.COMPARISON,
            _COMPARISON_SIGNALS_V2,
        ),
        (
            AnalysisModeV2.COMPOSITION,
            _COMPOSITION_SIGNALS_V2,
        ),
    ):
        matched = _matched_signals_v2(
            normalized,
            signals,
        )
        if matched:
            return AnalysisModeResolutionV2(
                analysis_mode=mode,
                matched_signals=matched,
            )

    return AnalysisModeResolutionV2(
        analysis_mode=AnalysisModeV2.FACT,
        matched_signals=(),
    )
