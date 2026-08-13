from __future__ import annotations

from decimal import Decimal

from app.agents.anomaly_detection_v2 import (
    AnomalyDecisionStatusV2,
    AnomalyDecisionV2,
)
from app.agents.investigation_contracts_v2 import (
    AnalysisModeV2,
    EvidenceReferenceV2,
    InsightContractV2,
    SupportedInsightStatementV2,
)


def _format_relative_change(
    value: Decimal | None,
) -> str:
    if value is None:
        return "undefined"

    return f"{value * Decimal('100'):.2f}%"


def build_detected_anomaly_material_v2(
    decision: AnomalyDecisionV2,
) -> tuple[
    SupportedInsightStatementV2,
    EvidenceReferenceV2,
]:
    """
    Convert one deterministic ANOMALY decision into the lightweight
    Day82 Insight material.

    The adapter does not add causes, explanations, or contributions.
    Those belong to later investigation stages.
    """

    if (
        decision.status
        != AnomalyDecisionStatusV2.ANOMALY
    ):
        raise ValueError(
            "Only ANOMALY decisions may populate "
            "InsightContractV2.detected_anomalies."
        )

    if decision.policy is None:
        raise ValueError(
            "ANOMALY decision must carry an active policy."
        )

    comparison_type = (
        decision.comparison.comparison_type.value
    )

    statement = SupportedInsightStatementV2(
        statement=(
            f"{decision.metric_name} met the active deterministic "
            f"anomaly policy for {comparison_type}; "
            f"absolute_change={decision.absolute_change}; "
            f"relative_change="
            f"{_format_relative_change(decision.relative_change)}."
        ),
        evidence_ids=(decision.evidence_id,),
    )

    evidence = EvidenceReferenceV2(
        evidence_id=decision.evidence_id,
        source="deterministic_anomaly_detector_v2",
        description=(
            f"status={decision.status.value}; "
            f"reason={decision.reason_code.value}; "
            f"policy_version={decision.policy.policy_version}; "
            f"sample_metric={decision.policy.sample_metric_name}; "
            f"current_sample={decision.current_sample_value}; "
            f"reference_sample={decision.reference_sample_value}"
        ),
    )

    return statement, evidence


def attach_anomaly_decision_to_insight_v2(
    *,
    insight: InsightContractV2,
    decision: AnomalyDecisionV2,
) -> InsightContractV2:
    """
    Attach one confirmed deterministic anomaly to a DIAGNOSTIC or
    INVESTIGATION InsightContractV2.

    This is an assembly boundary:
    - AnomalyDecisionV2 remains the detector's structured verdict.
    - InsightContractV2 keeps a supported statement plus a lightweight
      evidence reference.
    """

    if insight.analysis_mode not in {
        AnalysisModeV2.DIAGNOSTIC,
        AnalysisModeV2.INVESTIGATION,
    }:
        raise ValueError(
            "Detected anomalies can only be attached to "
            "DIAGNOSTIC / INVESTIGATION insight modes."
        )

    if (
        decision.metric_name
        != insight.analysis_scope.metric_name
    ):
        raise ValueError(
            "Anomaly decision metric does not match "
            "Insight analysis_scope metric."
        )

    if insight.analysis_scope.comparison is None:
        raise ValueError(
            "An anomaly-bearing Insight requires "
            "analysis_scope.comparison."
        )

    if (
        decision.comparison
        != insight.analysis_scope.comparison
    ):
        raise ValueError(
            "Anomaly decision comparison does not match "
            "Insight analysis_scope comparison."
        )

    statement, evidence = (
        build_detected_anomaly_material_v2(
            decision
        )
    )

    existing_evidence_ids = {
        item.evidence_id
        for item in insight.evidence
    }

    if evidence.evidence_id in existing_evidence_ids:
        raise ValueError(
            "Anomaly evidence_id already exists in Insight evidence."
        )

    payload = insight.model_dump()
    payload["detected_anomalies"] = [
        *payload["detected_anomalies"],
        statement.model_dump(),
    ]
    payload["evidence"] = [
        *payload["evidence"],
        evidence.model_dump(),
    ]

    return InsightContractV2.model_validate(payload)
