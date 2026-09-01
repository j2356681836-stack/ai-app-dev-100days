from enum import Enum
from typing import FrozenSet

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AccessRole(str, Enum):
    SCOPED_ANALYST = "scoped_analyst"
    EXECUTIVE_ANALYST = "executive_analyst"
    GOVERNANCE_AUDITOR = "governance_auditor"


class OperationMode(str, Enum):
    OBSERVE_ADVISE = "observe_advise"
    

class SensitiveDataPolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    allow_direct_identifiers: bool = False
    allow_free_text: bool = False
    allow_cost_data: bool = False

    # 聚合业务敏感指标与原始成本/退款/营销敏感数据分离。
    # 默认 False，只有 server-owned composition root 可以显式开启。
    allow_aggregated_business_metrics: bool = False

    minimum_group_size: int = Field(default=5, ge=1)


class AccessContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    request_id: str
    actor_id: str
    role: AccessRole

    dataset_name: str
    target_schema: str
    operation_mode: OperationMode

    allowed_metrics: FrozenSet[str]
    allowed_tables: FrozenSet[str]
    allowed_columns: FrozenSet[str]
    denied_columns: FrozenSet[str]

    allowed_region_codes: FrozenSet[str]
    allowed_channel_codes: FrozenSet[str]

    sensitive_data_policy: SensitiveDataPolicy
    policy_version: str
    scope_source: str

    @model_validator(mode="after")
    def validate_governance_contract(self):
        if self.dataset_name != "beauty_bi_v2":
            raise ValueError("dataset_name must be 'beauty_bi_v2'")

        if self.target_schema != "beauty_bi_v2":
            raise ValueError("target_schema must be 'beauty_bi_v2' (public is forbidden)")

        intersection = self.allowed_columns & self.denied_columns
        if intersection:
            raise ValueError(f"allowed_columns and denied_columns cannot overlap: {intersection}")

        for field_name in ("request_id", "actor_id", "policy_version", "scope_source"):
            value = getattr(self, field_name)
            if not value or not value.strip():
                raise ValueError(f"{field_name} cannot be empty or whitespace")

        return self