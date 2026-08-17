from __future__ import annotations

from datetime import date

from pydantic import ValidationError

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
    RecommendedCheckV2,
    SupportedInsightStatementV2,
    ToolFailureCodeV2,
    UnknownV2,
)
from app.agents.investigation_loop_v2 import (
    ToolObservationStatusV2,
    ToolObservationV2,
)
from app.agents.investigation_observation_evidence_builder_v2 import (
    build_investigation_observation_evidence_v2,
)
from app.semantic_layer.time_comparison_contract_v2 import (
    TimeWindowReferenceV2,
)


WINDOW = TimeWindowReferenceV2(
    start_date=date(2025, 1, 1),
    end_date=date(2025, 12, 31),
)

SCOPE = AnalysisScopeV2(
    metric_name="gmv",
    analysis_window=WINDOW,
    result_grain="channel",
    scope_summary="Day87 Observation Evidence Acceptance。",
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


def _query_record(
    evidence_id: str = "ev_query",
) -> EvidenceRecordV2:
    provenance = GovernedEvidenceProvenanceV2(
        dataset_name="beauty_bi_v2",
        target_schema="beauty_bi_v2",
        metric_name="gmv",
        result_grain="channel",
        analysis_window=WINDOW,
        scope_summary="当前授权范围。",
        plan_name="gmv_channel_v2",
        query_plan_fingerprint="qpf",
        envelope_fingerprint="env",
        compiled_contract_fingerprint="compiled",
        sql_fingerprint="sql",
        time_binding_fingerprint="time",
        scope_binding_fingerprint="scope",
        tool_name="governed_gmv_channel_query",
        tool_version="dataset_v2",
        audit_event_id="audit-event",
        audit_event_fingerprint="audit-fp",
        audit_record_hash="audit-hash",
        finalization_contract_version="governed_finalization_v1",
    )

    return EvidenceRecordV2(
        reference=_ref(
            evidence_id,
            "tool:governed_gmv_channel_query@dataset_v2",
        ),
        evidence_type=EvidenceTypeV2.GOVERNED_QUERY_RESULT,
        provenance=provenance,
        protected_result=ProtectedResultV2(
            field_names=("channel_name", "gmv"),
            rows=(
                {
                    "channel_name": "天猫",
                    "gmv": 800,
                },
            ),
            row_count=1,
        ),
    )


def _observation_ref(
    evidence_id: str,
) -> EvidenceReferenceV2:
    return _ref(
        evidence_id,
        "investigation_loop_v2",
    )


def test_evidence_observation_preserves_parent_lineage() -> None:
    observation = ToolObservationV2(
        action_id="drill_channel",
        attempt_number=1,
        status=ToolObservationStatusV2.EVIDENCE,
        failure_code=None,
        retryable=False,
        produced_evidence_ids=("ev_query",),
        summary="渠道查询成功并产生受保护 Evidence。",
    )

    decision = build_investigation_observation_evidence_v2(
        evidence_reference=_observation_ref("ev_obs"),
        observation=observation,
    )

    assert decision.success
    assert decision.record is not None
    assert decision.record.parent_evidence_ids == ("ev_query",)
    assert (
        decision.record.investigation_observation.status
        == "evidence"
    )


def test_no_data_observation_has_no_parent() -> None:
    observation = ToolObservationV2(
        action_id="drill_product",
        attempt_number=1,
        status=ToolObservationStatusV2.NO_DATA,
        failure_code=ToolFailureCodeV2.NO_DATA,
        retryable=False,
        produced_evidence_ids=(),
        summary="当前 Scope 下商品方向没有数据。",
    )

    decision = build_investigation_observation_evidence_v2(
        evidence_reference=_observation_ref("ev_no_data"),
        observation=observation,
    )

    assert decision.success
    assert decision.record is not None
    assert decision.record.parent_evidence_ids == ()
    assert (
        decision.record.investigation_observation.status
        == "no_data"
    )


def test_failure_observation_preserves_failure_boundary() -> None:
    observation = ToolObservationV2(
        action_id="drill_region",
        attempt_number=1,
        status=ToolObservationStatusV2.FAILURE,
        failure_code=ToolFailureCodeV2.UNAUTHORIZED,
        retryable=False,
        produced_evidence_ids=(),
        summary="区域路径因权限边界被拒绝。",
    )

    decision = build_investigation_observation_evidence_v2(
        evidence_reference=_observation_ref("ev_failure"),
        observation=observation,
    )

    assert decision.success
    assert decision.record is not None
    assert (
        decision.record.investigation_observation.failure_code
        == "unauthorized"
    )
    assert decision.record.investigation_observation.retryable is False


def test_wrong_observation_source_fails() -> None:
    observation = ToolObservationV2(
        action_id="drill_channel",
        attempt_number=1,
        status=ToolObservationStatusV2.EVIDENCE,
        produced_evidence_ids=("ev_query",),
        summary="成功。",
    )

    decision = build_investigation_observation_evidence_v2(
        evidence_reference=_ref(
            "ev_obs",
            "llm_summary",
        ),
        observation=observation,
    )

    assert not decision.success
    assert decision.record is None


def test_no_data_can_support_recommended_check() -> None:
    observation = ToolObservationV2(
        action_id="drill_product",
        attempt_number=1,
        status=ToolObservationStatusV2.NO_DATA,
        failure_code=ToolFailureCodeV2.NO_DATA,
        retryable=False,
        summary="当前商品 Scope 没有可返回数据。",
    )

    decision = build_investigation_observation_evidence_v2(
        evidence_reference=_observation_ref("ev_no_data"),
        observation=observation,
    )
    assert decision.record is not None

    insight = InsightContractV2(
        analysis_mode=AnalysisModeV2.INVESTIGATION,
        analysis_scope=SCOPE,
        unknowns=(
            UnknownV2(
                description=(
                    "当前商品方向没有可用数据，无法判断商品层驱动。"
                ),
            ),
        ),
        recommended_checks=(
            RecommendedCheckV2(
                check="继续检查仍有数据的其他合法维度。",
                rationale=(
                    "商品方向返回 NO_DATA，当前不能据此形成商品原因结论。"
                ),
                evidence_ids=("ev_no_data",),
            ),
        ),
        evidence=(
            _observation_ref("ev_no_data"),
        ),
    )

    pack = EvidencePackV2(
        pack_id="pack-no-data",
        analysis_scope=SCOPE,
        insight=insight,
        evidence_records=(decision.record,),
    )

    assert len(pack.insight.unknowns) == 1
    assert len(pack.insight.recommended_checks) == 1


def test_no_data_cannot_support_confirmed_fact() -> None:
    observation = ToolObservationV2(
        action_id="drill_product",
        attempt_number=1,
        status=ToolObservationStatusV2.NO_DATA,
        failure_code=ToolFailureCodeV2.NO_DATA,
        retryable=False,
        summary="当前商品 Scope 没有可返回数据。",
    )

    decision = build_investigation_observation_evidence_v2(
        evidence_reference=_observation_ref("ev_no_data"),
        observation=observation,
    )
    assert decision.record is not None

    insight = InsightContractV2(
        analysis_mode=AnalysisModeV2.INVESTIGATION,
        analysis_scope=SCOPE,
        confirmed_facts=(
            SupportedInsightStatementV2(
                statement="商品贡献为 0。",
                evidence_ids=("ev_no_data",),
            ),
        ),
        evidence=(
            _observation_ref("ev_no_data"),
        ),
    )

    try:
        EvidencePackV2(
            pack_id="pack-invalid-no-data-fact",
            analysis_scope=SCOPE,
            insight=insight,
            evidence_records=(decision.record,),
        )
    except ValidationError:
        return

    raise AssertionError(
        "NO_DATA Observation 不能支撑“商品贡献为 0”的 Confirmed Fact。"
    )


def test_failure_cannot_support_confirmed_fact() -> None:
    observation = ToolObservationV2(
        action_id="drill_region",
        attempt_number=1,
        status=ToolObservationStatusV2.FAILURE,
        failure_code=ToolFailureCodeV2.UNAUTHORIZED,
        retryable=False,
        summary="区域路径被授权边界拒绝。",
    )

    decision = build_investigation_observation_evidence_v2(
        evidence_reference=_observation_ref("ev_failure"),
        observation=observation,
    )
    assert decision.record is not None

    insight = InsightContractV2(
        analysis_mode=AnalysisModeV2.INVESTIGATION,
        analysis_scope=SCOPE,
        confirmed_facts=(
            SupportedInsightStatementV2(
                statement="华东区域 GMV 下降。",
                evidence_ids=("ev_failure",),
            ),
        ),
        evidence=(
            _observation_ref("ev_failure"),
        ),
    )

    try:
        EvidencePackV2(
            pack_id="pack-invalid-failure-fact",
            analysis_scope=SCOPE,
            insight=insight,
            evidence_records=(decision.record,),
        )
    except ValidationError:
        return

    raise AssertionError(
        "FAILURE Observation 不能支撑业务 Confirmed Fact。"
    )


def test_query_result_can_support_confirmed_fact() -> None:
    query_record = _query_record()

    insight = InsightContractV2(
        analysis_mode=AnalysisModeV2.INVESTIGATION,
        analysis_scope=SCOPE,
        confirmed_facts=(
            SupportedInsightStatementV2(
                statement="天猫 GMV 为 800。",
                evidence_ids=("ev_query",),
            ),
        ),
        evidence=(query_record.reference,),
    )

    pack = EvidencePackV2(
        pack_id="pack-query-fact",
        analysis_scope=SCOPE,
        insight=insight,
        evidence_records=(query_record,),
    )

    assert len(pack.insight.confirmed_facts) == 1


def test_anomaly_statement_requires_anomaly_evidence_type() -> None:
    query_record = _query_record()

    insight = InsightContractV2(
        analysis_mode=AnalysisModeV2.INVESTIGATION,
        analysis_scope=SCOPE,
        detected_anomalies=(
            SupportedInsightStatementV2(
                statement="GMV 发生异常。",
                evidence_ids=("ev_query",),
            ),
        ),
        evidence=(query_record.reference,),
    )

    try:
        EvidencePackV2(
            pack_id="pack-invalid-anomaly-source",
            analysis_scope=SCOPE,
            insight=insight,
            evidence_records=(query_record,),
        )
    except ValidationError:
        return

    raise AssertionError(
        "Detected Anomaly 不能直接引用普通 Query Evidence。"
    )


def test_contribution_statement_requires_contribution_type() -> None:
    query_record = _query_record()

    insight = InsightContractV2(
        analysis_mode=AnalysisModeV2.INVESTIGATION,
        analysis_scope=SCOPE,
        dimension_contributions=(
            SupportedInsightStatementV2(
                statement="天猫是最大负向贡献渠道。",
                evidence_ids=("ev_query",),
            ),
        ),
        evidence=(query_record.reference,),
    )

    try:
        EvidencePackV2(
            pack_id="pack-invalid-contribution-source",
            analysis_scope=SCOPE,
            insight=insight,
            evidence_records=(query_record,),
        )
    except ValidationError:
        return

    raise AssertionError(
        "Contribution Statement 必须引用 Contribution Evidence。"
    )


TESTS = (
    test_evidence_observation_preserves_parent_lineage,
    test_no_data_observation_has_no_parent,
    test_failure_observation_preserves_failure_boundary,
    test_wrong_observation_source_fails,
    test_no_data_can_support_recommended_check,
    test_no_data_cannot_support_confirmed_fact,
    test_failure_cannot_support_confirmed_fact,
    test_query_result_can_support_confirmed_fact,
    test_anomaly_statement_requires_anomaly_evidence_type,
    test_contribution_statement_requires_contribution_type,
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
        "Day87 Investigation Observation Evidence V2 "
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
