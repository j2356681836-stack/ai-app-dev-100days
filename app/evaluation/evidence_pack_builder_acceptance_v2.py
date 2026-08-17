from __future__ import annotations

from datetime import date

from app.agents.evidence_pack_builder_v2 import (
    EvidenceBuildStatusV2,
    build_governed_query_evidence_record_v2,
)
from app.agents.investigation_contracts_v2 import (
    AnalysisScopeV2,
    EvidenceReferenceV2,
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
from app.governance.governed_finalization import (
    FinalizationOutcome,
    FinalizationReason,
    GovernedFinalizationResult,
)
from app.governance.governed_planning_envelope_v2 import (
    GovernedPlanningStatusV2,
    build_governed_planning_envelope_v2,
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
QUESTION = "2025年各渠道GMV是多少？"

WINDOW_2025 = TimeWindowReferenceV2(
    start_date=date(2025, 1, 1),
    end_date=date(2025, 12, 31),
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


def _context() -> AccessContext:
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

    return AccessContext(
        request_id="day87-evidence-builder",
        actor_id="day87-user",
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
        policy_version="day87_evidence_builder_v2",
        scope_source="day87_acceptance",
    )


def _ready_pair():
    plan = get_query_plan_v2_by_name(
        "gmv_channel_v2"
    )
    assert plan is not None

    resolution = resolve_time_window_v2(
        QUESTION,
        reference_date=REFERENCE_DATE,
    )

    planning = build_governed_planning_envelope_v2(
        context=_context(),
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


def _tool() -> ToolContractV2:
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


def _reference() -> EvidenceReferenceV2:
    return EvidenceReferenceV2(
        evidence_id="ev_day87_channel",
        source=(
            "tool:governed_gmv_channel_query"
            "@dataset_v2"
        ),
        description="渠道 GMV 的受保护查询证据。",
    )


def _scope(
    *,
    window: TimeWindowReferenceV2 = WINDOW_2025,
) -> AnalysisScopeV2:
    return AnalysisScopeV2(
        metric_name="gmv",
        analysis_window=window,
        result_grain="channel",
        scope_summary="当前授权 Region / Channel Scope。",
    )


def _success_finalization() -> GovernedFinalizationResult:
    return GovernedFinalizationResult(
        success=True,
        outcome=FinalizationOutcome.SUCCEEDED,
        reason_code=FinalizationReason.ALLOWED,
        message="Governed request finalized and rows released.",
        rows=(
            {
                "channel_name": "天猫",
                "gmv": 800,
            },
            {
                "channel_name": "京东",
                "gmv": 500,
            },
        ),
        row_count=2,
        blocked_stage=None,
        blocked_reason=None,
        audit_persisted=True,
        audit_event_id="day87-audit-event-001",
        audit_event_fingerprint="a" * 64,
        audit_sequence_number=1,
        audit_record_hash="b" * 64,
        error_type=None,
        retryable=False,
    )


def _build(**overrides):
    envelope, compiled = _ready_pair()

    payload = {
        "analysis_scope": _scope(),
        "evidence_reference": _reference(),
        "tool_contract": _tool(),
        "envelope": envelope,
        "compiled": compiled,
        "finalization": _success_finalization(),
        "parent_evidence_ids": (),
    }
    payload.update(overrides)

    return build_governed_query_evidence_record_v2(
        **payload
    )


def test_valid_governed_result_builds_record() -> None:
    decision = _build()

    assert decision.success
    assert decision.status == EvidenceBuildStatusV2.BUILT
    assert decision.record is not None

    record = decision.record

    assert record.provenance is not None
    assert record.protected_result is not None
    assert record.provenance.metric_name == "gmv"
    assert record.provenance.result_grain == "channel"
    assert record.provenance.analysis_window == WINDOW_2025
    assert record.protected_result.row_count == 2
    assert record.protected_result.field_names == (
        "channel_name",
        "gmv",
    )

    for row in record.protected_result.rows:
        assert set(row) == {
            "channel_name",
            "gmv",
        }
        assert "__group_size" not in row


def test_blocked_finalization_cannot_build_evidence() -> None:
    blocked = GovernedFinalizationResult(
        success=False,
        outcome=FinalizationOutcome.BLOCKED,
        reason_code=(
            FinalizationReason.RESULT_PROTECTION_BLOCKED
        ),
        message="Governed request was blocked.",
        rows=(),
        row_count=0,
        blocked_stage="result_protection",
        blocked_reason="minimum_group_size_violation",
        audit_persisted=True,
        audit_event_id="day87-audit-blocked",
        audit_event_fingerprint="c" * 64,
        audit_sequence_number=2,
        audit_record_hash="d" * 64,
        error_type="governance_blocked",
        retryable=False,
    )

    decision = _build(
        finalization=blocked
    )

    assert not decision.success
    assert (
        decision.status
        == EvidenceBuildStatusV2.FINALIZATION_NOT_RELEASABLE
    )
    assert decision.record is None


def test_metric_mismatch_fails_closed() -> None:
    decision = _build(
        analysis_scope=_scope().model_copy(
            update={
                "metric_name": "order_count",
            }
        )
    )

    assert not decision.success
    assert (
        decision.status
        == EvidenceBuildStatusV2.TRUST_LINKAGE_MISMATCH
    )


def test_grain_mismatch_fails_closed() -> None:
    decision = _build(
        analysis_scope=_scope().model_copy(
            update={
                "result_grain": "region",
            }
        )
    )

    assert not decision.success
    assert (
        decision.status
        == EvidenceBuildStatusV2.TRUST_LINKAGE_MISMATCH
    )


def test_tool_source_mismatch_fails_closed() -> None:
    bad_reference = _reference().model_copy(
        update={
            "source": "tool:another_tool@dataset_v2",
        }
    )

    decision = _build(
        evidence_reference=bad_reference
    )

    assert not decision.success
    assert (
        decision.status
        == EvidenceBuildStatusV2.TOOL_CONTRACT_MISMATCH
    )


def test_wrong_executor_binding_fails_closed() -> None:
    bad_tool = _tool().model_copy(
        update={
            "executor_binding": "unsafe_executor",
        }
    )

    decision = _build(
        tool_contract=bad_tool
    )

    assert not decision.success
    assert (
        decision.status
        == EvidenceBuildStatusV2.TOOL_CONTRACT_MISMATCH
    )


def test_outside_time_window_fails_closed() -> None:
    wrong_window = TimeWindowReferenceV2(
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
    )

    decision = _build(
        analysis_scope=_scope(
            window=wrong_window
        )
    )

    assert not decision.success
    assert (
        decision.status
        == EvidenceBuildStatusV2.TIME_WINDOW_MISMATCH
    )


def test_released_hidden_field_fails_closed() -> None:
    bad_finalization = _success_finalization().model_copy(
        update={
            "rows": (
                {
                    "channel_name": "天猫",
                    "gmv": 800,
                    "__group_size": 100,
                },
            ),
            "row_count": 1,
        }
    )

    decision = _build(
        finalization=bad_finalization
    )

    assert not decision.success
    assert (
        decision.status
        == EvidenceBuildStatusV2.RESULT_SHAPE_MISMATCH
    )


def test_envelope_compiled_linkage_mismatch_fails() -> None:
    envelope, compiled = _ready_pair()

    tampered = compiled.model_copy(
        update={
            "scope_binding_fingerprint": "f" * 64,
        }
    )

    decision = build_governed_query_evidence_record_v2(
        analysis_scope=_scope(),
        evidence_reference=_reference(),
        tool_contract=_tool(),
        envelope=envelope,
        compiled=tampered,
        finalization=_success_finalization(),
    )

    assert not decision.success
    assert (
        decision.status
        == EvidenceBuildStatusV2.TRUST_LINKAGE_MISMATCH
    )


def test_parent_evidence_ids_are_preserved() -> None:
    decision = _build(
        parent_evidence_ids=(
            "ev_upstream_anomaly",
        )
    )

    assert decision.success
    assert decision.record is not None
    assert decision.record.parent_evidence_ids == (
        "ev_upstream_anomaly",
    )


TESTS = (
    test_valid_governed_result_builds_record,
    test_blocked_finalization_cannot_build_evidence,
    test_metric_mismatch_fails_closed,
    test_grain_mismatch_fails_closed,
    test_tool_source_mismatch_fails_closed,
    test_wrong_executor_binding_fails_closed,
    test_outside_time_window_fails_closed,
    test_released_hidden_field_fails_closed,
    test_envelope_compiled_linkage_mismatch_fails,
    test_parent_evidence_ids_are_preserved,
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

    print(
        "Day87 Evidence Pack V2 Step B "
        "Builder Acceptance Summary"
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
