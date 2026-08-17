from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, model_validator

from app.agents.evidence_pack_v2 import (
    EvidenceRecordV2,
    EvidenceTypeV2,
)
from app.agents.investigation_contracts_v2 import (
    EvidenceReferenceV2,
)


class DerivedEvidenceBuildStatusV2(str, Enum):
    """
    Day87 派生证据登记结果。

    这里不重新执行 Anomaly / Contribution 计算，
    只验证其轻量 Evidence Reference 与上游 lineage 是否可登记。
    """

    BUILT = "built"
    INVALID_SOURCE = "invalid_source"
    INVALID_LINEAGE = "invalid_lineage"


class DerivedEvidenceBuildDecisionV2(BaseModel):
    """
    派生证据 Builder 的 fail-closed 决策。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    success: bool
    status: DerivedEvidenceBuildStatusV2
    record: EvidenceRecordV2 | None = None
    detail: str | None = None

    @model_validator(mode="after")
    def validate_decision(
        self,
    ) -> "DerivedEvidenceBuildDecisionV2":
        if self.success:
            if self.status != DerivedEvidenceBuildStatusV2.BUILT:
                raise ValueError(
                    "成功 Build 必须使用 BUILT。"
                )
            if self.record is None:
                raise ValueError(
                    "成功 Build 必须返回 EvidenceRecordV2。"
                )
            if self.detail is not None:
                raise ValueError(
                    "成功 Build 不应携带 failure detail。"
                )
            return self

        if self.status == DerivedEvidenceBuildStatusV2.BUILT:
            raise ValueError(
                "失败 Build 不能使用 BUILT。"
            )
        if self.record is not None:
            raise ValueError(
                "失败 Build 不能释放 EvidenceRecordV2。"
            )
        if not self.detail:
            raise ValueError(
                "失败 Build 必须说明 detail。"
            )

        return self


def _failed(
    *,
    status: DerivedEvidenceBuildStatusV2,
    detail: str,
) -> DerivedEvidenceBuildDecisionV2:
    return DerivedEvidenceBuildDecisionV2(
        success=False,
        status=status,
        record=None,
        detail=detail,
    )


def _validate_parent_evidence_ids(
    *,
    derived_evidence_id: str,
    parent_evidence_ids: tuple[str, ...],
    minimum_count: int,
) -> str | None:
    if len(parent_evidence_ids) < minimum_count:
        return (
            "派生 Evidence 的 parent evidence 数量不足："
            f"minimum={minimum_count}; "
            f"actual={len(parent_evidence_ids)}"
        )

    if any(
        not evidence_id.strip()
        for evidence_id in parent_evidence_ids
    ):
        return "parent_evidence_ids 不能包含空值。"

    if (
        len(set(parent_evidence_ids))
        != len(parent_evidence_ids)
    ):
        return "parent_evidence_ids 不能重复。"

    if derived_evidence_id in parent_evidence_ids:
        return "派生 Evidence 不能把自己声明为 parent。"

    return None


def build_anomaly_evidence_record_v2(
    *,
    evidence_reference: EvidenceReferenceV2,
    parent_evidence_ids: tuple[str, ...],
) -> DerivedEvidenceBuildDecisionV2:
    """
    登记 Day83 deterministic anomaly evidence 的 lineage。

    本 Builder 不重新验证 threshold / sample gate / comparison math。
    这些职责属于 Day83 Detector + Insight Adapter。

    Day87 只要求：
    - source 必须仍然来自 deterministic anomaly detector；
    - 至少存在 current/reference 两侧的上游数据 Evidence；
    - 如果 sample basis 使用独立查询，可继续把 sample Evidence
      作为更多 parent IDs 加入；
    - 最终 parent 是否真的存在，由 EvidencePackV2 统一校验。

    因此本层不会绑定已经漂移过的 Day83 内部字段名。
    """

    if (
        evidence_reference.source
        != "deterministic_anomaly_detector_v2"
    ):
        return _failed(
            status=DerivedEvidenceBuildStatusV2.INVALID_SOURCE,
            detail=(
                "Anomaly Evidence source 必须来自 "
                "deterministic_anomaly_detector_v2。"
            ),
        )

    lineage_error = _validate_parent_evidence_ids(
        derived_evidence_id=evidence_reference.evidence_id,
        parent_evidence_ids=parent_evidence_ids,
        minimum_count=2,
    )

    if lineage_error is not None:
        return _failed(
            status=DerivedEvidenceBuildStatusV2.INVALID_LINEAGE,
            detail=lineage_error,
        )

    record = EvidenceRecordV2(
        reference=evidence_reference,
        evidence_type=EvidenceTypeV2.ANOMALY_DECISION,
        parent_evidence_ids=parent_evidence_ids,
        provenance=None,
        protected_result=None,
    )

    return DerivedEvidenceBuildDecisionV2(
        success=True,
        status=DerivedEvidenceBuildStatusV2.BUILT,
        record=record,
        detail=None,
    )


def build_contribution_evidence_record_v2(
    *,
    evidence_reference: EvidenceReferenceV2,
    current_overall_evidence_id: str,
    reference_overall_evidence_id: str,
    current_dimension_evidence_id: str,
    reference_dimension_evidence_id: str,
) -> DerivedEvidenceBuildDecisionV2:
    """
    登记 Day84 deterministic contribution evidence 的 lineage。

    Day84 当前首版 Contribution 明确依赖四类受保护输入：
    1. current overall；
    2. reference overall；
    3. current dimension；
    4. reference dimension。

    Contribution Builder 不重新计算 delta / ranking / remainder，
    只把这四条上游 Evidence 绑定到派生 Evidence。
    """

    if (
        evidence_reference.source
        != "deterministic_contribution_analysis_v2"
    ):
        return _failed(
            status=DerivedEvidenceBuildStatusV2.INVALID_SOURCE,
            detail=(
                "Contribution Evidence source 必须来自 "
                "deterministic_contribution_analysis_v2。"
            ),
        )

    parent_evidence_ids = (
        current_overall_evidence_id,
        reference_overall_evidence_id,
        current_dimension_evidence_id,
        reference_dimension_evidence_id,
    )

    lineage_error = _validate_parent_evidence_ids(
        derived_evidence_id=evidence_reference.evidence_id,
        parent_evidence_ids=parent_evidence_ids,
        minimum_count=4,
    )

    if lineage_error is not None:
        return _failed(
            status=DerivedEvidenceBuildStatusV2.INVALID_LINEAGE,
            detail=lineage_error,
        )

    record = EvidenceRecordV2(
        reference=evidence_reference,
        evidence_type=EvidenceTypeV2.CONTRIBUTION_RESULT,
        parent_evidence_ids=parent_evidence_ids,
        provenance=None,
        protected_result=None,
    )

    return DerivedEvidenceBuildDecisionV2(
        success=True,
        status=DerivedEvidenceBuildStatusV2.BUILT,
        record=record,
        detail=None,
    )
