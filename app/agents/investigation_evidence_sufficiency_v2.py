from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.agents.investigation_step_assessment_v2 import (
    ChangeConcentrationPatternV2,
    InvestigationStepAssessmentV2,
)


class InvestigationEvidenceSufficiencyV2(str, Enum):
    CONCLUSIVE = "conclusive"
    DIRECTIONAL = "directional"
    INCONCLUSIVE_ACTIONABLE = "inconclusive_actionable"
    BLOCKED = "blocked"


class InvestigationBudgetStageV2(str, Enum):
    WITHIN_SOFT_BUDGET = "within_soft_budget"
    SOFT_BUDGET_REACHED = "soft_budget_reached"
    HARD_CAP_REACHED = "hard_cap_reached"


class InvestigationBudgetExtensionPolicyV2(BaseModel):
    """
    Day93 Investigation Budget Policy。

    soft_budget_steps:
        默认成本预算。达到后必须停下来向用户汇报，
        不能自动继续。

    hard_cap_steps:
        当前 Session 的安全上限。即使用户愿意继续，
        也不能超过该上限。

    extension_chunk_steps:
        一次建议追加的步数，不代表这些步数一定能得到结论。
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    policy_version: str = "day93_investigation_budget_extension_v2_0"
    soft_budget_steps: int = Field(default=2, ge=1)
    hard_cap_steps: int = Field(default=5, ge=1)
    extension_chunk_steps: int = Field(default=2, ge=1)

    @model_validator(mode="after")
    def validate_policy(
        self,
    ) -> "InvestigationBudgetExtensionPolicyV2":
        if self.hard_cap_steps < self.soft_budget_steps:
            raise ValueError(
                "hard_cap_steps 不能小于 soft_budget_steps。"
            )
        return self


class InvestigationEvidenceStatusV2(BaseModel):
    """
    把“证据是否够”与“步数是否用完”拆开。

    该合同不负责执行下一步，只负责告诉 Runtime / UI：
    - 当前证据到了什么程度；
    - 当前只是阶段性结论还是已经可以结束；
    - 是否建议用户追加调查预算。
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    policy_version: str
    status: InvestigationEvidenceSufficiencyV2
    budget_stage: InvestigationBudgetStageV2

    stage_conclusion: str
    unresolved_boundary: tuple[str, ...]
    next_action_recommendation: str | None = None

    extension_recommended: bool
    suggested_additional_steps: int = Field(ge=0)
    hard_cap_reached: bool

    @model_validator(mode="after")
    def validate_status(
        self,
    ) -> "InvestigationEvidenceStatusV2":
        if not self.stage_conclusion.strip():
            raise ValueError("stage_conclusion 不能为空。")

        if self.extension_recommended:
            if self.suggested_additional_steps <= 0:
                raise ValueError(
                    "建议追加预算时 suggested_additional_steps 必须 > 0。"
                )
            if self.hard_cap_reached:
                raise ValueError(
                    "达到 hard cap 后不能再建议追加预算。"
                )
        elif self.suggested_additional_steps != 0:
            raise ValueError(
                "不建议追加预算时 suggested_additional_steps 必须为 0。"
            )

        if (
            self.status == InvestigationEvidenceSufficiencyV2.CONCLUSIVE
            and self.extension_recommended
        ):
            raise ValueError(
                "CONCLUSIVE 状态不应继续建议追加调查预算。"
            )

        return self


DEFAULT_INVESTIGATION_BUDGET_EXTENSION_POLICY_V2 = (
    InvestigationBudgetExtensionPolicyV2()
)


def _budget_stage_v2(
    *,
    steps_used: int,
    policy: InvestigationBudgetExtensionPolicyV2,
) -> InvestigationBudgetStageV2:
    if steps_used >= policy.hard_cap_steps:
        return InvestigationBudgetStageV2.HARD_CAP_REACHED

    if steps_used >= policy.soft_budget_steps:
        return InvestigationBudgetStageV2.SOFT_BUDGET_REACHED

    return InvestigationBudgetStageV2.WITHIN_SOFT_BUDGET


def assess_investigation_evidence_sufficiency_v2(
    *,
    steps_used: int,
    assessment: InvestigationStepAssessmentV2 | None,
    has_legal_next_action: bool,
    explicit_evidence_sufficient: bool = False,
    blocked_reason: str | None = None,
    policy: InvestigationBudgetExtensionPolicyV2 = (
        DEFAULT_INVESTIGATION_BUDGET_EXTENSION_POLICY_V2
    ),
) -> InvestigationEvidenceStatusV2:
    if steps_used < 0:
        raise ValueError("steps_used 不能为负数。")

    budget_stage = _budget_stage_v2(
        steps_used=steps_used,
        policy=policy,
    )
    hard_cap_reached = (
        budget_stage == InvestigationBudgetStageV2.HARD_CAP_REACHED
    )

    if blocked_reason is not None:
        reason = blocked_reason.strip()
        if not reason:
            raise ValueError("blocked_reason 不能为空字符串。")

        return InvestigationEvidenceStatusV2(
            policy_version=policy.policy_version,
            status=InvestigationEvidenceSufficiencyV2.BLOCKED,
            budget_stage=budget_stage,
            stage_conclusion=(
                "当前调查无法继续形成新的受治理证据。"
            ),
            unresolved_boundary=(reason,),
            next_action_recommendation=None,
            extension_recommended=False,
            suggested_additional_steps=0,
            hard_cap_reached=hard_cap_reached,
        )

    if explicit_evidence_sufficient:
        conclusion = (
            assessment.conclusion
            if assessment is not None
            else "当前证据已经满足本次调查问题的既定结论标准。"
        )

        return InvestigationEvidenceStatusV2(
            policy_version=policy.policy_version,
            status=InvestigationEvidenceSufficiencyV2.CONCLUSIVE,
            budget_stage=budget_stage,
            stage_conclusion=conclusion,
            unresolved_boundary=(),
            next_action_recommendation=None,
            extension_recommended=False,
            suggested_additional_steps=0,
            hard_cap_reached=hard_cap_reached,
        )

    if assessment is None:
        status = (
            InvestigationEvidenceSufficiencyV2.INCONCLUSIVE_ACTIONABLE
            if has_legal_next_action
            else InvestigationEvidenceSufficiencyV2.BLOCKED
        )
        conclusion = (
            "当前已执行调查，但还没有形成可解释的变化结构。"
        )
        unresolved = (
            "现有证据不足以形成业务原因结论。",
        )
        next_recommendation = (
            "继续执行一个合法调查方向，补充新的受治理证据。"
            if has_legal_next_action
            else None
        )
    else:
        if assessment.pattern in {
            ChangeConcentrationPatternV2.DOMINANT,
            ChangeConcentrationPatternV2.LEADING_NOT_DOMINANT,
        }:
            status = InvestigationEvidenceSufficiencyV2.DIRECTIONAL
        else:
            status = (
                InvestigationEvidenceSufficiencyV2
                .INCONCLUSIVE_ACTIONABLE
            )

        conclusion = assessment.conclusion
        unresolved = assessment.cannot_confirm
        next_recommendation = assessment.next_step_recommendation

    extension_recommended = False
    suggested_additional_steps = 0

    if (
        status
        not in {
            InvestigationEvidenceSufficiencyV2.CONCLUSIVE,
            InvestigationEvidenceSufficiencyV2.BLOCKED,
        }
        and budget_stage
        == InvestigationBudgetStageV2.SOFT_BUDGET_REACHED
        and has_legal_next_action
        and not hard_cap_reached
    ):
        remaining_capacity = policy.hard_cap_steps - steps_used
        suggested_additional_steps = min(
            policy.extension_chunk_steps,
            remaining_capacity,
        )
        extension_recommended = suggested_additional_steps > 0

    return InvestigationEvidenceStatusV2(
        policy_version=policy.policy_version,
        status=status,
        budget_stage=budget_stage,
        stage_conclusion=conclusion,
        unresolved_boundary=tuple(unresolved),
        next_action_recommendation=next_recommendation,
        extension_recommended=extension_recommended,
        suggested_additional_steps=suggested_additional_steps,
        hard_cap_reached=hard_cap_reached,
    )
