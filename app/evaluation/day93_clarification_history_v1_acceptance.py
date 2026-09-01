from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

from app.delivery.analysis_session_history_v1 import (
    AnalysisSessionHistoryV1,
    append_analysis_history_item_v1,
    build_analysis_history_item_v1,
    empty_analysis_session_history_v1,
)
from app.delivery.business_clarification_continuation_v1 import (
    build_pending_business_clarification_v1,
    resolve_business_clarification_v1,
)
from app.delivery.decision_console_runtime_v2 import (
    build_day89_business_question_tool_binding_registry_v2,
)
from app.delivery.runtime_delivery_bridge_v2 import (
    RuntimeDeliveryBridgeResultV2,
    RuntimeDeliveryBridgeStatusV2,
)
from app.semantic_layer.time_comparison_contract_v2 import (
    TimeWindowReferenceV2,
)


def _stopped_f04_result() -> RuntimeDeliveryBridgeResultV2:
    return RuntimeDeliveryBridgeResultV2(
        status=RuntimeDeliveryBridgeStatusV2.GRAPH_STOPPED,
        message=(
            "“表现最好”需要先确定评价指标。"
        ),
        safe_runtime_result={
            "success": False,
            "outcome": "stopped",
            "stop_stage": "business_request_preflight",
            "reason_code": "ambiguous_performance_metric",
        },
    )


def _fake_ready_result(
    *,
    question: str = "2025年上海地区GMV是多少？",
) -> RuntimeDeliveryBridgeResultV2:
    scope = SimpleNamespace(
        metric_name="gmv",
        analysis_window=TimeWindowReferenceV2(
            start_date=date(2025, 1, 1),
            end_date=date(2025, 12, 31),
        ),
        result_grain="overall",
    )

    record = SimpleNamespace(
        reference=SimpleNamespace(
            evidence_id="ev_test_history"
        )
    )

    delivery = SimpleNamespace(
        evidence_pack=SimpleNamespace(
            analysis_scope=scope,
            evidence_records=(record,),
        )
    )

    return RuntimeDeliveryBridgeResultV2.model_construct(
        status=RuntimeDeliveryBridgeStatusV2.READY,
        message="GMV = 1,015,873.29",
        safe_runtime_result={
            "success": True,
            "question": question,
        },
        requested_scope=None,
        delivery=delivery,
        console_view=SimpleNamespace(),
        executive_brief=SimpleNamespace(),
    )


def run_acceptance() -> None:
    passed = 0

    pending = build_pending_business_clarification_v1(
        original_question="2025年表现最好的渠道是哪一个？",
        runtime_result=_stopped_f04_result(),
        reference_date=date(2026, 8, 29),
    )
    assert pending is not None
    assert len(pending.choices) == 3
    assert {
        choice.metric_name
        for choice in pending.choices
    } == {
        "gmv",
        "order_count",
        "buyer_count",
    }
    assert pending.preserved_grain_resolution.grain_key == "channel"
    assert (
        pending.preserved_time_resolution.requested_start_date
        == date(2025, 1, 1)
    )
    assert (
        pending.preserved_time_resolution.requested_end_date
        == date(2025, 12, 31)
    )
    passed += 1

    resolved = resolve_business_clarification_v1(
        pending=pending,
        choice_id="performance_metric_gmv",
    )
    assert "GMV" in resolved.resolved_question
    assert "2025年" in resolved.resolved_question
    assert "渠道" in resolved.resolved_question
    passed += 1

    try:
        resolve_business_clarification_v1(
            pending=pending,
            choice_id="ui_invented_metric",
        )
    except ValueError:
        passed += 1
    else:
        raise AssertionError(
            "UI invented choice_id must fail closed."
        )

    bindings = (
        build_day89_business_question_tool_binding_registry_v2()
    )
    plan_names = {
        item.plan_name
        for item in bindings
    }
    assert "order_count_channel_v2" in plan_names
    assert "buyer_count_channel_v2" in plan_names
    passed += 1

    ready = _fake_ready_result()
    item = build_analysis_history_item_v1(
        original_question="2025年上海地区GMV是多少？",
        runtime_delivery=ready,
        history_id="history_seed",
        created_at_utc=datetime(
            2026, 8, 29, 8, 0,
            tzinfo=timezone.utc,
        ),
    )
    assert item.metric_name == "gmv"
    assert item.analysis_window.start_date == date(2025, 1, 1)
    assert item.analysis_window.end_date == date(2025, 12, 31)
    assert item.evidence_ids == ("ev_test_history",)
    assert item.follow_up_context.source_history_id == "history_seed"
    passed += 1

    session = empty_analysis_session_history_v1()
    assert isinstance(session, AnalysisSessionHistoryV1)
    assert session.items == ()
    passed += 1

    for index in range(12):
        history_item = build_analysis_history_item_v1(
            original_question=f"问题{index}",
            runtime_delivery=ready,
            history_id=f"history_{index}",
            created_at_utc=datetime(
                2026, 8, 29, 8, index,
                tzinfo=timezone.utc,
            ),
        )
        session = append_analysis_history_item_v1(
            session=session,
            item=history_item,
        )

    assert len(session.items) == 10
    assert session.items[0].history_id == "history_11"
    assert session.items[-1].history_id == "history_2"
    assert session.active_history_id == "history_11"
    passed += 1

    assert all(
        history_item.runtime_delivery_snapshot.status
        == RuntimeDeliveryBridgeStatusV2.READY
        for history_item in session.items
    )
    passed += 1

    print(
        f"Day93 Clarification + Session History V1 "
        f"Acceptance: {passed}/8 PASS"
    )


if __name__ == "__main__":
    run_acceptance()
