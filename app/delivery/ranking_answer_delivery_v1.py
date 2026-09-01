from __future__ import annotations

import re
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator

from app.agents.evidence_pack_delivery_v2 import (
    EvidencePackDeliveryV2,
)
from app.agents.evidence_pack_v2 import EvidenceTypeV2
from app.semantic_layer.time_comparison_contract_v2 import (
    TimeWindowReferenceV2,
)


RANKING_ANSWER_DELIVERY_VERSION = "ranking_answer_delivery_v1_0"
PRIORITY_ASSESSMENT_VERSION = "priority_assessment_v1_0"


class RankingIntentV1(str, Enum):
    BEST = "best"
    WORST = "worst"
    HIGHEST = "highest"
    LOWEST = "lowest"


class MetricRankingPreferenceV1(str, Enum):
    HIGHER_IS_BETTER = "higher_is_better"
    LOWER_IS_BETTER = "lower_is_better"
    NEUTRAL = "neutral"


class RankingSelectionDirectionV1(str, Enum):
    MAX = "max"
    MIN = "min"


class PriorityEvidenceStatusV1(str, Enum):
    """
    业务优先级证据状态。

    PARTIAL 表示：
    当前证据足够形成“调查优先候选”，
    但不足以形成“最终业务优先级”结论。
    """

    PARTIAL = "partial"


class PriorityAssessmentV1(BaseModel):
    """
    F03 的确定性 Priority + Evidence Sufficiency 结论。

    只允许基于当前已释放 Protected Result：
    - 不重新查询；
    - 不访问 blocked/raw rows；
    - 不把单一退款率事实升级为因果或最终业务优先级。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    contract_version: str = PRIORITY_ASSESSMENT_VERSION
    policy_version: str = "refund_rate_category_triage_v1"

    metric_name: str
    result_grain: str

    candidate_member_labels: tuple[str, ...]
    candidate_value: Decimal
    is_tie: bool

    screening_rule: str
    evidence_status: PriorityEvidenceStatusV1

    can_confirm: tuple[str, ...]
    cannot_confirm: tuple[str, ...]
    next_evidence_needed: tuple[str, ...]

    evidence_id: str
    analysis_window: TimeWindowReferenceV2
    scope_summary: str | None = None

    @model_validator(mode="after")
    def validate_priority_assessment(
        self,
    ) -> "PriorityAssessmentV1":
        if self.metric_name != "refund_rate":
            raise ValueError(
                "PriorityAssessmentV1 当前只批准 refund_rate。"
            )

        if self.result_grain != "category":
            raise ValueError(
                "PriorityAssessmentV1 当前只批准 category grain。"
            )

        if not self.candidate_member_labels:
            raise ValueError(
                "Priority assessment requires at least one candidate."
            )

        if self.is_tie != (
            len(self.candidate_member_labels) > 1
        ):
            raise ValueError(
                "is_tie must match candidate cardinality."
            )

        if not self.evidence_id.strip():
            raise ValueError(
                "Priority assessment requires evidence_id."
            )

        if not self.can_confirm:
            raise ValueError(
                "Priority assessment requires can_confirm."
            )

        if not self.cannot_confirm:
            raise ValueError(
                "Priority assessment requires cannot_confirm."
            )

        return self


class RankingConclusionV1(BaseModel):
    """
    Result Protection 之后的确定性 Ranking 结论。

    结论只在当前已释放 ProtectedResult 范围内成立；
    不重新查询数据库，也不访问 blocked/raw rows。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    contract_version: str = RANKING_ANSWER_DELIVERY_VERSION

    metric_name: str
    result_grain: str
    ranking_intent: RankingIntentV1
    ranking_preference: MetricRankingPreferenceV1
    selection_direction: RankingSelectionDirectionV1

    member_field: str
    metric_field: str
    winning_member_labels: tuple[str, ...]
    winning_value: Decimal
    is_tie: bool

    evidence_id: str
    analysis_window: TimeWindowReferenceV2
    scope_summary: str | None = None

    @model_validator(mode="after")
    def validate_conclusion(
        self,
    ) -> "RankingConclusionV1":
        if not self.metric_name.strip():
            raise ValueError("metric_name cannot be empty.")
        if not self.result_grain.strip():
            raise ValueError("result_grain cannot be empty.")
        if not self.member_field.strip():
            raise ValueError("member_field cannot be empty.")
        if not self.metric_field.strip():
            raise ValueError("metric_field cannot be empty.")
        if not self.winning_member_labels:
            raise ValueError(
                "Ranking conclusion requires at least one winner."
            )
        if self.is_tie != (len(self.winning_member_labels) > 1):
            raise ValueError(
                "is_tie must match winning_member_labels cardinality."
            )
        return self


def resolve_priority_intent_v1(
    question: str,
) -> bool:
    """
    只识别“需要业务调查优先级”的显式表达。

    “退款率最高/最低”只是事实 Ranking，不属于 Priority Intent。
    """
    text = re.sub(r"\s+", "", question).casefold()

    return bool(
        re.search(
            (
                r"(?:最值得|应该|应当)?"
                r"(?:优先|首先)"
                r"(?:关注|调查|排查|处理)"
                r"|"
                r"最值得(?:关注|调查|排查|处理)"
            ),
            text,
        )
    )


def select_refund_rate_priority_candidates_v1(
    *,
    rows: tuple[dict[str, Any], ...],
    member_field: str = "category",
    metric_field: str = "refund_rate",
) -> tuple[tuple[str, ...], Decimal] | None:
    """
    从已释放 rows 中选择“退款率最高”的调查优先候选。

    这是筛查规则，不是最终业务优先级。
    """
    candidates: list[tuple[str, Decimal]] = []

    for row in rows:
        member = row.get(member_field)
        raw_value = row.get(metric_field)

        if (
            member is None
            or raw_value is None
            or isinstance(raw_value, bool)
        ):
            continue

        try:
            value = Decimal(str(raw_value))
        except Exception:
            continue

        candidates.append((str(member), value))

    if not candidates:
        return None

    winning_value = max(
        value
        for _, value in candidates
    )

    winners = tuple(
        member
        for member, value in candidates
        if value == winning_value
    )

    return winners, winning_value


def resolve_ranking_intent_v1(
    question: str,
) -> RankingIntentV1 | None:
    """
    确定性识别用户显式 Ranking Intent。

    highest / lowest 优先于 best / worst；
    “表现最好”属于 BEST，而“退款率最高”属于 HIGHEST。
    """
    text = re.sub(r"\s+", "", question).casefold()

    if re.search(
        r"(?:最高|最大|最多|第一高|top1|top\s*1)",
        text,
    ):
        return RankingIntentV1.HIGHEST

    if re.search(
        r"(?:最低|最小|最少|第一低)",
        text,
    ):
        return RankingIntentV1.LOWEST

    if re.search(
        r"(?:表现)?(?:最好|最佳|最优)",
        text,
    ):
        return RankingIntentV1.BEST

    if re.search(
        r"(?:表现)?(?:最差|最弱|最不好)",
        text,
    ):
        return RankingIntentV1.WORST

    return None


def load_metric_ranking_preference_v1(
    *,
    metadata_catalog: dict[str, Any],
    metric_name: str,
) -> MetricRankingPreferenceV1 | None:
    """
    从既有 business_metrics.yaml 读取 Business Preference。

    没有声明 preference 的指标不允许把“best/worst”自行解释成
    max/min；保持无 Ranking Conclusion。
    """
    metrics = metadata_catalog.get("metrics")

    if not isinstance(metrics, list):
        raise ValueError(
            "business_metrics metadata must contain metrics list."
        )

    matches = tuple(
        item
        for item in metrics
        if isinstance(item, dict)
        and item.get("name") == metric_name
    )

    if len(matches) != 1:
        raise ValueError(
            f"Metric metadata must be unique: {metric_name}"
        )

    raw = matches[0].get("ranking_preference")

    if raw is None:
        return None

    return MetricRankingPreferenceV1(raw)


def _selection_direction_v1(
    *,
    intent: RankingIntentV1,
    preference: MetricRankingPreferenceV1 | None,
) -> RankingSelectionDirectionV1 | None:
    if intent == RankingIntentV1.HIGHEST:
        return RankingSelectionDirectionV1.MAX

    if intent == RankingIntentV1.LOWEST:
        return RankingSelectionDirectionV1.MIN

    if preference is None or preference == MetricRankingPreferenceV1.NEUTRAL:
        return None

    if intent == RankingIntentV1.BEST:
        return (
            RankingSelectionDirectionV1.MAX
            if preference
            == MetricRankingPreferenceV1.HIGHER_IS_BETTER
            else RankingSelectionDirectionV1.MIN
        )

    if intent == RankingIntentV1.WORST:
        return (
            RankingSelectionDirectionV1.MIN
            if preference
            == MetricRankingPreferenceV1.HIGHER_IS_BETTER
            else RankingSelectionDirectionV1.MAX
        )

    return None


def _find_breakdown_record_v1(
    *,
    delivery: EvidencePackDeliveryV2,
    evidence_id: str,
):
    matches = tuple(
        record
        for record in delivery.evidence_pack.evidence_records
        if record.reference.evidence_id == evidence_id
    )

    if len(matches) != 1:
        raise ValueError(
            "Ranking breakdown evidence must exist exactly once."
        )

    record = matches[0]

    if (
        record.evidence_type
        != EvidenceTypeV2.GOVERNED_QUERY_RESULT
        or record.provenance is None
        or record.protected_result is None
    ):
        raise ValueError(
            "Ranking conclusion requires protected governed evidence."
        )

    return record


def build_ranking_conclusion_v1(
    *,
    delivery: EvidencePackDeliveryV2,
    question: str,
    metadata_catalog: dict[str, Any],
    breakdown_evidence_id: str | None,
) -> RankingConclusionV1 | None:
    """
    从已释放 Breakdown 生成 Top-1 / Bottom-1 业务结论。

    注意：
    - 只消费 ProtectedResultV2；
    - 不依赖 Query Plan default_sort；
    - BEST/WORST 使用 Metric Business Preference；
    - HIGHEST/LOWEST 使用用户显式数学方向；
    - tie 保留全部并列成员；
    - 没有 Ranking Intent 时不自动排名。
    """
    if breakdown_evidence_id is None:
        return None

    intent = resolve_ranking_intent_v1(question)

    if intent is None:
        return None

    scope = delivery.evidence_pack.analysis_scope
    metric_name = scope.metric_name

    preference = load_metric_ranking_preference_v1(
        metadata_catalog=metadata_catalog,
        metric_name=metric_name,
    )

    direction = _selection_direction_v1(
        intent=intent,
        preference=preference,
    )

    if direction is None:
        return None

    record = _find_breakdown_record_v1(
        delivery=delivery,
        evidence_id=breakdown_evidence_id,
    )
    provenance = record.provenance
    protected = record.protected_result
    assert provenance is not None
    assert protected is not None

    if provenance.metric_name != metric_name:
        raise ValueError(
            "Ranking evidence metric does not match delivery metric."
        )

    if provenance.result_grain != scope.result_grain:
        raise ValueError(
            "Ranking evidence grain does not match delivery grain."
        )

    if provenance.analysis_window != scope.analysis_window:
        raise ValueError(
            "Ranking evidence window does not match delivery window."
        )

    metric_field = metric_name

    candidate_member_fields = tuple(
        field
        for field in protected.field_names
        if field != metric_field
    )

    if len(candidate_member_fields) != 1:
        return None

    member_field = candidate_member_fields[0]

    candidates: list[tuple[str, Decimal]] = []

    for row in protected.rows:
        member = row.get(member_field)
        raw_value = row.get(metric_field)

        if (
            member is None
            or raw_value is None
            or isinstance(raw_value, bool)
        ):
            continue

        try:
            value = Decimal(str(raw_value))
        except Exception:
            continue

        candidates.append((str(member), value))

    if not candidates:
        return None

    values = tuple(value for _, value in candidates)

    winning_value = (
        max(values)
        if direction == RankingSelectionDirectionV1.MAX
        else min(values)
    )

    winners = tuple(
        member
        for member, value in candidates
        if value == winning_value
    )

    if preference is None:
        # HIGHEST / LOWEST does not require business preference, but the
        # view contract still carries an explicit neutral marker.
        effective_preference = MetricRankingPreferenceV1.NEUTRAL
    else:
        effective_preference = preference

    return RankingConclusionV1(
        metric_name=metric_name,
        result_grain=provenance.result_grain,
        ranking_intent=intent,
        ranking_preference=effective_preference,
        selection_direction=direction,
        member_field=member_field,
        metric_field=metric_field,
        winning_member_labels=winners,
        winning_value=winning_value,
        is_tie=len(winners) > 1,
        evidence_id=record.reference.evidence_id,
        analysis_window=provenance.analysis_window,
        scope_summary=provenance.scope_summary,
    )


def build_priority_assessment_v1(
    *,
    delivery: EvidencePackDeliveryV2,
    question: str,
    breakdown_evidence_id: str | None,
) -> PriorityAssessmentV1 | None:
    """
    F03 V1：
    Category Refund Rate -> Investigation Priority Candidate.

    只在以下条件同时成立时启用：
    - 用户显式询问“优先关注 / 调查 / 排查 / 处理”；
    - metric == refund_rate；
    - result_grain == category；
    - 当前 Breakdown 是受保护 Governed Evidence。

    V1 筛查规则：
    退款率最高 -> 调查优先候选。

    这个规则只支持“先查谁”，不支持以下结论：
    - 最大退款金额损失；
    - 最大销售影响；
    - 根因；
    - 最终业务优先级。
    """
    if breakdown_evidence_id is None:
        return None

    if not resolve_priority_intent_v1(question):
        return None

    scope = delivery.evidence_pack.analysis_scope

    if (
        scope.metric_name != "refund_rate"
        or scope.result_grain != "category"
    ):
        return None

    record = _find_breakdown_record_v1(
        delivery=delivery,
        evidence_id=breakdown_evidence_id,
    )

    provenance = record.provenance
    protected = record.protected_result
    assert provenance is not None
    assert protected is not None

    if (
        provenance.metric_name != "refund_rate"
        or provenance.result_grain != "category"
        or provenance.analysis_window
        != scope.analysis_window
    ):
        raise ValueError(
            "Priority Evidence must match refund_rate/category scope."
        )

    if "category" not in protected.field_names:
        return None

    if "refund_rate" not in protected.field_names:
        return None

    selected = select_refund_rate_priority_candidates_v1(
        rows=tuple(
            dict(row)
            for row in protected.rows
        ),
        member_field="category",
        metric_field="refund_rate",
    )

    if selected is None:
        return None

    winners, winning_value = selected
    member_text = "、".join(winners)

    can_confirm = (
        (
            f"当前已释放的品类结果中，{member_text}"
            "退款率最高。"
        ),
        (
            "若明确以“退款率异常程度”作为筛查标准，"
            f"{member_text}可作为优先调查候选。"
        ),
    )

    cannot_confirm = (
        "不能仅凭退款率确认其退款金额损失最大。",
        "不能仅凭退款率确认其销售影响最大。",
        "不能仅凭当前结果确认退款根因或责任环节。",
        "不能把调查优先候选直接等同于最终业务优先级。",
    )

    next_evidence_needed = (
        "补充品类销售规模与完成退款金额，用于评估实际损失规模。",
        "补充退款原因、商品与履约等原因类证据，用于进一步定位根因。",
    )

    return PriorityAssessmentV1(
        metric_name="refund_rate",
        result_grain="category",
        candidate_member_labels=winners,
        candidate_value=winning_value,
        is_tie=len(winners) > 1,
        screening_rule="highest_refund_rate",
        evidence_status=PriorityEvidenceStatusV1.PARTIAL,
        can_confirm=can_confirm,
        cannot_confirm=cannot_confirm,
        next_evidence_needed=next_evidence_needed,
        evidence_id=record.reference.evidence_id,
        analysis_window=provenance.analysis_window,
        scope_summary=provenance.scope_summary,
    )
