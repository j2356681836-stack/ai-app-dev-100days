from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, model_validator

from app.agents.contribution_analysis_v2 import (
    ContributionAnalysisResultV2,
    ContributionReconciliationStatusV2,
)


CONTRIBUTION_INVESTIGATION_RECOMMENDATION_POLICY_V1 = (
    "gmv_channel_directional_contribution_triage_v1"
)


class ContributionInvestigationRecommendationV1(BaseModel):
    """
    F02 的确定性“下一步调查候选”合同。

    只允许从已经完成 Reconciliation 的 GMV × Channel
    Contribution Result 中选择与 Overall 变化方向一致的第一名：

    - Overall 下降 -> negative_change_ranking[0]
    - Overall 上升 -> positive_change_ranking[0]

    该合同表达的是 investigation triage，不表达 causality。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    policy_version: str = (
        CONTRIBUTION_INVESTIGATION_RECOMMENDATION_POLICY_V1
    )

    metric_name: str
    dimension_name: str

    member_key: str
    member_label: str

    reference_value: Decimal
    current_value: Decimal
    delta: Decimal
    contribution_rate: Decimal | None

    overall_delta: Decimal
    direction: str

    rationale: str
    can_confirm: tuple[str, ...]
    cannot_confirm: tuple[str, ...]

    contribution_evidence_id: str

    @model_validator(mode="after")
    def validate_recommendation(
        self,
    ) -> "ContributionInvestigationRecommendationV1":
        if self.metric_name != "gmv":
            raise ValueError(
                "F02 Recommendation V1 只接受 GMV。"
            )

        if self.dimension_name != "channel":
            raise ValueError(
                "F02 Recommendation V1 只接受 Channel。"
            )

        if self.direction not in {"negative", "positive"}:
            raise ValueError(
                "direction 必须是 negative 或 positive。"
            )

        if not self.member_key.strip():
            raise ValueError("member_key 不能为空。")

        if not self.member_label.strip():
            raise ValueError("member_label 不能为空。")

        if not self.contribution_evidence_id.strip():
            raise ValueError(
                "contribution_evidence_id 不能为空。"
            )

        if self.direction == "negative":
            if not (self.overall_delta < 0 and self.delta < 0):
                raise ValueError(
                    "negative recommendation 必须与 Overall "
                    "负向变化保持同方向。"
                )

        if self.direction == "positive":
            if not (self.overall_delta > 0 and self.delta > 0):
                raise ValueError(
                    "positive recommendation 必须与 Overall "
                    "正向变化保持同方向。"
                )

        return self


def build_contribution_investigation_recommendation_v1(
    *,
    contribution: ContributionAnalysisResultV2,
    contribution_evidence_id: str,
) -> ContributionInvestigationRecommendationV1 | None:
    """
    从可信 Contribution Result 生成 F02 调查优先候选。

    Fail-closed conditions:
    - 不是 GMV × Channel；
    - Contribution 未完成 Reconciliation；
    - Overall 没有净变化；
    - 与 Overall 同方向的渠道不存在。

    返回 None 表示：
    当前证据不足以安全形成“优先看哪个渠道”的建议。
    """
    if (
        contribution.metric_name != "gmv"
        or contribution.dimension_name != "channel"
    ):
        return None

    if (
        contribution.reconciliation_status
        != ContributionReconciliationStatusV2.RECONCILED
    ):
        return None

    if contribution.overall_delta == 0:
        return None

    by_key = {
        member.member_key: member
        for member in contribution.members
    }

    if contribution.overall_delta < 0:
        ranking = contribution.negative_change_ranking
        direction = "negative"
        direction_label = "下降"
    else:
        ranking = contribution.positive_change_ranking
        direction = "positive"
        direction_label = "增长"

    if not ranking:
        return None

    candidate = by_key.get(ranking[0])

    if candidate is None:
        return None

    can_confirm = (
        (
            f"当前 Overall GMV 为{direction_label}方向，"
            f"{candidate.member_label}与 Overall 变化方向一致。"
        ),
        (
            f"在当前已释放的渠道 Contribution Evidence 中，"
            f"{candidate.member_label}是同方向变化额最大的渠道。"
        ),
        (
            "当前渠道变化额合计已与 Overall GMV 变化额完成 "
            "Reconciliation。"
        ),
    )

    cannot_confirm = (
        (
            f"不能仅凭 Contribution 证明"
            f"{candidate.member_label}就是 GMV 变化的根因。"
        ),
        "不能仅凭当前渠道贡献判断具体商品、客户、活动或履约原因。",
        "不能把“优先调查候选”直接等同于最终业务责任或决策结论。",
    )

    return ContributionInvestigationRecommendationV1(
        metric_name=contribution.metric_name,
        dimension_name=contribution.dimension_name,
        member_key=candidate.member_key,
        member_label=candidate.member_label,
        reference_value=candidate.reference_value,
        current_value=candidate.current_value,
        delta=candidate.delta,
        contribution_rate=candidate.contribution_rate,
        overall_delta=contribution.overall_delta,
        direction=direction,
        rationale=(
            f"{candidate.member_label}在与 Overall GMV "
            f"{direction_label}一致的渠道中变化额最大，"
            "因此适合作为下一步调查入口。"
        ),
        can_confirm=can_confirm,
        cannot_confirm=cannot_confirm,
        contribution_evidence_id=contribution_evidence_id,
    )
