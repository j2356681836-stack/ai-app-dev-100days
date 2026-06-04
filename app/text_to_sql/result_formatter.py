from decimal import Decimal     


def format_value(value):
    if isinstance(value, Decimal):      # 判断value是不是Decimal类型，Decimal保证浮点数的精度
        return float(value)             # json不认识Decimal，如果是Decimal需要转成float

    return value        # 非Decimal原样返回


def format_result(rows: list[dict]) -> list[dict]:
    formatted_rows = []

    for row in rows:
        formatted_row = {}
        for key, value in row.items():
            formatted_row[key] = format_value(value)
        formatted_rows.append(formatted_row)
    return formatted_rows


def to_table(rows: list[dict]) -> dict:
    if not rows:
        return {
            "columns": [],
            "rows": [],
            "row_count": 0,
        }

    return {
        "columns": list(rows[0].keys()),
        "rows": rows,
        "row_count": len(rows),
    }