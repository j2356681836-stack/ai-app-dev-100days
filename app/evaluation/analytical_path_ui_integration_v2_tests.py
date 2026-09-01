from __future__ import annotations

import ast
from pathlib import Path


APP_PATH = (
    Path(__file__).resolve().parents[1]
    / "ui"
    / "decision_console_app.py"
)


def _function_node(name: str) -> ast.FunctionDef:
    tree = ast.parse(
        APP_PATH.read_text(encoding="utf-8")
    )

    for node in tree.body:
        if (
            isinstance(node, ast.FunctionDef)
            and node.name == name
        ):
            return node

    raise AssertionError(
        f"Missing function: {name}"
    )


def _called_names(node: ast.FunctionDef) -> set[str]:
    names: set[str] = set()

    for item in ast.walk(node):
        if not isinstance(item, ast.Call):
            continue

        if isinstance(item.func, ast.Name):
            names.add(item.func.id)
        elif isinstance(item.func, ast.Attribute):
            names.add(item.func.attr)

    return names


def test_user_submit_uses_new_analytical_pipeline() -> None:
    node = _function_node(
        "_submit_user_investigation_intent_v2"
    )
    calls = _called_names(node)

    required = {
        "resolve_business_analytical_intent_v2",
        "resolve_analytical_capability_v2",
        "decide_user_analytical_path_v2",
    }

    assert required.issubset(calls)
    assert (
        "resolve_user_investigation_intent_v2"
        not in calls
    )

    print(
        "PASS: "
        "test_user_submit_uses_new_analytical_pipeline"
    )


def test_stale_hypothesis_is_explicitly_cleared() -> None:
    node = _function_node(
        "_submit_user_investigation_intent_v2"
    )
    source = ast.get_source_segment(
        APP_PATH.read_text(encoding="utf-8"),
        node,
    )

    assert source is not None
    assert (
        '"user_investigation_hypothesis_v2"'
        in source
    )
    assert ".pop(" in source

    print(
        "PASS: "
        "test_stale_hypothesis_is_explicitly_cleared"
    )


def test_geography_exploration_can_continue_to_city() -> None:
    node = _function_node(
        "_render_user_analytical_intent_result_v2"
    )
    source = ast.get_source_segment(
        APP_PATH.read_text(encoding="utf-8"),
        node,
    )

    assert source is not None
    assert "继续探索城市" in source
    assert "城市已经是当前 Geography Hierarchy 的叶子层级" in source

    print(
        "PASS: "
        "test_geography_exploration_can_continue_to_city"
    )


def test_business_rows_use_safe_dimension_projection() -> None:
    body = APP_PATH.read_text(
        encoding="utf-8"
    )

    assert (
        "business_safe_breakdown_row_v2"
        in body
    )

    print(
        "PASS: "
        "test_business_rows_use_safe_dimension_projection"
    )


def main() -> None:
    test_user_submit_uses_new_analytical_pipeline()
    test_stale_hypothesis_is_explicitly_cleared()
    test_geography_exploration_can_continue_to_city()
    test_business_rows_use_safe_dimension_projection()


if __name__ == "__main__":
    main()
