from __future__ import annotations

from datetime import date

from app.agents.investigation_contracts_v2 import (
    AnalysisModeV2,
    AnalysisScopeV2,
    EvidenceReferenceV2,
    InsightContractV2,
    SupportedInsightStatementV2,
    ToolContractV2,
    ToolFailureCodeV2,
    ToolIdentityV2,
)
from app.agents.investigation_planner_llm_v2 import (
    plan_next_investigation_step_v2,
)
from app.agents.investigation_planner_v2 import (
    AvailableInvestigationActionV2,
    BoundToolArgumentV2,
    InvestigationStateV2,
    PlannerDecisionTypeV2,
)
from app.llm.deepseek_client import DEEPSEEK_MODEL
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
            start_date=date(2025, 1, 1),
            end_date=date(2025, 12, 31),
        ),
        reference_window=TimeWindowReferenceV2(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
        ),
    )


def _tool(name: str, purpose: str) -> ToolContractV2:
    return ToolContractV2(
        identity=ToolIdentityV2(
            name=name,
            version="dataset_v2",
            purpose=purpose,
        ),
        input_schema_name=f"{name.title().replace('_', '')}InputV2",
        output_schema_name=f"{name.title().replace('_', '')}ResultV2",
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


def _build_state() -> InvestigationStateV2:
    comparison = _comparison()
    insight = InsightContractV2(
        analysis_mode=AnalysisModeV2.INVESTIGATION,
        analysis_scope=AnalysisScopeV2(
            metric_name="gmv",
            analysis_window=comparison.current_window,
            comparison=comparison,
            result_grain="category",
            scope_summary="authorized_scope_only",
        ),
        detected_anomalies=(
            SupportedInsightStatementV2(
                statement="GMV 同比下降已达到当前 Active Policy 的异常阈值。",
                evidence_ids=("ev_anomaly",),
            ),
        ),
        dimension_contributions=(
            SupportedInsightStatementV2(
                statement=(
                    "护肤是当前已释放的最强负向品类贡献，对本次 GMV 变化的贡献率为 -72%。"
                ),
                evidence_ids=("ev_contribution",),
            ),
        ),
        evidence=(
            EvidenceReferenceV2(
                evidence_id="ev_anomaly",
                source="deterministic_anomaly_detector_v2",
                description="受治理的 GMV 同比异常判断证据。",
            ),
            EvidenceReferenceV2(
                evidence_id="ev_contribution",
                source="deterministic_contribution_analysis_v2",
                description=(
                    "受治理的品类贡献证据，显示护肤是当前已释放的最强负向贡献项。"
                ),
            ),
        ),
    )

    product_action = AvailableInvestigationActionV2(
        action_id="drill_product_within_skincare",
        tool_contract=_tool(
            "drill_down_by_product",
            "在已批准 Scope 内按商品进一步分解受治理指标。",
        ),
        arguments=(
            BoundToolArgumentV2(name="category", value="skincare"),
        ),
    )
    region_action = AvailableInvestigationActionV2(
        action_id="drill_region",
        tool_contract=_tool(
            "drill_down_by_region",
            "按地区分解受治理指标。",
        ),
    )

    return InvestigationStateV2(
        insight=insight,
        completed_action_ids=(
            "overall_gmv",
            "channel_contribution",
            "category_contribution",
        ),
        available_actions=(product_action, region_action),
    )


def run_live_probe() -> None:
    expected_action_id = "drill_product_within_skincare"

    print("=" * 80)
    print("Day85 Investigation Planner V2 — DeepSeek 真实观察 Probe")
    print(f"模型：{DEEPSEEK_MODEL}")
    print("当前证据：护肤是已释放的最强负向品类贡献（-72%）。")
    print("可选动作：drill_product_within_skincare, drill_region")
    print("预期规划质量：优先选择 drill_product_within_skincare")
    print("-" * 80)

    try:
        decision = plan_next_investigation_step_v2(state=_build_state())
    except Exception as exc:
        print("观察合同：FAIL")
        print(f"错误：{type(exc).__name__}: {exc}")
        raise SystemExit(1) from exc

    print("观察合同：PASS")
    print(f"决策类型：{decision.decision_type.value}")
    print(f"规划理由：{decision.rationale}")
    print(f"支持证据：{list(decision.supporting_evidence_ids)}")

    selected_action_id = (
        decision.selected_action.action_id
        if decision.selected_action is not None
        else None
    )
    print(f"选择动作：{selected_action_id}")

    quality_pass = (
        decision.decision_type == PlannerDecisionTypeV2.SELECT_TOOL
        and selected_action_id == expected_action_id
        and "ev_contribution" in decision.supporting_evidence_ids
    )

    print(
        "观察规划质量："
        + ("PASS" if quality_pass else "FAIL")
    )
    print("-" * 80)
    print(
        "说明：这是 live model observed evidence，不是 deterministic regression evidence。"
    )

    if not quality_pass:
        raise SystemExit(2)


if __name__ == "__main__":
    run_live_probe()
