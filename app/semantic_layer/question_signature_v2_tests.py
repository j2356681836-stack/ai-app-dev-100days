from __future__ import annotations

from app.semantic_layer.metric_signature_v2 import (
    IntrinsicPartition,
    SemanticOperand,
    SemanticQualifier,
)
from app.semantic_layer.question_signature_v2 import (
    QuestionOperator,
    extract_question_semantic_signature_v2,
)


def assert_equal(
    actual,
    expected,
    message: str,
) -> None:
    if actual != expected:
        raise AssertionError(
            f"{message}\n"
            f"Expected: {expected}\n"
            f"Actual: {actual}"
        )


def assert_true(
    condition: bool,
    message: str,
) -> None:
    if not condition:
        raise AssertionError(
            message
        )


def test_spending_per_buyer_structure_without_metric_rule() -> None:
    signature = (
        extract_question_semantic_signature_v2(
            "商品付款总金额平均摊到每个不同付款客户后是多少？"
        )
    )

    assert_equal(
        signature.operator,
        QuestionOperator.DIVIDE,
        "应识别为 divide。",
    )
    assert_equal(
        signature.left_operand,
        SemanticOperand.PAID_AMOUNT,
        "numerator 应为 paid_amount。",
    )
    assert_equal(
        signature.right_operand,
        SemanticOperand.PAID_BUYER,
        "denominator 应为 paid_buyer。",
    )


def test_ipt_structure() -> None:
    signature = (
        extract_question_semantic_signature_v2(
            "成功付款商品总数量除以成功付款单据笔数是多少？"
        )
    )

    assert_equal(
        (
            signature.operator,
            signature.left_operand,
            signature.right_operand,
        ),
        (
            QuestionOperator.DIVIDE,
            SemanticOperand.PAID_UNITS,
            SemanticOperand.PAID_ORDER,
        ),
        "IPT-like question 应解析 units / order。",
    )


def test_gross_margin_rate_structure() -> None:
    signature = (
        extract_question_semantic_signature_v2(
            "商品收入减成本后的金额，占商品实收金额的比例是多少？"
        )
    )

    assert_equal(
        (
            signature.operator,
            signature.left_operand,
            signature.right_operand,
        ),
        (
            QuestionOperator.DIVIDE,
            SemanticOperand.GROSS_MARGIN_AMOUNT,
            SemanticOperand.PAID_AMOUNT,
        ),
        "毛利率结构解析错误。",
    )

    assert_true(
        SemanticQualifier.PRODUCT_COST_BASIS
        in signature.qualifiers,
        "毛利结构应携带 product_cost_basis。",
    )


def test_channel_acquisition_structure() -> None:
    signature = (
        extract_question_semantic_signature_v2(
            "渠道营销投入除以该渠道第一次付款的客户数量是多少？"
        )
    )

    assert_equal(
        (
            signature.operator,
            signature.left_operand,
            signature.right_operand,
        ),
        (
            QuestionOperator.DIVIDE,
            SemanticOperand.MARKETING_SPEND,
            SemanticOperand.CHANNEL_FIRST_PAID_CUSTOMER,
        ),
        "CAC-like structure 解析错误。",
    )

    assert_equal(
        signature.intrinsic_partition,
        IntrinsicPartition.CHANNEL,
        "渠道问题应识别 channel partition。",
    )


def test_repeat_and_multi_order_are_structurally_distinct() -> None:
    repeat_signature = (
        extract_question_semantic_signature_v2(
            "统计在至少两个不同付款日期都出现过的不同客户数量"
        )
    )

    multi_signature = (
        extract_question_semantic_signature_v2(
            "统计成功付款交易达到两笔或更多的不同客户数量"
        )
    )

    assert_equal(
        repeat_signature.left_operand,
        SemanticOperand.REPEAT_DISTINCT_PAID_DATE_CUSTOMER,
        "跨日客户结构错误。",
    )

    assert_equal(
        multi_signature.left_operand,
        SemanticOperand.MULTI_PAID_ORDER_CUSTOMER,
        "多单客户结构错误。",
    )

    assert_true(
        SemanticQualifier.DISTINCT_PAID_DATES_GE_2
        in repeat_signature.qualifiers,
        "跨日结构缺 qualifier。",
    )

    assert_true(
        SemanticQualifier.PAID_ORDERS_GE_2
        in multi_signature.qualifiers,
        "多单结构缺 qualifier。",
    )


def test_member_snapshot_structure() -> None:
    signature = (
        extract_question_semantic_signature_v2(
            "付款当时带有会员等级的商品实收金额，占全部商品实收金额多少？"
        )
    )

    assert_equal(
        (
            signature.left_operand,
            signature.right_operand,
        ),
        (
            SemanticOperand.PAYMENT_TIME_MEMBER_PAID_AMOUNT,
            SemanticOperand.PAID_AMOUNT,
        ),
        "会员支付时点结构错误。",
    )

    assert_true(
        SemanticQualifier.PAYMENT_TIME_MEMBERSHIP_SNAPSHOT
        in signature.qualifiers,
        "支付时点会员 qualifier 缺失。",
    )


def test_refund_cohort_structure() -> None:
    signature = (
        extract_question_semantic_signature_v2(
            "按原购买期归属，完成退回金额相对原实付金额的比值"
        )
    )

    assert_equal(
        (
            signature.left_operand,
            signature.right_operand,
        ),
        (
            SemanticOperand.COMPLETED_REFUND_AMOUNT,
            SemanticOperand.PAID_AMOUNT,
        ),
        "退款金额比结构错误。",
    )

    assert_true(
        SemanticQualifier.SALES_COHORT_ATTRIBUTION
        in signature.qualifiers,
        "退款 sales cohort qualifier 缺失。",
    )


def test_partial_unknown_does_not_guess_metric() -> None:
    signature = (
        extract_question_semantic_signature_v2(
            "看看最近业务表现怎么样"
        )
    )

    assert_equal(
        signature.operator,
        None,
        "未知问题不应猜 operator。",
    )
    assert_equal(
        signature.left_operand,
        None,
        "未知问题不应猜 operand。",
    )
    assert_equal(
        signature.right_operand,
        None,
        "未知问题不应猜 denominator。",
    )

    assert_true(
        "metric_name"
        not in signature.model_dump(),
        "Question Signature Contract 不得输出 Metric ID。",
    )


def test_new_ratio_using_existing_atoms_needs_no_metric_specific_rule() -> None:
    signature = (
        extract_question_semantic_signature_v2(
            "把商品实付金额平均到每个售出的商品单位"
        )
    )

    assert_equal(
        (
            signature.operator,
            signature.left_operand,
            signature.right_operand,
        ),
        (
            QuestionOperator.DIVIDE,
            SemanticOperand.PAID_AMOUNT,
            SemanticOperand.PAID_UNITS,
        ),
        (
            "使用现有 amount/units atoms 的新 ratio "
            "应能被结构解析，不需要新增 Metric 名规则。"
        ),
    )


def run_tests() -> None:
    tests = [
        test_spending_per_buyer_structure_without_metric_rule,
        test_ipt_structure,
        test_gross_margin_rate_structure,
        test_channel_acquisition_structure,
        test_repeat_and_multi_order_are_structurally_distinct,
        test_member_snapshot_structure,
        test_refund_cohort_structure,
        test_partial_unknown_does_not_guess_metric,
        test_new_ratio_using_existing_atoms_needs_no_metric_specific_rule,
    ]

    passed = 0
    failed = 0

    for test in tests:
        print("=" * 80)
        print(
            f"Running: {test.__name__}"
        )

        try:
            test()
            passed += 1
            print("[PASS]")
        except Exception as exc:
            failed += 1
            print("[FAIL]")
            print(exc)

    print("=" * 80)
    print(
        "Question Semantic Signature V2 Test Summary"
    )
    print(
        f"Total: {len(tests)}"
    )
    print(
        f"Passed: {passed}"
    )
    print(
        f"Failed: {failed}"
    )

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    run_tests()
