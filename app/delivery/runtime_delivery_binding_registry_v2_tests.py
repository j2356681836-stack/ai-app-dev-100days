from __future__ import annotations

from app.delivery.decision_console_runtime_v2 import (
    build_day89_channel_tool_binding_v2,
    build_day89_overall_gmv_tool_binding_v2,
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

    selected = _select_approved_tool_binding_for_plan_v2(
        actual_plan_name="gmv_overall_v2",
        primary_binding=channel,
        approved_tool_binding_registry=(overall,),
    )

    _assert_equal(
        selected,
        overall,
        "gmv_overall_v2 必须选择已预注册的 overall binding。",
    )


def test_unregistered_plan_remains_fail_closed() -> None:
    channel = build_day89_channel_tool_binding_v2()
    overall = build_day89_overall_gmv_tool_binding_v2()

    selected = _select_approved_tool_binding_for_plan_v2(
        actual_plan_name="gmv_region_v2",
        primary_binding=channel,
        approved_tool_binding_registry=(overall,),
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
