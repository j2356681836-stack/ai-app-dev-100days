from __future__ import annotations

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
from app.evaluation.insight_golden_case_contract_v2 import (
    BusinessDecisionScoreFloorV2,
    BusinessInsightThemeV2,
    EvaluationEvidenceClassV2,
    ForbiddenBusinessClaimV2,
    InsightGoldenCaseCatalogV2,
    InsightGoldenCaseV2,
    InsightSectionV2,
)


PASS_FLOOR = BusinessDecisionScoreFloorV2(
    factual_correctness=EvaluationScoreV2.PASS,
    diagnostic_relevance=EvaluationScoreV2.PASS,
    prioritization=EvaluationScoreV2.PASS,
    actionability=EvaluationScoreV2.PASS,
    epistemic_discipline=EvaluationScoreV2.PASS,
    evidence_sufficiency=EvaluationScoreV2.PASS,
)

DIAGNOSTIC_PARTIAL_FLOOR = BusinessDecisionScoreFloorV2(
    factual_correctness=EvaluationScoreV2.PASS,
    diagnostic_relevance=EvaluationScoreV2.PARTIAL,
    prioritization=EvaluationScoreV2.PASS,
    actionability=EvaluationScoreV2.PASS,
    epistemic_discipline=EvaluationScoreV2.PASS,
    evidence_sufficiency=EvaluationScoreV2.PARTIAL,
)

BOUNDARY_PARTIAL_FLOOR = BusinessDecisionScoreFloorV2(
    factual_correctness=EvaluationScoreV2.PASS,
    diagnostic_relevance=EvaluationScoreV2.PARTIAL,
    prioritization=EvaluationScoreV2.PARTIAL,
    actionability=EvaluationScoreV2.PASS,
    epistemic_discipline=EvaluationScoreV2.PASS,
    evidence_sufficiency=EvaluationScoreV2.PARTIAL,
)


VISIBLE_REGRESSION_CASES_V2 = (
    InsightGoldenCaseV2(
        case_id="INS-REG-001",
        question="2025 年 GMV 同比为什么下降，我应该先查什么？",
        theme=BusinessInsightThemeV2.ACTIVITY_REVIEW,
        evidence_class=EvaluationEvidenceClassV2.REGRESSION,
        previously_observed=True,
        used_for_development=True,
        metric_name="gmv",
        expected_analysis_mode=AnalysisModeV2.INVESTIGATION,
        expected_sufficiency=EvidenceSufficiencyStatusV2.PARTIAL,
        expected_overall_status=BusinessDecisionOverallStatusV2.PARTIAL,
        score_floor=DIAGNOSTIC_PARTIAL_FLOOR,
        required_sections=(
            InsightSectionV2.CONFIRMED_FACT,
            InsightSectionV2.DIMENSION_CONTRIBUTION,
            InsightSectionV2.RECOMMENDED_CHECK,
        ),
        forbidden_sections=(),
        forbidden_claims=(
            ForbiddenBusinessClaimV2.CAUSAL_ATTRIBUTION,
            ForbiddenBusinessClaimV2.UNSUPPORTED_FACT,
            ForbiddenBusinessClaimV2.ZERO_FROM_NO_DATA,
        ),
        rationale=(
            "GMV × channel 已具备 additive contribution 首版能力，"
            "可以回答变化主要来自哪里；但 Contribution 不能被写成原因，"
            "仍需保留下一步调查方向。"
        ),
        tags=("gmv", "yoy", "channel", "contribution"),
    ),
    InsightGoldenCaseV2(
        case_id="INS-REG-002",
        question="2025 年哪个渠道 ROI 最低，这是否已经说明渠道效率出了问题？",
        theme=BusinessInsightThemeV2.ROI,
        evidence_class=EvaluationEvidenceClassV2.REGRESSION,
        previously_observed=True,
        used_for_development=True,
        metric_name="roi",
        expected_analysis_mode=AnalysisModeV2.INVESTIGATION,
        expected_sufficiency=EvidenceSufficiencyStatusV2.PARTIAL,
        expected_overall_status=BusinessDecisionOverallStatusV2.PARTIAL,
        score_floor=DIAGNOSTIC_PARTIAL_FLOOR,
        required_sections=(
            InsightSectionV2.CONFIRMED_FACT,
            InsightSectionV2.UNKNOWN,
            InsightSectionV2.RECOMMENDED_CHECK,
        ),
        forbidden_sections=(
            InsightSectionV2.DIMENSION_CONTRIBUTION,
        ),
        forbidden_claims=(
            ForbiddenBusinessClaimV2.CAUSAL_ATTRIBUTION,
            ForbiddenBusinessClaimV2.UNSUPPORTED_FACT,
        ),
        rationale=(
            "ROI Query Plan 可以支持渠道事实比较，但当前没有 ratio metric "
            "的通用 Contribution decomposition。低 ROI 只能形成调查优先级，"
            "不能自动证明效率问题的具体原因。"
        ),
        tags=("roi", "channel", "ratio_metric", "boundary"),
    ),
    InsightGoldenCaseV2(
        case_id="INS-REG-003",
        question="2025 年毛利率同比下降了吗？如果下降，下一步应该优先看哪里？",
        theme=BusinessInsightThemeV2.MARGIN,
        evidence_class=EvaluationEvidenceClassV2.REGRESSION,
        previously_observed=True,
        used_for_development=True,
        metric_name="gross_margin_rate",
        expected_analysis_mode=AnalysisModeV2.INVESTIGATION,
        expected_sufficiency=EvidenceSufficiencyStatusV2.PARTIAL,
        expected_overall_status=BusinessDecisionOverallStatusV2.PARTIAL,
        score_floor=DIAGNOSTIC_PARTIAL_FLOOR,
        required_sections=(
            InsightSectionV2.CONFIRMED_FACT,
            InsightSectionV2.UNKNOWN,
            InsightSectionV2.RECOMMENDED_CHECK,
        ),
        forbidden_sections=(
            InsightSectionV2.DIMENSION_CONTRIBUTION,
        ),
        forbidden_claims=(
            ForbiddenBusinessClaimV2.CAUSAL_ATTRIBUTION,
            ForbiddenBusinessClaimV2.UNSUPPORTED_FACT,
        ),
        rationale=(
            "Gross Margin Rate 是 ratio metric。当前可以查询并比较事实，"
            "但不能套用 GMV additive contribution 公式，因此需要保持原因未知"
            "并给出后续合法调查建议。"
        ),
        tags=("gross_margin_rate", "ratio_metric", "yoy", "boundary"),
    ),
    InsightGoldenCaseV2(
        case_id="INS-REG-004",
        question="2025 年退款率比去年高了吗？如果变差，我应该先调查什么？",
        theme=BusinessInsightThemeV2.REFUND,
        evidence_class=EvaluationEvidenceClassV2.REGRESSION,
        previously_observed=True,
        used_for_development=True,
        metric_name="refund_rate",
        expected_analysis_mode=AnalysisModeV2.INVESTIGATION,
        expected_sufficiency=EvidenceSufficiencyStatusV2.PARTIAL,
        expected_overall_status=BusinessDecisionOverallStatusV2.PARTIAL,
        score_floor=DIAGNOSTIC_PARTIAL_FLOOR,
        required_sections=(
            InsightSectionV2.CONFIRMED_FACT,
            InsightSectionV2.UNKNOWN,
            InsightSectionV2.RECOMMENDED_CHECK,
        ),
        forbidden_sections=(
            InsightSectionV2.DIMENSION_CONTRIBUTION,
        ),
        forbidden_claims=(
            ForbiddenBusinessClaimV2.CAUSAL_ATTRIBUTION,
            ForbiddenBusinessClaimV2.UNSUPPORTED_FACT,
            ForbiddenBusinessClaimV2.ZERO_FROM_NO_DATA,
        ),
        rationale=(
            "Refund Rate 可以形成受治理事实比较，但当前 Production Active "
            "Anomaly Policy = 0，且 ratio contribution 尚未定义。"
            "系统不能把 Dataset Acceptance threshold 或 LLM 判断冒充 anomaly truth。"
        ),
        tags=("refund_rate", "ratio_metric", "policy_boundary"),
    ),
    InsightGoldenCaseV2(
        case_id="INS-REG-005",
        question="当前授权范围下，2025 年哪个渠道 CAC 最高？能否直接判断获客效率问题？",
        theme=BusinessInsightThemeV2.CAC,
        evidence_class=EvaluationEvidenceClassV2.REGRESSION,
        previously_observed=True,
        used_for_development=True,
        metric_name="cac",
        expected_analysis_mode=AnalysisModeV2.INVESTIGATION,
        expected_sufficiency=EvidenceSufficiencyStatusV2.INSUFFICIENT,
        expected_overall_status=BusinessDecisionOverallStatusV2.PARTIAL,
        score_floor=BOUNDARY_PARTIAL_FLOOR,
        required_sections=(
            InsightSectionV2.UNKNOWN,
            InsightSectionV2.RECOMMENDED_CHECK,
        ),
        forbidden_sections=(
            InsightSectionV2.DIMENSION_CONTRIBUTION,
        ),
        forbidden_claims=(
            ForbiddenBusinessClaimV2.CAUSAL_ATTRIBUTION,
            ForbiddenBusinessClaimV2.UNSUPPORTED_FACT,
            ForbiddenBusinessClaimV2.UNAUTHORIZED_EXISTENCE_DISCLOSURE,
        ),
        rationale=(
            "CAC 是 cross-fact metric，当前部分 Query Plan 会因 Region / "
            "post-sequence Scope Contract 保持 fail-closed。Golden Case 要求系统"
            "尊重治理边界，不用被阻断的数据编造排名或原因。"
        ),
        tags=("cac", "cross_fact", "scope_boundary", "fail_closed"),
    ),
    InsightGoldenCaseV2(
        case_id="INS-REG-006",
        question="2025 年哪些区域的 GMV 表现最弱？下一步应该优先调查哪个区域？",
        theme=BusinessInsightThemeV2.REGION,
        evidence_class=EvaluationEvidenceClassV2.REGRESSION,
        previously_observed=True,
        used_for_development=True,
        metric_name="gmv",
        expected_analysis_mode=AnalysisModeV2.INVESTIGATION,
        expected_sufficiency=EvidenceSufficiencyStatusV2.PARTIAL,
        expected_overall_status=BusinessDecisionOverallStatusV2.PARTIAL,
        score_floor=DIAGNOSTIC_PARTIAL_FLOOR,
        required_sections=(
            InsightSectionV2.CONFIRMED_FACT,
            InsightSectionV2.RECOMMENDED_CHECK,
        ),
        forbidden_sections=(
            InsightSectionV2.DIMENSION_CONTRIBUTION,
        ),
        forbidden_claims=(
            ForbiddenBusinessClaimV2.CAUSAL_ATTRIBUTION,
            ForbiddenBusinessClaimV2.UNSUPPORTED_FACT,
        ),
        rationale=(
            "V2 支持 GMV × region 查询，但 Day84 Contribution Engine "
            "当前只冻结 GMV × channel。区域事实可以用于调查优先级，"
            "不能伪装成已经实现 region contribution decomposition。"
        ),
        tags=("gmv", "region", "prioritization", "boundary"),
    ),
    InsightGoldenCaseV2(
        case_id="INS-REG-007",
        question="2025 年会员 GMV 贡献率表现如何？如果下降，能否直接说明会员经营变差？",
        theme=BusinessInsightThemeV2.MEMBERSHIP,
        evidence_class=EvaluationEvidenceClassV2.REGRESSION,
        previously_observed=True,
        used_for_development=True,
        metric_name="member_gmv_share",
        expected_analysis_mode=AnalysisModeV2.INVESTIGATION,
        expected_sufficiency=EvidenceSufficiencyStatusV2.PARTIAL,
        expected_overall_status=BusinessDecisionOverallStatusV2.PARTIAL,
        score_floor=DIAGNOSTIC_PARTIAL_FLOOR,
        required_sections=(
            InsightSectionV2.CONFIRMED_FACT,
            InsightSectionV2.UNKNOWN,
            InsightSectionV2.RECOMMENDED_CHECK,
        ),
        forbidden_sections=(
            InsightSectionV2.DIMENSION_CONTRIBUTION,
        ),
        forbidden_claims=(
            ForbiddenBusinessClaimV2.CAUSAL_ATTRIBUTION,
            ForbiddenBusinessClaimV2.UNSUPPORTED_FACT,
        ),
        rationale=(
            "Member GMV Share 是 ratio / derived metric。数值变化可以成为事实，"
            "但不能仅凭份额下降就得出会员经营变差的原因结论。"
        ),
        tags=("member_gmv_share", "membership", "ratio_metric"),
    ),
    InsightGoldenCaseV2(
        case_id="INS-REG-008",
        question="双11活动 GMV 相比去年同期表现如何？下一步应该先检查什么？",
        theme=BusinessInsightThemeV2.PROMOTION,
        evidence_class=EvaluationEvidenceClassV2.REGRESSION,
        previously_observed=True,
        used_for_development=True,
        metric_name="gmv",
        expected_analysis_mode=AnalysisModeV2.INVESTIGATION,
        expected_sufficiency=EvidenceSufficiencyStatusV2.INSUFFICIENT,
        expected_overall_status=BusinessDecisionOverallStatusV2.PARTIAL,
        score_floor=BOUNDARY_PARTIAL_FLOOR,
        required_sections=(
            InsightSectionV2.UNKNOWN,
            InsightSectionV2.RECOMMENDED_CHECK,
        ),
        forbidden_sections=(),
        forbidden_claims=(
            ForbiddenBusinessClaimV2.CAUSAL_ATTRIBUTION,
            ForbiddenBusinessClaimV2.UNSUPPORTED_FACT,
        ),
        rationale=(
            "TimeComparisonContractV2 已支持 Campaign YoY 概念，"
            "但完整 Campaign Resolver / campaign-aware runtime 尚未完成。"
            "当前 Golden Case 用来保护“不因问题听起来合理就伪造活动期事实”的边界。"
        ),
        tags=("gmv", "promotion", "campaign_yoy", "runtime_boundary"),
    ),
)


VISIBLE_REGRESSION_CATALOG_V2 = InsightGoldenCaseCatalogV2(
    cases=VISIBLE_REGRESSION_CASES_V2,
)
