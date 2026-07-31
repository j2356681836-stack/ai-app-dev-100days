from __future__ import annotations

from enum import Enum
from typing import AbstractSet, Iterable

from pydantic import BaseModel, ConfigDict

from app.semantic_layer.metric_signature_v2 import (
    MetricSemanticSignatureV2,
    SignatureOperator,
    load_metric_signature_catalog_v2,
)
from app.semantic_layer.question_signature_v2 import (
    QuestionOperator,
    QuestionSemanticSignatureV2,
)


class MetricCompatibilityV2(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    metric_name: str
    compatible: bool
    matched_fields: tuple[str, ...] = ()
    conflicting_fields: tuple[str, ...] = ()
    unresolved_fields: tuple[str, ...] = ()


_QUESTION_TO_METRIC_OPERATORS: dict[
    QuestionOperator,
    frozenset[SignatureOperator],
] = {
    QuestionOperator.SUM: frozenset(
        {SignatureOperator.SUM}
    ),
    QuestionOperator.COUNT: frozenset(
        {
            SignatureOperator.DISTINCT_COUNT,
            SignatureOperator.QUALIFIED_COUNT,
        }
    ),
    QuestionOperator.DIVIDE: frozenset(
        {SignatureOperator.DIVIDE}
    ),
}


def evaluate_metric_compatibility_v2(
    *,
    question_signature: QuestionSemanticSignatureV2,
    metric_signature: MetricSemanticSignatureV2,
) -> MetricCompatibilityV2:
    matched_fields: list[str] = []
    conflicting_fields: list[str] = []
    unresolved_fields: list[str] = []

    if question_signature.operator is None:
        unresolved_fields.append("operator")
    else:
        allowed = _QUESTION_TO_METRIC_OPERATORS[
            question_signature.operator
        ]
        if metric_signature.operator in allowed:
            matched_fields.append("operator")
        else:
            conflicting_fields.append("operator")

    if question_signature.left_operand is None:
        unresolved_fields.append("left_operand")
    elif question_signature.left_operand == metric_signature.left_operand:
        matched_fields.append("left_operand")
    else:
        conflicting_fields.append("left_operand")

    if question_signature.right_operand is None:
        unresolved_fields.append("right_operand")
    elif question_signature.right_operand == metric_signature.right_operand:
        matched_fields.append("right_operand")
    else:
        conflicting_fields.append("right_operand")

    question_qualifiers = set(question_signature.qualifiers)
    metric_qualifiers = set(metric_signature.qualifiers)

    if not question_qualifiers:
        unresolved_fields.append("qualifiers")
    elif question_qualifiers.issubset(metric_qualifiers):
        matched_fields.append("qualifiers")
    else:
        conflicting_fields.append("qualifiers")

    # 暂不把 intrinsic_partition 当作 hard conflict。
    if question_signature.intrinsic_partition is None:
        unresolved_fields.append("intrinsic_partition")
    elif question_signature.intrinsic_partition == metric_signature.intrinsic_partition:
        matched_fields.append("intrinsic_partition")
    else:
        unresolved_fields.append("intrinsic_partition")

    return MetricCompatibilityV2(
        metric_name=metric_signature.metric_name,
        compatible=not conflicting_fields,
        matched_fields=tuple(matched_fields),
        conflicting_fields=tuple(conflicting_fields),
        unresolved_fields=tuple(unresolved_fields),
    )

class CandidateDecisionStatusV2(str, Enum):
    MATCHED = "matched"
    NEEDS_CLARIFICATION = "needs_clarification"
    UNSUPPORTED = "unsupported"


class CandidateDecisionV2(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    status: CandidateDecisionStatusV2
    metric_name: str | None = None
    candidates: tuple[str, ...] = ()
    method: str = "structural_compatibility_v2"


def build_structural_candidate_pool_v2(
    *,
    question_signature: QuestionSemanticSignatureV2,
    metric_signatures: Iterable[MetricSemanticSignatureV2],
    allowed_metric_names: AbstractSet[str] | None = None,
) -> tuple[MetricCompatibilityV2, ...]:
    """
    Apply authorization filtering before structural compatibility.
    """
    authorized_signatures = [
        signature
        for signature in metric_signatures
        if (
            allowed_metric_names is None
            or signature.metric_name in allowed_metric_names
        )
    ]

    results = [
        evaluate_metric_compatibility_v2(
            question_signature=question_signature,
            metric_signature=signature,
        )
        for signature in authorized_signatures
    ]

    return tuple(
        sorted(
            results,
            key=lambda item: item.metric_name,
        )
    )


def decide_metric_candidate_from_signatures_v2(
    *,
    question_signature: QuestionSemanticSignatureV2,
    metric_signatures: Iterable[MetricSemanticSignatureV2],
    allowed_metric_names: AbstractSet[str] | None = None,
) -> CandidateDecisionV2:
    compatibility = build_structural_candidate_pool_v2(
        question_signature=question_signature,
        metric_signatures=metric_signatures,
        allowed_metric_names=allowed_metric_names,
    )

    compatible_names = tuple(
        item.metric_name
        for item in compatibility
        if item.compatible
    )

    if not compatible_names:
        return CandidateDecisionV2(
            status=CandidateDecisionStatusV2.UNSUPPORTED,
            metric_name=None,
            candidates=(),
        )

    if len(compatible_names) == 1:
        return CandidateDecisionV2(
            status=CandidateDecisionStatusV2.MATCHED,
            metric_name=compatible_names[0],
            candidates=compatible_names,
        )

    return CandidateDecisionV2(
        status=CandidateDecisionStatusV2.NEEDS_CLARIFICATION,
        metric_name=None,
        candidates=compatible_names,
    )


def decide_metric_candidate_v2(
    *,
    question_signature: QuestionSemanticSignatureV2,
    allowed_metric_names: AbstractSet[str] | None = None,
) -> CandidateDecisionV2:
    catalog = load_metric_signature_catalog_v2()

    return decide_metric_candidate_from_signatures_v2(
        question_signature=question_signature,
        metric_signatures=catalog.signatures,
        allowed_metric_names=allowed_metric_names,
    )

