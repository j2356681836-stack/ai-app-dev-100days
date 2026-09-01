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
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"Missing function: {name}")


def test_auto_semantic_submit_button_is_not_dynamically_disabled() -> None:
    node = _function(
        "_render_user_investigation_intent_controls_v2"
    )
    source = ast.get_source_segment(SOURCE, node)
    assert source is not None

    assert "disabled=semantic_hint_required" not in source
    assert "if semantic_hint_required:" in source
    assert "st.warning(" in source

    print(
        "PASS: "
        "test_auto_semantic_submit_button_is_not_dynamically_disabled"
    )


def test_auto_semantic_help_says_direct_submit_without_ctrl_enter() -> None:
    node = _function(
        "_render_user_investigation_intent_controls_v2"
    )
    source = ast.get_source_segment(SOURCE, node)
    assert source is not None

    assert "无需先按 Ctrl+Enter" in source
    assert "填写后可以直接点击提交" in source

    print(
        "PASS: "
        "test_auto_semantic_help_says_direct_submit_without_ctrl_enter"
    )


def test_empty_auto_semantic_submission_remains_fail_closed() -> None:
    node = _function(
        "_render_user_investigation_intent_controls_v2"
    )
    source = ast.get_source_segment(SOURCE, node)
    assert source is not None

    warning_pos = source.find(
        "当前使用自动识别，请先填写具体业务判断"
    )
    submit_pos = source.find(
        "_submit_user_investigation_intent_v2("
    )

    assert warning_pos >= 0
    assert submit_pos > warning_pos

    print(
        "PASS: "
        "test_empty_auto_semantic_submission_remains_fail_closed"
    )


def main() -> None:
    test_auto_semantic_submit_button_is_not_dynamically_disabled()
    test_auto_semantic_help_says_direct_submit_without_ctrl_enter()
    test_empty_auto_semantic_submission_remains_fail_closed()


if __name__ == "__main__":
    main()
