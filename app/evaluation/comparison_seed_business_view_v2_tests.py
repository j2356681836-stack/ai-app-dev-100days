from __future__ import annotations

import ast
from pathlib import Path


APP_PATH = (
    Path(__file__).resolve().parents[1]
    / "ui"
    / "decision_console_app.py"
)
SOURCE = APP_PATH.read_text(
    encoding="utf-8"
)
TREE = ast.parse(SOURCE)


def _function(name: str) -> ast.FunctionDef:
    for node in TREE.body:
        if (
            isinstance(node, ast.FunctionDef)
            and node.name == name
        ):
            return node
    raise AssertionError(
        f"Missing function: {name}"
    )


def test_comparison_seed_has_business_renderer() -> None:
    node = _function(
        "_render_comparison_seed_business_v2"
    )
    source = ast.get_source_segment(
        SOURCE,
        node,
    )

    assert source is not None
    assert "### 核心结论" in source
    assert "参考期：" in source
    assert "当前期：" in source
    assert '"变化额"' in source
    assert '"变化率"' in source
    assert "_render_fact_verification_v2(result)" in source

    print(
        "PASS: "
        "test_comparison_seed_has_business_renderer"
    )


def test_generic_seed_dispatch_is_after_richer_f02() -> None:
    node = _function(
        "_render_business_view"
    )
    source = ast.get_source_segment(
        SOURCE,
        node,
    )

    assert source is not None

    f02_pos = source.find(
        "_render_f02_compound_comparison_business_v1"
    )
    generic_marker_pos = source.find(
        "comparison_seed_then_investigation_v2"
    )
    generic_render_pos = source.find(
        "_render_comparison_seed_business_v2"
    )
    fact_render_pos = source.find(
        "_render_fact_delivery_business"
    )

    assert f02_pos >= 0
    assert generic_marker_pos > f02_pos
    assert generic_render_pos > generic_marker_pos
    assert fact_render_pos > generic_render_pos

    print(
        "PASS: "
        "test_generic_seed_dispatch_is_after_richer_f02"
    )


def test_generic_seed_result_is_rendered_before_agentic_controls() -> None:
    node = _function(
        "_render_business_view"
    )
    source = ast.get_source_segment(
        SOURCE,
        node,
    )

    assert source is not None

    marker_pos = source.find(
        "comparison_seed_then_investigation_v2"
    )
    render_pos = source.find(
        "_render_comparison_seed_business_v2",
        marker_pos,
    )
    agentic_pos = source.find(
        "_render_agentic_business_section()",
        render_pos,
    )
    return_pos = source.find(
        "return",
        agentic_pos,
    )

    assert marker_pos >= 0
    assert render_pos > marker_pos
    assert agentic_pos > render_pos
    assert return_pos > agentic_pos

    print(
        "PASS: "
        "test_generic_seed_result_is_rendered_before_agentic_controls"
    )


def main() -> None:
    test_comparison_seed_has_business_renderer()
    test_generic_seed_dispatch_is_after_richer_f02()
    test_generic_seed_result_is_rendered_before_agentic_controls()


if __name__ == "__main__":
    main()
