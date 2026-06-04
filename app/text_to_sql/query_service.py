from app.db.sql_runner import run_sql
from app.text_to_sql.sql_cleaner import clean_sql
from app.text_to_sql.sql_generator import generate_sql
from app.text_to_sql.sql_validator import validate_sql
from app.text_to_sql.result_formatter import format_result, to_table

import time

start = time.time()

def ask(question: str):
    """
    自然语言问题 -> SQL -> 数据库结果
    """

    raw_sql = generate_sql(question)
    sql = clean_sql(raw_sql)

    if not validate_sql(sql):
        raise ValueError("SQL 校验失败，拒绝执行。")

    rows = format_result(run_sql(sql))
    table = to_table(rows)  # 转成表格

    return {
        "success": True,
        "question": question,
        "sql": sql,
        "table": table,
    }


if __name__ == "__main__":
    result = ask("退款率最高的是啥？")

    print("Question:")
    print(result["question"])

    print("\nSQL:")
    print(result["sql"])

    print("\nTable:")
    print(result["table"])
    
    elapsed = round(time.time() - start, 2)
    print(f"\nElapsed: {elapsed}s")