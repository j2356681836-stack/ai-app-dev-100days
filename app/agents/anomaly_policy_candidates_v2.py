from __future__ import annotations

from decimal import Decimal
from enum import Enum

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from app.agents.anomaly_detection_v2 import (
    AnomalyChangeTypeV2,
    AnomalyDirectionV2,
    AnomalyPolicyV2,
)
from app.semantic_layer.time_comparison_contract_v2 import (
    ComparisonTypeV2,
)


class AnomalyPolicyCandidateStatusV2(str, Enum):
    TBD_CALIBRATION = "tbd_calibration"
    ACTIVE = "active"
    REJECTED = "rejected"


class AnomalyPolicySourceV2(str, Enum):
    METADATA_DEFINITION = "metadata_definition"
    DATASET_MANIFEST = "dataset_manifest"
    DATASET_ACCEPTANCE = "dataset_acceptance"
    BUSINESS_RULE = "business_rule"
    HISTORICAL_CALIBRATION = "historical_calibration"
    HUMAN_CALIBRATION = "human_calibration"


class AnomalyPolicyCandidateV2(BaseModel):
    """
    Design/calibration state for one metric + comparison type.

    A candidate is not executable merely because it exists.

    Only an ACTIVE candidate with a complete threshold, sample basis,
    minimum sample value, and policy version can be promoted to the
    runtime AnomalyPolicyV2 used by the deterministic detector.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    candidate_id: str

    metric_name: str
    comparison_type: ComparisonTypeV2
    change_type: AnomalyChangeTypeV2
    direction: AnomalyDirectionV2

    sample_metric_name: str | None = None
    minimum_sample_candidate: Decimal | None = Field(
        default=None,
        gt=Decimal("0"),
    )
    threshold_candidate: Decimal | None = Field(
        default=None,
        gt=Decimal("0"),
    )

    policy_sources: tuple[AnomalyPolicySourceV2, ...]
    evidence_references: tuple[str, ...]

    status: AnomalyPolicyCandidateStatusV2
    active_policy_version: str | None = None

    calibration_notes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_candidate(
        self,
    ) -> "AnomalyPolicyCandidateV2":
        for field_name, value in (
            ("candidate_id", self.candidate_id),
            ("metric_name", self.metric_name),
        ):
            if not value.strip():
                raise ValueError(
                    f"{field_name} cannot be empty."
                )

        if not self.policy_sources:
            raise ValueError(
                "policy_sources cannot be empty."
            )

        if not self.evidence_references:
            raise ValueError(
                "evidence_references cannot be empty."
            )

        if any(
            not reference.strip()
            for reference in self.evidence_references
        ):
            raise ValueError(
                "evidence_references cannot contain empty values."
            )

        if (
            self.sample_metric_name is not None
            and not self.sample_metric_name.strip()
        ):
            raise ValueError(
                "sample_metric_name cannot be blank."
            )

        if (
            self.active_policy_version is not None
            and not self.active_policy_version.strip()
        ):
            raise ValueError(
                "active_policy_version cannot be blank."
            )

        if (
            self.status
            == AnomalyPolicyCandidateStatusV2.ACTIVE
        ):
            required_values = {
                "sample_metric_name": self.sample_metric_name,
                "minimum_sample_candidate":
                    self.minimum_sample_candidate,
                "threshold_candidate":
                    self.threshold_candidate,
                "active_policy_version":
                    self.active_policy_version,
            }

            missing = [
                name
                for name, value in required_values.items()
                if value is None
            ]

            if missing:
                raise ValueError(
                    "ACTIVE candidate is incomplete: "
                    + ", ".join(missing)
                )

        elif self.active_policy_version is not None:
            raise ValueError(
                "Only ACTIVE candidates may carry "
                "active_policy_version."
            )

        return self

    def to_active_policy_v2(
        self,
    ) -> AnomalyPolicyV2:
        if (
            self.status
            != AnomalyPolicyCandidateStatusV2.ACTIVE
        ):
            raise ValueError(
                "Only ACTIVE candidates can be promoted "
                "to AnomalyPolicyV2."
            )

        if (
            self.sample_metric_name is None
            or self.minimum_sample_candidate is None
            or self.threshold_candidate is None
            or self.active_policy_version is None
        ):
            raise ValueError(
                "ACTIVE candidate is incomplete."
            )

        return AnomalyPolicyV2(
            metric_name=self.metric_name,
            comparison_type=self.comparison_type,
            change_type=self.change_type,
            direction=self.direction,
            threshold_value=self.threshold_candidate,
            sample_metric_name=self.sample_metric_name,
            minimum_sample_value=(
                self.minimum_sample_candidate
            ),
            policy_version=self.active_policy_version,
        )


DAY83_TIER_A_POLICY_CANDIDATES_V2 = (
    AnomalyPolicyCandidateV2(
        candidate_id="gmv_yoy",
        metric_name="gmv",
        comparison_type=ComparisonTypeV2.YOY,
        change_type=AnomalyChangeTypeV2.RELATIVE,
        direction=AnomalyDirectionV2.DECREASE,
        policy_sources=(
            AnomalyPolicySourceV2.METADATA_DEFINITION,
            AnomalyPolicySourceV2.DATASET_MANIFEST,
        ),
        evidence_references=(
            "metadata.metric.gmv",
            "manifest.order_generation.date_allocation",
            "manifest.business_calendar",
        ),
        status=(
            AnomalyPolicyCandidateStatusV2.TBD_CALIBRATION
        ),
        calibration_notes=(
            "Threshold is not supported by the current sources.",
            "Sample basis is intentionally not frozen yet.",
        ),
    ),
    AnomalyPolicyCandidateV2(
        candidate_id="gmv_campaign_yoy",
        metric_name="gmv",
        comparison_type=ComparisonTypeV2.CAMPAIGN_YOY,
        change_type=AnomalyChangeTypeV2.RELATIVE,
        direction=AnomalyDirectionV2.DECREASE,
        policy_sources=(
            AnomalyPolicySourceV2.METADATA_DEFINITION,
            AnomalyPolicySourceV2.DATASET_MANIFEST,
        ),
        evidence_references=(
            "metadata.metric.gmv",
            "manifest.business_calendar.campaigns",
            "manifest.order_generation.date_allocation."
            "campaign_family_multipliers",
        ),
        status=(
            AnomalyPolicyCandidateStatusV2.TBD_CALIBRATION
        ),
        calibration_notes=(
            "Campaign family is a better comparison regime "
            "than ordinary calendar MoM for major promotions.",
            "Threshold and sample basis remain uncalibrated.",
        ),
    ),
    AnomalyPolicyCandidateV2(
        candidate_id="gross_margin_rate_yoy",
        metric_name="gross_margin_rate",
        comparison_type=ComparisonTypeV2.YOY,
        change_type=AnomalyChangeTypeV2.RELATIVE,
        direction=AnomalyDirectionV2.DECREASE,
        policy_sources=(
            AnomalyPolicySourceV2.METADATA_DEFINITION,
            AnomalyPolicySourceV2.DATASET_ACCEPTANCE,
        ),
        evidence_references=(
            "metadata.metric.gross_margin_rate",
            "manifest.business_pattern_acceptance.P08",
        ),
        status=(
            AnomalyPolicyCandidateStatusV2.TBD_CALIBRATION
        ),
        calibration_notes=(
            "P08 proves a promotion-margin trade-off in the "
            "dataset but does not define an online anomaly threshold.",
            "Sample basis remains uncalibrated.",
        ),
    ),
    AnomalyPolicyCandidateV2(
        candidate_id="gross_margin_rate_campaign_yoy",
        metric_name="gross_margin_rate",
        comparison_type=ComparisonTypeV2.CAMPAIGN_YOY,
        change_type=AnomalyChangeTypeV2.RELATIVE,
        direction=AnomalyDirectionV2.DECREASE,
        policy_sources=(
            AnomalyPolicySourceV2.METADATA_DEFINITION,
            AnomalyPolicySourceV2.DATASET_MANIFEST,
            AnomalyPolicySourceV2.DATASET_ACCEPTANCE,
        ),
        evidence_references=(
            "metadata.metric.gross_margin_rate",
            "manifest.business_calendar.campaigns",
            "manifest.business_pattern_acceptance.P08",
        ),
        status=(
            AnomalyPolicyCandidateStatusV2.TBD_CALIBRATION
        ),
        calibration_notes=(
            "Promotion regime matters for margin comparison.",
            "Acceptance ranges must not be copied as anomaly thresholds.",
        ),
    ),
    AnomalyPolicyCandidateV2(
        candidate_id="refund_rate_yoy",
        metric_name="refund_rate",
        comparison_type=ComparisonTypeV2.YOY,
        change_type=AnomalyChangeTypeV2.RELATIVE,
        direction=AnomalyDirectionV2.INCREASE,
        policy_sources=(
            AnomalyPolicySourceV2.METADATA_DEFINITION,
            AnomalyPolicySourceV2.DATASET_ACCEPTANCE,
        ),
        evidence_references=(
            "metadata.metric.refund_rate",
            "manifest.business_pattern_acceptance.P09",
        ),
        status=(
            AnomalyPolicyCandidateStatusV2.TBD_CALIBRATION
        ),
        calibration_notes=(
            "Metadata refund_rate is amount-based.",
            "P09 supplies contextual quality/refund evidence, "
            "not a direct amount-based anomaly threshold.",
            "Sample basis remains intentionally unresolved.",
        ),
    ),
    AnomalyPolicyCandidateV2(
        candidate_id="refund_rate_baseline_deviation",
        metric_name="refund_rate",
        comparison_type=(
            ComparisonTypeV2.BASELINE_DEVIATION
        ),
        change_type=AnomalyChangeTypeV2.RELATIVE,
        direction=AnomalyDirectionV2.INCREASE,
        policy_sources=(
            AnomalyPolicySourceV2.METADATA_DEFINITION,
            AnomalyPolicySourceV2.DATASET_ACCEPTANCE,
        ),
        evidence_references=(
            "metadata.metric.refund_rate",
            "manifest.business_pattern_acceptance.P09",
        ),
        status=(
            AnomalyPolicyCandidateStatusV2.TBD_CALIBRATION
        ),
        calibration_notes=(
            "A baseline-deviation policy needs historical or "
            "business calibration before activation.",
        ),
    ),
    AnomalyPolicyCandidateV2(
        candidate_id="order_count_yoy",
        metric_name="order_count",
        comparison_type=ComparisonTypeV2.YOY,
        change_type=AnomalyChangeTypeV2.RELATIVE,
        direction=AnomalyDirectionV2.DECREASE,
        sample_metric_name="order_count",
        policy_sources=(
            AnomalyPolicySourceV2.METADATA_DEFINITION,
            AnomalyPolicySourceV2.DATASET_MANIFEST,
        ),
        evidence_references=(
            "metadata.metric.order_count",
            "manifest.order_generation",
        ),
        status=(
            AnomalyPolicyCandidateStatusV2.TBD_CALIBRATION
        ),
        calibration_notes=(
            "The sample basis can use the metric itself, "
            "but minimum sample and threshold are not calibrated.",
        ),
    ),
    AnomalyPolicyCandidateV2(
        candidate_id="order_count_campaign_yoy",
        metric_name="order_count",
        comparison_type=ComparisonTypeV2.CAMPAIGN_YOY,
        change_type=AnomalyChangeTypeV2.RELATIVE,
        direction=AnomalyDirectionV2.DECREASE,
        sample_metric_name="order_count",
        policy_sources=(
            AnomalyPolicySourceV2.METADATA_DEFINITION,
            AnomalyPolicySourceV2.DATASET_MANIFEST,
        ),
        evidence_references=(
            "metadata.metric.order_count",
            "manifest.business_calendar.campaigns",
            "manifest.order_generation.date_allocation."
            "campaign_family_multipliers",
        ),
        status=(
            AnomalyPolicyCandidateStatusV2.TBD_CALIBRATION
        ),
        calibration_notes=(
            "Campaign-relative comparison avoids treating "
            "promotion regime changes as ordinary calendar anomalies.",
            "Minimum sample and threshold remain uncalibrated.",
        ),
    ),
)
