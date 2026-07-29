from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class SemanticFallbackPositiveCaseV2(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str
    metric_name: str
    question: str
    rationale: str


SEMANTIC_FALLBACK_POSITIVE_CASES_V2 = (
    SemanticFallbackPositiveCaseV2(
        case_id="fallback_gmv_001",
        metric_name="gmv",
        question="把分析期内所有已付款商品行的实收金额加在一起是多少？",
        rationale="paid item amount aggregation。",
    ),
    SemanticFallbackPositiveCaseV2(
        case_id="fallback_gmv_002",
        metric_name="gmv",
        question="成功付款商品明细贡献的金额总和有多少？",
        rationale="总额语义但不复制 aliases。",
    ),
    SemanticFallbackPositiveCaseV2(
        case_id="fallback_gmv_003",
        metric_name="gmv",
        question="把每个已支付商品明细的付款金额求和",
        rationale="事实粒度 + SUM。",
    ),

    SemanticFallbackPositiveCaseV2(
        case_id="fallback_gross_margin_001",
        metric_name="gross_margin",
        question="商品实收金额扣掉对应商品成本后合计还剩多少？",
        rationale="paid amount - cost。",
    ),
    SemanticFallbackPositiveCaseV2(
        case_id="fallback_gross_margin_002",
        metric_name="gross_margin",
        question="所有已付款商品的收入减去进货成本后的总金额",
        rationale="公式 paraphrase。",
    ),
    SemanticFallbackPositiveCaseV2(
        case_id="fallback_gross_margin_003",
        metric_name="gross_margin",
        question="支付商品产生的金额与商品成本之间的差额总计",
        rationale="金额差额语义。",
    ),

    SemanticFallbackPositiveCaseV2(
        case_id="fallback_gross_margin_rate_001",
        metric_name="gross_margin_rate",
        question="商品收入减成本后的金额，占商品实收金额的比例是多少？",
        rationale="gross margin / GMV。",
    ),
    SemanticFallbackPositiveCaseV2(
        case_id="fallback_gross_margin_rate_002",
        metric_name="gross_margin_rate",
        question="每一百元商品实收金额里扣除成本后剩余金额的占比",
        rationale="比例语义。",
    ),
    SemanticFallbackPositiveCaseV2(
        case_id="fallback_gross_margin_rate_003",
        metric_name="gross_margin_rate",
        question="商品付款金额扣成本后的部分相对全部付款金额有多大比例？",
        rationale="ratio semantics。",
    ),

    SemanticFallbackPositiveCaseV2(
        case_id="fallback_refund_rate_001",
        metric_name="refund_rate",
        question="已完成退回的金额除以原商品付款金额是多少比例？",
        rationale="amount-based refund ratio。",
    ),
    SemanticFallbackPositiveCaseV2(
        case_id="fallback_refund_rate_002",
        metric_name="refund_rate",
        question="原支付商品金额中最终被完成退款的金额占多少？",
        rationale="amount basis。",
    ),
    SemanticFallbackPositiveCaseV2(
        case_id="fallback_refund_rate_003",
        metric_name="refund_rate",
        question="按原购买期归属，完成退回金额相对原实付金额的比值",
        rationale="sales cohort attribution。",
    ),

    SemanticFallbackPositiveCaseV2(
        case_id="fallback_roi_001",
        metric_name="roi",
        question="渠道带来的付款金额除以同期广告投入后得到多少倍？",
        rationale="GMV / spend。",
    ),
    SemanticFallbackPositiveCaseV2(
        case_id="fallback_roi_002",
        metric_name="roi",
        question="每投入一元渠道营销费用能带来几元成功付款金额？",
        rationale="unit spend return。",
    ),
    SemanticFallbackPositiveCaseV2(
        case_id="fallback_roi_003",
        metric_name="roi",
        question="比较渠道同期付款产出与营销投入的倍数关系",
        rationale="return multiple。",
    ),

    SemanticFallbackPositiveCaseV2(
        case_id="fallback_cac_001",
        metric_name="cac",
        question="渠道营销投入除以该渠道第一次付款的客户数量是多少？",
        rationale="spend / channel first-paid customers。",
    ),
    SemanticFallbackPositiveCaseV2(
        case_id="fallback_cac_002",
        metric_name="cac",
        question="平均为了得到一个首次在该平台付费的客户要花多少投放费用？",
        rationale="channel acquisition formula。",
    ),
    SemanticFallbackPositiveCaseV2(
        case_id="fallback_cac_003",
        metric_name="cac",
        question="各平台投入费用摊到首次在平台完成付款的客户后每人是多少？",
        rationale="first-paid acquisition cost。",
    ),

    SemanticFallbackPositiveCaseV2(
        case_id="fallback_brand_new_001",
        metric_name="brand_paid_new_customer_count",
        question="统计第一次在整个品牌完成付款的不同客户数量",
        rationale="global first paid event。",
    ),
    SemanticFallbackPositiveCaseV2(
        case_id="fallback_brand_new_002",
        metric_name="brand_paid_new_customer_count",
        question="分析期里全历史第一次成功付费发生在本期的客户有多少？",
        rationale="full-history first payment then window。",
    ),
    SemanticFallbackPositiveCaseV2(
        case_id="fallback_brand_new_003",
        metric_name="brand_paid_new_customer_count",
        question="从全品牌历史付款记录找每人第一笔，再数第一笔落在本期的人",
        rationale="algorithmic brand first-paid count。",
    ),

    SemanticFallbackPositiveCaseV2(
        case_id="fallback_channel_new_001",
        metric_name="channel_paid_new_customer_count",
        question="每个平台统计客户第一次在这个平台完成付款的事件数量",
        rationale="customer × channel first paid。",
    ),
    SemanticFallbackPositiveCaseV2(
        case_id="fallback_channel_new_002",
        metric_name="channel_paid_new_customer_count",
        question="一个客户在某个平台首次成功付费且发生在本期的数量",
        rationale="channel-local first paid。",
    ),
    SemanticFallbackPositiveCaseV2(
        case_id="fallback_channel_new_003",
        metric_name="channel_paid_new_customer_count",
        question="按平台分别找每个客户历史第一笔付款，再统计落入当前周期的数量",
        rationale="full-history channel first-paid。",
    ),

    SemanticFallbackPositiveCaseV2(
        case_id="fallback_repeat_rate_001",
        metric_name="repeat_customer_rate",
        question="本期至少在两个不同付款日期出现的客户，占全部付款客户多少比例？",
        rationale="cross-date numerator / buyers。",
    ),
    SemanticFallbackPositiveCaseV2(
        case_id="fallback_repeat_rate_002",
        metric_name="repeat_customer_rate",
        question="付款客户中有多少比例的人在另一个日期再次完成过付款？",
        rationale="period cross-date repeat ratio。",
    ),
    SemanticFallbackPositiveCaseV2(
        case_id="fallback_repeat_rate_003",
        metric_name="repeat_customer_rate",
        question="把拥有两个以上不同购买日的人数除以本期所有付过款的人数",
        rationale="formula paraphrase without buyer_count alias。",
    ),

    SemanticFallbackPositiveCaseV2(
        case_id="fallback_member_share_001",
        metric_name="member_gmv_share",
        question="付款当时带有会员等级的商品实收金额，占全部商品实收金额多少？",
        rationale="payment-time member snapshot share。",
    ),
    SemanticFallbackPositiveCaseV2(
        case_id="fallback_member_share_002",
        metric_name="member_gmv_share",
        question="只看支付瞬间已有会员等级的订单，它们贡献的付款金额占整体多少？",
        rationale="snapshot semantics。",
    ),
    SemanticFallbackPositiveCaseV2(
        case_id="fallback_member_share_003",
        metric_name="member_gmv_share",
        question="历史交易按下单付款时的会员等级判断后，会员部分金额占总金额比例",
        rationale="historical snapshot basis。",
    ),

    SemanticFallbackPositiveCaseV2(
        case_id="fallback_buyer_count_001",
        metric_name="buyer_count",
        question="本期有多少不同客户至少成功完成过一次付款？",
        rationale="distinct paid customers。",
    ),
    SemanticFallbackPositiveCaseV2(
        case_id="fallback_buyer_count_002",
        metric_name="buyer_count",
        question="对成功付款记录里的客户去重后共有多少人？",
        rationale="distinct customer count。",
    ),
    SemanticFallbackPositiveCaseV2(
        case_id="fallback_buyer_count_003",
        metric_name="buyer_count",
        question="只要发生过付款就算一个人，重复购买去重后人数是多少？",
        rationale="buyer distinctness。",
    ),

    SemanticFallbackPositiveCaseV2(
        case_id="fallback_order_count_001",
        metric_name="order_count",
        question="本期成功完成付款的交易记录一共有多少笔？",
        rationale="paid transaction count。",
    ),
    SemanticFallbackPositiveCaseV2(
        case_id="fallback_order_count_002",
        metric_name="order_count",
        question="把所有付款成功的单据逐笔计数得到多少？",
        rationale="count paid orders。",
    ),
    SemanticFallbackPositiveCaseV2(
        case_id="fallback_order_count_003",
        metric_name="order_count",
        question="成功支付发生了多少次独立交易？",
        rationale="transaction occurrence count。",
    ),

    SemanticFallbackPositiveCaseV2(
        case_id="fallback_units_sold_001",
        metric_name="units_sold",
        question="把已付款商品明细里的购买数量全部相加是多少？",
        rationale="sum quantity。",
    ),
    SemanticFallbackPositiveCaseV2(
        case_id="fallback_units_sold_002",
        metric_name="units_sold",
        question="成功付款商品一共售出了多少个单位？",
        rationale="quantity total。",
    ),
    SemanticFallbackPositiveCaseV2(
        case_id="fallback_units_sold_003",
        metric_name="units_sold",
        question="对付款商品的 quantity 字段求总和",
        rationale="field aggregation。",
    ),

    SemanticFallbackPositiveCaseV2(
        case_id="fallback_spending_per_buyer_001",
        metric_name="spending_per_buyer",
        question="商品付款总金额平均摊到每个不同付款客户后是多少？",
        rationale="GMV / distinct buyers。",
    ),
    SemanticFallbackPositiveCaseV2(
        case_id="fallback_spending_per_buyer_002",
        metric_name="spending_per_buyer",
        question="每位实际付过款的不同客户平均贡献多少商品付款金额？",
        rationale="buyer-normalized spend。",
    ),
    SemanticFallbackPositiveCaseV2(
        case_id="fallback_spending_per_buyer_003",
        metric_name="spending_per_buyer",
        question="用全部商品实收金额除以去重后的付款客户数",
        rationale="formula paraphrase。",
    ),

    SemanticFallbackPositiveCaseV2(
        case_id="fallback_ipt_001",
        metric_name="ipt",
        question="成功付款商品总数量除以成功付款单据笔数是多少？",
        rationale="units / paid documents without order_count alias。",
    ),
    SemanticFallbackPositiveCaseV2(
        case_id="fallback_ipt_002",
        metric_name="ipt",
        question="一笔完成付款的交易平均包含多少个商品单位？",
        rationale="average units per paid order。",
    ),
    SemanticFallbackPositiveCaseV2(
        case_id="fallback_ipt_003",
        metric_name="ipt",
        question="把卖出的商品数量按付款交易平均分，每笔是多少个？",
        rationale="per-transaction unit count。",
    ),

    SemanticFallbackPositiveCaseV2(
        case_id="fallback_aus_001",
        metric_name="aus",
        question="全部商品付款金额除以成功付款单据笔数后是多少？",
        rationale="GMV / paid document count without order_count alias。",
    ),
    SemanticFallbackPositiveCaseV2(
        case_id="fallback_aus_002",
        metric_name="aus",
        question="每次成功付款交易平均对应多少商品付款金额？",
        rationale="average paid amount per transaction。",
    ),
    SemanticFallbackPositiveCaseV2(
        case_id="fallback_aus_003",
        metric_name="aus",
        question="把总付款产出平均到每一笔支付成功交易",
        rationale="transaction-normalized amount。",
    ),

    SemanticFallbackPositiveCaseV2(
        case_id="fallback_purchase_frequency_001",
        metric_name="purchase_frequency",
        question="成功付款单据数量平均摊到每个不同购买客户后是多少次？",
        rationale="paid document count / distinct buyers。",
    ),
    SemanticFallbackPositiveCaseV2(
        case_id="fallback_purchase_frequency_002",
        metric_name="purchase_frequency",
        question="每位实际付款客户在本期平均产生几次成功交易？",
        rationale="buyer-normalized transaction count。",
    ),
    SemanticFallbackPositiveCaseV2(
        case_id="fallback_purchase_frequency_003",
        metric_name="purchase_frequency",
        question="用支付成功的交易次数除以去重付款客户数量",
        rationale="formula paraphrase。",
    ),

    SemanticFallbackPositiveCaseV2(
        case_id="fallback_repeat_count_001",
        metric_name="repeat_customer_count",
        question="统计在至少两个不同付款日期都出现过的不同客户数量",
        rationale="cross-date repeat count。",
    ),
    SemanticFallbackPositiveCaseV2(
        case_id="fallback_repeat_count_002",
        metric_name="repeat_customer_count",
        question="同一天多次付款只算一个购买日，拥有两个以上购买日的客户有多少？",
        rationale="distinct paid-date threshold。",
    ),
    SemanticFallbackPositiveCaseV2(
        case_id="fallback_repeat_count_003",
        metric_name="repeat_customer_count",
        question="对每个客户先数不同付款日期，再统计日期数至少为二的人",
        rationale="algorithmic paraphrase。",
    ),

    SemanticFallbackPositiveCaseV2(
        case_id="fallback_multi_order_count_001",
        metric_name="multi_order_customer_count",
        question="统计成功付款交易达到两笔或更多的不同客户数量",
        rationale="paid order threshold。",
    ),
    SemanticFallbackPositiveCaseV2(
        case_id="fallback_multi_order_count_002",
        metric_name="multi_order_customer_count",
        question="即使同一天也分别算单，只要完成至少两次付款的客户有多少？",
        rationale="same-day multi-order remains multi-order。",
    ),
    SemanticFallbackPositiveCaseV2(
        case_id="fallback_multi_order_count_003",
        metric_name="multi_order_customer_count",
        question="先按客户累计付款成功单据数，再数单据数不小于二的客户",
        rationale="algorithmic paraphrase。",
    ),
)


def get_semantic_fallback_positive_cases_v2(
) -> tuple[SemanticFallbackPositiveCaseV2, ...]:
    return SEMANTIC_FALLBACK_POSITIVE_CASES_V2
