from __future__ import annotations

import re
from enum import Enum
from typing import Iterable

from pydantic import BaseModel, ConfigDict, model_validator

from app.semantic_layer.metric_signature_v2 import (
    IntrinsicPartition,
    SemanticOperand,
    SemanticQualifier,
)


class QuestionOperator(str, Enum):
    SUM = "sum"
    COUNT = "count"
    DIVIDE = "divide"


class QuestionSignatureEvidenceV2(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    dimension: str
    value: str
    matched_text: str
    start: int
    end: int


class QuestionSemanticSignatureV2(BaseModel):
    """
    Partial structure extracted from one user question.

    Important:
    - This is NOT a Metric prediction.
    - Fields may remain unknown.
    - It contains no metric_name and no candidate scores.
    - It only records business-semantic structure explicitly
      supported by deterministic question evidence.
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
    evidence: tuple[QuestionSignatureEvidenceV2, ...] = ()

    @model_validator(mode="after")
    def validate_partial_structure(
        self,
    ) -> "QuestionSemanticSignatureV2":
        if (
            self.operator != QuestionOperator.DIVIDE
            and self.right_operand is not None
        ):
            raise ValueError(
                "Only divide question signatures may declare right_operand."
            )

        if (
            self.left_operand is not None
            and self.left_operand == self.right_operand
        ):
            raise ValueError(
                "Question signature cannot use identical left/right operands."
            )

        if len(self.qualifiers) != len(set(self.qualifiers)):
            raise ValueError(
                "Question semantic qualifiers must be unique."
            )

        return self


class _OperandHit(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    operand: SemanticOperand
    matched_text: str
    start: int
    end: int


# Semantic atoms are intentionally reusable across Metrics.
# There is no mapping here from a phrase directly to a Metric name.
_OPERAND_PATTERNS: tuple[
    tuple[
        SemanticOperand,
        tuple[str, ...],
    ],
    ...,
] = (
    (
        SemanticOperand.PAYMENT_TIME_MEMBER_PAID_AMOUNT,
        (
            r"(?:付款当时|支付瞬间|下单付款时).*?会员.*?"
            r"(?:付款金额|实收金额|金额|订单)",
            r"会员(?:部分)?金额.*?(?:占|比例|总金额)",
        ),
    ),
    (
        SemanticOperand.COMPLETED_REFUND_AMOUNT,
        (
            r"(?:已完成退回|完成退款|完成退回|最终被完成退款|最终被退回)"
            r".*?金额",
            r"(?:完成退回|完成退款)金额",
        ),
    ),
    (
        SemanticOperand.GROSS_MARGIN_AMOUNT,
        (
            r"(?:商品)?(?:实收|付款|支付|收入).*?金额.*?"
            r"(?:扣掉|扣除|扣|减去|减).*?(?:进货)?成本.*?"
            r"(?:后)?(?:合计|剩余|还剩|部分|金额|差额)?",
            r"(?:收入|金额).*?(?:与|和).*?(?:商品)?成本.*?差额",
            r"(?:商品)?收入.*?(?:减去|减|扣除|扣掉|扣).*?"
            r"(?:进货)?成本.*?(?:后)?(?:的)?(?:总)?金额",
            r"(?:商品)?(?:付款|支付|实收)金额.*?"
            r"(?:减去|减|扣除|扣掉|扣).*?成本.*?"
            r"(?:后)?(?:的)?(?:部分|金额)",
            r"(?:扣除|扣掉|扣).*?成本.*?(?:后)?"
            r"(?:剩余|还剩).*?金额",
        ),
    ),
    (
        SemanticOperand.CHANNEL_FIRST_PAID_CUSTOMER,
        (
            r"(?:渠道|平台).*?(?:第一次|首次|第一笔).*?"
            r"(?:付款|付费).*?(?:客户|人)",
            r"(?:首次|第一次|第一笔).*?(?:在|于)?(?:该)?"
            r"(?:渠道|平台).*?(?:完成)?(?:付款|付费).*?(?:客户|人)",
            r"(?:每个|各|按)平台.*?客户.*?"
            r"(?:第一次|首次|历史第一笔|第一笔).*?(?:付款|付费)",
            r"客户.*?(?:某个|这个)平台.*?"
            r"(?:首次|第一次).*?(?:付费|付款)",
            r"按平台.*?客户.*?(?:历史)?第一笔付款",
        ),
    ),
    (
        SemanticOperand.GLOBAL_FIRST_PAID_CUSTOMER,
        (
            r"(?:整个品牌|全品牌).*?(?:第一次|首次|第一笔).*?"
            r"(?:付款|付费).*?(?:客户|人)?",
            r"(?:全历史|全品牌历史).*?(?:第一次|首次|第一笔).*?"
            r"(?:成功)?(?:付款|付费).*?(?:客户|人)?",
            r"全品牌.*?每人第一笔",
            r"(?:第一次|首次|第一笔).*?(?:整个品牌|全品牌).*?"
            r"(?:完成)?(?:付款|付费).*?(?:不同)?(?:客户|人)",
        ),
    ),
    (
        SemanticOperand.REPEAT_DISTINCT_PAID_DATE_CUSTOMER,
        (
            r"(?:至少|拥有)?(?:两个|两|2)(?:个|次)?(?:以上)?"
            r"不同(?:付款|购买)(?:日期|日).*?(?:客户|人)",
            r"(?:客户|人).*?另一个日期再次.*?(?:付款|购买)",
            r"另一个日期再次.*?(?:付款|购买).*?(?:客户|人)?",
            r"(?:不同付款日期|不同购买日|购买日).*?"
            r"(?:至少为二|至少两个|两个以上).*?(?:客户|人)",
            r"客户.*?不同付款日期.*?"
            r"(?:至少为二|不少于二|至少.*?二).*?(?:人)?",
        ),
    ),
    (
        SemanticOperand.MULTI_PAID_ORDER_CUSTOMER,
        (
            r"(?:付款交易|交易|单据).*?(?:达到)?"
            r"(?:两笔|2笔|两次|2次|至少两次|两笔或更多|不小于二)"
            r".*?(?:客户|人)",
            r"(?:至少两次|两笔|两笔或更多).*?付款.*?(?:客户|人)",
            r"(?:客户).*?(?:至少两次|两笔|单据数不小于二)"
            r".*?(?:付款)?",
        ),
    ),
    (
        SemanticOperand.MARKETING_SPEND,
        (
            r"广告投入",
            r"营销投入",
            r"渠道营销费用",
            r"渠道营销投入",
            r"投放费用",
            r"平台投入费用",
            r"投入费用",
            r"营销费用",
        ),
    ),
    (
        SemanticOperand.PAID_UNITS,
        (
            r"商品(?:总)?数量",
            r"购买数量",
            r"quantity",
            r"商品单位",
            r"个商品单位",
            r"售出.*?单位",
            r"卖出的商品数量",
        ),
    ),
    (
        SemanticOperand.PAID_ORDER,
        (
            r"成功付款单据",
            r"付款单据",
            r"支付成功的交易",
            r"成功支付.*?交易",
            r"成功付款交易",
            r"完成付款的交易",
            r"付款成功的单据",
            r"交易次数",
            r"单据笔数",
            r"单据数",
            r"交易记录",
            r"独立交易",
            r"成功交易",
            r"付款交易",
        ),
    ),
    (
        SemanticOperand.PAID_BUYER,
        (
            r"不同付款客户",
            r"去重后的付款客户",
            r"实际付过款的不同客户",
            r"实际付款客户",
            r"付款客户",
            r"购买客户",
            r"付过款的人",
            r"付款记录里的客户",
            r"成功付款记录里的客户",
            r"发生过付款.*?人",
            r"不同客户.*?(?:成功)?(?:完成)?(?:过)?(?:一次)?付款",
            r"付款客户数",
        ),
    ),
    (
        SemanticOperand.PAID_AMOUNT,
        (
            r"商品付款总金额",
            r"商品(?:实收|付款)金额",
            r"成功付款商品明细贡献的金额",
            r"实收金额",
            r"付款金额",
            r"实付金额",
            r"支付商品金额",
            r"成功付款金额",
            r"总付款产出",
            r"付款产出",
            r"商品收入",
            r"收入",
        ),
    ),
)


_DIVIDE_PATTERN = re.compile(
    r"除以|占比|比例|比值|倍数|平均|摊到|平均到|"
    r"按.*?平均分|每投入.*?带来|占整体|占全部|占多少|"
    r"相对.*?比例"
)

_SUM_PATTERN = re.compile(
    r"总和|求和|合计|总金额|全部相加|加在一起|总计|"
    r"一共售出|字段求总和|一共.*?单位"
)

_COUNT_PATTERN = re.compile(
    r"有多少|数量|人数|计数|多少笔|多少次|再数|统计|"
    r"共有多少|数.*?客户|多少人"
)


def _overlaps(
    start: int,
    end: int,
    occupied: Iterable[tuple[int, int]],
) -> bool:
    return any(
        not (
            end <= used_start
            or start >= used_end
        )
        for used_start, used_end in occupied
    )


def _detect_operand_hits_v2(
    text: str,
) -> tuple[_OperandHit, ...]:
    """
    Higher-specificity semantic atoms are evaluated first.

    Generic atoms such as paid_amount / paid_buyer do not overwrite
    more specific spans such as gross_margin_amount or
    channel_first_paid_customer.
    """
    hits: list[_OperandHit] = []
    occupied: list[tuple[int, int]] = []

    for operand, patterns in _OPERAND_PATTERNS:
        for pattern in patterns:
            for match in re.finditer(
                pattern,
                text,
                flags=re.IGNORECASE,
            ):
                start, end = match.span()

                if _overlaps(
                    start,
                    end,
                    occupied,
                ):
                    continue

                hits.append(
                    _OperandHit(
                        operand=operand,
                        matched_text=match.group(0),
                        start=start,
                        end=end,
                    )
                )
                occupied.append(
                    (
                        start,
                        end,
                    )
                )

    return tuple(
        sorted(
            hits,
            key=lambda item: (
                item.start,
                item.end,
            ),
        )
    )


def _detect_operator_v2(
    text: str,
) -> tuple[
    QuestionOperator | None,
    QuestionSignatureEvidenceV2 | None,
]:
    for operator, pattern in (
        (
            QuestionOperator.DIVIDE,
            _DIVIDE_PATTERN,
        ),
        (
            QuestionOperator.SUM,
            _SUM_PATTERN,
        ),
        (
            QuestionOperator.COUNT,
            _COUNT_PATTERN,
        ),
    ):
        match = pattern.search(
            text
        )

        if match:
            return (
                operator,
                QuestionSignatureEvidenceV2(
                    dimension="operator",
                    value=operator.value,
                    matched_text=match.group(0),
                    start=match.start(),
                    end=match.end(),
                ),
            )

    return (
        None,
        None,
    )


def _first_operand_in_text_v2(
    text: str,
) -> SemanticOperand | None:
    hits = _detect_operand_hits_v2(
        text
    )

    if not hits:
        return None

    return hits[0].operand


def _unique_operands_v2(
    hits: tuple[_OperandHit, ...],
) -> tuple[SemanticOperand, ...]:
    values: list[
        SemanticOperand
    ] = []

    for hit in hits:
        if hit.operand not in values:
            values.append(
                hit.operand
            )

    return tuple(
        values
    )


def _resolve_divide_operands_v2(
    text: str,
    hits: tuple[_OperandHit, ...],
) -> tuple[
    SemanticOperand | None,
    SemanticOperand | None,
    str,
]:
    operands = _unique_operands_v2(
        hits
    )

    if "除以" in text:
        left_text, right_text = text.split(
            "除以",
            1,
        )

        return (
            _first_operand_in_text_v2(
                left_text
            ),
            _first_operand_in_text_v2(
                right_text
            ),
            "explicit_divide",
        )

    for anchor in (
        "摊到",
        "平均到",
    ):
        if anchor in text:
            left_text, right_text = text.split(
                anchor,
                1,
            )

            return (
                _first_operand_in_text_v2(
                    left_text
                ),
                _first_operand_in_text_v2(
                    right_text
                ),
                anchor,
            )

    average_split = re.search(
        r"(.+?)按(.+?)平均分",
        text,
    )

    if average_split:
        return (
            _first_operand_in_text_v2(
                average_split.group(1)
            ),
            _first_operand_in_text_v2(
                average_split.group(2)
            ),
            "按...平均分",
        )

    base_then_share = re.search(
        r"(.+?)(?:中|里)(.+?)占",
        text,
    )

    if base_then_share:
        return (
            _first_operand_in_text_v2(
                base_then_share.group(2)
            ),
            _first_operand_in_text_v2(
                base_then_share.group(1)
            ),
            "base_then_share",
        )

    if "占" in text:
        left_text, right_text = text.split(
            "占",
            1,
        )

        left_candidates = list(
            _unique_operands_v2(
                _detect_operand_hits_v2(
                    left_text
                )
            )
        )

        if len(left_candidates) > 1:
            non_base = [
                operand
                for operand in left_candidates
                if operand
                != SemanticOperand.PAID_AMOUNT
            ]

            left_operand = (
                non_base[-1]
                if non_base
                else left_candidates[-1]
            )
        else:
            left_operand = (
                left_candidates[0]
                if left_candidates
                else None
            )

        right_operand = (
            _first_operand_in_text_v2(
                right_text
            )
        )

        if (
            right_operand is None
            and left_operand
            in {
                SemanticOperand.PAYMENT_TIME_MEMBER_PAID_AMOUNT,
                SemanticOperand.COMPLETED_REFUND_AMOUNT,
                SemanticOperand.GROSS_MARGIN_AMOUNT,
            }
            and re.search(
                r"整体|全部|总金额|总额",
                right_text,
            )
        ):
            right_operand = (
                SemanticOperand.PAID_AMOUNT
            )

        if (
            right_operand is None
            and left_operand
            == SemanticOperand.REPEAT_DISTINCT_PAID_DATE_CUSTOMER
            and re.search(
                r"全部付款客户|付款客户",
                text,
            )
        ):
            right_operand = (
                SemanticOperand.PAID_BUYER
            )

        if (
            right_operand is None
            and SemanticOperand.PAID_AMOUNT
            in operands
            and left_operand
            != SemanticOperand.PAID_AMOUNT
        ):
            right_operand = (
                SemanticOperand.PAID_AMOUNT
            )

        if (
            right_operand is None
            and SemanticOperand.PAID_BUYER
            in operands
            and left_operand
            != SemanticOperand.PAID_BUYER
        ):
            right_operand = (
                SemanticOperand.PAID_BUYER
            )

        return (
            left_operand,
            right_operand,
            "share_relation",
        )

    if "相对" in text:
        left_text, right_text = text.split(
            "相对",
            1,
        )

        return (
            _first_operand_in_text_v2(
                left_text
            ),
            _first_operand_in_text_v2(
                right_text
            ),
            "relative_relation",
        )

    if re.search(
        r"每投入.*?带来",
        text,
    ):
        if (
            SemanticOperand.PAID_AMOUNT
            in operands
            and SemanticOperand.MARKETING_SPEND
            in operands
        ):
            return (
                SemanticOperand.PAID_AMOUNT,
                SemanticOperand.MARKETING_SPEND,
                "return_per_spend",
            )

    if "平均" in text:
        if (
            SemanticOperand.MARKETING_SPEND
            in operands
            and SemanticOperand.CHANNEL_FIRST_PAID_CUSTOMER
            in operands
        ):
            return (
                SemanticOperand.MARKETING_SPEND,
                SemanticOperand.CHANNEL_FIRST_PAID_CUSTOMER,
                "acquisition_cost_average",
            )

        denominator: SemanticOperand | None = None

        for candidate in (
            SemanticOperand.PAID_BUYER,
            SemanticOperand.PAID_ORDER,
        ):
            if candidate in operands:
                denominator = candidate
                break

        for numerator in (
            SemanticOperand.PAID_AMOUNT,
            SemanticOperand.PAID_UNITS,
            SemanticOperand.PAID_ORDER,
        ):
            if (
                numerator in operands
                and numerator != denominator
            ):
                return (
                    numerator,
                    denominator,
                    "average_relation",
                )

    if (
        "倍数关系" in text
        and SemanticOperand.PAID_AMOUNT
        in operands
        and SemanticOperand.MARKETING_SPEND
        in operands
    ):
        return (
            SemanticOperand.PAID_AMOUNT,
            SemanticOperand.MARKETING_SPEND,
            "return_multiple",
        )

    if (
        SemanticOperand.REPEAT_DISTINCT_PAID_DATE_CUSTOMER
        in operands
        and re.search(
            r"付款客户中|全部付款客户|付过款的人数",
            text,
        )
    ):
        return (
            SemanticOperand.REPEAT_DISTINCT_PAID_DATE_CUSTOMER,
            SemanticOperand.PAID_BUYER,
            "repeat_share_population",
        )

    structural_pairs = (
        (
            SemanticOperand.GROSS_MARGIN_AMOUNT,
            SemanticOperand.PAID_AMOUNT,
        ),
        (
            SemanticOperand.COMPLETED_REFUND_AMOUNT,
            SemanticOperand.PAID_AMOUNT,
        ),
        (
            SemanticOperand.PAYMENT_TIME_MEMBER_PAID_AMOUNT,
            SemanticOperand.PAID_AMOUNT,
        ),
        (
            SemanticOperand.REPEAT_DISTINCT_PAID_DATE_CUSTOMER,
            SemanticOperand.PAID_BUYER,
        ),
        (
            SemanticOperand.PAID_AMOUNT,
            SemanticOperand.MARKETING_SPEND,
        ),
        (
            SemanticOperand.MARKETING_SPEND,
            SemanticOperand.CHANNEL_FIRST_PAID_CUSTOMER,
        ),
        (
            SemanticOperand.PAID_AMOUNT,
            SemanticOperand.PAID_BUYER,
        ),
        (
            SemanticOperand.PAID_UNITS,
            SemanticOperand.PAID_ORDER,
        ),
        (
            SemanticOperand.PAID_AMOUNT,
            SemanticOperand.PAID_ORDER,
        ),
        (
            SemanticOperand.PAID_ORDER,
            SemanticOperand.PAID_BUYER,
        ),
    )

    possible_pairs = [
        pair
        for pair in structural_pairs
        if (
            pair[0] in operands
            and pair[1] in operands
        )
    ]

    if len(possible_pairs) == 1:
        return (
            possible_pairs[0][0],
            possible_pairs[0][1],
            "unique_structural_pair",
        )

    return (
        (
            operands[0]
            if operands
            else None
        ),
        (
            operands[1]
            if len(operands) > 1
            else None
        ),
        "partial_fallback",
    )


def _resolve_non_divide_left_operand_v2(
    hits: tuple[_OperandHit, ...],
) -> SemanticOperand | None:
    if not hits:
        return None

    return hits[0].operand


def _detect_partition_v2(
    text: str,
) -> tuple[
    IntrinsicPartition | None,
    QuestionSignatureEvidenceV2 | None,
]:
    match = re.search(
        r"渠道|平台",
        text,
    )

    if not match:
        return (
            None,
            None,
        )

    return (
        IntrinsicPartition.CHANNEL,
        QuestionSignatureEvidenceV2(
            dimension="intrinsic_partition",
            value=IntrinsicPartition.CHANNEL.value,
            matched_text=match.group(0),
            start=match.start(),
            end=match.end(),
        ),
    )


def _detect_qualifiers_v2(
    text: str,
    operands: tuple[SemanticOperand, ...],
) -> tuple[
    tuple[SemanticQualifier, ...],
    tuple[QuestionSignatureEvidenceV2, ...],
]:
    rules: list[
        tuple[
            SemanticQualifier,
            str,
        ]
    ] = []

    if (
        SemanticOperand.GROSS_MARGIN_AMOUNT
        in operands
    ):
        rules.append(
            (
                SemanticQualifier.PRODUCT_COST_BASIS,
                r"成本|进货成本",
            )
        )

    if (
        SemanticOperand.COMPLETED_REFUND_AMOUNT
        in operands
    ):
        rules.append(
            (
                SemanticQualifier.COMPLETED_REFUND_ONLY,
                r"完成退款|完成退回|已完成退回|最终被完成退款|最终被退回",
            )
        )

    if re.search(
        r"原购买期归属|购买期归属|销售期归属",
        text,
    ):
        rules.append(
            (
                SemanticQualifier.SALES_COHORT_ATTRIBUTION,
                r"原购买期归属|购买期归属|销售期归属",
            )
        )

    if (
        SemanticOperand.GLOBAL_FIRST_PAID_CUSTOMER
        in operands
    ):
        rules.append(
            (
                SemanticQualifier.FULL_HISTORY_BRAND_FIRST_PAID,
                r"全历史|全品牌历史|整个品牌|全品牌|第一次|首次|第一笔",
            )
        )

    if (
        SemanticOperand.CHANNEL_FIRST_PAID_CUSTOMER
        in operands
    ):
        rules.append(
            (
                SemanticQualifier.FULL_HISTORY_CHANNEL_FIRST_PAID,
                r"历史|第一次|首次|第一笔",
            )
        )

    if (
        SemanticOperand.REPEAT_DISTINCT_PAID_DATE_CUSTOMER
        in operands
    ):
        rules.append(
            (
                SemanticQualifier.DISTINCT_PAID_DATES_GE_2,
                r"两个.*?不同|两.*?不同|另一个日期再次|两个以上|至少为二",
            )
        )

    if (
        SemanticOperand.MULTI_PAID_ORDER_CUSTOMER
        in operands
    ):
        rules.append(
            (
                SemanticQualifier.PAID_ORDERS_GE_2,
                r"两笔|两次|至少两次|两笔或更多|不小于二",
            )
        )

    if (
        SemanticOperand.PAYMENT_TIME_MEMBER_PAID_AMOUNT
        in operands
    ):
        rules.append(
            (
                SemanticQualifier.PAYMENT_TIME_MEMBERSHIP_SNAPSHOT,
                r"付款当时|支付瞬间|下单付款时",
            )
        )

    if re.search(
        r"同期",
        text,
    ):
        rules.append(
            (
                SemanticQualifier.SAME_WINDOW_SALES_SPEND,
                r"同期",
            )
        )
    qualifiers: list[
        SemanticQualifier
    ] = []

    evidence: list[
        QuestionSignatureEvidenceV2
    ] = []

    for qualifier, pattern in rules:
        if qualifier in qualifiers:
            continue

        match = re.search(
            pattern,
            text,
        )

        if not match:
            continue

        qualifiers.append(
            qualifier
        )

        evidence.append(
            QuestionSignatureEvidenceV2(
                dimension="qualifier",
                value=qualifier.value,
                matched_text=match.group(0),
                start=match.start(),
                end=match.end(),
            )
        )

    return (
        tuple(
            qualifiers
        ),
        tuple(
            evidence
        ),
    )


def extract_question_semantic_signature_v2(
    question: str,
) -> QuestionSemanticSignatureV2:
    text = str(
        question
    ).strip()

    operator, operator_evidence = (
        _detect_operator_v2(
            text
        )
    )

    hits = _detect_operand_hits_v2(
        text
    )

    operands = _unique_operands_v2(
        hits
    )

    if operator == QuestionOperator.DIVIDE:
        (
            left_operand,
            right_operand,
            relation_rule,
        ) = _resolve_divide_operands_v2(
            text,
            hits,
        )
    else:
        left_operand = (
            _resolve_non_divide_left_operand_v2(
                hits
            )
        )
        right_operand = None
        relation_rule = (
            "non_divide"
        )

    partition, partition_evidence = (
        _detect_partition_v2(
            text
        )
    )

    (
        qualifiers,
        qualifier_evidence,
    ) = _detect_qualifiers_v2(
        text,
        operands,
    )

    evidence: list[
        QuestionSignatureEvidenceV2
    ] = []

    if operator_evidence is not None:
        evidence.append(
            operator_evidence
        )

    for hit in hits:
        evidence.append(
            QuestionSignatureEvidenceV2(
                dimension="operand",
                value=hit.operand.value,
                matched_text=hit.matched_text,
                start=hit.start,
                end=hit.end,
            )
        )

    if (
        operator == QuestionOperator.DIVIDE
        and (
            left_operand is not None
            or right_operand is not None
        )
    ):
        evidence.append(
            QuestionSignatureEvidenceV2(
                dimension="relation_rule",
                value=relation_rule,
                matched_text=relation_rule,
                start=0,
                end=0,
            )
        )

    if partition_evidence is not None:
        evidence.append(
            partition_evidence
        )

    evidence.extend(
        qualifier_evidence
    )

    return QuestionSemanticSignatureV2(
        operator=operator,
        left_operand=left_operand,
        right_operand=right_operand,
        intrinsic_partition=partition,
        qualifiers=qualifiers,
        evidence=tuple(
            evidence
        ),
    )


if __name__ == "__main__":
    samples = (
        "商品付款总金额平均摊到每个不同付款客户后是多少？",
        "成功付款商品总数量除以成功付款单据笔数是多少？",
        "每投入一元渠道营销费用能带来几元成功付款金额？",
    )

    for sample in samples:
        print("=" * 80)
        print(sample)
        print(
            extract_question_semantic_signature_v2(
                sample
            ).model_dump(
                mode="json"
            )
        )
