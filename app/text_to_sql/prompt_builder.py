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
"""

    return prompt


if __name__ == "__main__":

    print(
        build_prompt(
            "哪个品类的退款率最高？"
        )
    )