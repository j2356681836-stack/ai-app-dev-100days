from app.db.sql_runner import run_sql
from app.text_to_sql.sql_cleaner import clean_sql
from app.text_to_sql.sql_generator import generate_sql
from app.text_to_sql.sql_validator import validate_sql
from app.text_to_sql.result_formatter import format_result

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

    return {
        "success": True,
        "question": question,
        "sql": sql,
        "rows": rows,
    }


if __name__ == "__main__":
    result = ask("哪个品类的退款率最高？")

    print("Question:")
    print(result["question"])

    print("\nSQL:")
    print(result["sql"])

    print("\nRows:")
    print(result["rows"])
    
    elapsed = round(time.time() - start, 2)
    print(f"\nElapsed: {elapsed}s")