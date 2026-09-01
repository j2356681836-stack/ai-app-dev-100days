from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.delivery.breakdown_trusted_summary_v2 import (
    TrustedBreakdownSummaryResultV2,
)
from app.delivery.fact_composition_delivery_v2 import (
    FactCompositionResultV2,
)
from app.delivery.runtime_delivery_bridge_v2 import (
    RuntimeDeliveryBridgeResultV2,
    RuntimeDeliveryBridgeStatusV2,
)
from app.semantic_layer.requested_scope_resolution_v2 import (
    RequestedScopeResolutionV2,
)
from app.semantic_layer.time_comparison_contract_v2 import (
    TimeWindowReferenceV2,
)


ANALYSIS_SESSION_HISTORY_VERSION = (
    "analysis_session_history_v1_0"
)
ANALYSIS_SESSION_HISTORY_MAX_ITEMS = 10


class FollowUpContextV1(BaseModel):
    """
    后续追问可继承的可信结构化上下文。

    不是聊天文本摘要，也不授权访问。
    下一轮仍必须重新经过 Governance。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    source_history_id: str
    metric_name: str
    analysis_window: TimeWindowReferenceV2
    requested_scope: RequestedScopeResolutionV2 | None = None
    result_grain: str
    evidence_ids: tuple[str, ...] = ()


class AnalysisHistoryItemV1(BaseModel):
    """
    Session 内的一次可信分析快照。

    保存的是 Result Protection 之后的 Delivery Snapshot；
    “查看历史”不会重新查询数据库。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        arbitrary_types_allowed=True,
    )

    contract_version: str = ANALYSIS_SESSION_HISTORY_VERSION
    history_id: str
    parent_history_id: str | None = None

    original_question: str
    resolved_question: str | None = None
    resolution_note: str | None = None

    metric_name: str
    analysis_window: TimeWindowReferenceV2
    requested_scope: RequestedScopeResolutionV2 | None = None
    result_grain: str
    answer_snapshot: str
    evidence_ids: tuple[str, ...] = ()

    created_at_utc: datetime

    runtime_delivery_snapshot: RuntimeDeliveryBridgeResultV2
    breakdown_summary_snapshot: (
        TrustedBreakdownSummaryResultV2 | None
    ) = None
    fact_composition_snapshots: tuple[
        FactCompositionResultV2,
        ...,
    ] = ()

    follow_up_context: FollowUpContextV1

    @model_validator(mode="after")
    def validate_item(
        self,
    ) -> "AnalysisHistoryItemV1":
        if not self.history_id.strip():
            raise ValueError("history_id cannot be empty.")
        if not self.original_question.strip():
            raise ValueError("original_question cannot be empty.")
        if not self.metric_name.strip():
            raise ValueError("metric_name cannot be empty.")
        if not self.result_grain.strip():
            raise ValueError("result_grain cannot be empty.")
        if not self.answer_snapshot.strip():
            raise ValueError("answer_snapshot cannot be empty.")

        if self.created_at_utc.tzinfo is None:
            raise ValueError(
                "created_at_utc must be timezone-aware."
            )

        if (
            self.runtime_delivery_snapshot.status
            != RuntimeDeliveryBridgeStatusV2.READY
        ):
            raise ValueError(
                "Analysis history only stores READY protected delivery."
            )

        if (
            self.follow_up_context.source_history_id
            != self.history_id
        ):
            raise ValueError(
                "follow_up_context must reference this history item."
            )

        return self


class AnalysisSessionHistoryV1(BaseModel):
    """
    Streamlit Session 生命周期内最近 10 次 READY 分析。

    不写数据库、不跨浏览器 Session 持久化。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    contract_version: str = ANALYSIS_SESSION_HISTORY_VERSION
    max_items: int = Field(
        default=ANALYSIS_SESSION_HISTORY_MAX_ITEMS,
        ge=1,
        le=ANALYSIS_SESSION_HISTORY_MAX_ITEMS,
    )
    items: tuple[AnalysisHistoryItemV1, ...] = ()
    active_history_id: str | None = None

    @model_validator(mode="after")
    def validate_session(
        self,
    ) -> "AnalysisSessionHistoryV1":
        if len(self.items) > self.max_items:
            raise ValueError(
                "Analysis history exceeds max_items."
            )

        ids = tuple(
            item.history_id
            for item in self.items
        )
        if len(ids) != len(set(ids)):
            raise ValueError(
                "Analysis history_id values must be unique."
            )

        if (
            self.active_history_id is not None
            and self.active_history_id not in set(ids)
        ):
            raise ValueError(
                "active_history_id must reference an existing item."
            )

        return self


def empty_analysis_session_history_v1(
) -> AnalysisSessionHistoryV1:
    return AnalysisSessionHistoryV1()


def build_analysis_history_item_v1(
    *,
    original_question: str,
    runtime_delivery: RuntimeDeliveryBridgeResultV2,
    resolved_question: str | None = None,
    resolution_note: str | None = None,
    parent_history_id: str | None = None,
    breakdown_summary: (
        TrustedBreakdownSummaryResultV2 | None
    ) = None,
    fact_compositions: tuple[
        FactCompositionResultV2,
        ...,
    ] = (),
    history_id: str | None = None,
    created_at_utc: datetime | None = None,
) -> AnalysisHistoryItemV1:
    """
    从 READY Runtime Delivery 构造 Session Snapshot。

    Context 来自受保护 Delivery 的 AnalysisScope，
    不从用户问题文本反向猜 Metric / Time / Grain。
    """
    if (
        runtime_delivery.status
        != RuntimeDeliveryBridgeStatusV2.READY
        or runtime_delivery.delivery is None
    ):
        raise ValueError(
            "Only READY Runtime Delivery can enter analysis history."
        )

    scope = (
        runtime_delivery.delivery
        .evidence_pack
        .analysis_scope
    )

    evidence_ids = tuple(
        record.reference.evidence_id
        for record in (
            runtime_delivery.delivery
            .evidence_pack
            .evidence_records
        )
    )

    active_history_id = (
        history_id
        if history_id is not None
        else f"history_{uuid4().hex[:12]}"
    )

    timestamp = (
        created_at_utc
        if created_at_utc is not None
        else datetime.now(timezone.utc)
    )

    follow_up = FollowUpContextV1(
        source_history_id=active_history_id,
        metric_name=scope.metric_name,
        analysis_window=scope.analysis_window,
        requested_scope=runtime_delivery.requested_scope,
        result_grain=scope.result_grain,
        evidence_ids=evidence_ids,
    )

    return AnalysisHistoryItemV1(
        history_id=active_history_id,
        parent_history_id=parent_history_id,
        original_question=original_question,
        resolved_question=resolved_question,
        resolution_note=resolution_note,
        metric_name=scope.metric_name,
        analysis_window=scope.analysis_window,
        requested_scope=runtime_delivery.requested_scope,
        result_grain=scope.result_grain,
        answer_snapshot=runtime_delivery.message,
        evidence_ids=evidence_ids,
        created_at_utc=timestamp,
        runtime_delivery_snapshot=runtime_delivery,
        breakdown_summary_snapshot=breakdown_summary,
        fact_composition_snapshots=fact_compositions,
        follow_up_context=follow_up,
    )


def append_analysis_history_item_v1(
    *,
    session: AnalysisSessionHistoryV1,
    item: AnalysisHistoryItemV1,
) -> AnalysisSessionHistoryV1:
    """
    新结果放在最前；超过 10 条时丢弃最旧快照。

    相同问题重复查询仍保留为不同快照，因为底层数据可能变化。
    """
    retained = (
        item,
        *session.items,
    )[:session.max_items]

    return session.model_copy(
        update={
            "items": retained,
            "active_history_id": item.history_id,
        }
    )


def activate_analysis_history_item_v1(
    *,
    session: AnalysisSessionHistoryV1,
    history_id: str,
) -> AnalysisSessionHistoryV1:
    if history_id not in {
        item.history_id
        for item in session.items
    }:
        raise ValueError(
            "history_id does not exist in this session."
        )

    return session.model_copy(
        update={
            "active_history_id": history_id,
        }
    )


def clear_active_analysis_history_v1(
    *,
    session: AnalysisSessionHistoryV1,
) -> AnalysisSessionHistoryV1:
    return session.model_copy(
        update={
            "active_history_id": None,
        }
    )


def get_analysis_history_item_v1(
    *,
    session: AnalysisSessionHistoryV1,
    history_id: str,
) -> AnalysisHistoryItemV1 | None:
    matches = tuple(
        item
        for item in session.items
        if item.history_id == history_id
    )

    if len(matches) == 1:
        return matches[0]

    return None


def update_analysis_history_snapshots_v1(
    *,
    session: AnalysisSessionHistoryV1,
    history_id: str,
    breakdown_summary: (
        TrustedBreakdownSummaryResultV2 | None
    ) = None,
    fact_compositions: tuple[
        FactCompositionResultV2,
        ...,
    ] = (),
) -> AnalysisSessionHistoryV1:
    """
    更新当前分析后来主动展开的安全辅助结果。

    不改变主 Runtime Delivery，不重新查询数据库。
    """
    target = get_analysis_history_item_v1(
        session=session,
        history_id=history_id,
    )

    if target is None:
        raise ValueError(
            "history_id does not exist in this session."
        )

    updated_target = target.model_copy(
        update={
            "breakdown_summary_snapshot": breakdown_summary,
            "fact_composition_snapshots": fact_compositions,
        }
    )

    updated_items = tuple(
        (
            updated_target
            if item.history_id == history_id
            else item
        )
        for item in session.items
    )

    return session.model_copy(
        update={
            "items": updated_items,
        }
    )
