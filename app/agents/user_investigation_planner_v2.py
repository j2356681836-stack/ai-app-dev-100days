from __future__ import annotations

from app.agents.investigation_planner_v2 import (
    InvestigationStateV2,
    PlannerDecisionTypeV2,
    PlannerDecisionV2,
    PlannerProposalV2,
    validate_planner_proposal_v2,
)


def plan_user_selected_investigation_action_v2(
    *,
    state: InvestigationStateV2,
    action_id: str,
    rationale: str,
) -> PlannerDecisionV2:
    """
    USER-owned Business Intent -> one validated server-owned Action.

    用户决定“想调查什么”，但不能：
    - 注入 SQL；
    - 修改 Tool Contract；
    - 修改预绑定参数；
    - 选择 available_actions 之外的 Action。

    supporting evidence 仍从当前 trusted Insight 中取得。
    """

    if not action_id.strip():
        raise ValueError("action_id 不能为空。")

    if not rationale.strip():
        raise ValueError("rationale 不能为空。")

    evidence_ids = tuple(
        item.evidence_id
        for item in state.insight.evidence
    )

    if not evidence_ids:
        raise ValueError(
            "User-selected Investigation 必须从已有 trusted Evidence 启动。"
        )

    return validate_planner_proposal_v2(
        state=state,
        proposal=PlannerProposalV2(
            decision_type=PlannerDecisionTypeV2.SELECT_TOOL,
            action_id=action_id,
            rationale=rationale,
            supporting_evidence_ids=evidence_ids,
        ),
    )
