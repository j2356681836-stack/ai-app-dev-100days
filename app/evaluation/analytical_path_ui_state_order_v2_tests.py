from __future__ import annotations

import ast
from pathlib import Path


APP_PATH = (
    Path(__file__).resolve().parents[1]
    / "ui"
    / "decision_console_app.py"
)

SOURCE = APP_PATH.read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)


def _function(name: str) -> ast.FunctionDef:
    for node in TREE.body:
        if (
            isinstance(node, ast.FunctionDef)
            and node.name == name
        ):
            return node
    raise AssertionError(f"Missing function: {name}")


def _calls(node: ast.FunctionDef) -> set[str]:
    result: set[str] = set()
    for item in ast.walk(node):
        if not isinstance(item, ast.Call):
            continue
        target = item.func
        if isinstance(target, ast.Name):
            result.add(target.id)
        elif isinstance(target, ast.Attribute):
            result.add(target.attr)
    return result


def test_followup_user_switch_continues_existing_session() -> None:
    node = _function(
        "_execute_user_analytical_investigation_v2"
    )
    calls = _calls(node)

    assert (
        "continue_day89_agentic_investigation_step_v2"
        in calls
    )
    assert (
        "build_continued_investigation_step_delivery_v2"
        in calls
    )
    assert (
        "run_day89_agentic_investigation_step_v2"
        in calls
    )

    print(
        "PASS: "
        "test_followup_user_switch_continues_existing_session"
    )


def test_grain_widget_key_is_scoped_by_domain() -> None:
    node = _function(
        "_render_user_investigation_intent_controls_v2"
    )
    segment = ast.get_source_segment(
        SOURCE,
        node,
    )

    assert segment is not None
    assert (
        'key=f"{key_prefix}::grain::{domain.value}"'
        in segment
    )

    print(
        "PASS: "
        "test_grain_widget_key_is_scoped_by_domain"
    )


def test_geography_exploration_keeps_ordered_history() -> None:
    store = _function(
        "_store_geography_exploration_result_v2"
    )
    render = _function(
        "_render_user_analytical_intent_result_v2"
    )

    store_source = ast.get_source_segment(
        SOURCE,
        store,
    )
    render_source = ast.get_source_segment(
        SOURCE,
        render,
    )

    assert store_source is not None
    assert render_source is not None

    assert (
        '"geography_exploration_results_v2"'
        in store_source
    )
    assert "current.append(result)" in store_source
    assert "上一级探索结果" in render_source
    assert "继续探索城市" in render_source

    print(
        "PASS: "
        "test_geography_exploration_keeps_ordered_history"
    )


def test_latest_geography_helper_uses_history_tail() -> None:
    node = _function(
        "_geography_exploration_result_v2"
    )
    segment = ast.get_source_segment(
        SOURCE,
        node,
    )

    assert segment is not None
    assert "results[-1]" in segment

    print(
        "PASS: "
        "test_latest_geography_helper_uses_history_tail"
    )


def main() -> None:
    test_followup_user_switch_continues_existing_session()
    test_grain_widget_key_is_scoped_by_domain()
    test_geography_exploration_keeps_ordered_history()
    test_latest_geography_helper_uses_history_tail()


if __name__ == "__main__":
    main()
