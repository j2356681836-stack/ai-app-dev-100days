import os

from dotenv import load_dotenv
from openai import OpenAI

from app.text_to_sql.prompt_builder import build_prompt
from app.text_to_sql.sql_cleaner import clean_sql


load_dotenv()


client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url=os.getenv("DEEPSEEK_BASE_URL"),
)


def generate_sql(question: str) -> str:
    prompt = build_prompt(question)

    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "user", "content": prompt},
        ],
        temperature=0,
    )

    return response.choices[0].message.content or ""


if __name__ == "__main__":
    sql = generate_sql("退款金额最高的品类是什么？")
    sql = clean_sql(sql)
    print(sql)