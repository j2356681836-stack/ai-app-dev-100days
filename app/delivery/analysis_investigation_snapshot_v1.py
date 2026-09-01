from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from app.agents.analytical_path_contract_v2 import (
    AnalyticalPathNodeV2,
)
from app.agents.investigation_loop_v2 import (
    InvestigationStopStatusV2,
)
from app.delivery.focused_change_breakdown_delivery_v2 import (
    FocusedChangeBreakdownDeliveryV2,
)
from app.delivery.investigation_delivery_adapter_v2 import (
    InvestigationDeliveryResultV2,
    InvestigationDeliveryStatusV2,
)
from app.delivery.investigation_runtime_v2 import (
    Day89InvestigationContinuationStateV2,
    Day89PendingClarificationStateV2,
)


ANALYSIS_INVESTIGATION_SNAPSHOT_VERSION = (
    "analysis_investigation_snapshot_v1_0"
)


class EvidenceLineageStageV1(str, Enum):
    SEED = "seed"
    AGENTIC_PACK = "agentic_pack"
    INVESTIGATION_CHANGE = "investigation_change"
    USER_EXPLORATION = "user_exploration"


class AnalysisEvidenceLineageRecordV1(BaseModel):
    """
    History / Verification 可展示的安全 Evidence Lineage 摘要。

    只允许保存：
    - evidence id；
    - protected plan / audit id；
    - result grain / reconciliation；
    - safe scope summary。

    不保存 SQL、parameters、raw rows、database URL 或 secret。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    sequence_number: int
    stage: EvidenceLineageStageV1
    business_label: str
    dimension: str | None = None

    evidence_ids: tuple[str, ...] = ()
    plan_names: tuple[str, ...] = ()
    audit_event_ids: tuple[str, ...] = ()

    scope_summary: str | None = None
    reconciliation_status: str | None = None

    @model_validator(mode="after")
    def validate_record(
        self,
    ) -> "AnalysisEvidenceLineageRecordV1":
        if self.sequence_number < 1:
            raise ValueError(
                "sequence_number must be >= 1."
            )
        if not self.business_label.strip():
            raise ValueError(
                "business_label cannot be empty."
            )
        if any(not value.strip() for value in self.evidence_ids):
            raise ValueError(
                "evidence_ids cannot contain empty values."
            )
        return self


class AnalysisInvestigationSnapshotV1(BaseModel):
    """
    AnalysisHistoryItemV1 的“深入调查伴随快照”。

    不修改既有 AnalysisHistoryItemV1 contract；
    该对象仅在同一个 Streamlit Session 内按 history_id 保存。

    只保存已经过保护的 Delivery 与 bounded continuation state，
    不持久化 runtime_step / envelope / compiled SQL / parameters。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        arbitrary_types_allowed=True,
    )

    contract_version: str = (
        ANALYSIS_INVESTIGATION_SNAPSHOT_VERSION
    )

    agentic_delivery_snapshot: (
        InvestigationDeliveryResultV2 | None
    ) = None

    focused_change_snapshots: tuple[
        FocusedChangeBreakdownDeliveryV2,
        ...,
    ] = ()

    geography_exploration_snapshots: tuple[
        FocusedChangeBreakdownDeliveryV2,
        ...,
    ] = ()

    completed_analytical_nodes: tuple[
        AnalyticalPathNodeV2,
        ...,
    ] = ()

    continuation_state_snapshot: (
        Day89InvestigationContinuationStateV2 | None
    ) = None

    prior_stop_status_snapshots: tuple[
        InvestigationStopStatusV2,
        ...,
    ] = ()

    pending_clarification_snapshot: (
        Day89PendingClarificationStateV2 | None
    ) = None

    initial_decision_owner: (
        Literal["system", "user"] | None
    ) = None
    user_selected_action: str | None = None

    @model_validator(mode="after")
    def validate_snapshot(
        self,
    ) -> "AnalysisInvestigationSnapshotV1":
        if self.agentic_delivery_snapshot is not None:
            if self.agentic_delivery_snapshot.status not in {
                InvestigationDeliveryStatusV2.READY,
                InvestigationDeliveryStatusV2.CLARIFICATION_READY,
            }:
                raise ValueError(
                    "History only stores safe READY / "
                    "CLARIFICATION_READY Agentic Delivery."
                )

        if (
            self.continuation_state_snapshot is not None
            and self.agentic_delivery_snapshot is None
        ):
            raise ValueError(
                "Continuation snapshot requires Agentic Delivery."
            )

        if (
            self.pending_clarification_snapshot is not None
            and self.agentic_delivery_snapshot is None
        ):
            raise ValueError(
                "Pending clarification requires Agentic Delivery."
            )

        if (
            self.user_selected_action is not None
            and not self.user_selected_action.strip()
        ):
            raise ValueError(
                "user_selected_action cannot be blank."
            )

        return self


def empty_analysis_investigation_snapshot_v1(
) -> AnalysisInvestigationSnapshotV1:
    return AnalysisInvestigationSnapshotV1()


def _unique_nonempty_v1(
    values: tuple[str, ...],
) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            value
            for value in values
            if isinstance(value, str)
            and value.strip()
        )
    )


def _change_lineage_record_v1(
    *,
    sequence_number: int,
    stage: EvidenceLineageStageV1,
    change: FocusedChangeBreakdownDeliveryV2,
) -> AnalysisEvidenceLineageRecordV1:
    dimension = change.result.dimension_name.value

    labels = {
        "category": "品类变化",
        "area": "大区变化",
        "province": "省级变化",
        "city": "城市变化",
        "campaign": "活动实例变化",
        "region": "城市变化（旧路径）",
    }

    reconciliation = (
        change.result.reconciliation_status.value
        if change.result.reconciliation_status is not None
        else None
    )

    return AnalysisEvidenceLineageRecordV1(
        sequence_number=sequence_number,
        stage=stage,
        business_label=labels.get(
            dimension,
            dimension,
        ),
        dimension=dimension,
        evidence_ids=_unique_nonempty_v1(
            (
                change.reference_evidence_id,
                change.current_evidence_id,
            )
        ),
        plan_names=_unique_nonempty_v1(
            (
                change.reference_plan_name,
                change.current_plan_name,
            )
        ),
        audit_event_ids=_unique_nonempty_v1(
            (
                change.reference_audit_event_id,
                change.current_audit_event_id,
            )
        ),
        scope_summary=change.scope_summary,
        reconciliation_status=reconciliation,
    )


def build_analysis_evidence_lineage_v1(
    *,
    seed_evidence_ids: tuple[str, ...],
    snapshot: AnalysisInvestigationSnapshotV1 | None,
) -> tuple[AnalysisEvidenceLineageRecordV1, ...]:
    """
    构造安全、可恢复的 Evidence Lineage。

    顺序原则：
    1. Seed；
    2. Agentic Delivery 新增 Evidence Pack records；
    3. Investigation Focused Change；
    4. USER Exploration companion evidence。

    Focused Change / Exploration 保存 current + reference evidence，
    因此可以解释“两期变化结论从哪两份受保护结果而来”。
    """

    records: list[AnalysisEvidenceLineageRecordV1] = []
    sequence = 1

    safe_seed_ids = _unique_nonempty_v1(
        seed_evidence_ids
    )

    if safe_seed_ids:
        records.append(
            AnalysisEvidenceLineageRecordV1(
                sequence_number=sequence,
                stage=EvidenceLineageStageV1.SEED,
                business_label="Seed 分析证据",
                evidence_ids=safe_seed_ids,
            )
        )
        sequence += 1

    if snapshot is None:
        return tuple(records)

    agentic = snapshot.agentic_delivery_snapshot
    if (
        agentic is not None
        and agentic.delivery is not None
    ):
        pack_ids = tuple(
            record.reference.evidence_id
            for record in (
                agentic.delivery.evidence_pack.evidence_records
            )
        )
        new_ids = _unique_nonempty_v1(
            tuple(
                evidence_id
                for evidence_id in pack_ids
                if evidence_id not in set(safe_seed_ids)
            )
        )

        if new_ids:
            records.append(
                AnalysisEvidenceLineageRecordV1(
                    sequence_number=sequence,
                    stage=EvidenceLineageStageV1.AGENTIC_PACK,
                    business_label="受控调查 Evidence Pack",
                    evidence_ids=new_ids,
                )
            )
            sequence += 1

    seen_change_signatures: set[
        tuple[str, str, str]
    ] = set()

    for change in snapshot.focused_change_snapshots:
        signature = (
            change.result.dimension_name.value,
            change.reference_evidence_id,
            change.current_evidence_id,
        )
        if signature in seen_change_signatures:
            continue
        seen_change_signatures.add(signature)

        records.append(
            _change_lineage_record_v1(
                sequence_number=sequence,
                stage=(
                    EvidenceLineageStageV1
                    .INVESTIGATION_CHANGE
                ),
                change=change,
            )
        )
        sequence += 1

    for change in snapshot.geography_exploration_snapshots:
        signature = (
            change.result.dimension_name.value,
            change.reference_evidence_id,
            change.current_evidence_id,
        )
        if signature in seen_change_signatures:
            continue
        seen_change_signatures.add(signature)

        records.append(
            _change_lineage_record_v1(
                sequence_number=sequence,
                stage=(
                    EvidenceLineageStageV1
                    .USER_EXPLORATION
                ),
                change=change,
            )
        )
        sequence += 1

    return tuple(records)
