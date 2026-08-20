from __future__ import annotations

import inspect
from datetime import date

import app.delivery.decision_console_view_v2 as console_view_module
from app.agents.evidence_pack_delivery_v2 import (
    MetricDefinitionSnapshotV2,
    assemble_evidence_pack_delivery_v2,
)
from app.agents.evidence_pack_v2 import EvidencePackV2
from app.agents.investigation_contracts_v2 import (
    AnalysisModeV2,
    AnalysisScopeV2,
    InsightContractV2,
    ToolContractV2,
    ToolFailureCodeV2,
    ToolIdentityV2,
)
from app.agents.investigation_planner_v2 import (
    AvailableInvestigationActionV2,
    ClarificationRequirementV2,
    InvestigationStateV2,
    PlannerDecisionTypeV2,
    PlannerDecisionV2,
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


def _insight() -> InsightContractV2:
    comparison = _comparison()
    return InsightContractV2(
        analysis_mode=AnalysisModeV2.INVESTIGATION,
        analysis_scope=AnalysisScopeV2(
            metric_name="gmv",
            analysis_window=comparison.current_window,
            comparison=comparison,
            result_grain="channel",
            scope_summary="authorized_scope_only",
        ),
    )


def _delivery():
    insight = _insight()
    pack = EvidencePackV2(
        pack_id="day89-clarification-pack",
        analysis_scope=insight.analysis_scope,
        insight=insight,
        evidence_records=(),
    )

    return assemble_evidence_pack_delivery_v2(
        evidence_pack=pack,
        metric_definition=MetricDefinitionSnapshotV2(
            metadata_version="v2",
            dataset_name="beauty_bi_v2",
            metric_name="gmv",
            chinese_name="销售额",
            grain="paid_order_items",
            definition="测试用 GMV Definition。",
            formula="SUM(item_paid_amount)",
            filters=(),
            metric_fingerprint="metric-fingerprint",
        ),
    )


def _required_state() -> InvestigationStateV2:
    return InvestigationStateV2(
        insight=_insight(),
        clarification_requirement=ClarificationRequirementV2(
            source="semantic_decision_v2",
            reason="metric ambiguity remains unresolved",
        ),
    )


def _region_action() -> AvailableInvestigationActionV2:
    return AvailableInvestigationActionV2(
        action_id="drill_region",
        tool_contract=ToolContractV2(
            identity=ToolIdentityV2(
                name="drill_down_by_region",
                version="dataset_v2",
                purpose="按地区分解受治理指标。",
            ),
            input_schema_name="DrillDownByRegionInputV2",
            output_schema_name="DrillDownByRegionResultV2",
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
        ),
    )


def _clarify_decision() -> PlannerDecisionV2:
    return PlannerDecisionV2(
        decision_type=PlannerDecisionTypeV2.CLARIFY,
        selected_action=None,
        clarification_prompt="你希望分析成交 GMV 还是下单 GMV？",
        rationale="上游语义决策仍存在指标歧义，必须先澄清。",
        supporting_evidence_ids=(),
    )


def test_required_clarification_is_projected() -> None:
    view = build_decision_console_view_v2(
        delivery=_delivery(),
        clarification_planner_state=_required_state(),
        clarification_planner_decision=_clarify_decision(),
    )

    assert view.clarification is not None
    assert (
        view.clarification.requirement_source
        == "semantic_decision_v2"
    )
    assert (
        view.clarification.requirement_reason
        == "metric ambiguity remains unresolved"
    )
    assert (
        view.clarification.clarification_prompt
        == "你希望分析成交 GMV 还是下单 GMV？"
    )


def test_required_clarification_blocks_tool_execution() -> None:
    view = build_decision_console_view_v2(
        delivery=_delivery(),
        clarification_planner_state=_required_state(),
        clarification_planner_decision=_clarify_decision(),
    )

    assert view.clarification is not None
    assert view.clarification.requires_user_response is True
    assert view.clarification.tool_execution_blocked is True


def test_clarification_cannot_be_invented_without_requirement() -> None:
    state = InvestigationStateV2(
        insight=_insight(),
    )

    try:
        build_decision_console_view_v2(
            delivery=_delivery(),
            clarification_planner_state=state,
            clarification_planner_decision=_clarify_decision(),
        )
    except ValueError:
        return

    raise AssertionError(
        "没有 trusted requirement 时不能投影 CLARIFY。"
    )


def test_requirement_cannot_release_select_tool() -> None:
    select_decision = PlannerDecisionV2(
        decision_type=PlannerDecisionTypeV2.SELECT_TOOL,
        selected_action=_region_action(),
        clarification_prompt=None,
        rationale="尝试在未澄清前执行地区下钻。",
        supporting_evidence_ids=(),
    )

    try:
        build_decision_console_view_v2(
            delivery=_delivery(),
            clarification_planner_state=_required_state(),
            clarification_planner_decision=select_decision,
        )
    except ValueError:
        return

    raise AssertionError(
        "存在 trusted clarification requirement 时，"
        "Decision Console 必须阻止 SELECT_TOOL。"
    )


def test_only_state_without_decision_fails_closed() -> None:
    try:
        build_decision_console_view_v2(
            delivery=_delivery(),
            clarification_planner_state=_required_state(),
        )
    except ValueError:
        return

    raise AssertionError(
        "Runtime Clarification 缺少 planner_decision 必须 fail-closed。"
    )


def test_only_decision_without_state_fails_closed() -> None:
    try:
        build_decision_console_view_v2(
            delivery=_delivery(),
            clarification_planner_decision=_clarify_decision(),
        )
    except ValueError:
        return

    raise AssertionError(
        "Runtime Clarification 缺少 planner_state 必须 fail-closed。"
    )


def test_no_requirement_and_no_clarify_returns_none() -> None:
    state = InvestigationStateV2(
        insight=_insight(),
    )

    # 没有 requirement 时，不向 Console 传 planner decision。
    view = build_decision_console_view_v2(
        delivery=_delivery(),
    )

    assert view.clarification is None
    assert state.clarification_requirement is None


TESTS = (
    test_required_clarification_is_projected,
    test_required_clarification_blocks_tool_execution,
    test_clarification_cannot_be_invented_without_requirement,
    test_requirement_cannot_release_select_tool,
    test_only_state_without_decision_fails_closed,
    test_only_decision_without_state_fails_closed,
    test_no_requirement_and_no_clarify_returns_none,
)


def run_acceptance() -> None:
    print("Day89 Decision Console Runtime Clarification Preflight")
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
    print(
        "Day89 Decision Console Runtime Clarification "
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
