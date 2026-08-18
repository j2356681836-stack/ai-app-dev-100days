from __future__ import annotations

import json
from enum import Enum
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

from app.agents.evidence_pack_delivery_v2 import (
    EvidencePackDeliveryV2,
)
from app.evaluation.automated_insight_evaluator_v2 import (
    AutomatedInsightEvaluationResultV2,
    AutomatedInsightEvaluationStatusV2,
)
from app.evaluation.business_decision_evaluation_contract_v2 import (
    BusinessDecisionEvaluationResultV2,
    BusinessDecisionOverallStatusV2,
    EvaluationDimensionResultV2,
    EvaluationScoreV2,
    derive_overall_status_v2,
)
from app.evaluation.insight_golden_case_contract_v2 import (
    InsightGoldenCaseV2,
)


_SYSTEM_PROMPT = """你是一个受约束的 Business Decision Quality Judge。

你只评估给定业务回答与 Evidence Delivery，不生成新的业务事实。

六个评分维度：
1. factual_correctness：事实陈述是否被给定 Evidence 支持。
2. diagnostic_relevance：是否真正推进了用户业务问题，而不只是重复数字。
3. prioritization：是否根据现有证据给出了合理的调查优先级。
4. actionability：是否给出了证据边界内可执行的下一步。
5. epistemic_discipline：是否严格区分 Fact / Contribution / Hypothesis / Unknown，
   是否避免把 contribution / correlation 写成 cause，是否避免把 NO_DATA 写成 0。
6. evidence_sufficiency：回答是否正确表达当前证据充分或不足，而不是夸大确定性。

评分：
0 = FAIL
1 = PARTIAL
2 = PASS

规则：
- 只能使用输入中提供的 Evidence。
- 不得自行补充外部知识、业务原因或隐藏数据。
- evidence_ids 只能复制输入中真实存在的 evidence_id。
- 没有必要引用 Evidence 的维度可以使用空数组，但 factual_correctness 为 PASS/PARTIAL
  时至少应引用一条真实 Evidence。
- 所有 reason 必须使用简体中文。
- 不要输出 overall_status；系统会根据 Day82 hard-gate rule 确定性计算。
- 只返回一个 JSON 对象，不要 Markdown，不要额外文字。

JSON 结构：
{
  "factual_correctness":{"score":0|1|2,"reason":"...","evidence_ids":["..."]},
  "diagnostic_relevance":{"score":0|1|2,"reason":"...","evidence_ids":["..."]},
  "prioritization":{"score":0|1|2,"reason":"...","evidence_ids":["..."]},
  "actionability":{"score":0|1|2,"reason":"...","evidence_ids":["..."]},
  "epistemic_discipline":{"score":0|1|2,"reason":"...","evidence_ids":["..."]},
  "evidence_sufficiency":{"score":0|1|2,"reason":"...","evidence_ids":["..."]}
}
"""


class BusinessDecisionJudgeProposalV2(BaseModel):
    """
    LLM Judge 只能填写六个维度。

    overall_status 不属于模型权限，
    继续由 Day82 deterministic rule 计算。
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


class BusinessDecisionJudgeExecutionStatusV2(str, Enum):
    JUDGED = "judged"
    SKIPPED_DETERMINISTIC_FAIL = "skipped_deterministic_fail"


class BusinessDecisionJudgeOutcomeV2(BaseModel):
    """
    Judge 执行结果。

    meets_golden_floor 只表示 Judge 分数达到 Golden Case 的最低要求，
    不等于 Human Calibration 已通过。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    case_id: str
    status: BusinessDecisionJudgeExecutionStatusV2
    evaluation: BusinessDecisionEvaluationResultV2 | None = None

    meets_golden_floor: bool | None = None
    below_floor_dimensions: tuple[str, ...] = ()
    meets_expected_overall_status: bool | None = None

    detail: str | None = None

    @model_validator(mode="after")
    def validate_outcome(
        self,
    ) -> "BusinessDecisionJudgeOutcomeV2":
        if self.status == BusinessDecisionJudgeExecutionStatusV2.JUDGED:
            if self.evaluation is None:
                raise ValueError(
                    "JUDGED 状态必须包含 Business Decision Evaluation。"
                )

            if self.meets_golden_floor is None:
                raise ValueError(
                    "JUDGED 状态必须包含 meets_golden_floor。"
                )

            if self.meets_expected_overall_status is None:
                raise ValueError(
                    "JUDGED 状态必须包含 overall floor 判断。"
                )

            if self.detail is not None:
                raise ValueError(
                    "JUDGED 状态不应携带 skip detail。"
                )
        else:
            if self.evaluation is not None:
                raise ValueError(
                    "Deterministic Fail 后不能释放 Judge Evaluation。"
                )

            if self.meets_golden_floor is not None:
                raise ValueError(
                    "跳过 Judge 时不能伪造 score floor 结果。"
                )

            if self.meets_expected_overall_status is not None:
                raise ValueError(
                    "跳过 Judge 时不能伪造 overall floor 结果。"
                )

            if not self.detail:
                raise ValueError(
                    "跳过 Judge 时必须说明 detail。"
                )

        return self


_DIMENSION_NAMES = (
    "factual_correctness",
    "diagnostic_relevance",
    "prioritization",
    "actionability",
    "epistemic_discipline",
    "evidence_sufficiency",
)


_OVERALL_RANK = {
    BusinessDecisionOverallStatusV2.FAIL: 0,
    BusinessDecisionOverallStatusV2.PARTIAL: 1,
    BusinessDecisionOverallStatusV2.PASS: 2,
}


def _contains_cjk(
    text: str,
) -> bool:
    return any(
        "\u4e00" <= char <= "\u9fff"
        for char in text
    )


def _statement_payload(
    items: tuple[Any, ...],
) -> list[dict[str, Any]]:
    return [
        {
            "statement": item.statement,
            "evidence_ids": list(item.evidence_ids),
        }
        for item in items
    ]


def _build_evidence_payload(
    delivery: EvidencePackDeliveryV2,
) -> list[dict[str, Any]]:
    """
    只向 Judge 暴露 Evidence Pack 已允许释放的信息。

    不暴露 raw SQL / raw parameters / blocked raw rows。
    """

    result: list[dict[str, Any]] = []

    for record in delivery.evidence_pack.evidence_records:
        item: dict[str, Any] = {
            "evidence_id": record.reference.evidence_id,
            "source": record.reference.source,
            "description": record.reference.description,
            "evidence_type": record.evidence_type.value,
            "parent_evidence_ids": list(
                record.parent_evidence_ids
            ),
        }

        if record.provenance is not None:
            item["provenance"] = {
                "dataset_name": record.provenance.dataset_name,
                "metric_name": record.provenance.metric_name,
                "result_grain": record.provenance.result_grain,
                "analysis_window": {
                    "start_date": (
                        record.provenance.analysis_window
                        .start_date.isoformat()
                    ),
                    "end_date": (
                        record.provenance.analysis_window
                        .end_date.isoformat()
                    ),
                },
                "scope_summary": record.provenance.scope_summary,
                "plan_name": record.provenance.plan_name,
                "audit_event_id": record.provenance.audit_event_id,
            }

        if record.protected_result is not None:
            item["protected_result"] = {
                "field_names": list(
                    record.protected_result.field_names
                ),
                "rows": list(
                    record.protected_result.rows
                ),
                "row_count": record.protected_result.row_count,
            }

        if record.investigation_observation is not None:
            item["investigation_observation"] = (
                record.investigation_observation.model_dump()
            )

        result.append(item)

    return result


def build_business_decision_judge_context_v2(
    *,
    golden_case: InsightGoldenCaseV2,
    delivery: EvidencePackDeliveryV2,
    automated_result: AutomatedInsightEvaluationResultV2,
) -> dict[str, Any]:
    """
    构建最小 Business Decision Judge Context。

    不向模型提供 Golden score floor / expected overall status，
    避免 Judge 直接照抄预期评分。
    """

    insight = delivery.evidence_pack.insight

    return {
        "case": {
            "case_id": golden_case.case_id,
            "question": golden_case.question,
            "theme": golden_case.theme.value,
            "forbidden_business_claims_for_review": [
                item.value
                for item in automated_result.semantic_review_items
            ],
        },
        "metric_definition": (
            delivery.metric_definition.model_dump()
        ),
        "insight": {
            "analysis_mode": insight.analysis_mode.value,
            "confirmed_facts": _statement_payload(
                insight.confirmed_facts
            ),
            "detected_anomalies": _statement_payload(
                insight.detected_anomalies
            ),
            "dimension_contributions": _statement_payload(
                insight.dimension_contributions
            ),
            "candidate_explanations": [
                {
                    "explanation": item.explanation,
                    "supporting_evidence_ids": list(
                        item.supporting_evidence_ids
                    ),
                }
                for item in insight.candidate_explanations
            ],
            "unknowns": [
                item.description
                for item in insight.unknowns
            ],
            "recommended_checks": [
                {
                    "check": item.check,
                    "rationale": item.rationale,
                    "evidence_ids": list(item.evidence_ids),
                }
                for item in insight.recommended_checks
            ],
        },
        "evidence_sufficiency": (
            delivery.sufficiency.model_dump()
        ),
        "evidence": _build_evidence_payload(
            delivery
        ),
        "deterministic_precheck": {
            "status": automated_result.status.value,
            "gate_results": [
                {
                    "gate": item.gate.value,
                    "status": item.status.value,
                    "reason": item.reason,
                }
                for item in automated_result.gate_results
            ],
        },
    }


def build_business_decision_judge_messages_v2(
    *,
    golden_case: InsightGoldenCaseV2,
    delivery: EvidencePackDeliveryV2,
    automated_result: AutomatedInsightEvaluationResultV2,
) -> list[dict[str, str]]:
    context = build_business_decision_judge_context_v2(
        golden_case=golden_case,
        delivery=delivery,
        automated_result=automated_result,
    )

    return [
        {
            "role": "system",
            "content": _SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": (
                "请仅依据以下受保护 Evidence Delivery 评估业务决策质量。"
                "不得补造业务原因或外部事实。\n"
                + json.dumps(
                    context,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    default=str,
                )
            ),
        },
    ]


def parse_business_decision_judge_proposal_v2(
    raw_text: str,
) -> BusinessDecisionJudgeProposalV2:
    """
    Judge 输出必须是 exact JSON。

    不做 markdown-fence stripping，也不自动修复格式错误。
    """

    if not raw_text.strip():
        raise ValueError(
            "Business Decision Judge 返回空响应。"
        )

    try:
        proposal = (
            BusinessDecisionJudgeProposalV2
            .model_validate_json(raw_text)
        )
    except ValidationError as exc:
        raise ValueError(
            "Business Decision Judge 必须返回严格符合合同的 JSON。"
        ) from exc

    for dimension_name in _DIMENSION_NAMES:
        dimension = getattr(
            proposal,
            dimension_name,
        )

        if not _contains_cjk(
            dimension.reason
        ):
            raise ValueError(
                "Business Decision Judge 的 reason 必须使用中文："
                f"dimension={dimension_name}"
            )

    return proposal


def _validate_judge_evidence_ids_v2(
    *,
    proposal: BusinessDecisionJudgeProposalV2,
    delivery: EvidencePackDeliveryV2,
) -> None:
    available_ids = {
        record.reference.evidence_id
        for record in delivery.evidence_pack.evidence_records
    }

    for dimension_name in _DIMENSION_NAMES:
        dimension = getattr(
            proposal,
            dimension_name,
        )

        unknown_ids = (
            set(dimension.evidence_ids)
            - available_ids
        )

        if unknown_ids:
            raise ValueError(
                "Judge 引用了 Evidence Pack 中不存在的 evidence_id："
                f"dimension={dimension_name}; "
                f"unknown={sorted(unknown_ids)}"
            )

    if (
        proposal.factual_correctness.score
        != EvaluationScoreV2.FAIL
        and not proposal.factual_correctness.evidence_ids
    ):
        raise ValueError(
            "factual_correctness 为 PASS/PARTIAL 时必须引用真实 Evidence。"
        )


def materialize_business_decision_evaluation_v2(
    proposal: BusinessDecisionJudgeProposalV2,
) -> BusinessDecisionEvaluationResultV2:
    """
    overall_status 由 Day82 deterministic rule 计算，
    不接受模型自行填写。
    """

    values = {
        name: getattr(
            proposal,
            name,
        )
        for name in _DIMENSION_NAMES
    }

    overall_status = derive_overall_status_v2(
        **values
    )

    return BusinessDecisionEvaluationResultV2(
        **values,
        overall_status=overall_status,
    )


def _score_floor_result(
    *,
    golden_case: InsightGoldenCaseV2,
    evaluation: BusinessDecisionEvaluationResultV2,
) -> tuple[bool, tuple[str, ...]]:
    below: list[str] = []

    for dimension_name in _DIMENSION_NAMES:
        actual = getattr(
            evaluation,
            dimension_name,
        ).score
        floor = getattr(
            golden_case.score_floor,
            dimension_name,
        )

        if int(actual) < int(floor):
            below.append(
                dimension_name
            )

    return (
        not below,
        tuple(below),
    )


def judge_business_decision_v2(
    *,
    golden_case: InsightGoldenCaseV2,
    delivery: EvidencePackDeliveryV2,
    automated_result: AutomatedInsightEvaluationResultV2,
    model: str | None = None,
    client: Any | None = None,
    transport: Callable[..., str] | None = None,
) -> BusinessDecisionJudgeOutcomeV2:
    """
    在 deterministic pre-check 之后执行 Business Decision Judge。

    如果 Step C 已失败：
    → 不调用 LLM；
    → 不允许 Judge 覆盖结构性失败。

    如果 Step C 通过：
    → 调用 shared DeepSeek transport；
    → strict JSON parse；
    → Evidence ID validation；
    → Day82 deterministic overall status；
    → 对 Golden score floor 做确定性比较。
    """

    if (
        automated_result.status
        != (
            AutomatedInsightEvaluationStatusV2
            .READY_FOR_BUSINESS_REVIEW
        )
    ):
        return BusinessDecisionJudgeOutcomeV2(
            case_id=golden_case.case_id,
            status=(
                BusinessDecisionJudgeExecutionStatusV2
                .SKIPPED_DETERMINISTIC_FAIL
            ),
            evaluation=None,
            meets_golden_floor=None,
            below_floor_dimensions=(),
            meets_expected_overall_status=None,
            detail=(
                "Deterministic Insight Gate 未通过，"
                "Business Decision Judge 不执行。"
            ),
        )

    if automated_result.case_id != golden_case.case_id:
        raise ValueError(
            "Automated Result case_id 与 Golden Case 不一致。"
        )

    actual_transport = transport

    if actual_transport is None:
        # 生产环境默认复用项目共享 DeepSeek Transport。
        # 使用 lazy import，避免仅导入 Evaluation Contract 时
        # 就强制加载 LLM SDK。
        from app.llm.deepseek_client import chat_completion

        actual_transport = chat_completion

    raw_text = actual_transport(
        messages=build_business_decision_judge_messages_v2(
            golden_case=golden_case,
            delivery=delivery,
            automated_result=automated_result,
        ),
        temperature=0,
        model=model,
        client=client,
    )

    proposal = parse_business_decision_judge_proposal_v2(
        raw_text
    )

    _validate_judge_evidence_ids_v2(
        proposal=proposal,
        delivery=delivery,
    )

    evaluation = (
        materialize_business_decision_evaluation_v2(
            proposal
        )
    )

    (
        meets_floor,
        below_floor,
    ) = _score_floor_result(
        golden_case=golden_case,
        evaluation=evaluation,
    )

    meets_expected_overall = (
        _OVERALL_RANK[evaluation.overall_status]
        >= _OVERALL_RANK[
            golden_case.expected_overall_status
        ]
    )

    return BusinessDecisionJudgeOutcomeV2(
        case_id=golden_case.case_id,
        status=BusinessDecisionJudgeExecutionStatusV2.JUDGED,
        evaluation=evaluation,
        meets_golden_floor=meets_floor,
        below_floor_dimensions=below_floor,
        meets_expected_overall_status=meets_expected_overall,
        detail=None,
    )
