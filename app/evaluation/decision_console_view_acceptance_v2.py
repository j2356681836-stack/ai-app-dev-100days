from __future__ import annotations

import inspect
from datetime import date
from decimal import Decimal

import app.delivery.decision_console_view_v2 as console_view_module
from app.agents.contribution_analysis_v2 import (
    ContributionObservationV2,
    ContributionReconciliationStatusV2,
    analyze_additive_contribution_v2,
)
from app.agents.contribution_insight_adapter_v2 import (
    attach_contribution_result_to_insight_v2,
)
from app.agents.evidence_pack_delivery_v2 import (
    EvidenceSufficiencyStatusV2,
    MetricDefinitionSnapshotV2,
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
from app.delivery.decision_console_view_v2 import (
    VIEW_CONTRACT_VERSION,
    build_decision_console_view_v2,
)
from app.semantic_layer.time_comparison_contract_v2 import (
    AlignmentModeV2,
    ComparisonTypeV2,
    PeriodModeV2,
    TimeComparisonContractV2,
    TimeWindowReferenceV2,
)


EXPECTED_VIEW_VERSION = "day89_decision_console_view_v2_7"
EVIDENCE_ID = "contribution-console-001"


def _window(
    start_date: date,
    end_date: date,
) -> TimeWindowReferenceV2:
    return TimeWindowReferenceV2(
        start_date=start_date,
        end_date=end_date,
    )


def _comparison() -> TimeComparisonContractV2:
    return TimeComparisonContractV2(
        comparison_type=ComparisonTypeV2.YOY,
        period_mode=PeriodModeV2.COMPLETED_PERIOD,
        alignment_mode=AlignmentModeV2.CALENDAR_ALIGNED,
        current_window=_window(
            date(2025, 7, 1),
            date(2025, 7, 31),
        ),
        reference_window=_window(
            date(2024, 7, 1),
            date(2024, 7, 31),
        ),
    )


def _obs(
    key: str,
    label: str,
    value: str,
) -> ContributionObservationV2:
    return ContributionObservationV2(
        member_key=key,
        member_label=label,
        value=Decimal(value),
    )


def _contribution_result():
    return analyze_additive_contribution_v2(
        metric_name="gmv",
        dimension_name="channel",
        comparison=_comparison(),
        current_overall_value=Decimal("90"),
        reference_overall_value=Decimal("100"),
        current_members=(
            _obs("tmall", "天猫", "90"),
        ),
        reference_members=(
            _obs("tmall", "天猫", "95"),
        ),
    )


def _metric_definition() -> MetricDefinitionSnapshotV2:
    return MetricDefinitionSnapshotV2(
        metadata_version="v2",
        dataset_name="beauty_bi_v2",
        metric_name="gmv",
        chinese_name="销售额",
        grain="paid_order_items",
        definition="测试用 GMV Definition。",
        formula="SUM(item_paid_amount)",
        filters=(),
        metric_fingerprint="metric-fingerprint",
    )


def _delivery(
    *,
    extra_record: EvidenceRecordV2 | None = None,
):
    comparison = _comparison()
    scope = AnalysisScopeV2(
        metric_name="gmv",
        analysis_window=comparison.current_window,
        comparison=comparison,
        result_grain="channel",
        scope_summary="Day89 Decision Console Acceptance。",
    )

    insight = InsightContractV2(
        analysis_mode=AnalysisModeV2.DIAGNOSTIC,
        analysis_scope=scope,
    )

    insight = attach_contribution_result_to_insight_v2(
        insight=insight,
        result=_contribution_result(),
        evidence_id=EVIDENCE_ID,
    )

    records = [
        EvidenceRecordV2(
            reference=next(
                ref
                for ref in insight.evidence
                if ref.evidence_id == EVIDENCE_ID
            ),
            evidence_type=EvidenceTypeV2.CONTRIBUTION_RESULT,
        ),
    ]

    if extra_record is not None:
        records.append(extra_record)

    pack = EvidencePackV2(
        pack_id="day89-console-pack",
        analysis_scope=scope,
        insight=insight,
        evidence_records=tuple(records),
    )

    return assemble_evidence_pack_delivery_v2(
        evidence_pack=pack,
        metric_definition=_metric_definition(),
    )


def test_projection_preserves_contribution_values() -> None:
    result = _contribution_result()
    delivery = _delivery()

    view = build_decision_console_view_v2(
        delivery=delivery,
        contribution_result=result,
        contribution_evidence_id=EVIDENCE_ID,
    )

    assert view.contribution is not None
    assert (
        view.contribution.overall_delta
        == result.overall_delta
        == Decimal("-10")
    )
    assert (
        view.contribution.sum_member_delta
        == result.sum_member_delta
        == Decimal("-5")
    )
    assert (
        view.contribution.unexplained_remainder
        == result.unexplained_remainder
        == Decimal("-5")
    )


def test_reconciliation_status_is_inherited() -> None:
    result = _contribution_result()
    view = build_decision_console_view_v2(
        delivery=_delivery(),
        contribution_result=result,
        contribution_evidence_id=EVIDENCE_ID,
    )

    assert (
        result.reconciliation_status
        == ContributionReconciliationStatusV2.NOT_RECONCILED
    )
    assert (
        view.contribution is not None
        and view.contribution.reconciliation_status
        == result.reconciliation_status
    )


def test_ranking_is_inherited() -> None:
    result = _contribution_result()
    view = build_decision_console_view_v2(
        delivery=_delivery(),
        contribution_result=result,
        contribution_evidence_id=EVIDENCE_ID,
    )

    assert view.contribution is not None
    assert (
        view.contribution.negative_change_ranking
        == result.negative_change_ranking
    )
    assert (
        view.contribution.positive_change_ranking
        == result.positive_change_ranking
    )


def test_partial_sufficiency_is_not_upgraded() -> None:
    delivery = _delivery()

    assert (
        delivery.sufficiency.status
        == EvidenceSufficiencyStatusV2.PARTIAL
    )

    view = build_decision_console_view_v2(
        delivery=delivery,
        contribution_result=_contribution_result(),
        contribution_evidence_id=EVIDENCE_ID,
    )

    assert (
        view.evidence_sufficiency
        == EvidenceSufficiencyStatusV2.PARTIAL
    )


def test_contribution_requires_evidence_id() -> None:
    try:
        build_decision_console_view_v2(
            delivery=_delivery(),
            contribution_result=_contribution_result(),
        )
    except ValueError:
        return

    raise AssertionError(
        "Contribution Result 必须绑定 evidence_id。"
    )


def test_unknown_evidence_id_fails_closed() -> None:
    try:
        build_decision_console_view_v2(
            delivery=_delivery(),
            contribution_result=_contribution_result(),
            contribution_evidence_id="missing-evidence",
        )
    except ValueError:
        return

    raise AssertionError(
        "不存在的 Contribution Evidence 必须 fail-closed。"
    )


def test_non_contribution_evidence_id_fails_closed() -> None:
    unrelated = EvidenceRecordV2(
        reference=EvidenceReferenceV2(
            evidence_id="anomaly-evidence",
            source="test",
        ),
        evidence_type=EvidenceTypeV2.ANOMALY_DECISION,
    )

    delivery = _delivery(
        extra_record=unrelated,
    )

    try:
        build_decision_console_view_v2(
            delivery=delivery,
            contribution_result=_contribution_result(),
            contribution_evidence_id="anomaly-evidence",
        )
    except ValueError:
        return

    raise AssertionError(
        "非 CONTRIBUTION_RESULT Evidence 不能绑定 Contribution View。"
    )


TESTS = (
    test_projection_preserves_contribution_values,
    test_reconciliation_status_is_inherited,
    test_ranking_is_inherited,
    test_partial_sufficiency_is_not_upgraded,
    test_contribution_requires_evidence_id,
    test_unknown_evidence_id_fails_closed,
    test_non_contribution_evidence_id_fails_closed,
)


def run_acceptance() -> None:
    print("Day89 Decision Console View V2 Preflight")
    print(f"Module: {console_view_module.__file__}")
    print(f"Version: {VIEW_CONTRACT_VERSION}")
    print(
        "Signature: "
        f"{inspect.signature(build_decision_console_view_v2)}"
    )

    if VIEW_CONTRACT_VERSION != EXPECTED_VIEW_VERSION:
        raise SystemExit(
            "Loaded Decision Console View version is stale: "
            f"expected={EXPECTED_VIEW_VERSION}, "
            f"actual={VIEW_CONTRACT_VERSION}"
        )

    passed = 0
    failures: list[str] = []

    for test in TESTS:
        try:
            test()
            passed += 1
        except Exception as exc:  # noqa: BLE001
            failures.append(
                f"{test.__name__}: "
                f"{type(exc).__name__}: {exc}"
            )

    print()
    print("Day89 Decision Console View V2 Acceptance Summary")
    print(f"Total: {len(TESTS)}")
    print(f"Passed: {passed}")
    print(f"Failed: {len(failures)}")

    for failure in failures:
        print(f"- {failure}")

    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    run_acceptance()
