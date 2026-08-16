from __future__ import annotations

from datetime import date

from pydantic import ValidationError

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
from app.agents.investigation_loop_v2 import (
    InvestigationBudgetPolicyV2,
    InvestigationLoopStateV2,
    InvestigationReplanResultV2,
    InvestigationSessionPolicyV2,
    InvestigationSessionStateV2,
    InvestigationStopStatusV2,
    InvestigationStopReasonV2,
    LoopDirectiveV2,
    ToolObservationStatusV2,
    ToolObservationV2,
    advance_investigation_loop_v2,
    decide_loop_control_v2,
    replan_after_transition_v2,
    build_investigation_stop_status_v2,
    continue_investigation_session_v2,
)
from app.agents.investigation_planner_v2 import (
    AvailableInvestigationActionV2,
    BoundToolArgumentV2,
    ClarificationRequirementV2,
    InvestigationStateV2,
    PlannerDecisionTypeV2,
    PlannerDecisionV2,
    PlannerProposalV2,
    validate_planner_proposal_v2,
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
            start_date=date(2025, 1, 1),
            end_date=date(2025, 12, 31),
        ),
        reference_window=TimeWindowReferenceV2(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
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
            scope_summary="已授权的 beauty_bi_v2 数据范围",
        ),
        detected_anomalies=(
            SupportedInsightStatementV2(
                statement="GMV 同比变化满足当前 ACTIVE anomaly policy。",
                evidence_ids=("ev_anomaly",),
            ),
        ),
        evidence=(
            EvidenceReferenceV2(
                evidence_id="ev_anomaly",
                source="deterministic_anomaly_detector_v2",
            ),
        ),
    )


def _insight_with_category_evidence() -> InsightContractV2:
    base = _insight()
    return base.model_copy(
        update={
            "dimension_contributions": (
                SupportedInsightStatementV2(
                    statement="护肤是当前最强负向品类贡献项。",
                    evidence_ids=("ev_category",),
                ),
            ),
            "evidence": (
                *base.evidence,
                EvidenceReferenceV2(
                    evidence_id="ev_category",
                    source="contribution_analysis_v2",
                    description="护肤贡献率 -72%。",
                ),
            ),
        }
    )


def _tool(name: str) -> ToolContractV2:
    return ToolContractV2(
        identity=ToolIdentityV2(
            name=name,
            version="dataset_v2",
            purpose="执行一次受治理、受边界约束的调查动作。",
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


def _action(action_id: str) -> AvailableInvestigationActionV2:
    return AvailableInvestigationActionV2(
        action_id=action_id,
        tool_contract=_tool(action_id),
        arguments=(
            BoundToolArgumentV2(
                name="metric_name",
                value="gmv",
            ),
        ),
    )


def _state(
    *,
    steps_used: int = 0,
    max_steps: int = 3,
    max_retries: int = 1,
    actions: tuple[str, ...] = (
        "drill_category",
        "drill_region",
        "drill_channel",
    ),
    clarification: bool = False,
    history: tuple[ToolObservationV2, ...] = (),
) -> InvestigationLoopStateV2:
    planner_state = InvestigationStateV2(
        insight=_insight(),
        available_actions=tuple(_action(item) for item in actions),
        clarification_requirement=(
            ClarificationRequirementV2(
                source="semantic_decision_v2",
                reason="指标歧义仍未解决",
            )
            if clarification
            else None
        ),
    )
    return InvestigationLoopStateV2(
        planner_state=planner_state,
        budget_policy=InvestigationBudgetPolicyV2(
            max_investigation_steps=max_steps,
            max_retries_per_action=max_retries,
        ),
        investigation_steps_used=steps_used,
        observation_history=history,
    )


def _failure(
    action_id: str,
    code: ToolFailureCodeV2,
    *,
    attempt_number: int = 1,
    retryable: bool | None = None,
) -> ToolObservationV2:
    effective_retryable = (
        code == ToolFailureCodeV2.TIMEOUT
        if retryable is None
        else retryable
    )
    return ToolObservationV2(
        action_id=action_id,
        attempt_number=attempt_number,
        status=ToolObservationStatusV2.FAILURE,
        failure_code=code,
        retryable=effective_retryable,
        summary=f"{action_id} 执行失败，failure_code={code.value}。",
    )


def _first_timeout(action_id: str = "drill_category") -> ToolObservationV2:
    return _failure(
        action_id,
        ToolFailureCodeV2.TIMEOUT,
        attempt_number=1,
    )


# ---------------------------------------------------------------------------
# Step A regression：保留原有 Retry / Recovery / Stop 基础边界
# ---------------------------------------------------------------------------


def test_timeout_retries_when_retry_budget_remains() -> None:
    decision = decide_loop_control_v2(
        state=_state(max_retries=1),
        observation=_first_timeout(),
    )
    assert decision.directive == LoopDirectiveV2.RETRY
    assert decision.action_id == "drill_category"
    assert decision.next_investigation_steps_used == 1


def test_second_timeout_does_not_exceed_retry_budget() -> None:
    history = (_first_timeout(),)
    decision = decide_loop_control_v2(
        state=_state(
            steps_used=1,
            max_retries=1,
            history=history,
        ),
        observation=_failure(
            "drill_category",
            ToolFailureCodeV2.TIMEOUT,
            attempt_number=2,
        ),
    )
    assert decision.directive == LoopDirectiveV2.RECOVER
    assert decision.next_investigation_steps_used == 1


def test_unauthorized_is_not_retried() -> None:
    decision = decide_loop_control_v2(
        state=_state(),
        observation=_failure(
            "drill_category",
            ToolFailureCodeV2.UNAUTHORIZED,
        ),
    )
    assert decision.directive == LoopDirectiveV2.RECOVER


def test_unsupported_is_not_retried() -> None:
    decision = decide_loop_control_v2(
        state=_state(),
        observation=_failure(
            "drill_category",
            ToolFailureCodeV2.UNSUPPORTED,
        ),
    )
    assert decision.directive == LoopDirectiveV2.RECOVER


def test_no_data_is_valid_observation_and_replans() -> None:
    decision = decide_loop_control_v2(
        state=_state(),
        observation=ToolObservationV2(
            action_id="drill_region",
            attempt_number=1,
            status=ToolObservationStatusV2.NO_DATA,
            failure_code=ToolFailureCodeV2.NO_DATA,
            summary="当前绑定的时间窗口与 Scope 下没有数据。",
        ),
    )
    assert decision.directive == LoopDirectiveV2.REPLAN


def test_no_data_cannot_invent_zero_evidence() -> None:
    try:
        ToolObservationV2(
            action_id="drill_region",
            attempt_number=1,
            status=ToolObservationStatusV2.NO_DATA,
            failure_code=ToolFailureCodeV2.NO_DATA,
            produced_evidence_ids=("ev_fake_zero",),
            summary="当前查询没有数据。",
        )
    except ValidationError:
        return
    raise AssertionError("NO_DATA 不能凭空生成 evidence。")


def test_successful_evidence_replans_when_more_work_is_allowed() -> None:
    decision = decide_loop_control_v2(
        state=_state(),
        observation=ToolObservationV2(
            action_id="drill_channel",
            attempt_number=1,
            status=ToolObservationStatusV2.EVIDENCE,
            produced_evidence_ids=("ev_channel",),
            summary="渠道贡献证据已通过受控边界释放。",
        ),
    )
    assert decision.directive == LoopDirectiveV2.REPLAN


def test_evidence_sufficient_early_stops() -> None:
    decision = decide_loop_control_v2(
        state=_state(),
        observation=ToolObservationV2(
            action_id="drill_channel",
            attempt_number=1,
            status=ToolObservationStatusV2.EVIDENCE,
            produced_evidence_ids=("ev_channel",),
            summary="当前证据已经足以支持一个有边界的结论。",
        ),
        evidence_sufficient=True,
    )
    assert decision.directive == LoopDirectiveV2.STOP
    assert (
        decision.stop_reason
        == InvestigationStopReasonV2.EVIDENCE_SUFFICIENT
    )


def test_investigation_budget_stops_new_direction() -> None:
    decision = decide_loop_control_v2(
        state=_state(steps_used=2, max_steps=3),
        observation=ToolObservationV2(
            action_id="drill_region",
            attempt_number=1,
            status=ToolObservationStatusV2.NO_DATA,
            failure_code=ToolFailureCodeV2.NO_DATA,
            summary="当前查询没有数据。",
        ),
    )
    assert decision.directive == LoopDirectiveV2.STOP
    assert (
        decision.stop_reason
        == InvestigationStopReasonV2.INVESTIGATION_BUDGET_EXHAUSTED
    )


def test_retry_does_not_consume_another_logical_investigation_step() -> None:
    history = (_first_timeout(),)
    decision = decide_loop_control_v2(
        state=_state(
            steps_used=1,
            max_steps=3,
            max_retries=2,
            history=history,
        ),
        observation=_failure(
            "drill_category",
            ToolFailureCodeV2.TIMEOUT,
            attempt_number=2,
        ),
    )
    assert decision.directive == LoopDirectiveV2.RETRY
    assert decision.next_investigation_steps_used == 1


def test_no_alternative_after_no_data_stops() -> None:
    decision = decide_loop_control_v2(
        state=_state(actions=("drill_region",)),
        observation=ToolObservationV2(
            action_id="drill_region",
            attempt_number=1,
            status=ToolObservationStatusV2.NO_DATA,
            failure_code=ToolFailureCodeV2.NO_DATA,
            summary="当前查询没有数据。",
        ),
    )
    assert decision.directive == LoopDirectiveV2.STOP
    assert (
        decision.stop_reason
        == InvestigationStopReasonV2.NO_LEGAL_ACTION
    )


def test_retry_exhausted_without_alternative_stops() -> None:
    history = (_first_timeout(),)
    decision = decide_loop_control_v2(
        state=_state(
            steps_used=1,
            max_steps=3,
            max_retries=1,
            actions=("drill_category",),
            history=history,
        ),
        observation=_failure(
            "drill_category",
            ToolFailureCodeV2.TIMEOUT,
            attempt_number=2,
        ),
    )
    assert decision.directive == LoopDirectiveV2.STOP
    assert (
        decision.stop_reason
        == InvestigationStopReasonV2.RETRY_BUDGET_EXHAUSTED
    )


def test_non_retryable_failure_without_alternative_stops() -> None:
    decision = decide_loop_control_v2(
        state=_state(actions=("drill_category",)),
        observation=_failure(
            "drill_category",
            ToolFailureCodeV2.UNSUPPORTED,
        ),
    )
    assert decision.directive == LoopDirectiveV2.STOP
    assert (
        decision.stop_reason
        == InvestigationStopReasonV2.NON_RETRYABLE_FAILURE
    )


def test_observation_action_must_be_currently_available() -> None:
    try:
        decide_loop_control_v2(
            state=_state(actions=("drill_region",)),
            observation=_failure(
                "drill_product",
                ToolFailureCodeV2.TIMEOUT,
            ),
        )
    except ValueError:
        return
    raise AssertionError("未知的已执行 action 必须 fail-closed。")


def test_clarification_blocks_execution() -> None:
    try:
        decide_loop_control_v2(
            state=_state(clarification=True),
            observation=_failure(
                "drill_region",
                ToolFailureCodeV2.TIMEOUT,
            ),
        )
    except ValueError:
        return
    raise AssertionError(
        "未解决的 clarification 必须阻止 Tool 执行。"
    )


def test_new_action_cannot_run_after_budget_is_already_exhausted() -> None:
    try:
        decide_loop_control_v2(
            state=_state(steps_used=3, max_steps=3),
            observation=ToolObservationV2(
                action_id="drill_region",
                attempt_number=1,
                status=ToolObservationStatusV2.NO_DATA,
                failure_code=ToolFailureCodeV2.NO_DATA,
                summary="该动作在预算耗尽后不应该被执行。",
            ),
        )
    except ValueError:
        return
    raise AssertionError(
        "Investigation Budget 耗尽后，新调查动作必须 fail-closed。"
    )


# ---------------------------------------------------------------------------
# Step B：Observation 写回 State + action refresh + 再次交给 Planner
# ---------------------------------------------------------------------------


def test_transition_appends_observation_history() -> None:
    observation = ToolObservationV2(
        action_id="drill_region",
        attempt_number=1,
        status=ToolObservationStatusV2.NO_DATA,
        failure_code=ToolFailureCodeV2.NO_DATA,
        summary="当前查询没有数据。",
    )
    transition = advance_investigation_loop_v2(
        state=_state(),
        observation=observation,
    )
    assert transition.next_state.observation_history == (observation,)


def test_retry_keeps_current_action_available_and_not_completed() -> None:
    transition = advance_investigation_loop_v2(
        state=_state(max_retries=1),
        observation=_first_timeout(),
    )
    next_planner = transition.next_state.planner_state

    assert transition.control_decision.directive == LoopDirectiveV2.RETRY
    assert "drill_category" not in next_planner.completed_action_ids
    assert "drill_category" in {
        item.action_id
        for item in next_planner.available_actions
    }


def test_completed_action_moves_to_completed_and_is_removed() -> None:
    observation = ToolObservationV2(
        action_id="drill_region",
        attempt_number=1,
        status=ToolObservationStatusV2.NO_DATA,
        failure_code=ToolFailureCodeV2.NO_DATA,
        summary="当前查询没有数据。",
    )
    transition = advance_investigation_loop_v2(
        state=_state(),
        observation=observation,
    )
    next_planner = transition.next_state.planner_state

    assert "drill_region" in next_planner.completed_action_ids
    assert "drill_region" not in {
        item.action_id
        for item in next_planner.available_actions
    }


def test_new_evidence_can_unlock_new_action_before_stop_decision() -> None:
    state = _state(actions=("drill_category",))
    observation = ToolObservationV2(
        action_id="drill_category",
        attempt_number=1,
        status=ToolObservationStatusV2.EVIDENCE,
        produced_evidence_ids=("ev_category",),
        summary="护肤是当前最强负向品类贡献项。",
    )
    new_action = _action("drill_product_within_skincare")

    transition = advance_investigation_loop_v2(
        state=state,
        observation=observation,
        refreshed_insight=_insight_with_category_evidence(),
        refreshed_available_actions=(new_action,),
    )

    assert transition.control_decision.directive == LoopDirectiveV2.REPLAN
    assert (
        transition.next_state.planner_state.available_actions
        == (new_action,)
    )


def test_new_evidence_must_exist_in_refreshed_insight() -> None:
    state = _state(actions=("drill_category",))
    observation = ToolObservationV2(
        action_id="drill_category",
        attempt_number=1,
        status=ToolObservationStatusV2.EVIDENCE,
        produced_evidence_ids=("ev_category",),
        summary="产生了新的品类贡献证据。",
    )

    try:
        advance_investigation_loop_v2(
            state=state,
            observation=observation,
            refreshed_insight=_insight(),
            refreshed_available_actions=(
                _action("drill_product_within_skincare"),
            ),
        )
    except ValueError:
        return

    raise AssertionError(
        "Observation 声称产生的 evidence 必须真实进入 refreshed Insight。"
    )


def test_refreshed_state_cannot_silently_change_analysis_scope() -> None:
    current = _insight()
    changed_scope = current.analysis_scope.model_copy(
        update={"metric_name": "order_count"}
    )
    changed_insight = current.model_copy(
        update={"analysis_scope": changed_scope}
    )

    observation = ToolObservationV2(
        action_id="drill_region",
        attempt_number=1,
        status=ToolObservationStatusV2.NO_DATA,
        failure_code=ToolFailureCodeV2.NO_DATA,
        summary="当前查询没有数据。",
    )

    try:
        advance_investigation_loop_v2(
            state=_state(),
            observation=observation,
            refreshed_insight=changed_insight,
        )
    except ValueError:
        return

    raise AssertionError(
        "Loop State 更新不能静默改变 metric / analysis scope。"
    )


def test_attempt_number_must_follow_observation_history() -> None:
    history = (_first_timeout(),)
    state = _state(
        steps_used=1,
        max_retries=2,
        history=history,
    )

    try:
        decide_loop_control_v2(
            state=state,
            observation=_failure(
                "drill_category",
                ToolFailureCodeV2.TIMEOUT,
                attempt_number=3,
            ),
        )
    except ValueError:
        return

    raise AssertionError(
        "attempt_number 必须按 Observation history 连续递增。"
    )


def test_refreshed_planner_state_can_select_newly_unlocked_action() -> None:
    state = _state(actions=("drill_category",))
    observation = ToolObservationV2(
        action_id="drill_category",
        attempt_number=1,
        status=ToolObservationStatusV2.EVIDENCE,
        produced_evidence_ids=("ev_category",),
        summary="护肤是当前最强负向品类贡献项。",
    )
    new_action = _action("drill_product_within_skincare")

    transition = advance_investigation_loop_v2(
        state=state,
        observation=observation,
        refreshed_insight=_insight_with_category_evidence(),
        refreshed_available_actions=(new_action,),
    )

    proposal = PlannerProposalV2(
        decision_type=PlannerDecisionTypeV2.SELECT_TOOL,
        action_id="drill_product_within_skincare",
        clarification_prompt=None,
        rationale="护肤是当前最强负向贡献项，应继续在护肤范围内查看商品。",
        supporting_evidence_ids=("ev_category",),
    )

    decision = validate_planner_proposal_v2(
        state=transition.next_state.planner_state,
        proposal=proposal,
    )

    assert decision.selected_action == new_action


def test_non_retryable_timeout_does_not_retry_even_with_budget() -> None:
    decision = decide_loop_control_v2(
        state=_state(
            max_retries=2,
            actions=("drill_category", "drill_region"),
        ),
        observation=_failure(
            "drill_category",
            ToolFailureCodeV2.TIMEOUT,
            retryable=False,
        ),
    )
    assert decision.directive == LoopDirectiveV2.RECOVER


def test_non_retryable_timeout_without_alternative_stops_as_non_retryable() -> None:
    decision = decide_loop_control_v2(
        state=_state(
            max_retries=2,
            actions=("drill_category",),
        ),
        observation=_failure(
            "drill_category",
            ToolFailureCodeV2.TIMEOUT,
            retryable=False,
        ),
    )
    assert decision.directive == LoopDirectiveV2.STOP
    assert (
        decision.stop_reason
        == InvestigationStopReasonV2.NON_RETRYABLE_FAILURE
    )


# ---------------------------------------------------------------------------
# Step C：新 State → 再次交给 Planner → 新 Decision
# ---------------------------------------------------------------------------


def _planner_select(
    *,
    expected_action_id: str,
    evidence_ids: tuple[str, ...],
    rationale: str,
):
    """
    构造一个测试用 deterministic Planner。

    它不模拟 LLM，而是复用 Day85 的 deterministic validator，
    用来证明 Day86 确实把“刷新后的新 State”重新送进 Planner。
    """

    def planner(state: InvestigationStateV2) -> PlannerDecisionV2:
        proposal = PlannerProposalV2(
            decision_type=PlannerDecisionTypeV2.SELECT_TOOL,
            action_id=expected_action_id,
            clarification_prompt=None,
            rationale=rationale,
            supporting_evidence_ids=evidence_ids,
        )
        return validate_planner_proposal_v2(
            state=state,
            proposal=proposal,
        )

    return planner


def test_replan_uses_refreshed_state_and_new_evidence() -> None:
    state = _state(actions=("drill_category",))
    observation = ToolObservationV2(
        action_id="drill_category",
        attempt_number=1,
        status=ToolObservationStatusV2.EVIDENCE,
        produced_evidence_ids=("ev_category",),
        summary="护肤是当前最强负向品类贡献项。",
    )
    new_action = _action("drill_product_within_skincare")

    transition = advance_investigation_loop_v2(
        state=state,
        observation=observation,
        refreshed_insight=_insight_with_category_evidence(),
        refreshed_available_actions=(new_action,),
    )

    result = replan_after_transition_v2(
        transition=transition,
        planner=_planner_select(
            expected_action_id="drill_product_within_skincare",
            evidence_ids=("ev_category",),
            rationale="新证据显示护肤贡献最强，因此继续在护肤范围内查看商品。",
        ),
    )

    assert isinstance(result, InvestigationReplanResultV2)
    assert (
        result.planner_decision.selected_action.action_id
        == "drill_product_within_skincare"
    )
    assert (
        result.planner_decision.supporting_evidence_ids
        == ("ev_category",)
    )


def test_recover_can_choose_alternative_action() -> None:
    state = _state(
        actions=("drill_category", "drill_region")
    )
    observation = _failure(
        "drill_category",
        ToolFailureCodeV2.UNSUPPORTED,
    )

    transition = advance_investigation_loop_v2(
        state=state,
        observation=observation,
        refreshed_available_actions=(
            _action("drill_region"),
        ),
    )

    assert (
        transition.control_decision.directive
        == LoopDirectiveV2.RECOVER
    )

    result = replan_after_transition_v2(
        transition=transition,
        planner=_planner_select(
            expected_action_id="drill_region",
            evidence_ids=("ev_anomaly",),
            rationale="品类路径当前不支持，改为从仍然合法的区域方向继续调查。",
        ),
    )

    assert (
        result.planner_decision.selected_action.action_id
        == "drill_region"
    )


def test_retry_transition_must_not_call_planner() -> None:
    transition = advance_investigation_loop_v2(
        state=_state(max_retries=1),
        observation=_first_timeout(),
    )
    assert transition.control_decision.directive == LoopDirectiveV2.RETRY

    called = False

    def planner(_: InvestigationStateV2) -> PlannerDecisionV2:
        nonlocal called
        called = True
        raise AssertionError("RETRY 不应该进入 Planner。")

    try:
        replan_after_transition_v2(
            transition=transition,
            planner=planner,
        )
    except ValueError:
        assert called is False
        return

    raise AssertionError("RETRY transition 必须阻止 Planner 调用。")


def test_stop_transition_must_not_call_planner() -> None:
    transition = advance_investigation_loop_v2(
        state=_state(
            steps_used=2,
            max_steps=3,
            actions=("drill_region",),
        ),
        observation=ToolObservationV2(
            action_id="drill_region",
            attempt_number=1,
            status=ToolObservationStatusV2.NO_DATA,
            failure_code=ToolFailureCodeV2.NO_DATA,
            summary="当前查询没有数据。",
        ),
    )
    assert transition.control_decision.directive == LoopDirectiveV2.STOP

    called = False

    def planner(_: InvestigationStateV2) -> PlannerDecisionV2:
        nonlocal called
        called = True
        raise AssertionError("STOP 后不应该再次调用 Planner。")

    try:
        replan_after_transition_v2(
            transition=transition,
            planner=planner,
        )
    except ValueError:
        assert called is False
        return

    raise AssertionError("STOP transition 必须阻止 Planner 调用。")


def test_replan_rejects_action_outside_new_available_actions() -> None:
    state = _state(actions=("drill_category",))
    observation = ToolObservationV2(
        action_id="drill_category",
        attempt_number=1,
        status=ToolObservationStatusV2.EVIDENCE,
        produced_evidence_ids=("ev_category",),
        summary="护肤是当前最强负向品类贡献项。",
    )

    transition = advance_investigation_loop_v2(
        state=state,
        observation=observation,
        refreshed_insight=_insight_with_category_evidence(),
        refreshed_available_actions=(
            _action("drill_product_within_skincare"),
        ),
    )

    illegal_action = _action("drill_customer_private_data")

    def bad_planner(_: InvestigationStateV2) -> PlannerDecisionV2:
        return PlannerDecisionV2(
            decision_type=PlannerDecisionTypeV2.SELECT_TOOL,
            selected_action=illegal_action,
            rationale="错误地选择了不在新 State 中的动作。",
            supporting_evidence_ids=("ev_category",),
        )

    try:
        replan_after_transition_v2(
            transition=transition,
            planner=bad_planner,
        )
    except ValueError:
        return

    raise AssertionError(
        "Loop 必须拒绝不属于新 available_actions 的 Planner Decision。"
    )


def test_replan_rejects_tampered_bound_action() -> None:
    state = _state(actions=("drill_category",))
    observation = ToolObservationV2(
        action_id="drill_category",
        attempt_number=1,
        status=ToolObservationStatusV2.EVIDENCE,
        produced_evidence_ids=("ev_category",),
        summary="护肤是当前最强负向品类贡献项。",
    )
    trusted_action = _action("drill_product_within_skincare")

    transition = advance_investigation_loop_v2(
        state=state,
        observation=observation,
        refreshed_insight=_insight_with_category_evidence(),
        refreshed_available_actions=(trusted_action,),
    )

    tampered_action = trusted_action.model_copy(
        update={
            "arguments": (
                BoundToolArgumentV2(
                    name="metric_name",
                    value="order_count",
                ),
            )
        }
    )

    def bad_planner(_: InvestigationStateV2) -> PlannerDecisionV2:
        return PlannerDecisionV2(
            decision_type=PlannerDecisionTypeV2.SELECT_TOOL,
            selected_action=tampered_action,
            rationale="错误地修改了系统预绑定参数。",
            supporting_evidence_ids=("ev_category",),
        )

    try:
        replan_after_transition_v2(
            transition=transition,
            planner=bad_planner,
        )
    except ValueError:
        return

    raise AssertionError(
        "Loop 必须拒绝 Planner 修改可信 Tool 参数。"
    )


# ---------------------------------------------------------------------------
# Step F：Round Budget / Session Budget / Continuation
# ---------------------------------------------------------------------------


def _session(
    *,
    loop_state: InvestigationLoopStateV2,
    max_rounds: int = 3,
    max_total_steps: int = 8,
    round_number: int = 1,
    completed_round_steps_used: int = 0,
) -> InvestigationSessionStateV2:
    return InvestigationSessionStateV2(
        loop_state=loop_state,
        session_policy=InvestigationSessionPolicyV2(
            max_rounds=max_rounds,
            max_total_investigation_steps=max_total_steps,
        ),
        round_number=round_number,
        completed_round_steps_used=completed_round_steps_used,
    )


def test_budget_stop_reports_remaining_actions_and_can_continue() -> None:
    state = _state(
        steps_used=2,
        max_steps=3,
        actions=("drill_region", "drill_product"),
    )
    observation = ToolObservationV2(
        action_id="drill_region",
        attempt_number=1,
        status=ToolObservationStatusV2.NO_DATA,
        failure_code=ToolFailureCodeV2.NO_DATA,
        retryable=False,
        summary="区域方向没有数据。",
    )
    transition = advance_investigation_loop_v2(
        state=state,
        observation=observation,
        refreshed_available_actions=(
            _action("drill_product"),
            _action("drill_membership"),
        ),
    )

    session = _session(loop_state=state)
    status = build_investigation_stop_status_v2(
        session=session,
        transition=transition,
        evidence_sufficient=False,
    )

    assert status.can_continue is True
    assert status.uninvestigated_action_ids == (
        "drill_product",
        "drill_membership",
    )
    assert status.total_steps_used == 3


def test_evidence_sufficient_stop_cannot_continue_same_session() -> None:
    state = _state(
        steps_used=1,
        max_steps=3,
        actions=("drill_channel", "drill_region"),
    )

    observation = ToolObservationV2(
        action_id="drill_channel",
        attempt_number=1,
        status=ToolObservationStatusV2.EVIDENCE,
        produced_evidence_ids=("ev_channel",),
        summary="已获得足够渠道证据。",
    )

    base_insight = _insight()
    refreshed_insight = base_insight.model_copy(
        update={
            "evidence": (
                *base_insight.evidence,
                EvidenceReferenceV2(
                    evidence_id="ev_channel",
                    source="day86_step_f_test",
                    description="渠道证据。",
                ),
            )
        }
    )

    transition = advance_investigation_loop_v2(
        state=state,
        observation=observation,
        evidence_sufficient=True,
        refreshed_insight=refreshed_insight,
        refreshed_available_actions=(
            _action("drill_region"),
        ),
    )

    session = _session(loop_state=state)
    status = build_investigation_stop_status_v2(
        session=session,
        transition=transition,
        evidence_sufficient=True,
    )

    assert status.can_continue is False
    assert status.evidence_sufficient is True


def test_session_total_budget_blocks_continuation() -> None:
    state = _state(
        steps_used=2,
        max_steps=3,
        actions=("drill_region", "drill_product"),
    )
    observation = ToolObservationV2(
        action_id="drill_region",
        attempt_number=1,
        status=ToolObservationStatusV2.NO_DATA,
        failure_code=ToolFailureCodeV2.NO_DATA,
        retryable=False,
        summary="区域方向没有数据。",
    )
    transition = advance_investigation_loop_v2(
        state=state,
        observation=observation,
        refreshed_available_actions=(
            _action("drill_product"),
        ),
    )

    session = _session(
        loop_state=state,
        round_number=2,
        completed_round_steps_used=3,
        max_rounds=3,
        max_total_steps=6,
    )
    status = build_investigation_stop_status_v2(
        session=session,
        transition=transition,
        evidence_sufficient=False,
    )

    assert status.total_steps_used == 6
    assert status.can_continue is False


def test_session_round_budget_blocks_continuation() -> None:
    state = _state(
        steps_used=2,
        max_steps=3,
        actions=("drill_region", "drill_product"),
    )
    observation = ToolObservationV2(
        action_id="drill_region",
        attempt_number=1,
        status=ToolObservationStatusV2.NO_DATA,
        failure_code=ToolFailureCodeV2.NO_DATA,
        retryable=False,
        summary="区域方向没有数据。",
    )
    transition = advance_investigation_loop_v2(
        state=state,
        observation=observation,
        refreshed_available_actions=(
            _action("drill_product"),
        ),
    )

    session = _session(
        loop_state=state,
        round_number=3,
        completed_round_steps_used=3,
        max_rounds=3,
        max_total_steps=10,
    )
    status = build_investigation_stop_status_v2(
        session=session,
        transition=transition,
        evidence_sufficient=False,
    )

    assert status.can_continue is False


def test_user_continuation_preserves_history_and_resets_round_steps() -> None:
    state = _state(
        steps_used=2,
        max_steps=3,
        actions=("drill_region", "drill_product"),
    )
    observation = ToolObservationV2(
        action_id="drill_region",
        attempt_number=1,
        status=ToolObservationStatusV2.NO_DATA,
        failure_code=ToolFailureCodeV2.NO_DATA,
        retryable=False,
        summary="区域方向没有数据。",
    )
    transition = advance_investigation_loop_v2(
        state=state,
        observation=observation,
        refreshed_available_actions=(
            _action("drill_product"),
            _action("drill_membership"),
        ),
    )

    session = _session(loop_state=state)
    status = build_investigation_stop_status_v2(
        session=session,
        transition=transition,
        evidence_sufficient=False,
    )
    next_session = continue_investigation_session_v2(
        session=session,
        stop_status=status,
        transition=transition,
        user_requested_continue=True,
    )

    assert next_session.round_number == 2
    assert next_session.completed_round_steps_used == 3
    assert next_session.loop_state.investigation_steps_used == 0
    assert (
        next_session.loop_state.observation_history
        == transition.next_state.observation_history
    )
    assert (
        next_session.loop_state.planner_state.completed_action_ids
        == transition.next_state.planner_state.completed_action_ids
    )
    assert tuple(
        action.action_id
        for action in next_session.loop_state.planner_state.available_actions
    ) == (
        "drill_product",
        "drill_membership",
    )


def test_system_cannot_auto_continue_without_user_request() -> None:
    state = _state(
        steps_used=2,
        max_steps=3,
        actions=("drill_region", "drill_product"),
    )
    observation = ToolObservationV2(
        action_id="drill_region",
        attempt_number=1,
        status=ToolObservationStatusV2.NO_DATA,
        failure_code=ToolFailureCodeV2.NO_DATA,
        retryable=False,
        summary="区域方向没有数据。",
    )
    transition = advance_investigation_loop_v2(
        state=state,
        observation=observation,
        refreshed_available_actions=(
            _action("drill_product"),
        ),
    )

    session = _session(loop_state=state)
    status = build_investigation_stop_status_v2(
        session=session,
        transition=transition,
        evidence_sufficient=False,
    )

    try:
        continue_investigation_session_v2(
            session=session,
            stop_status=status,
            transition=transition,
            user_requested_continue=False,
        )
    except ValueError:
        return

    raise AssertionError(
        "系统不能在没有用户明确 continuation 请求时自动续轮。"
    )


def test_no_legal_action_stop_reports_insufficient_path_without_continuation() -> None:
    state = _state(
        steps_used=0,
        max_steps=3,
        actions=("drill_region",),
    )
    observation = ToolObservationV2(
        action_id="drill_region",
        attempt_number=1,
        status=ToolObservationStatusV2.NO_DATA,
        failure_code=ToolFailureCodeV2.NO_DATA,
        retryable=False,
        summary="区域方向没有数据。",
    )
    transition = advance_investigation_loop_v2(
        state=state,
        observation=observation,
        refreshed_available_actions=(),
    )

    session = _session(loop_state=state)
    status = build_investigation_stop_status_v2(
        session=session,
        transition=transition,
        evidence_sufficient=False,
    )

    assert status.can_continue is False
    assert status.uninvestigated_action_ids == ()
    assert "没有剩余合法调查动作" in status.detail


TESTS = [
    # Step A regression
    test_timeout_retries_when_retry_budget_remains,
    test_second_timeout_does_not_exceed_retry_budget,
    test_unauthorized_is_not_retried,
    test_unsupported_is_not_retried,
    test_no_data_is_valid_observation_and_replans,
    test_no_data_cannot_invent_zero_evidence,
    test_successful_evidence_replans_when_more_work_is_allowed,
    test_evidence_sufficient_early_stops,
    test_investigation_budget_stops_new_direction,
    test_retry_does_not_consume_another_logical_investigation_step,
    test_no_alternative_after_no_data_stops,
    test_retry_exhausted_without_alternative_stops,
    test_non_retryable_failure_without_alternative_stops,
    test_observation_action_must_be_currently_available,
    test_clarification_blocks_execution,
    test_new_action_cannot_run_after_budget_is_already_exhausted,
    test_non_retryable_timeout_does_not_retry_even_with_budget,
    test_non_retryable_timeout_without_alternative_stops_as_non_retryable,
    # Step B
    test_transition_appends_observation_history,
    test_retry_keeps_current_action_available_and_not_completed,
    test_completed_action_moves_to_completed_and_is_removed,
    test_new_evidence_can_unlock_new_action_before_stop_decision,
    test_new_evidence_must_exist_in_refreshed_insight,
    test_refreshed_state_cannot_silently_change_analysis_scope,
    test_attempt_number_must_follow_observation_history,
    test_refreshed_planner_state_can_select_newly_unlocked_action,
    # Step C
    test_replan_uses_refreshed_state_and_new_evidence,
    test_recover_can_choose_alternative_action,
    test_retry_transition_must_not_call_planner,
    test_stop_transition_must_not_call_planner,
    test_replan_rejects_action_outside_new_available_actions,
    test_replan_rejects_tampered_bound_action,
    # Step F
    test_budget_stop_reports_remaining_actions_and_can_continue,
    test_evidence_sufficient_stop_cannot_continue_same_session,
    test_session_total_budget_blocks_continuation,
    test_session_round_budget_blocks_continuation,
    test_user_continuation_preserves_history_and_resets_round_steps,
    test_system_cannot_auto_continue_without_user_request,
    test_no_legal_action_stop_reports_insufficient_path_without_continuation,
]


def main() -> None:
    passed = 0
    failures: list[str] = []

    for test in TESTS:
        try:
            test()
            passed += 1
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{test.__name__}: {exc}")

    print("Day86 Investigation Loop V2 Step F Acceptance Summary")
    print(f"Total: {len(TESTS)}")
    print(f"Passed: {passed}")
    print(f"Failed: {len(failures)}")

    for failure in failures:
        print(f"- {failure}")

    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
