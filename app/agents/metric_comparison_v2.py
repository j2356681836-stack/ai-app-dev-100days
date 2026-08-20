from __future__ import annotations

from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, model_validator

from app.semantic_layer.time_comparison_contract_v2 import (
    TimeComparisonContractV2,
)


class RelativeChangeStatusV2(str, Enum):
    """
    Relative change 的确定性可用状态。

    reference_value == 0 时，relative change 数学上未定义。
    """

    DEFINED = "defined"
    UNDEFINED_REFERENCE_ZERO = "undefined_reference_zero"


class MetricComparisonResultV2(BaseModel):
    """
    一个已经解析好 TimeComparisonContractV2 的指标数值比较结果。

    本合同只负责 current/reference 的确定性数值比较：
    - absolute_change = current - reference
    - relative_change = (current - reference) / reference
    - reference == 0 时 relative_change 明确为 None

    它不负责：
    - SQL execution；
    - Metric semantic resolution；
    - Anomaly threshold；
    - Contribution decomposition；
    - UI formatting。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    metric_name: str
    comparison: TimeComparisonContractV2

    current_evidence_id: str
    reference_evidence_id: str

    current_value: Decimal
    reference_value: Decimal

    absolute_change: Decimal
    relative_change: Decimal | None
    relative_change_status: RelativeChangeStatusV2

    @model_validator(mode="after")
    def validate_result(
        self,
    ) -> "MetricComparisonResultV2":
        if not self.metric_name.strip():
            raise ValueError(
                "metric_name cannot be empty."
            )

        if not self.current_evidence_id.strip():
            raise ValueError(
                "current_evidence_id cannot be empty."
            )

        if not self.reference_evidence_id.strip():
            raise ValueError(
                "reference_evidence_id cannot be empty."
            )

        expected_absolute = (
            self.current_value - self.reference_value
        )

        if self.absolute_change != expected_absolute:
            raise ValueError(
                "absolute_change must equal "
                "current_value - reference_value."
            )

        if self.reference_value == 0:
            if self.relative_change is not None:
                raise ValueError(
                    "reference_value == 0 cannot expose "
                    "relative_change."
                )

            if (
                self.relative_change_status
                != RelativeChangeStatusV2
                .UNDEFINED_REFERENCE_ZERO
            ):
                raise ValueError(
                    "reference_value == 0 requires "
                    "UNDEFINED_REFERENCE_ZERO."
                )

            return self

        expected_relative = (
            self.current_value - self.reference_value
        ) / self.reference_value

        if self.relative_change != expected_relative:
            raise ValueError(
                "relative_change must equal "
                "(current_value - reference_value) "
                "/ reference_value."
            )

        if (
            self.relative_change_status
            != RelativeChangeStatusV2.DEFINED
        ):
            raise ValueError(
                "Comparable values require DEFINED "
                "relative_change_status."
            )

        return self


def compare_metric_values_v2(
    *,
    metric_name: str,
    comparison: TimeComparisonContractV2,
    current_evidence_id: str,
    reference_evidence_id: str,
    current_value: Decimal,
    reference_value: Decimal,
) -> MetricComparisonResultV2:
    """
    对一个 Metric 的 current/reference trusted values
    做确定性比较。

    调用方必须保证输入值来自已经通过治理与 Result Protection
    的可释放 Evidence。本函数不查询数据库，也不重新做权限判断。
    """

    absolute_change = current_value - reference_value

    if reference_value == 0:
        relative_change = None
        relative_status = (
            RelativeChangeStatusV2
            .UNDEFINED_REFERENCE_ZERO
        )
    else:
        relative_change = (
            current_value - reference_value
        ) / reference_value
        relative_status = RelativeChangeStatusV2.DEFINED

    return MetricComparisonResultV2(
        metric_name=metric_name,
        comparison=comparison,
        current_evidence_id=current_evidence_id,
        reference_evidence_id=reference_evidence_id,
        current_value=current_value,
        reference_value=reference_value,
        absolute_change=absolute_change,
        relative_change=relative_change,
        relative_change_status=relative_status,
    )
