from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.agents.evidence_pack_delivery_v2 import (
    EvidenceSufficiencyStatusV2,
)
from app.agents.investigation_contracts_v2 import (
    AnalysisModeV2,
)
from app.evaluation.business_decision_evaluation_contract_v2 import (
    BusinessDecisionOverallStatusV2,
    EvaluationScoreV2,
)


class EvaluationEvidenceClassV2(str, Enum):
    """
    Day88 Evaluation Case 的证据类别。

    REGRESSION：
    已被观察、调试或用于开发的固定案例。
    证明“旧能力没有被改坏”，不证明 fresh generalization。

    HOLDOUT：
    预先锁定、开发过程中不用于调规则的案例。
    可以用于阶段性评估，但一旦结果反复影响开发决策，
    其独立 holdout 价值会下降。

    FRESH_GENERALIZATION：
    系统冻结后第一次真正观察的未见案例。
    第一次运行之后，未来不能继续把同一案例声称为 Fresh。
    """

    REGRESSION = "regression"
    HOLDOUT = "holdout"
    FRESH_GENERALIZATION = "fresh_generalization"


class BusinessInsightThemeV2(str, Enum):
    """
    Day88 首批 Business Insight Golden Cases 的业务主题。
    """

    ACTIVITY_REVIEW = "activity_review"
    ROI = "roi"
    MARGIN = "margin"
    REFUND = "refund"
    CAC = "cac"
    REGION = "region"
    MEMBERSHIP = "membership"
    PROMOTION = "promotion"


class InsightSectionV2(str, Enum):
    """
    Evidence-backed Insight 的结构化内容区。
    """

    CONFIRMED_FACT = "confirmed_fact"
    DETECTED_ANOMALY = "detected_anomaly"
    DIMENSION_CONTRIBUTION = "dimension_contribution"
    CANDIDATE_HYPOTHESIS = "candidate_hypothesis"
    UNKNOWN = "unknown"
    RECOMMENDED_CHECK = "recommended_check"


class ForbiddenBusinessClaimV2(str, Enum):
    """
    Golden Case 可以显式禁止的认知越界。

    这些不是“措辞风格”，而是业务事实边界。
    """

    CAUSAL_ATTRIBUTION = "causal_attribution"
    UNSUPPORTED_FACT = "unsupported_fact"
    ZERO_FROM_NO_DATA = "zero_from_no_data"
    UNAUTHORIZED_EXISTENCE_DISCLOSURE = (
        "unauthorized_existence_disclosure"
    )


class BusinessDecisionScoreFloorV2(BaseModel):
    """
    Golden Case 对六维 Business Decision Evaluation 的最低要求。

    这里不是实际评分结果，只是 acceptance floor。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    factual_correctness: EvaluationScoreV2
    diagnostic_relevance: EvaluationScoreV2
    prioritization: EvaluationScoreV2
    actionability: EvaluationScoreV2
    epistemic_discipline: EvaluationScoreV2
    evidence_sufficiency: EvaluationScoreV2

    def as_tuple(
        self,
    ) -> tuple[EvaluationScoreV2, ...]:
        return (
            self.factual_correctness,
            self.diagnostic_relevance,
            self.prioritization,
            self.actionability,
            self.epistemic_discipline,
            self.evidence_sufficiency,
        )


class InsightGoldenCaseV2(BaseModel):
    """
    Day88 Business Insight Golden Case 合同。

    Golden Case 不要求系统逐字复述标准答案。
    它冻结的是：
    - 业务问题属于什么主题；
    - 当前可信 Metric / Analysis Mode；
    - 预期 Evidence Sufficiency；
    - Business Decision 六维最低要求；
    - 哪些 Insight Section 必须 / 禁止出现；
    - 哪些 epistemic violation 绝不能出现；
    - 这条案例的证据身份是 Regression / Holdout / Fresh。

    Freshness 是数据治理事实，不是模型输出字段。
    Contract 只能要求调用方显式声明，不能凭代码自动证明
    “这个问题以前真的从未被人看过”。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    case_id: str
    question: str
    theme: BusinessInsightThemeV2

    evidence_class: EvaluationEvidenceClassV2
    previously_observed: bool
    used_for_development: bool

    metric_name: str
    expected_analysis_mode: AnalysisModeV2
    expected_sufficiency: EvidenceSufficiencyStatusV2
    expected_overall_status: BusinessDecisionOverallStatusV2

    score_floor: BusinessDecisionScoreFloorV2

    required_sections: tuple[InsightSectionV2, ...]
    forbidden_sections: tuple[InsightSectionV2, ...] = ()

    forbidden_claims: tuple[ForbiddenBusinessClaimV2, ...] = (
        ForbiddenBusinessClaimV2.CAUSAL_ATTRIBUTION,
        ForbiddenBusinessClaimV2.UNSUPPORTED_FACT,
        ForbiddenBusinessClaimV2.ZERO_FROM_NO_DATA,
        ForbiddenBusinessClaimV2.UNAUTHORIZED_EXISTENCE_DISCLOSURE,
    )

    rationale: str
    tags: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_case(
        self,
    ) -> "InsightGoldenCaseV2":
        string_fields = {
            "case_id": self.case_id,
            "question": self.question,
            "metric_name": self.metric_name,
            "rationale": self.rationale,
        }

        empty = [
            name
            for name, value in string_fields.items()
            if not value.strip()
        ]

        if empty:
            raise ValueError(
                "Golden Case 关键文本字段不能为空："
                f"{sorted(empty)}"
            )

        if (
            len(set(self.required_sections))
            != len(self.required_sections)
        ):
            raise ValueError(
                "required_sections 不能重复。"
            )

        if (
            len(set(self.forbidden_sections))
            != len(self.forbidden_sections)
        ):
            raise ValueError(
                "forbidden_sections 不能重复。"
            )

        overlap = (
            set(self.required_sections)
            & set(self.forbidden_sections)
        )

        if overlap:
            raise ValueError(
                "同一个 Insight Section 不能同时 required / forbidden："
                f"{sorted(item.value for item in overlap)}"
            )

        if not self.required_sections:
            raise ValueError(
                "Golden Case 至少需要一个 required Insight Section。"
            )

        if (
            len(set(self.forbidden_claims))
            != len(self.forbidden_claims)
        ):
            raise ValueError(
                "forbidden_claims 不能重复。"
            )

        if any(
            not tag.strip()
            for tag in self.tags
        ):
            raise ValueError(
                "tags 不能包含空字符串。"
            )

        if len(set(self.tags)) != len(self.tags):
            raise ValueError(
                "tags 不能重复。"
            )

        if (
            self.evidence_class
            == EvaluationEvidenceClassV2.REGRESSION
        ):
            if not self.previously_observed:
                raise ValueError(
                    "Regression Case 必须已经被观察过。"
                )

        elif (
            self.evidence_class
            == EvaluationEvidenceClassV2.HOLDOUT
        ):
            if self.used_for_development:
                raise ValueError(
                    "Holdout Case 不能已经被用于开发调优。"
                )

        elif (
            self.evidence_class
            == EvaluationEvidenceClassV2.FRESH_GENERALIZATION
        ):
            if self.previously_observed:
                raise ValueError(
                    "Fresh Generalization Case 不能已经被观察过。"
                )

            if self.used_for_development:
                raise ValueError(
                    "Fresh Generalization Case 不能已经用于开发调优。"
                )

        # factual correctness 与 epistemic discipline 是 Day82 hard gate。
        if (
            self.expected_overall_status
            == BusinessDecisionOverallStatusV2.PASS
        ):
            if any(
                score != EvaluationScoreV2.PASS
                for score in self.score_floor.as_tuple()
            ):
                raise ValueError(
                    "如果 Golden Case 期望 Overall PASS，"
                    "六个维度的最低要求都必须是 PASS。"
                )

        if (
            self.score_floor.factual_correctness
            == EvaluationScoreV2.FAIL
            and self.expected_overall_status
            != BusinessDecisionOverallStatusV2.FAIL
        ):
            raise ValueError(
                "factual correctness floor=FAIL 时，"
                "expected overall 必须为 FAIL。"
            )

        if (
            self.score_floor.epistemic_discipline
            == EvaluationScoreV2.FAIL
            and self.expected_overall_status
            != BusinessDecisionOverallStatusV2.FAIL
        ):
            raise ValueError(
                "epistemic discipline floor=FAIL 时，"
                "expected overall 必须为 FAIL。"
            )

        return self


class InsightGoldenCaseCatalogV2(BaseModel):
    """
    Day88 Golden Case Catalog。

    Catalog 只负责静态一致性，不把 Fresh Case 自动转成 Regression。
    第一次 Fresh Evaluation 后，维护者必须更新 artifact / evidence label。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    contract_version: str = "insight_golden_case_catalog_v2_0"
    cases: tuple[InsightGoldenCaseV2, ...] = Field(
        min_length=1
    )

    @model_validator(mode="after")
    def validate_catalog(
        self,
    ) -> "InsightGoldenCaseCatalogV2":
        case_ids = [
            case.case_id
            for case in self.cases
        ]

        if len(set(case_ids)) != len(case_ids):
            raise ValueError(
                "Golden Case Catalog 中 case_id 不能重复。"
            )

        return self
