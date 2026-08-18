from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, model_validator

from app.evaluation.business_decision_evaluation_contract_v2 import (
    BusinessDecisionEvaluationResultV2,
    EvaluationDimensionResultV2,
    EvaluationScoreV2,
    derive_overall_status_v2,
)
from app.evaluation.business_decision_rubric_v2 import (
    BUSINESS_DECISION_RUBRIC_V1_0,
    BUSINESS_DECISION_RUBRIC_V2_0,
)
from app.evaluation.judge_human_calibration_v2 import (
    BusinessDecisionDimensionV2,
    HumanBusinessDecisionReviewV2,
    JudgeHumanCalibrationResultV2,
    build_judge_human_calibration_v2,
)


class EvaluationProvenanceV2(BaseModel):
    """
    一次 Business Decision Evaluation 的最小 provenance。

    用来回答：
    - 哪个 Case；
    - 哪版 Rubric；
    - 哪版 Judge Prompt；
    - 哪个模型；
    - Human 以什么角色复核；
    - 什么时候评的。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    case_id: str
    rubric_version: str
    judge_prompt_version: str
    judge_model: str
    human_reviewer_role: str
    evaluated_at_utc: datetime

    @model_validator(mode="after")
    def validate_provenance(
        self,
    ) -> "EvaluationProvenanceV2":
        for field_name in (
            "case_id",
            "rubric_version",
            "judge_prompt_version",
            "judge_model",
            "human_reviewer_role",
        ):
            if not getattr(
                self,
                field_name,
            ).strip():
                raise ValueError(
                    f"{field_name} 不能为空。"
                )

        if self.evaluated_at_utc.tzinfo is None:
            raise ValueError(
                "evaluated_at_utc 必须包含 timezone。"
            )

        return self


class ObservedCalibrationEvidenceV2(BaseModel):
    """
    Day88 Live Judge ↔ Human Calibration Evidence。

    这是一条 observed evaluation evidence：
    - 不是 Fresh Generalization；
    - 不是长期模型稳定性证明；
    - 不修改历史 Judge 结果；
    - 可以作为新 Rubric 版本的变更依据。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    provenance: EvaluationProvenanceV2

    judge_evaluation: BusinessDecisionEvaluationResultV2
    human_review: HumanBusinessDecisionReviewV2
    calibration: JudgeHumanCalibrationResultV2

    observed_evidence_ids: tuple[str, ...]

    proposed_rubric_version: str
    change_recommendation: str

    @model_validator(mode="after")
    def validate_evidence(
        self,
    ) -> "ObservedCalibrationEvidenceV2":
        case_id = self.provenance.case_id

        if self.human_review.case_id != case_id:
            raise ValueError(
                "Human Review case_id 与 provenance 不一致。"
            )

        if self.calibration.case_id != case_id:
            raise ValueError(
                "Calibration case_id 与 provenance 不一致。"
            )

        if not self.observed_evidence_ids:
            raise ValueError(
                "Observed Calibration Evidence 必须引用真实 Evidence ID。"
            )

        if (
            self.proposed_rubric_version
            == self.provenance.rubric_version
        ):
            raise ValueError(
                "proposed_rubric_version 必须与当时实际使用的 "
                "rubric_version 区分。"
            )

        if not self.change_recommendation.strip():
            raise ValueError(
                "change_recommendation 不能为空。"
            )

        return self


def _dimension(
    *,
    score: EvaluationScoreV2,
    reason: str,
    evidence_ids: tuple[str, ...],
) -> EvaluationDimensionResultV2:
    return EvaluationDimensionResultV2(
        score=score,
        reason=reason,
        evidence_ids=evidence_ids,
    )


def _evaluation(
    *,
    prioritization: EvaluationScoreV2,
    prioritization_reason: str,
) -> BusinessDecisionEvaluationResultV2:
    evidence_id = "ev_day88_observed_channel_gmv"

    values = {
        "factual_correctness": _dimension(
            score=EvaluationScoreV2.PASS,
            reason=(
                "2025年当前授权范围内天猫旗舰店 GMV 最高，"
                "该事实由真实受保护渠道 GMV Evidence 支持。"
            ),
            evidence_ids=(evidence_id,),
        ),
        "diagnostic_relevance": _dimension(
            score=EvaluationScoreV2.PASS,
            reason=(
                "回答给出渠道事实，并提出下一步同比比较方向，"
                "对继续调查渠道表现有帮助。"
            ),
            evidence_ids=(evidence_id,),
        ),
        "prioritization": _dimension(
            score=prioritization,
            reason=prioritization_reason,
            evidence_ids=(evidence_id,),
        ),
        "actionability": _dimension(
            score=EvaluationScoreV2.PASS,
            reason=(
                "下一步比较 2025 / 2024 GMV 是明确、可执行的受治理调查动作。"
            ),
            evidence_ids=(evidence_id,),
        ),
        "epistemic_discipline": _dimension(
            score=EvaluationScoreV2.PASS,
            reason=(
                "回答明确指出当前只证明渠道排名，"
                "没有把排名写成 Contribution 或 Cause。"
            ),
            evidence_ids=(evidence_id,),
        ),
        "evidence_sufficiency": _dimension(
            score=EvaluationScoreV2.PASS,
            reason=(
                "回答正确承认证据仅支持当前排名，"
                "并把进一步判断保留到后续 Evidence。"
            ),
            evidence_ids=(evidence_id,),
        ),
    }

    return BusinessDecisionEvaluationResultV2(
        **values,
        overall_status=derive_overall_status_v2(
            **values
        ),
    )


def build_day88_observed_calibration_evidence_v2(
) -> ObservedCalibrationEvidenceV2:
    """
    固化 Day88 的第一条真实 Judge ↔ Human disagreement。

    Live Judge：
    prioritization = PASS

    Human Expert Proxy：
    prioritization = PARTIAL

    Human rationale：
    “需要和业务问题挂钩；仅知道 GMV 最高不足以证明
    天猫就是最值得优先调查的方向。”
    """

    judge_evaluation = _evaluation(
        prioritization=EvaluationScoreV2.PASS,
        prioritization_reason=(
            "Judge 认为天猫 GMV 最高，因此优先围绕天猫做同比比较，"
            "优先级与现有 Evidence 一致。"
        ),
    )

    human_evaluation = _evaluation(
        prioritization=EvaluationScoreV2.PARTIAL,
        prioritization_reason=(
            "调查优先级需要与用户真正的业务问题挂钩。"
            "当前 Evidence 只证明天猫 GMV 最高，"
            "没有证明天猫同比下降、负向 Contribution 最大或存在 Anomaly；"
            "因此不足以判断它就是最值得优先调查的方向。"
        ),
    )

    human_review = HumanBusinessDecisionReviewV2(
        case_id="INS-OBS-001",
        evaluation=human_evaluation,
        review_notes=(
            "Human Expert Proxy 将 prioritization 从 PASS 调整为 PARTIAL。"
            "该 disagreement 不否定事实正确性，而是暴露优先级 Rubric "
            "与 business objective 绑定不够明确。"
        ),
    )

    calibration = build_judge_human_calibration_v2(
        case_id="INS-OBS-001",
        judge_evaluation=judge_evaluation,
        human_review=human_review,
    )

    return ObservedCalibrationEvidenceV2(
        provenance=EvaluationProvenanceV2(
            case_id="INS-OBS-001",
            rubric_version=(
                BUSINESS_DECISION_RUBRIC_V1_0
                .rubric_version
            ),
            judge_prompt_version=(
                "business_decision_judge_prompt_day88_v1"
            ),
            judge_model="deepseek-v4-pro",
            human_reviewer_role="human_expert_proxy",
            evaluated_at_utc=datetime(
                2026,
                8,
                18,
                7,
                4,
                tzinfo=timezone.utc,
            ),
        ),
        judge_evaluation=judge_evaluation,
        human_review=human_review,
        calibration=calibration,
        observed_evidence_ids=(
            "ev_day88_observed_channel_gmv",
        ),
        proposed_rubric_version=(
            BUSINESS_DECISION_RUBRIC_V2_0
            .rubric_version
        ),
        change_recommendation=(
            "收紧 prioritization：PASS 不仅要求方向合理，"
            "还要求调查优先级与用户 business objective 直接相关，"
            "并有比较性 Evidence 证明该方向更值得优先。"
        ),
    )
