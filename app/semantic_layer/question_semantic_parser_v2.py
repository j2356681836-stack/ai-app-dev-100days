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
    left_operand: SemanticOperand | None = None
    intrinsic_partition: IntrinsicPartition | None = None
    evidence: tuple[str, ...] = ()
    qualifiers: tuple[SemanticQualifier, ...,] = ()

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
        "客户在整个品牌全历史中的首次成功成交/付款；"
        "品牌内最早一笔、品牌历史首笔、品牌全历史第一次成交均属于该结构。",
    SemanticOperand.CHANNEL_FIRST_PAID_CUSTOMER:
        "客户在某一渠道/平台自己的历史中的首次成功成交/付款；"
        "包括按各渠道/各平台分别寻找客户历史首笔成交、首次成交客户、"
        "历史首笔成交人数等表达。",
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
    SemanticQualifier.SALES_COHORT_ATTRIBUTION:
        "退款按原销售/成交期归属。",
    SemanticQualifier.DIRECT_RESPONSE_CHANNEL:
        "直接响应型渠道口径。",
    SemanticQualifier.SAME_WINDOW_SALES_SPEND:
        "销售与营销投入使用同一分析时间窗口。",
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
6. “怎么样”“如何”“情况”“表现”等泛化分析请求，只表示用户关注某个业务对象，
   不足以证明 sum、count 或 divide；如果原句没有明确的求和、计数、比例、平均等运算关系，
   operator 返回 null。

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


def _apply_semantic_specificity_guard_v2(
    *,
    question: str,
    signature: LLMQuestionSemanticSignaturePayloadV2,
) -> LLMQuestionSemanticSignaturePayloadV2:
    """
    Prevent the LLM from making a semantic operand more specific
    than the user's wording supports.

    In particular, generic "new customer" wording does not prove
    whether the user means brand-global first paid or channel-local
    first paid.
    """
    text = str(
        question
    )

    left_operand = (
        signature.left_operand
    )

    right_operand = (
        signature.right_operand
    )

    global_first_paid_explicit = bool(
        re.search(
            (
                r"全品牌|整个品牌|品牌全历史|品牌内"
                r"|品牌.*(?:历史|最早|首次|第一次|首笔)"
            ),
            text,
        )
    )

    channel_first_paid_explicit = bool(
        re.search(
            (
                r"(?:渠道|平台).*(?:历史|最早|首次|第一次|首笔)"
                r"|(?:历史|最早|首次|第一次|首笔).*(?:渠道|平台)"
            ),
            text,
        )
    )

    normalized_text = re.sub(
        r"\s+",
        "",
        text,
    )

    generic_average_underspecified = bool(
        re.fullmatch(
            (
                r"(?:平均|均值)"
                r"(?:消费|消费金额|金额)"
                r"(?:大概|大约|大致)?"
                r"(?:是|有)?"
                r"多少"
                r"[？?]?"
            ),
            normalized_text,
        )
    )

    if (
        left_operand
        == SemanticOperand.GLOBAL_FIRST_PAID_CUSTOMER
        and not global_first_paid_explicit
    ):
        left_operand = None

    elif (
        left_operand
        == SemanticOperand.CHANNEL_FIRST_PAID_CUSTOMER
        and not channel_first_paid_explicit
    ):
        left_operand = None
    if generic_average_underspecified:
        left_operand = None
        right_operand = None
    if (
        left_operand
        == signature.left_operand
        and right_operand
        == signature.right_operand
    ):
        return signature


    return signature.model_copy(
        update={
            "left_operand": left_operand,
            "right_operand": right_operand,
        }
    )


def _is_explicit_separate_result_grain_request_v2(
    text: str,
) -> bool:
    """
    High-precision exception for one Metric requested as separate
    result sets across multiple supported dimensions.

    Examples:
    - 分别按渠道和地区看GMV
    - 分别按地区、品类统计销售额

    This does not resolve the grain itself. It only prevents the
    multi-intent discourse guard from consuming a request that belongs
    to Result Grain Resolver V2.
    """
    dimension_token = (
        r"(?:渠道|平台|地区|区域|品类|类别)"
    )

    return bool(
        re.search(
            (
                r"分别"
                r"(?:按|从)?"
                r".{0,8}"
                + dimension_token
                + r".{0,8}"
                r"(?:和|与|、)"
                r".{0,8}"
                + dimension_token
            ),
            text,
        )
    )


def detect_multiple_intents_v2(
    question: str,
) -> tuple[bool, str | None]:
    """
    Conservative guard.

    Only strong discourse markers are used here.
    It intentionally does NOT attempt generic semantic decomposition.

    Important boundary:
    "分别" may describe either multiple business requests or one Metric
    requested as separate result sets across multiple dimensions.
    The latter belongs to Result Grain Resolver V2 and must pass through.
    """
    text = str(
        question
    )

    if _is_explicit_separate_result_grain_request_v2(
        text
    ):
        return (
            False,
            None,
        )

    patterns = (
        (
            r"同时",
            "simultaneous_marker",
        ),
        (
            r"分别.*(?:以及|并且|和|与|、)",
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
    qualifiers: list[SemanticQualifier] = []

    total_amount_explicit = bool(
        re.search(
            (
                r"(?:总共|一共|合计|总计)"
                r".{0,12}"
                r"(?:多少钱|金额|成交额|销售额|收入|收款|"
                r"花费|费用|成本|毛利)"
            ),
            text,
        )
    )

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
        (
            r"均摊到|摊到|平均到"
            r"|按.{0,20}?平均分"
            r"|平均|均值|人均"
        ),
        text,
    ):
        operator = (
            QuestionOperator.DIVIDE
        )
        evidence.append(
            "explicit_average_token"
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

    elif total_amount_explicit:
        operator = (
            QuestionOperator.SUM
        )
        evidence.append(
            "explicit_total_amount_token"
        )

    elif re.search(
        (
            r"人数|客户数|买家数|订单数|单量|件数"
            r"|(?:新客|客户|买家|订单)(?:有)?多少(?:人|位|个|单|笔|件)?"
            r"|多少(?:人|位|个|单|笔|件)?(?:新客|客户|买家|订单)"
        ),
        text,
    ):
        operator = (
            QuestionOperator.COUNT
        )
        evidence.append(
            "explicit_count_token"
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

    explicit_product_cost = bool(
        re.search(
            r"商品成本",
            text,
        )
    )

    marketing_cost_explicit = bool(
        re.search(
            (
                r"广告成本"
                r"|推广成本"
                r"|投放成本"
                r"|获客成本"
                r"|营销成本"
                r"|营销费用"
                r"|推广费用"
                r"|投放费用"
                r"|渠道投入"
            ),
            text,
        )
    )

    revenue_minus_cost = bool(
        re.search(
            (
                r"(?:成交收入|收入|收款|成交金额)"
                r".{0,10}"
                r"(?:扣(?:掉|除)?|减去|减)"
                r".{0,6}"
                r"成本"
            ),
            text,
        )
    )

    revenue_cost_difference = bool(
        re.search(
            (
                r"(?:成交收入|收入|收款|成交金额)"
                r".{0,8}"
                r"(?:和|与)"
                r".{0,6}"
                r"成本"
                r".{0,8}"
                r"(?:做差|差额)"
            ),
            text,
        )
    )

    same_window_explicit = bool(
        re.search(
            (
                r"同期"
                r"|同周期"
                r"|同一周期"
                r"|同期间"
                r"|同一期间"
                r"|同时间窗口"
                r"|同一时间窗口"
            ),
            text,
        )
    )

    sales_amount_explicit = bool(
        re.search(
            (
                r"成交金额"
                r"|成交额"
                r"|成交付款"
                r"|付款金额"
                r"|销售金额"
                r"|销售额"
                r"|成交收入"
                r"|销售收入"
                r"|收款"
            ),
            text,
        )
    )

    marketing_spend_window_explicit = bool(
        re.search(
            (
                r"推广花费"
                r"|推广费用"
                r"|推广成本"
                r"|广告花费"
                r"|广告费用"
                r"|广告成本"
                r"|营销花费"
                r"|营销费用"
                r"|营销投入"
                r"|投放花费"
                r"|投放费用"
                r"|投放成本"
                r"|渠道投入"
                r"|获客投入"
            ),
            text,
        )
    )

    same_window_sales_spend_explicit = (
        same_window_explicit
        and sales_amount_explicit
        and marketing_spend_window_explicit
    )
    
    product_cost_basis_explicit = (
        explicit_product_cost
        or (
            (
                revenue_minus_cost
                or revenue_cost_difference
            )
            and not marketing_cost_explicit
        )
    )

    left_operand = None

    gross_margin_amount_explicit = (
        (
            revenue_minus_cost
            or revenue_cost_difference
        )
        and not marketing_cost_explicit
    )

    if gross_margin_amount_explicit:
        left_operand = (
            SemanticOperand.GROSS_MARGIN_AMOUNT
        )
        evidence.append(
            "explicit_gross_margin_amount"
        )

    if product_cost_basis_explicit:
        qualifiers.append(
            SemanticQualifier.PRODUCT_COST_BASIS
        )
        evidence.append(
            "explicit_product_cost_basis"
        )

    if same_window_sales_spend_explicit:
        qualifiers.append(
            SemanticQualifier.SAME_WINDOW_SALES_SPEND
        )
        evidence.append(
            "explicit_same_window_sales_spend"
        )

    return DeterministicQuestionEvidenceV2(
        operator=operator,
        left_operand=left_operand,
        intrinsic_partition=partition,
        qualifiers=tuple(
            qualifiers
        ),
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

    left_operand = (
        signature.left_operand
    )

    if evidence.left_operand is not None:
        if left_operand is None:
            left_operand = (
                evidence.left_operand
            )

        elif (
            left_operand
            != evidence.left_operand
        ):
            conflicts.append(
                "left_operand_conflict: "
                f"llm={left_operand.value}; "
                "deterministic="
                f"{evidence.left_operand.value}"
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

    qualifiers = set(
        signature.qualifiers
    )

    qualifiers.update(
        evidence.qualifiers
    )

    merged = (
        QuestionSemanticSignatureV2(
            operator=operator,
            left_operand=left_operand,
            right_operand=signature.right_operand,
            intrinsic_partition=partition,
            qualifiers=tuple(
                sorted(
                    qualifiers,
                    key=lambda item: item.value,
                )
            ),
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

        signature = (
            _apply_semantic_specificity_guard_v2(
                question=question,
                signature=signature,
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
