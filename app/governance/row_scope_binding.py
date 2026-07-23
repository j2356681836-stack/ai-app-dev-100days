from enum import Enum
from hashlib import sha256
import json
from typing import Sequence

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.governance.row_scope import (
    RowScopePlan,
    RowScopeRequirement,
    ScopeDimension,
)


_IDENTIFIER_PATTERN = r"^[A-Za-z_][A-Za-z0-9_]*$"


class ScopeBindingReason(str, Enum):
    ALLOWED = "allowed"
    INVALID_TARGET_DECLARATION = "invalid_target_declaration"
    MISSING_SCOPE_TARGET = "missing_scope_target"
    EXTRA_SCOPE_TARGET = "extra_scope_target"
    MISSING_PATH_ALIAS = "missing_path_alias"
    PLAN_CONTRACT_MISMATCH = "plan_contract_mismatch"


class TableAliasBinding(BaseModel):
    """
    一个可信 Query Plan 中声明的表名与 SQL 别名绑定。
    """

    model_config = ConfigDict(frozen=True)

    table_name: str = Field(pattern=_IDENTIFIER_PATTERN)
    alias: str = Field(pattern=_IDENTIFIER_PATTERN)


class ScopeTarget(BaseModel):
    """
    SQL 中一个需要应用 Row Scope 的查询目标。

    target_id 用于区分同一张事实表在不同 CTE / 子查询中的实例。
    table_aliases 只声明 Scope Path 所需的表别名，不要求枚举查询中的所有表。
    """

    model_config = ConfigDict(frozen=True)

    target_id: str = Field(pattern=_IDENTIFIER_PATTERN)
    source_table: str = Field(pattern=_IDENTIFIER_PATTERN)
    table_aliases: tuple[TableAliasBinding, ...]

    @model_validator(mode="after")
    def validate_alias_bindings(self):
        if not self.table_aliases:
            raise ValueError("table_aliases cannot be empty")

        table_names = [
            binding.table_name
            for binding in self.table_aliases
        ]
        aliases = [
            binding.alias
            for binding in self.table_aliases
        ]

        if len(table_names) != len(set(table_names)):
            raise ValueError(
                "Each table_name can appear only once in a ScopeTarget."
            )

        if len(aliases) != len(set(aliases)):
            raise ValueError(
                "Each SQL alias can belong to only one table in a ScopeTarget."
            )

        return self


class ScopeParameter(BaseModel):
    """
    SQL 参数绑定。业务编码永远作为参数值，不直接插值进 SQL。
    """

    model_config = ConfigDict(frozen=True)

    name: str = Field(pattern=_IDENTIFIER_PATTERN)
    value: str


class ScopedPredicate(BaseModel):
    """
    某个查询目标上的一个确定性 Region / Channel Predicate。
    """

    model_config = ConfigDict(frozen=True)

    target_id: str
    source_table: str
    dimension: ScopeDimension

    anchor_reference: str
    sql_fragment: str
    parameter_names: tuple[str, ...]


class ScopedQueryContract(BaseModel):
    """
    RowScopePlan 到 SQL Predicate / Parameters 的不可变绑定合同。

    Initial SQL 和 Repaired SQL 必须复用同一个 contract_fingerprint。
    """

    model_config = ConfigDict(frozen=True)

    request_id: str
    policy_version: str
    target_schema: str

    plan_fingerprint: str
    contract_fingerprint: str

    targets: tuple[ScopeTarget, ...]
    predicates: tuple[ScopedPredicate, ...]
    parameters: tuple[ScopeParameter, ...]


class ScopeBindingDecision(BaseModel):
    """
    Scope Predicate Binding 的确定性结果。
    """

    model_config = ConfigDict(frozen=True)

    allowed: bool
    error_type: str | None = None
    reason_code: ScopeBindingReason
    message: str

    contract: ScopedQueryContract | None = None

    missing_source_tables: frozenset[str] = Field(
        default_factory=frozenset
    )
    extra_source_tables: frozenset[str] = Field(
        default_factory=frozenset
    )
    missing_path_aliases: frozenset[str] = Field(
        default_factory=frozenset
    )

    policy_version: str
    retryable: bool = False

    @model_validator(mode="after")
    def validate_decision_contract(self):
        if self.allowed:
            if self.error_type is not None:
                raise ValueError(
                    "Allowed scope binding must not contain error_type."
                )
            if self.reason_code != ScopeBindingReason.ALLOWED:
                raise ValueError(
                    "Allowed scope binding must use reason_code='allowed'."
                )
            if self.contract is None:
                raise ValueError(
                    "Allowed scope binding must contain a contract."
                )
        else:
            if self.error_type != "authorization_error":
                raise ValueError(
                    "Denied scope binding must use authorization_error."
                )
            if self.reason_code == ScopeBindingReason.ALLOWED:
                raise ValueError(
                    "Denied scope binding cannot use reason_code='allowed'."
                )
            if self.contract is not None:
                raise ValueError(
                    "Denied scope binding must not contain a contract."
                )

        if self.retryable:
            raise ValueError(
                "Row Scope binding failures must never be retryable."
            )

        return self


def _denied(
    plan: RowScopePlan,
    *,
    reason_code: ScopeBindingReason,
    message: str,
    missing_source_tables: frozenset[str] = frozenset(),
    extra_source_tables: frozenset[str] = frozenset(),
    missing_path_aliases: frozenset[str] = frozenset(),
) -> ScopeBindingDecision:
    return ScopeBindingDecision(
        allowed=False,
        error_type="authorization_error",
        reason_code=reason_code,
        message=message,
        contract=None,
        missing_source_tables=missing_source_tables,
        extra_source_tables=extra_source_tables,
        missing_path_aliases=missing_path_aliases,
        policy_version=plan.policy_version,
        retryable=False,
    )


def _alias_map(target: ScopeTarget) -> dict[str, str]:
    return {
        binding.table_name: binding.alias
        for binding in target.table_aliases
    }


def _required_path_tables(
    requirement: RowScopeRequirement,
) -> frozenset[str]:
    tables = {
        requirement.source_table,
        requirement.anchor_table,
    }

    for join in requirement.join_path:
        tables.add(join.left_table)
        tables.add(join.right_table)

    return frozenset(tables)


def _parameter_prefix(
    target: ScopeTarget,
    dimension: ScopeDimension,
) -> str:
    return f"scope_{target.target_id}_{dimension.value}"


def _build_predicate(
    plan: RowScopePlan,
    target: ScopeTarget,
    requirement: RowScopeRequirement,
) -> tuple[ScopedPredicate, tuple[ScopeParameter, ...]]:
    aliases = _alias_map(target)
    anchor_alias = aliases[requirement.anchor_table]
    anchor_reference = (
        f"{anchor_alias}.{requirement.anchor_column}"
    )

    sorted_codes = sorted(requirement.allowed_codes)
    prefix = _parameter_prefix(
        target,
        requirement.dimension,
    )

    parameters = tuple(
        ScopeParameter(
            name=f"{prefix}_{index}",
            value=code,
        )
        for index, code in enumerate(sorted_codes)
    )

    placeholders = ", ".join(
        f":{parameter.name}"
        for parameter in parameters
    )

    sql_fragment = (
        f"{anchor_reference} IN ("
        f"SELECT scope_lookup.{requirement.lookup_id_column} "
        f"FROM {plan.target_schema}.{requirement.lookup_table} "
        f"AS scope_lookup "
        f"WHERE scope_lookup.{requirement.lookup_code_column} "
        f"IN ({placeholders})"
        f")"
    )

    predicate = ScopedPredicate(
        target_id=target.target_id,
        source_table=target.source_table,
        dimension=requirement.dimension,
        anchor_reference=anchor_reference,
        sql_fragment=sql_fragment,
        parameter_names=tuple(
            parameter.name
            for parameter in parameters
        ),
    )

    return predicate, parameters


def _contract_fingerprint(
    plan: RowScopePlan,
    targets: tuple[ScopeTarget, ...],
    predicates: tuple[ScopedPredicate, ...],
    parameters: tuple[ScopeParameter, ...],
) -> str:
    payload = {
        "request_id": plan.request_id,
        "policy_version": plan.policy_version,
        "target_schema": plan.target_schema,
        "plan_fingerprint": plan.plan_fingerprint,
        "targets": [
            {
                "target_id": target.target_id,
                "source_table": target.source_table,
                "table_aliases": sorted(
                    (
                        binding.table_name,
                        binding.alias,
                    )
                    for binding in target.table_aliases
                ),
            }
            for target in targets
        ],
        "predicates": [
            {
                "target_id": predicate.target_id,
                "source_table": predicate.source_table,
                "dimension": predicate.dimension.value,
                "anchor_reference": predicate.anchor_reference,
                "sql_fragment": predicate.sql_fragment,
                "parameter_names": list(
                    predicate.parameter_names
                ),
            }
            for predicate in predicates
        ],
        "parameters": [
            {
                "name": parameter.name,
                "value": parameter.value,
            }
            for parameter in parameters
        ],
    }

    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    return sha256(encoded).hexdigest()


def build_scoped_query_contract(
    plan: RowScopePlan,
    targets: Sequence[ScopeTarget],
) -> ScopeBindingDecision:
    """
    将不可变 RowScopePlan 绑定为参数化 SQL Predicate 合同。

    安全约束：
    - 每个 plan.source_table 至少要有一个 ScopeTarget；
    - ScopeTarget 不能引用 plan 外的 source_table；
    - 每条 Scope Path 所需表都必须显式提供可信 SQL alias；
    - Region / Channel 业务编码只进入参数字典，不直接插入 SQL；
    - 不修改任意 SQL 字符串；
    - 合同 fingerprint 应在 Initial SQL 与 Repaired SQL 间复用。
    """

    normalized_targets = tuple(
        sorted(
            targets,
            key=lambda target: target.target_id,
        )
    )

    if not normalized_targets:
        return _denied(
            plan,
            reason_code=(
                ScopeBindingReason.INVALID_TARGET_DECLARATION
            ),
            message="At least one ScopeTarget is required.",
            missing_source_tables=plan.source_tables,
        )

    target_ids = [
        target.target_id
        for target in normalized_targets
    ]

    if len(target_ids) != len(set(target_ids)):
        return _denied(
            plan,
            reason_code=(
                ScopeBindingReason.INVALID_TARGET_DECLARATION
            ),
            message="ScopeTarget target_id values must be unique.",
        )

    target_source_tables = frozenset(
        target.source_table
        for target in normalized_targets
    )

    missing_source_tables = (
        plan.source_tables - target_source_tables
    )
    extra_source_tables = (
        target_source_tables - plan.source_tables
    )

    if missing_source_tables:
        return _denied(
            plan,
            reason_code=ScopeBindingReason.MISSING_SCOPE_TARGET,
            message=(
                "One or more Row Scope source tables have no "
                "ScopeTarget."
            ),
            missing_source_tables=missing_source_tables,
        )

    if extra_source_tables:
        return _denied(
            plan,
            reason_code=ScopeBindingReason.EXTRA_SCOPE_TARGET,
            message=(
                "ScopeTarget contains source tables outside the "
                "RowScopePlan."
            ),
            extra_source_tables=extra_source_tables,
        )

    missing_path_aliases: set[str] = set()

    requirements_by_source: dict[
        str,
        tuple[RowScopeRequirement, ...],
    ] = {}

    for source_table in plan.source_tables:
        requirements = tuple(
            sorted(
                (
                    requirement
                    for requirement in plan.requirements
                    if requirement.source_table == source_table
                ),
                key=lambda requirement: (
                    requirement.dimension.value,
                    requirement.anchor_table,
                    requirement.anchor_column,
                ),
            )
        )

        if not requirements:
            return _denied(
                plan,
                reason_code=(
                    ScopeBindingReason.PLAN_CONTRACT_MISMATCH
                ),
                message=(
                    "RowScopePlan contains a source table without "
                    "requirements."
                ),
            )

        requirements_by_source[source_table] = requirements

    for target in normalized_targets:
        aliases = _alias_map(target)

        for requirement in requirements_by_source[
            target.source_table
        ]:
            required_tables = _required_path_tables(
                requirement
            )

            for table_name in required_tables:
                if table_name not in aliases:
                    missing_path_aliases.add(
                        f"{target.target_id}:{table_name}"
                    )

    if missing_path_aliases:
        return _denied(
            plan,
            reason_code=ScopeBindingReason.MISSING_PATH_ALIAS,
            message=(
                "One or more ScopeTargets do not declare all aliases "
                "required by the deterministic Scope Path."
            ),
            missing_path_aliases=frozenset(
                missing_path_aliases
            ),
        )

    predicates: list[ScopedPredicate] = []
    parameters: list[ScopeParameter] = []

    for target in normalized_targets:
        for requirement in requirements_by_source[
            target.source_table
        ]:
            predicate, predicate_parameters = _build_predicate(
                plan=plan,
                target=target,
                requirement=requirement,
            )

            predicates.append(predicate)
            parameters.extend(predicate_parameters)

    normalized_predicates = tuple(
        sorted(
            predicates,
            key=lambda predicate: (
                predicate.target_id,
                predicate.dimension.value,
            ),
        )
    )

    normalized_parameters = tuple(
        sorted(
            parameters,
            key=lambda parameter: parameter.name,
        )
    )

    contract_fingerprint = _contract_fingerprint(
        plan=plan,
        targets=normalized_targets,
        predicates=normalized_predicates,
        parameters=normalized_parameters,
    )

    contract = ScopedQueryContract(
        request_id=plan.request_id,
        policy_version=plan.policy_version,
        target_schema=plan.target_schema,
        plan_fingerprint=plan.plan_fingerprint,
        contract_fingerprint=contract_fingerprint,
        targets=normalized_targets,
        predicates=normalized_predicates,
        parameters=normalized_parameters,
    )

    return ScopeBindingDecision(
        allowed=True,
        error_type=None,
        reason_code=ScopeBindingReason.ALLOWED,
        message="Scoped Query Contract created.",
        contract=contract,
        policy_version=plan.policy_version,
        retryable=False,
    )


def verify_scope_contract_reuse(
    plan: RowScopePlan,
    contract: ScopedQueryContract,
) -> ScopeBindingDecision:
    """
    验证某个 Initial / Repaired SQL 流程是否仍复用原 RowScopePlan。

    该函数不解析 SQL；它保护的是不可变合同身份。
    SQL AST / Query Plan Enforcement 仍需在后续集成阶段完成。
    """

    matches = (
        contract.request_id == plan.request_id
        and contract.policy_version == plan.policy_version
        and contract.target_schema == plan.target_schema
        and contract.plan_fingerprint == plan.plan_fingerprint
    )

    if not matches:
        return _denied(
            plan,
            reason_code=(
                ScopeBindingReason.PLAN_CONTRACT_MISMATCH
            ),
            message=(
                "Scoped Query Contract does not match the original "
                "RowScopePlan."
            ),
        )

    return ScopeBindingDecision(
        allowed=True,
        error_type=None,
        reason_code=ScopeBindingReason.ALLOWED,
        message="Scoped Query Contract matches the RowScopePlan.",
        contract=contract,
        policy_version=plan.policy_version,
        retryable=False,
    )
