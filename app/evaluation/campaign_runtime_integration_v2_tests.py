from app.agents.analytical_capability_registry_v2 import (
    AnalyticalCapabilityStatusV2,
    resolve_analytical_capability_v2,
)
from app.agents.analytical_path_contract_v2 import (
    AnalyticalGrainV2,
    AnalyticalOperationV2,
)
from app.agents.business_analytical_intent_v2 import (
    BusinessAnalyticalIntentTargetV2,
)
from app.agents.focused_change_breakdown_v2 import (
    FocusedChangeDimensionV2,
)
from app.delivery.investigation_runtime_v2 import (
    _day93_focused_dimension_for_action_v2,
)
from app.ui.decision_console_app import (
    _investigation_action_label_v1,
)


def _campaign_target() -> BusinessAnalyticalIntentTargetV2:
    return BusinessAnalyticalIntentTargetV2(
        domain="activity_promotion",
        operation=AnalyticalOperationV2.CHANGE_BREAKDOWN,
        grain=AnalyticalGrainV2.CAMPAIGN,
    )


def test_campaign_capability_is_now_registered() -> None:
    resolution = resolve_analytical_capability_v2(
        _campaign_target()
    )

    assert (
        resolution.status
        == AnalyticalCapabilityStatusV2.READY
    )
    assert resolution.action_id == "drill_campaign"
    assert resolution.query_plan_name == "gmv_campaign_v2"

    print(
        "PASS: "
        "test_campaign_capability_is_now_registered"
    )


def test_campaign_action_maps_to_focused_change_dimension() -> None:
    assert (
        _day93_focused_dimension_for_action_v2(
            "drill_campaign"
        )
        == FocusedChangeDimensionV2.CAMPAIGN
    )

    print(
        "PASS: "
        "test_campaign_action_maps_to_focused_change_dimension"
    )


def test_campaign_has_business_action_label() -> None:
    assert (
        _investigation_action_label_v1(
            "drill_campaign"
        )
        == "活动实例变化"
    )

    print(
        "PASS: "
        "test_campaign_has_business_action_label"
    )


def main() -> None:
    test_campaign_capability_is_now_registered()
    test_campaign_action_maps_to_focused_change_dimension()
    test_campaign_has_business_action_label()


if __name__ == "__main__":
    main()
