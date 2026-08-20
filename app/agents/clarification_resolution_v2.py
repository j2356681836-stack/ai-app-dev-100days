from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, model_validator

from app.agents.investigation_planner_v2 import (
    ClarificationRequirementV2,
    InvestigationStateV2,
    PlannerDecisionTypeV2,
    PlannerDecisionV2,
    PlannerProposalV2,
    validate_planner_proposal_v2,
)


CLARIFICATION_RESOLUTION_VERSION = (
    "day89_clarification_resolution_v2_0"
)

DAY89_DIRECTION_REQUIREMENT_SOURCE = (
    "day89_investigation_direction_gate_v2"
)
DAY89_DIRECTION_REQUIREMENT_REASON = (
    "user must choose one approved investigation direction "
    "before tool execution"
)


class ClarificationResolutionStatusV2(str, Enum):
    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"
    CONTRACT_MISMATCH = "contract_mismatch"


class ClarificationChoiceV2(BaseModel):
    """
    一个 server-owned clarification 选项。

    choice_id 是 UI 可以回传的稳定机器值；
    selected_action_id 必须指向当前 InvestigationStateV2 中
    已经经过授权/范围过滤的 available action。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    choice_id: str
    display_label: str
    selected_action_id: str

    @model_validator(mode="after")
    def validate_choice(self) -> "ClarificationChoiceV2":
        for field_name, value in (
            ("choice_id", self.choice_id),
            ("display_label", self.display_label),
            ("selected_action_id", self.selected_action_id),
        ):
            if not value.strip():
                raise ValueError(
                    f"{field_name} cannot be empty."
                )
        return self


class ClarificationResolutionContractV2(BaseModel):
    """
    一个精确绑定 trusted ClarificationRequirementV2 的 Resolver Contract。

    Day89 不做通用自然语言猜测：
    - requirement source/reason 必须精确匹配；
    - choice_id 必须来自 server-owned choices；
    - choice 只能收窄到当前已经合法的 action；
    - 不能新增 action / arguments / metric / scope / permission。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    contract_version: str = CLARIFICATION_RESOLUTION_VERSION
    contract_id: str
    requirement_source: str
    requirement_reason: str
    choices: tuple[ClarificationChoiceV2, ...]

    @model_validator(mode="after")
    def validate_contract(
        self,
    ) -> "ClarificationResolutionContractV2":
        for field_name, value in (
            ("contract_id", self.contract_id),
            ("requirement_source", self.requirement_source),
            ("requirement_reason", self.requirement_reason),
        ):
            if not value.strip():
                raise ValueError(
                    f"{field_name} cannot be empty."
                )

        if len(self.choices) < 2:
            raise ValueError(
                "Clarification Resolution Contract 至少需要两个明确选项。"
            )

        choice_ids = [item.choice_id for item in self.choices]
        if len(choice_ids) != len(set(choice_ids)):
            raise ValueError("choice_id 不能重复。")

        action_ids = [
            item.selected_action_id
            for item in self.choices
        ]
        if len(action_ids) != len(set(action_ids)):
            raise ValueError(
                "不同 clarification choice 不能映射到同一 action_id。"
            )

        return self


class ClarificationResponseV2(BaseModel):
    """
    用户对 trusted choice 的显式选择。

    第一版故意不接受任意 free text；避免用 LLM/模糊匹配
    猜测用户是否真正解决了 prerequisite。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    choice_id: str

    @model_validator(mode="after")
    def validate_response(self) -> "ClarificationResponseV2":
        if not self.choice_id.strip():
            raise ValueError("choice_id cannot be empty.")
        return self


class ClarificationResolutionResultV2(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    status: ClarificationResolutionStatusV2
    contract_id: str
    selected_choice_id: str | None = None
    resolved_state: InvestigationStateV2 | None = None
    detail: str

    @model_validator(mode="after")
    def validate_result(
        self,
    ) -> "ClarificationResolutionResultV2":
        if not self.contract_id.strip():
            raise ValueError("contract_id cannot be empty.")
        if not self.detail.strip():
            raise ValueError("detail cannot be empty.")

        if self.status == ClarificationResolutionStatusV2.RESOLVED:
            if self.selected_choice_id is None:
                raise ValueError(
                    "RESOLVED 必须包含 selected_choice_id。"
                )
            if self.resolved_state is None:
                raise ValueError(
                    "RESOLVED 必须返回 resolved_state。"
                )
            if (
                self.resolved_state.clarification_requirement
                is not None
            ):
                raise ValueError(
                    "RESOLVED state 必须清除已解决的 clarification requirement。"
                )
        else:
            if self.resolved_state is not None:
                raise ValueError(
                    "非 RESOLVED 不能释放修改后的 InvestigationState。"
                )

        return self


def build_day89_direction_clarification_requirement_v2(
) -> ClarificationRequirementV2:
    """
    Day89 Runtime HITL 的正式“调查方向选择” prerequisite。
    """

    return ClarificationRequirementV2(
        source=DAY89_DIRECTION_REQUIREMENT_SOURCE,
        reason=DAY89_DIRECTION_REQUIREMENT_REASON,
    )


def build_day89_direction_resolution_contract_v2(
) -> ClarificationResolutionContractV2:
    """
    第一版只允许用户在两个已批准调查方向中显式选择：
    Region / Category。

    这里声明的是 workflow choice，不是新的 authorization。
    最终 Resolver 仍会校验这些 action_id 当前是否真实存在于
    InvestigationStateV2.available_actions。
    """

    return ClarificationResolutionContractV2(
        contract_id="day89_investigation_direction_choice_v2",
        requirement_source=DAY89_DIRECTION_REQUIREMENT_SOURCE,
        requirement_reason=DAY89_DIRECTION_REQUIREMENT_REASON,
        choices=(
            ClarificationChoiceV2(
                choice_id="region",
                display_label="先检查区域维度",
                selected_action_id="drill_region",
            ),
            ClarificationChoiceV2(
                choice_id="category",
                display_label="先检查品类维度",
                selected_action_id="drill_category",
            ),
        ),
    )


def resolve_clarification_response_v2(
    *,
    state: InvestigationStateV2,
    contract: ClarificationResolutionContractV2,
    response: ClarificationResponseV2,
) -> ClarificationResolutionResultV2:
    """
    确定性解除一个 trusted clarification prerequisite。

    Fail-closed rules：
    1. 当前必须真的存在 clarification requirement；
    2. source/reason 必须与 contract 精确绑定；
    3. choice_id 必须来自 contract；
    4. choice 对应 action 必须已经存在于当前 available_actions；
    5. 成功时只把 available_actions 收窄到用户选择的现有 action，
       其他 insight / completed actions / prebound Tool Contract 全部保持原样；
    6. 不解析 free text，不调用 LLM，不修改 metric/time/scope/auth。
    """

    requirement = state.clarification_requirement

    if requirement is None:
        return ClarificationResolutionResultV2(
            status=(
                ClarificationResolutionStatusV2
                .CONTRACT_MISMATCH
            ),
            contract_id=contract.contract_id,
            detail=(
                "当前 InvestigationState 没有 unresolved "
                "clarification requirement。"
            ),
        )

    if (
        requirement.source != contract.requirement_source
        or requirement.reason != contract.requirement_reason
    ):
        return ClarificationResolutionResultV2(
            status=(
                ClarificationResolutionStatusV2
                .CONTRACT_MISMATCH
            ),
            contract_id=contract.contract_id,
            detail=(
                "当前 trusted clarification requirement "
                "与 Resolution Contract 不匹配；保持 Tool blocked。"
            ),
        )

    choices = {
        item.choice_id: item
        for item in contract.choices
    }
    choice = choices.get(response.choice_id)

    if choice is None:
        return ClarificationResolutionResultV2(
            status=ClarificationResolutionStatusV2.UNRESOLVED,
            contract_id=contract.contract_id,
            detail=(
                "用户响应不是当前 Resolution Contract "
                "允许的 choice_id；clarification 仍未解决。"
            ),
        )

    actions_by_id = {
        action.action_id: action
        for action in state.available_actions
    }
    selected_action = actions_by_id.get(
        choice.selected_action_id
    )

    if selected_action is None:
        return ClarificationResolutionResultV2(
            status=(
                ClarificationResolutionStatusV2
                .CONTRACT_MISMATCH
            ),
            contract_id=contract.contract_id,
            detail=(
                "Resolution Contract 选择的 action 当前并不在 "
                "authorization/scope-filtered available_actions 中；"
                "禁止通过 clarification 扩展 Tool 权限。"
            ),
        )

    resolved_state = InvestigationStateV2(
        insight=state.insight,
        completed_action_ids=state.completed_action_ids,
        available_actions=(selected_action,),
        clarification_requirement=None,
    )

    return ClarificationResolutionResultV2(
        status=ClarificationResolutionStatusV2.RESOLVED,
        contract_id=contract.contract_id,
        selected_choice_id=choice.choice_id,
        resolved_state=resolved_state,
        detail=(
            "Clarification 已由 deterministic server-owned contract "
            "解决；Planner 只能看到用户选择后保留下来的合法 action。"
        ),
    )

def plan_day89_direction_clarification_v2(
    state: InvestigationStateV2,
) -> PlannerDecisionV2:
    """
    Direction Gate 的 deterministic CLARIFY adapter。

    这里不让 LLM 重新判断“要不要澄清”：
    trusted requirement 已经存在，所以只能生成 CLARIFY Decision。
    """

    requirement = state.clarification_requirement

    if requirement is None:
        raise ValueError(
            "Direction Clarification Planner 需要 unresolved requirement。"
        )

    if (
        requirement.source
        != DAY89_DIRECTION_REQUIREMENT_SOURCE
        or requirement.reason
        != DAY89_DIRECTION_REQUIREMENT_REASON
    ):
        raise ValueError(
            "Direction Clarification Planner 不能处理其他 prerequisite。"
        )

    return validate_planner_proposal_v2(
        state=state,
        proposal=PlannerProposalV2(
            decision_type=PlannerDecisionTypeV2.CLARIFY,
            clarification_prompt=(
                "请选择首个受控调查方向：区域维度或品类维度。"
            ),
            rationale=(
                "当前存在两个已经批准的调查方向；"
                "在用户明确选择前，不执行 Investigation Tool。"
            ),
        ),
    )


def plan_day89_resolved_single_action_v2(
    state: InvestigationStateV2,
) -> PlannerDecisionV2:
    """
    Resolver 成功后的 deterministic SELECT_TOOL adapter。

    用户已经通过 server-owned choice 明确选择下一 Action；
    此时无需再让 LLM 二次覆盖用户选择。
    """

    if state.clarification_requirement is not None:
        raise ValueError(
            "Resolved Action Planner 不能绕过 unresolved clarification。"
        )

    if len(state.available_actions) != 1:
        raise ValueError(
            "Resolved Action Planner 需要恰好一个合法 available action。"
        )

    if not state.insight.evidence:
        raise ValueError(
            "Resolved Action Planner 需要至少一条 trusted evidence。"
        )

    action = state.available_actions[0]
    supporting_id = state.insight.evidence[-1].evidence_id

    return validate_planner_proposal_v2(
        state=state,
        proposal=PlannerProposalV2(
            decision_type=PlannerDecisionTypeV2.SELECT_TOOL,
            action_id=action.action_id,
            rationale=(
                "用户已通过 deterministic clarification resolver "
                "明确选择该受控调查方向。"
            ),
            supporting_evidence_ids=(supporting_id,),
        ),
    )
