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


def test_periodic_entry_no_longer_uses_streamlit_form() -> None:
    main = _function("main")
    source = ast.get_source_segment(SOURCE, main)
    assert source is not None

    # Only the Periodic Report entry contract moved out of st.form.
    # Other independent forms in Decision Console may still legitimately
    # use st.form_submit_button, so do not assert globally on main().
    assert 'st.form("periodic_report_entry_form")' not in source
    assert 'key="periodic_report_submit"' in source
    assert (
        'submitted = st.button(\n'
        '            "生成周期报表请求"'
        in source
    )

    print(
        "PASS: "
        "test_periodic_entry_no_longer_uses_streamlit_form"
    )


def test_periodic_date_is_committed_before_explicit_generate_button() -> None:
    main = _function("main")
    source = ast.get_source_segment(SOURCE, main)
    assert source is not None

    date_pos = source.find("anchor_date = st.date_input(")
    button_pos = source.find(
        'submitted = st.button(\n'
        '            "生成周期报表请求"'
    )
    runtime_pos = source.find("_submit_periodic_report(")

    assert date_pos >= 0
    assert button_pos > date_pos
    assert runtime_pos > button_pos

    print(
        "PASS: "
        "test_periodic_date_is_committed_before_explicit_generate_button"
    )


def test_periodic_submit_still_compares_widget_and_return_anchor() -> None:
    main = _function("main")
    source = ast.get_source_segment(SOURCE, main)
    assert source is not None

    assert (
        "widget_state_value = st.session_state.get("
        in source
    )
    assert "anchor_date=anchor_date" in source
    assert "widget_state_value=(" in source

    print(
        "PASS: "
        "test_periodic_submit_still_compares_widget_and_return_anchor"
    )


def test_periodic_controls_have_stable_widget_keys() -> None:
    main = _function("main")
    source = ast.get_source_segment(SOURCE, main)
    assert source is not None

    assert 'key="periodic_report_cadence"' in source
    assert 'key="periodic_report_submit"' in source
    assert "_periodic_anchor_state_key_v2(cadence)" in source

    print(
        "PASS: "
        "test_periodic_controls_have_stable_widget_keys"
    )


def main() -> None:
    test_periodic_entry_no_longer_uses_streamlit_form()
    test_periodic_date_is_committed_before_explicit_generate_button()
    test_periodic_submit_still_compares_widget_and_return_anchor()
    test_periodic_controls_have_stable_widget_keys()


if __name__ == "__main__":
    main()
