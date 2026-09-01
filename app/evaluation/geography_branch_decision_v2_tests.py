from decimal import Decimal

from app.agents.focused_change_breakdown_v2 import (
    FocusedChangeDimensionV2,
    FocusedChangeObservationV2,
    analyze_focused_change_breakdown_v2,
)
from app.agents.geography_branch_decision_v2 import (
    GeographyBranchDecisionReasonV2,
    GeographyBranchDecisionTypeV2,
    build_geography_branch_decision_v2,
)
from app.agents.investigation_route_v2 import GeographyLevelV2
from app.agents.investigation_step_assessment_v2 import (
    assess_investigation_step_v2,
)


def _assessment(*, east_current: str, south_current: str):
    result = analyze_focused_change_breakdown_v2(
        dimension_name=FocusedChangeDimensionV2.AREA,
        focus_member_key="__overall__",
        focus_member_label="整体GMV",
        reference_focus_value=Decimal("100"),
        current_focus_value=Decimal("200"),
        reference_members=(
            FocusedChangeObservationV2(
                member_key="east",
                member_label="华东",
                value=Decimal("50"),
            ),
            FocusedChangeObservationV2(
                member_key="south",
                member_label="华南",
                value=Decimal("50"),
            ),
        ),
        current_members=(
            FocusedChangeObservationV2(
                member_key="east",
                member_label="华东",
                value=Decimal(east_current),
            ),
            FocusedChangeObservationV2(
                member_key="south",
                member_label="华南",
                value=Decimal(south_current),
            ),
        ),
    )
    return assess_investigation_step_v2(
        result=result,
        is_overall_scope=True,
    )


def test_non_dominant_area_stops_without_query_or_budget() -> None:
    decision = build_geography_branch_decision_v2(
        current_level=GeographyLevelV2.AREA,
        assessment=_assessment(
            east_current="105",
            south_current="95",
        ),
    )

    assert decision.decision == GeographyBranchDecisionTypeV2.STOP_INVESTIGATION
    assert decision.reason == GeographyBranchDecisionReasonV2.NO_DOMINANT_GEOGRAPHY
    assert decision.query_executed is False
    assert decision.next_investigation_level is None
    assert decision.exploration_available is True
    assert decision.exploration_level == GeographyLevelV2.PROVINCE
    assert decision.recommended_next_domains

    print("PASS: test_non_dominant_area_stops_without_query_or_budget")


def test_dominant_area_allows_investigation_to_province() -> None:
    decision = build_geography_branch_decision_v2(
        current_level=GeographyLevelV2.AREA,
        assessment=_assessment(
            east_current="130",
            south_current="70",
        ),
    )

    assert decision.decision == GeographyBranchDecisionTypeV2.CONTINUE_INVESTIGATION
    assert decision.reason == GeographyBranchDecisionReasonV2.DOMINANT_FOCUS
    assert decision.query_executed is False
    assert decision.next_investigation_level == GeographyLevelV2.PROVINCE
    assert decision.exploration_available is False

    print("PASS: test_dominant_area_allows_investigation_to_province")


def test_city_is_geography_leaf() -> None:
    decision = build_geography_branch_decision_v2(
        current_level=GeographyLevelV2.CITY,
        assessment=None,
    )

    assert decision.decision == GeographyBranchDecisionTypeV2.LEAF_REACHED
    assert decision.reason == GeographyBranchDecisionReasonV2.GEOGRAPHY_LEAF
    assert decision.query_executed is False
    assert decision.next_investigation_level is None
    assert decision.exploration_available is False

    print("PASS: test_city_is_geography_leaf")


def main() -> None:
    test_non_dominant_area_stops_without_query_or_budget()
    test_dominant_area_allows_investigation_to_province()
    test_city_is_geography_leaf()


if __name__ == "__main__":
    main()
