from __future__ import annotations

import json

from app.semantic_layer.metric_signature_v2 import (
    IntrinsicPartition,
    SemanticOperand,
)
from app.semantic_layer.question_semantic_parser_v2 import (
    QuestionSemanticParseStatusV2,
    build_question_semantic_parser_prompt_v2,
    parse_question_semantics_v2,
)
from app.semantic_layer.question_signature_v2 import (
    QuestionOperator,
)


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(
            f"{message}\nExpected: {expected}\nActual: {actual}"
        )


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def fake_llm_payload(**kwargs) -> str:
    payload = {
        "operator": None,
        "left_operand": None,
        "right_operand": None,
        "intrinsic_partition": None,
        "qualifiers": [],
    }
    payload.update(kwargs)

    return json.dumps(
        payload,
        ensure_ascii=False,
    )


def test_prompt_contains_no_metric_selection_contract() -> None:
    prompt = (
        build_question_semantic_parser_prompt_v2(
            "平均每位成交买家贡献多少成交金额？"
        )
    )

    assert_true(
        "metric_name" in prompt,
        "Prompt 应明确禁止 metric_name。",
    )

    for metric_name in (
        "spending_per_buyer",
        "aus",
        "ipt",
        "purchase_frequency",
        "gmv",
    ):
        assert_true(
            metric_name not in prompt,
            (
                "Structured Parser Prompt 不应泄漏 "
                f"Metric ID: {metric_name}"
            ),
        )


def test_amount_per_buyer_parses_to_structure() -> None:
    def fake_llm(**kwargs):
        return fake_llm_payload(
            operator="divide",
            left_operand="paid_amount",
            right_operand="paid_buyer",
        )

    result = parse_question_semantics_v2(
        "平均每位成交买家贡献多少成交金额？",
        llm_call=fake_llm,
    )

    assert_equal(
        result.status,
        QuestionSemanticParseStatusV2.PARSED,
        "应成功解析。",
    )

    assert_true(
        result.signature is not None,
        "Parsed result 必须有 signature。",
    )

    assert_equal(
        (
            result.signature.operator,
            result.signature.left_operand,
            result.signature.right_operand,
        ),
        (
            QuestionOperator.DIVIDE,
            SemanticOperand.PAID_AMOUNT,
            SemanticOperand.PAID_BUYER,
        ),
        "Amount/buyer 结构错误。",
    )


def test_unknown_structure_preserves_nulls() -> None:
    def fake_llm(**kwargs):
        return fake_llm_payload()

    result = parse_question_semantics_v2(
        "业务最近怎么样？",
        llm_call=fake_llm,
    )

    assert_equal(
        result.status,
        QuestionSemanticParseStatusV2.PARSED,
        "未知结构本身是合法 parsed result。",
    )

    assert_true(
        result.signature is not None,
        "Unknown parsed signature should exist.",
    )

    assert_equal(
        result.signature.operator,
        None,
        "未知 operator 不应猜测。",
    )
    assert_equal(
        result.signature.left_operand,
        None,
        "未知 operand 不应猜测。",
    )


def test_forbidden_metric_name_fails_closed() -> None:
    def fake_llm(**kwargs):
        return json.dumps(
            {
                "operator": "divide",
                "left_operand": "paid_amount",
                "right_operand": "paid_buyer",
                "intrinsic_partition": None,
                "qualifiers": [],
                "metric_name": "spending_per_buyer",
            },
            ensure_ascii=False,
        )

    result = parse_question_semantics_v2(
        "平均每位成交买家贡献多少成交金额？",
        llm_call=fake_llm,
    )

    assert_equal(
        result.status,
        QuestionSemanticParseStatusV2.PARSE_FAILED,
        "Forbidden metric_name 必须 fail closed。",
    )


def test_invalid_enum_fails_closed() -> None:
    def fake_llm(**kwargs):
        return fake_llm_payload(
            operator="ratio_magic",
        )

    result = parse_question_semantics_v2(
        "A 除以 B",
        llm_call=fake_llm,
    )

    assert_equal(
        result.status,
        QuestionSemanticParseStatusV2.PARSE_FAILED,
        "非法 enum 必须 fail closed。",
    )


def test_explicit_divide_conflict_is_rejected() -> None:
    def fake_llm(**kwargs):
        return fake_llm_payload(
            operator="count",
            left_operand="paid_order",
        )

    result = parse_question_semantics_v2(
        "成交订单数除以成交客户数",
        llm_call=fake_llm,
    )

    assert_equal(
        result.status,
        QuestionSemanticParseStatusV2.EVIDENCE_CONFLICT,
        "明确“除以”与 LLM count 冲突时必须拒绝。",
    )


def test_explicit_divide_can_fill_missing_llm_operator() -> None:
    def fake_llm(**kwargs):
        return fake_llm_payload(
            operator=None,
            left_operand="paid_order",
            right_operand="paid_buyer",
        )

    result = parse_question_semantics_v2(
        "成交订单数除以成交客户数",
        llm_call=fake_llm,
    )

    assert_equal(
        result.status,
        QuestionSemanticParseStatusV2.PARSED,
        "High-confidence evidence 可补空 operator。",
    )

    assert_true(
        result.signature is not None,
        "Signature missing.",
    )

    assert_equal(
        result.signature.operator,
        QuestionOperator.DIVIDE,
        "Explicit divide evidence 应补成 divide。",
    )


def test_channel_evidence_can_fill_partition() -> None:
    def fake_llm(**kwargs):
        return fake_llm_payload(
            operator="divide",
            left_operand="paid_amount",
            right_operand="marketing_spend",
            intrinsic_partition=None,
        )

    result = parse_question_semantics_v2(
        "渠道成交金额除以推广费用",
        llm_call=fake_llm,
    )

    assert_true(
        result.signature is not None,
        "Signature missing.",
    )

    assert_equal(
        result.signature.intrinsic_partition,
        IntrinsicPartition.CHANNEL,
        "明确渠道 evidence 应补 channel partition。",
    )


def test_multi_intent_guard_stops_llm_call() -> None:
    called = {
        "value": False,
    }

    def fake_llm(**kwargs):
        called["value"] = True
        raise AssertionError(
            "Multi-intent case must not call LLM."
        )

    result = parse_question_semantics_v2(
        "同时告诉我成交总金额和成交客户数",
        llm_call=fake_llm,
    )

    assert_equal(
        result.status,
        QuestionSemanticParseStatusV2.MULTIPLE_INTENTS,
        "明显 multi-intent 应提前截断。",
    )

    assert_true(
        not called["value"],
        "Multi-intent guard 后不应调用 LLM。",
    )


def run_tests() -> None:
    tests = [
        test_prompt_contains_no_metric_selection_contract,
        test_amount_per_buyer_parses_to_structure,
        test_unknown_structure_preserves_nulls,
        test_forbidden_metric_name_fails_closed,
        test_invalid_enum_fails_closed,
        test_explicit_divide_conflict_is_rejected,
        test_explicit_divide_can_fill_missing_llm_operator,
        test_channel_evidence_can_fill_partition,
        test_multi_intent_guard_stops_llm_call,
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
    print(
        "Question Structured Semantic Parser V2 Test Summary"
    )
    print(f"Total: {len(tests)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    run_tests()
