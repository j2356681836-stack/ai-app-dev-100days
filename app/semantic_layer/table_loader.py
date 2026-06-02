from pathlib import Path
from typing import Any

import yaml

def load_tables() -> list[dict[str, Any]]:
    """
    Load business tables from metadata/table_dictionary.yaml.
    """
    project_root = Path(__file__).resolve().parents[2]
    tables_path = project_root / "metadata" / "table_dictionary.yaml"

    with tables_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)    # .safe.load():将YAML → Python对象

    return data["tables"]

def get_table_by_name(table_name: str) -> dict | None:
    """
    根据技术名或中文名查找指标
    """

    tables = load_tables()

    for table in tables:
        if table["name"] == table_name:
            return table
        if table["chinese_name"] == table_name:
            return table
    return None

def search_tables(query: str) -> list[dict[str, Any]]:
    """
    根据关键词搜索数据表。
    当前是 V0：基于 name、chinese_name、definition 的简单包含匹配。
    """

    tables = load_tables()
    results = []

    keywords = [
        "退款率",
        "退款",
        "退货",
        "销售额",
        "销售",
        "实付",
        "订单",
    ]

    for table in tables:
        # 字段
        fields = table.get("fields", {})
        field_text = " ".join(
        [field_name + " " + field_info.get("description", "")
        for field_name, field_info in fields.items()]
    )

        searchable_text = " ".join([
            table.get("name", ""),
            table.get("chinese_name", ""),
            table.get("description", ""),
            field_text,
        ])

        for keyword in keywords:
            if keyword in query and keyword in searchable_text:
                results.append(table)
                break
    return results

if __name__ == "__main__":
    results = search_tables("退款金额")

    for table in results:
        print(table["name"], "-", table["chinese_name"])