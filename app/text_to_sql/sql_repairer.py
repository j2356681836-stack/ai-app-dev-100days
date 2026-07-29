from app.llm.deepseek_client import (
    DEEPSEEK_MODEL,
    chat_completion,
)
from app.semantic_layer.context_builder import build_context
from app.text_to_sql.prompt_builder import (
    build_intent_context,
    build_sql_generation_rules,
)


def build_repair_prompt(
    question: str,
    intent: dict | None,
    sql: str,
    error_message: str,
    context: str | None = None,
) -> str:
    """
    构建 SQL repair prompt。

    注意：
    repair prompt 不等于普通 SQL generation prompt。
    它需要额外包含：
    - 原 SQL
    - 数据库执行错误
    - 只允许返回修复后的 SELECT SQL
    """

    if context is None:
        context = build_context(question)

    intent_context = build_intent_context(intent)
    sql_generation_rules = build_sql_generation_rules()

    return f"""
你是一名 PostgreSQL SQL 修复器。

用户问题：
{question}

业务上下文：
{context}

结构化意图上下文：
{intent_context}

原 SQL：
{sql}

数据库执行错误：
{error_message}

任务：
请根据业务上下文、结构化意图和数据库错误，修复原 SQL。

要求：
1. 只返回修复后的 PostgreSQL SELECT SQL。
2. 不要返回解释。
3. 不要返回 Markdown。
4. 不要返回多个 SQL。
5. 不要使用 DROP / DELETE / UPDATE / INSERT / ALTER / TRUNCATE。
6. 不要编造业务上下文中不存在的表名、字段名、状态值或枚举值。
7. 必须尽量保持原 SQL 的业务意图不变。

SQL 生成规则：
{sql_generation_rules}
""".strip()


def repair_sql(
    question: str,
    intent: dict | None,
    sql: str,
    error_message: str,
    context: str | None = None,
) -> str:
    """
    调用 LLM 修复 SQL。

    返回值：
    - LLM 原始输出文本
    - 后续由 clean_sql_node 统一清洗
    """

    prompt = build_repair_prompt(
        question=question,
        intent=intent,
        sql=sql,
        error_message=error_message,
        context=context,
    )

    return chat_completion(
        model=DEEPSEEK_MODEL,
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
        temperature=0,
    )


if __name__ == "__main__":
    repaired = repair_sql(
        question="哪个品类订单最多？",
        intent={
            "dimension": "category",
            "ranking_type": "top1",
            "limit": 1,
            "sort_hint": "desc",
            "final_sort_direction": "desc",
            "sort_field": "order_count",
        },
        sql="""
SELECT
    dp.category,
    COUNT(fo.not_exist_column) AS order_count
FROM fact_orders fo
JOIN fact_order_items foi ON fo.order_id = foi.order_id
JOIN dim_product dp ON foi.product_id = dp.product_id
GROUP BY dp.category
ORDER BY order_count DESC
LIMIT 1
""",
        error_message='column fo.not_exist_column does not exist',
    )

    print(repaired)
