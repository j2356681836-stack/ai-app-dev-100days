from __future__ import annotations

from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class FocusedChangeDimensionV2(str, Enum):
    CATEGORY = "category"
    CHANNEL = "channel"

    # Legacy city-level compatibility dimension.
    REGION = "region"

    # Day93 Geography Hierarchy.
    AREA = "area"
    PROVINCE = "province"
    CITY = "city"

    # Day93 Activity / Promotion:
    # Campaign is order-level activity attribution.
    CAMPAIGN = "campaign"


class FocusedChangeReconciliationStatusV2(str, Enum):
    RECONCILED = "reconciled"
    NOT_RECONCILED = "not_reconciled"


class FocusedChangeObservationV2(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    member_key: str
    member_label: str
    value: Decimal


class FocusedChangeMemberV2(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    member_key: str
    member_label: str
    reference_value: Decimal
    current_value: Decimal
    delta: Decimal
    share_of_focus_delta: Decimal | None


class FocusedChangeBreakdownResultV2(BaseModel):
    """
    Dataset V2 candidate path 下的 Focused Change Breakdown。

    当前支持：
    - GMV × channel
    - GMV × category
    - GMV × region（legacy city-level compatibility）
    - GMV × area
    - GMV × province
    - GMV × city
    - GMV × campaign

    只证明数值变化来源，不证明业务因果。
    Campaign 贡献只表示与活动归因订单的数值关联，
    不等价于活动造成的增量 uplift。
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    metric_name: str = "gmv"
    dimension_name: FocusedChangeDimensionV2

    focus_member_key: str
    focus_member_label: str

    reference_focus_value: Decimal
    current_focus_value: Decimal
    focus_delta: Decimal

    members: tuple[FocusedChangeMemberV2, ...]
    positive_change_ranking: tuple[str, ...]
    negative_change_ranking: tuple[str, ...]

    sum_member_delta: Decimal
    unexplained_remainder: Decimal

    reconciliation_tolerance: Decimal = Field(
        default=Decimal("0.01"),
        ge=Decimal("0"),
    )
    reconciliation_status: FocusedChangeReconciliationStatusV2


def _index_observations_v2(
    *,
    observations: tuple[FocusedChangeObservationV2, ...],
    side: str,
) -> dict[str, FocusedChangeObservationV2]:
    indexed: dict[str, FocusedChangeObservationV2] = {}

    for observation in observations:
        key = observation.member_key.strip()

        if not key:
            raise ValueError(f"{side} member_key 不能为空。")

        if not observation.member_label.strip():
            raise ValueError(f"{side} member_label 不能为空。")

        if key in indexed:
            raise ValueError(f"{side} 存在重复 member_key：{key}")

        indexed[key] = observation

    return indexed


def analyze_focused_change_breakdown_v2(
    *,
    dimension_name: FocusedChangeDimensionV2,
    focus_member_key: str,
    focus_member_label: str,
    reference_focus_value: Decimal,
    current_focus_value: Decimal,
    reference_members: tuple[FocusedChangeObservationV2, ...],
    current_members: tuple[FocusedChangeObservationV2, ...],
    reconciliation_tolerance: Decimal = Decimal("0.01"),
) -> FocusedChangeBreakdownResultV2:
    if not focus_member_key.strip():
        raise ValueError("focus_member_key 不能为空。")

    if not focus_member_label.strip():
        raise ValueError("focus_member_label 不能为空。")

    if reconciliation_tolerance < 0:
        raise ValueError("reconciliation_tolerance 不能小于 0。")

    reference_by_key = _index_observations_v2(
        observations=reference_members,
        side="reference",
    )
    current_by_key = _index_observations_v2(
        observations=current_members,
        side="current",
    )

    member_keys = sorted(set(reference_by_key) | set(current_by_key))
    focus_delta = current_focus_value - reference_focus_value

    members: list[FocusedChangeMemberV2] = []

    for member_key in member_keys:
        reference = reference_by_key.get(member_key)
        current = current_by_key.get(member_key)

        if reference is not None and current is not None:
            if reference.member_label != current.member_label:
                raise ValueError(
                    "同一 member_key 在两期的 label 不一致："
                    f"{member_key}"
                )
            member_label = current.member_label
        elif current is not None:
            member_label = current.member_label
        elif reference is not None:
            member_label = reference.member_label
        else:
            raise RuntimeError("不可达的 member alignment 状态。")

        reference_value = (
            reference.value if reference is not None else Decimal("0")
        )
        current_value = (
            current.value if current is not None else Decimal("0")
        )
        delta = current_value - reference_value

        share_of_focus_delta = (
            None if focus_delta == 0 else delta / focus_delta
        )

        members.append(
            FocusedChangeMemberV2(
                member_key=member_key,
                member_label=member_label,
                reference_value=reference_value,
                current_value=current_value,
                delta=delta,
                share_of_focus_delta=share_of_focus_delta,
            )
        )

    sum_member_delta = sum(
        (member.delta for member in members),
        Decimal("0"),
    )
    unexplained_remainder = focus_delta - sum_member_delta

    reconciliation_status = (
        FocusedChangeReconciliationStatusV2.RECONCILED
        if abs(unexplained_remainder) <= reconciliation_tolerance
        else FocusedChangeReconciliationStatusV2.NOT_RECONCILED
    )

    positive_change_ranking = tuple(
        member.member_key
        for member in sorted(
            (item for item in members if item.delta > 0),
            key=lambda item: (-item.delta, item.member_key),
        )
    )

    negative_change_ranking = tuple(
        member.member_key
        for member in sorted(
            (item for item in members if item.delta < 0),
            key=lambda item: (item.delta, item.member_key),
        )
    )

    return FocusedChangeBreakdownResultV2(
        dimension_name=dimension_name,
        focus_member_key=focus_member_key.strip(),
        focus_member_label=focus_member_label.strip(),
        reference_focus_value=reference_focus_value,
        current_focus_value=current_focus_value,
        focus_delta=focus_delta,
        members=tuple(members),
        positive_change_ranking=positive_change_ranking,
        negative_change_ranking=negative_change_ranking,
        sum_member_delta=sum_member_delta,
        unexplained_remainder=unexplained_remainder,
        reconciliation_tolerance=reconciliation_tolerance,
        reconciliation_status=reconciliation_status,
    )
