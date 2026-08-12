from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, model_validator

from app.semantic_layer.time_comparison_contract_v2 import (
    TimeComparisonContractV2,
    TimeWindowReferenceV2,
)


class AnalysisModeV2(str, Enum):
    FACT = "fact"
    COMPARISON = "comparison"
    DIAGNOSTIC = "diagnostic"
    INVESTIGATION = "investigation"


class AnalysisScopeV2(BaseModel):
    """
    Scope of one Phase4 insight result.

    Structured authorization scope remains owned by the existing
    governance layer. This contract only carries the released summary.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    metric_name: str
    analysis_window: TimeWindowReferenceV2
    comparison: TimeComparisonContractV2 | None = None
    result_grain: str | None = None
    scope_summary: str | None = None

    @model_validator(mode="after")
    def validate_scope(self) -> "AnalysisScopeV2":
        if not self.metric_name.strip():
            raise ValueError("metric_name cannot be empty.")

        if (
            self.result_grain is not None
            and not self.result_grain.strip()
        ):
            raise ValueError(
                "result_grain cannot be blank when provided."
            )

        if (
            self.scope_summary is not None
            and not self.scope_summary.strip()
        ):
            raise ValueError(
                "scope_summary cannot be blank when provided."
            )

        return self


class EvidenceReferenceV2(BaseModel):
    """
    Lightweight Day82 evidence reference.

    Day87 will define the richer Evidence Pack.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    evidence_id: str
    source: str
    description: str | None = None

    @model_validator(mode="after")
    def validate_reference(self) -> "EvidenceReferenceV2":
        if not self.evidence_id.strip():
            raise ValueError("evidence_id cannot be empty.")

        if not self.source.strip():
            raise ValueError("evidence source cannot be empty.")

        if (
            self.description is not None
            and not self.description.strip()
        ):
            raise ValueError(
                "description cannot be blank when provided."
            )

        return self


class SupportedInsightStatementV2(BaseModel):
    """
    A statement that is presented as supported by trusted evidence.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    statement: str
    evidence_ids: tuple[str, ...]

    @model_validator(mode="after")
    def validate_statement(self) -> "SupportedInsightStatementV2":
        if not self.statement.strip():
            raise ValueError("statement cannot be empty.")

        if not self.evidence_ids:
            raise ValueError(
                "Supported statements require evidence_ids."
            )

        if any(
            not evidence_id.strip()
            for evidence_id in self.evidence_ids
        ):
            raise ValueError(
                "evidence_ids cannot contain blank values."
            )

        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError(
                "evidence_ids cannot contain duplicates."
            )

        return self


class CandidateExplanationV2(BaseModel):
    """
    A hypothesis, not a confirmed fact.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    explanation: str
    supporting_evidence_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_explanation(self) -> "CandidateExplanationV2":
        if not self.explanation.strip():
            raise ValueError("explanation cannot be empty.")

        if any(
            not evidence_id.strip()
            for evidence_id in self.supporting_evidence_ids
        ):
            raise ValueError(
                "supporting_evidence_ids cannot contain blanks."
            )

        if (
            len(set(self.supporting_evidence_ids))
            != len(self.supporting_evidence_ids)
        ):
            raise ValueError(
                "supporting_evidence_ids cannot contain duplicates."
            )

        return self


class UnknownV2(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    description: str

    @model_validator(mode="after")
    def validate_unknown(self) -> "UnknownV2":
        if not self.description.strip():
            raise ValueError("unknown description cannot be empty.")
        return self


class RecommendedCheckV2(BaseModel):
    """
    A next investigation check, not an asserted business action.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    check: str
    rationale: str | None = None
    evidence_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_check(self) -> "RecommendedCheckV2":
        if not self.check.strip():
            raise ValueError("recommended check cannot be empty.")

        if (
            self.rationale is not None
            and not self.rationale.strip()
        ):
            raise ValueError(
                "rationale cannot be blank when provided."
            )

        if any(
            not evidence_id.strip()
            for evidence_id in self.evidence_ids
        ):
            raise ValueError(
                "evidence_ids cannot contain blank values."
            )

        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError(
                "evidence_ids cannot contain duplicates."
            )

        return self


class InsightContractV2(BaseModel):
    """
    Phase4 structured insight contract for the Dataset V2 candidate path.

    Facts, anomalies, and contributions are evidence-backed statements.
    Candidate explanations remain hypotheses.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    analysis_mode: AnalysisModeV2
    analysis_scope: AnalysisScopeV2

    confirmed_facts: tuple[SupportedInsightStatementV2, ...] = ()
    detected_anomalies: tuple[SupportedInsightStatementV2, ...] = ()
    dimension_contributions: tuple[
        SupportedInsightStatementV2, ...
    ] = ()
    candidate_explanations: tuple[CandidateExplanationV2, ...] = ()
    unknowns: tuple[UnknownV2, ...] = ()
    recommended_checks: tuple[RecommendedCheckV2, ...] = ()
    evidence: tuple[EvidenceReferenceV2, ...] = ()

    @model_validator(mode="after")
    def validate_contract(self) -> "InsightContractV2":
        if (
            self.analysis_mode == AnalysisModeV2.FACT
            and self.analysis_scope.comparison is not None
        ):
            raise ValueError(
                "FACT mode cannot carry a comparison contract."
            )

        if (
            self.analysis_mode == AnalysisModeV2.COMPARISON
            and self.analysis_scope.comparison is None
        ):
            raise ValueError(
                "COMPARISON mode requires a comparison contract."
            )

        if self.analysis_mode in {
            AnalysisModeV2.FACT,
            AnalysisModeV2.COMPARISON,
        }:
            if any(
                (
                    self.detected_anomalies,
                    self.dimension_contributions,
                    self.candidate_explanations,
                    self.recommended_checks,
                )
            ):
                raise ValueError(
                    "FACT / COMPARISON mode cannot silently "
                    "escalate into diagnostic or investigation output."
                )

        evidence_ids = [
            item.evidence_id
            for item in self.evidence
        ]

        if len(set(evidence_ids)) != len(evidence_ids):
            raise ValueError(
                "Insight evidence_id values must be unique."
            )

        evidence_id_set = set(evidence_ids)

        referenced_ids: set[str] = set()

        for item in (
            *self.confirmed_facts,
            *self.detected_anomalies,
            *self.dimension_contributions,
        ):
            referenced_ids.update(item.evidence_ids)

        for item in self.candidate_explanations:
            referenced_ids.update(
                item.supporting_evidence_ids
            )

        for item in self.recommended_checks:
            referenced_ids.update(item.evidence_ids)

        missing_ids = referenced_ids - evidence_id_set

        if missing_ids:
            raise ValueError(
                "Insight statements reference unknown evidence_ids: "
                f"{sorted(missing_ids)}"
            )

        return self


class ToolFailureCodeV2(str, Enum):
    INVALID_INPUT = "invalid_input"
    UNAUTHORIZED = "unauthorized"
    UNSUPPORTED = "unsupported"
    TIMEOUT = "timeout"
    NO_DATA = "no_data"
    EXECUTION_FAILURE = "execution_failure"


class ToolIdentityV2(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    name: str
    version: str
    purpose: str

    @model_validator(mode="after")
    def validate_identity(self) -> "ToolIdentityV2":
        for field_name, value in (
            ("name", self.name),
            ("version", self.version),
            ("purpose", self.purpose),
        ):
            if not value.strip():
                raise ValueError(f"{field_name} cannot be empty.")
        return self


class ToolContractV2(BaseModel):
    """
    Contract between the future Agentic Investigation Plane
    and an existing governed executor.

    This is a static boundary definition only. It does not perform
    tool calling or agent planning.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    identity: ToolIdentityV2
    input_schema_name: str
    output_schema_name: str
    required_permissions: tuple[str, ...] = ()
    execution_policy_reference: str
    failure_semantics: tuple[ToolFailureCodeV2, ...]
    executor_binding: str

    accepts_raw_sql: bool = False
    accepts_metric_formula: bool = False
    requires_governed_executor: bool = True

    @model_validator(mode="after")
    def validate_contract(self) -> "ToolContractV2":
        for field_name, value in (
            ("input_schema_name", self.input_schema_name),
            ("output_schema_name", self.output_schema_name),
            (
                "execution_policy_reference",
                self.execution_policy_reference,
            ),
            ("executor_binding", self.executor_binding),
        ):
            if not value.strip():
                raise ValueError(f"{field_name} cannot be empty.")

        if any(
            not permission.strip()
            for permission in self.required_permissions
        ):
            raise ValueError(
                "required_permissions cannot contain blank values."
            )

        if (
            len(set(self.required_permissions))
            != len(self.required_permissions)
        ):
            raise ValueError(
                "required_permissions cannot contain duplicates."
            )

        if not self.failure_semantics:
            raise ValueError(
                "Tool contract must declare failure semantics."
            )

        if (
            len(set(self.failure_semantics))
            != len(self.failure_semantics)
        ):
            raise ValueError(
                "failure_semantics cannot contain duplicates."
            )

        if self.accepts_raw_sql:
            raise ValueError(
                "Phase4 tools cannot accept model-supplied raw SQL."
            )

        if self.accepts_metric_formula:
            raise ValueError(
                "Phase4 tools cannot accept model-supplied metric formulas."
            )

        if not self.requires_governed_executor:
            raise ValueError(
                "Phase4 tools must use a governed executor."
            )

        return self
