from __future__ import annotations

from typing import Any, Callable

from pydantic import BaseModel, ConfigDict

from app.semantic_layer.candidate_decision_v2 import (
    CandidateDecisionStatusV2,
    CandidateDecisionV2,
)


EmbeddingRankerV2 = Callable[..., dict[str, Any]]


def _resolve_default_embedding_ranker_v2() -> EmbeddingRankerV2:
    """
    仅在确实需要 Embedding Ranking 时加载本地实现。

    普通 MATCHED / UNSUPPORTED / 页面启动路径不会因为模块导入
    提前加载 sentence-transformers / torch。
    """

    from app.semantic_layer.metric_semantic_search_v2 import (
        rank_metric_candidates_by_embedding_v2,
    )

    return rank_metric_candidates_by_embedding_v2


class RankedCandidateDecisionV2(BaseModel):
    """
    Candidate Decision + embedding ranking evidence.

    Embedding is allowed to reorder clarification candidates only.
    It must never change MATCHED / NEEDS_CLARIFICATION / UNSUPPORTED.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    status: CandidateDecisionStatusV2
    metric_name: str | None = None
    candidates: tuple[str, ...] = ()
    ranking_applied: bool
    ranking_method: str | None = None


def apply_embedding_ranking_v2(
    *,
    question: str,
    decision: CandidateDecisionV2,
    ranker: EmbeddingRankerV2 | None = None,
) -> RankedCandidateDecisionV2:
    """
    Use embedding as ranking evidence only.

    Rules:
    - MATCHED: keep the matched metric; do not call embedding.
    - UNSUPPORTED: keep unsupported; do not call embedding.
    - NEEDS_CLARIFICATION: embedding may reorder only the already-compatible
      candidate names. It cannot add candidates or turn clarification into
      matched.
    """
    if (
        decision.status
        != CandidateDecisionStatusV2.NEEDS_CLARIFICATION
    ):
        return RankedCandidateDecisionV2(
            status=decision.status,
            metric_name=decision.metric_name,
            candidates=decision.candidates,
            ranking_applied=False,
            ranking_method=None,
        )

    allowed_names = set(
        decision.candidates
    )

    if not allowed_names:
        return RankedCandidateDecisionV2(
            status=decision.status,
            metric_name=None,
            candidates=(),
            ranking_applied=False,
            ranking_method=None,
        )

    if ranker is None:
        ranker = _resolve_default_embedding_ranker_v2()

    result = ranker(
        question,
        allowed_metric_names=allowed_names,
        top_k=len(allowed_names),
    )

    ranked_names: list[str] = []

    for item in result.get(
        "candidates",
        [],
    ):
        name = item.get(
            "name"
        )

        if (
            name in allowed_names
            and name not in ranked_names
        ):
            ranked_names.append(
                name
            )

    for name in decision.candidates:
        if name not in ranked_names:
            ranked_names.append(
                name
            )

    return RankedCandidateDecisionV2(
        status=decision.status,
        metric_name=None,
        candidates=tuple(
            ranked_names
        ),
        ranking_applied=True,
        ranking_method=(
            str(
                result.get(
                    "method",
                    "embedding_v2",
                )
            )
        ),
    )
