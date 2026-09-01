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
)
from app.agents.investigation_route_v2 import (
    InvestigationDecisionOwnerV2,
    InvestigationFocusDimensionV2,
    InvestigationNextDimensionV2,
    InvestigationScopeStrategyV2,
)
from app.delivery.contribution_investigation_route_v2 import (
    build_contribution_investigation_route_v2,
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
    reconciliation_status=(
        ContributionReconciliationStatusV2.RECONCILED
    ),
) -> ContributionAnalysisResultV2:
    overall_delta = Decimal("383605.84")

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
        overall_delta=overall_delta,
        members=members,
        negative_change_ranking=(),
        positive_change_ranking=tuple(
            key
            for key, _, _ in rates
        ),
        sum_member_delta=overall_delta,
        unexplained_remainder=Decimal("0"),
        reconciliation_tolerance=Decimal("0.01"),
        reconciliation_status=reconciliation_status,
    )


def test_f02_near_tie_recommends_global_category() -> None:
    recommendation = build_contribution_investigation_route_v2(
        contribution=_result(
            rates=(
                ("JD", "京东旗舰店", "0.2720"),
                ("DOUYIN", "抖音商城", "0.2707"),
                ("TMALL", "天猫旗舰店", "0.2378"),
                ("WECHAT", "微信小程序", "0.1820"),
                ("OFFICIAL", "品牌官方商城", "0.0376"),
            ),
        ),
        contribution_evidence_id="ev_f02_contribution",
    )

    assert recommendation is not None
    assert (
        recommendation.pattern_assessment.pattern
        == ContributionPatternV2.NEAR_TIE
    )
    assert (
        recommendation.route.decision_owner
        == InvestigationDecisionOwnerV2.SYSTEM
    )
    assert (
        recommendation.route.scope_strategy
        == InvestigationScopeStrategyV2.KEEP_REQUESTED_SCOPE
    )
    assert (
        recommendation.route.next_dimension
        == InvestigationNextDimensionV2.CATEGORY
    )
    assert recommendation.route.focus_member_key is None
    assert "0.13" in recommendation.recommendation_summary

    print("PASS: test_f02_near_tie_recommends_global_category")
    print("PASS: pattern = near_tie")
    print("PASS: route = global category")
    print("PASS: channel focus = none")


def test_dominant_channel_recommends_focused_category() -> None:
    recommendation = build_contribution_investigation_route_v2(
        contribution=_result(
            rates=(
                ("JD", "京东旗舰店", "0.62"),
                ("DOUYIN", "抖音商城", "0.20"),
                ("TMALL", "天猫旗舰店", "0.18"),
            ),
        ),
        contribution_evidence_id="ev_contribution",
    )

    assert recommendation is not None
    assert (
        recommendation.pattern_assessment.pattern
        == ContributionPatternV2.DOMINANT
    )
    assert (
        recommendation.route.scope_strategy
        == InvestigationScopeStrategyV2.FOCUS_MEMBER
    )
    assert (
        recommendation.route.focus_dimension
        == InvestigationFocusDimensionV2.CHANNEL
    )
    assert recommendation.route.focus_member_key == "JD"
    assert (
        recommendation.route.next_dimension
        == InvestigationNextDimensionV2.CATEGORY
    )

    print(
        "PASS: "
        "test_dominant_channel_recommends_focused_category"
    )


def test_unreconciled_contribution_has_no_route() -> None:
    recommendation = build_contribution_investigation_route_v2(
        contribution=_result(
            rates=(
                ("JD", "京东旗舰店", "0.60"),
                ("DOUYIN", "抖音商城", "0.40"),
            ),
            reconciliation_status=(
                ContributionReconciliationStatusV2.NOT_RECONCILED
            ),
        ),
        contribution_evidence_id="ev_unreconciled",
    )

    assert recommendation is None

    print("PASS: test_unreconciled_contribution_has_no_route")


def main() -> None:
    test_f02_near_tie_recommends_global_category()
    test_dominant_channel_recommends_focused_category()
    test_unreconciled_contribution_has_no_route()


if __name__ == "__main__":
    main()
