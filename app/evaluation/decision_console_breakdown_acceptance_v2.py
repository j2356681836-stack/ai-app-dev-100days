from __future__ import annotations

import inspect
from datetime import date
from decimal import Decimal

import app.delivery.decision_console_view_v2 as console_view_module
from app.agents.evidence_pack_delivery_v2 import (
    MetricDefinitionSnapshotV2,
    assemble_evidence_pack_delivery_v2,
)
from app.agents.evidence_pack_v2 import (
    EvidencePackV2,
    EvidenceRecordV2,
    EvidenceTypeV2,
    GovernedEvidenceProvenanceV2,
    ProtectedResultV2,
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
BREAKDOWN_ID = "ev-channel-breakdown"


def _comparison() -> TimeComparisonContractV2:
    return TimeComparisonContractV2(
        comparison_type=ComparisonTypeV2.YOY,
        period_mode=PeriodModeV2.COMPLETED_PERIOD,
        alignment_mode=AlignmentModeV2.CALENDAR_ALIGNED,
        current_window=TimeWindowReferenceV2(
            start_date=date(2025, 7, 1),
            end_date=date(2025, 7, 31),
        ),
        reference_window=TimeWindowReferenceV2(
            start_date=date(2024, 7, 1),
            end_date=date(2024, 7, 31),
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


def _provenance(
    *,
    window: TimeWindowReferenceV2,
    result_grain: str = "channel",
) -> GovernedEvidenceProvenanceV2:
    return GovernedEvidenceProvenanceV2(
        dataset_name="beauty_bi_v2",
        target_schema="analytics",
        metric_name="gmv",
        result_grain=result_grain,
        analysis_window=window,
        scope_summary="authorized_scope_only",
        plan_name="gmv_by_channel",
        query_plan_fingerprint="plan-channel",
        envelope_fingerprint="envelope-channel",
        compiled_contract_fingerprint="compiled-channel",
        sql_fingerprint="sql-channel",
        time_binding_fingerprint="time-channel",
        scope_binding_fingerprint="scope-channel",
        tool_name="governed_metric_query",
        tool_version="v2",
        audit_event_id="audit-channel",
        audit_event_fingerprint="audit-fp-channel",
        audit_record_hash="audit-hash-channel",
        finalization_contract_version="v2",
    )


def _governed_breakdown_record(
    *,
    window: TimeWindowReferenceV2,
    result_grain: str = "channel",
) -> EvidenceRecordV2:
    return EvidenceRecordV2(
        reference=EvidenceReferenceV2(
            evidence_id=BREAKDOWN_ID,
            source="governed_query_result_v2",
            description="当前周期按渠道的受保护 GMV 分解。",
        ),
        evidence_type=EvidenceTypeV2.GOVERNED_QUERY_RESULT,
        provenance=_provenance(
            window=window,
            result_grain=result_grain,
        ),
        protected_result=ProtectedResultV2(
            field_names=("channel_name", "gmv"),
            rows=(
                {
                    "channel_name": "Tmall",
                    "gmv": Decimal("2586549.37"),
                },
                {
                    "channel_name": "JD",
                    "gmv": Decimal("1800000.00"),
                },
            ),
            row_count=2,
        ),
    )


def _non_governed_record() -> EvidenceRecordV2:
    return EvidenceRecordV2(
        reference=EvidenceReferenceV2(
            evidence_id="ev-anomaly",
            source="deterministic_anomaly_detector_v2",
            description="测试 anomaly evidence。",
        ),
        evidence_type=EvidenceTypeV2.ANOMALY_DECISION,
    )


def _delivery(
    *,
    record: EvidenceRecordV2 | None = None,
):
    comparison = _comparison()
    scope = AnalysisScopeV2(
        metric_name="gmv",
        analysis_window=comparison.current_window,
        comparison=comparison,
        result_grain="channel",
        scope_summary="authorized_scope_only",
    )
    insight = InsightContractV2(
        analysis_mode=AnalysisModeV2.DIAGNOSTIC,
        analysis_scope=scope,
    )

    records = (
        (record,)
        if record is not None
        else (
            _governed_breakdown_record(
                window=comparison.current_window,
            ),
        )
    )

    pack = EvidencePackV2(
        pack_id="day89-breakdown-pack",
        analysis_scope=scope,
        insight=insight,
        evidence_records=records,
    )

    return assemble_evidence_pack_delivery_v2(
        evidence_pack=pack,
        metric_definition=_metric_definition(),
    )


def test_protected_rows_are_projected_exactly() -> None:
    delivery = _delivery()
    source = delivery.evidence_pack.evidence_records[0].protected_result
    assert source is not None

    view = build_decision_console_view_v2(
        delivery=delivery,
        breakdown_evidence_id=BREAKDOWN_ID,
    )

    assert view.breakdown is not None
    assert view.breakdown.field_names == source.field_names
    assert view.breakdown.rows == source.rows
    assert view.breakdown.row_count == source.row_count


def test_breakdown_provenance_is_inherited() -> None:
    delivery = _delivery()
    source = delivery.evidence_pack.evidence_records[0].provenance
    assert source is not None

    view = build_decision_console_view_v2(
        delivery=delivery,
        breakdown_evidence_id=BREAKDOWN_ID,
    )

    assert view.breakdown is not None
    assert view.breakdown.dataset_name == source.dataset_name
    assert view.breakdown.plan_name == source.plan_name
    assert view.breakdown.tool_name == source.tool_name
    assert view.breakdown.audit_event_id == source.audit_event_id


def test_missing_breakdown_evidence_fails_closed() -> None:
    try:
        build_decision_console_view_v2(
            delivery=_delivery(),
            breakdown_evidence_id="missing-breakdown",
        )
    except ValueError:
        return

    raise AssertionError(
        "不存在的 Breakdown Evidence 必须 fail-closed。"
    )


def test_non_governed_evidence_fails_closed() -> None:
    try:
        build_decision_console_view_v2(
            delivery=_delivery(
                record=_non_governed_record(),
            ),
            breakdown_evidence_id="ev-anomaly",
        )
    except ValueError:
        return

    raise AssertionError(
        "Breakdown 不能绑定非 GOVERNED_QUERY_RESULT。"
    )


def test_reference_window_breakdown_fails_closed() -> None:
    comparison = _comparison()

    try:
        build_decision_console_view_v2(
            delivery=_delivery(
                record=_governed_breakdown_record(
                    window=comparison.reference_window,
                ),
            ),
            breakdown_evidence_id=BREAKDOWN_ID,
        )
    except ValueError:
        return

    raise AssertionError(
        "Day89 第一版 Breakdown 不能把 reference window "
        "冒充 current breakdown。"
    )


def test_wrong_result_grain_fails_closed() -> None:
    comparison = _comparison()

    try:
        build_decision_console_view_v2(
            delivery=_delivery(
                record=_governed_breakdown_record(
                    window=comparison.current_window,
                    result_grain="region",
                ),
            ),
            breakdown_evidence_id=BREAKDOWN_ID,
        )
    except ValueError:
        return

    raise AssertionError(
        "Breakdown result_grain 不一致必须 fail-closed。"
    )


def test_breakdown_is_optional() -> None:
    view = build_decision_console_view_v2(
        delivery=_delivery(),
    )

    assert view.breakdown is None


TESTS = (
    test_protected_rows_are_projected_exactly,
    test_breakdown_provenance_is_inherited,
    test_missing_breakdown_evidence_fails_closed,
    test_non_governed_evidence_fails_closed,
    test_reference_window_breakdown_fails_closed,
    test_wrong_result_grain_fails_closed,
    test_breakdown_is_optional,
)


def run_acceptance() -> None:
    print("Day89 Decision Console Protected Breakdown Preflight")
    print(f"Module: {console_view_module.__file__}")
    print(f"Version: {VIEW_CONTRACT_VERSION}")
    print(
        "Signature: "
        f"{inspect.signature(build_decision_console_view_v2)}"
    )

    if VIEW_CONTRACT_VERSION != EXPECTED_VIEW_VERSION:
        raise SystemExit(
            "Loaded Decision Console View version is stale: "
            f"expected={EXPECTED_VIEW_VERSION}; "
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
    print(
        "Day89 Decision Console Protected Breakdown "
        "Acceptance Summary"
    )
    print(f"Total: {len(TESTS)}")
    print(f"Passed: {passed}")
    print(f"Failed: {len(failures)}")

    for failure in failures:
        print(f"- {failure}")

    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    run_acceptance()
