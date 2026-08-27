from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, model_validator

from app.agents.contribution_analysis_v2 import (
    ContributionAnalysisResultV2,
    ContributionObservationV2,
    ContributionReconciliationStatusV2,
    analyze_additive_contribution_v2,
)
from app.agents.contribution_insight_adapter_v2 import (
    attach_contribution_result_to_insight_v2,
    build_dimension_contribution_material_v2,
)
from app.agents.derived_evidence_builder_v2 import (
    DerivedEvidenceBuildStatusV2,
    build_contribution_evidence_record_v2,
)
from app.agents.evidence_pack_delivery_v2 import (
    EvidencePackDeliveryV2,
    assemble_evidence_pack_delivery_v2,
)
from app.agents.evidence_pack_v2 import (
    EvidencePackV2,
    EvidenceRecordV2,
    EvidenceTypeV2,
)
from app.agents.investigation_contracts_v2 import (
    AnalysisModeV2,
    AnalysisScopeV2,
    EvidenceReferenceV2,
    InsightContractV2,
)
from app.agents.metric_comparison_v2 import (
    MetricComparisonResultV2,
)
from app.delivery.decision_console_entry_v2 import (
    PeriodicReportCadenceV2,
)
from app.delivery.decision_console_runtime_v2 import (
    build_day89_channel_tool_binding_v2,
    build_day89_local_access_context_v2,
    run_day89_monthly_gmv_report_v2,
    run_day89_periodic_gmv_report_v2,
)
from app.delivery.decision_console_view_v2 import (
    DecisionConsoleViewV2,
    build_decision_console_view_v2,
)
from app.delivery.executive_decision_brief_v2 import (
    ExecutiveDecisionBriefPreviewV2,
    build_executive_decision_brief_preview_v2,
)
from app.delivery.runtime_comparison_delivery_v2 import (
    RuntimeComparisonDeliveryResultV2,
    RuntimeComparisonDeliveryStatusV2,
)
from app.delivery.runtime_delivery_bridge_v2 import (
    RuntimeDeliveryBridgeResultV2,
    RuntimeDeliveryBridgeStatusV2,
    invoke_governed_plan_delivery_v2,
)
from app.governance.execution_policy import (
    GovernedExecutionPolicy,
)
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


MONTHLY_CONTRIBUTION_DELIVERY_VERSION = (
    "day89_monthly_contribution_delivery_v2_0"
)


def _log_day93_periodic_internal_stage_v2(
    *,
    trace_id: str,
    anchor_date,
    stage: str,
    status: str | None = None,
) -> None:
    """
    输出 Day93 Periodic Runtime 内部分段日志。

    仅记录：
    - trace_id；
    - UTC 时间；
    - anchor；
    - stage；
    - status（如有）。

    不记录 SQL、parameters、raw rows、数据库连接信息或 secret。
    """

    fields = {
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "trace_id": trace_id,
        "anchor": (
            anchor_date.isoformat()
            if hasattr(anchor_date, "isoformat")
            else str(anchor_date)
        ),
        "stage": stage,
        "status": status,
    }

    payload = " ".join(
        f"{key}={value}"
        for key, value in fields.items()
        if value is not None
    )

    print(
        f"[D93_PERIODIC_INTERNAL] {payload}",
        flush=True,
    )


class MonthlyContributionDeliveryStatusV2(str, Enum):
    READY = "ready"
    PARTIAL_READY = "partial_ready"
    COMPARISON_NOT_READY = "comparison_not_ready"
    CURRENT_CHANNEL_NOT_READY = "current_channel_not_ready"
    REFERENCE_CHANNEL_NOT_READY = "reference_channel_not_ready"
    TRUST_LINKAGE_MISMATCH = "trust_linkage_mismatch"
    RESULT_SHAPE_MISMATCH = "result_shape_mismatch"
    EVIDENCE_BUILD_FAILED = "evidence_build_failed"


class MonthlyContributionDeliveryResultV2(BaseModel):
    """
    Day89 Monthly GMV × Channel Contribution Delivery。

    该合同只释放：
    - safe runtime summaries；
    - deterministic comparison / contribution result；
    - EvidencePackDelivery；
    - Decision Console / Brief。

    不释放 Graph state、raw SQL、SQL parameters、raw DB rows。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        arbitrary_types_allowed=True,
    )

    contract_version: str = (
        MONTHLY_CONTRIBUTION_DELIVERY_VERSION
    )

    status: MonthlyContributionDeliveryStatusV2
    message: str
    comparison: TimeComparisonContractV2 | None = None

    current_channel_safe_runtime_result: (
        dict[str, Any] | None
    ) = None
    reference_channel_safe_runtime_result: (
        dict[str, Any] | None
    ) = None

    metric_comparison_result: (
        MetricComparisonResultV2 | None
    ) = None
    contribution_result: (
        ContributionAnalysisResultV2 | None
    ) = None

    delivery: EvidencePackDeliveryV2 | None = None
    console_view: DecisionConsoleViewV2 | None = None
    executive_brief: (
        ExecutiveDecisionBriefPreviewV2 | None
    ) = None

    @model_validator(mode="after")
    def validate_result(
        self,
    ) -> "MonthlyContributionDeliveryResultV2":
        if not self.message.strip():
            raise ValueError(
                "Monthly Contribution message 不能为空。"
            )

        artifacts = (
            self.metric_comparison_result,
            self.contribution_result,
            self.delivery,
            self.console_view,
            self.executive_brief,
        )

        if (
            self.status
            == MonthlyContributionDeliveryStatusV2.READY
        ):
            if self.comparison is None:
                raise ValueError(
                    "READY 必须包含 comparison。"
                )
            if any(item is None for item in artifacts):
                raise ValueError(
                    "READY 必须完整返回 Comparison / "
                    "Contribution / Delivery / Console / Brief。"
                )

        elif (
            self.status
            == MonthlyContributionDeliveryStatusV2
            .PARTIAL_READY
        ):
            if self.comparison is None:
                raise ValueError(
                    "PARTIAL_READY 必须包含 comparison。"
                )

            # Privacy-aware graceful degradation：
            # Overall Comparison 仍然是可信业务结果；
            # Breakdown / Contribution 不可释放时必须保持 None。
            required_partial_artifacts = (
                self.metric_comparison_result,
                self.delivery,
                self.console_view,
                self.executive_brief,
            )

            if any(
                item is None
                for item in required_partial_artifacts
            ):
                raise ValueError(
                    "PARTIAL_READY 必须保留可信 Overall "
                    "Comparison / Delivery / Console / Brief。"
                )

            if self.contribution_result is not None:
                raise ValueError(
                    "PARTIAL_READY 不得伪造 Contribution Result。"
                )

        elif any(item is not None for item in artifacts):
            raise ValueError(
                "失败状态不得释放半成品业务 artifacts。"
            )

        return self


# Day89 compatibility bridge:
# existing Monthly imports remain valid while Daily/Weekly reuse the same
# safe result/status contract. A future cleanup can rename the underlying
# class after the Day89 delivery gate.
PeriodicContributionDeliveryStatusV2 = (
    MonthlyContributionDeliveryStatusV2
)
PeriodicContributionDeliveryResultV2 = (
    MonthlyContributionDeliveryResultV2
)


def _failed(
    *,
    status: MonthlyContributionDeliveryStatusV2,
    message: str,
    comparison: TimeComparisonContractV2 | None = None,
    current_channel_result: (
        RuntimeDeliveryBridgeResultV2 | None
    ) = None,
    reference_channel_result: (
        RuntimeDeliveryBridgeResultV2 | None
    ) = None,
) -> MonthlyContributionDeliveryResultV2:
    return MonthlyContributionDeliveryResultV2(
        status=status,
        message=message,
        comparison=comparison,
        current_channel_safe_runtime_result=(
            dict(current_channel_result.safe_runtime_result)
            if current_channel_result is not None
            else None
        ),
        reference_channel_safe_runtime_result=(
            dict(reference_channel_result.safe_runtime_result)
            if reference_channel_result is not None
            else None
        ),
    )


def _partial_ready_from_comparison(
    *,
    message: str,
    comparison_delivery: RuntimeComparisonDeliveryResultV2,
    current_channel_result: (
        RuntimeDeliveryBridgeResultV2 | None
    ) = None,
    reference_channel_result: (
        RuntimeDeliveryBridgeResultV2 | None
    ) = None,
) -> MonthlyContributionDeliveryResultV2:
    """
    Periodic Report 的 privacy-aware graceful degradation。

    只有 Overall Comparison 已经完整 READY 时才能进入这里。
    Channel Breakdown / Contribution 无法安全释放时：
    - 保留 Overall KPI / Comparison / Evidence / Console / Brief；
    - 不释放任何 blocked channel rows；
    - contribution_result 保持 None；
    - safe runtime summary 仅用于说明 Breakdown 为什么不可用。
    """

    if (
        comparison_delivery.status
        != RuntimeComparisonDeliveryStatusV2.READY
        or comparison_delivery.delivery is None
        or comparison_delivery.metric_comparison_result is None
        or comparison_delivery.console_view is None
        or comparison_delivery.executive_brief is None
    ):
        raise ValueError(
            "PARTIAL_READY 只能建立在完整 READY "
            "Overall Comparison 之上。"
        )

    return MonthlyContributionDeliveryResultV2(
        status=(
            MonthlyContributionDeliveryStatusV2
            .PARTIAL_READY
        ),
        message=message,
        comparison=comparison_delivery.comparison,
        current_channel_safe_runtime_result=(
            dict(current_channel_result.safe_runtime_result)
            if current_channel_result is not None
            else None
        ),
        reference_channel_safe_runtime_result=(
            dict(reference_channel_result.safe_runtime_result)
            if reference_channel_result is not None
            else None
        ),
        metric_comparison_result=(
            comparison_delivery.metric_comparison_result
        ),
        contribution_result=None,
        delivery=comparison_delivery.delivery,
        console_view=comparison_delivery.console_view,
        executive_brief=comparison_delivery.executive_brief,
    )


def _single_query_record(
    delivery: EvidencePackDeliveryV2,
) -> EvidenceRecordV2:
    records = tuple(
        record
        for record in delivery.evidence_pack.evidence_records
        if (
            record.evidence_type
            == EvidenceTypeV2.GOVERNED_QUERY_RESULT
        )
    )

    if len(records) != 1:
        raise ValueError(
            "单侧 Runtime Delivery 必须恰好包含一条 "
            "GOVERNED_QUERY_RESULT。"
        )

    return records[0]


def _comparison_overall_records(
    comparison_delivery: RuntimeComparisonDeliveryResultV2,
) -> tuple[EvidenceRecordV2, EvidenceRecordV2]:
    if (
        comparison_delivery.status
        != RuntimeComparisonDeliveryStatusV2.READY
        or comparison_delivery.delivery is None
        or comparison_delivery.metric_comparison_result is None
    ):
        raise ValueError(
            "Monthly Overall Comparison 尚未 READY。"
        )

    records = {
        record.reference.evidence_id: record
        for record
        in comparison_delivery.delivery.evidence_pack.evidence_records
        if (
            record.evidence_type
            == EvidenceTypeV2.GOVERNED_QUERY_RESULT
        )
    }

    result = comparison_delivery.metric_comparison_result

    current = records.get(result.current_evidence_id)
    reference = records.get(result.reference_evidence_id)

    if current is None or reference is None:
        raise ValueError(
            "Comparison Result 引用的 Overall Evidence "
            "不完整。"
        )

    return current, reference


def _validate_query_record(
    *,
    record: EvidenceRecordV2,
    metric_name: str,
    result_grain: str,
    expected_window: TimeWindowReferenceV2,
) -> None:
    provenance = record.provenance
    protected = record.protected_result

    if provenance is None or protected is None:
        raise ValueError(
            "Governed Query Evidence 必须包含 provenance "
            "与 protected_result。"
        )

    if provenance.metric_name != metric_name:
        raise ValueError(
            "Evidence metric 与 Contribution metric 不一致。"
        )

    if provenance.result_grain != result_grain:
        raise ValueError(
            "Evidence result_grain 与预期不一致："
            f"expected={result_grain}; "
            f"actual={provenance.result_grain}"
        )

    if provenance.analysis_window != expected_window:
        raise ValueError(
            "Evidence analysis_window 与 Comparison Contract 不一致。"
        )


def _channel_observations(
    record: EvidenceRecordV2,
) -> tuple[ContributionObservationV2, ...]:
    protected = record.protected_result

    if protected is None:
        raise ValueError(
            "Channel Evidence 缺少 protected_result。"
        )

    if protected.field_names != (
        "channel_name",
        "gmv",
    ):
        raise ValueError(
            "GMV × Channel Contribution 只接受 "
            "(channel_name, gmv) 受保护结果。"
        )

    observations: list[ContributionObservationV2] = []
    seen: set[str] = set()

    for row in protected.rows:
        channel_name = row.get("channel_name")
        value = row.get("gmv")

        if (
            channel_name is None
            or not str(channel_name).strip()
        ):
            raise ValueError(
                "Channel Evidence 包含空 channel_name。"
            )

        if value is None:
            raise ValueError(
                "Channel Evidence 包含空 GMV value。"
            )

        key = str(channel_name).strip()

        if key in seen:
            raise ValueError(
                "Channel Evidence 包含重复 channel_name："
                f"{key}"
            )
        seen.add(key)

        # Protected result 当前不释放 channel_code，
        # 因此 Day89 v1 以已发布且唯一的 channel_name
        # 同时作为 member_key / member_label。
        observations.append(
            ContributionObservationV2(
                member_key=key,
                member_label=key,
                value=Decimal(str(value)),
            )
        )

    return tuple(observations)


def _validate_plan_scope_semantics_v2(
    *,
    overall_plan_name: str,
    channel_plan_name: str,
) -> None:
    """
    验证 Overall / Channel Query Plan 使用同一业务 Scope 语义。

    注意：
    ScopedQueryContract.contract_fingerprint 是单次查询实例身份，
    包含 request_id / target_id / parameter names，不能跨 request
    或跨 Query Plan 直接比较相等。

    Day89 当前只要求两类 approved GMV Plan：
    - 使用相同 scope_mode；
    - 覆盖相同 required_dimensions；
    - 从相同 scoped source tables 继承 Row Scope。
    """

    overall_plan = get_query_plan_v2_by_name(
        overall_plan_name
    )
    channel_plan = get_query_plan_v2_by_name(
        channel_plan_name
    )

    if overall_plan is None or channel_plan is None:
        raise ValueError(
            "Contribution Scope 校验缺少正式 Query Plan。"
        )

    overall_scope = overall_plan.scope_contract
    channel_scope = channel_plan.scope_contract

    if overall_scope.scope_mode != channel_scope.scope_mode:
        raise ValueError(
            "Overall / Channel Query Plan scope_mode 不一致。"
        )

    if (
        overall_scope.required_dimensions
        != channel_scope.required_dimensions
    ):
        raise ValueError(
            "Overall / Channel Query Plan required_dimensions 不一致。"
        )

    if (
        overall_scope.source_tables
        != channel_scope.source_tables
    ):
        raise ValueError(
            "Overall / Channel Query Plan scoped source_tables 不一致。"
        )


def _validate_four_way_trust_linkage(
    *,
    current_overall: EvidenceRecordV2,
    reference_overall: EvidenceRecordV2,
    current_channel: EvidenceRecordV2,
    reference_channel: EvidenceRecordV2,
    comparison: TimeComparisonContractV2,
) -> None:
    records = (
        current_overall,
        reference_overall,
        current_channel,
        reference_channel,
    )

    for record in records:
        if record.provenance is None:
            raise ValueError(
                "Contribution parent Evidence 缺少 provenance。"
            )

    current_overall_p = current_overall.provenance
    reference_overall_p = reference_overall.provenance
    current_channel_p = current_channel.provenance
    reference_channel_p = reference_channel.provenance

    assert current_overall_p is not None
    assert reference_overall_p is not None
    assert current_channel_p is not None
    assert reference_channel_p is not None

    datasets = {
        item.dataset_name
        for item in (
            current_overall_p,
            reference_overall_p,
            current_channel_p,
            reference_channel_p,
        )
    }
    schemas = {
        item.target_schema
        for item in (
            current_overall_p,
            reference_overall_p,
            current_channel_p,
            reference_channel_p,
        )
    }
    scope_summaries = {
        item.scope_summary
        for item in (
            current_overall_p,
            reference_overall_p,
            current_channel_p,
            reference_channel_p,
        )
    }

    if len(datasets) != 1 or len(schemas) != 1:
        raise ValueError(
            "Contribution 四侧 Evidence 的 dataset / schema 不一致。"
        )

    # scope_binding_fingerprint 是 execution-instance contract identity，
    # 不能跨不同 request / plan 直接比较。
    # 当前 Production MVP 使用 server-owned scope_summary +
    # Query Plan scope semantics 证明四侧 effective scope 等价。
    if None in scope_summaries or len(scope_summaries) != 1:
        raise ValueError(
            "Contribution 四侧 Evidence 的 effective scope_summary "
            "不一致或缺失，禁止做贡献度分解。"
        )

    if (
        current_overall_p.plan_name
        != reference_overall_p.plan_name
        or current_channel_p.plan_name
        != reference_channel_p.plan_name
    ):
        raise ValueError(
            "Current / Reference 必须分别复用同一个 "
            "Overall / Channel Query Plan。"
        )

    _validate_plan_scope_semantics_v2(
        overall_plan_name=current_overall_p.plan_name,
        channel_plan_name=current_channel_p.plan_name,
    )

    _validate_query_record(
        record=current_overall,
        metric_name="gmv",
        result_grain="overall",
        expected_window=comparison.current_window,
    )
    _validate_query_record(
        record=reference_overall,
        metric_name="gmv",
        result_grain="overall",
        expected_window=comparison.reference_window,
    )
    _validate_query_record(
        record=current_channel,
        metric_name="gmv",
        result_grain="channel",
        expected_window=comparison.current_window,
    )
    _validate_query_record(
        record=reference_channel,
        metric_name="gmv",
        result_grain="channel",
        expected_window=comparison.reference_window,
    )


def _question_for_window(
    window: TimeWindowReferenceV2,
) -> str:
    return (
        f"{window.start_date.year}年"
        f"{window.start_date.month}月"
        f"{window.start_date.day}日至"
        f"{window.end_date.year}年"
        f"{window.end_date.month}月"
        f"{window.end_date.day}日"
        "各渠道GMV是多少？"
    )


def run_day89_monthly_gmv_channel_contribution_v2(
    *,
    anchor_date,
    runtime_config: GovernanceRuntimeConfig | None = None,
    execution_policy: GovernedExecutionPolicy | None = None,
) -> MonthlyContributionDeliveryResultV2:
    """
    Day89 Monthly GMV Contribution Runtime：

    已有 Monthly Overall Comparison（2 queries）
      + current channel Governed Query
      + reference channel Governed Query
      -> deterministic GMV × channel contribution
      -> 4-parent Contribution Evidence
      -> DIAGNOSTIC EvidencePackDelivery
      -> Comparison + Contribution + current breakdown Console

    本函数不计算 Anomaly，不声明 causality。
    """

    internal_trace_id = (
        f"d93-internal-{uuid4().hex[:12]}"
    )

    _log_day93_periodic_internal_stage_v2(
        trace_id=internal_trace_id,
        anchor_date=anchor_date,
        stage="config_start",
    )

    active_config = (
        runtime_config
        if runtime_config is not None
        else load_governance_runtime_config()
    )

    _log_day93_periodic_internal_stage_v2(
        trace_id=internal_trace_id,
        anchor_date=anchor_date,
        stage="config_done",
    )

    _log_day93_periodic_internal_stage_v2(
        trace_id=internal_trace_id,
        anchor_date=anchor_date,
        stage="overall_comparison_start",
    )

    comparison_delivery = run_day89_monthly_gmv_report_v2(
        anchor_date=anchor_date,
        runtime_config=active_config,
        execution_policy=execution_policy,
    )

    _log_day93_periodic_internal_stage_v2(
        trace_id=internal_trace_id,
        anchor_date=anchor_date,
        stage="overall_comparison_done",
        status=comparison_delivery.status.value,
    )

    if (
        comparison_delivery.status
        != RuntimeComparisonDeliveryStatusV2.READY
        or comparison_delivery.delivery is None
        or comparison_delivery.metric_comparison_result is None
    ):
        _log_day93_periodic_internal_stage_v2(
            trace_id=internal_trace_id,
            anchor_date=anchor_date,
            stage="function_return",
            status="comparison_not_ready",
        )
        return _failed(
            status=(
                MonthlyContributionDeliveryStatusV2
                .COMPARISON_NOT_READY
            ),
            message=(
                "Monthly Overall Comparison 未 READY；"
                f"{comparison_delivery.message}"
            ),
            comparison=comparison_delivery.comparison,
        )

    comparison = comparison_delivery.comparison

    _log_day93_periodic_internal_stage_v2(
        trace_id=internal_trace_id,
        anchor_date=anchor_date,
        stage="channel_binding_start",
    )

    binding = build_day89_channel_tool_binding_v2()

    _log_day93_periodic_internal_stage_v2(
        trace_id=internal_trace_id,
        anchor_date=anchor_date,
        stage="channel_binding_done",
    )

    base_id = (
        f"day89-monthly-contribution-"
        f"{anchor_date.isoformat()}-{uuid4().hex}"
    )

    current_request_id = f"{base_id}-current-channel"

    _log_day93_periodic_internal_stage_v2(
        trace_id=internal_trace_id,
        anchor_date=anchor_date,
        stage="current_channel_start",
    )

    current_channel_result = invoke_governed_plan_delivery_v2(
        context=build_day89_local_access_context_v2(
            request_id=current_request_id,
        ),
        plan_name=binding.plan_name,
        analysis_window=comparison.current_window,
        question=_question_for_window(
            comparison.current_window
        ),
        runtime_config=active_config,
        approved_tool_binding=binding,
        execution_policy=execution_policy,
        event_id=current_request_id,
    )

    _log_day93_periodic_internal_stage_v2(
        trace_id=internal_trace_id,
        anchor_date=anchor_date,
        stage="current_channel_done",
        status=current_channel_result.status.value,
    )

    if (
        current_channel_result.status
        != RuntimeDeliveryBridgeStatusV2.READY
        or current_channel_result.delivery is None
    ):
        _log_day93_periodic_internal_stage_v2(
            trace_id=internal_trace_id,
            anchor_date=anchor_date,
            stage="function_return",
            status="current_channel_not_ready",
        )
        return _failed(
            status=(
                MonthlyContributionDeliveryStatusV2
                .CURRENT_CHANNEL_NOT_READY
            ),
            message=(
                "Current Channel Delivery 未 READY；"
                f"{current_channel_result.message}"
            ),
            comparison=comparison,
            current_channel_result=current_channel_result,
        )

    reference_request_id = f"{base_id}-reference-channel"

    _log_day93_periodic_internal_stage_v2(
        trace_id=internal_trace_id,
        anchor_date=anchor_date,
        stage="reference_channel_start",
    )

    reference_channel_result = invoke_governed_plan_delivery_v2(
        context=build_day89_local_access_context_v2(
            request_id=reference_request_id,
        ),
        plan_name=binding.plan_name,
        analysis_window=comparison.reference_window,
        question=_question_for_window(
            comparison.reference_window
        ),
        runtime_config=active_config,
        approved_tool_binding=binding,
        execution_policy=execution_policy,
        event_id=reference_request_id,
    )

    _log_day93_periodic_internal_stage_v2(
        trace_id=internal_trace_id,
        anchor_date=anchor_date,
        stage="reference_channel_done",
        status=reference_channel_result.status.value,
    )

    if (
        reference_channel_result.status
        != RuntimeDeliveryBridgeStatusV2.READY
        or reference_channel_result.delivery is None
    ):
        _log_day93_periodic_internal_stage_v2(
            trace_id=internal_trace_id,
            anchor_date=anchor_date,
            stage="function_return",
            status="reference_channel_not_ready",
        )
        return _failed(
            status=(
                MonthlyContributionDeliveryStatusV2
                .REFERENCE_CHANNEL_NOT_READY
            ),
            message=(
                "Reference Channel Delivery 未 READY；"
                f"{reference_channel_result.message}"
            ),
            comparison=comparison,
            current_channel_result=current_channel_result,
            reference_channel_result=reference_channel_result,
        )

    try:
        _log_day93_periodic_internal_stage_v2(
            trace_id=internal_trace_id,
            anchor_date=anchor_date,
            stage="trust_linkage_start",
        )

        current_overall, reference_overall = (
            _comparison_overall_records(
                comparison_delivery
            )
        )

        current_channel = _single_query_record(
            current_channel_result.delivery
        )
        reference_channel = _single_query_record(
            reference_channel_result.delivery
        )

        if (
            current_channel_result.delivery.metric_definition
            != comparison_delivery.delivery.metric_definition
            or reference_channel_result.delivery.metric_definition
            != comparison_delivery.delivery.metric_definition
        ):
            raise ValueError(
                "Overall / Channel Metric Definition Snapshot 不一致。"
            )

        _validate_four_way_trust_linkage(
            current_overall=current_overall,
            reference_overall=reference_overall,
            current_channel=current_channel,
            reference_channel=reference_channel,
            comparison=comparison,
        )

        _log_day93_periodic_internal_stage_v2(
            trace_id=internal_trace_id,
            anchor_date=anchor_date,
            stage="trust_linkage_done",
        )

        metric_comparison = (
            comparison_delivery.metric_comparison_result
        )

        _log_day93_periodic_internal_stage_v2(
            trace_id=internal_trace_id,
            anchor_date=anchor_date,
            stage="contribution_start",
        )

        contribution = analyze_additive_contribution_v2(
            metric_name="gmv",
            dimension_name="channel",
            comparison=comparison,
            current_overall_value=(
                metric_comparison.current_value
            ),
            reference_overall_value=(
                metric_comparison.reference_value
            ),
            current_members=_channel_observations(
                current_channel
            ),
            reference_members=_channel_observations(
                reference_channel
            ),
        )

        _log_day93_periodic_internal_stage_v2(
            trace_id=internal_trace_id,
            anchor_date=anchor_date,
            stage="contribution_done",
            status=contribution.reconciliation_status.value,
        )

        parent_ids = (
            current_overall.reference.evidence_id,
            reference_overall.reference.evidence_id,
            current_channel.reference.evidence_id,
            reference_channel.reference.evidence_id,
        )

        contribution_evidence_id = (
            'ev_contrib_'
            + hashlib.sha256(
                '|'.join(parent_ids).encode('utf-8')
            ).hexdigest()[:20]
        )

        # Canonical Contribution Evidence Reference 必须由既有
        # Contribution Insight Adapter 生成。
        # EvidencePackV2 要求 Insight / Record 对同一 evidence_id
        # 保留完全相同的 EvidenceReferenceV2，而不仅仅是 ID 相同。
        _, contribution_ref = (
            build_dimension_contribution_material_v2(
                result=contribution,
                evidence_id=contribution_evidence_id,
            )
        )

        _log_day93_periodic_internal_stage_v2(
            trace_id=internal_trace_id,
            anchor_date=anchor_date,
            stage="evidence_build_start",
        )

        derived = build_contribution_evidence_record_v2(
            evidence_reference=contribution_ref,
            current_overall_evidence_id=(
                current_overall.reference.evidence_id
            ),
            reference_overall_evidence_id=(
                reference_overall.reference.evidence_id
            ),
            current_dimension_evidence_id=(
                current_channel.reference.evidence_id
            ),
            reference_dimension_evidence_id=(
                reference_channel.reference.evidence_id
            ),
        )

        _log_day93_periodic_internal_stage_v2(
            trace_id=internal_trace_id,
            anchor_date=anchor_date,
            stage="evidence_build_done",
            status=derived.status.value,
        )

        if (
            not derived.success
            or derived.status
            != DerivedEvidenceBuildStatusV2.BUILT
            or derived.record is None
        ):
            _log_day93_periodic_internal_stage_v2(
                trace_id=internal_trace_id,
                anchor_date=anchor_date,
                stage="function_return",
                status="evidence_build_failed",
            )
            return _failed(
                status=(
                    MonthlyContributionDeliveryStatusV2
                    .EVIDENCE_BUILD_FAILED
                ),
                message=(
                    derived.detail
                    or "Contribution Evidence Build failed。"
                ),
                comparison=comparison,
                current_channel_result=current_channel_result,
                reference_channel_result=reference_channel_result,
            )

        scope_summary = (
            current_overall.provenance.scope_summary
            if current_overall.provenance is not None
            else None
        )

        _log_day93_periodic_internal_stage_v2(
            trace_id=internal_trace_id,
            anchor_date=anchor_date,
            stage="delivery_assembly_start",
        )

        scope = AnalysisScopeV2(
            metric_name="gmv",
            analysis_window=comparison.current_window,
            comparison=comparison,
            result_grain="channel",
            scope_summary=scope_summary,
        )

        base_insight = InsightContractV2(
            analysis_mode=AnalysisModeV2.DIAGNOSTIC,
            analysis_scope=scope,
            confirmed_facts=(
                comparison_delivery.delivery.evidence_pack
                .insight.confirmed_facts
            ),
            evidence=(
                current_overall.reference,
                reference_overall.reference,
                current_channel.reference,
                reference_channel.reference,
            ),
        )

        insight = attach_contribution_result_to_insight_v2(
            insight=base_insight,
            result=contribution,
            evidence_id=contribution_ref.evidence_id,
        )

        pack = EvidencePackV2(
            pack_id=(
                "pack-monthly-contribution-"
                f"{contribution_ref.evidence_id}"
            ),
            analysis_scope=scope,
            insight=insight,
            evidence_records=(
                current_overall,
                reference_overall,
                current_channel,
                reference_channel,
                derived.record,
            ),
        )

        delivery = assemble_evidence_pack_delivery_v2(
            evidence_pack=pack,
            metric_definition=(
                comparison_delivery.delivery.metric_definition
            ),
        )

        console = build_decision_console_view_v2(
            delivery=delivery,
            metric_comparison_result=metric_comparison,
            contribution_result=contribution,
            contribution_evidence_id=(
                contribution_ref.evidence_id
            ),
            breakdown_evidence_id=(
                current_channel.reference.evidence_id
            ),
        )

        brief = build_executive_decision_brief_preview_v2(
            request_subject=(
                f"{comparison.current_window.start_date:%Y年%m月}"
                " GMV 月度环比与渠道贡献分析"
            ),
            delivery=delivery,
            console_view=console,
        )

        _log_day93_periodic_internal_stage_v2(
            trace_id=internal_trace_id,
            anchor_date=anchor_date,
            stage="delivery_assembly_done",
        )

    except ValueError as exc:
        _log_day93_periodic_internal_stage_v2(
            trace_id=internal_trace_id,
            anchor_date=anchor_date,
            stage="function_return",
            status="trust_linkage_mismatch",
        )
        return _failed(
            status=(
                MonthlyContributionDeliveryStatusV2
                .TRUST_LINKAGE_MISMATCH
            ),
            message=str(exc),
            comparison=comparison,
            current_channel_result=current_channel_result,
            reference_channel_result=reference_channel_result,
        )

    _log_day93_periodic_internal_stage_v2(
        trace_id=internal_trace_id,
        anchor_date=anchor_date,
        stage="function_return",
        status="ready",
    )

    return MonthlyContributionDeliveryResultV2(
        status=MonthlyContributionDeliveryStatusV2.READY,
        message=(
            "Monthly GMV Comparison + Channel Contribution "
            "Delivery 已生成。"
        ),
        comparison=comparison,
        current_channel_safe_runtime_result=dict(
            current_channel_result.safe_runtime_result
        ),
        reference_channel_safe_runtime_result=dict(
            reference_channel_result.safe_runtime_result
        ),
        metric_comparison_result=metric_comparison,
        contribution_result=contribution,
        delivery=delivery,
        console_view=console,
        executive_brief=brief,
    )


def run_day89_periodic_gmv_channel_contribution_v2(
    *,
    cadence: PeriodicReportCadenceV2,
    anchor_date,
    runtime_config: GovernanceRuntimeConfig | None = None,
    execution_policy: GovernedExecutionPolicy | None = None,
) -> MonthlyContributionDeliveryResultV2:
    """
    Day89 Daily / Weekly / Monthly GMV Contribution Runtime：

    已有 Periodic Overall Comparison（2 queries）
      + current channel Governed Query
      + reference channel Governed Query
      -> deterministic GMV × channel contribution
      -> 4-parent Contribution Evidence
      -> DIAGNOSTIC EvidencePackDelivery
      -> Comparison + Contribution + current breakdown Console

    本函数不计算 Anomaly，不声明 causality。
    """

    if cadence == PeriodicReportCadenceV2.MONTHLY:
        return run_day89_monthly_gmv_channel_contribution_v2(
            anchor_date=anchor_date,
            runtime_config=runtime_config,
            execution_policy=execution_policy,
        )

    active_config = (
        runtime_config
        if runtime_config is not None
        else load_governance_runtime_config()
    )

    comparison_delivery = run_day89_periodic_gmv_report_v2(
        cadence=cadence,
        anchor_date=anchor_date,
        runtime_config=active_config,
        execution_policy=execution_policy,
    )

    if (
        comparison_delivery.status
        != RuntimeComparisonDeliveryStatusV2.READY
        or comparison_delivery.delivery is None
        or comparison_delivery.metric_comparison_result is None
    ):
        return _failed(
            status=(
                MonthlyContributionDeliveryStatusV2
                .COMPARISON_NOT_READY
            ),
            message=(
                "Periodic Overall Comparison 未 READY；"
                f"{comparison_delivery.message}"
            ),
            comparison=comparison_delivery.comparison,
        )

    comparison = comparison_delivery.comparison
    binding = build_day89_channel_tool_binding_v2()

    base_id = (
        f"day89-{cadence.value}-contribution-"
        f"{anchor_date.isoformat()}-{uuid4().hex}"
    )

    current_request_id = f"{base_id}-current-channel"

    current_channel_result = invoke_governed_plan_delivery_v2(
        context=build_day89_local_access_context_v2(
            request_id=current_request_id,
        ),
        plan_name=binding.plan_name,
        analysis_window=comparison.current_window,
        question=_question_for_window(
            comparison.current_window
        ),
        runtime_config=active_config,
        approved_tool_binding=binding,
        execution_policy=execution_policy,
        event_id=current_request_id,
    )

    if (
        current_channel_result.status
        != RuntimeDeliveryBridgeStatusV2.READY
        or current_channel_result.delivery is None
    ):
        return _partial_ready_from_comparison(
            message=(
                "Periodic Overall Comparison 已 READY；"
                "但 Current Channel Breakdown 未能安全释放，"
                "因此本期 Contribution 不可用。"
                f" {current_channel_result.message}"
            ),
            comparison_delivery=comparison_delivery,
            current_channel_result=current_channel_result,
        )

    reference_request_id = f"{base_id}-reference-channel"

    reference_channel_result = invoke_governed_plan_delivery_v2(
        context=build_day89_local_access_context_v2(
            request_id=reference_request_id,
        ),
        plan_name=binding.plan_name,
        analysis_window=comparison.reference_window,
        question=_question_for_window(
            comparison.reference_window
        ),
        runtime_config=active_config,
        approved_tool_binding=binding,
        execution_policy=execution_policy,
        event_id=reference_request_id,
    )

    if (
        reference_channel_result.status
        != RuntimeDeliveryBridgeStatusV2.READY
        or reference_channel_result.delivery is None
    ):
        return _partial_ready_from_comparison(
            message=(
                "Periodic Overall Comparison 已 READY；"
                "但 Reference Channel Breakdown 未能安全释放，"
                "因此本期 Contribution 不可用。"
                f" {reference_channel_result.message}"
            ),
            comparison_delivery=comparison_delivery,
            current_channel_result=current_channel_result,
            reference_channel_result=reference_channel_result,
        )

    try:
        current_overall, reference_overall = (
            _comparison_overall_records(
                comparison_delivery
            )
        )

        current_channel = _single_query_record(
            current_channel_result.delivery
        )
        reference_channel = _single_query_record(
            reference_channel_result.delivery
        )

        if (
            current_channel_result.delivery.metric_definition
            != comparison_delivery.delivery.metric_definition
            or reference_channel_result.delivery.metric_definition
            != comparison_delivery.delivery.metric_definition
        ):
            raise ValueError(
                "Overall / Channel Metric Definition Snapshot 不一致。"
            )

        _validate_four_way_trust_linkage(
            current_overall=current_overall,
            reference_overall=reference_overall,
            current_channel=current_channel,
            reference_channel=reference_channel,
            comparison=comparison,
        )

        metric_comparison = (
            comparison_delivery.metric_comparison_result
        )

        contribution = analyze_additive_contribution_v2(
            metric_name="gmv",
            dimension_name="channel",
            comparison=comparison,
            current_overall_value=(
                metric_comparison.current_value
            ),
            reference_overall_value=(
                metric_comparison.reference_value
            ),
            current_members=_channel_observations(
                current_channel
            ),
            reference_members=_channel_observations(
                reference_channel
            ),
        )

        parent_ids = (
            current_overall.reference.evidence_id,
            reference_overall.reference.evidence_id,
            current_channel.reference.evidence_id,
            reference_channel.reference.evidence_id,
        )

        contribution_evidence_id = (
            'ev_contrib_'
            + hashlib.sha256(
                '|'.join(parent_ids).encode('utf-8')
            ).hexdigest()[:20]
        )

        # Canonical Contribution Evidence Reference 必须由既有
        # Contribution Insight Adapter 生成。
        # EvidencePackV2 要求 Insight / Record 对同一 evidence_id
        # 保留完全相同的 EvidenceReferenceV2，而不仅仅是 ID 相同。
        _, contribution_ref = (
            build_dimension_contribution_material_v2(
                result=contribution,
                evidence_id=contribution_evidence_id,
            )
        )

        derived = build_contribution_evidence_record_v2(
            evidence_reference=contribution_ref,
            current_overall_evidence_id=(
                current_overall.reference.evidence_id
            ),
            reference_overall_evidence_id=(
                reference_overall.reference.evidence_id
            ),
            current_dimension_evidence_id=(
                current_channel.reference.evidence_id
            ),
            reference_dimension_evidence_id=(
                reference_channel.reference.evidence_id
            ),
        )

        if (
            not derived.success
            or derived.status
            != DerivedEvidenceBuildStatusV2.BUILT
            or derived.record is None
        ):
            return _failed(
                status=(
                    MonthlyContributionDeliveryStatusV2
                    .EVIDENCE_BUILD_FAILED
                ),
                message=(
                    derived.detail
                    or "Contribution Evidence Build failed。"
                ),
                comparison=comparison,
                current_channel_result=current_channel_result,
                reference_channel_result=reference_channel_result,
            )

        scope_summary = (
            current_overall.provenance.scope_summary
            if current_overall.provenance is not None
            else None
        )

        scope = AnalysisScopeV2(
            metric_name="gmv",
            analysis_window=comparison.current_window,
            comparison=comparison,
            result_grain="channel",
            scope_summary=scope_summary,
        )

        base_insight = InsightContractV2(
            analysis_mode=AnalysisModeV2.DIAGNOSTIC,
            analysis_scope=scope,
            confirmed_facts=(
                comparison_delivery.delivery.evidence_pack
                .insight.confirmed_facts
            ),
            evidence=(
                current_overall.reference,
                reference_overall.reference,
                current_channel.reference,
                reference_channel.reference,
            ),
        )

        insight = attach_contribution_result_to_insight_v2(
            insight=base_insight,
            result=contribution,
            evidence_id=contribution_ref.evidence_id,
        )

        pack = EvidencePackV2(
            pack_id=(
                f"pack-{cadence.value}-contribution-"
                f"{contribution_ref.evidence_id}"
            ),
            analysis_scope=scope,
            insight=insight,
            evidence_records=(
                current_overall,
                reference_overall,
                current_channel,
                reference_channel,
                derived.record,
            ),
        )

        delivery = assemble_evidence_pack_delivery_v2(
            evidence_pack=pack,
            metric_definition=(
                comparison_delivery.delivery.metric_definition
            ),
        )

        console = build_decision_console_view_v2(
            delivery=delivery,
            metric_comparison_result=metric_comparison,
            contribution_result=contribution,
            contribution_evidence_id=(
                contribution_ref.evidence_id
            ),
            breakdown_evidence_id=(
                current_channel.reference.evidence_id
            ),
        )

        brief = build_executive_decision_brief_preview_v2(
            request_subject=(
                f"{comparison.current_window.start_date.isoformat()}"
                f" {cadence.value.upper()} GMV 比较与渠道贡献分析"
            ),
            delivery=delivery,
            console_view=console,
        )

    except ValueError as exc:
        return _failed(
            status=(
                MonthlyContributionDeliveryStatusV2
                .TRUST_LINKAGE_MISMATCH
            ),
            message=str(exc),
            comparison=comparison,
            current_channel_result=current_channel_result,
            reference_channel_result=reference_channel_result,
        )

    return MonthlyContributionDeliveryResultV2(
        status=MonthlyContributionDeliveryStatusV2.READY,
        message=(
            f"{cadence.value.upper()} GMV Comparison + "
            "Channel Contribution Delivery 已生成。"
        ),
        comparison=comparison,
        current_channel_safe_runtime_result=dict(
            current_channel_result.safe_runtime_result
        ),
        reference_channel_safe_runtime_result=dict(
            reference_channel_result.safe_runtime_result
        ),
        metric_comparison_result=metric_comparison,
        contribution_result=contribution,
        delivery=delivery,
        console_view=console,
        executive_brief=brief,
    )

