from datetime import date

from pydantic import ValidationError

from app.semantic_layer.time_comparison_contract_v2 import (
    AlignmentModeV2,
    CampaignReferenceV2,
    ComparisonTypeV2,
    PeriodModeV2,
    TimeComparisonContractV2,
    TimeWindowReferenceV2,
)


def _window(
    start_date: date,
    end_date: date,
) -> TimeWindowReferenceV2:
    return TimeWindowReferenceV2(
        start_date=start_date,
        end_date=end_date,
    )


def test_completed_yoy_passes() -> None:
    contract = TimeComparisonContractV2(
        comparison_type=ComparisonTypeV2.YOY,
        period_mode=PeriodModeV2.COMPLETED_PERIOD,
        alignment_mode=AlignmentModeV2.CALENDAR_ALIGNED,
        current_window=_window(
            date(2025, 7, 1),
            date(2025, 7, 31),
        ),
        reference_window=_window(
            date(2024, 7, 1),
            date(2024, 7, 31),
        ),
    )

    assert contract.comparison_type == ComparisonTypeV2.YOY
    assert not contract.is_partial_period


def test_period_to_date_yoy_passes() -> None:
    contract = TimeComparisonContractV2(
        comparison_type=ComparisonTypeV2.YOY,
        period_mode=PeriodModeV2.PERIOD_TO_DATE,
        alignment_mode=AlignmentModeV2.SAME_ELAPSED_PERIOD,
        current_window=_window(
            date(2025, 8, 1),
            date(2025, 8, 10),
        ),
        reference_window=_window(
            date(2024, 8, 1),
            date(2024, 8, 10),
        ),
        data_complete_through=date(2025, 8, 10),
        is_partial_period=True,
    )

    assert contract.is_partial_period


def test_campaign_yoy_passes() -> None:
    contract = TimeComparisonContractV2(
        comparison_type=ComparisonTypeV2.CAMPAIGN_YOY,
        period_mode=PeriodModeV2.PERIOD_TO_DATE,
        alignment_mode=AlignmentModeV2.CAMPAIGN_RELATIVE,
        current_window=_window(
            date(2025, 10, 20),
            date(2025, 10, 24),
        ),
        reference_window=_window(
            date(2024, 10, 24),
            date(2024, 10, 28),
        ),
        is_partial_period=True,
        campaign_reference=CampaignReferenceV2(
            campaign_family="double11",
            current_campaign_code="double11_2025",
            reference_campaign_code="double11_2024",
        ),
    )

    assert contract.campaign_reference is not None


def test_campaign_yoy_requires_reference() -> None:
    try:
        TimeComparisonContractV2(
            comparison_type=ComparisonTypeV2.CAMPAIGN_YOY,
            period_mode=PeriodModeV2.COMPLETED_PERIOD,
            alignment_mode=AlignmentModeV2.CAMPAIGN_RELATIVE,
            current_window=_window(
                date(2025, 10, 20),
                date(2025, 11, 11),
            ),
            reference_window=_window(
                date(2024, 10, 24),
                date(2024, 11, 15),
            ),
        )
    except ValidationError:
        return

    raise AssertionError(
        "CAMPAIGN_YOY without campaign_reference must fail."
    )


def test_baseline_requires_reference() -> None:
    try:
        TimeComparisonContractV2(
            comparison_type=ComparisonTypeV2.BASELINE_DEVIATION,
            period_mode=PeriodModeV2.COMPLETED_PERIOD,
            alignment_mode=AlignmentModeV2.CALENDAR_ALIGNED,
            current_window=_window(
                date(2025, 7, 1),
                date(2025, 7, 31),
            ),
            reference_window=_window(
                date(2025, 6, 1),
                date(2025, 6, 30),
            ),
        )
    except ValidationError:
        return

    raise AssertionError(
        "BASELINE_DEVIATION without baseline_reference must fail."
    )


def test_reversed_window_fails() -> None:
    try:
        _window(
            date(2025, 8, 10),
            date(2025, 8, 1),
        )
    except ValidationError:
        return

    raise AssertionError(
        "Reversed time window must fail."
    )


TESTS = (
    test_completed_yoy_passes,
    test_period_to_date_yoy_passes,
    test_campaign_yoy_passes,
    test_campaign_yoy_requires_reference,
    test_baseline_requires_reference,
    test_reversed_window_fails,
)


def run_acceptance() -> None:
    passed = 0
    failed = 0

    print("=" * 80)
    print("Time Comparison Contract V2 Acceptance")
    print(f"Cases: {len(TESTS)}")

    for test in TESTS:
        print("=" * 80)
        print(test.__name__)

        try:
            test()
        except Exception as exc:
            failed += 1
            print("[FAIL]")
            print(f"{type(exc).__name__}: {exc}")
        else:
            passed += 1
            print("[PASS]")

    print("=" * 80)
    print("Time Comparison Contract V2 Acceptance Summary")
    print(f"Total: {len(TESTS)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    run_acceptance()
