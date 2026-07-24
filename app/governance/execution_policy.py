from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ExecutionErrorType(str, Enum):
    INVALID_EXECUTION_REQUEST = "invalid_execution_request"
    CONFIGURATION_ERROR = "configuration_error"
    STATEMENT_TIMEOUT = "statement_timeout"
    RESULT_TOO_LARGE = "result_too_large"
    POOL_TIMEOUT = "pool_timeout"
    READ_ONLY_VIOLATION = "read_only_violation"
    RESULT_NOT_READABLE = "result_not_readable"
    DATABASE_ERROR = "database_error"


class GovernedExecutionPolicy(BaseModel):
    """
    Dataset V2 的最小数据库执行治理合同。

    当前第一版固定：
    - 只允许 beauty_bi_v2；
    - 事务必须 read-only；
    - 结果超过 max_rows 时拒绝，不返回截断结果；
    - statement timeout、max rows 和参数数量由系统配置。
    """

    model_config = ConfigDict(frozen=True)

    target_schema: str = "beauty_bi_v2"
    read_only: bool = True
    reject_on_row_limit: bool = True

    statement_timeout_ms: int = Field(
        default=5_000,
        ge=100,
        le=60_000,
    )
    max_rows: int = Field(
        default=200,
        ge=1,
        le=5_000,
    )
    max_parameters: int = Field(
        default=200,
        ge=1,
        le=2_000,
    )

    policy_version: str = "execution_governance_v1"

    @model_validator(mode="after")
    def validate_policy_contract(self):
        if self.target_schema != "beauty_bi_v2":
            raise ValueError(
                "target_schema must be 'beauty_bi_v2'"
            )

        if self.read_only is not True:
            raise ValueError(
                "Governed execution must remain read-only."
            )

        if self.reject_on_row_limit is not True:
            raise ValueError(
                "V1 must reject oversized results instead of "
                "silently truncating them."
            )

        if (
            not self.policy_version
            or not self.policy_version.strip()
        ):
            raise ValueError(
                "policy_version cannot be empty or whitespace."
            )

        return self


class GovernedExecutionResult(BaseModel):
    """
    Governed SQL Runner 的结构化结果。

    失败统一 non-retryable，避免 SQL Repair 通过重试绕过
    timeout、row limit、read-only 或连接池限制。
    """

    model_config = ConfigDict(frozen=True)

    success: bool
    rows: tuple[dict[str, Any], ...] = ()
    row_count: int = Field(default=0, ge=0)
    observed_row_count: int = Field(default=0, ge=0)

    error_type: ExecutionErrorType | None = None
    message: str | None = None
    retryable: bool = False

    execution_time_ms: float = Field(ge=0)

    target_schema: str
    statement_timeout_ms: int
    max_rows: int
    policy_version: str

    @model_validator(mode="after")
    def validate_result_contract(self):
        if self.success:
            if self.error_type is not None:
                raise ValueError(
                    "Successful execution cannot contain error_type."
                )

            if self.row_count != len(self.rows):
                raise ValueError(
                    "row_count must equal the number of returned rows."
                )

            if self.observed_row_count != self.row_count:
                raise ValueError(
                    "Successful execution must report the exact "
                    "observed row count."
                )
        else:
            if self.error_type is None:
                raise ValueError(
                    "Failed execution must contain error_type."
                )

            if self.rows:
                raise ValueError(
                    "Failed execution must not return partial rows."
                )

            if self.row_count != 0:
                raise ValueError(
                    "Failed execution must use row_count=0."
                )

        if self.retryable:
            raise ValueError(
                "Execution governance failures must not be retryable."
            )

        return self
