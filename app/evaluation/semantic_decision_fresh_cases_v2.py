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
from app.semantic_layer.question_semantic_parser_v2 import (
    QuestionSemanticParseStatusV2,
)
from app.semantic_layer.question_signature_v2 import QuestionOperator
from app.semantic_layer.semantic_decision_service_v2 import (
    SemanticDecisionStatusV2,
)


SEMANTIC_DECISION_FRESH_CASES_VERSION_V2 = (
    "beauty_bi_v2_semantic_decision_fresh_holdout_1"
)


class FreshCaseRoleV2(str, Enum):
    MATCHED_REPHRASE = "matched_rephrase"
    CLARIFICATION = "clarification"
    UNSUPPORTED_PARSEABLE = "unsupported_parseable"
    REVERSAL = "reversal"
    MULTIPLE_INTENTS = "multiple_intents"
    AUTHORIZATION = "authorization"


class ExpectedFreshQuestionSignatureV2(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    operator: QuestionOperator | None = None
    left_operand: SemanticOperand | None = None
    right_operand: SemanticOperand | None = None
    intrinsic_partition: IntrinsicPartition | None = None
    qualifiers: tuple[SemanticQualifier, ...] = ()

    @model_validator(mode="after")
    def validate_structure(self) -> "ExpectedFreshQuestionSignatureV2":
        if self.operator != QuestionOperator.DIVIDE and self.right_operand is not None:
            raise ValueError("Only divide signatures may declare right_operand.")
        if self.left_operand is not None and self.left_operand == self.right_operand:
            raise ValueError("Expected left/right operands must differ.")
        if len(self.qualifiers) != len(set(self.qualifiers)):
            raise ValueError("Expected qualifiers must be unique.")
        return self


class SemanticDecisionFreshCaseV2(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str
    role: FreshCaseRoleV2
    family: str
    question: str
    expected_parser_status: QuestionSemanticParseStatusV2
    expected_signature: ExpectedFreshQuestionSignatureV2 | None
    expected_semantic_status: SemanticDecisionStatusV2
    expected_metric_name: str | None = None
    expected_candidates: tuple[str, ...] = ()
    expected_ranking_applied: bool | None = None
    allowed_metric_names: tuple[str, ...] = ()
    note: str

    @model_validator(mode="after")
    def validate_case_contract(self) -> "SemanticDecisionFreshCaseV2":
        parsed = self.expected_parser_status == QuestionSemanticParseStatusV2.PARSED
        if parsed != (self.expected_signature is not None):
            raise ValueError("Expected signature must exist exactly when parser status is PARSED.")

        matched = self.expected_semantic_status == SemanticDecisionStatusV2.MATCHED
        if matched != (self.expected_metric_name is not None):
            raise ValueError("Expected metric_name must exist exactly for MATCHED cases.")

        clarification = (
            self.expected_semantic_status
            == SemanticDecisionStatusV2.NEEDS_CLARIFICATION
        )
        if clarification != bool(self.expected_candidates):
            raise ValueError("Expected candidates must exist exactly for clarification cases.")

        if len(self.expected_candidates) != len(set(self.expected_candidates)):
            raise ValueError("Expected candidates must be unique.")
        if len(self.allowed_metric_names) != len(set(self.allowed_metric_names)):
            raise ValueError("Allowed metric names must be unique.")
        return self


def sig(
    *,
    operator: QuestionOperator | None = None,
    left: SemanticOperand | None = None,
    right: SemanticOperand | None = None,
    partition: IntrinsicPartition | None = None,
    qualifiers: tuple[SemanticQualifier, ...] = (),
) -> ExpectedFreshQuestionSignatureV2:
    return ExpectedFreshQuestionSignatureV2(
        operator=operator,
        left_operand=left,
        right_operand=right,
        intrinsic_partition=partition,
        qualifiers=qualifiers,
    )


def case(
    case_id: str,
    role: FreshCaseRoleV2,
    family: str,
    question: str,
    *,
    parser_status: QuestionSemanticParseStatusV2,
    signature: ExpectedFreshQuestionSignatureV2 | None,
    semantic_status: SemanticDecisionStatusV2,
    metric_name: str | None = None,
    candidates: tuple[str, ...] = (),
    ranking_applied: bool | None = None,
    allowed_metric_names: tuple[str, ...] = (),
    note: str,
) -> SemanticDecisionFreshCaseV2:
    return SemanticDecisionFreshCaseV2(
        case_id=case_id,
        role=role,
        family=family,
        question=question,
        expected_parser_status=parser_status,
        expected_signature=signature,
        expected_semantic_status=semantic_status,
        expected_metric_name=metric_name,
        expected_candidates=candidates,
        expected_ranking_applied=ranking_applied,
        allowed_metric_names=allowed_metric_names,
        note=note,
    )


SEMANTIC_DECISION_FRESH_CASES_V2 = (
    case(
        "SDFRESH-001", FreshCaseRoleV2.MATCHED_REPHRASE, "gmv",
        "这段时间成功付款商品一共收了多少实付款？",
        parser_status=QuestionSemanticParseStatusV2.PARSED,
        signature=sig(operator=QuestionOperator.SUM, left=SemanticOperand.PAID_AMOUNT),
        semantic_status=SemanticDecisionStatusV2.MATCHED,
        metric_name="gmv", ranking_applied=False,
        note="GMV using total received-payment wording.",
    ),
    case(
        "SDFRESH-002", FreshCaseRoleV2.MATCHED_REPHRASE, "gross_margin_rate",
        "每一百元商品成交收入，扣除商品成本后能留下多少元？",
        parser_status=QuestionSemanticParseStatusV2.PARSED,
        signature=sig(
            operator=QuestionOperator.DIVIDE,
            left=SemanticOperand.GROSS_MARGIN_AMOUNT,
            right=SemanticOperand.PAID_AMOUNT,
            qualifiers=(SemanticQualifier.PRODUCT_COST_BASIS,),
        ),
        semantic_status=SemanticDecisionStatusV2.MATCHED,
        metric_name="gross_margin_rate", ranking_applied=False,
        note="Gross-margin rate expressed as retained amount per revenue.",
    ),
    case(
        "SDFRESH-003", FreshCaseRoleV2.MATCHED_REPHRASE, "refund_rate",
        "把退款归回原销售周期后，完成退款金额占对应成交额的百分比是多少？",
        parser_status=QuestionSemanticParseStatusV2.PARSED,
        signature=sig(
            operator=QuestionOperator.DIVIDE,
            left=SemanticOperand.COMPLETED_REFUND_AMOUNT,
            right=SemanticOperand.PAID_AMOUNT,
            qualifiers=(SemanticQualifier.SALES_COHORT_ATTRIBUTION,),
        ),
        semantic_status=SemanticDecisionStatusV2.MATCHED,
        metric_name="refund_rate", ranking_applied=False,
        note="Refund rate with original-sales-period attribution.",
    ),
    case(
        "SDFRESH-004", FreshCaseRoleV2.MATCHED_REPHRASE, "roi",
        "同一统计周期内，各渠道每元营销投入带来多少成交金额？",
        parser_status=QuestionSemanticParseStatusV2.PARSED,
        signature=sig(
            operator=QuestionOperator.DIVIDE,
            left=SemanticOperand.PAID_AMOUNT,
            right=SemanticOperand.MARKETING_SPEND,
            partition=IntrinsicPartition.CHANNEL,
            qualifiers=(SemanticQualifier.SAME_WINDOW_SALES_SPEND,),
        ),
        semantic_status=SemanticDecisionStatusV2.MATCHED,
        metric_name="roi", ranking_applied=False,
        note="ROI with channel and shared analysis window.",
    ),
    case(
        "SDFRESH-005", FreshCaseRoleV2.MATCHED_REPHRASE, "channel_new_customer",
        "按各平台自己的成交历史，本期首次付款客户一共有多少人？",
        parser_status=QuestionSemanticParseStatusV2.PARSED,
        signature=sig(
            operator=QuestionOperator.COUNT,
            left=SemanticOperand.CHANNEL_FIRST_PAID_CUSTOMER,
            partition=IntrinsicPartition.CHANNEL,
        ),
        semantic_status=SemanticDecisionStatusV2.MATCHED,
        metric_name="channel_paid_new_customer_count", ranking_applied=False,
        note="Channel-local first-paid customer count.",
    ),
    case(
        "SDFRESH-006", FreshCaseRoleV2.MATCHED_REPHRASE, "purchase_frequency",
        "去重后的成交买家平均各自下了几笔成功订单？",
        parser_status=QuestionSemanticParseStatusV2.PARSED,
        signature=sig(
            operator=QuestionOperator.DIVIDE,
            left=SemanticOperand.PAID_ORDER,
            right=SemanticOperand.PAID_BUYER,
        ),
        semantic_status=SemanticDecisionStatusV2.MATCHED,
        metric_name="purchase_frequency", ranking_applied=False,
        note="Paid orders per distinct paid buyer.",
    ),
    case(
        "SDFRESH-007", FreshCaseRoleV2.CLARIFICATION, "generic_average_consumption",
        "平均消费金额大约有多少？",
        parser_status=QuestionSemanticParseStatusV2.PARSED,
        signature=sig(operator=QuestionOperator.DIVIDE),
        semantic_status=SemanticDecisionStatusV2.NEEDS_CLARIFICATION,
        candidates=("spending_per_buyer", "aus"), ranking_applied=True,
        note="Average consumption lacks buyer/order denominator.",
    ),
    case(
        "SDFRESH-008", FreshCaseRoleV2.CLARIFICATION, "generic_new_customer",
        "本月新客总共有多少位？",
        parser_status=QuestionSemanticParseStatusV2.PARSED,
        signature=sig(operator=QuestionOperator.COUNT),
        semantic_status=SemanticDecisionStatusV2.NEEDS_CLARIFICATION,
        candidates=(
            "brand_paid_new_customer_count",
            "channel_paid_new_customer_count",
        ),
        ranking_applied=True,
        note="New-customer basis is not identified as brand or channel.",
    ),
    case(
        "SDFRESH-009", FreshCaseRoleV2.UNSUPPORTED_PARSEABLE, "units_per_buyer",
        "把已售商品件数均摊到去重付款买家，每人是多少件？",
        parser_status=QuestionSemanticParseStatusV2.PARSED,
        signature=sig(
            operator=QuestionOperator.DIVIDE,
            left=SemanticOperand.PAID_UNITS,
            right=SemanticOperand.PAID_BUYER,
        ),
        semantic_status=SemanticDecisionStatusV2.UNSUPPORTED,
        ranking_applied=False,
        note="Current catalog has no paid-units per paid-buyer Metric.",
    ),
    case(
        "SDFRESH-010", FreshCaseRoleV2.UNSUPPORTED_PARSEABLE, "buyers_per_amount",
        "每一万元成交额能对应多少位去重付款客户？",
        parser_status=QuestionSemanticParseStatusV2.PARSED,
        signature=sig(
            operator=QuestionOperator.DIVIDE,
            left=SemanticOperand.PAID_BUYER,
            right=SemanticOperand.PAID_AMOUNT,
        ),
        semantic_status=SemanticDecisionStatusV2.UNSUPPORTED,
        ranking_applied=False,
        note="Reverse buyer/amount structure is unsupported.",
    ),
    case(
        "SDFRESH-011", FreshCaseRoleV2.REVERSAL, "roi_inverse",
        "每一元成交额对应多少渠道投放费用？",
        parser_status=QuestionSemanticParseStatusV2.PARSED,
        signature=sig(
            operator=QuestionOperator.DIVIDE,
            left=SemanticOperand.MARKETING_SPEND,
            right=SemanticOperand.PAID_AMOUNT,
            partition=IntrinsicPartition.CHANNEL,
        ),
        semantic_status=SemanticDecisionStatusV2.UNSUPPORTED,
        ranking_applied=False,
        note="Marketing spend / paid amount must not become ROI.",
    ),
    case(
        "SDFRESH-012", FreshCaseRoleV2.REVERSAL, "ipt_inverse",
        "每件已成交商品平均对应多少笔成功付款订单？",
        parser_status=QuestionSemanticParseStatusV2.PARSED,
        signature=sig(
            operator=QuestionOperator.DIVIDE,
            left=SemanticOperand.PAID_ORDER,
            right=SemanticOperand.PAID_UNITS,
        ),
        semantic_status=SemanticDecisionStatusV2.UNSUPPORTED,
        ranking_applied=False,
        note="Paid order / paid units must not become IPT.",
    ),
    case(
        "SDFRESH-013", FreshCaseRoleV2.MULTIPLE_INTENTS, "three_parallel_measures",
        "请分别给出成交买家数、成交订单数和成交件数",
        parser_status=QuestionSemanticParseStatusV2.MULTIPLE_INTENTS,
        signature=None,
        semantic_status=SemanticDecisionStatusV2.MULTIPLE_INTENTS,
        ranking_applied=False,
        note="Three parallel measures are not one semantic structure.",
    ),
    case(
        "SDFRESH-014", FreshCaseRoleV2.MULTIPLE_INTENTS, "roi_and_cac",
        "我既要看渠道投放回报，也要看渠道获客成本",
        parser_status=QuestionSemanticParseStatusV2.MULTIPLE_INTENTS,
        signature=None,
        semantic_status=SemanticDecisionStatusV2.MULTIPLE_INTENTS,
        ranking_applied=False,
        note="ROI and CAC are two independent channel intents.",
    ),
    case(
        "SDFRESH-015", FreshCaseRoleV2.AUTHORIZATION, "gmv_denied",
        "成功付款商品的总实收额是多少？",
        parser_status=QuestionSemanticParseStatusV2.PARSED,
        signature=sig(operator=QuestionOperator.SUM, left=SemanticOperand.PAID_AMOUNT),
        semantic_status=SemanticDecisionStatusV2.UNSUPPORTED,
        ranking_applied=False,
        allowed_metric_names=("buyer_count", "order_count"),
        note="GMV is requested but unavailable in visible scope.",
    ),
    case(
        "SDFRESH-016", FreshCaseRoleV2.AUTHORIZATION, "visible_uniqueness",
        "本周新客人数是多少？",
        parser_status=QuestionSemanticParseStatusV2.PARSED,
        signature=sig(operator=QuestionOperator.COUNT),
        semantic_status=SemanticDecisionStatusV2.MATCHED,
        metric_name="channel_paid_new_customer_count",
        ranking_applied=False,
        allowed_metric_names=("channel_paid_new_customer_count",),
        note=(
            "Visible scope leaves one compatible Metric; this records visible "
            "uniqueness, not global semantic uniqueness."
        ),
    ),
)


def canonical_semantic_decision_fresh_cases_v2() -> bytes:
    payload = {
        "version": SEMANTIC_DECISION_FRESH_CASES_VERSION_V2,
        "cases": [
            {
                **item.model_dump(
                    mode="json",
                    exclude={"expected_candidates", "allowed_metric_names"},
                ),
                "expected_candidates": sorted(item.expected_candidates),
                "allowed_metric_names": sorted(item.allowed_metric_names),
            }
            for item in SEMANTIC_DECISION_FRESH_CASES_V2
        ],
    }
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def semantic_decision_fresh_cases_fingerprint_v2() -> str:
    return hashlib.sha256(
        canonical_semantic_decision_fresh_cases_v2()
    ).hexdigest()


if __name__ == "__main__":
    print("Semantic Decision V2 Fresh Holdout Cases")
    print("Version:", SEMANTIC_DECISION_FRESH_CASES_VERSION_V2)
    print("Total:", len(SEMANTIC_DECISION_FRESH_CASES_V2))
    print("Fingerprint:", semantic_decision_fresh_cases_fingerprint_v2())
