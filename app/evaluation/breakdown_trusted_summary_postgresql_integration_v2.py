from __future__ import annotations

from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from app.delivery.breakdown_trusted_summary_v2 import (
    TrustedBreakdownSummaryStatusV2,
)
from app.delivery.decision_console_runtime_v2 import (
    run_day89_breakdown_summary_v2,
    run_day89_local_investigation_v2,
)
from app.governance.audit_sink import verify_audit_log
from app.governance.execution_policy import GovernedExecutionPolicy
from app.governance.governance_runtime import GovernanceRuntimeConfig


REFERENCE_DATE = date(2026, 8, 19)
QUESTION = "2025年各渠道GMV是多少？"

EXECUTION_POLICY = GovernedExecutionPolicy(
    statement_timeout_ms=30_000,
    max_rows=20,
)


def _runtime_config(
    audit_path: Path,
) -> GovernanceRuntimeConfig:
    return GovernanceRuntimeConfig(
        result_tokenization_secret=(
            "day89-summary-tokenization-secret-32-chars"
        ),
        audit_secret=(
            "day89-summary-audit-secret-32-characters"
        ),
        audit_log_path=audit_path,
        create_parent_directory=True,
        fsync_enabled=True,
    )


def test_real_breakdown_has_independent_trusted_total() -> None:
    with TemporaryDirectory() as tmp:
        audit_path = (
            Path(tmp)
            / "day89_breakdown_summary_audit.jsonl"
        )
        config = _runtime_config(audit_path)

        primary = run_day89_local_investigation_v2(
            question=QUESTION,
            reference_date=REFERENCE_DATE,
            runtime_config=config,
            execution_policy=EXECUTION_POLICY,
        )

        assert primary.console_view is not None
        assert primary.console_view.breakdown is not None

        summary_result = run_day89_breakdown_summary_v2(
            primary_result=primary,
            reference_date=REFERENCE_DATE,
            runtime_config=config,
            execution_policy=EXECUTION_POLICY,
        )

        assert (
            summary_result.status
            == TrustedBreakdownSummaryStatusV2.READY
        )
        assert summary_result.summary is not None

        summary = summary_result.summary
        breakdown = primary.console_view.breakdown

        assert summary.metric_name == breakdown.metric_name
        assert summary.analysis_window == breakdown.analysis_window
        assert summary.plan_name == "gmv_overall_v2"
        assert summary.evidence_id != breakdown.evidence_id
        assert summary.audit_event_id != breakdown.audit_event_id
        assert summary.value > 0

        # 两个独立 Governed Query，各有一条 Audit。
        verification = verify_audit_log(audit_path)
        assert verification.success
        assert verification.record_count == 2

        # Summary safe result 仍不暴露 rows / SQL。
        dumped = str(
            summary_result.safe_overall_runtime_result
        ).lower()

        assert "select " not in dumped
        assert " from " not in dumped
        assert (
            "rows"
            not in summary_result.safe_overall_runtime_result
        )


TESTS = (
    test_real_breakdown_has_independent_trusted_total,
)


def run_acceptance() -> None:
    print("Day89 Trusted Breakdown Summary PostgreSQL Integration")

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

    print(f"Total: {len(TESTS)}")
    print(f"Passed: {passed}")
    print(f"Failed: {len(failures)}")

    for failure in failures:
        print(f"- {failure}")

    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    run_acceptance()
