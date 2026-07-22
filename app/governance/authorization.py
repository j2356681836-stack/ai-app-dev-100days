from enum import Enum
from typing import AbstractSet

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.governance.access_context import AccessContext


class AuthorizationReason(str, Enum):
    ALLOWED = "allowed"
    METRIC_NOT_ALLOWED = "metric_not_allowed"
    TABLE_NOT_ALLOWED = "table_not_allowed"
    COLUMN_NOT_ALLOWED = "column_not_allowed"
    EXPLICITLY_DENIED_COLUMN = "explicitly_denied_column"
    INVALID_RESOURCE_DECLARATION = "invalid_resource_declaration"


class AuthorizationDecision(BaseModel):
    """
    确定性权限决策。

    约束：
    - allowed=True 时，不得携带 authorization_error；
    - allowed=False 时，必须是 non-retryable authorization_error；
    - denied_* 字段用于返回完整越权资源，而不是只报告第一个。
    """

    model_config = ConfigDict(frozen=True)

    allowed: bool
    error_type: str | None = None
    reason_code: AuthorizationReason
    message: str

    denied_metrics: frozenset[str] = Field(default_factory=frozenset)
    denied_tables: frozenset[str] = Field(default_factory=frozenset)
    denied_columns: frozenset[str] = Field(default_factory=frozenset)
    explicitly_denied_columns: frozenset[str] = Field(
        default_factory=frozenset
    )

    policy_version: str
    retryable: bool = False

    @model_validator(mode="after")
    def validate_decision_contract(self):
        if self.allowed:
            if self.error_type is not None:
                raise ValueError(
                    "Allowed decision must not contain error_type."
                )
            if self.reason_code != AuthorizationReason.ALLOWED:
                raise ValueError(
                    "Allowed decision must use reason_code='allowed'."
                )
            if self.retryable:
                raise ValueError(
                    "Allowed decision cannot be retryable."
                )
        else:
            if self.error_type != "authorization_error":
                raise ValueError(
                    "Denied decision must use authorization_error."
                )
            if self.reason_code == AuthorizationReason.ALLOWED:
                raise ValueError(
                    "Denied decision cannot use reason_code='allowed'."
                )
            if self.retryable:
                raise ValueError(
                    "Authorization failure must be non-retryable."
                )

        return self


def _allowed(
    context: AccessContext,
    message: str,
) -> AuthorizationDecision:
    return AuthorizationDecision(
        allowed=True,
        error_type=None,
        reason_code=AuthorizationReason.ALLOWED,
        message=message,
        policy_version=context.policy_version,
        retryable=False,
    )


def _denied(
    context: AccessContext,
    *,
    reason_code: AuthorizationReason,
    message: str,
    denied_metrics: AbstractSet[str] = frozenset(),
    denied_tables: AbstractSet[str] = frozenset(),
    denied_columns: AbstractSet[str] = frozenset(),
    explicitly_denied_columns: AbstractSet[str] = frozenset(),
) -> AuthorizationDecision:
    return AuthorizationDecision(
        allowed=False,
        error_type="authorization_error",
        reason_code=reason_code,
        message=message,
        denied_metrics=frozenset(denied_metrics),
        denied_tables=frozenset(denied_tables),
        denied_columns=frozenset(denied_columns),
        explicitly_denied_columns=frozenset(
            explicitly_denied_columns
        ),
        policy_version=context.policy_version,
        retryable=False,
    )


def _invalid_resource_names(
    resources: AbstractSet[str],
) -> frozenset[str]:
    """
    资源名必须是非空字符串，且不能依赖自动 trim 修正。
    """

    return frozenset(
        resource
        for resource in resources
        if (
            not isinstance(resource, str)
            or not resource
            or resource != resource.strip()
        )
    )


def _invalid_column_names(
    columns: AbstractSet[str],
) -> frozenset[str]:
    """
    Day68 列资源使用 table.column 格式。

    Schema 由 AccessContext.target_schema 单独管理，
    因此当前不接受 schema.table.column。
    """

    invalid = set(_invalid_resource_names(columns))

    for column in columns:
        if not isinstance(column, str):
            continue

        parts = column.split(".")

        if (
            len(parts) != 2
            or not parts[0]
            or not parts[1]
        ):
            invalid.add(column)

    return frozenset(invalid)


def _extract_column_tables(
    columns: AbstractSet[str],
) -> frozenset[str]:
    """
    从合法的 table.column 中提取 table。
    调用前必须先通过 _invalid_column_names。
    """

    return frozenset(
        column.split(".", 1)[0]
        for column in columns
    )


def authorize_metric(
    context: AccessContext,
    metric_name: str,
) -> AuthorizationDecision:
    invalid_metrics = _invalid_resource_names(
        frozenset({metric_name})
    )

    if invalid_metrics:
        return _denied(
            context,
            reason_code=(
                AuthorizationReason.INVALID_RESOURCE_DECLARATION
            ),
            message="Metric resource declaration is invalid.",
            denied_metrics=invalid_metrics,
        )

    if metric_name not in context.allowed_metrics:
        return _denied(
            context,
            reason_code=AuthorizationReason.METRIC_NOT_ALLOWED,
            message=(
                f"Metric '{metric_name}' is not allowed "
                "by the current access context."
            ),
            denied_metrics={metric_name},
        )

    return _allowed(
        context,
        message=f"Metric '{metric_name}' is authorized.",
    )


def authorize_tables(
    context: AccessContext,
    required_tables: AbstractSet[str],
) -> AuthorizationDecision:
    required = frozenset(required_tables)
    invalid_tables = _invalid_resource_names(required)

    if invalid_tables:
        return _denied(
            context,
            reason_code=(
                AuthorizationReason.INVALID_RESOURCE_DECLARATION
            ),
            message="Table resource declaration is invalid.",
            denied_tables=invalid_tables,
        )

    denied_tables = required - context.allowed_tables

    if denied_tables:
        return _denied(
            context,
            reason_code=AuthorizationReason.TABLE_NOT_ALLOWED,
            message="One or more required tables are not allowed.",
            denied_tables=denied_tables,
        )

    return _allowed(
        context,
        message="All required tables are authorized.",
    )


def authorize_columns(
    context: AccessContext,
    required_columns: AbstractSet[str],
) -> AuthorizationDecision:
    required = frozenset(required_columns)
    invalid_columns = _invalid_column_names(required)

    if invalid_columns:
        return _denied(
            context,
            reason_code=(
                AuthorizationReason.INVALID_RESOURCE_DECLARATION
            ),
            message="Column resource declaration is invalid.",
            denied_columns=invalid_columns,
        )

    column_tables = _extract_column_tables(required)
    denied_tables = column_tables - context.allowed_tables

    if denied_tables:
        return _denied(
            context,
            reason_code=AuthorizationReason.TABLE_NOT_ALLOWED,
            message=(
                "One or more column source tables are not allowed."
            ),
            denied_tables=denied_tables,
        )

    explicitly_denied = required & context.denied_columns

    if explicitly_denied:
        return _denied(
            context,
            reason_code=(
                AuthorizationReason.EXPLICITLY_DENIED_COLUMN
            ),
            message=(
                "One or more required columns are explicitly denied."
            ),
            explicitly_denied_columns=explicitly_denied,
        )

    denied_columns = required - context.allowed_columns

    if denied_columns:
        return _denied(
            context,
            reason_code=AuthorizationReason.COLUMN_NOT_ALLOWED,
            message="One or more required columns are not allowed.",
            denied_columns=denied_columns,
        )

    return _allowed(
        context,
        message="All required columns are authorized.",
    )


def authorize_resources(
    context: AccessContext,
    required_tables: AbstractSet[str],
    required_columns: AbstractSet[str],
) -> AuthorizationDecision:
    """
    统一检查 Table / Column Scope。

    注意：
    - 每个 table.column 的 table 必须同时出现在 required_tables；
    - 返回所有越权资源，而不是遇到第一个就停止；
    - 显式 denied column 优先决定 reason_code；
    - allowed table 不会隐式开放该表全部列。
    """

    tables = frozenset(required_tables)
    columns = frozenset(required_columns)

    invalid_tables = _invalid_resource_names(tables)
    invalid_columns = _invalid_column_names(columns)

    if invalid_tables or invalid_columns:
        return _denied(
            context,
            reason_code=(
                AuthorizationReason.INVALID_RESOURCE_DECLARATION
            ),
            message="One or more resource declarations are invalid.",
            denied_tables=invalid_tables,
            denied_columns=invalid_columns,
        )

    column_tables = _extract_column_tables(columns)
    undeclared_column_tables = column_tables - tables

    if undeclared_column_tables:
        return _denied(
            context,
            reason_code=(
                AuthorizationReason.INVALID_RESOURCE_DECLARATION
            ),
            message=(
                "Every required column table must also be declared "
                "in required_tables."
            ),
            denied_tables=undeclared_column_tables,
        )

    denied_tables = tables - context.allowed_tables
    explicitly_denied = columns & context.denied_columns
    denied_columns = (
        columns
        - context.allowed_columns
        - explicitly_denied
    )

    if explicitly_denied:
        reason_code = (
            AuthorizationReason.EXPLICITLY_DENIED_COLUMN
        )
        message = (
            "One or more required columns are explicitly denied."
        )
    elif denied_tables:
        reason_code = AuthorizationReason.TABLE_NOT_ALLOWED
        message = "One or more required tables are not allowed."
    elif denied_columns:
        reason_code = AuthorizationReason.COLUMN_NOT_ALLOWED
        message = "One or more required columns are not allowed."
    else:
        return _allowed(
            context,
            message=(
                "All required tables and columns are authorized."
            ),
        )

    return _denied(
        context,
        reason_code=reason_code,
        message=message,
        denied_tables=denied_tables,
        denied_columns=denied_columns,
        explicitly_denied_columns=explicitly_denied,
    )
