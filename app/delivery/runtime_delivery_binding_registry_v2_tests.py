from __future__ import annotations

from app.delivery.decision_console_runtime_v2 import (
    build_day89_business_question_tool_binding_registry_v2,
    build_day89_channel_buyer_count_tool_binding_v2,
    build_day89_channel_order_count_tool_binding_v2,
    build_day89_channel_tool_binding_v2,
    build_day89_overall_gmv_tool_binding_v2,
    build_day89_overall_order_count_tool_binding_v2,
    build_day93_category_refund_rate_tool_binding_v2,
    build_day93_channel_refund_rate_tool_binding_v2,
    build_day93_overall_refund_rate_tool_binding_v2,
    build_day93_region_refund_rate_tool_binding_v2,
)
from app.delivery.runtime_delivery_bridge_v2 import (
    _select_approved_tool_binding_for_plan_v2,
)


def _assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(
            f"{message}\nExpected: {expected}\nActual: {actual}"
        )


def test_primary_channel_binding_still_matches() -> None:
    channel = build_day89_channel_tool_binding_v2()
    overall = build_day89_overall_gmv_tool_binding_v2()

    selected = _select_approved_tool_binding_for_plan_v2(
        actual_plan_name="gmv_channel_v2",
        primary_binding=channel,
        approved_tool_binding_registry=(overall,),
    )

    _assert_equal(
        selected,
        channel,
        "gmv_channel_v2 必须继续选择原 channel binding。",
    )


def test_overall_binding_is_selected_from_static_registry() -> None:
    channel = build_day89_channel_tool_binding_v2()
    overall = build_day89_overall_gmv_tool_binding_v2()
    registry = (
        build_day89_business_question_tool_binding_registry_v2()
    )

    selected = _select_approved_tool_binding_for_plan_v2(
        actual_plan_name="gmv_overall_v2",
        primary_binding=channel,
        approved_tool_binding_registry=registry,
    )

    _assert_equal(
        selected,
        overall,
        "gmv_overall_v2 必须选择已预注册的 overall binding。",
    )


def test_order_count_binding_is_selected_from_static_registry() -> None:
    channel = build_day89_channel_tool_binding_v2()
    registry = (
        build_day89_business_question_tool_binding_registry_v2()
    )

    selected = _select_approved_tool_binding_for_plan_v2(
        actual_plan_name="order_count_overall_v2",
        primary_binding=channel,
        approved_tool_binding_registry=registry,
    )

    expected = build_day89_overall_order_count_tool_binding_v2()

    _assert_equal(
        selected,
        expected,
        "order_count_overall_v2 必须选择显式注册的订单数 binding。",
    )


def test_order_count_channel_binding_is_selected_from_static_registry() -> None:
    channel = build_day89_channel_tool_binding_v2()
    registry = (
        build_day89_business_question_tool_binding_registry_v2()
    )

    selected = _select_approved_tool_binding_for_plan_v2(
        actual_plan_name="order_count_channel_v2",
        primary_binding=channel,
        approved_tool_binding_registry=registry,
    )

    expected = build_day89_channel_order_count_tool_binding_v2()

    _assert_equal(
        selected,
        expected,
        "order_count_channel_v2 必须选择显式注册的渠道订单数 binding。",
    )


def test_buyer_count_channel_binding_is_selected_from_static_registry() -> None:
    channel = build_day89_channel_tool_binding_v2()
    registry = (
        build_day89_business_question_tool_binding_registry_v2()
    )

    selected = _select_approved_tool_binding_for_plan_v2(
        actual_plan_name="buyer_count_channel_v2",
        primary_binding=channel,
        approved_tool_binding_registry=registry,
    )

    expected = build_day89_channel_buyer_count_tool_binding_v2()

    _assert_equal(
        selected,
        expected,
        "buyer_count_channel_v2 必须选择显式注册的渠道购买人数 binding。",
    )


def test_refund_rate_bindings_are_selected_from_static_registry() -> None:
    channel = build_day89_channel_tool_binding_v2()
    registry = (
        build_day89_business_question_tool_binding_registry_v2()
    )

    expectations = (
        (
            "refund_rate_overall_v2",
            build_day93_overall_refund_rate_tool_binding_v2(),
        ),
        (
            "refund_rate_channel_v2",
            build_day93_channel_refund_rate_tool_binding_v2(),
        ),
        (
            "refund_rate_region_v2",
            build_day93_region_refund_rate_tool_binding_v2(),
        ),
        (
            "refund_rate_category_v2",
            build_day93_category_refund_rate_tool_binding_v2(),
        ),
    )

    for plan_name, expected in expectations:
        selected = _select_approved_tool_binding_for_plan_v2(
            actual_plan_name=plan_name,
            primary_binding=channel,
            approved_tool_binding_registry=registry,
        )

        _assert_equal(
            selected,
            expected,
            f"{plan_name} 必须选择显式注册的退款率 binding。",
        )


def test_business_question_registry_is_static_and_unique() -> None:
    registry = (
        build_day89_business_question_tool_binding_registry_v2()
    )

    plan_names = tuple(
        binding.plan_name
        for binding in registry
    )

    _assert_equal(
        plan_names,
        (
            "gmv_overall_v2",
            "order_count_overall_v2",
            "order_count_channel_v2",
            "buyer_count_channel_v2",
            "refund_rate_overall_v2",
            "refund_rate_channel_v2",
            "refund_rate_region_v2",
            "refund_rate_category_v2",
        ),
        "Business Question Registry 必须保持当前显式批准集合。",
    )

    _assert_equal(
        len(plan_names),
        len(set(plan_names)),
        "Approved Registry plan_name 不得重复。",
    )


def test_unregistered_plan_remains_fail_closed() -> None:
    channel = build_day89_channel_tool_binding_v2()
    registry = (
        build_day89_business_question_tool_binding_registry_v2()
    )

    selected = _select_approved_tool_binding_for_plan_v2(
        actual_plan_name="gmv_region_v2",
        primary_binding=channel,
        approved_tool_binding_registry=registry,
    )

    _assert_equal(
        selected,
        None,
        "未注册 Query Plan 不得动态创建 Tool Binding。",
    )


def test_duplicate_registration_is_rejected() -> None:
    channel = build_day89_channel_tool_binding_v2()

    try:
        _select_approved_tool_binding_for_plan_v2(
            actual_plan_name="gmv_channel_v2",
            primary_binding=channel,
            approved_tool_binding_registry=(channel,),
        )
    except ValueError:
        return

    raise AssertionError(
        "重复 plan_name 的 Approved Binding Registry 必须拒绝。"
    )


_TESTS = (
    test_primary_channel_binding_still_matches,
    test_overall_binding_is_selected_from_static_registry,
    test_order_count_binding_is_selected_from_static_registry,
    test_order_count_channel_binding_is_selected_from_static_registry,
    test_buyer_count_channel_binding_is_selected_from_static_registry,
    test_refund_rate_bindings_are_selected_from_static_registry,
    test_business_question_registry_is_static_and_unique,
    test_unregistered_plan_remains_fail_closed,
    test_duplicate_registration_is_rejected,
)


def run_tests() -> None:
    passed = 0
    failed = 0

    for test in _TESTS:
        print("=" * 80)
        print(f"Running: {test.__name__}")

        try:
            test()
            passed += 1
            print("[PASS]")
        except Exception as exc:
            failed += 1
            print("[FAIL]")
            print(exc)

    print("=" * 80)
    print("Runtime Delivery Binding Registry V2 Test Summary")
    print(f"Total: {len(_TESTS)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    run_tests()
