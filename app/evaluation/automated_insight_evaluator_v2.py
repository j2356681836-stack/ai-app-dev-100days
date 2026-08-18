from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, model_validator

from app.agents.evidence_pack_delivery_v2 import (
    EvidencePackDeliveryV2,
)
from app.evaluation.insight_golden_case_contract_v2 import (
    EvaluationEvidenceClassV2,
    ForbiddenBusinessClaimV2,
    InsightGoldenCaseV2,
    InsightSectionV2,
)


class DeterministicInsightGateStatusV2(str, Enum):
    """
    Day88 自动化结构 Gate 的结果。

    这里只回答“可确定性判断的合同要求是否满足”，
    不冒充 Business Decision Judge。
    """

    PASS = "pass"
    FAIL = "fail"


class DeterministicInsightGateV2(str, Enum):
    METRIC = "metric"
    ANALYSIS_MODE = "analysis_mode"
    EVIDENCE_SUFFICIENCY = "evidence_sufficiency"
    REQUIRED_SECTIONS = "required_sections"
    FORBIDDEN_SECTIONS = "forbidden_sections"


class DeterministicInsightGateResultV2(BaseModel):
    """
    单个 deterministic gate 的验收结果。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    gate: DeterministicInsightGateV2
    status: DeterministicInsightGateStatusV2
    reason: str

    @model_validator(mode="after")
    def validate_result(
        self,
    ) -> "DeterministicInsightGateResultV2":
        if not self.reason.strip():
            raise ValueError(
                "Deterministic Insight Gate reason 不能为空。"
            )
        return self


class AutomatedInsightEvaluationStatusV2(str, Enum):
    """
    Automated pre-check 的总体状态。
    """

    READY_FOR_BUSINESS_REVIEW = "ready_for_business_review"
    DETERMINISTIC_FAIL = "deterministic_fail"


class AutomatedInsightEvaluationResultV2(BaseModel):
    """
    Day88 Automated Insight Evaluation。

    这是 Business Decision Evaluation 前的 deterministic pre-check：
    - 对结构、Metric、Mode、Sufficiency、Section 做自动判断；
    - 不把自然语言业务质量假装成 deterministic truth；
    - forbidden business claim 作为后续 semantic review obligation。

    因此：
    READY_FOR_BUSINESS_REVIEW
    ≠ Business Decision PASS
    ≠ Human Review PASS
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    case_id: str
    evidence_class: EvaluationEvidenceClassV2
    status: AutomatedInsightEvaluationStatusV2
    gate_results: tuple[DeterministicInsightGateResultV2, ...]

    semantic_review_items: tuple[
        ForbiddenBusinessClaimV2, ...
    ]
    business_decision_review_required: bool = True

    @model_validator(mode="after")
    def validate_evaluation(
        self,
    ) -> "AutomatedInsightEvaluationResultV2":
        if not self.case_id.strip():
            raise ValueError(
                "case_id 不能为空。"
            )

        expected_gates = set(
            DeterministicInsightGateV2
        )
        actual_gates = {
            result.gate
            for result in self.gate_results
        }

        if actual_gates != expected_gates:
            raise ValueError(
                "Automated Insight Evaluation 必须完整执行全部 "
                "deterministic gates。"
            )

        if (
            len(self.gate_results)
            != len(actual_gates)
        ):
            raise ValueError(
                "deterministic gate 不能重复。"
            )

        has_failure = any(
            result.status
            == DeterministicInsightGateStatusV2.FAIL
            for result in self.gate_results
        )

        expected_status = (
            AutomatedInsightEvaluationStatusV2.DETERMINISTIC_FAIL
            if has_failure
            else (
                AutomatedInsightEvaluationStatusV2
                .READY_FOR_BUSINESS_REVIEW
            )
        )

        if self.status != expected_status:
            raise ValueError(
                "Automated Insight Evaluation status "
                "必须由 deterministic gate 结果推导。"
            )

        if not self.business_decision_review_required:
            raise ValueError(
                "Day88 第一版 Automated Evaluation 不能跳过 "
                "Business Decision semantic review。"
            )

        return self


def _present_sections(
    delivery: EvidencePackDeliveryV2,
) -> frozenset[InsightSectionV2]:
    insight = delivery.evidence_pack.insight
    sections: set[InsightSectionV2] = set()

    if insight.confirmed_facts:
        sections.add(
            InsightSectionV2.CONFIRMED_FACT
        )

    if insight.detected_anomalies:
        sections.add(
            InsightSectionV2.DETECTED_ANOMALY
        )

    if insight.dimension_contributions:
        sections.add(
            InsightSectionV2.DIMENSION_CONTRIBUTION
        )

    if insight.candidate_explanations:
        sections.add(
            InsightSectionV2.CANDIDATE_HYPOTHESIS
        )

    if insight.unknowns:
        sections.add(
            InsightSectionV2.UNKNOWN
        )

    if insight.recommended_checks:
        sections.add(
            InsightSectionV2.RECOMMENDED_CHECK
        )

    return frozenset(sections)


def _gate_result(
    *,
    gate: DeterministicInsightGateV2,
    passed: bool,
    reason: str,
) -> DeterministicInsightGateResultV2:
    return DeterministicInsightGateResultV2(
        gate=gate,
        status=(
            DeterministicInsightGateStatusV2.PASS
            if passed
            else DeterministicInsightGateStatusV2.FAIL
        ),
        reason=reason,
    )


def evaluate_insight_delivery_v2(
    *,
    golden_case: InsightGoldenCaseV2,
    delivery: EvidencePackDeliveryV2,
) -> AutomatedInsightEvaluationResultV2:
    """
    对 EvidencePackDeliveryV2 做 deterministic Golden Case pre-check。

    能自动判定：
    - Metric；
    - Analysis Mode；
    - Evidence Sufficiency；
    - required Insight Sections；
    - forbidden Insight Sections。

    不能仅凭结构可靠判定：
    - 数值是否符合业务 Golden Truth；
    - 诊断是否真正相关；
    - 优先级是否合理；
    - 建议是否真正可行动；
    - 文本是否存在隐含 causal attribution / unsupported fact。

    这些必须进入后续 Judge / Human Review。
    """

    insight = delivery.evidence_pack.insight
    present_sections = _present_sections(
        delivery
    )

    metric_pass = (
        delivery.metric_definition.metric_name
        == golden_case.metric_name
        and insight.analysis_scope.metric_name
        == golden_case.metric_name
    )

    mode_pass = (
        insight.analysis_mode
        == golden_case.expected_analysis_mode
    )

    sufficiency_pass = (
        delivery.sufficiency.status
        == golden_case.expected_sufficiency
    )

    missing_required = (
        set(golden_case.required_sections)
        - set(present_sections)
    )
    required_pass = not missing_required

    forbidden_present = (
        set(golden_case.forbidden_sections)
        & set(present_sections)
    )
    forbidden_pass = not forbidden_present

    gate_results = (
        _gate_result(
            gate=DeterministicInsightGateV2.METRIC,
            passed=metric_pass,
            reason=(
                "Metric 与 Golden Case 一致。"
                if metric_pass
                else (
                    "Metric 与 Golden Case 不一致："
                    f"expected={golden_case.metric_name}; "
                    f"actual={delivery.metric_definition.metric_name}"
                )
            ),
        ),
        _gate_result(
            gate=DeterministicInsightGateV2.ANALYSIS_MODE,
            passed=mode_pass,
            reason=(
                "Analysis Mode 与 Golden Case 一致。"
                if mode_pass
                else (
                    "Analysis Mode 不一致："
                    f"expected={golden_case.expected_analysis_mode.value}; "
                    f"actual={insight.analysis_mode.value}"
                )
            ),
        ),
        _gate_result(
            gate=(
                DeterministicInsightGateV2
                .EVIDENCE_SUFFICIENCY
            ),
            passed=sufficiency_pass,
            reason=(
                "Evidence Sufficiency 与 Golden Case 一致。"
                if sufficiency_pass
                else (
                    "Evidence Sufficiency 不一致："
                    f"expected={golden_case.expected_sufficiency.value}; "
                    f"actual={delivery.sufficiency.status.value}"
                )
            ),
        ),
        _gate_result(
            gate=DeterministicInsightGateV2.REQUIRED_SECTIONS,
            passed=required_pass,
            reason=(
                "所有 required Insight Sections 均存在。"
                if required_pass
                else (
                    "缺少 required Insight Sections："
                    f"{sorted(item.value for item in missing_required)}"
                )
            ),
        ),
        _gate_result(
            gate=DeterministicInsightGateV2.FORBIDDEN_SECTIONS,
            passed=forbidden_pass,
            reason=(
                "未出现 forbidden Insight Sections。"
                if forbidden_pass
                else (
                    "出现 forbidden Insight Sections："
                    f"{sorted(item.value for item in forbidden_present)}"
                )
            ),
        ),
    )

    has_failure = any(
        result.status
        == DeterministicInsightGateStatusV2.FAIL
        for result in gate_results
    )

    return AutomatedInsightEvaluationResultV2(
        case_id=golden_case.case_id,
        evidence_class=golden_case.evidence_class,
        status=(
            AutomatedInsightEvaluationStatusV2.DETERMINISTIC_FAIL
            if has_failure
            else (
                AutomatedInsightEvaluationStatusV2
                .READY_FOR_BUSINESS_REVIEW
            )
        ),
        gate_results=gate_results,
        semantic_review_items=golden_case.forbidden_claims,
        business_decision_review_required=True,
    )
