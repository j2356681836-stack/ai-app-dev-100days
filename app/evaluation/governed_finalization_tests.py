import json
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from pydantic import ValidationError

from app.governance.access_context import (
    AccessContext,
    AccessRole,
    OperationMode,
    SensitiveDataPolicy,
)
from app.governance.authorization import (
    AuthorizationDecision,
    AuthorizationReason,
)
from app.governance.audit_sink import verify_audit_log
from app.governance.execution_budget import (
    ExecutionBudgetPolicy,
    create_initial_budget_state,
)
from app.governance.execution_policy import (
    ExecutionErrorType,
    GovernedExecutionResult,
)
from app.governance.governance_runtime import (
    GovernanceRuntimeConfig,
)
from app.governance.governed_finalization import (
    FinalizationOutcome,
    FinalizationReason,
    finalize_governed_request,
)
from app.governance.sensitive_data import (
    ResultFieldBinding,
    ResultProtectionContract,
    ResultShape,
    SensitiveDataCategory,
)


FIXED_TIME = datetime(
    2026,
    7,
    25,
    14,
    0,
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
        request_id="req-finalization-001",
        actor_id="analyst-001",
        role=AccessRole.SCOPED_ANALYST,
        dataset_name="beauty_bi_v2",
        target_schema="beauty_bi_v2",
        operation_mode=OperationMode.OBSERVE_ADVISE,
        allowed_metrics=frozenset({"order_count"}),
        allowed_tables=frozenset({
            "fact_orders",
            "dim_channel",
            "dim_customer",
            "fact_reviews",
        }),
        allowed_columns=frozenset({
            "fact_orders.order_id",
            "dim_channel.channel_name",
            "dim_customer.customer_code",
            "fact_reviews.review_text",
        }),
        denied_columns=frozenset(),
        allowed_region_codes=frozenset({"EAST"}),
        allowed_channel_codes=frozenset({"TMALL"}),
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
        reason_code=AuthorizationReason.COLUMN_NOT_ALLOWED,
        message="Denied.",
        denied_columns=frozenset({
            "fact_orders.customer_id",
        }),
        policy_version="access_policy_v1",
        retryable=False,
    )


def build_config(path: Path) -> GovernanceRuntimeConfig:
    return GovernanceRuntimeConfig(
        result_tokenization_secret=(
            "result-tokenization-secret-32-chars"
        ),
        audit_secret="audit-secret-32-characters-long",
        audit_log_path=path,
        create_parent_directory=True,
        fsync_enabled=True,
    )


def successful_execution(
    rows,
) -> GovernedExecutionResult:
    normalized = tuple(dict(row) for row in rows)

    return GovernedExecutionResult(
        success=True,
        rows=normalized,
        row_count=len(normalized),
        observed_row_count=len(normalized),
        error_type=None,
        message=None,
        retryable=False,
        execution_time_ms=12.0,
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


def ordinary_contract() -> ResultProtectionContract:
    return ResultProtectionContract(
        field_bindings=(
            ResultFieldBinding(
                output_field="channel_name",
                source_columns=frozenset({
                    "dim_channel.channel_name",
                }),
                category=SensitiveDataCategory.ORDINARY,
            ),
            ResultFieldBinding(
                output_field="order_count",
                source_columns=frozenset({
                    "fact_orders.order_id",
                }),
                category=SensitiveDataCategory.ORDINARY,
            ),
        ),
        result_shape=ResultShape.AGGREGATE,
    )


def pseudonymous_contract() -> ResultProtectionContract:
    return ResultProtectionContract(
        field_bindings=(
            ResultFieldBinding(
                output_field="customer_code",
                source_columns=frozenset({
                    "dim_customer.customer_code",
                }),
                category=(
                    SensitiveDataCategory
                    .PSEUDONYMOUS_IDENTIFIER
                ),
                token_namespace="customer",
            ),
        ),
        result_shape=ResultShape.DETAIL,
    )


def free_text_contract() -> ResultProtectionContract:
    return ResultProtectionContract(
        field_bindings=(
            ResultFieldBinding(
                output_field="review_text",
                source_columns=frozenset({
                    "fact_reviews.review_text",
                }),
                category=SensitiveDataCategory.FREE_TEXT,
            ),
        ),
        result_shape=ResultShape.DETAIL,
    )


def build_success(
    path: Path,
    *,
    execution=None,
    contract=None,
):
    active_execution = execution or successful_execution([
        {
            "channel_name": "天猫",
            "order_count": 10,
        }
    ])

    return finalize_governed_request(
        context=build_context(),
        question="各渠道订单数排名",
        authorization=allowed_authorization(),
        runtime_config=build_config(path),
        required_tables=(
            "fact_orders",
            "dim_channel",
        ),
        required_columns=(
            "fact_orders.order_id",
            "dim_channel.channel_name",
        ),
        metric_name="order_count",
        generated_sql="SELECT channel_name, COUNT(*)",
        executed_sql="SELECT channel_name, COUNT(*)",
        execution=active_execution,
        protection_contract=(
            contract or ordinary_contract()
        ),
        budget=create_initial_budget_state(
            ExecutionBudgetPolicy()
        ),
        event_id="finalization-event-001",
        occurred_at_utc=FIXED_TIME,
        written_at_utc=FIXED_TIME,
    )


def test_success_releases_only_protected_rows() -> None:
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "audit.jsonl"
        result = build_success(path)

        assert_equal(
            result.success,
            True,
            "Successful finalization should release rows.",
        )

        assert_equal(
            result.outcome,
            FinalizationOutcome.SUCCEEDED,
            "Successful path needs succeeded outcome.",
        )

        assert_equal(
            result.rows,
            ({"channel_name": "天猫", "order_count": 10},),
            "Protected rows should be released unchanged.",
        )

        assert_equal(
            result.audit_persisted,
            True,
            "Audit must persist before release.",
        )


def test_pseudonymous_value_is_tokenized_before_release() -> None:
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "audit.jsonl"

        result = build_success(
            path,
            execution=successful_execution([
                {"customer_code": "CUS-000001"}
            ]),
            contract=pseudonymous_contract(),
        )

        token = result.rows[0]["customer_code"]

        assert_true(
            token.startswith("TOK_"),
            "Released identifier must be tokenized.",
        )

        assert_true(
            "CUS-000001" not in token,
            "Original identifier must not be released.",
        )


def test_authorization_denial_is_audited_and_blocked() -> None:
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "audit.jsonl"

        result = finalize_governed_request(
            context=build_context(),
            question="返回所有客户ID",
            authorization=denied_authorization(),
            runtime_config=build_config(path),
            required_tables=("fact_orders",),
            required_columns=(
                "fact_orders.customer_id",
            ),
            event_id="finalization-auth-block",
            occurred_at_utc=FIXED_TIME,
            written_at_utc=FIXED_TIME,
        )

        assert_equal(
            result.outcome,
            FinalizationOutcome.BLOCKED,
            "Authorization denial should be blocked.",
        )

        assert_equal(
            result.reason_code,
            FinalizationReason.AUTHORIZATION_BLOCKED,
            "Authorization block needs stable reason.",
        )

        assert_equal(
            result.audit_persisted,
            True,
            "Authorization block must be audited.",
        )

        assert_equal(
            result.rows,
            (),
            "Blocked request cannot release rows.",
        )


def test_authorization_denial_with_execution_is_invalid() -> None:
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "audit.jsonl"

        result = finalize_governed_request(
            context=build_context(),
            question="返回所有客户ID",
            authorization=denied_authorization(),
            runtime_config=build_config(path),
            generated_sql="SELECT customer_id",
            executed_sql="SELECT customer_id",
            execution=successful_execution([
                {"customer_id": 1}
            ]),
        )

        assert_equal(
            result.outcome,
            FinalizationOutcome.FAILED,
            "Contradictory authorization evidence must fail.",
        )

        assert_equal(
            result.reason_code,
            FinalizationReason.INVALID_FINALIZATION_INPUT,
            "Invalid state needs stable reason.",
        )

        assert_equal(
            path.exists(),
            False,
            "Invalid finalization must not create false audit evidence.",
        )


def test_execution_failure_is_audited_and_blocked() -> None:
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "audit.jsonl"

        result = finalize_governed_request(
            context=build_context(),
            question="导出所有订单",
            authorization=allowed_authorization(),
            runtime_config=build_config(path),
            generated_sql="SELECT * FROM fact_orders",
            executed_sql="SELECT * FROM fact_orders",
            execution=failed_execution(),
            event_id="finalization-execution-block",
            occurred_at_utc=FIXED_TIME,
            written_at_utc=FIXED_TIME,
        )

        assert_equal(
            result.outcome,
            FinalizationOutcome.BLOCKED,
            "Execution governance failure should block.",
        )

        assert_equal(
            result.reason_code,
            FinalizationReason.EXECUTION_BLOCKED,
            "Execution block needs stable reason.",
        )

        assert_equal(
            result.blocked_reason,
            "result_too_large",
            "Execution reason should be retained.",
        )


def test_result_protection_failure_is_audited() -> None:
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "audit.jsonl"

        result = build_success(
            path,
            execution=successful_execution([
                {"review_text": "联系电话 13800000000"}
            ]),
            contract=free_text_contract(),
        )

        assert_equal(
            result.outcome,
            FinalizationOutcome.BLOCKED,
            "Protection failure should block.",
        )

        assert_equal(
            result.reason_code,
            FinalizationReason.RESULT_PROTECTION_BLOCKED,
            "Protection block needs stable reason.",
        )

        assert_equal(
            result.blocked_reason,
            "free_text_not_allowed",
            "Protection reason should be retained.",
        )

        assert_equal(
            result.audit_persisted,
            True,
            "Protection block must be audited.",
        )


def test_missing_protection_contract_fails_closed() -> None:
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "audit.jsonl"

        result = finalize_governed_request(
            context=build_context(),
            question="各渠道订单数排名",
            authorization=allowed_authorization(),
            runtime_config=build_config(path),
            generated_sql="SELECT 1",
            executed_sql="SELECT 1",
            execution=successful_execution([{"value": 1}]),
            protection_contract=None,
        )

        assert_equal(
            result.reason_code,
            FinalizationReason.INVALID_FINALIZATION_INPUT,
            "Missing protection contract must fail.",
        )

        assert_equal(
            result.rows,
            (),
            "Missing protection contract cannot release rows.",
        )


def test_missing_sql_evidence_fails_closed() -> None:
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "audit.jsonl"

        result = finalize_governed_request(
            context=build_context(),
            question="各渠道订单数排名",
            authorization=allowed_authorization(),
            runtime_config=build_config(path),
            execution=successful_execution([
                {"channel_name": "天猫", "order_count": 10}
            ]),
            protection_contract=ordinary_contract(),
        )

        assert_equal(
            result.reason_code,
            FinalizationReason.INVALID_FINALIZATION_INPUT,
            "Executed request needs SQL evidence.",
        )


def test_corrupted_audit_log_prevents_row_release() -> None:
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "audit.jsonl"
        path.write_text(
            '{"corrupted":true}\n',
            encoding="utf-8",
        )

        result = build_success(path)

        assert_equal(
            result.outcome,
            FinalizationOutcome.FAILED,
            "Audit persistence failure must fail finalization.",
        )

        assert_equal(
            result.reason_code,
            FinalizationReason.AUDIT_PERSISTENCE_FAILED,
            "Corrupt log should surface persistence failure.",
        )

        assert_equal(
            result.rows,
            (),
            "Rows must not release when audit persistence fails.",
        )

        assert_equal(
            result.audit_persisted,
            False,
            "Failed sink cannot claim persisted evidence.",
        )


def test_successful_log_contains_no_released_row_values() -> None:
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "audit.jsonl"
        build_success(path)

        log_text = path.read_text(encoding="utf-8")

        assert_true(
            "天猫" not in log_text,
            "Audit log must not contain result row values.",
        )


def test_pseudonymous_raw_value_does_not_enter_log() -> None:
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "audit.jsonl"

        build_success(
            path,
            execution=successful_execution([
                {"customer_code": "CUS-000001"}
            ]),
            contract=pseudonymous_contract(),
        )

        log_text = path.read_text(encoding="utf-8")

        assert_true(
            "CUS-000001" not in log_text,
            "Raw identifier must not enter audit log.",
        )


def test_audit_chain_verifies_after_finalization() -> None:
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "audit.jsonl"
        build_success(path)

        verification = verify_audit_log(path)

        assert_equal(
            verification.success,
            True,
            "Finalization must produce a valid audit chain.",
        )

        assert_equal(
            verification.record_count,
            1,
            "One request should create one audit record.",
        )


def test_finalization_result_is_immutable() -> None:
    with TemporaryDirectory() as tmp:
        result = build_success(
            Path(tmp) / "audit.jsonl"
        )

        try:
            result.success = False
        except ValidationError:
            return

        raise AssertionError(
            "GovernedFinalizationResult must be immutable."
        )


def test_repair_summary_is_preserved_without_raw_content() -> None:
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "audit.jsonl"
        source_sql = "SELECT bad_column FROM fact_orders"
        repaired_sql = "SELECT order_id FROM fact_orders"
        error_text = "column bad_column does not exist"

        result = finalize_governed_request(
            context=build_context(),
            question="订单查询",
            authorization=allowed_authorization(),
            runtime_config=build_config(path),
            generated_sql=source_sql,
            executed_sql=repaired_sql,
            execution=successful_execution([
                {"channel_name": "天猫", "order_count": 10}
            ]),
            protection_contract=ordinary_contract(),
            repair_history=(
                {
                    "attempt": 1,
                    "source_sql": source_sql,
                    "repaired_sql": repaired_sql,
                    "execution_error": error_text,
                },
            ),
            event_id="finalization-repair-event",
            occurred_at_utc=FIXED_TIME,
            written_at_utc=FIXED_TIME,
        )

        assert_equal(
            result.success,
            True,
            "Repaired successful request should finalize.",
        )

        payload = json.loads(
            path.read_text(encoding="utf-8").splitlines()[0]
        )

        assert_equal(
            payload["event"]["repair"]["attempt_count"],
            1,
            "Repair attempt count should be audited.",
        )

        serialized = json.dumps(payload, ensure_ascii=False)

        for raw_value in (
            source_sql,
            repaired_sql,
            error_text,
        ):
            assert_true(
                raw_value not in serialized,
                "Raw repair content must not enter audit log.",
            )


def run_tests() -> None:
    tests = [
        test_success_releases_only_protected_rows,
        test_pseudonymous_value_is_tokenized_before_release,
        test_authorization_denial_is_audited_and_blocked,
        test_authorization_denial_with_execution_is_invalid,
        test_execution_failure_is_audited_and_blocked,
        test_result_protection_failure_is_audited,
        test_missing_protection_contract_fails_closed,
        test_missing_sql_evidence_fails_closed,
        test_corrupted_audit_log_prevents_row_release,
        test_successful_log_contains_no_released_row_values,
        test_pseudonymous_raw_value_does_not_enter_log,
        test_audit_chain_verifies_after_finalization,
        test_finalization_result_is_immutable,
        test_repair_summary_is_preserved_without_raw_content,
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
    print("Governed Finalization Test Summary")
    print(f"Total: {len(tests)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    run_tests()
