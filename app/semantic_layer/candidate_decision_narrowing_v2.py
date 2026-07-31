from __future__ import annotations

from app.semantic_layer.candidate_decision_v2 import (
    CandidateDecisionStatusV2,
    CandidateDecisionV2,
)


GATE3G_NARROWING_VERSION = "gate3g_generic_average_consumption_1"


_GENERIC_NEW_CUSTOMER_CANDIDATES = (
    "brand_paid_new_customer_count",
    "channel_paid_new_customer_count",
)

_GENERIC_AVERAGE_CONSUMPTION_CANDIDATES = (
    "spending_per_buyer",
    "aus",
)


def _keep_existing_candidates(
    *,
    preferred_candidates: tuple[str, ...],
    decision: CandidateDecisionV2,
) -> tuple[str, ...]:
    """
    Keep only candidates that already exist in the structural pool.
    Narrowing must never invent a metric.
    """
    return tuple(
        metric_name
        for metric_name in preferred_candidates
        if metric_name in decision.candidates
    )


def narrow_clarification_candidates_v2(
    *,
    question: str,
    decision: CandidateDecisionV2,
) -> CandidateDecisionV2:
    """
    Narrow clarification candidates only with reliable family-level evidence.

    Current rules:
    1. Generic "新客" without brand/channel/platform qualification
       -> brand new + channel new.
    2. Generic "平均消费"
       -> spending per buyer + average order value.

    This layer must not:
    - modify MATCHED / UNSUPPORTED decisions;
    - invent candidates outside the structural pool;
    - turn clarification into matched.
    """
    if (
        decision.status
        != CandidateDecisionStatusV2.NEEDS_CLARIFICATION
    ):
        return decision

    text = str(question).strip()

    is_generic_new_customer = (
        "新客" in text
        and "品牌" not in text
        and "渠道" not in text
        and "平台" not in text
    )

    if is_generic_new_customer:
        narrowed_candidates = _keep_existing_candidates(
            preferred_candidates=(
                _GENERIC_NEW_CUSTOMER_CANDIDATES
            ),
            decision=decision,
        )

        if narrowed_candidates:
            return decision.model_copy(
                update={
                    "candidates": narrowed_candidates,
                }
            )

    is_generic_average_consumption = (
        "平均" in text
        and "消费" in text
    )

    if is_generic_average_consumption:
        narrowed_candidates = _keep_existing_candidates(
            preferred_candidates=(
                _GENERIC_AVERAGE_CONSUMPTION_CANDIDATES
            ),
            decision=decision,
        )

        if narrowed_candidates:
            return decision.model_copy(
                update={
                    "candidates": narrowed_candidates,
                }
            )

    return decision
