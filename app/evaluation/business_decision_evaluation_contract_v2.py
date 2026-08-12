from __future__ import annotations

from enum import Enum, IntEnum

from pydantic import BaseModel, ConfigDict, model_validator


class EvaluationScoreV2(IntEnum):
    FAIL = 0
    PARTIAL = 1
    PASS = 2


class BusinessDecisionOverallStatusV2(str, Enum):
    PASS = "pass"
    PARTIAL = "partial"
    FAIL = "fail"


class EvaluationDimensionResultV2(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    score: EvaluationScoreV2
    reason: str
    evidence_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_dimension(
        self,
    ) -> "EvaluationDimensionResultV2":
        if not self.reason.strip():
            raise ValueError(
                "Evaluation reason cannot be empty."
            )

        if any(
            not evidence_id.strip()
            for evidence_id in self.evidence_ids
        ):
            raise ValueError(
                "evidence_ids cannot contain blank values."
            )

        if (
            len(set(self.evidence_ids))
            != len(self.evidence_ids)
        ):
            raise ValueError(
                "evidence_ids cannot contain duplicates."
            )

        return self


def derive_overall_status_v2(
    *,
    factual_correctness: EvaluationDimensionResultV2,
    diagnostic_relevance: EvaluationDimensionResultV2,
    prioritization: EvaluationDimensionResultV2,
    actionability: EvaluationDimensionResultV2,
    epistemic_discipline: EvaluationDimensionResultV2,
    evidence_sufficiency: EvaluationDimensionResultV2,
) -> BusinessDecisionOverallStatusV2:
    """
    Day82 deterministic status rule.

    Hard gates:
    - factual_correctness FAIL -> overall FAIL
    - epistemic_discipline FAIL -> overall FAIL

    evidence_sufficiency FAIL prevents a full PASS, but does not
    automatically become a hard FAIL in this first contract version.
    """

    if (
        factual_correctness.score
        == EvaluationScoreV2.FAIL
    ):
        return BusinessDecisionOverallStatusV2.FAIL

    if (
        epistemic_discipline.score
        == EvaluationScoreV2.FAIL
    ):
        return BusinessDecisionOverallStatusV2.FAIL

    dimensions = (
        factual_correctness,
        diagnostic_relevance,
        prioritization,
        actionability,
        epistemic_discipline,
        evidence_sufficiency,
    )

    if all(
        item.score == EvaluationScoreV2.PASS
        for item in dimensions
    ):
        return BusinessDecisionOverallStatusV2.PASS

    return BusinessDecisionOverallStatusV2.PARTIAL


class BusinessDecisionEvaluationResultV2(BaseModel):
    """
    Phase4 business decision quality evaluation contract.

    This contract defines the six Day82 quality dimensions and
    verifies the deterministic overall hard-gate rule.

    It does not implement an automated judge or human review.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    factual_correctness: EvaluationDimensionResultV2
    diagnostic_relevance: EvaluationDimensionResultV2
    prioritization: EvaluationDimensionResultV2
    actionability: EvaluationDimensionResultV2
    epistemic_discipline: EvaluationDimensionResultV2
    evidence_sufficiency: EvaluationDimensionResultV2

    overall_status: BusinessDecisionOverallStatusV2

    @model_validator(mode="after")
    def validate_overall_status(
        self,
    ) -> "BusinessDecisionEvaluationResultV2":
        expected = derive_overall_status_v2(
            factual_correctness=self.factual_correctness,
            diagnostic_relevance=self.diagnostic_relevance,
            prioritization=self.prioritization,
            actionability=self.actionability,
            epistemic_discipline=self.epistemic_discipline,
            evidence_sufficiency=self.evidence_sufficiency,
        )

        if self.overall_status != expected:
            raise ValueError(
                "overall_status does not match "
                "the Day82 deterministic evaluation rule."
            )

        return self
