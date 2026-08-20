from __future__ import annotations

from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from app.agents.contribution_analysis_v2 import (
    ContributionReconciliationStatusV2,
)
from app.agents.evidence_pack_v2 import (
    EvidenceTypeV2,
)
from app.delivery.monthly_contribution_delivery_v2 import (
    MonthlyContributionDeliveryStatusV2,
    run_day89_monthly_gmv_channel_contribution_v2,
)
from app.governance.audit_sink import verify_audit_log
from app.governance.execution_policy import (
    GovernedExecutionPolicy,
)
from app.governance.governance_runtime import (
    GovernanceRuntimeConfig,
)


EXECUTION_POLICY = GovernedExecutionPolicy(
    statement_timeout_ms=30_000,
    max_rows=20,
)


def _runtime_config(
    audit_path: Path,
) -> GovernanceRuntimeConfig:
    return GovernanceRuntimeConfig(
        result_tokenization_secret=(
            "day89-contribution-token-secret-32-chars"
        ),
        audit_secret=(
            "day89-contribution-audit-secret-32-characters"
        ),
        audit_log_path=audit_path,
        create_parent_directory=True,
        fsync_enabled=True,
    )


def test_real_monthly_gmv_channel_contribution_postgresql() -> None:
    """
    真实 PostgreSQL：

    July 2025 overall + June 2025 overall
    + July 2025 channel + June 2025 channel
    -> deterministic contribution
    -> 4-parent Contribution Evidence
    -> reconciled Decision Console contribution view
    """

    with TemporaryDirectory() as tmp:
        audit_path = (
            Path(tmp)
            / "day89_monthly_contribution_audit.jsonl"
        )
        config = _runtime_config(audit_path)

        result = (
            run_day89_monthly_gmv_channel_contribution_v2(
                anchor_date=date(2025, 7, 31),
                runtime_config=config,
                execution_policy=EXECUTION_POLICY,
            )
        )

        assert (
            result.status
            == MonthlyContributionDeliveryStatusV2.READY
        ), (
            "Monthly Contribution Runtime 未 READY："
            f"status={result.status.value}; "
            f"message={result.message}; "
            f"current_channel="
            f"{result.current_channel_safe_runtime_result}; "
            f"reference_channel="
            f"{result.reference_channel_safe_runtime_result}"
        )
        assert result.delivery is not None
        assert result.console_view is not None
        assert result.contribution_result is not None

        contribution = result.contribution_result

        assert contribution.metric_name == "gmv"
        assert contribution.dimension_name == "channel"
        assert (
            contribution.reconciliation_status
            == ContributionReconciliationStatusV2.RECONCILED
        ), (
            "真实 Channel Contribution 未 reconciled："
            f"overall_delta={contribution.overall_delta}; "
            f"sum_member_delta={contribution.sum_member_delta}; "
            f"unexplained_remainder="
            f"{contribution.unexplained_remainder}"
        )
        assert abs(
            contribution.unexplained_remainder
        ) <= contribution.reconciliation_tolerance

        records = result.delivery.evidence_pack.evidence_records

        query_records = tuple(
            record
            for record in records
            if (
                record.evidence_type
                == EvidenceTypeV2.GOVERNED_QUERY_RESULT
            )
        )
        contribution_records = tuple(
            record
            for record in records
            if (
                record.evidence_type
                == EvidenceTypeV2.CONTRIBUTION_RESULT
            )
        )

        assert len(query_records) == 4
        assert len(contribution_records) == 1
        assert len(
            contribution_records[0].parent_evidence_ids
        ) == 4

        view = result.console_view

        assert view.comparison is not None
        assert view.contribution is not None
        assert view.breakdown is not None
        assert view.breakdown.result_grain == "channel"
        assert (
            view.contribution.reconciliation_status
            == ContributionReconciliationStatusV2.RECONCILED
        )

        # Contribution Insight 是算术诊断，不是 causal claim。
        assert result.delivery.evidence_pack.insight.candidate_explanations == ()

        # 2 overall + 2 channel Governed Query 均应留下 Audit。
        verification = verify_audit_log(audit_path)
        assert verification.success
        assert verification.record_count == 4


TESTS = (
    test_real_monthly_gmv_channel_contribution_postgresql,
)


def run_acceptance() -> None:
    print(
        "Day89 Monthly GMV Channel Contribution "
        "PostgreSQL Integration"
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

    print(f"Total: {len(TESTS)}")
    print(f"Passed: {passed}")
    print(f"Failed: {len(failures)}")

    for failure in failures:
        print(f"- {failure}")

    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    run_acceptance()
