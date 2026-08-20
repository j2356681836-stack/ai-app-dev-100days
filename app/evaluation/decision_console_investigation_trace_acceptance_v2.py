from __future__ import annotations

import inspect
from datetime import date

import app.delivery.decision_console_view_v2 as console_view_module
from app.agents.evidence_pack_delivery_v2 import (
    MetricDefinitionSnapshotV2,
    assemble_evidence_pack_delivery_v2,
)
from app.agents.evidence_pack_v2 import (
    EvidencePackV2,
    EvidenceRecordV2,
    EvidenceTypeV2,
    GovernedEvidenceProvenanceV2,
    InvestigationObservationEvidenceV2,
    ProtectedResultV2,
)
from app.agents.investigation_contracts_v2 import (
    AnalysisModeV2,
    AnalysisScopeV2,
    EvidenceReferenceV2,
    InsightContractV2,
    ToolFailureCodeV2,
)
from app.agents.investigation_loop_v2 import (
    InvestigationBudgetPolicyV2,
    InvestigationLoopStateV2,
    InvestigationLoopTransitionV2,
    InvestigationStopReasonV2,
    InvestigationStopStatusV2,
    LoopControlDecisionV2,
    LoopDirectiveV2,
    ToolObservationStatusV2,
    ToolObservationV2,
)
from app.agents.investigation_planner_v2 import InvestigationStateV2
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


def _scope() -> AnalysisScopeV2:
    comparison = _comparison()
    return AnalysisScopeV2(
        metric_name="gmv",
        analysis_window=comparison.current_window,
        comparison=comparison,
        result_grain="channel",
        scope_summary="authorized_scope_only",
    )


def _insight() -> InsightContractV2:
    return InsightContractV2(
        analysis_mode=AnalysisModeV2.INVESTIGATION,
        analysis_scope=_scope(),
    )


def _metric_definition() -> MetricDefinitionSnapshotV2:
    return MetricDefinitionSnapshotV2(
        metadata_version="v2",
        dataset_name="beauty_bi_v2",
        metric_name="gmv",
        chinese_name="销售额",
        grain="paid_order_items",
        definition="测试用 GMV Definition。",
        formula="SUM(item_paid_amount)",
        filters=(),
        metric_fingerprint="metric-fingerprint",
    )


def _governed_result_record(
    evidence_id: str,
) -> EvidenceRecordV2:
    return EvidenceRecordV2(
        reference=EvidenceReferenceV2(
            evidence_id=evidence_id,
            source="governed_query_result_v2",
            description=f"{evidence_id} 受保护调查结果。",
        ),
        evidence_type=EvidenceTypeV2.GOVERNED_QUERY_RESULT,
        provenance=GovernedEvidenceProvenanceV2(
            dataset_name="beauty_bi_v2",
            target_schema="beauty_bi_v2",
            metric_name="gmv",
            result_grain="channel",
            analysis_window=_comparison().current_window,
            scope_summary="authorized_scope_only",
            plan_name="gmv_channel_v2",
            query_plan_fingerprint=f"qpf-{evidence_id}",
            envelope_fingerprint=f"env-{evidence_id}",
            compiled_contract_fingerprint=f"compiled-{evidence_id}",
            sql_fingerprint=f"sql-{evidence_id}",
            time_binding_fingerprint=f"time-{evidence_id}",
            scope_binding_fingerprint=f"scope-{evidence_id}",
            tool_name="governed_gmv_channel_query",
            tool_version="dataset_v2",
            audit_event_id=f"audit-{evidence_id}",
            audit_event_fingerprint=f"audit-fp-{evidence_id}",
            audit_record_hash=f"audit-hash-{evidence_id}",
            finalization_contract_version="governed_finalization_v1",
        ),
        protected_result=ProtectedResultV2(
            field_names=("channel_name", "gmv"),
            rows=({"channel_name": "Tmall", "gmv": 100},),
            row_count=1,
        ),
    )


def _observation(
    *,
    action_id: str,
    attempt_number: int,
    status: ToolObservationStatusV2,
    produced: tuple[str, ...] = (),
    failure_code: ToolFailureCodeV2 | None = None,
    retryable: bool = False,
    summary: str,
) -> ToolObservationV2:
    return ToolObservationV2(
        action_id=action_id,
        attempt_number=attempt_number,
        status=status,
        failure_code=failure_code,
        retryable=retryable,
        produced_evidence_ids=produced,
        summary=summary,
    )


def _observation_record(
    observation: ToolObservationV2,
    *,
    record_id: str,
) -> EvidenceRecordV2:
    return EvidenceRecordV2(
        reference=EvidenceReferenceV2(
            evidence_id=record_id,
            source="investigation_loop_v2",
            description="Day89 trace observation。",
        ),
        evidence_type=EvidenceTypeV2.INVESTIGATION_OBSERVATION,
        parent_evidence_ids=observation.produced_evidence_ids,
        investigation_observation=InvestigationObservationEvidenceV2(
            action_id=observation.action_id,
            attempt_number=observation.attempt_number,
            status=observation.status.value,
            failure_code=(
                observation.failure_code.value
                if observation.failure_code is not None
                else None
            ),
            retryable=observation.retryable,
            summary=observation.summary,
        ),
    )


def _planner_state() -> InvestigationStateV2:
    return InvestigationStateV2(
        insight=_insight(),
        completed_action_ids=(),
        available_actions=(),
    )


def _transition(
    *,
    history: tuple[ToolObservationV2, ...],
    directive: LoopDirectiveV2,
    stop_reason: InvestigationStopReasonV2 | None = None,
    steps_used: int,
) -> InvestigationLoopTransitionV2:
    return InvestigationLoopTransitionV2(
        control_decision=LoopControlDecisionV2(
            directive=directive,
            stop_reason=stop_reason,
            next_investigation_steps_used=steps_used,
        ),
        next_state=InvestigationLoopStateV2(
            planner_state=_planner_state(),
            budget_policy=InvestigationBudgetPolicyV2(
                max_investigation_steps=3,
                max_retries_per_action=1,
            ),
            investigation_steps_used=steps_used,
            observation_history=history,
        ),
    )


def _fixture():
    obs1 = _observation(
        action_id="drill_channel",
        attempt_number=1,
        status=ToolObservationStatusV2.EVIDENCE,
        produced=("ev-channel",),
        summary="渠道分解成功并产生受保护 Evidence。",
    )
    obs2 = _observation(
        action_id="drill_product",
        attempt_number=1,
        status=ToolObservationStatusV2.FAILURE,
        failure_code=ToolFailureCodeV2.EXECUTION_FAILURE,
        retryable=False,
        summary="商品路径执行失败，进入替代路径恢复。",
    )
    obs3 = _observation(
        action_id="drill_region",
        attempt_number=1,
        status=ToolObservationStatusV2.EVIDENCE,
        produced=("ev-region",),
        summary="区域分解成功，当前 Evidence 已足够。",
    )

    transitions = (
        _transition(
            history=(obs1,),
            directive=LoopDirectiveV2.REPLAN,
            steps_used=1,
        ),
        _transition(
            history=(obs1, obs2),
            directive=LoopDirectiveV2.RECOVER,
            steps_used=2,
        ),
        _transition(
            history=(obs1, obs2, obs3),
            directive=LoopDirectiveV2.STOP,
            stop_reason=InvestigationStopReasonV2.EVIDENCE_SUFFICIENT,
            steps_used=3,
        ),
    )

    records = (
        _governed_result_record("ev-channel"),
        _governed_result_record("ev-region"),
        _observation_record(obs1, record_id="obs-1"),
        _observation_record(obs2, record_id="obs-2"),
        _observation_record(obs3, record_id="obs-3"),
    )

    pack = EvidencePackV2(
        pack_id="day89-trace-pack",
        analysis_scope=_scope(),
        insight=_insight(),
        evidence_records=records,
    )

    delivery = assemble_evidence_pack_delivery_v2(
        evidence_pack=pack,
        metric_definition=_metric_definition(),
    )

    stop = InvestigationStopStatusV2(
        stop_reason=InvestigationStopReasonV2.EVIDENCE_SUFFICIENT,
        evidence_sufficient=True,
        uninvestigated_action_ids=(),
        can_continue=False,
        current_round=1,
        max_rounds=2,
        total_steps_used=3,
        max_total_investigation_steps=5,
        detail="当前 Evidence 已足以支持有边界的结论，本轮调查停止。",
    )

    return delivery, transitions, stop


def test_trace_preserves_replan_recover_stop() -> None:
    delivery, transitions, stop = _fixture()

    view = build_decision_console_view_v2(
        delivery=delivery,
        investigation_transitions=transitions,
        investigation_stop_status=stop,
    )

    assert tuple(
        item.next_directive
        for item in view.investigation_trace
    ) == (
        LoopDirectiveV2.REPLAN,
        LoopDirectiveV2.RECOVER,
        LoopDirectiveV2.STOP,
    )


def test_trace_preserves_observation_status_and_lineage() -> None:
    delivery, transitions, stop = _fixture()

    view = build_decision_console_view_v2(
        delivery=delivery,
        investigation_transitions=transitions,
        investigation_stop_status=stop,
    )

    first = view.investigation_trace[0]
    assert first.observation_status == ToolObservationStatusV2.EVIDENCE
    assert first.produced_evidence_ids == ("ev-channel",)
    assert first.observation_evidence_id == "obs-1"


def test_runtime_control_preserves_explicit_continuation_gate() -> None:
    delivery, transitions, _ = _fixture()

    budget_stop = InvestigationStopStatusV2(
        stop_reason=(
            InvestigationStopReasonV2.INVESTIGATION_BUDGET_EXHAUSTED
        ),
        evidence_sufficient=False,
        uninvestigated_action_ids=("drill_product",),
        can_continue=True,
        current_round=1,
        max_rounds=2,
        total_steps_used=3,
        max_total_investigation_steps=5,
        detail="本轮预算耗尽，但用户可以明确要求继续下一轮。",
    )

    final = transitions[-1].model_copy(
        update={
            "control_decision": LoopControlDecisionV2(
                directive=LoopDirectiveV2.STOP,
                stop_reason=(
                    InvestigationStopReasonV2
                    .INVESTIGATION_BUDGET_EXHAUSTED
                ),
                next_investigation_steps_used=3,
            )
        }
    )
    changed = (*transitions[:-1], final)

    view = build_decision_console_view_v2(
        delivery=delivery,
        investigation_transitions=changed,
        investigation_stop_status=budget_stop,
    )

    assert view.runtime_control is not None
    assert view.runtime_control.evidence_sufficient is False
    assert view.runtime_control.can_continue is True
    assert view.runtime_control.uninvestigated_action_ids == (
        "drill_product",
    )


def test_missing_produced_evidence_fails_closed() -> None:
    delivery, transitions, stop = _fixture()

    bad_obs = transitions[0].next_state.observation_history[0].model_copy(
        update={"produced_evidence_ids": ("missing-evidence",)}
    )
    bad_first = _transition(
        history=(bad_obs,),
        directive=LoopDirectiveV2.REPLAN,
        steps_used=1,
    )

    try:
        build_decision_console_view_v2(
            delivery=delivery,
            investigation_transitions=(bad_first,),
        )
    except ValueError:
        return

    raise AssertionError(
        "Trace produced Evidence 不存在时必须 fail-closed。"
    )


def test_discontinuous_history_fails_closed() -> None:
    delivery, transitions, stop = _fixture()

    broken_second = transitions[1].model_copy(
        update={
            "next_state": transitions[1].next_state.model_copy(
                update={
                    "observation_history": (
                        transitions[1].next_state.observation_history[-1],
                    )
                }
            )
        }
    )

    try:
        build_decision_console_view_v2(
            delivery=delivery,
            investigation_transitions=(
                transitions[0],
                broken_second,
            ),
        )
    except ValueError:
        return

    raise AssertionError(
        "不连续的 Investigation history 必须 fail-closed。"
    )


def test_stop_reason_mismatch_fails_closed() -> None:
    delivery, transitions, stop = _fixture()

    wrong_stop = stop.model_copy(
        update={
            "stop_reason": InvestigationStopReasonV2.NO_LEGAL_ACTION,
        }
    )

    try:
        build_decision_console_view_v2(
            delivery=delivery,
            investigation_transitions=transitions,
            investigation_stop_status=wrong_stop,
        )
    except ValueError:
        return

    raise AssertionError(
        "Stop Status 与最终 transition 不一致必须 fail-closed。"
    )


def test_transition_after_stop_fails_closed() -> None:
    delivery, transitions, stop = _fixture()

    extra = transitions[-1].model_copy()

    try:
        build_decision_console_view_v2(
            delivery=delivery,
            investigation_transitions=(
                *transitions,
                extra,
            ),
            investigation_stop_status=stop,
        )
    except ValueError:
        return

    raise AssertionError(
        "STOP 后不能继续追加 transition。"
    )


TESTS = (
    test_trace_preserves_replan_recover_stop,
    test_trace_preserves_observation_status_and_lineage,
    test_runtime_control_preserves_explicit_continuation_gate,
    test_missing_produced_evidence_fails_closed,
    test_discontinuous_history_fails_closed,
    test_stop_reason_mismatch_fails_closed,
    test_transition_after_stop_fails_closed,
)


def run_acceptance() -> None:
    print("Day89 Decision Console Investigation Trace / HITL Preflight")
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
        "Day89 Decision Console Investigation Trace / HITL "
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
