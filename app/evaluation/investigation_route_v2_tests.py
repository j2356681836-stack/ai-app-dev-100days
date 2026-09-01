from decimal import Decimal

from app.agents.contribution_pattern_assessment_v2 import (
    ContributionPatternAssessmentV2,
    ContributionPatternV2,
)
from app.agents.investigation_route_v2 import (
    GeographyLevelV2,
    InvestigationDecisionOwnerV2,
    InvestigationFocusDimensionV2,
    InvestigationNextDimensionV2,
    InvestigationScopeStrategyV2,
    build_system_route_from_channel_pattern_v2,
    build_user_selected_route_v2,
)


def _near_tie() -> ContributionPatternAssessmentV2:
    return ContributionPatternAssessmentV2(
        policy_version="day93_contribution_pattern_policy_v2_0",
        metric_name="gmv",
        dimension_name="channel",
        pattern=ContributionPatternV2.NEAR_TIE,
        auto_member_focus_allowed=False,
        leader_member_key="JD",
        leader_member_label="京东旗舰店",
        leader_contribution_rate=Decimal("0.2720"),
        runner_up_member_key="DOUYIN",
        runner_up_member_label="抖音商城",
        runner_up_contribution_rate=Decimal("0.2707"),
        leader_gap=Decimal("0.0013"),
        rationale=(
            "Top1 与 Top2 Contribution 差距很小，"
            "保持原 Requested Scope。"
        ),
    )


def _dominant() -> ContributionPatternAssessmentV2:
    return ContributionPatternAssessmentV2(
        policy_version="day93_contribution_pattern_policy_v2_0",
        metric_name="gmv",
        dimension_name="channel",
        pattern=ContributionPatternV2.DOMINANT,
        auto_member_focus_allowed=True,
        leader_member_key="JD",
        leader_member_label="京东旗舰店",
        leader_contribution_rate=Decimal("0.62"),
        runner_up_member_key="DOUYIN",
        runner_up_member_label="抖音商城",
        runner_up_contribution_rate=Decimal("0.20"),
        leader_gap=Decimal("0.42"),
        rationale=(
            "Top1 达到主导阈值并与 Top2 存在足够差距。"
        ),
    )


def test_f02_near_tie_system_category_keeps_global_scope() -> None:
    route = build_system_route_from_channel_pattern_v2(
        assessment=_near_tie(),
        next_dimension=InvestigationNextDimensionV2.CATEGORY,
        supporting_evidence_ids=("ev_f02_contribution",),
        planner_rationale=(
            "渠道贡献接近，建议切换到品类维度寻找更集中的变化来源。"
        ),
    )

    assert route.decision_owner == InvestigationDecisionOwnerV2.SYSTEM
    assert (
        route.scope_strategy
        == InvestigationScopeStrategyV2.KEEP_REQUESTED_SCOPE
    )
    assert route.next_dimension == InvestigationNextDimensionV2.CATEGORY
    assert route.focus_dimension is None
    assert route.focus_member_key is None

    print(
        "PASS: "
        "test_f02_near_tie_system_category_keeps_global_scope"
    )
    print("PASS: decision owner = system")
    print("PASS: scope strategy = keep_requested_scope")
    print("PASS: channel focus = none")


def test_dominant_system_category_may_focus_leader() -> None:
    route = build_system_route_from_channel_pattern_v2(
        assessment=_dominant(),
        next_dimension=InvestigationNextDimensionV2.CATEGORY,
        supporting_evidence_ids=("ev_contribution",),
        planner_rationale=(
            "主导渠道已明确，继续检查该渠道内部品类变化。"
        ),
    )

    assert route.decision_owner == InvestigationDecisionOwnerV2.SYSTEM
    assert (
        route.scope_strategy
        == InvestigationScopeStrategyV2.FOCUS_MEMBER
    )
    assert route.focus_dimension == InvestigationFocusDimensionV2.CHANNEL
    assert route.focus_member_key == "JD"
    assert route.focus_member_label == "京东旗舰店"

    print("PASS: test_dominant_system_category_may_focus_leader")


def test_user_can_explicitly_focus_jd_despite_near_tie() -> None:
    route = build_user_selected_route_v2(
        next_dimension=InvestigationNextDimensionV2.CATEGORY,
        focus_dimension=InvestigationFocusDimensionV2.CHANNEL,
        focus_member_key="JD",
        focus_member_label="京东旗舰店",
        supporting_evidence_ids=("ev_f02_contribution",),
    )

    assert route.decision_owner == InvestigationDecisionOwnerV2.USER
    assert (
        route.scope_strategy
        == InvestigationScopeStrategyV2.FOCUS_MEMBER
    )
    assert route.focus_member_key == "JD"

    print(
        "PASS: test_user_can_explicitly_focus_jd_despite_near_tie"
    )


def test_system_geography_starts_at_area_without_focus() -> None:
    route = build_system_route_from_channel_pattern_v2(
        assessment=_near_tie(),
        next_dimension=InvestigationNextDimensionV2.GEOGRAPHY,
        geography_level=GeographyLevelV2.AREA,
        supporting_evidence_ids=("ev_f02_contribution",),
        planner_rationale=(
            "渠道贡献分散，检查整体增量是否集中在某个大区。"
        ),
    )

    assert route.next_dimension == InvestigationNextDimensionV2.GEOGRAPHY
    assert route.geography_level == GeographyLevelV2.AREA
    assert (
        route.scope_strategy
        == InvestigationScopeStrategyV2.KEEP_REQUESTED_SCOPE
    )

    print("PASS: test_system_geography_starts_at_area_without_focus")


def main() -> None:
    test_f02_near_tie_system_category_keeps_global_scope()
    test_dominant_system_category_may_focus_leader()
    test_user_can_explicitly_focus_jd_despite_near_tie()
    test_system_geography_starts_at_area_without_focus()


if __name__ == "__main__":
    main()
