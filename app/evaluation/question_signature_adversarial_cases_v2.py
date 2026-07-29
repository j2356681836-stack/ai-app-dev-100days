from __future__ import annotations

import hashlib
import json
from enum import Enum

from pydantic import BaseModel, ConfigDict, model_validator

from app.semantic_layer.metric_signature_v2 import (
    IntrinsicPartition,
    SemanticOperand,
    SemanticQualifier,
)
from app.semantic_layer.question_signature_v2 import (
    QuestionOperator,
)


QUESTION_SIGNATURE_ADVERSARIAL_VERSION_V2 = (
    "beauty_bi_v2_question_signature_adversarial_1"
)


class QuestionSignatureCaseRoleV2(str, Enum):
    SUPPORTED_REPHRASE = "supported_rephrase"
    PARTIAL_STRUCTURE = "partial_structure"
    UNSUPPORTED_PARSEABLE = "unsupported_parseable"
    COLLISION = "collision"
    REVERSAL = "reversal"


class ExpectedQuestionSignatureV2(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    operator: QuestionOperator | None = None
    left_operand: SemanticOperand | None = None
    right_operand: SemanticOperand | None = None
    intrinsic_partition: IntrinsicPartition | None = None
    qualifiers: tuple[SemanticQualifier, ...] = ()

    @model_validator(mode="after")
    def validate_expected_structure(
        self,
    ) -> "ExpectedQuestionSignatureV2":
        if (
            self.operator != QuestionOperator.DIVIDE
            and self.right_operand is not None
        ):
            raise ValueError(
                "Only divide expected signatures may declare right_operand."
            )

        if (
            self.left_operand is not None
            and self.left_operand == self.right_operand
        ):
            raise ValueError(
                "Expected left/right operands must differ."
            )

        if len(self.qualifiers) != len(set(self.qualifiers)):
            raise ValueError(
                "Expected qualifiers must be unique."
            )

        return self


class QuestionSignatureAdversarialCaseV2(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    case_id: str
    role: QuestionSignatureCaseRoleV2
    family: str
    question: str
    expected: ExpectedQuestionSignatureV2
    note: str


def _case(
    case_id: str,
    role: QuestionSignatureCaseRoleV2,
    family: str,
    question: str,
    *,
    operator: QuestionOperator | None = None,
    left: SemanticOperand | None = None,
    right: SemanticOperand | None = None,
    partition: IntrinsicPartition | None = None,
    qualifiers: tuple[SemanticQualifier, ...] = (),
    note: str,
) -> QuestionSignatureAdversarialCaseV2:
    return QuestionSignatureAdversarialCaseV2(
        case_id=case_id,
        role=role,
        family=family,
        question=question,
        expected=ExpectedQuestionSignatureV2(
            operator=operator,
            left_operand=left,
            right_operand=right,
            intrinsic_partition=partition,
            qualifiers=qualifiers,
        ),
        note=note,
    )


QUESTION_SIGNATURE_ADVERSARIAL_CASES_V2 = (
    # -----------------------------------------------------------------
    # Supported semantic families — deliberately use fresh phrasings.
    # -----------------------------------------------------------------
    _case(
        "QSADV-001",
        QuestionSignatureCaseRoleV2.SUPPORTED_REPHRASE,
        "gmv",
        "本周期成交商品实际收进来的钱全部汇总是多少？",
        operator=QuestionOperator.SUM,
        left=SemanticOperand.PAID_AMOUNT,
        note="GMV: amount sum with colloquial revenue wording.",
    ),
    _case(
        "QSADV-002",
        QuestionSignatureCaseRoleV2.SUPPORTED_REPHRASE,
        "gmv",
        "把完成支付的商品金额累计起来",
        operator=QuestionOperator.SUM,
        left=SemanticOperand.PAID_AMOUNT,
        note="GMV: concise accumulation wording.",
    ),
    _case(
        "QSADV-003",
        QuestionSignatureCaseRoleV2.SUPPORTED_REPHRASE,
        "gross_margin",
        "成交商品收款扣掉商品成本以后，总共留下多少钱？",
        operator=QuestionOperator.SUM,
        left=SemanticOperand.GROSS_MARGIN_AMOUNT,
        qualifiers=(SemanticQualifier.PRODUCT_COST_BASIS,),
        note="Gross margin amount.",
    ),
    _case(
        "QSADV-004",
        QuestionSignatureCaseRoleV2.SUPPORTED_REPHRASE,
        "gross_margin",
        "已成交商品的收入和成本做差后累计金额",
        operator=QuestionOperator.SUM,
        left=SemanticOperand.GROSS_MARGIN_AMOUNT,
        qualifiers=(SemanticQualifier.PRODUCT_COST_BASIS,),
        note="Gross margin via difference wording.",
    ),
    _case(
        "QSADV-005",
        QuestionSignatureCaseRoleV2.SUPPORTED_REPHRASE,
        "gross_margin_rate",
        "成交收入扣成本后的余额，占成交收入本身几成？",
        operator=QuestionOperator.DIVIDE,
        left=SemanticOperand.GROSS_MARGIN_AMOUNT,
        right=SemanticOperand.PAID_AMOUNT,
        qualifiers=(SemanticQualifier.PRODUCT_COST_BASIS,),
        note="Margin ratio expressed as share.",
    ),
    _case(
        "QSADV-006",
        QuestionSignatureCaseRoleV2.SUPPORTED_REPHRASE,
        "gross_margin_rate",
        "每一元成交收入里有多少是扣除商品成本后留下的？",
        operator=QuestionOperator.DIVIDE,
        left=SemanticOperand.GROSS_MARGIN_AMOUNT,
        right=SemanticOperand.PAID_AMOUNT,
        qualifiers=(SemanticQualifier.PRODUCT_COST_BASIS,),
        note="Margin rate via per-yuan wording.",
    ),
    _case(
        "QSADV-007",
        QuestionSignatureCaseRoleV2.SUPPORTED_REPHRASE,
        "refund_rate",
        "最终完成退款的钱，占这些成交原始付款金额多少？",
        operator=QuestionOperator.DIVIDE,
        left=SemanticOperand.COMPLETED_REFUND_AMOUNT,
        right=SemanticOperand.PAID_AMOUNT,
        qualifiers=(SemanticQualifier.COMPLETED_REFUND_ONLY,),
        note="Refund amount ratio.",
    ),
    _case(
        "QSADV-008",
        QuestionSignatureCaseRoleV2.SUPPORTED_REPHRASE,
        "refund_rate",
        "按原成交月份归回去看，已完成退款金额和原成交金额之比",
        operator=QuestionOperator.DIVIDE,
        left=SemanticOperand.COMPLETED_REFUND_AMOUNT,
        right=SemanticOperand.PAID_AMOUNT,
        qualifiers=(
            SemanticQualifier.COMPLETED_REFUND_ONLY,
            SemanticQualifier.SALES_COHORT_ATTRIBUTION,
        ),
        note="Refund cohort attribution phrased differently.",
    ),
    _case(
        "QSADV-009",
        QuestionSignatureCaseRoleV2.SUPPORTED_REPHRASE,
        "roi",
        "渠道广告每花一元，能对应多少成交付款产出？",
        operator=QuestionOperator.DIVIDE,
        left=SemanticOperand.PAID_AMOUNT,
        right=SemanticOperand.MARKETING_SPEND,
        partition=IntrinsicPartition.CHANNEL,
        note="ROI amount/spend.",
    ),
    _case(
        "QSADV-010",
        QuestionSignatureCaseRoleV2.SUPPORTED_REPHRASE,
        "roi",
        "各平台成交金额相对于同期推广花费是几倍",
        operator=QuestionOperator.DIVIDE,
        left=SemanticOperand.PAID_AMOUNT,
        right=SemanticOperand.MARKETING_SPEND,
        partition=IntrinsicPartition.CHANNEL,
        qualifiers=(SemanticQualifier.SAME_WINDOW_SALES_SPEND,),
        note="ROI with same-window evidence.",
    ),
    _case(
        "QSADV-011",
        QuestionSignatureCaseRoleV2.SUPPORTED_REPHRASE,
        "cac",
        "每个平台的推广费用，平均分到首次在该平台成交的客户头上是多少？",
        operator=QuestionOperator.DIVIDE,
        left=SemanticOperand.MARKETING_SPEND,
        right=SemanticOperand.CHANNEL_FIRST_PAID_CUSTOMER,
        partition=IntrinsicPartition.CHANNEL,
        qualifiers=(SemanticQualifier.FULL_HISTORY_CHANNEL_FIRST_PAID,),
        note="CAC using per-channel first-paid customer basis.",
    ),
    _case(
        "QSADV-012",
        QuestionSignatureCaseRoleV2.SUPPORTED_REPHRASE,
        "cac",
        "渠道获客投入除以该渠道历史首次成交客户数",
        operator=QuestionOperator.DIVIDE,
        left=SemanticOperand.MARKETING_SPEND,
        right=SemanticOperand.CHANNEL_FIRST_PAID_CUSTOMER,
        partition=IntrinsicPartition.CHANNEL,
        qualifiers=(SemanticQualifier.FULL_HISTORY_CHANNEL_FIRST_PAID,),
        note="CAC direct quotient phrasing.",
    ),
    _case(
        "QSADV-013",
        QuestionSignatureCaseRoleV2.SUPPORTED_REPHRASE,
        "brand_new",
        "全品牌历史里，本期才第一次成交的客户共有多少？",
        operator=QuestionOperator.COUNT,
        left=SemanticOperand.GLOBAL_FIRST_PAID_CUSTOMER,
        qualifiers=(SemanticQualifier.FULL_HISTORY_BRAND_FIRST_PAID,),
        note="Brand first-paid count.",
    ),
    _case(
        "QSADV-014",
        QuestionSignatureCaseRoleV2.SUPPORTED_REPHRASE,
        "brand_new",
        "先找每位客户在品牌内最早的成交，再数最早成交落在本期的人",
        operator=QuestionOperator.COUNT,
        left=SemanticOperand.GLOBAL_FIRST_PAID_CUSTOMER,
        qualifiers=(SemanticQualifier.FULL_HISTORY_BRAND_FIRST_PAID,),
        note="Brand first-paid procedural paraphrase.",
    ),
    _case(
        "QSADV-015",
        QuestionSignatureCaseRoleV2.SUPPORTED_REPHRASE,
        "channel_new",
        "按渠道分别看，每位客户第一次在该渠道成交的人数",
        operator=QuestionOperator.COUNT,
        left=SemanticOperand.CHANNEL_FIRST_PAID_CUSTOMER,
        partition=IntrinsicPartition.CHANNEL,
        qualifiers=(SemanticQualifier.FULL_HISTORY_CHANNEL_FIRST_PAID,),
        note="Channel first-paid count.",
    ),
    _case(
        "QSADV-016",
        QuestionSignatureCaseRoleV2.SUPPORTED_REPHRASE,
        "channel_new",
        "各平台把客户历史首笔成交找出来，再统计本期首笔人数",
        operator=QuestionOperator.COUNT,
        left=SemanticOperand.CHANNEL_FIRST_PAID_CUSTOMER,
        partition=IntrinsicPartition.CHANNEL,
        qualifiers=(SemanticQualifier.FULL_HISTORY_CHANNEL_FIRST_PAID,),
        note="Channel first-paid procedural paraphrase.",
    ),
    _case(
        "QSADV-017",
        QuestionSignatureCaseRoleV2.SUPPORTED_REPHRASE,
        "repeat_rate",
        "本期成交客户里，至少跨两个成交日购买的人占多少？",
        operator=QuestionOperator.DIVIDE,
        left=SemanticOperand.REPEAT_DISTINCT_PAID_DATE_CUSTOMER,
        right=SemanticOperand.PAID_BUYER,
        qualifiers=(SemanticQualifier.DISTINCT_PAID_DATES_GE_2,),
        note="Cross-date repeat rate.",
    ),
    _case(
        "QSADV-018",
        QuestionSignatureCaseRoleV2.SUPPORTED_REPHRASE,
        "repeat_rate",
        "所有付款买家中，在两个不同日期都成交过的买家比例",
        operator=QuestionOperator.DIVIDE,
        left=SemanticOperand.REPEAT_DISTINCT_PAID_DATE_CUSTOMER,
        right=SemanticOperand.PAID_BUYER,
        qualifiers=(SemanticQualifier.DISTINCT_PAID_DATES_GE_2,),
        note="Cross-date repeat share.",
    ),
    _case(
        "QSADV-019",
        QuestionSignatureCaseRoleV2.SUPPORTED_REPHRASE,
        "member_share",
        "按交易发生时是否已有会员等级判断，会员成交金额占全部成交金额多少？",
        operator=QuestionOperator.DIVIDE,
        left=SemanticOperand.PAYMENT_TIME_MEMBER_PAID_AMOUNT,
        right=SemanticOperand.PAID_AMOUNT,
        qualifiers=(SemanticQualifier.PAYMENT_TIME_MEMBERSHIP_SNAPSHOT,),
        note="Payment-time membership share.",
    ),
    _case(
        "QSADV-020",
        QuestionSignatureCaseRoleV2.SUPPORTED_REPHRASE,
        "member_share",
        "只算成交那一刻已经是会员的金额，这部分在总成交额里占多少",
        operator=QuestionOperator.DIVIDE,
        left=SemanticOperand.PAYMENT_TIME_MEMBER_PAID_AMOUNT,
        right=SemanticOperand.PAID_AMOUNT,
        qualifiers=(SemanticQualifier.PAYMENT_TIME_MEMBERSHIP_SNAPSHOT,),
        note="Payment-time member basis, colloquial.",
    ),
    _case(
        "QSADV-021",
        QuestionSignatureCaseRoleV2.SUPPORTED_REPHRASE,
        "buyer_count",
        "成交记录里的客户去重以后有多少位？",
        operator=QuestionOperator.COUNT,
        left=SemanticOperand.PAID_BUYER,
        note="Distinct paid buyers.",
    ),
    _case(
        "QSADV-022",
        QuestionSignatureCaseRoleV2.SUPPORTED_REPHRASE,
        "buyer_count",
        "至少成交过一次的不同买家人数",
        operator=QuestionOperator.COUNT,
        left=SemanticOperand.PAID_BUYER,
        note="Distinct paid buyers via buyer wording.",
    ),
    _case(
        "QSADV-023",
        QuestionSignatureCaseRoleV2.SUPPORTED_REPHRASE,
        "order_count",
        "一共发生了多少笔成交订单？",
        operator=QuestionOperator.COUNT,
        left=SemanticOperand.PAID_ORDER,
        note="Paid order count.",
    ),
    _case(
        "QSADV-024",
        QuestionSignatureCaseRoleV2.SUPPORTED_REPHRASE,
        "order_count",
        "把成交成功的订单逐单数一遍有几单",
        operator=QuestionOperator.COUNT,
        left=SemanticOperand.PAID_ORDER,
        note="Paid order transaction count.",
    ),
    _case(
        "QSADV-025",
        QuestionSignatureCaseRoleV2.SUPPORTED_REPHRASE,
        "units_sold",
        "成交商品总共卖出了多少件？",
        operator=QuestionOperator.SUM,
        left=SemanticOperand.PAID_UNITS,
        note="Paid units sum.",
    ),
    _case(
        "QSADV-026",
        QuestionSignatureCaseRoleV2.SUPPORTED_REPHRASE,
        "units_sold",
        "所有成交明细的件数加总",
        operator=QuestionOperator.SUM,
        left=SemanticOperand.PAID_UNITS,
        note="Units sum using 件数.",
    ),
    _case(
        "QSADV-027",
        QuestionSignatureCaseRoleV2.SUPPORTED_REPHRASE,
        "spending_per_buyer",
        "平均每位成交买家贡献多少成交金额？",
        operator=QuestionOperator.DIVIDE,
        left=SemanticOperand.PAID_AMOUNT,
        right=SemanticOperand.PAID_BUYER,
        note="Amount per buyer.",
    ),
    _case(
        "QSADV-028",
        QuestionSignatureCaseRoleV2.SUPPORTED_REPHRASE,
        "spending_per_buyer",
        "总成交金额除以去重后的成交客户数是多少",
        operator=QuestionOperator.DIVIDE,
        left=SemanticOperand.PAID_AMOUNT,
        right=SemanticOperand.PAID_BUYER,
        note="Amount divided by distinct paid buyers.",
    ),
    _case(
        "QSADV-029",
        QuestionSignatureCaseRoleV2.SUPPORTED_REPHRASE,
        "ipt",
        "每一笔成交订单平均包含多少件商品？",
        operator=QuestionOperator.DIVIDE,
        left=SemanticOperand.PAID_UNITS,
        right=SemanticOperand.PAID_ORDER,
        note="Units per paid order.",
    ),
    _case(
        "QSADV-030",
        QuestionSignatureCaseRoleV2.SUPPORTED_REPHRASE,
        "ipt",
        "成交件数除以成交订单数",
        operator=QuestionOperator.DIVIDE,
        left=SemanticOperand.PAID_UNITS,
        right=SemanticOperand.PAID_ORDER,
        note="Units/order direct quotient.",
    ),
    _case(
        "QSADV-031",
        QuestionSignatureCaseRoleV2.SUPPORTED_REPHRASE,
        "aus",
        "一笔成交订单平均对应多少成交金额？",
        operator=QuestionOperator.DIVIDE,
        left=SemanticOperand.PAID_AMOUNT,
        right=SemanticOperand.PAID_ORDER,
        note="Amount per order.",
    ),
    _case(
        "QSADV-032",
        QuestionSignatureCaseRoleV2.SUPPORTED_REPHRASE,
        "aus",
        "成交总额除以成交单量是多少",
        operator=QuestionOperator.DIVIDE,
        left=SemanticOperand.PAID_AMOUNT,
        right=SemanticOperand.PAID_ORDER,
        note="Amount/order direct quotient.",
    ),
    _case(
        "QSADV-033",
        QuestionSignatureCaseRoleV2.SUPPORTED_REPHRASE,
        "purchase_frequency",
        "每位成交客户平均产生多少笔成交订单？",
        operator=QuestionOperator.DIVIDE,
        left=SemanticOperand.PAID_ORDER,
        right=SemanticOperand.PAID_BUYER,
        note="Orders per buyer.",
    ),
    _case(
        "QSADV-034",
        QuestionSignatureCaseRoleV2.SUPPORTED_REPHRASE,
        "purchase_frequency",
        "成交订单数平均分到每个去重买家后是多少",
        operator=QuestionOperator.DIVIDE,
        left=SemanticOperand.PAID_ORDER,
        right=SemanticOperand.PAID_BUYER,
        note="Order/buyer.",
    ),
    _case(
        "QSADV-035",
        QuestionSignatureCaseRoleV2.SUPPORTED_REPHRASE,
        "repeat_count",
        "本期有多少买家至少在两个不同成交日期买过？",
        operator=QuestionOperator.COUNT,
        left=SemanticOperand.REPEAT_DISTINCT_PAID_DATE_CUSTOMER,
        qualifiers=(SemanticQualifier.DISTINCT_PAID_DATES_GE_2,),
        note="Cross-date repeat buyer count.",
    ),
    _case(
        "QSADV-036",
        QuestionSignatureCaseRoleV2.SUPPORTED_REPHRASE,
        "repeat_count",
        "不同成交日达到两个及以上的客户人数",
        operator=QuestionOperator.COUNT,
        left=SemanticOperand.REPEAT_DISTINCT_PAID_DATE_CUSTOMER,
        qualifiers=(SemanticQualifier.DISTINCT_PAID_DATES_GE_2,),
        note="Repeat count structural definition.",
    ),
    _case(
        "QSADV-037",
        QuestionSignatureCaseRoleV2.SUPPORTED_REPHRASE,
        "multi_order_count",
        "本期成交订单达到两单及以上的客户有多少？",
        operator=QuestionOperator.COUNT,
        left=SemanticOperand.MULTI_PAID_ORDER_CUSTOMER,
        qualifiers=(SemanticQualifier.PAID_ORDERS_GE_2,),
        note="Multi-order customer count.",
    ),
    _case(
        "QSADV-038",
        QuestionSignatureCaseRoleV2.SUPPORTED_REPHRASE,
        "multi_order_count",
        "不管是不是同一天，只要成交两单以上就算，这样的客户人数",
        operator=QuestionOperator.COUNT,
        left=SemanticOperand.MULTI_PAID_ORDER_CUSTOMER,
        qualifiers=(SemanticQualifier.PAID_ORDERS_GE_2,),
        note="Multi-order explicitly contrasted with cross-date repeat.",
    ),

    # -----------------------------------------------------------------
    # Unsupported but structurally parseable — extractor should recover
    # structure without inventing a current Metric.
    # -----------------------------------------------------------------
    _case(
        "QSADV-039",
        QuestionSignatureCaseRoleV2.UNSUPPORTED_PARSEABLE,
        "average_unit_price",
        "成交金额平均到每一件卖出的商品上是多少？",
        operator=QuestionOperator.DIVIDE,
        left=SemanticOperand.PAID_AMOUNT,
        right=SemanticOperand.PAID_UNITS,
        note="Unsupported current metric: amount / units.",
    ),
    _case(
        "QSADV-040",
        QuestionSignatureCaseRoleV2.UNSUPPORTED_PARSEABLE,
        "buyer_per_order",
        "每笔成交订单平均对应多少个不同成交客户？",
        operator=QuestionOperator.DIVIDE,
        left=SemanticOperand.PAID_BUYER,
        right=SemanticOperand.PAID_ORDER,
        note="Unsupported reverse structure: buyer / order.",
    ),
    _case(
        "QSADV-041",
        QuestionSignatureCaseRoleV2.UNSUPPORTED_PARSEABLE,
        "units_per_buyer",
        "每位成交客户平均买了多少件商品？",
        operator=QuestionOperator.DIVIDE,
        left=SemanticOperand.PAID_UNITS,
        right=SemanticOperand.PAID_BUYER,
        note="Unsupported current metric: units / buyer.",
    ),
    _case(
        "QSADV-042",
        QuestionSignatureCaseRoleV2.UNSUPPORTED_PARSEABLE,
        "buyers_per_amount",
        "每一百元成交金额对应多少位不同买家？",
        operator=QuestionOperator.DIVIDE,
        left=SemanticOperand.PAID_BUYER,
        right=SemanticOperand.PAID_AMOUNT,
        note="Unsupported reverse structure: buyer / amount.",
    ),

    # -----------------------------------------------------------------
    # Reversal: direction matters.
    # -----------------------------------------------------------------
    _case(
        "QSADV-043",
        QuestionSignatureCaseRoleV2.REVERSAL,
        "roi_reverse",
        "成交付款产出除以渠道推广费用",
        operator=QuestionOperator.DIVIDE,
        left=SemanticOperand.PAID_AMOUNT,
        right=SemanticOperand.MARKETING_SPEND,
        partition=IntrinsicPartition.CHANNEL,
        note="Explicit ROI direction.",
    ),
    _case(
        "QSADV-044",
        QuestionSignatureCaseRoleV2.REVERSAL,
        "roi_inverted",
        "渠道推广费用除以成交付款金额",
        operator=QuestionOperator.DIVIDE,
        left=SemanticOperand.MARKETING_SPEND,
        right=SemanticOperand.PAID_AMOUNT,
        partition=IntrinsicPartition.CHANNEL,
        note="Inverted ROI direction must remain inverted.",
    ),
    _case(
        "QSADV-045",
        QuestionSignatureCaseRoleV2.REVERSAL,
        "frequency_reverse",
        "成交订单数除以成交客户数",
        operator=QuestionOperator.DIVIDE,
        left=SemanticOperand.PAID_ORDER,
        right=SemanticOperand.PAID_BUYER,
        note="Order / buyer.",
    ),
    _case(
        "QSADV-046",
        QuestionSignatureCaseRoleV2.REVERSAL,
        "frequency_inverted",
        "成交客户数除以成交订单数",
        operator=QuestionOperator.DIVIDE,
        left=SemanticOperand.PAID_BUYER,
        right=SemanticOperand.PAID_ORDER,
        note="Buyer / order must not be normalized to known Metric.",
    ),

    # -----------------------------------------------------------------
    # Partial structure — no silent filling.
    # -----------------------------------------------------------------
    _case(
        "QSADV-047",
        QuestionSignatureCaseRoleV2.PARTIAL_STRUCTURE,
        "generic_average",
        "平均消费大概是多少？",
        operator=QuestionOperator.DIVIDE,
        note="Operator visible; operands absent.",
    ),
    _case(
        "QSADV-048",
        QuestionSignatureCaseRoleV2.PARTIAL_STRUCTURE,
        "generic_repeat",
        "复购情况怎么样？",
        note="No safe core structure should be invented.",
    ),
    _case(
        "QSADV-049",
        QuestionSignatureCaseRoleV2.PARTIAL_STRUCTURE,
        "generic_new_customer",
        "本期新客有多少？",
        operator=QuestionOperator.COUNT,
        note="Brand/channel first-paid basis absent.",
    ),
    _case(
        "QSADV-050",
        QuestionSignatureCaseRoleV2.PARTIAL_STRUCTURE,
        "generic_amount",
        "成交金额怎么样？",
        left=SemanticOperand.PAID_AMOUNT,
        note="Amount atom visible but aggregation not explicit.",
    ),

    # -----------------------------------------------------------------
    # Collision / mixed evidence — do not splice unrelated operands into
    # a fabricated ratio.
    # -----------------------------------------------------------------
    _case(
        "QSADV-051",
        QuestionSignatureCaseRoleV2.COLLISION,
        "amount_and_buyer_parallel",
        "同时告诉我成交总金额和成交客户数",
        note="Two requested metrics, not a ratio.",
    ),
    _case(
        "QSADV-052",
        QuestionSignatureCaseRoleV2.COLLISION,
        "order_and_units_parallel",
        "我想同时看成交订单数以及卖出的商品件数",
        note="Two requested measures, no divide relationship.",
    ),
    _case(
        "QSADV-053",
        QuestionSignatureCaseRoleV2.COLLISION,
        "roi_and_cac_parallel",
        "渠道投放我既想看成交产出，也想看首次成交客户数量",
        partition=IntrinsicPartition.CHANNEL,
        note="Multiple channel business objects, no unique operator.",
    ),
    _case(
        "QSADV-054",
        QuestionSignatureCaseRoleV2.COLLISION,
        "repeat_and_multi_parallel",
        "分别看跨两个成交日的客户数，以及成交两单以上的客户数",
        note="Two repeat-family metrics, no single left operand.",
    ),

    # -----------------------------------------------------------------
    # Boundary-sensitive semantic distinctions at signature layer.
    # -----------------------------------------------------------------
    _case(
        "QSADV-055",
        QuestionSignatureCaseRoleV2.SUPPORTED_REPHRASE,
        "same_day_multi_order",
        "同一天成交两单也算，统计达到两单以上的客户人数",
        operator=QuestionOperator.COUNT,
        left=SemanticOperand.MULTI_PAID_ORDER_CUSTOMER,
        qualifiers=(SemanticQualifier.PAID_ORDERS_GE_2,),
        note="Same-day two orders => multi-order, not cross-date repeat.",
    ),
    _case(
        "QSADV-056",
        QuestionSignatureCaseRoleV2.SUPPORTED_REPHRASE,
        "cross_date_repeat",
        "必须至少两个不同成交日才算，符合条件的客户数",
        operator=QuestionOperator.COUNT,
        left=SemanticOperand.REPEAT_DISTINCT_PAID_DATE_CUSTOMER,
        qualifiers=(SemanticQualifier.DISTINCT_PAID_DATES_GE_2,),
        note="Explicit cross-date repeat.",
    ),
    _case(
        "QSADV-057",
        QuestionSignatureCaseRoleV2.SUPPORTED_REPHRASE,
        "brand_vs_channel",
        "只按品牌全历史判断第一次成交的客户人数",
        operator=QuestionOperator.COUNT,
        left=SemanticOperand.GLOBAL_FIRST_PAID_CUSTOMER,
        qualifiers=(SemanticQualifier.FULL_HISTORY_BRAND_FIRST_PAID,),
        note="Explicit brand-first basis.",
    ),
    _case(
        "QSADV-058",
        QuestionSignatureCaseRoleV2.SUPPORTED_REPHRASE,
        "brand_vs_channel",
        "按每个平台自己的历史判断首次成交客户数",
        operator=QuestionOperator.COUNT,
        left=SemanticOperand.CHANNEL_FIRST_PAID_CUSTOMER,
        partition=IntrinsicPartition.CHANNEL,
        qualifiers=(SemanticQualifier.FULL_HISTORY_CHANNEL_FIRST_PAID,),
        note="Explicit channel-first basis.",
    ),
    _case(
        "QSADV-059",
        QuestionSignatureCaseRoleV2.SUPPORTED_REPHRASE,
        "membership_snapshot",
        "会员身份按成交当刻的等级快照判断，会员成交额占总成交额多少",
        operator=QuestionOperator.DIVIDE,
        left=SemanticOperand.PAYMENT_TIME_MEMBER_PAID_AMOUNT,
        right=SemanticOperand.PAID_AMOUNT,
        qualifiers=(SemanticQualifier.PAYMENT_TIME_MEMBERSHIP_SNAPSHOT,),
        note="Payment-time snapshot explicit.",
    ),
    _case(
        "QSADV-060",
        QuestionSignatureCaseRoleV2.SUPPORTED_REPHRASE,
        "refund_sales_cohort",
        "退款按原订单成交期回溯归属，完成退款金额占原成交金额的比例",
        operator=QuestionOperator.DIVIDE,
        left=SemanticOperand.COMPLETED_REFUND_AMOUNT,
        right=SemanticOperand.PAID_AMOUNT,
        qualifiers=(
            SemanticQualifier.COMPLETED_REFUND_ONLY,
            SemanticQualifier.SALES_COHORT_ATTRIBUTION,
        ),
        note="Refund sales-cohort attribution explicit.",
    ),
)


def canonical_question_signature_adversarial_cases_v2() -> bytes:
    payload = {
        "version": QUESTION_SIGNATURE_ADVERSARIAL_VERSION_V2,
        "cases": [
            case.model_dump(
                mode="json"
            )
            for case in QUESTION_SIGNATURE_ADVERSARIAL_CASES_V2
        ],
    }

    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def question_signature_adversarial_fingerprint_v2() -> str:
    return hashlib.sha256(
        canonical_question_signature_adversarial_cases_v2()
    ).hexdigest()


if __name__ == "__main__":
    print(
        "Question Signature Fresh Adversarial Cases V2"
    )
    print(
        "Total:",
        len(
            QUESTION_SIGNATURE_ADVERSARIAL_CASES_V2
        ),
    )
    print(
        "Fingerprint:",
        question_signature_adversarial_fingerprint_v2(),
    )
