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
11. 比率类指标必须乘以 100，并使用 ROUND(..., 2)，字段别名使用 *_pct。
12. 当用户问题包含“最高”、“最低”、“最大”、“最小”、“最多”、“最少”、“第一”等排序取极值含义时，必须使用 ORDER BY，并添加 LIMIT 1。
13. 当用户问题没有明确指定分析维度，但指标与商品相关时，默认使用 dim_product.category 作为分析维度，不要默认使用 dim_product.product_name。
"""

    return prompt


if __name__ == "__main__":

    print(
        build_prompt(
            "哪个品类的退款率最高？"
        )
    )