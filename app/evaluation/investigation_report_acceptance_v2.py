from __future__ import annotations

from datetime import datetime, timezone

from app.delivery.analysis_investigation_snapshot_v1 import (
    AnalysisInvestigationSnapshotV1,
    EvidenceLineageStageV1,
)
from app.delivery.analysis_session_history_v1 import (
    build_analysis_history_item_v1,
)
from app.delivery.investigation_report_v2 import (
    INVESTIGATION_REPORT_VERSION,
    build_investigation_report_v2,
)
from app.delivery.runtime_delivery_bridge_v2 import (
    RuntimeDeliveryBridgeResultV2,
    RuntimeDeliveryBridgeStatusV2,
)
from app.evaluation.executive_decision_brief_acceptance_v2 import (
    _delivery,
    _view,
)
from app.delivery.executive_decision_brief_v2 import (
    build_executive_decision_brief_preview_v2,
)
from app.agents.investigation_contracts_v2 import (
    AnalysisModeV2,
)


def _runtime_delivery() -> RuntimeDeliveryBridgeResultV2:
    delivery = _delivery()
    view = _view()
    brief = build_executive_decision_brief_preview_v2(
        request_subject="为什么 7 月 GMV 同比变化？",
        delivery=delivery,
        console_view=view,
    )

    return RuntimeDeliveryBridgeResultV2(
        status=RuntimeDeliveryBridgeStatusV2.READY,
        message="当前 GMV 为 120。",
        safe_runtime_result={
            "success": True,
            "outcome": "answered",
        },
        requested_analysis_mode=AnalysisModeV2.INVESTIGATION,
        delivery=delivery,
        console_view=view,
        executive_brief=brief,
    )


def _history_item():
    return build_analysis_history_item_v1(
        original_question="为什么 7 月 GMV 同比变化？",
        runtime_delivery=_runtime_delivery(),
        history_id="history_day94_report",
        created_at_utc=datetime(
            2026,
            9,
            2,
            0,
            0,
            tzinfo=timezone.utc,
        ),
    )


def test_identity_scope_and_time_are_preserved() -> None:
    history = _history_item()

    report = build_investigation_report_v2(
        history_item=history,
    )

    assert report.contract_version == INVESTIGATION_REPORT_VERSION
    assert report.history_id == history.history_id
    assert report.original_question == history.original_question
    assert report.metric_name == history.metric_name
    assert report.analysis_window == history.analysis_window
    assert report.requested_scope == history.requested_scope
    assert report.result_grain == history.result_grain


def test_executive_brief_is_inherited_without_regeneration() -> None:
    history = _history_item()

    report = build_investigation_report_v2(
        history_item=history,
    )

    assert (
        report.executive_brief
        == history.runtime_delivery_snapshot.executive_brief
    )


def test_existing_safe_auxiliary_snapshots_are_preserved() -> None:
    history = _history_item()

    report = build_investigation_report_v2(
        history_item=history,
    )

    assert (
        report.breakdown_summary
        == history.breakdown_summary_snapshot
    )
    assert (
        report.fact_compositions
        == history.fact_composition_snapshots
    )


def test_seed_evidence_lineage_is_preserved() -> None:
    history = _history_item()

    report = build_investigation_report_v2(
        history_item=history,
        investigation_snapshot=(
            AnalysisInvestigationSnapshotV1()
        ),
    )

    assert len(report.evidence_lineage) == 1

    seed = report.evidence_lineage[0]

    assert seed.stage == EvidenceLineageStageV1.SEED
    assert seed.evidence_ids == history.evidence_ids


def test_empty_investigation_snapshot_does_not_create_fake_steps() -> None:
    history = _history_item()

    report = build_investigation_report_v2(
        history_item=history,
        investigation_snapshot=(
            AnalysisInvestigationSnapshotV1()
        ),
    )

    assert report.investigation_steps == ()
    assert report.user_exploration_steps == ()


def test_final_report_does_not_embed_runtime_or_sql_artifacts() -> None:
    history = _history_item()

    report = build_investigation_report_v2(
        history_item=history,
    )

    payload = report.model_dump()

    forbidden_top_level_fields = {
        "runtime_delivery_snapshot",
        "safe_runtime_result",
        "compiled",
        "compiled_sql",
        "sql",
        "sql_parameters",
        "parameters",
        "raw_rows",
        "governed_query_context",
    }

    assert not (
        forbidden_top_level_fields
        & set(payload)
    )


TESTS = (
    test_identity_scope_and_time_are_preserved,
    test_executive_brief_is_inherited_without_regeneration,
    test_existing_safe_auxiliary_snapshots_are_preserved,
    test_seed_evidence_lineage_is_preserved,
    test_empty_investigation_snapshot_does_not_create_fake_steps,
    test_final_report_does_not_embed_runtime_or_sql_artifacts,
)


def run_acceptance() -> None:
    passed = 0
    failures: list[str] = []

    for test in TESTS:
        try:
            test()
            passed += 1
        except Exception as exc:  # noqa: BLE001
            failures.append(
                f"{test.__name__}: "
                f"{type(exc).__name__}: {exc}"
            )

    print("Day94 Investigation Report V2 Acceptance Summary")
    print(f"Total: {len(TESTS)}")
    print(f"Passed: {passed}")
    print(f"Failed: {len(failures)}")

    for failure in failures:
        print(f"- {failure}")

    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    run_acceptance()
