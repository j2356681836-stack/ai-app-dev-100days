from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, ConfigDict, model_validator


class ComparisonTypeV2(str, Enum):
    WOW = "wow"
    MOM = "mom"
    YOY = "yoy"
    CAMPAIGN_YOY = "campaign_yoy"
    BASELINE_DEVIATION = "baseline_deviation"


class PeriodModeV2(str, Enum):
    COMPLETED_PERIOD = "completed_period"
    PERIOD_TO_DATE = "period_to_date"
    ROLLING_WINDOW = "rolling_window"


class AlignmentModeV2(str, Enum):
    CALENDAR_ALIGNED = "calendar_aligned"
    SAME_ELAPSED_PERIOD = "same_elapsed_period"
    CAMPAIGN_RELATIVE = "campaign_relative"
    ROLLING = "rolling"


class TimeWindowReferenceV2(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    start_date: date
    end_date: date

    @model_validator(mode="after")
    def validate_window(self) -> "TimeWindowReferenceV2":
        if self.start_date > self.end_date:
            raise ValueError(
                "Time window start_date cannot be after end_date."
            )
        return self


class CampaignReferenceV2(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    campaign_family: str
    current_campaign_code: str
    reference_campaign_code: str

    @model_validator(mode="after")
    def validate_reference(self) -> "CampaignReferenceV2":
        values = (
            self.campaign_family,
            self.current_campaign_code,
            self.reference_campaign_code,
        )

        if any(not value.strip() for value in values):
            raise ValueError(
                "Campaign reference fields cannot be empty."
            )

        if self.current_campaign_code == self.reference_campaign_code:
            raise ValueError(
                "Current and reference campaigns must be different instances."
            )

        return self


class BaselineReferenceV2(BaseModel):
    """
    Reference only.

    Day82 does not define how the baseline is calculated.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    reference_id: str

    @model_validator(mode="after")
    def validate_reference(self) -> "BaselineReferenceV2":
        if not self.reference_id.strip():
            raise ValueError(
                "Baseline reference_id cannot be empty."
            )
        return self


class TimeComparisonContractV2(BaseModel):
    """
    Phase4 comparison contract for the Dataset V2 candidate path.

    This contract describes an already resolved comparison relationship.
    It does not:
    - parse comparison semantics from natural language;
    - resolve campaign instances;
    - determine data freshness;
    - execute SQL.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    comparison_type: ComparisonTypeV2
    period_mode: PeriodModeV2
    alignment_mode: AlignmentModeV2

    current_window: TimeWindowReferenceV2
    reference_window: TimeWindowReferenceV2

    data_complete_through: date | None = None
    is_partial_period: bool = False

    campaign_reference: CampaignReferenceV2 | None = None
    baseline_reference: BaselineReferenceV2 | None = None

    @model_validator(mode="after")
    def validate_contract(self) -> "TimeComparisonContractV2":
        if (
            self.period_mode == PeriodModeV2.COMPLETED_PERIOD
            and self.is_partial_period
        ):
            raise ValueError(
                "COMPLETED_PERIOD cannot be marked as partial."
            )

        if (
            self.period_mode == PeriodModeV2.PERIOD_TO_DATE
            and not self.is_partial_period
        ):
            raise ValueError(
                "PERIOD_TO_DATE must be marked as partial."
            )

        if (
            self.alignment_mode == AlignmentModeV2.SAME_ELAPSED_PERIOD
            and self.period_mode != PeriodModeV2.PERIOD_TO_DATE
        ):
            raise ValueError(
                "SAME_ELAPSED_PERIOD requires PERIOD_TO_DATE."
            )

        if (
            self.period_mode == PeriodModeV2.ROLLING_WINDOW
            and self.alignment_mode != AlignmentModeV2.ROLLING
        ):
            raise ValueError(
                "ROLLING_WINDOW requires ROLLING alignment."
            )

        if (
            self.alignment_mode == AlignmentModeV2.CAMPAIGN_RELATIVE
            and self.comparison_type != ComparisonTypeV2.CAMPAIGN_YOY
        ):
            raise ValueError(
                "CAMPAIGN_RELATIVE is only valid for CAMPAIGN_YOY."
            )

        if self.comparison_type == ComparisonTypeV2.CAMPAIGN_YOY:
            if self.campaign_reference is None:
                raise ValueError(
                    "CAMPAIGN_YOY requires campaign_reference."
                )
            if self.alignment_mode != AlignmentModeV2.CAMPAIGN_RELATIVE:
                raise ValueError(
                    "CAMPAIGN_YOY requires CAMPAIGN_RELATIVE alignment."
                )
        elif self.campaign_reference is not None:
            raise ValueError(
                "campaign_reference is only valid for CAMPAIGN_YOY."
            )

        if self.comparison_type == ComparisonTypeV2.BASELINE_DEVIATION:
            if self.baseline_reference is None:
                raise ValueError(
                    "BASELINE_DEVIATION requires baseline_reference."
                )
        elif self.baseline_reference is not None:
            raise ValueError(
                "baseline_reference is only valid for BASELINE_DEVIATION."
            )

        if (
            self.data_complete_through is not None
            and self.current_window.end_date > self.data_complete_through
        ):
            raise ValueError(
                "Current window cannot extend past data_complete_through."
            )

        if self.alignment_mode in {
            AlignmentModeV2.SAME_ELAPSED_PERIOD,
            AlignmentModeV2.CAMPAIGN_RELATIVE,
        }:
            current_days = (
                self.current_window.end_date
                - self.current_window.start_date
            ).days

            reference_days = (
                self.reference_window.end_date
                - self.reference_window.start_date
            ).days

            if current_days != reference_days:
                raise ValueError(
                    "Elapsed-period comparison requires equally sized windows."
                )

        return self
