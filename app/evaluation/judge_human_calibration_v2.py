from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, model_validator

from app.evaluation.business_decision_evaluation_contract_v2 import (
    BusinessDecisionEvaluationResultV2,
    BusinessDecisionOverallStatusV2,
    EvaluationScoreV2,
)


class BusinessDecisionDimensionV2(str, Enum):
    FACTUAL_CORRECTNESS = "factual_correctness"
    DIAGNOSTIC_RELEVANCE = "diagnostic_relevance"
    PRIORITIZATION = "prioritization"
    ACTIONABILITY = "actionability"
    EPISTEMIC_DISCIPLINE = "epistemic_discipline"
    EVIDENCE_SUFFICIENCY = "evidence_sufficiency"


class JudgeHumanAgreementStatusV2(str, Enum):
    AGREEMENT = "agreement"
    DISAGREEMENT = "disagreement"


class HumanBusinessDecisionReviewV2(BaseModel):
    """
    Human Expert Proxy Review。

    Human Review 与 Judge 使用同一 Day82 六维合同，
    但 Human 不是通过修改 Judge 结果来“校正”；
    两份结果独立保存，再由 Calibration 层比较。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    case_id: str
    evaluation: BusinessDecisionEvaluationResultV2
    review_notes: str

    @model_validator(mode="after")
    def validate_review(
        self,
    ) -> "HumanBusinessDecisionReviewV2":
        if not self.case_id.strip():
            raise ValueError(
                "Human Review case_id 不能为空。"
            )

        if not self.review_notes.strip():
            raise ValueError(
                "Human Review 必须留下 review_notes。"
            )

        return self


class JudgeHumanDimensionComparisonV2(BaseModel):
    """
    单个 Business Decision 维度的 Judge ↔ Human 比较。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    dimension: BusinessDecisionDimensionV2
    judge_score: EvaluationScoreV2
    human_score: EvaluationScoreV2
    status: JudgeHumanAgreementStatusV2

    @model_validator(mode="after")
    def validate_comparison(
        self,
    ) -> "JudgeHumanDimensionComparisonV2":
        expected = (
            JudgeHumanAgreementStatusV2.AGREEMENT
            if self.judge_score == self.human_score
            else JudgeHumanAgreementStatusV2.DISAGREEMENT
        )

        if self.status != expected:
            raise ValueError(
                "Agreement status 必须由 Judge / Human score "
                "确定性推导。"
            )

        return self


class JudgeHumanCalibrationResultV2(BaseModel):
    """
    Judge ↔ Human Calibration 结果。

    disagreement 是评估数据，不自动判定“谁错了”。

    factual_correctness / epistemic_discipline 是 Day82 hard gate，
    因此这两个维度的 disagreement 被标记为 critical。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    case_id: str
    comparisons: tuple[
        JudgeHumanDimensionComparisonV2, ...
    ]

    agreement_count: int
    disagreement_count: int
    overall_status_agreement: bool

    critical_disagreement_dimensions: tuple[
        BusinessDecisionDimensionV2, ...
    ]

    requires_calibration_review: bool

    @model_validator(mode="after")
    def validate_calibration(
        self,
    ) -> "JudgeHumanCalibrationResultV2":
        expected_dimensions = set(
            BusinessDecisionDimensionV2
        )
        actual_dimensions = {
            item.dimension
            for item in self.comparisons
        }

        if actual_dimensions != expected_dimensions:
            raise ValueError(
                "Calibration 必须比较完整六个 Business Decision 维度。"
            )

        if (
            len(self.comparisons)
            != len(actual_dimensions)
        ):
            raise ValueError(
                "Calibration dimension 不能重复。"
            )

        actual_agreements = sum(
            item.status
            == JudgeHumanAgreementStatusV2.AGREEMENT
            for item in self.comparisons
        )

        actual_disagreements = (
            len(self.comparisons)
            - actual_agreements
        )

        if self.agreement_count != actual_agreements:
            raise ValueError(
                "agreement_count 与 comparisons 不一致。"
            )

        if self.disagreement_count != actual_disagreements:
            raise ValueError(
                "disagreement_count 与 comparisons 不一致。"
            )

        expected_review = (
            actual_disagreements > 0
            or not self.overall_status_agreement
        )

        if self.requires_calibration_review != expected_review:
            raise ValueError(
                "requires_calibration_review 必须由 disagreement "
                "确定性推导。"
            )

        expected_critical = tuple(
            item.dimension
            for item in self.comparisons
            if (
                item.status
                == JudgeHumanAgreementStatusV2.DISAGREEMENT
                and item.dimension
                in {
                    BusinessDecisionDimensionV2.FACTUAL_CORRECTNESS,
                    BusinessDecisionDimensionV2.EPISTEMIC_DISCIPLINE,
                }
            )
        )

        if (
            self.critical_disagreement_dimensions
            != expected_critical
        ):
            raise ValueError(
                "critical disagreement 必须只来自 hard-gate 维度。"
            )

        return self


_DIMENSION_ORDER = (
    BusinessDecisionDimensionV2.FACTUAL_CORRECTNESS,
    BusinessDecisionDimensionV2.DIAGNOSTIC_RELEVANCE,
    BusinessDecisionDimensionV2.PRIORITIZATION,
    BusinessDecisionDimensionV2.ACTIONABILITY,
    BusinessDecisionDimensionV2.EPISTEMIC_DISCIPLINE,
    BusinessDecisionDimensionV2.EVIDENCE_SUFFICIENCY,
)


def build_judge_human_calibration_v2(
    *,
    case_id: str,
    judge_evaluation: BusinessDecisionEvaluationResultV2,
    human_review: HumanBusinessDecisionReviewV2,
) -> JudgeHumanCalibrationResultV2:
    """
    独立比较 Judge 与 Human。

    本函数不修改任何一方的评分，也不自动把 Human 当作 ground truth。
    disagreement 后续需要检查：
    - Rubric 是否模糊；
    - Judge Context 是否缺失；
    - Judge reasoning 是否偏离；
    - Human 标准是否不一致；
    - Case / Evidence 是否本身含糊。
    """

    if human_review.case_id != case_id:
        raise ValueError(
            "Human Review case_id 与 Calibration case_id 不一致。"
        )

    comparisons: list[
        JudgeHumanDimensionComparisonV2
    ] = []

    for dimension in _DIMENSION_ORDER:
        judge_score = getattr(
            judge_evaluation,
            dimension.value,
        ).score
        human_score = getattr(
            human_review.evaluation,
            dimension.value,
        ).score

        status = (
            JudgeHumanAgreementStatusV2.AGREEMENT
            if judge_score == human_score
            else JudgeHumanAgreementStatusV2.DISAGREEMENT
        )

        comparisons.append(
            JudgeHumanDimensionComparisonV2(
                dimension=dimension,
                judge_score=judge_score,
                human_score=human_score,
                status=status,
            )
        )

    comparison_tuple = tuple(
        comparisons
    )

    disagreement_count = sum(
        item.status
        == JudgeHumanAgreementStatusV2.DISAGREEMENT
        for item in comparison_tuple
    )

    critical = tuple(
        item.dimension
        for item in comparison_tuple
        if (
            item.status
            == JudgeHumanAgreementStatusV2.DISAGREEMENT
            and item.dimension
            in {
                BusinessDecisionDimensionV2.FACTUAL_CORRECTNESS,
                BusinessDecisionDimensionV2.EPISTEMIC_DISCIPLINE,
            }
        )
    )

    overall_agreement = (
        judge_evaluation.overall_status
        == human_review.evaluation.overall_status
    )

    return JudgeHumanCalibrationResultV2(
        case_id=case_id,
        comparisons=comparison_tuple,
        agreement_count=(
            len(comparison_tuple)
            - disagreement_count
        ),
        disagreement_count=disagreement_count,
        overall_status_agreement=overall_agreement,
        critical_disagreement_dimensions=critical,
        requires_calibration_review=(
            disagreement_count > 0
            or not overall_agreement
        ),
    )
