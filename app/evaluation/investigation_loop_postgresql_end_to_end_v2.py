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
from app.governance.execution_policy import (
    GovernedExecutionPolicy,
)
from app.governance.governance_runtime import (
    GovernanceRuntimeConfig,
)
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
    0,
    tzinfo=timezone.utc,
)

CHANNEL_ACTION_ID = "drill_channel"
REGION_ACTION_ID = "drill_region"

CHANNEL_PLAN_NAME = "gmv_channel_v2"
REGION_PLAN_NAME = "gmv_region_v2"

CHANNEL_QUESTION = "2025年各渠道GMV是多少？"
REGION_QUESTION = "2025年各区域GMV是多少？"

# 真实 PostgreSQL Integration 使用更宽的 max_rows，
# 以容纳 Dataset V2 的区域结果。这里不修改生产默认策略。
INTEGRATION_EXECUTION_POLICY = GovernedExecutionPolicy(
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
        audit_secret=(
            "audit-secret-32-characters-long"
        ),
        audit_log_path=audit_log_path,
        create_parent_directory=True,
        fsync_enabled=True,
    )


def _catalog_resources():
    """
    直接从 V2 Query Plan Catalog 汇总本次 Integration 允许资源，
    避免手写 table / column allowlist 与真实 Catalog 漂移。
    """

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
        request_id="day86-loop-postgresql-end-to-end",
        actor_id="day86-end-to-end-user",
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
        policy_version="day86_loop_postgresql_end_to_end",
        scope_source="day86_end_to_end_fixture",
    )


def _ready_pair(
    *,
    context: AccessContext,
    plan_name: str,
    question: str,
):
    """
    复用 Phase3 Trust Plane 生成可信 Envelope + Compiled Contract。

    Planner 仍然看不到 SQL，也不能自己构造 Envelope。
    """

    plan = get_query_plan_v2_by_name(plan_name)

    assert plan is not None, (
        f"缺少 Query Plan：{plan_name}"
    )
    assert plan.metric == "gmv"

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
    ), (
        "Governed Planning 未通过："
        f"plan={plan_name}；"
        f"status={planning.status.value}；"
        f"detail={planning.detail}"
    )
    assert planning.envelope is not None

    compilation = compile_governed_query_plan_v2(
        planning.envelope
    )

    assert (
        compilation.status
        == QueryPlanCompileStatusV2.COMPILED
    ), (
        "Query Plan Compilation 未通过："
        f"plan={plan_name}；"
        f"status={compilation.status.value}；"
        f"detail={compilation.detail}"
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
                f"在既有 Governance Boundary 内查询"
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
    """
    Step G 从“一条已经存在的异常 Evidence”开始。

    这不是绕过 Day83，而是把 Day86 验收范围固定在：
    Planner → Tool → Observation → State Update → Re-plan → Stop。
    """

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
                    "上游异常检测已确认当前 GMV 需要进入进一步调查。"
                ),
            ),
        ),
    )


def _append_evidence(
    *,
    insight: InsightContractV2,
    evidence: EvidenceReferenceV2,
) -> InsightContractV2:
    """
    系统侧把 Governed Tool 释放的新 Evidence 写入 Insight。

    不在这里让 LLM 自动生成因果结论。
    """

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
            execution_policy=INTEGRATION_EXECUTION_POLICY,
            event_id=event_id,
            occurred_at_utc=FIXED_TIME,
            written_at_utc=FIXED_TIME,
        )

    return TrustedToolExecutionBindingV2(
        action_id=action_id,
        executor_binding="execute_governed_query_v2",
        executor=governed_executor,
    )


def test_real_postgresql_two_step_investigation_loop() -> None:
    """
    Day86 Step G 端到端闭环：

    初始异常 Evidence
    → Planner 选择渠道
    → 真实 Governed PostgreSQL Tool
    → Observation / Evidence
    → State Update
    → Re-plan 选择区域
    → 真实 Governed PostgreSQL Tool
    → Observation / Evidence
    → Evidence Sufficient
    → STOP

    这里使用 deterministic Planner Proposal，
    目的是验收 Loop 编排，不重复测试 Day85 的 Live LLM。
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
            max_retries_per_action=0,
        ),
        investigation_steps_used=0,
        observation_history=(),
    )

    # 第一步：Planner 在当前合法集合中选择渠道。
    first_proposal = PlannerProposalV2(
        decision_type=PlannerDecisionTypeV2.SELECT_TOOL,
        action_id=CHANNEL_ACTION_ID,
        clarification_prompt=None,
        rationale=(
            "先查看渠道层分布，判断变化是否集中在某一销售渠道。"
        ),
        supporting_evidence_ids=("ev_anomaly",),
    )

    first_decision = validate_planner_proposal_v2(
        state=initial_state.planner_state,
        proposal=first_proposal,
    )

    with TemporaryDirectory() as tmp:
        audit_path = Path(tmp) / "day86_loop_audit.jsonl"
        runtime_config = _runtime_config(audit_path)

        bindings = {
            CHANNEL_ACTION_ID: _binding(
                context=context,
                runtime_config=runtime_config,
                action_id=CHANNEL_ACTION_ID,
                plan_name=CHANNEL_PLAN_NAME,
                question=CHANNEL_QUESTION,
                event_id="day86-loop-drill-channel",
            ),
            REGION_ACTION_ID: _binding(
                context=context,
                runtime_config=runtime_config,
                action_id=REGION_ACTION_ID,
                plan_name=REGION_PLAN_NAME,
                question=REGION_QUESTION,
                event_id="day86-loop-drill-region",
            ),
        }

        # -------------------------
        # Round 内 Step 1：渠道
        # -------------------------
        channel_result = execute_investigation_tool_v2(
            decision=first_decision,
            attempt_number=1,
            bindings=bindings,
        )

        assert (
            channel_result.observation.status
            == ToolObservationStatusV2.EVIDENCE
        )
        assert channel_result.evidence_reference is not None
        assert channel_result.released_rows

        for row in channel_result.released_rows:
            assert set(row) == {
                "channel_name",
                "gmv",
            }
            assert "__group_size" not in row

        insight_after_channel = _append_evidence(
            insight=initial_state.planner_state.insight,
            evidence=channel_result.evidence_reference,
        )

        first_transition = advance_investigation_loop_v2(
            state=initial_state,
            observation=channel_result.observation,
            refreshed_insight=insight_after_channel,
            refreshed_available_actions=(
                region_action,
            ),
            evidence_sufficient=False,
        )

        assert (
            first_transition.control_decision.directive
            == LoopDirectiveV2.REPLAN
        )
        assert first_transition.next_state.investigation_steps_used == 1
        assert first_transition.next_state.planner_state.completed_action_ids == (
            CHANNEL_ACTION_ID,
        )

        channel_evidence_id = (
            channel_result.evidence_reference.evidence_id
        )

        # -------------------------
        # Re-plan：必须使用更新后的 State
        # -------------------------
        def planner_after_channel(state: InvestigationStateV2):
            proposal = PlannerProposalV2(
                decision_type=PlannerDecisionTypeV2.SELECT_TOOL,
                action_id=REGION_ACTION_ID,
                clarification_prompt=None,
                rationale=(
                    "渠道 Evidence 已写入 State，"
                    "继续从仍然合法的区域方向补充调查。"
                ),
                supporting_evidence_ids=(
                    channel_evidence_id,
                ),
            )
            return validate_planner_proposal_v2(
                state=state,
                proposal=proposal,
            )

        replan_result = replan_after_transition_v2(
            transition=first_transition,
            planner=planner_after_channel,
        )

        second_decision = replan_result.planner_decision

        assert second_decision.selected_action is not None
        assert (
            second_decision.selected_action.action_id
            == REGION_ACTION_ID
        )
        assert (
            second_decision.supporting_evidence_ids
            == (channel_evidence_id,)
        )

        # -------------------------
        # Round 内 Step 2：区域
        # -------------------------
        region_result = execute_investigation_tool_v2(
            decision=second_decision,
            attempt_number=1,
            bindings=bindings,
        )

        assert (
            region_result.observation.status
            == ToolObservationStatusV2.EVIDENCE
        )
        assert region_result.evidence_reference is not None
        assert region_result.released_rows

        for row in region_result.released_rows:
            assert set(row) == {
                "region_name",
                "gmv",
            }
            assert "__group_size" not in row

        insight_after_region = _append_evidence(
            insight=first_transition.next_state.planner_state.insight,
            evidence=region_result.evidence_reference,
        )

        final_transition = advance_investigation_loop_v2(
            state=first_transition.next_state,
            observation=region_result.observation,
            refreshed_insight=insight_after_region,
            refreshed_available_actions=(),
            evidence_sufficient=True,
        )

        # -------------------------
        # 最终 Stop Boundary
        # -------------------------
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
        assert final_state.planner_state.completed_action_ids == (
            CHANNEL_ACTION_ID,
            REGION_ACTION_ID,
        )
        assert final_state.planner_state.available_actions == ()

        final_evidence_ids = {
            item.evidence_id
            for item in final_state.planner_state.insight.evidence
        }

        assert "ev_anomaly" in final_evidence_ids
        assert (
            channel_result.evidence_reference.evidence_id
            in final_evidence_ids
        )
        assert (
            region_result.evidence_reference.evidence_id
            in final_evidence_ids
        )

        # 两次真实 PostgreSQL Tool 执行都必须留下可验证 Audit。
        verification = verify_audit_log(audit_path)
        assert verification.success
        assert verification.record_count == 2


TESTS = (
    test_real_postgresql_two_step_investigation_loop,
)


def run_acceptance() -> None:
    passed = 0
    failed = 0

    print("=" * 80)
    print(
        "Day86 Investigation Loop V2 "
        "PostgreSQL End-to-End"
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
        "PostgreSQL End-to-End Summary"
    )
    print(f"Total: {len(TESTS)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    run_acceptance()
