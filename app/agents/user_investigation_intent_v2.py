from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, model_validator


class UserInvestigationDomainV2(str, Enum):
    CATEGORY_PRODUCT = "category_product"
    CHANNEL = "channel"
    GEOGRAPHY = "geography"
    ACTIVITY_PROMOTION = "activity_promotion"
    AUDIENCE = "audience"
    MARKETING = "marketing"
    OTHER = "other"


class UserInvestigationCapabilityStatusV2(str, Enum):
    READY = "ready"
    NEEDS_CLARIFICATION = "needs_clarification"
    DATA_AVAILABLE_NOT_REGISTERED = "data_available_not_registered"
    UNSUPPORTED = "unsupported"


class UserInvestigationIntentV2(BaseModel):
    """
    用户的业务调查意图。

    重要边界：
    - 这是 USER-owned business intent；
    - 它不是 Planner Action；
    - 用户可以表达系统推荐空间之外的调查想法；
    - 后续 Resolver 决定当前系统是否有安全、受治理的执行能力。
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    domain: UserInvestigationDomainV2
    hypothesis: str | None = None

    @model_validator(mode="after")
    def validate_intent(
        self,
    ) -> "UserInvestigationIntentV2":
        if self.hypothesis is not None and not self.hypothesis.strip():
            raise ValueError("hypothesis 不能是空字符串。")
        return self


class UserInvestigationCapabilityResolutionV2(BaseModel):
    """
    User Intent -> Capability Resolution。

    mapped_action_id 只有 READY 时才允许存在。
    UI / Runtime 不得把 NOT_REGISTERED / UNSUPPORTED
    的业务意图偷偷降级成其他已有 Action。
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: UserInvestigationCapabilityStatusV2
    domain: UserInvestigationDomainV2

    display_label: str
    message: str

    mapped_action_id: str | None = None
    mapped_plan_name: str | None = None

    clarification_choices: tuple[str, ...] = ()
    data_available: bool
    safe_to_execute: bool

    @model_validator(mode="after")
    def validate_resolution(
        self,
    ) -> "UserInvestigationCapabilityResolutionV2":
        if not self.display_label.strip():
            raise ValueError("display_label 不能为空。")
        if not self.message.strip():
            raise ValueError("message 不能为空。")

        if self.status == UserInvestigationCapabilityStatusV2.READY:
            if (
                self.mapped_action_id is None
                or self.mapped_plan_name is None
            ):
                raise ValueError(
                    "READY capability 必须绑定 action / plan。"
                )
            if not self.safe_to_execute:
                raise ValueError(
                    "READY capability 必须 safe_to_execute=True。"
                )
        else:
            if (
                self.mapped_action_id is not None
                or self.mapped_plan_name is not None
            ):
                raise ValueError(
                    "非 READY capability 不能偷偷绑定执行 Action。"
                )
            if self.safe_to_execute:
                raise ValueError(
                    "非 READY capability 不能标记为可执行。"
                )

        if (
            self.status
            == UserInvestigationCapabilityStatusV2.NEEDS_CLARIFICATION
            and not self.clarification_choices
        ):
            raise ValueError(
                "NEEDS_CLARIFICATION 必须提供 clarification choices。"
            )

        return self


def resolve_user_investigation_intent_v2(
    intent: UserInvestigationIntentV2,
) -> UserInvestigationCapabilityResolutionV2:
    """
    Day93 第一版 Capability Catalog。

    已正式可执行：
    - 品类 / 商品方向（当前落到 category grain）
    - 渠道

    数据存在但调查能力尚未正式注册：
    - 活动 / 促销
    - 营销投入

    Geography Hierarchy 已正式注册：Area -> Province -> City。

    人群：
    Dataset V2 已有支付时会员等级 GMV 能力，
    但“人群”本身过宽，必须先澄清具体人群口径。
    """

    domain = intent.domain

    if domain == UserInvestigationDomainV2.CATEGORY_PRODUCT:
        return UserInvestigationCapabilityResolutionV2(
            status=UserInvestigationCapabilityStatusV2.READY,
            domain=domain,
            display_label="商品 / 品类",
            message=(
                "当前已注册 GMV 品类变化调查能力；"
                "可以在现有 Governance Boundary 内执行。"
            ),
            mapped_action_id="drill_category",
            mapped_plan_name="gmv_category_v2",
            data_available=True,
            safe_to_execute=True,
        )

    if domain == UserInvestigationDomainV2.CHANNEL:
        return UserInvestigationCapabilityResolutionV2(
            status=UserInvestigationCapabilityStatusV2.READY,
            domain=domain,
            display_label="渠道",
            message=(
                "当前已注册 GMV 渠道变化调查能力；"
                "可以在现有 Governance Boundary 内执行。"
            ),
            mapped_action_id="drill_channel",
            mapped_plan_name="gmv_channel_v2",
            data_available=True,
            safe_to_execute=True,
        )

    if domain == UserInvestigationDomainV2.GEOGRAPHY:
        return UserInvestigationCapabilityResolutionV2(
            status=UserInvestigationCapabilityStatusV2.READY,
            domain=domain,
            display_label="地区",
            message=(
                "当前已注册 GMV Geography Hierarchy 调查能力；"
                "地区调查从大区开始，只有上一层 Evidence 达到"
                "单一主导条件时才允许继续收窄到省 / 市。"
            ),
            mapped_action_id="drill_area",
            mapped_plan_name="gmv_area_v2",
            data_available=True,
            safe_to_execute=True,
        )

    if domain == UserInvestigationDomainV2.ACTIVITY_PROMOTION:
        return UserInvestigationCapabilityResolutionV2(
            status=(
                UserInvestigationCapabilityStatusV2
                .DATA_AVAILABLE_NOT_REGISTERED
            ),
            domain=domain,
            display_label="活动 / 促销",
            message=(
                "Dataset V2 已有 Campaign / Promotion 数据，"
                "但 GMV 活动变化调查 Query Plan 尚未正式注册。"
                "当前可以接受该业务假设，但不能伪装成已有品类/地区查询。"
            ),
            data_available=True,
            safe_to_execute=False,
        )

    if domain == UserInvestigationDomainV2.AUDIENCE:
        return UserInvestigationCapabilityResolutionV2(
            status=(
                UserInvestigationCapabilityStatusV2.NEEDS_CLARIFICATION
            ),
            domain=domain,
            display_label="客户 / 人群",
            message=(
                "“人群”口径过宽。Dataset V2 已有支付时会员等级、"
                "新老客等相关能力，必须先明确希望验证的人群口径。"
            ),
            clarification_choices=(
                "支付时会员等级",
                "新客 / 老客与会员生命周期",
            ),
            data_available=True,
            safe_to_execute=False,
        )

    if domain == UserInvestigationDomainV2.MARKETING:
        return UserInvestigationCapabilityResolutionV2(
            status=(
                UserInvestigationCapabilityStatusV2
                .DATA_AVAILABLE_NOT_REGISTERED
            ),
            domain=domain,
            display_label="营销投入",
            message=(
                "Dataset V2 已有 Marketing Spend 数据，"
                "但当前 F02 Investigation 尚未注册"
                "“营销投入变化 -> GMV”受治理调查 Route。"
            ),
            data_available=True,
            safe_to_execute=False,
        )

    return UserInvestigationCapabilityResolutionV2(
        status=UserInvestigationCapabilityStatusV2.UNSUPPORTED,
        domain=domain,
        display_label="其他业务问题",
        message=(
            "当前意图没有匹配到已注册的 Investigation Capability。"
            "系统会保留该用户假设，但不会自动改写成其他调查方向。"
        ),
        data_available=False,
        safe_to_execute=False,
    )
