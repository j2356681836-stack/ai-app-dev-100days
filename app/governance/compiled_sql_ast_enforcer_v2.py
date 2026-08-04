from __future__ import annotations

import json
import re
from collections.abc import Mapping
from enum import Enum
from hashlib import sha256
from typing import Any

import sqlglot
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlglot import exp
from sqlglot.errors import ParseError

from app.governance.governed_planning_envelope_v2 import (
    GovernedPlanningEnvelopeV2,
)
from app.semantic_layer.query_plan_compiler_v2 import (
    CompiledQueryPlanContractV2,
)


AST_ENFORCEMENT_VERSION_V2 = (
    "compiled_sql_ast_enforcement_v2_0"
)

_IDENTIFIER_PATTERN = r"^[A-Za-z_][A-Za-z0-9_]*$"
_RESOURCE_COLUMN_PATTERN = (
    r"^[a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*$"
)
_FINGERPRINT_PATTERN = r"^[0-9a-f]{64}$"

_PARAMETER_FINDER = re.compile(
    r"(?<!:):(?P<name>[A-Za-z_][A-Za-z0-9_]*)"
)


# Current Query Plan V2 uses a deliberately narrow SQL capability set.
# CASE / FILTER / arithmetic operators are AST structures rather than
# Func subclasses, so they are governed separately by the parser tree.
_ALLOWED_FUNCTION_CLASSES = frozenset(
    {
        "Avg",
        "Cast",
        "Coalesce",
        "Count",
        "FirstValue",
        "Greatest",
        "LastValue",
        "Least",
        "Max",
        "Min",
        "Nullif",
        "Round",
        "RowNumber",
        "Sum",
    }
)


# Root SELECT checking already blocks ordinary standalone DDL / DML.
# This denylist protects against command or write nodes embedded inside
# a WITH clause or another query subtree.
_FORBIDDEN_NODE_CLASSES = frozenset(
    {
        "Alter",
        "Analyze",
        "Cache",
        "Call",
        "Command",
        "Commit",
        "Copy",
        "Create",
        "Delete",
        "Drop",
        "Execute",
        "Grant",
        "Insert",
        "Intersect",
        "Into",
        "Limit",
        "LoadData",
        "Lock",
        "Merge",
        "Offset",
        "Pragma",
        "Replace",
        "Revoke",
        "Rollback",
        "Set",
        "Transaction",
        "TruncateTable",
        "Uncache",
        "Union",
        "Update",
        "Use",
        "Values",
        "Vacuum",
    }
)


class CompiledSqlAstStatusV2(str, Enum):
    ENFORCED = "enforced"
    INVALID_CONTRACT_LINKAGE = (
        "invalid_contract_linkage"
    )
    SQL_FINGERPRINT_MISMATCH = (
        "sql_fingerprint_mismatch"
    )
    PARSE_FAILED = "parse_failed"
    MULTIPLE_STATEMENTS = "multiple_statements"
    NON_SELECT_ROOT = "non_select_root"
    FORBIDDEN_AST_NODE = "forbidden_ast_node"
    FUNCTION_NOT_ALLOWED = "function_not_allowed"
    WILDCARD_NOT_ALLOWED = "wildcard_not_allowed"
    RECURSIVE_CTE_NOT_ALLOWED = (
        "recursive_cte_not_allowed"
    )
    CTE_CONTRACT_MISMATCH = (
        "cte_contract_mismatch"
    )
    SCHEMA_NOT_ALLOWED = "schema_not_allowed"
    TABLE_CONTRACT_MISMATCH = (
        "table_contract_mismatch"
    )
    COLUMN_CONTRACT_MISMATCH = (
        "column_contract_mismatch"
    )
    ALIAS_RESOLUTION_FAILED = (
        "alias_resolution_failed"
    )
    OUTPUT_CONTRACT_MISMATCH = (
        "output_contract_mismatch"
    )
    PARAMETER_CONTRACT_MISMATCH = (
        "parameter_contract_mismatch"
    )
    AST_ENFORCEMENT_FAILED = (
        "ast_enforcement_failed"
    )


class CompiledSqlAstEnforcementContractV2(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    enforcement_version: str = (
        AST_ENFORCEMENT_VERSION_V2
    )
    sqlglot_version: str

    request_id: str
    plan_name: str = Field(
        pattern=_IDENTIFIER_PATTERN
    )
    metric_name: str = Field(
        pattern=_IDENTIFIER_PATTERN
    )
    target_schema: str = Field(
        pattern=_IDENTIFIER_PATTERN
    )

    envelope_fingerprint: str = Field(
        pattern=_FINGERPRINT_PATTERN
    )
    compiled_contract_fingerprint: str = Field(
        pattern=_FINGERPRINT_PATTERN
    )
    sql_fingerprint: str = Field(
        pattern=_FINGERPRINT_PATTERN
    )
    normalized_ast_fingerprint: str = Field(
        pattern=_FINGERPRINT_PATTERN
    )

    observed_physical_tables: frozenset[str]
    observed_physical_columns: frozenset[str]
    observed_cte_names: tuple[str, ...]
    observed_output_fields: tuple[str, ...]
    observed_function_classes: frozenset[str]
    observed_parameter_names: frozenset[str]

    contract_fingerprint: str = Field(
        pattern=_FINGERPRINT_PATTERN
    )

    @model_validator(mode="after")
    def validate_contract(
        self,
    ) -> "CompiledSqlAstEnforcementContractV2":
        if not self.request_id:
            raise ValueError(
                "request_id cannot be empty."
            )

        for column in self.observed_physical_columns:
            if not re.fullmatch(
                _RESOURCE_COLUMN_PATTERN,
                column,
            ):
                raise ValueError(
                    "Observed physical columns must use "
                    "table.column."
                )

        if len(self.observed_cte_names) != len(
            set(self.observed_cte_names)
        ):
            raise ValueError(
                "Observed CTE names must be unique."
            )

        if len(self.observed_output_fields) != len(
            set(self.observed_output_fields)
        ):
            raise ValueError(
                "Observed output fields must be unique."
            )

        expected = _enforcement_contract_fingerprint(
            sqlglot_version=self.sqlglot_version,
            request_id=self.request_id,
            plan_name=self.plan_name,
            metric_name=self.metric_name,
            target_schema=self.target_schema,
            envelope_fingerprint=(
                self.envelope_fingerprint
            ),
            compiled_contract_fingerprint=(
                self.compiled_contract_fingerprint
            ),
            sql_fingerprint=self.sql_fingerprint,
            normalized_ast_fingerprint=(
                self.normalized_ast_fingerprint
            ),
            observed_physical_tables=(
                self.observed_physical_tables
            ),
            observed_physical_columns=(
                self.observed_physical_columns
            ),
            observed_cte_names=(
                self.observed_cte_names
            ),
            observed_output_fields=(
                self.observed_output_fields
            ),
            observed_function_classes=(
                self.observed_function_classes
            ),
            observed_parameter_names=(
                self.observed_parameter_names
            ),
        )

        if self.contract_fingerprint != expected:
            raise ValueError(
                "AST enforcement contract fingerprint mismatch."
            )

        return self


class CompiledSqlAstDecisionV2(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    success: bool
    status: CompiledSqlAstStatusV2

    plan_name: str
    metric_name: str

    contract: (
        CompiledSqlAstEnforcementContractV2
        | None
    ) = None
    detail: str | None = None
    retryable: bool = False

    @model_validator(mode="after")
    def validate_decision(
        self,
    ) -> "CompiledSqlAstDecisionV2":
        if self.retryable:
            raise ValueError(
                "AST enforcement decisions are deterministic "
                "and non-retryable."
            )

        if self.success:
            if (
                self.status
                != CompiledSqlAstStatusV2.ENFORCED
            ):
                raise ValueError(
                    "Successful AST enforcement must use "
                    "status=ENFORCED."
                )

            if self.contract is None:
                raise ValueError(
                    "Successful AST enforcement requires "
                    "a contract."
                )

            if self.detail is not None:
                raise ValueError(
                    "Successful AST enforcement must not "
                    "expose detail."
                )

            return self

        if self.status == CompiledSqlAstStatusV2.ENFORCED:
            raise ValueError(
                "Failed AST enforcement cannot use ENFORCED."
            )

        if self.contract is not None:
            raise ValueError(
                "Failed AST enforcement must not expose "
                "a contract."
            )

        if not self.detail:
            raise ValueError(
                "Failed AST enforcement requires detail."
            )

        return self


class _AstPolicyError(ValueError):
    def __init__(
        self,
        status: CompiledSqlAstStatusV2,
        detail: str,
    ) -> None:
        super().__init__(
            detail
        )
        self.status = status
        self.detail = detail


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


def _enforcement_contract_fingerprint(
    *,
    sqlglot_version: str,
    request_id: str,
    plan_name: str,
    metric_name: str,
    target_schema: str,
    envelope_fingerprint: str,
    compiled_contract_fingerprint: str,
    sql_fingerprint: str,
    normalized_ast_fingerprint: str,
    observed_physical_tables: frozenset[str],
    observed_physical_columns: frozenset[str],
    observed_cte_names: tuple[str, ...],
    observed_output_fields: tuple[str, ...],
    observed_function_classes: frozenset[str],
    observed_parameter_names: frozenset[str],
) -> str:
    return _sha256_payload(
        {
            "enforcement_version": (
                AST_ENFORCEMENT_VERSION_V2
            ),
            "sqlglot_version": sqlglot_version,
            "request_id": request_id,
            "plan_name": plan_name,
            "metric_name": metric_name,
            "target_schema": target_schema,
            "envelope_fingerprint": (
                envelope_fingerprint
            ),
            "compiled_contract_fingerprint": (
                compiled_contract_fingerprint
            ),
            "sql_fingerprint": sql_fingerprint,
            "normalized_ast_fingerprint": (
                normalized_ast_fingerprint
            ),
            "observed_physical_tables": (
                observed_physical_tables
            ),
            "observed_physical_columns": (
                observed_physical_columns
            ),
            "observed_cte_names": observed_cte_names,
            "observed_output_fields": (
                observed_output_fields
            ),
            "observed_function_classes": (
                observed_function_classes
            ),
            "observed_parameter_names": (
                observed_parameter_names
            ),
        }
    )


def _failed(
    *,
    compiled: CompiledQueryPlanContractV2,
    status: CompiledSqlAstStatusV2,
    detail: str,
) -> CompiledSqlAstDecisionV2:
    return CompiledSqlAstDecisionV2(
        success=False,
        status=status,
        plan_name=compiled.plan_name,
        metric_name=compiled.metric_name,
        contract=None,
        detail=detail,
        retryable=False,
    )


def _assert_contract_linkage(
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
        raise _AstPolicyError(
            CompiledSqlAstStatusV2
            .INVALID_CONTRACT_LINKAGE,
            (
                "Compiled SQL contract does not belong to the "
                "provided governed envelope. "
                f"mismatches={mismatches}"
            ),
        )


def _nearest_select(
    node: exp.Expr,
) -> exp.Select | None:
    current = node.parent

    while current is not None:
        if isinstance(
            current,
            exp.Select,
        ):
            return current

        current = current.parent

    return None


def _projection_names(
    select: exp.Select,
) -> tuple[str, ...]:
    names: list[str] = []

    for projection in select.expressions:
        name = projection.alias_or_name

        if not name:
            raise _AstPolicyError(
                CompiledSqlAstStatusV2
                .OUTPUT_CONTRACT_MISMATCH,
                (
                    "Every SELECT projection must expose a "
                    "deterministic output name. "
                    f"projection={projection.sql(dialect='postgres')}"
                ),
            )

        names.append(
            name
        )

    if len(names) != len(set(names)):
        raise _AstPolicyError(
            CompiledSqlAstStatusV2
            .OUTPUT_CONTRACT_MISMATCH,
            (
                "SELECT projection names must be unique. "
                f"names={names}"
            ),
        )

    return tuple(
        names
    )


def _cte_contract(
    tree: exp.Select,
) -> tuple[
    tuple[str, ...],
    dict[str, frozenset[str]],
]:
    ctes = tuple(
        tree.find_all(
            exp.CTE
        )
    )
    names: list[str] = []
    outputs: dict[
        str,
        frozenset[str],
    ] = {}

    for cte in ctes:
        name = cte.alias_or_name

        if not name:
            raise _AstPolicyError(
                CompiledSqlAstStatusV2
                .CTE_CONTRACT_MISMATCH,
                "Every CTE must have a deterministic name.",
            )

        body = cte.this

        if isinstance(
            body,
            exp.Subquery,
        ):
            body = body.this

        if not isinstance(
            body,
            exp.Select,
        ):
            raise _AstPolicyError(
                CompiledSqlAstStatusV2
                .CTE_CONTRACT_MISMATCH,
                (
                    "Every governed CTE body must be SELECT. "
                    f"cte={name}, "
                    f"node={type(body).__name__}"
                ),
            )

        names.append(
            name
        )
        outputs[name] = frozenset(
            _projection_names(
                body
            )
        )

    if len(names) != len(set(names)):
        raise _AstPolicyError(
            CompiledSqlAstStatusV2
            .CTE_CONTRACT_MISMATCH,
            (
                "CTE names must be unique. "
                f"names={names}"
            ),
        )

    return (
        tuple(
            names
        ),
        outputs,
    )


def _assert_single_select_statement(
    sql: str,
) -> exp.Select:
    try:
        statements = sqlglot.parse(
            sql,
            read="postgres",
        )
    except ParseError as exc:
        raise _AstPolicyError(
            CompiledSqlAstStatusV2.PARSE_FAILED,
            f"PostgreSQL AST parsing failed: {exc}",
        ) from exc

    statements = [
        statement
        for statement in statements
        if statement is not None
    ]

    if len(statements) != 1:
        raise _AstPolicyError(
            CompiledSqlAstStatusV2
            .MULTIPLE_STATEMENTS,
            (
                "Governed SQL must contain exactly one "
                f"statement; actual={len(statements)}"
            ),
        )

    root = statements[0]

    if not isinstance(
        root,
        exp.Select,
    ):
        raise _AstPolicyError(
            CompiledSqlAstStatusV2.NON_SELECT_ROOT,
            (
                "Governed SQL root must be SELECT. "
                f"actual={type(root).__name__}"
            ),
        )

    return root




def _callable_function_identity(
    node: exp.Expr,
) -> tuple[str, str] | None:
    """
    Return (expression_class, SQL_function_name) only when an AST
    node represents an actual callable SQL function.

    SQLGlot's expression hierarchy is broader than "database
    function": structural expressions such as AND can also satisfy
    isinstance(node, exp.Func). Therefore exp.Func alone is not a
    safe classifier.

    Classification rules:
    - exp.Anonymous always represents a parsed function call whose
      concrete name is carried by the node;
    - known governed function classes are callable functions;
    - other exp.Func subclasses are treated as callable only when
      their PostgreSQL serialization starts with FUNCTION_NAME(...).

    Infix / structural expressions such as AND, IN and BETWEEN do not
    match that call shape and are not checked against the function
    allowlist.
    """
    class_name = type(
        node
    ).__name__

    if isinstance(
        node,
        exp.Anonymous,
    ):
        function_name = str(
            node.name
            or class_name
        ).upper()

        return (
            class_name,
            function_name,
        )

    if not isinstance(
        node,
        exp.Func,
    ):
        return None

    if class_name in _ALLOWED_FUNCTION_CLASSES:
        try:
            function_name = str(
                node.sql_name()
            ).upper()
        except (
            AttributeError,
            TypeError,
            ValueError,
        ):
            function_name = class_name.upper()

        return (
            class_name,
            function_name,
        )

    rendered = node.sql(
        dialect="postgres"
    ).lstrip()

    try:
        sql_name = str(
            node.sql_name()
        ).strip()
    except (
        AttributeError,
        TypeError,
        ValueError,
    ):
        sql_name = ""

    candidates = tuple(
        candidate
        for candidate in (
            sql_name,
            class_name,
        )
        if candidate
    )

    for candidate in candidates:
        call_pattern = re.compile(
            rf"^{re.escape(candidate)}\s*\(",
            re.IGNORECASE,
        )

        if call_pattern.match(
            rendered
        ):
            return (
                class_name,
                candidate.upper(),
            )

    return None


def _assert_ast_capabilities(
    tree: exp.Select,
) -> frozenset[str]:
    with_expression = tree.args.get(
        "with_"
    )

    if (
        with_expression is not None
        and bool(
            with_expression.args.get(
                "recursive"
            )
        )
    ):
        raise _AstPolicyError(
            CompiledSqlAstStatusV2
            .RECURSIVE_CTE_NOT_ALLOWED,
            "WITH RECURSIVE is not allowed.",
        )

    function_classes: set[str] = set()

    for node in tree.walk():
        class_name = type(
            node
        ).__name__

        if class_name in _FORBIDDEN_NODE_CLASSES:
            raise _AstPolicyError(
                CompiledSqlAstStatusV2
                .FORBIDDEN_AST_NODE,
                (
                    "AST contains a forbidden capability. "
                    f"node={class_name}, "
                    f"sql={node.sql(dialect='postgres')}"
                ),
            )

        if isinstance(
            node,
            exp.Star,
        ):
            parent = node.parent

            if type(parent).__name__ != "Count":
                raise _AstPolicyError(
                    CompiledSqlAstStatusV2
                    .WILDCARD_NOT_ALLOWED,
                    (
                        "Wildcard projection/reference is not "
                        "allowed. COUNT(*) is the only accepted "
                        "star form."
                    ),
                )

        function_identity = (
            _callable_function_identity(
                node
            )
        )

        if function_identity is not None:
            (
                function_class,
                function_name,
            ) = function_identity

            function_classes.add(
                function_class
            )

            if (
                function_class
                not in _ALLOWED_FUNCTION_CLASSES
            ):
                raise _AstPolicyError(
                    CompiledSqlAstStatusV2
                    .FUNCTION_NOT_ALLOWED,
                    (
                        "SQL function capability is not in the "
                        "Query Plan V2 allowlist. "
                        f"function_class={function_class}, "
                        f"function_name={function_name}, "
                        f"sql={node.sql(dialect='postgres')}"
                    ),
                )

    return frozenset(
        function_classes
    )


def _direct_tables_for_select(
    *,
    tree: exp.Select,
    select: exp.Select,
) -> tuple[exp.Table, ...]:
    return tuple(
        table
        for table in tree.find_all(
            exp.Table
        )
        if _nearest_select(
            table
        ) is select
    )


def _direct_columns_for_select(
    *,
    tree: exp.Select,
    select: exp.Select,
) -> tuple[exp.Column, ...]:
    return tuple(
        column
        for column in tree.find_all(
            exp.Column
        )
        if _nearest_select(
            column
        ) is select
    )


def _is_output_alias_reference(
    *,
    column: exp.Column,
    select: exp.Select,
    output_names: frozenset[str],
) -> bool:
    if column.table:
        return False

    if column.name not in output_names:
        return False

    current = column.parent

    while (
        current is not None
        and current is not select
    ):
        if type(current).__name__ in {
            "Order",
            "Group",
            "Having",
        }:
            return True

        current = current.parent

    return False


def _inspect_resources(
    *,
    tree: exp.Select,
    envelope: GovernedPlanningEnvelopeV2,
    cte_outputs: Mapping[
        str,
        frozenset[str],
    ],
) -> tuple[
    frozenset[str],
    frozenset[str],
]:
    physical_tables: set[str] = set()
    physical_columns: set[str] = set()
    cte_names = frozenset(
        cte_outputs
    )

    selects = tuple(
        tree.find_all(
            exp.Select
        )
    )

    for select in selects:
        source_aliases: dict[
            str,
            tuple[str, str],
        ] = {}

        for table in _direct_tables_for_select(
            tree=tree,
            select=select,
        ):
            if not isinstance(
                table.this,
                exp.Identifier,
            ):
                raise _AstPolicyError(
                    CompiledSqlAstStatusV2
                    .FORBIDDEN_AST_NODE,
                    (
                        "Table functions or dynamic table "
                        "expressions are not allowed. "
                        f"table={table.sql(dialect='postgres')}"
                    ),
                )

            table_name = table.name
            schema_name = table.db
            catalog_name = table.catalog
            alias = table.alias_or_name

            if not alias:
                raise _AstPolicyError(
                    CompiledSqlAstStatusV2
                    .ALIAS_RESOLUTION_FAILED,
                    (
                        "Every table or CTE reference must expose "
                        "a deterministic alias."
                    ),
                )

            if alias in source_aliases:
                raise _AstPolicyError(
                    CompiledSqlAstStatusV2
                    .ALIAS_RESOLUTION_FAILED,
                    (
                        "A SELECT scope contains duplicate source "
                        f"alias={alias}"
                    ),
                )

            if catalog_name:
                raise _AstPolicyError(
                    CompiledSqlAstStatusV2
                    .SCHEMA_NOT_ALLOWED,
                    (
                        "Catalog-qualified table references are "
                        "not allowed. "
                        f"table={table.sql(dialect='postgres')}"
                    ),
                )

            if schema_name:
                if schema_name != envelope.target_schema:
                    raise _AstPolicyError(
                        CompiledSqlAstStatusV2
                        .SCHEMA_NOT_ALLOWED,
                        (
                            "Physical table uses a schema outside "
                            "the governed target. "
                            f"table={table_name}, "
                            f"schema={schema_name}, "
                            f"expected={envelope.target_schema}"
                        ),
                    )

                physical_tables.add(
                    table_name
                )
                source_aliases[alias] = (
                    "physical",
                    table_name,
                )
                continue

            if table_name not in cte_names:
                raise _AstPolicyError(
                    CompiledSqlAstStatusV2
                    .TABLE_CONTRACT_MISMATCH,
                    (
                        "Unqualified table reference is not a "
                        "declared CTE. "
                        f"table={table_name}"
                    ),
                )

            source_aliases[alias] = (
                "cte",
                table_name,
            )

        output_names = frozenset(
            _projection_names(
                select
            )
        )

        for column in _direct_columns_for_select(
            tree=tree,
            select=select,
        ):
            qualifier = column.table
            column_name = column.name

            if not qualifier:
                if _is_output_alias_reference(
                    column=column,
                    select=select,
                    output_names=output_names,
                ):
                    continue

                raise _AstPolicyError(
                    CompiledSqlAstStatusV2
                    .ALIAS_RESOLUTION_FAILED,
                    (
                        "Unqualified column reference is not an "
                        "allowed GROUP/HAVING/ORDER output alias. "
                        f"column={column.sql(dialect='postgres')}"
                    ),
                )

            source = source_aliases.get(
                qualifier
            )

            if source is None:
                raise _AstPolicyError(
                    CompiledSqlAstStatusV2
                    .ALIAS_RESOLUTION_FAILED,
                    (
                        "Column references an unknown source alias "
                        "inside its SELECT scope. "
                        f"column={column.sql(dialect='postgres')}, "
                        f"known_aliases={sorted(source_aliases)}"
                    ),
                )

            source_type, source_name = source

            if source_type == "physical":
                resource_column = (
                    f"{source_name}.{column_name}"
                )

                if (
                    resource_column
                    not in envelope.required_columns
                ):
                    raise _AstPolicyError(
                        CompiledSqlAstStatusV2
                        .COLUMN_CONTRACT_MISMATCH,
                        (
                            "AST references a physical column "
                            "outside the governed resource "
                            "contract. "
                            f"column={resource_column}"
                        ),
                    )

                physical_columns.add(
                    resource_column
                )
                continue

            declared_fields = cte_outputs[
                source_name
            ]

            if column_name not in declared_fields:
                raise _AstPolicyError(
                    CompiledSqlAstStatusV2
                    .COLUMN_CONTRACT_MISMATCH,
                    (
                        "AST references a field not exposed by "
                        "the declared CTE. "
                        f"cte={source_name}, "
                        f"field={column_name}, "
                        f"available={sorted(declared_fields)}"
                    ),
                )

    observed_tables = frozenset(
        physical_tables
    )
    observed_columns = frozenset(
        physical_columns
    )

    if observed_tables != envelope.required_tables:
        raise _AstPolicyError(
            CompiledSqlAstStatusV2
            .TABLE_CONTRACT_MISMATCH,
            (
                "Observed physical tables must exactly match the "
                "governed required_tables. "
                f"missing={sorted(envelope.required_tables - observed_tables)}, "
                f"extra={sorted(observed_tables - envelope.required_tables)}"
            ),
        )

    if observed_columns != envelope.required_columns:
        raise _AstPolicyError(
            CompiledSqlAstStatusV2
            .COLUMN_CONTRACT_MISMATCH,
            (
                "Observed physical columns must exactly match the "
                "governed required_columns. "
                f"missing={sorted(envelope.required_columns - observed_columns)}, "
                f"extra={sorted(observed_columns - envelope.required_columns)}"
            ),
        )

    return (
        observed_tables,
        observed_columns,
    )


def enforce_compiled_sql_ast_v2(
    *,
    envelope: GovernedPlanningEnvelopeV2,
    compiled: CompiledQueryPlanContractV2,
) -> CompiledSqlAstDecisionV2:
    """
    Independently parse and enforce the final compiled PostgreSQL SQL.

    This is a pre-execution governance gate. It never modifies SQL,
    never performs SQL Repair, and never connects to the database.
    """
    if not isinstance(
        envelope,
        GovernedPlanningEnvelopeV2,
    ):
        raise TypeError(
            "envelope must be GovernedPlanningEnvelopeV2."
        )

    if not isinstance(
        compiled,
        CompiledQueryPlanContractV2,
    ):
        raise TypeError(
            "compiled must be CompiledQueryPlanContractV2."
        )

    try:
        _assert_contract_linkage(
            envelope=envelope,
            compiled=compiled,
        )

        actual_sql_fingerprint = _sha256_text(
            compiled.sql
        )

        if (
            actual_sql_fingerprint
            != compiled.sql_fingerprint
        ):
            raise _AstPolicyError(
                CompiledSqlAstStatusV2
                .SQL_FINGERPRINT_MISMATCH,
                (
                    "Compiled SQL no longer matches its frozen "
                    "sql_fingerprint."
                ),
            )

        parameter_names = frozenset(
            _PARAMETER_FINDER.findall(
                compiled.sql
            )
        )
        declared_parameter_names = frozenset(
            compiled.parameter_names
        )

        if parameter_names != declared_parameter_names:
            raise _AstPolicyError(
                CompiledSqlAstStatusV2
                .PARAMETER_CONTRACT_MISMATCH,
                (
                    "SQL placeholders must exactly match the "
                    "compiled parameter contract. "
                    f"missing={sorted(parameter_names - declared_parameter_names)}, "
                    f"unused={sorted(declared_parameter_names - parameter_names)}"
                ),
            )

        tree = _assert_single_select_statement(
            compiled.sql
        )
        function_classes = (
            _assert_ast_capabilities(
                tree
            )
        )

        (
            cte_names,
            cte_outputs,
        ) = _cte_contract(
            tree
        )

        if cte_names != compiled.compiled_stage_ids:
            raise _AstPolicyError(
                CompiledSqlAstStatusV2
                .CTE_CONTRACT_MISMATCH,
                (
                    "Observed CTE sequence must exactly match "
                    "compiled_stage_ids. "
                    f"observed={cte_names}, "
                    f"declared={compiled.compiled_stage_ids}"
                ),
            )

        root_output_fields = _projection_names(
            tree
        )
        expected_output_fields = (
            *compiled.visible_output_fields,
            *compiled.hidden_output_fields,
        )

        if root_output_fields != expected_output_fields:
            raise _AstPolicyError(
                CompiledSqlAstStatusV2
                .OUTPUT_CONTRACT_MISMATCH,
                (
                    "Root SELECT outputs must exactly match the "
                    "compiled visible/hidden output contract. "
                    f"observed={root_output_fields}, "
                    f"expected={expected_output_fields}"
                ),
            )

        (
            physical_tables,
            physical_columns,
        ) = _inspect_resources(
            tree=tree,
            envelope=envelope,
            cte_outputs=cte_outputs,
        )

        normalized_sql = tree.sql(
            dialect="postgres",
            pretty=False,
        )
        normalized_ast_fingerprint = (
            _sha256_text(
                normalized_sql
            )
        )

    except _AstPolicyError as exc:
        return _failed(
            compiled=compiled,
            status=exc.status,
            detail=exc.detail,
        )
    except (
        AttributeError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        return _failed(
            compiled=compiled,
            status=(
                CompiledSqlAstStatusV2
                .AST_ENFORCEMENT_FAILED
            ),
            detail=(
                f"{type(exc).__name__}: {exc}"
            ),
        )

    sqlglot_version = sqlglot.__version__

    contract_fingerprint = (
        _enforcement_contract_fingerprint(
            sqlglot_version=sqlglot_version,
            request_id=compiled.request_id,
            plan_name=compiled.plan_name,
            metric_name=compiled.metric_name,
            target_schema=compiled.target_schema,
            envelope_fingerprint=(
                compiled.envelope_fingerprint
            ),
            compiled_contract_fingerprint=(
                compiled.contract_fingerprint
            ),
            sql_fingerprint=(
                compiled.sql_fingerprint
            ),
            normalized_ast_fingerprint=(
                normalized_ast_fingerprint
            ),
            observed_physical_tables=(
                physical_tables
            ),
            observed_physical_columns=(
                physical_columns
            ),
            observed_cte_names=cte_names,
            observed_output_fields=(
                root_output_fields
            ),
            observed_function_classes=(
                function_classes
            ),
            observed_parameter_names=(
                parameter_names
            ),
        )
    )

    contract = (
        CompiledSqlAstEnforcementContractV2(
            sqlglot_version=sqlglot_version,
            request_id=compiled.request_id,
            plan_name=compiled.plan_name,
            metric_name=compiled.metric_name,
            target_schema=compiled.target_schema,
            envelope_fingerprint=(
                compiled.envelope_fingerprint
            ),
            compiled_contract_fingerprint=(
                compiled.contract_fingerprint
            ),
            sql_fingerprint=(
                compiled.sql_fingerprint
            ),
            normalized_ast_fingerprint=(
                normalized_ast_fingerprint
            ),
            observed_physical_tables=(
                physical_tables
            ),
            observed_physical_columns=(
                physical_columns
            ),
            observed_cte_names=cte_names,
            observed_output_fields=(
                root_output_fields
            ),
            observed_function_classes=(
                function_classes
            ),
            observed_parameter_names=(
                parameter_names
            ),
            contract_fingerprint=(
                contract_fingerprint
            ),
        )
    )

    return CompiledSqlAstDecisionV2(
        success=True,
        status=CompiledSqlAstStatusV2.ENFORCED,
        plan_name=compiled.plan_name,
        metric_name=compiled.metric_name,
        contract=contract,
        detail=None,
        retryable=False,
    )
