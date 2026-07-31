from __future__ import annotations

from app.semantic_layer.candidate_decision_v2 import (
    CandidateDecisionStatusV2,
    decide_metric_candidate_from_signatures_v2,
    evaluate_metric_compatibility_v2,
)
from app.semantic_layer.metric_signature_v2 import (
    IntrinsicPartition,
    MetricSemanticSignatureV2,
    SemanticOperand,
    SemanticQualifier,
    SignatureOperator,
)
from app.semantic_layer.question_signature_v2 import (
    QuestionOperator,
    QuestionSemanticSignatureV2,
)


def _assert_true(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def _metric(
    *,
    name: str = "test_metric",
    operator: SignatureOperator,
    left: SemanticOperand,
    right: SemanticOperand | None = None,
    partition: IntrinsicPartition = IntrinsicPartition.NONE,
    qualifiers: tuple[SemanticQualifier, ...] = (),
) -> MetricSemanticSignatureV2:
    return MetricSemanticSignatureV2(
        metric_name=name,
        operator=operator,
        left_operand=left,
        right_operand=right,
        intrinsic_partition=partition,
        qualifiers=qualifiers,
    )


def test_sum_matches_sum() -> None:
    result = evaluate_metric_compatibility_v2(
        question_signature=QuestionSemanticSignatureV2(
            operator=QuestionOperator.SUM,
            left_operand=SemanticOperand.PAID_AMOUNT,
        ),
        metric_signature=_metric(
            operator=SignatureOperator.SUM,
            left=SemanticOperand.PAID_AMOUNT,
        ),
    )
    _assert_true(result.compatible, "SUM 应兼容 SUM。")


def test_sum_conflicts_with_divide() -> None:
    result = evaluate_metric_compatibility_v2(
        question_signature=QuestionSemanticSignatureV2(
            operator=QuestionOperator.SUM,
            left_operand=SemanticOperand.PAID_AMOUNT,
        ),
        metric_signature=_metric(
            operator=SignatureOperator.DIVIDE,
            left=SemanticOperand.PAID_AMOUNT,
            right=SemanticOperand.PAID_BUYER,
        ),
    )
    _assert_true(not result.compatible, "SUM 不应兼容 DIVIDE。")


def test_count_matches_distinct_count() -> None:
    result = evaluate_metric_compatibility_v2(
        question_signature=QuestionSemanticSignatureV2(
            operator=QuestionOperator.COUNT,
            left_operand=SemanticOperand.PAID_BUYER,
        ),
        metric_signature=_metric(
            operator=SignatureOperator.DISTINCT_COUNT,
            left=SemanticOperand.PAID_BUYER,
        ),
    )
    _assert_true(result.compatible, "COUNT 应兼容 DISTINCT_COUNT。")


def test_count_matches_qualified_count() -> None:
    result = evaluate_metric_compatibility_v2(
        question_signature=QuestionSemanticSignatureV2(
            operator=QuestionOperator.COUNT,
            left_operand=SemanticOperand.MULTI_PAID_ORDER_CUSTOMER,
        ),
        metric_signature=_metric(
            operator=SignatureOperator.QUALIFIED_COUNT,
            left=SemanticOperand.MULTI_PAID_ORDER_CUSTOMER,
        ),
    )
    _assert_true(result.compatible, "COUNT 应兼容 QUALIFIED_COUNT。")


def test_count_conflicts_with_sum() -> None:
    result = evaluate_metric_compatibility_v2(
        question_signature=QuestionSemanticSignatureV2(
            operator=QuestionOperator.COUNT,
            left_operand=SemanticOperand.PAID_BUYER,
        ),
        metric_signature=_metric(
            operator=SignatureOperator.SUM,
            left=SemanticOperand.PAID_AMOUNT,
        ),
    )
    _assert_true(not result.compatible, "COUNT 不应兼容 SUM。")


def test_known_left_operand_mismatch_conflicts() -> None:
    result = evaluate_metric_compatibility_v2(
        question_signature=QuestionSemanticSignatureV2(
            operator=QuestionOperator.SUM,
            left_operand=SemanticOperand.PAID_AMOUNT,
        ),
        metric_signature=_metric(
            operator=SignatureOperator.SUM,
            left=SemanticOperand.PAID_UNITS,
        ),
    )
    _assert_true(
        "left_operand" in result.conflicting_fields,
        "left_operand 不一致时必须冲突。",
    )


def test_null_left_operand_is_unresolved_not_conflict() -> None:
    result = evaluate_metric_compatibility_v2(
        question_signature=QuestionSemanticSignatureV2(
            operator=QuestionOperator.DIVIDE,
            left_operand=None,
            right_operand=None,
        ),
        metric_signature=_metric(
            operator=SignatureOperator.DIVIDE,
            left=SemanticOperand.PAID_AMOUNT,
            right=SemanticOperand.PAID_BUYER,
        ),
    )
    _assert_true(result.compatible, "未知 left_operand 不应冲突。")
    _assert_true(
        "left_operand" in result.unresolved_fields,
        "未知 left_operand 应记录 unresolved。",
    )


def test_known_right_operand_mismatch_conflicts() -> None:
    result = evaluate_metric_compatibility_v2(
        question_signature=QuestionSemanticSignatureV2(
            operator=QuestionOperator.DIVIDE,
            left_operand=SemanticOperand.PAID_AMOUNT,
            right_operand=SemanticOperand.PAID_BUYER,
        ),
        metric_signature=_metric(
            operator=SignatureOperator.DIVIDE,
            left=SemanticOperand.PAID_AMOUNT,
            right=SemanticOperand.PAID_ORDER,
        ),
    )
    _assert_true(
        "right_operand" in result.conflicting_fields,
        "right_operand 不一致时必须冲突。",
    )


def test_null_right_operand_is_unresolved_not_conflict() -> None:
    result = evaluate_metric_compatibility_v2(
        question_signature=QuestionSemanticSignatureV2(
            operator=QuestionOperator.DIVIDE,
            left_operand=SemanticOperand.PAID_AMOUNT,
            right_operand=None,
        ),
        metric_signature=_metric(
            operator=SignatureOperator.DIVIDE,
            left=SemanticOperand.PAID_AMOUNT,
            right=SemanticOperand.PAID_BUYER,
        ),
    )
    _assert_true(result.compatible, "未知 right_operand 不应冲突。")
    _assert_true(
        "right_operand" in result.unresolved_fields,
        "未知 right_operand 应记录 unresolved。",
    )


def test_question_qualifiers_must_be_metric_subset() -> None:
    matching = evaluate_metric_compatibility_v2(
        question_signature=QuestionSemanticSignatureV2(
            operator=QuestionOperator.SUM,
            left_operand=SemanticOperand.GROSS_MARGIN_AMOUNT,
            qualifiers=(SemanticQualifier.PRODUCT_COST_BASIS,),
        ),
        metric_signature=_metric(
            operator=SignatureOperator.SUM,
            left=SemanticOperand.GROSS_MARGIN_AMOUNT,
            qualifiers=(SemanticQualifier.PRODUCT_COST_BASIS,),
        ),
    )
    _assert_true(matching.compatible, "Qualifier 被满足时应兼容。")

    missing = evaluate_metric_compatibility_v2(
        question_signature=QuestionSemanticSignatureV2(
            operator=QuestionOperator.SUM,
            left_operand=SemanticOperand.GROSS_MARGIN_AMOUNT,
            qualifiers=(SemanticQualifier.PRODUCT_COST_BASIS,),
        ),
        metric_signature=_metric(
            operator=SignatureOperator.SUM,
            left=SemanticOperand.GROSS_MARGIN_AMOUNT,
        ),
    )
    _assert_true(
        not missing.compatible,
        "Metric 缺少 Question qualifier 时必须冲突。",
    )


def test_question_channel_partition_does_not_exclude_non_intrinsic_metric() -> None:
    result = evaluate_metric_compatibility_v2(
        question_signature=QuestionSemanticSignatureV2(
            operator=QuestionOperator.SUM,
            left_operand=SemanticOperand.PAID_AMOUNT,
            intrinsic_partition=IntrinsicPartition.CHANNEL,
        ),
        metric_signature=_metric(
            operator=SignatureOperator.SUM,
            left=SemanticOperand.PAID_AMOUNT,
            partition=IntrinsicPartition.NONE,
        ),
    )
    _assert_true(result.compatible, "Question channel 不应硬排除 Metric。")
    _assert_true(
        "intrinsic_partition" not in result.conflicting_fields,
        "partition 暂不作为 hard conflict。",
    )


def test_metric_channel_partition_accepts_unknown_question_partition() -> None:
    result = evaluate_metric_compatibility_v2(
        question_signature=QuestionSemanticSignatureV2(
            operator=QuestionOperator.DIVIDE,
            left_operand=SemanticOperand.PAID_AMOUNT,
            right_operand=SemanticOperand.MARKETING_SPEND,
            intrinsic_partition=None,
        ),
        metric_signature=_metric(
            operator=SignatureOperator.DIVIDE,
            left=SemanticOperand.PAID_AMOUNT,
            right=SemanticOperand.MARKETING_SPEND,
            partition=IntrinsicPartition.CHANNEL,
        ),
    )
    _assert_true(result.compatible, "未知 partition 不应排除 channel Metric。")



def test_zero_compatible_candidates_is_unsupported() -> None:
    decision = decide_metric_candidate_from_signatures_v2(
        question_signature=QuestionSemanticSignatureV2(
            operator=QuestionOperator.SUM,
            left_operand=SemanticOperand.PAID_AMOUNT,
        ),
        metric_signatures=(
            _metric(
                name="ratio_metric",
                operator=SignatureOperator.DIVIDE,
                left=SemanticOperand.PAID_AMOUNT,
                right=SemanticOperand.PAID_BUYER,
            ),
        ),
    )

    _assert_true(
        decision.status == CandidateDecisionStatusV2.UNSUPPORTED,
        "0 个兼容 Metric 应返回 unsupported。",
    )


def test_one_compatible_candidate_is_matched() -> None:
    decision = decide_metric_candidate_from_signatures_v2(
        question_signature=QuestionSemanticSignatureV2(
            operator=QuestionOperator.SUM,
            left_operand=SemanticOperand.PAID_AMOUNT,
        ),
        metric_signatures=(
            _metric(
                name="gmv_like",
                operator=SignatureOperator.SUM,
                left=SemanticOperand.PAID_AMOUNT,
            ),
            _metric(
                name="units_like",
                operator=SignatureOperator.SUM,
                left=SemanticOperand.PAID_UNITS,
            ),
        ),
    )

    _assert_true(
        decision.status == CandidateDecisionStatusV2.MATCHED,
        "1 个兼容 Metric 应返回 matched。",
    )
    _assert_true(
        decision.metric_name == "gmv_like",
        "唯一兼容 Metric 应成为 metric_name。",
    )


def test_multiple_compatible_candidates_need_clarification() -> None:
    decision = decide_metric_candidate_from_signatures_v2(
        question_signature=QuestionSemanticSignatureV2(
            operator=QuestionOperator.DIVIDE,
            left_operand=None,
            right_operand=None,
        ),
        metric_signatures=(
            _metric(
                name="spending_per_buyer_like",
                operator=SignatureOperator.DIVIDE,
                left=SemanticOperand.PAID_AMOUNT,
                right=SemanticOperand.PAID_BUYER,
            ),
            _metric(
                name="aus_like",
                operator=SignatureOperator.DIVIDE,
                left=SemanticOperand.PAID_AMOUNT,
                right=SemanticOperand.PAID_ORDER,
            ),
        ),
    )

    _assert_true(
        decision.status == CandidateDecisionStatusV2.NEEDS_CLARIFICATION,
        "多个兼容 Metric 应返回 needs_clarification。",
    )
    _assert_true(
        decision.candidates == (
            "aus_like",
            "spending_per_buyer_like",
        ),
        "候选应稳定排序。",
    )


def test_authorization_filter_happens_before_decision() -> None:
    decision = decide_metric_candidate_from_signatures_v2(
        question_signature=QuestionSemanticSignatureV2(
            operator=QuestionOperator.DIVIDE,
            left_operand=None,
            right_operand=None,
        ),
        metric_signatures=(
            _metric(
                name="allowed_metric",
                operator=SignatureOperator.DIVIDE,
                left=SemanticOperand.PAID_AMOUNT,
                right=SemanticOperand.PAID_BUYER,
            ),
            _metric(
                name="forbidden_metric",
                operator=SignatureOperator.DIVIDE,
                left=SemanticOperand.PAID_AMOUNT,
                right=SemanticOperand.PAID_ORDER,
            ),
        ),
        allowed_metric_names={"allowed_metric"},
    )

    _assert_true(
        decision.status == CandidateDecisionStatusV2.MATCHED,
        "授权过滤后只剩 1 个兼容 Metric，应 matched。",
    )
    _assert_true(
        decision.metric_name == "allowed_metric",
        "未授权 Metric 不得参与最终 decision。",
    )
    _assert_true(
        "forbidden_metric" not in decision.candidates,
        "未授权 Metric 不得出现在候选中。",
    )


def test_no_authorized_candidates_is_unsupported() -> None:
    decision = decide_metric_candidate_from_signatures_v2(
        question_signature=QuestionSemanticSignatureV2(
            operator=QuestionOperator.SUM,
            left_operand=SemanticOperand.PAID_AMOUNT,
        ),
        metric_signatures=(
            _metric(
                name="gmv_like",
                operator=SignatureOperator.SUM,
                left=SemanticOperand.PAID_AMOUNT,
            ),
        ),
        allowed_metric_names=set(),
    )

    _assert_true(
        decision.status == CandidateDecisionStatusV2.UNSUPPORTED,
        "没有授权候选时必须 fail closed。",
    )


def test_partial_structure_does_not_guess_top1() -> None:
    decision = decide_metric_candidate_from_signatures_v2(
        question_signature=QuestionSemanticSignatureV2(
            operator=QuestionOperator.DIVIDE,
            left_operand=SemanticOperand.PAID_AMOUNT,
            right_operand=None,
        ),
        metric_signatures=(
            _metric(
                name="per_buyer_like",
                operator=SignatureOperator.DIVIDE,
                left=SemanticOperand.PAID_AMOUNT,
                right=SemanticOperand.PAID_BUYER,
            ),
            _metric(
                name="per_order_like",
                operator=SignatureOperator.DIVIDE,
                left=SemanticOperand.PAID_AMOUNT,
                right=SemanticOperand.PAID_ORDER,
            ),
        ),
    )

    _assert_true(
        decision.status == CandidateDecisionStatusV2.NEEDS_CLARIFICATION,
        "结构不足时不能自行猜 top1。",
    )

_TESTS = (
    test_sum_matches_sum,
    test_sum_conflicts_with_divide,
    test_count_matches_distinct_count,
    test_count_matches_qualified_count,
    test_count_conflicts_with_sum,
    test_known_left_operand_mismatch_conflicts,
    test_null_left_operand_is_unresolved_not_conflict,
    test_known_right_operand_mismatch_conflicts,
    test_null_right_operand_is_unresolved_not_conflict,
    test_question_qualifiers_must_be_metric_subset,
    test_question_channel_partition_does_not_exclude_non_intrinsic_metric,
    test_metric_channel_partition_accepts_unknown_question_partition,
    test_zero_compatible_candidates_is_unsupported,
    test_one_compatible_candidate_is_matched,
    test_multiple_compatible_candidates_need_clarification,
    test_authorization_filter_happens_before_decision,
    test_no_authorized_candidates_is_unsupported,
    test_partial_structure_does_not_guess_top1,
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
    print("Candidate Decision V2 Gate 3B Test Summary")
    print(f"Total: {len(_TESTS)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    run_tests()
