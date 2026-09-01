from __future__ import annotations

from datetime import date, datetime, timezone

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
from app.delivery.analysis_session_history_v1 import (
    build_analysis_history_item_v1,
)
from app.delivery.runtime_delivery_bridge_v2 import (
    RuntimeDeliveryBridgeResultV2,
    RuntimeDeliveryBridgeStatusV2,
)
from app.semantic_layer.time_comparison_contract_v2 import (
    TimeWindowReferenceV2,
)


def run_acceptance() -> None:
    window = TimeWindowReferenceV2(
        start_date=date(2025, 1, 1),
        end_date=date(2025, 12, 31),
    )

    scope = AnalysisScopeV2(
        metric_name="gmv",
        analysis_window=window,
        result_grain="channel",
        scope_summary="test scope",
    )

    reference = EvidenceReferenceV2(
        evidence_id="ev_history_real_record",
        source="tool:test",
        description="真实 EvidenceRecordV2 结构测试。",
    )

    provenance = GovernedEvidenceProvenanceV2(
        dataset_name="beauty_bi_v2",
        target_schema="beauty_bi_v2",
        metric_name="gmv",
        result_grain="channel",
        analysis_window=window,
        scope_summary="test scope",
        plan_name="gmv_channel_v2",
        query_plan_fingerprint="qpf",
        envelope_fingerprint="env",
        compiled_contract_fingerprint="compiled",
        sql_fingerprint="sql",
        time_binding_fingerprint="time",
        scope_binding_fingerprint="scope",
        tool_name="governed_gmv_channel_query",
        tool_version="dataset_v2",
        audit_event_id="audit-event",
        audit_event_fingerprint="audit-fp",
        audit_record_hash="audit-hash",
        finalization_contract_version="governed_finalization_v1",
    )

    record = EvidenceRecordV2(
        reference=reference,
        evidence_type=EvidenceTypeV2.GOVERNED_QUERY_RESULT,
        provenance=provenance,
        protected_result=ProtectedResultV2(
            field_names=("channel_name", "gmv"),
            rows=(
                {
                    "channel_name": "天猫旗舰店",
                    "gmv": 100,
                },
            ),
            row_count=1,
        ),
    )

    insight = InsightContractV2(
        analysis_mode=AnalysisModeV2.FACT,
        analysis_scope=scope,
        evidence=(reference,),
    )

    pack = EvidencePackV2(
        pack_id="pack_history_real_record",
        analysis_scope=scope,
        insight=insight,
        evidence_records=(record,),
    )

    # RuntimeDeliveryBridgeResultV2 READY normally requires several
    # delivery artifacts. For this focused unit acceptance, construct the
    # minimal real-shape object needed by History Builder.
    runtime_delivery = RuntimeDeliveryBridgeResultV2.model_construct(
        status=RuntimeDeliveryBridgeStatusV2.READY,
        message="测试历史快照",
        safe_runtime_result={"success": True},
        requested_scope=None,
        delivery=type(
            "DeliveryStub",
            (),
            {"evidence_pack": pack},
        )(),
        console_view=object(),
        executive_brief=object(),
    )

    item = build_analysis_history_item_v1(
        original_question="2025年各渠道GMV是多少？",
        runtime_delivery=runtime_delivery,
        history_id="history_real_record",
        created_at_utc=datetime(
            2026, 8, 29, 8, 0,
            tzinfo=timezone.utc,
        ),
    )

    assert item.evidence_ids == (
        "ev_history_real_record",
    )
    assert item.follow_up_context.evidence_ids == (
        "ev_history_real_record",
    )

    print(
        "Day93 History Evidence ID Repair Acceptance: "
        "1/1 PASS"
    )


if __name__ == "__main__":
    run_acceptance()
