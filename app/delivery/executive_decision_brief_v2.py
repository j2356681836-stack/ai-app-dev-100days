from __future__ import annotations

from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, model_validator

from app.agents.contribution_analysis_v2 import (
    ContributionDirectionV2,
    ContributionReconciliationStatusV2,
)
from app.agents.evidence_pack_delivery_v2 import (
    EvidencePackDeliveryV2,
    EvidenceSufficiencyStatusV2,
)
from app.delivery.decision_console_view_v2 import (
    ContributionMemberViewV2,
    DecisionConsoleViewV2,
    MetricComparisonViewV2,
)
from app.semantic_layer.time_comparison_contract_v2 import (
    TimeWindowReferenceV2,
)


BRIEF_CONTRACT_VERSION = "executive_decision_brief_preview_v2_0"


class ExecutiveFindingTypeV2(str, Enum):
    CONFIRMED_FACT = "confirmed_fact"
    DETECTED_ANOMALY = "detected_anomaly"
    DIMENSION_CONTRIBUTION = "dimension_contribution"


class ExecutiveLimitationCodeV2(str, Enum):
    EVIDENCE_NOT_FULLY_SUFFICIENT = "evidence_not_fully_sufficient"
    CONTRIBUTION_NOT_RECONCILED = "contribution_not_reconciled"
    CLARIFICATION_REQUIRED = "clarification_required"
    INVESTIGATION_CAN_CONTINUE = "investigation_can_continue"


class ExecutiveKeyFindingV2(BaseModel):
    """
    Executive Brief 中的一条 evidence-backed finding。

    summary 与 evidence_ids 直接继承 InsightContractV2，
    Brief 不重新生成业务事实。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    finding_type: ExecutiveFindingTypeV2
    summary: str
    evidence_ids: tuple[str, ...]


class ExecutiveContributionHighlightV2(BaseModel):
    """
    已按 Day84 deterministic ranking 排序后的 Contribution Highlight。

    Brief 只截取已有 ranking 的前几项，不重新计算或重新排序。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    member_key: str
    member_label: str
    delta: Decimal
    contribution_rate: Decimal | None
    direction: ContributionDirectionV2


class ExecutiveContributionHighlightsV2(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    negative: tuple[ExecutiveContributionHighlightV2, ...] = ()
    positive: tuple[ExecutiveContributionHighlightV2, ...] = ()


class ExecutiveLimitationV2(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    code: ExecutiveLimitationCodeV2
    detail: str

    @model_validator(mode="after")
    def validate_limitation(
        self,
    ) -> "ExecutiveLimitationV2":
        if not self.detail.strip():
            raise ValueError(
                "Executive Brief limitation detail 不能为空。"
            )
        return self


class ExecutiveDecisionBriefPreviewV2(BaseModel):
    """
    Day89 Executive Decision Brief 的结构化 preview。

    它是 Presentation Contract，不是新的分析 / 推理层。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    contract_version: str = BRIEF_CONTRACT_VERSION

    request_subject: str

    metric_name: str
    result_grain: str | None
    scope_summary: str | None
    analysis_window: TimeWindowReferenceV2

    kpi_summary: MetricComparisonViewV2 | None = None

    key_findings: tuple[ExecutiveKeyFindingV2, ...]
    top_contributions: ExecutiveContributionHighlightsV2

    confirmed_facts: tuple[str, ...]
    candidate_hypotheses: tuple[str, ...]
    unknowns: tuple[str, ...]
    recommended_checks: tuple[str, ...]

    evidence_sufficiency: EvidenceSufficiencyStatusV2
    evidence_confidence_level: str

    limitations: tuple[ExecutiveLimitationV2, ...]

    @model_validator(mode="after")
    def validate_brief(
        self,
    ) -> "ExecutiveDecisionBriefPreviewV2":
        if not self.request_subject.strip():
            raise ValueError(
                "Executive Brief request_subject 不能为空。"
            )

        if not self.metric_name.strip():
            raise ValueError(
                "Executive Brief metric_name 不能为空。"
            )

        return self


def _finding_rows_v2(
    delivery: EvidencePackDeliveryV2,
) -> tuple[ExecutiveKeyFindingV2, ...]:
    insight = delivery.evidence_pack.insight

    result: list[ExecutiveKeyFindingV2] = []

    for item in insight.confirmed_facts:
        result.append(
            ExecutiveKeyFindingV2(
                finding_type=(
                    ExecutiveFindingTypeV2.CONFIRMED_FACT
                ),
                summary=item.statement,
                evidence_ids=item.evidence_ids,
            )
        )

    for item in insight.detected_anomalies:
        result.append(
            ExecutiveKeyFindingV2(
                finding_type=(
                    ExecutiveFindingTypeV2.DETECTED_ANOMALY
                ),
                summary=item.statement,
                evidence_ids=item.evidence_ids,
            )
        )

    for item in insight.dimension_contributions:
        result.append(
            ExecutiveKeyFindingV2(
                finding_type=(
                    ExecutiveFindingTypeV2
                    .DIMENSION_CONTRIBUTION
                ),
                summary=item.statement,
                evidence_ids=item.evidence_ids,
            )
        )

    return tuple(result)


def _highlight_v2(
    member: ContributionMemberViewV2,
) -> ExecutiveContributionHighlightV2:
    return ExecutiveContributionHighlightV2(
        member_key=member.member_key,
        member_label=member.member_label,
        delta=member.delta,
        contribution_rate=member.contribution_rate,
        direction=member.direction,
    )


def _contribution_highlights_v2(
    view: DecisionConsoleViewV2,
) -> ExecutiveContributionHighlightsV2:
    contribution = view.contribution

    if contribution is None:
        return ExecutiveContributionHighlightsV2()

    by_key = {
        member.member_key: member
        for member in contribution.members
    }

    negative = tuple(
        _highlight_v2(by_key[member_key])
        for member_key
        in contribution.negative_change_ranking[:3]
    )

    positive = tuple(
        _highlight_v2(by_key[member_key])
        for member_key
        in contribution.positive_change_ranking[:3]
    )

    return ExecutiveContributionHighlightsV2(
        negative=negative,
        positive=positive,
    )


def _limitations_v2(
    *,
    delivery: EvidencePackDeliveryV2,
    view: DecisionConsoleViewV2,
) -> tuple[ExecutiveLimitationV2, ...]:
    limitations: list[ExecutiveLimitationV2] = []

    if (
        delivery.sufficiency.status
        != EvidenceSufficiencyStatusV2.SUFFICIENT_FOR_CURRENT_SCOPE
    ):
        limitations.append(
            ExecutiveLimitationV2(
                code=(
                    ExecutiveLimitationCodeV2
                    .EVIDENCE_NOT_FULLY_SUFFICIENT
                ),
                detail=" | ".join(
                    delivery.sufficiency.basis
                ),
            )
        )

    if (
        view.contribution is not None
        and view.contribution.reconciliation_status
        == ContributionReconciliationStatusV2.NOT_RECONCILED
    ):
        limitations.append(
            ExecutiveLimitationV2(
                code=(
                    ExecutiveLimitationCodeV2
                    .CONTRIBUTION_NOT_RECONCILED
                ),
                detail=(
                    "Contribution reconciliation_status="
                    f"{view.contribution.reconciliation_status.value}; "
                    "unexplained_remainder="
                    f"{view.contribution.unexplained_remainder}"
                ),
            )
        )

    if view.clarification is not None:
        limitations.append(
            ExecutiveLimitationV2(
                code=(
                    ExecutiveLimitationCodeV2
                    .CLARIFICATION_REQUIRED
                ),
                detail=(
                    view.clarification.requirement_reason
                ),
            )
        )

    if (
        view.runtime_control is not None
        and view.runtime_control.can_continue
    ):
        limitations.append(
            ExecutiveLimitationV2(
                code=(
                    ExecutiveLimitationCodeV2
                    .INVESTIGATION_CAN_CONTINUE
                ),
                detail=view.runtime_control.detail,
            )
        )

    return tuple(limitations)


def build_executive_decision_brief_preview_v2(
    *,
    request_subject: str,
    delivery: EvidencePackDeliveryV2,
    console_view: DecisionConsoleViewV2,
) -> ExecutiveDecisionBriefPreviewV2:
    """
    将 Day87 Evidence Delivery + Day89 Decision Console View
    投影成 Executive Decision Brief Preview。

    本 Builder：
    - 不调用 LLM；
    - 不重新计算 KPI；
    - 不重新排序 Contribution；
    - 不升级 Evidence Sufficiency；
    - 不生成新的业务原因。
    """

    subject = request_subject.strip()
    if not subject:
        raise ValueError(
            "request_subject 不能为空。"
        )

    scope = delivery.evidence_pack.analysis_scope

    if console_view.metric_name != scope.metric_name:
        raise ValueError(
            "Console View metric 与 Evidence Delivery metric 不一致。"
        )

    if console_view.result_grain != scope.result_grain:
        raise ValueError(
            "Console View result_grain 与 Evidence Delivery 不一致。"
        )

    if console_view.scope_summary != scope.scope_summary:
        raise ValueError(
            "Console View scope_summary 与 Evidence Delivery 不一致。"
        )

    return ExecutiveDecisionBriefPreviewV2(
        request_subject=subject,
        metric_name=scope.metric_name,
        result_grain=scope.result_grain,
        scope_summary=scope.scope_summary,
        analysis_window=scope.analysis_window,
        kpi_summary=console_view.comparison,
        key_findings=_finding_rows_v2(
            delivery
        ),
        top_contributions=(
            _contribution_highlights_v2(
                console_view
            )
        ),
        confirmed_facts=console_view.confirmed_facts,
        candidate_hypotheses=(
            console_view.candidate_hypotheses
        ),
        unknowns=console_view.unknowns,
        recommended_checks=(
            console_view.recommended_checks
        ),
        evidence_sufficiency=(
            delivery.sufficiency.status
        ),
        evidence_confidence_level=(
            delivery.sufficiency.confidence_level.value
        ),
        limitations=_limitations_v2(
            delivery=delivery,
            view=console_view,
        ),
    )
