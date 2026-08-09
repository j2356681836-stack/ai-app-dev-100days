from __future__ import annotations

import json
from collections.abc import Mapping
from enum import Enum
from hashlib import sha256
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from app.governance.governed_planning_envelope_v2 import (
    GovernedPlanningEnvelopeV2,
)
from app.semantic_layer.query_plan_compiler_v2 import (
    CompiledQueryPlanContractV2,
)


_FINGERPRINT_PATTERN = r"^[0-9a-f]{64}$"
_IDENTIFIER_PATTERN = r"^[A-Za-z_][A-Za-z0-9_]*$"


def _canonicalize(
    value: Any,
) -> Any:
    if isinstance(value, BaseModel):
        return _canonicalize(
            value.model_dump(
                mode="python"
            )
        )

    if isinstance(value, Mapping):
        return {
            str(key): _canonicalize(item)
            for key, item in sorted(
                value.items(),
                key=lambda pair: str(pair[0]),
            )
        }

    if isinstance(
        value,
        (
            set,
            frozenset,
        ),
    ):
        items = [
            _canonicalize(item)
            for item in value
        ]

        return sorted(
            items,
            key=lambda item: json.dumps(
                item,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
        )

    if isinstance(
        value,
        (
            list,
            tuple,
        ),
    ):
        return [
            _canonicalize(item)
            for item in value
        ]

    if isinstance(value, Enum):
        return value.value

    return value


def _sha256_payload(
    payload: Any,
) -> str:
    encoded = json.dumps(
        _canonicalize(
            payload
        ),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode(
        "utf-8"
    )

    return sha256(
        encoded
    ).hexdigest()


def _sha256_text(
    text: str,
) -> str:
    return sha256(
        text.encode(
            "utf-8"
        )
    ).hexdigest()


class RepairedSqlCandidateV2(BaseModel):
    """
    Immutable untrusted SQL repair candidate.

    This object is NOT executable evidence.

    It proves only:
    - which immutable Envelope the repair belongs to;
    - which original deterministic Compiled Contract it derives from;
    - the repaired SQL text has not changed after candidate creation.

    It does NOT prove that the repaired SQL is safe. The candidate must
    pass the PostgreSQL AST governance gate before any execution path
    may consume it.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    contract_version: str = (
        "repaired_sql_candidate_v2_0"
    )

    request_id: str
    plan_name: str = Field(
        pattern=_IDENTIFIER_PATTERN
    )
    metric_name: str = Field(
        pattern=_IDENTIFIER_PATTERN
    )
    result_grain: str = Field(
        pattern=_IDENTIFIER_PATTERN
    )
    target_schema: str = Field(
        pattern=_IDENTIFIER_PATTERN
    )

    envelope_fingerprint: str = Field(
        pattern=_FINGERPRINT_PATTERN
    )
    source_compiled_contract_fingerprint: str = Field(
        pattern=_FINGERPRINT_PATTERN
    )
    source_sql_fingerprint: str = Field(
        pattern=_FINGERPRINT_PATTERN
    )

    repaired_sql: str
    repaired_sql_fingerprint: str = Field(
        pattern=_FINGERPRINT_PATTERN
    )

    parameter_names: tuple[str, ...]
    visible_output_fields: tuple[str, ...]
    hidden_output_fields: tuple[str, ...]
    compiled_stage_ids: tuple[str, ...]

    repair_attempt: int = Field(
        ge=1,
        le=5,
    )

    candidate_fingerprint: str = Field(
        pattern=_FINGERPRINT_PATTERN
    )

    @model_validator(mode="after")
    def validate_contract(
        self,
    ) -> "RepairedSqlCandidateV2":
        if not self.request_id:
            raise ValueError(
                "request_id cannot be empty."
            )

        if not self.repaired_sql.strip():
            raise ValueError(
                "repaired_sql cannot be empty."
            )

        actual_sql_fingerprint = _sha256_text(
            self.repaired_sql
        )

        if (
            self.repaired_sql_fingerprint
            != actual_sql_fingerprint
        ):
            raise ValueError(
                "repaired_sql_fingerprint mismatch."
            )

        expected_candidate_fingerprint = (
            _candidate_fingerprint(
                request_id=self.request_id,
                plan_name=self.plan_name,
                metric_name=self.metric_name,
                result_grain=self.result_grain,
                target_schema=self.target_schema,
                envelope_fingerprint=(
                    self.envelope_fingerprint
                ),
                source_compiled_contract_fingerprint=(
                    self.source_compiled_contract_fingerprint
                ),
                source_sql_fingerprint=(
                    self.source_sql_fingerprint
                ),
                repaired_sql_fingerprint=(
                    self.repaired_sql_fingerprint
                ),
                parameter_names=self.parameter_names,
                visible_output_fields=(
                    self.visible_output_fields
                ),
                hidden_output_fields=(
                    self.hidden_output_fields
                ),
                compiled_stage_ids=(
                    self.compiled_stage_ids
                ),
                repair_attempt=self.repair_attempt,
            )
        )

        if (
            self.candidate_fingerprint
            != expected_candidate_fingerprint
        ):
            raise ValueError(
                "candidate_fingerprint mismatch."
            )

        return self


def _candidate_fingerprint(
    *,
    request_id: str,
    plan_name: str,
    metric_name: str,
    result_grain: str,
    target_schema: str,
    envelope_fingerprint: str,
    source_compiled_contract_fingerprint: str,
    source_sql_fingerprint: str,
    repaired_sql_fingerprint: str,
    parameter_names: tuple[str, ...],
    visible_output_fields: tuple[str, ...],
    hidden_output_fields: tuple[str, ...],
    compiled_stage_ids: tuple[str, ...],
    repair_attempt: int,
) -> str:
    return _sha256_payload(
        {
            "contract_version": (
                "repaired_sql_candidate_v2_0"
            ),
            "request_id": request_id,
            "plan_name": plan_name,
            "metric_name": metric_name,
            "result_grain": result_grain,
            "target_schema": target_schema,
            "envelope_fingerprint": (
                envelope_fingerprint
            ),
            "source_compiled_contract_fingerprint": (
                source_compiled_contract_fingerprint
            ),
            "source_sql_fingerprint": (
                source_sql_fingerprint
            ),
            "repaired_sql_fingerprint": (
                repaired_sql_fingerprint
            ),
            "parameter_names": parameter_names,
            "visible_output_fields": (
                visible_output_fields
            ),
            "hidden_output_fields": (
                hidden_output_fields
            ),
            "compiled_stage_ids": (
                compiled_stage_ids
            ),
            "repair_attempt": repair_attempt,
        }
    )


def _assert_source_linkage(
    *,
    envelope: GovernedPlanningEnvelopeV2,
    compiled: CompiledQueryPlanContractV2,
) -> None:
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
        field: {
            "envelope": expected,
            "compiled": actual,
        }
        for field, (
            expected,
            actual,
        ) in comparisons.items()
        if expected != actual
    }

    if mismatches:
        raise ValueError(
            "Original compiled contract does not belong to the "
            "provided governed envelope. "
            f"mismatches={mismatches}"
        )


def build_repaired_sql_candidate_v2(
    *,
    envelope: GovernedPlanningEnvelopeV2,
    source_compiled: CompiledQueryPlanContractV2,
    repaired_sql: str,
    repair_attempt: int,
) -> RepairedSqlCandidateV2:
    """
    Bind raw Repair output to the original immutable governance chain.

    Callers are deliberately NOT allowed to provide their own:
    - parameter contract;
    - output contract;
    - Query Plan / stage contract;
    - resource contract;
    - Scope contract.

    Those identities are inherited from the original deterministic
    compiled contract and the governed envelope.
    """
    if not isinstance(
        envelope,
        GovernedPlanningEnvelopeV2,
    ):
        raise TypeError(
            "envelope must be GovernedPlanningEnvelopeV2."
        )

    if not isinstance(
        source_compiled,
        CompiledQueryPlanContractV2,
    ):
        raise TypeError(
            "source_compiled must be CompiledQueryPlanContractV2."
        )

    if not isinstance(
        repaired_sql,
        str,
    ):
        raise TypeError(
            "repaired_sql must be a string."
        )

    _assert_source_linkage(
        envelope=envelope,
        compiled=source_compiled,
    )

    repaired_sql_fingerprint = (
        _sha256_text(
            repaired_sql
        )
    )

    candidate_fingerprint = (
        _candidate_fingerprint(
            request_id=source_compiled.request_id,
            plan_name=source_compiled.plan_name,
            metric_name=source_compiled.metric_name,
            result_grain=source_compiled.result_grain,
            target_schema=source_compiled.target_schema,
            envelope_fingerprint=(
                source_compiled.envelope_fingerprint
            ),
            source_compiled_contract_fingerprint=(
                source_compiled.contract_fingerprint
            ),
            source_sql_fingerprint=(
                source_compiled.sql_fingerprint
            ),
            repaired_sql_fingerprint=(
                repaired_sql_fingerprint
            ),
            parameter_names=(
                source_compiled.parameter_names
            ),
            visible_output_fields=(
                source_compiled.visible_output_fields
            ),
            hidden_output_fields=(
                source_compiled.hidden_output_fields
            ),
            compiled_stage_ids=(
                source_compiled.compiled_stage_ids
            ),
            repair_attempt=repair_attempt,
        )
    )

    return RepairedSqlCandidateV2(
        request_id=source_compiled.request_id,
        plan_name=source_compiled.plan_name,
        metric_name=source_compiled.metric_name,
        result_grain=source_compiled.result_grain,
        target_schema=source_compiled.target_schema,
        envelope_fingerprint=(
            source_compiled.envelope_fingerprint
        ),
        source_compiled_contract_fingerprint=(
            source_compiled.contract_fingerprint
        ),
        source_sql_fingerprint=(
            source_compiled.sql_fingerprint
        ),
        repaired_sql=repaired_sql,
        repaired_sql_fingerprint=(
            repaired_sql_fingerprint
        ),
        parameter_names=(
            source_compiled.parameter_names
        ),
        visible_output_fields=(
            source_compiled.visible_output_fields
        ),
        hidden_output_fields=(
            source_compiled.hidden_output_fields
        ),
        compiled_stage_ids=(
            source_compiled.compiled_stage_ids
        ),
        repair_attempt=repair_attempt,
        candidate_fingerprint=(
            candidate_fingerprint
        ),
    )
