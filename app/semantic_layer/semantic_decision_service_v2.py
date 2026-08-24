from __future__ import annotations

from enum import Enum
from typing import AbstractSet

from pydantic import BaseModel, ConfigDict

from app.semantic_layer.candidate_decision_pipeline_v2 import (
    resolve_candidate_decision_v2,
)
from app.semantic_layer.candidate_decision_ranking_v2 import (
    EmbeddingRankerV2,
)
from app.semantic_layer.candidate_decision_v2 import (
    CandidateDecisionStatusV2,
)
from app.semantic_layer.question_semantic_parser_v2 import (
    LLMCall,
    QuestionSemanticParseStatusV2,
    parse_question_semantics_v2,
)


class SemanticDecisionStatusV2(str, Enum):
    MATCHED = "matched"
    NEEDS_CLARIFICATION = "needs_clarification"
    UNSUPPORTED = "unsupported"
    MULTIPLE_INTENTS = "multiple_intents"
    PARSE_FAILED = "parse_failed"
    EVIDENCE_CONFLICT = "evidence_conflict"


class SemanticDecisionResultV2(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    status: SemanticDecisionStatusV2
    parser_status: QuestionSemanticParseStatusV2
    metric_name: str | None = None
    candidates: tuple[str, ...] = ()
    ranking_applied: bool = False
    ranking_method: str | None = None
    parser_error: str | None = None
    parser_conflicts: tuple[str, ...] = ()


_CANDIDATE_STATUS_MAP = {
    CandidateDecisionStatusV2.MATCHED:
        SemanticDecisionStatusV2.MATCHED,
    CandidateDecisionStatusV2.NEEDS_CLARIFICATION:
        SemanticDecisionStatusV2.NEEDS_CLARIFICATION,
    CandidateDecisionStatusV2.UNSUPPORTED:
        SemanticDecisionStatusV2.UNSUPPORTED,
}


_PARSER_STOP_STATUS_MAP = {
    QuestionSemanticParseStatusV2.MULTIPLE_INTENTS:
        SemanticDecisionStatusV2.MULTIPLE_INTENTS,
    QuestionSemanticParseStatusV2.PARSE_FAILED:
        SemanticDecisionStatusV2.PARSE_FAILED,
    QuestionSemanticParseStatusV2.EVIDENCE_CONFLICT:
        SemanticDecisionStatusV2.EVIDENCE_CONFLICT,
}


def resolve_semantic_decision_v2(
    *,
    question: str,
    allowed_metric_names: AbstractSet[str] | None = None,
    llm_call: LLMCall | None = None,
    ranker: EmbeddingRankerV2 | None = None,
) -> SemanticDecisionResultV2:
    """
    Gate 3J unified Semantic Decision entry point.

    Order:
    Question
    -> Structured Parser
    -> stop on parser guard/failure/conflict
    -> Candidate Pipeline
       (authorization -> structural decision
        -> narrowing -> embedding ranking)
    """
    if llm_call is None:
        parsed = parse_question_semantics_v2(
            question
        )
    else:
        parsed = parse_question_semantics_v2(
            question,
            llm_call=llm_call,
        )

    if (
        parsed.status
        != QuestionSemanticParseStatusV2.PARSED
    ):
        return SemanticDecisionResultV2(
            status=_PARSER_STOP_STATUS_MAP[
                parsed.status
            ],
            parser_status=parsed.status,
            parser_error=parsed.error,
            parser_conflicts=parsed.conflicts,
        )

    if parsed.signature is None:
        raise RuntimeError(
            "PARSED result must contain a Question Semantic Signature."
        )

    decision = resolve_candidate_decision_v2(
        question=question,
        question_signature=parsed.signature,
        allowed_metric_names=allowed_metric_names,
        ranker=ranker,
    )

    return SemanticDecisionResultV2(
        status=_CANDIDATE_STATUS_MAP[
            decision.status
        ],
        parser_status=parsed.status,
        metric_name=decision.metric_name,
        candidates=decision.candidates,
        ranking_applied=decision.ranking_applied,
        ranking_method=decision.ranking_method,
    )
