from __future__ import annotations

from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, model_validator

from app.agents.analytical_path_contract_v2 import (
    AnalyticalFocusV2,
    AnalyticalGrainV2,
    AnalyticalOperationV2,
    AnalyticalPathNodeV2,
)
from app.agents.user_investigation_intent_v2 import (
    UserInvestigationDomainV2,
)


class BusinessAnalyticalIntentStatusV2(str, Enum):
    RESOLVED = "resolved"
    NEEDS_CLARIFICATION = "needs_clarification"
    DOMAIN_CONFLICT = "domain_conflict"
    UNSUPPORTED = "unsupported"


class BusinessAnalyticalIntentRequestV2(BaseModel):
    """
    USER-owned business intent.

    domain:
        用户显式选择的业务方向。

    hypothesis:
        用户的自然语言业务判断。它只用于解析“想分析什么”，
        绝不能直接成为 SQL / Tool / Scope。

    explicit_grain:
        未来 UI 可提供 server-owned 明确层级选择。
        显式控件优先于自然语言猜测，但仍需做冲突校验。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    domain: UserInvestigationDomainV2
    hypothesis: str | None = None
    explicit_grain: AnalyticalGrainV2 | None = None

    @model_validator(mode="after")
    def validate_request(
        self,
    ) -> "BusinessAnalyticalIntentRequestV2":
        if (
            self.hypothesis is not None
            and not self.hypothesis.strip()
        ):
            raise ValueError(
                "hypothesis 若存在，不能是空字符串。"
            )
        return self


class BusinessAnalyticalIntentTargetV2(BaseModel):
    """
    Semantic target only.

    还不是 executable action。
    后面必须继续经过：
    Analytical Relation -> Capability -> Scope -> Governance。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    domain: UserInvestigationDomainV2
    operation: AnalyticalOperationV2
    grain: AnalyticalGrainV2

    focus: AnalyticalFocusV2 | None = None
    cross_grains: tuple[AnalyticalGrainV2, ...] = ()

    @model_validator(mode="after")
    def validate_target(
        self,
    ) -> "BusinessAnalyticalIntentTargetV2":
        if self.cross_grains:
            if len(self.cross_grains) < 2:
                raise ValueError(
                    "cross_grains 至少需要两个粒度。"
                )
            if len(set(self.cross_grains)) != len(
                self.cross_grains
            ):
                raise ValueError(
                    "cross_grains 不能重复。"
                )
        return self


class BusinessAnalyticalIntentResolutionV2(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    status: BusinessAnalyticalIntentStatusV2
    selected_domain: UserInvestigationDomainV2

    target: BusinessAnalyticalIntentTargetV2 | None = None

    detected_domains: tuple[
        UserInvestigationDomainV2, ...
    ] = ()

    clarification_grains: tuple[
        AnalyticalGrainV2, ...
    ] = ()

    message: str

    @model_validator(mode="after")
    def validate_resolution(
        self,
    ) -> "BusinessAnalyticalIntentResolutionV2":
        if not self.message.strip():
            raise ValueError("message 不能为空。")

        if self.status == BusinessAnalyticalIntentStatusV2.RESOLVED:
            if self.target is None:
                raise ValueError(
                    "RESOLVED 必须返回 target。"
                )
            if self.clarification_grains:
                raise ValueError(
                    "RESOLVED 不应携带 clarification_grains。"
                )
        else:
            if self.target is not None:
                raise ValueError(
                    "非 RESOLVED 不得偷偷绑定 executable semantic target。"
                )

        if (
            self.status
            == BusinessAnalyticalIntentStatusV2.NEEDS_CLARIFICATION
            and not self.clarification_grains
        ):
            raise ValueError(
                "NEEDS_CLARIFICATION 必须给出受控粒度选项。"
            )

        return self


_DOMAIN_KEYWORDS_V2: dict[
    UserInvestigationDomainV2,
    tuple[str, ...],
] = {
    UserInvestigationDomainV2.CATEGORY_PRODUCT: (
        "品类",
        "类目",
        "商品",
        "单品",
        "sku",
        "产品",
    ),
    UserInvestigationDomainV2.CHANNEL: (
        "渠道",
        "天猫",
        "京东",
        "抖音",
        "微信",
        "小红书",
        "官方商城",
    ),
    UserInvestigationDomainV2.GEOGRAPHY: (
        "地区",
        "地理",
        "大区",
        "区域",
        "省级",
        "省份",
        "各省",
        "城市",
        "市级",
        "各市",
        "华东",
        "华南",
        "华北",
        "华中",
        "西南",
        "东北",
        "西北",
    ),
    UserInvestigationDomainV2.ACTIVITY_PROMOTION: (
        "活动",
        "促销",
        "大促",
        "双十一",
        "双11",
        "618",
        "campaign",
    ),
    UserInvestigationDomainV2.AUDIENCE: (
        "客户",
        "人群",
        "新客",
        "老客",
        "新老客",
        "新客户",
        "老客户",
        "会员",
        "非会员",
        "会员等级",
        "青铜",
        "白银",
        "黄金",
        "铂金",
    ),
    UserInvestigationDomainV2.MARKETING: (
        "营销",
        "投放",
        "广告",
        "花费",
        "marketing",
    ),
}


def _normalized_text_v2(
    value: str | None,
) -> str:
    return (
        value.strip().lower()
        if isinstance(value, str)
        else ""
    )


def _contains_any_v2(
    text: str,
    keywords: tuple[str, ...],
) -> bool:
    return any(
        keyword.lower() in text
        for keyword in keywords
    )


def detect_business_domains_v2(
    hypothesis: str | None,
) -> tuple[UserInvestigationDomainV2, ...]:
    text = _normalized_text_v2(hypothesis)

    if not text:
        return ()

    detected = [
        domain
        for domain, keywords in _DOMAIN_KEYWORDS_V2.items()
        if _contains_any_v2(
            text,
            keywords,
        )
    ]

    return tuple(detected)


def _category_product_target_v2(
    *,
    text: str,
    explicit_grain: AnalyticalGrainV2 | None,
) -> BusinessAnalyticalIntentTargetV2 | None:
    if explicit_grain is not None:
        if explicit_grain not in {
            AnalyticalGrainV2.CATEGORY,
            AnalyticalGrainV2.PRODUCT,
        }:
            return None

        return BusinessAnalyticalIntentTargetV2(
            domain=UserInvestigationDomainV2.CATEGORY_PRODUCT,
            operation=AnalyticalOperationV2.CHANGE_BREAKDOWN,
            grain=explicit_grain,
        )

    product_terms = (
        "商品",
        "单品",
        "sku",
        "产品",
    )

    if _contains_any_v2(text, product_terms):
        return BusinessAnalyticalIntentTargetV2(
            domain=UserInvestigationDomainV2.CATEGORY_PRODUCT,
            operation=AnalyticalOperationV2.CHANGE_BREAKDOWN,
            grain=AnalyticalGrainV2.PRODUCT,
        )

    if _contains_any_v2(
        text,
        ("品类", "类目"),
    ):
        return BusinessAnalyticalIntentTargetV2(
            domain=UserInvestigationDomainV2.CATEGORY_PRODUCT,
            operation=AnalyticalOperationV2.CHANGE_BREAKDOWN,
            grain=AnalyticalGrainV2.CATEGORY,
        )

    return None


def _geography_target_v2(
    *,
    text: str,
    explicit_grain: AnalyticalGrainV2 | None,
) -> BusinessAnalyticalIntentTargetV2 | None:
    if explicit_grain is not None:
        if explicit_grain not in {
            AnalyticalGrainV2.AREA,
            AnalyticalGrainV2.PROVINCE,
            AnalyticalGrainV2.CITY,
        }:
            return None

        return BusinessAnalyticalIntentTargetV2(
            domain=UserInvestigationDomainV2.GEOGRAPHY,
            operation=AnalyticalOperationV2.CHANGE_BREAKDOWN,
            grain=explicit_grain,
        )

    if _contains_any_v2(
        text,
        ("城市", "市级", "各市"),
    ):
        grain = AnalyticalGrainV2.CITY
    elif _contains_any_v2(
        text,
        ("省级", "省份", "各省"),
    ):
        grain = AnalyticalGrainV2.PROVINCE
    elif _contains_any_v2(
        text,
        (
            "大区",
            "区域",
            "华东",
            "华南",
            "华北",
            "华中",
            "西南",
            "东北",
            "西北",
        ),
    ):
        grain = AnalyticalGrainV2.AREA
    else:
        return None

    return BusinessAnalyticalIntentTargetV2(
        domain=UserInvestigationDomainV2.GEOGRAPHY,
        operation=AnalyticalOperationV2.CHANGE_BREAKDOWN,
        grain=grain,
    )


def _audience_target_v2(
    *,
    text: str,
    explicit_grain: AnalyticalGrainV2 | None,
) -> BusinessAnalyticalIntentTargetV2 | None:
    if explicit_grain is not None:
        if explicit_grain not in {
            AnalyticalGrainV2.CUSTOMER_LIFECYCLE,
            AnalyticalGrainV2.MEMBERSHIP_LEVEL,
        }:
            return None

        return BusinessAnalyticalIntentTargetV2(
            domain=UserInvestigationDomainV2.AUDIENCE,
            operation=AnalyticalOperationV2.CHANGE_BREAKDOWN,
            grain=explicit_grain,
        )

    has_lifecycle = _contains_any_v2(
        text,
        (
            "新客",
            "老客",
            "新老客",
            "新客户",
            "老客户",
        ),
    )
    has_membership = _contains_any_v2(
        text,
        (
            "会员",
            "非会员",
            "会员等级",
            "青铜",
            "白银",
            "黄金",
            "铂金",
        ),
    )

    if has_lifecycle and has_membership:
        if _contains_any_v2(
            text,
            ("老客", "老客户"),
        ):
            focus = AnalyticalFocusV2(
                source_grain=AnalyticalGrainV2.CUSTOMER_LIFECYCLE,
                member_key="old_customer",
                member_label="老客",
            )
        elif _contains_any_v2(
            text,
            ("新客", "新客户"),
        ):
            focus = AnalyticalFocusV2(
                source_grain=AnalyticalGrainV2.CUSTOMER_LIFECYCLE,
                member_key="new_customer",
                member_label="新客",
            )
        else:
            focus = None

        if focus is not None:
            return BusinessAnalyticalIntentTargetV2(
                domain=UserInvestigationDomainV2.AUDIENCE,
                operation=AnalyticalOperationV2.CHANGE_BREAKDOWN,
                grain=AnalyticalGrainV2.MEMBERSHIP_LEVEL,
                focus=focus,
            )

        return BusinessAnalyticalIntentTargetV2(
            domain=UserInvestigationDomainV2.AUDIENCE,
            operation=AnalyticalOperationV2.CHANGE_BREAKDOWN,
            grain=AnalyticalGrainV2.CUSTOMER_LIFECYCLE,
            cross_grains=(
                AnalyticalGrainV2.CUSTOMER_LIFECYCLE,
                AnalyticalGrainV2.MEMBERSHIP_LEVEL,
            ),
        )

    if has_lifecycle:
        return BusinessAnalyticalIntentTargetV2(
            domain=UserInvestigationDomainV2.AUDIENCE,
            operation=AnalyticalOperationV2.CHANGE_BREAKDOWN,
            grain=AnalyticalGrainV2.CUSTOMER_LIFECYCLE,
        )

    if has_membership:
        return BusinessAnalyticalIntentTargetV2(
            domain=UserInvestigationDomainV2.AUDIENCE,
            operation=AnalyticalOperationV2.CHANGE_BREAKDOWN,
            grain=AnalyticalGrainV2.MEMBERSHIP_LEVEL,
        )

    return None


def _activity_promotion_target_v2(
    *,
    text: str,
    explicit_grain: AnalyticalGrainV2 | None,
) -> BusinessAnalyticalIntentTargetV2 | None:
    """
    Activity / Promotion 是同一个业务域里的两个不同分析对象。

    Campaign:
        活动实例 / 大促 / 双十一 / 618 / 预热期。

    Promotion:
        优惠机制 / 折扣 / 满减 / 优惠券。

    “促销”单独出现时故意不猜，要求澄清。
    """

    if explicit_grain is not None:
        if explicit_grain not in {
            AnalyticalGrainV2.CAMPAIGN,
            AnalyticalGrainV2.PROMOTION,
        }:
            return None

        return BusinessAnalyticalIntentTargetV2(
            domain=UserInvestigationDomainV2.ACTIVITY_PROMOTION,
            operation=AnalyticalOperationV2.CHANGE_BREAKDOWN,
            grain=explicit_grain,
        )

    campaign_terms = (
        "活动",
        "大促",
        "双十一",
        "双11",
        "618",
        "38大促",
        "预热",
        "campaign",
    )
    promotion_terms = (
        "优惠",
        "优惠券",
        "券",
        "折扣",
        "满减",
        "promotion",
    )

    has_campaign = _contains_any_v2(
        text,
        campaign_terms,
    )
    has_promotion = _contains_any_v2(
        text,
        promotion_terms,
    )

    if has_campaign and has_promotion:
        return None

    if has_campaign:
        return BusinessAnalyticalIntentTargetV2(
            domain=UserInvestigationDomainV2.ACTIVITY_PROMOTION,
            operation=AnalyticalOperationV2.CHANGE_BREAKDOWN,
            grain=AnalyticalGrainV2.CAMPAIGN,
        )

    if has_promotion:
        return BusinessAnalyticalIntentTargetV2(
            domain=UserInvestigationDomainV2.ACTIVITY_PROMOTION,
            operation=AnalyticalOperationV2.CHANGE_BREAKDOWN,
            grain=AnalyticalGrainV2.PROMOTION,
        )

    return None


def _simple_domain_target_v2(
    domain: UserInvestigationDomainV2,
) -> BusinessAnalyticalIntentTargetV2:
    grain = {
        UserInvestigationDomainV2.CHANNEL:
            AnalyticalGrainV2.CHANNEL,
        UserInvestigationDomainV2.MARKETING:
            AnalyticalGrainV2.MARKETING,
    }[domain]

    return BusinessAnalyticalIntentTargetV2(
        domain=domain,
        operation=AnalyticalOperationV2.CHANGE_BREAKDOWN,
        grain=grain,
    )


def _with_cross_dimension_if_needed_v2(
    *,
    selected_domain: UserInvestigationDomainV2,
    target: BusinessAnalyticalIntentTargetV2,
    detected_domains: tuple[
        UserInvestigationDomainV2, ...
    ],
    text: str,
) -> BusinessAnalyticalIntentTargetV2:
    """
    只有 hypothesis 同时明确包含 selected domain 和其他 domain
    才投影成 CROSS_ANALYZE。

    若文本只描述其他 domain，则由上层判定 DOMAIN_CONFLICT，
    不偷偷把用户下拉选择改掉。
    """

    other_domains = tuple(
        domain
        for domain in detected_domains
        if domain != selected_domain
    )

    if not other_domains:
        return target

    cross_grains = [target.grain]

    for domain in other_domains:
        if domain == UserInvestigationDomainV2.CATEGORY_PRODUCT:
            other = _category_product_target_v2(
                text=text,
                explicit_grain=None,
            )
        elif domain == UserInvestigationDomainV2.GEOGRAPHY:
            other = _geography_target_v2(
                text=text,
                explicit_grain=None,
            )
        elif domain == UserInvestigationDomainV2.AUDIENCE:
            other = _audience_target_v2(
                text=text,
                explicit_grain=None,
            )
        elif domain == UserInvestigationDomainV2.ACTIVITY_PROMOTION:
            other = _activity_promotion_target_v2(
                text=text,
                explicit_grain=None,
            )
        elif domain in {
            UserInvestigationDomainV2.CHANNEL,
            UserInvestigationDomainV2.MARKETING,
        }:
            other = _simple_domain_target_v2(
                domain
            )
        else:
            other = None

        if other is not None:
            cross_grains.append(
                other.grain
            )

    unique = tuple(
        dict.fromkeys(cross_grains)
    )

    if len(unique) < 2:
        return target

    return target.model_copy(
        update={
            "cross_grains": unique,
        }
    )


def resolve_business_analytical_intent_v2(
    request: BusinessAnalyticalIntentRequestV2,
) -> BusinessAnalyticalIntentResolutionV2:
    """
    Bounded deterministic Semantic Preflight。

    它负责：
    - 识别用户在一个业务域里想看的真实粒度；
    - 识别显式跨维度意图；
    - 识别下拉 domain 与 hypothesis 的明显冲突；
    - 不把 domain 本身当成 action_id；
    - 不判断 Query Plan 是否存在。

    Query Capability 是下一层独立合同。
    """

    domain = request.domain
    text = _normalized_text_v2(
        request.hypothesis
    )
    detected = detect_business_domains_v2(
        request.hypothesis
    )

    if domain == UserInvestigationDomainV2.OTHER:
        return BusinessAnalyticalIntentResolutionV2(
            status=BusinessAnalyticalIntentStatusV2.UNSUPPORTED,
            selected_domain=domain,
            detected_domains=detected,
            message=(
                "当前业务方向没有注册可验证的 Analytical Ontology。"
            ),
        )

    # 文本明确只描述其他 domain 时，不相信下拉框或关键词中的任一方；
    # 要求用户确认，避免偷偷执行错误分析。
    if (
        text
        and detected
        and domain not in detected
    ):
        return BusinessAnalyticalIntentResolutionV2(
            status=BusinessAnalyticalIntentStatusV2.DOMAIN_CONFLICT,
            selected_domain=domain,
            detected_domains=detected,
            message=(
                "业务判断描述的方向与当前选择的业务域不一致；"
                "需要用户确认本轮真正要验证的方向。"
            ),
        )

    if domain == UserInvestigationDomainV2.CATEGORY_PRODUCT:
        target = _category_product_target_v2(
            text=text,
            explicit_grain=request.explicit_grain,
        )

        if target is None:
            return BusinessAnalyticalIntentResolutionV2(
                status=BusinessAnalyticalIntentStatusV2.NEEDS_CLARIFICATION,
                selected_domain=domain,
                detected_domains=detected,
                clarification_grains=(
                    AnalyticalGrainV2.CATEGORY,
                    AnalyticalGrainV2.PRODUCT,
                ),
                message=(
                    "“商品 / 品类”包含不同分析粒度；"
                    "需要明确本轮看品类还是具体商品。"
                ),
            )

    elif domain == UserInvestigationDomainV2.GEOGRAPHY:
        target = _geography_target_v2(
            text=text,
            explicit_grain=request.explicit_grain,
        )

        if target is None:
            return BusinessAnalyticalIntentResolutionV2(
                status=BusinessAnalyticalIntentStatusV2.NEEDS_CLARIFICATION,
                selected_domain=domain,
                detected_domains=detected,
                clarification_grains=(
                    AnalyticalGrainV2.AREA,
                    AnalyticalGrainV2.PROVINCE,
                    AnalyticalGrainV2.CITY,
                ),
                message=(
                    "“地区”本身不是单一分析粒度；"
                    "需要明确大区、省级或城市。"
                ),
            )

    elif domain == UserInvestigationDomainV2.AUDIENCE:
        target = _audience_target_v2(
            text=text,
            explicit_grain=request.explicit_grain,
        )

        if target is None:
            return BusinessAnalyticalIntentResolutionV2(
                status=BusinessAnalyticalIntentStatusV2.NEEDS_CLARIFICATION,
                selected_domain=domain,
                detected_domains=detected,
                clarification_grains=(
                    AnalyticalGrainV2.CUSTOMER_LIFECYCLE,
                    AnalyticalGrainV2.MEMBERSHIP_LEVEL,
                ),
                message=(
                    "“客户 / 人群”包含不同业务切面；"
                    "需要明确新老客生命周期或会员等级。"
                ),
            )

    elif domain == UserInvestigationDomainV2.ACTIVITY_PROMOTION:
        target = _activity_promotion_target_v2(
            text=text,
            explicit_grain=request.explicit_grain,
        )

        if target is None:
            return BusinessAnalyticalIntentResolutionV2(
                status=BusinessAnalyticalIntentStatusV2.NEEDS_CLARIFICATION,
                selected_domain=domain,
                detected_domains=detected,
                clarification_grains=(
                    AnalyticalGrainV2.CAMPAIGN,
                    AnalyticalGrainV2.PROMOTION,
                ),
                message=(
                    "“活动 / 促销”包含两个不同分析对象；"
                    "需要明确本轮看活动实例，还是具体优惠机制。"
                ),
            )

    elif domain in {
        UserInvestigationDomainV2.CHANNEL,
        UserInvestigationDomainV2.MARKETING,
    }:
        target = _simple_domain_target_v2(
            domain
        )

    else:
        return BusinessAnalyticalIntentResolutionV2(
            status=BusinessAnalyticalIntentStatusV2.UNSUPPORTED,
            selected_domain=domain,
            detected_domains=detected,
            message=(
                "当前业务方向没有注册 Semantic Target Resolver。"
            ),
        )

    target = _with_cross_dimension_if_needed_v2(
        selected_domain=domain,
        target=target,
        detected_domains=detected,
        text=text,
    )

    return BusinessAnalyticalIntentResolutionV2(
        status=BusinessAnalyticalIntentStatusV2.RESOLVED,
        selected_domain=domain,
        target=target,
        detected_domains=detected,
        message=(
            "业务分析意图已解析成结构化 Analytical Target；"
            "尚未做 Capability / Scope / Governance 判断。"
        ),
    )


def materialize_analytical_path_node_v2(
    *,
    target: BusinessAnalyticalIntentTargetV2,
    metric_name: str,
    comparison_key: str | None,
    scope_fingerprint: str | None,
    node_id: str | None = None,
) -> AnalyticalPathNodeV2:
    """
    把 Semantic Target 与可信 Runtime identity 组合成 Path Node。

    comparison_key / scope_fingerprint 必须来自可信 Delivery / Scope，
    不能从 hypothesis 反向解析。
    """

    return AnalyticalPathNodeV2(
        node_id=(
            node_id
            if node_id is not None
            else f"analytical-node-{uuid4().hex}"
        ),
        metric_name=metric_name,
        domain=target.domain,
        operation=target.operation,
        grain=target.grain,
        focus=target.focus,
        cross_grains=target.cross_grains,
        comparison_key=comparison_key,
        scope_fingerprint=scope_fingerprint,
    )
