from app.agents.user_investigation_intent_v2 import (
    UserInvestigationCapabilityStatusV2,
    UserInvestigationDomainV2,
    UserInvestigationIntentV2,
    resolve_user_investigation_intent_v2,
)


def test_user_category_intent_maps_to_supported_action() -> None:
    resolution = resolve_user_investigation_intent_v2(
        UserInvestigationIntentV2(
            domain=UserInvestigationDomainV2.CATEGORY_PRODUCT,
        )
    )

    assert resolution.status == UserInvestigationCapabilityStatusV2.READY
    assert resolution.mapped_action_id == "drill_category"
    assert resolution.mapped_plan_name == "gmv_category_v2"
    assert resolution.safe_to_execute is True

    print("PASS: test_user_category_intent_maps_to_supported_action")


def test_activity_intent_is_preserved_not_rewritten() -> None:
    resolution = resolve_user_investigation_intent_v2(
        UserInvestigationIntentV2(
            domain=UserInvestigationDomainV2.ACTIVITY_PROMOTION,
            hypothesis="我怀疑10月增长与双十一预热有关。",
        )
    )

    assert (
        resolution.status
        == UserInvestigationCapabilityStatusV2.DATA_AVAILABLE_NOT_REGISTERED
    )
    assert resolution.data_available is True
    assert resolution.mapped_action_id is None
    assert resolution.safe_to_execute is False
    assert "Campaign / Promotion" in resolution.message

    print("PASS: test_activity_intent_is_preserved_not_rewritten")
    print("PASS: user activity hypothesis != category/region action")


def test_geography_is_ready_from_area() -> None:
    intent = UserInvestigationIntentV2(
        domain=UserInvestigationDomainV2.GEOGRAPHY,
    )
    result = resolve_user_investigation_intent_v2(intent)

    assert result.status == UserInvestigationCapabilityStatusV2.READY
    assert result.mapped_action_id == "drill_area"
    assert result.mapped_plan_name == "gmv_area_v2"
    assert result.data_available is True
    assert result.safe_to_execute is True

    print("PASS: test_geography_is_ready_from_area")

def test_audience_requires_business_clarification() -> None:
    resolution = resolve_user_investigation_intent_v2(
        UserInvestigationIntentV2(
            domain=UserInvestigationDomainV2.AUDIENCE,
        )
    )

    assert (
        resolution.status
        == UserInvestigationCapabilityStatusV2.NEEDS_CLARIFICATION
    )
    assert "支付时会员等级" in resolution.clarification_choices
    assert resolution.mapped_action_id is None

    print("PASS: test_audience_requires_business_clarification")


def main() -> None:
    test_user_category_intent_maps_to_supported_action()
    test_activity_intent_is_preserved_not_rewritten()
    test_geography_is_ready_from_area()
    test_audience_requires_business_clarification()


if __name__ == "__main__":
    main()
