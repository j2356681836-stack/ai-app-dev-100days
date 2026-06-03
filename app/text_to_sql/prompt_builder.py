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
"""

    return prompt


if __name__ == "__main__":

    print(
        build_prompt(
            "哪个品类的退款率最高？"
        )
    )