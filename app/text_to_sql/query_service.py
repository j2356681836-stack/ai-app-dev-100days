from app.db.sql_runner import run_sql
from app.text_to_sql.sql_cleaner import clean_sql
from app.text_to_sql.sql_generator import generate_sql
from app.text_to_sql.sql_validator import validate_sql
from app.text_to_sql.result_formatter import format_result, to_table
from app.semantic_layer.hybrid_search import search_metric
from app.text_to_sql.template_sql_generator import generate_template_sql

import time

start = time.time()

def ask(question: str):
    """
    自然语言问题 -> SQL -> 数据库结果
    """

    try:
        metric_result = search_metric(question)

        if metric_result.get("status") != "matched":
            return {
                "success": False,
                **metric_result,
            }

        metrics = metric_result.get("metrics", [])

        if not metrics:
            return {
                "success": False,
                "status": "error",
                "message": "未识别到业务指标",
            }

        metric_name = metrics[0]["name"]

        template_sql = generate_template_sql(
            metric_name=metric_name,
            question=question,
        )

        if template_sql:
            raw_sql = template_sql
            generation_method = "template"
        else:
            raw_sql = generate_sql(question)
            generation_method = "llm"

        sql = clean_sql(raw_sql)

    except ValueError as e:
        payload = e.args[0]
        if isinstance(payload, dict):
            return {
                "success": False,
                **payload,
            }
        return {
            "success": False,
            "status": "error",
            "message": str(e),
        }

    if not validate_sql(sql):
        raise ValueError("SQL 校验失败，拒绝执行。")

    rows = format_result(run_sql(sql))
    table = to_table(rows)  # 转成表格

    return {
        "success": True,
        "status": "completed",
        "question": question,
        "generation_method": generation_method,
        "sql": sql,
        "table": table,
    }


if __name__ == "__main__":
    questions = [
        "哪个品类销售额最高",
        "哪个订单支付金额最高",
        "哪个品类销量最高",
        "哪个品类订单最多",
        "销售额Top5品类",
    ]

    for question in questions:
        result = ask(question)

        print("Question:")
        print(result["question"])

        if not result["success"]:
            print("\nStatus:")
            print(result["status"])

            print("\nMessage:")
            print(result["message"])

            if "suggestions" in result:

                print("\nSuggestions:")

                for item in result["suggestions"]:

                    print(
                        "-",
                        item["metric_label"]
                    )

        else:
            print("\nSQL:")
            print(result["sql"])

            print("\nTable:")
            print(result["table"])

        elapsed = round(time.time() - start, 2)
        print(f"\nElapsed: {elapsed}s")