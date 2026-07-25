import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from pydantic import ValidationError

from app.governance.audit_event import (
    AuditEvent,
    AuditOutcome,
    AuthorizationAuditSummary,
    ExecutionAuditSummary,
    PolicyVersionSnapshot,
    ProtectionAuditSummary,
    RepairAuditSummary,
    ScopeAuditSnapshot,
)
from app.governance.audit_sink import (
    AuditLogRecord,
    AuditSinkReason,
    append_audit_event,
    verify_audit_log,
)
from app.governance.governance_runtime import (
    GovernanceConfigurationError,
    GovernanceRuntimeConfig,
    load_governance_runtime_config,
)


FIXED_TIME = datetime(
    2026,
    7,
    25,
    12,
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


def build_event(
    event_id: str,
    *,
    event_fingerprint: str | None = None,
) -> AuditEvent:
    return AuditEvent(
        event_id=event_id,
        request_id=f"request-{event_id}",
        occurred_at_utc=FIXED_TIME,
        actor_ref="ACT_1234567890abcdef12345678",
        scope=ScopeAuditSnapshot(
            role="scoped_analyst",
            dataset_name="beauty_bi_v2",
            target_schema="beauty_bi_v2",
            operation_mode="observe_advise",
            allowed_region_codes=("EAST",),
            allowed_channel_codes=("TMALL",),
            metric_name="order_count",
            required_tables=("fact_orders",),
            required_columns=(
                "fact_orders.order_id",
            ),
        ),
        policies=PolicyVersionSnapshot(
            access_policy_version="access_policy_v1",
            execution_policy_version=(
                "execution_governance_v1"
            ),
            protection_policy_version=(
                "result_protection_v1"
            ),
        ),
        question_fingerprint=(
            "a" * 64
        ),
        question_length=8,
        generated_sql_fingerprint="b" * 64,
        executed_sql_fingerprint="b" * 64,
        authorization=AuthorizationAuditSummary(
            allowed=True,
            error_type=None,
            reason_code="allowed",
            denied_metrics=(),
            denied_tables=(),
            denied_columns=(),
            explicitly_denied_columns=(),
            retryable=False,
        ),
        execution=ExecutionAuditSummary(
            success=True,
            error_type=None,
            execution_time_ms=10.0,
            row_count=1,
            observed_row_count=1,
            statement_timeout_ms=5_000,
            max_rows=200,
            retryable=False,
        ),
        budget=None,
        protection=ProtectionAuditSummary(
            success=True,
            error_type=None,
            reason_code="allowed",
            row_count=1,
            tokenized_fields=(),
            allowed_sensitive_fields=(),
            rejected_fields=(),
            minimum_group_size_checked=False,
            minimum_observed_group_size=None,
            contract_fingerprint="c" * 64,
            protection_fingerprint="d" * 64,
            retryable=False,
        ),
        repair=RepairAuditSummary(
            attempt_count=0,
            attempts=(),
        ),
        outcome=AuditOutcome.SUCCEEDED,
        blocked_stage=None,
        blocked_reason=None,
        event_fingerprint=(
            event_fingerprint
            or ("e" * 63 + str(len(event_id) % 10))
        ),
        retryable=False,
        audit_schema_version="audit_event_v1",
    )


def test_runtime_config_masks_secrets() -> None:
    with TemporaryDirectory() as tmp:
        config = build_config(
            Path(tmp) / "audit.jsonl"
        )

        rendered = repr(config)
        serialized = config.model_dump_json()

        assert_true(
            "result-tokenization-secret" not in rendered,
            "repr must mask tokenization secret.",
        )

        assert_true(
            "audit-secret-32" not in rendered,
            "repr must mask audit secret.",
        )

        assert_true(
            "result-tokenization-secret" not in serialized,
            "JSON must mask tokenization secret.",
        )

        assert_true(
            "audit-secret-32" not in serialized,
            "JSON must mask audit secret.",
        )


def test_runtime_config_loads_from_mapping() -> None:
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "audit.jsonl"

        config = load_governance_runtime_config({
            "AI_RESULT_TOKENIZATION_SECRET": (
                "result-tokenization-secret-32-chars"
            ),
            "AI_AUDIT_SECRET": (
                "audit-secret-32-characters-long"
            ),
            "AI_AUDIT_LOG_PATH": str(path),
        })

        assert_equal(
            config.audit_log_path,
            path,
            "Configured audit path should be loaded.",
        )


def test_runtime_config_missing_env_fails() -> None:
    try:
        load_governance_runtime_config({})
    except GovernanceConfigurationError:
        return

    raise AssertionError(
        "Missing governance environment must fail."
    )


def test_runtime_config_rejects_non_jsonl_path() -> None:
    try:
        GovernanceRuntimeConfig(
            result_tokenization_secret=(
                "result-tokenization-secret-32-chars"
            ),
            audit_secret=(
                "audit-secret-32-characters-long"
            ),
            audit_log_path=Path("audit.log"),
        )
    except ValidationError:
        return

    raise AssertionError(
        "Audit path without .jsonl must fail."
    )


def test_empty_or_missing_log_verifies() -> None:
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "audit.jsonl"

        missing = verify_audit_log(path)

        assert_equal(
            missing.success,
            True,
            "Missing log should verify as empty.",
        )

        path.touch()
        empty = verify_audit_log(path)

        assert_equal(
            empty.record_count,
            0,
            "Empty log should have zero records.",
        )


def test_first_event_is_appended() -> None:
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "audit.jsonl"
        config = build_config(path)

        result = append_audit_event(
            event=build_event("event-001"),
            config=config,
            written_at_utc=FIXED_TIME,
        )

        assert_equal(
            result.success,
            True,
            "First append should succeed.",
        )

        assert_equal(
            result.sequence_number,
            1,
            "First sequence must be one.",
        )

        assert_true(
            path.exists(),
            "Audit log should be created.",
        )

        assert_true(
            path.read_bytes().endswith(b"\n"),
            "Audit record must end with newline.",
        )


def test_second_event_links_to_first() -> None:
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "audit.jsonl"
        config = build_config(path)

        first = append_audit_event(
            event=build_event("event-001"),
            config=config,
            written_at_utc=FIXED_TIME,
        )

        second = append_audit_event(
            event=build_event("event-002"),
            config=config,
            written_at_utc=FIXED_TIME,
        )

        lines = path.read_text(
            encoding="utf-8"
        ).splitlines()

        second_record = AuditLogRecord.model_validate(
            json.loads(lines[1])
        )

        assert_equal(
            second.sequence_number,
            2,
            "Second sequence must be two.",
        )

        assert_equal(
            second_record.previous_record_hash,
            first.record_hash,
            "Second record must link to first hash.",
        )


def test_complete_chain_verifies() -> None:
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "audit.jsonl"
        config = build_config(path)

        for index in range(1, 4):
            append_audit_event(
                event=build_event(
                    f"event-{index:03d}"
                ),
                config=config,
                written_at_utc=FIXED_TIME,
            )

        verification = verify_audit_log(path)

        assert_equal(
            verification.success,
            True,
            "Valid chain should verify.",
        )

        assert_equal(
            verification.record_count,
            3,
            "All records should be counted.",
        )


def test_tampered_record_is_detected() -> None:
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "audit.jsonl"
        config = build_config(path)

        append_audit_event(
            event=build_event("event-001"),
            config=config,
            written_at_utc=FIXED_TIME,
        )

        payload = json.loads(
            path.read_text(
                encoding="utf-8"
            ).splitlines()[0]
        )
        payload["event"]["request_id"] = "tampered"

        path.write_text(
            json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
            )
            + "\n",
            encoding="utf-8",
        )

        verification = verify_audit_log(path)

        assert_equal(
            verification.success,
            False,
            "Tampering must break verification.",
        )

        assert_equal(
            verification.reason_code,
            AuditSinkReason.AUDIT_LOG_CORRUPTED,
            "Tampering needs a stable reason.",
        )


def test_deleted_first_record_is_detected() -> None:
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "audit.jsonl"
        config = build_config(path)

        append_audit_event(
            event=build_event("event-001"),
            config=config,
            written_at_utc=FIXED_TIME,
        )
        append_audit_event(
            event=build_event("event-002"),
            config=config,
            written_at_utc=FIXED_TIME,
        )

        lines = path.read_text(
            encoding="utf-8"
        ).splitlines()

        path.write_text(
            lines[1] + "\n",
            encoding="utf-8",
        )

        verification = verify_audit_log(path)

        assert_equal(
            verification.success,
            False,
            "Deleting first record must break sequence.",
        )


def test_incomplete_final_line_is_detected() -> None:
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "audit.jsonl"
        config = build_config(path)

        append_audit_event(
            event=build_event("event-001"),
            config=config,
            written_at_utc=FIXED_TIME,
        )

        raw = path.read_bytes()
        path.write_bytes(raw[:-1])

        verification = verify_audit_log(path)

        assert_equal(
            verification.success,
            False,
            "Missing final newline must be detected.",
        )


def test_append_refuses_corrupted_log() -> None:
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "audit.jsonl"
        config = build_config(path)

        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        path.write_text(
            '{"invalid":true}\n',
            encoding="utf-8",
        )

        result = append_audit_event(
            event=build_event("event-001"),
            config=config,
            written_at_utc=FIXED_TIME,
        )

        assert_equal(
            result.success,
            False,
            "Sink must not append after corruption.",
        )

        assert_equal(
            result.reason_code,
            AuditSinkReason.AUDIT_LOG_CORRUPTED,
            "Corrupt log must use stable reason.",
        )

        assert_equal(
            len(path.read_text(
                encoding="utf-8"
            ).splitlines()),
            1,
            "Failed append must not add another line.",
        )


def test_naive_write_timestamp_is_rejected() -> None:
    with TemporaryDirectory() as tmp:
        config = build_config(
            Path(tmp) / "audit.jsonl"
        )

        result = append_audit_event(
            event=build_event("event-001"),
            config=config,
            written_at_utc=datetime(
                2026,
                7,
                25,
                12,
                0,
            ),
        )

        assert_equal(
            result.reason_code,
            AuditSinkReason.INVALID_SINK_INPUT,
            "Naive timestamp must be rejected.",
        )


def test_secrets_do_not_enter_audit_log() -> None:
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "audit.jsonl"
        config = build_config(path)

        append_audit_event(
            event=build_event("event-001"),
            config=config,
            written_at_utc=FIXED_TIME,
        )

        log_text = path.read_text(encoding="utf-8")

        assert_true(
            config.audit_secret.get_secret_value()
            not in log_text,
            "Audit secret must not enter JSONL.",
        )

        assert_true(
            config.result_tokenization_secret
            .get_secret_value()
            not in log_text,
            "Tokenization secret must not enter JSONL.",
        )


def test_input_event_is_not_mutated() -> None:
    with TemporaryDirectory() as tmp:
        config = build_config(
            Path(tmp) / "audit.jsonl"
        )
        event = build_event("event-001")
        before = event.model_dump(mode="json")

        append_audit_event(
            event=event,
            config=config,
            written_at_utc=FIXED_TIME,
        )

        assert_equal(
            event.model_dump(mode="json"),
            before,
            "Audit sink must not mutate AuditEvent.",
        )


def test_concurrent_appends_form_valid_chain() -> None:
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "audit.jsonl"
        config = build_config(path)

        def append_one(index: int):
            return append_audit_event(
                event=build_event(
                    f"event-{index:03d}",
                    event_fingerprint=(
                        f"{index:064x}"
                    ),
                ),
                config=config,
                written_at_utc=FIXED_TIME,
            )

        with ThreadPoolExecutor(
            max_workers=8
        ) as executor:
            results = list(
                executor.map(
                    append_one,
                    range(1, 21),
                )
            )

        assert_true(
            all(result.success for result in results),
            "All concurrent appends should succeed.",
        )

        verification = verify_audit_log(path)

        assert_equal(
            verification.success,
            True,
            "Concurrent writes must preserve hash chain.",
        )

        assert_equal(
            verification.record_count,
            20,
            "All concurrent events must be persisted.",
        )

        sequence_numbers = sorted(
            result.sequence_number
            for result in results
        )

        assert_equal(
            sequence_numbers,
            list(range(1, 21)),
            "Concurrent sequence numbers must be continuous.",
        )


def run_tests() -> None:
    tests = [
        test_runtime_config_masks_secrets,
        test_runtime_config_loads_from_mapping,
        test_runtime_config_missing_env_fails,
        test_runtime_config_rejects_non_jsonl_path,
        test_empty_or_missing_log_verifies,
        test_first_event_is_appended,
        test_second_event_links_to_first,
        test_complete_chain_verifies,
        test_tampered_record_is_detected,
        test_deleted_first_record_is_detected,
        test_incomplete_final_line_is_detected,
        test_append_refuses_corrupted_log,
        test_naive_write_timestamp_is_rejected,
        test_secrets_do_not_enter_audit_log,
        test_input_event_is_not_mutated,
        test_concurrent_appends_form_valid_chain,
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
    print("Audit Sink Test Summary")
    print(f"Total: {len(tests)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    run_tests()
