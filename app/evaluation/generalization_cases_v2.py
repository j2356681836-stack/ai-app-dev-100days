from __future__ import annotations

import hashlib
import json

from app.evaluation.golden_case_v2_models import (
    ExpectedGovernanceDecision,
    ExpectedIntentDecision,
    ExpectedMetricDecision,
    ExpectedPlanDecision,
    GoldenCaseCategory,
    GoldenCaseSplit,
    GoldenCaseV2,
    GovernanceOutcome,
    MetricDecisionStatus,
    PlanDecisionStatus,
    RankingType,
    ResultGrain,
    SortDirection,
)


def _semantic_case(
    *,
    case_id: str,
    split: GoldenCaseSplit,
    category: GoldenCaseCategory,
    question: str,
    description: str,
    metric_name: str,
    result_grain: ResultGrain,
    plan_name: str,
    limit: int | None = None,
    ranking_type: RankingType | None = None,
    sort_direction: SortDirection | None = None,
) -> GoldenCaseV2:
    return GoldenCaseV2(
        case_id=case_id,
        split=split,
        category=category,
        question=question,
        description=description,
        expected_metric=ExpectedMetricDecision(
            status=MetricDecisionStatus.MATCHED,
            metric_name=metric_name,
        ),
        expected_intent=ExpectedIntentDecision(
            result_grain=result_grain,
            limit=limit,
            ranking_type=ranking_type,
            sort_direction=sort_direction,
        ),
        expected_plan=ExpectedPlanDecision(
            status=PlanDecisionStatus.SELECTED,
            plan_name=plan_name,
        ),
        expected_governance=ExpectedGovernanceDecision(
            outcome=GovernanceOutcome.NOT_EVALUATED,
        ),
    )


def _unsupported_metric_case(
    *,
    case_id: str,
    question: str,
    description: str,
) -> GoldenCaseV2:
    return GoldenCaseV2(
        case_id=case_id,
        split=GoldenCaseSplit.ADVERSARIAL,
        category=GoldenCaseCategory.UNSUPPORTED_SEMANTICS,
        question=question,
        description=description,
        expected_metric=ExpectedMetricDecision(
            status=MetricDecisionStatus.UNSUPPORTED,
        ),
        expected_intent=ExpectedIntentDecision(),
        expected_plan=ExpectedPlanDecision(
            status=PlanDecisionStatus.NOT_APPLICABLE,
        ),
        expected_governance=ExpectedGovernanceDecision(
            outcome=GovernanceOutcome.NOT_EVALUATED,
        ),
    )


def _clarification_case(
    *,
    case_id: str,
    question: str,
    description: str,
    candidates: tuple[str, ...],
) -> GoldenCaseV2:
    return GoldenCaseV2(
        case_id=case_id,
        split=GoldenCaseSplit.ADVERSARIAL,
        category=GoldenCaseCategory.AMBIGUITY,
        question=question,
        description=description,
        expected_metric=ExpectedMetricDecision(
            status=MetricDecisionStatus.NEEDS_CLARIFICATION,
            acceptable_candidates=candidates,
        ),
        expected_intent=ExpectedIntentDecision(),
        expected_plan=ExpectedPlanDecision(
            status=PlanDecisionStatus.NOT_APPLICABLE,
        ),
        expected_governance=ExpectedGovernanceDecision(
            outcome=GovernanceOutcome.NOT_EVALUATED,
        ),
    )


def _unsupported_shape_case(
    *,
    case_id: str,
    question: str,
    description: str,
    metric_name: str,
    result_grain: ResultGrain,
    ranking_type: RankingType | None = None,
    sort_direction: SortDirection | None = None,
) -> GoldenCaseV2:
    return GoldenCaseV2(
        case_id=case_id,
        split=GoldenCaseSplit.ADVERSARIAL,
        category=GoldenCaseCategory.UNSUPPORTED_SEMANTICS,
        question=question,
        description=description,
        expected_metric=ExpectedMetricDecision(
            status=MetricDecisionStatus.MATCHED,
            metric_name=metric_name,
        ),
        expected_intent=ExpectedIntentDecision(
            result_grain=result_grain,
            ranking_type=ranking_type,
            sort_direction=sort_direction,
        ),
        expected_plan=ExpectedPlanDecision(
            status=PlanDecisionStatus.UNSUPPORTED_SHAPE,
        ),
        expected_governance=ExpectedGovernanceDecision(
            outcome=GovernanceOutcome.NOT_EVALUATED,
        ),
    )


LOCKED_HOLDOUT_CASES_V2 = (
    _semantic_case(
        case_id="holdout_gmv_channel_001",
        split=GoldenCaseSplit.LOCKED_HOLDOUT,
        category=GoldenCaseCategory.PARAPHRASE,
        question="按平台比较实付成交金额，哪个最高？",
        description="GMV unseen paraphrase；平台表示 Channel Grain。",
        metric_name="gmv",
        result_grain=ResultGrain.CHANNEL,
        plan_name="gmv_channel_v2",
        limit=1,
        ranking_type=RankingType.TOP1,
        sort_direction=SortDirection.DESC,
    ),
    _semantic_case(
        case_id="holdout_gross_margin_overall_001",
        split=GoldenCaseSplit.LOCKED_HOLDOUT,
        category=GoldenCaseCategory.PARAPHRASE,
        question="今年商品销售收入减商品成本后还剩多少？",
        description="用公式语义表达商品毛利额。",
        metric_name="gross_margin",
        result_grain=ResultGrain.OVERALL,
        plan_name="gross_margin_overall_v2",
    ),
    _semantic_case(
        case_id="holdout_gross_margin_rate_category_001",
        split=GoldenCaseSplit.LOCKED_HOLDOUT,
        category=GoldenCaseCategory.PARAPHRASE,
        question="不同类目里，商品毛利占成交额的比例谁最高？",
        description="用比例定义表达 Gross Margin Rate。",
        metric_name="gross_margin_rate",
        result_grain=ResultGrain.CATEGORY,
        plan_name="gross_margin_rate_category_v2",
        limit=1,
        ranking_type=RankingType.TOP1,
        sort_direction=SortDirection.DESC,
    ),
    _semantic_case(
        case_id="holdout_refund_rate_overall_001",
        split=GoldenCaseSplit.LOCKED_HOLDOUT,
        category=GoldenCaseCategory.PARAPHRASE,
        question="今年完成退款金额占原支付成交金额的比例是多少？",
        description="显式表达 amount-based Refund Rate 公式。",
        metric_name="refund_rate",
        result_grain=ResultGrain.OVERALL,
        plan_name="refund_rate_overall_v2",
    ),
    _semantic_case(
        case_id="holdout_roi_channel_001",
        split=GoldenCaseSplit.LOCKED_HOLDOUT,
        category=GoldenCaseCategory.PARAPHRASE,
        question="按渠道看，每1元投放费用带来的成交金额回报怎么排？",
        description="用投入产出含义表达 ROI。",
        metric_name="roi",
        result_grain=ResultGrain.CHANNEL,
        plan_name="roi_channel_v2",
        ranking_type=RankingType.RANKING,
        sort_direction=SortDirection.DESC,
    ),
    _semantic_case(
        case_id="holdout_cac_channel_001",
        split=GoldenCaseSplit.LOCKED_HOLDOUT,
        category=GoldenCaseCategory.PARAPHRASE,
        question="不同平台平均花多少投放费才能获得一个该平台首次付款客户？",
        description="用 Spend / Channel New Customer 公式表达 CAC。",
        metric_name="cac",
        result_grain=ResultGrain.CHANNEL,
        plan_name="cac_channel_v2",
    ),
    _semantic_case(
        case_id="holdout_brand_new_overall_001",
        split=GoldenCaseSplit.LOCKED_HOLDOUT,
        category=GoldenCaseCategory.PARAPHRASE,
        question="今年第一次在整个品牌成功付款的去重客户有多少？",
        description="Brand-first paid identity = customer。",
        metric_name="brand_paid_new_customer_count",
        result_grain=ResultGrain.OVERALL,
        plan_name="brand_paid_new_customer_count_overall_v2",
    ),
    _semantic_case(
        case_id="holdout_channel_new_channel_001",
        split=GoldenCaseSplit.LOCKED_HOLDOUT,
        category=GoldenCaseCategory.PARAPHRASE,
        question="按渠道统计，每个客户第一次在该渠道付款的人数",
        description="Channel-first paid identity = customer × channel。",
        metric_name="channel_paid_new_customer_count",
        result_grain=ResultGrain.CHANNEL,
        plan_name="channel_paid_new_customer_count_channel_v2",
    ),
    _semantic_case(
        case_id="holdout_repeat_rate_overall_001",
        split=GoldenCaseSplit.LOCKED_HOLDOUT,
        category=GoldenCaseCategory.PARAPHRASE,
        question="今年在至少两个不同付款日期购买的客户，占全部购买客户多少？",
        description="用 numerator / buyer denominator 表达跨日复购率。",
        metric_name="repeat_customer_rate",
        result_grain=ResultGrain.OVERALL,
        plan_name="repeat_customer_rate_overall_v2",
    ),
    _semantic_case(
        case_id="holdout_member_share_overall_001",
        split=GoldenCaseSplit.LOCKED_HOLDOUT,
        category=GoldenCaseCategory.PARAPHRASE,
        question="下单支付那一刻具有会员等级的成交额，占全部成交额多少？",
        description="Payment-time membership snapshot，而非 current membership。",
        metric_name="member_gmv_share",
        result_grain=ResultGrain.OVERALL,
        plan_name="member_gmv_share_overall_v2",
    ),
    _semantic_case(
        case_id="holdout_buyer_count_region_001",
        split=GoldenCaseSplit.LOCKED_HOLDOUT,
        category=GoldenCaseCategory.PARAPHRASE,
        question="各区域分别有多少去重成功付款客户？",
        description="Distinct paid customers by Region。",
        metric_name="buyer_count",
        result_grain=ResultGrain.REGION,
        plan_name="buyer_count_region_v2",
    ),
    _semantic_case(
        case_id="holdout_order_count_channel_001",
        split=GoldenCaseSplit.LOCKED_HOLDOUT,
        category=GoldenCaseCategory.PARAPHRASE,
        question="各平台成功支付的订单笔数怎么排？",
        description="Paid transaction count by Channel。",
        metric_name="order_count",
        result_grain=ResultGrain.CHANNEL,
        plan_name="order_count_channel_v2",
        ranking_type=RankingType.RANKING,
        sort_direction=SortDirection.DESC,
    ),
    _semantic_case(
        case_id="holdout_units_category_001",
        split=GoldenCaseSplit.LOCKED_HOLDOUT,
        category=GoldenCaseCategory.PARAPHRASE,
        question="不同类目实际成交的商品总件数哪个最多？",
        description="Sum(quantity) by Category。",
        metric_name="units_sold",
        result_grain=ResultGrain.CATEGORY,
        plan_name="units_sold_category_v2",
        limit=1,
        ranking_type=RankingType.TOP1,
        sort_direction=SortDirection.DESC,
    ),
    _semantic_case(
        case_id="holdout_spending_channel_001",
        split=GoldenCaseSplit.LOCKED_HOLDOUT,
        category=GoldenCaseCategory.PARAPHRASE,
        question="按渠道看，每位去重付款客户平均贡献多少成交额？",
        description="GMV / buyer_count by Channel。",
        metric_name="spending_per_buyer",
        result_grain=ResultGrain.CHANNEL,
        plan_name="spending_per_buyer_channel_v2",
    ),
    _semantic_case(
        case_id="holdout_ipt_category_001",
        split=GoldenCaseSplit.LOCKED_HOLDOUT,
        category=GoldenCaseCategory.PARAPHRASE,
        question="不同类目每张成功支付订单平均包含多少件商品？",
        description="units_sold / order_count by Category。",
        metric_name="ipt",
        result_grain=ResultGrain.CATEGORY,
        plan_name="ipt_category_v2",
    ),
    _semantic_case(
        case_id="holdout_aus_region_001",
        split=GoldenCaseSplit.LOCKED_HOLDOUT,
        category=GoldenCaseCategory.PARAPHRASE,
        question="按区域看，每笔成功支付订单平均成交金额是多少？",
        description="GMV / order_count by Region。",
        metric_name="aus",
        result_grain=ResultGrain.REGION,
        plan_name="aus_region_v2",
    ),
    _semantic_case(
        case_id="holdout_frequency_region_001",
        split=GoldenCaseSplit.LOCKED_HOLDOUT,
        category=GoldenCaseCategory.PARAPHRASE,
        question="各区域每个去重购买客户平均下了多少张支付订单？",
        description="order_count / buyer_count by Region。",
        metric_name="purchase_frequency",
        result_grain=ResultGrain.REGION,
        plan_name="purchase_frequency_region_v2",
    ),
    _semantic_case(
        case_id="holdout_repeat_count_overall_001",
        split=GoldenCaseSplit.LOCKED_HOLDOUT,
        category=GoldenCaseCategory.PARAPHRASE,
        question="今年有多少客户在至少两个不同的付款日期出现过？",
        description="Distinct purchase-date repeat customer count。",
        metric_name="repeat_customer_count",
        result_grain=ResultGrain.OVERALL,
        plan_name="repeat_customer_count_overall_v2",
    ),
    _semantic_case(
        case_id="holdout_multi_order_overall_001",
        split=GoldenCaseSplit.LOCKED_HOLDOUT,
        category=GoldenCaseCategory.PARAPHRASE,
        question="今年有多少客户至少完成了两笔成功支付订单？",
        description="Two-or-more paid orders, including same-day multiple orders。",
        metric_name="multi_order_customer_count",
        result_grain=ResultGrain.OVERALL,
        plan_name="multi_order_customer_count_overall_v2",
    ),
)


SEMANTIC_ADVERSARIAL_CASES_V2 = (
    _clarification_case(
        case_id="adv_new_customer_wording_001",
        question="今年新增客户一共有多少？",
        description="新增客户未声明 Brand-first 或 Channel-first。",
        candidates=(
            "brand_paid_new_customer_count",
            "channel_paid_new_customer_count",
        ),
    ),
    _clarification_case(
        case_id="adv_repeat_people_ambiguity_001",
        question="今年复购人数有多少？",
        description="未声明跨购买日口径还是两单口径。",
        candidates=(
            "repeat_customer_count",
            "multi_order_customer_count",
        ),
    ),
    _unsupported_metric_case(
        case_id="adv_net_sales_001",
        question="今年退款后的净销售额是多少？",
        description="GMV 不做退款回调，当前 Contract 没有 Net Sales Metric。",
    ),
    _unsupported_metric_case(
        case_id="adv_unit_price_001",
        question="平均每件商品卖多少钱？",
        description="AUS 是 GMV / order_count，不是 unit selling price。",
    ),
    _unsupported_metric_case(
        case_id="adv_refund_count_rate_001",
        question="退款订单数占支付订单数的比例是多少？",
        description="当前 refund_rate 是 amount-based，不是 count-based。",
    ),
    _unsupported_metric_case(
        case_id="adv_cohort_repeat_001",
        question="双11新客30天复购率是多少？",
        description="Cohort post-first-purchase repeat rate 不属于当前 period repeat metric。",
    ),
    _unsupported_metric_case(
        case_id="adv_current_membership_001",
        question="按当前会员身份计算会员GMV占比",
        description="当前会员身份不同于 payment-time member snapshot。",
    ),
    _unsupported_metric_case(
        case_id="adv_ltv_001",
        question="今年客户生命周期价值是多少？",
        description="当前 19 Metrics 不包含 Customer Lifetime Value。",
    ),
    _unsupported_metric_case(
        case_id="adv_net_margin_rate_001",
        question="今年净利润率是多少？",
        description="Gross Margin Rate 不等于 Net Profit Margin。",
    ),
    _unsupported_shape_case(
        case_id="adv_refund_region_shape_001",
        question="各区域销售退款率怎么排？",
        description="refund_rate 当前只有 overall Plan。",
        metric_name="refund_rate",
        result_grain=ResultGrain.REGION,
        ranking_type=RankingType.RANKING,
        sort_direction=SortDirection.DESC,
    ),
    _unsupported_shape_case(
        case_id="adv_cac_region_shape_001",
        question="分区域看拉新成本",
        description="CAC 当前只有 Channel Result Grain。",
        metric_name="cac",
        result_grain=ResultGrain.REGION,
    ),
    _unsupported_shape_case(
        case_id="adv_aus_category_shape_001",
        question="各品类平均每笔交易金额怎么排？",
        description="AUS 当前不支持 Category Result Grain。",
        metric_name="aus",
        result_grain=ResultGrain.CATEGORY,
        ranking_type=RankingType.RANKING,
        sort_direction=SortDirection.DESC,
    ),
    _unsupported_shape_case(
        case_id="adv_brand_new_channel_shape_001",
        question="按渠道拆分品牌首次购买客户数",
        description="Brand New 当前 Catalog 只有 overall Plan。",
        metric_name="brand_paid_new_customer_count",
        result_grain=ResultGrain.CHANNEL,
    ),
    _unsupported_shape_case(
        case_id="adv_channel_new_region_shape_001",
        question="各地区渠道支付新客数",
        description="Channel New 当前 Catalog 只有 channel Plan；这里请求 Region Grain。",
        metric_name="channel_paid_new_customer_count",
        result_grain=ResultGrain.REGION,
    ),
)


def _canonical_case_payload(
    cases: tuple[GoldenCaseV2, ...],
) -> bytes:
    payload = [
        case.model_dump(mode="json")
        for case in cases
    ]

    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def compute_locked_holdout_fingerprint() -> str:
    return hashlib.sha256(
        _canonical_case_payload(
            LOCKED_HOLDOUT_CASES_V2
        )
    ).hexdigest()


LOCKED_HOLDOUT_FINGERPRINT = "2c2a9f6c2f55e4f2788b6ef847917f30c98a54dc8fc729e09ec33f466f75c332"
