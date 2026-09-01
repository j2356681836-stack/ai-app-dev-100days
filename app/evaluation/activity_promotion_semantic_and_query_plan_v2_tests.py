from app.agents.analytical_capability_registry_v2 import (
    AnalyticalCapabilityStatusV2,
    resolve_analytical_capability_v2,
)
from app.agents.analytical_path_contract_v2 import (
    AnalyticalGrainV2,
)
from app.agents.business_analytical_intent_v2 import (
    BusinessAnalyticalIntentRequestV2,
    BusinessAnalyticalIntentStatusV2,
    resolve_business_analytical_intent_v2,
)
from app.agents.user_investigation_intent_v2 import (
    UserInvestigationDomainV2,
)
from app.semantic_layer.campaign_query_plan_v2_builder import (
    build_gmv_campaign_plan_v2,
)
from app.semantic_layer.query_plan_v2_catalog_builder import (
    build_query_plan_v2_catalog,
)
from app.ui.analytical_ui_projection_v2 import (
    explicit_grain_options_v2,
)


def _resolve(
    *,
    hypothesis: str | None = None,
    explicit_grain: AnalyticalGrainV2 | None = None,
):
    return resolve_business_analytical_intent_v2(
        BusinessAnalyticalIntentRequestV2(
            domain=(
                UserInvestigationDomainV2.ACTIVITY_PROMOTION
            ),
            hypothesis=hypothesis,
            explicit_grain=explicit_grain,
        )
    )


def test_activity_domain_is_not_flattened_to_campaign() -> None:
    resolution = _resolve()

    assert (
        resolution.status
        == BusinessAnalyticalIntentStatusV2.NEEDS_CLARIFICATION
    )
    assert resolution.clarification_grains == (
        AnalyticalGrainV2.CAMPAIGN,
        AnalyticalGrainV2.PROMOTION,
    )

    assert explicit_grain_options_v2(
        UserInvestigationDomainV2.ACTIVITY_PROMOTION
    ) == (
        AnalyticalGrainV2.CAMPAIGN,
        AnalyticalGrainV2.PROMOTION,
    )

    print(
        "PASS: "
        "test_activity_domain_is_not_flattened_to_campaign"
    )


def test_double11_preheat_resolves_to_campaign() -> None:
    resolution = _resolve(
        hypothesis="我怀疑10月增长和双十一预热活动有关"
    )

    assert (
        resolution.status
        == BusinessAnalyticalIntentStatusV2.RESOLVED
    )
    assert resolution.target is not None
    assert (
        resolution.target.grain
        == AnalyticalGrainV2.CAMPAIGN
    )

    # Campaign Runtime has now been formally registered.
    capability = resolve_analytical_capability_v2(
        resolution.target
    )
    assert (
        capability.status
        == AnalyticalCapabilityStatusV2.READY
    )
    assert capability.action_id == "drill_campaign"
    assert capability.query_plan_name == "gmv_campaign_v2"

    print(
        "PASS: "
        "test_double11_preheat_resolves_to_campaign"
    )


def test_discount_coupon_resolves_to_promotion() -> None:
    resolution = _resolve(
        hypothesis="我想看看优惠券和满减的变化"
    )

    assert (
        resolution.status
        == BusinessAnalyticalIntentStatusV2.RESOLVED
    )
    assert resolution.target is not None
    assert (
        resolution.target.grain
        == AnalyticalGrainV2.PROMOTION
    )

    capability = resolve_analytical_capability_v2(
        resolution.target
    )
    assert (
        capability.status
        == AnalyticalCapabilityStatusV2
        .UNDERSTOOD_NOT_REGISTERED
    )

    print(
        "PASS: "
        "test_discount_coupon_resolves_to_promotion"
    )


def test_gmv_campaign_plan_preserves_scope_and_non_campaign_bucket() -> None:
    plan = build_gmv_campaign_plan_v2()

    assert plan.name == "gmv_campaign_v2"
    assert plan.metric == "gmv"
    assert plan.result_grain == "campaign"

    logic = plan.query_logic

    assert tuple(logic.group_by) == (
        "dca.campaign_id",
        "dca.campaign_name",
    )

    joins = {
        (item.table, item.alias): item
        for item in logic.joins
    }

    campaign_join = joins[
        ("dim_campaign", "dca")
    ]
    assert campaign_join.join_type == "left"

    outputs = {
        item.field: item.expression
        for item in logic.outputs
    }

    assert outputs["campaign_name"] == (
        "COALESCE(dca.campaign_name, '非活动订单')"
    )
    assert outputs["gmv"] == (
        "SUM(foi.item_paid_amount)"
    )

    assert set(
        plan.scope_contract.required_dimensions
    ) == {"channel", "region"}

    assert "fact_orders.campaign_id" in (
        plan.resource_contract.required_columns
    )
    assert "dim_campaign.campaign_name" in (
        plan.resource_contract.required_columns
    )

    assert (
        plan.result_contract.minimum_group_size_required
        is True
    )
    assert (
        plan.result_contract.group_size_field
        == "__group_size"
    )

    print(
        "PASS: "
        "test_gmv_campaign_plan_preserves_scope_and_non_campaign_bucket"
    )


def test_campaign_plan_is_in_canonical_catalog() -> None:
    catalog = build_query_plan_v2_catalog()

    by_name = {
        plan.name: plan
        for plan in catalog.query_plans
    }

    assert "gmv_campaign_v2" in by_name
    assert len(catalog.query_plans) == 60

    print(
        "PASS: "
        "test_campaign_plan_is_in_canonical_catalog"
    )


def main() -> None:
    test_activity_domain_is_not_flattened_to_campaign()
    test_double11_preheat_resolves_to_campaign()
    test_discount_coupon_resolves_to_promotion()
    test_gmv_campaign_plan_preserves_scope_and_non_campaign_bucket()
    test_campaign_plan_is_in_canonical_catalog()


if __name__ == "__main__":
    main()
