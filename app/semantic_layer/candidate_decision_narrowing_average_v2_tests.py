from __future__ import annotations

from app.semantic_layer.candidate_decision_narrowing_v2 import (
    narrow_clarification_candidates_v2,
)
from app.semantic_layer.candidate_decision_v2 import (
    CandidateDecisionStatusV2,
    CandidateDecisionV2,
)


def _assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(
            f"{message}\nExpected: {expected}\nActual: {actual}"
        )


def test_generic_average_consumption_narrows_to_two_money_average_metrics() -> None:
    structural_decision = CandidateDecisionV2(
        status=CandidateDecisionStatusV2.NEEDS_CLARIFICATION,
        metric_name=None,
        candidates=(
            "aus",
            "cac",
            "gross_margin_rate",
            "ipt",
            "member_gmv_share",
            "purchase_frequency",
            "refund_rate",
            "repeat_customer_rate",
            "roi",
            "spending_per_buyer",
        ),
    )

    narrowed = narrow_clarification_candidates_v2(
        question="平均消费大概是多少？",
        decision=structural_decision,
    )

    _assert_equal(
        narrowed.status,
        CandidateDecisionStatusV2.NEEDS_CLARIFICATION,
        "普通“平均消费”仍然必须澄清，不能自动 MATCHED。",
    )

    _assert_equal(
        narrowed.candidates,
        (
            "spending_per_buyer",
            "aus",
        ),
        "普通“平均消费”只应保留按买家与按订单两种金额平均口径。",
    )


def test_average_without_consumption_word_is_not_narrowed() -> None:
    structural_decision = CandidateDecisionV2(
        status=CandidateDecisionStatusV2.NEEDS_CLARIFICATION,
        metric_name=None,
        candidates=(
            "aus",
            "ipt",
            "spending_per_buyer",
        ),
    )

    narrowed = narrow_clarification_candidates_v2(
        question="平均是多少？",
        decision=structural_decision,
    )

    _assert_equal(
        narrowed,
        structural_decision,
        "只有“平均”而没有消费/金额语义时不能随意缩小候选。",
    )


def test_existing_generic_new_customer_rule_still_works() -> None:
    structural_decision = CandidateDecisionV2(
        status=CandidateDecisionStatusV2.NEEDS_CLARIFICATION,
        metric_name=None,
        candidates=(
            "brand_paid_new_customer_count",
            "buyer_count",
            "channel_paid_new_customer_count",
            "order_count",
        ),
    )

    narrowed = narrow_clarification_candidates_v2(
        question="本期新客有多少？",
        decision=structural_decision,
    )

    _assert_equal(
        narrowed.candidates,
        (
            "brand_paid_new_customer_count",
            "channel_paid_new_customer_count",
        ),
        "新增 average 规则不能破坏已有的新客 narrowing。",
    )


_TESTS = (
    test_generic_average_consumption_narrows_to_two_money_average_metrics,
    test_average_without_consumption_word_is_not_narrowed,
    test_existing_generic_new_customer_rule_still_works,
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
    print("Candidate Decision V2 Gate 3G Average Narrowing Test Summary")
    print(f"Total: {len(_TESTS)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    run_tests()
