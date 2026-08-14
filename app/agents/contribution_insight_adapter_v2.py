from __future__ import annotations

from decimal import Decimal

from app.agents.contribution_analysis_v2 import (
    ContributionAnalysisResultV2,
    ContributionDirectionV2,
    ContributionReconciliationStatusV2,
)
from app.agents.investigation_contracts_v2 import (
    AnalysisModeV2,
    EvidenceReferenceV2,
    InsightContractV2,
    SupportedInsightStatementV2,
    UnknownV2,
)


def _format_decimal(value: Decimal) -> str:
    return format(value, "f")


def _format_contribution_rate(value: Decimal | None) -> str:
    if value is None:
        return "undefined"
    return f"{value * Decimal('100'):.2f}%"


def _ordered_changed_members(
    result: ContributionAnalysisResultV2,
):
    by_key = {
        member.member_key: member
        for member in result.members
    }

    ordered_keys = (
        *result.negative_change_ranking,
        *result.positive_change_ranking,
    )

    return tuple(
        by_key[key]
        for key in ordered_keys
        if by_key[key].direction
        != ContributionDirectionV2.NEUTRAL
    )


def build_dimension_contribution_material_v2(
    *,
    result: ContributionAnalysisResultV2,
    evidence_id: str,
) -> tuple[
    tuple[SupportedInsightStatementV2, ...],
    EvidenceReferenceV2,
]:
    """
    Convert one deterministic contribution result into lightweight
    Day82 Insight material.

    The adapter preserves arithmetic evidence only. It does not claim
    business cause, explanation, or recommended action.
    """

    if not evidence_id.strip():
        raise ValueError("evidence_id cannot be empty.")

    statements = tuple(
        SupportedInsightStatementV2(
            statement=(
                f"{result.dimension_name}={member.member_label} "
                f"changed {result.metric_name} from "
                f"{_format_decimal(member.reference_value)} to "
                f"{_format_decimal(member.current_value)}; "
                f"member_delta={_format_decimal(member.delta)}; "
                f"contribution_rate="
                f"{_format_contribution_rate(member.contribution_rate)} "
                f"of overall_delta="
                f"{_format_decimal(result.overall_delta)}."
            ),
            evidence_ids=(evidence_id,),
        )
        for member in _ordered_changed_members(result)
    )

    evidence = EvidenceReferenceV2(
        evidence_id=evidence_id,
        source="deterministic_contribution_analysis_v2",
        description=(
            f"metric={result.metric_name}; "
            f"dimension={result.dimension_name}; "
            f"comparison_type="
            f"{result.comparison.comparison_type.value}; "
            f"current_window="
            f"{result.comparison.current_window.start_date}.."
            f"{result.comparison.current_window.end_date}; "
            f"reference_window="
            f"{result.comparison.reference_window.start_date}.."
            f"{result.comparison.reference_window.end_date}; "
            f"overall_delta={_format_decimal(result.overall_delta)}; "
            f"sum_member_delta="
            f"{_format_decimal(result.sum_member_delta)}; "
            f"unexplained_remainder="
            f"{_format_decimal(result.unexplained_remainder)}; "
            f"reconciliation_status="
            f"{result.reconciliation_status.value}"
        ),
    )

    return statements, evidence


def attach_contribution_result_to_insight_v2(
    *,
    insight: InsightContractV2,
    result: ContributionAnalysisResultV2,
    evidence_id: str,
) -> InsightContractV2:
    """
    Attach deterministic contribution evidence to a DIAGNOSTIC or
    INVESTIGATION InsightContractV2.

    Non-reconciled decomposition remains usable as partial arithmetic
    evidence, but the unexplained remainder is explicitly preserved as
    an Unknown instead of being invented away.
    """

    if insight.analysis_mode not in {
        AnalysisModeV2.DIAGNOSTIC,
        AnalysisModeV2.INVESTIGATION,
    }:
        raise ValueError(
            "Dimension contributions can only be attached to "
            "DIAGNOSTIC / INVESTIGATION insight modes."
        )

    if result.metric_name != insight.analysis_scope.metric_name:
        raise ValueError(
            "Contribution result metric does not match "
            "Insight analysis_scope metric."
        )

    if insight.analysis_scope.comparison is None:
        raise ValueError(
            "A contribution-bearing Insight requires "
            "analysis_scope.comparison."
        )

    if result.comparison != insight.analysis_scope.comparison:
        raise ValueError(
            "Contribution result comparison does not match "
            "Insight analysis_scope comparison."
        )

    if (
        insight.analysis_scope.analysis_window
        != result.comparison.current_window
    ):
        raise ValueError(
            "Insight analysis_window must equal the contribution "
            "comparison current_window."
        )

    if (
        insight.analysis_scope.result_grain is not None
        and insight.analysis_scope.result_grain
        != result.dimension_name
    ):
        raise ValueError(
            "Contribution dimension does not match "
            "Insight analysis_scope result_grain."
        )

    statements, evidence = build_dimension_contribution_material_v2(
        result=result,
        evidence_id=evidence_id,
    )

    existing_evidence_ids = {
        item.evidence_id
        for item in insight.evidence
    }

    if evidence.evidence_id in existing_evidence_ids:
        raise ValueError(
            "Contribution evidence_id already exists in Insight evidence."
        )

    payload = insight.model_dump()
    payload["dimension_contributions"] = [
        *payload["dimension_contributions"],
        *(statement.model_dump() for statement in statements),
    ]
    payload["evidence"] = [
        *payload["evidence"],
        evidence.model_dump(),
    ]

    if (
        result.reconciliation_status
        == ContributionReconciliationStatusV2.NOT_RECONCILED
    ):
        unknown = UnknownV2(
            description=(
                "Contribution decomposition is not fully reconciled; "
                "unexplained_remainder="
                f"{_format_decimal(result.unexplained_remainder)}. "
                "Do not treat the visible member contributions as a "
                "complete explanation."
            )
        )
        payload["unknowns"] = [
            *payload["unknowns"],
            unknown.model_dump(),
        ]

    return InsightContractV2.model_validate(payload)
