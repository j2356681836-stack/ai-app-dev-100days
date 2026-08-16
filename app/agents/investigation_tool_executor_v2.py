from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.agents.investigation_contracts_v2 import (
    EvidenceReferenceV2,
    ToolFailureCodeV2,
)
from app.agents.investigation_loop_v2 import (
    ToolObservationStatusV2,
    ToolObservationV2,
)
from app.agents.investigation_planner_v2 import (
    PlannerDecisionTypeV2,
    PlannerDecisionV2,
)
from app.governance.governed_finalization import (
    FinalizationOutcome,
    FinalizationReason,
    GovernedFinalizationResult,
)


GovernedToolExecutorV2 = Callable[[], GovernedFinalizationResult]


@dataclass(frozen=True)
class TrustedToolExecutionBindingV2:
    """
    系统侧可信执行绑定。

    Planner 看不到这个对象，也不能修改里面的 executor。
    executor 应该已经通过闭包或上层服务绑定好：
    AccessContext / Envelope / Compiled Contract / Runtime Config 等可信输入。

    action_id 与 executor_binding 只是用于把 Day85 Planner Decision
    和真正的 governed executor 绑定起来。
    """

    action_id: str
    executor_binding: str
    executor: GovernedToolExecutorV2


class InvestigationToolExecutionResultV2(BaseModel):
    """
    一次 Investigation Tool 执行后的安全结果。

    observation：
    提供给 Day86 Loop 的控制层结果。

    evidence_reference：
    只有 Governed Finalization 成功并释放数据时才存在。

    released_rows：
    只允许保存 GovernedFinalizationResult 已经释放的 protected rows。
    这里绝不接收 raw execution rows。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        arbitrary_types_allowed=True,
    )

    observation: ToolObservationV2
    evidence_reference: EvidenceReferenceV2 | None = None
    released_rows: tuple[dict[str, Any], ...] = ()

    finalization_outcome: str
    finalization_reason: str
    blocked_stage: str | None = None
    blocked_reason: str | None = None
    audit_event_fingerprint: str | None = None


def _evidence_id(
    *,
    action_id: str,
    result: GovernedFinalizationResult,
) -> str:
    """
    用已经持久化的 Audit Event Fingerprint 生成轻量 evidence_id。

    不把 row values、SQL 或原始问题写进 ID。
    """

    fingerprint = result.audit_event_fingerprint
    if fingerprint is None:
        raise ValueError(
            "成功释放 Evidence 前必须存在 audit_event_fingerprint。"
        )

    digest = sha256(
        f"{action_id}|{fingerprint}".encode("utf-8")
    ).hexdigest()[:16]

    return f"ev_tool_{digest}"


def _map_failure_code(
    result: GovernedFinalizationResult,
) -> ToolFailureCodeV2:
    """
    把现有 Governed Finalization 语义映射到 Day82 Tool Failure Code。

    注意：
    Result Protection / Audit / 其他治理失败当前统一映射到
    EXECUTION_FAILURE，但 blocked_stage / blocked_reason 会保留在
    InvestigationToolExecutionResultV2 中，不会丢失治理细节。
    """

    if (
        result.reason_code
        == FinalizationReason.AUTHORIZATION_BLOCKED
    ):
        return ToolFailureCodeV2.UNAUTHORIZED

    if (
        result.reason_code
        == FinalizationReason.INVALID_FINALIZATION_INPUT
    ):
        return ToolFailureCodeV2.INVALID_INPUT

    if (
        result.reason_code
        == FinalizationReason.EXECUTION_BLOCKED
        and result.blocked_reason
        in {"statement_timeout", "pool_timeout"}
    ):
        return ToolFailureCodeV2.TIMEOUT

    return ToolFailureCodeV2.EXECUTION_FAILURE


def execute_investigation_tool_v2(
    *,
    decision: PlannerDecisionV2,
    attempt_number: int,
    bindings: Mapping[str, TrustedToolExecutionBindingV2],
) -> InvestigationToolExecutionResultV2:
    """
    把 Day85 的合法 Planner Decision 接到真实 Governed Executor Output。

    关键边界：
    - 只接受已经通过 Day85 deterministic validation 的 PlannerDecisionV2；
    - Planner 只能选择 action_id，不能传 raw SQL / Metric Formula；
    - 真正执行对象来自系统侧 trusted binding registry；
    - executor_binding 必须和 ToolContractV2 完全一致；
    - 只有 GovernedFinalizationResult.SUCCEEDED 的 protected rows
      才能转换成 Evidence；
    - retryable 完全继承真实 Executor Result，Loop 不自行猜测。
    """

    if decision.decision_type != PlannerDecisionTypeV2.SELECT_TOOL:
        raise ValueError(
            "只有 SELECT_TOOL Planner Decision 才允许进入 Tool Executor。"
        )

    if decision.selected_action is None:
        raise ValueError(
            "SELECT_TOOL Planner Decision 缺少 selected_action。"
        )

    action = decision.selected_action

    binding = bindings.get(action.action_id)
    if binding is None:
        raise ValueError(
            "当前 action 没有系统侧可信 Tool Execution Binding。"
        )

    if binding.action_id != action.action_id:
        raise ValueError(
            "Trusted Tool Binding 的 action_id 与 Planner Decision 不一致。"
        )

    if (
        binding.executor_binding
        != action.tool_contract.executor_binding
    ):
        raise ValueError(
            "Trusted Tool Binding 与 ToolContractV2.executor_binding 不一致。"
        )

    result = binding.executor()

    if not isinstance(result, GovernedFinalizationResult):
        raise TypeError(
            "Investigation Tool Executor 必须返回 GovernedFinalizationResult。"
        )

    if result.outcome == FinalizationOutcome.SUCCEEDED:
        if not result.success:
            raise ValueError(
                "SUCCEEDED finalization 必须 success=True。"
            )

        if result.row_count == 0:
            observation = ToolObservationV2(
                action_id=action.action_id,
                attempt_number=attempt_number,
                status=ToolObservationStatusV2.NO_DATA,
                failure_code=ToolFailureCodeV2.NO_DATA,
                retryable=False,
                summary=(
                    "Governed Executor 执行成功，但当前绑定条件下没有可释放数据。"
                ),
            )
            return InvestigationToolExecutionResultV2(
                observation=observation,
                evidence_reference=None,
                released_rows=(),
                finalization_outcome=result.outcome.value,
                finalization_reason=result.reason_code.value,
                blocked_stage=result.blocked_stage,
                blocked_reason=result.blocked_reason,
                audit_event_fingerprint=(
                    result.audit_event_fingerprint
                ),
            )

        evidence_id = _evidence_id(
            action_id=action.action_id,
            result=result,
        )

        evidence = EvidenceReferenceV2(
            evidence_id=evidence_id,
            source=(
                f"tool:{action.tool_contract.identity.name}"
                f"@{action.tool_contract.identity.version}"
            ),
            description=(
                f"action={action.action_id}；"
                f"released_rows={result.row_count}；"
                "结果已经通过 Governed Finalization。"
            ),
        )

        observation = ToolObservationV2(
            action_id=action.action_id,
            attempt_number=attempt_number,
            status=ToolObservationStatusV2.EVIDENCE,
            failure_code=None,
            retryable=False,
            produced_evidence_ids=(evidence_id,),
            summary=(
                "Governed Executor 已成功释放受保护 Evidence。"
            ),
        )

        return InvestigationToolExecutionResultV2(
            observation=observation,
            evidence_reference=evidence,
            released_rows=result.rows,
            finalization_outcome=result.outcome.value,
            finalization_reason=result.reason_code.value,
            blocked_stage=result.blocked_stage,
            blocked_reason=result.blocked_reason,
            audit_event_fingerprint=(
                result.audit_event_fingerprint
            ),
        )

    failure_code = _map_failure_code(result)

    observation = ToolObservationV2(
        action_id=action.action_id,
        attempt_number=attempt_number,
        status=ToolObservationStatusV2.FAILURE,
        failure_code=failure_code,
        retryable=result.retryable,
        summary=(
            "Governed Executor 未释放 Evidence；"
            f"outcome={result.outcome.value}；"
            f"reason={result.reason_code.value}；"
            f"blocked_stage={result.blocked_stage or 'none'}；"
            f"blocked_reason={result.blocked_reason or 'none'}。"
        ),
    )

    return InvestigationToolExecutionResultV2(
        observation=observation,
        evidence_reference=None,
        released_rows=(),
        finalization_outcome=result.outcome.value,
        finalization_reason=result.reason_code.value,
        blocked_stage=result.blocked_stage,
        blocked_reason=result.blocked_reason,
        audit_event_fingerprint=(
            result.audit_event_fingerprint
        ),
    )
