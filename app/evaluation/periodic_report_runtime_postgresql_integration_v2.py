from __future__ import annotations

from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from app.delivery.decision_console_runtime_v2 import (
    run_day89_monthly_gmv_report_v2,
)
from app.delivery.runtime_comparison_delivery_v2 import (
    RuntimeComparisonDeliveryStatusV2,
)
from app.governance.audit_sink import verify_audit_log
from app.governance.execution_policy import GovernedExecutionPolicy
from app.governance.governance_runtime import GovernanceRuntimeConfig
from app.semantic_layer.time_comparison_contract_v2 import (
    ComparisonTypeV2,
)


ANCHOR_DATE = date(2025, 7, 31)

INTEGRATION_EXECUTION_POLICY = GovernedExecutionPolicy(
    statement_timeout_ms=30_000,
    max_rows=10,
)


def _runtime_config(
    audit_path: Path,
) -> GovernanceRuntimeConfig:
    return GovernanceRuntimeConfig(
        result_tokenization_secret=(
            "day89-monthly-tokenization-secret-32-chars"
        ),
        audit_secret=(
            "day89-monthly-audit-secret-32-characters"
        ),
        audit_log_path=audit_path,
        create_parent_directory=True,
        fsync_enabled=True,
    )


def test_real_monthly_gmv_mom_delivery() -> None:
    with TemporaryDirectory() as tmp:
        audit_path = (
            Path(tmp)
            / "day89_monthly_gmv_mom_audit.jsonl"
        )

        result = run_day89_monthly_gmv_report_v2(
            anchor_date=ANCHOR_DATE,
            runtime_config=_runtime_config(audit_path),
            execution_policy=INTEGRATION_EXECUTION_POLICY,
        )

        assert (
            result.status
            == RuntimeComparisonDeliveryStatusV2.READY
        )
        assert result.metric_comparison_result is not None
        assert result.delivery is not None
        assert result.console_view is not None
        assert result.executive_brief is not None

        comparison = result.metric_comparison_result
        view = result.console_view

        assert (
            comparison.comparison.comparison_type
            == ComparisonTypeV2.MOM
        )
        assert (
            comparison.comparison.current_window.start_date
            == date(2025, 7, 1)
        )
        assert (
            comparison.comparison.current_window.end_date
            == date(2025, 7, 31)
        )
        assert (
            comparison.comparison.reference_window.start_date
            == date(2025, 6, 1)
        )
        assert (
            comparison.comparison.reference_window.end_date
            == date(2025, 6, 30)
        )

        assert comparison.current_evidence_id != (
            comparison.reference_evidence_id
        )

        assert view.comparison is not None
        assert view.verification is not None
        assert view.breakdown is None

        assert (
            view.comparison.current_value
            == comparison.current_value
        )
        assert (
            view.comparison.reference_value
            == comparison.reference_value
        )
        assert (
            view.comparison.absolute_change
            == comparison.absolute_change
        )
        assert (
            view.comparison.relative_change
            == comparison.relative_change
        )

        assert (
            view.verification.current_evidence.analysis_window
            == comparison.comparison.current_window
        )
        assert (
            view.verification.reference_evidence.analysis_window
            == comparison.comparison.reference_window
        )
        assert (
            view.verification.current_evidence.audit_event_id
            != view.verification.reference_evidence.audit_event_id
        )

        records = result.delivery.evidence_pack.evidence_records
        assert len(records) == 2

        for record in records:
            assert record.protected_result is not None
            assert record.protected_result.field_names == ("gmv",)
            assert record.protected_result.row_count == 1

        current_dump = str(
            result.current_safe_runtime_result
        ).lower()
        reference_dump = str(
            result.reference_safe_runtime_result
        ).lower()

        for dumped in (current_dump, reference_dump):
            assert "select " not in dumped
            assert " from " not in dumped

        assert "rows" not in result.current_safe_runtime_result
        assert "rows" not in result.reference_safe_runtime_result

        verification = verify_audit_log(audit_path)
        assert verification.success
        assert verification.record_count == 2


TESTS = (
    test_real_monthly_gmv_mom_delivery,
)


def run_acceptance() -> None:
    print("Day89 Monthly GMV MoM PostgreSQL Integration")

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
