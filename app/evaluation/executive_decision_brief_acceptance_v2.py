from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.agents.contribution_analysis_v2 import (
    ContributionDirectionV2,
    ContributionReconciliationStatusV2,
)
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
    ProtectedResultV2,
)
from app.agents.investigation_contracts_v2 import (
    AnalysisModeV2,
    AnalysisScopeV2,
    EvidenceReferenceV2,
    InsightContractV2,
    RecommendedCheckV2,
    SupportedInsightStatementV2,
    UnknownV2,
)
from app.agents.investigation_loop_v2 import (
    InvestigationStopReasonV2,
)
from app.agents.metric_comparison_v2 import (
    RelativeChangeStatusV2,
)
from app.delivery.decision_console_view_v2 import (
    ContributionMemberViewV2,
    ContributionViewV2,
    DecisionConsoleViewV2,
    EvidenceDrawerViewV2,
    InvestigationRuntimeControlViewV2,
    MetricComparisonViewV2,
    RuntimeClarificationViewV2,
)
from app.delivery.executive_decision_brief_v2 import (
    ExecutiveFindingTypeV2,
    ExecutiveLimitationCodeV2,
    build_executive_decision_brief_preview_v2,
)
from app.semantic_layer.time_comparison_contract_v2 import (
    AlignmentModeV2,
    ComparisonTypeV2,
    PeriodModeV2,
    TimeComparisonContractV2,
    TimeWindowReferenceV2,
)


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
            evidence_id="ev-fact",
            source="governed_query_result_v2",
            description="GMV current evidence。",
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
            sql_fingerprint="sql",
            time_binding_fingerprint="time",
            scope_binding_fingerprint="scope",
            tool_name="governed_metric_query",
            tool_version="v2",
            audit_event_id="audit-001",
            audit_event_fingerprint="audit-fp",
            audit_record_hash="audit-hash",
            finalization_contract_version="v2",
        ),
        protected_result=ProtectedResultV2(
            field_names=("gmv",),
            rows=({"gmv": Decimal("120")},),
            row_count=1,
        ),
    )


def _delivery() -> EvidencePackDeliveryV2:
    insight = InsightContractV2(
        analysis_mode=AnalysisModeV2.INVESTIGATION,
        analysis_scope=_scope(),
        confirmed_facts=(
            SupportedInsightStatementV2(
                statement="当前 GMV 为 120。",
                evidence_ids=("ev-fact",),
            ),
        ),
        dimension_contributions=(
            SupportedInsightStatementV2(
                statement="Tmall 是主要负向贡献渠道。",
                evidence_ids=("ev-contribution",),
            ),
        ),
        unknowns=(
            UnknownV2(
                description="尚未验证商品层变化。"
            ),
        ),
        recommended_checks=(
            RecommendedCheckV2(
                check="继续检查 Tmall 内商品贡献。",
                rationale="当前仍有未解释空间。",
                evidence_ids=("ev-contribution",),
            ),
        ),
        evidence=(
            _governed_record().reference,
            EvidenceReferenceV2(
                evidence_id="ev-contribution",
                source="deterministic_contribution_analysis_v2",
                description="Channel contribution。",
            ),
        ),
    )

    pack = EvidencePackV2(
        pack_id="brief-pack",
        analysis_scope=_scope(),
        insight=insight,
        evidence_records=(
            _governed_record(),
            EvidenceRecordV2(
                reference=insight.evidence[1],
                evidence_type=EvidenceTypeV2.CONTRIBUTION_RESULT,
                parent_evidence_ids=("ev-fact",),
            ),
        ),
    )

    return assemble_evidence_pack_delivery_v2(
        evidence_pack=pack,
        metric_definition=_metric_definition(),
    )


def _view() -> DecisionConsoleViewV2:
    delivery = _delivery()

    return DecisionConsoleViewV2(
        metric_name="gmv",
        result_grain="channel",
        scope_summary="authorized_scope_only",
        evidence_sufficiency=EvidenceSufficiencyStatusV2.PARTIAL,
        evidence_drawer=EvidenceDrawerViewV2(
            metric_definition=delivery.metric_definition,
            sufficiency_status=delivery.sufficiency.status,
            confidence_level=delivery.sufficiency.confidence_level.value,
            sufficiency_basis=delivery.sufficiency.basis,
            records=(),
        ),
        confirmed_facts=("当前 GMV 为 120。",),
        candidate_hypotheses=("Tmall 变化可能来自商品结构。",),
        unknowns=("尚未验证商品层变化。",),
        recommended_checks=("继续检查 Tmall 内商品贡献。",),
        comparison=MetricComparisonViewV2(
            metric_name="gmv",
            comparison_type=ComparisonTypeV2.YOY,
            current_window=_comparison().current_window,
            reference_window=_comparison().reference_window,
            current_value=Decimal("120"),
            reference_value=Decimal("100"),
            absolute_change=Decimal("20"),
            relative_change=Decimal("0.2"),
            relative_change_status=RelativeChangeStatusV2.DEFINED,
            current_evidence_id="ev-current",
            reference_evidence_id="ev-reference",
        ),
        contribution=ContributionViewV2(
            evidence_id="ev-contribution",
            metric_name="gmv",
            dimension_name="channel",
            current_overall_value=Decimal("120"),
            reference_overall_value=Decimal("100"),
            overall_delta=Decimal("20"),
            members=(
                ContributionMemberViewV2(
                    member_key="tmall",
                    member_label="Tmall",
                    current_value=Decimal("60"),
                    reference_value=Decimal("80"),
                    delta=Decimal("-20"),
                    contribution_rate=Decimal("-1"),
                    direction=ContributionDirectionV2.NEGATIVE,
                ),
                ContributionMemberViewV2(
                    member_key="jd",
                    member_label="JD",
                    current_value=Decimal("60"),
                    reference_value=Decimal("20"),
                    delta=Decimal("40"),
                    contribution_rate=Decimal("2"),
                    direction=ContributionDirectionV2.POSITIVE,
                ),
            ),
            negative_change_ranking=("tmall",),
            positive_change_ranking=("jd",),
            sum_member_delta=Decimal("20"),
            unexplained_remainder=Decimal("5"),
            reconciliation_status=(
                ContributionReconciliationStatusV2.NOT_RECONCILED
            ),
        ),
        runtime_control=InvestigationRuntimeControlViewV2(
            stop_reason=InvestigationStopReasonV2.INVESTIGATION_BUDGET_EXHAUSTED,
            evidence_sufficient=False,
            uninvestigated_action_ids=("drill_product",),
            can_continue=True,
            current_round=1,
            max_rounds=2,
            total_steps_used=3,
            max_total_investigation_steps=5,
            detail="本轮预算耗尽，但仍可由用户明确继续。",
        ),
        clarification=RuntimeClarificationViewV2(
            requirement_source="semantic_decision_v2",
            requirement_reason="商品范围仍需用户确认。",
            clarification_prompt="是否继续调查 Tmall 商品？",
            rationale="当前需要明确商品调查范围。",
        ),
    )


def test_subject_and_scope_are_preserved() -> None:
    brief = build_executive_decision_brief_preview_v2(
        request_subject="为什么 7 月 GMV 同比变化？",
        delivery=_delivery(),
        console_view=_view(),
    )

    assert brief.request_subject == "为什么 7 月 GMV 同比变化？"
    assert brief.metric_name == "gmv"
    assert brief.analysis_window == _comparison().current_window
    assert brief.scope_summary == "authorized_scope_only"


def test_kpi_summary_is_inherited() -> None:
    view = _view()
    brief = build_executive_decision_brief_preview_v2(
        request_subject="GMV 分析",
        delivery=_delivery(),
        console_view=view,
    )

    assert brief.kpi_summary == view.comparison


def test_key_findings_preserve_insight_statements_and_evidence() -> None:
    brief = build_executive_decision_brief_preview_v2(
        request_subject="GMV 分析",
        delivery=_delivery(),
        console_view=_view(),
    )

    assert brief.key_findings[0].finding_type == (
        ExecutiveFindingTypeV2.CONFIRMED_FACT
    )
    assert brief.key_findings[0].summary == "当前 GMV 为 120。"
    assert brief.key_findings[0].evidence_ids == ("ev-fact",)

    assert brief.key_findings[1].finding_type == (
        ExecutiveFindingTypeV2.DIMENSION_CONTRIBUTION
    )
    assert brief.key_findings[1].evidence_ids == (
        "ev-contribution",
    )


def test_contribution_highlights_follow_existing_ranking() -> None:
    brief = build_executive_decision_brief_preview_v2(
        request_subject="GMV 分析",
        delivery=_delivery(),
        console_view=_view(),
    )

    assert (
        brief.top_contributions.negative[0].member_key
        == "tmall"
    )
    assert (
        brief.top_contributions.positive[0].member_key
        == "jd"
    )


def test_epistemic_sections_are_preserved() -> None:
    view = _view()
    brief = build_executive_decision_brief_preview_v2(
        request_subject="GMV 分析",
        delivery=_delivery(),
        console_view=view,
    )

    assert brief.confirmed_facts == view.confirmed_facts
    assert brief.candidate_hypotheses == view.candidate_hypotheses
    assert brief.unknowns == view.unknowns
    assert brief.recommended_checks == view.recommended_checks


def test_partial_and_unreconciled_are_exposed_as_limitations() -> None:
    brief = build_executive_decision_brief_preview_v2(
        request_subject="GMV 分析",
        delivery=_delivery(),
        console_view=_view(),
    )

    codes = {
        item.code
        for item in brief.limitations
    }

    assert (
        ExecutiveLimitationCodeV2.EVIDENCE_NOT_FULLY_SUFFICIENT
        in codes
    )
    assert (
        ExecutiveLimitationCodeV2.CONTRIBUTION_NOT_RECONCILED
        in codes
    )
    assert brief.evidence_sufficiency == EvidenceSufficiencyStatusV2.PARTIAL


def test_runtime_human_controls_are_exposed_as_limitations() -> None:
    brief = build_executive_decision_brief_preview_v2(
        request_subject="GMV 分析",
        delivery=_delivery(),
        console_view=_view(),
    )

    codes = {
        item.code
        for item in brief.limitations
    }

    assert (
        ExecutiveLimitationCodeV2.CLARIFICATION_REQUIRED
        in codes
    )
    assert (
        ExecutiveLimitationCodeV2.INVESTIGATION_CAN_CONTINUE
        in codes
    )


TESTS = (
    test_subject_and_scope_are_preserved,
    test_kpi_summary_is_inherited,
    test_key_findings_preserve_insight_statements_and_evidence,
    test_contribution_highlights_follow_existing_ranking,
    test_epistemic_sections_are_preserved,
    test_partial_and_unreconciled_are_exposed_as_limitations,
    test_runtime_human_controls_are_exposed_as_limitations,
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

    print("Day89 Executive Decision Brief Preview Acceptance Summary")
    print(f"Total: {len(TESTS)}")
    print(f"Passed: {passed}")
    print(f"Failed: {len(failures)}")

    for failure in failures:
        print(f"- {failure}")

    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    run_acceptance()
