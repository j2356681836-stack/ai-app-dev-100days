from __future__ import annotations

from app.semantic_layer.candidate_decision_ranking_v2 import (
    apply_embedding_ranking_v2,
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
            f"{message}\nExpected: {expected}\nActual: {actual}"
        )


def _assert_true(
    value: bool,
    message: str,
) -> None:
    if not value:
        raise AssertionError(
            message
        )


def test_clarification_candidates_can_be_reordered() -> None:
    def fake_ranker(
        question,
        *,
        allowed_metric_names,
        top_k,
    ):
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

    decision = CandidateDecisionV2(
        status=CandidateDecisionStatusV2.NEEDS_CLARIFICATION,
        metric_name=None,
        candidates=(
            "spending_per_buyer",
            "aus",
        ),
    )

    ranked = apply_embedding_ranking_v2(
        question="平均消费大概是多少？",
        decision=decision,
        ranker=fake_ranker,
    )

    _assert_equal(
        ranked.candidates,
        (
            "aus",
            "spending_per_buyer",
        ),
        "Embedding 应允许重排已有 clarification candidates。",
    )


def test_embedding_cannot_turn_clarification_into_matched() -> None:
    def fake_ranker(
        question,
        *,
        allowed_metric_names,
        top_k,
    ):
        return {
            "method": "embedding_v2",
            "candidates": [
                {
                    "name": "aus",
                    "score": 0.99,
                },
            ],
        }

    decision = CandidateDecisionV2(
        status=CandidateDecisionStatusV2.NEEDS_CLARIFICATION,
        metric_name=None,
        candidates=(
            "aus",
            "spending_per_buyer",
        ),
    )

    ranked = apply_embedding_ranking_v2(
        question="平均消费大概是多少？",
        decision=decision,
        ranker=fake_ranker,
    )

    _assert_equal(
        ranked.status,
        CandidateDecisionStatusV2.NEEDS_CLARIFICATION,
        "Embedding top1 再高也不能把 clarification 改成 matched。",
    )

    _assert_equal(
        ranked.metric_name,
        None,
        "Clarification 状态不得产生 metric_name。",
    )


def test_matched_does_not_call_embedding() -> None:
    called = False

    def fake_ranker(
        question,
        *,
        allowed_metric_names,
        top_k,
    ):
        nonlocal called
        called = True
        raise AssertionError(
            "MATCHED 不应调用 embedding。"
        )

    decision = CandidateDecisionV2(
        status=CandidateDecisionStatusV2.MATCHED,
        metric_name="gmv",
        candidates=(
            "gmv",
        ),
    )

    ranked = apply_embedding_ranking_v2(
        question="成交金额汇总",
        decision=decision,
        ranker=fake_ranker,
    )

    _assert_true(
        not called,
        "MATCHED 不应调用 embedding。",
    )

    _assert_equal(
        ranked.metric_name,
        "gmv",
        "MATCHED 结果必须保持原 metric。",
    )


def test_unsupported_does_not_call_embedding() -> None:
    called = False

    def fake_ranker(
        question,
        *,
        allowed_metric_names,
        top_k,
    ):
        nonlocal called
        called = True
        raise AssertionError(
            "UNSUPPORTED 不应调用 embedding。"
        )

    decision = CandidateDecisionV2(
        status=CandidateDecisionStatusV2.UNSUPPORTED,
        metric_name=None,
        candidates=(),
    )

    ranked = apply_embedding_ranking_v2(
        question="当前不支持的指标结构",
        decision=decision,
        ranker=fake_ranker,
    )

    _assert_true(
        not called,
        "UNSUPPORTED 不应调用 embedding。",
    )

    _assert_equal(
        ranked.status,
        CandidateDecisionStatusV2.UNSUPPORTED,
        "UNSUPPORTED 状态必须保持。",
    )


def test_embedding_cannot_inject_out_of_pool_candidate() -> None:
    def fake_ranker(
        question,
        *,
        allowed_metric_names,
        top_k,
    ):
        return {
            "method": "embedding_v2",
            "candidates": [
                {
                    "name": "forbidden_metric",
                    "score": 1.0,
                },
                {
                    "name": "aus",
                    "score": 0.9,
                },
            ],
        }

    decision = CandidateDecisionV2(
        status=CandidateDecisionStatusV2.NEEDS_CLARIFICATION,
        metric_name=None,
        candidates=(
            "aus",
            "spending_per_buyer",
        ),
    )

    ranked = apply_embedding_ranking_v2(
        question="平均消费大概是多少？",
        decision=decision,
        ranker=fake_ranker,
    )

    _assert_true(
        "forbidden_metric"
        not in ranked.candidates,
        "Embedding 不得注入结构候选池之外的 Metric。",
    )

    _assert_equal(
        set(
            ranked.candidates
        ),
        {
            "aus",
            "spending_per_buyer",
        },
        "排序后候选集合必须与原 structural pool 相同。",
    )


def test_missing_embedding_result_keeps_remaining_candidates() -> None:
    def fake_ranker(
        question,
        *,
        allowed_metric_names,
        top_k,
    ):
        return {
            "method": "embedding_v2",
            "candidates": [
                {
                    "name": "aus",
                    "score": 0.9,
                },
            ],
        }

    decision = CandidateDecisionV2(
        status=CandidateDecisionStatusV2.NEEDS_CLARIFICATION,
        metric_name=None,
        candidates=(
            "spending_per_buyer",
            "aus",
            "ipt",
        ),
    )

    ranked = apply_embedding_ranking_v2(
        question="平均消费大概是多少？",
        decision=decision,
        ranker=fake_ranker,
    )

    _assert_equal(
        ranked.candidates,
        (
            "aus",
            "spending_per_buyer",
            "ipt",
        ),
        "Embedding 未返回的合法候选必须保留。",
    )


_TESTS = (
    test_clarification_candidates_can_be_reordered,
    test_embedding_cannot_turn_clarification_into_matched,
    test_matched_does_not_call_embedding,
    test_unsupported_does_not_call_embedding,
    test_embedding_cannot_inject_out_of_pool_candidate,
    test_missing_embedding_result_keeps_remaining_candidates,
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
        "Candidate Decision V2 Gate 3D Ranking Test Summary"
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
