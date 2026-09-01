from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
from typing import AbstractSet

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.governance.access_context import AccessContext
from app.semantic_layer.requested_scope_resolution_v2 import (
    RequestedScopeResolutionStatusV2,
    RequestedScopeResolutionV2,
)


class ScopeDimension(str, Enum):
    REGION = "region"
    CHANNEL = "channel"


class RowScopeReason(str, Enum):
    ALLOWED = "allowed"
    EMPTY_SCOPE = "empty_scope"
    INVALID_SOURCE_TABLE = "invalid_source_table"
    INVALID_SCOPE_DECLARATION = "invalid_scope_declaration"
    UNSUPPORTED_SCOPE_PATH = "unsupported_scope_path"
    REQUESTED_SCOPE_UNAUTHORIZED = (
        "requested_scope_unauthorized"
    )
    REQUESTED_SCOPE_DIMENSION_UNSUPPORTED = (
        "requested_scope_dimension_unsupported"
    )
    REQUESTED_SCOPE_UNRESOLVED = (
        "requested_scope_unresolved"
    )


class ScopeJoin(BaseModel):
    """
    一个确定性的表连接步骤。

    left_table.left_column = right_table.right_column
    """

    model_config = ConfigDict(frozen=True)

    left_table: str
    left_column: str
    right_table: str
    right_column: str


class RowScopeRequirement(BaseModel):
    """
    单个事实来源表对应的行级权限要求。

    allowed_codes 保存服务端 AccessContext 中的稳定业务编码。
    lookup_* 描述业务编码如何映射到事实表上的外键锚点。
    """

    model_config = ConfigDict(frozen=True)

    dimension: ScopeDimension
    source_table: str

    anchor_table: str
    anchor_column: str

    lookup_table: str
    lookup_id_column: str
    lookup_code_column: str

    allowed_codes: frozenset[str]
    parameter_name: str

    join_path: tuple[ScopeJoin, ...] = ()


class RowScopePlan(BaseModel):
    """
    不可变 Row Scope Plan。

    plan_fingerprint 用于后续 Initial SQL 与 Repaired SQL
    复用同一个 Scope Requirement。
    """

    model_config = ConfigDict(frozen=True)

    request_id: str
    policy_version: str
    dataset_name: str
    target_schema: str

    source_tables: frozenset[str]
    required_dimensions: frozenset[ScopeDimension]
    requirements: tuple[RowScopeRequirement, ...]

    plan_fingerprint: str


class RowScopeDecision(BaseModel):
    """
    Row Scope Planning 的确定性结果。
    """

    model_config = ConfigDict(frozen=True)

    allowed: bool
    error_type: str | None = None
    reason_code: RowScopeReason
    message: str

    plan: RowScopePlan | None = None

    empty_scope_dimensions: frozenset[ScopeDimension] = Field(
        default_factory=frozenset
    )
    invalid_source_tables: frozenset[str] = Field(
        default_factory=frozenset
    )
    unsupported_scope_paths: frozenset[str] = Field(
        default_factory=frozenset
    )

    policy_version: str
    retryable: bool = False

    @model_validator(mode="after")
    def validate_decision_contract(self):
        if self.allowed:
            if self.error_type is not None:
                raise ValueError(
                    "Allowed Row Scope decision must not contain error_type."
                )
            if self.reason_code != RowScopeReason.ALLOWED:
                raise ValueError(
                    "Allowed Row Scope decision must use reason_code='allowed'."
                )
            if self.plan is None:
                raise ValueError(
                    "Allowed Row Scope decision must contain a plan."
                )
        else:
            if self.error_type != "authorization_error":
                raise ValueError(
                    "Denied Row Scope decision must use authorization_error."
                )
            if self.reason_code == RowScopeReason.ALLOWED:
                raise ValueError(
                    "Denied Row Scope decision cannot use reason_code='allowed'."
                )
            if self.plan is not None:
                raise ValueError(
                    "Denied Row Scope decision must not contain a plan."
                )

        if self.retryable:
            raise ValueError(
                "Row Scope authorization must never be retryable."
            )

        return self


@dataclass(frozen=True)
class _ScopePathSpec:
    anchor_table: str
    anchor_column: str

    lookup_table: str
    lookup_id_column: str
    lookup_code_column: str

    parameter_name: str
    join_path: tuple[tuple[str, str, str, str], ...] = ()


_ORDER_ITEMS_TO_ORDERS = (
    (
        "fact_order_items",
        "order_id",
        "fact_orders",
        "order_id",
    ),
)

_REFUNDS_TO_ORDERS = (
    (
        "fact_refunds",
        "order_item_id",
        "fact_order_items",
        "order_item_id",
    ),
    (
        "fact_order_items",
        "order_id",
        "fact_orders",
        "order_id",
    ),
)

_REVIEWS_TO_ORDERS = (
    (
        "fact_reviews",
        "order_item_id",
        "fact_order_items",
        "order_item_id",
    ),
    (
        "fact_order_items",
        "order_id",
        "fact_orders",
        "order_id",
    ),
)


_REGION_PATHS: dict[str, _ScopePathSpec] = {
    "fact_orders": _ScopePathSpec(
        anchor_table="fact_orders",
        anchor_column="shipping_region_id",
        lookup_table="dim_region",
        lookup_id_column="region_id",
        lookup_code_column="region_code",
        parameter_name="allowed_region_codes",
    ),
    "fact_order_items": _ScopePathSpec(
        anchor_table="fact_orders",
        anchor_column="shipping_region_id",
        lookup_table="dim_region",
        lookup_id_column="region_id",
        lookup_code_column="region_code",
        parameter_name="allowed_region_codes",
        join_path=_ORDER_ITEMS_TO_ORDERS,
    ),
    "fact_refunds": _ScopePathSpec(
        anchor_table="fact_orders",
        anchor_column="shipping_region_id",
        lookup_table="dim_region",
        lookup_id_column="region_id",
        lookup_code_column="region_code",
        parameter_name="allowed_region_codes",
        join_path=_REFUNDS_TO_ORDERS,
    ),
    "fact_reviews": _ScopePathSpec(
        anchor_table="fact_orders",
        anchor_column="shipping_region_id",
        lookup_table="dim_region",
        lookup_id_column="region_id",
        lookup_code_column="region_code",
        parameter_name="allowed_region_codes",
        join_path=_REVIEWS_TO_ORDERS,
    ),
}


_CHANNEL_PATHS: dict[str, _ScopePathSpec] = {
    "fact_orders": _ScopePathSpec(
        anchor_table="fact_orders",
        anchor_column="channel_id",
        lookup_table="dim_channel",
        lookup_id_column="channel_id",
        lookup_code_column="channel_code",
        parameter_name="allowed_channel_codes",
    ),
    "fact_order_items": _ScopePathSpec(
        anchor_table="fact_orders",
        anchor_column="channel_id",
        lookup_table="dim_channel",
        lookup_id_column="channel_id",
        lookup_code_column="channel_code",
        parameter_name="allowed_channel_codes",
        join_path=_ORDER_ITEMS_TO_ORDERS,
    ),
    "fact_refunds": _ScopePathSpec(
        anchor_table="fact_orders",
        anchor_column="channel_id",
        lookup_table="dim_channel",
        lookup_id_column="channel_id",
        lookup_code_column="channel_code",
        parameter_name="allowed_channel_codes",
        join_path=_REFUNDS_TO_ORDERS,
    ),
    "fact_reviews": _ScopePathSpec(
        anchor_table="fact_orders",
        anchor_column="channel_id",
        lookup_table="dim_channel",
        lookup_id_column="channel_id",
        lookup_code_column="channel_code",
        parameter_name="allowed_channel_codes",
        join_path=_REVIEWS_TO_ORDERS,
    ),
    "fact_marketing_spend": _ScopePathSpec(
        anchor_table="fact_marketing_spend",
        anchor_column="channel_id",
        lookup_table="dim_channel",
        lookup_id_column="channel_id",
        lookup_code_column="channel_code",
        parameter_name="allowed_channel_codes",
    ),
    "fact_membership_channel_binding_history": _ScopePathSpec(
        anchor_table="fact_membership_channel_binding_history",
        anchor_column="channel_id",
        lookup_table="dim_channel",
        lookup_id_column="channel_id",
        lookup_code_column="channel_code",
        parameter_name="allowed_channel_codes",
    ),
}


_KNOWN_ANALYTICAL_SOURCE_TABLES = frozenset(
    {
        "fact_orders",
        "fact_order_items",
        "fact_refunds",
        "fact_marketing_spend",
        "fact_reviews",
        "fact_membership_channel_binding_history",
        "fact_membership_tier_history",
    }
)


def _allowed_codes_for_dimension(
    context: AccessContext,
    dimension: ScopeDimension,
) -> frozenset[str]:
    if dimension == ScopeDimension.REGION:
        return context.allowed_region_codes

    return context.allowed_channel_codes


def _requested_codes_for_dimension(
    requested_scope: RequestedScopeResolutionV2 | None,
    dimension: ScopeDimension,
) -> frozenset[str]:
    if (
        requested_scope is None
        or requested_scope.status
        == RequestedScopeResolutionStatusV2.NO_EXPLICIT_SCOPE
    ):
        return frozenset()

    if dimension == ScopeDimension.REGION:
        return requested_scope.region_codes

    return requested_scope.channel_codes


def _effective_codes_for_dimension(
    *,
    context: AccessContext,
    requested_scope: RequestedScopeResolutionV2 | None,
    dimension: ScopeDimension,
) -> frozenset[str]:
    authorized = _allowed_codes_for_dimension(
        context,
        dimension,
    )

    requested = _requested_codes_for_dimension(
        requested_scope,
        dimension,
    )

    if not requested:
        return authorized

    return requested


def _path_for(
    dimension: ScopeDimension,
    source_table: str,
) -> _ScopePathSpec | None:
    if dimension == ScopeDimension.REGION:
        return _REGION_PATHS.get(source_table)

    return _CHANNEL_PATHS.get(source_table)


def _invalid_names(
    values: AbstractSet[str],
) -> frozenset[str]:
    return frozenset(
        value
        for value in values
        if (
            not isinstance(value, str)
            or not value
            or value != value.strip()
        )
    )


def _denied(
    context: AccessContext,
    *,
    reason_code: RowScopeReason,
    message: str,
    empty_scope_dimensions: AbstractSet[ScopeDimension] = frozenset(),
    invalid_source_tables: AbstractSet[str] = frozenset(),
    unsupported_scope_paths: AbstractSet[str] = frozenset(),
) -> RowScopeDecision:
    return RowScopeDecision(
        allowed=False,
        error_type="authorization_error",
        reason_code=reason_code,
        message=message,
        plan=None,
        empty_scope_dimensions=frozenset(
            empty_scope_dimensions
        ),
        invalid_source_tables=frozenset(
            invalid_source_tables
        ),
        unsupported_scope_paths=frozenset(
            unsupported_scope_paths
        ),
        policy_version=context.policy_version,
        retryable=False,
    )


def _build_requirement(
    context: AccessContext,
    dimension: ScopeDimension,
    source_table: str,
    spec: _ScopePathSpec,
    requested_scope: RequestedScopeResolutionV2 | None,
) -> RowScopeRequirement:
    joins = tuple(
        ScopeJoin(
            left_table=left_table,
            left_column=left_column,
            right_table=right_table,
            right_column=right_column,
        )
        for (
            left_table,
            left_column,
            right_table,
            right_column,
        ) in spec.join_path
    )

    return RowScopeRequirement(
        dimension=dimension,
        source_table=source_table,
        anchor_table=spec.anchor_table,
        anchor_column=spec.anchor_column,
        lookup_table=spec.lookup_table,
        lookup_id_column=spec.lookup_id_column,
        lookup_code_column=spec.lookup_code_column,
        allowed_codes=_effective_codes_for_dimension(
            context=context,
            requested_scope=requested_scope,
            dimension=dimension,
        ),
        parameter_name=spec.parameter_name,
        join_path=joins,
    )


def _build_plan_fingerprint(
    context: AccessContext,
    source_tables: frozenset[str],
    dimensions: frozenset[ScopeDimension],
    requirements: tuple[RowScopeRequirement, ...],
) -> str:
    canonical_requirements = []

    for requirement in requirements:
        canonical_requirements.append(
            {
                "dimension": requirement.dimension.value,
                "source_table": requirement.source_table,
                "anchor_table": requirement.anchor_table,
                "anchor_column": requirement.anchor_column,
                "lookup_table": requirement.lookup_table,
                "lookup_id_column": requirement.lookup_id_column,
                "lookup_code_column": requirement.lookup_code_column,
                "allowed_codes": sorted(
                    requirement.allowed_codes
                ),
                "parameter_name": requirement.parameter_name,
                "join_path": [
                    {
                        "left_table": join.left_table,
                        "left_column": join.left_column,
                        "right_table": join.right_table,
                        "right_column": join.right_column,
                    }
                    for join in requirement.join_path
                ],
            }
        )

    payload = {
        "request_id": context.request_id,
        "policy_version": context.policy_version,
        "dataset_name": context.dataset_name,
        "target_schema": context.target_schema,
        "source_tables": sorted(source_tables),
        "required_dimensions": sorted(
            dimension.value
            for dimension in dimensions
        ),
        "requirements": canonical_requirements,
    }

    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    return sha256(encoded).hexdigest()


def plan_row_scope(
    context: AccessContext,
    source_tables: AbstractSet[str],
    required_dimensions: AbstractSet[
        ScopeDimension | str
    ] = frozenset(
        {
            ScopeDimension.REGION,
            ScopeDimension.CHANNEL,
        }
    ),
    requested_scope: RequestedScopeResolutionV2 | None = None,
) -> RowScopeDecision:
    """
    为明确声明的分析事实来源表生成不可变 Row Scope Plan。

    重要边界：
    - source_tables 必须是 Query Plan / Metadata 提供的可信事实来源；
    - 空 Region / Channel 集合表示没有对应行权限，不表示全量权限；
    - 找不到确定性 Scope Path 时 fail closed；
    - 本函数不修改任意 SQL 字符串，也不依赖 LLM；
    - 后续 Initial SQL 与 Repaired SQL 应复用同一个 plan_fingerprint。
    """

    normalized_tables = frozenset(source_tables)

    invalid_names = _invalid_names(normalized_tables)
    unknown_tables = (
        normalized_tables
        - _KNOWN_ANALYTICAL_SOURCE_TABLES
    )

    invalid_tables = invalid_names | unknown_tables

    if not normalized_tables or invalid_tables:
        return _denied(
            context,
            reason_code=RowScopeReason.INVALID_SOURCE_TABLE,
            message=(
                "Row Scope requires one or more known analytical "
                "source tables."
            ),
            invalid_source_tables=invalid_tables,
        )

    try:
        dimensions = frozenset(
            ScopeDimension(dimension)
            for dimension in required_dimensions
        )
    except (TypeError, ValueError):
        return _denied(
            context,
            reason_code=(
                RowScopeReason.INVALID_SCOPE_DECLARATION
            ),
            message="Required scope dimensions are invalid.",
        )

    if not dimensions:
        return _denied(
            context,
            reason_code=(
                RowScopeReason.INVALID_SCOPE_DECLARATION
            ),
            message=(
                "At least one Row Scope dimension is required."
            ),
        )

    if (
        requested_scope is not None
        and requested_scope.status
        == RequestedScopeResolutionStatusV2
        .UNRESOLVED_EXPLICIT_SCOPE
    ):
        return _denied(
            context,
            reason_code=(
                RowScopeReason
                .REQUESTED_SCOPE_UNRESOLVED
            ),
            message=(
                "Explicit Requested Scope contains one or more "
                "unresolved dimension values."
            ),
        )

    requested_dimensions = frozenset(
        dimension
        for dimension in ScopeDimension
        if _requested_codes_for_dimension(
            requested_scope,
            dimension,
        )
    )

    unsupported_requested_dimensions = (
        requested_dimensions
        - dimensions
    )

    if unsupported_requested_dimensions:
        return _denied(
            context,
            reason_code=(
                RowScopeReason
                .REQUESTED_SCOPE_DIMENSION_UNSUPPORTED
            ),
            message=(
                "The Query Plan cannot safely apply one or more "
                "explicitly requested Scope dimensions."
            ),
        )

    unauthorized_requested_dimensions = frozenset(
        dimension
        for dimension in requested_dimensions
        if not _requested_codes_for_dimension(
            requested_scope,
            dimension,
        ).issubset(
            _allowed_codes_for_dimension(
                context,
                dimension,
            )
        )
    )

    if unauthorized_requested_dimensions:
        return _denied(
            context,
            reason_code=(
                RowScopeReason
                .REQUESTED_SCOPE_UNAUTHORIZED
            ),
            message=(
                "One or more explicitly requested Scope values "
                "are outside the authorized data scope."
            ),
        )

    empty_dimensions = frozenset(
        dimension
        for dimension in dimensions
        if not _allowed_codes_for_dimension(
            context,
            dimension,
        )
    )

    if empty_dimensions:
        return _denied(
            context,
            reason_code=RowScopeReason.EMPTY_SCOPE,
            message=(
                "The access context has no allowed codes for one "
                "or more required Row Scope dimensions."
            ),
            empty_scope_dimensions=empty_dimensions,
        )

    unsupported_paths = set()

    for source_table in normalized_tables:
        for dimension in dimensions:
            if _path_for(dimension, source_table) is None:
                unsupported_paths.add(
                    f"{dimension.value}:{source_table}"
                )

    if unsupported_paths:
        return _denied(
            context,
            reason_code=(
                RowScopeReason.UNSUPPORTED_SCOPE_PATH
            ),
            message=(
                "One or more source tables have no deterministic "
                "path for a required Row Scope dimension."
            ),
            unsupported_scope_paths=unsupported_paths,
        )

    requirements = tuple(
        _build_requirement(
            context=context,
            dimension=dimension,
            source_table=source_table,
            spec=_path_for(dimension, source_table),
            requested_scope=requested_scope,
        )
        for source_table in sorted(normalized_tables)
        for dimension in sorted(
            dimensions,
            key=lambda item: item.value,
        )
    )

    fingerprint = _build_plan_fingerprint(
        context=context,
        source_tables=normalized_tables,
        dimensions=dimensions,
        requirements=requirements,
    )

    plan = RowScopePlan(
        request_id=context.request_id,
        policy_version=context.policy_version,
        dataset_name=context.dataset_name,
        target_schema=context.target_schema,
        source_tables=normalized_tables,
        required_dimensions=dimensions,
        requirements=requirements,
        plan_fingerprint=fingerprint,
    )

    return RowScopeDecision(
        allowed=True,
        error_type=None,
        reason_code=RowScopeReason.ALLOWED,
        message="Row Scope plan created.",
        plan=plan,
        policy_version=context.policy_version,
        retryable=False,
    )
