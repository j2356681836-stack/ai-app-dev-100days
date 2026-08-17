from __future__ import annotations

from datetime import date
from pathlib import Path

import yaml
from pydantic import ValidationError

from app.agents.evidence_pack_delivery_v2 import (
    EvidenceConfidenceLevelV2,
    EvidencePackDeliveryV2,
    EvidenceSufficiencyStatusV2,
    assemble_evidence_pack_delivery_v2,
    assess_evidence_sufficiency_v2,
    build_metric_definition_snapshot_v2,
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
    CandidateExplanationV2,
    EvidenceReferenceV2,
    InsightContractV2,
    RecommendedCheckV2,
    SupportedInsightStatementV2,
    UnknownV2,
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
    scope_summary="Day87 Evidence Delivery Acceptance。",
)


def _metadata_catalog():
    """
    Day87 必须读取 Dataset V2 的正式 Business Metrics Catalog。

    项目同时保留 V1 与 V2 Metadata：
    - metadata/business_metrics.yaml → V1 Stable
    - metadata/beauty_bi_v2/business_metrics.yaml → V2 Candidate

    Evidence Pack 当前建立在 beauty_bi_v2 Candidate 上，
    因此不能因为 V1 文件也存在就误读 V1 Metadata。
    """

    path = Path(
        "metadata/beauty_bi_v2/business_metrics.yaml"
    )

    if not path.exists():
        # 仅供隔离 acceptance fixture 使用；
        # 项目正式运行路径仍固定为 Dataset V2 Catalog。
        path = Path("business_metrics_v2.yaml")

    return yaml.safe_load(
        path.read_text(encoding="utf-8")
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


def _query_record() -> EvidenceRecordV2:
    reference = _ref(
        "ev_query",
        "tool:governed_gmv_channel_query@dataset_v2",
    )

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
        reference=reference,
        evidence_type=EvidenceTypeV2.GOVERNED_QUERY_RESULT,
        provenance=provenance,
        protected_result=ProtectedResultV2(
            field_names=("channel_name", "gmv"),
            rows=(
                {
                    "channel_name": "天猫旗舰店",
                    "gmv": 800,
                },
            ),
            row_count=1,
        ),
    )


def _fact_pack() -> EvidencePackV2:
    record = _query_record()

    insight = InsightContractV2(
        analysis_mode=AnalysisModeV2.FACT,
        analysis_scope=SCOPE,
        confirmed_facts=(
            SupportedInsightStatementV2(
                statement="天猫旗舰店 GMV 为 800。",
                evidence_ids=("ev_query",),
            ),
        ),
        evidence=(record.reference,),
    )

    return EvidencePackV2(
        pack_id="pack-fact",
        analysis_scope=SCOPE,
        insight=insight,
        evidence_records=(record,),
    )


def _partial_pack() -> EvidencePackV2:
    record = _query_record()

    insight = InsightContractV2(
        analysis_mode=AnalysisModeV2.INVESTIGATION,
        analysis_scope=SCOPE,
        confirmed_facts=(
            SupportedInsightStatementV2(
                statement="天猫旗舰店 GMV 为 800。",
                evidence_ids=("ev_query",),
            ),
        ),
        candidate_explanations=(
            CandidateExplanationV2(
                explanation="渠道变化可能与商品结构有关。",
                supporting_evidence_ids=("ev_query",),
            ),
        ),
        unknowns=(
            UnknownV2(
                description="尚未验证商品层驱动。"
            ),
        ),
        recommended_checks=(
            RecommendedCheckV2(
                check="继续检查商品结构。",
                rationale="当前证据只到渠道层。",
                evidence_ids=("ev_query",),
            ),
        ),
        evidence=(record.reference,),
    )

    return EvidencePackV2(
        pack_id="pack-partial",
        analysis_scope=SCOPE,
        insight=insight,
        evidence_records=(record,),
    )


def _insufficient_pack() -> EvidencePackV2:
    insight = InsightContractV2(
        analysis_mode=AnalysisModeV2.INVESTIGATION,
        analysis_scope=SCOPE,
        unknowns=(
            UnknownV2(
                description="当前没有足够数据形成业务结论。"
            ),
        ),
    )

    return EvidencePackV2(
        pack_id="pack-insufficient",
        analysis_scope=SCOPE,
        insight=insight,
        evidence_records=(),
    )


def test_metric_definition_is_built_from_real_metadata() -> None:
    snapshot = build_metric_definition_snapshot_v2(
        metadata_catalog=_metadata_catalog(),
        metric_name="gmv",
    )

    assert snapshot.dataset_name == "beauty_bi_v2"
    assert snapshot.metric_name == "gmv"
    assert snapshot.chinese_name == "销售额"
    assert snapshot.grain == "paid_order_items"
    assert "paid_at" in snapshot.definition
    assert "item_paid_amount" in snapshot.formula
    assert len(snapshot.metric_fingerprint) == 64


def test_unknown_metric_fails() -> None:
    try:
        build_metric_definition_snapshot_v2(
            metadata_catalog=_metadata_catalog(),
            metric_name="not_a_metric",
        )
    except ValueError:
        return

    raise AssertionError(
        "不存在的 Metric 不能生成 Definition Snapshot。"
    )


def test_fact_only_pack_is_sufficient_for_current_scope() -> None:
    assessment = assess_evidence_sufficiency_v2(
        _fact_pack()
    )

    assert (
        assessment.status
        == EvidenceSufficiencyStatusV2.SUFFICIENT_FOR_CURRENT_SCOPE
    )
    assert (
        assessment.confidence_level
        == EvidenceConfidenceLevelV2.EVIDENCE_BACKED
    )
    assert assessment.supported_claim_count == 1


def test_hypothesis_unknown_check_make_pack_partial() -> None:
    assessment = assess_evidence_sufficiency_v2(
        _partial_pack()
    )

    assert (
        assessment.status
        == EvidenceSufficiencyStatusV2.PARTIAL
    )
    assert (
        assessment.confidence_level
        == EvidenceConfidenceLevelV2.PARTIAL_EVIDENCE
    )
    assert assessment.candidate_hypothesis_count == 1
    assert assessment.unknown_count == 1
    assert assessment.recommended_check_count == 1


def test_no_supported_claim_is_insufficient() -> None:
    assessment = assess_evidence_sufficiency_v2(
        _insufficient_pack()
    )

    assert (
        assessment.status
        == EvidenceSufficiencyStatusV2.INSUFFICIENT
    )
    assert (
        assessment.confidence_level
        == EvidenceConfidenceLevelV2.INSUFFICIENT_EVIDENCE
    )
    assert assessment.supported_claim_count == 0


def test_delivery_assembles_metric_and_sufficiency() -> None:
    pack = _fact_pack()
    metric_definition = build_metric_definition_snapshot_v2(
        metadata_catalog=_metadata_catalog(),
        metric_name="gmv",
    )

    delivery = assemble_evidence_pack_delivery_v2(
        evidence_pack=pack,
        metric_definition=metric_definition,
    )

    assert delivery.metric_definition.metric_name == "gmv"
    assert (
        delivery.sufficiency.status
        == EvidenceSufficiencyStatusV2.SUFFICIENT_FOR_CURRENT_SCOPE
    )
    assert (
        delivery.evidence_pack.analysis_scope.analysis_window
        == WINDOW
    )


def test_metric_definition_mismatch_fails_closed() -> None:
    pack = _fact_pack()

    wrong_metric = build_metric_definition_snapshot_v2(
        metadata_catalog=_metadata_catalog(),
        metric_name="order_count",
    )

    try:
        assemble_evidence_pack_delivery_v2(
            evidence_pack=pack,
            metric_definition=wrong_metric,
        )
    except ValidationError:
        return

    raise AssertionError(
        "Metric Definition 与 Pack metric 不一致时必须 fail-closed。"
    )


def test_dataset_mismatch_fails_closed() -> None:
    pack = _fact_pack()

    snapshot = build_metric_definition_snapshot_v2(
        metadata_catalog=_metadata_catalog(),
        metric_name="gmv",
    ).model_copy(
        update={
            "dataset_name": "beauty_bi_v1",
        }
    )

    try:
        assemble_evidence_pack_delivery_v2(
            evidence_pack=pack,
            metric_definition=snapshot,
        )
    except ValidationError:
        return

    raise AssertionError(
        "Metadata Dataset 与 Governed Evidence Dataset "
        "不一致时必须 fail-closed。"
    )


def test_sufficiency_cannot_be_manually_upgraded() -> None:
    pack = _partial_pack()
    metric_definition = build_metric_definition_snapshot_v2(
        metadata_catalog=_metadata_catalog(),
        metric_name="gmv",
    )

    correct = assess_evidence_sufficiency_v2(pack)

    tampered = correct.model_copy(
        update={
            "status": (
                EvidenceSufficiencyStatusV2
                .SUFFICIENT_FOR_CURRENT_SCOPE
            ),
            "confidence_level": (
                EvidenceConfidenceLevelV2.EVIDENCE_BACKED
            ),
        }
    )

    try:
        EvidencePackDeliveryV2(
            evidence_pack=pack,
            metric_definition=metric_definition,
            sufficiency=tampered,
        )
    except ValidationError:
        return

    raise AssertionError(
        "调用方不能把 PARTIAL Evidence 手工升级成 SUFFICIENT。"
    )


def test_no_numeric_confidence_field_exists() -> None:
    delivery = assemble_evidence_pack_delivery_v2(
        evidence_pack=_fact_pack(),
        metric_definition=build_metric_definition_snapshot_v2(
            metadata_catalog=_metadata_catalog(),
            metric_name="gmv",
        ),
    )

    payload = delivery.model_dump()

    assert "confidence_score" not in payload["sufficiency"]
    assert "probability" not in payload["sufficiency"]
    assert (
        payload["sufficiency"]["confidence_level"]
        == "evidence_backed"
    )


TESTS = (
    test_metric_definition_is_built_from_real_metadata,
    test_unknown_metric_fails,
    test_fact_only_pack_is_sufficient_for_current_scope,
    test_hypothesis_unknown_check_make_pack_partial,
    test_no_supported_claim_is_insufficient,
    test_delivery_assembles_metric_and_sufficiency,
    test_metric_definition_mismatch_fails_closed,
    test_dataset_mismatch_fails_closed,
    test_sufficiency_cannot_be_manually_upgraded,
    test_no_numeric_confidence_field_exists,
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
        "Day87 Evidence Pack Delivery V2 "
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
