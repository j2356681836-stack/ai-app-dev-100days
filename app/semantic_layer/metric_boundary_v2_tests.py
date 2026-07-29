from pydantic import ValidationError

from app.semantic_layer.metric_boundary_v2 import (
    BoundaryOutcome,
    MetricBoundaryDecisionV2,
    evaluate_metric_boundary_v2,
)


def assert_equal(
    actual,
    expected,
    message: str,
) -> None:
    if actual != expected:
        raise AssertionError(
            f"{message}\nExpected: {expected}\nActual: {actual}"
        )


def assert_true(
    condition: bool,
    message: str,
) -> None:
    if not condition:
        raise AssertionError(message)


def test_generic_new_customer_requires_clarification() -> None:
    decision = evaluate_metric_boundary_v2(
        "今年新增客户一共有多少？"
    )

    assert_equal(
        decision.outcome,
        BoundaryOutcome.NEEDS_CLARIFICATION,
        "泛化“新增客户”必须进入 Brand vs Channel 澄清。",
    )

    assert_equal(
        set(decision.candidates),
        {
            "brand_paid_new_customer_count",
            "channel_paid_new_customer_count",
        },
        "新客澄清候选错误。",
    )


def test_explicit_brand_new_customer_can_continue() -> None:
    decision = evaluate_metric_boundary_v2(
        "2025年品牌新客有多少？"
    )

    assert_equal(
        decision.outcome,
        BoundaryOutcome.CONTINUE,
        "明确品牌口径后不得继续澄清。",
    )


def test_explicit_channel_new_customer_can_continue() -> None:
    decision = evaluate_metric_boundary_v2(
        "各渠道支付新客数"
    )

    assert_equal(
        decision.outcome,
        BoundaryOutcome.CONTINUE,
        "明确渠道新客后不得继续澄清。",
    )


def test_generic_repeat_people_requires_clarification() -> None:
    decision = evaluate_metric_boundary_v2(
        "今年复购人数有多少？"
    )

    assert_equal(
        decision.outcome,
        BoundaryOutcome.NEEDS_CLARIFICATION,
        "未限定复购人数口径必须澄清。",
    )

    assert_equal(
        set(decision.candidates),
        {
            "repeat_customer_count",
            "multi_order_customer_count",
        },
        "复购人数澄清候选错误。",
    )


def test_cross_day_repeat_people_can_continue() -> None:
    assert_equal(
        evaluate_metric_boundary_v2(
            "今年跨日复购客户数"
        ).outcome,
        BoundaryOutcome.CONTINUE,
        "明确跨日口径不得误判歧义。",
    )


def test_multi_order_repeat_people_can_continue() -> None:
    assert_equal(
        evaluate_metric_boundary_v2(
            "今年两单及以上复购人数"
        ).outcome,
        BoundaryOutcome.CONTINUE,
        "明确两单口径不得误判歧义。",
    )


def test_net_sales_is_unsupported() -> None:
    decision = evaluate_metric_boundary_v2(
        "今年退款后的净销售额是多少？"
    )

    assert_equal(
        decision.outcome,
        BoundaryOutcome.UNSUPPORTED,
        "Net Sales 不属于当前 GMV Contract。",
    )

    assert_equal(
        decision.reason_code,
        "unsupported_net_sales",
        "Net Sales reason code 错误。",
    )


def test_count_based_refund_rate_is_unsupported() -> None:
    decision = evaluate_metric_boundary_v2(
        "退款订单数占支付订单数的比例是多少？"
    )

    assert_equal(
        decision.reason_code,
        "unsupported_count_based_refund_rate",
        "Count-based Refund Rate 边界错误。",
    )


def test_current_membership_basis_is_unsupported() -> None:
    decision = evaluate_metric_boundary_v2(
        "按当前会员身份计算会员GMV占比"
    )

    assert_equal(
        decision.reason_code,
        "unsupported_current_membership_basis",
        "Current Membership Basis 边界错误。",
    )


def test_cohort_repeat_is_unsupported_before_new_customer_ambiguity() -> None:
    decision = evaluate_metric_boundary_v2(
        "双11新客30天复购率是多少？"
    )

    assert_equal(
        decision.outcome,
        BoundaryOutcome.UNSUPPORTED,
        "Cohort Repeat 应优先于 generic 新客 ambiguity。",
    )

    assert_equal(
        decision.reason_code,
        "unsupported_cohort_repeat_rate",
        "Cohort Repeat reason code 错误。",
    )


def test_net_profit_margin_is_unsupported() -> None:
    assert_equal(
        evaluate_metric_boundary_v2(
            "今年净利润率是多少？"
        ).reason_code,
        "unsupported_net_profit_margin",
        "净利润率不得冒充 Gross Margin Rate。",
    )


def test_unit_selling_price_is_unsupported() -> None:
    assert_equal(
        evaluate_metric_boundary_v2(
            "平均每件商品卖多少钱？"
        ).reason_code,
        "unsupported_unit_selling_price",
        "平均单件售价不得冒充 AUS。",
    )


def test_ltv_is_unsupported() -> None:
    assert_equal(
        evaluate_metric_boundary_v2(
            "今年客户生命周期价值是多少？"
        ).reason_code,
        "unsupported_customer_lifetime_value",
        "LTV 应保持 unsupported。",
    )


def test_normal_metric_question_continues() -> None:
    assert_equal(
        evaluate_metric_boundary_v2(
            "各渠道GMV排名"
        ).outcome,
        BoundaryOutcome.CONTINUE,
        "普通合法 Metric 不应被 Boundary 误拦截。",
    )


def test_model_rejects_invalid_clarification_without_candidates() -> None:
    try:
        MetricBoundaryDecisionV2(
            outcome=BoundaryOutcome.NEEDS_CLARIFICATION,
            reason_code="invalid",
        )
    except ValidationError:
        return

    raise AssertionError(
        "Clarification without candidates 必须被拒绝。"
    )


def run_tests() -> None:
    tests = [
        test_generic_new_customer_requires_clarification,
        test_explicit_brand_new_customer_can_continue,
        test_explicit_channel_new_customer_can_continue,
        test_generic_repeat_people_requires_clarification,
        test_cross_day_repeat_people_can_continue,
        test_multi_order_repeat_people_can_continue,
        test_net_sales_is_unsupported,
        test_count_based_refund_rate_is_unsupported,
        test_current_membership_basis_is_unsupported,
        test_cohort_repeat_is_unsupported_before_new_customer_ambiguity,
        test_net_profit_margin_is_unsupported,
        test_unit_selling_price_is_unsupported,
        test_ltv_is_unsupported,
        test_normal_metric_question_continues,
        test_model_rejects_invalid_clarification_without_candidates,
    ]

    passed = 0
    failed = 0

    for test in tests:
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
    print("Metric Boundary V2 Test Summary")
    print(f"Total: {len(tests)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    run_tests()
