from __future__ import annotations

import ast
from pathlib import Path

from app.delivery.decision_console_runtime_v2 import (
    _resolve_day93_gmv_comparison_seed_investigation_v2,
)
from app.semantic_layer.result_grain_resolver_v2 import (
    ResultGrainResolutionStatusV2,
    resolve_result_grain_v2,
)


FG01 = (
    "2025年8月GMV相比7月表现怎么样？"
    "如果我要继续调查，最值得优先看哪个方向？"
)


def test_fg01_resolves_comparison_seed_not_target_grain() -> None:
    resolved = (
        _resolve_day93_gmv_comparison_seed_investigation_v2(
            FG01
        )
    )

    assert resolved is not None

    current_anchor, reference_anchor, scope = resolved

    assert current_anchor.isoformat() == "2025-08-31"
    assert reference_anchor.isoformat() == "2025-07-31"
    assert scope is not None

    raw_grain = resolve_result_grain_v2(FG01)
    assert (
        raw_grain.status
        == ResultGrainResolutionStatusV2.UNSPECIFIED
    )

    print(
        "PASS: "
        "test_fg01_resolves_comparison_seed_not_target_grain"
    )


def test_plain_comparison_is_not_intercepted() -> None:
    question = (
        "2025年8月GMV相比7月表现怎么样？"
    )

    assert (
        _resolve_day93_gmv_comparison_seed_investigation_v2(
            question
        )
        is None
    )

    print(
        "PASS: "
        "test_plain_comparison_is_not_intercepted"
    )


def test_explicit_seed_grain_is_not_intercepted() -> None:
    question = (
        "按渠道看2025年8月GMV相比7月表现怎么样？"
        "如果继续调查，最值得优先看哪个方向？"
    )

    assert (
        _resolve_day93_gmv_comparison_seed_investigation_v2(
            question
        )
        is None
    )

    print(
        "PASS: "
        "test_explicit_seed_grain_is_not_intercepted"
    )


def test_non_adjacent_months_are_not_silently_rewritten() -> None:
    question = (
        "2025年8月GMV相比6月表现怎么样？"
        "如果继续调查，最值得优先看哪个方向？"
    )

    assert (
        _resolve_day93_gmv_comparison_seed_investigation_v2(
            question
        )
        is None
    )

    print(
        "PASS: "
        "test_non_adjacent_months_are_not_silently_rewritten"
    )


def test_richer_f02_runs_before_generic_seed() -> None:
    path = (
        Path(__file__).resolve().parents[1]
        / "delivery"
        / "decision_console_runtime_v2.py"
    )
    source = path.read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)

    target = next(
        node
        for node in tree.body
        if (
            isinstance(node, ast.FunctionDef)
            and node.name
            == "run_day89_local_investigation_v2"
        )
    )

    body = ast.get_source_segment(
        source,
        target,
    )
    assert body is not None

    f02_pos = body.find(
        "_run_day93_f02_compound_comparison_v1"
    )
    generic_pos = body.find(
        "_run_day93_gmv_comparison_seed_investigation_v2"
    )

    assert f02_pos >= 0
    assert generic_pos > f02_pos

    print(
        "PASS: "
        "test_richer_f02_runs_before_generic_seed"
    )


def test_ready_seed_preserves_investigation_intent_and_time_windows() -> None:
    path = (
        Path(__file__).resolve().parents[1]
        / "delivery"
        / "decision_console_runtime_v2.py"
    )
    source = path.read_text(
        encoding="utf-8"
    )

    assert (
        '"comparison_seed_then_investigation_v2"'
        in source
    )
    assert (
        '"investigation_target_grain": None'
        in source
    )
    assert (
        '"current_window": {'
        in source
    )
    assert (
        '"reference_window": {'
        in source
    )
    assert (
        "AnalysisModeV2.INVESTIGATION"
        in source
    )

    print(
        "PASS: "
        "test_ready_seed_preserves_investigation_intent_and_time_windows"
    )


def main() -> None:
    test_fg01_resolves_comparison_seed_not_target_grain()
    test_plain_comparison_is_not_intercepted()
    test_explicit_seed_grain_is_not_intercepted()
    test_non_adjacent_months_are_not_silently_rewritten()
    test_richer_f02_runs_before_generic_seed()
    test_ready_seed_preserves_investigation_intent_and_time_windows()


if __name__ == "__main__":
    main()
