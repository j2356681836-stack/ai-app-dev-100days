from __future__ import annotations

from datetime import date

from pydantic import ValidationError

from app.agents.derived_evidence_builder_v2 import (
    DerivedEvidenceBuildStatusV2,
    build_anomaly_evidence_record_v2,
    build_contribution_evidence_record_v2,
)
from app.agents.evidence_pack_v2 import (
    EvidencePackV2,
    EvidenceRecordV2,
    EvidenceTypeV2,
    GovernedEvidenceProvenanceV2,
    ProtectedResultV2,
)
from app.agents.investigation_contracts_v2 import (
    AnalysisModeV2,
    AnalysisScopeV2,
    EvidenceReferenceV2,
    InsightContractV2,
    SupportedInsightStatementV2,
)
from app.semantic_layer.time_comparison_contract_v2 import (
    AlignmentModeV2,
    ComparisonTypeV2,
    PeriodModeV2,
    TimeComparisonContractV2,
    TimeWindowReferenceV2,
)


CURRENT_WINDOW = TimeWindowReferenceV2(
    start_date=date(2025, 1, 1),
    end_date=date(2025, 12, 31),
)

REFERENCE_WINDOW = TimeWindowReferenceV2(
    start_date=date(2024, 1, 1),
    end_date=date(2024, 12, 31),
)

COMPARISON = TimeComparisonContractV2(
    comparison_type=ComparisonTypeV2.YOY,
    period_mode=PeriodModeV2.COMPLETED_PERIOD,
    alignment_mode=AlignmentModeV2.CALENDAR_ALIGNED,
    current_window=CURRENT_WINDOW,
    reference_window=REFERENCE_WINDOW,
)

SCOPE = AnalysisScopeV2(
    metric_name="gmv",
    analysis_window=CURRENT_WINDOW,
    comparison=COMPARISON,
    result_grain="channel",
    scope_summary="Day87 derived evidence lineage acceptance。",
)


def _ref(
    evidence_id: str,
    source: str,
) -> EvidenceReferenceV2:
    return EvidenceReferenceV2(
        evidence_id=evidence_id,
        source=source,
        description=f"{evidence_id} 测试证据。",
    )


def _parent_record(
    evidence_id: str,
) -> EvidenceRecordV2:
    """
    Step D 的 parent fixture 代表“已经被 Governed Query Builder
    验证过的上游受保护 Evidence”。

    Step E 收紧了 INVESTIGATION_OBSERVATION 合同后，这里不能再用
    Observation 类型充当占位符；否则测试会把不同 Evidence 类型混在一起。
    """

    is_reference = "reference" in evidence_id
    is_dimension = "channel" in evidence_id

    window = (
        REFERENCE_WINDOW
        if is_reference
        else CURRENT_WINDOW
    )
    result_grain = (
        "channel"
        if is_dimension
        else "overall"
    )

    if is_dimension:
        field_names = ("channel_name", "gmv")
        rows = (
            {
                "channel_name": "天猫",
                "gmv": 800,
            },
        )
    else:
        field_names = ("gmv",)
        rows = (
            {
                "gmv": 1000,
            },
        )

    provenance = GovernedEvidenceProvenanceV2(
        dataset_name="beauty_bi_v2",
        target_schema="beauty_bi_v2",
        metric_name="gmv",
        result_grain=result_grain,
        analysis_window=window,
        scope_summary="Day87 lineage fixture scope。",
        plan_name=(
            "gmv_channel_v2"
            if is_dimension
            else "gmv_overall_v2"
        ),
        query_plan_fingerprint=f"qpf-{evidence_id}",
        envelope_fingerprint=f"env-{evidence_id}",
        compiled_contract_fingerprint=f"compiled-{evidence_id}",
        sql_fingerprint=f"sql-{evidence_id}",
        time_binding_fingerprint=f"time-{evidence_id}",
        scope_binding_fingerprint=f"scope-{evidence_id}",
        tool_name="governed_metric_query",
        tool_version="dataset_v2",
        audit_event_id=f"audit-{evidence_id}",
        audit_event_fingerprint=f"audit-fp-{evidence_id}",
        audit_record_hash=f"audit-hash-{evidence_id}",
        finalization_contract_version="governed_finalization_v1",
    )

    return EvidenceRecordV2(
        reference=_ref(
            evidence_id,
            "tool:governed_metric_query@dataset_v2",
        ),
        evidence_type=EvidenceTypeV2.GOVERNED_QUERY_RESULT,
        parent_evidence_ids=(),
        provenance=provenance,
        protected_result=ProtectedResultV2(
            field_names=field_names,
            rows=rows,
            row_count=1,
        ),
    )


def _anomaly_ref() -> EvidenceReferenceV2:
    return _ref(
        "ev_anomaly",
        "deterministic_anomaly_detector_v2",
    )


def _contribution_ref() -> EvidenceReferenceV2:
    return _ref(
        "ev_contribution",
        "deterministic_contribution_analysis_v2",
    )


def test_anomaly_two_parent_lineage_passes() -> None:
    decision = build_anomaly_evidence_record_v2(
        evidence_reference=_anomaly_ref(),
        parent_evidence_ids=(
            "ev_current_metric",
            "ev_reference_metric",
        ),
    )

    assert decision.success
    assert decision.status == DerivedEvidenceBuildStatusV2.BUILT
    assert decision.record is not None
    assert decision.record.parent_evidence_ids == (
        "ev_current_metric",
        "ev_reference_metric",
    )


def test_anomaly_can_include_sample_evidence_parents() -> None:
    decision = build_anomaly_evidence_record_v2(
        evidence_reference=_anomaly_ref(),
        parent_evidence_ids=(
            "ev_current_metric",
            "ev_reference_metric",
            "ev_current_sample",
            "ev_reference_sample",
        ),
    )

    assert decision.success
    assert decision.record is not None
    assert len(decision.record.parent_evidence_ids) == 4


def test_anomaly_wrong_source_fails() -> None:
    decision = build_anomaly_evidence_record_v2(
        evidence_reference=_ref(
            "ev_anomaly",
            "llm_guess",
        ),
        parent_evidence_ids=(
            "ev_current_metric",
            "ev_reference_metric",
        ),
    )

    assert not decision.success
    assert (
        decision.status
        == DerivedEvidenceBuildStatusV2.INVALID_SOURCE
    )


def test_anomaly_without_both_windows_fails() -> None:
    decision = build_anomaly_evidence_record_v2(
        evidence_reference=_anomaly_ref(),
        parent_evidence_ids=(
            "ev_current_metric",
        ),
    )

    assert not decision.success
    assert (
        decision.status
        == DerivedEvidenceBuildStatusV2.INVALID_LINEAGE
    )


def test_contribution_four_parent_lineage_passes() -> None:
    decision = build_contribution_evidence_record_v2(
        evidence_reference=_contribution_ref(),
        current_overall_evidence_id="ev_current_overall",
        reference_overall_evidence_id="ev_reference_overall",
        current_dimension_evidence_id="ev_current_channel",
        reference_dimension_evidence_id="ev_reference_channel",
    )

    assert decision.success
    assert decision.record is not None
    assert decision.record.parent_evidence_ids == (
        "ev_current_overall",
        "ev_reference_overall",
        "ev_current_channel",
        "ev_reference_channel",
    )


def test_contribution_wrong_source_fails() -> None:
    decision = build_contribution_evidence_record_v2(
        evidence_reference=_ref(
            "ev_contribution",
            "llm_contribution_guess",
        ),
        current_overall_evidence_id="ev_current_overall",
        reference_overall_evidence_id="ev_reference_overall",
        current_dimension_evidence_id="ev_current_channel",
        reference_dimension_evidence_id="ev_reference_channel",
    )

    assert not decision.success
    assert (
        decision.status
        == DerivedEvidenceBuildStatusV2.INVALID_SOURCE
    )


def test_contribution_duplicate_parent_fails() -> None:
    decision = build_contribution_evidence_record_v2(
        evidence_reference=_contribution_ref(),
        current_overall_evidence_id="ev_current",
        reference_overall_evidence_id="ev_reference",
        current_dimension_evidence_id="ev_current",
        reference_dimension_evidence_id="ev_reference_channel",
    )

    assert not decision.success
    assert (
        decision.status
        == DerivedEvidenceBuildStatusV2.INVALID_LINEAGE
    )


def test_derived_evidence_cannot_parent_itself() -> None:
    decision = build_anomaly_evidence_record_v2(
        evidence_reference=_anomaly_ref(),
        parent_evidence_ids=(
            "ev_anomaly",
            "ev_reference_metric",
        ),
    )

    assert not decision.success
    assert (
        decision.status
        == DerivedEvidenceBuildStatusV2.INVALID_LINEAGE
    )


def _full_insight() -> InsightContractV2:
    return InsightContractV2(
        analysis_mode=AnalysisModeV2.INVESTIGATION,
        analysis_scope=SCOPE,
        detected_anomalies=(
            SupportedInsightStatementV2(
                statement="GMV 达到已冻结异常策略。",
                evidence_ids=("ev_anomaly",),
            ),
        ),
        dimension_contributions=(
            SupportedInsightStatementV2(
                statement="天猫是主要负向贡献渠道。",
                evidence_ids=("ev_contribution",),
            ),
        ),
        evidence=(
            _anomaly_ref(),
            _contribution_ref(),
        ),
    )


def _derived_records():
    anomaly = build_anomaly_evidence_record_v2(
        evidence_reference=_anomaly_ref(),
        parent_evidence_ids=(
            "ev_current_overall",
            "ev_reference_overall",
        ),
    )
    contribution = build_contribution_evidence_record_v2(
        evidence_reference=_contribution_ref(),
        current_overall_evidence_id="ev_current_overall",
        reference_overall_evidence_id="ev_reference_overall",
        current_dimension_evidence_id="ev_current_channel",
        reference_dimension_evidence_id="ev_reference_channel",
    )

    assert anomaly.record is not None
    assert contribution.record is not None

    return anomaly.record, contribution.record


def test_full_pack_with_derived_lineage_passes() -> None:
    anomaly_record, contribution_record = _derived_records()

    pack = EvidencePackV2(
        pack_id="pack-derived-lineage-001",
        analysis_scope=SCOPE,
        insight=_full_insight(),
        evidence_records=(
            _parent_record("ev_current_overall"),
            _parent_record("ev_reference_overall"),
            _parent_record("ev_current_channel"),
            _parent_record("ev_reference_channel"),
            anomaly_record,
            contribution_record,
        ),
    )

    assert len(pack.evidence_records) == 6
    assert (
        pack.evidence_records[-1].parent_evidence_ids
        == (
            "ev_current_overall",
            "ev_reference_overall",
            "ev_current_channel",
            "ev_reference_channel",
        )
    )


def test_pack_missing_parent_fails_closed() -> None:
    anomaly_record, contribution_record = _derived_records()

    try:
        EvidencePackV2(
            pack_id="pack-missing-parent",
            analysis_scope=SCOPE,
            insight=_full_insight(),
            evidence_records=(
                _parent_record("ev_current_overall"),
                _parent_record("ev_reference_overall"),
                _parent_record("ev_current_channel"),
                # 故意缺少 ev_reference_channel
                anomaly_record,
                contribution_record,
            ),
        )
    except ValidationError:
        return

    raise AssertionError(
        "派生 Evidence 缺少 parent record 时 Evidence Pack 必须 fail-closed。"
    )


TESTS = (
    test_anomaly_two_parent_lineage_passes,
    test_anomaly_can_include_sample_evidence_parents,
    test_anomaly_wrong_source_fails,
    test_anomaly_without_both_windows_fails,
    test_contribution_four_parent_lineage_passes,
    test_contribution_wrong_source_fails,
    test_contribution_duplicate_parent_fails,
    test_derived_evidence_cannot_parent_itself,
    test_full_pack_with_derived_lineage_passes,
    test_pack_missing_parent_fails_closed,
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

    print(
        "Day87 Derived Evidence Lineage V2 "
        "Acceptance Summary"
    )
    print(f"Total: {len(TESTS)}")
    print(f"Passed: {passed}")
    print(f"Failed: {len(failures)}")

    for failure in failures:
        print(f"- {failure}")

    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    run_acceptance()
