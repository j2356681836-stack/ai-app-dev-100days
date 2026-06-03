def clean_sql(sql: str) -> str:
    sql = sql.replace("```sql", "")
    sql = sql.replace("```", "")
    return sql.strip()