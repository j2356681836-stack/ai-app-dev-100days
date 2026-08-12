from datetime import date

from pydantic import ValidationError

from app.agents.investigation_contracts_v2 import (
    AnalysisModeV2,
    AnalysisScopeV2,
    CandidateExplanationV2,
    EvidenceReferenceV2,
    InsightContractV2,
    RecommendedCheckV2,
    SupportedInsightStatementV2,
    ToolContractV2,
    ToolFailureCodeV2,
    ToolIdentityV2,
)
from app.semantic_layer.time_comparison_contract_v2 import (
    AlignmentModeV2,
    ComparisonTypeV2,
    PeriodModeV2,
    TimeComparisonContractV2,
    TimeWindowReferenceV2,
)


def _window(
    start_date: date,
    end_date: date,
) -> TimeWindowReferenceV2:
    return TimeWindowReferenceV2(
        start_date=start_date,
        end_date=end_date,
    )


def _evidence() -> EvidenceReferenceV2:
    return EvidenceReferenceV2(
        evidence_id="ev-001",
        source="governed_analytics_v2",
        description="Released governed metric result.",
    )


def _fact_scope() -> AnalysisScopeV2:
    return AnalysisScopeV2(
        metric_name="gmv",
        analysis_window=_window(
            date(2026, 7, 1),
            date(2026, 7, 31),
        ),
        result_grain="overall",
    )


def _yoy_comparison() -> TimeComparisonContractV2:
    return TimeComparisonContractV2(
        comparison_type=ComparisonTypeV2.YOY,
        period_mode=PeriodModeV2.COMPLETED_PERIOD,
        alignment_mode=AlignmentModeV2.CALENDAR_ALIGNED,
        current_window=_window(
            date(2026, 7, 1),
            date(2026, 7, 31),
        ),
        reference_window=_window(
            date(2025, 7, 1),
            date(2025, 7, 31),
        ),
    )


def test_fact_mode_passes() -> None:
    contract = InsightContractV2(
        analysis_mode=AnalysisModeV2.FACT,
        analysis_scope=_fact_scope(),
        confirmed_facts=(
            SupportedInsightStatementV2(
                statement="2026年7月GMV为已释放查询结果。",
                evidence_ids=("ev-001",),
            ),
        ),
        evidence=(_evidence(),),
    )

    assert len(contract.confirmed_facts) == 1
    assert not contract.recommended_checks


def test_fact_mode_rejects_recommendation() -> None:
    try:
        InsightContractV2(
            analysis_mode=AnalysisModeV2.FACT,
            analysis_scope=_fact_scope(),
            confirmed_facts=(
                SupportedInsightStatementV2(
                    statement="GMV事实。",
                    evidence_ids=("ev-001",),
                ),
            ),
            recommended_checks=(
                RecommendedCheckV2(
                    check="继续检查渠道贡献。",
                    evidence_ids=("ev-001",),
                ),
            ),
            evidence=(_evidence(),),
        )
    except ValidationError:
        return

    raise AssertionError(
        "FACT mode must reject diagnostic escalation."
    )


def test_comparison_requires_contract() -> None:
    try:
        InsightContractV2(
            analysis_mode=AnalysisModeV2.COMPARISON,
            analysis_scope=_fact_scope(),
            evidence=(_evidence(),),
        )
    except ValidationError:
        return

    raise AssertionError(
        "COMPARISON mode without comparison must fail."
    )


def test_comparison_mode_passes() -> None:
    scope = AnalysisScopeV2(
        metric_name="gmv",
        analysis_window=_window(
            date(2026, 7, 1),
            date(2026, 7, 31),
        ),
        comparison=_yoy_comparison(),
        result_grain="overall",
    )

    contract = InsightContractV2(
        analysis_mode=AnalysisModeV2.COMPARISON,
        analysis_scope=scope,
        confirmed_facts=(
            SupportedInsightStatementV2(
                statement="GMV同比变化已确认。",
                evidence_ids=("ev-001",),
            ),
        ),
        evidence=(_evidence(),),
    )

    assert contract.analysis_scope.comparison is not None


def test_supported_fact_requires_evidence() -> None:
    try:
        SupportedInsightStatementV2(
            statement="没有证据的事实。",
            evidence_ids=(),
        )
    except ValidationError:
        return

    raise AssertionError(
        "Supported fact without evidence_ids must fail."
    )


def test_dangling_evidence_reference_fails() -> None:
    try:
        InsightContractV2(
            analysis_mode=AnalysisModeV2.DIAGNOSTIC,
            analysis_scope=_fact_scope(),
            confirmed_facts=(
                SupportedInsightStatementV2(
                    statement="GMV同比下降。",
                    evidence_ids=("ev-missing",),
                ),
            ),
            evidence=(_evidence(),),
        )
    except ValidationError:
        return

    raise AssertionError(
        "Unknown evidence_id reference must fail."
    )


def test_candidate_explanation_stays_hypothesis() -> None:
    contract = InsightContractV2(
        analysis_mode=AnalysisModeV2.DIAGNOSTIC,
        analysis_scope=_fact_scope(),
        candidate_explanations=(
            CandidateExplanationV2(
                explanation="营销投入变化可能值得进一步检查。",
            ),
        ),
    )

    assert not contract.confirmed_facts
    assert len(contract.candidate_explanations) == 1


def _tool_identity() -> ToolIdentityV2:
    return ToolIdentityV2(
        name="compare_metric",
        version="dataset_v2",
        purpose=(
            "Compare one trusted business metric across "
            "two governed time windows."
        ),
    )


def _tool_contract() -> ToolContractV2:
    return ToolContractV2(
        identity=_tool_identity(),
        input_schema_name="CompareMetricToolInputV2",
        output_schema_name="CompareMetricToolResultV2",
        required_permissions=("metric_access", "data_scope"),
        execution_policy_reference="governed_execution_policy_v2",
        failure_semantics=(
            ToolFailureCodeV2.INVALID_INPUT,
            ToolFailureCodeV2.UNAUTHORIZED,
            ToolFailureCodeV2.UNSUPPORTED,
            ToolFailureCodeV2.TIMEOUT,
            ToolFailureCodeV2.NO_DATA,
            ToolFailureCodeV2.EXECUTION_FAILURE,
        ),
        executor_binding="execute_governed_analytics_v2",
    )


def test_tool_contract_passes() -> None:
    contract = _tool_contract()

    assert contract.identity.name == "compare_metric"
    assert contract.requires_governed_executor
    assert not contract.accepts_raw_sql
    assert not contract.accepts_metric_formula


def test_tool_contract_rejects_raw_sql_boundary() -> None:
    try:
        ToolContractV2(
            **{
                **_tool_contract().model_dump(),
                "accepts_raw_sql": True,
            }
        )
    except ValidationError:
        return

    raise AssertionError(
        "Tool contract accepting raw SQL must fail."
    )


def test_tool_contract_rejects_metric_formula_boundary() -> None:
    try:
        ToolContractV2(
            **{
                **_tool_contract().model_dump(),
                "accepts_metric_formula": True,
            }
        )
    except ValidationError:
        return

    raise AssertionError(
        "Tool contract accepting metric formulas must fail."
    )


def test_tool_contract_requires_governed_executor() -> None:
    try:
        ToolContractV2(
            **{
                **_tool_contract().model_dump(),
                "requires_governed_executor": False,
            }
        )
    except ValidationError:
        return

    raise AssertionError(
        "Ungoverned executor boundary must fail."
    )


def test_tool_contract_requires_failure_semantics() -> None:
    try:
        ToolContractV2(
            **{
                **_tool_contract().model_dump(),
                "failure_semantics": (),
            }
        )
    except ValidationError:
        return

    raise AssertionError(
        "Tool contract without failure semantics must fail."
    )


TESTS = (
    test_fact_mode_passes,
    test_fact_mode_rejects_recommendation,
    test_comparison_requires_contract,
    test_comparison_mode_passes,
    test_supported_fact_requires_evidence,
    test_dangling_evidence_reference_fails,
    test_candidate_explanation_stays_hypothesis,
    test_tool_contract_passes,
    test_tool_contract_rejects_raw_sql_boundary,
    test_tool_contract_rejects_metric_formula_boundary,
    test_tool_contract_requires_governed_executor,
    test_tool_contract_requires_failure_semantics,
)


def run_acceptance() -> None:
    passed = 0
    failed = 0

    print("=" * 80)
    print("Insight Contract V2 Acceptance")
    print(f"Cases: {len(TESTS)}")

    for test in TESTS:
        print("=" * 80)
        print(test.__name__)

        try:
            test()
        except Exception as exc:
            failed += 1
            print("[FAIL]")
            print(f"{type(exc).__name__}: {exc}")
        else:
            passed += 1
            print("[PASS]")

    print("=" * 80)
    print("Insight Contract V2 Acceptance Summary")
    print(f"Total: {len(TESTS)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    run_acceptance()
