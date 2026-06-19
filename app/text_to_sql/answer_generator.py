def format_value(value) -> str:
    """
    将结果值转换成适合回答展示的字符串。
    """
    if isinstance(value, float):
        return str(round(value, 2))

    return str(value)


def infer_dimension_field(row: dict) -> str | None:
    """
    从结果行中推断维度字段。
    """
    for field in ["channel_name", "category"]:
        if field in row:
            return field

    return None


def infer_metric_field(row: dict, dimension_field: str | None) -> str | None:
    """
    从结果行中推断指标字段。
    """
    for field in row.keys():
        if field != dimension_field:
            return field

    return None


def get_metric_label(metric_field: str | None) -> str:
    """
    将技术字段名转换成中文指标名。
    """
    metric_labels = {
        "refund_rate_pct": "退款率",
        "channel_refund_rate_pct": "退款率",
        "channel_sales_amount": "销售额",
        "sales_quantity": "销量",
        "order_count": "订单数",
        "roi": "ROI",
        "cac": "获客成本",
    }

    if not metric_field:
        return "指标"

    return metric_labels.get(metric_field, metric_field)


def get_dimension_label(dimension_field: str | None) -> str:
    """
    将维度字段名转换成中文维度名。
    """
    dimension_labels = {
        "category": "品类",
        "channel_name": "渠道",
    }

    if not dimension_field:
        return "维度"

    return dimension_labels.get(dimension_field, dimension_field)


def format_row(row: dict, dimension_field: str, metric_field: str) -> str:
    """
    将单行结果转换成中文片段。
    """
    dimension_value = row.get(dimension_field)
    metric_value = format_value(row.get(metric_field))

    if metric_field and metric_field.endswith("_pct"):
        return f"{dimension_value} {metric_value}%"

    return f"{dimension_value} {metric_value}"


def generate_answer(
    question: str,
    table: dict,
    intent: dict | None = None,
) -> str:
    """
    根据 SQL 查询结果生成中文业务回答。

    V1 规则：
    - 只基于 table 中的结果生成回答
    - 不做额外原因解释
    - 不编造 table 中不存在的信息
    """
    rows = table.get("rows", [])
    row_count = table.get("row_count", len(rows))

    if row_count == 0 or not rows:
        return "未查询到符合条件的数据。"

    first_row = rows[0]
    dimension_field = infer_dimension_field(first_row)
    metric_field = infer_metric_field(first_row, dimension_field)

    if not dimension_field or not metric_field:
        return "查询已完成，但暂时无法生成结构化业务回答。"

    metric_label = get_metric_label(metric_field)
    dimension_label = get_dimension_label(dimension_field)

    ranking_type = None
    final_sort_direction = None

    if intent:
        ranking_type = intent.get("ranking_type")
        final_sort_direction = intent.get("final_sort_direction")

    if ranking_type == "top1":
        row_text = format_row(first_row, dimension_field, metric_field)
        return f"{dimension_label}{metric_label}排名第一的是：{row_text}。"

    if ranking_type == "topn":
        row_texts = [
            format_row(row, dimension_field, metric_field)
            for row in rows
        ]
        return f"{dimension_label}{metric_label}Top{len(rows)}分别是：" + "，".join(row_texts) + "。"

    if ranking_type == "ranking":
        row_texts = [
            format_row(row, dimension_field, metric_field)
            for row in rows
        ]

        if final_sort_direction == "asc":
            return f"{dimension_label}{metric_label}从低到高依次为：" + "，".join(row_texts) + "。"

        if final_sort_direction == "desc":
            return f"{dimension_label}{metric_label}从高到低依次为：" + "，".join(row_texts) + "。"

        return f"{dimension_label}{metric_label}排名依次为：" + "，".join(row_texts) + "。"

    row_texts = [
        format_row(row, dimension_field, metric_field)
        for row in rows
    ]
    return f"查询结果为：" + "，".join(row_texts) + "。"


if __name__ == "__main__":
    table = {
        "columns": ["category", "refund_rate_pct"],
        "rows": [
            {"category": "精华", "refund_rate_pct": 10.0},
            {"category": "防晒", "refund_rate_pct": 4.55},
            {"category": "面膜", "refund_rate_pct": 4.48},
        ],
        "row_count": 3,
    }

    intent = {
        "ranking_type": "topn",
        "final_sort_direction": None,
    }

    print(
        generate_answer(
            question="品类退款率Top3",
            table=table,
            intent=intent,
        )
    )