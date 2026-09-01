from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, model_validator

from app.agents.investigation_route_v2 import GeographyLevelV2
from app.agents.investigation_step_assessment_v2 import (
    ChangeConcentrationPatternV2,
    InvestigationStepAssessmentV2,
)
from app.agents.user_investigation_intent_v2 import (
    UserInvestigationDomainV2,
)


class GeographyBranchDecisionTypeV2(str, Enum):
    CONTINUE_INVESTIGATION = "continue_investigation"
    STOP_INVESTIGATION = "stop_investigation"
    LEAF_REACHED = "leaf_reached"


class GeographyBranchDecisionReasonV2(str, Enum):
    DOMINANT_FOCUS = "dominant_focus"
    NO_DOMINANT_GEOGRAPHY = "no_dominant_geography"
    ASSESSMENT_UNAVAILABLE = "assessment_unavailable"
    GEOGRAPHY_LEAF = "geography_leaf"


class GeographyBranchDecisionV2(BaseModel):
    """
    Geography Investigation 的显式业务控制结果。

    重要边界：
    - Decision 本身不执行 Query；
    - STOP 不消耗 Investigation Step Budget；
    - Exploration 只是 escape hatch，不等于系统推荐；
    - 推荐换维度只是产品级下一步建议，不自动执行 Tool。
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    decision: GeographyBranchDecisionTypeV2
    reason: GeographyBranchDecisionReasonV2
    current_level: GeographyLevelV2

    query_executed: bool = False

    next_investigation_level: GeographyLevelV2 | None = None
    exploration_available: bool = False
    exploration_level: GeographyLevelV2 | None = None

    recommended_next_domains: tuple[UserInvestigationDomainV2, ...] = ()

    summary: str
    detail: str

    @model_validator(mode="after")
    def validate_decision(self) -> "GeographyBranchDecisionV2":
        if self.query_executed:
            raise ValueError(
                "Geography Branch Decision 是控制结果，本身不得执行 Query。"
            )

        if not self.summary.strip() or not self.detail.strip():
            raise ValueError("summary / detail 不能为空。")

        if self.decision == GeographyBranchDecisionTypeV2.CONTINUE_INVESTIGATION:
            if self.next_investigation_level is None:
                raise ValueError("CONTINUE 必须提供 next_investigation_level。")
            if self.exploration_available:
                raise ValueError("Evidence 已支持继续调查时不需要 Exploration escape hatch。")

        if self.decision == GeographyBranchDecisionTypeV2.STOP_INVESTIGATION:
            if self.next_investigation_level is not None:
                raise ValueError("STOP 不能声明系统调查下一层。")
            if self.exploration_available and self.exploration_level is None:
                raise ValueError("可探索时必须声明 exploration_level。")

        if self.decision == GeographyBranchDecisionTypeV2.LEAF_REACHED:
            if self.next_investigation_level is not None:
                raise ValueError("Leaf 不能继续 Geography Investigation。")
            if self.exploration_available:
                raise ValueError("City 已是叶子，不再提供更深 Geography Exploration。")

        return self


def _next_level_v2(level: GeographyLevelV2) -> GeographyLevelV2 | None:
    return {
        GeographyLevelV2.AREA: GeographyLevelV2.PROVINCE,
        GeographyLevelV2.PROVINCE: GeographyLevelV2.CITY,
        GeographyLevelV2.CITY: None,
    }[level]


def _level_label_v2(level: GeographyLevelV2) -> str:
    return {
        GeographyLevelV2.AREA: "大区",
        GeographyLevelV2.PROVINCE: "省级地区",
        GeographyLevelV2.CITY: "城市",
    }[level]


def build_geography_branch_decision_v2(
    *,
    current_level: GeographyLevelV2,
    assessment: InvestigationStepAssessmentV2 | None,
) -> GeographyBranchDecisionV2:
    next_level = _next_level_v2(current_level)
    current_label = _level_label_v2(current_level)

    if current_level == GeographyLevelV2.CITY:
        return GeographyBranchDecisionV2(
            decision=GeographyBranchDecisionTypeV2.LEAF_REACHED,
            reason=GeographyBranchDecisionReasonV2.GEOGRAPHY_LEAF,
            current_level=current_level,
            summary="当前已经到城市层级，Geography 调查没有更深的受治理层级。",
            detail=(
                "如需继续解释业务原因，应切换到品类、活动 / 促销、"
                "营销投入或客户结构等其他业务维度。"
            ),
            recommended_next_domains=(
                UserInvestigationDomainV2.CATEGORY_PRODUCT,
                UserInvestigationDomainV2.ACTIVITY_PROMOTION,
                UserInvestigationDomainV2.MARKETING,
                UserInvestigationDomainV2.AUDIENCE,
            ),
        )

    if assessment is None or assessment.pattern == ChangeConcentrationPatternV2.UNAVAILABLE:
        return GeographyBranchDecisionV2(
            decision=GeographyBranchDecisionTypeV2.STOP_INVESTIGATION,
            reason=GeographyBranchDecisionReasonV2.ASSESSMENT_UNAVAILABLE,
            current_level=current_level,
            exploration_available=False,
            summary=(
                f"当前{current_label}证据还不足以决定是否继续向下调查。"
            ),
            detail=(
                "系统不会在缺少可靠变化结构判断时机械下钻；"
                "请先解决当前证据缺口或改看其他业务维度。"
            ),
            recommended_next_domains=(
                UserInvestigationDomainV2.CATEGORY_PRODUCT,
                UserInvestigationDomainV2.ACTIVITY_PROMOTION,
                UserInvestigationDomainV2.MARKETING,
                UserInvestigationDomainV2.AUDIENCE,
            ),
        )

    if assessment.pattern == ChangeConcentrationPatternV2.DOMINANT:
        assert next_level is not None
        next_label = _level_label_v2(next_level)
        leader = assessment.leader_member_label or "当前领先成员"
        share_text = (
            f"，占净变化 {assessment.leader_share * 100:.2f}%"
            if assessment.leader_share is not None
            else ""
        )

        return GeographyBranchDecisionV2(
            decision=GeographyBranchDecisionTypeV2.CONTINUE_INVESTIGATION,
            reason=GeographyBranchDecisionReasonV2.DOMINANT_FOCUS,
            current_level=current_level,
            next_investigation_level=next_level,
            summary=(
                f"当前{current_label}变化已经形成明确优先焦点，"
                f"可以继续到{next_label}调查。"
            ),
            detail=(
                f"{leader}是当前明确领先的数值变化来源{share_text}；"
                "下一层仍会保持原 Requested Scope，并只使用 server-trusted Focus。"
            ),
        )

    assert next_level is not None
    next_label = _level_label_v2(next_level)
    leader = assessment.leader_member_label
    share = assessment.leader_share

    if leader is not None and share is not None:
        leader_clause = (
            f"{leader}贡献最高，为 {share * 100:.2f}%，"
            "但当前证据不足以支持系统只围绕它继续调查。"
        )
    else:
        leader_clause = "当前没有形成足以支持单一优先焦点的成员。"

    return GeographyBranchDecisionV2(
        decision=GeographyBranchDecisionTypeV2.STOP_INVESTIGATION,
        reason=GeographyBranchDecisionReasonV2.NO_DOMINANT_GEOGRAPHY,
        current_level=current_level,
        exploration_available=True,
        exploration_level=next_level,
        recommended_next_domains=(
            UserInvestigationDomainV2.CATEGORY_PRODUCT,
            UserInvestigationDomainV2.ACTIVITY_PROMOTION,
            UserInvestigationDomainV2.MARKETING,
            UserInvestigationDomainV2.AUDIENCE,
        ),
        summary=(
            f"当前{current_label}变化较分散，没有一个{current_label}"
            "足以成为优先下钻对象。"
        ),
        detail=(
            f"{leader_clause}系统建议换一个业务维度继续调查。"
            f"如果你仍希望查看{next_label}数据，可以进入探索性查看；"
            "探索结果不代表系统推荐，也不会改变 Investigation Budget。"
        ),
    )
