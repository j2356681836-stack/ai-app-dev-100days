from __future__ import annotations

from app.semantic_layer.candidate_decision_pipeline_v2 import (
    resolve_candidate_decision_v2,
)
from app.semantic_layer.candidate_decision_v2 import (
    CandidateDecisionStatusV2,
)
from app.semantic_layer.metric_signature_v2 import (
    SemanticOperand,
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


def _fail_if_called(
    question,
    *,
    allowed_metric_names,
    top_k,
):
    raise AssertionError(
        "该路径不应调用 Embedding ranker。"
    )


def test_matched_gmv_uses_unified_pipeline_without_embedding() -> None:
    result = resolve_candidate_decision_v2(
        question="把完成支付的商品金额累计起来",
        question_signature=QuestionSemanticSignatureV2(
            operator=QuestionOperator.SUM,
            left_operand=SemanticOperand.PAID_AMOUNT,
        ),
        ranker=_fail_if_called,
    )

    _assert_equal(
        result.status,
        CandidateDecisionStatusV2.MATCHED,
        "GMV 应保持 MATCHED。",
    )
    _assert_equal(
        result.metric_name,
        "gmv",
        "GMV 结构应命中 gmv。",
    )
    _assert_true(
        not result.ranking_applied,
        "MATCHED 不应使用 Embedding。",
    )


def test_generic_new_customer_is_narrowed_before_ranking() -> None:
    seen_allowed = None

    def fake_ranker(
        question,
        *,
        allowed_metric_names,
        top_k,
    ):
        nonlocal seen_allowed
        seen_allowed = set(allowed_metric_names)

        return {
            "method": "embedding_v2",
            "candidates": [
                {
                    "name": "channel_paid_new_customer_count",
                    "score": 0.9,
                },
                {
                    "name": "brand_paid_new_customer_count",
                    "score": 0.8,
                },
            ],
        }

    result = resolve_candidate_decision_v2(
        question="本期新客有多少？",
        question_signature=QuestionSemanticSignatureV2(
            operator=QuestionOperator.COUNT,
            left_operand=None,
            right_operand=None,
        ),
        ranker=fake_ranker,
    )

    _assert_equal(
        result.status,
        CandidateDecisionStatusV2.NEEDS_CLARIFICATION,
        "Generic new customer 必须保持 clarification。",
    )

    _assert_equal(
        seen_allowed,
        {
            "brand_paid_new_customer_count",
            "channel_paid_new_customer_count",
        },
        "Embedding 应只看到 Narrowing 之后的两个新客候选。",
    )

    _assert_equal(
        result.candidates,
        (
            "channel_paid_new_customer_count",
            "brand_paid_new_customer_count",
        ),
        "Embedding 只允许重排这两个候选。",
    )


def test_generic_average_is_narrowed_before_ranking() -> None:
    seen_allowed = None

    def fake_ranker(
        question,
        *,
        allowed_metric_names,
        top_k,
    ):
        nonlocal seen_allowed
        seen_allowed = set(allowed_metric_names)

        return {
            "method": "embedding_v2",
            "candidates": [
                {
                    "name": "aus",
                    "score": 0.9,
                },
                {
                    "name": "spending_per_buyer",
                    "score": 0.8,
                },
            ],
        }

    result = resolve_candidate_decision_v2(
        question="平均消费大概是多少？",
        question_signature=QuestionSemanticSignatureV2(
            operator=QuestionOperator.DIVIDE,
            left_operand=None,
            right_operand=None,
        ),
        ranker=fake_ranker,
    )

    _assert_equal(
        result.status,
        CandidateDecisionStatusV2.NEEDS_CLARIFICATION,
        "Generic average 必须保持 clarification。",
    )

    _assert_equal(
        seen_allowed,
        {
            "spending_per_buyer",
            "aus",
        },
        "Embedding 应只看到 average narrowing 后的两个候选。",
    )


def test_authorization_happens_before_narrowing_and_ranking() -> None:
    result = resolve_candidate_decision_v2(
        question="本期新客有多少？",
        question_signature=QuestionSemanticSignatureV2(
            operator=QuestionOperator.COUNT,
            left_operand=None,
            right_operand=None,
        ),
        allowed_metric_names={
            "brand_paid_new_customer_count",
        },
        ranker=_fail_if_called,
    )

    _assert_equal(
        result.status,
        CandidateDecisionStatusV2.MATCHED,
        "授权过滤后只有一个结构候选时应直接 MATCHED。",
    )

    _assert_equal(
        result.metric_name,
        "brand_paid_new_customer_count",
        "未授权 channel metric 不得进入后续 Narrowing/Embedding。",
    )


def test_unsupported_path_does_not_call_embedding() -> None:
    result = resolve_candidate_decision_v2(
        question="成交金额平均到每件商品是多少？",
        question_signature=QuestionSemanticSignatureV2(
            operator=QuestionOperator.DIVIDE,
            left_operand=SemanticOperand.PAID_AMOUNT,
            right_operand=SemanticOperand.PAID_UNITS,
        ),
        ranker=_fail_if_called,
    )

    _assert_equal(
        result.status,
        CandidateDecisionStatusV2.UNSUPPORTED,
        "不存在的结构必须保持 UNSUPPORTED。",
    )

    _assert_true(
        not result.ranking_applied,
        "UNSUPPORTED 不应调用 Embedding。",
    )


_TESTS = (
    test_matched_gmv_uses_unified_pipeline_without_embedding,
    test_generic_new_customer_is_narrowed_before_ranking,
    test_generic_average_is_narrowed_before_ranking,
    test_authorization_happens_before_narrowing_and_ranking,
    test_unsupported_path_does_not_call_embedding,
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
    print("Candidate Decision V2 Gate 3H Pipeline Test Summary")
    print(f"Total: {len(_TESTS)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    run_tests()
