from __future__ import annotations

import os
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

import yaml

from app.agents.evidence_pack_builder_v2 import (
    EvidenceBuildStatusV2,
    build_governed_query_evidence_record_v2,
)
from app.agents.evidence_pack_delivery_v2 import (
    EvidenceSufficiencyStatusV2,
    assemble_evidence_pack_delivery_v2,
    build_metric_definition_snapshot_v2,
)
from app.agents.evidence_pack_v2 import (
    EvidencePackV2,
)
from app.agents.investigation_contracts_v2 import (
    AnalysisModeV2,
    AnalysisScopeV2,
    EvidenceReferenceV2,
    InsightContractV2,
    RecommendedCheckV2,
    SupportedInsightStatementV2,
    ToolContractV2,
    ToolFailureCodeV2,
    ToolIdentityV2,
)
from app.evaluation.automated_insight_evaluator_v2 import (
    AutomatedInsightEvaluationStatusV2,
    evaluate_insight_delivery_v2,
)
from app.evaluation.business_decision_evaluation_contract_v2 import (
    BusinessDecisionOverallStatusV2,
    EvaluationScoreV2,
)
from app.evaluation.business_decision_judge_v2 import (
    BusinessDecisionJudgeExecutionStatusV2,
    judge_business_decision_v2,
)
from app.evaluation.insight_golden_case_contract_v2 import (
    BusinessDecisionScoreFloorV2,
    BusinessInsightThemeV2,
    EvaluationEvidenceClassV2,
    ForbiddenBusinessClaimV2,
    InsightGoldenCaseV2,
    InsightSectionV2,
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


REFERENCE_DATE = date(2026, 8, 18)
FIXED_TIME = datetime(
    2026,
    8,
    18,
    6,
    30,
    tzinfo=timezone.utc,
)

QUESTION = (
    "2025年哪个渠道 GMV 最高？"
    "如果要进一步调查渠道表现，下一步应该先查什么？"
)
PLAN_NAME = "gmv_channel_v2"

EXECUTION_POLICY = GovernedExecutionPolicy(
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

PASS_FLOOR = BusinessDecisionScoreFloorV2(
    factual_correctness=EvaluationScoreV2.PASS,
    diagnostic_relevance=EvaluationScoreV2.PASS,
    prioritization=EvaluationScoreV2.PASS,
    actionability=EvaluationScoreV2.PASS,
    epistemic_discipline=EvaluationScoreV2.PASS,
    evidence_sufficiency=EvaluationScoreV2.PASS,
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
        request_id="day88-observed-business-decision",
        actor_id="day88-observed-user",
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
        policy_version="day88_observed_business_decision",
        scope_source="day88_postgresql_observed_probe",
    )


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


def _observed_case() -> InsightGoldenCaseV2:
    """
    这是 live observed regression evidence，不冒充 Fresh。

    Case 只要求当前已被 Day87 真实验证过的渠道 GMV 查询能力，
    不为了 Live Judge Probe 重新打开 gmv_overall_v2 Result Protection。
    """

    return InsightGoldenCaseV2(
        case_id="INS-OBS-001",
        question=QUESTION,
        theme=BusinessInsightThemeV2.ACTIVITY_REVIEW,
        evidence_class=EvaluationEvidenceClassV2.REGRESSION,
        previously_observed=True,
        used_for_development=True,
        metric_name="gmv",
        expected_analysis_mode=AnalysisModeV2.INVESTIGATION,
        expected_sufficiency=EvidenceSufficiencyStatusV2.PARTIAL,
        expected_overall_status=BusinessDecisionOverallStatusV2.PASS,
        score_floor=PASS_FLOOR,
        required_sections=(
            InsightSectionV2.CONFIRMED_FACT,
            InsightSectionV2.RECOMMENDED_CHECK,
        ),
        forbidden_sections=(
            InsightSectionV2.DIMENSION_CONTRIBUTION,
        ),
        forbidden_claims=(
            ForbiddenBusinessClaimV2.CAUSAL_ATTRIBUTION,
            ForbiddenBusinessClaimV2.UNSUPPORTED_FACT,
            ForbiddenBusinessClaimV2.ZERO_FROM_NO_DATA,
        ),
        rationale=(
            "真实受保护渠道 GMV 可以回答最高渠道事实；"
            "下一步调查建议必须保持为 Recommended Check，"
            "不能把最高渠道静默升级成原因或 Contribution。"
        ),
        tags=(
            "observed",
            "postgresql",
            "live_judge",
            "gmv",
            "channel",
        ),
    )


def _metric_definition():
    path = Path(
        "metadata/beauty_bi_v2/business_metrics.yaml"
    )

    payload = yaml.safe_load(
        path.read_text(encoding="utf-8")
    )

    return build_metric_definition_snapshot_v2(
        metadata_catalog=payload,
        metric_name="gmv",
    )


def _execute_real_channel_evidence(
    *,
    audit_path: Path,
):
    context = _integration_context()

    plan = get_query_plan_v2_by_name(
        PLAN_NAME
    )
    assert plan is not None

    resolution = resolve_time_window_v2(
        "2025年各渠道 GMV 是多少？",
        reference_date=REFERENCE_DATE,
    )

    # Day88 Observed Probe 必须验证真实的 2025 全年窗口。
    # 如果时间解析失败并静默回退到默认最近 3 个月，
    # 应在数据库执行前立即失败，避免把 fixture bug
    # 误判成 Result Protection / Evidence Builder 问题。
    expected_start = date(2025, 1, 1)
    expected_end = date(2025, 12, 31)

    assert resolution.effective_start_date == expected_start, (
        "Observed Probe 时间窗口错误："
        f"expected_start={expected_start}, "
        f"actual_start={resolution.effective_start_date}, "
        f"source={getattr(resolution.source, 'value', resolution.source)}, "
        f"expression_type={getattr(resolution.expression_type, 'value', resolution.expression_type)}, "
        f"notice={resolution.user_notice}"
    )
    assert resolution.effective_end_date == expected_end, (
        "Observed Probe 时间窗口错误："
        f"expected_end={expected_end}, "
        f"actual_end={resolution.effective_end_date}, "
        f"source={getattr(resolution.source, 'value', resolution.source)}, "
        f"expression_type={getattr(resolution.expression_type, 'value', resolution.expression_type)}, "
        f"notice={resolution.user_notice}"
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
        f"{planning.status.value}; "
        f"{planning.detail}"
    )
    assert planning.envelope is not None

    compilation = compile_governed_query_plan_v2(
        planning.envelope
    )

    assert (
        compilation.status
        == QueryPlanCompileStatusV2.COMPILED
    ), (
        "Compilation 未通过："
        f"{compilation.status.value}; "
        f"{compilation.detail}"
    )
    assert compilation.contract is not None

    finalization = execute_governed_query_v2(
        context=context,
        question="2025年各渠道 GMV 是多少？",
        envelope=planning.envelope,
        compiled=compilation.contract,
        runtime_config=_runtime_config(
            audit_path
        ),
        execution_policy=EXECUTION_POLICY,
        event_id="day88-observed-channel-gmv",
        occurred_at_utc=FIXED_TIME,
        written_at_utc=FIXED_TIME,
    )

    if not finalization.success:
        print("=" * 88)
        print("Day88 Governed Finalization Failure")
        print("=" * 88)
        print("plan_name:", PLAN_NAME)
        print("success:", finalization.success)
        print("outcome:", getattr(
            finalization.outcome,
            "value",
            finalization.outcome,
        ))
        print("message:", finalization.message)
        print("blocked_stage:", finalization.blocked_stage)
        print("blocked_reason:", finalization.blocked_reason)
        print("audit_persisted:", finalization.audit_persisted)
        print("audit_event_id:", finalization.audit_event_id)
        print("retryable:", finalization.retryable)
        print("row_count:", finalization.row_count)
        print("=" * 88)

        raise AssertionError(
            "真实渠道 GMV Governed Finalization 未成功。"
        )

    assert finalization.rows, (
        "Governed Finalization 成功但没有 released rows。"
        "请检查 Time Window / Scope，而不要把空结果构造成 Evidence。"
    )

    evidence_reference = EvidenceReferenceV2(
        evidence_id="ev_day88_observed_channel_gmv",
        source="tool:governed_gmv_channel_query@dataset_v2",
        description="2025年授权范围内各渠道 GMV 的真实受保护查询证据。",
    )

    analysis_scope = AnalysisScopeV2(
        metric_name="gmv",
        analysis_window=resolution_to_window(
            resolution
        ),
        result_grain="channel",
        scope_summary=(
            "当前 AccessContext 授权 Region / Channel Scope 内的 "
            "2025年渠道 GMV。"
        ),
    )

    build = build_governed_query_evidence_record_v2(
        analysis_scope=analysis_scope,
        evidence_reference=evidence_reference,
        tool_contract=_tool_contract(),
        envelope=planning.envelope,
        compiled=compilation.contract,
        finalization=finalization,
    )

    assert build.success, build.detail
    assert build.status == EvidenceBuildStatusV2.BUILT
    assert build.record is not None

    verification = verify_audit_log(
        audit_path
    )
    assert verification.success
    assert verification.record_count == 1

    return (
        build.record,
        analysis_scope,
    )


def resolution_to_window(
    resolution,
):
    from app.semantic_layer.time_comparison_contract_v2 import (
        TimeWindowReferenceV2,
    )

    assert resolution.effective_start_date is not None
    assert resolution.effective_end_date is not None

    return TimeWindowReferenceV2(
        start_date=resolution.effective_start_date,
        end_date=resolution.effective_end_date,
    )


def _build_delivery(
    *,
    audit_path: Path,
):
    record, scope = (
        _execute_real_channel_evidence(
            audit_path=audit_path
        )
    )

    protected = record.protected_result
    assert protected is not None
    assert protected.rows

    top_row = max(
        protected.rows,
        key=lambda row: Decimal(
            str(row["gmv"])
        ),
    )

    channel_name = str(
        top_row["channel_name"]
    )
    gmv_value = Decimal(
        str(top_row["gmv"])
    )

    fact = SupportedInsightStatementV2(
        statement=(
            f"2025年当前授权范围内，GMV 最高的渠道是 "
            f"{channel_name}，GMV={gmv_value}。"
        ),
        evidence_ids=(
            record.reference.evidence_id,
        ),
    )

    recommended = RecommendedCheckV2(
        check=(
            f"下一步优先比较 {channel_name} 的 2025 / 2024 "
            "GMV 变化，并在有受支持 decomposition 后再决定是否继续下钻。"
        ),
        rationale=(
            "当前 Evidence 只证明 2025年渠道排名，"
            "尚未证明该渠道对同比变化的 Contribution 或任何业务原因。"
        ),
        evidence_ids=(
            record.reference.evidence_id,
        ),
    )

    insight = InsightContractV2(
        analysis_mode=AnalysisModeV2.INVESTIGATION,
        analysis_scope=scope,
        confirmed_facts=(fact,),
        recommended_checks=(recommended,),
        evidence=(
            record.reference,
        ),
    )

    pack = EvidencePackV2(
        pack_id="pack-day88-observed-live-001",
        analysis_scope=scope,
        insight=insight,
        evidence_records=(record,),
    )

    return assemble_evidence_pack_delivery_v2(
        evidence_pack=pack,
        metric_definition=_metric_definition(),
    )


def run_observed_probe() -> None:
    case = _observed_case()

    with TemporaryDirectory() as tmp:
        audit_path = (
            Path(tmp)
            / "day88_observed_business_decision_audit.jsonl"
        )

        delivery = _build_delivery(
            audit_path=audit_path
        )

        automated = evaluate_insight_delivery_v2(
            golden_case=case,
            delivery=delivery,
        )

        print("=" * 88)
        print("Day88 Observed Business Decision Evaluation")
        print("=" * 88)
        print("Case ID:", case.case_id)
        print(
            "Evidence Class:",
            case.evidence_class.value,
        )
        print(
            "Evidence Sufficiency:",
            delivery.sufficiency.status.value,
        )
        print(
            "Deterministic Precheck:",
            automated.status.value,
        )

        for gate in automated.gate_results:
            print(
                f"- {gate.gate.value}: "
                f"{gate.status.value} | "
                f"{gate.reason}"
            )

        assert (
            automated.status
            == (
                AutomatedInsightEvaluationStatusV2
                .READY_FOR_BUSINESS_REVIEW
            )
        )

        print("-" * 88)
        print("Business Insight")
        print("-" * 88)

        for fact in (
            delivery.evidence_pack.insight.confirmed_facts
        ):
            print(
                "Fact:",
                fact.statement,
            )

        for check in (
            delivery.evidence_pack.insight.recommended_checks
        ):
            print(
                "Recommended Check:",
                check.check,
            )
            print(
                "Recommendation Rationale:",
                check.rationale,
            )

        print("-" * 88)
        print(
            "Live Judge Model:",
            os.getenv(
                "DEEPSEEK_MODEL",
                "<DeepSeek client default>",
            ),
        )

        outcome = judge_business_decision_v2(
            golden_case=case,
            delivery=delivery,
            automated_result=automated,
        )

        assert (
            outcome.status
            == BusinessDecisionJudgeExecutionStatusV2.JUDGED
        )
        assert outcome.evaluation is not None

        evaluation = outcome.evaluation

        print(
            "Judge Overall:",
            evaluation.overall_status.value,
        )
        print(
            "Meets Golden Floor:",
            outcome.meets_golden_floor,
        )
        print(
            "Meets Expected Overall:",
            outcome.meets_expected_overall_status,
        )

        dimensions = (
            "factual_correctness",
            "diagnostic_relevance",
            "prioritization",
            "actionability",
            "epistemic_discipline",
            "evidence_sufficiency",
        )

        for name in dimensions:
            result = getattr(
                evaluation,
                name,
            )
            print(
                f"{name}: "
                f"{result.score.name}({int(result.score)})"
            )
            print(
                "  reason:",
                result.reason,
            )
            print(
                "  evidence_ids:",
                list(result.evidence_ids),
            )

        print("=" * 88)
        print(
            "Observed Probe Result:",
            (
                "PASS"
                if (
                    outcome.meets_golden_floor
                    and outcome.meets_expected_overall_status
                )
                else "PARTIAL / REVIEW_REQUIRED"
            ),
        )
        print(
            "注意：这是一次 live observed evidence，"
            "不是 deterministic regression，"
            "也不能证明模型长期稳定。"
        )


if __name__ == "__main__":
    run_observed_probe()
