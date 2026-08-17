from __future__ import annotations

from pydantic import BaseModel, ConfigDict, model_validator

from app.agents.evidence_pack_v2 import (
    EvidenceRecordV2,
    EvidenceTypeV2,
    InvestigationObservationEvidenceV2,
)
from app.agents.investigation_contracts_v2 import (
    EvidenceReferenceV2,
)
from app.agents.investigation_loop_v2 import (
    ToolObservationStatusV2,
    ToolObservationV2,
)


class InvestigationObservationBuildDecisionV2(BaseModel):
    """
    Day86 ToolObservation → Day87 Evidence Record 的确定性 Adapter。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    success: bool
    record: EvidenceRecordV2 | None = None
    detail: str | None = None

    @model_validator(mode="after")
    def validate_decision(
        self,
    ) -> "InvestigationObservationBuildDecisionV2":
        if self.success:
            if self.record is None:
                raise ValueError(
                    "成功 Build 必须返回 EvidenceRecordV2。"
                )
            if self.detail is not None:
                raise ValueError(
                    "成功 Build 不应携带 failure detail。"
                )
        else:
            if self.record is not None:
                raise ValueError(
                    "失败 Build 不能释放 EvidenceRecordV2。"
                )
            if not self.detail:
                raise ValueError(
                    "失败 Build 必须说明 detail。"
                )

        return self


def build_investigation_observation_evidence_v2(
    *,
    evidence_reference: EvidenceReferenceV2,
    observation: ToolObservationV2,
) -> InvestigationObservationBuildDecisionV2:
    """
    将 Day86 的受保护 ToolObservation 登记成 Day87 Investigation Evidence。

    规则：
    - EVIDENCE Observation 的 produced_evidence_ids 作为 parent lineage；
    - NO_DATA / FAILURE 不产生业务数据 Evidence，因此 parent 为空；
    - Observation 只证明“调查动作发生了什么”，不能单独证明业务数值事实；
    - 不重新执行 Tool，不读取 raw SQL / raw rows。
    """

    if evidence_reference.source != "investigation_loop_v2":
        return InvestigationObservationBuildDecisionV2(
            success=False,
            detail=(
                "Investigation Observation Evidence source 必须是 "
                "investigation_loop_v2。"
            ),
        )

    if observation.status == ToolObservationStatusV2.EVIDENCE:
        parent_evidence_ids = observation.produced_evidence_ids
    else:
        parent_evidence_ids = ()

    snapshot = InvestigationObservationEvidenceV2(
        action_id=observation.action_id,
        attempt_number=observation.attempt_number,
        status=observation.status.value,
        failure_code=(
            observation.failure_code.value
            if observation.failure_code is not None
            else None
        ),
        retryable=observation.retryable,
        summary=observation.summary,
    )

    record = EvidenceRecordV2(
        reference=evidence_reference,
        evidence_type=EvidenceTypeV2.INVESTIGATION_OBSERVATION,
        parent_evidence_ids=parent_evidence_ids,
        provenance=None,
        protected_result=None,
        investigation_observation=snapshot,
    )

    return InvestigationObservationBuildDecisionV2(
        success=True,
        record=record,
        detail=None,
    )
