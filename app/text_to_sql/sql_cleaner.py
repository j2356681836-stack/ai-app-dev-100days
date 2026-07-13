def clean_sql(sql: str) -> str:
    """
    清理 LLM 或 Template 生成的 SQL。

    当前规则：
    1. 删除 Markdown SQL code fence
    2. 删除首尾空白
    3. 将结尾的一个或多个分号统一为一个分号
    4. 空 SQL 保持为空字符串
    """
    cleaned_sql = sql.replace("```sql", "")
    cleaned_sql = cleaned_sql.replace("```", "")
    cleaned_sql = cleaned_sql.strip()

    if not cleaned_sql:
        return ""

    cleaned_sql = cleaned_sql.rstrip(";").rstrip()

    return f"{cleaned_sql};"