from __future__ import annotations

from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.agents.focused_change_breakdown_v2 import (
    FocusedChangeBreakdownResultV2,
    FocusedChangeDimensionV2,
    FocusedChangeReconciliationStatusV2,
)


class ChangeConcentrationPatternV2(str, Enum):
    DOMINANT = "dominant"
    LEADING_NOT_DOMINANT = "leading_not_dominant"
    NEAR_TIE = "near_tie"
    DISTRIBUTED = "distributed"
    UNAVAILABLE = "unavailable"


class InvestigationStepAssessmentPolicyV2(BaseModel):
    """
    Day93 Post-Step Business Interpretation Policy。

    这是调查路由使用的第一版保守阈值，不是统计学定律。
    后续应通过 Blind Test / Human Calibration 调整。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    policy_version: str = "day93_investigation_step_assessment_v2_0"

    dominant_min_share: Decimal = Field(
        default=Decimal("0.50"),
        ge=Decimal("0"),
    )
    dominant_min_gap: Decimal = Field(
        default=Decimal("0.15"),
        ge=Decimal("0"),
    )
    near_tie_max_gap: Decimal = Field(
        default=Decimal("0.05"),
        ge=Decimal("0"),
    )

    @model_validator(mode="after")
    def validate_policy(
        self,
    ) -> "InvestigationStepAssessmentPolicyV2":
        if self.near_tie_max_gap > self.dominant_min_gap:
            raise ValueError(
                "near_tie_max_gap 不能大于 dominant_min_gap。"
            )
        return self


class InvestigationStepAssessmentV2(BaseModel):
    """
    已完成 Change Breakdown 的确定性业务解释。

    这里只解释数值变化结构：
    - 最大同方向变化成员；
    - Top1 / Top2 gap；
    - Top2 concentration；
    - concentration pattern；
    - 可以确认 / 不能确认；
    - 下一步调查建议。

    不证明业务因果。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    policy_version: str

    dimension_name: FocusedChangeDimensionV2
    pattern: ChangeConcentrationPatternV2

    leader_member_key: str | None = None
    leader_member_label: str | None = None
    leader_share: Decimal | None = None

    runner_up_member_key: str | None = None
    runner_up_member_label: str | None = None
    runner_up_share: Decimal | None = None

    leader_gap: Decimal | None = None
    top2_concentration: Decimal | None = None

    conclusion: str
    can_confirm: tuple[str, ...]
    cannot_confirm: tuple[str, ...]
    next_step_recommendation: str

    @model_validator(mode="after")
    def validate_assessment(
        self,
    ) -> "InvestigationStepAssessmentV2":
        for value, field_name in (
            (self.conclusion, "conclusion"),
            (self.next_step_recommendation, "next_step_recommendation"),
        ):
            if not value.strip():
                raise ValueError(f"{field_name} 不能为空。")

        if not self.can_confirm:
            raise ValueError("can_confirm 不能为空。")

        if not self.cannot_confirm:
            raise ValueError("cannot_confirm 不能为空。")

        if self.pattern == ChangeConcentrationPatternV2.UNAVAILABLE:
            if any(
                value is not None
                for value in (
                    self.leader_member_key,
                    self.leader_member_label,
                    self.leader_share,
                    self.runner_up_member_key,
                    self.runner_up_member_label,
                    self.runner_up_share,
                    self.leader_gap,
                    self.top2_concentration,
                )
            ):
                raise ValueError(
                    "UNAVAILABLE assessment 不应发布 concentration ranking。"
                )

        return self


DEFAULT_INVESTIGATION_STEP_ASSESSMENT_POLICY_V2 = (
    InvestigationStepAssessmentPolicyV2()
)


def _dimension_label_v2(
    dimension: FocusedChangeDimensionV2,
) -> str:
    return {
        FocusedChangeDimensionV2.CHANNEL: "渠道",
        FocusedChangeDimensionV2.CATEGORY: "品类",
        FocusedChangeDimensionV2.REGION: "城市",
        FocusedChangeDimensionV2.AREA: "大区",
        FocusedChangeDimensionV2.PROVINCE: "省级地区",
        FocusedChangeDimensionV2.CITY: "城市",
        FocusedChangeDimensionV2.CAMPAIGN: "活动实例",
    }[dimension]


def _same_direction_members_v2(
    result: FocusedChangeBreakdownResultV2,
):
    if result.focus_delta > 0:
        ranked_keys = result.positive_change_ranking
    elif result.focus_delta < 0:
        ranked_keys = result.negative_change_ranking
    else:
        return ()

    by_key = {
        member.member_key: member
        for member in result.members
    }

    members = []

    for key in ranked_keys:
        member = by_key[key]
        share = member.share_of_focus_delta

        if share is None or share <= 0:
            continue

        members.append(member)

    return tuple(members)


def assess_investigation_step_v2(
    *,
    result: FocusedChangeBreakdownResultV2,
    is_overall_scope: bool,
    policy: InvestigationStepAssessmentPolicyV2 = (
        DEFAULT_INVESTIGATION_STEP_ASSESSMENT_POLICY_V2
    ),
) -> InvestigationStepAssessmentV2:
    """
    对已经完成 Reconciliation 的 Change Breakdown 做业务解释。

    分类：
    - DOMINANT：
      Top1 share >= 50%，且 Top1-Top2 >= 15pp。
    - NEAR_TIE：
      Top1-Top2 <= 5pp。
    - LEADING_NOT_DOMINANT：
      Top1-Top2 >= 15pp，但 Top1 share < 50%。
    - DISTRIBUTED：
      其他已对账情况。
    """

    dimension_label = _dimension_label_v2(
        result.dimension_name
    )
    scope_label = (
        "整体 GMV"
        if is_overall_scope
        else f"{result.focus_member_label} GMV"
    )

    if (
        result.reconciliation_status
        != FocusedChangeReconciliationStatusV2.RECONCILED
    ):
        return InvestigationStepAssessmentV2(
            policy_version=policy.policy_version,
            dimension_name=result.dimension_name,
            pattern=ChangeConcentrationPatternV2.UNAVAILABLE,
            conclusion=(
                f"{dimension_label}变化额尚未与{scope_label}变化额"
                "完成核对，因此当前不发布集中度结论。"
            ),
            can_confirm=(
                "当前已有两期受治理结果。",
            ),
            cannot_confirm=(
                "在变化额未完成核对前，不能把可见成员视为完整数值解释。",
                "不能据此判断业务根因。",
            ),
            next_step_recommendation=(
                "先解决当前变化分解的核对缺口，再决定后续调查方向。"
            ),
        )

    if result.focus_delta == 0:
        return InvestigationStepAssessmentV2(
            policy_version=policy.policy_version,
            dimension_name=result.dimension_name,
            pattern=ChangeConcentrationPatternV2.UNAVAILABLE,
            conclusion=(
                f"{scope_label}本期与参考期没有净变化，"
                f"当前不使用{dimension_label}贡献率判断调查优先级。"
            ),
            can_confirm=(
                f"{scope_label}两期净变化为 0。",
            ),
            cannot_confirm=(
                f"不能用{dimension_label}贡献率形成单一调查焦点。",
                "不能据此判断业务根因。",
            ),
            next_step_recommendation=(
                "如需继续调查，应改看绝对变化、结构迁移或其他业务信号。"
            ),
        )

    ranked = _same_direction_members_v2(result)

    if not ranked:
        return InvestigationStepAssessmentV2(
            policy_version=policy.policy_version,
            dimension_name=result.dimension_name,
            pattern=ChangeConcentrationPatternV2.UNAVAILABLE,
            conclusion=(
                f"当前没有可用于{dimension_label}集中度判断的"
                "同方向变化成员。"
            ),
            can_confirm=(
                f"{dimension_label}变化额已经与{scope_label}变化额核对一致。",
            ),
            cannot_confirm=(
                "当前不能形成可靠的成员集中度排序。",
                "不能据此判断业务根因。",
            ),
            next_step_recommendation=(
                "继续补充其他维度或业务证据。"
            ),
        )

    leader = ranked[0]
    leader_share = leader.share_of_focus_delta
    assert leader_share is not None

    runner_up = ranked[1] if len(ranked) >= 2 else None
    runner_up_share = (
        runner_up.share_of_focus_delta
        if runner_up is not None
        else None
    )

    leader_gap = (
        leader_share - runner_up_share
        if runner_up_share is not None
        else None
    )
    top2_concentration = (
        leader_share + runner_up_share
        if runner_up_share is not None
        else leader_share
    )

    if (
        leader_share >= policy.dominant_min_share
        and (
            runner_up_share is None
            or (
                leader_gap is not None
                and leader_gap >= policy.dominant_min_gap
            )
        )
    ):
        pattern = ChangeConcentrationPatternV2.DOMINANT
    elif (
        leader_gap is not None
        and leader_gap <= policy.near_tie_max_gap
    ):
        pattern = ChangeConcentrationPatternV2.NEAR_TIE
    elif (
        leader_gap is not None
        and leader_gap >= policy.dominant_min_gap
        and leader_share < policy.dominant_min_share
    ):
        pattern = (
            ChangeConcentrationPatternV2
            .LEADING_NOT_DOMINANT
        )
    else:
        pattern = ChangeConcentrationPatternV2.DISTRIBUTED

    change_word = (
        "增长"
        if result.focus_delta > 0
        else "下降"
    )

    if runner_up is None:
        comparison_clause = ""
    else:
        assert runner_up_share is not None
        assert leader_gap is not None
        comparison_clause = (
            f"，第二位是{runner_up.member_label}"
            f"（{runner_up_share * 100:.2f}%），"
            f"两者相差 {leader_gap * 100:.2f} 个百分点"
        )

    if pattern == ChangeConcentrationPatternV2.DOMINANT:
        if result.dimension_name == FocusedChangeDimensionV2.CAMPAIGN:
            pattern_sentence = (
                f"在活动归因订单的数值分解中，"
                f"{leader.member_label}已经形成单一主导的数值来源。"
            )
        else:
            pattern_sentence = (
                f"{leader.member_label}已经达到当前调查规则的"
                "单一主导条件。"
            )
    elif (
        pattern
        == ChangeConcentrationPatternV2.LEADING_NOT_DOMINANT
    ):
        pattern_sentence = (
            f"{leader.member_label}明显领先其他{dimension_label}，"
            "但占比尚未达到单一主导阈值。"
        )
    elif pattern == ChangeConcentrationPatternV2.NEAR_TIE:
        pattern_sentence = (
            f"前两位{dimension_label}的变化贡献非常接近，"
            "当前没有明显单一主导成员。"
        )
    else:
        pattern_sentence = (
            f"{dimension_label}变化贡献较为分散，"
            "当前没有形成满足单一主导条件的成员。"
        )

    if result.dimension_name == FocusedChangeDimensionV2.CHANNEL:
        conclusion = (
            f"{leader.member_label}是当前渠道层面最大的数值"
            f"{change_word}来源，"
            f"占{scope_label}净变化的 {leader_share * 100:.2f}%"
            f"{comparison_clause}。"
            f"{pattern_sentence}"
        )
    else:
        conclusion = (
            f"{leader.member_label}是当前最大的数值{change_word}来源，"
            f"占{scope_label}净变化的 {leader_share * 100:.2f}%"
            f"{comparison_clause}。"
            f"{pattern_sentence}"
        )

    can_confirm_items = [
        f"{dimension_label}变化额合计与{scope_label}变化额一致。",
        (
            f"{leader.member_label}是当前最大的同方向数值变化来源，"
            f"占比为 {leader_share * 100:.2f}%。"
        ),
    ]

    if runner_up is not None:
        can_confirm_items.append(
            f"前两位{dimension_label}合计贡献 "
            f"{top2_concentration * 100:.2f}% 的净变化。"
        )

    if result.dimension_name == FocusedChangeDimensionV2.CAMPAIGN:
        cannot_confirm = (
            (
                "这些结果只能说明不同活动归因订单与 GMV 净变化之间的"
                "数值关联，不能证明活动造成了对应增量。"
            ),
            (
                "没有反事实或实验对照时，不能把 Campaign 贡献率"
                "解释成活动 uplift 或最终业务根因。"
            ),
        )
    else:
        cannot_confirm = (
            (
                f"这些结果只能说明{dimension_label}层面的数值变化来源，"
                "不能证明业务因果。"
            ),
            (
                f"不能仅凭当前{dimension_label}贡献，"
                "直接认定某个成员是最终业务根因。"
            ),
        )

    if result.dimension_name == FocusedChangeDimensionV2.CHANNEL:
        if pattern == ChangeConcentrationPatternV2.DOMINANT:
            next_step = (
                f"{leader.member_label}在渠道变化中形成单一主导；"
                "建议继续补充品类、活动或客户证据，判断该渠道的"
                "数值集中是否具有稳定业务解释。"
            )
        else:
            next_step = (
                "当前渠道变化没有形成单一主导。"
                "系统不会机械锁定 Top1 渠道；建议保持当前分析范围，"
                "转向品类、地区、活动或客户证据继续调查。"
            )

    elif result.dimension_name == FocusedChangeDimensionV2.CATEGORY:
        if pattern == ChangeConcentrationPatternV2.DOMINANT:
            next_step = (
                f"建议围绕{leader.member_label}继续补充渠道或地区证据，"
                "验证该品类的变化是否集中在特定业务范围。"
            )
        else:
            next_step = (
                "建议从大区层级检查地理分布，判断整体变化是否存在"
                "明显的区域集中。"
            )

    elif result.dimension_name == FocusedChangeDimensionV2.AREA:
        if pattern == ChangeConcentrationPatternV2.DOMINANT:
            next_step = (
                f"{leader.member_label}达到单一主导条件；"
                "可以在保持原 Requested Scope 的前提下，"
                "只在该大区内继续检查省级变化。"
            )
        else:
            next_step = (
                "当前大区变化没有形成单一主导。"
                "系统不会机械选择 Top1 大区继续下钻；"
                "建议转向品类、活动、营销或客户证据。"
            )

    elif result.dimension_name == FocusedChangeDimensionV2.PROVINCE:
        if pattern == ChangeConcentrationPatternV2.DOMINANT:
            next_step = (
                f"{leader.member_label}达到单一主导条件；"
                "可以在当前大区范围内进一步检查该省的城市变化。"
            )
        else:
            next_step = (
                "当前省级变化没有形成单一主导。"
                "系统不会机械选择 Top1 省份继续下钻到城市。"
            )

    elif result.dimension_name == FocusedChangeDimensionV2.CITY:
        next_step = (
            "城市已经是当前 Geography Hierarchy 的叶子层级。"
            "如需继续解释业务原因，应转向品类、活动、营销或客户证据。"
        )

    elif result.dimension_name == FocusedChangeDimensionV2.CAMPAIGN:
        if pattern == ChangeConcentrationPatternV2.DOMINANT:
            next_step = (
                f"{leader.member_label}对应订单的数值变化较集中；"
                "下一步应补充活动窗口、优惠机制、客户或渠道证据，"
                "判断该活动关联是否具有稳定业务解释。"
            )
        else:
            next_step = (
                "活动实例层面的变化贡献没有形成单一主导。"
                "建议结合活动窗口、优惠机制、客户或渠道证据继续判断。"
            )

    else:
        if pattern == ChangeConcentrationPatternV2.DOMINANT:
            next_step = (
                f"建议围绕{leader.member_label}继续补充品类、活动、"
                "流量或客户证据，验证数值集中背后的业务解释。"
            )
        else:
            next_step = (
                "当前旧城市粒度变化贡献没有形成明确单一主导。"
                "新业务路径应优先使用大区 → 省 → 市层级。"
            )

    return InvestigationStepAssessmentV2(
        policy_version=policy.policy_version,
        dimension_name=result.dimension_name,
        pattern=pattern,
        leader_member_key=leader.member_key,
        leader_member_label=leader.member_label,
        leader_share=leader_share,
        runner_up_member_key=(
            runner_up.member_key
            if runner_up is not None
            else None
        ),
        runner_up_member_label=(
            runner_up.member_label
            if runner_up is not None
            else None
        ),
        runner_up_share=runner_up_share,
        leader_gap=leader_gap,
        top2_concentration=top2_concentration,
        conclusion=conclusion,
        can_confirm=tuple(can_confirm_items),
        cannot_confirm=cannot_confirm,
        next_step_recommendation=next_step,
    )
