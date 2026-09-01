from __future__ import annotations

from datetime import date

from app.semantic_layer.business_request_preflight_v2 import (
    BusinessRequestPreflightOutcomeV2,
    evaluate_business_request_preflight_v2,
)
from app.semantic_layer.dataset_availability_contract_v2 import (
    DatasetAvailabilityOutcomeV2,
    DatasetBusinessWindowV2,
    evaluate_dataset_availability_v2,
)
from app.semantic_layer.time_window_resolver_v2 import (
    resolve_time_window_v2,
)


REFERENCE_DATE = date(2025, 12, 31)
BUSINESS_WINDOW = DatasetBusinessWindowV2(
    start_date=date(2024, 1, 1),
    end_date=date(2025, 12, 31),
)


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_f04_requires_business_metric_clarification() -> None:
    result = evaluate_business_request_preflight_v2(
        "2025年表现最好的渠道是哪一个？"
    )
    _assert(
        result.outcome
        == BusinessRequestPreflightOutcomeV2.NEEDS_CLARIFICATION,
        f"unexpected F04 outcome: {result}",
    )
    _assert(
        result.reason_code == "ambiguous_performance_metric",
        f"unexpected F04 reason: {result}",
    )
    _assert(
        "评价指标" in (result.user_message or ""),
        f"F04 user copy is not business-facing: {result}",
    )


def test_explicit_metric_best_channel_continues() -> None:
    result = evaluate_business_request_preflight_v2(
        "2025年GMV表现最好的渠道是哪一个？"
    )
    _assert(
        result.outcome
        == BusinessRequestPreflightOutcomeV2.CONTINUE,
        f"explicit metric ranking should continue: {result}",
    )


def test_f05_forecast_inventory_is_unsupported_before_query() -> None:
    result = evaluate_business_request_preflight_v2(
        "预测2026年1月GMV，并告诉我应该准备多少库存。"
    )
    _assert(
        result.outcome
        == BusinessRequestPreflightOutcomeV2.UNSUPPORTED_CAPABILITY,
        f"unexpected F05 outcome: {result}",
    )
    _assert(
        result.reason_code
        == "unsupported_forecast_and_inventory_planning",
        f"unexpected F05 reason: {result}",
    )
    _assert(
        "暂不支持查询" in (result.user_message or ""),
        f"F05 copy is not user-facing: {result}",
    )


def test_normal_fact_question_continues() -> None:
    result = evaluate_business_request_preflight_v2(
        "2025年一共有多少笔成功支付订单？"
    )
    _assert(
        result.outcome
        == BusinessRequestPreflightOutcomeV2.CONTINUE,
        f"normal FACT must continue: {result}",
    )


def _availability(question: str):
    time_resolution = resolve_time_window_v2(
        question,
        reference_date=REFERENCE_DATE,
    )
    return evaluate_dataset_availability_v2(
        time_resolution=time_resolution,
        business_window=BUSINESS_WINDOW,
    )


def test_b01_is_outside_business_window() -> None:
    result = _availability("2023年GMV是多少？")
    _assert(
        result.outcome
        == DatasetAvailabilityOutcomeV2.OUTSIDE_BUSINESS_WINDOW,
        f"unexpected B01 outcome: {result}",
    )
    _assert(
        result.reason_code
        == "requested_window_outside_dataset_business_window",
        f"unexpected B01 reason: {result}",
    )
    _assert(
        "2024-01-01" in (result.user_message or "")
        and "2025-12-31" in (result.user_message or ""),
        f"B01 copy must state dataset window: {result}",
    )


def test_2025_window_is_available() -> None:
    result = _availability("2025年GMV是多少？")
    _assert(
        result.outcome == DatasetAvailabilityOutcomeV2.AVAILABLE,
        f"2025 should be available: {result}",
    )


def test_partial_overlap_does_not_silently_clamp() -> None:
    result = _availability(
        "2023年12月1日至2024年1月31日GMV是多少？"
    )
    _assert(
        result.outcome == DatasetAvailabilityOutcomeV2.PARTIAL_OVERLAP,
        f"partial overlap must stop explicitly: {result}",
    )
    _assert(
        "部分超出" in (result.user_message or ""),
        f"partial overlap copy missing: {result}",
    )


def test_future_forecast_stops_before_dataset_availability_semantics() -> None:
    preflight = evaluate_business_request_preflight_v2(
        "预测2026年1月GMV"
    )
    _assert(
        preflight.outcome
        == BusinessRequestPreflightOutcomeV2.UNSUPPORTED_CAPABILITY,
        f"forecast must stop at capability preflight: {preflight}",
    )


def run_acceptance() -> None:
    tests = (
        test_f04_requires_business_metric_clarification,
        test_explicit_metric_best_channel_continues,
        test_f05_forecast_inventory_is_unsupported_before_query,
        test_normal_fact_question_continues,
        test_b01_is_outside_business_window,
        test_2025_window_is_available,
        test_partial_overlap_does_not_silently_clamp,
        test_future_forecast_stops_before_dataset_availability_semantics,
    )

    passed = 0
    for test in tests:
        test()
        passed += 1
        print(f"PASS {passed:02d}: {test.__name__}")

    print(f"Day93 Preflight Boundary Acceptance: {passed}/{len(tests)} PASS")


if __name__ == "__main__":
    run_acceptance()
