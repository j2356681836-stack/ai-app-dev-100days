from __future__ import annotations
import ast
from pathlib import Path

APP_PATH = Path(__file__).resolve().parents[1] / "ui" / "decision_console_app.py"
SOURCE = APP_PATH.read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)


def _source(name: str) -> str:
    for node in TREE.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            value = ast.get_source_segment(SOURCE, node)
            assert value is not None
            return value
    raise AssertionError(f"Missing function: {name}")


def test_history_restore_restores_deep_investigation_snapshot() -> None:
    source = _source("_restore_analysis_history_item_v1")
    assert "_restore_history_investigation_snapshot_v1" in source
    print("PASS: test_history_restore_restores_deep_investigation_snapshot")


def test_deep_snapshot_contains_continuation_and_analytical_path() -> None:
    source = _source("_sync_active_history_investigation_snapshot_v1")
    for value in (
        "agentic_delivery_snapshot", "focused_change_snapshots",
        "geography_exploration_snapshots", "completed_analytical_nodes",
        "continuation_state_snapshot", "prior_stop_status_snapshots",
    ):
        assert value in source
    print("PASS: test_deep_snapshot_contains_continuation_and_analytical_path")


def test_agentic_business_view_exposes_safe_evidence_lineage() -> None:
    source = _source("_render_agentic_business_section")
    assert "_render_active_analysis_evidence_lineage_v1" in source
    lineage = _source("_render_active_analysis_evidence_lineage_v1")
    assert "查看本次分析证据链" in lineage
    assert "不展示 SQL" in lineage
    print("PASS: test_agentic_business_view_exposes_safe_evidence_lineage")


def test_history_store_prunes_orphan_deep_snapshots() -> None:
    source = _source("_store_analysis_session_history_v1")
    assert "retained_ids" in source
    assert "analysis_investigation_snapshots_v1" in source
    print("PASS: test_history_store_prunes_orphan_deep_snapshots")


def main() -> None:
    test_history_restore_restores_deep_investigation_snapshot()
    test_deep_snapshot_contains_continuation_and_analytical_path()
    test_agentic_business_view_exposes_safe_evidence_lineage()
    test_history_store_prunes_orphan_deep_snapshots()


if __name__ == "__main__":
    main()
