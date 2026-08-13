from decimal import Decimal

from pydantic import ValidationError

from app.agents.anomaly_detection_v2 import (
    AnomalyChangeTypeV2,
    AnomalyDirectionV2,
)
from app.agents.anomaly_policy_candidates_v2 import (
    AnomalyPolicyCandidateStatusV2,
    AnomalyPolicyCandidateV2,
    AnomalyPolicySourceV2,
    DAY83_TIER_A_POLICY_CANDIDATES_V2,
)
from app.semantic_layer.time_comparison_contract_v2 import (
    ComparisonTypeV2,
)


def _base_kwargs() -> dict:
    return {
        "candidate_id": "gmv_campaign_yoy",
        "metric_name": "gmv",
        "comparison_type":
            ComparisonTypeV2.CAMPAIGN_YOY,
        "change_type":
            AnomalyChangeTypeV2.RELATIVE,
        "direction":
            AnomalyDirectionV2.DECREASE,
        "policy_sources": (
            AnomalyPolicySourceV2.METADATA_DEFINITION,
            AnomalyPolicySourceV2.DATASET_MANIFEST,
        ),
        "evidence_references": (
            "metadata.metric.gmv",
            "manifest.business_calendar.campaigns",
        ),
    }


def test_tbd_candidate_can_remain_incomplete() -> None:
    candidate = AnomalyPolicyCandidateV2(
        **_base_kwargs(),
        status=(
            AnomalyPolicyCandidateStatusV2
            .TBD_CALIBRATION
        ),
    )

    assert candidate.threshold_candidate is None
    assert candidate.minimum_sample_candidate is None
    assert candidate.sample_metric_name is None


def test_tbd_candidate_cannot_promote() -> None:
    candidate = AnomalyPolicyCandidateV2(
        **_base_kwargs(),
        status=(
            AnomalyPolicyCandidateStatusV2
            .TBD_CALIBRATION
        ),
    )

    try:
        candidate.to_active_policy_v2()
    except ValueError:
        return

    raise AssertionError(
        "TBD candidate must not become runtime policy."
    )


def test_active_candidate_must_be_complete() -> None:
    try:
        AnomalyPolicyCandidateV2(
            **_base_kwargs(),
            status=(
                AnomalyPolicyCandidateStatusV2.ACTIVE
            ),
        )
    except ValidationError:
        return

    raise AssertionError(
        "Incomplete ACTIVE candidate must fail."
    )


def test_active_candidate_promotes_deterministically() -> None:
    candidate = AnomalyPolicyCandidateV2(
        **_base_kwargs(),
        sample_metric_name="order_count",
        minimum_sample_candidate=Decimal("100"),
        threshold_candidate=Decimal("0.15"),
        status=(
            AnomalyPolicyCandidateStatusV2.ACTIVE
        ),
        active_policy_version="fixture_policy_v2",
    )

    policy = candidate.to_active_policy_v2()

    assert policy.metric_name == "gmv"
    assert (
        policy.comparison_type
        == ComparisonTypeV2.CAMPAIGN_YOY
    )
    assert policy.threshold_value == Decimal("0.15")
    assert (
        policy.minimum_sample_value
        == Decimal("100")
    )
    assert policy.policy_version == "fixture_policy_v2"


def test_rejected_candidate_cannot_promote() -> None:
    candidate = AnomalyPolicyCandidateV2(
        **_base_kwargs(),
        status=(
            AnomalyPolicyCandidateStatusV2.REJECTED
        ),
    )

    try:
        candidate.to_active_policy_v2()
    except ValueError:
        return

    raise AssertionError(
        "REJECTED candidate must not become runtime policy."
    )


def test_non_active_candidate_cannot_carry_version() -> None:
    try:
        AnomalyPolicyCandidateV2(
            **_base_kwargs(),
            status=(
                AnomalyPolicyCandidateStatusV2
                .TBD_CALIBRATION
            ),
            active_policy_version="should_not_exist",
        )
    except ValidationError:
        return

    raise AssertionError(
        "Non-ACTIVE candidate must not carry runtime version."
    )


def test_day83_tier_a_candidates_are_all_non_active() -> None:
    assert len(
        DAY83_TIER_A_POLICY_CANDIDATES_V2
    ) == 8

    assert all(
        candidate.status
        == AnomalyPolicyCandidateStatusV2.TBD_CALIBRATION
        for candidate
        in DAY83_TIER_A_POLICY_CANDIDATES_V2
    )

    assert all(
        candidate.threshold_candidate is None
        for candidate
        in DAY83_TIER_A_POLICY_CANDIDATES_V2
    )

    assert all(
        candidate.active_policy_version is None
        for candidate
        in DAY83_TIER_A_POLICY_CANDIDATES_V2
    )


def test_refund_candidates_do_not_invent_sample_basis() -> None:
    refund_candidates = [
        candidate
        for candidate
        in DAY83_TIER_A_POLICY_CANDIDATES_V2
        if candidate.metric_name == "refund_rate"
    ]

    assert len(refund_candidates) == 2
    assert all(
        candidate.sample_metric_name is None
        for candidate in refund_candidates
    )


TESTS = (
    test_tbd_candidate_can_remain_incomplete,
    test_tbd_candidate_cannot_promote,
    test_active_candidate_must_be_complete,
    test_active_candidate_promotes_deterministically,
    test_rejected_candidate_cannot_promote,
    test_non_active_candidate_cannot_carry_version,
    test_day83_tier_a_candidates_are_all_non_active,
    test_refund_candidates_do_not_invent_sample_basis,
)


def run_acceptance() -> None:
    passed = 0
    failed = 0

    print("=" * 80)
    print("Anomaly Policy Candidate V2 Acceptance")
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
    print(
        "Anomaly Policy Candidate V2 "
        "Acceptance Summary"
    )
    print(f"Total: {len(TESTS)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    run_acceptance()
