from __future__ import annotations

from typing import AbstractSet

from app.semantic_layer.candidate_decision_narrowing_v2 import (
    narrow_clarification_candidates_v2,
)
from app.semantic_layer.candidate_decision_ranking_v2 import (
    EmbeddingRankerV2,
    RankedCandidateDecisionV2,
    apply_embedding_ranking_v2,
)
from app.semantic_layer.candidate_decision_v2 import (
    CandidateDecisionStatusV2,
    CandidateDecisionV2,
    decide_metric_candidate_v2,
)
from app.semantic_layer.metric_loader_v2 import (
    search_metric_candidates_v2,
)
from app.semantic_layer.question_signature_v2 import (
    QuestionSemanticSignatureV2,
)


def _apply_explicit_metric_grounding_v2(
    *,
    question: str,
    decision: CandidateDecisionV2,
) -> CandidateDecisionV2:
    """
    使用 Metadata 中已经存在的正式 Metric name / chinese_name / aliases，
    对“结构上仍需澄清”的候选做一次确定性身份收窄。

    设计边界：
    1. 只处理 NEEDS_CLARIFICATION；
    2. 只接受唯一的 deterministic Metric Rule Baseline 命中；
    3. 命中的 Metric 必须已经存在于 structural candidate pool；
    4. 不创建新候选；
    5. 不覆盖已经 MATCHED / UNSUPPORTED 的结构判断；
    6. Grounding 成功后不再调用 Embedding。
    """
    if (
        decision.status
        != CandidateDecisionStatusV2.NEEDS_CLARIFICATION
    ):
        return decision

    explicit_matches = search_metric_candidates_v2(
        question
    )

    if len(explicit_matches) != 1:
        return decision

    metric_name = str(
        explicit_matches[0]["name"]
    )

    if metric_name not in decision.candidates:
        return decision

    return decision.model_copy(
        update={
            "status": CandidateDecisionStatusV2.MATCHED,
            "metric_name": metric_name,
            "candidates": (metric_name,),
            "method": (
                "structural_compatibility_v2"
                "+explicit_metric_grounding_v2"
            ),
        }
    )


def resolve_candidate_decision_v2(
    *,
    question: str,
    question_signature: QuestionSemanticSignatureV2,
    allowed_metric_names: AbstractSet[str] | None = None,
    ranker: EmbeddingRankerV2 | None = None,
) -> RankedCandidateDecisionV2:
    """
    Gate 3H unified Candidate Decision entry point.

    Required order:
    1. authorization-aware structural decision;
    2. explicit Metric / Alias deterministic grounding;
    3. clarification candidate narrowing;
    4. embedding ranking evidence.

    Explicit grounding 的职责非常窄：
    - 只解决“结构候选已经合法，但 Live Parser 信息不足”的 clarification；
    - 只使用 Metadata 正式 name / chinese_name / aliases；
    - 不能绕过 Authorization；
    - 不能覆盖 structural conflict；
    - 不能把 Embedding top1 当成 MATCHED。
    """
    structural_decision = decide_metric_candidate_v2(
        question_signature=question_signature,
        allowed_metric_names=allowed_metric_names,
    )

    grounded_decision = (
        _apply_explicit_metric_grounding_v2(
            question=question,
            decision=structural_decision,
        )
    )

    narrowed_decision = narrow_clarification_candidates_v2(
        question=question,
        decision=grounded_decision,
    )

    return apply_embedding_ranking_v2(
        question=question,
        decision=narrowed_decision,
        ranker=ranker,
    )
