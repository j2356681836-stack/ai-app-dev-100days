from app.llm.deepseek_client import (
    DEEPSEEK_MODEL,
    chat_completion,
)
from app.text_to_sql.prompt_builder import build_prompt
from app.text_to_sql.sql_cleaner import clean_sql


def generate_sql(question: str, intent: dict | None = None) -> str:
    prompt = build_prompt(question, intent=intent)

    return chat_completion(
        model=DEEPSEEK_MODEL,
        messages=[
            {
                "role": "user",
                "content": prompt,
            },
        ],
        temperature=0,
    )


if __name__ == "__main__":
    sql = generate_sql("退款金额最高的品类是什么？")
    sql = clean_sql(sql)
    print(sql)
