from pathlib import Path
from typing import Any

import yaml


def load_relationships() -> list[dict[str, Any]]:
    project_root = Path(__file__).resolve().parents[2]
    relationships_path = project_root / "metadata" / "table_relationships.yaml"

    with relationships_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    return data["relationships"]


def get_relationships_for_tables(
    table_names: list[str],
) -> list[dict[str, Any]]:
    relationships = load_relationships()
    table_name_set = set(table_names)

    results = []

    for relationship in relationships:
        left_table = relationship["left_table"]
        right_table = relationship["right_table"]

        if left_table in table_name_set and right_table in table_name_set:
            results.append(relationship)

    return results


if __name__ == "__main__":
    relationships = get_relationships_for_tables(
        [
            "fact_orders",
            "fact_order_items",
            "fact_refunds",
            "dim_product",
        ]
    )

    for relationship in relationships:
        print(
            f'{relationship["left_table"]}.{relationship["left_field"]} '
            f'= {relationship["right_table"]}.{relationship["right_field"]}'
        )