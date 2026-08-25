from __future__ import annotations

from app.semantic_layer.candidate_decision_pipeline_v2 import (
    resolve_candidate_decision_v2,
)
from app.semantic_layer.candidate_decision_v2 import (
    CandidateDecisionStatusV2,
)
from app.semantic_layer.question_semantic_parser_v2 import (
    QuestionSemanticParseStatusV2,
    parse_question_semantics_v2,
)


def _assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(
            f"{message}\nExpected: {expected}\nActual: {actual}"
        )


def _assert_true(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def _parse_single(question: str):
    parsed = parse_question_semantics_v2(question)

    _assert_equal(
        parsed.status,
        QuestionSemanticParseStatusV2.PARSED,
        f"测试问题应被 Parser 解析为单一 signature: {question}",
    )
    _assert_true(
        parsed.signature is not None,
        f"PARSED 状态必须带 signature: {question}",
    )
    return parsed.signature


def _fail_if_called(
    question,
    *,
    allowed_metric_names,
    top_k,
):
    raise AssertionError(
        "该路径不应调用 Embedding ranker。"
    )


def test_parser_to_pipeline_matches_gmv() -> None:
    question = "把完成支付的商品金额累计起来"

    result = resolve_candidate_decision_v2(
        question=question,
        question_signature=_parse_single(question),
        ranker=_fail_if_called,
    )

    _assert_equal(
        result.status,
        CandidateDecisionStatusV2.MATCHED,
        "GMV 应在 Parser -> Pipeline 后 MATCHED。",
    )
    _assert_equal(
        result.metric_name,
        "gmv",
        "GMV 应命中 gmv。",
    )


def test_parser_partial_gmv_alias_is_grounded_without_embedding() -> None:
    """
    Day92 真实回归的 deterministic reproduction：
    模拟 Live Parser 漏掉 SUM，只保留 paid_amount。
    """
    question = "2025年GMV是多少？"

    def partial_gmv_llm(
        *,
        messages,
        temperature,
    ) -> str:
        return (
            '{"operator": null, '
            '"left_operand": "paid_amount", '
            '"right_operand": null, '
            '"intrinsic_partition": null, '
            '"qualifiers": []}'
        )

    parsed = parse_question_semantics_v2(
        question,
        llm_call=partial_gmv_llm,
    )

    _assert_equal(
        parsed.status,
        QuestionSemanticParseStatusV2.PARSED,
        "欠解析 GMV payload 仍应形成合法 PARSED signature。",
    )
    _assert_true(
        parsed.signature is not None,
        "PARSED 必须包含 signature。",
    )
    _assert_equal(
        parsed.signature.operator,
        None,
        "本测试必须真实模拟 operator 丢失。",
    )

    result = resolve_candidate_decision_v2(
        question=question,
        question_signature=parsed.signature,
        ranker=_fail_if_called,
    )

    _assert_equal(
        result.status,
        CandidateDecisionStatusV2.MATCHED,
        "显式 GMV 应由 deterministic Alias Grounding 恢复 MATCHED。",
    )
    _assert_equal(
        result.metric_name,
        "gmv",
        "欠解析 GMV 最终应稳定命中 gmv。",
    )
    _assert_true(
        not result.ranking_applied,
        "确定性 Grounding 成功后不应调用 Embedding。",
    )


def test_parser_to_pipeline_matches_ipt() -> None:
    question = "每一笔成交订单平均包含多少件商品？"

    result = resolve_candidate_decision_v2(
        question=question,
        question_signature=_parse_single(question),
        ranker=_fail_if_called,
    )

    _assert_equal(
        result.status,
        CandidateDecisionStatusV2.MATCHED,
        "IPT 应在 Parser -> Pipeline 后 MATCHED。",
    )
    _assert_equal(
        result.metric_name,
        "ipt",
        "IPT 应命中 ipt。",
    )


def test_parser_to_pipeline_matches_roi() -> None:
    question = "各平台成交金额相对于同期推广花费是几倍"

    result = resolve_candidate_decision_v2(
        question=question,
        question_signature=_parse_single(question),
        ranker=_fail_if_called,
    )

    _assert_equal(
        result.status,
        CandidateDecisionStatusV2.MATCHED,
        "ROI 应在 Parser -> Pipeline 后 MATCHED。",
    )
    _assert_equal(
        result.metric_name,
        "roi",
        "ROI 应命中 roi。",
    )


def test_parser_to_pipeline_narrows_generic_average() -> None:
    question = "平均消费大概是多少？"

    def fake_ranker(
        question,
        *,
        allowed_metric_names,
        top_k,
    ):
        _assert_equal(
            set(allowed_metric_names),
            {"spending_per_buyer", "aus"},
            "Embedding 只能看到 average narrowing 后的两个候选。",
        )
        return {
            "method": "embedding_v2",
            "candidates": [
                {"name": "spending_per_buyer", "score": 0.9},
                {"name": "aus", "score": 0.8},
            ],
        }

    result = resolve_candidate_decision_v2(
        question=question,
        question_signature=_parse_single(question),
        ranker=fake_ranker,
    )

    _assert_equal(
        result.status,
        CandidateDecisionStatusV2.NEEDS_CLARIFICATION,
        "平均消费仍应需要澄清。",
    )
    _assert_equal(
        set(result.candidates),
        {"spending_per_buyer", "aus"},
        "平均消费应只剩两个金额平均口径。",
    )


def test_parser_to_pipeline_narrows_generic_new_customer() -> None:
    question = "本期新客有多少？"

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
            "Embedding 只能看到两个新客候选。",
        )
        return {
            "method": "embedding_v2",
            "candidates": [
                {"name": "brand_paid_new_customer_count", "score": 0.9},
                {"name": "channel_paid_new_customer_count", "score": 0.8},
            ],
        }

    result = resolve_candidate_decision_v2(
        question=question,
        question_signature=_parse_single(question),
        ranker=fake_ranker,
    )

    _assert_equal(
        result.status,
        CandidateDecisionStatusV2.NEEDS_CLARIFICATION,
        "普通“新客”仍应需要澄清。",
    )
    _assert_equal(
        set(result.candidates),
        {
            "brand_paid_new_customer_count",
            "channel_paid_new_customer_count",
        },
        "普通“新客”应只剩品牌/渠道两个候选。",
    )


def test_parser_to_pipeline_keeps_unsupported_ratio_unsupported() -> None:
    question = "成交金额平均到每一件卖出的商品上是多少？"

    result = resolve_candidate_decision_v2(
        question=question,
        question_signature=_parse_single(question),
        ranker=_fail_if_called,
    )

    _assert_equal(
        result.status,
        CandidateDecisionStatusV2.UNSUPPORTED,
        "Catalog 不支持的 ratio 应保持 UNSUPPORTED。",
    )


_TESTS = (
    test_parser_to_pipeline_matches_gmv,
    test_parser_partial_gmv_alias_is_grounded_without_embedding,
    test_parser_to_pipeline_matches_ipt,
    test_parser_to_pipeline_matches_roi,
    test_parser_to_pipeline_narrows_generic_average,
    test_parser_to_pipeline_narrows_generic_new_customer,
    test_parser_to_pipeline_keeps_unsupported_ratio_unsupported,
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
    print("Candidate Decision V2 Gate 3I Parser Pipeline Test Summary")
    print(f"Total: {len(_TESTS)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    run_tests()
