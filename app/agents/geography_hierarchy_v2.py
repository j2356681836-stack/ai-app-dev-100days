from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from enum import Enum
from functools import lru_cache
from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator

from app.agents.investigation_route_v2 import GeographyLevelV2
from app.db.beauty_bi_v2.manifest_loader import (
    load_and_validate_day64_manifest,
)
from app.semantic_layer.requested_scope_resolution_v2 import (
    RequestedScopeDimensionV2,
    RequestedScopeResolutionStatusV2,
    RequestedScopeResolutionV2,
)


class GeographyHierarchyStatusV2(str, Enum):
    READY = "ready"
    LEAF = "leaf"


AREA_DISPLAY_LABELS_V2: dict[str, str] = {
    "north": "华北",
    "east": "华东",
    "south": "华南",
    "central": "华中",
    "southwest": "西南",
    "northeast": "东北",
    "northwest": "西北",
}


class GeographyHierarchyMemberV2(BaseModel):
    """
    Dataset V2 Geography Hierarchy 的稳定业务成员。

    area:
        member_key = region_group code
    province:
        member_key = province_name
        Dataset V2 当前没有独立 province_code，因此不伪造代码。
    city:
        member_key = region_code

    无论在哪一层，最终 Governed Scope 都只释放为真实 region_codes。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    level: GeographyLevelV2
    member_key: str
    member_label: str
    region_codes: frozenset[str]

    parent_level: GeographyLevelV2 | None = None
    parent_key: str | None = None

    @model_validator(mode="after")
    def validate_member(
        self,
    ) -> "GeographyHierarchyMemberV2":
        if not self.member_key.strip():
            raise ValueError("member_key 不能为空。")

        if not self.member_label.strip():
            raise ValueError("member_label 不能为空。")

        if not self.region_codes:
            raise ValueError(
                "Geography member 必须绑定至少一个真实 region_code。"
            )

        if (self.parent_level is None) != (self.parent_key is None):
            raise ValueError(
                "parent_level / parent_key 必须同时存在或同时为空。"
            )

        return self


class GeographyFocusScopeV2(BaseModel):
    """
    Investigation Geography Focus。

    这里保存业务层 Focus，但 Governed Planning 仍只消费
    region_codes，因此不需要让 SQL / Governance 层理解
    “华南”或“广东省”这样的新自由文本维度。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    level: GeographyLevelV2
    member_key: str
    member_label: str
    region_codes: frozenset[str]
    source_evidence_id: str

    # Two-period values are only promoted from reconciled Geography Change Evidence.
    reference_value: Decimal | None = None
    current_value: Decimal | None = None
    delta: Decimal | None = None

    @model_validator(mode="after")
    def validate_focus(
        self,
    ) -> "GeographyFocusScopeV2":
        if not self.member_key.strip():
            raise ValueError("member_key 不能为空。")
        if not self.member_label.strip():
            raise ValueError("member_label 不能为空。")
        if not self.region_codes:
            raise ValueError(
                "Geography Focus 必须绑定至少一个 region_code。"
            )
        if not self.source_evidence_id.strip():
            raise ValueError("source_evidence_id 不能为空。")

        values = (self.reference_value, self.current_value, self.delta)
        present = tuple(value is not None for value in values)

        if any(present) and not all(present):
            raise ValueError(
                "Geography Focus comparison values 必须全部存在或全部为空。"
            )

        if all(present):
            assert self.reference_value is not None
            assert self.current_value is not None
            assert self.delta is not None
            if self.current_value - self.reference_value != self.delta:
                raise ValueError(
                    "Geography Focus delta 必须等于 current-reference。"
                )

        return self


@lru_cache(maxsize=1)
def _region_rows_v2() -> tuple[dict[str, Any], ...]:
    manifest = load_and_validate_day64_manifest()
    rows = manifest["fixed_dimensions"]["regions"]

    normalized: list[dict[str, Any]] = []

    for row in rows:
        normalized.append(
            {
                "region_code": str(row["region_code"]).strip(),
                "region_name": str(row["region_name"]).strip(),
                "province_name": str(row["province_name"]).strip(),
                "region_group": str(row["region_group"]).strip(),
            }
        )

    return tuple(normalized)


def next_geography_level_v2(
    current_level: GeographyLevelV2 | None,
) -> GeographyLevelV2 | None:
    """
    无 Geography Focus 时只能从 AREA 开始。

    AREA -> PROVINCE -> CITY -> None
    """

    if current_level is None:
        return GeographyLevelV2.AREA

    return {
        GeographyLevelV2.AREA: GeographyLevelV2.PROVINCE,
        GeographyLevelV2.PROVINCE: GeographyLevelV2.CITY,
        GeographyLevelV2.CITY: None,
    }[current_level]


def list_geography_members_v2(
    *,
    level: GeographyLevelV2,
    parent: GeographyHierarchyMemberV2 | None = None,
) -> tuple[GeographyHierarchyMemberV2, ...]:
    rows = _region_rows_v2()

    if parent is not None:
        expected_level = next_geography_level_v2(
            parent.level
        )
        if expected_level != level:
            raise ValueError(
                "Geography Hierarchy 只能逐层下钻，"
                f"不能从 {parent.level.value} 跳到 {level.value}。"
            )
        rows = tuple(
            row
            for row in rows
            if row["region_code"] in parent.region_codes
        )

    if level == GeographyLevelV2.AREA:
        grouped: dict[str, set[str]] = defaultdict(set)

        for row in rows:
            grouped[row["region_group"]].add(
                row["region_code"]
            )

        members = []

        for group_code, region_codes in grouped.items():
            label = AREA_DISPLAY_LABELS_V2.get(
                group_code
            )
            if label is None:
                raise ValueError(
                    "Dataset V2 出现尚未注册业务展示名的 region_group："
                    f"{group_code}"
                )

            members.append(
                GeographyHierarchyMemberV2(
                    level=level,
                    member_key=group_code,
                    member_label=label,
                    region_codes=frozenset(region_codes),
                )
            )

        return tuple(
            sorted(
                members,
                key=lambda item: item.member_key,
            )
        )

    if level == GeographyLevelV2.PROVINCE:
        grouped: dict[str, set[str]] = defaultdict(set)

        for row in rows:
            grouped[row["province_name"]].add(
                row["region_code"]
            )

        members = []

        for province_name, region_codes in grouped.items():
            members.append(
                GeographyHierarchyMemberV2(
                    level=level,
                    member_key=province_name,
                    member_label=province_name,
                    region_codes=frozenset(region_codes),
                    parent_level=(
                        parent.level
                        if parent is not None
                        else None
                    ),
                    parent_key=(
                        parent.member_key
                        if parent is not None
                        else None
                    ),
                )
            )

        return tuple(
            sorted(
                members,
                key=lambda item: item.member_label,
            )
        )

    if level == GeographyLevelV2.CITY:
        members = []

        for row in rows:
            members.append(
                GeographyHierarchyMemberV2(
                    level=level,
                    member_key=row["region_code"],
                    member_label=row["region_name"],
                    region_codes=frozenset(
                        {row["region_code"]}
                    ),
                    parent_level=(
                        parent.level
                        if parent is not None
                        else None
                    ),
                    parent_key=(
                        parent.member_key
                        if parent is not None
                        else None
                    ),
                )
            )

        return tuple(
            sorted(
                members,
                key=lambda item: item.member_label,
            )
        )

    raise ValueError(
        f"Unsupported Geography Level: {level}"
    )


def get_geography_member_v2(
    *,
    level: GeographyLevelV2,
    member_key: str,
    parent: GeographyHierarchyMemberV2 | None = None,
) -> GeographyHierarchyMemberV2:
    target = member_key.strip()

    if not target:
        raise ValueError("member_key 不能为空。")

    matches = tuple(
        item
        for item in list_geography_members_v2(
            level=level,
            parent=parent,
        )
        if item.member_key == target
    )

    if len(matches) != 1:
        raise ValueError(
            "无法把 Geography member_key 绑定到唯一可信成员："
            f"level={level.value}; key={target}"
        )

    return matches[0]


def build_geography_focus_scope_v2(
    *,
    member: GeographyHierarchyMemberV2,
    source_evidence_id: str,
    reference_value: Decimal | None = None,
    current_value: Decimal | None = None,
    delta: Decimal | None = None,
) -> GeographyFocusScopeV2:
    return GeographyFocusScopeV2(
        level=member.level,
        member_key=member.member_key,
        member_label=member.member_label,
        region_codes=member.region_codes,
        source_evidence_id=source_evidence_id,
        reference_value=reference_value,
        current_value=current_value,
        delta=delta,
    )


def merge_requested_scope_with_geography_focus_v2(
    *,
    requested_scope: RequestedScopeResolutionV2 | None,
    geography_focus: GeographyFocusScopeV2 | None,
) -> RequestedScopeResolutionV2 | None:
    """
    Effective Region Scope =
        Requested Region Scope ∩ Geography Focus Region Codes

    Authorized Scope 仍由 AccessContext 在 Governed Planning 时继续求交集。

    这样“大区 / 省 / 市”只是安全地解析成已有 region_codes，
    不绕过现有 Governance Scope Contract。
    """

    if geography_focus is None:
        return requested_scope

    if requested_scope is None:
        return RequestedScopeResolutionV2(
            status=RequestedScopeResolutionStatusV2.RESOLVED,
            region_codes=geography_focus.region_codes,
            matched_region_terms=(
                geography_focus.member_label,
            ),
        )

    if (
        requested_scope.status
        == RequestedScopeResolutionStatusV2
        .UNRESOLVED_EXPLICIT_SCOPE
        and RequestedScopeDimensionV2.REGION
        in requested_scope.unresolved_dimensions
    ):
        raise ValueError(
            "原始问题存在未解决的明确 Region Scope；"
            "不能通过后续 Geography Focus 偷偷替代。"
        )

    if requested_scope.region_codes:
        effective_regions = (
            requested_scope.region_codes
            & geography_focus.region_codes
        )
    else:
        effective_regions = geography_focus.region_codes

    if not effective_regions:
        raise ValueError(
            "Requested Region Scope 与 Geography Focus 不相交；"
            "调查不能扩大或跳出原用户范围。"
        )

    return RequestedScopeResolutionV2(
        status=RequestedScopeResolutionStatusV2.RESOLVED,
        region_codes=frozenset(effective_regions),
        channel_codes=requested_scope.channel_codes,
        matched_region_terms=(
            *requested_scope.matched_region_terms,
            geography_focus.member_label,
        ),
        matched_channel_terms=(
            requested_scope.matched_channel_terms
        ),
    )
