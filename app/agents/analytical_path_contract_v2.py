from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, model_validator

from app.agents.user_investigation_intent_v2 import (
    UserInvestigationDomainV2,
)


class AnalyticalRelationV2(str, Enum):
    """
    用户下一步分析意图与既有分析路径之间的关系。

    SAME:
        完整分析语义签名相同，才允许判定“重复”。

    REFINE:
        同一业务域进入更细粒度，例如：
        category -> product
        area -> province -> city

    SLICE:
        在已有分析成员内切另一维度，例如：
        老客 -> 老客中的会员结构
        护肤 -> 护肤中的渠道结构

    SWITCH:
        切换到另一个独立业务域，例如：
        category -> geography

    CROSS_ANALYZE:
        显式请求两个或以上维度交叉分析，例如：
        geography x category
        lifecycle x membership

    NEW:
        当前历史里没有足够相关的已完成分析。
    """

    SAME = "same"
    REFINE = "refine"
    SLICE = "slice"
    SWITCH = "switch"
    CROSS_ANALYZE = "cross_analyze"
    NEW = "new"


class AnalyticalOperationV2(str, Enum):
    CHANGE_BREAKDOWN = "change_breakdown"
    COMPOSITION = "composition"
    COMPARISON = "comparison"
    RANKING = "ranking"
    DETAIL = "detail"


class AnalyticalGrainV2(str, Enum):
    OVERALL = "overall"

    CHANNEL = "channel"

    CATEGORY = "category"
    PRODUCT = "product"

    AREA = "area"
    PROVINCE = "province"
    CITY = "city"

    CUSTOMER_LIFECYCLE = "customer_lifecycle"
    MEMBERSHIP_LEVEL = "membership_level"

    CAMPAIGN = "campaign"
    PROMOTION = "promotion"
    MARKETING = "marketing"


class AnalyticalFocusV2(BaseModel):
    """
    USER-owned / SYSTEM-owned Focus 的纯语义描述。

    这里不直接保存 SQL predicate。
    Runtime 仍必须把 Focus 绑定到 server-trusted scope contract。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    source_grain: AnalyticalGrainV2
    member_key: str
    member_label: str

    @model_validator(mode="after")
    def validate_focus(self) -> "AnalyticalFocusV2":
        if not self.member_key.strip():
            raise ValueError("member_key 不能为空。")
        if not self.member_label.strip():
            raise ValueError("member_label 不能为空。")
        return self


class AnalyticalPathNodeV2(BaseModel):
    """
    一个已完成或目标分析的“语义签名”。

    判断 SAME 不能只看 domain / action_id。
    必须至少同时考虑：
    - metric；
    - operation；
    - domain；
    - grain；
    - focus；
    - cross grains；
    - comparison identity；
    - effective scope identity。

    comparison_key / scope_fingerprint 由上层使用可信合同生成。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    node_id: str

    metric_name: str
    domain: UserInvestigationDomainV2
    operation: AnalyticalOperationV2
    grain: AnalyticalGrainV2

    focus: AnalyticalFocusV2 | None = None
    cross_grains: tuple[AnalyticalGrainV2, ...] = ()

    comparison_key: str | None = None
    scope_fingerprint: str | None = None

    @model_validator(mode="after")
    def validate_node(self) -> "AnalyticalPathNodeV2":
        if not self.node_id.strip():
            raise ValueError("node_id 不能为空。")
        if not self.metric_name.strip():
            raise ValueError("metric_name 不能为空。")

        if self.cross_grains:
            if len(self.cross_grains) < 2:
                raise ValueError(
                    "cross_grains 若存在，必须至少包含两个粒度。"
                )
            if len(set(self.cross_grains)) != len(self.cross_grains):
                raise ValueError("cross_grains 不能重复。")

        return self

    def semantic_signature(self) -> tuple[object, ...]:
        focus_signature = (
            None
            if self.focus is None
            else (
                self.focus.source_grain.value,
                self.focus.member_key,
            )
        )

        return (
            self.metric_name,
            self.domain.value,
            self.operation.value,
            self.grain.value,
            focus_signature,
            tuple(item.value for item in self.cross_grains),
            self.comparison_key,
            self.scope_fingerprint,
        )


class AnalyticalRelationDecisionV2(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    relation: AnalyticalRelationV2
    target_node_id: str

    matched_completed_node_id: str | None = None

    # REFINE 时记录完整层级路径。
    # 例如 AREA -> CITY 会返回 (PROVINCE, CITY)，
    # 用来阻止 UI / Runtime 静默跳级。
    required_grain_path: tuple[AnalyticalGrainV2, ...] = ()

    next_required_grain: AnalyticalGrainV2 | None = None
    direct_target_allowed: bool = True

    query_should_be_blocked_as_repeat: bool = False

    detail: str

    @model_validator(mode="after")
    def validate_decision(self) -> "AnalyticalRelationDecisionV2":
        if not self.target_node_id.strip():
            raise ValueError("target_node_id 不能为空。")
        if not self.detail.strip():
            raise ValueError("detail 不能为空。")

        if self.relation == AnalyticalRelationV2.SAME:
            if self.matched_completed_node_id is None:
                raise ValueError("SAME 必须绑定已完成分析。")
            if not self.query_should_be_blocked_as_repeat:
                raise ValueError(
                    "只有 SAME 才能作为 No-New-Evidence repeat block。"
                )
        elif self.query_should_be_blocked_as_repeat:
            raise ValueError(
                "REFINE / SLICE / SWITCH / CROSS_ANALYZE / NEW "
                "都不能被误判为重复查询。"
            )

        if self.relation == AnalyticalRelationV2.REFINE:
            if not self.required_grain_path:
                raise ValueError("REFINE 必须声明 required_grain_path。")
            if self.next_required_grain != self.required_grain_path[0]:
                raise ValueError(
                    "next_required_grain 必须是 required_grain_path 第一层。"
                )
        else:
            if self.required_grain_path:
                raise ValueError(
                    "只有 REFINE 可以携带 required_grain_path。"
                )
            if self.next_required_grain is not None:
                raise ValueError(
                    "只有 REFINE 可以携带 next_required_grain。"
                )

        return self


# 只在业务语义明确存在父子层级时注册。
# 不把“同一个大类里的不同维度”强行伪装成 hierarchy。
_HIERARCHY_CHILD_V2: dict[
    AnalyticalGrainV2,
    AnalyticalGrainV2,
] = {
    AnalyticalGrainV2.CATEGORY: AnalyticalGrainV2.PRODUCT,
    AnalyticalGrainV2.AREA: AnalyticalGrainV2.PROVINCE,
    AnalyticalGrainV2.PROVINCE: AnalyticalGrainV2.CITY,
}


def analytical_descendant_path_v2(
    *,
    ancestor: AnalyticalGrainV2,
    descendant: AnalyticalGrainV2,
) -> tuple[AnalyticalGrainV2, ...] | None:
    """
    返回从 ancestor 的下一层开始，到 descendant 为止的路径。

    AREA -> CITY = (PROVINCE, CITY)
    CATEGORY -> PRODUCT = (PRODUCT,)
    """

    if ancestor == descendant:
        return ()

    path: list[AnalyticalGrainV2] = []
    current = ancestor
    visited: set[AnalyticalGrainV2] = set()

    while current in _HIERARCHY_CHILD_V2:
        if current in visited:
            raise RuntimeError("Analytical hierarchy 出现循环。")
        visited.add(current)

        child = _HIERARCHY_CHILD_V2[current]
        path.append(child)

        if child == descendant:
            return tuple(path)

        current = child

    return None


def _best_same_v2(
    *,
    target: AnalyticalPathNodeV2,
    completed: tuple[AnalyticalPathNodeV2, ...],
) -> AnalyticalPathNodeV2 | None:
    target_signature = target.semantic_signature()

    for node in reversed(completed):
        if node.semantic_signature() == target_signature:
            return node

    return None


def _slice_source_v2(
    *,
    target: AnalyticalPathNodeV2,
    completed: tuple[AnalyticalPathNodeV2, ...],
) -> AnalyticalPathNodeV2 | None:
    if target.focus is None:
        return None

    for node in reversed(completed):
        if (
            node.metric_name == target.metric_name
            and node.grain == target.focus.source_grain
            and node.comparison_key == target.comparison_key
            and node.scope_fingerprint == target.scope_fingerprint
        ):
            return node

    return None


def _refine_source_v2(
    *,
    target: AnalyticalPathNodeV2,
    completed: tuple[AnalyticalPathNodeV2, ...],
) -> tuple[
    AnalyticalPathNodeV2,
    tuple[AnalyticalGrainV2, ...],
] | None:
    candidates: list[
        tuple[
            AnalyticalPathNodeV2,
            tuple[AnalyticalGrainV2, ...],
        ]
    ] = []

    for node in completed:
        if node.metric_name != target.metric_name:
            continue
        if node.domain != target.domain:
            continue
        if node.operation != target.operation:
            continue
        if node.focus != target.focus:
            continue
        if node.comparison_key != target.comparison_key:
            continue
        if node.scope_fingerprint != target.scope_fingerprint:
            continue

        path = analytical_descendant_path_v2(
            ancestor=node.grain,
            descendant=target.grain,
        )

        if path:
            candidates.append((node, path))

    if not candidates:
        return None

    # 优先选择离 target 最近的已完成父层，
    # 避免已经完成 Province 后仍从 Area 重新开始。
    candidates.sort(
        key=lambda item: len(item[1])
    )

    return candidates[0]


def resolve_analytical_relation_v2(
    *,
    target: AnalyticalPathNodeV2,
    completed: tuple[AnalyticalPathNodeV2, ...],
) -> AnalyticalRelationDecisionV2:
    """
    通用 Analytical Path Relation Resolver。

    判定优先级：
    1. EXACT SAME；
    2. CROSS_ANALYZE；
    3. SLICE；
    4. REFINE；
    5. SWITCH；
    6. NEW。

    只有 EXACT SAME 才允许阻止 Query 作为“重复执行”。
    """

    same = _best_same_v2(
        target=target,
        completed=completed,
    )

    if same is not None:
        return AnalyticalRelationDecisionV2(
            relation=AnalyticalRelationV2.SAME,
            target_node_id=target.node_id,
            matched_completed_node_id=same.node_id,
            query_should_be_blocked_as_repeat=True,
            detail=(
                "目标分析与已有分析的 metric / operation / domain / grain / "
                "focus / comparison / scope 语义签名完全一致。"
                "只有这种情况才允许判定为 No New Evidence。"
            ),
        )

    if len(target.cross_grains) >= 2:
        return AnalyticalRelationDecisionV2(
            relation=AnalyticalRelationV2.CROSS_ANALYZE,
            target_node_id=target.node_id,
            query_should_be_blocked_as_repeat=False,
            detail=(
                "目标显式要求多个分析粒度交叉；"
                "不能因为其中某个单维度已经分析过就判定为重复。"
            ),
        )

    slice_source = _slice_source_v2(
        target=target,
        completed=completed,
    )

    if slice_source is not None:
        return AnalyticalRelationDecisionV2(
            relation=AnalyticalRelationV2.SLICE,
            target_node_id=target.node_id,
            matched_completed_node_id=slice_source.node_id,
            query_should_be_blocked_as_repeat=False,
            detail=(
                "目标是在已有分析成员 Focus 内切换到新的分析粒度；"
                "它是新的 Slice，不是对原查询的重复执行。"
            ),
        )

    refine = _refine_source_v2(
        target=target,
        completed=completed,
    )

    if refine is not None:
        source, path = refine

        return AnalyticalRelationDecisionV2(
            relation=AnalyticalRelationV2.REFINE,
            target_node_id=target.node_id,
            matched_completed_node_id=source.node_id,
            required_grain_path=path,
            next_required_grain=path[0],
            direct_target_allowed=(len(path) == 1),
            query_should_be_blocked_as_repeat=False,
            detail=(
                "目标是同一业务域的更细分析粒度。"
                "必须遵守已注册层级路径，不能因为父层已经执行过而判定为重复。"
            ),
        )

    if completed and any(
        node.domain != target.domain
        for node in completed
    ):
        # 这里的 SWITCH 表示 target 相对于当前已存在分析路径
        # 是一个独立业务域。它仍需 Capability / Scope 检查。
        return AnalyticalRelationDecisionV2(
            relation=AnalyticalRelationV2.SWITCH,
            target_node_id=target.node_id,
            query_should_be_blocked_as_repeat=False,
            detail=(
                "目标切换到另一个业务分析域；"
                "应重新做 Capability / Scope 检查，而不是按重复查询阻断。"
            ),
        )

    return AnalyticalRelationDecisionV2(
        relation=AnalyticalRelationV2.NEW,
        target_node_id=target.node_id,
        query_should_be_blocked_as_repeat=False,
        detail=(
            "当前历史中没有足够相关的已完成分析来形成 SAME / REFINE / "
            "SLICE / CROSS_ANALYZE 关系；按新分析意图继续做能力检查。"
        ),
    )
