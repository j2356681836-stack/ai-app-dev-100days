from app.agents.analytical_capability_registry_v2 import (
    AnalyticalCapabilityStatusV2,
    resolve_analytical_capability_v2,
)
from app.agents.analytical_path_contract_v2 import (
    AnalyticalGrainV2,
    AnalyticalRelationV2,
    resolve_analytical_relation_v2,
)
from app.agents.business_analytical_intent_v2 import (
    BusinessAnalyticalIntentRequestV2,
    BusinessAnalyticalIntentStatusV2,
    materialize_analytical_path_node_v2,
    resolve_business_analytical_intent_v2,
)
from app.agents.user_investigation_intent_v2 import (
    UserInvestigationDomainV2,
)


COMPARISON = "2025-09__2025-10"
SCOPE = "scope-f02"


def _resolve(
    *,
    domain: UserInvestigationDomainV2,
    hypothesis: str | None = None,
    explicit_grain: AnalyticalGrainV2 | None = None,
):
    return resolve_business_analytical_intent_v2(
        BusinessAnalyticalIntentRequestV2(
            domain=domain,
            hypothesis=hypothesis,
            explicit_grain=explicit_grain,
        )
    )


def test_category_product_requires_real_grain() -> None:
    unresolved = _resolve(
        domain=UserInvestigationDomainV2.CATEGORY_PRODUCT,
    )

    assert (
        unresolved.status
        == BusinessAnalyticalIntentStatusV2.NEEDS_CLARIFICATION
    )
    assert unresolved.clarification_grains == (
        AnalyticalGrainV2.CATEGORY,
        AnalyticalGrainV2.PRODUCT,
    )

    product = _resolve(
        domain=UserInvestigationDomainV2.CATEGORY_PRODUCT,
        hypothesis="我想继续看看具体商品的变化",
    )

    assert product.status == BusinessAnalyticalIntentStatusV2.RESOLVED
    assert product.target is not None
    assert product.target.grain == AnalyticalGrainV2.PRODUCT

    print("PASS: test_category_product_requires_real_grain")


def test_category_to_product_becomes_refine() -> None:
    category = _resolve(
        domain=UserInvestigationDomainV2.CATEGORY_PRODUCT,
        explicit_grain=AnalyticalGrainV2.CATEGORY,
    )
    product = _resolve(
        domain=UserInvestigationDomainV2.CATEGORY_PRODUCT,
        hypothesis="看一下具体商品",
    )

    assert category.target is not None
    assert product.target is not None

    completed = materialize_analytical_path_node_v2(
        target=category.target,
        metric_name="gmv",
        comparison_key=COMPARISON,
        scope_fingerprint=SCOPE,
        node_id="done-category",
    )
    target = materialize_analytical_path_node_v2(
        target=product.target,
        metric_name="gmv",
        comparison_key=COMPARISON,
        scope_fingerprint=SCOPE,
        node_id="target-product",
    )

    relation = resolve_analytical_relation_v2(
        target=target,
        completed=(completed,),
    )

    assert relation.relation == AnalyticalRelationV2.REFINE
    assert relation.query_should_be_blocked_as_repeat is False

    capability = resolve_analytical_capability_v2(
        product.target
    )
    assert (
        capability.status
        == AnalyticalCapabilityStatusV2.UNDERSTOOD_NOT_REGISTERED
    )

    print("PASS: test_category_to_product_becomes_refine")


def test_geography_grain_is_explicit_and_capability_separate() -> None:
    province = _resolve(
        domain=UserInvestigationDomainV2.GEOGRAPHY,
        hypothesis="我想看省级变化",
    )

    assert province.status == BusinessAnalyticalIntentStatusV2.RESOLVED
    assert province.target is not None
    assert province.target.grain == AnalyticalGrainV2.PROVINCE

    capability = resolve_analytical_capability_v2(
        province.target
    )

    assert capability.status == AnalyticalCapabilityStatusV2.READY
    assert capability.action_id == "drill_province"
    assert capability.query_plan_name == "gmv_province_v2"

    print(
        "PASS: "
        "test_geography_grain_is_explicit_and_capability_separate"
    )


def test_new_old_customer_semantics_are_understood() -> None:
    lifecycle = _resolve(
        domain=UserInvestigationDomainV2.AUDIENCE,
        hypothesis="我想看一下新老客的购买情况对比",
    )

    assert lifecycle.status == BusinessAnalyticalIntentStatusV2.RESOLVED
    assert lifecycle.target is not None
    assert (
        lifecycle.target.grain
        == AnalyticalGrainV2.CUSTOMER_LIFECYCLE
    )

    capability = resolve_analytical_capability_v2(
        lifecycle.target
    )

    assert (
        capability.status
        == AnalyticalCapabilityStatusV2.UNDERSTOOD_NOT_REGISTERED
    )

    print("PASS: test_new_old_customer_semantics_are_understood")


def test_old_customer_membership_is_slice_semantics() -> None:
    lifecycle = _resolve(
        domain=UserInvestigationDomainV2.AUDIENCE,
        hypothesis="先看新老客变化",
    )
    membership = _resolve(
        domain=UserInvestigationDomainV2.AUDIENCE,
        hypothesis="我还想看老客中的会员等级情况",
    )

    assert lifecycle.target is not None
    assert membership.target is not None
    assert (
        membership.target.grain
        == AnalyticalGrainV2.MEMBERSHIP_LEVEL
    )
    assert membership.target.focus is not None
    assert membership.target.focus.member_key == "old_customer"

    completed = materialize_analytical_path_node_v2(
        target=lifecycle.target,
        metric_name="gmv",
        comparison_key=COMPARISON,
        scope_fingerprint=SCOPE,
        node_id="done-lifecycle",
    )
    target = materialize_analytical_path_node_v2(
        target=membership.target,
        metric_name="gmv",
        comparison_key=COMPARISON,
        scope_fingerprint=SCOPE,
        node_id="target-old-membership",
    )

    relation = resolve_analytical_relation_v2(
        target=target,
        completed=(completed,),
    )

    assert relation.relation == AnalyticalRelationV2.SLICE
    assert relation.query_should_be_blocked_as_repeat is False

    print("PASS: test_old_customer_membership_is_slice_semantics")


def test_domain_conflict_does_not_silently_switch_tool() -> None:
    conflict = _resolve(
        domain=UserInvestigationDomainV2.ACTIVITY_PROMOTION,
        hypothesis="我想看新客和老客的购买差异",
    )

    assert (
        conflict.status
        == BusinessAnalyticalIntentStatusV2.DOMAIN_CONFLICT
    )
    assert conflict.target is None
    assert (
        UserInvestigationDomainV2.AUDIENCE
        in conflict.detected_domains
    )

    print(
        "PASS: "
        "test_domain_conflict_does_not_silently_switch_tool"
    )


def test_cross_domain_semantics_are_not_misclassified_as_repeat() -> None:
    cross = _resolve(
        domain=UserInvestigationDomainV2.GEOGRAPHY,
        hypothesis="我想看华东各品类的GMV变化",
    )

    assert cross.status == BusinessAnalyticalIntentStatusV2.RESOLVED
    assert cross.target is not None
    assert set(cross.target.cross_grains) == {
        AnalyticalGrainV2.AREA,
        AnalyticalGrainV2.CATEGORY,
    }

    capability = resolve_analytical_capability_v2(
        cross.target
    )

    assert (
        capability.status
        == AnalyticalCapabilityStatusV2.UNDERSTOOD_NOT_REGISTERED
    )

    print(
        "PASS: "
        "test_cross_domain_semantics_are_not_misclassified_as_repeat"
    )


def main() -> None:
    test_category_product_requires_real_grain()
    test_category_to_product_becomes_refine()
    test_geography_grain_is_explicit_and_capability_separate()
    test_new_old_customer_semantics_are_understood()
    test_old_customer_membership_is_slice_semantics()
    test_domain_conflict_does_not_silently_switch_tool()
    test_cross_domain_semantics_are_not_misclassified_as_repeat()


if __name__ == "__main__":
    main()
