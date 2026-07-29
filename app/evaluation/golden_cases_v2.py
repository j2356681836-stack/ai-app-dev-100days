from app.evaluation.golden_case_v2_models import (
    ExpectedGovernanceDecision,
    ExpectedIntentDecision,
    ExpectedMetricDecision,
    ExpectedPlanDecision,
    GoldenCaseCatalogV2,
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
    """
    构建 Metric → Grain → Query Plan 已明确的语义 Case。

    Gate 3 不对这些普通 Case 强制执行 Governance。
    Governance 会在后续专门的 Adversarial / Governance Cases
    中绑定明确 AccessContext 后验证。
    """
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


def _unsupported_shape_case(
    *,
    case_id: str,
    question: str,
    description: str,
    metric_name: str,
    result_grain: ResultGrain,
    limit: int | None = None,
    ranking_type: RankingType | None = None,
    sort_direction: SortDirection | None = None,
) -> GoldenCaseV2:
    """
    Metric 识别正确，但当前 48-plan Catalog 不支持该结果 Grain。
    """
    return GoldenCaseV2(
        case_id=case_id,
        split=GoldenCaseSplit.REGRESSION,
        category=GoldenCaseCategory.UNSUPPORTED_SEMANTICS,
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
            status=PlanDecisionStatus.UNSUPPORTED_SHAPE,
        ),
        expected_governance=ExpectedGovernanceDecision(
            outcome=GovernanceOutcome.NOT_EVALUATED,
        ),
    )


def _new_customer_ambiguity_case() -> GoldenCaseV2:
    """
    “新客”在 V2 中不能静默等价为品牌新客或渠道新客。
    """
    return GoldenCaseV2(
        case_id="reg_new_customer_ambiguity_001",
        split=GoldenCaseSplit.REGRESSION,
        category=GoldenCaseCategory.AMBIGUITY,
        question="今年新客多少？",
        description=(
            "未说明品牌口径还是渠道口径，必须在 "
            "brand_paid_new_customer_count 与 "
            "channel_paid_new_customer_count 之间澄清。"
        ),
        expected_metric=ExpectedMetricDecision(
            status=MetricDecisionStatus.NEEDS_CLARIFICATION,
            acceptable_candidates=(
                "brand_paid_new_customer_count",
                "channel_paid_new_customer_count",
            ),
        ),
        expected_intent=ExpectedIntentDecision(
            result_grain=None,
        ),
        expected_plan=ExpectedPlanDecision(
            status=PlanDecisionStatus.NOT_APPLICABLE,
        ),
        expected_governance=ExpectedGovernanceDecision(
            outcome=GovernanceOutcome.NOT_EVALUATED,
        ),
    )


DEVELOPMENT_CASES_V2 = (
    _semantic_case(
        case_id="dev_gmv_channel_001",
        split=GoldenCaseSplit.DEVELOPMENT,
        category=GoldenCaseCategory.GRAIN_SELECTION,
        question="各渠道GMV排名",
        description="GMV + Channel Grain + 排名。",
        metric_name="gmv",
        result_grain=ResultGrain.CHANNEL,
        plan_name="gmv_channel_v2",
        ranking_type=RankingType.RANKING,
        sort_direction=SortDirection.DESC,
    ),
    _semantic_case(
        case_id="dev_gross_margin_overall_001",
        split=GoldenCaseSplit.DEVELOPMENT,
        category=GoldenCaseCategory.CANONICAL,
        question="2025年毛利额是多少？",
        description="整体商品毛利额。",
        metric_name="gross_margin",
        result_grain=ResultGrain.OVERALL,
        plan_name="gross_margin_overall_v2",
    ),
    _semantic_case(
        case_id="dev_gross_margin_rate_category_001",
        split=GoldenCaseSplit.DEVELOPMENT,
        category=GoldenCaseCategory.GRAIN_SELECTION,
        question="哪个品类毛利率最高？",
        description="毛利率 + Category Grain + Top1。",
        metric_name="gross_margin_rate",
        result_grain=ResultGrain.CATEGORY,
        plan_name="gross_margin_rate_category_v2",
        limit=1,
        ranking_type=RankingType.TOP1,
        sort_direction=SortDirection.DESC,
    ),
    _semantic_case(
        case_id="dev_refund_rate_overall_001",
        split=GoldenCaseSplit.DEVELOPMENT,
        category=GoldenCaseCategory.CANONICAL,
        question="2025年退款率是多少？",
        description="当前 V2 Refund Rate 正式 Plan 为 overall。",
        metric_name="refund_rate",
        result_grain=ResultGrain.OVERALL,
        plan_name="refund_rate_overall_v2",
    ),
    _semantic_case(
        case_id="dev_roi_channel_001",
        split=GoldenCaseSplit.DEVELOPMENT,
        category=GoldenCaseCategory.PARAPHRASE,
        question="各渠道投产比排名",
        description="“投产比”应识别为 ROI，并选择 Channel Plan。",
        metric_name="roi",
        result_grain=ResultGrain.CHANNEL,
        plan_name="roi_channel_v2",
        ranking_type=RankingType.RANKING,
        sort_direction=SortDirection.DESC,
    ),
    _semantic_case(
        case_id="dev_cac_channel_001",
        split=GoldenCaseSplit.DEVELOPMENT,
        category=GoldenCaseCategory.CANONICAL,
        question="哪个渠道获客成本最低？",
        description="CAC + Channel Grain + 最低 Top1。",
        metric_name="cac",
        result_grain=ResultGrain.CHANNEL,
        plan_name="cac_channel_v2",
        limit=1,
        ranking_type=RankingType.TOP1,
        sort_direction=SortDirection.ASC,
    ),
    _semantic_case(
        case_id="dev_brand_new_customer_overall_001",
        split=GoldenCaseSplit.DEVELOPMENT,
        category=GoldenCaseCategory.CANONICAL,
        question="2025年品牌首次购买客户数是多少？",
        description="品牌首购 identity = customer。",
        metric_name="brand_paid_new_customer_count",
        result_grain=ResultGrain.OVERALL,
        plan_name="brand_paid_new_customer_count_overall_v2",
    ),
    _semantic_case(
        case_id="dev_channel_new_customer_channel_001",
        split=GoldenCaseSplit.DEVELOPMENT,
        category=GoldenCaseCategory.GRAIN_SELECTION,
        question="2025年各渠道支付新客有多少？",
        description="渠道新客 identity = customer × channel。",
        metric_name="channel_paid_new_customer_count",
        result_grain=ResultGrain.CHANNEL,
        plan_name="channel_paid_new_customer_count_channel_v2",
    ),
    _semantic_case(
        case_id="dev_repeat_rate_overall_001",
        split=GoldenCaseSplit.DEVELOPMENT,
        category=GoldenCaseCategory.CANONICAL,
        question="2025年整体复购率是多少？",
        description="复购率采用跨不同支付日期口径。",
        metric_name="repeat_customer_rate",
        result_grain=ResultGrain.OVERALL,
        plan_name="repeat_customer_rate_overall_v2",
    ),
    _semantic_case(
        case_id="dev_member_gmv_share_overall_001",
        split=GoldenCaseSplit.DEVELOPMENT,
        category=GoldenCaseCategory.PARAPHRASE,
        question="今年会员GMV占比是多少？",
        description="会员 GMV 贡献使用支付时点会员快照。",
        metric_name="member_gmv_share",
        result_grain=ResultGrain.OVERALL,
        plan_name="member_gmv_share_overall_v2",
    ),
    _semantic_case(
        case_id="dev_buyer_count_region_001",
        split=GoldenCaseSplit.DEVELOPMENT,
        category=GoldenCaseCategory.GRAIN_SELECTION,
        question="各地区购买客户数",
        description="购买人数 + Region Grain。",
        metric_name="buyer_count",
        result_grain=ResultGrain.REGION,
        plan_name="buyer_count_region_v2",
    ),
    _semantic_case(
        case_id="dev_order_count_channel_001",
        split=GoldenCaseSplit.DEVELOPMENT,
        category=GoldenCaseCategory.GRAIN_SELECTION,
        question="各渠道订单量排名",
        description="支付订单量 + Channel Grain。",
        metric_name="order_count",
        result_grain=ResultGrain.CHANNEL,
        plan_name="order_count_channel_v2",
        ranking_type=RankingType.RANKING,
        sort_direction=SortDirection.DESC,
    ),
    _semantic_case(
        case_id="dev_units_sold_category_001",
        split=GoldenCaseSplit.DEVELOPMENT,
        category=GoldenCaseCategory.PARAPHRASE,
        question="哪个品类销量最高？",
        description="“销量”对应交易件数，不是订单量。",
        metric_name="units_sold",
        result_grain=ResultGrain.CATEGORY,
        plan_name="units_sold_category_v2",
        limit=1,
        ranking_type=RankingType.TOP1,
        sort_direction=SortDirection.DESC,
    ),
    _semantic_case(
        case_id="dev_spending_overall_001",
        split=GoldenCaseSplit.DEVELOPMENT,
        category=GoldenCaseCategory.CANONICAL,
        question="今年人均消费金额是多少？",
        description="Spending = GMV / buyer_count。",
        metric_name="spending_per_buyer",
        result_grain=ResultGrain.OVERALL,
        plan_name="spending_per_buyer_overall_v2",
    ),
    _semantic_case(
        case_id="dev_ipt_channel_001",
        split=GoldenCaseSplit.DEVELOPMENT,
        category=GoldenCaseCategory.GRAIN_SELECTION,
        question="各渠道每单件数",
        description="IPT = units_sold / order_count。",
        metric_name="ipt",
        result_grain=ResultGrain.CHANNEL,
        plan_name="ipt_channel_v2",
    ),
    _semantic_case(
        case_id="dev_aus_region_001",
        split=GoldenCaseSplit.DEVELOPMENT,
        category=GoldenCaseCategory.GRAIN_SELECTION,
        question="各地区AUS是多少？",
        description="AUS 当前支持 Region Grain，但不支持 Category Grain。",
        metric_name="aus",
        result_grain=ResultGrain.REGION,
        plan_name="aus_region_v2",
    ),
    _semantic_case(
        case_id="dev_purchase_frequency_category_001",
        split=GoldenCaseSplit.DEVELOPMENT,
        category=GoldenCaseCategory.GRAIN_SELECTION,
        question="各品类平均购买次数",
        description="FREQ = order_count / buyer_count。",
        metric_name="purchase_frequency",
        result_grain=ResultGrain.CATEGORY,
        plan_name="purchase_frequency_category_v2",
    ),
    _semantic_case(
        case_id="dev_repeat_customer_count_overall_001",
        split=GoldenCaseSplit.DEVELOPMENT,
        category=GoldenCaseCategory.CANONICAL,
        question="今年跨日复购客户数是多少？",
        description="至少两个不同支付日期的 customer。",
        metric_name="repeat_customer_count",
        result_grain=ResultGrain.OVERALL,
        plan_name="repeat_customer_count_overall_v2",
    ),
    _semantic_case(
        case_id="dev_multi_order_customer_count_overall_001",
        split=GoldenCaseSplit.DEVELOPMENT,
        category=GoldenCaseCategory.CANONICAL,
        question="今年多单客户有多少？",
        description="至少两张成功支付订单，同日多单仍分别计数。",
        metric_name="multi_order_customer_count",
        result_grain=ResultGrain.OVERALL,
        plan_name="multi_order_customer_count_overall_v2",
    ),
)


REGRESSION_CASES_V2 = (
    _new_customer_ambiguity_case(),
    _semantic_case(
        case_id="reg_aus_vs_spending_001",
        split=GoldenCaseSplit.REGRESSION,
        category=GoldenCaseCategory.PARAPHRASE,
        question="平均每单多少钱？",
        description="每单金额应归 AUS，不是人均消费。",
        metric_name="aus",
        result_grain=ResultGrain.OVERALL,
        plan_name="aus_overall_v2",
    ),
    _semantic_case(
        case_id="reg_spending_vs_aus_001",
        split=GoldenCaseSplit.REGRESSION,
        category=GoldenCaseCategory.PARAPHRASE,
        question="人均消费是多少？",
        description="人均消费应归 Spending，不是 AUS。",
        metric_name="spending_per_buyer",
        result_grain=ResultGrain.OVERALL,
        plan_name="spending_per_buyer_overall_v2",
    ),
    _semantic_case(
        case_id="reg_ipt_vs_units_001",
        split=GoldenCaseSplit.REGRESSION,
        category=GoldenCaseCategory.PARAPHRASE,
        question="平均每单买几件？",
        description="平均每单件数应归 IPT，不是总交易件数。",
        metric_name="ipt",
        result_grain=ResultGrain.OVERALL,
        plan_name="ipt_overall_v2",
    ),
    _semantic_case(
        case_id="reg_frequency_vs_repeat_001",
        split=GoldenCaseSplit.REGRESSION,
        category=GoldenCaseCategory.PARAPHRASE,
        question="今年平均购买次数是多少？",
        description="平均购买次数应归 FREQ，不是跨日复购率。",
        metric_name="purchase_frequency",
        result_grain=ResultGrain.OVERALL,
        plan_name="purchase_frequency_overall_v2",
    ),
    _semantic_case(
        case_id="reg_repeat_vs_multi_order_001",
        split=GoldenCaseSplit.REGRESSION,
        category=GoldenCaseCategory.PARAPHRASE,
        question="至少在两个不同日期购买过的客户有多少？",
        description="明确跨购买日，应归 repeat_customer_count。",
        metric_name="repeat_customer_count",
        result_grain=ResultGrain.OVERALL,
        plan_name="repeat_customer_count_overall_v2",
    ),
    _semantic_case(
        case_id="reg_multi_order_vs_repeat_001",
        split=GoldenCaseSplit.REGRESSION,
        category=GoldenCaseCategory.PARAPHRASE,
        question="下过两单及以上的客户有多少？",
        description="明确两张订单，应归 multi_order_customer_count。",
        metric_name="multi_order_customer_count",
        result_grain=ResultGrain.OVERALL,
        plan_name="multi_order_customer_count_overall_v2",
    ),
    _unsupported_shape_case(
        case_id="reg_roi_region_shape_001",
        question="各地区ROI排名",
        description="ROI Metric 正确，但当前 Catalog 只有 channel Grain。",
        metric_name="roi",
        result_grain=ResultGrain.REGION,
        ranking_type=RankingType.RANKING,
    ),
    _unsupported_shape_case(
        case_id="reg_cac_region_shape_001",
        question="各地区获客成本排名",
        description="CAC Metric 正确，但当前 Catalog 只有 channel Grain。",
        metric_name="cac",
        result_grain=ResultGrain.REGION,
        ranking_type=RankingType.RANKING,
    ),
    _unsupported_shape_case(
        case_id="reg_aus_category_shape_001",
        question="各品类AUS排名",
        description="AUS 当前只支持 overall / channel / region。",
        metric_name="aus",
        result_grain=ResultGrain.CATEGORY,
        ranking_type=RankingType.RANKING,
    ),
    _unsupported_shape_case(
        case_id="reg_refund_rate_category_shape_001",
        question="哪个品类退款率最高？",
        description=(
            "问题仍然属于 refund_rate Metric，"
            "但当前 48-plan Catalog 只提供 overall Refund Rate。"
        ),
        metric_name="refund_rate",
        result_grain=ResultGrain.CATEGORY,
        limit=1,
        ranking_type=RankingType.TOP1,
        sort_direction=SortDirection.DESC,
    ),
)


GOLDEN_CASES_V2 = GoldenCaseCatalogV2(
    version="golden_case_v2_0",
    dataset_name="beauty_bi_v2",
    cases=(
        *DEVELOPMENT_CASES_V2,
        *REGRESSION_CASES_V2,
    ),
)
