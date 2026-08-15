from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, model_validator

from app.agents.investigation_contracts_v2 import (
    AnalysisModeV2,
    InsightContractV2,
    ToolContractV2,
)


class PlannerDecisionTypeV2(str, Enum):
    SELECT_TOOL = "select_tool"
    CLARIFY = "clarify"


class ClarificationRequirementV2(BaseModel):
    """
    An unresolved prerequisite produced by an upstream trusted layer.

    Day85 does not rediscover semantic ambiguity inside the planner. It only
    carries a structured reason that requires user clarification before any
    tool action may be selected.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str
    reason: str

    @model_validator(mode="after")
    def validate_requirement(self) -> "ClarificationRequirementV2":
        if not self.source.strip():
            raise ValueError("clarification source cannot be empty.")
        if not self.reason.strip():
            raise ValueError("clarification reason cannot be empty.")
        return self


class BoundToolArgumentV2(BaseModel):
    """
    One system-prebound tool argument.

    The model does not supply arbitrary arguments in Day85 Step A. It chooses
    one already-approved action_id. This keeps model choice separate from
    trusted parameter construction.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    value: str

    @model_validator(mode="after")
    def validate_argument(self) -> "BoundToolArgumentV2":
        if not self.name.strip():
            raise ValueError("argument name cannot be empty.")
        if not self.value.strip():
            raise ValueError("argument value cannot be empty.")
        return self


class AvailableInvestigationActionV2(BaseModel):
    """
    One authorization/scope-filtered action exposed to the planner.

    The action carries a trusted ToolContractV2 plus prebound arguments. The
    model can select the action_id, but cannot replace the tool contract or
    inject raw SQL / metric formulas.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    action_id: str
    tool_contract: ToolContractV2
    arguments: tuple[BoundToolArgumentV2, ...] = ()

    @model_validator(mode="after")
    def validate_action(self) -> "AvailableInvestigationActionV2":
        if not self.action_id.strip():
            raise ValueError("action_id cannot be empty.")

        names = [argument.name for argument in self.arguments]
        if len(names) != len(set(names)):
            raise ValueError(
                "Available action arguments cannot contain duplicate names."
            )

        return self


class InvestigationStateV2(BaseModel):
    """
    Minimal Day85 planner state.

    It records what the investigation already knows, what exact action ids have
    already been executed, what actions remain legally available, and whether
    an upstream prerequisite still requires clarification.

    Day86 will add loop/recovery/stop-budget behavior. This contract does not.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    insight: InsightContractV2
    completed_action_ids: tuple[str, ...] = ()
    available_actions: tuple[AvailableInvestigationActionV2, ...] = ()
    clarification_requirement: ClarificationRequirementV2 | None = None

    @model_validator(mode="after")
    def validate_state(self) -> "InvestigationStateV2":
        if self.insight.analysis_mode not in {
            AnalysisModeV2.DIAGNOSTIC,
            AnalysisModeV2.INVESTIGATION,
        }:
            raise ValueError(
                "Planner state requires DIAGNOSTIC or INVESTIGATION insight."
            )

        if any(
            not action_id.strip()
            for action_id in self.completed_action_ids
        ):
            raise ValueError(
                "completed_action_ids cannot contain blank values."
            )

        if len(set(self.completed_action_ids)) != len(
            self.completed_action_ids
        ):
            raise ValueError(
                "completed_action_ids cannot contain duplicates."
            )

        action_ids = [action.action_id for action in self.available_actions]
        if len(action_ids) != len(set(action_ids)):
            raise ValueError("available action_id values must be unique.")

        repeated = set(action_ids) & set(self.completed_action_ids)
        if repeated:
            raise ValueError(
                "Completed actions cannot remain available: "
                f"{sorted(repeated)}"
            )

        return self


class PlannerProposalV2(BaseModel):
    """
    Model-proposed next step.

    The proposal deliberately contains only an action_id for tool selection.
    It cannot carry raw SQL, metric formulas, or model-invented tool arguments.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    decision_type: PlannerDecisionTypeV2
    action_id: str | None = None
    clarification_prompt: str | None = None
    rationale: str
    supporting_evidence_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_proposal(self) -> "PlannerProposalV2":
        if not self.rationale.strip():
            raise ValueError("planner rationale cannot be empty.")

        if any(
            not evidence_id.strip()
            for evidence_id in self.supporting_evidence_ids
        ):
            raise ValueError(
                "supporting_evidence_ids cannot contain blank values."
            )

        if len(set(self.supporting_evidence_ids)) != len(
            self.supporting_evidence_ids
        ):
            raise ValueError(
                "supporting_evidence_ids cannot contain duplicates."
            )

        if self.decision_type == PlannerDecisionTypeV2.SELECT_TOOL:
            if self.action_id is None or not self.action_id.strip():
                raise ValueError("SELECT_TOOL requires action_id.")
            if self.clarification_prompt is not None:
                raise ValueError(
                    "SELECT_TOOL cannot carry clarification_prompt."
                )
            if not self.supporting_evidence_ids:
                raise ValueError(
                    "SELECT_TOOL requires supporting evidence."
                )

        if self.decision_type == PlannerDecisionTypeV2.CLARIFY:
            if self.action_id is not None:
                raise ValueError("CLARIFY cannot carry action_id.")
            if (
                self.clarification_prompt is None
                or not self.clarification_prompt.strip()
            ):
                raise ValueError(
                    "CLARIFY requires clarification_prompt."
                )

        return self


class PlannerDecisionV2(BaseModel):
    """Validated Day85 next-step decision."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    decision_type: PlannerDecisionTypeV2
    selected_action: AvailableInvestigationActionV2 | None = None
    clarification_prompt: str | None = None
    rationale: str
    supporting_evidence_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_decision(self) -> "PlannerDecisionV2":
        if not self.rationale.strip():
            raise ValueError("planner decision rationale cannot be empty.")

        if self.decision_type == PlannerDecisionTypeV2.SELECT_TOOL:
            if self.selected_action is None:
                raise ValueError(
                    "SELECT_TOOL decision requires selected_action."
                )
            if self.clarification_prompt is not None:
                raise ValueError(
                    "SELECT_TOOL decision cannot carry clarification_prompt."
                )

        if self.decision_type == PlannerDecisionTypeV2.CLARIFY:
            if self.selected_action is not None:
                raise ValueError(
                    "CLARIFY decision cannot carry selected_action."
                )
            if (
                self.clarification_prompt is None
                or not self.clarification_prompt.strip()
            ):
                raise ValueError(
                    "CLARIFY decision requires clarification_prompt."
                )

        return self


def validate_planner_proposal_v2(
    *,
    state: InvestigationStateV2,
    proposal: PlannerProposalV2,
) -> PlannerDecisionV2:
    """
    Constrain one model proposal against the trusted Day85 state.

    Rules:
    - unresolved prerequisite forces CLARIFY;
    - CLARIFY is not allowed when no prerequisite is unresolved;
    - SELECT_TOOL must name an action in the already-filtered action set;
    - the model cannot alter prebound arguments or the ToolContractV2;
    - SELECT_TOOL evidence ids must exist in the current Insight evidence.

    Invalid proposals fail closed with ValueError. Retry/recovery belongs to
    Day86 and is intentionally not implemented here.
    """

    if state.clarification_requirement is not None:
        if proposal.decision_type != PlannerDecisionTypeV2.CLARIFY:
            raise ValueError(
                "Unresolved prerequisite requires CLARIFY before tool selection."
            )

        return PlannerDecisionV2(
            decision_type=PlannerDecisionTypeV2.CLARIFY,
            selected_action=None,
            clarification_prompt=proposal.clarification_prompt,
            rationale=proposal.rationale,
            supporting_evidence_ids=proposal.supporting_evidence_ids,
        )

    if proposal.decision_type == PlannerDecisionTypeV2.CLARIFY:
        raise ValueError(
            "Planner cannot invent clarification when no trusted prerequisite "
            "requires it."
        )

    actions_by_id = {
        action.action_id: action
        for action in state.available_actions
    }

    selected_action = actions_by_id.get(proposal.action_id or "")
    if selected_action is None:
        raise ValueError(
            "Planner selected an action outside available_actions."
        )

    available_evidence_ids = {
        evidence.evidence_id
        for evidence in state.insight.evidence
    }
    missing_evidence = (
        set(proposal.supporting_evidence_ids)
        - available_evidence_ids
    )
    if missing_evidence:
        raise ValueError(
            "Planner proposal references unknown evidence_ids: "
            f"{sorted(missing_evidence)}"
        )

    return PlannerDecisionV2(
        decision_type=PlannerDecisionTypeV2.SELECT_TOOL,
        selected_action=selected_action,
        clarification_prompt=None,
        rationale=proposal.rationale,
        supporting_evidence_ids=proposal.supporting_evidence_ids,
    )
