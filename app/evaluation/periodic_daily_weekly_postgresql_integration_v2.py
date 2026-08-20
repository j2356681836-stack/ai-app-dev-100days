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
from app.governance.audit_sink import verify_audit_log
from app.governance.execution_policy import GovernedExecutionPolicy
from app.governance.governance_runtime import GovernanceRuntimeConfig
from app.semantic_layer.time_comparison_contract_v2 import (
    ComparisonTypeV2,
)


EXECUTION_POLICY = GovernedExecutionPolicy(
    statement_timeout_ms=30_000,
    max_rows=20,
)


def _runtime_config(audit_path: Path) -> GovernanceRuntimeConfig:
    return GovernanceRuntimeConfig(
        result_tokenization_secret=(
            "day89-periodic-token-secret-32-characters"
        ),
        audit_secret=(
            "day89-periodic-audit-secret-32-characters"
        ),
        audit_log_path=audit_path,
        create_parent_directory=True,
        fsync_enabled=True,
    )


def test_real_daily_report_degrades_when_channel_breakdown_is_protected() -> None:
    """
    2025-07-15 的 Daily Overall Comparison 可以安全释放，
    但当前真实 Dataset 下 Channel Breakdown 被 Result Protection 阻断。

    正确产品行为不是绕过保护，也不是把整个日报判成失败：
    保留可信 DoD KPI / Overall Evidence，Contribution 显式不可用。
    """

    with TemporaryDirectory() as tmp:
        audit_path = (
            Path(tmp)
            / "day89_daily_periodic_audit.jsonl"
        )
        config = _runtime_config(audit_path)

        result = (
            run_day89_periodic_gmv_channel_contribution_v2(
                cadence=PeriodicReportCadenceV2.DAILY,
                anchor_date=date(2025, 7, 15),
                runtime_config=config,
                execution_policy=EXECUTION_POLICY,
            )
        )

        assert (
            result.status
            == PeriodicContributionDeliveryStatusV2
            .PARTIAL_READY
        ), (
            "Daily 应在 Channel Result Protection 阻断时 "
            "privacy-aware degrade，而不是绕过保护或丢弃 Overall："
            f"status={result.status.value}; "
            f"message={result.message}"
        )

        assert result.comparison is not None
        assert (
            result.comparison.comparison_type
            == ComparisonTypeV2.DOD
        )

        assert result.metric_comparison_result is not None
        assert result.delivery is not None
        assert result.console_view is not None
        assert result.executive_brief is not None

        # 受保护 Channel rows 绝不能被拿来计算 Contribution。
        assert result.contribution_result is None
        assert result.current_channel_safe_runtime_result is not None

        channel_safe = result.current_channel_safe_runtime_result
        assert channel_safe.get("success") is False
        assert channel_safe.get("outcome") == "blocked"
        assert channel_safe.get("stop_stage") == "finalization"

        records = result.delivery.evidence_pack.evidence_records
        query_records = tuple(
            item
            for item in records
            if item.evidence_type
            == EvidenceTypeV2.GOVERNED_QUERY_RESULT
        )

        # 只允许 current/ref Overall 两条已释放 Evidence。
        assert len(query_records) == 2

        verification = verify_audit_log(audit_path)
        assert verification.success

        # current overall + reference overall + blocked current channel.
        # 被保护阻断的请求仍必须留下 Audit。
        assert verification.record_count == 3


def test_real_weekly_gmv_channel_contribution_postgresql() -> None:
    with TemporaryDirectory() as tmp:
        audit_path = (
            Path(tmp)
            / "day89_weekly_periodic_audit.jsonl"
        )
        config = _runtime_config(audit_path)

        result = (
            run_day89_periodic_gmv_channel_contribution_v2(
                cadence=PeriodicReportCadenceV2.WEEKLY,
                anchor_date=date(2025, 7, 20),
                runtime_config=config,
                execution_policy=EXECUTION_POLICY,
            )
        )

        assert (
            result.status
            == PeriodicContributionDeliveryStatusV2.READY
        ), (
            "Weekly Periodic Runtime 未 READY："
            f"status={result.status.value}; "
            f"message={result.message}"
        )

        assert result.comparison is not None
        assert (
            result.comparison.comparison_type
            == ComparisonTypeV2.WOW
        )

        assert result.delivery is not None
        assert result.console_view is not None
        assert result.contribution_result is not None

        contribution = result.contribution_result
        assert (
            contribution.reconciliation_status
            == ContributionReconciliationStatusV2.RECONCILED
        )

        records = result.delivery.evidence_pack.evidence_records

        query_records = tuple(
            item
            for item in records
            if item.evidence_type
            == EvidenceTypeV2.GOVERNED_QUERY_RESULT
        )
        contribution_records = tuple(
            item
            for item in records
            if item.evidence_type
            == EvidenceTypeV2.CONTRIBUTION_RESULT
        )

        assert len(query_records) == 4
        assert len(contribution_records) == 1
        assert len(
            contribution_records[0].parent_evidence_ids
        ) == 4

        assert result.console_view.contribution is not None
        assert result.console_view.breakdown is not None
        assert (
            result.console_view.breakdown.result_grain
            == "channel"
        )

        verification = verify_audit_log(audit_path)
        assert verification.success
        assert verification.record_count == 4


TESTS = (
    test_real_daily_report_degrades_when_channel_breakdown_is_protected,
    test_real_weekly_gmv_channel_contribution_postgresql,
)


def run_acceptance() -> None:
    print(
        "Day89 Daily / Weekly Periodic Runtime "
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
