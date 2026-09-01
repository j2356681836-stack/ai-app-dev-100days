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


def test_ready_submit_reruns_after_history_activation() -> None:
    node = _function("_submit_investigation")
    source = ast.get_source_segment(SOURCE, node)
    assert source is not None

    append_pos = source.find("append_analysis_history_item_v1")
    activate_pos = source.find("activate_analysis_history_item_v1")
    sync_pos = source.find("_sync_active_history_investigation_snapshot_v1")
    rerun_pos = source.rfind("st.rerun()")

    assert append_pos >= 0
    assert activate_pos > append_pos
    assert sync_pos > activate_pos
    assert rerun_pos > sync_pos

    print("PASS: test_ready_submit_reruns_after_history_activation")


def test_auto_semantic_identification_requires_business_hint() -> None:
    node = _function("_render_user_investigation_intent_controls_v2")
    source = ast.get_source_segment(SOURCE, node)
    assert source is not None

    assert "根据下方业务判断自动识别（需填写）" in source
    assert "semantic_hint_required" in source
    assert "disabled=semantic_hint_required" in source
    assert "系统不会仅凭" in source

    print("PASS: test_auto_semantic_identification_requires_business_hint")


def test_campaign_evidence_ui_imports_focused_change_dimension() -> None:
    imports = {
        alias.name
        for node in TREE.body
        if isinstance(node, ast.ImportFrom)
        and node.module == "app.agents.focused_change_breakdown_v2"
        for alias in node.names
    }

    assert "FocusedChangeDimensionV2" in imports
    assert "FocusedChangeDimensionV2.CAMPAIGN" in SOURCE

    print("PASS: test_campaign_evidence_ui_imports_focused_change_dimension")


def main() -> None:
    test_ready_submit_reruns_after_history_activation()
    test_auto_semantic_identification_requires_business_hint()
    test_campaign_evidence_ui_imports_focused_change_dimension()


if __name__ == "__main__":
    main()
