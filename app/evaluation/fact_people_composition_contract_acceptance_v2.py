from app.semantic_layer.membership_composition_query_plan_v2 import (
    build_gmv_membership_level_plan,
)
from app.semantic_layer.query_plan_v2_catalog_builder import (
    build_query_plan_v2_catalog,
)


def main() -> None:
    plan = build_gmv_membership_level_plan()

    assert plan.name == "gmv_membership_level_v2"
    assert plan.metric == "gmv"
    assert plan.result_grain == "membership_level"

    logic = plan.query_logic
    assert logic.group_by == (
        "fo.member_level_at_order",
    )

    outputs = {
        item.field: item.expression
        for item in logic.outputs
    }

    assert (
        outputs["membership_segment"]
        == "COALESCE(fo.member_level_at_order, 'NON_MEMBER')"
    )
    assert outputs["gmv"] == "SUM(foi.item_paid_amount)"

    assert (
        "fact_orders.member_level_at_order"
        in plan.resource_contract.required_columns
    )

    assert (
        plan.scope_contract.scope_mode.value
        == "predicate_safe"
    )

    catalog = build_query_plan_v2_catalog()
    names = {
        item.name
        for item in catalog.query_plans
    }

    assert len(catalog.query_plans) == 50
    assert "gmv_membership_level_v2" in names

    print("PASS: 支付时会员等级 GMV Query Plan 合同成立")
    print("PASS: NULL 会员快照显式归入 NON_MEMBER")
    print("PASS: Region / Channel Scope 继续走 predicate_safe")
    print("PASS: Canonical Query Plan Catalog = 50 plans")
    print("=" * 72)
    print("Fact People Composition Contract Acceptance passed.")


if __name__ == "__main__":
    main()
