from __future__ import annotations

from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, model_validator

from app.agents.evidence_pack_v2 import (
    EvidenceRecordV2,
    EvidenceTypeV2,
    GovernedEvidenceProvenanceV2,
    ProtectedResultV2,
)
from app.agents.investigation_contracts_v2 import (
    AnalysisScopeV2,
    EvidenceReferenceV2,
    ToolContractV2,
)
from app.governance.compiled_sql_ast_enforcer_v2 import (
    CompiledSqlAstStatusV2,
    enforce_compiled_sql_ast_v2,
)
from app.governance.governed_finalization import (
    FinalizationOutcome,
    GovernedFinalizationResult,
)
from app.governance.governed_planning_envelope_v2 import (
    GovernedPlanningEnvelopeV2,
)
from app.semantic_layer.query_plan_compiler_v2 import (
    CompiledQueryPlanContractV2,
)
from app.semantic_layer.time_comparison_contract_v2 import (
    TimeWindowReferenceV2,
)


class EvidenceBuildStatusV2(str, Enum):
    """
    Governed Query Evidence Builder 的确定性结果。
    """

    BUILT = "built"
    INVALID_INPUT = "invalid_input"
    TRUST_LINKAGE_MISMATCH = "trust_linkage_mismatch"
    FINALIZATION_NOT_RELEASABLE = "finalization_not_releasable"
    AST_NOT_ENFORCED = "ast_not_enforced"
    TIME_WINDOW_MISMATCH = "time_window_mismatch"
    RESULT_SHAPE_MISMATCH = "result_shape_mismatch"
    TOOL_CONTRACT_MISMATCH = "tool_contract_mismatch"


class EvidenceBuildDecisionV2(BaseModel):
    """
    Evidence Builder 的 fail-closed 决策。

    success=True 时才允许把 record 放进 Evidence Pack。
    失败时不会产生半成品 EvidenceRecordV2。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    success: bool
    status: EvidenceBuildStatusV2
    record: EvidenceRecordV2 | None = None
    detail: str | None = None
    retryable: bool = False

    @model_validator(mode="after")
    def validate_decision(
        self,
    ) -> "EvidenceBuildDecisionV2":
        if self.retryable:
            raise ValueError(
                "Evidence Builder 是确定性校验，不允许自动 retry。"
            )

        if self.success:
            if self.status != EvidenceBuildStatusV2.BUILT:
                raise ValueError(
                    "成功 Build 必须使用 BUILT 状态。"
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

        if self.status == EvidenceBuildStatusV2.BUILT:
            raise ValueError(
                "失败 Build 不能使用 BUILT 状态。"
            )
        if self.record is not None:
            raise ValueError(
                "失败 Build 不能释放 Evidence Record。"
            )
        if not self.detail:
            raise ValueError(
                "失败 Build 必须说明 detail。"
            )

        return self


def _failed(
    *,
    status: EvidenceBuildStatusV2,
    detail: str,
) -> EvidenceBuildDecisionV2:
    return EvidenceBuildDecisionV2(
        success=False,
        status=status,
        record=None,
        detail=detail,
        retryable=False,
    )


def _as_date(
    value,
) -> date | None:
    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    return None


def _compiled_analysis_window(
    compiled: CompiledQueryPlanContractV2,
) -> TimeWindowReferenceV2 | None:
    """
    从可信 Compiled Contract 的参数映射中恢复实际分析时间窗。

    Evidence Pack 只保存最终时间窗，不复制整包 SQL parameters。
    """

    parameters = compiled.parameter_mapping()

    start_date = _as_date(
        parameters.get("analysis_start_date")
    )
    end_date = _as_date(
        parameters.get("analysis_end_date")
    )

    if start_date is None or end_date is None:
        return None

    return TimeWindowReferenceV2(
        start_date=start_date,
        end_date=end_date,
    )


def _allowed_analysis_windows(
    scope: AnalysisScopeV2,
) -> frozenset[TimeWindowReferenceV2]:
    windows = {
        scope.analysis_window,
    }

    if scope.comparison is not None:
        windows.add(
            scope.comparison.reference_window
        )

    return frozenset(windows)


def _validate_envelope_compiled_linkage(
    *,
    envelope: GovernedPlanningEnvelopeV2,
    compiled: CompiledQueryPlanContractV2,
) -> str | None:
    comparisons = {
        "request_id": (
            envelope.request_id,
            compiled.request_id,
        ),
        "plan_name": (
            envelope.plan_name,
            compiled.plan_name,
        ),
        "metric_name": (
            envelope.metric_name,
            compiled.metric_name,
        ),
        "result_grain": (
            envelope.result_grain,
            compiled.result_grain,
        ),
        "target_schema": (
            envelope.target_schema,
            compiled.target_schema,
        ),
        "envelope_fingerprint": (
            envelope.envelope_fingerprint,
            compiled.envelope_fingerprint,
        ),
        "query_plan_fingerprint": (
            envelope.query_plan_fingerprint,
            compiled.query_plan_fingerprint,
        ),
        "time_binding_fingerprint": (
            envelope.time_binding.contract_fingerprint,
            compiled.time_binding_fingerprint,
        ),
        "scope_binding_fingerprint": (
            envelope.scope_binding.contract_fingerprint,
            compiled.scope_binding_fingerprint,
        ),
    }

    mismatches = {
        name: {
            "envelope": expected,
            "compiled": actual,
        }
        for name, (expected, actual) in comparisons.items()
        if expected != actual
    }

    if mismatches:
        return (
            "Governed Envelope 与 Compiled Contract linkage 不一致："
            f"{mismatches}"
        )

    return None


def build_governed_query_evidence_record_v2(
    *,
    analysis_scope: AnalysisScopeV2,
    evidence_reference: EvidenceReferenceV2,
    tool_contract: ToolContractV2,
    envelope: GovernedPlanningEnvelopeV2,
    compiled: CompiledQueryPlanContractV2,
    finalization: GovernedFinalizationResult,
    parent_evidence_ids: tuple[str, ...] = (),
) -> EvidenceBuildDecisionV2:
    """
    将真实 Governed Query 的“可释放执行事实”转换为 EvidenceRecordV2。

    Trust Boundary：
    - 不接受 raw SQL / raw SQL parameters；
    - SQL 与 parameter mapping 只能来自 Compiled Contract；
    - 不接受 raw execution rows；
    - rows 只能来自 GovernedFinalizationResult；
    - Finalization 必须成功且 Audit 已持久化；
    - 再次执行 deterministic AST Gate，确认 Envelope / Compiled
      Contract 仍然匹配；
    - Evidence 的时间窗必须来自 Compiled Contract 的实际绑定参数；
    - Tool source 必须与静态 Tool Contract 一致。

    这个 Builder 不负责数据库执行，也不负责产生新业务结论。
    """

    if not isinstance(analysis_scope, AnalysisScopeV2):
        return _failed(
            status=EvidenceBuildStatusV2.INVALID_INPUT,
            detail="analysis_scope 必须是 AnalysisScopeV2。",
        )

    if not isinstance(evidence_reference, EvidenceReferenceV2):
        return _failed(
            status=EvidenceBuildStatusV2.INVALID_INPUT,
            detail="evidence_reference 必须是 EvidenceReferenceV2。",
        )

    if not isinstance(tool_contract, ToolContractV2):
        return _failed(
            status=EvidenceBuildStatusV2.INVALID_INPUT,
            detail="tool_contract 必须是 ToolContractV2。",
        )

    if not isinstance(envelope, GovernedPlanningEnvelopeV2):
        return _failed(
            status=EvidenceBuildStatusV2.INVALID_INPUT,
            detail="envelope 必须是 GovernedPlanningEnvelopeV2。",
        )

    if not isinstance(compiled, CompiledQueryPlanContractV2):
        return _failed(
            status=EvidenceBuildStatusV2.INVALID_INPUT,
            detail="compiled 必须是 CompiledQueryPlanContractV2。",
        )

    if not isinstance(finalization, GovernedFinalizationResult):
        return _failed(
            status=EvidenceBuildStatusV2.INVALID_INPUT,
            detail="finalization 必须是 GovernedFinalizationResult。",
        )

    if tool_contract.executor_binding != "execute_governed_query_v2":
        return _failed(
            status=EvidenceBuildStatusV2.TOOL_CONTRACT_MISMATCH,
            detail=(
                "Day87 第一版 Governed Query Evidence Builder "
                "只接受 execute_governed_query_v2 Tool Binding。"
            ),
        )

    expected_source = (
        f"tool:{tool_contract.identity.name}"
        f"@{tool_contract.identity.version}"
    )

    if evidence_reference.source != expected_source:
        return _failed(
            status=EvidenceBuildStatusV2.TOOL_CONTRACT_MISMATCH,
            detail=(
                "EvidenceReference.source 与 Tool Contract identity "
                "不一致。"
            ),
        )

    linkage_error = _validate_envelope_compiled_linkage(
        envelope=envelope,
        compiled=compiled,
    )

    if linkage_error is not None:
        return _failed(
            status=EvidenceBuildStatusV2.TRUST_LINKAGE_MISMATCH,
            detail=linkage_error,
        )

    if analysis_scope.metric_name != envelope.metric_name:
        return _failed(
            status=EvidenceBuildStatusV2.TRUST_LINKAGE_MISMATCH,
            detail=(
                "Analysis Scope metric 与 Governed Envelope metric "
                "不一致。"
            ),
        )

    if (
        analysis_scope.result_grain is not None
        and analysis_scope.result_grain
        != envelope.result_grain
    ):
        return _failed(
            status=EvidenceBuildStatusV2.TRUST_LINKAGE_MISMATCH,
            detail=(
                "Analysis Scope result_grain 与 Governed Query "
                "result_grain 不一致。"
            ),
        )

    if (
        not finalization.success
        or finalization.outcome
        != FinalizationOutcome.SUCCEEDED
        or not finalization.audit_persisted
        or finalization.row_count <= 0
        or not finalization.rows
    ):
        return _failed(
            status=(
                EvidenceBuildStatusV2
                .FINALIZATION_NOT_RELEASABLE
            ),
            detail=(
                "只有成功、已持久化 Audit、且实际释放 rows 的 "
                "GovernedFinalizationResult 才能生成 Evidence Record。"
            ),
        )

    audit_fields = (
        finalization.audit_event_id,
        finalization.audit_event_fingerprint,
        finalization.audit_sequence_number,
        finalization.audit_record_hash,
    )

    if any(value is None for value in audit_fields):
        return _failed(
            status=(
                EvidenceBuildStatusV2
                .FINALIZATION_NOT_RELEASABLE
            ),
            detail=(
                "Governed Finalization 缺少完整 Audit identifiers。"
            ),
        )

    ast_decision = enforce_compiled_sql_ast_v2(
        envelope=envelope,
        compiled=compiled,
    )

    if (
        not ast_decision.success
        or ast_decision.status
        != CompiledSqlAstStatusV2.ENFORCED
        or ast_decision.contract is None
    ):
        return _failed(
            status=EvidenceBuildStatusV2.AST_NOT_ENFORCED,
            detail=(
                "Evidence Builder 重新验证时，Compiled SQL 未通过 "
                "PostgreSQL AST Gate。"
            ),
        )

    ast_contract = ast_decision.contract

    if (
        ast_contract.envelope_fingerprint
        != envelope.envelope_fingerprint
        or ast_contract.compiled_contract_fingerprint
        != compiled.contract_fingerprint
        or ast_contract.sql_fingerprint
        != compiled.sql_fingerprint
    ):
        return _failed(
            status=EvidenceBuildStatusV2.AST_NOT_ENFORCED,
            detail=(
                "AST Enforcement Evidence 与当前 Envelope / "
                "Compiled Contract 不一致。"
            ),
        )

    actual_window = _compiled_analysis_window(
        compiled
    )

    if actual_window is None:
        return _failed(
            status=EvidenceBuildStatusV2.TIME_WINDOW_MISMATCH,
            detail=(
                "Compiled Contract 缺少可验证的 "
                "analysis_start_date / analysis_end_date。"
            ),
        )

    if actual_window not in _allowed_analysis_windows(
        analysis_scope
    ):
        return _failed(
            status=EvidenceBuildStatusV2.TIME_WINDOW_MISMATCH,
            detail=(
                "真实 Compiled Time Window 不属于 Insight 当前 / "
                "参考时间窗。"
            ),
        )

    expected_fields = tuple(
        compiled.visible_output_fields
    )
    expected_field_set = set(expected_fields)

    if not expected_fields:
        return _failed(
            status=EvidenceBuildStatusV2.RESULT_SHAPE_MISMATCH,
            detail="Compiled Contract 缺少 visible_output_fields。",
        )

    for index, row in enumerate(finalization.rows):
        actual_fields = set(row)

        if actual_fields != expected_field_set:
            return _failed(
                status=(
                    EvidenceBuildStatusV2
                    .RESULT_SHAPE_MISMATCH
                ),
                detail=(
                    "Finalization released row 与 Compiled visible "
                    "output contract 不一致。"
                    f" row_index={index}; "
                    f"missing={sorted(expected_field_set - actual_fields)}; "
                    f"extra={sorted(actual_fields - expected_field_set)}"
                ),
            )

    provenance = GovernedEvidenceProvenanceV2(
        dataset_name=envelope.dataset_name,
        target_schema=envelope.target_schema,
        metric_name=envelope.metric_name,
        result_grain=envelope.result_grain,
        analysis_window=actual_window,
        scope_summary=analysis_scope.scope_summary,
        plan_name=envelope.plan_name,
        query_plan_fingerprint=(
            envelope.query_plan_fingerprint
        ),
        envelope_fingerprint=(
            envelope.envelope_fingerprint
        ),
        compiled_contract_fingerprint=(
            compiled.contract_fingerprint
        ),
        sql_fingerprint=compiled.sql_fingerprint,
        time_binding_fingerprint=(
            compiled.time_binding_fingerprint
        ),
        scope_binding_fingerprint=(
            compiled.scope_binding_fingerprint
        ),
        tool_name=tool_contract.identity.name,
        tool_version=tool_contract.identity.version,
        audit_event_id=finalization.audit_event_id,
        audit_event_fingerprint=(
            finalization.audit_event_fingerprint
        ),
        audit_record_hash=(
            finalization.audit_record_hash
        ),
        finalization_contract_version=(
            finalization.contract_version
        ),
    )

    protected_result = ProtectedResultV2(
        field_names=expected_fields,
        rows=finalization.rows,
        row_count=finalization.row_count,
    )

    record = EvidenceRecordV2(
        reference=evidence_reference,
        evidence_type=(
            EvidenceTypeV2.GOVERNED_QUERY_RESULT
        ),
        parent_evidence_ids=parent_evidence_ids,
        provenance=provenance,
        protected_result=protected_result,
    )

    return EvidenceBuildDecisionV2(
        success=True,
        status=EvidenceBuildStatusV2.BUILT,
        record=record,
        detail=None,
        retryable=False,
    )
