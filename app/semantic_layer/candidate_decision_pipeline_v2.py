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
    decide_metric_candidate_v2,
)
from app.semantic_layer.metric_semantic_search_v2 import (
    rank_metric_candidates_by_embedding_v2,
)
from app.semantic_layer.question_signature_v2 import (
    QuestionSemanticSignatureV2,
)


def resolve_candidate_decision_v2(
    *,
    question: str,
    question_signature: QuestionSemanticSignatureV2,
    allowed_metric_names: AbstractSet[str] | None = None,
    ranker: EmbeddingRankerV2 = (
        rank_metric_candidates_by_embedding_v2
    ),
) -> RankedCandidateDecisionV2:
    """
    Gate 3H unified Candidate Decision entry point.

    Required order:
    1. authorization-aware structural decision;
    2. clarification candidate narrowing;
    3. embedding ranking evidence.

    This function deliberately starts from a frozen Question Signature.
    Parser orchestration and Graph integration remain outside this gate.
    """
    structural_decision = decide_metric_candidate_v2(
        question_signature=question_signature,
        allowed_metric_names=allowed_metric_names,
    )

    narrowed_decision = narrow_clarification_candidates_v2(
        question=question,
        decision=structural_decision,
    )

    return apply_embedding_ranking_v2(
        question=question,
        decision=narrowed_decision,
        ranker=ranker,
    )
