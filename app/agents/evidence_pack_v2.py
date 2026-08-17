from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from app.agents.investigation_contracts_v2 import (
    AnalysisScopeV2,
    EvidenceReferenceV2,
    InsightContractV2,
)
from app.semantic_layer.time_comparison_contract_v2 import (
    TimeWindowReferenceV2,
)


class EvidenceTypeV2(str, Enum):
    """
    Evidence Pack 中一条证据的来源类型。

    这里描述“证据是什么”，不描述“证据意味着什么”。
    结论语义仍由 InsightContractV2 负责。
    """

    GOVERNED_QUERY_RESULT = "governed_query_result"
    ANOMALY_DECISION = "anomaly_decision"
    CONTRIBUTION_RESULT = "contribution_result"
    INVESTIGATION_OBSERVATION = "investigation_observation"


class ProtectedResultV2(BaseModel):
    """
    已经通过 Result Protection、允许离开治理边界的结果快照。

    重要边界：
    - 这里只能接收 protected / released rows；
    - 不能用本合同重新包装 raw execution rows；
    - field_names 是允许交付给 Answer / UI 的可见字段；
    - 每一行必须与 field_names 完全一致。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    field_names: tuple[str, ...]
    rows: tuple[dict[str, Any], ...] = ()
    row_count: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_result(self) -> "ProtectedResultV2":
        if not self.field_names:
            raise ValueError(
                "ProtectedResultV2 至少需要一个可见字段。"
            )

        if any(
            not field.strip()
            for field in self.field_names
        ):
            raise ValueError(
                "field_names 不能包含空字段名。"
            )

        if len(set(self.field_names)) != len(self.field_names):
            raise ValueError(
                "field_names 不能重复。"
            )

        if self.row_count != len(self.rows):
            raise ValueError(
                "row_count 必须等于 rows 的实际行数。"
            )

        expected_fields = set(self.field_names)

        for index, row in enumerate(self.rows):
            actual_fields = set(row)
            if actual_fields != expected_fields:
                raise ValueError(
                    "Protected Result 每一行都必须严格匹配 "
                    "field_names。"
                    f" row_index={index}; "
                    f"missing={sorted(expected_fields - actual_fields)}; "
                    f"extra={sorted(actual_fields - expected_fields)}"
                )

        return self


class InvestigationObservationEvidenceV2(BaseModel):
    """
    Day86 ToolObservationV2 在 Evidence Pack 中的交付快照。

    这里只描述“调查动作发生了什么”：
    - EVIDENCE：该动作真实产生了哪些 Evidence；
    - NO_DATA：当前 Scope / Time Window 下执行成功但没有数据；
    - FAILURE：真实执行失败以及 failure_code / retryable。

    Observation 本身不是业务数值事实。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    action_id: str
    attempt_number: int = Field(ge=1)
    status: str
    failure_code: str | None = None
    retryable: bool = False
    summary: str

    @model_validator(mode="after")
    def validate_observation(
        self,
    ) -> "InvestigationObservationEvidenceV2":
        if not self.action_id.strip():
            raise ValueError(
                "Investigation Observation action_id 不能为空。"
            )

        if not self.summary.strip():
            raise ValueError(
                "Investigation Observation summary 不能为空。"
            )

        if self.status not in {
            "evidence",
            "no_data",
            "failure",
        }:
            raise ValueError(
                "Investigation Observation status 只允许 "
                "evidence / no_data / failure。"
            )

        if self.status == "evidence":
            if self.failure_code is not None:
                raise ValueError(
                    "EVIDENCE Observation 不能携带 failure_code。"
                )
            if self.retryable:
                raise ValueError(
                    "EVIDENCE Observation 不能标记 retryable。"
                )

        elif self.status == "no_data":
            if self.failure_code != "no_data":
                raise ValueError(
                    "NO_DATA Observation 必须携带 no_data failure_code。"
                )
            if self.retryable:
                raise ValueError(
                    "NO_DATA 不能标记 retryable。"
                )

        else:
            if self.failure_code is None:
                raise ValueError(
                    "FAILURE Observation 必须携带 failure_code。"
                )
            if self.failure_code == "no_data":
                raise ValueError(
                    "NO_DATA 必须使用 no_data status，而不是 failure。"
                )

        return self


class GovernedEvidenceProvenanceV2(BaseModel):
    """
    一条 Governed Query / Tool Evidence 的可信来源信息。

    第一版只保留“可验证身份”和“交付必要信息”：
    - 不复制 raw SQL；
    - 不复制 SQL parameters；
    - 不复制 actor 的敏感身份信息；
    - 使用既有 Query Plan / Envelope / Compiler / Audit fingerprint
      证明这条证据来自哪条可信执行链。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    dataset_name: str
    target_schema: str

    metric_name: str
    result_grain: str
    analysis_window: TimeWindowReferenceV2
    scope_summary: str | None = None

    plan_name: str
    query_plan_fingerprint: str
    envelope_fingerprint: str
    compiled_contract_fingerprint: str
    sql_fingerprint: str
    time_binding_fingerprint: str
    scope_binding_fingerprint: str

    tool_name: str
    tool_version: str

    audit_event_id: str
    audit_event_fingerprint: str
    audit_record_hash: str
    finalization_contract_version: str

    @model_validator(mode="after")
    def validate_provenance(
        self,
    ) -> "GovernedEvidenceProvenanceV2":
        required_values = {
            "dataset_name": self.dataset_name,
            "target_schema": self.target_schema,
            "metric_name": self.metric_name,
            "result_grain": self.result_grain,
            "plan_name": self.plan_name,
            "query_plan_fingerprint": self.query_plan_fingerprint,
            "envelope_fingerprint": self.envelope_fingerprint,
            "compiled_contract_fingerprint": (
                self.compiled_contract_fingerprint
            ),
            "sql_fingerprint": self.sql_fingerprint,
            "time_binding_fingerprint": (
                self.time_binding_fingerprint
            ),
            "scope_binding_fingerprint": (
                self.scope_binding_fingerprint
            ),
            "tool_name": self.tool_name,
            "tool_version": self.tool_version,
            "audit_event_id": self.audit_event_id,
            "audit_event_fingerprint": (
                self.audit_event_fingerprint
            ),
            "audit_record_hash": self.audit_record_hash,
            "finalization_contract_version": (
                self.finalization_contract_version
            ),
        }

        empty_fields = [
            name
            for name, value in required_values.items()
            if not value.strip()
        ]

        if empty_fields:
            raise ValueError(
                "Governed Evidence Provenance 不能包含空字段："
                f"{sorted(empty_fields)}"
            )

        if (
            self.scope_summary is not None
            and not self.scope_summary.strip()
        ):
            raise ValueError(
                "scope_summary 提供时不能是空字符串。"
            )

        return self


class EvidenceRecordV2(BaseModel):
    """
    Evidence Pack 中的一条结构化证据记录。

    reference：
    与 Day82 Insight 中的 evidence_id / source 保持兼容。

    parent_evidence_ids：
    用于表达“这条派生证据依赖哪些上游证据”。
    第一版只保证引用存在，不尝试做完整 DAG / cycle engine。

    provenance / protected_result：
    Governed Query Result 必须同时具备；
    deterministic anomaly / contribution 可以是派生证据，
    不强迫它们伪造不存在的 SQL provenance。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    reference: EvidenceReferenceV2
    evidence_type: EvidenceTypeV2
    parent_evidence_ids: tuple[str, ...] = ()

    provenance: GovernedEvidenceProvenanceV2 | None = None
    protected_result: ProtectedResultV2 | None = None
    investigation_observation: (
        InvestigationObservationEvidenceV2 | None
    ) = None

    @model_validator(mode="after")
    def validate_record(self) -> "EvidenceRecordV2":
        if any(
            not evidence_id.strip()
            for evidence_id in self.parent_evidence_ids
        ):
            raise ValueError(
                "parent_evidence_ids 不能包含空值。"
            )

        if (
            len(set(self.parent_evidence_ids))
            != len(self.parent_evidence_ids)
        ):
            raise ValueError(
                "parent_evidence_ids 不能重复。"
            )

        if self.reference.evidence_id in self.parent_evidence_ids:
            raise ValueError(
                "Evidence 不能把自己声明为 parent evidence。"
            )

        if (
            self.evidence_type
            == EvidenceTypeV2.GOVERNED_QUERY_RESULT
        ):
            if self.provenance is None:
                raise ValueError(
                    "Governed Query Result 必须包含 provenance。"
                )
            if self.protected_result is None:
                raise ValueError(
                    "Governed Query Result 必须包含 protected_result。"
                )

        if (
            self.protected_result is not None
            and self.provenance is None
        ):
            raise ValueError(
                "携带 protected_result 的 Evidence 必须同时包含 "
                "Governed provenance。"
            )

        if (
            self.evidence_type
            == EvidenceTypeV2.INVESTIGATION_OBSERVATION
        ):
            if self.investigation_observation is None:
                raise ValueError(
                    "Investigation Observation Evidence 必须包含 "
                    "investigation_observation。"
                )

            if self.provenance is not None:
                raise ValueError(
                    "Investigation Observation Record 不直接伪装成 "
                    "Governed Query provenance。"
                )

            if self.protected_result is not None:
                raise ValueError(
                    "Investigation Observation Record 不直接携带 "
                    "protected_result；真实结果应作为 parent Evidence。"
                )

            if (
                self.investigation_observation.status
                == "evidence"
                and not self.parent_evidence_ids
            ):
                raise ValueError(
                    "EVIDENCE Observation 必须引用真实 produced Evidence "
                    "作为 parent_evidence_ids。"
                )

            if (
                self.investigation_observation.status
                in {"no_data", "failure"}
                and self.parent_evidence_ids
            ):
                raise ValueError(
                    "NO_DATA / FAILURE Observation 当前不能伪造 "
                    "produced Evidence lineage。"
                )

        elif self.investigation_observation is not None:
            raise ValueError(
                "只有 INVESTIGATION_OBSERVATION Evidence 才能携带 "
                "investigation_observation。"
            )

        return self


class EpistemicBoundaryV2(BaseModel):
    """
    Day87 Evidence Pack 的认知 / 推荐边界。

    这些不是让调用方自由配置的“偏好”，而是当前项目硬边界：
    - confirmed claim 必须有 evidence；
    - candidate explanation 也必须有 supporting evidence；
    - contribution / correlation 不能自动升级成 causality；
    - 当前系统只能推荐“下一步检查”，不能自主下业务执行决策。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    confirmed_claim_requires_evidence: bool = True
    candidate_explanation_requires_evidence: bool = True
    causal_attribution_allowed: bool = False
    autonomous_business_action_allowed: bool = False

    @model_validator(mode="after")
    def validate_boundary(
        self,
    ) -> "EpistemicBoundaryV2":
        if not self.confirmed_claim_requires_evidence:
            raise ValueError(
                "Evidence Pack 不允许关闭 confirmed claim evidence gate。"
            )

        if not self.candidate_explanation_requires_evidence:
            raise ValueError(
                "Evidence Pack 不允许无证据 Candidate Explanation。"
            )

        if self.causal_attribution_allowed:
            raise ValueError(
                "当前项目不支持把 Evidence Pack 升级为因果归因。"
            )

        if self.autonomous_business_action_allowed:
            raise ValueError(
                "当前项目不允许 Evidence Pack 自主执行或批准业务动作。"
            )

        return self


class EvidencePackV2(BaseModel):
    """
    Day87 第一版 Evidence Pack。

    InsightContractV2 负责“准备说什么”；
    EvidencePackV2 负责“这些话凭什么可以说，以及证据从哪来”。

    它不是新的推理层，也不会重新定义 Metric / Scope / SQL。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    contract_version: str = "evidence_pack_v2_0"

    pack_id: str
    analysis_scope: AnalysisScopeV2
    insight: InsightContractV2
    evidence_records: tuple[EvidenceRecordV2, ...]

    epistemic_boundary: EpistemicBoundaryV2 = (
        EpistemicBoundaryV2()
    )

    @model_validator(mode="after")
    def validate_pack(self) -> "EvidencePackV2":
        if not self.pack_id.strip():
            raise ValueError(
                "pack_id 不能为空。"
            )

        if self.insight.analysis_scope != self.analysis_scope:
            raise ValueError(
                "Evidence Pack analysis_scope 必须与 Insight 完全一致。"
            )

        if (
            self.analysis_scope.comparison is not None
            and self.analysis_scope.analysis_window
            != self.analysis_scope.comparison.current_window
        ):
            raise ValueError(
                "Comparison Evidence Pack 的 analysis_window "
                "必须等于 comparison.current_window。"
            )

        record_ids = [
            record.reference.evidence_id
            for record in self.evidence_records
        ]

        if len(set(record_ids)) != len(record_ids):
            raise ValueError(
                "Evidence Pack 中 evidence_id 不能重复。"
            )

        record_by_id = {
            record.reference.evidence_id: record
            for record in self.evidence_records
        }
        record_id_set = set(record_by_id)

        insight_reference_by_id = {
            item.evidence_id: item
            for item in self.insight.evidence
        }

        missing_records = (
            set(insight_reference_by_id)
            - record_id_set
        )

        if missing_records:
            raise ValueError(
                "Insight 中的 Evidence 必须全部进入 Evidence Pack："
                f"{sorted(missing_records)}"
            )

        for evidence_id, insight_reference in (
            insight_reference_by_id.items()
        ):
            if (
                record_by_id[evidence_id].reference
                != insight_reference
            ):
                raise ValueError(
                    "Evidence Pack record 必须保留 Insight 中相同 "
                    "evidence_id 的原始 reference。"
                    f" evidence_id={evidence_id}"
                )

        for record in self.evidence_records:
            missing_parents = (
                set(record.parent_evidence_ids)
                - record_id_set
            )
            if missing_parents:
                raise ValueError(
                    "parent_evidence_ids 必须引用当前 Pack 内证据："
                    f"{sorted(missing_parents)}"
                )

            provenance = record.provenance
            if provenance is None:
                continue

            if provenance.metric_name != self.analysis_scope.metric_name:
                raise ValueError(
                    "Evidence provenance metric 必须与 "
                    "Evidence Pack analysis_scope metric 一致。"
                )

            allowed_windows = {
                self.analysis_scope.analysis_window,
            }

            if self.analysis_scope.comparison is not None:
                allowed_windows.add(
                    self.analysis_scope.comparison.reference_window
                )

            if provenance.analysis_window not in allowed_windows:
                raise ValueError(
                    "Governed Evidence 的 analysis_window 必须属于 "
                    "当前分析的 current / reference window。"
                )

        # Day82 的 CandidateExplanationV2 为兼容早期合同允许空证据。
        # Day87 交付 Gate 在这里收紧：没有 supporting evidence 就不能发布。
        for explanation in self.insight.candidate_explanations:
            if not explanation.supporting_evidence_ids:
                raise ValueError(
                    "Evidence Pack 不允许无 supporting evidence 的 "
                    "Candidate Explanation；应改为 Unknown + "
                    "Recommended Check。"
                )

            missing_support = (
                set(explanation.supporting_evidence_ids)
                - record_id_set
            )
            if missing_support:
                raise ValueError(
                    "Candidate Explanation 引用的 Evidence "
                    "必须存在于当前 Pack："
                    f"{sorted(missing_support)}"
                )

        # 再次显式检查所有“被支持结论”的 Evidence 都进入 Pack。
        supported_ids: set[str] = set()

        for statement in (
            *self.insight.confirmed_facts,
            *self.insight.detected_anomalies,
            *self.insight.dimension_contributions,
        ):
            supported_ids.update(statement.evidence_ids)

        for check in self.insight.recommended_checks:
            supported_ids.update(check.evidence_ids)

        missing_supported = supported_ids - record_id_set

        if missing_supported:
            raise ValueError(
                "被 Insight 引用的 Evidence 必须存在于 Evidence Pack："
                f"{sorted(missing_supported)}"
            )

        # Day87 交付层进一步限制：
        # “Evidence 存在”不等于“任何 Evidence 都能支撑任何结论”。
        for statement in self.insight.confirmed_facts:
            for evidence_id in statement.evidence_ids:
                if (
                    record_by_id[evidence_id].evidence_type
                    != EvidenceTypeV2.GOVERNED_QUERY_RESULT
                ):
                    raise ValueError(
                        "Confirmed Fact 第一版只允许由 "
                        "Governed Query Result 直接支撑。"
                        f" evidence_id={evidence_id}"
                    )

        for statement in self.insight.detected_anomalies:
            for evidence_id in statement.evidence_ids:
                if (
                    record_by_id[evidence_id].evidence_type
                    != EvidenceTypeV2.ANOMALY_DECISION
                ):
                    raise ValueError(
                        "Detected Anomaly 必须由 "
                        "ANOMALY_DECISION Evidence 支撑。"
                        f" evidence_id={evidence_id}"
                    )

        for statement in self.insight.dimension_contributions:
            for evidence_id in statement.evidence_ids:
                if (
                    record_by_id[evidence_id].evidence_type
                    != EvidenceTypeV2.CONTRIBUTION_RESULT
                ):
                    raise ValueError(
                        "Dimension Contribution 必须由 "
                        "CONTRIBUTION_RESULT Evidence 支撑。"
                        f" evidence_id={evidence_id}"
                    )

        return self
