from __future__ import annotations

from enum import Enum
from functools import lru_cache
from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator

from app.db.beauty_bi_v2.manifest_loader import (
    load_and_validate_day64_manifest,
)
from app.semantic_layer.requested_scope_resolution_v2 import (
    RequestedScopeResolutionV2,
)


class ChannelBusinessRoleV2(str, Enum):
    SALES = "sales"
    MARKETING = "marketing"
    DIRECT_RESPONSE = "direct_response"


class MetricChannelApplicabilityDecisionV2(BaseModel):
    """
    Metric / business role 对 Requested Channel Scope 的确定性校验。

    Authorized Scope 与业务适用 Scope 是两个不同概念：
    - Authorized: 用户有权看到哪些渠道；
    - Applicable: 当前指标在业务语义上允许哪些渠道。

    最终执行范围应继续满足：
    Authorized ∩ Applicable ∩ Requested ∩ Investigation Focus。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    metric_name: str
    channel_role: ChannelBusinessRoleV2
    allowed: bool

    applicable_channel_codes: frozenset[str]
    requested_channel_codes: frozenset[str]
    inapplicable_requested_codes: frozenset[str]

    message: str

    @model_validator(mode="after")
    def validate_decision(
        self,
    ) -> "MetricChannelApplicabilityDecisionV2":
        if not self.metric_name.strip():
            raise ValueError("metric_name 不能为空。")
        if not self.applicable_channel_codes:
            raise ValueError("Applicable Channel Scope 不能为空。")
        if not self.message.strip():
            raise ValueError("message 不能为空。")

        if self.allowed and self.inapplicable_requested_codes:
            raise ValueError(
                "allowed decision 不能携带 inapplicable requested codes。"
            )

        if not self.allowed and not self.inapplicable_requested_codes:
            raise ValueError(
                "denied decision 必须指出不适用的 requested codes。"
            )

        return self


@lru_cache(maxsize=1)
def _channel_catalog_v2() -> tuple[dict[str, Any], ...]:
    manifest = load_and_validate_day64_manifest()
    channels = manifest["fixed_dimensions"]["channels"]

    return tuple(
        dict(channel)
        for channel in channels
        if channel.get("is_active") is True
    )


@lru_cache(maxsize=1)
def channel_label_by_code_v2() -> dict[str, str]:
    return {
        str(channel["channel_code"]).strip(): (
            str(channel["channel_name"]).strip()
        )
        for channel in _channel_catalog_v2()
    }


def channel_codes_for_role_v2(
    role: ChannelBusinessRoleV2,
) -> frozenset[str]:
    codes: set[str] = set()

    for channel in _channel_catalog_v2():
        code = str(channel["channel_code"]).strip()
        is_sales = bool(channel["is_sales_channel"])
        is_marketing = bool(channel["is_marketing_channel"])

        if role == ChannelBusinessRoleV2.SALES and is_sales:
            codes.add(code)
        elif (
            role == ChannelBusinessRoleV2.MARKETING
            and is_marketing
        ):
            codes.add(code)
        elif (
            role == ChannelBusinessRoleV2.DIRECT_RESPONSE
            and is_sales
            and is_marketing
        ):
            codes.add(code)

    if not codes:
        raise ValueError(
            f"Manifest 没有为 role={role.value} 提供有效渠道。"
        )

    return frozenset(codes)


def resolve_metric_channel_role_v2(
    metric_name: str,
) -> ChannelBusinessRoleV2:
    """
    Day93 第一版 Metric -> Channel Business Role。

    - ROI / CAC 同时依赖销售与营销事实，当前使用
      direct-response intersection；
    - 纯营销投入类指标使用 marketing；
    - 其他当前 Query Plan Catalog 指标默认属于 sales scope。

    新营销指标进入正式 Catalog 时必须显式补充这里的 policy，
    不能靠 UI 猜。
    """

    normalized = metric_name.strip().casefold()

    if not normalized:
        raise ValueError("metric_name 不能为空。")

    if normalized in {"roi", "cac"}:
        return ChannelBusinessRoleV2.DIRECT_RESPONSE

    if normalized in {
        "marketing_spend",
        "marketing_cost",
        "ad_spend",
    }:
        return ChannelBusinessRoleV2.MARKETING

    return ChannelBusinessRoleV2.SALES


def validate_requested_channel_applicability_v2(
    *,
    metric_name: str,
    requested_scope: RequestedScopeResolutionV2 | None,
) -> MetricChannelApplicabilityDecisionV2:
    role = resolve_metric_channel_role_v2(metric_name)
    applicable = channel_codes_for_role_v2(role)

    requested = (
        requested_scope.channel_codes
        if requested_scope is not None
        else frozenset()
    )

    inapplicable = requested - applicable

    if inapplicable:
        labels = channel_label_by_code_v2()
        display = "、".join(
            labels.get(code, code)
            for code in sorted(inapplicable)
        )

        if role == ChannelBusinessRoleV2.SALES:
            reason = (
                f"{display}不是当前 Dataset V2 的销售渠道，"
                "不能作为该销售类指标的渠道范围。"
            )
        elif role == ChannelBusinessRoleV2.MARKETING:
            reason = (
                f"{display}不是当前 Dataset V2 的营销渠道，"
                "不能作为该营销类指标的渠道范围。"
            )
        else:
            reason = (
                f"{display}不属于当前可用于销售×营销直接响应"
                "指标计算的渠道交集。"
            )

        return MetricChannelApplicabilityDecisionV2(
            metric_name=metric_name,
            channel_role=role,
            allowed=False,
            applicable_channel_codes=applicable,
            requested_channel_codes=requested,
            inapplicable_requested_codes=inapplicable,
            message=reason,
        )

    return MetricChannelApplicabilityDecisionV2(
        metric_name=metric_name,
        channel_role=role,
        allowed=True,
        applicable_channel_codes=applicable,
        requested_channel_codes=requested,
        inapplicable_requested_codes=frozenset(),
        message=(
            "Requested Channel Scope 与当前指标的业务适用范围一致。"
        ),
    )
