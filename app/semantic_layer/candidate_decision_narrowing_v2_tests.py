from __future__ import annotations

from app.semantic_layer.candidate_decision_narrowing_v2 import (
    narrow_clarification_candidates_v2,
)
from app.semantic_layer.candidate_decision_v2 import (
    CandidateDecisionStatusV2,
    CandidateDecisionV2,
)


def _assert_equal(
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


def test_generic_new_customer_narrows_to_brand_and_channel() -> None:
    structural_decision = CandidateDecisionV2(
        status=(
            CandidateDecisionStatusV2.NEEDS_CLARIFICATION
        ),
        metric_name=None,
        candidates=(
            "brand_paid_new_customer_count",
            "buyer_count",
            "channel_paid_new_customer_count",
            "multi_order_customer_count",
            "order_count",
            "repeat_customer_count",
        ),
    )

    narrowed = narrow_clarification_candidates_v2(
        question="本期新客有多少？",
        decision=structural_decision,
    )

    _assert_equal(
        narrowed.status,
        CandidateDecisionStatusV2.NEEDS_CLARIFICATION,
        "未限定品牌/渠道的新客问题仍应需要澄清。",
    )

    _assert_equal(
        narrowed.candidates,
        (
            "brand_paid_new_customer_count",
            "channel_paid_new_customer_count",
        ),
        "“新客”只应保留品牌新客与渠道新客两个澄清候选。",
    )


def test_matched_decision_is_not_changed_by_narrowing() -> None:
    decision = CandidateDecisionV2(
        status=CandidateDecisionStatusV2.MATCHED,
        metric_name="gmv",
        candidates=(
            "gmv",
        ),
    )

    narrowed = narrow_clarification_candidates_v2(
        question="成交金额汇总",
        decision=decision,
    )

    _assert_equal(
        narrowed,
        decision,
        "MATCHED 结果不应被 clarification narrowing 修改。",
    )


def test_unrecognized_clarification_is_not_arbitrarily_reduced() -> None:
    decision = CandidateDecisionV2(
        status=(
            CandidateDecisionStatusV2.NEEDS_CLARIFICATION
        ),
        metric_name=None,
        candidates=(
            "aus",
            "ipt",
            "spending_per_buyer",
        ),
    )

    narrowed = narrow_clarification_candidates_v2(
        question="这个指标大概是多少？",
        decision=decision,
    )

    _assert_equal(
        narrowed,
        decision,
        "没有命中已定义 narrowing family 的问题不得随意删候选。",
    )


_TESTS = (
    test_generic_new_customer_narrows_to_brand_and_channel,
    test_matched_decision_is_not_changed_by_narrowing,
    test_unrecognized_clarification_is_not_arbitrarily_reduced,
)


def run_tests() -> None:
    passed = 0
    failed = 0

    for test in _TESTS:
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
        "Candidate Decision V2 Gate 3F Narrowing Test Summary"
    )
    print(
        f"Total: {len(_TESTS)}"
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
