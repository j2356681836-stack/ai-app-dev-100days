from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from app.agents.investigation_contracts_v2 import (
    ToolContractV2,
    ToolFailureCodeV2,
    ToolIdentityV2,
)
from app.agents.investigation_loop_v2 import (
    ToolObservationStatusV2,
)
from app.agents.investigation_planner_v2 import (
    AvailableInvestigationActionV2,
    BoundToolArgumentV2,
    PlannerDecisionTypeV2,
    PlannerDecisionV2,
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
from app.semantic_layer.time_window_resolver_v2 import (
    resolve_time_window_v2,
)


REFERENCE_DATE = date(2026, 8, 16)
FIXED_TIME = datetime(
    2026,
    8,
    16,
    9,
    30,
    tzinfo=timezone.utc,
)

QUESTION = "2025年各渠道GMV是多少？"
PLAN_NAME = "gmv_channel_v2"
ACTION_ID = "drill_channel"

# 这里只用于真实 PostgreSQL Integration。
# 不修改 GovernedExecutionPolicy 的生产默认值。
INTEGRATION_EXECUTION_POLICY = GovernedExecutionPolicy(
    statement_timeout_ms=30_000,
    max_rows=10,
)

# 与 Phase3 PostgreSQL Integration 已验证的数据范围保持一致。
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
    Integration Context 直接从 V2 Query Plan Catalog 汇总允许资源。

    这样测试不会手写一份可能已经漂移的 table / column allowlist。
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
        request_id="day86-investigation-tool-postgresql",
        actor_id="day86-integration-user",
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
        policy_version="day86_investigation_tool_postgresql",
        scope_source="day86_postgresql_integration_fixture",
    )


def _ready_channel_gmv_pair(
    *,
    context: AccessContext,
):
    """
    复用 Phase3 Trust Plane 生成真正可执行的可信 Envelope + Compiled Contract。

    Planner 不参与这一段，也不能自己提交 SQL。
    """

    plan = get_query_plan_v2_by_name(PLAN_NAME)

    assert plan is not None, (
        f"缺少 Query Plan：{PLAN_NAME}"
    )
    assert plan.metric == "gmv"
    assert plan.result_grain == "channel"

    resolution = resolve_time_window_v2(
        QUESTION,
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
        f"status={compilation.status.value}；"
        f"detail={compilation.detail}"
    )
    assert compilation.contract is not None

    return planning.envelope, compilation.contract


def _tool_contract() -> ToolContractV2:
    return ToolContractV2(
        identity=ToolIdentityV2(
            name="governed_gmv_channel_query",
            version="dataset_v2",
            purpose=(
                "在既有 Governance Boundary 内查询渠道 GMV。"
            ),
        ),
        input_schema_name="GovernedChannelGmvInvestigationInputV2",
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


def _planner_decision() -> PlannerDecisionV2:
    """
    模拟 Day85 已经完成 deterministic validation 的合法 Planner Decision。

    参数只表达业务动作身份，不包含 raw SQL。
    真正的 Envelope / Compiled Contract 只存在于系统侧 Binding。
    """

    action = AvailableInvestigationActionV2(
        action_id=ACTION_ID,
        tool_contract=_tool_contract(),
        arguments=(
            BoundToolArgumentV2(
                name="metric_name",
                value="gmv",
            ),
            BoundToolArgumentV2(
                name="query_plan_name",
                value=PLAN_NAME,
            ),
            BoundToolArgumentV2(
                name="result_grain",
                value="channel",
            ),
        ),
    )

    return PlannerDecisionV2(
        decision_type=PlannerDecisionTypeV2.SELECT_TOOL,
        selected_action=action,
        rationale=(
            "当前调查需要查看渠道层 GMV，"
            "因此选择已批准的渠道 GMV Tool。"
        ),
        supporting_evidence_ids=("ev_anomaly",),
    )


def test_real_postgresql_investigation_tool_releases_protected_evidence(
) -> None:
    """
    Day86 Step E 核心真实链路：

    Planner Action
    → 系统侧 Trusted Binding
    → Governed Query Execution
    → PostgreSQL
    → Result Protection
    → Audit Persistence
    → Governed Finalization
    → Tool Observation / Evidence
    """

    context = _integration_context()
    envelope, compiled = _ready_channel_gmv_pair(
        context=context,
    )

    with TemporaryDirectory() as tmp:
        audit_path = Path(tmp) / "day86_audit.jsonl"
        runtime_config = _runtime_config(audit_path)

        def governed_executor():
            return execute_governed_query_v2(
                context=context,
                question=QUESTION,
                envelope=envelope,
                compiled=compiled,
                runtime_config=runtime_config,
                execution_policy=INTEGRATION_EXECUTION_POLICY,
                event_id="day86-real-postgresql-drill-channel",
                occurred_at_utc=FIXED_TIME,
                written_at_utc=FIXED_TIME,
            )

        binding = TrustedToolExecutionBindingV2(
            action_id=ACTION_ID,
            executor_binding="execute_governed_query_v2",
            executor=governed_executor,
        )

        result = execute_investigation_tool_v2(
            decision=_planner_decision(),
            attempt_number=1,
            bindings={ACTION_ID: binding},
        )

        assert (
            result.observation.status
            == ToolObservationStatusV2.EVIDENCE
        ), (
            "真实 PostgreSQL Tool 没有释放 Evidence："
            f"status={result.observation.status.value}；"
            f"failure_code={result.observation.failure_code}；"
            f"summary={result.observation.summary}"
        )

        assert result.evidence_reference is not None
        assert len(result.observation.produced_evidence_ids) == 1
        assert (
            result.observation.produced_evidence_ids[0]
            == result.evidence_reference.evidence_id
        )

        assert result.released_rows
        assert 1 <= len(result.released_rows) <= 6

        for row in result.released_rows:
            assert set(row) == {
                "channel_name",
                "gmv",
            }, (
                "跨 Governance Boundary 的结果字段不符合预期："
                f"{sorted(row)}"
            )
            assert "__group_size" not in row
            assert row["channel_name"]
            assert row["gmv"] is not None

        assert result.audit_event_fingerprint is not None

        verification = verify_audit_log(audit_path)
        assert verification.success
        assert verification.record_count == 1


TESTS = (
    test_real_postgresql_investigation_tool_releases_protected_evidence,
)


def run_acceptance() -> None:
    passed = 0
    failed = 0

    print("=" * 80)
    print(
        "Day86 Investigation Tool Executor V2 "
        "PostgreSQL Integration"
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
        "Day86 Investigation Tool Executor V2 "
        "PostgreSQL Integration Summary"
    )
    print(f"Total: {len(TESTS)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    run_acceptance()
