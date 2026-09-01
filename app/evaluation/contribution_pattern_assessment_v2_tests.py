from datetime import date
from decimal import Decimal

from app.agents.contribution_analysis_v2 import (
    ContributionAnalysisResultV2,
    ContributionDecompositionTypeV2,
    ContributionDirectionV2,
    ContributionMemberResultV2,
    ContributionReconciliationStatusV2,
)
from app.agents.contribution_pattern_assessment_v2 import (
    ContributionPatternV2,
    assess_contribution_pattern_v2,
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
        comparison_type=ComparisonTypeV2.MOM,
        period_mode=PeriodModeV2.COMPLETED_PERIOD,
        alignment_mode=AlignmentModeV2.CALENDAR_ALIGNED,
        current_window=TimeWindowReferenceV2(
            start_date=date(2025, 10, 1),
            end_date=date(2025, 10, 31),
        ),
        reference_window=TimeWindowReferenceV2(
            start_date=date(2025, 9, 1),
            end_date=date(2025, 9, 30),
        ),
    )


def _result(
    *,
    rates: tuple[tuple[str, str, str], ...],
) -> ContributionAnalysisResultV2:
    members = tuple(
        ContributionMemberResultV2(
            member_key=key,
            member_label=label,
            reference_value=Decimal("100"),
            current_value=Decimal("110"),
            delta=Decimal("10"),
            contribution_rate=Decimal(rate),
            direction=ContributionDirectionV2.POSITIVE,
        )
        for key, label, rate in rates
    )

    return ContributionAnalysisResultV2(
        metric_name="gmv",
        dimension_name="channel",
        decomposition_type=ContributionDecompositionTypeV2.ADDITIVE,
        comparison=_comparison(),
        current_overall_value=Decimal("1231371.04"),
        reference_overall_value=Decimal("847765.20"),
        overall_delta=Decimal("383605.84"),
        members=members,
        negative_change_ranking=(),
        positive_change_ranking=tuple(item[0] for item in rates),
        sum_member_delta=Decimal("383605.84"),
        unexplained_remainder=Decimal("0"),
        reconciliation_tolerance=Decimal("0.01"),
        reconciliation_status=(
            ContributionReconciliationStatusV2.RECONCILED
        ),
    )


def test_f02_real_rates_are_near_tie() -> None:
    result = _result(
        rates=(
            ("JD", "京东旗舰店", "0.2720"),
            ("DOUYIN", "抖音商城", "0.2707"),
            ("TMALL", "天猫旗舰店", "0.2378"),
            ("WECHAT", "微信小程序", "0.1820"),
            ("OFFICIAL", "品牌官方商城", "0.0376"),
        )
    )

    assessment = assess_contribution_pattern_v2(result=result)

    assert assessment.pattern == ContributionPatternV2.NEAR_TIE
    assert assessment.auto_member_focus_allowed is False
    assert assessment.leader_member_key == "JD"
    assert assessment.runner_up_member_key == "DOUYIN"
    assert assessment.leader_gap == Decimal("0.0013")

    print("PASS: test_f02_real_rates_are_near_tie")
    print("PASS: pattern = near_tie")
    print("PASS: leader gap = 0.13pp")
    print("PASS: auto member focus = false")


def test_clear_leader_is_dominant() -> None:
    result = _result(
        rates=(
            ("A", "渠道A", "0.62"),
            ("B", "渠道B", "0.20"),
            ("C", "渠道C", "0.18"),
        )
    )

    assessment = assess_contribution_pattern_v2(result=result)

    assert assessment.pattern == ContributionPatternV2.DOMINANT
    assert assessment.auto_member_focus_allowed is True
    assert assessment.leader_member_key == "A"
    assert assessment.leader_gap == Decimal("0.42")

    print("PASS: test_clear_leader_is_dominant")


def test_non_dominant_non_tie_is_distributed() -> None:
    result = _result(
        rates=(
            ("A", "渠道A", "0.42"),
            ("B", "渠道B", "0.30"),
            ("C", "渠道C", "0.28"),
        )
    )

    assessment = assess_contribution_pattern_v2(result=result)

    assert assessment.pattern == ContributionPatternV2.DISTRIBUTED
    assert assessment.auto_member_focus_allowed is False

    print("PASS: test_non_dominant_non_tie_is_distributed")


def main() -> None:
    test_f02_real_rates_are_near_tie()
    test_clear_leader_is_dominant()
    test_non_dominant_non_tie_is_distributed()


if __name__ == "__main__":
    main()
