from __future__ import annotations

import calendar
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, model_validator
from sqlalchemy.engine import Engine

from app.agents.investigation_contracts_v2 import (
    ToolContractV2,
    ToolFailureCodeV2,
    ToolIdentityV2,
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
from app.db.beauty_bi_v2.manifest_loader import (
    load_and_validate_day66_manifest,
    parse_manifest_date,
)
from app.governance.execution_policy import GovernedExecutionPolicy
from app.governance.governance_runtime import (
    GovernanceRuntimeConfig,
    load_governance_runtime_config,
)
from app.semantic_layer.time_comparison_contract_v2 import (
    TimeComparisonContractV2,
    TimeWindowReferenceV2,
)


R12_COHORT_RUNTIME_VERSION = "r12_cohort_runtime_v2_0"
R12_MONTHS = 12
RATE_TOLERANCE = Decimal("0.0000000001")
MONEY_TOLERANCE = Decimal("0.01")


class R12RuntimeReadinessStatusV2(str, Enum):
    READY = "ready"
    INSUFFICIENT_HISTORY = "insufficient_history"
    OUTSIDE_BUSINESS_WINDOW = "outside_business_window"
    REFUND_OBSERVATION_INCOMPLETE = "refund_observation_incomplete"
    INVALID_DATASET_CONTRACT = "invalid_dataset_contract"


class R12CohortRuntimeStatusV2(str, Enum):
    READY = "ready"
    PARTIAL_READY = "partial_ready"
    NOT_READY = "not_ready"


class R12MetricRuntimeStatusV2(str, Enum):
    READY = "ready"
    NOT_READY = "not_ready"


class R12ReconciliationStatusV2(str, Enum):
    RECONCILED = "reconciled"
    NOT_RECONCILED = "not_reconciled"
    NOT_AVAILABLE = "not_available"


class R12RuntimeReadinessV2(BaseModel):
    """
    一个 Report Window 是否可以安全计算 R12 Effective Purchase。

    这里检查的是 Dataset 可观测性，不替代 Query Plan / Governance：
    - Base 是否拥有完整前 12 个日历月历史；
    - Report Window 是否仍在业务事实期内；
    - 从报表期最后一笔支付开始，最坏情况下的履约 + 退款申请
      + 退款处理是否已经完全落入 event observation window。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    status: R12RuntimeReadinessStatusV2
    ready: bool
    message: str

    report_window: TimeWindowReferenceV2
    base_window: TimeWindowReferenceV2

    dataset_business_start_date: date
    dataset_business_end_date: date
    event_observation_end_date: date

    maximum_observation_delay_seconds: int
    latest_required_observation_ts: datetime
    available_observation_end_ts: datetime

    @model_validator(mode="after")
    def validate_readiness(self) -> "R12RuntimeReadinessV2":
        if not self.message.strip():
            raise ValueError("R12 Runtime Readiness message 不能为空。")

        if self.ready != (
            self.status == R12RuntimeReadinessStatusV2.READY
        ):
            raise ValueError("ready 与 readiness status 不一致。")

        if (
            self.base_window.end_date
            >= self.report_window.start_date
        ):
            raise ValueError("R12 Base 与 Report Window 不得重叠。")

        if self.maximum_observation_delay_seconds < 0:
            raise ValueError(
                "maximum_observation_delay_seconds 不得为负。"
            )

        return self


class R12MetricRuntimeSnapshotV2(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    metric_name: str
    status: R12MetricRuntimeStatusV2
    message: str

    current_value: Decimal | None = None
    reference_value: Decimal | None = None
    absolute_change: Decimal | None = None
    relative_change: Decimal | None = None

    current_evidence_id: str | None = None
    reference_evidence_id: str | None = None

    @model_validator(mode="after")
    def validate_snapshot(self) -> "R12MetricRuntimeSnapshotV2":
        if not self.message.strip():
            raise ValueError("R12 Metric message 不能为空。")

        trusted = (
            self.current_value,
            self.reference_value,
            self.absolute_change,
            self.current_evidence_id,
            self.reference_evidence_id,
        )

        if self.status == R12MetricRuntimeStatusV2.READY:
            if any(value is None for value in trusted):
                raise ValueError(
                    "READY R12 Metric 缺少可信比较字段。"
                )
        else:
            if any(value is not None for value in trusted):
                raise ValueError(
                    "NOT_READY R12 Metric 不得释放可信数值。"
                )
            if self.relative_change is not None:
                raise ValueError(
                    "NOT_READY R12 Metric 不得释放 relative_change。"
                )

        return self


class R12ReconciliationV2(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    relationship: str
    status: R12ReconciliationStatusV2
    remainder: Decimal | None = None
    message: str

    @model_validator(mode="after")
    def validate_reconciliation(self) -> "R12ReconciliationV2":
        if not self.relationship.strip() or not self.message.strip():
            raise ValueError(
                "R12 reconciliation 文本字段不能为空。"
            )

        if (
            self.status
            == R12ReconciliationStatusV2.NOT_AVAILABLE
        ):
            if self.remainder is not None:
                raise ValueError(
                    "NOT_AVAILABLE reconciliation 不得释放 remainder。"
                )
        elif self.remainder is None:
            raise ValueError(
                "可验证 reconciliation 必须包含 remainder。"
            )

        return self


class R12CohortPeriodicRuntimeV2(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    contract_version: str = R12_COHORT_RUNTIME_VERSION
    status: R12CohortRuntimeStatusV2
    message: str

    cadence: PeriodicReportCadenceV2
    anchor_date: date
    comparison: TimeComparisonContractV2

    current_readiness: R12RuntimeReadinessV2
    reference_readiness: R12RuntimeReadinessV2

    metrics: tuple[R12MetricRuntimeSnapshotV2, ...] = ()
    reconciliations: tuple[R12ReconciliationV2, ...] = ()

    @model_validator(mode="after")
    def validate_runtime(self) -> "R12CohortPeriodicRuntimeV2":
        if not self.message.strip():
            raise ValueError("R12 Cohort Runtime message 不能为空。")

        readiness_ok = (
            self.current_readiness.ready
            and self.reference_readiness.ready
        )

        if self.status == R12CohortRuntimeStatusV2.NOT_READY:
            if readiness_ok and self.metrics:
                # 执行阶段失败可以是 PARTIAL_READY，不应伪装成 preflight NOT_READY。
                raise ValueError(
                    "Readiness 已通过且存在 Metric 时不得标记 NOT_READY。"
                )
            if self.metrics:
                raise ValueError(
                    "Preflight NOT_READY 不得执行或释放 Metric 结果。"
                )
        else:
            if not readiness_ok:
                raise ValueError(
                    "READY/PARTIAL_READY 必须通过 current/reference readiness。"
                )
            if len(self.metrics) != 5:
                raise ValueError(
                    "R12 Runtime 执行阶段必须覆盖完整 5 Metric family。"
                )

            ready_count = sum(
                item.status == R12MetricRuntimeStatusV2.READY
                for item in self.metrics
            )

            if self.status == R12CohortRuntimeStatusV2.READY:
                if ready_count != 5:
                    raise ValueError(
                        "READY R12 Runtime 必须 5/5 Metric READY。"
                    )
            elif ready_count in {0, 5}:
                raise ValueError(
                    "PARTIAL_READY 必须同时包含 READY 与 NOT_READY Metric。"
                )

        return self


class R12MetricSpecV2(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    metric_name: str
    plan_name: str
    chinese_name: str
    tool_name: str


R12_METRIC_REGISTRY_V2: tuple[R12MetricSpecV2, ...] = (
    R12MetricSpecV2(
        metric_name="r12_base_customer_count",
        plan_name="r12_base_customer_count_overall_v2",
        chinese_name="R12 Base客户数",
        tool_name="governed_r12_base_customer_count_query",
    ),
    R12MetricSpecV2(
        metric_name="r12_repurchase_customer_count",
        plan_name="r12_repurchase_customer_count_overall_v2",
        chinese_name="R12回购客户数",
        tool_name="governed_r12_repurchase_customer_count_query",
    ),
    R12MetricSpecV2(
        metric_name="r12_repurchase_rate",
        plan_name="r12_repurchase_rate_overall_v2",
        chinese_name="R12回购率",
        tool_name="governed_r12_repurchase_rate_query",
    ),
    R12MetricSpecV2(
        metric_name="r12_repurchase_amount",
        plan_name="r12_repurchase_amount_overall_v2",
        chinese_name="R12回购有效消费金额",
        tool_name="governed_r12_repurchase_amount_query",
    ),
    R12MetricSpecV2(
        metric_name="r12_repurchase_spending",
        plan_name="r12_repurchase_spending_overall_v2",
        chinese_name="R12回购客人均有效消费",
        tool_name="governed_r12_repurchase_spending_query",
    ),
)


def _shift_months(value: date, months: int) -> date:
    zero_based = value.month - 1 + months
    year = value.year + zero_based // 12
    month = zero_based % 12 + 1
    day = min(
        value.day,
        calendar.monthrange(year, month)[1],
    )
    return date(year, month, day)


def _base_window(report_window: TimeWindowReferenceV2) -> TimeWindowReferenceV2:
    return TimeWindowReferenceV2(
        start_date=_shift_months(
            report_window.start_date,
            -R12_MONTHS,
        ),
        end_date=(
            report_window.start_date
            - timedelta(days=1)
        ),
    )


def _maximum_observation_delay(manifest: dict) -> timedelta:
    fulfillment = manifest["fulfillment_generation"]
    refund = manifest["refund_generation"]

    shipping_hours = int(
        fulfillment["shipping_delay_hours"]["maximum"]
    )
    delivery_days = int(
        fulfillment["delivery_delay_days"]["maximum"]
    )

    remote = fulfillment["remote_region_extra_delay_days"]
    remote_days = (
        int(remote["maximum"])
        if bool(remote["enabled"])
        else 0
    )

    congestion = fulfillment["campaign_congestion"]
    congestion_days = (
        int(congestion["extra_delay_days"]["maximum"])
        if bool(congestion["enabled"])
        else 0
    )

    refund_request_days = int(
        refund["request_delay_days"]["maximum"]
    )
    refund_resolution_hours = int(
        refund["resolution"]["delay_hours"]["maximum"]
    )

    return timedelta(
        days=(
            delivery_days
            + remote_days
            + congestion_days
            + refund_request_days
        ),
        hours=(
            shipping_hours
            + refund_resolution_hours
        ),
    )


def build_r12_runtime_readiness_v2(
    *,
    report_window: TimeWindowReferenceV2,
    manifest: dict | None = None,
) -> R12RuntimeReadinessV2:
    active_manifest = (
        manifest
        if manifest is not None
        else load_and_validate_day66_manifest()
    )

    generation = active_manifest["generation"]

    business_start = parse_manifest_date(
        generation["business_start_date"],
        "generation.business_start_date",
    )
    business_end = parse_manifest_date(
        generation["business_end_date"],
        "generation.business_end_date",
    )
    observation_end = parse_manifest_date(
        generation["event_observation_end_date"],
        "generation.event_observation_end_date",
    )

    base = _base_window(report_window)
    max_delay = _maximum_observation_delay(active_manifest)

    latest_report_ts = datetime.combine(
        report_window.end_date,
        time(23, 59, 59),
    )
    required_observation_ts = latest_report_ts + max_delay
    available_observation_ts = datetime.combine(
        observation_end,
        time(23, 59, 59),
    )

    activity = active_manifest.get("activity_segmentation", {})
    observation_required = activity.get(
        "require_refund_observation_window"
    )

    if observation_required is not True:
        status = R12RuntimeReadinessStatusV2.INVALID_DATASET_CONTRACT
        message = (
            "Dataset 未冻结 require_refund_observation_window=true，"
            "不能安全形成 R12 Effective Purchase。"
        )
    elif base.start_date < business_start:
        status = R12RuntimeReadinessStatusV2.INSUFFICIENT_HISTORY
        message = (
            "R12 Base 所需历史早于 Dataset business_start_date；"
            "禁止使用部分历史冒充完整 R12。"
        )
    elif (
        report_window.start_date < business_start
        or report_window.end_date > business_end
    ):
        status = R12RuntimeReadinessStatusV2.OUTSIDE_BUSINESS_WINDOW
        message = (
            "Report Window 超出 Dataset 正式 business window。"
        )
    elif required_observation_ts > available_observation_ts:
        status = (
            R12RuntimeReadinessStatusV2
            .REFUND_OBSERVATION_INCOMPLETE
        )
        message = (
            "Report Window 的最坏履约/退款生命周期尚未完全落入 "
            "event observation window；不能把尚未可观察退款视为零退款。"
        )
    else:
        status = R12RuntimeReadinessStatusV2.READY
        message = (
            "完整 R12 历史与退款观察窗口均满足，"
            "可以进入 Governed R12 Query Runtime。"
        )

    return R12RuntimeReadinessV2(
        status=status,
        ready=(status == R12RuntimeReadinessStatusV2.READY),
        message=message,
        report_window=report_window,
        base_window=base,
        dataset_business_start_date=business_start,
        dataset_business_end_date=business_end,
        event_observation_end_date=observation_end,
        maximum_observation_delay_seconds=int(
            max_delay.total_seconds()
        ),
        latest_required_observation_ts=required_observation_ts,
        available_observation_end_ts=available_observation_ts,
    )


def _tool_binding(spec: R12MetricSpecV2) -> ApprovedGovernedQueryToolBindingV2:
    tool = ToolContractV2(
        identity=ToolIdentityV2(
            name=spec.tool_name,
            version="dataset_v2",
            purpose=(
                f"查询授权范围内的{spec.chinese_name}，"
                "用于 R12 Cohort Customer Health。"
            ),
        ),
        input_schema_name="GovernedInvestigationInputV2",
        output_schema_name="GovernedFinalizationResult",
        required_permissions=(
            "metric_access",
            "data_scope",
        ),
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


def _question(
    *,
    spec: R12MetricSpecV2,
    window: TimeWindowReferenceV2,
) -> str:
    return (
        f"{window.start_date:%Y年%m月%d日}"
        f"至{window.end_date:%Y年%m月%d日}"
        f"{spec.chinese_name}是多少？"
    )


def _run_metric(
    *,
    spec: R12MetricSpecV2,
    comparison: TimeComparisonContractV2,
    runtime_config: GovernanceRuntimeConfig,
    execution_policy: GovernedExecutionPolicy | None,
    engine_override: Engine | None,
) -> R12MetricRuntimeSnapshotV2:
    binding = _tool_binding(spec)
    base_id = f"day93-b5b2-{spec.metric_name}-{uuid4().hex}"

    current_id = f"{base_id}-current"
    current = invoke_governed_plan_delivery_v2(
        context=build_day89_local_access_context_v2(
            request_id=current_id,
            allow_aggregated_business_metrics=True,
        ),
        plan_name=spec.plan_name,
        analysis_window=comparison.current_window,
        question=_question(
            spec=spec,
            window=comparison.current_window,
        ),
        runtime_config=runtime_config,
        approved_tool_binding=binding,
        execution_policy=execution_policy,
        engine_override=engine_override,
        event_id=current_id,
    )

    reference_id = f"{base_id}-reference"
    reference = invoke_governed_plan_delivery_v2(
        context=build_day89_local_access_context_v2(
            request_id=reference_id,
            allow_aggregated_business_metrics=True,
        ),
        plan_name=spec.plan_name,
        analysis_window=comparison.reference_window,
        question=_question(
            spec=spec,
            window=comparison.reference_window,
        ),
        runtime_config=runtime_config,
        approved_tool_binding=binding,
        execution_policy=execution_policy,
        engine_override=engine_override,
        event_id=reference_id,
    )

    delivery = build_runtime_comparison_delivery_v2(
        current_result=current,
        reference_result=reference,
        comparison=comparison,
        request_subject=f"R12 Cohort｜{spec.chinese_name}",
    )

    if (
        delivery.status
        != RuntimeComparisonDeliveryStatusV2.READY
        or delivery.metric_comparison_result is None
    ):
        return R12MetricRuntimeSnapshotV2(
            metric_name=spec.metric_name,
            status=R12MetricRuntimeStatusV2.NOT_READY,
            message=(
                "R12 Metric 未形成可释放 current/reference 比较："
                f"{delivery.message}"
            ),
        )

    result = delivery.metric_comparison_result

    if result.metric_name != spec.metric_name:
        raise ValueError(
            "R12 Runtime metric mismatch："
            f"expected={spec.metric_name}; "
            f"actual={result.metric_name}"
        )

    return R12MetricRuntimeSnapshotV2(
        metric_name=spec.metric_name,
        status=R12MetricRuntimeStatusV2.READY,
        message="R12 current/reference Governed Evidence 已形成。",
        current_value=result.current_value,
        reference_value=result.reference_value,
        absolute_change=result.absolute_change,
        relative_change=result.relative_change,
        current_evidence_id=result.current_evidence_id,
        reference_evidence_id=result.reference_evidence_id,
    )


def _lookup(
    metrics: tuple[R12MetricRuntimeSnapshotV2, ...],
) -> dict[str, R12MetricRuntimeSnapshotV2]:
    return {
        item.metric_name: item
        for item in metrics
    }


def _reconcile_one_window(
    *,
    label: str,
    lookup: dict[str, R12MetricRuntimeSnapshotV2],
    value_field: str,
) -> tuple[R12ReconciliationV2, ...]:
    """
    每条 identity 只依赖自己真正需要的 Metric。

    这样 Amount / Spending 被 Result Protection 拦截时，
    已经可信的 Count / Rate 仍然可以独立完成 reconciliation。
    """

    base = lookup["r12_base_customer_count"]
    repurchase = lookup["r12_repurchase_customer_count"]
    rate = lookup["r12_repurchase_rate"]
    amount = lookup["r12_repurchase_amount"]
    spending = lookup["r12_repurchase_spending"]

    def ready_value(
        item: R12MetricRuntimeSnapshotV2,
    ) -> Decimal | None:
        if item.status != R12MetricRuntimeStatusV2.READY:
            return None
        value = getattr(item, value_field)
        if value is None:
            raise ValueError("READY R12 Metric 出现空值。")
        return value

    base_value = ready_value(base)
    repurchase_value = ready_value(repurchase)
    rate_value = ready_value(rate)
    amount_value = ready_value(amount)
    spending_value = ready_value(spending)

    # 1) Repurchase Count 必须是 Base 的子集。
    if base_value is None or repurchase_value is None:
        count_reconciliation = R12ReconciliationV2(
            relationship=(
                f"{label}: repurchase_customer_count <= base_customer_count"
            ),
            status=R12ReconciliationStatusV2.NOT_AVAILABLE,
            message="Base / Repurchase Count 未全部 READY。",
        )
    else:
        count_remainder = base_value - repurchase_value
        count_reconciliation = R12ReconciliationV2(
            relationship=(
                f"{label}: repurchase_customer_count <= base_customer_count"
            ),
            status=(
                R12ReconciliationStatusV2.RECONCILED
                if count_remainder >= 0
                else R12ReconciliationStatusV2.NOT_RECONCILED
            ),
            remainder=count_remainder,
            message="回购客户必须是对应 R12 Base 的子集。",
        )

    # 2) Rate identity 只依赖 Base / Repurchase Count / Rate。
    if (
        base_value is None
        or repurchase_value is None
        or rate_value is None
    ):
        rate_reconciliation = R12ReconciliationV2(
            relationship=(
                f"{label}: repurchase_rate = "
                "repurchase_count / base_count"
            ),
            status=R12ReconciliationStatusV2.NOT_AVAILABLE,
            message="Count / Rate 所需指标未全部 READY。",
        )
    elif base_value == 0:
        rate_reconciliation = R12ReconciliationV2(
            relationship=(
                f"{label}: repurchase_rate = "
                "repurchase_count / base_count"
            ),
            status=R12ReconciliationStatusV2.NOT_AVAILABLE,
            message="R12 Base 为 0，rate identity 不可计算。",
        )
    else:
        expected_rate = repurchase_value / base_value
        rate_remainder = rate_value - expected_rate
        rate_reconciliation = R12ReconciliationV2(
            relationship=(
                f"{label}: repurchase_rate = "
                "repurchase_count / base_count"
            ),
            status=(
                R12ReconciliationStatusV2.RECONCILED
                if abs(rate_remainder) <= RATE_TOLERANCE
                else R12ReconciliationStatusV2.NOT_RECONCILED
            ),
            remainder=rate_remainder,
            message="使用可信 Count / Rate 做确定性核对。",
        )

    # 3) Amount / Spending identity 只依赖回购人数、金额、人均金额。
    if (
        repurchase_value is None
        or amount_value is None
        or spending_value is None
    ):
        spending_reconciliation = R12ReconciliationV2(
            relationship=(
                f"{label}: repurchase_amount = "
                "repurchase_spending × repurchase_count"
            ),
            status=R12ReconciliationStatusV2.NOT_AVAILABLE,
            message="Amount / Spending 所需指标未全部 READY。",
        )
    elif repurchase_value == 0:
        spending_reconciliation = R12ReconciliationV2(
            relationship=(
                f"{label}: repurchase_amount = "
                "repurchase_spending × repurchase_count"
            ),
            status=R12ReconciliationStatusV2.NOT_AVAILABLE,
            message=(
                "R12 Repurchase Customer 为 0，"
                "Spending identity 不可计算。"
            ),
        )
    else:
        reconstructed_amount = (
            spending_value * repurchase_value
        )
        money_remainder = (
            amount_value - reconstructed_amount
        )
        spending_reconciliation = R12ReconciliationV2(
            relationship=(
                f"{label}: repurchase_amount = "
                "repurchase_spending × repurchase_count"
            ),
            status=(
                R12ReconciliationStatusV2.RECONCILED
                if abs(money_remainder) <= MONEY_TOLERANCE
                else R12ReconciliationStatusV2.NOT_RECONCILED
            ),
            remainder=money_remainder,
            message="使用可信 Amount / Spending / Count 做金额核对。",
        )

    return (
        count_reconciliation,
        rate_reconciliation,
        spending_reconciliation,
    )


def build_r12_reconciliations_v2(
    metrics: tuple[R12MetricRuntimeSnapshotV2, ...],
) -> tuple[R12ReconciliationV2, ...]:
    lookup = _lookup(metrics)

    return (
        *_reconcile_one_window(
            label="current",
            lookup=lookup,
            value_field="current_value",
        ),
        *_reconcile_one_window(
            label="reference",
            lookup=lookup,
            value_field="reference_value",
        ),
    )


def run_r12_cohort_periodic_runtime_v2(
    *,
    cadence: PeriodicReportCadenceV2,
    anchor_date: date,
    runtime_config: GovernanceRuntimeConfig | None = None,
    execution_policy: GovernedExecutionPolicy | None = None,
    engine_override: Engine | None = None,
    manifest: dict | None = None,
) -> R12CohortPeriodicRuntimeV2:
    """
    Day93 B5B-2 R12 Cohort Runtime。

    顺序：
    1. cadence -> trusted TimeComparisonContract；
    2. current/reference 各自执行 History + Refund Observation preflight；
    3. 任一 preflight 不通过：0 SQL，直接 NOT_READY；
    4. 通过后，5 个正式 R12 Query Plan 分别走 Structured Governed Runtime；
    5. 只消费可释放 Evidence，最后做 deterministic reconciliation。

    该函数不绕过：
    Authorization / Time+Scope Binding / Compiler / AST /
    Result Protection / Audit / Evidence Builder。
    """

    comparison = build_periodic_gmv_comparison_v2(
        cadence=cadence,
        anchor_date=anchor_date,
    )

    active_manifest = (
        manifest
        if manifest is not None
        else load_and_validate_day66_manifest()
    )

    current_readiness = build_r12_runtime_readiness_v2(
        report_window=comparison.current_window,
        manifest=active_manifest,
    )
    reference_readiness = build_r12_runtime_readiness_v2(
        report_window=comparison.reference_window,
        manifest=active_manifest,
    )

    if (
        not current_readiness.ready
        or not reference_readiness.ready
    ):
        return R12CohortPeriodicRuntimeV2(
            status=R12CohortRuntimeStatusV2.NOT_READY,
            message=(
                "R12 Cohort Runtime preflight 未通过；"
                "没有执行任何 R12 SQL。"
            ),
            cadence=cadence,
            anchor_date=anchor_date,
            comparison=comparison,
            current_readiness=current_readiness,
            reference_readiness=reference_readiness,
        )

    active_config = (
        runtime_config
        if runtime_config is not None
        else load_governance_runtime_config()
    )

    metrics = tuple(
        _run_metric(
            spec=spec,
            comparison=comparison,
            runtime_config=active_config,
            execution_policy=execution_policy,
            engine_override=engine_override,
        )
        for spec in R12_METRIC_REGISTRY_V2
    )

    ready_count = sum(
        item.status == R12MetricRuntimeStatusV2.READY
        for item in metrics
    )

    if ready_count == 5:
        status = R12CohortRuntimeStatusV2.READY
        message = "5/5 R12 Metric 已形成可信 current/reference Evidence。"
    elif ready_count == 0:
        # Readiness 已通过，但 Governance/Protection/Execution 全部没有形成可释放值。
        # 用 PARTIAL_READY 不满足模型约束，因此这里返回一个显式 NOT_READY
        # 需要允许 metrics；为避免语义混乱，直接 fail loud。
        raise RuntimeError(
            "R12 Readiness 已通过，但 5/5 Metric 全部执行 NOT_READY；"
            "这是 Runtime Integration blocker，不应伪装成业务 NOT_READY。"
        )
    else:
        status = R12CohortRuntimeStatusV2.PARTIAL_READY
        message = (
            f"R12 Cohort Runtime 部分形成可信 Evidence：{ready_count}/5。"
        )

    reconciliations = build_r12_reconciliations_v2(
        metrics
    )

    return R12CohortPeriodicRuntimeV2(
        status=status,
        message=message,
        cadence=cadence,
        anchor_date=anchor_date,
        comparison=comparison,
        current_readiness=current_readiness,
        reference_readiness=reference_readiness,
        metrics=metrics,
        reconciliations=reconciliations,
    )
