from __future__ import annotations

from datetime import date

from app.delivery.business_clarification_continuation_v1 import (
    build_pending_business_clarification_v1,
    resolve_business_clarification_v1,
)
from app.delivery.runtime_delivery_bridge_v2 import (
    RuntimeDeliveryBridgeResultV2,
    RuntimeDeliveryBridgeStatusV2,
)
from app.semantic_layer.query_plan_selector_v2 import (
    QueryPlanSelectionStatusV2,
    select_query_plan_v2,
)
from app.semantic_layer.result_grain_resolver_v2 import (
    ResultGrainResolutionStatusV2,
    resolve_result_grain_v2,
)


def _f04_stop() -> RuntimeDeliveryBridgeResultV2:
    return RuntimeDeliveryBridgeResultV2(
        status=RuntimeDeliveryBridgeStatusV2.GRAPH_STOPPED,
        message="需要先确定评价指标。",
        safe_runtime_result={
            "success": False,
            "outcome": "stopped",
            "stop_stage": "business_request_preflight",
            "reason_code": "ambiguous_performance_metric",
        },
    )


def _assert_plan(
    *,
    metric_name: str,
    expected_plan_name: str,
    grain,
) -> None:
    selection = select_query_plan_v2(
        metric_name=metric_name,
        grain_resolution=grain,
    )

    assert selection.status == QueryPlanSelectionStatusV2.MATCHED
    assert selection.plan_names == (expected_plan_name,)


def run_acceptance() -> None:
    passed = 0

    channel = resolve_result_grain_v2(
        "2025年表现最好的渠道是哪一个？"
    )
    assert channel.status == ResultGrainResolutionStatusV2.RESOLVED
    assert channel.grain_key == "channel"
    passed += 1

    region = resolve_result_grain_v2(
        "2025年表现最好的地区是哪一个？"
    )
    assert region.status == ResultGrainResolutionStatusV2.RESOLVED
    assert region.grain_key == "region"
    passed += 1

    category = resolve_result_grain_v2(
        "2025年表现最好的品类是哪一个？"
    )
    assert category.status == ResultGrainResolutionStatusV2.RESOLVED
    assert category.grain_key == "category"
    passed += 1

    pending = build_pending_business_clarification_v1(
        original_question="2025年表现最好的渠道是哪一个？",
        runtime_result=_f04_stop(),
        reference_date=date(2026, 8, 29),
    )
    assert pending is not None
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

    expectations = (
        (
            "performance_metric_gmv",
            "gmv",
            "gmv_channel_v2",
        ),
        (
            "performance_metric_order_count",
            "order_count",
            "order_count_channel_v2",
        ),
        (
            "performance_metric_buyer_count",
            "buyer_count",
            "buyer_count_channel_v2",
        ),
    )

    for choice_id, metric_name, plan_name in expectations:
        resolution = resolve_business_clarification_v1(
            pending=pending,
            choice_id=choice_id,
        )

        assert resolution.selected_metric_name == metric_name
        assert (
            resolution.preserved_grain_resolution.grain_key
            == "channel"
        )
        assert (
            resolution.preserved_time_resolution
            == pending.preserved_time_resolution
        )
        assert (
            resolution.preserved_requested_scope
            == pending.preserved_requested_scope
        )

        _assert_plan(
            metric_name=metric_name,
            expected_plan_name=plan_name,
            grain=resolution.preserved_grain_resolution,
        )
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
            "UI invented choice_id must remain fail closed."
        )

    print(
        "Day93 Structured Clarification Context Repair "
        f"Acceptance: {passed}/8 PASS"
    )


if __name__ == "__main__":
    run_acceptance()
