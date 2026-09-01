from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, ConfigDict, model_validator

from app.delivery.runtime_delivery_bridge_v2 import (
    RuntimeDeliveryBridgeResultV2,
)
from app.semantic_layer.requested_scope_resolution_v2 import (
    RequestedScopeResolutionV2,
    resolve_requested_scope_v2,
)
from app.semantic_layer.result_grain_resolver_v2 import (
    ResultGrainResolutionStatusV2,
    ResultGrainResolutionV2,
    resolve_result_grain_v2,
)
from app.semantic_layer.time_window_resolver_v2 import (
    TimeWindowResolutionV2,
    resolve_time_window_v2,
)


BUSINESS_CLARIFICATION_CONTINUATION_VERSION = (
    "business_clarification_continuation_v1_1"
)


class BusinessClarificationSlotV1(str, Enum):
    PERFORMANCE_METRIC = "performance_metric"


class BusinessClarificationChoiceV1(BaseModel):
    """
    Server-owned 业务澄清选项。

    UI 只能提交 choice_id；不能临时创造 Metric、Query Plan 或 Tool。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    choice_id: str
    display_label: str
    metric_name: str
    query_phrase: str

    @model_validator(mode="after")
    def validate_choice(
        self,
    ) -> "BusinessClarificationChoiceV1":
        values = (
            self.choice_id,
            self.display_label,
            self.metric_name,
            self.query_phrase,
        )
        if any(not value.strip() for value in values):
            raise ValueError(
                "Business clarification choice fields cannot be empty."
            )
        return self


class PendingBusinessClarificationV1(BaseModel):
    """
    普通业务问题的待澄清状态。

    V1.1 的关键变化：
    - 在第一次 Clarification Stop 时就冻结确定性 Context；
    - 后续用户只补 missing_slot；
    - 不把已经确认的 Time / Scope / Grain 再交给 NLP 重猜。

    仍然不持有：
    - raw SQL；
    - raw rows；
    - Tool execution state。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    contract_version: str = (
        BUSINESS_CLARIFICATION_CONTINUATION_VERSION
    )
    original_question: str
    missing_slot: BusinessClarificationSlotV1
    reason_code: str
    prompt: str
    choices: tuple[BusinessClarificationChoiceV1, ...]

    preserved_time_resolution: TimeWindowResolutionV2
    preserved_requested_scope: RequestedScopeResolutionV2
    preserved_grain_resolution: ResultGrainResolutionV2

    @model_validator(mode="after")
    def validate_pending(
        self,
    ) -> "PendingBusinessClarificationV1":
        if not self.original_question.strip():
            raise ValueError("original_question cannot be empty.")
        if not self.reason_code.strip():
            raise ValueError("reason_code cannot be empty.")
        if not self.prompt.strip():
            raise ValueError("prompt cannot be empty.")
        if not self.choices:
            raise ValueError("Pending clarification requires choices.")

        choice_ids = tuple(
            choice.choice_id
            for choice in self.choices
        )
        if len(choice_ids) != len(set(choice_ids)):
            raise ValueError(
                "Business clarification choice_id values must be unique."
            )

        metric_names = tuple(
            choice.metric_name
            for choice in self.choices
        )
        if len(metric_names) != len(set(metric_names)):
            raise ValueError(
                "Business clarification metric_name values must be unique."
            )

        if (
            self.missing_slot
            == BusinessClarificationSlotV1.PERFORMANCE_METRIC
        ):
            grain = self.preserved_grain_resolution

            if (
                grain.status
                != ResultGrainResolutionStatusV2.RESOLVED
                or len(grain.dimensions) != 1
            ):
                raise ValueError(
                    "Performance metric clarification requires one "
                    "already-resolved comparison grain."
                )

        return self


class BusinessClarificationResolutionV1(BaseModel):
    """
    用户补齐一个 missing slot 后的结构化恢复合同。

    resolved_question 只用于 UI / Audit 可读文本；
    Runtime Planning 必须使用 preserved_* + selected_metric_name，
    不能再从 resolved_question 重新推导 Grain / Time / Scope。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    original_question: str
    choice_id: str
    selected_metric_name: str
    selected_display_label: str
    resolved_question: str

    preserved_time_resolution: TimeWindowResolutionV2
    preserved_requested_scope: RequestedScopeResolutionV2
    preserved_grain_resolution: ResultGrainResolutionV2


_PERFORMANCE_METRIC_CHOICES_V1 = (
    BusinessClarificationChoiceV1(
        choice_id="performance_metric_gmv",
        display_label="GMV",
        metric_name="gmv",
        query_phrase="GMV",
    ),
    BusinessClarificationChoiceV1(
        choice_id="performance_metric_order_count",
        display_label="订单数",
        metric_name="order_count",
        query_phrase="订单数",
    ),
    BusinessClarificationChoiceV1(
        choice_id="performance_metric_buyer_count",
        display_label="购买人数",
        metric_name="buyer_count",
        query_phrase="购买人数",
    ),
)


def build_pending_business_clarification_v1(
    *,
    original_question: str,
    runtime_result: RuntimeDeliveryBridgeResultV2,
    reference_date: date,
) -> PendingBusinessClarificationV1 | None:
    """
    只把正式 Business Preflight 的已知澄清原因升级成可继续状态。

    在建立 Pending Contract 时冻结：
    - Time Resolution；
    - Requested Scope；
    - Result Grain。

    如果“表现最好”本身都不能可靠确定唯一比较维度，
    V1 不展示可继续按钮，保持 fail closed。
    """
    public = runtime_result.safe_runtime_result

    if not isinstance(public, dict):
        return None

    if (
        public.get("stop_stage")
        != "business_request_preflight"
    ):
        return None

    reason_code = public.get("reason_code")

    if reason_code != "ambiguous_performance_metric":
        return None

    grain = resolve_result_grain_v2(
        original_question
    )

    if (
        grain.status
        != ResultGrainResolutionStatusV2.RESOLVED
        or len(grain.dimensions) != 1
    ):
        return None

    time_resolution = resolve_time_window_v2(
        original_question,
        reference_date=reference_date,
    )

    requested_scope = resolve_requested_scope_v2(
        original_question
    )

    return PendingBusinessClarificationV1(
        original_question=original_question,
        missing_slot=(
            BusinessClarificationSlotV1.PERFORMANCE_METRIC
        ),
        reason_code=reason_code,
        prompt=(
            "“表现最好”需要先确定评价指标。"
            "请选择一个指标后继续原分析。"
        ),
        choices=_PERFORMANCE_METRIC_CHOICES_V1,
        preserved_time_resolution=time_resolution,
        preserved_requested_scope=requested_scope,
        preserved_grain_resolution=grain,
    )


def resolve_business_clarification_v1(
    *,
    pending: PendingBusinessClarificationV1,
    choice_id: str,
) -> BusinessClarificationResolutionV1:
    """
    只补 missing metric slot。

    resolved_question 仅用于可读展示与审计。
    Runtime 必须消费结构化 preserved Context，而不是再次 NLP 解析。
    """
    matches = tuple(
        choice
        for choice in pending.choices
        if choice.choice_id == choice_id
    )

    if len(matches) != 1:
        raise ValueError(
            "choice_id does not belong to the current "
            "server-owned clarification contract."
        )

    choice = matches[0]

    original = pending.original_question.strip()
    while original.endswith(("？", "?", "。", ".")):
        original = original[:-1].rstrip()

    resolved_question = (
        f"{original}；已选择评价指标：{choice.query_phrase}。"
    )

    return BusinessClarificationResolutionV1(
        original_question=pending.original_question,
        choice_id=choice.choice_id,
        selected_metric_name=choice.metric_name,
        selected_display_label=choice.display_label,
        resolved_question=resolved_question,
        preserved_time_resolution=(
            pending.preserved_time_resolution
        ),
        preserved_requested_scope=(
            pending.preserved_requested_scope
        ),
        preserved_grain_resolution=(
            pending.preserved_grain_resolution
        ),
    )
