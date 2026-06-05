from app.semantic_layer.semantic_search import semantic_search
from app.semantic_layer.table_loader import get_table_by_name
from app.semantic_layer.relationship_loader import get_relationships_for_tables


def build_context(query: str) -> str:

    result = semantic_search(query)     # Metrics,Tables
    metrics = result["metrics"]

    if not metrics:
        raise ValueError(f"未找到与问题相关的业务指标：{query}")    

    context_parts = []

    context_parts.append("=== Metrics ===")
    for metric in result["metrics"]:
        context_parts.append(
            f"""
指标: {metric["chinese_name"]} ({metric["name"]})
定义:
{metric["definition"]}
公式:
{metric["formula"]}
"""
        )

    related_tables = set()
    
    context_parts.append("=== Tables ===")
    for metric in result["metrics"]:
        for table_name in metric.get("tables", []):
            related_tables.add(table_name)

    table_details = []

    for table_name in related_tables:
        table = get_table_by_name(table_name)

        if table:
            table_details.append(table)

    for table in table_details:
        fields = table.get("fields", {})
        field_lines = []

        for field_name, field_info in fields.items():
            field_lines.append(
                f"- {field_name}: {field_info.get('description', '')}"
            )

        fields_text = "\n".join(field_lines)
        context_parts.append(
            f"""
表: {table["name"]}
字段：
{fields_text}
名称:
{table["chinese_name"]}
描述:
{table["description"]}
"""
        )

    context_parts.append("=== Relationships ===")
    table_names = [table["name"] for table in table_details]
    relationships = get_relationships_for_tables(table_names)
    for relationship in relationships:
        context_parts.append(
            f"""
{relationship["left_table"]}.{relationship["left_field"]} = {relationship["right_table"]}.{relationship["right_field"]}
"""
    )

    context_parts.append("=== filters_text ===")
    all_filters = []

    for metric in result["metrics"]:
        all_filters.extend(
            metric.get("filters", [])
        )

    filters_text = "\n".join(
        [f"- {item}" for item in all_filters]
    )
    context_parts.append(
        f"""
过滤条件:
{filters_text}
"""
    )

    return "\n".join(context_parts)


if __name__ == "__main__":
    print(build_context("退款"))