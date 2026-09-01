from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from datetime import date
from decimal import Decimal
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, model_validator

from app.agents.investigation_contracts_v2 import (
    ToolContractV2,
    ToolFailureCodeV2,
    ToolIdentityV2,
)
from app.agents.metric_comparison_v2 import (
    MetricComparisonResultV2,
)
from app.delivery.decision_console_entry_v2 import (
    PeriodicReportCadenceV2,
)
from app.delivery.decision_console_runtime_v2 import (
    build_day89_local_access_context_v2,
    build_periodic_gmv_comparison_v2,
)
from app.delivery.runtime_comparison_delivery_v2 import (
    RuntimeComparisonDeliveryStatusV2,
    build_runtime_comparison_delivery_v2,
)
from app.delivery.runtime_delivery_bridge_v2 import (
    ApprovedGovernedQueryToolBindingV2,
    invoke_governed_plan_delivery_v2,
)
from app.delivery.r12_cohort_runtime_v2 import (
    R12CohortPeriodicRuntimeV2,
    R12CohortRuntimeStatusV2,
    R12MetricRuntimeStatusV2,
    R12ReconciliationV2,
    R12RuntimeReadinessV2,
    run_r12_cohort_periodic_runtime_v2,
)
from app.governance.execution_policy import GovernedExecutionPolicy
from app.governance.governance_runtime import (
    GovernanceRuntimeConfig,
    load_governance_runtime_config,
)
from app.semantic_layer.query_plan_v2_loader import (
    get_query_plan_v2_by_name,
)
from app.semantic_layer.time_comparison_contract_v2 import (
    TimeComparisonContractV2,
    TimeWindowReferenceV2,
)


PERIODIC_BUSINESS_REPORT_VERSION = (
    "periodic_business_report_v2_1"
)
DRIVER_RECONCILIATION_MONEY_TOLERANCE = Decimal("0.01")
PERIODIC_METRIC_MAX_WORKERS = 4


class PeriodicBusinessReportStatusV2(str, Enum):
    READY = "ready"
    PARTIAL_READY = "partial_ready"
    NOT_READY = "not_ready"


class PeriodicMetricStatusV2(str, Enum):
    READY = "ready"
    NOT_READY = "not_ready"


class PeriodicMetricDisplayKindV2(str, Enum):
    MONEY = "money"
    COUNT = "count"
    RATIO = "ratio"
    DECIMAL = "decimal"


class PeriodicMetricSectionV2(str, Enum):
    OVERVIEW = "overview"
    SALES_DRIVER = "sales_driver"
    CUSTOMER_HEALTH = "customer_health"


class PeriodicMetricSpecV2(BaseModel):
    """
    Periodic Business Report 的 server-owned 指标注册合同。

    这里显式注册可用于正式报表的 Query Plan，
    不允许 UI 根据 metric 名称临时拼接 Plan / Tool identity。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    metric_name: str
    plan_name: str
    chinese_name: str
    section: PeriodicMetricSectionV2
    display_kind: PeriodicMetricDisplayKindV2
    required: bool
    tool_name: str
    purpose: str

    @model_validator(mode="after")
    def validate_spec(self) -> "PeriodicMetricSpecV2":
        text_fields = (
            self.metric_name,
            self.plan_name,
            self.chinese_name,
            self.tool_name,
            self.purpose,
        )

        if any(not value.strip() for value in text_fields):
            raise ValueError("Periodic Metric Spec 文本字段不能为空。")

        return self


class PeriodicMetricSnapshotV2(BaseModel):
    """
    单个指标在 current / reference 两个可信窗口中的报表投影。

    数值只来自 MetricComparisonResultV2，
    UI 不需要重新计算业务差值。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    spec: PeriodicMetricSpecV2
    status: PeriodicMetricStatusV2
    message: str

    current_value: Decimal | None = None
    reference_value: Decimal | None = None
    absolute_change: Decimal | None = None
    relative_change: Decimal | None = None

    # 只用于 ratio：
    # 例如 12% -> 10%，absolute_change=0.02，
    # percentage_point_change=2。
    percentage_point_change: Decimal | None = None

    current_evidence_id: str | None = None
    reference_evidence_id: str | None = None

    @model_validator(mode="after")
    def validate_snapshot(
        self,
    ) -> "PeriodicMetricSnapshotV2":
        if not self.message.strip():
            raise ValueError("Periodic Metric message 不能为空。")

        trusted_fields = (
            self.current_value,
            self.reference_value,
            self.absolute_change,
            self.current_evidence_id,
            self.reference_evidence_id,
        )

        if self.status == PeriodicMetricStatusV2.READY:
            if any(value is None for value in trusted_fields):
                raise ValueError(
                    "READY Metric Snapshot 缺少可信比较字段。"
                )

            if (
                self.spec.display_kind
                == PeriodicMetricDisplayKindV2.RATIO
            ):
                if self.percentage_point_change is None:
                    raise ValueError(
                        "READY ratio metric 必须提供百分点变化。"
                    )
            elif self.percentage_point_change is not None:
                raise ValueError(
                    "非 ratio metric 不得提供 percentage_point_change。"
                )
        else:
            if any(value is not None for value in trusted_fields):
                raise ValueError(
                    "NOT_READY Metric Snapshot 不得释放可信数值。"
                )

            if self.relative_change is not None:
                raise ValueError(
                    "NOT_READY Metric Snapshot 不得释放 relative_change。"
                )

            if self.percentage_point_change is not None:
                raise ValueError(
                    "NOT_READY Metric Snapshot 不得释放百分点变化。"
                )

        return self


class PeriodicDriverReconciliationStatusV2(str, Enum):
    RECONCILED = "reconciled"
    NOT_RECONCILED = "not_reconciled"
    NOT_AVAILABLE = "not_available"


class PeriodicDriverReconciliationV2(BaseModel):
    """
    已有正式指标之间的确定性驱动关系验证。

    不是新的业务指标，也不访问数据库。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    relationship: str
    status: PeriodicDriverReconciliationStatusV2
    observed_value: Decimal | None = None
    reconstructed_value: Decimal | None = None
    remainder: Decimal | None = None
    message: str

    @model_validator(mode="after")
    def validate_reconciliation(
        self,
    ) -> "PeriodicDriverReconciliationV2":
        if not self.relationship.strip():
            raise ValueError("relationship 不能为空。")

        if not self.message.strip():
            raise ValueError("reconciliation message 不能为空。")

        values = (
            self.observed_value,
            self.reconstructed_value,
            self.remainder,
        )

        if (
            self.status
            == PeriodicDriverReconciliationStatusV2.NOT_AVAILABLE
        ):
            if any(value is not None for value in values):
                raise ValueError(
                    "NOT_AVAILABLE reconciliation 不得释放数值。"
                )
        elif any(value is None for value in values):
            raise ValueError(
                "可验证 reconciliation 必须包含 observed / "
                "reconstructed / remainder。"
            )

        return self


class PeriodicR12CustomerHealthV2(BaseModel):
    """
    Periodic Business Report 内的 R12 Customer Health Trust Contract。

    R12 数值本身仍投影进顶层 metrics，方便统一 KPI/section 消费；
    这里保留的是 R12 特有的可信边界：
    - current/reference 各自的 R12 Base readiness；
    - refund observation readiness；
    - R12 deterministic reconciliation。

    UI 不需要重新推导这些状态。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    status: R12CohortRuntimeStatusV2
    message: str

    current_readiness: R12RuntimeReadinessV2
    reference_readiness: R12RuntimeReadinessV2

    ready_metric_count: int
    failed_metric_count: int

    reconciliations: tuple[
        R12ReconciliationV2,
        ...
    ] = ()

    @model_validator(mode="after")
    def validate_customer_health(
        self,
    ) -> "PeriodicR12CustomerHealthV2":
        if not self.message.strip():
            raise ValueError(
                "R12 Customer Health message 不能为空。"
            )

        if (
            self.ready_metric_count < 0
            or self.failed_metric_count < 0
        ):
            raise ValueError(
                "R12 metric counts 不得为负。"
            )

        if (
            self.ready_metric_count
            + self.failed_metric_count
            != 5
        ):
            raise ValueError(
                "R12 Customer Health 必须覆盖完整 5 Metric family。"
            )

        if self.status == R12CohortRuntimeStatusV2.READY:
            if (
                self.ready_metric_count != 5
                or self.failed_metric_count != 0
            ):
                raise ValueError(
                    "READY R12 Customer Health 必须 5/5 READY。"
                )
        elif (
            self.status
            == R12CohortRuntimeStatusV2.PARTIAL_READY
        ):
            if (
                self.ready_metric_count == 0
                or self.failed_metric_count == 0
            ):
                raise ValueError(
                    "PARTIAL_READY 必须同时包含 READY / NOT_READY。"
                )
        else:
            if (
                self.ready_metric_count != 0
                or self.failed_metric_count != 5
            ):
                raise ValueError(
                    "NOT_READY R12 Customer Health 必须 0/5 READY。"
                )

        return self


class PeriodicBusinessReportV2(BaseModel):
    """
    Multi-KPI Periodic Business Report Runtime Contract。

    当前阶段只负责：
    - 统一 TimeComparisonContract；
    - 多个正式 Overall Query Plan 的可信比较；
    - Metric-level partial failure；
    - 核心指标可用性 Gate；
    - 驱动关系 reconciliation。

    B5B-3A 新增：
    - R12 Customer Health Runtime projection；
    - R12 History / Refund Observation readiness disclosure；
    - R12 deterministic reconciliation disclosure。

    当前仍不负责：
    - 人货场 breakdown；
    - 图表；
    - Markdown / HTML Export；
    - LLM 自由总结。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    contract_version: str = PERIODIC_BUSINESS_REPORT_VERSION
    status: PeriodicBusinessReportStatusV2
    message: str

    cadence: PeriodicReportCadenceV2
    anchor_date: date
    comparison: TimeComparisonContractV2

    metrics: tuple[PeriodicMetricSnapshotV2, ...]

    ready_metric_count: int
    failed_metric_count: int
    required_failed_metric_names: tuple[str, ...] = ()

    driver_reconciliations: tuple[
        PeriodicDriverReconciliationV2,
        ...
    ] = ()

    # B5B-3：R12-specific readiness / reconciliation。
    # 顶层 metrics 仍包含 5 个 R12 snapshots，避免 UI 建立第二套 KPI 模型。
    r12_customer_health: (
        PeriodicR12CustomerHealthV2 | None
    ) = None

    @model_validator(mode="after")
    def validate_report(self) -> "PeriodicBusinessReportV2":
        if not self.message.strip():
            raise ValueError("Periodic Business Report message 不能为空。")

        if not self.metrics:
            raise ValueError("Periodic Business Report 至少需要一个指标。")

        metric_names = [
            item.spec.metric_name
            for item in self.metrics
        ]

        if len(metric_names) != len(set(metric_names)):
            raise ValueError(
                "Periodic Business Report 不能包含重复 metric。"
            )

        observed_ready = sum(
            item.status == PeriodicMetricStatusV2.READY
            for item in self.metrics
        )
        observed_failed = len(self.metrics) - observed_ready

        if self.ready_metric_count != observed_ready:
            raise ValueError("ready_metric_count 与 metrics 不一致。")

        if self.failed_metric_count != observed_failed:
            raise ValueError("failed_metric_count 与 metrics 不一致。")

        actual_required_failed = tuple(
            item.spec.metric_name
            for item in self.metrics
            if (
                item.spec.required
                and item.status != PeriodicMetricStatusV2.READY
            )
        )

        if self.required_failed_metric_names != actual_required_failed:
            raise ValueError(
                "required_failed_metric_names 与 metrics 不一致。"
            )

        if self.status == PeriodicBusinessReportStatusV2.READY:
            if self.failed_metric_count != 0:
                raise ValueError("READY Report 不能包含失败指标。")
        elif (
            self.status
            == PeriodicBusinessReportStatusV2.PARTIAL_READY
        ):
            if self.required_failed_metric_names:
                raise ValueError(
                    "PARTIAL_READY 的 required metrics 必须全部 READY。"
                )
            if (
                self.ready_metric_count == 0
                or self.failed_metric_count == 0
            ):
                raise ValueError(
                    "PARTIAL_READY 必须同时存在 READY 与失败指标。"
                )
        else:
            if not self.required_failed_metric_names:
                raise ValueError(
                    "NOT_READY 必须至少有一个 required metric 失败。"
                )

        if self.r12_customer_health is not None:
            r12_names = {
                spec.metric_name
                for spec in PERIODIC_R12_METRIC_SPECS_V2
            }
            r12_metrics = tuple(
                item
                for item in self.metrics
                if item.spec.metric_name in r12_names
            )

            if len(r12_metrics) != 5:
                raise ValueError(
                    "启用 R12 Customer Health 时，顶层 metrics "
                    "必须包含完整 5 个 R12 Metric snapshots。"
                )

            observed_r12_ready = sum(
                item.status == PeriodicMetricStatusV2.READY
                for item in r12_metrics
            )
            observed_r12_failed = (
                len(r12_metrics) - observed_r12_ready
            )

            if (
                observed_r12_ready
                != self.r12_customer_health.ready_metric_count
                or observed_r12_failed
                != self.r12_customer_health.failed_metric_count
            ):
                raise ValueError(
                    "R12 Customer Health counts 与顶层 metrics 不一致。"
                )

        return self


PERIODIC_METRIC_REGISTRY_V2: tuple[
    PeriodicMetricSpecV2,
    ...
] = (
    PeriodicMetricSpecV2(
        metric_name="gmv",
        plan_name="gmv_overall_v2",
        chinese_name="GMV",
        section=PeriodicMetricSectionV2.OVERVIEW,
        display_kind=PeriodicMetricDisplayKindV2.MONEY,
        required=True,
        tool_name="governed_periodic_gmv_overall_query",
        purpose="查询周期报表授权范围内的整体 GMV。",
    ),
    PeriodicMetricSpecV2(
        metric_name="buyer_count",
        plan_name="buyer_count_overall_v2",
        chinese_name="购买人数",
        section=PeriodicMetricSectionV2.OVERVIEW,
        display_kind=PeriodicMetricDisplayKindV2.COUNT,
        required=True,
        tool_name="governed_periodic_buyer_count_overall_query",
        purpose="查询周期报表授权范围内的整体购买人数。",
    ),
    PeriodicMetricSpecV2(
        metric_name="spending_per_buyer",
        plan_name="spending_per_buyer_overall_v2",
        chinese_name="Spending",
        section=PeriodicMetricSectionV2.OVERVIEW,
        display_kind=PeriodicMetricDisplayKindV2.MONEY,
        required=True,
        tool_name="governed_periodic_spending_overall_query",
        purpose="查询周期报表授权范围内的人均消费金额。",
    ),
    PeriodicMetricSpecV2(
        metric_name="refund_rate",
        plan_name="refund_rate_overall_v2",
        chinese_name="退款率",
        section=PeriodicMetricSectionV2.OVERVIEW,
        display_kind=PeriodicMetricDisplayKindV2.RATIO,
        required=False,
        tool_name="governed_periodic_refund_rate_overall_query",
        purpose="查询周期报表授权范围内的整体退款率。",
    ),
    PeriodicMetricSpecV2(
        metric_name="order_count",
        plan_name="order_count_overall_v2",
        chinese_name="订单量",
        section=PeriodicMetricSectionV2.SALES_DRIVER,
        display_kind=PeriodicMetricDisplayKindV2.COUNT,
        required=False,
        tool_name="governed_periodic_order_count_overall_query",
        purpose="查询周期报表授权范围内的成功支付订单量。",
    ),
    PeriodicMetricSpecV2(
        metric_name="units_sold",
        plan_name="units_sold_overall_v2",
        chinese_name="交易件数",
        section=PeriodicMetricSectionV2.SALES_DRIVER,
        display_kind=PeriodicMetricDisplayKindV2.COUNT,
        required=False,
        tool_name="governed_periodic_units_sold_overall_query",
        purpose="查询周期报表授权范围内的交易件数。",
    ),
    PeriodicMetricSpecV2(
        metric_name="aus",
        plan_name="aus_overall_v2",
        chinese_name="AUS",
        section=PeriodicMetricSectionV2.SALES_DRIVER,
        display_kind=PeriodicMetricDisplayKindV2.MONEY,
        required=False,
        tool_name="governed_periodic_aus_overall_query",
        purpose="查询周期报表授权范围内的平均订单金额 AUS。",
    ),
    PeriodicMetricSpecV2(
        metric_name="purchase_frequency",
        plan_name="purchase_frequency_overall_v2",
        chinese_name="FREQ",
        section=PeriodicMetricSectionV2.SALES_DRIVER,
        display_kind=PeriodicMetricDisplayKindV2.DECIMAL,
        required=False,
        tool_name="governed_periodic_purchase_frequency_overall_query",
        purpose="查询周期报表授权范围内的人均购买频次 FREQ。",
    ),
    PeriodicMetricSpecV2(
        metric_name="ipt",
        plan_name="ipt_overall_v2",
        chinese_name="IPT",
        section=PeriodicMetricSectionV2.SALES_DRIVER,
        display_kind=PeriodicMetricDisplayKindV2.DECIMAL,
        required=False,
        tool_name="governed_periodic_ipt_overall_query",
        purpose="查询周期报表授权范围内的每单件数 IPT。",
    ),
    PeriodicMetricSpecV2(
        metric_name="repeat_customer_rate",
        plan_name="repeat_customer_rate_overall_v2",
        chinese_name="窗口内跨日复购率",
        section=PeriodicMetricSectionV2.CUSTOMER_HEALTH,
        display_kind=PeriodicMetricDisplayKindV2.RATIO,
        required=False,
        tool_name="governed_periodic_repeat_rate_overall_query",
        purpose="查询周期报表授权范围内的窗口内跨日复购率。",
    ),
    PeriodicMetricSpecV2(
        metric_name="member_gmv_share",
        plan_name="member_gmv_share_overall_v2",
        chinese_name="会员GMV贡献率",
        section=PeriodicMetricSectionV2.CUSTOMER_HEALTH,
        display_kind=PeriodicMetricDisplayKindV2.RATIO,
        required=False,
        tool_name="governed_periodic_member_gmv_share_overall_query",
        purpose="查询周期报表授权范围内的会员 GMV 贡献率。",
    ),
)


PERIODIC_R12_METRIC_SPECS_V2: tuple[
    PeriodicMetricSpecV2,
    ...
] = (
    PeriodicMetricSpecV2(
        metric_name="r12_base_customer_count",
        plan_name="r12_base_customer_count_overall_v2",
        chinese_name="R12 Base客户数",
        section=PeriodicMetricSectionV2.CUSTOMER_HEALTH,
        display_kind=PeriodicMetricDisplayKindV2.COUNT,
        required=False,
        tool_name="governed_r12_base_customer_count_query",
        purpose=(
            "展示报表期前完整 R12 Effective Purchase Base 客户数。"
        ),
    ),
    PeriodicMetricSpecV2(
        metric_name="r12_repurchase_customer_count",
        plan_name="r12_repurchase_customer_count_overall_v2",
        chinese_name="R12回购客户数",
        section=PeriodicMetricSectionV2.CUSTOMER_HEALTH,
        display_kind=PeriodicMetricDisplayKindV2.COUNT,
        required=False,
        tool_name="governed_r12_repurchase_customer_count_query",
        purpose="展示 R12 Base 中本期再次 Effective Purchase 的客户数。",
    ),
    PeriodicMetricSpecV2(
        metric_name="r12_repurchase_rate",
        plan_name="r12_repurchase_rate_overall_v2",
        chinese_name="R12回购率",
        section=PeriodicMetricSectionV2.CUSTOMER_HEALTH,
        display_kind=PeriodicMetricDisplayKindV2.RATIO,
        required=False,
        tool_name="governed_r12_repurchase_rate_query",
        purpose="展示 R12回购客户数 / R12 Base客户数。",
    ),
    PeriodicMetricSpecV2(
        metric_name="r12_repurchase_amount",
        plan_name="r12_repurchase_amount_overall_v2",
        chinese_name="R12回购有效消费金额",
        section=PeriodicMetricSectionV2.CUSTOMER_HEALTH,
        display_kind=PeriodicMetricDisplayKindV2.MONEY,
        required=False,
        tool_name="governed_r12_repurchase_amount_query",
        purpose="展示通过聚合敏感数据保护后的 R12 回购有效消费金额。",
    ),
    PeriodicMetricSpecV2(
        metric_name="r12_repurchase_spending",
        plan_name="r12_repurchase_spending_overall_v2",
        chinese_name="R12回购客人均有效消费",
        section=PeriodicMetricSectionV2.CUSTOMER_HEALTH,
        display_kind=PeriodicMetricDisplayKindV2.MONEY,
        required=False,
        tool_name="governed_r12_repurchase_spending_query",
        purpose="展示 R12回购有效消费金额 / R12回购客户数。",
    ),
)


ALL_PERIODIC_METRIC_SPECS_V2: tuple[
    PeriodicMetricSpecV2,
    ...
] = (
    *PERIODIC_METRIC_REGISTRY_V2,
    *PERIODIC_R12_METRIC_SPECS_V2,
)


def validate_periodic_metric_registry_v2() -> None:
    """
    Registry 必须与当前 canonical Query Plan Catalog 一致。

    这里故意不做“找不到就猜 Plan 名”或动态 fallback。
    """

    metric_names: set[str] = set()
    plan_names: set[str] = set()
    tool_names: set[str] = set()

    for spec in ALL_PERIODIC_METRIC_SPECS_V2:
        if spec.metric_name in metric_names:
            raise ValueError(
                f"Periodic Registry metric 重复：{spec.metric_name}"
            )

        if spec.plan_name in plan_names:
            raise ValueError(
                f"Periodic Registry plan 重复：{spec.plan_name}"
            )

        if spec.tool_name in tool_names:
            raise ValueError(
                f"Periodic Registry tool identity 重复：{spec.tool_name}"
            )

        plan = get_query_plan_v2_by_name(spec.plan_name)

        if plan is None:
            raise ValueError(
                f"Periodic Registry Query Plan 不存在：{spec.plan_name}"
            )

        if plan.metric != spec.metric_name:
            raise ValueError(
                "Periodic Registry metric / plan 不一致："
                f"metric={spec.metric_name}; "
                f"plan_metric={plan.metric}; "
                f"plan={spec.plan_name}"
            )

        if plan.result_grain != "overall":
            raise ValueError(
                "Periodic Business Report V2 只注册 overall plan："
                f"{spec.plan_name} -> {plan.result_grain}"
            )

        metric_names.add(spec.metric_name)
        plan_names.add(spec.plan_name)
        tool_names.add(spec.tool_name)


def _tool_binding_v2(
    spec: PeriodicMetricSpecV2,
) -> ApprovedGovernedQueryToolBindingV2:
    tool = ToolContractV2(
        identity=ToolIdentityV2(
            name=spec.tool_name,
            version="dataset_v2",
            purpose=spec.purpose,
        ),
        input_schema_name="GovernedInvestigationInputV2",
        output_schema_name="GovernedFinalizationResult",
        required_permissions=(
            "metric_access",
            "data_scope",
        ),
        execution_policy_reference=(
            "governed_execution_policy_v2"
        ),
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


def _metric_question_v2(
    *,
    spec: PeriodicMetricSpecV2,
    window: TimeWindowReferenceV2,
) -> str:
    """
    question 只保留可读审计语义。

    真正执行边界由 plan_name + structured analysis_window 决定，
    不允许再次依赖自然语言解析时间。
    """

    start = window.start_date
    end = window.end_date

    if start == end:
        window_text = f"{start:%Y年%m月%d日}"
    else:
        window_text = (
            f"{start:%Y年%m月%d日}"
            f"至{end:%Y年%m月%d日}"
        )

    return f"{window_text}{spec.chinese_name}是多少？"


def project_metric_comparison_v2(
    *,
    spec: PeriodicMetricSpecV2,
    comparison_result: MetricComparisonResultV2,
) -> PeriodicMetricSnapshotV2:
    """
    Trusted MetricComparisonResult -> Periodic Metric Snapshot。
    """

    if comparison_result.metric_name != spec.metric_name:
        raise ValueError(
            "Periodic metric projection metric mismatch："
            f"spec={spec.metric_name}; "
            f"actual={comparison_result.metric_name}"
        )

    pp_change = None

    if spec.display_kind == PeriodicMetricDisplayKindV2.RATIO:
        pp_change = (
            comparison_result.absolute_change
            * Decimal("100")
        )

    return PeriodicMetricSnapshotV2(
        spec=spec,
        status=PeriodicMetricStatusV2.READY,
        message="当前/参考窗口可信比较已形成。",
        current_value=comparison_result.current_value,
        reference_value=comparison_result.reference_value,
        absolute_change=comparison_result.absolute_change,
        relative_change=comparison_result.relative_change,
        percentage_point_change=pp_change,
        current_evidence_id=(
            comparison_result.current_evidence_id
        ),
        reference_evidence_id=(
            comparison_result.reference_evidence_id
        ),
    )


def _metric_not_ready_v2(
    *,
    spec: PeriodicMetricSpecV2,
    message: str,
) -> PeriodicMetricSnapshotV2:
    return PeriodicMetricSnapshotV2(
        spec=spec,
        status=PeriodicMetricStatusV2.NOT_READY,
        message=message,
    )


def _run_single_metric_v2(
    *,
    spec: PeriodicMetricSpecV2,
    comparison: TimeComparisonContractV2,
    runtime_config: GovernanceRuntimeConfig,
    execution_policy: GovernedExecutionPolicy | None,
) -> PeriodicMetricSnapshotV2:
    binding = _tool_binding_v2(spec)

    base_request_id = (
        "day93-periodic-business-"
        f"{spec.metric_name}-{uuid4().hex}"
    )

    current_id = f"{base_request_id}-current"
    current_result = invoke_governed_plan_delivery_v2(
        context=build_day89_local_access_context_v2(
            request_id=current_id
        ),
        plan_name=spec.plan_name,
        analysis_window=comparison.current_window,
        question=_metric_question_v2(
            spec=spec,
            window=comparison.current_window,
        ),
        runtime_config=runtime_config,
        approved_tool_binding=binding,
        execution_policy=execution_policy,
        event_id=current_id,
    )

    reference_id = f"{base_request_id}-reference"
    reference_result = invoke_governed_plan_delivery_v2(
        context=build_day89_local_access_context_v2(
            request_id=reference_id
        ),
        plan_name=spec.plan_name,
        analysis_window=comparison.reference_window,
        question=_metric_question_v2(
            spec=spec,
            window=comparison.reference_window,
        ),
        runtime_config=runtime_config,
        approved_tool_binding=binding,
        execution_policy=execution_policy,
        event_id=reference_id,
    )

    comparison_delivery = build_runtime_comparison_delivery_v2(
        current_result=current_result,
        reference_result=reference_result,
        comparison=comparison,
        request_subject=(
            f"周期经营报表｜{spec.chinese_name}"
        ),
    )

    if (
        comparison_delivery.status
        != RuntimeComparisonDeliveryStatusV2.READY
        or comparison_delivery.metric_comparison_result is None
    ):
        return _metric_not_ready_v2(
            spec=spec,
            message=(
                "该指标未形成可释放周期比较："
                f"{comparison_delivery.message}"
            ),
        )

    return project_metric_comparison_v2(
        spec=spec,
        comparison_result=(
            comparison_delivery.metric_comparison_result
        ),
    )


def _project_r12_ready_metric_v2(
    *,
    spec: PeriodicMetricSpecV2,
    source,
) -> PeriodicMetricSnapshotV2:
    if source.metric_name != spec.metric_name:
        raise ValueError(
            "R12 Periodic projection metric mismatch："
            f"spec={spec.metric_name}; "
            f"actual={source.metric_name}"
        )

    if source.status != R12MetricRuntimeStatusV2.READY:
        return _metric_not_ready_v2(
            spec=spec,
            message=source.message,
        )

    if (
        source.current_value is None
        or source.reference_value is None
        or source.absolute_change is None
        or source.current_evidence_id is None
        or source.reference_evidence_id is None
    ):
        raise ValueError(
            f"READY R12 Metric 缺少可信字段：{source.metric_name}"
        )

    pp_change = None
    if spec.display_kind == PeriodicMetricDisplayKindV2.RATIO:
        pp_change = source.absolute_change * Decimal("100")

    return PeriodicMetricSnapshotV2(
        spec=spec,
        status=PeriodicMetricStatusV2.READY,
        message=source.message,
        current_value=source.current_value,
        reference_value=source.reference_value,
        absolute_change=source.absolute_change,
        relative_change=source.relative_change,
        percentage_point_change=pp_change,
        current_evidence_id=source.current_evidence_id,
        reference_evidence_id=source.reference_evidence_id,
    )


def project_r12_customer_health_v2(
    *,
    r12_runtime: R12CohortPeriodicRuntimeV2,
    cadence: PeriodicReportCadenceV2,
    anchor_date: date,
    comparison: TimeComparisonContractV2,
) -> tuple[
    tuple[PeriodicMetricSnapshotV2, ...],
    PeriodicR12CustomerHealthV2,
]:
    """
    已通过 B5B-2 的 R12 Runtime -> Periodic Report projection。

    这里不重新执行 SQL、不重新计算 R12 Base。
    只验证两个 Runtime 使用完全相同的 cadence / anchor / comparison，
    然后把可信结果投影进统一 KPI contract。
    """

    if r12_runtime.cadence != cadence:
        raise ValueError(
            "R12 Runtime cadence 与 Periodic Report 不一致。"
        )

    if r12_runtime.anchor_date != anchor_date:
        raise ValueError(
            "R12 Runtime anchor_date 与 Periodic Report 不一致。"
        )

    if r12_runtime.comparison != comparison:
        raise ValueError(
            "R12 Runtime TimeComparisonContract 与 "
            "Periodic Report 不一致。"
        )

    source_by_name = {
        item.metric_name: item
        for item in r12_runtime.metrics
    }

    if r12_runtime.metrics:
        expected_names = {
            spec.metric_name
            for spec in PERIODIC_R12_METRIC_SPECS_V2
        }

        if set(source_by_name) != expected_names:
            raise ValueError(
                "R12 Runtime 没有覆盖完整、唯一的 5 Metric family。"
            )

        snapshots = tuple(
            _project_r12_ready_metric_v2(
                spec=spec,
                source=source_by_name[spec.metric_name],
            )
            for spec in PERIODIC_R12_METRIC_SPECS_V2
        )
    else:
        # Readiness preflight NOT_READY 时 R12 Runtime 保证 0 SQL / 0 metrics。
        # Periodic Report 仍需要显式投影 5 个 NOT_READY slots，
        # 防止 UI 把“不可计算”误认为“指标不存在”。
        readiness_message = (
            "R12 Customer Health 当前不可计算："
            f"current={r12_runtime.current_readiness.status.value}; "
            f"reference={r12_runtime.reference_readiness.status.value}; "
            f"{r12_runtime.message}"
        )

        snapshots = tuple(
            _metric_not_ready_v2(
                spec=spec,
                message=readiness_message,
            )
            for spec in PERIODIC_R12_METRIC_SPECS_V2
        )

    ready_count = sum(
        item.status == PeriodicMetricStatusV2.READY
        for item in snapshots
    )
    failed_count = len(snapshots) - ready_count

    trust = PeriodicR12CustomerHealthV2(
        status=r12_runtime.status,
        message=r12_runtime.message,
        current_readiness=r12_runtime.current_readiness,
        reference_readiness=r12_runtime.reference_readiness,
        ready_metric_count=ready_count,
        failed_metric_count=failed_count,
        reconciliations=r12_runtime.reconciliations,
    )

    return snapshots, trust


def _snapshot_lookup_v2(
    metrics: tuple[PeriodicMetricSnapshotV2, ...],
) -> dict[str, PeriodicMetricSnapshotV2]:
    return {
        item.spec.metric_name: item
        for item in metrics
    }


def _money_reconciliation_v2(
    *,
    relationship: str,
    observed: PeriodicMetricSnapshotV2 | None,
    left: PeriodicMetricSnapshotV2 | None,
    right: PeriodicMetricSnapshotV2 | None,
) -> PeriodicDriverReconciliationV2:
    candidates = (observed, left, right)

    if (
        any(item is None for item in candidates)
        or any(
            item.status != PeriodicMetricStatusV2.READY
            for item in candidates
            if item is not None
        )
    ):
        return PeriodicDriverReconciliationV2(
            relationship=relationship,
            status=(
                PeriodicDriverReconciliationStatusV2
                .NOT_AVAILABLE
            ),
            message="驱动关系所需指标未全部 READY，暂不计算。",
        )

    assert observed is not None
    assert left is not None
    assert right is not None
    assert observed.current_value is not None
    assert left.current_value is not None
    assert right.current_value is not None

    reconstructed = (
        left.current_value
        * right.current_value
    )
    remainder = (
        observed.current_value
        - reconstructed
    )

    status = (
        PeriodicDriverReconciliationStatusV2.RECONCILED
        if abs(remainder)
        <= DRIVER_RECONCILIATION_MONEY_TOLERANCE
        else PeriodicDriverReconciliationStatusV2.NOT_RECONCILED
    )

    return PeriodicDriverReconciliationV2(
        relationship=relationship,
        status=status,
        observed_value=observed.current_value,
        reconstructed_value=reconstructed,
        remainder=remainder,
        message=(
            "驱动关系已在 current window 使用可信指标做确定性核对。"
        ),
    )


def build_driver_reconciliations_v2(
    metrics: tuple[PeriodicMetricSnapshotV2, ...],
) -> tuple[PeriodicDriverReconciliationV2, ...]:
    lookup = _snapshot_lookup_v2(metrics)

    return (
        _money_reconciliation_v2(
            relationship=(
                "GMV = Buyer Count × Spending"
            ),
            observed=lookup.get("gmv"),
            left=lookup.get("buyer_count"),
            right=lookup.get("spending_per_buyer"),
        ),
        _money_reconciliation_v2(
            relationship=(
                "Spending = AUS × FREQ"
            ),
            observed=lookup.get("spending_per_buyer"),
            left=lookup.get("aus"),
            right=lookup.get("purchase_frequency"),
        ),
    )



def _run_periodic_metrics_bounded_v2(
    *,
    comparison: TimeComparisonContractV2,
    runtime_config: GovernanceRuntimeConfig,
    execution_policy: GovernedExecutionPolicy | None,
    max_workers: int = PERIODIC_METRIC_MAX_WORKERS,
) -> tuple[PeriodicMetricSnapshotV2, ...]:
    """
    以 Metric 为并发粒度执行 Periodic Registry。

    安全/确定性约束：
    - 单个 Metric 内仍由 _run_single_metric_v2 串行执行
      Current -> Reference -> Comparison；
    - 最多同时运行 max_workers 个 Metric；
    - Runtime / DB / Audit 仍走既有 Governed Query 边界；
    - 最终返回顺序严格保持 PERIODIC_METRIC_REGISTRY_V2 顺序，
      不受线程完成先后影响；
    - worker 的程序级异常不吞掉，继续 fail loud，
      防止把实现 bug 伪装成业务 PARTIAL_READY。
    """

    if max_workers < 1:
        raise ValueError("max_workers 必须 >= 1。")

    futures: list[
        tuple[
            PeriodicMetricSpecV2,
            Future[PeriodicMetricSnapshotV2],
        ]
    ] = []

    with ThreadPoolExecutor(
        max_workers=max_workers,
        thread_name_prefix="periodic-metric",
    ) as executor:
        for spec in PERIODIC_METRIC_REGISTRY_V2:
            future = executor.submit(
                _run_single_metric_v2,
                spec=spec,
                comparison=comparison,
                runtime_config=runtime_config,
                execution_policy=execution_policy,
            )
            futures.append((spec, future))

        ordered_snapshots: list[
            PeriodicMetricSnapshotV2
        ] = []

        # 按 Registry 提交顺序读取结果。
        # 即使后面的 Future 更早完成，交付顺序仍保持 deterministic。
        for spec, future in futures:
            snapshot = future.result()

            if snapshot.spec.metric_name != spec.metric_name:
                raise ValueError(
                    "Periodic concurrent execution metric mismatch："
                    f"expected={spec.metric_name}; "
                    f"actual={snapshot.spec.metric_name}"
                )

            ordered_snapshots.append(snapshot)

    return tuple(ordered_snapshots)

def assemble_periodic_business_report_v2(
    *,
    cadence: PeriodicReportCadenceV2,
    anchor_date: date,
    comparison: TimeComparisonContractV2,
    metrics: tuple[PeriodicMetricSnapshotV2, ...],
    r12_customer_health: (
        PeriodicR12CustomerHealthV2 | None
    ) = None,
) -> PeriodicBusinessReportV2:
    """
    多个 metric-level 安全结果 -> Report-level readiness。
    """

    ready_count = sum(
        item.status == PeriodicMetricStatusV2.READY
        for item in metrics
    )
    failed_count = len(metrics) - ready_count

    required_failed = tuple(
        item.spec.metric_name
        for item in metrics
        if (
            item.spec.required
            and item.status != PeriodicMetricStatusV2.READY
        )
    )

    if required_failed:
        status = PeriodicBusinessReportStatusV2.NOT_READY
        message = (
            "周期经营报表核心指标未全部形成可信交付；"
            "不会把可选指标拼成伪完整报表。"
        )
    elif failed_count:
        status = PeriodicBusinessReportStatusV2.PARTIAL_READY
        message = (
            "周期经营报表核心指标已形成；"
            "部分扩展指标未就绪，报表以 PARTIAL_READY 交付。"
        )
    else:
        status = PeriodicBusinessReportStatusV2.READY
        message = "周期经营报表全部已注册指标形成可信交付。"

    return PeriodicBusinessReportV2(
        status=status,
        message=message,
        cadence=cadence,
        anchor_date=anchor_date,
        comparison=comparison,
        metrics=metrics,
        ready_metric_count=ready_count,
        failed_metric_count=failed_count,
        required_failed_metric_names=required_failed,
        driver_reconciliations=(
            build_driver_reconciliations_v2(metrics)
        ),
        r12_customer_health=r12_customer_health,
    )


def run_day93_periodic_business_report_v2(
    *,
    cadence: PeriodicReportCadenceV2,
    anchor_date: date,
    runtime_config: GovernanceRuntimeConfig | None = None,
    execution_policy: GovernedExecutionPolicy | None = None,
) -> PeriodicBusinessReportV2:
    """
    Day93 B5A Multi-KPI Periodic Business Report Runtime。

    B5A PERF 使用 Metric-level bounded concurrency：
    - 最多 4 个 Metric 并发；
    - 单 Metric 内 current/reference 仍串行；
    - 最终交付顺序保持 Registry deterministic order；
    - 不绕过既有 Governance / Audit / Evidence。
    """

    validate_periodic_metric_registry_v2()

    active_config = (
        runtime_config
        if runtime_config is not None
        else load_governance_runtime_config()
    )

    # 现有函数名仍带 gmv，但它实际负责 cadence -> TimeComparisonContract。
    # 当前步骤复用它以降低已有 Periodic Runtime 回归风险；
    # 后续可以单独做命名清理，不在 B5A 核心验证阶段混入重构。
    comparison = build_periodic_gmv_comparison_v2(
        cadence=cadence,
        anchor_date=anchor_date,
    )

    snapshots = _run_periodic_metrics_bounded_v2(
        comparison=comparison,
        runtime_config=active_config,
        execution_policy=execution_policy,
    )

    # B5B-3A correctness-first integration：
    # R12 branch 保留自己已经验证过的 Readiness / Governance /
    # Result Protection / Reconciliation，不复用普通 Metric executor。
    # 当前先串行整合，性能优化不与合同整合混在同一修改中。
    r12_runtime = run_r12_cohort_periodic_runtime_v2(
        cadence=cadence,
        anchor_date=anchor_date,
        runtime_config=active_config,
        execution_policy=execution_policy,
    )

    (
        r12_snapshots,
        r12_customer_health,
    ) = project_r12_customer_health_v2(
        r12_runtime=r12_runtime,
        cadence=cadence,
        anchor_date=anchor_date,
        comparison=comparison,
    )

    all_snapshots = (
        *snapshots,
        *r12_snapshots,
    )

    return assemble_periodic_business_report_v2(
        cadence=cadence,
        anchor_date=anchor_date,
        comparison=comparison,
        metrics=all_snapshots,
        r12_customer_health=r12_customer_health,
    )
