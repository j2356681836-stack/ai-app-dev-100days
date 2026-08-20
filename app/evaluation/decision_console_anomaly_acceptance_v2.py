from __future__ import annotations

import inspect
from datetime import date
from decimal import Decimal

import app.delivery.decision_console_view_v2 as console_view_module
from app.agents.anomaly_detection_v2 import (
    AnomalyChangeTypeV2,
    AnomalyDecisionStatusV2,
    AnomalyDirectionV2,
    AnomalyPolicyV2,
    detect_anomaly_v2,
)
from app.agents.anomaly_insight_adapter_v2 import (
    attach_anomaly_decision_to_insight_v2,
)
from app.agents.evidence_pack_delivery_v2 import (
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
ANOMALY_EVIDENCE_ID = "anomaly-console-001"


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


def _policy(
    *,
    change_type=AnomalyChangeTypeV2.RELATIVE,
    threshold="0.20",
    minimum_sample="10",
) -> AnomalyPolicyV2:
    return AnomalyPolicyV2(
        metric_name="gmv",
        comparison_type=ComparisonTypeV2.YOY,
        change_type=change_type,
        direction=AnomalyDirectionV2.BOTH,
        threshold_value=Decimal(threshold),
        sample_metric_name="order_count",
        minimum_sample_value=Decimal(minimum_sample),
        policy_version="test-policy-v1",
    )


def _decision(
    *,
    current="70",
    reference="100",
    current_sample="100",
    reference_sample="100",
    policy="active",
):
    return detect_anomaly_v2(
        evidence_id=ANOMALY_EVIDENCE_ID,
        metric_name="gmv",
        comparison=_comparison(),
        current_value=Decimal(current),
        reference_value=Decimal(reference),
        current_sample_value=Decimal(current_sample),
        reference_sample_value=Decimal(reference_sample),
        policy=(
            _policy()
            if policy == "active"
            else None
        ),
    )


def _base_insight() -> InsightContractV2:
    comparison = _comparison()
    return InsightContractV2(
        analysis_mode=AnalysisModeV2.DIAGNOSTIC,
        analysis_scope=AnalysisScopeV2(
            metric_name="gmv",
            analysis_window=comparison.current_window,
            comparison=comparison,
            result_grain="channel",
            scope_summary="Day89 Anomaly Projection Acceptance。",
        ),
    )


def _delivery_for_decision(
    decision,
    *,
    publish_detected_anomaly: bool,
):
    insight = _base_insight()
    records = []

    if publish_detected_anomaly:
        insight = attach_anomaly_decision_to_insight_v2(
            insight=insight,
            decision=decision,
        )
        records.append(
            EvidenceRecordV2(
                reference=next(
                    ref
                    for ref in insight.evidence
                    if ref.evidence_id == decision.evidence_id
                ),
                evidence_type=EvidenceTypeV2.ANOMALY_DECISION,
            )
        )

    pack = EvidencePackV2(
        pack_id="day89-anomaly-console-pack",
        analysis_scope=insight.analysis_scope,
        insight=insight,
        evidence_records=tuple(records),
    )

    return assemble_evidence_pack_delivery_v2(
        evidence_pack=pack,
        metric_definition=_metric_definition(),
    )


def test_anomaly_status_is_inherited_and_marker_is_true() -> None:
    decision = _decision()
    assert decision.status == AnomalyDecisionStatusV2.ANOMALY

    view = build_decision_console_view_v2(
        delivery=_delivery_for_decision(
            decision,
            publish_detected_anomaly=True,
        ),
        anomaly_decision=decision,
        anomaly_evidence_id=ANOMALY_EVIDENCE_ID,
    )

    assert view.anomaly is not None
    assert view.anomaly.status == decision.status
    assert view.anomaly.reason_code == decision.reason_code
    assert view.anomaly.absolute_change == decision.absolute_change
    assert view.anomaly.relative_change == decision.relative_change
    assert view.anomaly.show_anomaly_marker is True
    assert view.anomaly.published_as_detected_anomaly is True


def test_anomaly_requires_published_evidence() -> None:
    decision = _decision()

    try:
        build_decision_console_view_v2(
            delivery=_delivery_for_decision(
                decision,
                publish_detected_anomaly=False,
            ),
            anomaly_decision=decision,
        )
    except ValueError:
        return

    raise AssertionError(
        "ANOMALY verdict 必须绑定已发布 anomaly evidence。"
    )


def test_policy_not_found_does_not_fake_policy_or_marker() -> None:
    decision = _decision(policy="none")
    assert (
        decision.status
        == AnomalyDecisionStatusV2.POLICY_NOT_FOUND
    )

    view = build_decision_console_view_v2(
        delivery=_delivery_for_decision(
            decision,
            publish_detected_anomaly=False,
        ),
        anomaly_decision=decision,
    )

    assert view.anomaly is not None
    assert (
        view.anomaly.status
        == AnomalyDecisionStatusV2.POLICY_NOT_FOUND
    )
    assert view.anomaly.policy is None
    assert view.anomaly.show_anomaly_marker is False
    assert view.anomaly.published_as_detected_anomaly is False


def test_normal_does_not_show_anomaly_marker() -> None:
    decision = detect_anomaly_v2(
        evidence_id=ANOMALY_EVIDENCE_ID,
        metric_name="gmv",
        comparison=_comparison(),
        current_value=Decimal("110"),
        reference_value=Decimal("100"),
        current_sample_value=Decimal("100"),
        reference_sample_value=Decimal("100"),
        policy=_policy(),
    )
    assert decision.status == AnomalyDecisionStatusV2.NORMAL

    view = build_decision_console_view_v2(
        delivery=_delivery_for_decision(
            decision,
            publish_detected_anomaly=False,
        ),
        anomaly_decision=decision,
    )

    assert view.anomaly is not None
    assert view.anomaly.status == AnomalyDecisionStatusV2.NORMAL
    assert view.anomaly.show_anomaly_marker is False


def test_insufficient_sample_is_preserved() -> None:
    decision = _decision(
        current_sample="5",
        reference_sample="100",
    )
    assert (
        decision.status
        == AnomalyDecisionStatusV2.INSUFFICIENT_SAMPLE
    )

    view = build_decision_console_view_v2(
        delivery=_delivery_for_decision(
            decision,
            publish_detected_anomaly=False,
        ),
        anomaly_decision=decision,
    )

    assert view.anomaly is not None
    assert (
        view.anomaly.status
        == AnomalyDecisionStatusV2.INSUFFICIENT_SAMPLE
    )
    assert view.anomaly.current_sample_value == Decimal("5")
    assert view.anomaly.show_anomaly_marker is False


def test_not_comparable_preserves_undefined_relative_change() -> None:
    decision = detect_anomaly_v2(
        evidence_id=ANOMALY_EVIDENCE_ID,
        metric_name="gmv",
        comparison=_comparison(),
        current_value=Decimal("100"),
        reference_value=Decimal("0"),
        current_sample_value=Decimal("100"),
        reference_sample_value=Decimal("100"),
        policy=_policy(
            change_type=AnomalyChangeTypeV2.RELATIVE,
        ),
    )
    assert (
        decision.status
        == AnomalyDecisionStatusV2.NOT_COMPARABLE
    )
    assert decision.relative_change is None

    view = build_decision_console_view_v2(
        delivery=_delivery_for_decision(
            decision,
            publish_detected_anomaly=False,
        ),
        anomaly_decision=decision,
    )

    assert view.anomaly is not None
    assert (
        view.anomaly.status
        == AnomalyDecisionStatusV2.NOT_COMPARABLE
    )
    assert view.anomaly.relative_change is None
    assert view.anomaly.show_anomaly_marker is False


def test_non_anomaly_cannot_be_published_as_detected_anomaly() -> None:
    normal_decision = detect_anomaly_v2(
        evidence_id=ANOMALY_EVIDENCE_ID,
        metric_name="gmv",
        comparison=_comparison(),
        current_value=Decimal("110"),
        reference_value=Decimal("100"),
        current_sample_value=Decimal("100"),
        reference_sample_value=Decimal("100"),
        policy=_policy(),
    )

    anomaly_decision = _decision()
    published_delivery = _delivery_for_decision(
        anomaly_decision,
        publish_detected_anomaly=True,
    )

    try:
        build_decision_console_view_v2(
            delivery=published_delivery,
            anomaly_decision=normal_decision,
            anomaly_evidence_id=ANOMALY_EVIDENCE_ID,
        )
    except ValueError:
        return

    raise AssertionError(
        "非 ANOMALY verdict 不能复用 detected_anomaly evidence。"
    )


TESTS = (
    test_anomaly_status_is_inherited_and_marker_is_true,
    test_anomaly_requires_published_evidence,
    test_policy_not_found_does_not_fake_policy_or_marker,
    test_normal_does_not_show_anomaly_marker,
    test_insufficient_sample_is_preserved,
    test_not_comparable_preserves_undefined_relative_change,
    test_non_anomaly_cannot_be_published_as_detected_anomaly,
)


def run_acceptance() -> None:
    print("Day89 Decision Console Anomaly Projection Preflight")
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
    print("Day89 Decision Console Anomaly Projection Acceptance Summary")
    print(f"Total: {len(TESTS)}")
    print(f"Passed: {passed}")
    print(f"Failed: {len(failures)}")

    for failure in failures:
        print(f"- {failure}")

    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    run_acceptance()
