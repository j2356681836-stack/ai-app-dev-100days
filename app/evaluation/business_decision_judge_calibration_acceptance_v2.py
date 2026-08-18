from __future__ import annotations

import json
from datetime import date

from pydantic import ValidationError

from app.agents.evidence_pack_delivery_v2 import (
    EvidencePackDeliveryV2,
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
    evaluate_insight_delivery_v2,
)
from app.evaluation.business_decision_evaluation_contract_v2 import (
    BusinessDecisionEvaluationResultV2,
    EvaluationDimensionResultV2,
    EvaluationScoreV2,
    derive_overall_status_v2,
)
from app.evaluation.business_decision_judge_v2 import (
    BusinessDecisionJudgeExecutionStatusV2,
    judge_business_decision_v2,
    parse_business_decision_judge_proposal_v2,
)
from app.evaluation.insight_golden_cases_v2 import (
    VISIBLE_REGRESSION_CASES_V2,
)
from app.evaluation.judge_human_calibration_v2 import (
    BusinessDecisionDimensionV2,
    HumanBusinessDecisionReviewV2,
    JudgeHumanAgreementStatusV2,
    build_judge_human_calibration_v2,
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
    scope_summary="Day88 Judge fixture。",
)


def _gmv_case():
    return next(
        case
        for case in VISIBLE_REGRESSION_CASES_V2
        if case.case_id == "INS-REG-001"
    )


def _query_record() -> EvidenceRecordV2:
    reference = EvidenceReferenceV2(
        evidence_id="ev_query",
        source="tool:governed_gmv_channel_query@dataset_v2",
        description="2025 年渠道 GMV 受保护查询证据。",
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
                {
                    "channel_name": "京东",
                    "gmv": 500,
                },
            ),
            row_count=2,
        ),
    )


def _contribution_record() -> EvidenceRecordV2:
    return EvidenceRecordV2(
        reference=EvidenceReferenceV2(
            evidence_id="ev_contribution",
            source="deterministic_contribution_analysis_v2",
            description="渠道 GMV 负向贡献排序证据。",
        ),
        evidence_type=EvidenceTypeV2.CONTRIBUTION_RESULT,
        parent_evidence_ids=("ev_query",),
    )


def _delivery() -> EvidencePackDeliveryV2:
    query = _query_record()
    contribution = _contribution_record()

    insight = InsightContractV2(
        analysis_mode=AnalysisModeV2.INVESTIGATION,
        analysis_scope=SCOPE,
        confirmed_facts=(
            SupportedInsightStatementV2(
                statement="2025 年 GMV 同比下降。",
                evidence_ids=("ev_query",),
            ),
        ),
        dimension_contributions=(
            SupportedInsightStatementV2(
                statement="天猫是最大负向贡献渠道。",
                evidence_ids=("ev_contribution",),
            ),
        ),
        recommended_checks=(
            RecommendedCheckV2(
                check="继续检查天猫商品结构。",
                rationale=(
                    "渠道贡献已定位，但尚无证据证明具体业务原因。"
                ),
                evidence_ids=("ev_contribution",),
            ),
        ),
        evidence=(
            query.reference,
            contribution.reference,
        ),
    )

    pack = EvidencePackV2(
        pack_id="pack-day88-judge",
        analysis_scope=SCOPE,
        insight=insight,
        evidence_records=(
            query,
            contribution,
        ),
    )

    metric = MetricDefinitionSnapshotV2(
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
        metric_definition=metric,
    )


def _judge_json(
    *,
    actionability: int = 2,
    factual: int = 2,
    epistemic: int = 2,
    factual_evidence_ids=("ev_query",),
) -> str:
    payload = {
        "factual_correctness": {
            "score": factual,
            "reason": "事实陈述能够由受保护查询证据支持。",
            "evidence_ids": list(factual_evidence_ids),
        },
        "diagnostic_relevance": {
            "score": 2,
            "reason": "回答从变化事实推进到渠道贡献，回应了为什么下降的调查方向。",
            "evidence_ids": ["ev_contribution"],
        },
        "prioritization": {
            "score": 2,
            "reason": "根据最大负向贡献优先调查天猫，优先级有证据依据。",
            "evidence_ids": ["ev_contribution"],
        },
        "actionability": {
            "score": actionability,
            "reason": (
                "给出了继续检查天猫商品结构的可执行调查建议。"
                if actionability == 2
                else "虽然给出方向，但下一步操作仍不够具体。"
            ),
            "evidence_ids": ["ev_contribution"],
        },
        "epistemic_discipline": {
            "score": epistemic,
            "reason": "回答没有把贡献直接写成因果原因，并保留未知边界。",
            "evidence_ids": ["ev_contribution"],
        },
        "evidence_sufficiency": {
            "score": 2,
            "reason": "回答正确表达当前证据为部分充分，没有夸大确定性。",
            "evidence_ids": ["ev_query", "ev_contribution"],
        },
    }

    return json.dumps(
        payload,
        ensure_ascii=False,
    )


class _FakeTransport:
    def __init__(
        self,
        raw_text: str,
    ):
        self.raw_text = raw_text
        self.calls = 0

    def __call__(self, **kwargs):
        self.calls += 1
        return self.raw_text


def _ready():
    case = _gmv_case()
    delivery = _delivery()
    automated = evaluate_insight_delivery_v2(
        golden_case=case,
        delivery=delivery,
    )
    return case, delivery, automated


def _dimension(
    score: EvaluationScoreV2,
    reason: str,
) -> EvaluationDimensionResultV2:
    return EvaluationDimensionResultV2(
        score=score,
        reason=reason,
    )


def _evaluation(
    *,
    factual=EvaluationScoreV2.PASS,
    relevance=EvaluationScoreV2.PASS,
    prioritization=EvaluationScoreV2.PASS,
    actionability=EvaluationScoreV2.PASS,
    epistemic=EvaluationScoreV2.PASS,
    evidence=EvaluationScoreV2.PASS,
) -> BusinessDecisionEvaluationResultV2:
    values = {
        "factual_correctness": _dimension(
            factual,
            "人工事实判断。",
        ),
        "diagnostic_relevance": _dimension(
            relevance,
            "人工诊断相关性判断。",
        ),
        "prioritization": _dimension(
            prioritization,
            "人工优先级判断。",
        ),
        "actionability": _dimension(
            actionability,
            "人工可行动性判断。",
        ),
        "epistemic_discipline": _dimension(
            epistemic,
            "人工认知边界判断。",
        ),
        "evidence_sufficiency": _dimension(
            evidence,
            "人工证据充分度判断。",
        ),
    }

    return BusinessDecisionEvaluationResultV2(
        **values,
        overall_status=derive_overall_status_v2(
            **values
        ),
    )


def test_judge_runs_after_deterministic_pass() -> None:
    case, delivery, automated = _ready()
    transport = _FakeTransport(
        _judge_json()
    )

    outcome = judge_business_decision_v2(
        golden_case=case,
        delivery=delivery,
        automated_result=automated,
        transport=transport,
    )

    assert transport.calls == 1
    assert (
        outcome.status
        == BusinessDecisionJudgeExecutionStatusV2.JUDGED
    )
    assert outcome.evaluation is not None
    assert outcome.meets_golden_floor
    assert outcome.meets_expected_overall_status


def test_model_cannot_supply_overall_status() -> None:
    payload = json.loads(
        _judge_json()
    )
    payload["overall_status"] = "pass"

    try:
        parse_business_decision_judge_proposal_v2(
            json.dumps(
                payload,
                ensure_ascii=False,
            )
        )
    except ValueError:
        return

    raise AssertionError(
        "Judge 不能自行填写 overall_status。"
    )


def test_unknown_evidence_id_fails_closed() -> None:
    case, delivery, automated = _ready()
    transport = _FakeTransport(
        _judge_json(
            factual_evidence_ids=("ev_not_exist",)
        )
    )

    try:
        judge_business_decision_v2(
            golden_case=case,
            delivery=delivery,
            automated_result=automated,
            transport=transport,
        )
    except ValueError:
        return

    raise AssertionError(
        "Judge 引用不存在的 Evidence 时必须 fail-closed。"
    )


def test_factual_pass_requires_evidence_reference() -> None:
    case, delivery, automated = _ready()
    transport = _FakeTransport(
        _judge_json(
            factual_evidence_ids=(),
        )
    )

    try:
        judge_business_decision_v2(
            golden_case=case,
            delivery=delivery,
            automated_result=automated,
            transport=transport,
        )
    except ValueError:
        return

    raise AssertionError(
        "事实 PASS/PARTIAL 不能没有 Evidence 引用。"
    )


def test_below_floor_is_recorded() -> None:
    case, delivery, automated = _ready()
    transport = _FakeTransport(
        _judge_json(
            actionability=0,
        )
    )

    outcome = judge_business_decision_v2(
        golden_case=case,
        delivery=delivery,
        automated_result=automated,
        transport=transport,
    )

    assert not outcome.meets_golden_floor
    assert "actionability" in outcome.below_floor_dimensions


def test_deterministic_fail_skips_llm() -> None:
    case, delivery, automated = _ready()

    failed = automated.model_copy(
        update={
            "status": (
                AutomatedInsightEvaluationStatusV2
                .DETERMINISTIC_FAIL
            ),
            "gate_results": tuple(
                (
                    item.model_copy(
                        update={
                            "status": (
                                DeterministicInsightGateStatusV2
                                .FAIL
                            )
                        }
                    )
                    if item.gate.value == "required_sections"
                    else item
                )
                for item in automated.gate_results
            ),
        }
    )

    # 重新经过 Pydantic，保证不是非法伪造对象。
    failed = type(automated).model_validate(
        failed.model_dump()
    )

    transport = _FakeTransport(
        _judge_json()
    )

    outcome = judge_business_decision_v2(
        golden_case=case,
        delivery=delivery,
        automated_result=failed,
        transport=transport,
    )

    assert transport.calls == 0
    assert (
        outcome.status
        == (
            BusinessDecisionJudgeExecutionStatusV2
            .SKIPPED_DETERMINISTIC_FAIL
        )
    )


def test_full_human_judge_agreement_needs_no_review() -> None:
    judge_eval = _evaluation()
    human = HumanBusinessDecisionReviewV2(
        case_id="INS-REG-001",
        evaluation=_evaluation(),
        review_notes="人工评分与 Judge 完全一致。",
    )

    result = build_judge_human_calibration_v2(
        case_id="INS-REG-001",
        judge_evaluation=judge_eval,
        human_review=human,
    )

    assert result.agreement_count == 6
    assert result.disagreement_count == 0
    assert result.overall_status_agreement
    assert not result.requires_calibration_review
    assert result.critical_disagreement_dimensions == ()


def test_noncritical_disagreement_is_recorded() -> None:
    judge_eval = _evaluation()
    human = HumanBusinessDecisionReviewV2(
        case_id="INS-REG-001",
        evaluation=_evaluation(
            actionability=EvaluationScoreV2.PARTIAL,
        ),
        review_notes="人工认为建议还不够具体。",
    )

    result = build_judge_human_calibration_v2(
        case_id="INS-REG-001",
        judge_evaluation=judge_eval,
        human_review=human,
    )

    assert result.disagreement_count == 1
    assert result.requires_calibration_review
    assert result.critical_disagreement_dimensions == ()

    comparison = next(
        item
        for item in result.comparisons
        if (
            item.dimension
            == BusinessDecisionDimensionV2.ACTIONABILITY
        )
    )
    assert (
        comparison.status
        == JudgeHumanAgreementStatusV2.DISAGREEMENT
    )


def test_factual_disagreement_is_critical() -> None:
    judge_eval = _evaluation()
    human = HumanBusinessDecisionReviewV2(
        case_id="INS-REG-001",
        evaluation=_evaluation(
            factual=EvaluationScoreV2.FAIL,
        ),
        review_notes="人工发现事实引用与 Evidence 不一致。",
    )

    result = build_judge_human_calibration_v2(
        case_id="INS-REG-001",
        judge_evaluation=judge_eval,
        human_review=human,
    )

    assert (
        BusinessDecisionDimensionV2.FACTUAL_CORRECTNESS
        in result.critical_disagreement_dimensions
    )
    assert not result.overall_status_agreement
    assert result.requires_calibration_review


def test_epistemic_disagreement_is_critical() -> None:
    judge_eval = _evaluation()
    human = HumanBusinessDecisionReviewV2(
        case_id="INS-REG-001",
        evaluation=_evaluation(
            epistemic=EvaluationScoreV2.FAIL,
        ),
        review_notes="人工认为回答把贡献写成了原因。",
    )

    result = build_judge_human_calibration_v2(
        case_id="INS-REG-001",
        judge_evaluation=judge_eval,
        human_review=human,
    )

    assert (
        BusinessDecisionDimensionV2.EPISTEMIC_DISCIPLINE
        in result.critical_disagreement_dimensions
    )
    assert result.requires_calibration_review


TESTS = (
    test_judge_runs_after_deterministic_pass,
    test_model_cannot_supply_overall_status,
    test_unknown_evidence_id_fails_closed,
    test_factual_pass_requires_evidence_reference,
    test_below_floor_is_recorded,
    test_deterministic_fail_skips_llm,
    test_full_human_judge_agreement_needs_no_review,
    test_noncritical_disagreement_is_recorded,
    test_factual_disagreement_is_critical,
    test_epistemic_disagreement_is_critical,
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
        "Day88 Business Decision Judge + "
        "Human Calibration V2 Acceptance Summary"
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
