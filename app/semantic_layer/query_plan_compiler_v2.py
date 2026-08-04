from __future__ import annotations

import json
import re
from collections.abc import Mapping
from datetime import date, datetime
from enum import Enum
from hashlib import sha256
from textwrap import indent
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.governance.governed_planning_envelope_v2 import (
    GovernedPlanningEnvelopeV2,
    query_plan_fingerprint_v2,
)
from app.semantic_layer.query_plan_v2_models import (
    QueryJoin,
    QueryLogic,
    QueryPlanV2,
    QueryStage,
    StageJoin,
    StagedQueryLogic,
)


COMPILER_VERSION_V2 = "query_plan_compiler_v2_0"

_IDENTIFIER_PATTERN = r"^[A-Za-z_][A-Za-z0-9_]*$"
_FINGERPRINT_PATTERN = r"^[0-9a-f]{64}$"

_ALIAS_COLUMN_FINDER = re.compile(
    r"\b(?P<alias>[A-Za-z_][A-Za-z0-9_]*)\."
    r"(?P<column>[A-Za-z_][A-Za-z0-9_]*)\b"
)
_RESOURCE_COLUMN_FINDER = re.compile(
    r"\b(?P<table>[a-z_][a-z0-9_]*)\."
    r"(?P<column>[a-z_][a-z0-9_]*)\b"
)
_PARAMETER_FINDER = re.compile(
    r"(?<!:):(?P<name>[A-Za-z_][A-Za-z0-9_]*)"
)


_SCOPE_PREDICATE_PATTERN = re.compile(
    (
        r"^(?P<anchor_alias>[A-Za-z_][A-Za-z0-9_]*)\."
        r"(?P<anchor_column>[A-Za-z_][A-Za-z0-9_]*) "
        r"IN \(SELECT scope_lookup\."
        r"(?P<lookup_id_column>[A-Za-z_][A-Za-z0-9_]*) "
        r"FROM (?P<schema>[A-Za-z_][A-Za-z0-9_]*)\."
        r"(?P<lookup_table>[A-Za-z_][A-Za-z0-9_]*) "
        r"AS scope_lookup "
        r"WHERE scope_lookup\."
        r"(?P<lookup_code_column>[A-Za-z_][A-Za-z0-9_]*) "
        r"IN \((?P<placeholder_list>[^()]*)\)\)$"
    )
)

_FORBIDDEN_FRAGMENT_SEQUENCES = (
    ";",
    "--",
    "/*",
    "*/",
    "\x00",
)

_FORBIDDEN_FRAGMENT_KEYWORDS = (
    "select",
    "from",
    "join",
    "with",
    "union",
    "intersect",
    "except",
    "insert",
    "update",
    "delete",
    "drop",
    "alter",
    "truncate",
    "create",
    "grant",
    "revoke",
    "copy",
    "call",
    "do",
    "merge",
    "execute",
    "prepare",
    "deallocate",
    "set",
    "reset",
    "show",
    "vacuum",
    "analyze",
    "explain",
    "lock",
)

_FORBIDDEN_FRAGMENT_KEYWORD_RE = re.compile(
    r"\b(?:"
    + "|".join(
        re.escape(keyword)
        for keyword in _FORBIDDEN_FRAGMENT_KEYWORDS
    )
    + r")\b",
    re.IGNORECASE,
)


class QueryPlanCompileStatusV2(str, Enum):
    COMPILED = "compiled"
    INVALID_ENVELOPE = "invalid_envelope"
    UNSAFE_PLAN_FRAGMENT = "unsafe_plan_fragment"
    RESOURCE_REFERENCE_MISMATCH = (
        "resource_reference_mismatch"
    )
    PARAMETER_COLLISION = "parameter_collision"
    PLACEHOLDER_MISMATCH = "placeholder_mismatch"
    COMPILATION_FAILED = "compilation_failed"


class CompiledParameterV2(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    name: str = Field(
        pattern=_IDENTIFIER_PATTERN
    )
    value: (
        date
        | datetime
        | str
        | int
        | float
        | bool
        | None
    )


class CompiledQueryPlanContractV2(BaseModel):
    """
    Immutable output of deterministic Query Plan V2 compilation.

    This contract is ready for later SQL AST enforcement. It is not,
    by itself, proof that the SQL has been executed or accepted by
    PostgreSQL.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    compiler_version: str = COMPILER_VERSION_V2

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
    query_plan_fingerprint: str = Field(
        pattern=_FINGERPRINT_PATTERN
    )
    time_binding_fingerprint: str = Field(
        pattern=_FINGERPRINT_PATTERN
    )
    scope_binding_fingerprint: str = Field(
        pattern=_FINGERPRINT_PATTERN
    )

    sql: str
    parameters: tuple[CompiledParameterV2, ...]
    parameter_names: tuple[str, ...]

    visible_output_fields: tuple[str, ...]
    hidden_output_fields: tuple[str, ...]
    compiled_stage_ids: tuple[str, ...] = ()

    sql_fingerprint: str = Field(
        pattern=_FINGERPRINT_PATTERN
    )
    contract_fingerprint: str = Field(
        pattern=_FINGERPRINT_PATTERN
    )

    @model_validator(mode="after")
    def validate_contract(
        self,
    ) -> "CompiledQueryPlanContractV2":
        if not self.request_id:
            raise ValueError(
                "request_id cannot be empty."
            )

        if not self.sql.strip():
            raise ValueError(
                "Compiled SQL cannot be empty."
            )

        normalized_sql = self.sql.lstrip().upper()

        if not (
            normalized_sql.startswith("SELECT")
            or normalized_sql.startswith("WITH")
        ):
            raise ValueError(
                "Compiled SQL must start with SELECT or WITH."
            )

        if any(
            sequence in self.sql
            for sequence in _FORBIDDEN_FRAGMENT_SEQUENCES
        ):
            raise ValueError(
                "Compiled SQL cannot contain statement separators "
                "or SQL comments."
            )

        names = tuple(
            parameter.name
            for parameter in self.parameters
        )

        if len(names) != len(set(names)):
            raise ValueError(
                "Compiled parameter names must be unique."
            )

        if names != self.parameter_names:
            raise ValueError(
                "parameter_names must match parameters in order."
            )

        placeholder_names = tuple(
            sorted(
                set(
                    _PARAMETER_FINDER.findall(
                        self.sql
                    )
                )
            )
        )

        if placeholder_names != tuple(
            sorted(
                self.parameter_names
            )
        ):
            raise ValueError(
                "SQL placeholders must exactly match compiled "
                "parameter names."
            )

        if not self.visible_output_fields:
            raise ValueError(
                "At least one visible output field is required."
            )

        if len(self.visible_output_fields) != len(
            set(self.visible_output_fields)
        ):
            raise ValueError(
                "Visible output fields must be unique."
            )

        if len(self.hidden_output_fields) != len(
            set(self.hidden_output_fields)
        ):
            raise ValueError(
                "Hidden output fields must be unique."
            )

        overlap = (
            set(self.visible_output_fields)
            & set(self.hidden_output_fields)
        )

        if overlap:
            raise ValueError(
                "Visible and hidden output fields cannot overlap."
            )

        expected_sql_fingerprint = _sha256_text(
            self.sql
        )

        if self.sql_fingerprint != expected_sql_fingerprint:
            raise ValueError(
                "sql_fingerprint mismatch."
            )

        expected_contract_fingerprint = (
            _compiled_contract_fingerprint(
                request_id=self.request_id,
                plan_name=self.plan_name,
                metric_name=self.metric_name,
                result_grain=self.result_grain,
                target_schema=self.target_schema,
                envelope_fingerprint=(
                    self.envelope_fingerprint
                ),
                query_plan_fingerprint=(
                    self.query_plan_fingerprint
                ),
                time_binding_fingerprint=(
                    self.time_binding_fingerprint
                ),
                scope_binding_fingerprint=(
                    self.scope_binding_fingerprint
                ),
                sql_fingerprint=self.sql_fingerprint,
                parameters=self.parameters,
                visible_output_fields=(
                    self.visible_output_fields
                ),
                hidden_output_fields=(
                    self.hidden_output_fields
                ),
                compiled_stage_ids=(
                    self.compiled_stage_ids
                ),
            )
        )

        if (
            self.contract_fingerprint
            != expected_contract_fingerprint
        ):
            raise ValueError(
                "contract_fingerprint mismatch."
            )

        return self

    def parameter_mapping(
        self,
    ) -> dict[str, Any]:
        return {
            parameter.name: parameter.value
            for parameter in self.parameters
        }


class QueryPlanCompileDecisionV2(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    success: bool
    status: QueryPlanCompileStatusV2

    plan_name: str
    metric_name: str

    contract: CompiledQueryPlanContractV2 | None = None
    detail: str | None = None
    retryable: bool = False

    @model_validator(mode="after")
    def validate_decision(
        self,
    ) -> "QueryPlanCompileDecisionV2":
        if self.retryable:
            raise ValueError(
                "Query Plan compilation is deterministic and "
                "must not be automatically retried."
            )

        if self.success:
            if (
                self.status
                != QueryPlanCompileStatusV2.COMPILED
            ):
                raise ValueError(
                    "Successful compilation must use COMPILED."
                )

            if self.contract is None:
                raise ValueError(
                    "Successful compilation requires a contract."
                )

            if self.detail is not None:
                raise ValueError(
                    "Successful compilation must not expose detail."
                )

            return self

        if self.status == QueryPlanCompileStatusV2.COMPILED:
            raise ValueError(
                "Failed compilation cannot use COMPILED."
            )

        if self.contract is not None:
            raise ValueError(
                "Failed compilation must not expose a contract."
            )

        if not self.detail:
            raise ValueError(
                "Failed compilation requires detail."
            )

        return self


class _UnsafeFragmentError(ValueError):
    pass


class _ResourceReferenceError(ValueError):
    pass


class _ParameterCollisionError(ValueError):
    pass


class _PlaceholderMismatchError(ValueError):
    pass


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

    if isinstance(
        value,
        (
            date,
            datetime,
        ),
    ):
        return value.isoformat()

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


def _compiled_contract_fingerprint(
    *,
    request_id: str,
    plan_name: str,
    metric_name: str,
    result_grain: str,
    target_schema: str,
    envelope_fingerprint: str,
    query_plan_fingerprint: str,
    time_binding_fingerprint: str,
    scope_binding_fingerprint: str,
    sql_fingerprint: str,
    parameters: tuple[CompiledParameterV2, ...],
    visible_output_fields: tuple[str, ...],
    hidden_output_fields: tuple[str, ...],
    compiled_stage_ids: tuple[str, ...],
) -> str:
    return _sha256_payload(
        {
            "compiler_version": COMPILER_VERSION_V2,
            "request_id": request_id,
            "plan_name": plan_name,
            "metric_name": metric_name,
            "result_grain": result_grain,
            "target_schema": target_schema,
            "envelope_fingerprint": envelope_fingerprint,
            "query_plan_fingerprint": (
                query_plan_fingerprint
            ),
            "time_binding_fingerprint": (
                time_binding_fingerprint
            ),
            "scope_binding_fingerprint": (
                scope_binding_fingerprint
            ),
            "sql_fingerprint": sql_fingerprint,
            "parameters": parameters,
            "visible_output_fields": (
                visible_output_fields
            ),
            "hidden_output_fields": (
                hidden_output_fields
            ),
            "compiled_stage_ids": compiled_stage_ids,
        }
    )


def _failed(
    envelope: GovernedPlanningEnvelopeV2,
    *,
    status: QueryPlanCompileStatusV2,
    detail: str,
) -> QueryPlanCompileDecisionV2:
    return QueryPlanCompileDecisionV2(
        success=False,
        status=status,
        plan_name=envelope.plan_name,
        metric_name=envelope.metric_name,
        contract=None,
        detail=detail,
        retryable=False,
    )


def _assert_safe_fragment(
    fragment: str,
    *,
    location: str,
    allowed_parameters: frozenset[str],
) -> None:
    text = str(
        fragment
    ).strip()

    if not text:
        raise _UnsafeFragmentError(
            f"Empty SQL fragment: {location}"
        )

    for sequence in _FORBIDDEN_FRAGMENT_SEQUENCES:
        if sequence in text:
            raise _UnsafeFragmentError(
                "SQL fragment contains a forbidden sequence. "
                f"location={location}, sequence={sequence!r}"
            )

    keyword_match = (
        _FORBIDDEN_FRAGMENT_KEYWORD_RE.search(
            text
        )
    )

    if keyword_match:
        raise _UnsafeFragmentError(
            "SQL fragment contains a statement-level keyword. "
            f"location={location}, "
            f"keyword={keyword_match.group(0)!r}"
        )

    placeholders = frozenset(
        _PARAMETER_FINDER.findall(
            text
        )
    )
    unexpected = (
        placeholders - allowed_parameters
    )

    if unexpected:
        raise _UnsafeFragmentError(
            "SQL fragment contains undeclared parameters. "
            f"location={location}, "
            f"unexpected={sorted(unexpected)}"
        )


def _assert_resource_references(
    fragment: str,
    *,
    location: str,
    physical_aliases: Mapping[str, str],
    derived_alias_fields: Mapping[
        str,
        frozenset[str],
    ],
    required_columns: frozenset[str],
) -> None:
    for match in _ALIAS_COLUMN_FINDER.finditer(
        fragment
    ):
        alias = match.group(
            "alias"
        )
        column = match.group(
            "column"
        )

        table = physical_aliases.get(
            alias
        )

        if table is not None:
            resource_column = (
                f"{table}.{column}"
            )

            if resource_column not in required_columns:
                raise _ResourceReferenceError(
                    "Physical alias reference is not declared "
                    "in Query Plan required_columns. "
                    f"location={location}, "
                    f"reference={alias}.{column}, "
                    f"resource={resource_column}"
                )

            continue

        derived_fields = (
            derived_alias_fields.get(
                alias
            )
        )

        if derived_fields is not None:
            if column not in derived_fields:
                raise _ResourceReferenceError(
                    "Derived alias reference uses a field not "
                    "exposed by the earlier Query Stage. "
                    f"location={location}, "
                    f"reference={alias}.{column}"
                )

            continue

        raise _ResourceReferenceError(
            "SQL fragment references an unknown alias. "
            f"location={location}, "
            f"reference={alias}.{column}"
        )


def _translate_simple_base_filter(
    fragment: str,
    *,
    logic: QueryLogic,
    required_columns: frozenset[str],
) -> str:
    aliases_by_table: dict[
        str,
        list[str],
    ] = {}

    for alias, table in (
        logic.alias_to_table().items()
    ):
        aliases_by_table.setdefault(
            table,
            [],
        ).append(
            alias
        )

    def replace(
        match: re.Match[str],
    ) -> str:
        table = match.group(
            "table"
        )
        column = match.group(
            "column"
        )
        resource_column = (
            f"{table}.{column}"
        )

        if resource_column not in required_columns:
            raise _ResourceReferenceError(
                "Simple base filter references an undeclared "
                f"resource column: {resource_column}"
            )

        aliases = aliases_by_table.get(
            table,
            [],
        )

        if len(aliases) != 1:
            raise _ResourceReferenceError(
                "Simple base filter requires exactly one trusted "
                "alias for its physical table. "
                f"table={table}, aliases={aliases}"
            )

        return (
            f"{aliases[0]}.{column}"
        )

    return _RESOURCE_COLUMN_FINDER.sub(
        replace,
        fragment,
    )


def _deduplicate(
    values: list[str],
) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()

    for value in values:
        normalized = value.strip()

        if normalized not in seen:
            seen.add(
                normalized
            )
            result.append(
                normalized
            )

    return tuple(
        result
    )


def _canonical_time_predicate(
    reference: str,
) -> str:
    return (
        f"CAST({reference} AS DATE) "
        "BETWEEN :analysis_start_date "
        "AND :analysis_end_date"
    )


def _time_filters_by_stage(
    envelope: GovernedPlanningEnvelopeV2,
) -> dict[str | None, tuple[str, ...]]:
    result: dict[
        str | None,
        list[str],
    ] = {}

    for application in (
        envelope.time_binding.applications
    ):
        stage_filters = result.setdefault(
            application.stage_id,
            [],
        )

        for reference in (
            application.query_references
        ):
            stage_filters.append(
                _canonical_time_predicate(
                    reference
                )
            )

    return {
        stage_id: _deduplicate(
            filters
        )
        for stage_id, filters in result.items()
    }


def _scope_filters_by_stage(
    envelope: GovernedPlanningEnvelopeV2,
) -> dict[str | None, tuple[str, ...]]:
    result: dict[
        str | None,
        list[str],
    ] = {}

    for placement in (
        envelope.scope_binding.placements
    ):
        result.setdefault(
            placement.stage_id,
            [],
        ).append(
            placement.sql_fragment
        )

    return {
        stage_id: _deduplicate(
            filters
        )
        for stage_id, filters in result.items()
    }




def _validate_scope_contract_fragments(
    envelope: GovernedPlanningEnvelopeV2,
    *,
    allowed_parameters: frozenset[str],
) -> None:
    """
    Validate governance-generated Row Scope fragments by provenance.

    Scope predicates intentionally contain one SELECT subquery.
    They must not be checked as ordinary Query Plan fragments.
    Instead, each placement must:
    - exactly match its immutable ScopedQueryContract predicate;
    - use the fixed lookup-subquery shape produced by Row Scope Binder;
    - reference only declared schema/table/columns and trusted aliases;
    - use exactly its declared parameter names.
    """
    scoped_contract = (
        envelope.scope_binding
        .scoped_query_contract
    )

    predicate_map = {
        (
            predicate.target_id,
            predicate.dimension,
        ): predicate
        for predicate in scoped_contract.predicates
    }
    target_map = {
        target.target_id: target
        for target in scoped_contract.targets
    }

    for placement in envelope.scope_binding.placements:
        key = (
            placement.target_id,
            placement.dimension,
        )
        predicate = predicate_map.get(
            key
        )

        if predicate is None:
            raise _ResourceReferenceError(
                "Scope placement has no matching immutable "
                "ScopedQueryContract predicate. "
                f"target={placement.target_id}, "
                f"dimension={placement.dimension.value}"
            )

        if (
            placement.source_table
            != predicate.source_table
            or placement.anchor_reference
            != predicate.anchor_reference
            or placement.sql_fragment
            != predicate.sql_fragment
            or placement.parameter_names
            != predicate.parameter_names
        ):
            raise _ResourceReferenceError(
                "Scope placement does not exactly match its "
                "immutable ScopedQueryContract predicate. "
                f"target={placement.target_id}, "
                f"dimension={placement.dimension.value}"
            )

        fragment = placement.sql_fragment.strip()

        for sequence in _FORBIDDEN_FRAGMENT_SEQUENCES:
            if sequence in fragment:
                raise _UnsafeFragmentError(
                    "Governance Scope fragment contains a forbidden "
                    "sequence. "
                    f"target={placement.target_id}, "
                    f"sequence={sequence!r}"
                )

        match = _SCOPE_PREDICATE_PATTERN.fullmatch(
            fragment
        )

        if match is None:
            raise _UnsafeFragmentError(
                "Governance Scope fragment does not match the "
                "fixed lookup-subquery shape. "
                f"target={placement.target_id}, "
                f"dimension={placement.dimension.value}"
            )

        anchor_reference = (
            f"{match.group('anchor_alias')}."
            f"{match.group('anchor_column')}"
        )

        if anchor_reference != placement.anchor_reference:
            raise _ResourceReferenceError(
                "Scope anchor reference mismatch. "
                f"target={placement.target_id}"
            )

        target = target_map.get(
            placement.target_id
        )

        if target is None:
            raise _ResourceReferenceError(
                "Scope placement references an unknown ScopeTarget. "
                f"target={placement.target_id}"
            )

        alias_to_table = {
            binding.alias: binding.table_name
            for binding in target.table_aliases
        }
        anchor_table = alias_to_table.get(
            match.group(
                "anchor_alias"
            )
        )

        if anchor_table is None:
            raise _ResourceReferenceError(
                "Scope anchor alias is not declared by ScopeTarget. "
                f"target={placement.target_id}, "
                f"alias={match.group('anchor_alias')}"
            )

        anchor_resource = (
            f"{anchor_table}."
            f"{match.group('anchor_column')}"
        )

        if anchor_resource not in envelope.required_columns:
            raise _ResourceReferenceError(
                "Scope anchor column is not declared in the "
                "governed resource contract. "
                f"resource={anchor_resource}"
            )

        if match.group("schema") != envelope.target_schema:
            raise _ResourceReferenceError(
                "Scope lookup schema does not match governed "
                "target_schema. "
                f"actual={match.group('schema')}, "
                f"expected={envelope.target_schema}"
            )

        lookup_table = match.group(
            "lookup_table"
        )

        if lookup_table not in envelope.required_tables:
            raise _ResourceReferenceError(
                "Scope lookup table is not declared in the "
                "governed resource contract. "
                f"table={lookup_table}"
            )

        lookup_resources = {
            (
                f"{lookup_table}."
                f"{match.group('lookup_id_column')}"
            ),
            (
                f"{lookup_table}."
                f"{match.group('lookup_code_column')}"
            ),
        }
        missing_lookup_columns = (
            lookup_resources
            - envelope.required_columns
        )

        if missing_lookup_columns:
            raise _ResourceReferenceError(
                "Scope lookup columns are not declared in the "
                "governed resource contract. "
                f"columns={sorted(missing_lookup_columns)}"
            )

        placeholders = frozenset(
            _PARAMETER_FINDER.findall(
                match.group(
                    "placeholder_list"
                )
            )
        )
        declared_parameters = frozenset(
            placement.parameter_names
        )

        if placeholders != declared_parameters:
            raise _PlaceholderMismatchError(
                "Scope fragment placeholders do not exactly match "
                "its declared parameter names. "
                f"target={placement.target_id}, "
                f"placeholders={sorted(placeholders)}, "
                f"declared={sorted(declared_parameters)}"
            )

        undeclared_parameters = (
            declared_parameters
            - allowed_parameters
        )

        if undeclared_parameters:
            raise _PlaceholderMismatchError(
                "Scope fragment uses parameters outside the "
                "compiled parameter contract. "
                f"parameters={sorted(undeclared_parameters)}"
            )


def _contains_declared_time_filter(
    filters: tuple[str, ...],
    *,
    reference: str,
) -> bool:
    return any(
        reference in item
        and ":analysis_start_date" in item
        and ":analysis_end_date" in item
        for item in filters
    )


def _merge_stage_time_filters(
    existing_filters: tuple[str, ...],
    requested_filters: tuple[str, ...],
) -> tuple[str, ...]:
    merged = list(
        existing_filters
    )

    for requested in requested_filters:
        references = tuple(
            f"{match.group('alias')}."
            f"{match.group('column')}"
            for match in (
                _ALIAS_COLUMN_FINDER.finditer(
                    requested
                )
            )
        )

        if (
            len(references) == 1
            and _contains_declared_time_filter(
                existing_filters,
                reference=references[0],
            )
        ):
            continue

        merged.append(
            requested
        )

    return _deduplicate(
        merged
    )


def _render_select_items(
    outputs,
    hidden_fields,
) -> tuple[str, ...]:
    items = [
        f"{output.expression} AS {output.field}"
        for output in outputs
    ]

    items.extend(
        f"{field.expression} AS {field.field}"
        for field in hidden_fields
    )

    return tuple(
        items
    )


def _render_select_clause(
    items: tuple[str, ...],
) -> str:
    return (
        "SELECT\n"
        + ",\n".join(
            f"    {item}"
            for item in items
        )
    )


def _render_physical_source(
    *,
    schema: str,
    table: str,
    alias: str,
) -> str:
    return (
        f"{schema}.{table} AS {alias}"
    )


def _render_query_join(
    join: QueryJoin,
    *,
    schema: str,
) -> str:
    conditions = " AND ".join(
        (
            f"{condition.left} = "
            f"{condition.right}"
        )
        for condition in join.conditions
    )

    return (
        f"{join.join_type.upper()} JOIN "
        f"{schema}.{join.table} AS {join.alias} "
        f"ON {conditions}"
    )


def _render_stage_join(
    join: StageJoin,
) -> str:
    conditions = " AND ".join(
        (
            f"{condition.left} = "
            f"{condition.right}"
        )
        for condition in join.conditions
    )

    return (
        f"{join.join_type.upper()} JOIN "
        f"{join.stage_id} AS {join.alias} "
        f"ON {conditions}"
    )


def _render_query_body(
    *,
    select_items: tuple[str, ...],
    source_sql: str,
    joins_sql: tuple[str, ...],
    filters: tuple[str, ...],
    group_by: tuple[str, ...],
    having: tuple[str, ...],
) -> str:
    parts = [
        _render_select_clause(
            select_items
        ),
        f"FROM {source_sql}",
    ]

    parts.extend(
        joins_sql
    )

    if filters:
        parts.append(
            "WHERE\n"
            + "\n    AND ".join(
                f"    {item}"
                for item in filters
            )
        )

    if group_by:
        parts.append(
            "GROUP BY\n"
            + ",\n".join(
                f"    {item}"
                for item in group_by
            )
        )

    if having:
        parts.append(
            "HAVING\n"
            + "\n    AND ".join(
                f"    {item}"
                for item in having
            )
        )

    return "\n".join(
        parts
    )


def _validate_query_logic_fragments(
    *,
    plan: QueryPlanV2,
    logic: QueryLogic,
    base_filters: tuple[str, ...],
    allowed_parameters: frozenset[str],
) -> None:
    physical_aliases = (
        logic.alias_to_table()
    )
    derived_alias_fields: dict[
        str,
        frozenset[str],
    ] = {}

    fragments: list[
        tuple[str, str]
    ] = []

    fragments.extend(
        (
            f"query_output:{output.field}",
            output.expression,
        )
        for output in logic.outputs
    )
    fragments.extend(
        (
            f"query_hidden:{field.field}",
            field.expression,
        )
        for field in logic.hidden_control_fields
    )
    fragments.extend(
        (
            f"query_base_filter:{index}",
            item,
        )
        for index, item in enumerate(
            base_filters
        )
    )
    fragments.extend(
        (
            f"query_group_by:{index}",
            item,
        )
        for index, item in enumerate(
            logic.group_by
        )
    )

    for join_index, join in enumerate(
        logic.joins
    ):
        fragments.extend(
            (
                (
                    "query_join:"
                    f"{join_index}:"
                    f"{condition_index}:left"
                ),
                condition.left,
            )
            for condition_index, condition in enumerate(
                join.conditions
            )
        )
        fragments.extend(
            (
                (
                    "query_join:"
                    f"{join_index}:"
                    f"{condition_index}:right"
                ),
                condition.right,
            )
            for condition_index, condition in enumerate(
                join.conditions
            )
        )

    for location, fragment in fragments:
        _assert_safe_fragment(
            fragment,
            location=location,
            allowed_parameters=(
                allowed_parameters
            ),
        )
        _assert_resource_references(
            fragment,
            location=location,
            physical_aliases=physical_aliases,
            derived_alias_fields=(
                derived_alias_fields
            ),
            required_columns=(
                plan.resource_contract
                .required_columns
            ),
        )


def _compile_query_logic(
    *,
    envelope: GovernedPlanningEnvelopeV2,
    logic: QueryLogic,
    time_filters: dict[
        str | None,
        tuple[str, ...],
    ],
    scope_filters: dict[
        str | None,
        tuple[str, ...],
    ],
    allowed_parameters: frozenset[str],
) -> tuple[
    str,
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
]:
    plan = envelope.query_plan

    if any(
        stage_id is not None
        for stage_id in (
            set(time_filters)
            | set(scope_filters)
        )
    ):
        raise _ResourceReferenceError(
            "Simple QueryLogic received a staged Time or "
            "Scope placement."
        )

    translated_base_filters = tuple(
        _translate_simple_base_filter(
            item,
            logic=logic,
            required_columns=(
                plan.resource_contract
                .required_columns
            ),
        )
        for item in (
            plan.semantic_contract.base_filters
        )
    )

    existing_filters = (
        translated_base_filters
    )

    merged_time_filters = (
        _merge_stage_time_filters(
            existing_filters,
            time_filters.get(
                None,
                (),
            ),
        )
    )

    filters = _deduplicate(
        [
            *merged_time_filters,
            *scope_filters.get(
                None,
                (),
            ),
        ]
    )

    _validate_query_logic_fragments(
        plan=plan,
        logic=logic,
        base_filters=translated_base_filters,
        allowed_parameters=(
            allowed_parameters
        ),
    )

    for index, item in enumerate(
        time_filters.get(
            None,
            (),
        )
    ):
        _assert_safe_fragment(
            item,
            location=f"query_time_filter:{index}",
            allowed_parameters=(
                allowed_parameters
            ),
        )
        _assert_resource_references(
            item,
            location=f"query_time_filter:{index}",
            physical_aliases=(
                logic.alias_to_table()
            ),
            derived_alias_fields={},
            required_columns=(
                plan.resource_contract
                .required_columns
            ),
        )

    select_items = _render_select_items(
        logic.outputs,
        logic.hidden_control_fields,
    )

    source_sql = _render_physical_source(
        schema=envelope.target_schema,
        table=logic.base_source.table,
        alias=logic.base_source.alias,
    )

    joins_sql = tuple(
        _render_query_join(
            join,
            schema=envelope.target_schema,
        )
        for join in logic.joins
    )

    sql = _render_query_body(
        select_items=select_items,
        source_sql=source_sql,
        joins_sql=joins_sql,
        filters=filters,
        group_by=logic.group_by,
        having=(),
    )

    sql += (
        "\nORDER BY "
        f"{plan.default_sort.field} "
        f"{plan.default_sort.direction.upper()}"
    )

    visible_fields = tuple(
        output.field
        for output in logic.outputs
    )
    hidden_fields = tuple(
        field.field
        for field in (
            logic.hidden_control_fields
        )
    )

    return (
        sql,
        visible_fields,
        hidden_fields,
        (),
    )


def _derived_alias_fields_for_stage(
    *,
    stage: QueryStage,
    stage_outputs: Mapping[
        str,
        frozenset[str],
    ],
) -> dict[str, frozenset[str]]:
    bindings: dict[
        str,
        frozenset[str],
    ] = {}

    if stage.source.stage_id is not None:
        bindings[stage.source.alias] = (
            stage_outputs[
                stage.source.stage_id
            ]
        )

    for join in stage.joins:
        if isinstance(
            join,
            StageJoin,
        ):
            bindings[join.alias] = (
                stage_outputs[
                    join.stage_id
                ]
            )

    return bindings


def _validate_stage_fragments(
    *,
    plan: QueryPlanV2,
    stage: QueryStage,
    filters: tuple[str, ...],
    allowed_parameters: frozenset[str],
    derived_alias_fields: Mapping[
        str,
        frozenset[str],
    ],
) -> None:
    physical_aliases = (
        stage.physical_alias_to_table()
    )

    fragments: list[
        tuple[str, str]
    ] = []

    fragments.extend(
        (
            (
                f"stage:{stage.stage_id}:"
                f"output:{output.field}"
            ),
            output.expression,
        )
        for output in stage.outputs
    )
    fragments.extend(
        (
            (
                f"stage:{stage.stage_id}:"
                f"hidden:{field.field}"
            ),
            field.expression,
        )
        for field in stage.hidden_control_fields
    )
    fragments.extend(
        (
            (
                f"stage:{stage.stage_id}:"
                f"filter:{index}"
            ),
            item,
        )
        for index, item in enumerate(
            filters
        )
    )
    fragments.extend(
        (
            (
                f"stage:{stage.stage_id}:"
                f"group_by:{index}"
            ),
            item,
        )
        for index, item in enumerate(
            stage.group_by
        )
    )
    fragments.extend(
        (
            (
                f"stage:{stage.stage_id}:"
                f"having:{index}"
            ),
            item,
        )
        for index, item in enumerate(
            stage.having
        )
    )

    for join_index, join in enumerate(
        stage.joins
    ):
        fragments.extend(
            (
                (
                    f"stage:{stage.stage_id}:"
                    f"join:{join_index}:"
                    f"{condition_index}:left"
                ),
                condition.left,
            )
            for condition_index, condition in enumerate(
                join.conditions
            )
        )
        fragments.extend(
            (
                (
                    f"stage:{stage.stage_id}:"
                    f"join:{join_index}:"
                    f"{condition_index}:right"
                ),
                condition.right,
            )
            for condition_index, condition in enumerate(
                join.conditions
            )
        )

    for location, fragment in fragments:
        _assert_safe_fragment(
            fragment,
            location=location,
            allowed_parameters=(
                allowed_parameters
            ),
        )
        _assert_resource_references(
            fragment,
            location=location,
            physical_aliases=physical_aliases,
            derived_alias_fields=(
                derived_alias_fields
            ),
            required_columns=(
                plan.resource_contract
                .required_columns
            ),
        )


def _render_stage_source(
    stage: QueryStage,
    *,
    schema: str,
) -> str:
    if stage.source.table is not None:
        return _render_physical_source(
            schema=schema,
            table=stage.source.table,
            alias=stage.source.alias,
        )

    if stage.source.stage_id is None:
        raise _ResourceReferenceError(
            "StageSource is missing both table and stage_id."
        )

    return (
        f"{stage.source.stage_id} "
        f"AS {stage.source.alias}"
    )


def _compile_staged_query_logic(
    *,
    envelope: GovernedPlanningEnvelopeV2,
    logic: StagedQueryLogic,
    time_filters: dict[
        str | None,
        tuple[str, ...],
    ],
    scope_filters: dict[
        str | None,
        tuple[str, ...],
    ],
    allowed_parameters: frozenset[str],
) -> tuple[
    str,
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
]:
    plan = envelope.query_plan

    if (
        None in time_filters
        or None in scope_filters
    ):
        raise _ResourceReferenceError(
            "StagedQueryLogic received a query-level Time or "
            "Scope placement."
        )

    declared_stage_ids = {
        stage.stage_id
        for stage in logic.stages
    }
    placement_stage_ids = (
        set(time_filters)
        | set(scope_filters)
    )
    unknown_placements = (
        placement_stage_ids
        - declared_stage_ids
    )

    if unknown_placements:
        raise _ResourceReferenceError(
            "Time or Scope placement references an unknown "
            "Query Stage. "
            f"stages={sorted(unknown_placements)}"
        )

    stage_outputs: dict[
        str,
        frozenset[str],
    ] = {}
    ctes: list[str] = []

    for stage in logic.stages:
        existing_filters = tuple(
            stage.filters
        )
        merged_time_filters = (
            _merge_stage_time_filters(
                existing_filters,
                time_filters.get(
                    stage.stage_id,
                    (),
                ),
            )
        )
        filters = _deduplicate(
            [
                *merged_time_filters,
                *scope_filters.get(
                    stage.stage_id,
                    (),
                ),
            ]
        )

        derived_alias_fields = (
            _derived_alias_fields_for_stage(
                stage=stage,
                stage_outputs=stage_outputs,
            )
        )

        _validate_stage_fragments(
            plan=plan,
            stage=stage,
            # Query Plan and Time fragments use the strict generic
            # fragment policy. Governance-generated Scope predicates
            # are validated separately by contract provenance because
            # their fixed form intentionally contains SELECT / FROM.
            filters=merged_time_filters,
            allowed_parameters=(
                allowed_parameters
            ),
            derived_alias_fields=(
                derived_alias_fields
            ),
        )

        source_sql = _render_stage_source(
            stage,
            schema=envelope.target_schema,
        )

        joins_sql: list[str] = []

        for join in stage.joins:
            if isinstance(
                join,
                QueryJoin,
            ):
                joins_sql.append(
                    _render_query_join(
                        join,
                        schema=envelope.target_schema,
                    )
                )
            else:
                joins_sql.append(
                    _render_stage_join(
                        join
                    )
                )

        body = _render_query_body(
            select_items=(
                _render_select_items(
                    stage.outputs,
                    stage.hidden_control_fields,
                )
            ),
            source_sql=source_sql,
            joins_sql=tuple(
                joins_sql
            ),
            filters=filters,
            group_by=stage.group_by,
            having=stage.having,
        )

        ctes.append(
            f"{stage.stage_id} AS (\n"
            f"{indent(body, '    ')}\n"
            ")"
        )

        stage_outputs[
            stage.stage_id
        ] = frozenset(
            output.field
            for output in stage.outputs
        )

    final_stage = (
        logic.final_stage_contract()
    )
    visible_fields = tuple(
        output.field
        for output in final_stage.outputs
    )
    hidden_fields = tuple(
        field.field
        for field in (
            final_stage.hidden_control_fields
        )
    )

    outer_fields = (
        *visible_fields,
        *hidden_fields,
    )

    outer_select = ",\n".join(
        (
            f"    compiled_final.{field} "
            f"AS {field}"
        )
        for field in outer_fields
    )

    sql = (
        "WITH\n"
        + ",\n".join(
            ctes
        )
        + "\nSELECT\n"
        + outer_select
        + "\nFROM "
        + f"{logic.final_stage} AS compiled_final"
        + "\nORDER BY "
        + (
            f"compiled_final."
            f"{plan.default_sort.field} "
            f"{plan.default_sort.direction.upper()}"
        )
    )

    return (
        sql,
        visible_fields,
        hidden_fields,
        tuple(
            stage.stage_id
            for stage in logic.stages
        ),
    )


def _merge_parameters(
    envelope: GovernedPlanningEnvelopeV2,
) -> tuple[CompiledParameterV2, ...]:
    values: dict[
        str,
        Any,
    ] = {}

    def add(
        *,
        name: str,
        value: Any,
        source: str,
    ) -> None:
        if name in values:
            raise _ParameterCollisionError(
                "Duplicate compiled parameter name. "
                f"name={name}, source={source}"
            )

        values[name] = value

    for parameter in (
        envelope.time_binding.parameters
    ):
        add(
            name=parameter.name,
            value=parameter.value,
            source="time_binding",
        )

    for parameter in (
        envelope.scope_binding
        .scoped_query_contract
        .parameters
    ):
        add(
            name=parameter.name,
            value=parameter.value,
            source="scope_binding",
        )

    return tuple(
        CompiledParameterV2(
            name=name,
            value=values[name],
        )
        for name in sorted(
            values
        )
    )


def _assert_placeholder_match(
    *,
    sql: str,
    parameters: tuple[
        CompiledParameterV2,
        ...,
    ],
) -> None:
    placeholders = frozenset(
        _PARAMETER_FINDER.findall(
            sql
        )
    )
    parameter_names = frozenset(
        parameter.name
        for parameter in parameters
    )

    if placeholders != parameter_names:
        raise _PlaceholderMismatchError(
            "Compiled SQL placeholders do not exactly match "
            "compiled parameters. "
            f"missing_parameters={sorted(placeholders - parameter_names)}, "
            f"unused_parameters={sorted(parameter_names - placeholders)}"
        )


def compile_governed_query_plan_v2(
    envelope: GovernedPlanningEnvelopeV2,
) -> QueryPlanCompileDecisionV2:
    """
    Deterministically compile one governed Query Plan V2.

    Guarantees:
    - accepts only an immutable GovernedPlanningEnvelopeV2;
    - physical tables are schema-qualified;
    - Time and Row Scope values remain named parameters;
    - Query Plan fragments cannot introduce statements, comments,
      undeclared parameters, aliases, or physical columns;
    - final SQL placeholders exactly match the parameter mapping.

    Non-goals:
    - no database execution;
    - no SQL Repair;
    - no user-provided SQL;
    - no claim of full PostgreSQL AST enforcement.
    """
    if not isinstance(
        envelope,
        GovernedPlanningEnvelopeV2,
    ):
        raise TypeError(
            "compile_governed_query_plan_v2 requires "
            "GovernedPlanningEnvelopeV2."
        )

    plan = envelope.query_plan

    if (
        envelope.query_plan_fingerprint
        != query_plan_fingerprint_v2(
            plan
        )
    ):
        return _failed(
            envelope,
            status=(
                QueryPlanCompileStatusV2
                .INVALID_ENVELOPE
            ),
            detail=(
                "Query Plan fingerprint no longer matches "
                "the governed envelope."
            ),
        )

    try:
        parameters = _merge_parameters(
            envelope
        )
        allowed_parameters = frozenset(
            parameter.name
            for parameter in parameters
        )

        _validate_scope_contract_fragments(
            envelope,
            allowed_parameters=(
                allowed_parameters
            ),
        )

        time_filters = (
            _time_filters_by_stage(
                envelope
            )
        )
        scope_filters = (
            _scope_filters_by_stage(
                envelope
            )
        )

        if isinstance(
            plan.query_logic,
            QueryLogic,
        ):
            (
                sql,
                visible_fields,
                hidden_fields,
                compiled_stage_ids,
            ) = _compile_query_logic(
                envelope=envelope,
                logic=plan.query_logic,
                time_filters=time_filters,
                scope_filters=scope_filters,
                allowed_parameters=(
                    allowed_parameters
                ),
            )
        elif isinstance(
            plan.query_logic,
            StagedQueryLogic,
        ):
            (
                sql,
                visible_fields,
                hidden_fields,
                compiled_stage_ids,
            ) = _compile_staged_query_logic(
                envelope=envelope,
                logic=plan.query_logic,
                time_filters=time_filters,
                scope_filters=scope_filters,
                allowed_parameters=(
                    allowed_parameters
                ),
            )
        else:
            return _failed(
                envelope,
                status=(
                    QueryPlanCompileStatusV2
                    .COMPILATION_FAILED
                ),
                detail=(
                    "Unsupported Query Plan logic type."
                ),
            )

        _assert_placeholder_match(
            sql=sql,
            parameters=parameters,
        )

    except _UnsafeFragmentError as exc:
        return _failed(
            envelope,
            status=(
                QueryPlanCompileStatusV2
                .UNSAFE_PLAN_FRAGMENT
            ),
            detail=str(
                exc
            ),
        )
    except _ResourceReferenceError as exc:
        return _failed(
            envelope,
            status=(
                QueryPlanCompileStatusV2
                .RESOURCE_REFERENCE_MISMATCH
            ),
            detail=str(
                exc
            ),
        )
    except _ParameterCollisionError as exc:
        return _failed(
            envelope,
            status=(
                QueryPlanCompileStatusV2
                .PARAMETER_COLLISION
            ),
            detail=str(
                exc
            ),
        )
    except _PlaceholderMismatchError as exc:
        return _failed(
            envelope,
            status=(
                QueryPlanCompileStatusV2
                .PLACEHOLDER_MISMATCH
            ),
            detail=str(
                exc
            ),
        )
    except (
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        return _failed(
            envelope,
            status=(
                QueryPlanCompileStatusV2
                .COMPILATION_FAILED
            ),
            detail=(
                f"{type(exc).__name__}: {exc}"
            ),
        )

    sql_fingerprint = _sha256_text(
        sql
    )
    parameter_names = tuple(
        parameter.name
        for parameter in parameters
    )

    contract_fingerprint = (
        _compiled_contract_fingerprint(
            request_id=envelope.request_id,
            plan_name=envelope.plan_name,
            metric_name=envelope.metric_name,
            result_grain=envelope.result_grain,
            target_schema=envelope.target_schema,
            envelope_fingerprint=(
                envelope.envelope_fingerprint
            ),
            query_plan_fingerprint=(
                envelope.query_plan_fingerprint
            ),
            time_binding_fingerprint=(
                envelope.time_binding
                .contract_fingerprint
            ),
            scope_binding_fingerprint=(
                envelope.scope_binding
                .contract_fingerprint
            ),
            sql_fingerprint=sql_fingerprint,
            parameters=parameters,
            visible_output_fields=(
                visible_fields
            ),
            hidden_output_fields=(
                hidden_fields
            ),
            compiled_stage_ids=(
                compiled_stage_ids
            ),
        )
    )

    contract = CompiledQueryPlanContractV2(
        request_id=envelope.request_id,
        plan_name=envelope.plan_name,
        metric_name=envelope.metric_name,
        result_grain=envelope.result_grain,
        target_schema=envelope.target_schema,
        envelope_fingerprint=(
            envelope.envelope_fingerprint
        ),
        query_plan_fingerprint=(
            envelope.query_plan_fingerprint
        ),
        time_binding_fingerprint=(
            envelope.time_binding
            .contract_fingerprint
        ),
        scope_binding_fingerprint=(
            envelope.scope_binding
            .contract_fingerprint
        ),
        sql=sql,
        parameters=parameters,
        parameter_names=parameter_names,
        visible_output_fields=(
            visible_fields
        ),
        hidden_output_fields=(
            hidden_fields
        ),
        compiled_stage_ids=(
            compiled_stage_ids
        ),
        sql_fingerprint=sql_fingerprint,
        contract_fingerprint=(
            contract_fingerprint
        ),
    )

    return QueryPlanCompileDecisionV2(
        success=True,
        status=QueryPlanCompileStatusV2.COMPILED,
        plan_name=envelope.plan_name,
        metric_name=envelope.metric_name,
        contract=contract,
        detail=None,
        retryable=False,
    )
