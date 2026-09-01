from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, model_validator

from app.agents.analytical_capability_registry_v2 import (
    AnalyticalCapabilityResolutionV2,
    AnalyticalCapabilityStatusV2,
)
from app.agents.analytical_path_contract_v2 import (
    AnalyticalGrainV2,
    AnalyticalPathNodeV2,
    AnalyticalRelationDecisionV2,
    AnalyticalRelationV2,
    resolve_analytical_relation_v2,
)
from app.agents.user_investigation_intent_v2 import (
    UserInvestigationDomainV2,
)


class UserAnalyticalExecutionModeV2(str, Enum):
    """
    USER-owned analytical intent 最终进入 UI / Runtime 前的控制结果。

    NO_NEW_EVIDENCE:
        完整语义签名 SAME，不能重复执行 Query。

    INVESTIGATION:
        新方向 / 切换方向，并且已有受治理 Action。
        可以进入 bounded Investigation。

    EXPLORATION:
        用户主动要求 REFINE / SLICE / deeper geography。
        允许在受治理边界内查看，但不能伪装成系统推荐。

    HIERARCHY_STEP_REQUIRED:
        用户请求跨越已注册 hierarchy。
        例如已有 AREA，却直接请求 CITY；
        必须明确先经过 PROVINCE。

    CAPABILITY_BOUNDARY:
        语义已经理解，但当前 Query Plan / Runtime Capability
        尚未正式注册。

    CLARIFICATION / DOMAIN_CONFLICT:
        由上层 Business Analytical Intent Resolver 处理；
        本合同只消费已经 RESOLVED 的 AnalyticalPathNode。
    """

    NO_NEW_EVIDENCE = "no_new_evidence"
    INVESTIGATION = "investigation"
    EXPLORATION = "exploration"
    HIERARCHY_STEP_REQUIRED = "hierarchy_step_required"
    CAPABILITY_BOUNDARY = "capability_boundary"
    UNSUPPORTED = "unsupported"


class UserAnalyticalPathDecisionV2(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    execution_mode: UserAnalyticalExecutionModeV2
    relation: AnalyticalRelationV2

    target_node_id: str
    matched_completed_node_id: str | None = None

    action_id: str | None = None
    query_plan_name: str | None = None

    next_required_grain: AnalyticalGrainV2 | None = None
    required_grain_path: tuple[AnalyticalGrainV2, ...] = ()

    query_should_execute: bool
    consumes_investigation_budget: bool
    system_recommended: bool = False

    detail: str

    @model_validator(mode="after")
    def validate_decision(
        self,
    ) -> "UserAnalyticalPathDecisionV2":
        if not self.target_node_id.strip():
            raise ValueError("target_node_id 不能为空。")

        if not self.detail.strip():
            raise ValueError("detail 不能为空。")

        if self.execution_mode in {
            UserAnalyticalExecutionModeV2.INVESTIGATION,
            UserAnalyticalExecutionModeV2.EXPLORATION,
        }:
            if (
                self.action_id is None
                or self.query_plan_name is None
            ):
                raise ValueError(
                    "可执行决定必须绑定 server-owned action / query plan。"
                )
            if not self.query_should_execute:
                raise ValueError(
                    "可执行决定必须 query_should_execute=True。"
                )
        else:
            if (
                self.action_id is not None
                or self.query_plan_name is not None
            ):
                raise ValueError(
                    "不可执行决定不能偷偷绑定 action / query plan。"
                )
            if self.query_should_execute:
                raise ValueError(
                    "不可执行决定必须 query_should_execute=False。"
                )

        if (
            self.execution_mode
            == UserAnalyticalExecutionModeV2.INVESTIGATION
        ):
            if not self.consumes_investigation_budget:
                raise ValueError(
                    "INVESTIGATION 必须消耗 bounded Investigation Budget。"
                )

        if (
            self.execution_mode
            == UserAnalyticalExecutionModeV2.EXPLORATION
        ):
            if self.consumes_investigation_budget:
                raise ValueError(
                    "USER Exploration 不能消耗 Investigation Budget。"
                )
            if self.system_recommended:
                raise ValueError(
                    "USER Exploration 不能伪装成系统推荐。"
                )

        if (
            self.execution_mode
            == UserAnalyticalExecutionModeV2.HIERARCHY_STEP_REQUIRED
        ):
            if self.next_required_grain is None:
                raise ValueError(
                    "HIERARCHY_STEP_REQUIRED 必须声明下一层。"
                )
            if not self.required_grain_path:
                raise ValueError(
                    "HIERARCHY_STEP_REQUIRED 必须保留完整 required path。"
                )
        else:
            if self.next_required_grain is not None:
                raise ValueError(
                    "只有 HIERARCHY_STEP_REQUIRED 可以携带 next_required_grain。"
                )
            if self.required_grain_path:
                raise ValueError(
                    "只有 HIERARCHY_STEP_REQUIRED 可以携带 required_grain_path。"
                )

        return self


def _is_user_owned_deeper_geography_v2(
    target: AnalyticalPathNodeV2,
) -> bool:
    return (
        target.domain == UserInvestigationDomainV2.GEOGRAPHY
        and target.grain
        in {
            AnalyticalGrainV2.PROVINCE,
            AnalyticalGrainV2.CITY,
        }
    )


def decide_user_analytical_path_v2(
    *,
    target: AnalyticalPathNodeV2,
    completed: tuple[AnalyticalPathNodeV2, ...],
    capability: AnalyticalCapabilityResolutionV2,
) -> UserAnalyticalPathDecisionV2:
    """
    Compose:

        Semantic Target
        -> Analytical Relation
        -> Capability
        -> USER-owned Runtime Mode

    关键原则：
    1. 只有 SAME 可以作为重复查询阻断；
    2. REFINE / SLICE 不能因为父分析已做过而阻断；
    3. hierarchy 不能静默跳层；
    4. capability 不存在时要保留“已理解”的语义，不降级成别的 Action；
    5. USER-owned deeper analysis 属于 Exploration，
       不等价于 SYSTEM evidence recommendation。
    """

    relation: AnalyticalRelationDecisionV2 = (
        resolve_analytical_relation_v2(
            target=target,
            completed=completed,
        )
    )

    if relation.relation == AnalyticalRelationV2.SAME:
        return UserAnalyticalPathDecisionV2(
            execution_mode=(
                UserAnalyticalExecutionModeV2.NO_NEW_EVIDENCE
            ),
            relation=relation.relation,
            target_node_id=target.node_id,
            matched_completed_node_id=(
                relation.matched_completed_node_id
            ),
            query_should_execute=False,
            consumes_investigation_budget=False,
            detail=(
                "该目标与已有分析的完整语义签名一致。"
                "本次不重复执行 Query；这是唯一允许作为"
                " No-New-Evidence 的情况。"
            ),
        )

    if (
        relation.relation == AnalyticalRelationV2.REFINE
        and not relation.direct_target_allowed
    ):
        return UserAnalyticalPathDecisionV2(
            execution_mode=(
                UserAnalyticalExecutionModeV2
                .HIERARCHY_STEP_REQUIRED
            ),
            relation=relation.relation,
            target_node_id=target.node_id,
            matched_completed_node_id=(
                relation.matched_completed_node_id
            ),
            next_required_grain=relation.next_required_grain,
            required_grain_path=relation.required_grain_path,
            query_should_execute=False,
            consumes_investigation_budget=False,
            detail=(
                "用户请求的是合法更细粒度，但当前分析路径存在"
                "尚未经过的中间层级。系统不会静默跳级。"
            ),
        )

    if (
        capability.status
        == AnalyticalCapabilityStatusV2
        .UNDERSTOOD_NOT_REGISTERED
    ):
        return UserAnalyticalPathDecisionV2(
            execution_mode=(
                UserAnalyticalExecutionModeV2
                .CAPABILITY_BOUNDARY
            ),
            relation=relation.relation,
            target_node_id=target.node_id,
            matched_completed_node_id=(
                relation.matched_completed_node_id
            ),
            query_should_execute=False,
            consumes_investigation_budget=False,
            detail=(
                "系统已经理解该 Analytical Target 以及它与已有"
                "分析路径的关系，但对应受治理执行能力尚未注册。"
            ),
        )

    if capability.status == AnalyticalCapabilityStatusV2.UNSUPPORTED:
        return UserAnalyticalPathDecisionV2(
            execution_mode=(
                UserAnalyticalExecutionModeV2.UNSUPPORTED
            ),
            relation=relation.relation,
            target_node_id=target.node_id,
            matched_completed_node_id=(
                relation.matched_completed_node_id
            ),
            query_should_execute=False,
            consumes_investigation_budget=False,
            detail=(
                "目标语义当前不在已声明的受治理 Analytical Capability 中。"
            ),
        )

    if capability.status != AnalyticalCapabilityStatusV2.READY:
        raise ValueError(
            f"Unexpected capability status: {capability.status}"
        )

    assert capability.action_id is not None
    assert capability.query_plan_name is not None

    # REFINE / SLICE / CROSS_ANALYZE 是用户主动深入已有路径。
    # 深层 Geography 即使是 NEW / SWITCH，也属于用户明确的
    # “查看更细数据”，不冒充 SYSTEM Investigation recommendation。
    user_exploration = (
        relation.relation
        in {
            AnalyticalRelationV2.REFINE,
            AnalyticalRelationV2.SLICE,
            AnalyticalRelationV2.CROSS_ANALYZE,
        }
        or _is_user_owned_deeper_geography_v2(target)
    )

    if user_exploration:
        return UserAnalyticalPathDecisionV2(
            execution_mode=(
                UserAnalyticalExecutionModeV2.EXPLORATION
            ),
            relation=relation.relation,
            target_node_id=target.node_id,
            matched_completed_node_id=(
                relation.matched_completed_node_id
            ),
            action_id=capability.action_id,
            query_plan_name=capability.query_plan_name,
            query_should_execute=True,
            consumes_investigation_budget=False,
            system_recommended=False,
            detail=(
                "这是 USER-owned 的深入/探索意图。"
                "可以执行受治理 Query，但不能伪装成系统基于 Evidence "
                "推荐的下一调查方向，也不消耗 Investigation Budget。"
            ),
        )

    # NEW / SWITCH 的已注册顶层方向可以进入 bounded Investigation。
    return UserAnalyticalPathDecisionV2(
        execution_mode=(
            UserAnalyticalExecutionModeV2.INVESTIGATION
        ),
        relation=relation.relation,
        target_node_id=target.node_id,
        matched_completed_node_id=(
            relation.matched_completed_node_id
        ),
        action_id=capability.action_id,
        query_plan_name=capability.query_plan_name,
        query_should_execute=True,
        consumes_investigation_budget=True,
        system_recommended=False,
        detail=(
            "用户切换到一个新的已注册分析方向；"
            "可以作为 USER-owned bounded Investigation 执行一步。"
        ),
    )
