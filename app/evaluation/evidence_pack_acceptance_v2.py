from __future__ import annotations

from datetime import date

from pydantic import ValidationError

from app.agents.evidence_pack_v2 import (
    EpistemicBoundaryV2,
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
    scope_summary="当前授权范围内的 2025 年 GMV YoY 调查。",
)


def _reference(
    evidence_id: str,
    source: str,
) -> EvidenceReferenceV2:
    return EvidenceReferenceV2(
        evidence_id=evidence_id,
        source=source,
        description=f"{evidence_id} 的测试证据。",
    )


def _provenance(
    *,
    window: TimeWindowReferenceV2 = CURRENT_WINDOW,
    result_grain: str = "channel",
    plan_name: str = "gmv_channel_v2",
) -> GovernedEvidenceProvenanceV2:
    return GovernedEvidenceProvenanceV2(
        dataset_name="beauty_bi_v2",
        target_schema="beauty_bi_v2",
        metric_name="gmv",
        result_grain=result_grain,
        analysis_window=window,
        scope_summary="当前 AccessContext 授权范围。",
        plan_name=plan_name,
        query_plan_fingerprint="qpf-001",
        envelope_fingerprint="env-001",
        compiled_contract_fingerprint="compiled-001",
        sql_fingerprint="sql-001",
        time_binding_fingerprint="time-001",
        scope_binding_fingerprint="scope-001",
        tool_name="governed_metric_query",
        tool_version="dataset_v2",
        audit_event_id="audit-event-001",
        audit_event_fingerprint="audit-fingerprint-001",
        audit_record_hash="audit-record-hash-001",
        finalization_contract_version="governed_finalization_v1",
    )


def _protected_result() -> ProtectedResultV2:
    return ProtectedResultV2(
        field_names=("channel_name", "gmv"),
        rows=(
            {
                "channel_name": "天猫",
                "gmv": 800,
            },
            {
                "channel_name": "京东",
                "gmv": 500,
            },
        ),
        row_count=2,
    )


def _governed_record(
    *,
    evidence_id: str = "ev_current",
) -> EvidenceRecordV2:
    reference = _reference(
        evidence_id,
        "tool:governed_metric_query@dataset_v2",
    )
    return EvidenceRecordV2(
        reference=reference,
        evidence_type=EvidenceTypeV2.GOVERNED_QUERY_RESULT,
        parent_evidence_ids=(),
        provenance=_provenance(),
        protected_result=_protected_result(),
    )


def _insight(
    *,
    candidate_with_evidence: bool = True,
) -> InsightContractV2:
    current_ref = _reference(
        "ev_current",
        "tool:governed_metric_query@dataset_v2",
    )
    contribution_ref = _reference(
        "ev_contribution",
        "deterministic_contribution_analysis_v2",
    )

    candidate_ids = (
        ("ev_contribution",)
        if candidate_with_evidence
        else ()
    )

    return InsightContractV2(
        analysis_mode=AnalysisModeV2.INVESTIGATION,
        analysis_scope=SCOPE,
        confirmed_facts=(
            SupportedInsightStatementV2(
                statement="2025 年 GMV 同比下降 20%。",
                evidence_ids=("ev_current",),
            ),
        ),
        dimension_contributions=(
            SupportedInsightStatementV2(
                statement="天猫是最大负向贡献渠道。",
                evidence_ids=("ev_contribution",),
            ),
        ),
        candidate_explanations=(
            CandidateExplanationV2(
                explanation="天猫下降可能与商品结构变化有关。",
                supporting_evidence_ids=candidate_ids,
            ),
        ),
        unknowns=(
            UnknownV2(
                description="尚未确认具体商品层驱动因素。"
            ),
        ),
        recommended_checks=(
            RecommendedCheckV2(
                check="继续检查天猫范围内的商品结构。",
                rationale="用于验证商品结构是否与当前变化相关。",
                evidence_ids=("ev_contribution",),
            ),
        ),
        evidence=(
            current_ref,
            contribution_ref,
        ),
    )


def _contribution_record() -> EvidenceRecordV2:
    return EvidenceRecordV2(
        reference=_reference(
            "ev_contribution",
            "deterministic_contribution_analysis_v2",
        ),
        evidence_type=EvidenceTypeV2.CONTRIBUTION_RESULT,
        parent_evidence_ids=("ev_current",),
        provenance=None,
        protected_result=None,
    )


def _pack(
    *,
    insight: InsightContractV2 | None = None,
    records: tuple[EvidenceRecordV2, ...] | None = None,
) -> EvidencePackV2:
    return EvidencePackV2(
        pack_id="pack-day87-001",
        analysis_scope=SCOPE,
        insight=insight or _insight(),
        evidence_records=records or (
            _governed_record(),
            _contribution_record(),
        ),
    )


def test_valid_pack_passes() -> None:
    pack = _pack()

    assert pack.pack_id == "pack-day87-001"
    assert len(pack.evidence_records) == 2
    assert (
        pack.epistemic_boundary
        .candidate_explanation_requires_evidence
        is True
    )
    assert pack.epistemic_boundary.causal_attribution_allowed is False


def test_candidate_explanation_without_evidence_fails() -> None:
    try:
        _pack(
            insight=_insight(
                candidate_with_evidence=False
            )
        )
    except ValidationError:
        return

    raise AssertionError(
        "无 supporting evidence 的 Candidate Explanation "
        "必须被 Evidence Pack 拒绝。"
    )


def test_missing_insight_evidence_record_fails() -> None:
    try:
        _pack(
            records=(
                _governed_record(),
            )
        )
    except ValidationError:
        return

    raise AssertionError(
        "Insight 中的 Evidence 必须全部进入 Evidence Pack。"
    )


def test_unknown_parent_evidence_fails() -> None:
    bad_contribution = EvidenceRecordV2(
        reference=_reference(
            "ev_contribution",
            "deterministic_contribution_analysis_v2",
        ),
        evidence_type=EvidenceTypeV2.CONTRIBUTION_RESULT,
        parent_evidence_ids=("ev_missing_parent",),
    )

    try:
        _pack(
            records=(
                _governed_record(),
                bad_contribution,
            )
        )
    except ValidationError:
        return

    raise AssertionError(
        "parent_evidence_ids 不能引用 Pack 外 Evidence。"
    )


def test_governed_result_requires_provenance() -> None:
    try:
        EvidenceRecordV2(
            reference=_reference(
                "ev_query",
                "governed_query",
            ),
            evidence_type=(
                EvidenceTypeV2.GOVERNED_QUERY_RESULT
            ),
            protected_result=_protected_result(),
        )
    except ValidationError:
        return

    raise AssertionError(
        "Governed Query Result 缺少 provenance 时必须失败。"
    )


def test_governed_result_requires_protected_result() -> None:
    try:
        EvidenceRecordV2(
            reference=_reference(
                "ev_query",
                "governed_query",
            ),
            evidence_type=(
                EvidenceTypeV2.GOVERNED_QUERY_RESULT
            ),
            provenance=_provenance(),
        )
    except ValidationError:
        return

    raise AssertionError(
        "Governed Query Result 缺少 protected_result 时必须失败。"
    )


def test_protected_result_shape_mismatch_fails() -> None:
    try:
        ProtectedResultV2(
            field_names=("channel_name", "gmv"),
            rows=(
                {
                    "channel_name": "天猫",
                    "gmv": 800,
                    "__group_size": 50,
                },
            ),
            row_count=1,
        )
    except ValidationError:
        return

    raise AssertionError(
        "Protected Result 出现未声明字段时必须失败。"
    )


def test_protected_result_row_count_mismatch_fails() -> None:
    try:
        ProtectedResultV2(
            field_names=("channel_name", "gmv"),
            rows=(
                {
                    "channel_name": "天猫",
                    "gmv": 800,
                },
            ),
            row_count=2,
        )
    except ValidationError:
        return

    raise AssertionError(
        "row_count 与实际 rows 不一致时必须失败。"
    )


def test_pack_scope_must_match_insight_scope() -> None:
    wrong_scope = SCOPE.model_copy(
        update={
            "metric_name": "order_count",
        }
    )

    try:
        EvidencePackV2(
            pack_id="pack-wrong-scope",
            analysis_scope=wrong_scope,
            insight=_insight(),
            evidence_records=(
                _governed_record(),
                _contribution_record(),
            ),
        )
    except ValidationError:
        return

    raise AssertionError(
        "Evidence Pack 与 Insight Scope 不一致时必须失败。"
    )


def test_provenance_metric_mismatch_fails() -> None:
    bad_record = _governed_record().model_copy(
        update={
            "provenance": _provenance().model_copy(
                update={
                    "metric_name": "order_count",
                }
            )
        }
    )

    try:
        _pack(
            records=(
                bad_record,
                _contribution_record(),
            )
        )
    except ValidationError:
        return

    raise AssertionError(
        "Governed provenance metric 与 Pack metric 不一致时必须失败。"
    )


def test_reference_window_is_allowed_for_provenance() -> None:
    reference_record = EvidenceRecordV2(
        reference=_reference(
            "ev_reference",
            "tool:governed_metric_query@dataset_v2",
        ),
        evidence_type=EvidenceTypeV2.GOVERNED_QUERY_RESULT,
        provenance=_provenance(
            window=REFERENCE_WINDOW,
            plan_name="gmv_channel_v2",
        ),
        protected_result=_protected_result(),
    )

    insight = _insight().model_copy(
        update={
            "evidence": (
                *_insight().evidence,
                reference_record.reference,
            )
        }
    )

    pack = EvidencePackV2(
        pack_id="pack-reference-window",
        analysis_scope=SCOPE,
        insight=insight,
        evidence_records=(
            _governed_record(),
            _contribution_record(),
            reference_record,
        ),
    )

    assert (
        pack.evidence_records[-1]
        .provenance.analysis_window
        == REFERENCE_WINDOW
    )


def test_outside_analysis_window_fails() -> None:
    outside_window = TimeWindowReferenceV2(
        start_date=date(2023, 1, 1),
        end_date=date(2023, 12, 31),
    )

    bad_record = _governed_record().model_copy(
        update={
            "provenance": _provenance(
                window=outside_window
            )
        }
    )

    try:
        _pack(
            records=(
                bad_record,
                _contribution_record(),
            )
        )
    except ValidationError:
        return

    raise AssertionError(
        "Evidence provenance 不能脱离当前 current/reference window。"
    )


def test_epistemic_boundary_cannot_enable_causality() -> None:
    try:
        EpistemicBoundaryV2(
            causal_attribution_allowed=True
        )
    except ValidationError:
        return

    raise AssertionError(
        "当前项目不能通过配置打开 causal attribution。"
    )


def test_epistemic_boundary_cannot_enable_autonomous_action() -> None:
    try:
        EpistemicBoundaryV2(
            autonomous_business_action_allowed=True
        )
    except ValidationError:
        return

    raise AssertionError(
        "Evidence Pack 不能自主批准业务执行动作。"
    )


TESTS = (
    test_valid_pack_passes,
    test_candidate_explanation_without_evidence_fails,
    test_missing_insight_evidence_record_fails,
    test_unknown_parent_evidence_fails,
    test_governed_result_requires_provenance,
    test_governed_result_requires_protected_result,
    test_protected_result_shape_mismatch_fails,
    test_protected_result_row_count_mismatch_fails,
    test_pack_scope_must_match_insight_scope,
    test_provenance_metric_mismatch_fails,
    test_reference_window_is_allowed_for_provenance,
    test_outside_analysis_window_fails,
    test_epistemic_boundary_cannot_enable_causality,
    test_epistemic_boundary_cannot_enable_autonomous_action,
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
                f"{test.__name__}: {type(exc).__name__}: {exc}"
            )

    print("Day87 Evidence Pack V2 Step A Acceptance Summary")
    print(f"Total: {len(TESTS)}")
    print(f"Passed: {passed}")
    print(f"Failed: {len(failures)}")

    for failure in failures:
        print(f"- {failure}")

    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    run_acceptance()
