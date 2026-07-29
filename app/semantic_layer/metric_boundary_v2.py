from __future__ import annotations

import re
from enum import Enum

from pydantic import BaseModel, ConfigDict, model_validator


class BoundaryOutcome(str, Enum):
    CONTINUE = "continue"
    NEEDS_CLARIFICATION = "needs_clarification"
    UNSUPPORTED = "unsupported"


class MetricBoundaryDecisionV2(BaseModel):
    """
    Metric Semantic Retrieval 之前的业务合同边界。

    continue:
        当前硬合同没有阻止后续 Rule / Embedding Retrieval。

    needs_clarification:
        问题本身缺少足以区分多个合法 Metric 的信息。

    unsupported:
        问题明确要求当前 19-Metric Contract 之外的语义。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    outcome: BoundaryOutcome
    reason_code: str | None = None
    candidates: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_decision(
        self,
    ) -> "MetricBoundaryDecisionV2":
        if self.outcome == BoundaryOutcome.CONTINUE:
            if self.reason_code is not None:
                raise ValueError(
                    "continue boundary decision must not carry reason_code."
                )
            if self.candidates:
                raise ValueError(
                    "continue boundary decision must not carry candidates."
                )
            return self

        if not self.reason_code:
            raise ValueError(
                f"{self.outcome.value} boundary decision requires reason_code."
            )

        if self.outcome == BoundaryOutcome.NEEDS_CLARIFICATION:
            if len(self.candidates) < 2:
                raise ValueError(
                    "needs_clarification requires at least two candidates."
                )
            if len(self.candidates) != len(set(self.candidates)):
                raise ValueError(
                    "clarification candidates must be unique."
                )
            return self

        if self.candidates:
            raise ValueError(
                "unsupported boundary decision must not carry candidates."
            )

        return self


def _normalize(text: str) -> str:
    return "".join(
        text.casefold().split()
    )


def _contains_any(
    text: str,
    phrases: tuple[str, ...],
) -> bool:
    return any(
        phrase in text
        for phrase in phrases
    )


def evaluate_metric_boundary_v2(
    question: str,
) -> MetricBoundaryDecisionV2:
    """
    Evaluates only explicit business-contract boundaries.

    设计原则：
    - 硬边界优先于 Embedding confidence；
    - 不尝试从 19 Metrics 中“猜最像谁”；
    - 不承担 Result Grain / Query Plan / Governance 职责。
    """
    q = _normalize(question)

    # --------------------------------------------------------
    # Unsupported semantic contracts
    # --------------------------------------------------------

    # Net Sales: current GMV deliberately does not refund-back-adjust.
    if (
        "净销售额" in q
        or "净成交额" in q
        or re.search(
            r"(退款后|扣除退款|减去退款).*(销售额|成交额|gmv)",
            q,
        )
    ):
        return MetricBoundaryDecisionV2(
            outcome=BoundaryOutcome.UNSUPPORTED,
            reason_code="unsupported_net_sales",
        )

    # Count-based refund rate is not the amount-based refund_rate contract.
    count_refund_signals = (
        "退款订单数",
        "退款订单量",
        "退款单数",
        "退款笔数",
        "退款申请数量",
        "退款申请数",
    )

    if (
        _contains_any(
            q,
            count_refund_signals,
        )
        and _contains_any(
            q,
            (
                "占",
                "比例",
                "比率",
                "率",
            ),
        )
    ):
        return MetricBoundaryDecisionV2(
            outcome=BoundaryOutcome.UNSUPPORTED,
            reason_code="unsupported_count_based_refund_rate",
        )

    # Current membership basis is different from payment-time membership snapshot.
    if (
        _contains_any(
            q,
            (
                "当前会员",
                "现有会员",
                "现在会员",
                "当前会员身份",
                "当前会员等级",
            ),
        )
        and _contains_any(
            q,
            (
                "gmv",
                "成交额",
                "销售额",
                "贡献",
                "占比",
                "比例",
            ),
        )
    ):
        return MetricBoundaryDecisionV2(
            outcome=BoundaryOutcome.UNSUPPORTED,
            reason_code="unsupported_current_membership_basis",
        )

    # Cohort / post-first-purchase repeat rate is not period repeat_customer_rate.
    cohort_window = re.search(
        r"(?<!\d)(\d{1,3})(天|日|周|个月|月)",
        q,
    )

    if (
        "复购" in q
        and (
            cohort_window is not None
            or _contains_any(
                q,
                (
                    "首购后",
                    "首单后",
                    "首次购买后",
                    "新客复购",
                    "cohort",
                    "留存",
                ),
            )
        )
    ):
        return MetricBoundaryDecisionV2(
            outcome=BoundaryOutcome.UNSUPPORTED,
            reason_code="unsupported_cohort_repeat_rate",
        )

    # Net profit margin is not gross margin rate.
    if _contains_any(
        q,
        (
            "净利润率",
            "净利率",
            "净利润占比",
        ),
    ):
        return MetricBoundaryDecisionV2(
            outcome=BoundaryOutcome.UNSUPPORTED,
            reason_code="unsupported_net_profit_margin",
        )

    # Unit selling price is not AUS in current V2.
    if (
        _contains_any(
            q,
            (
                "每件商品",
                "每件",
                "单件商品",
                "单件",
            ),
        )
        and _contains_any(
            q,
            (
                "多少钱",
                "成交金额",
                "销售金额",
                "售价",
                "价格",
                "卖多少",
                "卖多少钱",
            ),
        )
    ):
        return MetricBoundaryDecisionV2(
            outcome=BoundaryOutcome.UNSUPPORTED,
            reason_code="unsupported_unit_selling_price",
        )

    # LTV / customer lifetime value is outside current 19 metrics.
    if _contains_any(
        q,
        (
            "客户生命周期价值",
            "用户生命周期价值",
            "customerlifetimevalue",
            "ltv",
        ),
    ):
        return MetricBoundaryDecisionV2(
            outcome=BoundaryOutcome.UNSUPPORTED,
            reason_code="unsupported_customer_lifetime_value",
        )

    # --------------------------------------------------------
    # Explicit ambiguity contracts
    # --------------------------------------------------------

    # Generic new customer wording must not silently choose brand vs channel.
    generic_new_customer = _contains_any(
        q,
        (
            "新客",
            "新增客户",
            "新增顾客",
            "新增用户",
        ),
    )

    brand_specific = _contains_any(
        q,
        (
            "品牌新客",
            "品牌支付新客",
            "品牌首次",
            "整个品牌",
            "全品牌",
            "品牌首购",
        ),
    )

    channel_specific = _contains_any(
        q,
        (
            "渠道新客",
            "渠道支付新客",
            "各渠道新客",
            "按渠道新客",
            "分渠道新客",
            "该渠道首次",
            "渠道首次",
        ),
    )

    if (
        generic_new_customer
        and not brand_specific
        and not channel_specific
    ):
        return MetricBoundaryDecisionV2(
            outcome=BoundaryOutcome.NEEDS_CLARIFICATION,
            reason_code="ambiguous_new_customer_basis",
            candidates=(
                "brand_paid_new_customer_count",
                "channel_paid_new_customer_count",
            ),
        )

    # “复购人数” without date-vs-order-count basis is ambiguous.
    generic_repeat_people = _contains_any(
        q,
        (
            "复购人数",
            "复购客户数",
            "复购客户",
        ),
    )

    cross_day_specific = _contains_any(
        q,
        (
            "跨日",
            "不同日期",
            "不同付款日期",
            "不同支付日期",
            "不同购买日",
            "跨购买日",
        ),
    )

    multi_order_specific = _contains_any(
        q,
        (
            "两单及以上",
            "两单以上",
            "2单及以上",
            "2单以上",
            "多单客户",
            "多订单",
            "至少两单",
            "至少2单",
        ),
    )

    if (
        generic_repeat_people
        and not cross_day_specific
        and not multi_order_specific
    ):
        return MetricBoundaryDecisionV2(
            outcome=BoundaryOutcome.NEEDS_CLARIFICATION,
            reason_code="ambiguous_repeat_customer_basis",
            candidates=(
                "repeat_customer_count",
                "multi_order_customer_count",
            ),
        )

    return MetricBoundaryDecisionV2(
        outcome=BoundaryOutcome.CONTINUE,
    )


if __name__ == "__main__":
    questions = (
        "今年新增客户一共有多少？",
        "今年复购人数有多少？",
        "今年退款后的净销售额是多少？",
        "退款订单数占支付订单数的比例是多少？",
        "按当前会员身份计算会员GMV占比",
        "双11新客30天复购率是多少？",
        "今年净利润率是多少？",
        "平均每件商品卖多少钱？",
        "今年客户生命周期价值是多少？",
        "2025年品牌新客有多少？",
        "各渠道支付新客数",
        "今年跨日复购客户数",
    )

    for question in questions:
        print("=" * 80)
        print(question)
        print(
            evaluate_metric_boundary_v2(
                question
            ).model_dump(
                mode="json"
            )
        )
