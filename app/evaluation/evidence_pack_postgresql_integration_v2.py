from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from app.agents.evidence_pack_builder_v2 import (
    EvidenceBuildStatusV2,
    build_governed_query_evidence_record_v2,
)
from app.agents.evidence_pack_v2 import (
    EvidencePackV2,
    EvidenceTypeV2,
)
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
from app.governance.access_context import (
    AccessContext,
    AccessRole,
    OperationMode,
    SensitiveDataPolicy,
)
from app.governance.audit_sink import verify_audit_log
from app.governance.execution_policy import GovernedExecutionPolicy
from app.governance.governance_runtime import GovernanceRuntimeConfig
from app.governance.governed_finalization import (
    FinalizationOutcome,
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
    11,
    30,
    tzinfo=timezone.utc,
)

QUESTION = "2025年各渠道GMV是多少？"
PLAN_NAME = "gmv_channel_v2"

ANALYSIS_WINDOW = TimeWindowReferenceV2(
    start_date=date(2025, 1, 1),
    end_date=date(2025, 12, 31),
)

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
        audit_secret="audit-secret-32-characters-long",
        audit_log_path=audit_log_path,
        create_parent_directory=True,
        fsync_enabled=True,
    )


def _catalog_resources():
    """
    Integration Context 从真实 V2 Query Plan Catalog 汇总允许资源。

    避免手写 table / column allowlist 与 Catalog 漂移。
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
        request_id="day87-real-evidence-pack",
        actor_id="day87-integration-user",
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
        policy_version="day87_real_evidence_pack",
        scope_source="day87_postgresql_integration_fixture",
    )


def _ready_pair(
    *,
    context: AccessContext,
):
    """
    复用 Phase3 Trust Plane 生成可信 Envelope + Compiled Contract。
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
            purpose="查询授权范围内的渠道 GMV。",
        ),
        input_schema_name="GovernedInvestigationInputV2",
        output_schema_name="GovernedFinalizationResult",
        required_permissions=(
            "metric_access",
            "data_scope",
        ),
        execution_policy_reference=(
            "governed_execution_policy_v2"
        ),
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


def _analysis_scope() -> AnalysisScopeV2:
    return AnalysisScopeV2(
        metric_name="gmv",
        analysis_window=ANALYSIS_WINDOW,
        result_grain="channel",
        scope_summary=(
            "当前 AccessContext 授权 Region / Channel Scope 内的 "
            "2025 年渠道 GMV。"
        ),
    )


def test_real_postgresql_result_builds_evidence_pack() -> None:
    """
    Day87 Step C 真实链路：

    Query Plan
    → Governed Planning Envelope
    → Deterministic Compilation
    → AST Enforcement
    → Read-only PostgreSQL
    → Result Protection
    → Audit Persistence
    → Governed Finalization
    → Evidence Builder
    → EvidenceRecordV2
    → InsightContractV2
    → EvidencePackV2

    这条测试证明 Evidence Pack 使用的不是 mock rows，
    也不是从 ToolObservation summary 反推出来的证据。
    """

    context = _integration_context()
    envelope, compiled = _ready_pair(
        context=context,
    )
    tool_contract = _tool_contract()
    analysis_scope = _analysis_scope()

    evidence_reference = EvidenceReferenceV2(
        evidence_id="ev_day87_real_channel_gmv",
        source=(
            "tool:governed_gmv_channel_query"
            "@dataset_v2"
        ),
        description=(
            "2025 年授权范围内各渠道 GMV 的真实受保护查询证据。"
        ),
    )

    with TemporaryDirectory() as tmp:
        audit_path = Path(tmp) / "day87_evidence_pack_audit.jsonl"
        runtime_config = _runtime_config(audit_path)

        finalization = execute_governed_query_v2(
            context=context,
            question=QUESTION,
            envelope=envelope,
            compiled=compiled,
            runtime_config=runtime_config,
            execution_policy=INTEGRATION_EXECUTION_POLICY,
            event_id="day87-real-evidence-pack-channel-gmv",
            occurred_at_utc=FIXED_TIME,
            written_at_utc=FIXED_TIME,
        )

        assert finalization.success
        assert (
            finalization.outcome
            == FinalizationOutcome.SUCCEEDED
        )
        assert finalization.audit_persisted
        assert finalization.rows
        assert 1 <= finalization.row_count <= 6

        # 跨 Governance Boundary 的 rows 只能包含 visible outputs。
        for row in finalization.rows:
            assert set(row) == {
                "channel_name",
                "gmv",
            }
            assert "__group_size" not in row
            assert row["channel_name"]
            assert row["gmv"] is not None

        build_decision = (
            build_governed_query_evidence_record_v2(
                analysis_scope=analysis_scope,
                evidence_reference=evidence_reference,
                tool_contract=tool_contract,
                envelope=envelope,
                compiled=compiled,
                finalization=finalization,
            )
        )

        assert build_decision.success
        assert (
            build_decision.status
            == EvidenceBuildStatusV2.BUILT
        )
        assert build_decision.record is not None

        record = build_decision.record

        assert (
            record.evidence_type
            == EvidenceTypeV2.GOVERNED_QUERY_RESULT
        )
        assert record.provenance is not None
        assert record.protected_result is not None

        # Evidence Pack 保存的是可验证 provenance，
        # 不是 raw SQL / raw parameters。
        assert record.provenance.dataset_name == "beauty_bi_v2"
        assert record.provenance.target_schema == "beauty_bi_v2"
        assert record.provenance.metric_name == "gmv"
        assert record.provenance.result_grain == "channel"
        assert record.provenance.plan_name == PLAN_NAME
        assert (
            record.provenance.analysis_window
            == ANALYSIS_WINDOW
        )
        assert (
            record.provenance.query_plan_fingerprint
            == envelope.query_plan_fingerprint
        )
        assert (
            record.provenance.envelope_fingerprint
            == envelope.envelope_fingerprint
        )
        assert (
            record.provenance.compiled_contract_fingerprint
            == compiled.contract_fingerprint
        )
        assert (
            record.provenance.sql_fingerprint
            == compiled.sql_fingerprint
        )
        assert (
            record.provenance.time_binding_fingerprint
            == compiled.time_binding_fingerprint
        )
        assert (
            record.provenance.scope_binding_fingerprint
            == compiled.scope_binding_fingerprint
        )
        assert (
            record.provenance.audit_event_id
            == finalization.audit_event_id
        )
        assert (
            record.provenance.audit_event_fingerprint
            == finalization.audit_event_fingerprint
        )
        assert (
            record.provenance.audit_record_hash
            == finalization.audit_record_hash
        )

        assert (
            record.protected_result.rows
            == finalization.rows
        )
        assert (
            record.protected_result.row_count
            == finalization.row_count
        )
        assert record.protected_result.field_names == (
            "channel_name",
            "gmv",
        )

        # 使用真实 protected rows 形成一个最小业务事实。
        top_row = max(
            record.protected_result.rows,
            key=lambda row: row["gmv"],
        )

        fact = SupportedInsightStatementV2(
            statement=(
                "2025 年当前授权范围内，"
                f"GMV 最高的渠道是 {top_row['channel_name']}。"
            ),
            evidence_ids=(
                evidence_reference.evidence_id,
            ),
        )

        insight = InsightContractV2(
            analysis_mode=AnalysisModeV2.FACT,
            analysis_scope=analysis_scope,
            confirmed_facts=(fact,),
            evidence=(evidence_reference,),
        )

        pack = EvidencePackV2(
            pack_id="pack-day87-real-postgresql-001",
            analysis_scope=analysis_scope,
            insight=insight,
            evidence_records=(record,),
        )

        assert pack.pack_id == "pack-day87-real-postgresql-001"
        assert len(pack.evidence_records) == 1
        assert len(pack.insight.confirmed_facts) == 1
        assert (
            pack.insight.confirmed_facts[0].evidence_ids
            == (evidence_reference.evidence_id,)
        )

        # 最终 Pack 中仍然只有 protected rows。
        for row in (
            pack.evidence_records[0]
            .protected_result.rows
        ):
            assert "__group_size" not in row

        # Evidence Pack 中的 Audit provenance 必须能对应真实 Audit Log。
        verification = verify_audit_log(audit_path)
        assert verification.success
        assert verification.record_count == 1

        print(
            "Confirmed Fact:",
            pack.insight.confirmed_facts[0].statement,
        )
        print(
            "Evidence ID:",
            evidence_reference.evidence_id,
        )
        print(
            "Audit Event ID:",
            record.provenance.audit_event_id,
        )


TESTS = (
    test_real_postgresql_result_builds_evidence_pack,
)


def run_acceptance() -> None:
    passed = 0
    failed = 0

    print("=" * 80)
    print(
        "Day87 Evidence Pack V2 "
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
        "Day87 Evidence Pack V2 "
        "PostgreSQL Integration Summary"
    )
    print(f"Total: {len(TESTS)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    run_acceptance()
