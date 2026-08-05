from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import app.governance.governed_query_execution_v2 as execution_service
from app.evaluation.compiled_sql_ast_enforcer_acceptance_v2 import (
    _context,
    _ready_pair,
    _rebuild_compiled,
)
from app.governance.access_context import AccessContext
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
    GovernedFinalizationResult,
)


FIXED_TIME = datetime(
    2026,
    8,
    5,
    15,
    0,
    tzinfo=timezone.utc,
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


def _successful_execution(
    rows: tuple[dict[str, Any], ...],
) -> GovernedExecutionResult:
    return GovernedExecutionResult(
        success=True,
        rows=rows,
        row_count=len(rows),
        observed_row_count=len(rows),
        error_type=None,
        message=None,
        retryable=False,
        execution_time_ms=8.0,
        target_schema="beauty_bi_v2",
        statement_timeout_ms=5_000,
        max_rows=200,
        policy_version="execution_governance_v1",
    )


def _failed_execution() -> GovernedExecutionResult:
    return GovernedExecutionResult(
        success=False,
        rows=(),
        row_count=0,
        observed_row_count=201,
        error_type=ExecutionErrorType.RESULT_TOO_LARGE,
        message=(
            "Query result exceeded the governed row limit."
        ),
        retryable=False,
        execution_time_ms=10.0,
        target_schema="beauty_bi_v2",
        statement_timeout_ms=5_000,
        max_rows=200,
        policy_version="execution_governance_v1",
    )


class _RunnerPatch:
    def __init__(
        self,
        replacement,
    ) -> None:
        self.replacement = replacement
        self.original = (
            execution_service.run_governed_sql
        )

    def __enter__(self):
        execution_service.run_governed_sql = (
            self.replacement
        )
        return self

    def __exit__(
        self,
        exc_type,
        exc,
        traceback,
    ) -> None:
        execution_service.run_governed_sql = (
            self.original
        )


def _execute(
    *,
    context: AccessContext,
    envelope,
    compiled,
    audit_log_path: Path,
) -> GovernedFinalizationResult:
    return execution_service.execute_governed_query_v2(
        context=context,
        question="GMV是多少？",
        envelope=envelope,
        compiled=compiled,
        runtime_config=(
            _runtime_config(
                audit_log_path
            )
        ),
        event_id="governed-query-execution-v2-event",
        occurred_at_utc=FIXED_TIME,
        written_at_utc=FIXED_TIME,
    )


def test_success_executes_compiled_contract_and_releases_only_safe_rows(
) -> None:
    envelope, compiled = _ready_pair(
        plan_name="gmv_overall_v2",
        question="GMV是多少？",
    )

    assert (
        envelope.result_protection_contract
        .minimum_group_size_required
    ), (
        "GMV aggregate fixture must require minimum group size."
    )

    captured: dict[str, Any] = {}

    def fake_runner(
        sql,
        parameters=None,
        policy=None,
        engine_override=None,
    ):
        captured["sql"] = sql
        captured["parameters"] = dict(
            parameters or {}
        )
        captured["policy"] = policy
        captured["engine_override"] = (
            engine_override
        )

        return _successful_execution(
            (
                {
                    "gmv": 125000.0,
                    "__group_size": 12,
                },
            )
        )

    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "audit.jsonl"

        with _RunnerPatch(fake_runner):
            result = _execute(
                context=_context(),
                envelope=envelope,
                compiled=compiled,
                audit_log_path=path,
            )

        assert result.success
        assert (
            result.outcome
            == FinalizationOutcome.SUCCEEDED
        )
        assert result.audit_persisted
        assert result.rows == (
            {
                "gmv": 125000.0,
            },
        )
        assert "__group_size" not in result.rows[0]

        assert captured["sql"] == compiled.sql
        assert (
            captured["parameters"]
            == compiled.parameter_mapping()
        )


def test_ast_failure_prevents_runner_call(
) -> None:
    envelope, compiled = _ready_pair(
        plan_name="gmv_overall_v2",
        question="GMV是多少？",
    )

    malicious_sql = compiled.sql.replace(
        "SUM(foi.item_paid_amount)",
        "PG_SLEEP(1)",
        1,
    )
    malicious = _rebuild_compiled(
        compiled,
        sql=malicious_sql,
    )

    calls = 0

    def forbidden_runner(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError(
            "Runner must not be called after AST failure."
        )

    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "audit.jsonl"

        with _RunnerPatch(forbidden_runner):
            result = _execute(
                context=_context(),
                envelope=envelope,
                compiled=malicious,
                audit_log_path=path,
            )

        assert calls == 0
        assert not result.success
        assert (
            result.outcome
            == FinalizationOutcome.FAILED
        )
        assert (
            result.reason_code
            == FinalizationReason
            .INVALID_FINALIZATION_INPUT
        )
        assert result.rows == ()
        assert not result.audit_persisted
        assert not path.exists()


def test_context_envelope_mismatch_prevents_runner_call(
) -> None:
    envelope, compiled = _ready_pair(
        plan_name="gmv_overall_v2",
        question="GMV是多少？",
    )

    payload = _context().model_dump(
        mode="python"
    )
    payload["request_id"] = (
        "different-request-id"
    )
    mismatched_context = AccessContext(
        **payload
    )

    calls = 0

    def forbidden_runner(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError(
            "Runner must not be called after linkage failure."
        )

    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "audit.jsonl"

        with _RunnerPatch(forbidden_runner):
            result = _execute(
                context=mismatched_context,
                envelope=envelope,
                compiled=compiled,
                audit_log_path=path,
            )

        assert calls == 0
        assert not result.success
        assert result.rows == ()
        assert not result.audit_persisted
        assert not path.exists()


def test_execution_failure_is_audited_and_blocks_release(
) -> None:
    envelope, compiled = _ready_pair(
        plan_name="gmv_overall_v2",
        question="GMV是多少？",
    )

    def failed_runner(*args, **kwargs):
        return _failed_execution()

    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "audit.jsonl"

        with _RunnerPatch(failed_runner):
            result = _execute(
                context=_context(),
                envelope=envelope,
                compiled=compiled,
                audit_log_path=path,
            )

        assert not result.success
        assert (
            result.outcome
            == FinalizationOutcome.BLOCKED
        )
        assert (
            result.reason_code
            == FinalizationReason.EXECUTION_BLOCKED
        )
        assert result.audit_persisted
        assert result.rows == ()
        assert path.exists()


def test_minimum_group_size_failure_is_audited(
) -> None:
    envelope, compiled = _ready_pair(
        plan_name="gmv_overall_v2",
        question="GMV是多少？",
    )

    def small_group_runner(*args, **kwargs):
        return _successful_execution(
            (
                {
                    "gmv": 100.0,
                    "__group_size": 2,
                },
            )
        )

    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "audit.jsonl"

        with _RunnerPatch(small_group_runner):
            result = _execute(
                context=_context(),
                envelope=envelope,
                compiled=compiled,
                audit_log_path=path,
            )

        assert not result.success
        assert (
            result.outcome
            == FinalizationOutcome.BLOCKED
        )
        assert (
            result.reason_code
            == FinalizationReason
            .RESULT_PROTECTION_BLOCKED
        )
        assert (
            result.blocked_reason
            == "minimum_group_size_violation"
        )
        assert result.audit_persisted
        assert result.rows == ()


def test_audit_persistence_failure_prevents_release(
) -> None:
    envelope, compiled = _ready_pair(
        plan_name="gmv_overall_v2",
        question="GMV是多少？",
    )

    def successful_runner(*args, **kwargs):
        return _successful_execution(
            (
                {
                    "gmv": 125000.0,
                    "__group_size": 12,
                },
            )
        )

    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "audit.jsonl"
        path.write_text(
            '{"corrupted":true}\n',
            encoding="utf-8",
        )

        with _RunnerPatch(successful_runner):
            result = _execute(
                context=_context(),
                envelope=envelope,
                compiled=compiled,
                audit_log_path=path,
            )

        assert not result.success
        assert (
            result.outcome
            == FinalizationOutcome.FAILED
        )
        assert (
            result.reason_code
            == FinalizationReason
            .AUDIT_PERSISTENCE_FAILED
        )
        assert not result.audit_persisted
        assert result.rows == ()


TESTS = (
    test_success_executes_compiled_contract_and_releases_only_safe_rows,
    test_ast_failure_prevents_runner_call,
    test_context_envelope_mismatch_prevents_runner_call,
    test_execution_failure_is_audited_and_blocks_release,
    test_minimum_group_size_failure_is_audited,
    test_audit_persistence_failure_prevents_release,
)


def run_acceptance() -> None:
    passed = 0
    failed = 0

    print("=" * 80)
    print(
        "Governed Query Execution V2 Acceptance"
    )
    print(
        f"Cases: {len(TESTS)}"
    )

    for test in TESTS:
        print("=" * 80)
        print(
            test.__name__
        )

        try:
            test()
        except Exception as exc:
            failed += 1
            print("[FAIL]")
            print(
                f"{type(exc).__name__}: {exc}"
            )
        else:
            passed += 1
            print("[PASS]")

    print("=" * 80)
    print(
        "Governed Query Execution V2 "
        "Acceptance Summary"
    )
    print(
        f"Total: {len(TESTS)}"
    )
    print(
        f"Passed: {passed}"
    )
    print(
        f"Failed: {failed}"
    )

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    run_acceptance()
