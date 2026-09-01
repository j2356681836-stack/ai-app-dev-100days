from decimal import Decimal

from app.agents.focused_change_breakdown_v2 import (
    FocusedChangeDimensionV2, FocusedChangeObservationV2,
    analyze_focused_change_breakdown_v2,
)
from app.agents.geography_hierarchy_v2 import (
    GeographyFocusScopeV2, get_geography_member_v2,
    merge_requested_scope_with_geography_focus_v2,
)
from app.agents.investigation_route_v2 import (
    GeographyLevelV2, InvestigationDecisionOwnerV2,
    InvestigationNextDimensionV2, InvestigationRouteV2,
    InvestigationScopeStrategyV2,
)
from app.agents.investigation_step_assessment_v2 import (
    ChangeConcentrationPatternV2, assess_investigation_step_v2,
)
from app.agents.user_investigation_intent_v2 import (
    UserInvestigationCapabilityStatusV2, UserInvestigationDomainV2,
    UserInvestigationIntentV2, resolve_user_investigation_intent_v2,
)
from app.delivery.investigation_runtime_v2 import (
    _day93_action_id_from_route_v2, _day93_geography_action_v2,
)


def test_geography_user_intent_is_ready_from_area():
    result = resolve_user_investigation_intent_v2(
        UserInvestigationIntentV2(domain=UserInvestigationDomainV2.GEOGRAPHY)
    )
    assert result.status == UserInvestigationCapabilityStatusV2.READY
    assert result.mapped_action_id == "drill_area"
    assert result.mapped_plan_name == "gmv_area_v2"
    print("PASS: test_geography_user_intent_is_ready_from_area")


def test_geography_action_contracts_are_hierarchical():
    expected = {
        GeographyLevelV2.AREA: ("drill_area", "gmv_area_v2"),
        GeographyLevelV2.PROVINCE: ("drill_province", "gmv_province_v2"),
        GeographyLevelV2.CITY: ("drill_city", "gmv_city_v2"),
    }
    for level, (action_id, plan_name) in expected.items():
        action = _day93_geography_action_v2(level)
        assert action.action_id == action_id
        args = {item.name: item.value for item in action.arguments}
        assert args["query_plan_name"] == plan_name
    print("PASS: test_geography_action_contracts_are_hierarchical")


def test_system_geography_route_starts_at_area():
    route = InvestigationRouteV2(
        decision_owner=InvestigationDecisionOwnerV2.SYSTEM,
        scope_strategy=InvestigationScopeStrategyV2.KEEP_REQUESTED_SCOPE,
        next_dimension=InvestigationNextDimensionV2.GEOGRAPHY,
        geography_level=GeographyLevelV2.AREA,
        supporting_evidence_ids=("ev-route",),
        rationale="test",
    )
    assert _day93_action_id_from_route_v2(route) == "drill_area"
    print("PASS: test_system_geography_route_starts_at_area")


def test_area_assessment_only_recommends_deeper_when_dominant():
    dominant = analyze_focused_change_breakdown_v2(
        dimension_name=FocusedChangeDimensionV2.AREA,
        focus_member_key="__overall__", focus_member_label="整体GMV",
        reference_focus_value=Decimal("100"), current_focus_value=Decimal("200"),
        reference_members=(
            FocusedChangeObservationV2(member_key="east", member_label="华东", value=Decimal("50")),
            FocusedChangeObservationV2(member_key="south", member_label="华南", value=Decimal("50")),
        ),
        current_members=(
            FocusedChangeObservationV2(member_key="east", member_label="华东", value=Decimal("130")),
            FocusedChangeObservationV2(member_key="south", member_label="华南", value=Decimal("70")),
        ),
    )
    assessment = assess_investigation_step_v2(result=dominant, is_overall_scope=True)
    assert assessment.pattern == ChangeConcentrationPatternV2.DOMINANT
    assert assessment.leader_member_key == "east"
    assert "省级" in assessment.next_step_recommendation

    near_tie = analyze_focused_change_breakdown_v2(
        dimension_name=FocusedChangeDimensionV2.AREA,
        focus_member_key="__overall__", focus_member_label="整体GMV",
        reference_focus_value=Decimal("100"), current_focus_value=Decimal("200"),
        reference_members=(
            FocusedChangeObservationV2(member_key="east", member_label="华东", value=Decimal("50")),
            FocusedChangeObservationV2(member_key="south", member_label="华南", value=Decimal("50")),
        ),
        current_members=(
            FocusedChangeObservationV2(member_key="east", member_label="华东", value=Decimal("101")),
            FocusedChangeObservationV2(member_key="south", member_label="华南", value=Decimal("99")),
        ),
    )
    assessment2 = assess_investigation_step_v2(result=near_tie, is_overall_scope=True)
    assert assessment2.pattern == ChangeConcentrationPatternV2.NEAR_TIE
    assert "不会机械选择 Top1" in assessment2.next_step_recommendation
    print("PASS: test_area_assessment_only_recommends_deeper_when_dominant")


def test_geography_focus_comparison_values_are_validated():
    east = get_geography_member_v2(level=GeographyLevelV2.AREA, member_key="east")
    focus = GeographyFocusScopeV2(
        level=GeographyLevelV2.AREA, member_key=east.member_key,
        member_label=east.member_label, region_codes=east.region_codes,
        source_evidence_id="ev-east", reference_value=Decimal("100"),
        current_value=Decimal("160"), delta=Decimal("60"),
    )
    effective = merge_requested_scope_with_geography_focus_v2(
        requested_scope=None, geography_focus=focus
    )
    assert effective is not None and effective.region_codes == east.region_codes
    try:
        focus.model_copy(update={"delta": Decimal("59")})
        GeographyFocusScopeV2(**{**focus.model_dump(), "delta": Decimal("59")})
    except ValueError:
        pass
    else:
        raise AssertionError("inconsistent geography delta must fail closed")
    print("PASS: test_geography_focus_comparison_values_are_validated")


def main():
    test_geography_user_intent_is_ready_from_area()
    test_geography_action_contracts_are_hierarchical()
    test_system_geography_route_starts_at_area()
    test_area_assessment_only_recommends_deeper_when_dominant()
    test_geography_focus_comparison_values_are_validated()


if __name__ == "__main__":
    main()
