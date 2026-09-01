from __future__ import annotations

from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.agents.contribution_analysis_v2 import (
    ContributionAnalysisResultV2,
    ContributionDirectionV2,
    ContributionReconciliationStatusV2,
)


class ContributionPatternV2(str, Enum):
    DOMINANT = "dominant"
    NEAR_TIE = "near_tie"
    DISTRIBUTED = "distributed"
    UNAVAILABLE = "unavailable"


class ContributionPatternPolicyV2(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    policy_version: str = "day93_contribution_pattern_policy_v2_0"

    dominant_min_share: Decimal = Field(
        default=Decimal("0.50"),
        ge=Decimal("0"),
        le=Decimal("1"),
    )
    dominant_min_gap: Decimal = Field(
        default=Decimal("0.15"),
        ge=Decimal("0"),
        le=Decimal("1"),
    )
    near_tie_max_gap: Decimal = Field(
        default=Decimal("0.05"),
        ge=Decimal("0"),
        le=Decimal("1"),
    )

    @model_validator(mode="after")
    def validate_thresholds(self) -> "ContributionPatternPolicyV2":
        if self.near_tie_max_gap > self.dominant_min_gap:
            raise ValueError(
                "near_tie_max_gap 不能大于 dominant_min_gap。"
            )
        return self


class ContributionPatternAssessmentV2(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    policy_version: str
    metric_name: str
    dimension_name: str

    pattern: ContributionPatternV2
    auto_member_focus_allowed: bool

    leader_member_key: str | None = None
    leader_member_label: str | None = None
    leader_contribution_rate: Decimal | None = None

    runner_up_member_key: str | None = None
    runner_up_member_label: str | None = None
    runner_up_contribution_rate: Decimal | None = None

    leader_gap: Decimal | None = None
    rationale: str

    @model_validator(mode="after")
    def validate_assessment(self) -> "ContributionPatternAssessmentV2":
        if self.auto_member_focus_allowed:
            if self.pattern != ContributionPatternV2.DOMINANT:
                raise ValueError(
                    "只有 DOMINANT pattern 才允许自动建立单一 Member Focus。"
                )
            if self.leader_member_key is None:
                raise ValueError(
                    "允许自动 Focus 时必须提供 leader。"
                )

        if self.pattern == ContributionPatternV2.UNAVAILABLE:
            if any(
                value is not None
                for value in (
                    self.leader_member_key,
                    self.leader_member_label,
                    self.leader_contribution_rate,
                    self.runner_up_member_key,
                    self.runner_up_member_label,
                    self.runner_up_contribution_rate,
                    self.leader_gap,
                )
            ):
                raise ValueError(
                    "UNAVAILABLE assessment 不应发布 leader / gap。"
                )

        if not self.rationale.strip():
            raise ValueError("rationale 不能为空。")

        return self


DEFAULT_CONTRIBUTION_PATTERN_POLICY_V2 = ContributionPatternPolicyV2()


def _same_direction_members_v2(
    result: ContributionAnalysisResultV2,
):
    if result.overall_delta > 0:
        target_direction = ContributionDirectionV2.POSITIVE
    elif result.overall_delta < 0:
        target_direction = ContributionDirectionV2.NEGATIVE
    else:
        return ()

    members = tuple(
        member
        for member in result.members
        if (
            member.direction == target_direction
            and member.contribution_rate is not None
            and member.contribution_rate > 0
        )
    )

    return tuple(
        sorted(
            members,
            key=lambda member: (
                -member.contribution_rate,
                member.member_key,
            ),
        )
    )


def assess_contribution_pattern_v2(
    *,
    result: ContributionAnalysisResultV2,
    policy: ContributionPatternPolicyV2 = (
        DEFAULT_CONTRIBUTION_PATTERN_POLICY_V2
    ),
) -> ContributionPatternAssessmentV2:
    """
    Day93 第一版 Contribution Pattern Assessment。

    当前只支持 GMV × Channel。
    只有已完成 Reconciliation 的结果才允许进入 Routing 判断。

    DOMINANT:
        Top1 share >= 50%
        且 Top1 - Top2 >= 15pp
        => 系统允许自动建立单一 Channel Focus。

    NEAR_TIE:
        Top1 - Top2 <= 5pp
        => 不建立单一 Focus。

    DISTRIBUTED:
        其他已对账情况
        => 不建立单一 Focus。
    """

    if (
        result.metric_name != "gmv"
        or result.dimension_name != "channel"
    ):
        raise ValueError(
            "Contribution Pattern V2 当前只支持 GMV × Channel。"
        )

    if (
        result.reconciliation_status
        != ContributionReconciliationStatusV2.RECONCILED
    ):
        return ContributionPatternAssessmentV2(
            policy_version=policy.policy_version,
            metric_name=result.metric_name,
            dimension_name=result.dimension_name,
            pattern=ContributionPatternV2.UNAVAILABLE,
            auto_member_focus_allowed=False,
            rationale=(
                "渠道 Contribution 尚未完成 Reconciliation，"
                "系统不能据此自动收窄 Investigation Scope。"
            ),
        )

    if result.overall_delta == 0:
        return ContributionPatternAssessmentV2(
            policy_version=policy.policy_version,
            metric_name=result.metric_name,
            dimension_name=result.dimension_name,
            pattern=ContributionPatternV2.UNAVAILABLE,
            auto_member_focus_allowed=False,
            rationale=(
                "Overall GMV 变化额为 0，Contribution Rate "
                "无法作为单一 Focus Routing 依据。"
            ),
        )

    ranked = _same_direction_members_v2(result)

    if not ranked:
        return ContributionPatternAssessmentV2(
            policy_version=policy.policy_version,
            metric_name=result.metric_name,
            dimension_name=result.dimension_name,
            pattern=ContributionPatternV2.UNAVAILABLE,
            auto_member_focus_allowed=False,
            rationale=(
                "当前没有可用于同方向 Contribution Pattern "
                "判断的渠道成员。"
            ),
        )

    leader = ranked[0]
    leader_rate = leader.contribution_rate
    assert leader_rate is not None

    runner_up = ranked[1] if len(ranked) >= 2 else None

    if runner_up is None:
        if leader_rate >= policy.dominant_min_share:
            return ContributionPatternAssessmentV2(
                policy_version=policy.policy_version,
                metric_name=result.metric_name,
                dimension_name=result.dimension_name,
                pattern=ContributionPatternV2.DOMINANT,
                auto_member_focus_allowed=True,
                leader_member_key=leader.member_key,
                leader_member_label=leader.member_label,
                leader_contribution_rate=leader_rate,
                rationale=(
                    "仅存在一个可比较的同方向主要贡献成员，"
                    "且其 Contribution Rate 达到自动 Focus 阈值。"
                ),
            )

        return ContributionPatternAssessmentV2(
            policy_version=policy.policy_version,
            metric_name=result.metric_name,
            dimension_name=result.dimension_name,
            pattern=ContributionPatternV2.DISTRIBUTED,
            auto_member_focus_allowed=False,
            leader_member_key=leader.member_key,
            leader_member_label=leader.member_label,
            leader_contribution_rate=leader_rate,
            rationale=(
                "当前没有第二个同方向成员可形成明显 gap，"
                "且 Top1 未达到单一主导阈值；保持原 Requested Scope。"
            ),
        )

    runner_up_rate = runner_up.contribution_rate
    assert runner_up_rate is not None

    leader_gap = leader_rate - runner_up_rate

    if (
        leader_rate >= policy.dominant_min_share
        and leader_gap >= policy.dominant_min_gap
    ):
        pattern = ContributionPatternV2.DOMINANT
        auto_focus = True
        rationale = (
            "Top1 Contribution 达到主导阈值，且与 Top2 "
            "存在足够差距；系统允许把 Top1 作为单一调查焦点。"
        )
    elif leader_gap <= policy.near_tie_max_gap:
        pattern = ContributionPatternV2.NEAR_TIE
        auto_focus = False
        rationale = (
            "Top1 与 Top2 Contribution 差距很小，"
            "当前证据不足以把单一渠道视为明显优先调查对象；"
            "保持原 Requested Scope。"
        )
    else:
        pattern = ContributionPatternV2.DISTRIBUTED
        auto_focus = False
        rationale = (
            "渠道贡献未形成满足主导阈值的单一 Leader；"
            "系统不自动收窄到单一渠道。"
        )

    return ContributionPatternAssessmentV2(
        policy_version=policy.policy_version,
        metric_name=result.metric_name,
        dimension_name=result.dimension_name,
        pattern=pattern,
        auto_member_focus_allowed=auto_focus,
        leader_member_key=leader.member_key,
        leader_member_label=leader.member_label,
        leader_contribution_rate=leader_rate,
        runner_up_member_key=runner_up.member_key,
        runner_up_member_label=runner_up.member_label,
        runner_up_contribution_rate=runner_up_rate,
        leader_gap=leader_gap,
        rationale=rationale,
    )
