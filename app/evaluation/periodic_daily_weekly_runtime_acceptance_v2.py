from __future__ import annotations

import inspect
from datetime import date

from app.agents.contribution_analysis_v2 import (
    ContributionReconciliationStatusV2,
)
from app.delivery.decision_console_entry_v2 import (
    PeriodicReportCadenceV2,
)
from app.delivery import decision_console_runtime_v2 as runtime
from app.delivery import monthly_contribution_delivery_v2 as contribution
from app.semantic_layer.time_comparison_contract_v2 import (
    AlignmentModeV2,
    ComparisonTypeV2,
    PeriodModeV2,
    TimeWindowReferenceV2,
)


def test_daily_uses_truthful_dod_semantics() -> None:
    comparison = runtime.build_daily_dod_comparison_v2(
        anchor_date=date(2025, 7, 15),
    )

    assert comparison.comparison_type == ComparisonTypeV2.DOD
    assert comparison.period_mode == PeriodModeV2.COMPLETED_PERIOD
    assert comparison.alignment_mode == AlignmentModeV2.CALENDAR_ALIGNED
    assert comparison.current_window == TimeWindowReferenceV2(
        start_date=date(2025, 7, 15),
        end_date=date(2025, 7, 15),
    )
    assert comparison.reference_window == TimeWindowReferenceV2(
        start_date=date(2025, 7, 14),
        end_date=date(2025, 7, 14),
    )


def test_daily_crosses_month_boundary_correctly() -> None:
    comparison = runtime.build_daily_dod_comparison_v2(
        anchor_date=date(2025, 7, 1),
    )

    assert comparison.reference_window == TimeWindowReferenceV2(
        start_date=date(2025, 6, 30),
        end_date=date(2025, 6, 30),
    )


def test_weekly_uses_monday_sunday_calendar_week() -> None:
    comparison = runtime.build_weekly_wow_comparison_v2(
        anchor_date=date(2025, 7, 16),  # Wednesday
    )

    assert comparison.comparison_type == ComparisonTypeV2.WOW
    assert comparison.period_mode == PeriodModeV2.COMPLETED_PERIOD
    assert comparison.alignment_mode == AlignmentModeV2.CALENDAR_ALIGNED

    assert comparison.current_window == TimeWindowReferenceV2(
        start_date=date(2025, 7, 14),
        end_date=date(2025, 7, 20),
    )
    assert comparison.reference_window == TimeWindowReferenceV2(
        start_date=date(2025, 7, 7),
        end_date=date(2025, 7, 13),
    )


def test_periodic_dispatch_preserves_monthly_contract() -> None:
    generic = runtime.build_periodic_gmv_comparison_v2(
        cadence=PeriodicReportCadenceV2.MONTHLY,
        anchor_date=date(2025, 7, 31),
    )
    existing = runtime.build_monthly_mom_comparison_v2(
        anchor_date=date(2025, 7, 31),
    )

    assert generic == existing
    assert generic.comparison_type == ComparisonTypeV2.MOM


def test_daily_weekly_runtime_use_structured_query_plan_only() -> None:
    source = inspect.getsource(
        runtime.run_day89_periodic_gmv_report_v2
    )

    assert source.count("invoke_governed_plan_delivery_v2(") == 2
    assert "invoke_governed_graph_delivery_v2(" not in source
    assert "analysis_window=comparison.current_window" in source
    assert "analysis_window=comparison.reference_window" in source


def test_periodic_runtime_does_not_use_semantic_time_parser() -> None:
    source = inspect.getsource(
        runtime.run_day89_periodic_gmv_report_v2
    )

    assert "llm_call" not in source
    assert "resolve_analytics_planning_v2" not in source
    assert "parse_question_semantics_v2" not in source


def test_periodic_contribution_keeps_monthly_path_unchanged() -> None:
    source = inspect.getsource(
        contribution.run_day89_periodic_gmv_channel_contribution_v2
    )

    assert "PeriodicReportCadenceV2.MONTHLY" in source
    assert "run_day89_monthly_gmv_channel_contribution_v2(" in source


def test_daily_weekly_contribution_add_exactly_two_channel_queries() -> None:
    source = inspect.getsource(
        contribution.run_day89_periodic_gmv_channel_contribution_v2
    )

    assert source.count("invoke_governed_plan_delivery_v2(") == 2
    assert "analysis_window=comparison.current_window" in source
    assert "analysis_window=comparison.reference_window" in source


def test_periodic_contribution_reuses_same_four_way_trust_linkage() -> None:
    source = inspect.getsource(
        contribution.run_day89_periodic_gmv_channel_contribution_v2
    )

    assert "_validate_four_way_trust_linkage(" in source
    assert "build_dimension_contribution_material_v2(" in source
    assert "build_contribution_evidence_record_v2(" in source
    assert "attach_contribution_result_to_insight_v2(" in source


def test_periodic_result_has_backward_compatible_safe_alias() -> None:
    assert (
        contribution.PeriodicContributionDeliveryResultV2
        is contribution.MonthlyContributionDeliveryResultV2
    )
    assert (
        contribution.PeriodicContributionDeliveryStatusV2
        is contribution.MonthlyContributionDeliveryStatusV2
    )


def test_partial_ready_preserves_overall_but_never_contribution() -> None:
    source = inspect.getsource(
        contribution._partial_ready_from_comparison
    )

    assert "PARTIAL_READY" in source
    assert "comparison_delivery.metric_comparison_result" in source
    assert "delivery=comparison_delivery.delivery" in source
    assert "console_view=comparison_delivery.console_view" in source
    assert "executive_brief=comparison_delivery.executive_brief" in source
    assert "contribution_result=None" in source


def test_periodic_channel_failure_degrades_without_bypassing_protection() -> None:
    source = inspect.getsource(
        contribution.run_day89_periodic_gmv_channel_contribution_v2
    )

    assert "_partial_ready_from_comparison(" in source
    assert "Current Channel Breakdown 未能安全释放" in source
    assert "Reference Channel Breakdown 未能安全释放" in source

    forbidden = (
        "minimum_group_size=1",
        "minimum_group_size_required=False",
        "raw_rows",
        "finalization.rows",
    )
    for token in forbidden:
        assert token not in source


TESTS = (
    test_daily_uses_truthful_dod_semantics,
    test_daily_crosses_month_boundary_correctly,
    test_weekly_uses_monday_sunday_calendar_week,
    test_periodic_dispatch_preserves_monthly_contract,
    test_daily_weekly_runtime_use_structured_query_plan_only,
    test_periodic_runtime_does_not_use_semantic_time_parser,
    test_periodic_contribution_keeps_monthly_path_unchanged,
    test_daily_weekly_contribution_add_exactly_two_channel_queries,
    test_periodic_contribution_reuses_same_four_way_trust_linkage,
    test_periodic_result_has_backward_compatible_safe_alias,
    test_partial_ready_preserves_overall_but_never_contribution,
    test_periodic_channel_failure_degrades_without_bypassing_protection,
)


def run_acceptance() -> None:
    print("Day89 Daily / Weekly Periodic Runtime Acceptance")

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
