from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, model_validator

from app.agents.contribution_pattern_assessment_v2 import (
    ContributionPatternAssessmentV2,
    ContributionPatternV2,
)


class InvestigationDecisionOwnerV2(str, Enum):
    SYSTEM = "system"
    USER = "user"


class InvestigationScopeStrategyV2(str, Enum):
    KEEP_REQUESTED_SCOPE = "keep_requested_scope"
    FOCUS_MEMBER = "focus_member"


class InvestigationNextDimensionV2(str, Enum):
    CATEGORY = "category"
    GEOGRAPHY = "geography"


class GeographyLevelV2(str, Enum):
    AREA = "area"
    PROVINCE = "province"
    CITY = "city"


class InvestigationFocusDimensionV2(str, Enum):
    CHANNEL = "channel"
    CATEGORY = "category"
    AREA = "area"
    PROVINCE = "province"
    CITY = "city"


class InvestigationRouteV2(BaseModel):
    """
    Day93 Investigation Route Contract。

    它回答的是：
    - 谁决定了这条调查路线；
    - 下一步看哪个业务维度；
    - 是否继续保持 Requested Scope；
    - 是否建立新的 Investigation Focus；
    - 如果进入 Geography，当前要看哪一层；
    - 这条路线由哪些 Evidence 支持。

    它不执行 Tool、不生成 SQL，也不修改 Authorized Scope。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    decision_owner: InvestigationDecisionOwnerV2
    scope_strategy: InvestigationScopeStrategyV2
    next_dimension: InvestigationNextDimensionV2

    geography_level: GeographyLevelV2 | None = None

    focus_dimension: InvestigationFocusDimensionV2 | None = None
    focus_member_key: str | None = None
    focus_member_label: str | None = None

    supporting_evidence_ids: tuple[str, ...]
    rationale: str

    @model_validator(mode="after")
    def validate_route(self) -> "InvestigationRouteV2":
        if not self.rationale.strip():
            raise ValueError("Investigation Route rationale 不能为空。")

        if not self.supporting_evidence_ids:
            raise ValueError(
                "Investigation Route 必须绑定 supporting evidence。"
            )

        if any(
            not evidence_id.strip()
            for evidence_id in self.supporting_evidence_ids
        ):
            raise ValueError(
                "supporting_evidence_ids 不能包含空值。"
            )

        if len(set(self.supporting_evidence_ids)) != len(
            self.supporting_evidence_ids
        ):
            raise ValueError(
                "supporting_evidence_ids 不能重复。"
            )

        if self.next_dimension == InvestigationNextDimensionV2.GEOGRAPHY:
            if self.geography_level is None:
                raise ValueError(
                    "Geography Route 必须显式声明 geography_level。"
                )
        elif self.geography_level is not None:
            raise ValueError(
                "非 Geography Route 不能携带 geography_level。"
            )

        focus_values = (
            self.focus_dimension,
            self.focus_member_key,
            self.focus_member_label,
        )

        if self.scope_strategy == InvestigationScopeStrategyV2.FOCUS_MEMBER:
            if any(value is None for value in focus_values):
                raise ValueError(
                    "FOCUS_MEMBER Route 必须完整提供 "
                    "focus_dimension / focus_member_key / focus_member_label。"
                )

            assert self.focus_member_key is not None
            assert self.focus_member_label is not None

            if not self.focus_member_key.strip():
                raise ValueError("focus_member_key 不能为空。")
            if not self.focus_member_label.strip():
                raise ValueError("focus_member_label 不能为空。")

        elif any(value is not None for value in focus_values):
            raise ValueError(
                "KEEP_REQUESTED_SCOPE Route 不能偷偷携带 Member Focus。"
            )

        return self


def build_system_route_from_channel_pattern_v2(
    *,
    assessment: ContributionPatternAssessmentV2,
    next_dimension: InvestigationNextDimensionV2,
    supporting_evidence_ids: tuple[str, ...],
    planner_rationale: str,
    geography_level: GeographyLevelV2 | None = None,
) -> InvestigationRouteV2:
    """
    根据已验证的 Channel Contribution Pattern
    建立 system-owned Route。

    关键安全规则：
    - DOMINANT 且 assessment 明确允许 auto focus：
      系统可建立 Channel Focus。
    - NEAR_TIE / DISTRIBUTED / UNAVAILABLE：
      系统不得自动锁定单一 Channel，
      必须保持原 Requested Scope。
    """

    if assessment.metric_name != "gmv":
        raise ValueError(
            "System Route 当前只接受 GMV Contribution Pattern。"
        )

    if assessment.dimension_name != "channel":
        raise ValueError(
            "System Route 当前只接受 Channel Contribution Pattern。"
        )

    if not planner_rationale.strip():
        raise ValueError("planner_rationale 不能为空。")

    if (
        assessment.pattern == ContributionPatternV2.DOMINANT
        and assessment.auto_member_focus_allowed
    ):
        if (
            assessment.leader_member_key is None
            or assessment.leader_member_label is None
        ):
            raise ValueError(
                "DOMINANT assessment 缺少可信 leader，不能建立 Focus。"
            )

        return InvestigationRouteV2(
            decision_owner=InvestigationDecisionOwnerV2.SYSTEM,
            scope_strategy=InvestigationScopeStrategyV2.FOCUS_MEMBER,
            next_dimension=next_dimension,
            geography_level=geography_level,
            focus_dimension=InvestigationFocusDimensionV2.CHANNEL,
            focus_member_key=assessment.leader_member_key,
            focus_member_label=assessment.leader_member_label,
            supporting_evidence_ids=supporting_evidence_ids,
            rationale=(
                f"{assessment.rationale} "
                f"Planner route rationale: {planner_rationale.strip()}"
            ),
        )

    return InvestigationRouteV2(
        decision_owner=InvestigationDecisionOwnerV2.SYSTEM,
        scope_strategy=(
            InvestigationScopeStrategyV2.KEEP_REQUESTED_SCOPE
        ),
        next_dimension=next_dimension,
        geography_level=geography_level,
        supporting_evidence_ids=supporting_evidence_ids,
        rationale=(
            f"{assessment.rationale} "
            f"Planner route rationale: {planner_rationale.strip()}"
        ),
    )


def build_user_selected_route_v2(
    *,
    next_dimension: InvestigationNextDimensionV2,
    supporting_evidence_ids: tuple[str, ...],
    geography_level: GeographyLevelV2 | None = None,
    focus_dimension: InvestigationFocusDimensionV2 | None = None,
    focus_member_key: str | None = None,
    focus_member_label: str | None = None,
) -> InvestigationRouteV2:
    """
    用户显式指定 Route。

    用户可以：
    - 只指定调查维度，保持 Requested Scope；
    - 或显式指定一个 Member Focus。

    这里仅记录 decision ownership。
    后续 Runtime 仍必须把 Focus 映射成 server-owned scope code，
    再走完整 Governance Boundary。
    """

    has_focus = any(
        value is not None
        for value in (
            focus_dimension,
            focus_member_key,
            focus_member_label,
        )
    )

    scope_strategy = (
        InvestigationScopeStrategyV2.FOCUS_MEMBER
        if has_focus
        else InvestigationScopeStrategyV2.KEEP_REQUESTED_SCOPE
    )

    if has_focus:
        rationale = (
            "用户明确指定调查范围与方向；系统只负责验证该 Route "
            "是否属于当前合法调查空间，并在 Governance Boundary 内执行。"
        )
    else:
        rationale = (
            "用户明确指定下一调查维度，但没有要求进一步收窄范围；"
            "继续保持原 Requested Scope。"
        )

    return InvestigationRouteV2(
        decision_owner=InvestigationDecisionOwnerV2.USER,
        scope_strategy=scope_strategy,
        next_dimension=next_dimension,
        geography_level=geography_level,
        focus_dimension=focus_dimension,
        focus_member_key=focus_member_key,
        focus_member_label=focus_member_label,
        supporting_evidence_ids=supporting_evidence_ids,
        rationale=rationale,
    )
