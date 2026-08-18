from __future__ import annotations

from datetime import date

from app.agents.evidence_pack_delivery_v2 import (
    EvidencePackDeliveryV2,
    EvidenceSufficiencyStatusV2,
    MetricDefinitionSnapshotV2,
    assemble_evidence_pack_delivery_v2,
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
    RecommendedCheckV2,
    SupportedInsightStatementV2,
)
from app.evaluation.automated_insight_evaluator_v2 import (
    AutomatedInsightEvaluationStatusV2,
    DeterministicInsightGateStatusV2,
    DeterministicInsightGateV2,
    evaluate_insight_delivery_v2,
)
from app.evaluation.insight_golden_cases_v2 import (
    VISIBLE_REGRESSION_CASES_V2,
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
    scope_summary="Day88 automated evaluator fixture。",
)


def _ref(
    evidence_id: str,
    source: str,
) -> EvidenceReferenceV2:
    return EvidenceReferenceV2(
        evidence_id=evidence_id,
        source=source,
        description=f"{evidence_id} fixture。",
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


def _contribution_record() -> EvidenceRecordV2:
    return EvidenceRecordV2(
        reference=_ref(
            "ev_contribution",
            "deterministic_contribution_analysis_v2",
        ),
        evidence_type=EvidenceTypeV2.CONTRIBUTION_RESULT,
        parent_evidence_ids=("ev_query",),
    )


def _delivery(
    *,
    analysis_mode: AnalysisModeV2 = AnalysisModeV2.INVESTIGATION,
    include_fact: bool = True,
    include_contribution: bool = True,
    include_check: bool = True,
) -> EvidencePackDeliveryV2:
    query_record = _query_record()
    contribution_record = _contribution_record()

    facts = (
        (
            SupportedInsightStatementV2(
                statement="2025 年 GMV 同比下降。",
                evidence_ids=("ev_query",),
            ),
        )
        if include_fact
        else ()
    )

    contributions = (
        (
            SupportedInsightStatementV2(
                statement="天猫是最大负向贡献渠道。",
                evidence_ids=("ev_contribution",),
            ),
        )
        if include_contribution
        else ()
    )

    checks = ()
    if include_check:
        checks = (
            RecommendedCheckV2(
                check="继续检查天猫商品结构。",
                rationale="当前证据仍未证明具体业务原因。",
                evidence_ids=(
                    ("ev_contribution",)
                    if include_contribution
                    else ("ev_query",)
                ),
            ),
        )

    evidence_refs = [query_record.reference]
    evidence_records = [query_record]

    if include_contribution:
        evidence_refs.append(
            contribution_record.reference
        )
        evidence_records.append(
            contribution_record
        )

    insight = InsightContractV2(
        analysis_mode=analysis_mode,
        analysis_scope=SCOPE,
        confirmed_facts=facts,
        dimension_contributions=contributions,
        recommended_checks=checks,
        evidence=tuple(evidence_refs),
    )

    pack = EvidencePackV2(
        pack_id="pack-day88-eval",
        analysis_scope=SCOPE,
        insight=insight,
        evidence_records=tuple(evidence_records),
    )

    metric_definition = MetricDefinitionSnapshotV2(
        metadata_version="beauty_bi_v2_metadata_v2",
        dataset_name="beauty_bi_v2",
        metric_name="gmv",
        chinese_name="销售额",
        grain="paid_order_items",
        definition="支付完成订单明细的销售额。",
        formula="SUM(item_paid_amount)",
        filters=("paid_at IS NOT NULL",),
        metric_fingerprint="metric-fp",
    )

    return assemble_evidence_pack_delivery_v2(
        evidence_pack=pack,
        metric_definition=metric_definition,
    )


def _gmv_case():
    return next(
        case
        for case in VISIBLE_REGRESSION_CASES_V2
        if case.case_id == "INS-REG-001"
    )


def _gate_map(result):
    return {
        item.gate: item
        for item in result.gate_results
    }


def test_valid_delivery_ready_for_business_review() -> None:
    result = evaluate_insight_delivery_v2(
        golden_case=_gmv_case(),
        delivery=_delivery(),
    )

    assert (
        result.status
        == (
            AutomatedInsightEvaluationStatusV2
            .READY_FOR_BUSINESS_REVIEW
        )
    )

    assert all(
        item.status
        == DeterministicInsightGateStatusV2.PASS
        for item in result.gate_results
    )

    assert result.business_decision_review_required


def test_required_section_missing_fails() -> None:
    result = evaluate_insight_delivery_v2(
        golden_case=_gmv_case(),
        delivery=_delivery(
            include_contribution=False,
        ),
    )

    assert (
        result.status
        == AutomatedInsightEvaluationStatusV2.DETERMINISTIC_FAIL
    )

    gates = _gate_map(result)
    assert (
        gates[
            DeterministicInsightGateV2.REQUIRED_SECTIONS
        ].status
        == DeterministicInsightGateStatusV2.FAIL
    )


def test_analysis_mode_mismatch_fails() -> None:
    # FACT mode 不能携带 recommendation / contribution，
    # 因此同时关闭相关 section，只制造 mode mismatch。
    result = evaluate_insight_delivery_v2(
        golden_case=_gmv_case(),
        delivery=_delivery(
            analysis_mode=AnalysisModeV2.FACT,
            include_contribution=False,
            include_check=False,
        ),
    )

    gates = _gate_map(result)

    assert (
        gates[
            DeterministicInsightGateV2.ANALYSIS_MODE
        ].status
        == DeterministicInsightGateStatusV2.FAIL
    )


def test_sufficiency_mismatch_fails() -> None:
    # 这个 fixture 直接构造 SUFFICIENT 会与 recommended check 的
    # Day87 deterministic rule 冲突，因此先关闭 recommended check。
    delivery = _delivery(
        include_check=False,
    )

    result = evaluate_insight_delivery_v2(
        golden_case=_gmv_case(),
        delivery=delivery,
    )

    gates = _gate_map(result)

    assert (
        gates[
            DeterministicInsightGateV2.EVIDENCE_SUFFICIENCY
        ].status
        == DeterministicInsightGateStatusV2.FAIL
    )


def test_semantic_business_review_is_not_skipped() -> None:
    result = evaluate_insight_delivery_v2(
        golden_case=_gmv_case(),
        delivery=_delivery(),
    )

    assert result.business_decision_review_required
    assert result.semantic_review_items


def test_ready_does_not_mean_business_decision_pass() -> None:
    result = evaluate_insight_delivery_v2(
        golden_case=_gmv_case(),
        delivery=_delivery(),
    )

    assert (
        result.status.value
        == "ready_for_business_review"
    )

    # Automated result 中故意不存在 overall_status / 六维真实评分。
    payload = result.model_dump()
    assert "overall_status" not in payload
    assert "factual_correctness" not in payload
    assert "diagnostic_relevance" not in payload


TESTS = (
    test_valid_delivery_ready_for_business_review,
    test_required_section_missing_fails,
    test_analysis_mode_mismatch_fails,
    test_sufficiency_mismatch_fails,
    test_semantic_business_review_is_not_skipped,
    test_ready_does_not_mean_business_decision_pass,
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
        "Day88 Automated Insight Evaluator V2 "
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
