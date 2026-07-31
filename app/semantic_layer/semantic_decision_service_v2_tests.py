from __future__ import annotations

import json

from app.semantic_layer.semantic_decision_service_v2 import (
    SemanticDecisionStatusV2,
    resolve_semantic_decision_v2,
)
from app.semantic_layer.question_semantic_parser_v2 import (
    QuestionSemanticParseStatusV2,
)


def _assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(
            f"{message}\nExpected: {expected}\nActual: {actual}"
        )


def _assert_true(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def _json_llm(payload: dict):
    def fake_llm(*, messages, temperature):
        return json.dumps(
            payload,
            ensure_ascii=False,
        )

    return fake_llm


def _fail_ranker(
    question,
    *,
    allowed_metric_names,
    top_k,
):
    raise AssertionError(
        "该路径不应调用 Embedding ranker。"
    )


def test_parsed_gmv_reaches_matched() -> None:
    result = resolve_semantic_decision_v2(
        question="把完成支付的商品金额累计起来",
        llm_call=_json_llm(
            {
                "operator": "sum",
                "left_operand": "paid_amount",
                "right_operand": None,
                "intrinsic_partition": None,
                "qualifiers": [],
            }
        ),
        ranker=_fail_ranker,
    )

    _assert_equal(
        result.status,
        SemanticDecisionStatusV2.MATCHED,
        "PARSED GMV 应进入 Candidate Pipeline 并 MATCHED。",
    )
    _assert_equal(
        result.metric_name,
        "gmv",
        "GMV 应命中 gmv。",
    )


def test_generic_new_customer_reaches_clarification() -> None:
    def fake_ranker(
        question,
        *,
        allowed_metric_names,
        top_k,
    ):
        _assert_equal(
            set(allowed_metric_names),
            {
                "brand_paid_new_customer_count",
                "channel_paid_new_customer_count",
            },
            "新客必须先 narrowing 再进入 embedding。",
        )

        return {
            "method": "embedding_v2",
            "candidates": [
                {
                    "name": "brand_paid_new_customer_count",
                    "score": 0.9,
                },
                {
                    "name": "channel_paid_new_customer_count",
                    "score": 0.8,
                },
            ],
        }

    result = resolve_semantic_decision_v2(
        question="本期新客有多少？",
        llm_call=_json_llm(
            {
                "operator": "count",
                "left_operand": None,
                "right_operand": None,
                "intrinsic_partition": None,
                "qualifiers": [],
            }
        ),
        ranker=fake_ranker,
    )

    _assert_equal(
        result.status,
        SemanticDecisionStatusV2.NEEDS_CLARIFICATION,
        "Generic 新客必须保持 clarification。",
    )
    _assert_equal(
        set(result.candidates),
        {
            "brand_paid_new_customer_count",
            "channel_paid_new_customer_count",
        },
        "Generic 新客应只剩两个候选。",
    )


def test_multiple_intents_stops_before_llm_and_candidate_pipeline() -> None:
    called = False

    def fake_llm(*, messages, temperature):
        nonlocal called
        called = True
        raise AssertionError(
            "MULTIPLE_INTENTS guard 应在 LLM 前停止。"
        )

    result = resolve_semantic_decision_v2(
        question="同时看成交金额和订单数",
        llm_call=fake_llm,
        ranker=_fail_ranker,
    )

    _assert_equal(
        result.status,
        SemanticDecisionStatusV2.MULTIPLE_INTENTS,
        "多意图问题必须停在 MULTIPLE_INTENTS。",
    )
    _assert_equal(
        result.parser_status,
        QuestionSemanticParseStatusV2.MULTIPLE_INTENTS,
        "必须保留 Parser 原始状态。",
    )
    _assert_true(
        not called,
        "MULTIPLE_INTENTS 不应调用 LLM。",
    )


def test_parse_failed_stops_before_candidate_pipeline() -> None:
    def broken_llm(*, messages, temperature):
        raise RuntimeError(
            "synthetic_llm_failure"
        )

    result = resolve_semantic_decision_v2(
        question="成交金额是多少？",
        llm_call=broken_llm,
        ranker=_fail_ranker,
    )

    _assert_equal(
        result.status,
        SemanticDecisionStatusV2.PARSE_FAILED,
        "Parser 失败必须 fail closed。",
    )
    _assert_true(
        result.parser_error is not None,
        "PARSE_FAILED 应保留 parser error。",
    )


def test_evidence_conflict_stops_before_candidate_pipeline() -> None:
    result = resolve_semantic_decision_v2(
        question="成交金额累计起来",
        llm_call=_json_llm(
            {
                "operator": "divide",
                "left_operand": "paid_amount",
                "right_operand": "paid_buyer",
                "intrinsic_partition": None,
                "qualifiers": [],
            }
        ),
        ranker=_fail_ranker,
    )

    _assert_equal(
        result.status,
        SemanticDecisionStatusV2.EVIDENCE_CONFLICT,
        "确定性 SUM 与 LLM DIVIDE 冲突时必须停止。",
    )
    _assert_true(
        len(result.parser_conflicts) > 0,
        "EVIDENCE_CONFLICT 应保留冲突证据。",
    )


def test_authorization_is_preserved_in_unified_service() -> None:
    result = resolve_semantic_decision_v2(
        question="把完成支付的商品金额累计起来",
        allowed_metric_names={
            "buyer_count",
            "order_count",
        },
        llm_call=_json_llm(
            {
                "operator": "sum",
                "left_operand": "paid_amount",
                "right_operand": None,
                "intrinsic_partition": None,
                "qualifiers": [],
            }
        ),
        ranker=_fail_ranker,
    )

    _assert_equal(
        result.status,
        SemanticDecisionStatusV2.UNSUPPORTED,
        "GMV 未授权时统一入口必须保持 fail closed。",
    )
    _assert_equal(
        result.metric_name,
        None,
        "未授权 gmv 不得返回 metric_name。",
    )


_TESTS = (
    test_parsed_gmv_reaches_matched,
    test_generic_new_customer_reaches_clarification,
    test_multiple_intents_stops_before_llm_and_candidate_pipeline,
    test_parse_failed_stops_before_candidate_pipeline,
    test_evidence_conflict_stops_before_candidate_pipeline,
    test_authorization_is_preserved_in_unified_service,
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
    print(
        "Semantic Decision V2 Gate 3J Service Test Summary"
    )
    print(f"Total: {len(_TESTS)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    run_tests()
