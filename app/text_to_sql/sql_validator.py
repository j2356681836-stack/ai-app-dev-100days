FORBIDDEN_KEYWORDS = [
    "drop",
    "delete",
    "truncate",
    "update",
    "insert",
    "alter",
]

def validate_sql(sql: str) -> bool:
    sql_lower = sql.lower()

    for keyword in FORBIDDEN_KEYWORDS:
        if keyword in sql_lower:
            return False

    return True

