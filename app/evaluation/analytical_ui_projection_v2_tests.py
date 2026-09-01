from app.agents.analytical_path_contract_v2 import (
    AnalyticalGrainV2,
    AnalyticalOperationV2,
)
from app.agents.business_analytical_intent_v2 import (
    BusinessAnalyticalIntentTargetV2,
)
from app.agents.user_investigation_intent_v2 import (
    UserInvestigationDomainV2,
)
from app.ui.analytical_ui_projection_v2 import (
    analytical_grain_label_v2,
    analytical_target_business_label_v2,
    business_safe_breakdown_row_v2,
    explicit_grain_options_v2,
)


def test_domain_options_are_not_flat_actions() -> None:
    assert explicit_grain_options_v2(
        UserInvestigationDomainV2.CATEGORY_PRODUCT
    ) == (
        AnalyticalGrainV2.CATEGORY,
        AnalyticalGrainV2.PRODUCT,
    )

    assert explicit_grain_options_v2(
        UserInvestigationDomainV2.GEOGRAPHY
    ) == (
        AnalyticalGrainV2.AREA,
        AnalyticalGrainV2.PROVINCE,
        AnalyticalGrainV2.CITY,
    )

    assert explicit_grain_options_v2(
        UserInvestigationDomainV2.AUDIENCE
    ) == (
        AnalyticalGrainV2.CUSTOMER_LIFECYCLE,
        AnalyticalGrainV2.MEMBERSHIP_LEVEL,
    )

    print("PASS: test_domain_options_are_not_flat_actions")


def test_target_labels_preserve_real_semantics() -> None:
    product = BusinessAnalyticalIntentTargetV2(
        domain=UserInvestigationDomainV2.CATEGORY_PRODUCT,
        operation=AnalyticalOperationV2.CHANGE_BREAKDOWN,
        grain=AnalyticalGrainV2.PRODUCT,
    )

    assert (
        analytical_target_business_label_v2(product)
        == "具体商品"
    )

    print("PASS: test_target_labels_preserve_real_semantics")


def test_business_verification_translates_area_codes() -> None:
    row = business_safe_breakdown_row_v2(
        {
            "region_group": "east",
            "gmv": 123,
        }
    )

    assert row["region_group"] == "华东"
    assert row["gmv"] == 123

    print(
        "PASS: "
        "test_business_verification_translates_area_codes"
    )


def main() -> None:
    test_domain_options_are_not_flat_actions()
    test_target_labels_preserve_real_semantics()
    test_business_verification_translates_area_codes()


if __name__ == "__main__":
    main()
