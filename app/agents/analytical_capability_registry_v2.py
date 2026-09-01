from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, model_validator

from app.agents.analytical_path_contract_v2 import (
    AnalyticalGrainV2,
    AnalyticalOperationV2,
)
from app.agents.business_analytical_intent_v2 import (
    BusinessAnalyticalIntentTargetV2,
)


class AnalyticalCapabilityStatusV2(str, Enum):
    READY = "ready"
    UNDERSTOOD_NOT_REGISTERED = "understood_not_registered"
    UNSUPPORTED = "unsupported"


class AnalyticalCapabilityResolutionV2(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    status: AnalyticalCapabilityStatusV2

    action_id: str | None = None
    query_plan_name: str | None = None

    message: str

    @model_validator(mode="after")
    def validate_resolution(
        self,
    ) -> "AnalyticalCapabilityResolutionV2":
        if not self.message.strip():
            raise ValueError("message 不能为空。")

        if self.status == AnalyticalCapabilityStatusV2.READY:
            if (
                self.action_id is None
                or self.query_plan_name is None
            ):
                raise ValueError(
                    "READY capability 必须绑定 action / query plan。"
                )
        else:
            if (
                self.action_id is not None
                or self.query_plan_name is not None
            ):
                raise ValueError(
                    "非 READY capability 不能偷偷绑定执行合同。"
                )

        return self


_READY_GMV_CHANGE_BREAKDOWN_V2: dict[
    AnalyticalGrainV2,
    tuple[str, str],
] = {
    AnalyticalGrainV2.CHANNEL: (
        "drill_channel",
        "gmv_channel_v2",
    ),
    AnalyticalGrainV2.CATEGORY: (
        "drill_category",
        "gmv_category_v2",
    ),
    AnalyticalGrainV2.AREA: (
        "drill_area",
        "gmv_area_v2",
    ),
    AnalyticalGrainV2.PROVINCE: (
        "drill_province",
        "gmv_province_v2",
    ),
    AnalyticalGrainV2.CITY: (
        "drill_city",
        "gmv_city_v2",
    ),
    AnalyticalGrainV2.CAMPAIGN: (
        "drill_campaign",
        "gmv_campaign_v2",
    ),
}


def resolve_analytical_capability_v2(
    target: BusinessAnalyticalIntentTargetV2,
    *,
    metric_name: str = "gmv",
) -> AnalyticalCapabilityResolutionV2:
    """
    Semantic understanding 与 Execution Capability 分离。

    当前只声明已经真正接入 Investigation / Exploration Runtime
    的 GMV Change Breakdown。

    例如：
    - “具体商品”可以被语义正确理解为 PRODUCT，
      但当前不因此伪造一个 Product Query Plan。
    - “老客中的会员结构”可以被正确理解为 SLICE target，
      但 Audience Investigation 尚未接入时仍明确 NOT_REGISTERED。
    """

    if target.cross_grains:
        return AnalyticalCapabilityResolutionV2(
            status=(
                AnalyticalCapabilityStatusV2
                .UNDERSTOOD_NOT_REGISTERED
            ),
            message=(
                "系统已经理解这是交叉分析意图，"
                "但当前尚未注册对应的受治理 Cross-Analysis Capability。"
            ),
        )

    if (
        metric_name == "gmv"
        and target.operation
        == AnalyticalOperationV2.CHANGE_BREAKDOWN
        and target.focus is None
    ):
        binding = _READY_GMV_CHANGE_BREAKDOWN_V2.get(
            target.grain
        )

        if binding is not None:
            return AnalyticalCapabilityResolutionV2(
                status=AnalyticalCapabilityStatusV2.READY,
                action_id=binding[0],
                query_plan_name=binding[1],
                message=(
                    "该 Analytical Target 已有受治理 GMV "
                    "Change Breakdown Capability。"
                ),
            )

    if target.grain in {
        AnalyticalGrainV2.PRODUCT,
        AnalyticalGrainV2.CUSTOMER_LIFECYCLE,
        AnalyticalGrainV2.MEMBERSHIP_LEVEL,
        AnalyticalGrainV2.PROMOTION,
        AnalyticalGrainV2.MARKETING,
    } or target.focus is not None:
        return AnalyticalCapabilityResolutionV2(
            status=(
                AnalyticalCapabilityStatusV2
                .UNDERSTOOD_NOT_REGISTERED
            ),
            message=(
                "业务语义已经理解，但对应 Investigation Capability "
                "尚未正式注册；系统不会降级成其他已有查询。"
            ),
        )

    return AnalyticalCapabilityResolutionV2(
        status=AnalyticalCapabilityStatusV2.UNSUPPORTED,
        message=(
            "当前 Analytical Target 不在已声明的受治理能力合同中。"
        ),
    )
