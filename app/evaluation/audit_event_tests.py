import json
from datetime import datetime, timezone

from pydantic import ValidationError

from app.governance.access_context import (
    AccessContext,
    AccessRole,
    OperationMode,
    SensitiveDataPolicy,
)
from app.governance.audit_event import (
    AuditBuildReason,
    AuditOutcome,
    AuditStage,
    build_actor_ref,
    build_audit_event,
    fingerprint_text,
    serialize_audit_event,
)
from app.governance.authorization import (
    AuthorizationDecision,
    AuthorizationReason,
)
from app.governance.execution_budget import (
    ExecutionBudgetPolicy,
    TokenUsage,
    consume_step,
    consume_token_usage,
    create_initial_budget_state,
)
from app.governance.execution_policy import (
    ExecutionErrorType,
    GovernedExecutionResult,
)
from app.governance.sensitive_data import (
    AppliedFieldProtection,
    ProtectionAction,
    ProtectionReason,
    ResultProtectionResult,
    SensitiveDataCategory,
)


AUDIT_SECRET = "day71-audit-secret-32-characters"
ALT_AUDIT_SECRET = "day72-alt-audit-secret-32-chars"
FIXED_TIME = datetime(
    2026,
    7,
    25,
    10,
    30,
    tzinfo=timezone.utc,
)


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(
            f"{message}\nExpected: {expected}\nActual: {actual}"
        )


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def build_context() -> AccessContext:
    return AccessContext(
        request_id="req-day71-audit-001",
        actor_id="analyst-001",
        role=AccessRole.SCOPED_ANALYST,
        dataset_name="beauty_bi_v2",
        target_schema="beauty_bi_v2",
        operation_mode=OperationMode.OBSERVE_ADVISE,
        allowed_metrics=frozenset({"order_count"}),
        allowed_tables=frozenset({
            "fact_orders",
            "dim_channel",
        }),
        allowed_columns=frozenset({
            "fact_orders.order_id",
            "dim_channel.channel_name",
        }),
        denied_columns=frozenset(),
        allowed_region_codes=frozenset({
            "SOUTH",
            "EAST",
        }),
        allowed_channel_codes=frozenset({
            "TMALL",
            "JD",
        }),
        sensitive_data_policy=SensitiveDataPolicy(),
        policy_version="access_policy_v1",
        scope_source="server_test_fixture",
    )


def allowed_authorization() -> AuthorizationDecision:
    return AuthorizationDecision(
        allowed=True,
        error_type=None,
        reason_code=AuthorizationReason.ALLOWED,
        message="Allowed.",
        policy_version="access_policy_v1",
        retryable=False,
    )


def denied_authorization() -> AuthorizationDecision:
    return AuthorizationDecision(
        allowed=False,
        error_type="authorization_error",
        reason_code=(
            AuthorizationReason.COLUMN_NOT_ALLOWED
        ),
        message="Denied.",
        denied_columns=frozenset({
            "fact_orders.customer_id",
        }),
        policy_version="access_policy_v1",
        retryable=False,
    )


def successful_execution() -> GovernedExecutionResult:
    return GovernedExecutionResult(
        success=True,
        rows=({"channel_name": "天猫", "order_count": 10},),
        row_count=1,
        observed_row_count=1,
        error_type=None,
        message=None,
        retryable=False,
        execution_time_ms=12.5,
        target_schema="beauty_bi_v2",
        statement_timeout_ms=5_000,
        max_rows=200,
        policy_version="execution_governance_v1",
    )


def failed_execution() -> GovernedExecutionResult:
    return GovernedExecutionResult(
        success=False,
        rows=(),
        row_count=0,
        observed_row_count=201,
        error_type=ExecutionErrorType.RESULT_TOO_LARGE,
        message="Rejected.",
        retryable=False,
        execution_time_ms=15.0,
        target_schema="beauty_bi_v2",
        statement_timeout_ms=5_000,
        max_rows=200,
        policy_version="execution_governance_v1",
    )


def successful_protection() -> ResultProtectionResult:
    return ResultProtectionResult(
        success=True,
        rows=({"channel_name": "天猫", "order_count": 10},),
        row_count=1,
        error_type=None,
        reason_code=ProtectionReason.ALLOWED,
        message="Protected.",
        applied_protections=(
            AppliedFieldProtection(
                output_field="channel_name",
                category=SensitiveDataCategory.ORDINARY,
                action=ProtectionAction.ALLOW,
            ),
            AppliedFieldProtection(
                output_field="order_count",
                category=SensitiveDataCategory.ORDINARY,
                action=ProtectionAction.ALLOW,
            ),
        ),
        rejected_fields=frozenset(),
        minimum_group_size_checked=True,
        minimum_observed_group_size=10,
        contract_fingerprint="contract-fingerprint",
        protection_fingerprint="protection-fingerprint",
        policy_version="result_protection_v1",
        retryable=False,
    )


def failed_protection() -> ResultProtectionResult:
    return ResultProtectionResult(
        success=False,
        rows=(),
        row_count=0,
        error_type="result_protection_error",
        reason_code=(
            ProtectionReason
            .MINIMUM_GROUP_SIZE_VIOLATION
        ),
        message="Small group.",
        applied_protections=(),
        rejected_fields=frozenset(),
        minimum_group_size_checked=True,
        minimum_observed_group_size=3,
        contract_fingerprint="contract-fingerprint",
        protection_fingerprint="protection-fingerprint",
        policy_version="result_protection_v1",
        retryable=False,
    )


def budget_state():
    policy = ExecutionBudgetPolicy()
    state = create_initial_budget_state(policy)

    step = consume_step(
        policy=policy,
        state=state,
        operation="sql_generation",
    )

    usage = consume_token_usage(
        policy=policy,
        state=step.state,
        usage=TokenUsage(
            prompt_tokens=100,
            completion_tokens=20,
            total_tokens=120,
        ),
        operation="sql_generation",
    )

    return usage.state


def build_success_event(
    *,
    generated_sql: str = "SELECT 1",
    executed_sql: str = "SELECT 1",
    repair_history=(),
):
    return build_audit_event(
        context=build_context(),
        question="各渠道订单数排名",
        authorization=allowed_authorization(),
        required_tables=(
            "dim_channel",
            "fact_orders",
        ),
        required_columns=(
            "dim_channel.channel_name",
            "fact_orders.order_id",
        ),
        metric_name="order_count",
        generated_sql=generated_sql,
        executed_sql=executed_sql,
        execution=successful_execution(),
        budget=budget_state(),
        protection=successful_protection(),
        repair_history=repair_history,
        audit_secret=AUDIT_SECRET,
        event_id="audit-event-001",
        occurred_at_utc=FIXED_TIME,
    )


def test_actor_ref_is_deterministic() -> None:
    first = build_actor_ref(
        actor_id="analyst-001",
        audit_secret=AUDIT_SECRET,
    )
    second = build_actor_ref(
        actor_id="analyst-001",
        audit_secret=AUDIT_SECRET,
    )

    assert_equal(
        first,
        second,
        "Actor reference should be deterministic.",
    )

    assert_true(
        "analyst-001" not in first,
        "Actor reference must not expose raw actor id.",
    )


def test_missing_audit_secret_fails_closed() -> None:
    result = build_audit_event(
        context=build_context(),
        question="test",
        authorization=denied_authorization(),
    )

    assert_equal(
        result.success,
        False,
        "Missing audit secret must fail.",
    )

    assert_equal(
        result.reason_code,
        AuditBuildReason.MISSING_AUDIT_SECRET,
        "Missing secret needs a stable reason.",
    )

    assert_equal(
        result.retryable,
        False,
        "Audit build failure must be non-retryable.",
    )


def test_success_event_is_built() -> None:
    result = build_success_event()

    assert_equal(
        result.success,
        True,
        "Complete successful evidence should build.",
    )

    assert_equal(
        result.event.outcome,
        AuditOutcome.SUCCEEDED,
        "Successful chain should use succeeded outcome.",
    )

    assert_equal(
        result.event.execution.row_count,
        1,
        "Execution row count should be retained.",
    )

    assert_equal(
        result.event.budget.total_tokens_used,
        120,
        "Token usage should be retained.",
    )


def test_success_event_is_immutable() -> None:
    event = build_success_event().event

    try:
        event.outcome = AuditOutcome.FAILED
    except ValidationError:
        return

    raise AssertionError(
        "AuditEvent must be immutable."
    )


def test_authorization_denial_is_blocked() -> None:
    result = build_audit_event(
        context=build_context(),
        question="返回所有客户ID",
        authorization=denied_authorization(),
        required_tables=("fact_orders",),
        required_columns=(
            "fact_orders.customer_id",
        ),
        audit_secret=AUDIT_SECRET,
        event_id="audit-event-auth-block",
        occurred_at_utc=FIXED_TIME,
    )

    assert_equal(
        result.success,
        True,
        "A blocked request should still create audit evidence.",
    )

    assert_equal(
        result.event.outcome,
        AuditOutcome.BLOCKED,
        "Authorization denial should be blocked.",
    )

    assert_equal(
        result.event.blocked_stage,
        AuditStage.AUTHORIZATION,
        "Block stage should be authorization.",
    )


def test_execution_governance_failure_is_blocked() -> None:
    result = build_audit_event(
        context=build_context(),
        question="导出所有订单",
        authorization=allowed_authorization(),
        execution=failed_execution(),
        audit_secret=AUDIT_SECRET,
        event_id="audit-event-execution-block",
        occurred_at_utc=FIXED_TIME,
    )

    assert_equal(
        result.event.outcome,
        AuditOutcome.BLOCKED,
        "Execution governance failure should be blocked.",
    )

    assert_equal(
        result.event.blocked_stage,
        AuditStage.SQL_EXECUTION,
        "Block stage should be sql_execution.",
    )

    assert_equal(
        result.event.blocked_reason,
        "result_too_large",
        "Stable execution error type should be retained.",
    )


def test_result_protection_failure_is_blocked() -> None:
    result = build_audit_event(
        context=build_context(),
        question="返回小样本会员分组",
        authorization=allowed_authorization(),
        execution=successful_execution(),
        protection=failed_protection(),
        audit_secret=AUDIT_SECRET,
        event_id="audit-event-protection-block",
        occurred_at_utc=FIXED_TIME,
    )

    assert_equal(
        result.event.outcome,
        AuditOutcome.BLOCKED,
        "Protection failure should be blocked.",
    )

    assert_equal(
        result.event.blocked_stage,
        AuditStage.RESULT_PROTECTION,
        "Block stage should be result protection.",
    )


def test_missing_execution_evidence_fails_audit_build() -> None:
    result = build_audit_event(
        context=build_context(),
        question="test",
        authorization=allowed_authorization(),
        audit_secret=AUDIT_SECRET,
    )

    assert_equal(
        result.success,
        False,
        "Incomplete evidence must fail audit build.",
    )

    assert_equal(
        result.reason_code,
        AuditBuildReason.INCOMPLETE_AUDIT_EVIDENCE,
        "Missing execution evidence needs stable reason.",
    )


def test_missing_protection_evidence_fails_audit_build() -> None:
    result = build_audit_event(
        context=build_context(),
        question="test",
        authorization=allowed_authorization(),
        execution=successful_execution(),
        audit_secret=AUDIT_SECRET,
    )

    assert_equal(
        result.reason_code,
        AuditBuildReason.INCOMPLETE_AUDIT_EVIDENCE,
        "Missing protection evidence must fail.",
    )


def test_raw_question_and_sql_are_not_serialized() -> None:
    raw_question = "查询客户 CUS-000001 的全部订单"
    raw_sql = (
        "SELECT * FROM fact_orders "
        "WHERE customer_id = 123"
    )

    result = build_audit_event(
        context=build_context(),
        question=raw_question,
        authorization=allowed_authorization(),
        generated_sql=raw_sql,
        executed_sql=raw_sql,
        execution=successful_execution(),
        protection=successful_protection(),
        audit_secret=AUDIT_SECRET,
        event_id="audit-event-no-raw-data",
        occurred_at_utc=FIXED_TIME,
    )

    serialized = serialize_audit_event(result.event)

    assert_true(
        raw_question not in serialized,
        "Raw question must not enter audit JSON.",
    )

    assert_true(
        raw_sql not in serialized,
        "Raw SQL must not enter audit JSON.",
    )

    assert_true(
        "CUS-000001" not in serialized,
        "Identifier in question must not leak.",
    )

    assert_true(
        "customer_id = 123" not in serialized,
        "SQL literal must not leak.",
    )


def test_result_rows_are_not_serialized() -> None:
    serialized = serialize_audit_event(
        build_success_event().event
    )

    assert_true(
        "天猫" not in serialized,
        "Result row values must not enter audit JSON.",
    )


def test_audit_secret_is_not_serialized() -> None:
    serialized = serialize_audit_event(
        build_success_event().event
    )

    assert_true(
        AUDIT_SECRET not in serialized,
        "Audit secret must never enter event JSON.",
    )


def test_repair_history_is_fingerprinted_only() -> None:
    source_sql = "SELECT bad_column FROM fact_orders"
    repaired_sql = "SELECT order_id FROM fact_orders"
    error_text = "column bad_column does not exist"

    result = build_success_event(
        executed_sql=repaired_sql,
        repair_history=(
            {
                "attempt": 1,
                "source_sql": source_sql,
                "repaired_sql": repaired_sql,
                "execution_error": error_text,
            },
        ),
    )

    serialized = serialize_audit_event(result.event)

    assert_equal(
        result.event.repair.attempt_count,
        1,
        "Repair attempt count should be retained.",
    )

    for raw_value in (
        source_sql,
        repaired_sql,
        error_text,
    ):
        assert_true(
            raw_value not in serialized,
            "Raw repair content must not be serialized.",
        )


def test_scope_values_are_sorted_deterministically() -> None:
    event = build_success_event().event

    assert_equal(
        event.scope.allowed_region_codes,
        ("EAST", "SOUTH"),
        "Region scope should be sorted.",
    )

    assert_equal(
        event.scope.allowed_channel_codes,
        ("JD", "TMALL"),
        "Channel scope should be sorted.",
    )

    assert_equal(
        event.scope.required_tables,
        ("dim_channel", "fact_orders"),
        "Required tables should be sorted.",
    )


def test_event_fingerprint_is_stable() -> None:
    first = build_success_event().event
    second = build_success_event().event

    assert_equal(
        first.event_fingerprint,
        second.event_fingerprint,
        "Equivalent evidence needs stable fingerprint.",
    )


def test_changed_executed_sql_changes_event_fingerprint() -> None:
    first = build_success_event(
        executed_sql="SELECT 1"
    ).event

    changed = build_success_event(
        executed_sql="SELECT 2"
    ).event

    assert_true(
        first.event_fingerprint
        != changed.event_fingerprint,
        "Executed SQL change must alter event fingerprint.",
    )


def test_generated_and_executed_sql_can_differ() -> None:
    event = build_success_event(
        generated_sql="SELECT bad_column FROM fact_orders",
        executed_sql="SELECT order_id FROM fact_orders",
    ).event

    assert_true(
        event.generated_sql_fingerprint
        != event.executed_sql_fingerprint,
        "Generated and executed SQL evidence must be separate.",
    )


def test_protection_summary_contains_no_rows() -> None:
    payload = json.loads(
        serialize_audit_event(
            build_success_event().event
        )
    )

    protection = payload["protection"]

    assert_true(
        "rows" not in protection,
        "Protection summary must not contain rows.",
    )

    assert_equal(
        protection["minimum_observed_group_size"],
        10,
        "Safe minimum group evidence should remain.",
    )


def test_naive_timestamp_is_rejected_structurally() -> None:
    result = build_audit_event(
        context=build_context(),
        question="test",
        authorization=allowed_authorization(),
        execution=successful_execution(),
        protection=successful_protection(),
        audit_secret=AUDIT_SECRET,
        event_id="audit-event-naive-time",
        occurred_at_utc=datetime(2026, 7, 25, 10, 30),
    )

    assert_equal(
        result.success,
        False,
        "Naive timestamp must fail.",
    )

    assert_equal(
        result.reason_code,
        AuditBuildReason.INVALID_AUDIT_INPUT,
        "Invalid timestamp must use invalid input.",
    )


def test_input_repair_history_is_not_mutated() -> None:
    repair_history = [
        {
            "attempt": 1,
            "source_sql": "SELECT bad",
            "repaired_sql": "SELECT good",
            "execution_error": "error",
        }
    ]

    before = [dict(repair_history[0])]

    build_success_event(
        repair_history=repair_history
    )

    assert_equal(
        repair_history,
        before,
        "Audit builder must not mutate repair history.",
    )



def test_sensitive_fingerprint_is_deterministic() -> None:
    first = fingerprint_text(
        "SELECT 1",
        namespace="executed_sql",
        audit_secret=AUDIT_SECRET,
    )
    second = fingerprint_text(
        "SELECT 1",
        namespace="executed_sql",
        audit_secret=AUDIT_SECRET,
    )

    assert_equal(
        first,
        second,
        "Same secret, namespace and text must be deterministic.",
    )


def test_sensitive_fingerprint_changes_with_secret() -> None:
    first = fingerprint_text(
        "SELECT 1",
        namespace="executed_sql",
        audit_secret=AUDIT_SECRET,
    )
    second = fingerprint_text(
        "SELECT 1",
        namespace="executed_sql",
        audit_secret=ALT_AUDIT_SECRET,
    )

    assert_true(
        first != second,
        "Sensitive fingerprint must change when the Audit Secret changes.",
    )


def test_sensitive_fingerprint_is_domain_separated() -> None:
    question_fp = fingerprint_text(
        "SELECT 1",
        namespace="question",
        audit_secret=AUDIT_SECRET,
    )
    sql_fp = fingerprint_text(
        "SELECT 1",
        namespace="executed_sql",
        audit_secret=AUDIT_SECRET,
    )

    assert_true(
        question_fp != sql_fp,
        "The same text in different audit domains must not share a fingerprint.",
    )


def test_repair_fingerprints_follow_hmac_contract() -> None:
    source_sql = "SELECT bad_column FROM fact_orders"
    repaired_sql = "SELECT order_id FROM fact_orders"
    error_text = "column bad_column does not exist"

    event = build_success_event(
        executed_sql=repaired_sql,
        repair_history=(
            {
                "attempt": 1,
                "source_sql": source_sql,
                "repaired_sql": repaired_sql,
                "execution_error": error_text,
            },
        ),
    ).event

    attempt = event.repair.attempts[0]

    assert_equal(
        attempt.source_sql_fingerprint,
        fingerprint_text(
            source_sql,
            namespace="repair_source_sql",
            audit_secret=AUDIT_SECRET,
        ),
        "Repair source SQL must use the keyed fingerprint contract.",
    )

    assert_equal(
        attempt.repaired_sql_fingerprint,
        fingerprint_text(
            repaired_sql,
            namespace="repair_output_sql",
            audit_secret=AUDIT_SECRET,
        ),
        "Repaired SQL must use the keyed fingerprint contract.",
    )

    assert_equal(
        attempt.execution_error_fingerprint,
        fingerprint_text(
            error_text,
            namespace="repair_execution_error",
            audit_secret=AUDIT_SECRET,
        ),
        "Repair error must use the keyed fingerprint contract.",
    )


def test_invalid_audit_input_message_does_not_echo_supplied_value() -> None:
    malicious_value = "TOP_SECRET_RAW_VALUE_SHOULD_NOT_ECHO"

    result = build_audit_event(
        context=build_context(),
        question="test",
        authorization=allowed_authorization(),
        execution=successful_execution(),
        protection=successful_protection(),
        metric_name={"payload": malicious_value},  # type: ignore[arg-type]
        audit_secret=AUDIT_SECRET,
        event_id="audit-event-invalid-input",
        occurred_at_utc=FIXED_TIME,
    )

    assert_equal(
        result.success,
        False,
        "Invalid audit input must fail closed.",
    )

    assert_equal(
        result.reason_code,
        AuditBuildReason.INVALID_AUDIT_INPUT,
        "Invalid input must use a stable audit reason.",
    )

    assert_true(
        malicious_value not in result.message,
        "Audit build failure message must not echo supplied raw values.",
    )


def test_hardened_audit_event_uses_v2_schema_version() -> None:
    event = build_success_event().event

    assert_equal(
        event.audit_schema_version,
        "audit_event_v2",
        "HMAC fingerprint semantics require a versioned audit schema.",
    )

def run_tests() -> None:
    tests = [
        test_actor_ref_is_deterministic,
        test_missing_audit_secret_fails_closed,
        test_success_event_is_built,
        test_success_event_is_immutable,
        test_authorization_denial_is_blocked,
        test_execution_governance_failure_is_blocked,
        test_result_protection_failure_is_blocked,
        test_missing_execution_evidence_fails_audit_build,
        test_missing_protection_evidence_fails_audit_build,
        test_raw_question_and_sql_are_not_serialized,
        test_result_rows_are_not_serialized,
        test_audit_secret_is_not_serialized,
        test_repair_history_is_fingerprinted_only,
        test_scope_values_are_sorted_deterministically,
        test_event_fingerprint_is_stable,
        test_changed_executed_sql_changes_event_fingerprint,
        test_generated_and_executed_sql_can_differ,
        test_protection_summary_contains_no_rows,
        test_naive_timestamp_is_rejected_structurally,
        test_input_repair_history_is_not_mutated,
        test_sensitive_fingerprint_is_deterministic,
        test_sensitive_fingerprint_changes_with_secret,
        test_sensitive_fingerprint_is_domain_separated,
        test_repair_fingerprints_follow_hmac_contract,
        test_invalid_audit_input_message_does_not_echo_supplied_value,
        test_hardened_audit_event_uses_v2_schema_version,
    ]

    passed = 0
    failed = 0

    for test in tests:
        print("=" * 80)
        print(f"Running: {test.__name__}")

        try:
            test()
            passed += 1
            print("[PASS]")
        except Exception as exc:
            failed += 1
            print("[FAIL]")
            print(exc)

    print("=" * 80)
    print("Audit Event Test Summary")
    print(f"Total: {len(tests)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    run_tests()
