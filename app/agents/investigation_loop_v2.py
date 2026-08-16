from __future__ import annotations

from collections.abc import Callable
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.agents.investigation_contracts_v2 import (
    InsightContractV2,
    ToolFailureCodeV2,
)
from app.agents.investigation_planner_v2 import (
    AvailableInvestigationActionV2,
    InvestigationStateV2,
    PlannerDecisionTypeV2,
    PlannerDecisionV2,
)


class ToolObservationStatusV2(str, Enum):
    EVIDENCE = "evidence"
    NO_DATA = "no_data"
    FAILURE = "failure"


class LoopDirectiveV2(str, Enum):
    RETRY = "retry"
    REPLAN = "replan"
    RECOVER = "recover"
    STOP = "stop"


class InvestigationStopReasonV2(str, Enum):
    EVIDENCE_SUFFICIENT = "evidence_sufficient"
    INVESTIGATION_BUDGET_EXHAUSTED = "investigation_budget_exhausted"
    NO_LEGAL_ACTION = "no_legal_action"
    RETRY_BUDGET_EXHAUSTED = "retry_budget_exhausted"
    NON_RETRYABLE_FAILURE = "non_retryable_failure"


class InvestigationBudgetPolicyV2(BaseModel):
    """
    Day86 Agent Loop 的逻辑调查预算。

    max_investigation_steps 统计不同的调查动作，不统计同一个动作的 Retry。
    max_retries_per_action 单独限制每个动作最多允许 Retry 几次。

    注意：
    Retry 虽然不额外消耗“逻辑调查步数”，但真实执行时仍然会消耗数据库、
    timeout、token 等既有底层 Execution Budget。
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    max_investigation_steps: int = Field(ge=1)
    max_retries_per_action: int = Field(ge=0)


class ToolObservationV2(BaseModel):
    """
    一次受控 Tool 执行后返回的“受保护观察结果”。

    EVIDENCE：
    Tool 成功返回了可以释放的新证据。

    NO_DATA：
    执行本身成功，但当前时间窗口 / Scope 下没有数据。
    NO_DATA 不是 0，也不能凭空制造 evidence。

    FAILURE：
    本次执行失败，并携带一个已声明的 failure_code。
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    action_id: str
    attempt_number: int = Field(ge=1)
    status: ToolObservationStatusV2
    failure_code: ToolFailureCodeV2 | None = None
    retryable: bool = False
    produced_evidence_ids: tuple[str, ...] = ()
    summary: str

    @model_validator(mode="after")
    def validate_observation(self) -> "ToolObservationV2":
        if not self.action_id.strip():
            raise ValueError("action_id 不能为空。")

        if not self.summary.strip():
            raise ValueError("Observation summary 不能为空。")

        if any(
            not evidence_id.strip()
            for evidence_id in self.produced_evidence_ids
        ):
            raise ValueError(
                "produced_evidence_ids 不能包含空值。"
            )

        if (
            len(set(self.produced_evidence_ids))
            != len(self.produced_evidence_ids)
        ):
            raise ValueError(
                "produced_evidence_ids 不能包含重复值。"
            )

        if self.status == ToolObservationStatusV2.EVIDENCE:
            if self.failure_code is not None:
                raise ValueError(
                    "EVIDENCE 类型的 Observation 不能携带 failure_code。"
                )
            if self.retryable:
                raise ValueError(
                    "EVIDENCE 类型的 Observation 不能标记为 retryable。"
                )
            if not self.produced_evidence_ids:
                raise ValueError(
                    "EVIDENCE 类型的 Observation 必须包含 produced evidence。"
                )

        elif self.status == ToolObservationStatusV2.NO_DATA:
            if self.failure_code != ToolFailureCodeV2.NO_DATA:
                raise ValueError(
                    "NO_DATA 类型的 Observation 必须携带 NO_DATA failure_code。"
                )
            if self.retryable:
                raise ValueError(
                    "NO_DATA 是有效执行结果，不能标记为 retryable。"
                )
            if self.produced_evidence_ids:
                raise ValueError(
                    "NO_DATA 类型的 Observation 不能凭空生成 produced evidence。"
                )

        else:
            if self.failure_code is None:
                raise ValueError(
                    "FAILURE 类型的 Observation 必须包含 failure_code。"
                )
            if self.failure_code == ToolFailureCodeV2.NO_DATA:
                raise ValueError(
                    "NO_DATA 必须使用 NO_DATA Observation status。"
                )
            if self.produced_evidence_ids:
                raise ValueError(
                    "FAILURE 类型的 Observation 不能携带 produced evidence。"
                )

        return self


class InvestigationLoopStateV2(BaseModel):
    """
    Day86 的 Loop 状态。

    planner_state：
    继续复用 Day85 的可信 Planner State，保存当前 Insight、
    completed_action_ids、available_actions 与 clarification_requirement。

    observation_history：
    保存本次调查中已经发生过的 Tool Observation。
    它属于当前一次调查的短期 State，不是 Long-term Memory。

    investigation_steps_used：
    统计已经开始过多少个不同调查动作。
    Retry 不重复增加这个数字。
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    planner_state: InvestigationStateV2
    budget_policy: InvestigationBudgetPolicyV2
    investigation_steps_used: int = Field(default=0, ge=0)
    observation_history: tuple[ToolObservationV2, ...] = ()

    @model_validator(mode="after")
    def validate_loop_state(self) -> "InvestigationLoopStateV2":
        if (
            self.investigation_steps_used
            > self.budget_policy.max_investigation_steps
        ):
            raise ValueError(
                "investigation_steps_used 不能超过 max_investigation_steps。"
            )

        seen_attempts: set[tuple[str, int]] = set()
        for observation in self.observation_history:
            key = (
                observation.action_id,
                observation.attempt_number,
            )
            if key in seen_attempts:
                raise ValueError(
                    "observation_history 不能重复记录同一个 action attempt。"
                )
            seen_attempts.add(key)

        return self


class LoopControlDecisionV2(BaseModel):
    """一次 Observation 后，由确定性规则给出的 Loop 控制决策。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    directive: LoopDirectiveV2
    action_id: str | None = None
    stop_reason: InvestigationStopReasonV2 | None = None
    next_investigation_steps_used: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_decision(self) -> "LoopControlDecisionV2":
        if self.directive == LoopDirectiveV2.RETRY:
            if self.action_id is None or not self.action_id.strip():
                raise ValueError("RETRY 必须指定 action_id。")
            if self.stop_reason is not None:
                raise ValueError("RETRY 不能携带 stop_reason。")

        elif self.directive in {
            LoopDirectiveV2.REPLAN,
            LoopDirectiveV2.RECOVER,
        }:
            if self.action_id is not None:
                raise ValueError(
                    "REPLAN / RECOVER 不能提前指定下一步 action。"
                )
            if self.stop_reason is not None:
                raise ValueError(
                    "REPLAN / RECOVER 不能携带 stop_reason。"
                )

        else:
            if self.action_id is not None:
                raise ValueError("STOP 不能携带 action_id。")
            if self.stop_reason is None:
                raise ValueError("STOP 必须包含 stop_reason。")

        return self


class InvestigationLoopTransitionV2(BaseModel):
    """
    一次 Observation 处理完成后的完整状态迁移结果。

    control_decision：
    下一步控制动作是 RETRY / REPLAN / RECOVER / STOP 中的哪一种。

    next_state：
    已经写入 Observation、更新步数，并按需要刷新 Planner State 后的状态。
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    control_decision: LoopControlDecisionV2
    next_state: InvestigationLoopStateV2


PlannerInvokerV2 = Callable[[InvestigationStateV2], PlannerDecisionV2]



class InvestigationSessionPolicyV2(BaseModel):
    """
    围绕“同一个业务问题”的累计调查预算。

    max_rounds：
    用户明确要求“继续调查”时，最多允许开启多少轮。

    max_total_investigation_steps：
    所有轮次累计最多允许执行多少个新的调查动作。

    这一层解决：
    “每轮 3 步，但用户不断说继续，会不会变成无限调查？”
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    max_rounds: int = Field(ge=1)
    max_total_investigation_steps: int = Field(ge=1)


class InvestigationSessionStateV2(BaseModel):
    """
    一次 Investigation Session 的结构化状态。

    loop_state：
    当前这一轮的 Day86 Loop State。

    completed_round_steps_used：
    之前已经结束的轮次累计用了多少 Investigation Step。
    当前轮的步数仍保存在 loop_state.investigation_steps_used 中。

    round_number 从 1 开始。
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    loop_state: InvestigationLoopStateV2
    session_policy: InvestigationSessionPolicyV2
    round_number: int = Field(default=1, ge=1)
    completed_round_steps_used: int = Field(default=0, ge=0)

    @property
    def total_steps_used(self) -> int:
        return (
            self.completed_round_steps_used
            + self.loop_state.investigation_steps_used
        )

    @model_validator(mode="after")
    def validate_session_state(self) -> "InvestigationSessionStateV2":
        if self.round_number > self.session_policy.max_rounds:
            raise ValueError(
                "round_number 不能超过 Session max_rounds。"
            )

        if (
            self.total_steps_used
            > self.session_policy.max_total_investigation_steps
        ):
            raise ValueError(
                "Session 累计 Investigation Step 不能超过总预算。"
            )

        return self


class InvestigationStopStatusV2(BaseModel):
    """
    面向后续 Answer / UI 的停止状态。

    stop_reason：
    为什么这一轮停止。

    uninvestigated_action_ids：
    当前仍存在、但本轮还没执行的合法调查方向。

    can_continue：
    是否允许用户明确发起下一轮继续调查。

    注意：
    Budget Exhausted 不等于 Investigation Complete。
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    stop_reason: InvestigationStopReasonV2
    evidence_sufficient: bool
    uninvestigated_action_ids: tuple[str, ...]
    can_continue: bool
    current_round: int = Field(ge=1)
    max_rounds: int = Field(ge=1)
    total_steps_used: int = Field(ge=0)
    max_total_investigation_steps: int = Field(ge=1)
    detail: str


class InvestigationReplanResultV2(BaseModel):
    """
    Step C：State 更新完成后，再次交给 Planner 得到的新决策。

    transition：
    保存刚刚那次 Observation 如何把旧 State 推进成新 State。

    planner_decision：
    Planner 基于“新 State”作出的下一步选择。

    这两个对象同时保留，方便后续 Graph / Trace 清楚回答：
    “为什么上一轮结束后，会走到这一轮的这个动作？”
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    transition: InvestigationLoopTransitionV2
    planner_decision: PlannerDecisionV2


def _available_action_ids(
    actions: tuple[AvailableInvestigationActionV2, ...],
) -> set[str]:
    return {
        action.action_id
        for action in actions
    }


def _expected_attempt_number(
    *,
    state: InvestigationLoopStateV2,
    action_id: str,
) -> int:
    attempts = [
        item.attempt_number
        for item in state.observation_history
        if item.action_id == action_id
    ]

    if not attempts:
        return 1

    return max(attempts) + 1


def _validate_observation_against_state(
    *,
    state: InvestigationLoopStateV2,
    observation: ToolObservationV2,
) -> AvailableInvestigationActionV2:
    if state.planner_state.clarification_requirement is not None:
        raise ValueError(
            "clarification 尚未解决时，不允许执行 Tool。"
        )

    actions_by_id = {
        action.action_id: action
        for action in state.planner_state.available_actions
    }
    selected_action = actions_by_id.get(observation.action_id)
    if selected_action is None:
        raise ValueError(
            "Observation 的 action_id 必须来自当前 available_actions。"
        )

    expected_attempt = _expected_attempt_number(
        state=state,
        action_id=observation.action_id,
    )
    if observation.attempt_number != expected_attempt:
        raise ValueError(
            "Observation attempt_number 必须按当前 action 的执行历史连续递增。"
        )

    if (
        observation.failure_code is not None
        and observation.failure_code
        not in selected_action.tool_contract.failure_semantics
    ):
        raise ValueError(
            "本次 Observation 的 failure_code 未在所选 Tool Contract 中声明。"
        )

    return selected_action


def _validate_refreshed_insight(
    *,
    current_insight: InsightContractV2,
    refreshed_insight: InsightContractV2,
    observation: ToolObservationV2,
) -> None:
    if (
        refreshed_insight.analysis_scope
        != current_insight.analysis_scope
    ):
        raise ValueError(
            "Day86 Step B 不允许在 State 更新时静默改变 analysis_scope。"
        )

    if observation.status != ToolObservationStatusV2.EVIDENCE:
        return

    refreshed_ids = {
        item.evidence_id
        for item in refreshed_insight.evidence
    }
    missing_ids = (
        set(observation.produced_evidence_ids)
        - refreshed_ids
    )
    if missing_ids:
        raise ValueError(
            "Observation 声称产生的新 evidence 必须真实存在于 refreshed Insight 中："
            f"{sorted(missing_ids)}"
        )


def decide_loop_control_v2(
    *,
    state: InvestigationLoopStateV2,
    observation: ToolObservationV2,
    evidence_sufficient: bool = False,
    refreshed_available_actions: tuple[
        AvailableInvestigationActionV2, ...
    ] | None = None,
) -> LoopControlDecisionV2:
    """
    根据一次 Tool Observation，确定性判断 Loop 下一步允许做什么。

    重要顺序：
    Observation 之后，新的 Evidence 可能会解锁新的调查动作。
    因此 REPLAN / STOP 的判断优先使用 refreshed_available_actions，
    不能只依赖“执行前”的旧 available_actions。

    规则：
    - 新动作第一次执行消耗 1 个 Investigation Step；
    - Retry 不重复消耗 Investigation Step；
    - FAILURE 是否允许 Retry，由真实 Executor 返回的 retryable 决定；
    - Retry Budget 只决定“还能不能继续重试”，不能把 non-retryable
      的治理失败强行改成 retryable；
    - NO_DATA 是有效 Observation，不转换成 0；
    - 有新的合法方向时进入 REPLAN / RECOVER；
    - 证据足够、预算耗尽或没有合法方向时 STOP。
    """

    _validate_observation_against_state(
        state=state,
        observation=observation,
    )

    step_increment = (
        1
        if observation.attempt_number == 1
        else 0
    )
    next_steps_used = (
        state.investigation_steps_used
        + step_increment
    )

    if next_steps_used > state.budget_policy.max_investigation_steps:
        raise ValueError(
            "Investigation Budget 已耗尽后，不允许执行新的调查动作。"
        )

    if (
        observation.status == ToolObservationStatusV2.FAILURE
        and observation.retryable
    ):
        retries_already_used = observation.attempt_number - 1
        if (
            retries_already_used
            < state.budget_policy.max_retries_per_action
        ):
            return LoopControlDecisionV2(
                directive=LoopDirectiveV2.RETRY,
                action_id=observation.action_id,
                next_investigation_steps_used=next_steps_used,
            )

    if evidence_sufficient:
        return LoopControlDecisionV2(
            directive=LoopDirectiveV2.STOP,
            stop_reason=InvestigationStopReasonV2.EVIDENCE_SUFFICIENT,
            next_investigation_steps_used=next_steps_used,
        )

    if next_steps_used >= state.budget_policy.max_investigation_steps:
        return LoopControlDecisionV2(
            directive=LoopDirectiveV2.STOP,
            stop_reason=(
                InvestigationStopReasonV2.INVESTIGATION_BUDGET_EXHAUSTED
            ),
            next_investigation_steps_used=next_steps_used,
        )

    if refreshed_available_actions is None:
        current_actions = tuple(
            action
            for action in state.planner_state.available_actions
            if action.action_id != observation.action_id
        )
        next_actions = current_actions
    else:
        next_actions = refreshed_available_actions

    if observation.status == ToolObservationStatusV2.FAILURE:
        if next_actions:
            return LoopControlDecisionV2(
                directive=LoopDirectiveV2.RECOVER,
                next_investigation_steps_used=next_steps_used,
            )

        if observation.retryable:
            stop_reason = (
                InvestigationStopReasonV2.RETRY_BUDGET_EXHAUSTED
            )
        else:
            stop_reason = (
                InvestigationStopReasonV2.NON_RETRYABLE_FAILURE
            )

        return LoopControlDecisionV2(
            directive=LoopDirectiveV2.STOP,
            stop_reason=stop_reason,
            next_investigation_steps_used=next_steps_used,
        )

    if not next_actions:
        return LoopControlDecisionV2(
            directive=LoopDirectiveV2.STOP,
            stop_reason=InvestigationStopReasonV2.NO_LEGAL_ACTION,
            next_investigation_steps_used=next_steps_used,
        )

    return LoopControlDecisionV2(
        directive=LoopDirectiveV2.REPLAN,
        next_investigation_steps_used=next_steps_used,
    )


def advance_investigation_loop_v2(
    *,
    state: InvestigationLoopStateV2,
    observation: ToolObservationV2,
    refreshed_insight: InsightContractV2 | None = None,
    refreshed_available_actions: tuple[
        AvailableInvestigationActionV2, ...
    ] | None = None,
    evidence_sufficient: bool = False,
) -> InvestigationLoopTransitionV2:
    """
    把一次 Observation 真正写回 Loop State。

    这是 Day86 Step B 的核心：

    1. 校验 Observation 确实来自当前合法 action；
    2. 判断 RETRY / REPLAN / RECOVER / STOP；
    3. 把 Observation 写入 observation_history；
    4. 更新 investigation_steps_used；
    5. 如果当前 action 已经结束，则写入 completed_action_ids；
    6. 使用系统可信层传入的 refreshed Insight / available actions
       构造下一轮 Planner State。

    注意：
    refreshed_insight 与 refreshed_available_actions 必须来自系统可信逻辑，
    不能由 LLM 自由提交。

    真实 Tool Executor、真实数据库与 LLM re-plan orchestration
    仍不属于 Step B。
    """

    selected_action = _validate_observation_against_state(
        state=state,
        observation=observation,
    )

    control = decide_loop_control_v2(
        state=state,
        observation=observation,
        evidence_sufficient=evidence_sufficient,
        refreshed_available_actions=refreshed_available_actions,
    )

    next_history = (
        *state.observation_history,
        observation,
    )

    if control.directive == LoopDirectiveV2.RETRY:
        next_state = InvestigationLoopStateV2(
            planner_state=state.planner_state,
            budget_policy=state.budget_policy,
            investigation_steps_used=(
                control.next_investigation_steps_used
            ),
            observation_history=next_history,
        )
        return InvestigationLoopTransitionV2(
            control_decision=control,
            next_state=next_state,
        )

    next_insight = (
        refreshed_insight
        if refreshed_insight is not None
        else state.planner_state.insight
    )
    _validate_refreshed_insight(
        current_insight=state.planner_state.insight,
        refreshed_insight=next_insight,
        observation=observation,
    )

    completed_action_ids = (
        *state.planner_state.completed_action_ids,
        observation.action_id,
    )

    if refreshed_available_actions is None:
        next_actions = tuple(
            action
            for action in state.planner_state.available_actions
            if action.action_id != selected_action.action_id
        )
    else:
        next_actions = refreshed_available_actions

    if observation.action_id in _available_action_ids(next_actions):
        raise ValueError(
            "已经结束的 action 不能继续留在 refreshed available_actions 中。"
        )

    next_planner_state = InvestigationStateV2(
        insight=next_insight,
        completed_action_ids=completed_action_ids,
        available_actions=next_actions,
        clarification_requirement=(
            state.planner_state.clarification_requirement
        ),
    )

    next_state = InvestigationLoopStateV2(
        planner_state=next_planner_state,
        budget_policy=state.budget_policy,
        investigation_steps_used=(
            control.next_investigation_steps_used
        ),
        observation_history=next_history,
    )

    return InvestigationLoopTransitionV2(
        control_decision=control,
        next_state=next_state,
    )


def _validate_replanned_decision_against_state(
    *,
    state: InvestigationStateV2,
    decision: PlannerDecisionV2,
) -> None:
    """
    对 Planner 已经给出的 Decision 再做一层编排边界校验。

    正常情况下，Day85 Planner 内部已经完成 Proposal → deterministic validation。
    但 Day86 Loop 仍不盲信一个外部 callback 的返回值：

    - SELECT_TOOL 必须仍然来自“新 State”的 available_actions；
    - selected_action 必须和 State 中的可信 Tool Contract / 绑定参数完全一致；
    - supporting evidence 必须真实存在于“新 State”的 Insight；
    - 没有可信 clarification prerequisite 时，不允许凭空 CLARIFY。

    这一层不是重复让 LLM 判断，而是 defense-in-depth。
    """

    if decision.decision_type == PlannerDecisionTypeV2.CLARIFY:
        if state.clarification_requirement is None:
            raise ValueError(
                "新的 Planner Decision 不能在没有可信 prerequisite 时凭空 CLARIFY。"
            )
        return

    if decision.selected_action is None:
        raise ValueError(
            "SELECT_TOOL 类型的 Planner Decision 必须包含 selected_action。"
        )

    actions_by_id = {
        action.action_id: action
        for action in state.available_actions
    }
    trusted_action = actions_by_id.get(
        decision.selected_action.action_id
    )
    if trusted_action is None:
        raise ValueError(
            "重新规划后的 action 必须来自新 State 的 available_actions。"
        )

    if decision.selected_action != trusted_action:
        raise ValueError(
            "重新规划后的 selected_action 不能修改可信 Tool Contract 或绑定参数。"
        )

    available_evidence_ids = {
        item.evidence_id
        for item in state.insight.evidence
    }
    missing_evidence = (
        set(decision.supporting_evidence_ids)
        - available_evidence_ids
    )
    if missing_evidence:
        raise ValueError(
            "重新规划后的 supporting evidence 必须来自新 State："
            f"{sorted(missing_evidence)}"
        )


def replan_after_transition_v2(
    *,
    transition: InvestigationLoopTransitionV2,
    planner: PlannerInvokerV2,
) -> InvestigationReplanResultV2:
    """
    Day86 Step C：把 Step B 生成的“新 State”真正再次交给 Planner。

    只允许两种控制结果进入 Planner：
    - REPLAN：执行成功 / NO_DATA 后，根据新证据重新选择方向；
    - RECOVER：当前动作失败且不再机械 Retry，但仍有其他合法路径。

    RETRY 不调用 Planner：
    因为它仍然是同一个动作，应该直接再次执行。

    STOP 不调用 Planner：
    因为 Loop 已经触发明确停止条件，再调用模型会绕过 Stop Boundary。

    注意：
    planner 是一个注入的调用接口。测试时可以使用 deterministic planner；
    真实运行时再接 Day85 的 DeepSeek Planner Adapter。
    Loop Core 不直接依赖具体模型。
    """

    directive = transition.control_decision.directive
    if directive not in {
        LoopDirectiveV2.REPLAN,
        LoopDirectiveV2.RECOVER,
    }:
        raise ValueError(
            "只有 REPLAN / RECOVER transition 才允许再次调用 Planner。"
        )

    planner_state = transition.next_state.planner_state

    if (
        planner_state.clarification_requirement is None
        and not planner_state.available_actions
    ):
        raise ValueError(
            "新 State 没有合法 available_actions，不能继续调用 Planner。"
        )

    decision = planner(planner_state)

    _validate_replanned_decision_against_state(
        state=planner_state,
        decision=decision,
    )

    return InvestigationReplanResultV2(
        transition=transition,
        planner_decision=decision,
    )


def build_investigation_stop_status_v2(
    *,
    session: InvestigationSessionStateV2,
    transition: InvestigationLoopTransitionV2,
    evidence_sufficient: bool,
) -> InvestigationStopStatusV2:
    """
    把 Loop 的 STOP 转换成更完整的 Session Stop Status。

    这里明确区分：
    - “证据已经足够，所以停止”
    - “本轮预算用完，但还有方向没查”
    - “没有合法动作可继续”

    只有当前 transition 真的是 STOP 才允许调用。
    """

    control = transition.control_decision
    if control.directive != LoopDirectiveV2.STOP:
        raise ValueError(
            "只有 STOP transition 才能生成 InvestigationStopStatusV2。"
        )

    if control.stop_reason is None:
        raise ValueError(
            "STOP transition 必须包含 stop_reason。"
        )

    remaining_action_ids = tuple(
        action.action_id
        for action in transition.next_state.planner_state.available_actions
    )

    total_steps_used = (
        session.completed_round_steps_used
        + transition.next_state.investigation_steps_used
    )

    session_step_remaining = (
        total_steps_used
        < session.session_policy.max_total_investigation_steps
    )
    round_remaining = (
        session.round_number
        < session.session_policy.max_rounds
    )

    can_continue = (
        control.stop_reason
        == InvestigationStopReasonV2.INVESTIGATION_BUDGET_EXHAUSTED
        and not evidence_sufficient
        and bool(remaining_action_ids)
        and session_step_remaining
        and round_remaining
    )

    if evidence_sufficient:
        detail = (
            "当前 Evidence 已足以支持有边界的结论，本轮调查停止。"
        )
    elif (
        control.stop_reason
        == InvestigationStopReasonV2.INVESTIGATION_BUDGET_EXHAUSTED
    ):
        if can_continue:
            detail = (
                "本轮 Investigation Budget 已耗尽，但仍有合法方向未调查；"
                "用户可以明确要求继续下一轮。"
            )
        else:
            detail = (
                "本轮 Investigation Budget 已耗尽，且当前 Session "
                "已不允许继续分配新的调查轮次或步数。"
            )
    elif (
        control.stop_reason
        == InvestigationStopReasonV2.NO_LEGAL_ACTION
    ):
        detail = (
            "当前没有剩余合法调查动作；现有 Evidence 可能仍不足，"
            "但系统不能凭空扩展 Tool / Permission。"
        )
    else:
        detail = (
            "当前动作失败且无法在既有边界内继续本轮调查。"
        )

    return InvestigationStopStatusV2(
        stop_reason=control.stop_reason,
        evidence_sufficient=evidence_sufficient,
        uninvestigated_action_ids=remaining_action_ids,
        can_continue=can_continue,
        current_round=session.round_number,
        max_rounds=session.session_policy.max_rounds,
        total_steps_used=total_steps_used,
        max_total_investigation_steps=(
            session.session_policy.max_total_investigation_steps
        ),
        detail=detail,
    )


def continue_investigation_session_v2(
    *,
    session: InvestigationSessionStateV2,
    stop_status: InvestigationStopStatusV2,
    transition: InvestigationLoopTransitionV2,
    user_requested_continue: bool,
) -> InvestigationSessionStateV2:
    """
    用户明确要求“继续调查”后开启下一轮。

    保留：
    - Insight / Evidence；
    - observation_history；
    - completed_action_ids；
    - 当前剩余 available_actions；
    - 之前轮次消耗的累计步数。

    只重置：
    - 当前 Round 的 investigation_steps_used → 0。

    系统绝不能自己偷偷续预算。
    """

    if not user_requested_continue:
        raise ValueError(
            "没有用户明确 continuation 请求，不能自动开启下一轮。"
        )

    if not stop_status.can_continue:
        raise ValueError(
            "当前 Stop Status 不允许继续 Investigation Session。"
        )

    if (
        transition.control_decision.directive
        != LoopDirectiveV2.STOP
    ):
        raise ValueError(
            "只有已经 STOP 的上一轮才能开启下一轮。"
        )

    next_round_number = session.round_number + 1

    completed_steps = (
        session.completed_round_steps_used
        + transition.next_state.investigation_steps_used
    )

    if (
        next_round_number
        > session.session_policy.max_rounds
    ):
        raise ValueError(
            "Session Round Budget 已耗尽。"
        )

    if (
        completed_steps
        >= session.session_policy.max_total_investigation_steps
    ):
        raise ValueError(
            "Session Total Investigation Step Budget 已耗尽。"
        )

    next_loop_state = transition.next_state.model_copy(
        update={
            "investigation_steps_used": 0,
        }
    )

    return InvestigationSessionStateV2(
        loop_state=next_loop_state,
        session_policy=session.session_policy,
        round_number=next_round_number,
        completed_round_steps_used=completed_steps,
    )

