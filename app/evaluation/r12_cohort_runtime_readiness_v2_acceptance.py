from __future__ import annotations

from datetime import date

from app.delivery.r12_cohort_runtime_v2 import (
    R12RuntimeReadinessStatusV2,
    build_r12_runtime_readiness_v2,
)
from app.semantic_layer.time_comparison_contract_v2 import (
    TimeWindowReferenceV2,
)


def _manifest() -> dict:
    return {
        "generation": {
            "business_start_date": "2024-01-01",
            "business_end_date": "2025-12-31",
            "event_observation_end_date": "2026-01-31",
        },
        "activity_segmentation": {
            "require_refund_observation_window": True,
        },
        "fulfillment_generation": {
            "shipping_delay_hours": {
                "maximum": 36,
            },
            "delivery_delay_days": {
                "maximum": 7,
            },
            "remote_region_extra_delay_days": {
                "enabled": True,
                "maximum": 2,
            },
            "campaign_congestion": {
                "enabled": True,
                "extra_delay_days": {
                    "maximum": 3,
                },
            },
        },
        "refund_generation": {
            "request_delay_days": {
                "maximum": 30,
            },
            "resolution": {
                "delay_hours": {
                    "maximum": 72,
                },
            },
        },
    }


def _window(start: date, end: date) -> TimeWindowReferenceV2:
    return TimeWindowReferenceV2(
        start_date=start,
        end_date=end,
    )


def test_2025_july_is_ready() -> None:
    result = build_r12_runtime_readiness_v2(
        report_window=_window(
            date(2025, 7, 1),
            date(2025, 7, 31),
        ),
        manifest=_manifest(),
    )

    assert result.ready
    assert result.status == R12RuntimeReadinessStatusV2.READY
    assert result.base_window.start_date == date(2024, 7, 1)
    assert result.base_window.end_date == date(2025, 6, 30)


def test_2024_december_fails_closed_for_history() -> None:
    result = build_r12_runtime_readiness_v2(
        report_window=_window(
            date(2024, 12, 1),
            date(2024, 12, 31),
        ),
        manifest=_manifest(),
    )

    assert not result.ready
    assert (
        result.status
        == R12RuntimeReadinessStatusV2.INSUFFICIENT_HISTORY
    )
    assert result.base_window.start_date == date(2023, 12, 1)


def test_2025_december_fails_for_refund_observation() -> None:
    result = build_r12_runtime_readiness_v2(
        report_window=_window(
            date(2025, 12, 1),
            date(2025, 12, 31),
        ),
        manifest=_manifest(),
    )

    assert not result.ready
    assert (
        result.status
        == R12RuntimeReadinessStatusV2
        .REFUND_OBSERVATION_INCOMPLETE
    )
    assert (
        result.latest_required_observation_ts
        > result.available_observation_end_ts
    )


def test_2025_november_has_enough_observation_tail() -> None:
    result = build_r12_runtime_readiness_v2(
        report_window=_window(
            date(2025, 11, 1),
            date(2025, 11, 30),
        ),
        manifest=_manifest(),
    )

    assert result.ready
    assert result.status == R12RuntimeReadinessStatusV2.READY


def test_refund_observation_contract_is_required() -> None:
    manifest = _manifest()
    manifest["activity_segmentation"][
        "require_refund_observation_window"
    ] = False

    result = build_r12_runtime_readiness_v2(
        report_window=_window(
            date(2025, 7, 1),
            date(2025, 7, 31),
        ),
        manifest=manifest,
    )

    assert not result.ready
    assert (
        result.status
        == R12RuntimeReadinessStatusV2.INVALID_DATASET_CONTRACT
    )


TESTS = (
    test_2025_july_is_ready,
    test_2024_december_fails_closed_for_history,
    test_2025_december_fails_for_refund_observation,
    test_2025_november_has_enough_observation_tail,
    test_refund_observation_contract_is_required,
)


def run_acceptance() -> None:
    passed = 0
    failed = 0

    print("=" * 88)
    print("Day93 B5B-2 R12 Runtime Readiness Acceptance")
    print(f"Cases: {len(TESTS)}")

    for test in TESTS:
        try:
            test()
        except Exception as exc:
            failed += 1
            print(f"[FAIL] {test.__name__}")
            print(f"{type(exc).__name__}: {exc}")
        else:
            passed += 1
            print(f"[PASS] {test.__name__}")

    print("=" * 88)
    print("Summary")
    print(f"Total: {len(TESTS)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    run_acceptance()
