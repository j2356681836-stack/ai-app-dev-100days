from __future__ import annotations

from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.semantic_layer.time_comparison_contract_v2 import (
    TimeComparisonContractV2,
)


class ContributionDecompositionTypeV2(str, Enum):
    ADDITIVE = "additive"


class ContributionDirectionV2(str, Enum):
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    POSITIVE = "positive"


class ContributionReconciliationStatusV2(str, Enum):
    RECONCILED = "reconciled"
    NOT_RECONCILED = "not_reconciled"


class ContributionObservationV2(BaseModel):
    """
    One governed, releasable dimension-member observation.

    The Day84 core must receive only results that have already passed the
    existing authorization, scope, execution, and result-protection chain.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    member_key: str
    member_label: str
    value: Decimal

    @model_validator(mode="after")
    def validate_observation(self) -> "ContributionObservationV2":
        if not self.member_key.strip():
            raise ValueError("member_key cannot be empty.")
        if not self.member_label.strip():
            raise ValueError("member_label cannot be empty.")
        return self


class ContributionMemberResultV2(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    member_key: str
    member_label: str
    current_value: Decimal
    reference_value: Decimal
    delta: Decimal
    contribution_rate: Decimal | None
    direction: ContributionDirectionV2


class ContributionAnalysisResultV2(BaseModel):
    """
    Deterministic additive contribution decomposition.

    contribution_rate = member_delta / overall_delta.
    It may be greater than 1 or less than 0 when member changes offset each
    other. A zero overall delta makes contribution_rate undefined, so the
    per-member rate is None while member deltas remain available.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    metric_name: str
    dimension_name: str
    decomposition_type: ContributionDecompositionTypeV2
    comparison: TimeComparisonContractV2

    current_overall_value: Decimal
    reference_overall_value: Decimal
    overall_delta: Decimal

    members: tuple[ContributionMemberResultV2, ...]
    negative_change_ranking: tuple[str, ...]
    positive_change_ranking: tuple[str, ...]

    sum_member_delta: Decimal
    unexplained_remainder: Decimal
    reconciliation_tolerance: Decimal = Field(ge=Decimal("0"))
    reconciliation_status: ContributionReconciliationStatusV2


_SUPPORTED_ADDITIVE_PAIRS_V2 = frozenset({("gmv", "channel")})


def _normalize_name(value: str, *, field_name: str) -> str:
    normalized = value.strip().lower()
    if not normalized:
        raise ValueError(f"{field_name} cannot be empty.")
    return normalized


def _index_observations(
    observations: tuple[ContributionObservationV2, ...],
    *,
    side: str,
) -> dict[str, ContributionObservationV2]:
    indexed: dict[str, ContributionObservationV2] = {}

    for observation in observations:
        if observation.member_key in indexed:
            raise ValueError(
                f"Duplicate {side} member_key: {observation.member_key}"
            )
        indexed[observation.member_key] = observation

    return indexed


def _direction(delta: Decimal) -> ContributionDirectionV2:
    if delta < 0:
        return ContributionDirectionV2.NEGATIVE
    if delta > 0:
        return ContributionDirectionV2.POSITIVE
    return ContributionDirectionV2.NEUTRAL


def analyze_additive_contribution_v2(
    *,
    metric_name: str,
    dimension_name: str,
    comparison: TimeComparisonContractV2,
    current_overall_value: Decimal,
    reference_overall_value: Decimal,
    current_members: tuple[ContributionObservationV2, ...],
    reference_members: tuple[ContributionObservationV2, ...],
    reconciliation_tolerance: Decimal = Decimal("0.01"),
) -> ContributionAnalysisResultV2:
    """
    Analyze one additive Metric × Dimension pair.

    Preconditions:
    - current/reference overall and dimension results use the same effective
      authorization scope;
    - all supplied observations are governed, releasable evidence;
    - successful dimension result sets are complete, not partially redacted.

    Day84 Step A intentionally supports only GMV × channel. Unsupported metric
    semantics fail closed instead of silently applying additive math.
    """

    metric = _normalize_name(metric_name, field_name="metric_name")
    dimension = _normalize_name(
        dimension_name,
        field_name="dimension_name",
    )

    if (metric, dimension) not in _SUPPORTED_ADDITIVE_PAIRS_V2:
        raise ValueError(
            "Unsupported additive contribution pair: "
            f"metric={metric}, dimension={dimension}."
        )

    if reconciliation_tolerance < 0:
        raise ValueError("reconciliation_tolerance cannot be negative.")

    current_by_key = _index_observations(
        current_members,
        side="current",
    )
    reference_by_key = _index_observations(
        reference_members,
        side="reference",
    )

    member_keys = sorted(set(current_by_key) | set(reference_by_key))
    overall_delta = current_overall_value - reference_overall_value

    member_results: list[ContributionMemberResultV2] = []

    for member_key in member_keys:
        current = current_by_key.get(member_key)
        reference = reference_by_key.get(member_key)

        if current is not None and reference is not None:
            if current.member_label != reference.member_label:
                raise ValueError(
                    "Member label changed across comparison windows for "
                    f"member_key={member_key}: "
                    f"current={current.member_label!r}, "
                    f"reference={reference.member_label!r}."
                )
            member_label = current.member_label
        elif current is not None:
            member_label = current.member_label
        elif reference is not None:
            member_label = reference.member_label
        else:  # pragma: no cover - impossible after union construction
            raise RuntimeError("Unreachable member alignment state.")

        current_value = (
            current.value if current is not None else Decimal("0")
        )
        reference_value = (
            reference.value if reference is not None else Decimal("0")
        )
        delta = current_value - reference_value

        contribution_rate = (
            None if overall_delta == 0 else delta / overall_delta
        )

        member_results.append(
            ContributionMemberResultV2(
                member_key=member_key,
                member_label=member_label,
                current_value=current_value,
                reference_value=reference_value,
                delta=delta,
                contribution_rate=contribution_rate,
                direction=_direction(delta),
            )
        )

    sum_member_delta = sum(
        (member.delta for member in member_results),
        Decimal("0"),
    )
    unexplained_remainder = overall_delta - sum_member_delta

    reconciliation_status = (
        ContributionReconciliationStatusV2.RECONCILED
        if abs(unexplained_remainder) <= reconciliation_tolerance
        else ContributionReconciliationStatusV2.NOT_RECONCILED
    )

    negative_change_ranking = tuple(
        member.member_key
        for member in sorted(
            (
                item
                for item in member_results
                if item.direction == ContributionDirectionV2.NEGATIVE
            ),
            key=lambda item: (item.delta, item.member_key),
        )
    )
    positive_change_ranking = tuple(
        member.member_key
        for member in sorted(
            (
                item
                for item in member_results
                if item.direction == ContributionDirectionV2.POSITIVE
            ),
            key=lambda item: (-item.delta, item.member_key),
        )
    )

    return ContributionAnalysisResultV2(
        metric_name=metric,
        dimension_name=dimension,
        decomposition_type=ContributionDecompositionTypeV2.ADDITIVE,
        comparison=comparison,
        current_overall_value=current_overall_value,
        reference_overall_value=reference_overall_value,
        overall_delta=overall_delta,
        members=tuple(member_results),
        negative_change_ranking=negative_change_ranking,
        positive_change_ranking=positive_change_ranking,
        sum_member_delta=sum_member_delta,
        unexplained_remainder=unexplained_remainder,
        reconciliation_tolerance=reconciliation_tolerance,
        reconciliation_status=reconciliation_status,
    )
