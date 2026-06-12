from app.semantic_layer.context_builder import build_context


def build_prompt(user_question: str) -> str:
    """
    Build prompt for Text-to-SQL.
    """

    context = build_context(user_question)

    prompt = f"""
你是一名 PostgreSQL 数据分析助手。

用户问题：

{user_question}

业务上下文：

{context}

任务：

根据业务上下文生成 PostgreSQL SQL。

要求：

1. 使用提供的业务定义。
2. 使用提供的表。
3. 不要编造字段。
4. 只返回 SQL。
5. 必须使用指标中的 filters 作为 WHERE 条件。
6. 如果指标涉及 filters 中的字段，必须 JOIN 包含该字段的表。
7. 聚合除法必须使用 NULLIF 防止除以 0。
8. LEFT JOIN 用于可选事实表，例如退款表；不要因为没有退款记录而丢失销售明细。
9. SQL中的表别名和字段别名统一使用英文。
10. 不要使用中文字段别名。
11. 字段别名必须优先使用指标技术名。百分比类指标才乘以 100，并使用 ROUND(..., 2)，字段别名必须使用 指标技术名 + "_pct"。
例如 refund_rate 输出 refund_rate_pct，channel_refund_rate 输出 channel_refund_rate_pct。ROI / 投资回报率不是百分比，不要乘以 100，字段别名必须使用 roi。
12. 当用户问题包含“最高”、“最低”、“最大”、“最小”、“最多”、“最少”、“第一”等排序取极值含义时，必须使用 ORDER BY，并添加 LIMIT 1。
13. 当用户问题没有明确指定分析维度，但指标与商品相关时，默认使用 dim_product.category 作为分析维度，不要默认使用 dim_product.product_name。
14. 当指标同时涉及两张或多张事实表时，必须先在子查询或 CTE 中分别按共同维度聚合每张事实表，再 JOIN 聚合结果，禁止直接 JOIN 多张事实表后再 SUM，避免多对多行膨胀。
15. 计算 ROI 时，必须先按 channel_id 聚合 fact_orders.paid_amount 得到渠道销售额，再按 channel_id 聚合 fact_marketing_spend.spend_amount 得到渠道营销成本，最后 JOIN 两个聚合结果并计算 ROI = sales_amount / spend_amount。
16. 当 ROI 同时使用 fact_orders.order_date 和 fact_marketing_spend.spend_date，且用户没有指定日期范围时，禁止编造示例日期。必须使用 date_window CTE 计算两张表的重叠时间窗口：
start_date = GREATEST(MIN(fact_orders.order_date::date), MIN(fact_marketing_spend.spend_date))
end_date = LEAST(MAX(fact_orders.order_date::date), MAX(fact_marketing_spend.spend_date))
并分别在 channel_sales 和 channel_spend CTE 中使用该时间窗口过滤数据。
17. 计算 CAC / 获客成本时，获客客户数必须使用真实首单新客口径：
先在全量 paid 订单中用 ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY order_date ASC) 找到每个客户的真实首单，
再判断该真实首单是否落在分析时间窗口内，
最后按真实首单 channel_id 统计 acquired_customer_count。禁止先按时间窗口过滤订单后再计算 ROW_NUMBER()。
18. 计算 CAC / 获客成本时，如果未指定日期范围，必须使用 fact_orders 与 fact_marketing_spend 的重叠日期窗口，而不是只使用订单表自身的 MIN(order_date) 和 MAX(order_date)。
19. 18. 计算 ROI 时，如果使用 CTE，必须使用以下结构：
channel_sales CTE 只包含 channel_id 和 sales_amount；
channel_spend CTE 只包含 channel_id 和 spend_amount；
最终 SELECT 必须同时 JOIN channel_sales cs 和 channel_spend csp；
ROI 必须写为 ROUND(cs.sales_amount / NULLIF(csp.spend_amount, 0), 2) AS roi；
禁止使用 cs.spend_amount，因为 spend_amount 不属于 channel_sales。
"""

    return prompt


if __name__ == "__main__":

    print(
        build_prompt(
            "哪个品类的退款率最高？"
        )
    )