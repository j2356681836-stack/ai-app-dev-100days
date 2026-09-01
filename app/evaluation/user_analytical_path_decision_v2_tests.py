from app.agents.analytical_capability_registry_v2 import (
    resolve_analytical_capability_v2,
)
from app.agents.analytical_path_contract_v2 import (
    AnalyticalFocusV2,
    AnalyticalGrainV2,
    AnalyticalOperationV2,
    AnalyticalPathNodeV2,
)
from app.agents.business_analytical_intent_v2 import (
    BusinessAnalyticalIntentTargetV2,
)
from app.agents.user_analytical_path_decision_v2 import (
    UserAnalyticalExecutionModeV2,
    decide_user_analytical_path_v2,
)
from app.agents.user_investigation_intent_v2 import (
    UserInvestigationDomainV2,
)


COMPARISON = "2025-09__2025-10"
SCOPE = "scope-f02"


def _node(
    node_id: str,
    *,
    domain: UserInvestigationDomainV2,
    grain: AnalyticalGrainV2,
    focus: AnalyticalFocusV2 | None = None,
    cross_grains: tuple[AnalyticalGrainV2, ...] = (),
) -> AnalyticalPathNodeV2:
    return AnalyticalPathNodeV2(
        node_id=node_id,
        metric_name="gmv",
        domain=domain,
        operation=AnalyticalOperationV2.CHANGE_BREAKDOWN,
        grain=grain,
        focus=focus,
        cross_grains=cross_grains,
        comparison_key=COMPARISON,
        scope_fingerprint=SCOPE,
    )


def _capability(
    *,
    domain: UserInvestigationDomainV2,
    grain: AnalyticalGrainV2,
    focus: AnalyticalFocusV2 | None = None,
    cross_grains: tuple[AnalyticalGrainV2, ...] = (),
):
    return resolve_analytical_capability_v2(
        BusinessAnalyticalIntentTargetV2(
            domain=domain,
            operation=AnalyticalOperationV2.CHANGE_BREAKDOWN,
            grain=grain,
            focus=focus,
            cross_grains=cross_grains,
        )
    )


def test_only_exact_same_is_no_new_evidence() -> None:
    done = _node(
        "done-category",
        domain=UserInvestigationDomainV2.CATEGORY_PRODUCT,
        grain=AnalyticalGrainV2.CATEGORY,
    )
    target = _node(
        "target-category",
        domain=UserInvestigationDomainV2.CATEGORY_PRODUCT,
        grain=AnalyticalGrainV2.CATEGORY,
    )

    decision = decide_user_analytical_path_v2(
        target=target,
        completed=(done,),
        capability=_capability(
            domain=UserInvestigationDomainV2.CATEGORY_PRODUCT,
            grain=AnalyticalGrainV2.CATEGORY,
        ),
    )

    assert (
        decision.execution_mode
        == UserAnalyticalExecutionModeV2.NO_NEW_EVIDENCE
    )
    assert decision.query_should_execute is False
    assert decision.consumes_investigation_budget is False

    print("PASS: test_only_exact_same_is_no_new_evidence")


def test_category_to_product_is_boundary_not_repeat() -> None:
    done = _node(
        "done-category",
        domain=UserInvestigationDomainV2.CATEGORY_PRODUCT,
        grain=AnalyticalGrainV2.CATEGORY,
    )
    target = _node(
        "target-product",
        domain=UserInvestigationDomainV2.CATEGORY_PRODUCT,
        grain=AnalyticalGrainV2.PRODUCT,
    )

    decision = decide_user_analytical_path_v2(
        target=target,
        completed=(done,),
        capability=_capability(
            domain=UserInvestigationDomainV2.CATEGORY_PRODUCT,
            grain=AnalyticalGrainV2.PRODUCT,
        ),
    )

    assert (
        decision.execution_mode
        == UserAnalyticalExecutionModeV2.CAPABILITY_BOUNDARY
    )
    assert decision.relation.value == "refine"
    assert decision.query_should_execute is False

    print("PASS: test_category_to_product_is_boundary_not_repeat")


def test_area_to_province_is_user_exploration() -> None:
    done = _node(
        "done-area",
        domain=UserInvestigationDomainV2.GEOGRAPHY,
        grain=AnalyticalGrainV2.AREA,
    )
    target = _node(
        "target-province",
        domain=UserInvestigationDomainV2.GEOGRAPHY,
        grain=AnalyticalGrainV2.PROVINCE,
    )

    decision = decide_user_analytical_path_v2(
        target=target,
        completed=(done,),
        capability=_capability(
            domain=UserInvestigationDomainV2.GEOGRAPHY,
            grain=AnalyticalGrainV2.PROVINCE,
        ),
    )

    assert (
        decision.execution_mode
        == UserAnalyticalExecutionModeV2.EXPLORATION
    )
    assert decision.relation.value == "refine"
    assert decision.action_id == "drill_province"
    assert decision.query_plan_name == "gmv_province_v2"
    assert decision.consumes_investigation_budget is False
    assert decision.system_recommended is False

    print("PASS: test_area_to_province_is_user_exploration")


def test_area_to_city_requires_intermediate_province() -> None:
    done = _node(
        "done-area",
        domain=UserInvestigationDomainV2.GEOGRAPHY,
        grain=AnalyticalGrainV2.AREA,
    )
    target = _node(
        "target-city",
        domain=UserInvestigationDomainV2.GEOGRAPHY,
        grain=AnalyticalGrainV2.CITY,
    )

    decision = decide_user_analytical_path_v2(
        target=target,
        completed=(done,),
        capability=_capability(
            domain=UserInvestigationDomainV2.GEOGRAPHY,
            grain=AnalyticalGrainV2.CITY,
        ),
    )

    assert (
        decision.execution_mode
        == UserAnalyticalExecutionModeV2.HIERARCHY_STEP_REQUIRED
    )
    assert (
        decision.next_required_grain
        == AnalyticalGrainV2.PROVINCE
    )
    assert decision.required_grain_path == (
        AnalyticalGrainV2.PROVINCE,
        AnalyticalGrainV2.CITY,
    )
    assert decision.query_should_execute is False

    print("PASS: test_area_to_city_requires_intermediate_province")


def test_province_to_city_is_user_exploration() -> None:
    done = _node(
        "done-province",
        domain=UserInvestigationDomainV2.GEOGRAPHY,
        grain=AnalyticalGrainV2.PROVINCE,
    )
    target = _node(
        "target-city",
        domain=UserInvestigationDomainV2.GEOGRAPHY,
        grain=AnalyticalGrainV2.CITY,
    )

    decision = decide_user_analytical_path_v2(
        target=target,
        completed=(done,),
        capability=_capability(
            domain=UserInvestigationDomainV2.GEOGRAPHY,
            grain=AnalyticalGrainV2.CITY,
        ),
    )

    assert (
        decision.execution_mode
        == UserAnalyticalExecutionModeV2.EXPLORATION
    )
    assert decision.action_id == "drill_city"
    assert decision.consumes_investigation_budget is False

    print("PASS: test_province_to_city_is_user_exploration")


def test_switch_category_to_area_is_bounded_investigation() -> None:
    done = _node(
        "done-category",
        domain=UserInvestigationDomainV2.CATEGORY_PRODUCT,
        grain=AnalyticalGrainV2.CATEGORY,
    )
    target = _node(
        "target-area",
        domain=UserInvestigationDomainV2.GEOGRAPHY,
        grain=AnalyticalGrainV2.AREA,
    )

    decision = decide_user_analytical_path_v2(
        target=target,
        completed=(done,),
        capability=_capability(
            domain=UserInvestigationDomainV2.GEOGRAPHY,
            grain=AnalyticalGrainV2.AREA,
        ),
    )

    assert (
        decision.execution_mode
        == UserAnalyticalExecutionModeV2.INVESTIGATION
    )
    assert decision.relation.value == "switch"
    assert decision.action_id == "drill_area"
    assert decision.consumes_investigation_budget is True

    print("PASS: test_switch_category_to_area_is_bounded_investigation")


def test_old_customer_membership_keeps_slice_semantics_at_boundary() -> None:
    focus = AnalyticalFocusV2(
        source_grain=AnalyticalGrainV2.CUSTOMER_LIFECYCLE,
        member_key="old_customer",
        member_label="老客",
    )

    done = _node(
        "done-lifecycle",
        domain=UserInvestigationDomainV2.AUDIENCE,
        grain=AnalyticalGrainV2.CUSTOMER_LIFECYCLE,
    )
    target = _node(
        "target-old-membership",
        domain=UserInvestigationDomainV2.AUDIENCE,
        grain=AnalyticalGrainV2.MEMBERSHIP_LEVEL,
        focus=focus,
    )

    decision = decide_user_analytical_path_v2(
        target=target,
        completed=(done,),
        capability=_capability(
            domain=UserInvestigationDomainV2.AUDIENCE,
            grain=AnalyticalGrainV2.MEMBERSHIP_LEVEL,
            focus=focus,
        ),
    )

    assert (
        decision.execution_mode
        == UserAnalyticalExecutionModeV2.CAPABILITY_BOUNDARY
    )
    assert decision.relation.value == "slice"
    assert decision.query_should_execute is False

    print(
        "PASS: "
        "test_old_customer_membership_keeps_slice_semantics_at_boundary"
    )


def test_cross_analysis_is_boundary_not_repeat() -> None:
    done = _node(
        "done-category",
        domain=UserInvestigationDomainV2.CATEGORY_PRODUCT,
        grain=AnalyticalGrainV2.CATEGORY,
    )
    target = _node(
        "target-area-x-category",
        domain=UserInvestigationDomainV2.GEOGRAPHY,
        grain=AnalyticalGrainV2.AREA,
        cross_grains=(
            AnalyticalGrainV2.AREA,
            AnalyticalGrainV2.CATEGORY,
        ),
    )

    decision = decide_user_analytical_path_v2(
        target=target,
        completed=(done,),
        capability=_capability(
            domain=UserInvestigationDomainV2.GEOGRAPHY,
            grain=AnalyticalGrainV2.AREA,
            cross_grains=(
                AnalyticalGrainV2.AREA,
                AnalyticalGrainV2.CATEGORY,
            ),
        ),
    )

    assert (
        decision.execution_mode
        == UserAnalyticalExecutionModeV2.CAPABILITY_BOUNDARY
    )
    assert decision.relation.value == "cross_analyze"

    print("PASS: test_cross_analysis_is_boundary_not_repeat")


def main() -> None:
    test_only_exact_same_is_no_new_evidence()
    test_category_to_product_is_boundary_not_repeat()
    test_area_to_province_is_user_exploration()
    test_area_to_city_requires_intermediate_province()
    test_province_to_city_is_user_exploration()
    test_switch_category_to_area_is_bounded_investigation()
    test_old_customer_membership_keeps_slice_semantics_at_boundary()
    test_cross_analysis_is_boundary_not_repeat()


if __name__ == "__main__":
    main()
