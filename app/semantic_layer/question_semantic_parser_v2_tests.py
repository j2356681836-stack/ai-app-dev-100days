from __future__ import annotations

import json

from app.semantic_layer.metric_signature_v2 import (
    IntrinsicPartition,
    SemanticOperand,
    SemanticQualifier,
)
from app.semantic_layer.question_semantic_parser_v2 import (
    QuestionSemanticParseStatusV2,
    build_question_semantic_parser_prompt_v2,
    detect_multiple_intents_v2,
    extract_deterministic_question_evidence_v2,
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


def test_grouped_separately_is_not_multi_intent() -> None:
    is_multi, marker = detect_multiple_intents_v2(
        "按渠道分别看，每位客户第一次在该渠道成交的人数"
    )

    assert_equal(
        is_multi,
        False,
        "按维度分别展示不应被误判为多个业务请求。",
    )

    assert_equal(
        marker,
        None,
        "非 multi-intent 不应产生 guard marker。",
    )


def test_parallel_separate_requests_remain_multi_intent() -> None:
    is_multi, marker = detect_multiple_intents_v2(
        "分别看跨两个成交日的客户数，以及成交两单以上的客户数"
    )

    assert_equal(
        is_multi,
        True,
        "明确并列的分别请求必须继续被识别为 multi-intent。",
    )

    assert_equal(
        marker,
        "separate_requests_marker",
        "分别并列请求应保留正确 guard marker。",
    )



def test_separate_dimensions_pass_through_multi_intent_guard() -> None:
    is_multi, marker = detect_multiple_intents_v2(
        "分别按渠道和地区看2025年GMV"
    )

    assert_equal(
        is_multi,
        False,
        (
            "一个指标分别按多个结果维度查看时，"
            "不应被 Parser Guard 误判为多个业务意图。"
        ),
    )

    assert_equal(
        marker,
        None,
        "Result Grain request 不应产生 multi-intent marker。",
    )


def test_separate_region_category_pass_through_multi_intent_guard() -> None:
    is_multi, marker = detect_multiple_intents_v2(
        "分别按地区、品类统计销售额"
    )

    assert_equal(
        is_multi,
        False,
        "多个受支持维度的 separate result sets 应交给 Grain Resolver。",
    )

    assert_equal(
        marker,
        None,
        "Separate result grain request 不应产生 guard marker。",
    )


def test_average_is_deterministic_divide_evidence() -> None:
    evidence = (
        extract_deterministic_question_evidence_v2(
            "平均消费大概是多少？"
        )
    )

    assert_equal(
        evidence.operator,
        QuestionOperator.DIVIDE,
        "明确平均关系应提供 divide deterministic evidence。",
    )

    assert_true(
        "explicit_average_token"
        in evidence.evidence,
        "平均关系应记录 explicit_average_token。",
    )


def test_explicit_product_cost_is_deterministic_qualifier_evidence() -> None:
    evidence = (
        extract_deterministic_question_evidence_v2(
            "成交收入扣商品成本后剩多少？"
        )
    )

    assert_true(
        SemanticQualifier.PRODUCT_COST_BASIS
        in evidence.qualifiers,
        "明确商品成本应提供 product_cost_basis evidence。",
    )

    assert_true(
        "explicit_product_cost_basis"
        in evidence.evidence,
        "Product cost evidence 应记录明确 evidence marker。",
    )


def test_revenue_cost_difference_is_product_cost_basis_evidence() -> None:
    evidence = (
        extract_deterministic_question_evidence_v2(
            "已成交商品的收入和成本做差后累计金额"
        )
    )

    assert_true(
        SemanticQualifier.PRODUCT_COST_BASIS
        in evidence.qualifiers,
        "成交收入与成本做差应识别为 product_cost_basis。",
    )


def test_revenue_minus_cost_is_product_cost_basis_evidence() -> None:
    evidence = (
        extract_deterministic_question_evidence_v2(
            "成交收入扣成本后的余额，占成交收入本身几成？"
        )
    )

    assert_true(
        SemanticQualifier.PRODUCT_COST_BASIS
        in evidence.qualifiers,
        "成交收入扣成本应识别为 product_cost_basis。",
    )


def test_advertising_cost_is_not_product_cost_basis_evidence() -> None:
    evidence = (
        extract_deterministic_question_evidence_v2(
            "广告成本除以新客数"
        )
    )

    assert_true(
        SemanticQualifier.PRODUCT_COST_BASIS
        not in evidence.qualifiers,
        "广告成本不得误判为商品成本口径。",
    )


def test_advertising_cost_is_not_product_cost_basis_evidence() -> None:
    evidence = (
        extract_deterministic_question_evidence_v2(
            "广告成本除以新客数"
        )
    )

    assert_true(
        SemanticQualifier.PRODUCT_COST_BASIS
        not in evidence.qualifiers,
        "广告成本不得误判为商品成本口径。",
    )


def test_channel_marketing_cost_is_not_product_cost_basis_evidence() -> None:
    evidence = (
        extract_deterministic_question_evidence_v2(
            "渠道投放成本是多少？"
        )
    )

    assert_true(
        SemanticQualifier.PRODUCT_COST_BASIS
        not in evidence.qualifiers,
        "渠道投放成本不得误判为 product_cost_basis。",
    )
    

def test_product_cost_evidence_fills_missing_llm_qualifier() -> None:
    def fake_llm(**kwargs):
        return fake_llm_payload(
            operator="divide",
            left_operand="gross_margin_amount",
            right_operand="paid_amount",
            qualifiers=[],
        )

    result = parse_question_semantics_v2(
        "成交收入扣成本后的余额，占成交收入本身几成？",
        llm_call=fake_llm,
    )

    assert_equal(
        result.status,
        QuestionSemanticParseStatusV2.PARSED,
        "明确 product-cost 语义应正常解析。",
    )

    assert_true(
        result.signature is not None,
        "Parsed result 必须产生 signature。",
    )

    assert_true(
        SemanticQualifier.PRODUCT_COST_BASIS
        in result.signature.qualifiers,
        (
            "即使 LLM 漏掉 qualifier，"
            "deterministic evidence 也必须补入 product_cost_basis。"
        ),
    )


def test_prompt_forbids_generic_analysis_from_implying_aggregation() -> None:
    prompt = (
        build_question_semantic_parser_prompt_v2(
            "成交金额怎么样？"
        )
    )

    assert_true(
        "怎么样" in prompt,
        "Prompt 应明确覆盖泛化分析请求。",
    )

    assert_true(
        "operator 返回 null" in prompt,
        "泛化分析请求不得默认补 sum/count/divide。",
    )


def test_prompt_explains_channel_first_paid_procedural_phrasing() -> None:
    prompt = (
        build_question_semantic_parser_prompt_v2(
            "各平台把客户历史首笔成交找出来，再统计本期首笔人数"
        )
    )

    assert_true(
        "各渠道" in prompt
        or "各平台" in prompt,
        "channel-first operand 定义应覆盖按渠道/平台逐组表达。",
    )

    assert_true(
        "历史首笔" in prompt,
        "channel-first operand 定义应覆盖历史首笔程序式表达。",
    )


def test_countable_entity_question_is_deterministic_count_evidence() -> None:
    evidence = (
        extract_deterministic_question_evidence_v2(
            "本期新客有多少？"
        )
    )

    assert_equal(
        evidence.operator,
        QuestionOperator.COUNT,
        "明确询问可计数实体数量时应提供 count evidence。",
    )

    assert_true(
        "explicit_count_token"
        in evidence.evidence,
        "Count evidence 应记录 explicit_count_token。",
    )


def test_amount_how_much_is_not_count_evidence() -> None:
    evidence = (
        extract_deterministic_question_evidence_v2(
            "成交金额有多少？"
        )
    )

    assert_true(
        evidence.operator
        != QuestionOperator.COUNT,
        "金额“有多少”不得因为出现多少而误判为 count。",
    )


def test_revenue_cost_difference_fills_gross_margin_operand() -> None:
    def fake_llm(**kwargs):
        return fake_llm_payload(
            operator=None,
            left_operand=None,
            right_operand=None,
            qualifiers=[],
        )

    result = parse_question_semantics_v2(
        "已成交商品的收入和成本做差后累计金额",
        llm_call=fake_llm,
    )

    assert_equal(
        result.status,
        QuestionSemanticParseStatusV2.PARSED,
        "明确收入减成本结构应正常解析。",
    )

    assert_true(
        result.signature is not None,
        "Parsed result 必须有 signature。",
    )

    assert_equal(
        result.signature.operator,
        QuestionOperator.SUM,
        "累计金额应保留 deterministic sum。",
    )

    assert_equal(
        result.signature.left_operand,
        SemanticOperand.GROSS_MARGIN_AMOUNT,
        "收入与商品成本做差应补 gross_margin_amount。",
    )


def test_marketing_cost_does_not_fill_gross_margin_operand() -> None:
    def fake_llm(**kwargs):
        return fake_llm_payload(
            operator="divide",
            left_operand=None,
            right_operand="paid_buyer",
        )

    result = parse_question_semantics_v2(
        "广告成本除以成交客户数",
        llm_call=fake_llm,
    )

    assert_true(
        result.signature is not None,
        "Signature missing.",
    )

    assert_true(
        result.signature.left_operand
        != SemanticOperand.GROSS_MARGIN_AMOUNT,
        "广告成本不得被 deterministic evidence 解释成 gross margin。",
    )


def test_generic_average_rejects_paid_amount_over_inference() -> None:
    def fake_llm(**kwargs):
        return fake_llm_payload(
            operator="divide",
            left_operand="paid_amount",
            right_operand=None,
        )

    result = parse_question_semantics_v2(
        "平均消费大概是多少？",
        llm_call=fake_llm,
    )

    assert_equal(
        result.status,
        QuestionSemanticParseStatusV2.PARSED,
        "泛化 average 应保留合法 partial signature。",
    )

    assert_true(
        result.signature is not None,
        "Partial signature 不应缺失。",
    )

    assert_equal(
        result.signature.operator,
        QuestionOperator.DIVIDE,
        "明确 average evidence 应保留 divide。",
    )

    assert_equal(
        result.signature.left_operand,
        None,
        "未说明平均对象时，不得擅自补 paid_amount。",
    )

    assert_equal(
        result.signature.right_operand,
        None,
        "未说明 denominator 时应保持 null。",
    )


def test_explicit_average_per_buyer_preserves_operands() -> None:
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

    assert_true(
        result.signature is not None,
        "Signature missing.",
    )

    assert_equal(
        (
            result.signature.left_operand,
            result.signature.right_operand,
        ),
        (
            SemanticOperand.PAID_AMOUNT,
            SemanticOperand.PAID_BUYER,
        ),
        "明确每位成交买家时不得清空合法 amount/buyer 结构。",
    )


def test_generic_new_customer_rejects_operand_over_inference() -> None:
    def fake_llm(**kwargs):
        return fake_llm_payload(
            operator="count",
            left_operand="global_first_paid_customer",
        )

    result = parse_question_semantics_v2(
        "本期新客有多少？",
        llm_call=fake_llm,
    )

    assert_equal(
        result.status,
        QuestionSemanticParseStatusV2.PARSED,
        "泛化新客仍应得到合法 partial signature。",
    )

    assert_true(
        result.signature is not None,
        "Partial signature 不应缺失。",
    )

    assert_equal(
        result.signature.operator,
        QuestionOperator.COUNT,
        "明确数量问题应保留 count。",
    )

    assert_equal(
        result.signature.left_operand,
        None,
        "未说明品牌/渠道口径时，不得将泛化新客具体化为某种 first-paid customer。",
    )


def test_brand_first_paid_operand_remains_when_explicit() -> None:
    def fake_llm(**kwargs):
        return fake_llm_payload(
            operator="count",
            left_operand="global_first_paid_customer",
        )

    result = parse_question_semantics_v2(
        "全品牌历史里第一次成交的客户有多少？",
        llm_call=fake_llm,
    )

    assert_true(
        result.signature is not None,
        "Signature missing.",
    )

    assert_equal(
        result.signature.left_operand,
        SemanticOperand.GLOBAL_FIRST_PAID_CUSTOMER,
        "明确品牌全历史时应保留 global first-paid operand。",
    )


def test_channel_first_paid_operand_remains_when_explicit() -> None:
    def fake_llm(**kwargs):
        return fake_llm_payload(
            operator="count",
            left_operand="channel_first_paid_customer",
            intrinsic_partition="channel",
        )

    result = parse_question_semantics_v2(
        "按每个平台自己的历史统计首次成交客户数",
        llm_call=fake_llm,
    )

    assert_true(
        result.signature is not None,
        "Signature missing.",
    )

    assert_equal(
        result.signature.left_operand,
        SemanticOperand.CHANNEL_FIRST_PAID_CUSTOMER,
        "明确平台自己的历史时应保留 channel first-paid operand。",
    )


def test_average_per_order_units_preserves_operands() -> None:
    def fake_llm(**kwargs):
        return fake_llm_payload(
            operator="divide",
            left_operand="paid_units",
            right_operand="paid_order",
        )

    result = parse_question_semantics_v2(
        "每一笔成交订单平均包含多少件商品？",
        llm_call=fake_llm,
    )

    assert_true(
        result.signature is not None,
        "Signature missing.",
    )

    assert_equal(
        (
            result.signature.left_operand,
            result.signature.right_operand,
        ),
        (
            SemanticOperand.PAID_UNITS,
            SemanticOperand.PAID_ORDER,
        ),
        "明确每笔订单平均件数不得被 generic-average guard 清空。",
    )


def test_average_order_amount_preserves_operands() -> None:
    def fake_llm(**kwargs):
        return fake_llm_payload(
            operator="divide",
            left_operand="paid_amount",
            right_operand="paid_order",
        )

    result = parse_question_semantics_v2(
        "一笔成交订单平均对应多少成交金额？",
        llm_call=fake_llm,
    )

    assert_true(
        result.signature is not None,
        "Signature missing.",
    )

    assert_equal(
        (
            result.signature.left_operand,
            result.signature.right_operand,
        ),
        (
            SemanticOperand.PAID_AMOUNT,
            SemanticOperand.PAID_ORDER,
        ),
        "明确订单平均金额不得被清空。",
    )


def test_average_per_distinct_buyer_preserves_operands() -> None:
    def fake_llm(**kwargs):
        return fake_llm_payload(
            operator="divide",
            left_operand="paid_order",
            right_operand="paid_buyer",
        )

    result = parse_question_semantics_v2(
        "成交订单数平均分到每个去重买家后是多少",
        llm_call=fake_llm,
    )

    assert_true(
        result.signature is not None,
        "Signature missing.",
    )

    assert_equal(
        (
            result.signature.left_operand,
            result.signature.right_operand,
        ),
        (
            SemanticOperand.PAID_ORDER,
            SemanticOperand.PAID_BUYER,
        ),
        "明确每个去重买家时不得清空 frequency 结构。",
    )


def test_average_per_unit_preserves_operands() -> None:
    def fake_llm(**kwargs):
        return fake_llm_payload(
            operator="divide",
            left_operand="paid_amount",
            right_operand="paid_units",
        )

    result = parse_question_semantics_v2(
        "成交金额平均到每一件卖出的商品上是多少？",
        llm_call=fake_llm,
    )

    assert_true(
        result.signature is not None,
        "Signature missing.",
    )

    assert_equal(
        (
            result.signature.left_operand,
            result.signature.right_operand,
        ),
        (
            SemanticOperand.PAID_AMOUNT,
            SemanticOperand.PAID_UNITS,
        ),
        "明确每件商品 averaging basis 时不得清空。",
    )


def test_average_to_channel_first_customer_preserves_operands() -> None:
    def fake_llm(**kwargs):
        return fake_llm_payload(
            operator="divide",
            left_operand="marketing_spend",
            right_operand="channel_first_paid_customer",
            intrinsic_partition="channel",
        )

    result = parse_question_semantics_v2(
        "每个平台的推广费用，平均分到首次在该平台成交的客户头上是多少？",
        llm_call=fake_llm,
    )

    assert_true(
        result.signature is not None,
        "Signature missing.",
    )

    assert_equal(
        (
            result.signature.left_operand,
            result.signature.right_operand,
        ),
        (
            SemanticOperand.MARKETING_SPEND,
            SemanticOperand.CHANNEL_FIRST_PAID_CUSTOMER,
        ),
        "明确 CAC averaging structure 不得被 generic-average guard 清空。",
    )


def test_generic_average_rejects_complete_ratio_over_inference() -> None:
    def fake_llm(**kwargs):
        return fake_llm_payload(
            operator="divide",
            left_operand="paid_amount",
            right_operand="paid_buyer",
        )

    result = parse_question_semantics_v2(
        "平均消费大概是多少？",
        llm_call=fake_llm,
    )

    assert_true(
        result.signature is not None,
        "Partial signature 不应缺失。",
    )

    assert_equal(
        (
            result.signature.left_operand,
            result.signature.right_operand,
        ),
        (
            None,
            None,
        ),
        "泛化 average 不得因为 LLM 给出完整 ratio 就接受无证据 operands。",
    )


def test_total_money_expression_is_deterministic_sum_evidence() -> None:
    evidence = (
        extract_deterministic_question_evidence_v2(
            "成交商品收款扣掉商品成本以后，总共留下多少钱？"
        )
    )

    assert_equal(
        evidence.operator,
        QuestionOperator.SUM,
        "明确询问总金额时应提供 sum deterministic evidence。",
    )

    assert_true(
        "explicit_total_amount_token"
        in evidence.evidence,
        "总金额证据应记录 explicit_total_amount_token。",
    )


def test_total_count_expression_is_not_sum_evidence() -> None:
    evidence = (
        extract_deterministic_question_evidence_v2(
            "总共有多少客户？"
        )
    )

    assert_equal(
        evidence.operator,
        QuestionOperator.COUNT,
        "“总共有多少客户”是实体计数，不得因“总共”误判为 sum。",
    )


def test_same_window_sales_spend_is_deterministic_qualifier_evidence() -> None:
    evidence = (
        extract_deterministic_question_evidence_v2(
            "各平台成交金额相对于同期推广花费是几倍"
        )
    )

    assert_true(
        SemanticQualifier.SAME_WINDOW_SALES_SPEND
        in evidence.qualifiers,
        (
            "销售金额与同期推广投入同时出现时，"
            "应提供 same_window_sales_spend evidence。"
        ),
    )

    assert_true(
        "explicit_same_window_sales_spend"
        in evidence.evidence,
        "Same-window evidence 应记录明确 marker。",
    )


def test_same_period_without_sales_spend_pair_is_not_same_window_evidence() -> None:
    evidence = (
        extract_deterministic_question_evidence_v2(
            "同期成交客户有多少？"
        )
    )

    assert_true(
        SemanticQualifier.SAME_WINDOW_SALES_SPEND
        not in evidence.qualifiers,
        (
            "仅出现“同期”但没有销售与营销投入配对时，"
            "不得产生 same_window_sales_spend。"
        ),
    )


def test_total_money_evidence_fills_missing_llm_sum() -> None:
    def fake_llm(**kwargs):
        return fake_llm_payload(
            operator=None,
            left_operand="gross_margin_amount",
            right_operand=None,
            qualifiers=[],
        )

    result = parse_question_semantics_v2(
        "成交商品收款扣掉商品成本以后，总共留下多少钱？",
        llm_call=fake_llm,
    )

    assert_equal(
        result.status,
        QuestionSemanticParseStatusV2.PARSED,
        "明确总金额结构应正常解析。",
    )

    assert_true(
        result.signature is not None,
        "Parsed result 必须有 signature。",
    )

    assert_equal(
        result.signature.operator,
        QuestionOperator.SUM,
        "LLM 漏掉 operator 时，total amount evidence 应补 sum。",
    )

    assert_equal(
        result.signature.left_operand,
        SemanticOperand.GROSS_MARGIN_AMOUNT,
        "gross margin operand 应保持正确。",
    )

    assert_true(
        SemanticQualifier.PRODUCT_COST_BASIS
        in result.signature.qualifiers,
        "product_cost_basis 应保持正确。",
    )


def test_same_window_evidence_fills_missing_llm_qualifier() -> None:
    def fake_llm(**kwargs):
        return fake_llm_payload(
            operator="divide",
            left_operand="paid_amount",
            right_operand="marketing_spend",
            intrinsic_partition="channel",
            qualifiers=[],
        )

    result = parse_question_semantics_v2(
        "各平台成交金额相对于同期推广花费是几倍",
        llm_call=fake_llm,
    )

    assert_equal(
        result.status,
        QuestionSemanticParseStatusV2.PARSED,
        "明确 same-window ROI structure 应正常解析。",
    )

    assert_true(
        result.signature is not None,
        "Parsed result 必须有 signature。",
    )

    assert_true(
        SemanticQualifier.SAME_WINDOW_SALES_SPEND
        in result.signature.qualifiers,
        (
            "LLM 漏 qualifier 时，"
            "deterministic evidence 应补 same_window_sales_spend。"
        ),
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

        test_grouped_separately_is_not_multi_intent,
        test_parallel_separate_requests_remain_multi_intent,
        test_separate_dimensions_pass_through_multi_intent_guard,
        test_separate_region_category_pass_through_multi_intent_guard,
        test_average_is_deterministic_divide_evidence,
        
        test_explicit_product_cost_is_deterministic_qualifier_evidence,
        test_revenue_cost_difference_is_product_cost_basis_evidence,
        test_revenue_minus_cost_is_product_cost_basis_evidence,
        test_advertising_cost_is_not_product_cost_basis_evidence,
        test_channel_marketing_cost_is_not_product_cost_basis_evidence,
        test_product_cost_evidence_fills_missing_llm_qualifier,

        test_revenue_cost_difference_fills_gross_margin_operand,
        test_marketing_cost_does_not_fill_gross_margin_operand,
        test_generic_average_rejects_paid_amount_over_inference,
        test_explicit_average_per_buyer_preserves_operands,

        test_prompt_forbids_generic_analysis_from_implying_aggregation,
        test_prompt_explains_channel_first_paid_procedural_phrasing,

        test_countable_entity_question_is_deterministic_count_evidence,
        test_amount_how_much_is_not_count_evidence,
        test_generic_new_customer_rejects_operand_over_inference,
        test_brand_first_paid_operand_remains_when_explicit,
        test_channel_first_paid_operand_remains_when_explicit,

        test_average_per_order_units_preserves_operands,
        test_average_order_amount_preserves_operands,
        test_average_per_distinct_buyer_preserves_operands,
        test_average_per_unit_preserves_operands,
        test_average_to_channel_first_customer_preserves_operands,
        test_generic_average_rejects_complete_ratio_over_inference,

        test_total_money_expression_is_deterministic_sum_evidence,
        test_total_count_expression_is_not_sum_evidence,
        test_same_window_sales_spend_is_deterministic_qualifier_evidence,
        test_same_period_without_sales_spend_pair_is_not_same_window_evidence,
        test_total_money_evidence_fills_missing_llm_sum,
        test_same_window_evidence_fills_missing_llm_qualifier,
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
