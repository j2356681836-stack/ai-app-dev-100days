from __future__ import annotations

import inspect
from datetime import date

import app.delivery.decision_console_runtime_v2 as runtime
from app.semantic_layer.time_comparison_contract_v2 import (
    AlignmentModeV2,
    ComparisonTypeV2,
    PeriodModeV2,
    TimeWindowReferenceV2,
)


def test_july_monthly_mom_contract() -> None:
    comparison = runtime.build_monthly_mom_comparison_v2(
        anchor_date=date(2025, 7, 15),
    )

    assert comparison.current_window == TimeWindowReferenceV2(
        start_date=date(2025, 7, 1),
        end_date=date(2025, 7, 31),
    )
    assert comparison.reference_window == TimeWindowReferenceV2(
        start_date=date(2025, 6, 1),
        end_date=date(2025, 6, 30),
    )


def test_january_rolls_reference_to_previous_year() -> None:
    comparison = runtime.build_monthly_mom_comparison_v2(
        anchor_date=date(2025, 1, 8),
    )

    assert comparison.current_window.start_date == date(2025, 1, 1)
    assert comparison.current_window.end_date == date(2025, 1, 31)
    assert comparison.reference_window.start_date == date(2024, 12, 1)
    assert comparison.reference_window.end_date == date(2024, 12, 31)


def test_monthly_contract_is_completed_calendar_mom() -> None:
    comparison = runtime.build_monthly_mom_comparison_v2(
        anchor_date=date(2025, 7, 31),
    )

    assert comparison.comparison_type == ComparisonTypeV2.MOM
    assert comparison.period_mode == PeriodModeV2.COMPLETED_PERIOD
    assert comparison.alignment_mode == AlignmentModeV2.CALENDAR_ALIGNED
    assert comparison.is_partial_period is False


def test_overall_gmv_binding_is_explicit() -> None:
    binding = runtime.build_day89_overall_gmv_tool_binding_v2()

    assert binding.plan_name == "gmv_overall_v2"
    assert (
        binding.tool_contract.identity.name
        == "governed_gmv_overall_query"
    )
    assert binding.tool_contract.identity.version == "dataset_v2"
    assert (
        binding.tool_contract.executor_binding
        == "execute_governed_query_v2"
    )


def test_periodic_runtime_does_not_import_evaluation_fixture() -> None:
    source = inspect.getsource(runtime)
    assert "app.evaluation" not in source


def test_monthly_runtime_uses_two_structured_single_window_queries() -> None:
    source = inspect.getsource(
        runtime.run_day89_monthly_gmv_report_v2
    )

    assert source.count("invoke_governed_plan_delivery_v2(") == 2
    assert "invoke_governed_graph_delivery_v2(" not in source
    assert "本月和上月" not in source


def test_monthly_runtime_does_not_depend_on_live_semantic_parser() -> None:
    source = inspect.getsource(
        runtime.run_day89_monthly_gmv_report_v2
    )

    assert "llm_call" not in source
    assert "resolve_analytics_planning_v2" not in source
    assert "parse_question_semantics_v2" not in source


TESTS = (
    test_july_monthly_mom_contract,
    test_january_rolls_reference_to_previous_year,
    test_monthly_contract_is_completed_calendar_mom,
    test_overall_gmv_binding_is_explicit,
    test_periodic_runtime_does_not_import_evaluation_fixture,
    test_monthly_runtime_uses_two_structured_single_window_queries,
    test_monthly_runtime_does_not_depend_on_live_semantic_parser,
)


def run_acceptance() -> None:
    print("Day89 Monthly GMV Periodic Runtime Acceptance")

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
