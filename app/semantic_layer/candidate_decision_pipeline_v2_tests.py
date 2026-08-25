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


def test_explicit_gmv_alias_recovers_partial_signature() -> None:
    """
    Day92 SEM-REL-GAP-001 回归：
    Live Parser 曾真实出现 operator=None + paid_amount。
    显式 GMV Alias 应把已有 structural candidates 收窄为 gmv。
    """
    result = resolve_candidate_decision_v2(
        question="2025年GMV是多少？",
        question_signature=QuestionSemanticSignatureV2(
            operator=None,
            left_operand=SemanticOperand.PAID_AMOUNT,
            right_operand=None,
        ),
        ranker=_fail_if_called,
    )

    _assert_equal(
        result.status,
        CandidateDecisionStatusV2.MATCHED,
        "显式 GMV 应在欠解析 Signature 下稳定 MATCHED。",
    )
    _assert_equal(
        result.metric_name,
        "gmv",
        "显式 GMV Alias 应收窄到 gmv。",
    )
    _assert_equal(
        result.candidates,
        ("gmv",),
        "Grounding 后只能保留 gmv。",
    )
    _assert_true(
        not result.ranking_applied,
        "确定性 Alias Grounding 成功后不应再调用 Embedding。",
    )


def test_explicit_roi_alias_recovers_partial_signature() -> None:
    result = resolve_candidate_decision_v2(
        question="2025年ROI是多少？",
        question_signature=QuestionSemanticSignatureV2(
            operator=None,
            left_operand=SemanticOperand.PAID_AMOUNT,
            right_operand=None,
        ),
        ranker=_fail_if_called,
    )

    _assert_equal(
        result.status,
        CandidateDecisionStatusV2.MATCHED,
        "显式 ROI 应在欠解析 Signature 下稳定 MATCHED。",
    )
    _assert_equal(
        result.metric_name,
        "roi",
        "显式 ROI Alias 应收窄到 roi。",
    )


def test_explicit_alias_does_not_override_structural_match() -> None:
    """
    Alias Grounding 只修 clarification，不覆盖已经明确的结构判断。
    """
    result = resolve_candidate_decision_v2(
        question="GMV除以订单量是多少？",
        question_signature=QuestionSemanticSignatureV2(
            operator=QuestionOperator.DIVIDE,
            left_operand=SemanticOperand.PAID_AMOUNT,
            right_operand=SemanticOperand.PAID_ORDER,
        ),
        ranker=_fail_if_called,
    )

    _assert_equal(
        result.status,
        CandidateDecisionStatusV2.MATCHED,
        "明确 ratio 结构应保持 MATCHED。",
    )
    _assert_equal(
        result.metric_name,
        "aus",
        "paid_amount / paid_order 应保持 AUS，不得被 GMV Alias 抢占。",
    )


def test_unauthorized_explicit_metric_is_not_invented() -> None:
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
                {"name": "aus", "score": 0.9},
                {"name": "roi", "score": 0.8},
                {"name": "spending_per_buyer", "score": 0.7},
            ],
        }

    result = resolve_candidate_decision_v2(
        question="2025年GMV是多少？",
        question_signature=QuestionSemanticSignatureV2(
            operator=None,
            left_operand=SemanticOperand.PAID_AMOUNT,
            right_operand=None,
        ),
        allowed_metric_names={
            "aus",
            "roi",
            "spending_per_buyer",
        },
        ranker=fake_ranker,
    )

    _assert_equal(
        result.status,
        CandidateDecisionStatusV2.NEEDS_CLARIFICATION,
        "未授权 gmv 不能由 Alias Grounding 重新注入。",
    )
    _assert_true(
        "gmv" not in result.candidates,
        "未授权 Metric 不得出现在最终候选中。",
    )
    _assert_equal(
        seen_allowed,
        {"aus", "roi", "spending_per_buyer"},
        "Embedding 只能看到授权后的 structural candidates。",
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
                {"name": "channel_paid_new_customer_count", "score": 0.9},
                {"name": "brand_paid_new_customer_count", "score": 0.8},
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
                {"name": "aus", "score": 0.9},
                {"name": "spending_per_buyer", "score": 0.8},
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
        {"spending_per_buyer", "aus"},
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
    test_explicit_gmv_alias_recovers_partial_signature,
    test_explicit_roi_alias_recovers_partial_signature,
    test_explicit_alias_does_not_override_structural_match,
    test_unauthorized_explicit_metric_is_not_invented,
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
