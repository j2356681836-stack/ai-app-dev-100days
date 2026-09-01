from app.agents.analytical_path_contract_v2 import (
    AnalyticalFocusV2,
    AnalyticalGrainV2,
    AnalyticalOperationV2,
    AnalyticalPathNodeV2,
    AnalyticalRelationV2,
    analytical_descendant_path_v2,
    resolve_analytical_relation_v2,
)
from app.agents.user_investigation_intent_v2 import (
    UserInvestigationDomainV2,
)


COMPARISON_KEY = "2025-09__2025-10"
SCOPE_KEY = "scope-f02-overall"


def _node(
    node_id: str,
    *,
    domain: UserInvestigationDomainV2,
    grain: AnalyticalGrainV2,
    operation: AnalyticalOperationV2 = (
        AnalyticalOperationV2.CHANGE_BREAKDOWN
    ),
    focus: AnalyticalFocusV2 | None = None,
    cross_grains: tuple[AnalyticalGrainV2, ...] = (),
) -> AnalyticalPathNodeV2:
    return AnalyticalPathNodeV2(
        node_id=node_id,
        metric_name="gmv",
        domain=domain,
        operation=operation,
        grain=grain,
        focus=focus,
        cross_grains=cross_grains,
        comparison_key=COMPARISON_KEY,
        scope_fingerprint=SCOPE_KEY,
    )


def test_same_requires_full_semantic_signature() -> None:
    category = _node(
        "done-category",
        domain=UserInvestigationDomainV2.CATEGORY_PRODUCT,
        grain=AnalyticalGrainV2.CATEGORY,
    )

    exact = _node(
        "target-category",
        domain=UserInvestigationDomainV2.CATEGORY_PRODUCT,
        grain=AnalyticalGrainV2.CATEGORY,
    )

    decision = resolve_analytical_relation_v2(
        target=exact,
        completed=(category,),
    )

    assert decision.relation == AnalyticalRelationV2.SAME
    assert decision.query_should_be_blocked_as_repeat is True

    category_composition = _node(
        "target-category-composition",
        domain=UserInvestigationDomainV2.CATEGORY_PRODUCT,
        grain=AnalyticalGrainV2.CATEGORY,
        operation=AnalyticalOperationV2.COMPOSITION,
    )

    different_operation = resolve_analytical_relation_v2(
        target=category_composition,
        completed=(category,),
    )

    assert different_operation.relation != AnalyticalRelationV2.SAME
    assert (
        different_operation.query_should_be_blocked_as_repeat
        is False
    )

    print("PASS: test_same_requires_full_semantic_signature")


def test_category_to_product_is_refine_not_repeat() -> None:
    category = _node(
        "done-category",
        domain=UserInvestigationDomainV2.CATEGORY_PRODUCT,
        grain=AnalyticalGrainV2.CATEGORY,
    )
    product = _node(
        "target-product",
        domain=UserInvestigationDomainV2.CATEGORY_PRODUCT,
        grain=AnalyticalGrainV2.PRODUCT,
    )

    decision = resolve_analytical_relation_v2(
        target=product,
        completed=(category,),
    )

    assert decision.relation == AnalyticalRelationV2.REFINE
    assert decision.required_grain_path == (
        AnalyticalGrainV2.PRODUCT,
    )
    assert decision.direct_target_allowed is True
    assert decision.query_should_be_blocked_as_repeat is False

    print("PASS: test_category_to_product_is_refine_not_repeat")


def test_geography_cannot_silently_skip_hierarchy() -> None:
    assert analytical_descendant_path_v2(
        ancestor=AnalyticalGrainV2.AREA,
        descendant=AnalyticalGrainV2.CITY,
    ) == (
        AnalyticalGrainV2.PROVINCE,
        AnalyticalGrainV2.CITY,
    )

    area = _node(
        "done-area",
        domain=UserInvestigationDomainV2.GEOGRAPHY,
        grain=AnalyticalGrainV2.AREA,
    )
    city = _node(
        "target-city",
        domain=UserInvestigationDomainV2.GEOGRAPHY,
        grain=AnalyticalGrainV2.CITY,
    )

    decision = resolve_analytical_relation_v2(
        target=city,
        completed=(area,),
    )

    assert decision.relation == AnalyticalRelationV2.REFINE
    assert decision.next_required_grain == AnalyticalGrainV2.PROVINCE
    assert decision.direct_target_allowed is False
    assert decision.query_should_be_blocked_as_repeat is False

    print("PASS: test_geography_cannot_silently_skip_hierarchy")


def test_old_customer_to_membership_is_slice_not_repeat() -> None:
    lifecycle = _node(
        "done-lifecycle",
        domain=UserInvestigationDomainV2.AUDIENCE,
        grain=AnalyticalGrainV2.CUSTOMER_LIFECYCLE,
    )

    old_customer_membership = _node(
        "target-old-membership",
        domain=UserInvestigationDomainV2.AUDIENCE,
        grain=AnalyticalGrainV2.MEMBERSHIP_LEVEL,
        focus=AnalyticalFocusV2(
            source_grain=AnalyticalGrainV2.CUSTOMER_LIFECYCLE,
            member_key="old_customer",
            member_label="老客",
        ),
    )

    decision = resolve_analytical_relation_v2(
        target=old_customer_membership,
        completed=(lifecycle,),
    )

    assert decision.relation == AnalyticalRelationV2.SLICE
    assert decision.query_should_be_blocked_as_repeat is False

    print("PASS: test_old_customer_to_membership_is_slice_not_repeat")


def test_switch_dimension_is_not_repeat() -> None:
    category = _node(
        "done-category",
        domain=UserInvestigationDomainV2.CATEGORY_PRODUCT,
        grain=AnalyticalGrainV2.CATEGORY,
    )
    geography = _node(
        "target-area",
        domain=UserInvestigationDomainV2.GEOGRAPHY,
        grain=AnalyticalGrainV2.AREA,
    )

    decision = resolve_analytical_relation_v2(
        target=geography,
        completed=(category,),
    )

    assert decision.relation == AnalyticalRelationV2.SWITCH
    assert decision.query_should_be_blocked_as_repeat is False

    print("PASS: test_switch_dimension_is_not_repeat")


def test_cross_analysis_is_not_blocked_by_single_dimension_history() -> None:
    category = _node(
        "done-category",
        domain=UserInvestigationDomainV2.CATEGORY_PRODUCT,
        grain=AnalyticalGrainV2.CATEGORY,
    )

    geography_by_category = _node(
        "target-area-x-category",
        domain=UserInvestigationDomainV2.GEOGRAPHY,
        grain=AnalyticalGrainV2.AREA,
        cross_grains=(
            AnalyticalGrainV2.AREA,
            AnalyticalGrainV2.CATEGORY,
        ),
    )

    decision = resolve_analytical_relation_v2(
        target=geography_by_category,
        completed=(category,),
    )

    assert decision.relation == AnalyticalRelationV2.CROSS_ANALYZE
    assert decision.query_should_be_blocked_as_repeat is False

    print(
        "PASS: "
        "test_cross_analysis_is_not_blocked_by_single_dimension_history"
    )


def main() -> None:
    test_same_requires_full_semantic_signature()
    test_category_to_product_is_refine_not_repeat()
    test_geography_cannot_silently_skip_hierarchy()
    test_old_customer_to_membership_is_slice_not_repeat()
    test_switch_dimension_is_not_repeat()
    test_cross_analysis_is_not_blocked_by_single_dimension_history()


if __name__ == "__main__":
    main()
