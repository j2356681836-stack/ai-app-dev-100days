from __future__ import annotations

from datetime import date, timedelta
from enum import Enum

from pydantic import BaseModel, ConfigDict, model_validator

from app.semantic_layer.time_comparison_contract_v2 import (
    TimeWindowReferenceV2,
)


R12_COHORT_CONTRACT_VERSION = "r12_cohort_contract_v2_0"
R12_ELIGIBILITY_MONTHS = 12
DATASET_V2_BUSINESS_START_DATE = date(2024, 1, 1)


class R12CohortHistoryStatusV2(str, Enum):
    READY = "ready"
    INSUFFICIENT_HISTORY = "insufficient_history"


class R12CohortContractV2(BaseModel):
    """
    Periodic Customer Health 的 R12 Eligibility Contract。

    重要边界：
    - report_window 是当前要评价的正式报表窗口；
    - base_window 永远位于 report_window 之前；
    - Base 是“前 12 个日历月中的有效购买客户”，
      不是会员等级历史，也不是窗口内跨日复购；
    - V1 使用 all-channel Base，但仍服从 Effective Scope / Authorization；
    - 完整 12 个月历史不足时 fail closed。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    contract_version: str = R12_COHORT_CONTRACT_VERSION

    report_window: TimeWindowReferenceV2
    base_window: TimeWindowReferenceV2

    eligibility_months: int = R12_ELIGIBILITY_MONTHS
    dataset_business_start_date: date = DATASET_V2_BUSINESS_START_DATE

    history_status: R12CohortHistoryStatusV2

    purchase_definition: str = "effective_purchase"
    scope_mode: str = "all_channel_within_effective_scope"
    refund_observation_required: bool = True

    @model_validator(mode="after")
    def validate_contract(self) -> "R12CohortContractV2":
        if self.eligibility_months != 12:
            raise ValueError("B5B V1 只允许固定 R12 eligibility。")

        if self.purchase_definition != "effective_purchase":
            raise ValueError("R12 Base 必须使用 effective_purchase。")

        if self.scope_mode != "all_channel_within_effective_scope":
            raise ValueError(
                "B5B V1 只允许 all-channel Base，"
                "但仍必须服从 Effective Scope。"
            )

        expected_base_start = shift_months_v2(
            self.report_window.start_date,
            -12,
        )
        expected_base_end = (
            self.report_window.start_date
            - timedelta(days=1)
        )

        if self.base_window.start_date != expected_base_start:
            raise ValueError(
                "R12 base_window.start_date 必须等于 "
                "report_start 往前 12 个日历月。"
            )

        if self.base_window.end_date != expected_base_end:
            raise ValueError(
                "R12 base_window.end_date 必须等于 report_start - 1 day。"
            )

        if (
            self.base_window.end_date
            >= self.report_window.start_date
        ):
            raise ValueError(
                "R12 Base 与 Report Window 不得重叠。"
            )

        expected_history = (
            R12CohortHistoryStatusV2.READY
            if self.base_window.start_date
            >= self.dataset_business_start_date
            else R12CohortHistoryStatusV2.INSUFFICIENT_HISTORY
        )

        if self.history_status != expected_history:
            raise ValueError(
                "history_status 与 Dataset business_start_date 不一致。"
            )

        return self


def shift_months_v2(value: date, months: int) -> date:
    """
    只用于 server-owned Cohort Contract 的日历月位移。

    report_start 通常是自然日/周/月窗口的起点；
    这里使用 calendar-month semantics，而不是固定 365 天。
    """

    zero_based = value.month - 1 + months
    year = value.year + zero_based // 12
    month = zero_based % 12 + 1

    # Periodic 自然窗口起点通常不会触发 month-end clamp，
    # 但这里仍保留安全 clamp，使函数成为通用确定性合同。
    import calendar

    day = min(
        value.day,
        calendar.monthrange(year, month)[1],
    )

    return date(year, month, day)


def build_r12_cohort_contract_v2(
    *,
    report_window: TimeWindowReferenceV2,
    dataset_business_start_date: date = (
        DATASET_V2_BUSINESS_START_DATE
    ),
) -> R12CohortContractV2:
    base_start = shift_months_v2(
        report_window.start_date,
        -12,
    )
    base_end = (
        report_window.start_date
        - timedelta(days=1)
    )

    history_status = (
        R12CohortHistoryStatusV2.READY
        if base_start >= dataset_business_start_date
        else R12CohortHistoryStatusV2.INSUFFICIENT_HISTORY
    )

    return R12CohortContractV2(
        report_window=report_window,
        base_window=TimeWindowReferenceV2(
            start_date=base_start,
            end_date=base_end,
        ),
        dataset_business_start_date=(
            dataset_business_start_date
        ),
        history_status=history_status,
    )
