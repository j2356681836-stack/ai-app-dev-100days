from __future__ import annotations

from app.agents.investigation_contracts_v2 import (
    AnalysisModeV2,
    AnalysisScopeV2,
    EvidenceReferenceV2,
    InsightContractV2,
    ToolContractV2,
    ToolFailureCodeV2,
    ToolIdentityV2,
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
from app.agents.investigation_loop_v2 import (
    ToolObservationStatusV2,
)
from app.governance.governed_finalization import (
    FinalizationOutcome,
    FinalizationReason,
    GovernedFinalizationResult,
)
from app.semantic_layer.time_comparison_contract_v2 import (
    TimeWindowReferenceV2,
)
from datetime import date


def _tool() -> ToolContractV2:
    return ToolContractV2(
        identity=ToolIdentityV2(
            name="governed_metric_query",
            version="dataset_v2",
            purpose="执行一次受治理的指标调查动作。",
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


def _decision() -> PlannerDecisionV2:
    action = AvailableInvestigationActionV2(
        action_id="drill_channel",
        tool_contract=_tool(),
        arguments=(
            BoundToolArgumentV2(
                name="metric_name",
                value="gmv",
            ),
        ),
    )
    return PlannerDecisionV2(
        decision_type=PlannerDecisionTypeV2.SELECT_TOOL,
        selected_action=action,
        rationale="当前证据需要继续查看渠道贡献。",
        supporting_evidence_ids=("ev_anomaly",),
    )


def _success(rows=({"channel_name": "天猫", "gmv": 100},)):
    return GovernedFinalizationResult(
        success=True,
        outcome=FinalizationOutcome.SUCCEEDED,
        reason_code=FinalizationReason.ALLOWED,
        message="Governed request finalized and rows released.",
        rows=tuple(dict(row) for row in rows),
        row_count=len(rows),
        blocked_stage=None,
        blocked_reason=None,
        audit_persisted=True,
        audit_event_id="audit-event-001",
        audit_event_fingerprint="audit-fingerprint-001",
        audit_sequence_number=1,
        audit_record_hash="audit-record-hash-001",
        error_type=None,
        retryable=False,
    )


def _blocked(
    *,
    reason_code: FinalizationReason,
    stage: str,
    reason: str,
):
    return GovernedFinalizationResult(
        success=False,
        outcome=FinalizationOutcome.BLOCKED,
        reason_code=reason_code,
        message="Governed request was blocked.",
        rows=(),
        row_count=0,
        blocked_stage=stage,
        blocked_reason=reason,
        audit_persisted=True,
        audit_event_id="audit-event-002",
        audit_event_fingerprint="audit-fingerprint-002",
        audit_sequence_number=2,
        audit_record_hash="audit-record-hash-002",
        error_type="governance_blocked",
        retryable=False,
    )


def _failed():
    return GovernedFinalizationResult(
        success=False,
        outcome=FinalizationOutcome.FAILED,
        reason_code=FinalizationReason.AUDIT_PERSISTENCE_FAILED,
        message="Audit persistence failed.",
        rows=(),
        row_count=0,
        blocked_stage=None,
        blocked_reason=None,
        audit_persisted=False,
        audit_event_id=None,
        audit_event_fingerprint=None,
        audit_sequence_number=None,
        audit_record_hash=None,
        error_type="governance_finalization_error",
        retryable=False,
    )


def _binding(result) -> TrustedToolExecutionBindingV2:
    return TrustedToolExecutionBindingV2(
        action_id="drill_channel",
        executor_binding="execute_governed_query_v2",
        executor=lambda: result,
    )


def test_success_maps_to_evidence_and_only_released_rows() -> None:
    result = execute_investigation_tool_v2(
        decision=_decision(),
        attempt_number=1,
        bindings={"drill_channel": _binding(_success())},
    )
    assert result.observation.status == ToolObservationStatusV2.EVIDENCE
    assert result.observation.retryable is False
    assert result.evidence_reference is not None
    assert result.released_rows == (
        {"channel_name": "天猫", "gmv": 100},
    )


def test_success_empty_rows_maps_to_no_data() -> None:
    result = execute_investigation_tool_v2(
        decision=_decision(),
        attempt_number=1,
        bindings={"drill_channel": _binding(_success(rows=()))},
    )
    assert result.observation.status == ToolObservationStatusV2.NO_DATA
    assert result.observation.failure_code == ToolFailureCodeV2.NO_DATA
    assert result.evidence_reference is None
    assert result.released_rows == ()


def test_authorization_block_maps_to_unauthorized() -> None:
    finalization = _blocked(
        reason_code=FinalizationReason.AUTHORIZATION_BLOCKED,
        stage="authorization",
        reason="column_not_allowed",
    )
    result = execute_investigation_tool_v2(
        decision=_decision(),
        attempt_number=1,
        bindings={"drill_channel": _binding(finalization)},
    )
    assert result.observation.failure_code == ToolFailureCodeV2.UNAUTHORIZED
    assert result.observation.retryable is False


def test_statement_timeout_keeps_timeout_code_but_non_retryable() -> None:
    finalization = _blocked(
        reason_code=FinalizationReason.EXECUTION_BLOCKED,
        stage="sql_execution",
        reason="statement_timeout",
    )
    result = execute_investigation_tool_v2(
        decision=_decision(),
        attempt_number=1,
        bindings={"drill_channel": _binding(finalization)},
    )
    assert result.observation.failure_code == ToolFailureCodeV2.TIMEOUT
    assert result.observation.retryable is False


def test_result_protection_block_releases_no_rows() -> None:
    finalization = _blocked(
        reason_code=FinalizationReason.RESULT_PROTECTION_BLOCKED,
        stage="result_protection",
        reason="minimum_group_size_violation",
    )
    result = execute_investigation_tool_v2(
        decision=_decision(),
        attempt_number=1,
        bindings={"drill_channel": _binding(finalization)},
    )
    assert (
        result.observation.failure_code
        == ToolFailureCodeV2.EXECUTION_FAILURE
    )
    assert result.released_rows == ()
    assert result.blocked_reason == "minimum_group_size_violation"


def test_audit_failure_is_non_retryable_execution_failure() -> None:
    result = execute_investigation_tool_v2(
        decision=_decision(),
        attempt_number=1,
        bindings={"drill_channel": _binding(_failed())},
    )
    assert (
        result.observation.failure_code
        == ToolFailureCodeV2.EXECUTION_FAILURE
    )
    assert result.observation.retryable is False
    assert result.released_rows == ()


def test_missing_binding_fails_closed() -> None:
    try:
        execute_investigation_tool_v2(
            decision=_decision(),
            attempt_number=1,
            bindings={},
        )
    except ValueError:
        return
    raise AssertionError("缺少可信 binding 时必须 fail-closed。")


def test_binding_name_mismatch_fails_closed() -> None:
    binding = TrustedToolExecutionBindingV2(
        action_id="drill_channel",
        executor_binding="wrong_executor",
        executor=lambda: _success(),
    )
    try:
        execute_investigation_tool_v2(
            decision=_decision(),
            attempt_number=1,
            bindings={"drill_channel": binding},
        )
    except ValueError:
        return
    raise AssertionError("executor_binding 不一致时必须 fail-closed。")


def test_clarify_decision_cannot_execute_tool() -> None:
    decision = PlannerDecisionV2(
        decision_type=PlannerDecisionTypeV2.CLARIFY,
        selected_action=None,
        clarification_prompt="请确认你要分析 GMV 还是订单数。",
        rationale="当前指标仍有歧义。",
        supporting_evidence_ids=(),
    )
    try:
        execute_investigation_tool_v2(
            decision=decision,
            attempt_number=1,
            bindings={},
        )
    except ValueError:
        return
    raise AssertionError("CLARIFY Decision 不能进入 Tool Executor。")


TESTS = [
    test_success_maps_to_evidence_and_only_released_rows,
    test_success_empty_rows_maps_to_no_data,
    test_authorization_block_maps_to_unauthorized,
    test_statement_timeout_keeps_timeout_code_but_non_retryable,
    test_result_protection_block_releases_no_rows,
    test_audit_failure_is_non_retryable_execution_failure,
    test_missing_binding_fails_closed,
    test_binding_name_mismatch_fails_closed,
    test_clarify_decision_cannot_execute_tool,
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

    print("Day86 Investigation Tool Executor V2 Acceptance Summary")
    print(f"Total: {len(TESTS)}")
    print(f"Passed: {passed}")
    print(f"Failed: {len(failures)}")

    for failure in failures:
        print(f"- {failure}")

    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
