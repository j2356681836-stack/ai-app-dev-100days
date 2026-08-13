from __future__ import annotations

from decimal import Decimal
from enum import Enum

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from app.semantic_layer.time_comparison_contract_v2 import (
    ComparisonTypeV2,
    TimeComparisonContractV2,
)


class AnomalyChangeTypeV2(str, Enum):
    ABSOLUTE = "absolute"
    RELATIVE = "relative"


class AnomalyDirectionV2(str, Enum):
    INCREASE = "increase"
    DECREASE = "decrease"
    BOTH = "both"


class AnomalyDecisionStatusV2(str, Enum):
    ANOMALY = "anomaly"
    NORMAL = "normal"
    INSUFFICIENT_SAMPLE = "insufficient_sample"
    NOT_COMPARABLE = "not_comparable"
    POLICY_NOT_FOUND = "policy_not_found"


class AnomalyDecisionReasonV2(str, Enum):
    THRESHOLD_REACHED = "threshold_reached"
    BELOW_THRESHOLD = "below_threshold"
    DIRECTION_NOT_TRIGGERED = "direction_not_triggered"
    INSUFFICIENT_SAMPLE = "insufficient_sample"
    RELATIVE_CHANGE_UNDEFINED = "relative_change_undefined"
    POLICY_NOT_FOUND = "policy_not_found"


class AnomalyPolicyV2(BaseModel):
    """
    Deterministic anomaly policy for one metric + comparison type.

    Threshold values are configuration/business-policy inputs.
    They are not selected by the LLM inside the detector.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    metric_name: str
    comparison_type: ComparisonTypeV2

    change_type: AnomalyChangeTypeV2
    direction: AnomalyDirectionV2
    threshold_value: Decimal = Field(gt=Decimal("0"))

    sample_metric_name: str
    minimum_sample_value: Decimal = Field(gt=Decimal("0"))

    policy_version: str

    @model_validator(mode="after")
    def validate_policy(self) -> "AnomalyPolicyV2":
        for field_name, value in (
            ("metric_name", self.metric_name),
            ("sample_metric_name", self.sample_metric_name),
            ("policy_version", self.policy_version),
        ):
            if not value.strip():
                raise ValueError(
                    f"{field_name} cannot be empty."
                )

        return self


class AnomalyDecisionV2(BaseModel):
    """
    Structured Day83 anomaly evidence.

    It records:
    - the trusted comparison context;
    - current/reference values;
    - absolute/relative change;
    - sample evidence;
    - the exact deterministic policy used;
    - the final decision and reason.

    It does not explain business causes.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    evidence_id: str

    metric_name: str
    comparison: TimeComparisonContractV2

    current_value: Decimal
    reference_value: Decimal

    absolute_change: Decimal
    relative_change: Decimal | None

    current_sample_value: Decimal = Field(ge=Decimal("0"))
    reference_sample_value: Decimal = Field(ge=Decimal("0"))

    policy: AnomalyPolicyV2 | None = None

    status: AnomalyDecisionStatusV2
    reason_code: AnomalyDecisionReasonV2

    @model_validator(mode="after")
    def validate_decision(self) -> "AnomalyDecisionV2":
        if not self.evidence_id.strip():
            raise ValueError(
                "evidence_id cannot be empty."
            )

        if not self.metric_name.strip():
            raise ValueError(
                "metric_name cannot be empty."
            )

        if (
            self.status
            == AnomalyDecisionStatusV2.POLICY_NOT_FOUND
        ):
            if self.policy is not None:
                raise ValueError(
                    "POLICY_NOT_FOUND cannot carry a policy."
                )

            if (
                self.reason_code
                != AnomalyDecisionReasonV2.POLICY_NOT_FOUND
            ):
                raise ValueError(
                    "POLICY_NOT_FOUND requires matching reason_code."
                )

            return self

        if self.policy is None:
            raise ValueError(
                "Non-POLICY_NOT_FOUND decisions require a policy."
            )

        if self.policy.metric_name != self.metric_name:
            raise ValueError(
                "Decision metric_name must match policy metric_name."
            )

        if (
            self.policy.comparison_type
            != self.comparison.comparison_type
        ):
            raise ValueError(
                "Decision comparison type must match policy."
            )

        if (
            self.status
            == AnomalyDecisionStatusV2.NOT_COMPARABLE
        ):
            if (
                self.reason_code
                != AnomalyDecisionReasonV2
                .RELATIVE_CHANGE_UNDEFINED
            ):
                raise ValueError(
                    "NOT_COMPARABLE requires "
                    "RELATIVE_CHANGE_UNDEFINED."
                )

            if self.relative_change is not None:
                raise ValueError(
                    "Undefined relative comparison cannot "
                    "expose relative_change."
                )

        if (
            self.status
            == AnomalyDecisionStatusV2.INSUFFICIENT_SAMPLE
            and self.reason_code
            != AnomalyDecisionReasonV2.INSUFFICIENT_SAMPLE
        ):
            raise ValueError(
                "INSUFFICIENT_SAMPLE requires matching reason_code."
            )

        if self.status == AnomalyDecisionStatusV2.ANOMALY:
            if (
                self.reason_code
                != AnomalyDecisionReasonV2.THRESHOLD_REACHED
            ):
                raise ValueError(
                    "ANOMALY requires THRESHOLD_REACHED."
                )

        if self.status == AnomalyDecisionStatusV2.NORMAL:
            if self.reason_code not in {
                AnomalyDecisionReasonV2.BELOW_THRESHOLD,
                AnomalyDecisionReasonV2.DIRECTION_NOT_TRIGGERED,
            }:
                raise ValueError(
                    "NORMAL requires a non-trigger reason."
                )

        return self


def _calculate_changes(
    *,
    current_value: Decimal,
    reference_value: Decimal,
) -> tuple[Decimal, Decimal | None]:
    absolute_change = current_value - reference_value

    if reference_value == 0:
        relative_change = None
    else:
        relative_change = (
            current_value - reference_value
        ) / reference_value

    return absolute_change, relative_change


def _direction_triggered(
    *,
    change: Decimal,
    direction: AnomalyDirectionV2,
) -> bool:
    if direction == AnomalyDirectionV2.INCREASE:
        return change > 0

    if direction == AnomalyDirectionV2.DECREASE:
        return change < 0

    return change != 0


def _threshold_reached(
    *,
    change: Decimal,
    direction: AnomalyDirectionV2,
    threshold: Decimal,
) -> bool:
    if direction == AnomalyDirectionV2.INCREASE:
        return change >= threshold

    if direction == AnomalyDirectionV2.DECREASE:
        return change <= -threshold

    return abs(change) >= threshold


def detect_anomaly_v2(
    *,
    evidence_id: str,
    metric_name: str,
    comparison: TimeComparisonContractV2,
    current_value: Decimal,
    reference_value: Decimal,
    current_sample_value: Decimal,
    reference_sample_value: Decimal,
    policy: AnomalyPolicyV2 | None,
) -> AnomalyDecisionV2:
    """
    Deterministic Day83 anomaly detector.

    Ordering:
    1. exact policy availability / binding;
    2. change calculation;
    3. mathematical comparability;
    4. minimum-sample-value gate for both windows;
    5. direction gate;
    6. deterministic threshold gate.
    """

    if not metric_name.strip():
        raise ValueError(
            "metric_name cannot be empty."
        )

    if current_sample_value < 0:
        raise ValueError(
            "current_sample_value cannot be negative."
        )

    if reference_sample_value < 0:
        raise ValueError(
            "reference_sample_value cannot be negative."
        )

    absolute_change, relative_change = _calculate_changes(
        current_value=current_value,
        reference_value=reference_value,
    )

    if policy is None:
        return AnomalyDecisionV2(
            evidence_id=evidence_id,
            metric_name=metric_name,
            comparison=comparison,
            current_value=current_value,
            reference_value=reference_value,
            absolute_change=absolute_change,
            relative_change=relative_change,
            current_sample_value=current_sample_value,
            reference_sample_value=reference_sample_value,
            policy=None,
            status=(
                AnomalyDecisionStatusV2.POLICY_NOT_FOUND
            ),
            reason_code=(
                AnomalyDecisionReasonV2.POLICY_NOT_FOUND
            ),
        )

    if policy.metric_name != metric_name:
        raise ValueError(
            "Policy metric_name does not match detector metric_name."
        )

    if (
        policy.comparison_type
        != comparison.comparison_type
    ):
        raise ValueError(
            "Policy comparison_type does not match "
            "the comparison contract."
        )

    if (
        policy.change_type
        == AnomalyChangeTypeV2.RELATIVE
        and relative_change is None
    ):
        return AnomalyDecisionV2(
            evidence_id=evidence_id,
            metric_name=metric_name,
            comparison=comparison,
            current_value=current_value,
            reference_value=reference_value,
            absolute_change=absolute_change,
            relative_change=None,
            current_sample_value=current_sample_value,
            reference_sample_value=reference_sample_value,
            policy=policy,
            status=(
                AnomalyDecisionStatusV2.NOT_COMPARABLE
            ),
            reason_code=(
                AnomalyDecisionReasonV2
                .RELATIVE_CHANGE_UNDEFINED
            ),
        )

    if (
        current_sample_value < policy.minimum_sample_value
        or reference_sample_value < policy.minimum_sample_value
    ):
        return AnomalyDecisionV2(
            evidence_id=evidence_id,
            metric_name=metric_name,
            comparison=comparison,
            current_value=current_value,
            reference_value=reference_value,
            absolute_change=absolute_change,
            relative_change=relative_change,
            current_sample_value=current_sample_value,
            reference_sample_value=reference_sample_value,
            policy=policy,
            status=(
                AnomalyDecisionStatusV2
                .INSUFFICIENT_SAMPLE
            ),
            reason_code=(
                AnomalyDecisionReasonV2
                .INSUFFICIENT_SAMPLE
            ),
        )

    evaluated_change = (
        absolute_change
        if policy.change_type
        == AnomalyChangeTypeV2.ABSOLUTE
        else relative_change
    )

    if evaluated_change is None:
        raise AssertionError(
            "Comparable policy must expose evaluated change."
        )

    if not _direction_triggered(
        change=evaluated_change,
        direction=policy.direction,
    ):
        return AnomalyDecisionV2(
            evidence_id=evidence_id,
            metric_name=metric_name,
            comparison=comparison,
            current_value=current_value,
            reference_value=reference_value,
            absolute_change=absolute_change,
            relative_change=relative_change,
            current_sample_value=current_sample_value,
            reference_sample_value=reference_sample_value,
            policy=policy,
            status=AnomalyDecisionStatusV2.NORMAL,
            reason_code=(
                AnomalyDecisionReasonV2
                .DIRECTION_NOT_TRIGGERED
            ),
        )

    if _threshold_reached(
        change=evaluated_change,
        direction=policy.direction,
        threshold=policy.threshold_value,
    ):
        status = AnomalyDecisionStatusV2.ANOMALY
        reason = (
            AnomalyDecisionReasonV2.THRESHOLD_REACHED
        )
    else:
        status = AnomalyDecisionStatusV2.NORMAL
        reason = (
            AnomalyDecisionReasonV2.BELOW_THRESHOLD
        )

    return AnomalyDecisionV2(
        evidence_id=evidence_id,
        metric_name=metric_name,
        comparison=comparison,
        current_value=current_value,
        reference_value=reference_value,
        absolute_change=absolute_change,
        relative_change=relative_change,
        current_sample_value=current_sample_value,
        reference_sample_value=reference_sample_value,
        policy=policy,
        status=status,
        reason_code=reason,
    )
