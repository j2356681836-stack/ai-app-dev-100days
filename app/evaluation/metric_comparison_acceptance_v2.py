from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.agents.anomaly_detection_v2 import (
    detect_anomaly_v2,
)
from app.agents.metric_comparison_v2 import (
    MetricComparisonResultV2,
    RelativeChangeStatusV2,
    compare_metric_values_v2,
)
from app.semantic_layer.time_comparison_contract_v2 import (
    AlignmentModeV2,
    ComparisonTypeV2,
    PeriodModeV2,
    TimeComparisonContractV2,
    TimeWindowReferenceV2,
)


def _comparison() -> TimeComparisonContractV2:
    return TimeComparisonContractV2(
        comparison_type=ComparisonTypeV2.YOY,
        period_mode=PeriodModeV2.COMPLETED_PERIOD,
        alignment_mode=AlignmentModeV2.CALENDAR_ALIGNED,
        current_window=TimeWindowReferenceV2(
            start_date=date(2025, 7, 1),
            end_date=date(2025, 7, 31),
        ),
        reference_window=TimeWindowReferenceV2(
            start_date=date(2024, 7, 1),
            end_date=date(2024, 7, 31),
        ),
    )


def _result(
    *,
    current: str,
    reference: str,
) -> MetricComparisonResultV2:
    return compare_metric_values_v2(
        metric_name="gmv",
        comparison=_comparison(),
        current_evidence_id="ev-current",
        reference_evidence_id="ev-reference",
        current_value=Decimal(current),
        reference_value=Decimal(reference),
    )


def test_positive_change() -> None:
    result = _result(
        current="120",
        reference="100",
    )

    assert result.absolute_change == Decimal("20")
    assert result.relative_change == Decimal("0.2")
    assert (
        result.relative_change_status
        == RelativeChangeStatusV2.DEFINED
    )


def test_negative_change() -> None:
    result = _result(
        current="80",
        reference="100",
    )

    assert result.absolute_change == Decimal("-20")
    assert result.relative_change == Decimal("-0.2")


def test_reference_zero_is_explicitly_undefined() -> None:
    result = _result(
        current="100",
        reference="0",
    )

    assert result.absolute_change == Decimal("100")
    assert result.relative_change is None
    assert (
        result.relative_change_status
        == RelativeChangeStatusV2
        .UNDEFINED_REFERENCE_ZERO
    )


def test_tampered_absolute_change_fails_closed() -> None:
    try:
        MetricComparisonResultV2(
            metric_name="gmv",
            comparison=_comparison(),
            current_evidence_id="ev-current",
            reference_evidence_id="ev-reference",
            current_value=Decimal("120"),
            reference_value=Decimal("100"),
            absolute_change=Decimal("999"),
            relative_change=Decimal("0.2"),
            relative_change_status=(
                RelativeChangeStatusV2.DEFINED
            ),
        )
    except ValueError:
        return

    raise AssertionError(
        "被篡改的 absolute_change 必须 fail-closed。"
    )


def test_blank_evidence_id_fails_closed() -> None:
    try:
        compare_metric_values_v2(
            metric_name="gmv",
            comparison=_comparison(),
            current_evidence_id="",
            reference_evidence_id="ev-reference",
            current_value=Decimal("120"),
            reference_value=Decimal("100"),
        )
    except ValueError:
        return

    raise AssertionError(
        "空 evidence_id 必须 fail-closed。"
    )


def test_parity_with_day83_change_calculation() -> None:
    comparison = _comparison()

    comparison_result = compare_metric_values_v2(
        metric_name="gmv",
        comparison=comparison,
        current_evidence_id="ev-current",
        reference_evidence_id="ev-reference",
        current_value=Decimal("70"),
        reference_value=Decimal("100"),
    )

    anomaly_decision = detect_anomaly_v2(
        evidence_id="ev-anomaly",
        metric_name="gmv",
        comparison=comparison,
        current_value=Decimal("70"),
        reference_value=Decimal("100"),
        current_sample_value=Decimal("100"),
        reference_sample_value=Decimal("100"),
        policy=None,
    )

    assert (
        comparison_result.absolute_change
        == anomaly_decision.absolute_change
    )
    assert (
        comparison_result.relative_change
        == anomaly_decision.relative_change
    )


def test_comparison_contract_is_preserved() -> None:
    comparison = _comparison()

    result = compare_metric_values_v2(
        metric_name="gmv",
        comparison=comparison,
        current_evidence_id="ev-current",
        reference_evidence_id="ev-reference",
        current_value=Decimal("120"),
        reference_value=Decimal("100"),
    )

    assert result.comparison == comparison


TESTS = (
    test_positive_change,
    test_negative_change,
    test_reference_zero_is_explicitly_undefined,
    test_tampered_absolute_change_fails_closed,
    test_blank_evidence_id_fails_closed,
    test_parity_with_day83_change_calculation,
    test_comparison_contract_is_preserved,
)


def run_acceptance() -> None:
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

    print("Day89 Metric Comparison V2 Acceptance Summary")
    print(f"Total: {len(TESTS)}")
    print(f"Passed: {passed}")
    print(f"Failed: {len(failures)}")

    for failure in failures:
        print(f"- {failure}")

    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    run_acceptance()
