from __future__ import annotations

from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from app.agents.contribution_analysis_v2 import (
    ContributionReconciliationStatusV2,
)
from app.agents.evidence_pack_v2 import EvidenceTypeV2
from app.delivery.decision_console_entry_v2 import (
    PeriodicReportCadenceV2,
)
from app.delivery.monthly_contribution_delivery_v2 import (
    PeriodicContributionDeliveryStatusV2,
    run_day89_periodic_gmv_channel_contribution_v2,
)
from app.evaluation.investigation_clarification_resume_postgresql_integration_v2 import (
    test_real_postgresql_clarification_response_resumes_governed_tool,
)
from app.evaluation.investigation_hitl_continue_postgresql_integration_v2 import (
    test_real_postgresql_explicit_continue_requires_user_and_preserves_trace,
)
from app.evaluation.periodic_daily_weekly_postgresql_integration_v2 import (
    test_real_daily_report_degrades_when_channel_breakdown_is_protected,
    test_real_weekly_gmv_channel_contribution_postgresql,
)
from app.governance.audit_sink import verify_audit_log
from app.governance.execution_policy import (
    GovernedExecutionPolicy,
)
from app.governance.governance_runtime import (
    GovernanceRuntimeConfig,
)
from app.semantic_layer.time_comparison_contract_v2 import (
    ComparisonTypeV2,
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
            "day89-final-gate-token-secret-32-characters"
        ),
        audit_secret=(
            "day89-final-gate-audit-secret-32-characters"
        ),
        audit_log_path=audit_path,
        create_parent_directory=True,
        fsync_enabled=True,
    )


def test_real_monthly_generic_periodic_runtime_postgresql() -> None:
    """
    最终 Gate 额外验证统一 Periodic Runtime 的 MONTHLY dispatch。

    目的：
    - UI 已经不再直连 Monthly-only 函数；
    - 因此最终 PostgreSQL Gate 必须证明 cadence=MONTHLY
      仍可完整走到 READY + Contribution + Audit。
    """

    with TemporaryDirectory() as tmp:
        audit_path = (
            Path(tmp)
            / "day89_final_monthly_audit.jsonl"
        )
        config = _runtime_config(audit_path)

        result = (
            run_day89_periodic_gmv_channel_contribution_v2(
                cadence=PeriodicReportCadenceV2.MONTHLY,
                anchor_date=date(2025, 7, 31),
                runtime_config=config,
                execution_policy=EXECUTION_POLICY,
            )
        )

        assert (
            result.status
            == PeriodicContributionDeliveryStatusV2.READY
        ), (
            "Monthly unified Periodic Runtime 未 READY："
            f"status={result.status.value}; "
            f"message={result.message}"
        )

        assert result.comparison is not None
        assert (
            result.comparison.comparison_type
            == ComparisonTypeV2.MOM
        )

        assert result.metric_comparison_result is not None
        assert result.contribution_result is not None
        assert result.delivery is not None
        assert result.console_view is not None
        assert result.executive_brief is not None

        contribution = result.contribution_result
        assert (
            contribution.reconciliation_status
            == ContributionReconciliationStatusV2.RECONCILED
        )

        records = (
            result.delivery.evidence_pack.evidence_records
        )

        query_records = tuple(
            item
            for item in records
            if (
                item.evidence_type
                == EvidenceTypeV2.GOVERNED_QUERY_RESULT
            )
        )
        contribution_records = tuple(
            item
            for item in records
            if (
                item.evidence_type
                == EvidenceTypeV2.CONTRIBUTION_RESULT
            )
        )

        assert len(query_records) == 4
        assert len(contribution_records) == 1
        assert len(
            contribution_records[0].parent_evidence_ids
        ) == 4

        assert result.console_view.comparison is not None
        assert result.console_view.contribution is not None
        assert result.console_view.breakdown is not None

        verification = verify_audit_log(audit_path)
        assert verification.success
        assert verification.record_count == 4


TESTS = (
    (
        "Explicit Continue",
        test_real_postgresql_explicit_continue_requires_user_and_preserves_trace,
    ),
    (
        "Clarification Resume",
        test_real_postgresql_clarification_response_resumes_governed_tool,
    ),
    (
        "Daily Privacy-aware Partial Delivery",
        test_real_daily_report_degrades_when_channel_breakdown_is_protected,
    ),
    (
        "Weekly Full Periodic Delivery",
        test_real_weekly_gmv_channel_contribution_postgresql,
    ),
    (
        "Monthly Unified Periodic Delivery",
        test_real_monthly_generic_periodic_runtime_postgresql,
    ),
)


def run_acceptance() -> None:
    print("Day89 Final Delivery Gate PostgreSQL Integration V2")
    print("=" * 72)

    passed = 0
    failures: list[str] = []

    for name, test in TESTS:
        try:
            test()
            passed += 1
            print(f"{name}: PASS")
        except Exception as exc:  # noqa: BLE001
            failures.append(
                f"{name}: {type(exc).__name__}: {exc}"
            )
            print(f"{name}: FAIL")

    print("-" * 72)
    print(f"Total: {len(TESTS)}")
    print(f"Passed: {passed}")
    print(f"Failed: {len(failures)}")

    for failure in failures:
        print(f"- {failure}")

    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    run_acceptance()
