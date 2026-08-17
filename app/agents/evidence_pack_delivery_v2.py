from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.agents.evidence_pack_v2 import (
    EvidencePackV2,
    EvidenceTypeV2,
)


class EvidenceSufficiencyStatusV2(str, Enum):
    """
    Evidence Pack 对“当前请求范围”的证据充分度。

    注意：
    这不是统计置信概率，也不是 LLM 自评分数。
    """

    SUFFICIENT_FOR_CURRENT_SCOPE = (
        "sufficient_for_current_scope"
    )
    PARTIAL = "partial"
    INSUFFICIENT = "insufficient"


class EvidenceConfidenceLevelV2(str, Enum):
    """
    用户可见的证据支持强度。

    不提供 0~1 数字，避免伪精确。
    """

    EVIDENCE_BACKED = "evidence_backed"
    PARTIAL_EVIDENCE = "partial_evidence"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class MetricDefinitionSnapshotV2(BaseModel):
    """
    Evidence Delivery 中的业务指标定义快照。

    这不是让 Agent 重新定义 Metric，而是把已经冻结在
    Business Semantic Layer 中的定义随 Evidence 一起交付，
    方便 Day89 UI / Audit / Human Review 回答：

    “这里的 GMV 到底按什么口径算？”
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    metadata_version: str
    dataset_name: str
    metric_name: str
    chinese_name: str
    grain: str
    definition: str
    formula: str
    filters: tuple[str, ...] = ()
    metric_fingerprint: str

    @model_validator(mode="after")
    def validate_snapshot(
        self,
    ) -> "MetricDefinitionSnapshotV2":
        required = {
            "metadata_version": self.metadata_version,
            "dataset_name": self.dataset_name,
            "metric_name": self.metric_name,
            "chinese_name": self.chinese_name,
            "grain": self.grain,
            "definition": self.definition,
            "formula": self.formula,
            "metric_fingerprint": self.metric_fingerprint,
        }

        empty = [
            name
            for name, value in required.items()
            if not value.strip()
        ]

        if empty:
            raise ValueError(
                "Metric Definition Snapshot 不能包含空字段："
                f"{sorted(empty)}"
            )

        if any(
            not item.strip()
            for item in self.filters
        ):
            raise ValueError(
                "Metric filters 不能包含空字符串。"
            )

        return self


class EvidenceSufficiencyAssessmentV2(BaseModel):
    """
    对最终 Evidence Pack 的确定性充分度摘要。

    assessment 只描述：
    - 当前 Pack 能确认多少；
    - 是否仍有 Hypothesis / Unknown / Recommended Check；
    - 是否还有未解决调查方向。

    它不声明“业务原因已被证明”，也不输出概率。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    status: EvidenceSufficiencyStatusV2
    confidence_level: EvidenceConfidenceLevelV2

    supported_claim_count: int = Field(ge=0)
    confirmed_fact_count: int = Field(ge=0)
    anomaly_count: int = Field(ge=0)
    contribution_count: int = Field(ge=0)
    candidate_hypothesis_count: int = Field(ge=0)
    unknown_count: int = Field(ge=0)
    recommended_check_count: int = Field(ge=0)

    basis: tuple[str, ...]

    @model_validator(mode="after")
    def validate_assessment(
        self,
    ) -> "EvidenceSufficiencyAssessmentV2":
        if not self.basis:
            raise ValueError(
                "Evidence Sufficiency Assessment 必须说明 basis。"
            )

        if any(
            not item.strip()
            for item in self.basis
        ):
            raise ValueError(
                "Evidence Sufficiency basis 不能包含空值。"
            )

        expected_supported = (
            self.confirmed_fact_count
            + self.anomaly_count
            + self.contribution_count
            + self.candidate_hypothesis_count
        )

        if self.supported_claim_count != expected_supported:
            raise ValueError(
                "supported_claim_count 与各类 claim 数量不一致。"
            )

        mapping = {
            EvidenceSufficiencyStatusV2.SUFFICIENT_FOR_CURRENT_SCOPE:
                EvidenceConfidenceLevelV2.EVIDENCE_BACKED,
            EvidenceSufficiencyStatusV2.PARTIAL:
                EvidenceConfidenceLevelV2.PARTIAL_EVIDENCE,
            EvidenceSufficiencyStatusV2.INSUFFICIENT:
                EvidenceConfidenceLevelV2.INSUFFICIENT_EVIDENCE,
        }

        if self.confidence_level != mapping[self.status]:
            raise ValueError(
                "confidence_level 必须由 sufficiency status "
                "确定性映射，不能自由填写。"
            )

        return self


class EvidencePackDeliveryV2(BaseModel):
    """
    Day87 最终 Evidence Delivery Contract。

    EvidencePackV2：
    → 证据记录、lineage、Insight 与 epistemic gate。

    MetricDefinitionSnapshotV2：
    → Business Semantic Layer 的指标口径快照。

    EvidenceSufficiencyAssessmentV2：
    → 当前证据支持强度与未解决边界。

    该 Delivery Contract 是 Day88 Evaluation / Day89 Decision Console
    的稳定输入，不是新的推理引擎。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    contract_version: str = "evidence_pack_delivery_v2_0"

    evidence_pack: EvidencePackV2
    metric_definition: MetricDefinitionSnapshotV2
    sufficiency: EvidenceSufficiencyAssessmentV2

    @model_validator(mode="after")
    def validate_delivery(
        self,
    ) -> "EvidencePackDeliveryV2":
        scope = self.evidence_pack.analysis_scope

        if (
            self.metric_definition.metric_name
            != scope.metric_name
        ):
            raise ValueError(
                "Metric Definition 与 Evidence Pack metric 不一致。"
            )

        governed_datasets = {
            record.provenance.dataset_name
            for record in self.evidence_pack.evidence_records
            if (
                record.evidence_type
                == EvidenceTypeV2.GOVERNED_QUERY_RESULT
                and record.provenance is not None
            )
        }

        if (
            governed_datasets
            and governed_datasets
            != {self.metric_definition.dataset_name}
        ):
            raise ValueError(
                "Metric Definition dataset 与 Governed Evidence "
                "dataset 不一致。"
            )

        expected = assess_evidence_sufficiency_v2(
            self.evidence_pack
        )

        if self.sufficiency != expected:
            raise ValueError(
                "Evidence Sufficiency 必须由当前 Evidence Pack "
                "确定性计算，不能由调用方自由改写。"
            )

        return self


def _canonical_metric_payload(
    *,
    metadata_version: str,
    dataset_name: str,
    metric: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "metadata_version": metadata_version.strip(),
        "dataset_name": dataset_name.strip(),
        "metric_name": str(metric["name"]).strip(),
        "chinese_name": str(metric["chinese_name"]).strip(),
        "grain": str(metric["grain"]).strip(),
        "definition": str(metric["definition"]).strip(),
        "formula": str(metric["formula"]).strip(),
        "filters": tuple(
            str(item).strip()
            for item in metric.get("filters", ())
        ),
    }


def build_metric_definition_snapshot_v2(
    *,
    metadata_catalog: Mapping[str, Any],
    metric_name: str,
) -> MetricDefinitionSnapshotV2:
    """
    从系统已加载的 Business Metrics Catalog 构建 Metric 快照。

    Builder 不接受模型自己给 formula / definition。
    调用方应传入项目可信 Metadata Catalog 的反序列化结果。
    """

    metadata_version = str(
        metadata_catalog.get("metadata_version", "")
    ).strip()
    dataset_name = str(
        metadata_catalog.get("dataset_name", "")
    ).strip()

    metrics = metadata_catalog.get("metrics")

    if (
        not metadata_version
        or not dataset_name
        or not isinstance(metrics, list)
    ):
        raise ValueError(
            "Metadata Catalog 缺少 metadata_version / "
            "dataset_name / metrics。"
        )

    matches = [
        metric
        for metric in metrics
        if (
            isinstance(metric, Mapping)
            and str(metric.get("name", "")).strip()
            == metric_name
        )
    ]

    if len(matches) != 1:
        raise ValueError(
            "Metric Definition Builder 必须唯一命中 metric："
            f"metric_name={metric_name}; matches={len(matches)}"
        )

    payload = _canonical_metric_payload(
        metadata_version=metadata_version,
        dataset_name=dataset_name,
        metric=matches[0],
    )

    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    fingerprint = hashlib.sha256(
        serialized
    ).hexdigest()

    return MetricDefinitionSnapshotV2(
        **payload,
        metric_fingerprint=fingerprint,
    )


def assess_evidence_sufficiency_v2(
    evidence_pack: EvidencePackV2,
) -> EvidenceSufficiencyAssessmentV2:
    """
    用 Pack 中已经通过 Epistemic Gate 的结构化内容，
    确定性计算证据充分度。

    第一版采用保守规则：

    1. 没有任何可发布 claim：
       → INSUFFICIENT

    2. 有 claim，但仍存在 Candidate Hypothesis / Unknown /
       Recommended Check：
       → PARTIAL

    3. 至少有一条已支持 claim，且没有上述未解决内容：
       → SUFFICIENT_FOR_CURRENT_SCOPE

    “当前范围充分”不等于因果证明，也不等于调查了所有可能维度。
    """

    insight = evidence_pack.insight

    confirmed_count = len(insight.confirmed_facts)
    anomaly_count = len(insight.detected_anomalies)
    contribution_count = len(
        insight.dimension_contributions
    )
    candidate_count = len(
        insight.candidate_explanations
    )
    unknown_count = len(insight.unknowns)
    recommended_count = len(
        insight.recommended_checks
    )

    supported_claim_count = (
        confirmed_count
        + anomaly_count
        + contribution_count
        + candidate_count
    )

    if supported_claim_count == 0:
        status = EvidenceSufficiencyStatusV2.INSUFFICIENT
        confidence = (
            EvidenceConfidenceLevelV2.INSUFFICIENT_EVIDENCE
        )
        basis = (
            "当前 Evidence Pack 没有可发布的 evidence-backed claim。",
            "可以保留 Unknown / Recommended Check，但不能冒充业务结论。",
        )

    elif (
        candidate_count > 0
        or unknown_count > 0
        or recommended_count > 0
    ):
        status = EvidenceSufficiencyStatusV2.PARTIAL
        confidence = (
            EvidenceConfidenceLevelV2.PARTIAL_EVIDENCE
        )
        basis = (
            "当前 Pack 已存在 evidence-backed claim。",
            "仍存在 Candidate Hypothesis / Unknown / "
            "Recommended Check，因此调查结论保持部分充分。",
        )

    else:
        status = (
            EvidenceSufficiencyStatusV2
            .SUFFICIENT_FOR_CURRENT_SCOPE
        )
        confidence = (
            EvidenceConfidenceLevelV2.EVIDENCE_BACKED
        )
        basis = (
            "当前 Pack 至少存在一条 evidence-backed claim。",
            "当前交付范围内没有未解决 Hypothesis / Unknown / "
            "Recommended Check。",
            "该结论仅表示当前 Scope 的证据支持充分，不代表因果证明。",
        )

    return EvidenceSufficiencyAssessmentV2(
        status=status,
        confidence_level=confidence,
        supported_claim_count=supported_claim_count,
        confirmed_fact_count=confirmed_count,
        anomaly_count=anomaly_count,
        contribution_count=contribution_count,
        candidate_hypothesis_count=candidate_count,
        unknown_count=unknown_count,
        recommended_check_count=recommended_count,
        basis=basis,
    )


def assemble_evidence_pack_delivery_v2(
    *,
    evidence_pack: EvidencePackV2,
    metric_definition: MetricDefinitionSnapshotV2,
) -> EvidencePackDeliveryV2:
    """
    组装 Day87 最终 Evidence Delivery。

    Sufficiency / Confidence 不接受外部输入，
    必须由 Evidence Pack 自动计算。
    """

    assessment = assess_evidence_sufficiency_v2(
        evidence_pack
    )

    return EvidencePackDeliveryV2(
        evidence_pack=evidence_pack,
        metric_definition=metric_definition,
        sufficiency=assessment,
    )
