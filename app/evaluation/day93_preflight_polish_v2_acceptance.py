from __future__ import annotations

from datetime import date

from app.semantic_layer.dataset_availability_contract_v2 import (
    DatasetAvailabilityOutcomeV2,
    DatasetBusinessWindowV2,
    evaluate_explicit_dataset_availability_preflight_v2,
)


REFERENCE_DATE = date(2025, 12, 31)
BUSINESS_WINDOW = DatasetBusinessWindowV2(
    start_date=date(2024, 1, 1),
    end_date=date(2025, 12, 31),
)


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _fast(question: str):
    return evaluate_explicit_dataset_availability_preflight_v2(
        question=question,
        reference_date=REFERENCE_DATE,
        business_window=BUSINESS_WINDOW,
    )


def test_b01_stops_on_explicit_dataset_fast_path() -> None:
    result = _fast("2023年GMV是多少？")

    _assert(
        result.outcome
        == DatasetAvailabilityOutcomeV2.OUTSIDE_BUSINESS_WINDOW,
        f"B01 should stop before semantic planning: {result}",
    )


def test_available_explicit_year_continues() -> None:
    result = _fast("2025年GMV是多少？")

    _assert(
        result.outcome == DatasetAvailabilityOutcomeV2.AVAILABLE,
        f"available explicit year must continue: {result}",
    )


def test_partial_overlap_stops_without_silent_clamp() -> None:
    result = _fast(
        "2023年12月1日至2024年1月31日GMV是多少？"
    )

    _assert(
        result.outcome == DatasetAvailabilityOutcomeV2.PARTIAL_OVERLAP,
        f"partial overlap must stop explicitly: {result}",
    )


def test_no_explicit_time_defers_to_main_chain() -> None:
    result = _fast("GMV是多少？")

    _assert(
        result.outcome == DatasetAvailabilityOutcomeV2.NOT_APPLICABLE,
        f"default time must not be claimed by fast path: {result}",
    )


def test_multiple_time_windows_defer_to_orchestration() -> None:
    result = _fast(
        "2025年10月GMV相比2025年9月表现怎么样？"
    )

    _assert(
        result.outcome == DatasetAvailabilityOutcomeV2.NOT_APPLICABLE,
        f"multi-window comparison must defer: {result}",
    )


def test_ambiguous_relative_comparison_does_not_stop() -> None:
    result = _fast(
        "2025年10月GMV相比9月表现怎么样？"
    )

    _assert(
        result.outcome
        in {
            DatasetAvailabilityOutcomeV2.AVAILABLE,
            DatasetAvailabilityOutcomeV2.NOT_APPLICABLE,
        },
        f"F02 wording must not be stopped by fast path: {result}",
    )


def run_acceptance() -> None:
    tests = (
        test_b01_stops_on_explicit_dataset_fast_path,
        test_available_explicit_year_continues,
        test_partial_overlap_stops_without_silent_clamp,
        test_no_explicit_time_defers_to_main_chain,
        test_multiple_time_windows_defer_to_orchestration,
        test_ambiguous_relative_comparison_does_not_stop,
    )

    passed = 0

    for test in tests:
        test()
        passed += 1
        print(f"PASS {passed:02d}: {test.__name__}")

    print(
        "Day93 Preflight Polish Acceptance: "
        f"{passed}/{len(tests)} PASS"
    )


if __name__ == "__main__":
    run_acceptance()
