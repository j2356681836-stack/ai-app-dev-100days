from __future__ import annotations

import inspect
from datetime import date
from decimal import Decimal

import app.delivery.decision_console_view_v2 as console_view_module
from app.agents.evidence_pack_delivery_v2 import (
    EvidenceSufficiencyStatusV2,
    MetricDefinitionSnapshotV2,
    assemble_evidence_pack_delivery_v2,
)
from app.agents.evidence_pack_v2 import (
    EvidencePackV2,
    EvidenceRecordV2,
    EvidenceTypeV2,
    GovernedEvidenceProvenanceV2,
    InvestigationObservationEvidenceV2,
    ProtectedResultV2,
)
from app.agents.investigation_contracts_v2 import (
    AnalysisModeV2,
    AnalysisScopeV2,
    EvidenceReferenceV2,
    InsightContractV2,
)
from app.delivery.decision_console_view_v2 import (
    VIEW_CONTRACT_VERSION,
    build_decision_console_view_v2,
)
from app.semantic_layer.time_comparison_contract_v2 import (
    AlignmentModeV2,
    ComparisonTypeV2,
    PeriodModeV2,
    TimeComparisonContractV2,
    TimeWindowReferenceV2,
)


EXPECTED_VIEW_VERSION = "day89_decision_console_view_v2_7"


def _comparison() -> TimeComparisonContractV2:
    return TimeComparisonContractV2(
        comparison_type=ComparisonTypeV2.YOY,
        period_mode=PeriodModeV2.COMPLETED_PERIOD,
        alignment_mode=AlignmentModeV2.CALENDAR_ALIGNED,
        current_window=TimeWindowReferenceV2(
            start_date=date(2025, 7, 1),
            end_date=date(2025, 7, 31),
        ),
        reference_window=TimeWindowReferenceV2(
            start_date=date(2024, 7, 1),
            end_date=date(2024, 7, 31),
        ),
    )


def _scope() -> AnalysisScopeV2:
    comparison = _comparison()
    return AnalysisScopeV2(
        metric_name="gmv",
        analysis_window=comparison.current_window,
        comparison=comparison,
        result_grain="channel",
        scope_summary="authorized_scope_only",
    )


def _metric_definition() -> MetricDefinitionSnapshotV2:
    return MetricDefinitionSnapshotV2(
        metadata_version="v2",
        dataset_name="beauty_bi_v2",
        metric_name="gmv",
        chinese_name="销售额",
        grain="paid_order_items",
        definition="测试用 GMV Definition。",
        formula="SUM(item_paid_amount)",
        filters=(),
        metric_fingerprint="metric-fingerprint",
    )


def _governed_record() -> EvidenceRecordV2:
    return EvidenceRecordV2(
        reference=EvidenceReferenceV2(
            evidence_id="ev-governed",
            source="governed_query_result_v2",
            description="当前周期按渠道 GMV。",
        ),
        evidence_type=EvidenceTypeV2.GOVERNED_QUERY_RESULT,
        provenance=GovernedEvidenceProvenanceV2(
            dataset_name="beauty_bi_v2",
            target_schema="beauty_bi_v2",
            metric_name="gmv",
            result_grain="channel",
            analysis_window=_comparison().current_window,
            scope_summary="authorized_scope_only",
            plan_name="gmv_by_channel",
            query_plan_fingerprint="qpf",
            envelope_fingerprint="env",
            compiled_contract_fingerprint="compiled",
            sql_fingerprint="sql-fingerprint",
            time_binding_fingerprint="time-fp",
            scope_binding_fingerprint="scope-fp",
            tool_name="governed_metric_query",
            tool_version="v2",
            audit_event_id="audit-001",
            audit_event_fingerprint="audit-fp",
            audit_record_hash="audit-hash",
            finalization_contract_version="v2",
        ),
        protected_result=ProtectedResultV2(
            field_names=("channel_name", "gmv"),
            rows=(
                {
                    "channel_name": "Tmall",
                    "gmv": Decimal("2586549.37"),
                },
            ),
            row_count=1,
        ),
    )


def _derived_record() -> EvidenceRecordV2:
    return EvidenceRecordV2(
        reference=EvidenceReferenceV2(
            evidence_id="ev-anomaly",
            source="deterministic_anomaly_detector_v2",
            description="确定性异常判断。",
        ),
        evidence_type=EvidenceTypeV2.ANOMALY_DECISION,
        parent_evidence_ids=("ev-governed",),
    )


def _observation_record() -> EvidenceRecordV2:
    return EvidenceRecordV2(
        reference=EvidenceReferenceV2(
            evidence_id="ev-observation",
            source="investigation_loop_v2",
            description="调查动作 Observation。",
        ),
        evidence_type=EvidenceTypeV2.INVESTIGATION_OBSERVATION,
        parent_evidence_ids=("ev-governed",),
        investigation_observation=InvestigationObservationEvidenceV2(
            action_id="drill_channel",
            attempt_number=1,
            status="evidence",
            failure_code=None,
            retryable=False,
            summary="渠道调查成功并产生 Evidence。",
        ),
    )


def _delivery():
    insight = InsightContractV2(
        analysis_mode=AnalysisModeV2.INVESTIGATION,
        analysis_scope=_scope(),
        evidence=(
            _governed_record().reference,
            _derived_record().reference,
            _observation_record().reference,
        ),
    )

    pack = EvidencePackV2(
        pack_id="day89-evidence-drawer-pack",
        analysis_scope=_scope(),
        insight=insight,
        evidence_records=(
            _governed_record(),
            _derived_record(),
            _observation_record(),
        ),
    )

    return assemble_evidence_pack_delivery_v2(
        evidence_pack=pack,
        metric_definition=_metric_definition(),
    )


def test_metric_definition_is_inherited() -> None:
    delivery = _delivery()
    view = build_decision_console_view_v2(
        delivery=delivery,
    )

    assert (
        view.evidence_drawer.metric_definition
        == delivery.metric_definition
    )


def test_sufficiency_is_inherited() -> None:
    delivery = _delivery()
    view = build_decision_console_view_v2(
        delivery=delivery,
    )

    assert (
        view.evidence_drawer.sufficiency_status
        == delivery.sufficiency.status
        == EvidenceSufficiencyStatusV2.INSUFFICIENT
    )
    assert (
        view.evidence_drawer.sufficiency_basis
        == delivery.sufficiency.basis
    )


def test_all_evidence_records_are_projected_in_order() -> None:
    view = build_decision_console_view_v2(
        delivery=_delivery(),
    )

    assert tuple(
        item.evidence_id
        for item in view.evidence_drawer.records
    ) == (
        "ev-governed",
        "ev-anomaly",
        "ev-observation",
    )


def test_governed_evidence_exposes_safe_provenance_only() -> None:
    view = build_decision_console_view_v2(
        delivery=_delivery(),
    )

    governed = view.evidence_drawer.records[0]

    assert governed.dataset_name == "beauty_bi_v2"
    assert governed.metric_name == "gmv"
    assert governed.plan_name == "gmv_by_channel"
    assert governed.audit_event_id == "audit-001"
    assert governed.released_field_names == (
        "channel_name",
        "gmv",
    )
    assert governed.released_row_count == 1

    dumped = governed.model_dump()
    assert "rows" not in dumped
    assert "sql" not in dumped
    assert "parameters" not in dumped


def test_derived_lineage_is_preserved() -> None:
    view = build_decision_console_view_v2(
        delivery=_delivery(),
    )

    derived = view.evidence_drawer.records[1]
    assert derived.evidence_type == EvidenceTypeV2.ANOMALY_DECISION
    assert derived.parent_evidence_ids == ("ev-governed",)
    assert derived.audit_event_id is None


def test_investigation_observation_summary_is_projected() -> None:
    view = build_decision_console_view_v2(
        delivery=_delivery(),
    )

    observation = view.evidence_drawer.records[2]
    assert observation.observation_action_id == "drill_channel"
    assert observation.observation_status == "evidence"
    assert (
        observation.observation_summary
        == "渠道调查成功并产生 Evidence。"
    )


def test_empty_evidence_pack_still_has_metric_definition() -> None:
    insight = InsightContractV2(
        analysis_mode=AnalysisModeV2.INVESTIGATION,
        analysis_scope=_scope(),
    )
    pack = EvidencePackV2(
        pack_id="day89-empty-drawer-pack",
        analysis_scope=_scope(),
        insight=insight,
        evidence_records=(),
    )
    delivery = assemble_evidence_pack_delivery_v2(
        evidence_pack=pack,
        metric_definition=_metric_definition(),
    )

    view = build_decision_console_view_v2(
        delivery=delivery,
    )

    assert view.evidence_drawer.records == ()
    assert (
        view.evidence_drawer.metric_definition.metric_name
        == "gmv"
    )


TESTS = (
    test_metric_definition_is_inherited,
    test_sufficiency_is_inherited,
    test_all_evidence_records_are_projected_in_order,
    test_governed_evidence_exposes_safe_provenance_only,
    test_derived_lineage_is_preserved,
    test_investigation_observation_summary_is_projected,
    test_empty_evidence_pack_still_has_metric_definition,
)


def run_acceptance() -> None:
    print("Day89 Decision Console Evidence Drawer Preflight")
    print(f"Module: {console_view_module.__file__}")
    print(f"Version: {VIEW_CONTRACT_VERSION}")
    print(
        "Signature: "
        f"{inspect.signature(build_decision_console_view_v2)}"
    )

    if VIEW_CONTRACT_VERSION != EXPECTED_VIEW_VERSION:
        raise SystemExit(
            "Loaded Decision Console View version is stale: "
            f"expected={EXPECTED_VIEW_VERSION}; "
            f"actual={VIEW_CONTRACT_VERSION}"
        )

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

    print()
    print("Day89 Decision Console Evidence Drawer Acceptance Summary")
    print(f"Total: {len(TESTS)}")
    print(f"Passed: {passed}")
    print(f"Failed: {len(failures)}")

    for failure in failures:
        print(f"- {failure}")

    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    run_acceptance()
