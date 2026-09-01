from __future__ import annotations

from app.agents.analytical_path_contract_v2 import (
    AnalyticalGrainV2,
)
from app.agents.business_analytical_intent_v2 import (
    BusinessAnalyticalIntentTargetV2,
)
from app.agents.geography_hierarchy_v2 import (
    AREA_DISPLAY_LABELS_V2,
)
from app.agents.user_investigation_intent_v2 import (
    UserInvestigationDomainV2,
)


_GRAIN_LABELS_V2: dict[AnalyticalGrainV2, str] = {
    AnalyticalGrainV2.OVERALL: "整体",
    AnalyticalGrainV2.CHANNEL: "渠道",
    AnalyticalGrainV2.CATEGORY: "品类",
    AnalyticalGrainV2.PRODUCT: "具体商品",
    AnalyticalGrainV2.AREA: "大区",
    AnalyticalGrainV2.PROVINCE: "省级",
    AnalyticalGrainV2.CITY: "城市",
    AnalyticalGrainV2.CUSTOMER_LIFECYCLE: "新客 / 老客",
    AnalyticalGrainV2.MEMBERSHIP_LEVEL: "会员等级",
    AnalyticalGrainV2.CAMPAIGN: "活动实例 / Campaign",
    AnalyticalGrainV2.PROMOTION: "优惠机制 / Promotion",
    AnalyticalGrainV2.MARKETING: "营销投入",
}


_DOMAIN_GRAIN_OPTIONS_V2: dict[
    UserInvestigationDomainV2,
    tuple[AnalyticalGrainV2, ...],
] = {
    UserInvestigationDomainV2.CATEGORY_PRODUCT: (
        AnalyticalGrainV2.CATEGORY,
        AnalyticalGrainV2.PRODUCT,
    ),
    UserInvestigationDomainV2.GEOGRAPHY: (
        AnalyticalGrainV2.AREA,
        AnalyticalGrainV2.PROVINCE,
        AnalyticalGrainV2.CITY,
    ),
    UserInvestigationDomainV2.AUDIENCE: (
        AnalyticalGrainV2.CUSTOMER_LIFECYCLE,
        AnalyticalGrainV2.MEMBERSHIP_LEVEL,
    ),
    UserInvestigationDomainV2.ACTIVITY_PROMOTION: (
        AnalyticalGrainV2.CAMPAIGN,
        AnalyticalGrainV2.PROMOTION,
    ),
}


def analytical_grain_label_v2(
    grain: AnalyticalGrainV2,
) -> str:
    return _GRAIN_LABELS_V2[grain]


def explicit_grain_options_v2(
    domain: UserInvestigationDomainV2,
) -> tuple[AnalyticalGrainV2, ...]:
    """
    只给存在真实层级 / 切面的 domain 展示 server-owned 明确选项。

    其他 domain 由其固定 semantic target 处理。
    """
    return _DOMAIN_GRAIN_OPTIONS_V2.get(
        domain,
        (),
    )


def analytical_target_business_label_v2(
    target: BusinessAnalyticalIntentTargetV2,
) -> str:
    label = analytical_grain_label_v2(
        target.grain
    )

    if target.focus is not None:
        return (
            f"{target.focus.member_label}中的{label}"
        )

    if target.cross_grains:
        return " × ".join(
            analytical_grain_label_v2(item)
            for item in target.cross_grains
        )

    return label


def business_safe_dimension_value_v2(
    *,
    field_name: str,
    value: object,
) -> object:
    """
    Business View 不暴露底层 Geography code。

    Engineering / Evidence contract 保持原始值；
    这里只处理 UI projection。
    """
    if field_name == "region_group":
        key = str(value).strip()
        return AREA_DISPLAY_LABELS_V2.get(
            key,
            value,
        )

    return value


def business_safe_breakdown_row_v2(
    row: dict[str, object],
) -> dict[str, object]:
    return {
        key: business_safe_dimension_value_v2(
            field_name=key,
            value=value,
        )
        for key, value in row.items()
    }
