from datetime import date
from decimal import Decimal

from app.agents.anomaly_detection_v2 import (
    AnomalyChangeTypeV2,
    AnomalyDecisionReasonV2,
    AnomalyDecisionStatusV2,
    AnomalyDirectionV2,
    AnomalyPolicyV2,
    detect_anomaly_v2,
)
from app.semantic_layer.time_comparison_contract_v2 import (
    AlignmentModeV2,
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


def _yoy() -> TimeComparisonContractV2:
    return TimeComparisonContractV2(
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


def _relative_decrease_policy() -> AnomalyPolicyV2:
    # Acceptance fixture only; not a production Beauty BI threshold.
    return AnomalyPolicyV2(
        metric_name="gmv",
        comparison_type=ComparisonTypeV2.YOY,
        change_type=AnomalyChangeTypeV2.RELATIVE,
        direction=AnomalyDirectionV2.DECREASE,
        threshold_value=Decimal("0.10"),
        sample_metric_name="paid_order_count",
        minimum_sample_value=Decimal("100"),
        policy_version="acceptance_fixture_v2",
    )


def test_relative_decrease_anomaly() -> None:
    result = detect_anomaly_v2(
        evidence_id="anomaly-001",
        metric_name="gmv",
        comparison=_yoy(),
        current_value=Decimal("85"),
        reference_value=Decimal("100"),
        current_sample_value=Decimal("500"),
        reference_sample_value=Decimal("480"),
        policy=_relative_decrease_policy(),
    )

    assert (
        result.status
        == AnomalyDecisionStatusV2.ANOMALY
    )
    assert (
        result.reason_code
        == AnomalyDecisionReasonV2.THRESHOLD_REACHED
    )
    assert result.absolute_change == Decimal("-15")
    assert result.relative_change == Decimal("-0.15")


def test_below_threshold_is_normal() -> None:
    result = detect_anomaly_v2(
        evidence_id="anomaly-002",
        metric_name="gmv",
        comparison=_yoy(),
        current_value=Decimal("92"),
        reference_value=Decimal("100"),
        current_sample_value=Decimal("500"),
        reference_sample_value=Decimal("480"),
        policy=_relative_decrease_policy(),
    )

    assert (
        result.status
        == AnomalyDecisionStatusV2.NORMAL
    )
    assert (
        result.reason_code
        == AnomalyDecisionReasonV2.BELOW_THRESHOLD
    )


def test_wrong_direction_is_normal() -> None:
    result = detect_anomaly_v2(
        evidence_id="anomaly-003",
        metric_name="gmv",
        comparison=_yoy(),
        current_value=Decimal("130"),
        reference_value=Decimal("100"),
        current_sample_value=Decimal("500"),
        reference_sample_value=Decimal("480"),
        policy=_relative_decrease_policy(),
    )

    assert (
        result.status
        == AnomalyDecisionStatusV2.NORMAL
    )
    assert (
        result.reason_code
        == AnomalyDecisionReasonV2
        .DIRECTION_NOT_TRIGGERED
    )


def test_current_sample_too_small() -> None:
    result = detect_anomaly_v2(
        evidence_id="anomaly-004",
        metric_name="gmv",
        comparison=_yoy(),
        current_value=Decimal("50"),
        reference_value=Decimal("100"),
        current_sample_value=Decimal("3"),
        reference_sample_value=Decimal("500"),
        policy=_relative_decrease_policy(),
    )

    assert (
        result.status
        == AnomalyDecisionStatusV2.INSUFFICIENT_SAMPLE
    )


def test_reference_sample_too_small() -> None:
    result = detect_anomaly_v2(
        evidence_id="anomaly-005",
        metric_name="gmv",
        comparison=_yoy(),
        current_value=Decimal("50"),
        reference_value=Decimal("100"),
        current_sample_value=Decimal("500"),
        reference_sample_value=Decimal("3"),
        policy=_relative_decrease_policy(),
    )

    assert (
        result.status
        == AnomalyDecisionStatusV2.INSUFFICIENT_SAMPLE
    )


def test_relative_reference_zero_is_not_comparable() -> None:
    result = detect_anomaly_v2(
        evidence_id="anomaly-006",
        metric_name="gmv",
        comparison=_yoy(),
        current_value=Decimal("100"),
        reference_value=Decimal("0"),
        current_sample_value=Decimal("500"),
        reference_sample_value=Decimal("500"),
        policy=_relative_decrease_policy(),
    )

    assert (
        result.status
        == AnomalyDecisionStatusV2.NOT_COMPARABLE
    )
    assert result.relative_change is None
    assert result.absolute_change == Decimal("100")


def test_absolute_policy_can_compare_reference_zero() -> None:
    policy = AnomalyPolicyV2(
        metric_name="order_count",
        comparison_type=ComparisonTypeV2.YOY,
        change_type=AnomalyChangeTypeV2.ABSOLUTE,
        direction=AnomalyDirectionV2.INCREASE,
        threshold_value=Decimal("50"),
        sample_metric_name="order_count",
        minimum_sample_value=Decimal("1"),
        policy_version="acceptance_fixture_v2",
    )

    result = detect_anomaly_v2(
        evidence_id="anomaly-007",
        metric_name="order_count",
        comparison=_yoy(),
        current_value=Decimal("100"),
        reference_value=Decimal("0"),
        current_sample_value=Decimal("100"),
        reference_sample_value=Decimal("1"),
        policy=policy,
    )

    assert (
        result.status
        == AnomalyDecisionStatusV2.ANOMALY
    )
    assert result.relative_change is None


def test_missing_policy_is_explicit() -> None:
    result = detect_anomaly_v2(
        evidence_id="anomaly-008",
        metric_name="gmv",
        comparison=_yoy(),
        current_value=Decimal("50"),
        reference_value=Decimal("100"),
        current_sample_value=Decimal("500"),
        reference_sample_value=Decimal("500"),
        policy=None,
    )

    assert (
        result.status
        == AnomalyDecisionStatusV2.POLICY_NOT_FOUND
    )
    assert (
        result.reason_code
        == AnomalyDecisionReasonV2.POLICY_NOT_FOUND
    )


def test_metric_policy_mismatch_fails() -> None:
    try:
        detect_anomaly_v2(
            evidence_id="anomaly-009",
            metric_name="refund_rate",
            comparison=_yoy(),
            current_value=Decimal("0.08"),
            reference_value=Decimal("0.04"),
            current_sample_value=Decimal("500"),
            reference_sample_value=Decimal("500"),
            policy=_relative_decrease_policy(),
        )
    except ValueError:
        return

    raise AssertionError(
        "Metric/policy mismatch must fail."
    )


def test_comparison_policy_mismatch_fails() -> None:
    policy = AnomalyPolicyV2(
        metric_name="gmv",
        comparison_type=ComparisonTypeV2.MOM,
        change_type=AnomalyChangeTypeV2.RELATIVE,
        direction=AnomalyDirectionV2.DECREASE,
        threshold_value=Decimal("0.10"),
        sample_metric_name="paid_order_count",
        minimum_sample_value=Decimal("100"),
        policy_version="acceptance_fixture_v2",
    )

    try:
        detect_anomaly_v2(
            evidence_id="anomaly-010",
            metric_name="gmv",
            comparison=_yoy(),
            current_value=Decimal("80"),
            reference_value=Decimal("100"),
            current_sample_value=Decimal("500"),
            reference_sample_value=Decimal("500"),
            policy=policy,
        )
    except ValueError:
        return

    raise AssertionError(
        "Comparison/policy mismatch must fail."
    )



def test_decimal_exposure_sample_basis_supported() -> None:
    policy = AnomalyPolicyV2(
        metric_name="roi",
        comparison_type=ComparisonTypeV2.YOY,
        change_type=AnomalyChangeTypeV2.RELATIVE,
        direction=AnomalyDirectionV2.DECREASE,
        threshold_value=Decimal("0.10"),
        sample_metric_name="marketing_spend",
        minimum_sample_value=Decimal("10000.50"),
        policy_version="acceptance_fixture_v2",
    )

    result = detect_anomaly_v2(
        evidence_id="anomaly-011",
        metric_name="roi",
        comparison=_yoy(),
        current_value=Decimal("2.0"),
        reference_value=Decimal("2.5"),
        current_sample_value=Decimal("12000.75"),
        reference_sample_value=Decimal("11950.25"),
        policy=policy,
    )

    assert (
        result.status
        == AnomalyDecisionStatusV2.ANOMALY
    )


TESTS = (
    test_relative_decrease_anomaly,
    test_below_threshold_is_normal,
    test_wrong_direction_is_normal,
    test_current_sample_too_small,
    test_reference_sample_too_small,
    test_relative_reference_zero_is_not_comparable,
    test_absolute_policy_can_compare_reference_zero,
    test_missing_policy_is_explicit,
    test_metric_policy_mismatch_fails,
    test_comparison_policy_mismatch_fails,
    test_decimal_exposure_sample_basis_supported,
)


def run_acceptance() -> None:
    passed = 0
    failed = 0

    print("=" * 80)
    print("Anomaly Detection V2 Acceptance")
    print(f"Cases: {len(TESTS)}")

    for test in TESTS:
        print("=" * 80)
        print(test.__name__)

        try:
            test()
        except Exception as exc:
            failed += 1
            print("[FAIL]")
            print(
                f"{type(exc).__name__}: {exc}"
            )
        else:
            passed += 1
            print("[PASS]")

    print("=" * 80)
    print("Anomaly Detection V2 Acceptance Summary")
    print(f"Total: {len(TESTS)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    run_acceptance()
