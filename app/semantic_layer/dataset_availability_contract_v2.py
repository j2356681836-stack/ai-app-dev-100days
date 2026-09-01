from __future__ import annotations

from datetime import date
from enum import Enum
from functools import lru_cache

from pydantic import BaseModel, ConfigDict, model_validator

from app.db.beauty_bi_v2.manifest_loader import (
    load_manifest,
    parse_manifest_date,
)
from app.semantic_layer.time_window_resolver_v2 import (
    TimeWindowResolutionSourceV2,
    TimeWindowResolutionStatusV2,
    TimeWindowResolutionV2,
    resolve_time_window_v2,
)


DATASET_AVAILABILITY_CONTRACT_VERSION = (
    "dataset_availability_contract_v2_0"
)


class DatasetAvailabilityOutcomeV2(str, Enum):
    AVAILABLE = "available"
    NOT_APPLICABLE = "not_applicable"
    OUTSIDE_BUSINESS_WINDOW = "outside_business_window"
    PARTIAL_OVERLAP = "partial_overlap"


class DatasetBusinessWindowV2(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    start_date: date
    end_date: date

    @model_validator(mode="after")
    def validate_window(self) -> "DatasetBusinessWindowV2":
        if self.start_date > self.end_date:
            raise ValueError(
                "Dataset business window start_date cannot exceed end_date."
            )
        return self


class DatasetAvailabilityDecisionV2(BaseModel):
    """
    已解析时间窗与 Dataset 正式业务数据覆盖范围之间的合同。

    这里只检查“请求时间是否有业务数据可查”，不负责：
    - 自然语言时间解析；
    - 查询结果是否为空；
    - Result Protection；
    - Event Observation Tail 的专用事件分析。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    contract_version: str = DATASET_AVAILABILITY_CONTRACT_VERSION
    outcome: DatasetAvailabilityOutcomeV2
    business_window: DatasetBusinessWindowV2
    requested_start_date: date | None = None
    requested_end_date: date | None = None
    reason_code: str | None = None
    user_message: str | None = None

    @model_validator(mode="after")
    def validate_decision(
        self,
    ) -> "DatasetAvailabilityDecisionV2":
        if self.outcome in {
            DatasetAvailabilityOutcomeV2.AVAILABLE,
            DatasetAvailabilityOutcomeV2.NOT_APPLICABLE,
        }:
            if self.reason_code is not None:
                raise ValueError(
                    "Non-stopped availability decision must not carry reason_code."
                )
            if self.user_message is not None:
                raise ValueError(
                    "Non-stopped availability decision must not carry user_message."
                )
            return self

        if (
            self.requested_start_date is None
            or self.requested_end_date is None
        ):
            raise ValueError(
                "Stopped availability decision requires requested dates."
            )

        if not self.reason_code:
            raise ValueError(
                "Stopped availability decision requires reason_code."
            )

        if not self.user_message or not self.user_message.strip():
            raise ValueError(
                "Stopped availability decision requires user_message."
            )

        return self


@lru_cache(maxsize=1)
def get_dataset_business_window_v2() -> DatasetBusinessWindowV2:
    """
    从 server-owned Dataset Manifest 读取正式业务数据窗口。

    不复制 2024/2025 常量，避免 Manifest 与 Runtime 漂移。
    """
    manifest = load_manifest()
    generation = manifest.get("generation")

    if not isinstance(generation, dict):
        raise ValueError(
            "Manifest 缺少有效的 generation。"
        )

    start_date = parse_manifest_date(
        generation.get("business_start_date"),
        "generation.business_start_date",
    )
    end_date = parse_manifest_date(
        generation.get("business_end_date"),
        "generation.business_end_date",
    )

    return DatasetBusinessWindowV2(
        start_date=start_date,
        end_date=end_date,
    )


def clear_dataset_business_window_cache_v2() -> None:
    get_dataset_business_window_v2.cache_clear()


def evaluate_dataset_availability_v2(
    *,
    time_resolution: TimeWindowResolutionV2,
    business_window: DatasetBusinessWindowV2 | None = None,
) -> DatasetAvailabilityDecisionV2:
    """
    在 SQL 之前检查已解析时间窗是否落在 Dataset 正式业务窗口内。

    - 完全在窗口内：AVAILABLE；
    - 完全在窗口外：OUTSIDE_BUSINESS_WINDOW；
    - 部分重叠：PARTIAL_OVERLAP，要求用户缩小时间范围；
    - Time Resolver 自己尚未 RESOLVED：NOT_APPLICABLE，保留既有
      Governed Planning 对时间合同的处理，不在这里重写语义。
    """
    active_window = (
        business_window
        if business_window is not None
        else get_dataset_business_window_v2()
    )

    if (
        time_resolution.status
        != TimeWindowResolutionStatusV2.RESOLVED
    ):
        return DatasetAvailabilityDecisionV2(
            outcome=DatasetAvailabilityOutcomeV2.NOT_APPLICABLE,
            business_window=active_window,
        )

    requested_start = time_resolution.requested_start_date
    requested_end = time_resolution.requested_end_date

    if requested_start is None or requested_end is None:
        raise RuntimeError(
            "RESOLVED time window must expose requested dates."
        )

    entirely_before = requested_end < active_window.start_date
    entirely_after = requested_start > active_window.end_date

    if entirely_before or entirely_after:
        return DatasetAvailabilityDecisionV2(
            outcome=(
                DatasetAvailabilityOutcomeV2
                .OUTSIDE_BUSINESS_WINDOW
            ),
            business_window=active_window,
            requested_start_date=requested_start,
            requested_end_date=requested_end,
            reason_code="requested_window_outside_dataset_business_window",
            user_message=(
                "当前数据覆盖 "
                f"{active_window.start_date.isoformat()} 至 "
                f"{active_window.end_date.isoformat()}，"
                "因此暂时无法查询你请求的 "
                f"{requested_start.isoformat()} 至 "
                f"{requested_end.isoformat()} 数据。"
            ),
        )

    partial_overlap = (
        requested_start < active_window.start_date
        or requested_end > active_window.end_date
    )

    if partial_overlap:
        return DatasetAvailabilityDecisionV2(
            outcome=DatasetAvailabilityOutcomeV2.PARTIAL_OVERLAP,
            business_window=active_window,
            requested_start_date=requested_start,
            requested_end_date=requested_end,
            reason_code="requested_window_partially_outside_dataset_business_window",
            user_message=(
                "当前数据只覆盖 "
                f"{active_window.start_date.isoformat()} 至 "
                f"{active_window.end_date.isoformat()}。"
                "你请求的时间范围有一部分超出数据覆盖范围，"
                "请调整为当前可查询的日期范围后再试。"
            ),
        )

    return DatasetAvailabilityDecisionV2(
        outcome=DatasetAvailabilityOutcomeV2.AVAILABLE,
        business_window=active_window,
        requested_start_date=requested_start,
        requested_end_date=requested_end,
    )

def evaluate_explicit_dataset_availability_preflight_v2(
    *,
    question: str,
    reference_date: date,
    business_window: DatasetBusinessWindowV2 | None = None,
) -> DatasetAvailabilityDecisionV2:
    """
    在昂贵的 Semantic / LLM Planning 之前做一个窄的显式时间快检。

    只在以下条件全部满足时提前形成 Dataset Availability 结论：
    1. Time Resolver 能确定性解析出单一时间窗；
    2. 该时间窗来自用户显式时间表达，而不是默认时间策略。

    对以下情况一律 DEFER（返回 NOT_APPLICABLE），保留原主链处理：
    - 多时间窗 / 模糊时间；
    - Time Resolver 暂不支持的表达；
    - 没有显式时间，依赖默认时间策略。

    这样可以让“2023年GMV”在调用 LLM 和 SQL 之前快速停止，
    同时不会抢走 Comparison / Multi-step Orchestration 对多时间窗的解释权。
    """
    time_resolution = resolve_time_window_v2(
        question,
        reference_date=reference_date,
    )

    if (
        time_resolution.status
        != TimeWindowResolutionStatusV2.RESOLVED
        or time_resolution.source
        != TimeWindowResolutionSourceV2.EXPLICIT
    ):
        active_window = (
            business_window
            if business_window is not None
            else get_dataset_business_window_v2()
        )
        return DatasetAvailabilityDecisionV2(
            outcome=DatasetAvailabilityOutcomeV2.NOT_APPLICABLE,
            business_window=active_window,
        )

    return evaluate_dataset_availability_v2(
        time_resolution=time_resolution,
        business_window=business_window,
    )

