from __future__ import annotations

import json
import re
from enum import Enum
from typing import Callable

from pydantic import BaseModel, ConfigDict

from app.llm.deepseek_client import chat_completion
from app.semantic_layer.metric_signature_v2 import (
    IntrinsicPartition,
    SemanticOperand,
    SemanticQualifier,
)
from app.semantic_layer.question_signature_v2 import (
    QuestionOperator,
    QuestionSemanticSignatureV2,
)


LLMCall = Callable[..., str]


class QuestionSemanticParseStatusV2(str, Enum):
    PARSED = "parsed"
    MULTIPLE_INTENTS = "multiple_intents"
    PARSE_FAILED = "parse_failed"
    EVIDENCE_CONFLICT = "evidence_conflict"


class DeterministicQuestionEvidenceV2(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    operator: QuestionOperator | None = None
    intrinsic_partition: IntrinsicPartition | None = None
    evidence: tuple[str, ...] = ()


class QuestionSemanticParseResultV2(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    status: QuestionSemanticParseStatusV2
    signature: QuestionSemanticSignatureV2 | None = None
    deterministic_evidence: DeterministicQuestionEvidenceV2
    conflicts: tuple[str, ...] = ()
    raw_response: str | None = None
    error: str | None = None


class LLMQuestionSemanticSignaturePayloadV2(BaseModel):
    """
    Raw structured LLM payload before deterministic evidence merge.

    Unlike the final QuestionSemanticSignatureV2 contract, this staging
    model allows operator=None together with a right_operand so that an
    explicit deterministic relation such as “除以” can safely fill the
    missing operator before final contract validation.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    operator: QuestionOperator | None = None
    left_operand: SemanticOperand | None = None
    right_operand: SemanticOperand | None = None
    intrinsic_partition: IntrinsicPartition | None = None
    qualifiers: tuple[SemanticQualifier, ...] = ()


_OPERAND_DESCRIPTIONS = {
    SemanticOperand.PAID_AMOUNT:
        "成功成交/付款商品对应的金额、成交额、销售金额。",
    SemanticOperand.GROSS_MARGIN_AMOUNT:
        "成交/付款金额扣除商品成本后剩余的毛利金额。",
    SemanticOperand.COMPLETED_REFUND_AMOUNT:
        "已经完成退款/退回的金额。",
    SemanticOperand.MARKETING_SPEND:
        "广告、推广、营销、渠道投放所花费的金额。",
    SemanticOperand.PAID_ORDER:
        "成功成交/付款的订单、交易、单据。",
    SemanticOperand.PAID_UNITS:
        "成功成交商品的件数、数量、商品单位。",
    SemanticOperand.PAID_BUYER:
        "至少发生过一次成功成交/付款的去重客户/买家。",
    SemanticOperand.GLOBAL_FIRST_PAID_CUSTOMER:
        "客户在整个品牌全历史中的首次成功成交/付款。",
    SemanticOperand.CHANNEL_FIRST_PAID_CUSTOMER:
        "客户在某一渠道/平台历史中的首次成功成交/付款。",
    SemanticOperand.REPEAT_DISTINCT_PAID_DATE_CUSTOMER:
        "至少在两个不同成交/付款日期发生过成功交易的客户。",
    SemanticOperand.MULTI_PAID_ORDER_CUSTOMER:
        "成功成交/付款订单数至少为两笔的客户；同日两单也满足。",
    SemanticOperand.PAYMENT_TIME_MEMBER_PAID_AMOUNT:
        "按交易发生/付款当时的会员身份判断得到的会员成交金额。",
}


_QUALIFIER_DESCRIPTIONS = {
    SemanticQualifier.PRODUCT_COST_BASIS:
        "明确按商品成本扣减口径。",
    SemanticQualifier.COMPLETED_REFUND_ONLY:
        "只计算完成状态的退款金额。",
    SemanticQualifier.SALES_COHORT_ATTRIBUTION:
        "退款按原销售/成交期归属。",
    SemanticQualifier.FULL_HISTORY_BRAND_FIRST_PAID:
        "首次成交按品牌全历史判断。",
    SemanticQualifier.FULL_HISTORY_CHANNEL_FIRST_PAID:
        "首次成交按渠道/平台全历史判断。",
    SemanticQualifier.DISTINCT_PAID_DATES_GE_2:
        "至少两个不同成功成交/付款日期。",
    SemanticQualifier.PAID_ORDERS_GE_2:
        "至少两笔成功成交/付款订单。",
    SemanticQualifier.PAYMENT_TIME_MEMBERSHIP_SNAPSHOT:
        "会员身份按支付/成交时点快照判断。",
    SemanticQualifier.SAME_WINDOW_SALES_SPEND:
        "销售与营销投入使用同一分析时间窗口。",
    SemanticQualifier.DIRECT_RESPONSE_CHANNEL:
        "直接响应型渠道口径。",
    SemanticQualifier.PAID_ONLY:
        "只考虑成功付款/成交记录。",
}


def _enum_values_text(enum_type) -> str:
    return ", ".join(
        item.value
        for item in enum_type
    )


def build_question_semantic_parser_prompt_v2(
    question: str,
) -> str:
    operand_lines = "\n".join(
        (
            f"- {operand.value}: "
            f"{_OPERAND_DESCRIPTIONS[operand]}"
        )
        for operand in SemanticOperand
    )

    qualifier_lines = "\n".join(
        (
            f"- {qualifier.value}: "
            f"{_QUALIFIER_DESCRIPTIONS[qualifier]}"
        )
        for qualifier in SemanticQualifier
    )

    return f"""
你是一个“业务语义结构解析器”，不是指标选择器，也不是 SQL 生成器。

任务：
只根据用户原始问题本身，把其中明确表达的业务结构解析成受控 JSON。

绝对禁止：
1. 不要输出 metric_name、指标名称、SQL、解释或候选指标。
2. 不要因为你觉得某个常见指标“应该是这样”就补齐问题中没有表达的结构。
3. 不要调用外部业务上下文；这里只分析用户原句。
4. 如果字段无法从问题中可靠确定，返回 null。
5. qualifiers 只放问题中明确表达的附加业务合同。

operator 允许值：
- sum: 求和/累计总量
- count: 人数、订单数等计数
- divide: A / B、占比、比例、平均到每个对象、每单位对应多少
- 无法确定时 null

operand 允许值与含义：
{operand_lines}

intrinsic_partition：
- channel: 问题的业务定义内在依赖渠道/平台分区
- 否则 null

qualifier 允许值与含义：
{qualifier_lines}

重要区分：
- paid_amount / paid_order = 每单金额类结构
- paid_amount / paid_buyer = 每位买家金额类结构
- paid_units / paid_order = 每单件数类结构
- paid_order / paid_buyer = 每位买家订单数类结构
- paid_amount / paid_units = 金额/件数，即使当前系统可能没有该指标，也要照实解析
- paid_buyer / paid_order 不能自动改成 paid_order / paid_buyer
- global_first_paid_customer 与 channel_first_paid_customer 必须按问题是否明确“品牌全历史”或“渠道/平台自己的历史”区分
- repeat_distinct_paid_date_customer 与 multi_paid_order_customer 必须区分“跨不同日期”与“订单数至少两笔”
- 多个并列业务请求不要强行拼成一个比率；如果当前句子无法表达为一个单一结构，各 core 字段返回 null

只输出下面 5 个字段的 JSON：
{{
  "operator": null,
  "left_operand": null,
  "right_operand": null,
  "intrinsic_partition": null,
  "qualifiers": []
}}

用户问题：
{question}
""".strip()


def _extract_json_object_text_v2(
    text: str,
) -> str:
    cleaned = str(
        text
    ).strip()

    if cleaned.startswith(
        "```json"
    ):
        cleaned = cleaned[
            len("```json"):
        ].strip()

    if cleaned.startswith(
        "```"
    ):
        cleaned = cleaned[
            len("```"):
        ].strip()

    if cleaned.endswith(
        "```"
    ):
        cleaned = cleaned[
            :-3
        ].strip()

    start = cleaned.find(
        "{"
    )
    end = cleaned.rfind(
        "}"
    )

    if (
        start == -1
        or end == -1
        or end <= start
    ):
        raise ValueError(
            "LLM response does not contain one JSON object."
        )

    return cleaned[
        start : end + 1
    ]


def _normalize_payload_v2(
    payload: dict,
) -> dict:
    normalized = dict(
        payload
    )

    if (
        normalized.get(
            "intrinsic_partition"
        )
        == IntrinsicPartition.NONE.value
    ):
        normalized[
            "intrinsic_partition"
        ] = None

    return normalized


def parse_question_signature_payload_v2(
    raw_text: str,
) -> LLMQuestionSemanticSignaturePayloadV2:
    cleaned = (
        _extract_json_object_text_v2(
            raw_text
        )
    )

    payload = json.loads(
        cleaned
    )

    if not isinstance(
        payload,
        dict,
    ):
        raise ValueError(
            "Question Semantic Parser JSON must be an object."
        )

    allowed_keys = {
        "operator",
        "left_operand",
        "right_operand",
        "intrinsic_partition",
        "qualifiers",
    }

    extra_keys = (
        set(payload)
        - allowed_keys
    )

    if extra_keys:
        raise ValueError(
            "Question Semantic Parser returned forbidden keys: "
            f"{sorted(extra_keys)}"
        )

    required_keys = (
        "operator",
        "left_operand",
        "right_operand",
        "intrinsic_partition",
        "qualifiers",
    )

    missing_keys = [
        key
        for key in required_keys
        if key not in payload
    ]

    if missing_keys:
        raise ValueError(
            "Question Semantic Parser missing keys: "
            f"{missing_keys}"
        )

    normalized = (
        _normalize_payload_v2(
            payload
        )
    )

    return LLMQuestionSemanticSignaturePayloadV2.model_validate(
        normalized
    )


def detect_multiple_intents_v2(
    question: str,
) -> tuple[bool, str | None]:
    """
    Conservative guard.

    Only strong discourse markers are used here.
    It intentionally does NOT attempt generic semantic decomposition.
    """
    text = str(
        question
    )

    patterns = (
        (
            r"同时",
            "simultaneous_marker",
        ),
        (
            r"分别",
            "separate_requests_marker",
        ),
        (
            r"既.+也",
            "both_and_marker",
        ),
    )

    for pattern, label in patterns:
        if re.search(
            pattern,
            text,
        ):
            return (
                True,
                label,
            )

    return (
        False,
        None,
    )


def extract_deterministic_question_evidence_v2(
    question: str,
) -> DeterministicQuestionEvidenceV2:
    """
    High-precision evidence only.

    This function is deliberately NOT a complete natural-language parser.
    """
    text = str(
        question
    )

    evidence: list[str] = []
    operator: QuestionOperator | None = None

    if "除以" in text:
        operator = (
            QuestionOperator.DIVIDE
        )
        evidence.append(
            "explicit_divide_token"
        )

    elif re.search(
        r"占比|比例|比值|之比|几倍|倍数",
        text,
    ):
        operator = (
            QuestionOperator.DIVIDE
        )
        evidence.append(
            "explicit_ratio_token"
        )

    elif re.search(
        r"汇总|累计|加总|求和",
        text,
    ):
        operator = (
            QuestionOperator.SUM
        )
        evidence.append(
            "explicit_sum_token"
        )

    partition = None

    if re.search(
        r"渠道|平台",
        text,
    ):
        partition = (
            IntrinsicPartition.CHANNEL
        )
        evidence.append(
            "explicit_channel_token"
        )

    return DeterministicQuestionEvidenceV2(
        operator=operator,
        intrinsic_partition=partition,
        evidence=tuple(
            evidence
        ),
    )


def _merge_and_validate_evidence_v2(
    *,
    signature: LLMQuestionSemanticSignaturePayloadV2,
    evidence: DeterministicQuestionEvidenceV2,
) -> tuple[
    QuestionSemanticSignatureV2 | None,
    tuple[str, ...],
]:
    conflicts: list[str] = []

    operator = signature.operator

    if evidence.operator is not None:
        if operator is None:
            operator = (
                evidence.operator
            )

        elif operator != evidence.operator:
            conflicts.append(
                "operator_conflict: "
                f"llm={operator.value}; "
                f"deterministic={evidence.operator.value}"
            )

    partition = (
        signature.intrinsic_partition
    )

    if (
        evidence.intrinsic_partition
        is not None
    ):
        if partition is None:
            partition = (
                evidence.intrinsic_partition
            )

        elif (
            partition
            != evidence.intrinsic_partition
        ):
            conflicts.append(
                "partition_conflict: "
                f"llm={partition.value}; "
                "deterministic="
                f"{evidence.intrinsic_partition.value}"
            )

    if conflicts:
        return (
            None,
            tuple(
                conflicts
            ),
        )

    merged = (
        QuestionSemanticSignatureV2(
            operator=operator,
            left_operand=signature.left_operand,
            right_operand=signature.right_operand,
            intrinsic_partition=partition,
            qualifiers=signature.qualifiers,
            evidence=(),
        )
    )

    return (
        merged,
        (),
    )


def parse_question_semantics_v2(
    question: str,
    *,
    llm_call: LLMCall = chat_completion,
) -> QuestionSemanticParseResultV2:
    multi_intent, marker = (
        detect_multiple_intents_v2(
            question
        )
    )

    evidence = (
        extract_deterministic_question_evidence_v2(
            question
        )
    )

    if multi_intent:
        return QuestionSemanticParseResultV2(
            status=QuestionSemanticParseStatusV2.MULTIPLE_INTENTS,
            signature=None,
            deterministic_evidence=evidence,
            conflicts=(),
            raw_response=None,
            error=marker,
        )

    prompt = (
        build_question_semantic_parser_prompt_v2(
            question
        )
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

        signature = (
            parse_question_signature_payload_v2(
                raw_text
            )
        )

    except Exception as exc:
        return QuestionSemanticParseResultV2(
            status=QuestionSemanticParseStatusV2.PARSE_FAILED,
            signature=None,
            deterministic_evidence=evidence,
            conflicts=(),
            raw_response=(
                raw_text
                if "raw_text" in locals()
                else None
            ),
            error=str(
                exc
            ),
        )

    try:
        merged, conflicts = (
            _merge_and_validate_evidence_v2(
                signature=signature,
                evidence=evidence,
            )
        )
    except Exception as exc:
        return QuestionSemanticParseResultV2(
            status=QuestionSemanticParseStatusV2.PARSE_FAILED,
            signature=None,
            deterministic_evidence=evidence,
            conflicts=(),
            raw_response=raw_text,
            error=str(exc),
        )

    if conflicts:
        return QuestionSemanticParseResultV2(
            status=QuestionSemanticParseStatusV2.EVIDENCE_CONFLICT,
            signature=None,
            deterministic_evidence=evidence,
            conflicts=conflicts,
            raw_response=raw_text,
            error=None,
        )

    return QuestionSemanticParseResultV2(
        status=QuestionSemanticParseStatusV2.PARSED,
        signature=merged,
        deterministic_evidence=evidence,
        conflicts=(),
        raw_response=raw_text,
        error=None,
    )


if __name__ == "__main__":
    result = parse_question_semantics_v2(
        "成交订单数除以成交客户数"
    )

    print(
        result.model_dump(
            mode="json"
        )
    )
