from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, ConfigDict, model_validator


ENTRY_CONTRACT_VERSION = "decision_console_entry_v2_0"


class DecisionConsoleEntryModeV2(str, Enum):
    """
    Day89 Decision Console 的两类人工入口。
    """

    INVESTIGATION = "investigation"
    PERIODIC_REPORT = "periodic_report"


class PeriodicReportCadenceV2(str, Enum):
    """
    Day89 只支持手工触发的基础周期报表。
    """

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class DecisionConsoleEntryRequestV2(BaseModel):
    """
    Day89 Decision Console 的薄入口合同。

    INVESTIGATION：
    - 必须提供 question；
    - 不允许携带 periodic report 参数。

    PERIODIC_REPORT：
    - 必须提供 cadence + anchor_date；
    - 不允许携带 investigation question。

    本合同明确不负责：
    - 解析自然语言时间；
    - 构造 TimeComparisonContractV2；
    - 查询数据库；
    - 调用 LLM；
    - 生成 Evidence；
    - 调度 / 订阅 / 邮件发送；
    - 保存 report history。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    contract_version: str = ENTRY_CONTRACT_VERSION

    entry_mode: DecisionConsoleEntryModeV2

    question: str | None = None

    report_cadence: PeriodicReportCadenceV2 | None = None
    report_anchor_date: date | None = None

    @model_validator(mode="after")
    def validate_entry(self) -> "DecisionConsoleEntryRequestV2":
        if self.entry_mode == DecisionConsoleEntryModeV2.INVESTIGATION:
            if self.question is None or not self.question.strip():
                raise ValueError(
                    "INVESTIGATION entry requires a non-empty question."
                )

            if (
                self.report_cadence is not None
                or self.report_anchor_date is not None
            ):
                raise ValueError(
                    "INVESTIGATION entry cannot carry periodic report fields."
                )

            return self

        if self.entry_mode == DecisionConsoleEntryModeV2.PERIODIC_REPORT:
            if self.question is not None:
                raise ValueError(
                    "PERIODIC_REPORT entry cannot carry question."
                )

            if self.report_cadence is None:
                raise ValueError(
                    "PERIODIC_REPORT entry requires report_cadence."
                )

            if self.report_anchor_date is None:
                raise ValueError(
                    "PERIODIC_REPORT entry requires report_anchor_date."
                )

            return self

        raise ValueError(
            f"Unsupported Decision Console entry_mode: {self.entry_mode}"
        )
