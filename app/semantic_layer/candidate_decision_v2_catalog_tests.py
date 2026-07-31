from __future__ import annotations

from app.semantic_layer.candidate_decision_v2 import (
    CandidateDecisionStatusV2,
    decide_metric_candidate_v2,
)
from app.semantic_layer.metric_signature_v2 import (
    SemanticOperand,
    SemanticQualifier,
)
from app.semantic_layer.question_signature_v2 import (
    QuestionOperator,
    QuestionSemanticSignatureV2,
)


def _assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(
            f"{message}\nExpected: {expected}\nActual: {actual}"
        )


def _assert_true(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def test_real_catalog_gmv_is_uniquely_matched() -> None:
    decision = decide_metric_candidate_v2(
        question_signature=QuestionSemanticSignatureV2(
            operator=QuestionOperator.SUM,
            left_operand=SemanticOperand.PAID_AMOUNT,
        )
    )

    _assert_equal(
        decision.status,
        CandidateDecisionStatusV2.MATCHED,
        "GMV 结构在真实 Catalog 中应唯一命中。",
    )
    _assert_equal(
        decision.metric_name,
        "gmv",
        "SUM(paid_amount) 应命中 gmv。",
    )


def test_real_catalog_ipt_is_uniquely_matched() -> None:
    decision = decide_metric_candidate_v2(
        question_signature=QuestionSemanticSignatureV2(
            operator=QuestionOperator.DIVIDE,
            left_operand=SemanticOperand.PAID_UNITS,
            right_operand=SemanticOperand.PAID_ORDER,
        )
    )

    _assert_equal(
        decision.status,
        CandidateDecisionStatusV2.MATCHED,
        "IPT 结构在真实 Catalog 中应唯一命中。",
    )
    _assert_equal(
        decision.metric_name,
        "ipt",
        "paid_units / paid_order 应命中 ipt。",
    )


def test_real_catalog_roi_is_uniquely_matched() -> None:
    decision = decide_metric_candidate_v2(
        question_signature=QuestionSemanticSignatureV2(
            operator=QuestionOperator.DIVIDE,
            left_operand=SemanticOperand.PAID_AMOUNT,
            right_operand=SemanticOperand.MARKETING_SPEND,
            qualifiers=(
                SemanticQualifier.SAME_WINDOW_SALES_SPEND,
            ),
        )
    )

    _assert_equal(
        decision.status,
        CandidateDecisionStatusV2.MATCHED,
        "ROI 结构在真实 Catalog 中应唯一命中。",
    )
    _assert_equal(
        decision.metric_name,
        "roi",
        "paid_amount / marketing_spend 应命中 roi。",
    )


def test_real_catalog_cac_is_uniquely_matched() -> None:
    decision = decide_metric_candidate_v2(
        question_signature=QuestionSemanticSignatureV2(
            operator=QuestionOperator.DIVIDE,
            left_operand=SemanticOperand.MARKETING_SPEND,
            right_operand=SemanticOperand.CHANNEL_FIRST_PAID_CUSTOMER,
        )
    )

    _assert_equal(
        decision.status,
        CandidateDecisionStatusV2.MATCHED,
        "CAC 结构在真实 Catalog 中应唯一命中。",
    )
    _assert_equal(
        decision.metric_name,
        "cac",
        "marketing_spend / channel_first_paid_customer 应命中 cac。",
    )


def test_generic_average_needs_clarification() -> None:
    decision = decide_metric_candidate_v2(
        question_signature=QuestionSemanticSignatureV2(
            operator=QuestionOperator.DIVIDE,
            left_operand=None,
            right_operand=None,
        )
    )

    _assert_equal(
        decision.status,
        CandidateDecisionStatusV2.NEEDS_CLARIFICATION,
        "只有 divide 而没有 operands 时必须澄清，不能猜指标。",
    )
    _assert_true(
        len(decision.candidates) > 1,
        "Generic average 应保留多个结构兼容候选。",
    )


def test_unsupported_ratio_is_unsupported() -> None:
    decision = decide_metric_candidate_v2(
        question_signature=QuestionSemanticSignatureV2(
            operator=QuestionOperator.DIVIDE,
            left_operand=SemanticOperand.PAID_AMOUNT,
            right_operand=SemanticOperand.PAID_UNITS,
        )
    )

    _assert_equal(
        decision.status,
        CandidateDecisionStatusV2.UNSUPPORTED,
        "Catalog 中不存在 paid_amount / paid_units 指标时应 unsupported。",
    )


def test_authorization_can_remove_otherwise_valid_metric() -> None:
    decision = decide_metric_candidate_v2(
        question_signature=QuestionSemanticSignatureV2(
            operator=QuestionOperator.SUM,
            left_operand=SemanticOperand.PAID_AMOUNT,
        ),
        allowed_metric_names={
            "buyer_count",
            "order_count",
        },
    )

    _assert_equal(
        decision.status,
        CandidateDecisionStatusV2.UNSUPPORTED,
        "gmv 未授权时不得返回 gmv，也不得泄露为候选。",
    )
    _assert_true(
        "gmv" not in decision.candidates,
        "未授权 gmv 不得出现在 candidates。",
    )


_TESTS = (
    test_real_catalog_gmv_is_uniquely_matched,
    test_real_catalog_ipt_is_uniquely_matched,
    test_real_catalog_roi_is_uniquely_matched,
    test_real_catalog_cac_is_uniquely_matched,
    test_generic_average_needs_clarification,
    test_unsupported_ratio_is_unsupported,
    test_authorization_can_remove_otherwise_valid_metric,
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
    print("Candidate Decision V2 Gate 3C Catalog Test Summary")
    print(f"Total: {len(_TESTS)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    run_tests()
