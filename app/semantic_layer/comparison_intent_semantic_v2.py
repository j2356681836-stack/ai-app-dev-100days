from __future__ import annotations

import calendar
import json
import re
from datetime import date
from enum import Enum

from pydantic import BaseModel, ConfigDict

from app.llm.deepseek_client import chat_completion
from app.semantic_layer.analysis_mode_contract_v2 import (
    AnalysisModeV2,
)
from app.semantic_layer.question_semantic_parser_v2 import (
    LLMCall,
)


DAY94_COMPARISON_INTENT_SEMANTIC_VERSION = (
    "day94_comparison_intent_semantic_v2_0"
)


class ComparisonIntentSemanticStatusV2(str, Enum):
    READY = "ready"
    NOT_APPLICABLE = "not_applicable"
    PARSE_FAILED = "parse_failed"
    VALIDATION_FAILED = "validation_failed"


class LLMComparisonIntentPayloadV2(BaseModel):
    """
    LLM staging payload。

    只允许做自然语言归一化：
    - 明确指标；
    - 当前月 / 参考月的语义角色；
    - 用户只要求比较，还是还明确要求继续调查。

    它不是执行合同。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    metric_name: str | None = None
    analysis_mode: AnalysisModeV2 | None = None

    current_year: int | None = None
    current_month: int | None = None
    reference_year: int | None = None
    reference_month: int | None = None


class ComparisonIntentSemanticResultV2(BaseModel):
    """
    LLM + deterministic validation 后的安全 Comparison Intent。

    READY 才允许进入后续 deterministic comparison builder。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    contract_version: str = (
        DAY94_COMPARISON_INTENT_SEMANTIC_VERSION
    )

    status: ComparisonIntentSemanticStatusV2
    analysis_mode: AnalysisModeV2 | None = None

    current_anchor_date: date | None = None
    reference_anchor_date: date | None = None

    source: str
    detail: str | None = None


def build_comparison_intent_semantic_prompt_v2(
    question: str,
) -> str:
    return f"""
你是“分析意图语义归一化器”，不是 SQL 生成器，也不是指标计算器。

只处理用户原句中的“GMV 月度比较 / 后续调查意图”。

你的职责：
1. 判断用户是否明确在问 GMV。
2. 不依赖中文语序，识别哪个月份是 current、哪个月份是 reference。
3. 判断用户只是要比较（comparison），还是在比较后还明确要求：
   - 继续调查；
   - 建议下一步看哪里；
   - 找最值得优先看的方向；
   - 判断后续应从什么方向分析。
   这类请求统一归一化为 investigation。
4. 如果只是问“相比如何 / 差多少 / 涨跌多少”，归一化为 comparison。
5. 不生成 grain、scope、query plan、SQL 或业务原因。
6. 不要补用户没有表达的月份。
7. 如果 reference 月份没有写年份，但从 current 年月与相邻月关系可以唯一确定，
   可以填入对应年份。
8. 无法可靠确定的字段返回 null。

只输出下面 6 个字段的 JSON，不要解释：
{{
  "metric_name": "gmv",
  "analysis_mode": "comparison",
  "current_year": 2025,
  "current_month": 10,
  "reference_year": 2025,
  "reference_month": 9
}}

analysis_mode 只允许：
- "comparison"
- "investigation"
- null

用户问题：
{question}
""".strip()


def _extract_json_object_text_v2(
    text: str,
) -> str:
    cleaned = str(text).strip()

    if cleaned.startswith("```json"):
        cleaned = cleaned[len("```json"):].strip()

    if cleaned.startswith("```"):
        cleaned = cleaned[3:].strip()

    if cleaned.endswith("```"):
        cleaned = cleaned[:-3].strip()

    start = cleaned.find("{")
    end = cleaned.rfind("}")

    if start == -1 or end == -1 or end <= start:
        raise ValueError(
            "Comparison Intent LLM response does not contain one JSON object."
        )

    return cleaned[start:end + 1]


def _parse_payload_v2(
    raw_text: str,
) -> LLMComparisonIntentPayloadV2:
    payload = json.loads(
        _extract_json_object_text_v2(raw_text)
    )

    if not isinstance(payload, dict):
        raise ValueError(
            "Comparison Intent payload must be a JSON object."
        )

    required = {
        "metric_name",
        "analysis_mode",
        "current_year",
        "current_month",
        "reference_year",
        "reference_month",
    }

    if set(payload) != required:
        raise ValueError(
            "Comparison Intent payload keys must exactly match contract."
        )

    return LLMComparisonIntentPayloadV2.model_validate(
        payload
    )


def _has_comparison_language_v2(
    question: str,
) -> bool:
    text = re.sub(r"\s+", "", str(question))

    return bool(
        re.search(
            (
                r"相比|比较|对比|环比"
                r"|(?:和|与|跟).{0,12}(?:比|相比)"
                r"|较上月|比上月|较前月|比前月"
            ),
            text,
        )
    )


def _explicit_current_month_supported_v2(
    *,
    question: str,
    year: int,
    month: int,
) -> bool:
    text = re.sub(r"\s+", "", str(question))

    return bool(
        re.search(
            rf"{year}年0?{month}月",
            text,
        )
    )


def _reference_month_supported_v2(
    *,
    question: str,
    year: int,
    month: int,
) -> bool:
    text = re.sub(r"\s+", "", str(question))

    explicit_year_month = bool(
        re.search(
            rf"{year}年0?{month}月",
            text,
        )
    )

    explicit_month_only = bool(
        re.search(
            rf"(?<!\d)0?{month}月",
            text,
        )
    )

    relative_previous_month = bool(
        re.search(
            r"上个月|上月|前一个月|前月",
            text,
        )
    )

    return (
        explicit_year_month
        or explicit_month_only
        or relative_previous_month
    )


def _expected_previous_month_v2(
    *,
    current_year: int,
    current_month: int,
) -> tuple[int, int]:
    if current_month == 1:
        return current_year - 1, 12

    return current_year, current_month - 1


def _month_anchor_v2(
    *,
    year: int,
    month: int,
) -> date:
    return date(
        year,
        month,
        calendar.monthrange(year, month)[1],
    )


def resolve_gmv_adjacent_month_comparison_intent_v2(
    question: str,
    *,
    llm_call: LLMCall = chat_completion,
) -> ComparisonIntentSemanticResultV2:
    """
    Natural language -> LLM semantic normalization
    -> deterministic adjacent-month validation。

    安全边界：
    - 仅处理问题中明确出现 GMV 的请求；
    - LLM 不决定 Scope / Grain / Query Plan / SQL；
    - current 年月必须真实出现在原句；
    - reference 月份必须真实出现或明确写成“上月”；
    - 最终必须证明 reference == current 的前一个自然月；
    - READY 只表示“语义合同可用于构造 comparison”，不表示已授权执行。
    """

    text = str(question).strip()

    if not text:
        return ComparisonIntentSemanticResultV2(
            status=ComparisonIntentSemanticStatusV2.NOT_APPLICABLE,
            source="preflight",
            detail="Question is empty.",
        )

    if "gmv" not in text.casefold():
        return ComparisonIntentSemanticResultV2(
            status=ComparisonIntentSemanticStatusV2.NOT_APPLICABLE,
            source="preflight",
            detail="Only explicit GMV is registered for this Day94 route.",
        )

    if not _has_comparison_language_v2(text):
        return ComparisonIntentSemanticResultV2(
            status=ComparisonIntentSemanticStatusV2.NOT_APPLICABLE,
            source="preflight",
            detail="No explicit comparison language.",
        )

    prompt = build_comparison_intent_semantic_prompt_v2(
        text
    )

    try:
        raw_text = llm_call(
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            temperature=0,
        )
        payload = _parse_payload_v2(
            raw_text
        )
    except Exception as exc:
        return ComparisonIntentSemanticResultV2(
            status=ComparisonIntentSemanticStatusV2.PARSE_FAILED,
            source="llm_semantic_normalization",
            detail=str(exc),
        )

    if (
        payload.metric_name is None
        or payload.metric_name.strip().casefold() != "gmv"
    ):
        return ComparisonIntentSemanticResultV2(
            status=ComparisonIntentSemanticStatusV2.VALIDATION_FAILED,
            source="llm_semantic_normalization",
            detail="LLM metric does not match explicit GMV contract.",
        )

    if payload.analysis_mode not in {
        AnalysisModeV2.COMPARISON,
        AnalysisModeV2.INVESTIGATION,
    }:
        return ComparisonIntentSemanticResultV2(
            status=ComparisonIntentSemanticStatusV2.VALIDATION_FAILED,
            source="llm_semantic_normalization",
            detail=(
                "LLM analysis_mode must be comparison or investigation."
            ),
        )

    values = (
        payload.current_year,
        payload.current_month,
        payload.reference_year,
        payload.reference_month,
    )

    if any(value is None for value in values):
        return ComparisonIntentSemanticResultV2(
            status=ComparisonIntentSemanticStatusV2.VALIDATION_FAILED,
            source="llm_semantic_normalization",
            detail="Comparison months are incomplete.",
        )

    assert payload.current_year is not None
    assert payload.current_month is not None
    assert payload.reference_year is not None
    assert payload.reference_month is not None

    if not (
        1 <= payload.current_month <= 12
        and 1 <= payload.reference_month <= 12
    ):
        return ComparisonIntentSemanticResultV2(
            status=ComparisonIntentSemanticStatusV2.VALIDATION_FAILED,
            source="llm_semantic_normalization",
            detail="Month is outside 1..12.",
        )

    if not _explicit_current_month_supported_v2(
        question=text,
        year=payload.current_year,
        month=payload.current_month,
    ):
        return ComparisonIntentSemanticResultV2(
            status=ComparisonIntentSemanticStatusV2.VALIDATION_FAILED,
            source="deterministic_validation",
            detail=(
                "LLM current month is not explicitly supported by the question."
            ),
        )

    if not _reference_month_supported_v2(
        question=text,
        year=payload.reference_year,
        month=payload.reference_month,
    ):
        return ComparisonIntentSemanticResultV2(
            status=ComparisonIntentSemanticStatusV2.VALIDATION_FAILED,
            source="deterministic_validation",
            detail=(
                "LLM reference month is not supported by explicit or relative "
                "question evidence."
            ),
        )

    (
        expected_reference_year,
        expected_reference_month,
    ) = _expected_previous_month_v2(
        current_year=payload.current_year,
        current_month=payload.current_month,
    )

    if (
        payload.reference_year != expected_reference_year
        or payload.reference_month != expected_reference_month
    ):
        return ComparisonIntentSemanticResultV2(
            status=ComparisonIntentSemanticStatusV2.VALIDATION_FAILED,
            source="deterministic_validation",
            detail=(
                "Only adjacent natural-month MoM is registered for this route."
            ),
        )

    return ComparisonIntentSemanticResultV2(
        status=ComparisonIntentSemanticStatusV2.READY,
        analysis_mode=payload.analysis_mode,
        current_anchor_date=_month_anchor_v2(
            year=payload.current_year,
            month=payload.current_month,
        ),
        reference_anchor_date=_month_anchor_v2(
            year=payload.reference_year,
            month=payload.reference_month,
        ),
        source="llm_semantic_normalization+deterministic_validation",
    )
