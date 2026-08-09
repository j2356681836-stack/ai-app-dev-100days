from __future__ import annotations

from datetime import date
from decimal import Decimal

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
from app.semantic_layer.query_plan_v2_loader import (
    get_query_plan_v2_by_name,
    load_query_plan_v2_catalog,
)
from app.semantic_layer.time_window_resolver_v2 import (
    resolve_time_window_v2,
)
from app.text_to_sql.final_answer_v2 import (
    FinalAnswerStatusV2,
    generate_final_answer_v2,
)


REFERENCE_DATE = date(2026, 8, 3)


def _context() -> AccessContext:
    catalog = load_query_plan_v2_catalog()

    return AccessContext(
        request_id="final-answer-v2-tests",
        actor_id="answer-test-user",
        role=AccessRole.SCOPED_ANALYST,
        dataset_name="beauty_bi_v2",
        target_schema="beauty_bi_v2",
        operation_mode=OperationMode.OBSERVE_ADVISE,
        allowed_metrics=frozenset(
            plan.metric for plan in catalog.query_plans
        ),
        allowed_tables=frozenset(
            table
            for plan in catalog.query_plans
            for table in plan.resource_contract.required_tables
        ),
        allowed_columns=frozenset(
            column
            for plan in catalog.query_plans
            for column in plan.resource_contract.required_columns
        ),
        denied_columns=frozenset(),
        allowed_region_codes=frozenset(
            {"BEIJING", "SHANGHAI"}
        ),
        allowed_channel_codes=frozenset(
            {"JD", "TMALL"}
        ),
        sensitive_data_policy=SensitiveDataPolicy(),
        policy_version="final_answer_v2_test_policy",
        scope_source="final_answer_v2_test_fixture",
    )


def _envelope(plan_name: str, question: str):
    plan = get_query_plan_v2_by_name(plan_name)
    assert plan is not None

    planning = build_governed_planning_envelope_v2(
        context=_context(),
        plan=plan,
        time_resolution=resolve_time_window_v2(
            question,
            reference_date=REFERENCE_DATE,
        ),
    )

    assert (
        planning.status
        == GovernedPlanningStatusV2.READY_FOR_COMPILATION
    )
    assert planning.envelope is not None
    return planning.envelope


def _succeeded(rows) -> GovernedFinalizationResult:
    normalized = tuple(dict(row) for row in rows)

    return GovernedFinalizationResult(
        success=True,
        outcome=FinalizationOutcome.SUCCEEDED,
        reason_code=FinalizationReason.ALLOWED,
        message="Governed request finalized and rows released.",
        rows=normalized,
        row_count=len(normalized),
        blocked_stage=None,
        blocked_reason=None,
        audit_persisted=True,
        audit_event_id="answer-test-event",
        audit_event_fingerprint="a" * 64,
        audit_sequence_number=1,
        audit_record_hash="b" * 64,
        error_type=None,
        retryable=False,
    )


def _blocked() -> GovernedFinalizationResult:
    return GovernedFinalizationResult(
        success=False,
        outcome=FinalizationOutcome.BLOCKED,
        reason_code=FinalizationReason.RESULT_PROTECTION_BLOCKED,
        message="Governed request was blocked.",
        rows=(),
        row_count=0,
        blocked_stage="result_protection",
        blocked_reason="minimum_group_size_violation",
        audit_persisted=True,
        audit_event_id="answer-test-block",
        audit_event_fingerprint="c" * 64,
        audit_sequence_number=1,
        audit_record_hash="d" * 64,
        error_type="governance_blocked",
        retryable=False,
    )


def _failed() -> GovernedFinalizationResult:
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


def test_overall_success_discloses_actual_bound_scope() -> None:
    result = generate_final_answer_v2(
        envelope=_envelope(
            "gmv_overall_v2",
            "2025年GMV是多少？",
        ),
        finalization=_succeeded([
            {"gmv": Decimal("11430211.41")}
        ]),
    )

    assert result.status == FinalAnswerStatusV2.ANSWERED
    assert "11,430,211.41" in result.answer
    assert "BEIJING" in result.answer
    assert "SHANGHAI" in result.answer
    assert "JD" in result.answer
    assert "TMALL" in result.answer
    assert "__group_size" not in result.answer


def test_dimension_result_uses_query_plan_visible_fields() -> None:
    result = generate_final_answer_v2(
        envelope=_envelope(
            "gmv_channel_v2",
            "2025年各渠道GMV",
        ),
        finalization=_succeeded([
            {
                "channel_name": "天猫",
                "gmv": Decimal("300.50"),
            },
            {
                "channel_name": "京东",
                "gmv": Decimal("200.25"),
            },
        ]),
    )

    assert result.status == FinalAnswerStatusV2.ANSWERED
    assert "渠道=天猫：300.5" in result.answer
    assert "渠道=京东：200.25" in result.answer


def test_blocked_never_turns_into_fact_or_zero() -> None:
    result = generate_final_answer_v2(
        envelope=_envelope(
            "gmv_overall_v2",
            "上月GMV是多少？",
        ),
        finalization=_blocked(),
    )

    assert result.status == FinalAnswerStatusV2.BLOCKED
    assert "数据保护策略" in result.answer
    assert "GMV为" not in result.answer
    assert "0元" not in result.answer
    assert (
        result.blocked_reason
        == "minimum_group_size_violation"
    )


def test_failed_does_not_masquerade_as_no_data() -> None:
    result = generate_final_answer_v2(
        envelope=_envelope(
            "gmv_overall_v2",
            "2025年GMV是多少？",
        ),
        finalization=_failed(),
    )

    assert result.status == FinalAnswerStatusV2.FAILED
    assert "未能安全完成" in result.answer
    assert "未查询到" not in result.answer


def test_succeeded_empty_rows_is_explicit_no_data() -> None:
    result = generate_final_answer_v2(
        envelope=_envelope(
            "gmv_channel_v2",
            "2025年各渠道GMV",
        ),
        finalization=_succeeded([]),
    )

    assert result.status == FinalAnswerStatusV2.NO_DATA
    assert "未查询到可释放的数据" in result.answer
    assert "BEIJING" in result.answer
    assert "JD" in result.answer


TESTS = (
    test_overall_success_discloses_actual_bound_scope,
    test_dimension_result_uses_query_plan_visible_fields,
    test_blocked_never_turns_into_fact_or_zero,
    test_failed_does_not_masquerade_as_no_data,
    test_succeeded_empty_rows_is_explicit_no_data,
)


def run_tests() -> None:
    passed = 0
    failed = 0

    print("=" * 80)
    print("Final Answer V2 Tests")
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
    print("Final Answer V2 Summary")
    print(f"Total: {len(TESTS)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    run_tests()
