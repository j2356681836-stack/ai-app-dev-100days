from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from app.agents.investigation_contracts_v2 import (
    AnalysisModeV2,
    AnalysisScopeV2,
    EvidenceReferenceV2,
    InsightContractV2,
    ToolContractV2,
    ToolFailureCodeV2,
    ToolIdentityV2,
)
from app.agents.investigation_loop_v2 import (
    InvestigationBudgetPolicyV2,
    InvestigationLoopStateV2,
    InvestigationStopReasonV2,
    LoopDirectiveV2,
    ToolObservationStatusV2,
    advance_investigation_loop_v2,
    replan_after_transition_v2,
)
from app.agents.investigation_planner_v2 import (
    AvailableInvestigationActionV2,
    BoundToolArgumentV2,
    InvestigationStateV2,
    PlannerDecisionTypeV2,
    PlannerProposalV2,
    validate_planner_proposal_v2,
)
from app.agents.investigation_tool_executor_v2 import (
    TrustedToolExecutionBindingV2,
    execute_investigation_tool_v2,
)
from app.governance.access_context import (
    AccessContext,
    AccessRole,
    OperationMode,
    SensitiveDataPolicy,
)
from app.governance.audit_sink import verify_audit_log
from app.governance.execution_policy import GovernedExecutionPolicy
from app.governance.governance_runtime import GovernanceRuntimeConfig
from app.governance.governed_planning_envelope_v2 import (
    GovernedPlanningStatusV2,
    build_governed_planning_envelope_v2,
)
from app.governance.governed_query_execution_v2 import (
    execute_governed_query_v2,
)
from app.semantic_layer.query_plan_compiler_v2 import (
    QueryPlanCompileStatusV2,
    compile_governed_query_plan_v2,
)
from app.semantic_layer.query_plan_v2_loader import (
    get_query_plan_v2_by_name,
    load_query_plan_v2_catalog,
)
from app.semantic_layer.time_comparison_contract_v2 import (
    TimeWindowReferenceV2,
)
from app.semantic_layer.time_window_resolver_v2 import (
    resolve_time_window_v2,
)


REFERENCE_DATE = date(2026, 8, 16)
FIXED_TIME = datetime(
    2026,
    8,
    16,
    10,
    30,
    tzinfo=timezone.utc,
)

CHANNEL_ACTION_ID = "drill_channel"
REGION_ACTION_ID = "drill_region"

CHANNEL_PLAN_NAME = "gmv_channel_v2"
REGION_PLAN_NAME = "gmv_region_v2"

CHANNEL_QUESTION = "2025年各渠道GMV是多少？"
REGION_QUESTION = "2025年各区域GMV是多少？"

# 第一条路径故意设置极低 row limit。
# Dataset V2 的渠道结果有多个成员，因此应该被 Governance Boundary 阻断。
FAILURE_POLICY = GovernedExecutionPolicy(
    statement_timeout_ms=30_000,
    max_rows=1,
)

# Recovery 后的替代路径使用正常 Integration row limit。
SUCCESS_POLICY = GovernedExecutionPolicy(
    statement_timeout_ms=30_000,
    max_rows=20,
)

V2_CHANNEL_CODES = frozenset(
    {
        "DOUYIN",
        "JD",
        "OFFICIAL_MALL",
        "TMALL",
        "WECHAT_MINI_PROGRAM",
        "XIAOHONGSHU",
    }
)

V2_REGION_CODES = frozenset(
    {
        "BEIJING",
        "CHONGQING",
        "GUANGDONG_GUANGZHOU",
        "GUANGDONG_SHENZHEN",
        "GUANGXI_GUILIN",
        "HENAN_LUOYANG",
        "HUBEI_WUHAN",
        "JIANGSU_NANJING",
        "LIAONING_SHENYANG",
        "SHAANXI_XIAN",
        "SHANDONG_QINGDAO",
        "SHANGHAI",
        "SICHUAN_CHENGDU",
        "SICHUAN_MIANYANG",
        "ZHEJIANG_HANGZHOU",
        "ZHEJIANG_JINHUA",
    }
)


def _runtime_config(
    audit_log_path: Path,
) -> GovernanceRuntimeConfig:
    return GovernanceRuntimeConfig(
        result_tokenization_secret=(
            "result-tokenization-secret-32-chars"
        ),
        audit_secret="audit-secret-32-characters-long",
        audit_log_path=audit_log_path,
        create_parent_directory=True,
        fsync_enabled=True,
    )


def _catalog_resources():
    catalog = load_query_plan_v2_catalog()

    metrics = frozenset(
        plan.metric
        for plan in catalog.query_plans
    )
    tables = frozenset(
        table
        for plan in catalog.query_plans
        for table in plan.resource_contract.required_tables
    )
    columns = frozenset(
        column
        for plan in catalog.query_plans
        for column in plan.resource_contract.required_columns
    )

    return metrics, tables, columns


def _integration_context() -> AccessContext:
    metrics, tables, columns = _catalog_resources()

    return AccessContext(
        request_id="day86-failure-recovery-postgresql",
        actor_id="day86-failure-recovery-user",
        role=AccessRole.SCOPED_ANALYST,
        dataset_name="beauty_bi_v2",
        target_schema="beauty_bi_v2",
        operation_mode=OperationMode.OBSERVE_ADVISE,
        allowed_metrics=metrics,
        allowed_tables=tables,
        allowed_columns=columns,
        denied_columns=frozenset(),
        allowed_region_codes=V2_REGION_CODES,
        allowed_channel_codes=V2_CHANNEL_CODES,
        sensitive_data_policy=SensitiveDataPolicy(),
        policy_version="day86_failure_recovery_postgresql",
        scope_source="day86_failure_recovery_fixture",
    )


def _ready_pair(
    *,
    context: AccessContext,
    plan_name: str,
    question: str,
):
    """
    继续复用 Phase3 的 Planning + Compilation，
    Planner 不直接接触 SQL。
    """

    plan = get_query_plan_v2_by_name(plan_name)

    assert plan is not None, (
        f"缺少 Query Plan：{plan_name}"
    )

    resolution = resolve_time_window_v2(
        question,
        reference_date=REFERENCE_DATE,
    )

    planning = build_governed_planning_envelope_v2(
        context=context,
        plan=plan,
        time_resolution=resolution,
    )

    assert (
        planning.status
        == GovernedPlanningStatusV2.READY_FOR_COMPILATION
    )
    assert planning.envelope is not None

    compilation = compile_governed_query_plan_v2(
        planning.envelope
    )

    assert (
        compilation.status
        == QueryPlanCompileStatusV2.COMPILED
    )
    assert compilation.contract is not None

    return planning.envelope, compilation.contract


def _tool_contract(
    *,
    name: str,
    purpose: str,
) -> ToolContractV2:
    return ToolContractV2(
        identity=ToolIdentityV2(
            name=name,
            version="dataset_v2",
            purpose=purpose,
        ),
        input_schema_name="GovernedInvestigationInputV2",
        output_schema_name="GovernedFinalizationResult",
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
        executor_binding="execute_governed_query_v2",
    )


def _action(
    *,
    action_id: str,
    plan_name: str,
    result_grain: str,
) -> AvailableInvestigationActionV2:
    return AvailableInvestigationActionV2(
        action_id=action_id,
        tool_contract=_tool_contract(
            name=f"governed_gmv_{result_grain}_query",
            purpose=(
                f"在 Governance Boundary 内查询"
                f"{result_grain} 粒度 GMV。"
            ),
        ),
        arguments=(
            BoundToolArgumentV2(
                name="metric_name",
                value="gmv",
            ),
            BoundToolArgumentV2(
                name="query_plan_name",
                value=plan_name,
            ),
            BoundToolArgumentV2(
                name="result_grain",
                value=result_grain,
            ),
        ),
    )


def _initial_insight() -> InsightContractV2:
    return InsightContractV2(
        analysis_mode=AnalysisModeV2.INVESTIGATION,
        analysis_scope=AnalysisScopeV2(
            metric_name="gmv",
            analysis_window=TimeWindowReferenceV2(
                start_date=date(2025, 1, 1),
                end_date=date(2025, 12, 31),
            ),
            result_grain=None,
            scope_summary="2025年 GMV 调查。",
        ),
        evidence=(
            EvidenceReferenceV2(
                evidence_id="ev_anomaly",
                source="day83_anomaly_detection_v2",
                description=(
                    "上游异常检测已确认 GMV 需要进一步调查。"
                ),
            ),
        ),
    )


def _append_evidence(
    *,
    insight: InsightContractV2,
    evidence: EvidenceReferenceV2,
) -> InsightContractV2:
    return insight.model_copy(
        update={
            "evidence": (
                *insight.evidence,
                evidence,
            )
        }
    )


def _binding(
    *,
    context: AccessContext,
    runtime_config: GovernanceRuntimeConfig,
    action_id: str,
    plan_name: str,
    question: str,
    event_id: str,
    execution_policy: GovernedExecutionPolicy,
) -> TrustedToolExecutionBindingV2:
    envelope, compiled = _ready_pair(
        context=context,
        plan_name=plan_name,
        question=question,
    )

    def governed_executor():
        return execute_governed_query_v2(
            context=context,
            question=question,
            envelope=envelope,
            compiled=compiled,
            runtime_config=runtime_config,
            execution_policy=execution_policy,
            event_id=event_id,
            occurred_at_utc=FIXED_TIME,
            written_at_utc=FIXED_TIME,
        )

    return TrustedToolExecutionBindingV2(
        action_id=action_id,
        executor_binding="execute_governed_query_v2",
        executor=governed_executor,
    )


def test_real_failure_recovers_to_alternative_postgresql_path() -> None:
    """
    Day86 最小 failure → recovery → alternative path：

    1. Planner 先选择渠道；
    2. 渠道查询真实进入 PostgreSQL，但被 max_rows=1 的治理边界阻断；
    3. 失败 Observation 写入 State；
    4. 该动作 non-retryable，因此不 RETRY；
    5. 仍有合法“区域”方向，所以进入 RECOVER；
    6. Planner 基于新 State 改选区域；
    7. 区域查询真实成功并释放 Evidence；
    8. Evidence sufficient → STOP。
    """

    context = _integration_context()

    channel_action = _action(
        action_id=CHANNEL_ACTION_ID,
        plan_name=CHANNEL_PLAN_NAME,
        result_grain="channel",
    )
    region_action = _action(
        action_id=REGION_ACTION_ID,
        plan_name=REGION_PLAN_NAME,
        result_grain="region",
    )

    initial_state = InvestigationLoopStateV2(
        planner_state=InvestigationStateV2(
            insight=_initial_insight(),
            completed_action_ids=(),
            available_actions=(
                channel_action,
                region_action,
            ),
            clarification_requirement=None,
        ),
        budget_policy=InvestigationBudgetPolicyV2(
            max_investigation_steps=2,
            max_retries_per_action=1,
        ),
        investigation_steps_used=0,
        observation_history=(),
    )

    first_proposal = PlannerProposalV2(
        decision_type=PlannerDecisionTypeV2.SELECT_TOOL,
        action_id=CHANNEL_ACTION_ID,
        clarification_prompt=None,
        rationale=(
            "先查看渠道层分布，寻找异常主要集中方向。"
        ),
        supporting_evidence_ids=("ev_anomaly",),
    )

    first_decision = validate_planner_proposal_v2(
        state=initial_state.planner_state,
        proposal=first_proposal,
    )

    with TemporaryDirectory() as tmp:
        audit_path = Path(tmp) / "day86_recovery_audit.jsonl"
        runtime_config = _runtime_config(audit_path)

        bindings = {
            CHANNEL_ACTION_ID: _binding(
                context=context,
                runtime_config=runtime_config,
                action_id=CHANNEL_ACTION_ID,
                plan_name=CHANNEL_PLAN_NAME,
                question=CHANNEL_QUESTION,
                event_id="day86-recovery-channel-blocked",
                execution_policy=FAILURE_POLICY,
            ),
            REGION_ACTION_ID: _binding(
                context=context,
                runtime_config=runtime_config,
                action_id=REGION_ACTION_ID,
                plan_name=REGION_PLAN_NAME,
                question=REGION_QUESTION,
                event_id="day86-recovery-region-success",
                execution_policy=SUCCESS_POLICY,
            ),
        }

        # -------------------------------------------------
        # Step 1：渠道路径真实执行，但被 Governance 阻断
        # -------------------------------------------------
        failed_result = execute_investigation_tool_v2(
            decision=first_decision,
            attempt_number=1,
            bindings=bindings,
        )

        assert (
            failed_result.observation.status
            == ToolObservationStatusV2.FAILURE
        ), (
            "预期渠道路径被 row limit 阻断，但实际状态为："
            f"{failed_result.observation.status.value}"
        )

        assert failed_result.observation.retryable is False, (
            "Governance row limit failure 不应该被机械 Retry。"
        )
        assert failed_result.evidence_reference is None
        assert failed_result.released_rows == ()
        assert failed_result.blocked_reason is not None

        # Failure 不会凭空增加 Evidence；
        # 但系统会刷新剩余合法动作，只保留区域。
        failure_transition = advance_investigation_loop_v2(
            state=initial_state,
            observation=failed_result.observation,
            refreshed_insight=initial_state.planner_state.insight,
            refreshed_available_actions=(
                region_action,
            ),
            evidence_sufficient=False,
        )

        assert (
            failure_transition.control_decision.directive
            == LoopDirectiveV2.RECOVER
        ), (
            "non-retryable failure 且还有合法替代路径时，"
            "必须进入 RECOVER。"
        )

        assert (
            failure_transition.next_state.planner_state.completed_action_ids
            == (CHANNEL_ACTION_ID,)
        )
        assert tuple(
            action.action_id
            for action
            in failure_transition.next_state.planner_state.available_actions
        ) == (REGION_ACTION_ID,)

        # -------------------------------------------------
        # Recovery：Planner 只能从“新 State”的合法剩余路径中选
        # -------------------------------------------------
        def recovery_planner(state: InvestigationStateV2):
            proposal = PlannerProposalV2(
                decision_type=PlannerDecisionTypeV2.SELECT_TOOL,
                action_id=REGION_ACTION_ID,
                clarification_prompt=None,
                rationale=(
                    "渠道路径已经被 Governance Boundary 阻断，"
                    "因此改从仍然合法的区域方向继续调查。"
                ),
                supporting_evidence_ids=("ev_anomaly",),
            )
            return validate_planner_proposal_v2(
                state=state,
                proposal=proposal,
            )

        recovery_decision = replan_after_transition_v2(
            transition=failure_transition,
            planner=recovery_planner,
        ).planner_decision

        assert recovery_decision.selected_action is not None
        assert (
            recovery_decision.selected_action.action_id
            == REGION_ACTION_ID
        )

        # -------------------------------------------------
        # Step 2：替代路径真实 PostgreSQL 成功
        # -------------------------------------------------
        recovered_result = execute_investigation_tool_v2(
            decision=recovery_decision,
            attempt_number=1,
            bindings=bindings,
        )

        assert (
            recovered_result.observation.status
            == ToolObservationStatusV2.EVIDENCE
        )
        assert recovered_result.evidence_reference is not None
        assert recovered_result.released_rows

        for row in recovered_result.released_rows:
            assert set(row) == {
                "region_name",
                "gmv",
            }
            assert "__group_size" not in row

        recovered_insight = _append_evidence(
            insight=(
                failure_transition.next_state.planner_state.insight
            ),
            evidence=recovered_result.evidence_reference,
        )

        final_transition = advance_investigation_loop_v2(
            state=failure_transition.next_state,
            observation=recovered_result.observation,
            refreshed_insight=recovered_insight,
            refreshed_available_actions=(),
            evidence_sufficient=True,
        )

        assert (
            final_transition.control_decision.directive
            == LoopDirectiveV2.STOP
        )
        assert (
            final_transition.control_decision.stop_reason
            == InvestigationStopReasonV2.EVIDENCE_SUFFICIENT
        )

        final_state = final_transition.next_state

        assert final_state.investigation_steps_used == 2
        assert len(final_state.observation_history) == 2
        assert (
            final_state.observation_history[0].status
            == ToolObservationStatusV2.FAILURE
        )
        assert (
            final_state.observation_history[1].status
            == ToolObservationStatusV2.EVIDENCE
        )
        assert final_state.planner_state.completed_action_ids == (
            CHANNEL_ACTION_ID,
            REGION_ACTION_ID,
        )

        # 第一次真实治理阻断 + 第二次真实成功，都应留下 Audit。
        verification = verify_audit_log(audit_path)
        assert verification.success
        assert verification.record_count == 2


TESTS = (
    test_real_failure_recovers_to_alternative_postgresql_path,
)


def run_acceptance() -> None:
    passed = 0
    failed = 0

    print("=" * 80)
    print(
        "Day86 Investigation Loop V2 "
        "Failure Recovery PostgreSQL"
    )
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
    print(
        "Day86 Investigation Loop V2 "
        "Failure Recovery PostgreSQL Summary"
    )
    print(f"Total: {len(TESTS)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    run_acceptance()
