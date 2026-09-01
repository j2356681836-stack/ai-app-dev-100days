from app.delivery.analysis_investigation_snapshot_v1 import (
    AnalysisInvestigationSnapshotV1,
    EvidenceLineageStageV1,
    build_analysis_evidence_lineage_v1,
    empty_analysis_investigation_snapshot_v1,
)


def test_empty_snapshot_is_safe_and_backward_compatible() -> None:
    snapshot = empty_analysis_investigation_snapshot_v1()
    assert isinstance(snapshot, AnalysisInvestigationSnapshotV1)
    assert snapshot.agentic_delivery_snapshot is None
    assert snapshot.focused_change_snapshots == ()
    assert snapshot.geography_exploration_snapshots == ()
    assert snapshot.completed_analytical_nodes == ()
    print("PASS: test_empty_snapshot_is_safe_and_backward_compatible")


def test_seed_lineage_can_exist_without_deep_investigation() -> None:
    lineage = build_analysis_evidence_lineage_v1(
        seed_evidence_ids=("ev_seed_1", "ev_seed_2"),
        snapshot=None,
    )
    assert len(lineage) == 1
    assert lineage[0].stage == EvidenceLineageStageV1.SEED
    assert lineage[0].evidence_ids == ("ev_seed_1", "ev_seed_2")
    print("PASS: test_seed_lineage_can_exist_without_deep_investigation")


def test_lineage_contract_has_no_raw_execution_fields() -> None:
    fields = set(AnalysisInvestigationSnapshotV1.model_fields)
    forbidden = {
        "sql", "raw_sql", "parameters", "raw_rows",
        "database_url", "envelope", "compiled", "runtime_step",
    }
    assert fields.isdisjoint(forbidden)
    print("PASS: test_lineage_contract_has_no_raw_execution_fields")


def main() -> None:
    test_empty_snapshot_is_safe_and_backward_compatible()
    test_seed_lineage_can_exist_without_deep_investigation()
    test_lineage_contract_has_no_raw_execution_fields()


if __name__ == "__main__":
    main()
