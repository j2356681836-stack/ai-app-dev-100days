from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, model_validator

from app.agents.investigation_contracts_v2 import (
    ToolContractV2,
    ToolFailureCodeV2,
    ToolIdentityV2,
)
from app.delivery.decision_console_runtime_v2 import (
    build_day89_local_access_context_v2,
)
from app.delivery.runtime_delivery_bridge_v2 import (
    ApprovedGovernedQueryToolBindingV2,
    RuntimeDeliveryBridgeResultV2,
    RuntimeDeliveryBridgeStatusV2,
    invoke_governed_plan_delivery_v2,
)
from app.governance.execution_policy import GovernedExecutionPolicy
from app.governance.governance_runtime import (
    GovernanceRuntimeConfig,
    load_governance_runtime_config,
)
from app.semantic_layer.analysis_mode_contract_v2 import (
    AnalysisModeV2,
)
from app.semantic_layer.time_comparison_contract_v2 import (
    TimeWindowReferenceV2,
)


FACT_COMPOSITION_CONTRACT_VERSION = "fact_composition_delivery_v2_2"
FACT_COMPOSITION_RECONCILIATION_TOLERANCE = Decimal("0.01")
FACT_COMPOSITION_DEFAULT_TOP_N = 3


class FactCompositionDimensionV2(str, Enum):
    PEOPLE = "membership_level"
    CATEGORY = "category"
    CHANNEL = "channel"
    REGION = "region"


class FactCompositionStatusV2(str, Enum):
    READY = "ready"
    SEED_NOT_READY = "seed_not_ready"
    NOT_APPLICABLE = "not_applicable"
    QUERY_NOT_READY = "query_not_ready"
    INVALID_RESULT = "invalid_result"


class FactCompositionReconciliationStatusV2(str, Enum):
    RECONCILED = "reconciled"
    NOT_RECONCILED = "not_reconciled"


class FactCompositionMemberV2(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    rank: int
    member_label: str
    value: Decimal
    share: Decimal | None


class FactCompositionResultV2(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    contract_version: str = FACT_COMPOSITION_CONTRACT_VERSION
    status: FactCompositionStatusV2
    message: str
    dimension: FactCompositionDimensionV2

    metric_name: str = "gmv"
    analysis_window: TimeWindowReferenceV2 | None = None
    scope_summary: str | None = None

    overall_value: Decimal | None = None
    member_sum: Decimal | None = None
    unexplained_remainder: Decimal | None = None
    reconciliation_status: FactCompositionReconciliationStatusV2 | None = None

    ranking_summary_enabled: bool = True
    top_n: int = 0
    top_n_share: Decimal | None = None
    members: tuple[FactCompositionMemberV2, ...] = ()

    evidence_id: str | None = None
    plan_name: str | None = None
    audit_event_id: str | None = None
    released_row_count: int = 0

    @model_validator(mode="after")
    def validate_result(self) -> "FactCompositionResultV2":
        if not self.message.strip():
            raise ValueError("Composition message 不能为空。")

        if self.status == FactCompositionStatusV2.READY:
            required = (
                self.analysis_window,
                self.overall_value,
                self.member_sum,
                self.unexplained_remainder,
                self.reconciliation_status,
                self.evidence_id,
                self.plan_name,
                self.audit_event_id,
            )
            if any(item is None for item in required):
                raise ValueError("READY Composition 缺少可信交付字段。")
            if self.released_row_count != len(self.members):
                raise ValueError("released_row_count 必须等于完整 members 数量。")
            if self.top_n < 0 or self.top_n > len(self.members):
                raise ValueError("top_n 超出 members 范围。")
        elif self.members:
            raise ValueError("非 READY Composition 不能释放成员结果。")

        return self


@dataclass(frozen=True)
class _FactCompositionSpecV2:
    metric_name: str
    dimension: FactCompositionDimensionV2
    plan_name: str
    result_grain: str
    member_field: str
    value_field: str
    tool_name: str
    tool_purpose: str
    member_order: tuple[str, ...] = ()
    ranking_summary_enabled: bool = True


# 这里只注册“可加构成”能力。
#
# 重要边界：
# - GMV × membership/channel/category 都可以加总回同一个 Overall GMV；
# - Order Count × customer lifecycle/payment-time membership、
#   channel、region 都可以加总回 Overall Order Count：
#   每一张订单在这些维度上都只有一个互斥归属；
# - Order Count × category 故意不注册为 Composition：
#   一张订单可能包含多个品类，按品类 COUNT(DISTINCT order_id)
#   会跨品类重复，因此只能作为 Breakdown，不能伪装成可加构成。
_FACT_COMPOSITION_SPECS_V2: dict[
    tuple[str, FactCompositionDimensionV2],
    _FactCompositionSpecV2,
] = {
    (
        "gmv",
        FactCompositionDimensionV2.PEOPLE,
    ): _FactCompositionSpecV2(
        metric_name="gmv",
        dimension=FactCompositionDimensionV2.PEOPLE,
        plan_name="gmv_membership_level_v2",
        result_grain="membership_level",
        member_field="membership_segment",
        value_field="gmv",
        tool_name="governed_gmv_membership_composition_query",
        tool_purpose=(
            "查询当前可信范围内按支付时会员等级拆分的完整 GMV 构成。"
        ),
    ),
    (
        "gmv",
        FactCompositionDimensionV2.CHANNEL,
    ): _FactCompositionSpecV2(
        metric_name="gmv",
        dimension=FactCompositionDimensionV2.CHANNEL,
        plan_name="gmv_channel_v2",
        result_grain="channel",
        member_field="channel_name",
        value_field="gmv",
        tool_name="governed_gmv_channel_composition_query",
        tool_purpose="查询当前可信范围内的完整渠道 GMV 构成。",
    ),
    (
        "gmv",
        FactCompositionDimensionV2.CATEGORY,
    ): _FactCompositionSpecV2(
        metric_name="gmv",
        dimension=FactCompositionDimensionV2.CATEGORY,
        plan_name="gmv_category_v2",
        result_grain="category",
        member_field="category",
        value_field="gmv",
        tool_name="governed_gmv_category_composition_query",
        tool_purpose="查询当前可信范围内的完整品类 GMV 构成。",
    ),
    (
        "order_count",
        FactCompositionDimensionV2.PEOPLE,
    ): _FactCompositionSpecV2(
        metric_name="order_count",
        dimension=FactCompositionDimensionV2.PEOPLE,
        plan_name="order_count_customer_lifecycle_membership_v2",
        result_grain="customer_lifecycle_membership",
        member_field="customer_segment",
        value_field="order_count",
        tool_name="governed_order_count_customer_composition_query",
        tool_purpose=(
            "查询当前可信范围内的新客订单与老客支付时会员层级订单构成。"
        ),
        member_order=(
            "OLD_PLATINUM",
            "OLD_GOLD",
            "OLD_SILVER",
            "OLD_BRONZE",
            "OLD_NON_MEMBER",
            "NEW_CUSTOMER",
        ),
        ranking_summary_enabled=False,
    ),
    (
        "order_count",
        FactCompositionDimensionV2.CHANNEL,
    ): _FactCompositionSpecV2(
        metric_name="order_count",
        dimension=FactCompositionDimensionV2.CHANNEL,
        plan_name="order_count_channel_v2",
        result_grain="channel",
        member_field="channel_name",
        value_field="order_count",
        tool_name="governed_order_count_channel_composition_query",
        tool_purpose="查询当前可信范围内的完整渠道订单数构成。",
    ),
    (
        "order_count",
        FactCompositionDimensionV2.REGION,
    ): _FactCompositionSpecV2(
        metric_name="order_count",
        dimension=FactCompositionDimensionV2.REGION,
        plan_name="order_count_region_v2",
        result_grain="region",
        member_field="region_name",
        value_field="order_count",
        tool_name="governed_order_count_region_composition_query",
        tool_purpose="查询当前可信范围内的完整地区订单数构成。",
    ),
}


def fact_composition_registered_dimensions_for_metric_v2(
    metric_name: str,
) -> tuple[FactCompositionDimensionV2, ...]:
    """
    返回一个 Metric 已显式批准的“可加构成”维度。

    这是 capability registry，不从 Query Plan 名称动态推断能力。
    """

    metric = metric_name.strip().lower()

    preferred_order = (
        FactCompositionDimensionV2.PEOPLE,
        FactCompositionDimensionV2.CHANNEL,
        FactCompositionDimensionV2.REGION,
        FactCompositionDimensionV2.CATEGORY,
    )

    return tuple(
        dimension
        for dimension in preferred_order
        if (
            metric,
            dimension,
        )
        in _FACT_COMPOSITION_SPECS_V2
    )


def fact_composition_registered_plan_name_v2(
    *,
    metric_name: str,
    dimension: FactCompositionDimensionV2,
) -> str | None:
    """
    返回显式注册的 Composition Query Plan；未注册则返回 None。
    """

    spec = _FACT_COMPOSITION_SPECS_V2.get(
        (
            metric_name.strip().lower(),
            dimension,
        )
    )

    return spec.plan_name if spec is not None else None


def _to_decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _tool_binding_v2(
    spec: _FactCompositionSpecV2,
) -> ApprovedGovernedQueryToolBindingV2:
    tool = ToolContractV2(
        identity=ToolIdentityV2(
            name=spec.tool_name,
            version="dataset_v2",
            purpose=spec.tool_purpose,
        ),
        input_schema_name="GovernedInvestigationInputV2",
        output_schema_name="GovernedFinalizationResult",
        required_permissions=("metric_access", "data_scope"),
        execution_policy_reference="governed_execution_policy_v2",
        failure_semantics=(
            ToolFailureCodeV2.INVALID_INPUT,
            ToolFailureCodeV2.UNAUTHORIZED,
            ToolFailureCodeV2.UNSUPPORTED,
            ToolFailureCodeV2.TIMEOUT,
            ToolFailureCodeV2.NO_DATA,
            ToolFailureCodeV2.EXECUTION_FAILURE,
        ),
        executor_binding="execute_governed_query_v2",
    )

    return ApprovedGovernedQueryToolBindingV2(
        plan_name=spec.plan_name,
        tool_contract=tool,
    )


def fact_composition_available_dimensions_v2(
    seed_result: RuntimeDeliveryBridgeResultV2,
) -> tuple[FactCompositionDimensionV2, ...]:
    if (
        seed_result.status != RuntimeDeliveryBridgeStatusV2.READY
        or seed_result.requested_analysis_mode != AnalysisModeV2.FACT
        or seed_result.delivery is None
        or seed_result.console_view is None
        or seed_result.console_view.fact_metric is None
    ):
        return ()

    scope = seed_result.delivery.evidence_pack.analysis_scope

    if scope.result_grain != "overall":
        return ()

    registered = list(
        fact_composition_registered_dimensions_for_metric_v2(
            scope.metric_name
        )
    )

    if not registered:
        return ()

    requested_scope = seed_result.requested_scope
    requested_channel_codes = (
        requested_scope.channel_codes
        if requested_scope is not None
        else frozenset()
    )

    # 如果 Seed 已经锁定单一/显式 Channel Scope，
    # 再做 Channel Composition 没有新增分析价值。
    if (
        requested_channel_codes
        and FactCompositionDimensionV2.CHANNEL in registered
    ):
        registered.remove(
            FactCompositionDimensionV2.CHANNEL
        )

    requested_region_codes = (
        requested_scope.region_codes
        if requested_scope is not None
        else frozenset()
    )

    if (
        requested_region_codes
        and FactCompositionDimensionV2.REGION in registered
    ):
        registered.remove(
            FactCompositionDimensionV2.REGION
        )

    return tuple(registered)


def build_fact_composition_projection_v2(
    *,
    dimension: FactCompositionDimensionV2,
    metric_name: str = "gmv",
    overall_value: Decimal,
    analysis_window: TimeWindowReferenceV2,
    scope_summary: str | None,
    rows: tuple[dict[str, Any], ...],
    evidence_id: str,
    plan_name: str,
    audit_event_id: str,
    top_n: int = FACT_COMPOSITION_DEFAULT_TOP_N,
) -> FactCompositionResultV2:
    normalized_metric = metric_name.strip().lower()
    spec = _FACT_COMPOSITION_SPECS_V2.get(
        (
            normalized_metric,
            dimension,
        )
    )

    if spec is None:
        raise ValueError(
            "Metric / Dimension 尚未注册 additive Composition："
            f"metric={normalized_metric}; dimension={dimension.value}"
        )

    expected_fields = {
        spec.member_field,
        spec.value_field,
    }

    prepared: list[tuple[str, Decimal]] = []

    for index, row in enumerate(rows):
        if set(row) != expected_fields:
            raise ValueError(
                "Composition Protected Row 与预期结果形状不一致："
                f"row_index={index}; "
                f"expected={sorted(expected_fields)}; actual={sorted(row)}"
            )

        label = str(row[spec.member_field]).strip()
        if not label:
            raise ValueError("Composition member label 不能为空。")

        prepared.append((label, _to_decimal(row[spec.value_field])))

    if spec.member_order:
        order_index = {
            label: index
            for index, label in enumerate(
                spec.member_order,
                start=1,
            )
        }

        unexpected = sorted(
            label
            for label, _ in prepared
            if label not in order_index
        )

        if unexpected:
            raise ValueError(
                "Composition 返回了未注册的人群成员："
                f"{unexpected}"
            )

        prepared.sort(
            key=lambda item: order_index[item[0]]
        )
    else:
        order_index = {}
        prepared.sort(
            key=lambda item: item[1],
            reverse=True,
        )

    members: list[FactCompositionMemberV2] = []
    for dynamic_rank, (label, value) in enumerate(
        prepared,
        start=1,
    ):
        share = value / overall_value if overall_value != 0 else None
        rank = (
            order_index[label]
            if spec.member_order
            else dynamic_rank
        )

        members.append(
            FactCompositionMemberV2(
                rank=rank,
                member_label=label,
                value=value,
                share=share,
            )
        )

    member_sum = sum((item.value for item in members), Decimal("0"))
    remainder = overall_value - member_sum

    reconciliation_status = (
        FactCompositionReconciliationStatusV2.RECONCILED
        if abs(remainder) <= FACT_COMPOSITION_RECONCILIATION_TOLERANCE
        else FactCompositionReconciliationStatusV2.NOT_RECONCILED
    )

    effective_top_n = (
        min(max(top_n, 0), len(members))
        if spec.ranking_summary_enabled
        else 0
    )
    top_n_share = None

    if (
        spec.ranking_summary_enabled
        and overall_value != 0
    ):
        top_n_value = sum(
            (members[index].value for index in range(effective_top_n)),
            Decimal("0"),
        )
        top_n_share = top_n_value / overall_value

    return FactCompositionResultV2(
        status=FactCompositionStatusV2.READY,
        message="Fact Composition 已形成可信交付。",
        dimension=dimension,
        metric_name=spec.metric_name,
        analysis_window=analysis_window,
        scope_summary=scope_summary,
        overall_value=overall_value,
        member_sum=member_sum,
        unexplained_remainder=remainder,
        reconciliation_status=reconciliation_status,
        ranking_summary_enabled=spec.ranking_summary_enabled,
        top_n=effective_top_n,
        top_n_share=top_n_share,
        members=tuple(members),
        evidence_id=evidence_id,
        plan_name=plan_name,
        audit_event_id=audit_event_id,
        released_row_count=len(members),
    )


def _failed(
    *,
    status: FactCompositionStatusV2,
    message: str,
    dimension: FactCompositionDimensionV2,
    metric_name: str = "gmv",
) -> FactCompositionResultV2:
    return FactCompositionResultV2(
        status=status,
        message=message,
        dimension=dimension,
        metric_name=metric_name,
    )


def run_day93_fact_composition_v2(
    *,
    seed_result: RuntimeDeliveryBridgeResultV2,
    dimension: FactCompositionDimensionV2,
    runtime_config: GovernanceRuntimeConfig | None = None,
    execution_policy: GovernedExecutionPolicy | None = None,
) -> FactCompositionResultV2:
    seed_metric_name = (
        seed_result.console_view.fact_metric.metric_name
        if (
            seed_result.console_view is not None
            and seed_result.console_view.fact_metric is not None
        )
        else "gmv"
    )

    available = fact_composition_available_dimensions_v2(seed_result)

    if dimension not in available:
        return _failed(
            status=FactCompositionStatusV2.NOT_APPLICABLE,
            message=(
                "当前 Metric / Requested Scope 下该维度"
                "不是已注册的可加构成，或没有新增分析价值。"
            ),
            dimension=dimension,
            metric_name=seed_metric_name,
        )

    if (
        seed_result.delivery is None
        or seed_result.console_view is None
        or seed_result.console_view.fact_metric is None
    ):
        return _failed(
            status=FactCompositionStatusV2.SEED_NOT_READY,
            message="Fact Seed 缺少可信 Overall KPI。",
            dimension=dimension,
            metric_name=seed_metric_name,
        )

    fact_metric = seed_result.console_view.fact_metric
    seed_scope = seed_result.delivery.evidence_pack.analysis_scope

    if (
        fact_metric.metric_name != seed_scope.metric_name
        or seed_scope.result_grain != "overall"
    ):
        return _failed(
            status=FactCompositionStatusV2.NOT_APPLICABLE,
            message=(
                "当前 Fact Seed 不是一致的 Overall Metric；"
                "不会推断 Composition。"
            ),
            dimension=dimension,
            metric_name=fact_metric.metric_name,
        )

    spec = _FACT_COMPOSITION_SPECS_V2.get(
        (
            seed_scope.metric_name,
            dimension,
        )
    )

    if spec is None:
        return _failed(
            status=FactCompositionStatusV2.NOT_APPLICABLE,
            message="当前 Metric / Dimension 尚未正式注册 additive Composition。",
            dimension=dimension,
            metric_name=seed_scope.metric_name,
        )
    binding = _tool_binding_v2(spec)
    active_config = (
        runtime_config
        if runtime_config is not None
        else load_governance_runtime_config()
    )

    request_id = (
        "day93-fact-composition-"
        f"{dimension.value}-{uuid4().hex}"
    )

    runtime_result = invoke_governed_plan_delivery_v2(
        context=build_day89_local_access_context_v2(request_id=request_id),
        plan_name=spec.plan_name,
        analysis_window=seed_scope.analysis_window,
        question=f"查看当前事实答案的{dimension.value}构成",
        runtime_config=active_config,
        approved_tool_binding=binding,
        requested_scope=seed_result.requested_scope,
        execution_policy=execution_policy,
        event_id=request_id,
    )

    if (
        runtime_result.status != RuntimeDeliveryBridgeStatusV2.READY
        or runtime_result.console_view is None
        or runtime_result.console_view.breakdown is None
    ):
        return _failed(
            status=FactCompositionStatusV2.QUERY_NOT_READY,
            message=(
                "Composition Governed Query 未形成可释放结果："
                f"{runtime_result.message}"
            ),
            dimension=dimension,
            metric_name=seed_scope.metric_name,
        )

    breakdown = runtime_result.console_view.breakdown

    if (
        breakdown.metric_name != spec.metric_name
        or breakdown.result_grain != spec.result_grain
        or breakdown.analysis_window != seed_scope.analysis_window
        or breakdown.plan_name != spec.plan_name
    ):
        return _failed(
            status=FactCompositionStatusV2.INVALID_RESULT,
            message=(
                "Composition Delivery 与 Seed / Plan Contract 不一致，"
                "已 fail closed。"
            ),
            dimension=dimension,
            metric_name=seed_scope.metric_name,
        )

    try:
        return build_fact_composition_projection_v2(
            dimension=dimension,
            metric_name=seed_scope.metric_name,
            overall_value=_to_decimal(fact_metric.value),
            analysis_window=seed_scope.analysis_window,
            scope_summary=breakdown.scope_summary,
            rows=breakdown.rows,
            evidence_id=breakdown.evidence_id,
            plan_name=breakdown.plan_name,
            audit_event_id=breakdown.audit_event_id,
        )
    except ValueError as exc:
        return _failed(
            status=FactCompositionStatusV2.INVALID_RESULT,
            message=(
                "Composition Protected Result 没有满足已注册业务构成合同："
                f"{exc}"
            ),
            dimension=dimension,
            metric_name=seed_scope.metric_name,
        )
