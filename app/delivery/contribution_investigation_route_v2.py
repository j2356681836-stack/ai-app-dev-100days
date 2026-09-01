from __future__ import annotations

from pydantic import BaseModel, ConfigDict, model_validator

from app.agents.contribution_analysis_v2 import (
    ContributionAnalysisResultV2,
)
from app.agents.contribution_pattern_assessment_v2 import (
    ContributionPatternAssessmentV2,
    ContributionPatternV2,
    assess_contribution_pattern_v2,
)
from app.agents.investigation_route_v2 import (
    InvestigationNextDimensionV2,
    InvestigationRouteV2,
    build_system_route_from_channel_pattern_v2,
)


class ContributionInvestigationRouteRecommendationV2(BaseModel):
    """
    Day93 F02：
    Channel Contribution Pattern -> System Investigation Route。

    该合同不再回答“哪个渠道排第一”，而回答：
    - 当前渠道贡献结构是什么；
    - 系统是否有资格自动收窄到单一渠道；
    - 下一步建议在哪个 Scope 下检查哪个维度。

    当前第一版 Route Policy：
    - DOMINANT -> 可以 Focus leader channel，再看 CATEGORY；
    - NEAR_TIE / DISTRIBUTED -> 保持 Requested Scope，看全局 CATEGORY；
    - UNAVAILABLE -> 不生成 Route Recommendation。

    这里仍然只做 investigation triage，不表达 causality。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    policy_version: str = (
        "day93_f02_contribution_route_policy_v2_0"
    )

    pattern_assessment: ContributionPatternAssessmentV2
    route: InvestigationRouteV2

    recommendation_summary: str
    can_confirm: tuple[str, ...]
    cannot_confirm: tuple[str, ...]

    @model_validator(mode="after")
    def validate_recommendation(
        self,
    ) -> "ContributionInvestigationRouteRecommendationV2":
        if not self.recommendation_summary.strip():
            raise ValueError(
                "recommendation_summary 不能为空。"
            )

        if not self.can_confirm:
            raise ValueError("can_confirm 不能为空。")

        if not self.cannot_confirm:
            raise ValueError("cannot_confirm 不能为空。")

        if (
            self.route.supporting_evidence_ids
            != tuple(
                dict.fromkeys(
                    self.route.supporting_evidence_ids
                )
            )
        ):
            raise ValueError(
                "Route supporting evidence 不能重复。"
            )

        return self


def build_contribution_investigation_route_v2(
    *,
    contribution: ContributionAnalysisResultV2,
    contribution_evidence_id: str,
) -> ContributionInvestigationRouteRecommendationV2 | None:
    """
    从可信 GMV × Channel Contribution 形成 F02 System Route。

    当前 Day93 第一版默认把 CATEGORY 作为跨维度下一步：
    - 这是明确的 deterministic routing policy；
    - 不是 LLM 自由选择；
    - Geography Route 会在正式 Area / Province / City Query Plans
      完成后进入同一 Route Space。

    返回 None：
    当前 Contribution 不能安全支持 Investigation Routing。
    """

    evidence_id = contribution_evidence_id.strip()
    if not evidence_id:
        raise ValueError(
            "contribution_evidence_id 不能为空。"
        )

    assessment = assess_contribution_pattern_v2(
        result=contribution
    )

    if assessment.pattern == ContributionPatternV2.UNAVAILABLE:
        return None

    if assessment.pattern == ContributionPatternV2.DOMINANT:
        planner_rationale = (
            "渠道贡献已经形成明显单一主导成员；"
            "建议先在该渠道范围内检查品类变化构成。"
        )
    elif assessment.pattern == ContributionPatternV2.NEAR_TIE:
        planner_rationale = (
            "渠道 Top1 与 Top2 贡献接近，"
            "不应因为排名第一就自动锁定单一渠道；"
            "建议保持当前 Requested Scope，"
            "切换到品类维度寻找更集中的变化来源。"
        )
    else:
        planner_rationale = (
            "渠道贡献未形成满足主导阈值的单一成员；"
            "建议保持当前 Requested Scope，"
            "切换到品类维度继续分解整体变化。"
        )

    route = build_system_route_from_channel_pattern_v2(
        assessment=assessment,
        next_dimension=InvestigationNextDimensionV2.CATEGORY,
        supporting_evidence_ids=(evidence_id,),
        planner_rationale=planner_rationale,
    )

    leader_label = (
        assessment.leader_member_label
        or "当前 Top1 渠道"
    )

    if assessment.pattern == ContributionPatternV2.DOMINANT:
        summary = (
            f"{leader_label}的变化贡献明显高于其他渠道，"
            "系统建议先把它作为调查焦点，"
            "继续检查该渠道内部的品类变化。"
        )

        can_confirm = (
            "各渠道变化额合计与整体 GMV 变化额一致。",
            (
                f"{leader_label}在当前渠道结果中形成明显领先。"
            ),
            (
                "下一步可以先收窄到该渠道，"
                "再比较参考期与当前期的品类变化。"
            ),
        )
    elif assessment.pattern == ContributionPatternV2.NEAR_TIE:
        gap = assessment.leader_gap
        gap_pp = (
            gap * 100
            if gap is not None
            else None
        )

        if (
            assessment.leader_member_label is not None
            and assessment.runner_up_member_label is not None
            and gap_pp is not None
        ):
            summary = (
                f"{assessment.leader_member_label}与"
                f"{assessment.runner_up_member_label}的渠道贡献"
                f"仅相差 {gap_pp:.2f} 个百分点，"
                "当前没有明显单一主导渠道。"
                "系统建议暂不锁定渠道，改看全局品类变化贡献。"
            )
        else:
            summary = (
                "渠道 Top1 与 Top2 贡献接近，"
                "当前没有明显单一主导渠道。"
                "系统建议暂不锁定渠道，改看全局品类变化贡献。"
            )

        can_confirm = (
            "各渠道变化额合计与整体 GMV 变化额一致。",
            (
                f"{assessment.leader_member_label or '第一位渠道'}与"
                f"{assessment.runner_up_member_label or '第二位渠道'}的"
                "变化贡献非常接近，当前没有明显单一主导渠道。"
            ),
            (
                "因此下一步先保持当前分析范围，"
                "不自动锁定某一个渠道。"
            ),
        )
    else:
        summary = (
            "渠道变化贡献没有形成明显单一主导成员。"
            "系统建议保持当前分析范围，"
            "切换到全局品类变化继续调查。"
        )

        can_confirm = (
            "各渠道变化额合计与整体 GMV 变化额一致。",
            "当前没有渠道形成明显单一主导。",
            "因此下一步保持当前分析范围，切换到品类维度。",
        )

    cannot_confirm = (
        "当前结果只能说明各渠道对整体变化的数值贡献，不能证明业务根因。",
        (
            "系统建议查看品类，只表示下一步值得验证，"
            "不代表品类已经被证明是增长或下降原因。"
        ),
        "品类是否存在更集中的变化来源，需要下一步两期数据验证。",
    )

    return ContributionInvestigationRouteRecommendationV2(
        pattern_assessment=assessment,
        route=route,
        recommendation_summary=summary,
        can_confirm=can_confirm,
        cannot_confirm=cannot_confirm,
    )
