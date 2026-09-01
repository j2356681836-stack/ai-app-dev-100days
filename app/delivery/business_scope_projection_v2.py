from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from app.semantic_layer.channel_applicability_v2 import (
    ChannelBusinessRoleV2,
    channel_codes_for_role_v2,
    channel_label_by_code_v2,
)
from app.db.beauty_bi_v2.manifest_loader import (
    load_and_validate_day64_manifest,
)


class BusinessScopeProjectionV2(BaseModel):
    """
    Business-facing Scope Projection。

    原始 scope_summary 仍来自 Governed Scope Binding；
    本层只负责把稳定代码转换成简洁业务摘要。

    注意：
    Authorized Scope != Metric Applicable Scope。
    channel_role 会进一步过滤业务上不适用于当前指标的渠道。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    channel_summary: str
    geography_summary: str

    channel_member_labels: tuple[str, ...] = ()
    geography_member_labels: tuple[str, ...] = ()

    channel_is_full_dataset_scope: bool = False
    geography_is_full_dataset_scope: bool = False


def _region_label_by_code_v2() -> dict[str, str]:
    manifest = load_and_validate_day64_manifest()
    regions = manifest["fixed_dimensions"]["regions"]

    return {
        str(region["region_code"]).strip(): (
            str(region["region_name"]).strip()
        )
        for region in regions
    }


def _parse_scope_codes_v2(
    scope_summary: str | None,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if scope_summary is None or not scope_summary.strip():
        return (), ()

    channel_codes: tuple[str, ...] = ()
    region_codes: tuple[str, ...] = ()

    parts = tuple(
        part.strip()
        for part in scope_summary.split("；")
        if part.strip()
    )

    for part in parts:
        if part.startswith("渠道代码："):
            raw = part.removeprefix("渠道代码：")
            channel_codes = tuple(
                item.strip()
                for item in raw.split("、")
                if item.strip()
            )
        elif part.startswith("地区代码："):
            raw = part.removeprefix("地区代码：")
            region_codes = tuple(
                item.strip()
                for item in raw.split("、")
                if item.strip()
            )

    return channel_codes, region_codes


def build_business_scope_projection_v2(
    scope_summary: str | None,
    *,
    channel_role: ChannelBusinessRoleV2 = (
        ChannelBusinessRoleV2.SALES
    ),
) -> BusinessScopeProjectionV2:
    raw_channel_codes, region_codes = _parse_scope_codes_v2(
        scope_summary
    )

    applicable_codes = channel_codes_for_role_v2(
        channel_role
    )

    # 即使历史 Evidence Scope Summary 仍含“有权访问但业务不适用”的
    # 渠道，Business Projection 也不能把它展示成当前指标范围。
    channel_codes = tuple(
        code
        for code in raw_channel_codes
        if code in applicable_codes
    )

    channel_labels_map = channel_label_by_code_v2()
    region_labels_map = _region_label_by_code_v2()

    channel_labels = tuple(
        channel_labels_map.get(code, code)
        for code in channel_codes
    )
    region_labels = tuple(
        region_labels_map.get(code, code)
        for code in region_codes
    )

    full_channel = (
        bool(channel_codes)
        and set(channel_codes) == set(applicable_codes)
    )

    all_region_codes = frozenset(region_labels_map)
    full_region = (
        bool(region_codes)
        and set(region_codes) == set(all_region_codes)
    )

    role_label = {
        ChannelBusinessRoleV2.SALES: "销售渠道",
        ChannelBusinessRoleV2.MARKETING: "营销渠道",
        ChannelBusinessRoleV2.DIRECT_RESPONSE: "直接响应渠道",
    }[channel_role]

    if full_channel:
        channel_summary = (
            f"全部{role_label}（{len(channel_codes)}个）"
        )
    elif len(channel_labels) == 1:
        channel_summary = channel_labels[0]
    elif channel_labels:
        channel_summary = (
            f"{len(channel_labels)}个{role_label}"
        )
    else:
        channel_summary = f"未显式限定{role_label}"

    if full_region:
        geography_summary = (
            f"全部可用城市（{len(region_codes)}个）"
        )
    elif len(region_labels) == 1:
        geography_summary = region_labels[0]
    elif region_labels:
        geography_summary = f"{len(region_labels)}个城市"
    else:
        geography_summary = "未显式限定地区"

    return BusinessScopeProjectionV2(
        channel_summary=channel_summary,
        geography_summary=geography_summary,
        channel_member_labels=channel_labels,
        geography_member_labels=region_labels,
        channel_is_full_dataset_scope=full_channel,
        geography_is_full_dataset_scope=full_region,
    )
