from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import ValidationError

from app.agents.contribution_analysis_v2 import (
    ContributionDirectionV2,
    ContributionObservationV2,
    ContributionReconciliationStatusV2,
    analyze_additive_contribution_v2,
)

from app.semantic_layer.time_comparison_contract_v2 import (
    AlignmentModeV2,
    ComparisonTypeV2,
    PeriodModeV2,
    TimeComparisonContractV2,
    TimeWindowReferenceV2,
)


PASSED = 0
TOTAL = 0


def check(name: str, condition: bool) -> None:
    global PASSED, TOTAL
    TOTAL += 1
    if not condition:
        raise AssertionError(name)
    PASSED += 1
    print(f"PASS {TOTAL:02d}: {name}")


def expect_value_error(name: str, fn) -> None:
    try:
        fn()
    except (ValueError, ValidationError):
        check(name, True)
        return
    check(name, False)


def obs(key: str, label: str, value: str) -> ContributionObservationV2:
    return ContributionObservationV2(
        member_key=key,
        member_label=label,
        value=Decimal(value),
    )



def yoy() -> TimeComparisonContractV2:
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


def main() -> None:
    decline = analyze_additive_contribution_v2(
        metric_name="gmv",
        dimension_name="channel",
        comparison=yoy(),
        current_overall_value=Decimal("900"),
        reference_overall_value=Decimal("1000"),
        current_members=(
            obs("tmall", "天猫", "350"),
            obs("douyin", "抖音", "270"),
            obs("jd", "京东", "180"),
            obs("red", "小红书", "100"),
        ),
        reference_members=(
            obs("tmall", "天猫", "500"),
            obs("douyin", "抖音", "300"),
            obs("jd", "京东", "150"),
            obs("red", "小红书", "50"),
        ),
    )

    by_key = {item.member_key: item for item in decline.members}

    check(
        "overall delta is deterministic",
        decline.overall_delta == Decimal("-100"),
    )
    check(
        "comparison contract is bound to contribution result",
        decline.comparison == yoy(),
    )
    check(
        "contribution rate may exceed 100 percent",
        by_key["tmall"].contribution_rate == Decimal("1.5"),
    )
    check(
        "positive offset has negative contribution rate during decline",
        by_key["red"].contribution_rate == Decimal("-0.5"),
    )
    check(
        "negative changes are ranked by largest decline first",
        decline.negative_change_ranking == ("tmall", "douyin"),
    )
    check(
        "positive changes are ranked by largest increase first",
        decline.positive_change_ranking == ("red", "jd"),
    )
    check(
        "member deltas reconcile to overall delta",
        decline.reconciliation_status
        == ContributionReconciliationStatusV2.RECONCILED
        and decline.unexplained_remainder == Decimal("0"),
    )

    aligned = analyze_additive_contribution_v2(
        metric_name="gmv",
        dimension_name="channel",
        comparison=yoy(),
        current_overall_value=Decimal("120"),
        reference_overall_value=Decimal("150"),
        current_members=(
            obs("tmall", "天猫", "70"),
            obs("douyin", "抖音", "50"),
        ),
        reference_members=(
            obs("tmall", "天猫", "70"),
            obs("jd", "京东", "80"),
        ),
    )
    aligned_by_key = {item.member_key: item for item in aligned.members}

    check(
        "current-only member aligns reference to zero",
        aligned_by_key["douyin"].reference_value == Decimal("0")
        and aligned_by_key["douyin"].delta == Decimal("50"),
    )
    check(
        "reference-only member aligns current to zero",
        aligned_by_key["jd"].current_value == Decimal("0")
        and aligned_by_key["jd"].delta == Decimal("-80"),
    )

    mismatch = analyze_additive_contribution_v2(
        metric_name="gmv",
        dimension_name="channel",
        comparison=yoy(),
        current_overall_value=Decimal("90"),
        reference_overall_value=Decimal("100"),
        current_members=(obs("tmall", "天猫", "90"),),
        reference_members=(obs("tmall", "天猫", "95"),),
    )
    check(
        "reconciliation gap remains explicit instead of being invented away",
        mismatch.reconciliation_status
        == ContributionReconciliationStatusV2.NOT_RECONCILED
        and mismatch.unexplained_remainder == Decimal("-5"),
    )

    zero_delta = analyze_additive_contribution_v2(
        metric_name="gmv",
        dimension_name="channel",
        comparison=yoy(),
        current_overall_value=Decimal("100"),
        reference_overall_value=Decimal("100"),
        current_members=(
            obs("tmall", "天猫", "60"),
            obs("jd", "京东", "40"),
        ),
        reference_members=(
            obs("tmall", "天猫", "50"),
            obs("jd", "京东", "50"),
        ),
    )
    check(
        "zero overall delta leaves contribution rate undefined",
        all(item.contribution_rate is None for item in zero_delta.members),
    )
    check(
        "zero overall delta can still expose offsetting member changes",
        {
            item.member_key: item.direction
            for item in zero_delta.members
        }
        == {
            "jd": ContributionDirectionV2.NEGATIVE,
            "tmall": ContributionDirectionV2.POSITIVE,
        },
    )

    expect_value_error(
        "duplicate member keys fail closed",
        lambda: analyze_additive_contribution_v2(
            metric_name="gmv",
            dimension_name="channel",
        comparison=yoy(),
            current_overall_value=Decimal("10"),
            reference_overall_value=Decimal("10"),
            current_members=(
                obs("tmall", "天猫", "5"),
                obs("tmall", "天猫", "5"),
            ),
            reference_members=(obs("tmall", "天猫", "10"),),
        ),
    )

    expect_value_error(
        "member label drift across windows fails closed",
        lambda: analyze_additive_contribution_v2(
            metric_name="gmv",
            dimension_name="channel",
        comparison=yoy(),
            current_overall_value=Decimal("10"),
            reference_overall_value=Decimal("10"),
            current_members=(obs("tmall", "天猫旗舰", "10"),),
            reference_members=(obs("tmall", "天猫", "10"),),
        ),
    )

    expect_value_error(
        "unsupported ratio metric cannot silently use additive math",
        lambda: analyze_additive_contribution_v2(
            metric_name="refund_rate",
            dimension_name="channel",
        comparison=yoy(),
            current_overall_value=Decimal("0.1"),
            reference_overall_value=Decimal("0.08"),
            current_members=(),
            reference_members=(),
        ),
    )

    expect_value_error(
        "negative reconciliation tolerance is invalid",
        lambda: analyze_additive_contribution_v2(
            metric_name="gmv",
            dimension_name="channel",
        comparison=yoy(),
            current_overall_value=Decimal("10"),
            reference_overall_value=Decimal("10"),
            current_members=(),
            reference_members=(),
            reconciliation_tolerance=Decimal("-0.01"),
        ),
    )

    print()
    print(f"Day84 Contribution Analysis V2 Acceptance: {PASSED}/{TOTAL} PASS")


if __name__ == "__main__":
    main()
