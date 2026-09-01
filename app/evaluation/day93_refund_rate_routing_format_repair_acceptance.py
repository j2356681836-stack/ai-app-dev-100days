from __future__ import annotations

from decimal import Decimal

from app.semantic_layer.query_plan_selector_v2 import (
    QueryPlanSelectionStatusV2,
    select_query_plan_v2,
)
from app.semantic_layer.result_grain_resolver_v2 import (
    ResultGrainResolutionStatusV2,
    apply_fact_overall_fallback_v2,
    resolve_result_grain_v2,
)
from app.ui.decision_console_presenters_v2 import (
    format_business_metric_value_v2,
)


def _assert_grain_and_plan(
    *,
    question: str,
    expected_grain: str,
    expected_plan: str,
) -> None:
    grain = resolve_result_grain_v2(
        question
    )

    assert (
        grain.status
        == ResultGrainResolutionStatusV2.RESOLVED
    )
    assert grain.grain_key == expected_grain

    # FACT overall fallback must never overwrite explicit Grain.
    after_fallback = apply_fact_overall_fallback_v2(
        resolution=grain,
        analysis_mode="fact",
    )

    assert after_fallback.grain_key == expected_grain

    selection = select_query_plan_v2(
        metric_name="refund_rate",
        grain_resolution=after_fallback,
    )

    assert (
        selection.status
        == QueryPlanSelectionStatusV2.MATCHED
    )
    assert selection.plan_names == (
        expected_plan,
    )


def run_acceptance() -> None:
    passed = 0

    _assert_grain_and_plan(
        question="2025年哪个品类退款率最高？",
        expected_grain="category",
        expected_plan="refund_rate_category_v2",
    )
    passed += 1

    _assert_grain_and_plan(
        question="2025年哪个渠道退款率最高？",
        expected_grain="channel",
        expected_plan="refund_rate_channel_v2",
    )
    passed += 1

    _assert_grain_and_plan(
        question="2025年哪个地区退款率最低？",
        expected_grain="region",
        expected_plan="refund_rate_region_v2",
    )
    passed += 1

    ranking = resolve_result_grain_v2(
        "2025年各渠道退款率排名"
    )
    assert (
        ranking.status
        == ResultGrainResolutionStatusV2.RESOLVED
    )
    assert ranking.grain_key == "channel"
    passed += 1

    overall = resolve_result_grain_v2(
        "2025年退款率是多少？"
    )
    assert (
        overall.status
        == ResultGrainResolutionStatusV2.RESOLVED
    )
    assert overall.grain_key == "overall"
    passed += 1

    assert (
        format_business_metric_value_v2(
            "refund_rate",
            Decimal("0.08"),
        )
        == "8.00%"
    )
    passed += 1

    print(
        "Day93 Refund Rate Routing + Format Repair "
        f"Acceptance: {passed}/6 PASS"
    )


if __name__ == "__main__":
    run_acceptance()
