from __future__ import annotations

from pydantic import ValidationError

from app.semantic_layer.metric_signature_v2 import (
    IntrinsicPartition,
    MetricSemanticSignatureV2,
    SemanticOperand,
    SemanticQualifier,
    SignatureOperator,
    canonical_metric_signature_catalog_v2,
    get_metric_signature_v2,
    load_metric_signature_catalog_v2,
    metric_signature_catalog_fingerprint_v2,
)
from app.semantic_layer.metric_text_builder_v2 import (
    metric_semantic_corpus_fingerprint_v2,
)


EXPECTED_METRICS = {
    "gmv",
    "gross_margin",
    "gross_margin_rate",
    "refund_rate",
    "roi",
    "cac",
    "brand_paid_new_customer_count",
    "channel_paid_new_customer_count",
    "repeat_customer_rate",
    "member_gmv_share",
    "buyer_count",
    "order_count",
    "units_sold",
    "spending_per_buyer",
    "ipt",
    "aus",
    "purchase_frequency",
    "repeat_customer_count",
    "multi_order_customer_count",
}

EXPECTED_EXISTING_SEMANTIC_CORPUS_FINGERPRINT = (
    "cdfbb9ef725134d14f7b5c4c43f3ca6adbf9690f06809a156722a37ca8fc0346"
)


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(
            f"{message}\nExpected: {expected}\nActual: {actual}"
        )


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_signature_catalog_covers_exactly_19_metrics() -> None:
    catalog = load_metric_signature_catalog_v2()

    assert_equal(
        len(catalog.signatures),
        19,
        "Signature Catalog 必须恰好覆盖 19 Metrics。",
    )

    assert_equal(
        {
            item.metric_name
            for item in catalog.signatures
        },
        EXPECTED_METRICS,
        "Signature Metric Set 必须与冻结的 19 Metrics 一致。",
    )


def test_signature_models_are_frozen_and_forbid_extra() -> None:
    signature = get_metric_signature_v2("gmv")
    assert_true(signature is not None, "GMV signature missing.")

    try:
        signature.metric_name = "changed"
    except (ValidationError, TypeError):
        pass
    else:
        raise AssertionError("Signature model 必须 frozen。")

    try:
        MetricSemanticSignatureV2(
            metric_name="synthetic",
            operator="sum",
            left_operand="paid_amount",
            extra_field="not_allowed",
        )
    except ValidationError:
        return

    raise AssertionError("Signature model 必须 extra=forbid。")


def test_divide_requires_denominator() -> None:
    try:
        MetricSemanticSignatureV2(
            metric_name="synthetic",
            operator=SignatureOperator.DIVIDE,
            left_operand=SemanticOperand.PAID_AMOUNT,
        )
    except ValidationError:
        return

    raise AssertionError("divide 必须声明 denominator/right_operand。")


def test_non_divide_rejects_denominator() -> None:
    try:
        MetricSemanticSignatureV2(
            metric_name="synthetic",
            operator=SignatureOperator.SUM,
            left_operand=SemanticOperand.PAID_AMOUNT,
            right_operand=SemanticOperand.PAID_ORDER,
        )
    except ValidationError:
        return

    raise AssertionError("非 divide 不得声明 right_operand。")


def test_core_ratio_family_is_structurally_distinct() -> None:
    expected = {
        "spending_per_buyer": (
            "paid_amount",
            "paid_buyer",
        ),
        "aus": (
            "paid_amount",
            "paid_order",
        ),
        "ipt": (
            "paid_units",
            "paid_order",
        ),
        "purchase_frequency": (
            "paid_order",
            "paid_buyer",
        ),
    }

    actual = {}

    for metric_name in expected:
        signature = get_metric_signature_v2(metric_name)
        assert_true(signature is not None, f"{metric_name} missing.")

        actual[metric_name] = (
            signature.left_operand.value,
            signature.right_operand.value,
        )

    assert_equal(
        actual,
        expected,
        "AUS / Spending / IPT / Frequency 必须由 numerator/denominator 区分。",
    )

    assert_equal(
        len(set(actual.values())),
        4,
        "核心 ratio family 的结构必须全部唯一。",
    )


def test_gross_margin_amount_and_rate_are_structurally_distinct() -> None:
    amount = get_metric_signature_v2("gross_margin")
    rate = get_metric_signature_v2("gross_margin_rate")

    assert_true(amount is not None and rate is not None, "Margin signatures missing.")

    assert_equal(amount.operator, SignatureOperator.SUM, "毛利额应为 SUM。")
    assert_equal(rate.operator, SignatureOperator.DIVIDE, "毛利率应为 DIVIDE。")

    assert_equal(
        rate.right_operand,
        SemanticOperand.PAID_AMOUNT,
        "毛利率 denominator 必须为 paid_amount。",
    )


def test_brand_and_channel_new_customer_are_structurally_distinct() -> None:
    brand = get_metric_signature_v2(
        "brand_paid_new_customer_count"
    )
    channel = get_metric_signature_v2(
        "channel_paid_new_customer_count"
    )

    assert_true(
        brand is not None and channel is not None,
        "New-customer signatures missing.",
    )

    assert_equal(
        brand.left_operand,
        SemanticOperand.GLOBAL_FIRST_PAID_CUSTOMER,
        "Brand New 必须是 global first paid。",
    )

    assert_equal(
        channel.left_operand,
        SemanticOperand.CHANNEL_FIRST_PAID_CUSTOMER,
        "Channel New 必须是 channel first paid。",
    )

    assert_equal(
        channel.intrinsic_partition,
        IntrinsicPartition.CHANNEL,
        "Channel New 必须内建 channel partition。",
    )


def test_repeat_customer_count_and_multi_order_are_structurally_distinct() -> None:
    repeat = get_metric_signature_v2(
        "repeat_customer_count"
    )
    multi = get_metric_signature_v2(
        "multi_order_customer_count"
    )

    assert_true(
        repeat is not None and multi is not None,
        "Repeat signatures missing.",
    )

    assert_equal(
        repeat.left_operand,
        SemanticOperand.REPEAT_DISTINCT_PAID_DATE_CUSTOMER,
        "跨日复购人数必须由 repeat-distinct-paid-date operand 表达。",
    )

    assert_equal(
        multi.left_operand,
        SemanticOperand.MULTI_PAID_ORDER_CUSTOMER,
        "两单及以上人数必须由 multi-paid-order operand 表达。",
    )

    assert_equal(
        repeat.qualifiers,
        (),
        "跨日条件已内生于 operand，不应重复声明 qualifier。",
    )

    assert_equal(
        multi.qualifiers,
        (),
        "两单及以上条件已内生于 operand，不应重复声明 qualifier。",
    )


def test_refund_rate_carries_amount_and_cohort_semantics() -> None:
    signature = get_metric_signature_v2("refund_rate")
    assert_true(signature is not None, "refund_rate missing.")

    assert_equal(
        (
            signature.left_operand,
            signature.right_operand,
        ),
        (
            SemanticOperand.COMPLETED_REFUND_AMOUNT,
            SemanticOperand.PAID_AMOUNT,
        ),
        "退款率必须是退款金额 / 原支付金额。",
    )

    assert_true(
        SemanticQualifier.SALES_COHORT_ATTRIBUTION
        in signature.qualifiers,
        "退款率必须保留 sales cohort attribution。",
    )


def test_member_share_carries_payment_time_snapshot() -> None:
    signature = get_metric_signature_v2("member_gmv_share")
    assert_true(signature is not None, "member_gmv_share missing.")

    assert_equal(
        signature.left_operand,
        SemanticOperand.PAYMENT_TIME_MEMBER_PAID_AMOUNT,
        "会员 GMV Share numerator 必须是支付时点会员金额。",
    )

    assert_equal(
        signature.qualifiers,
        (),
        "支付时点会员快照已内生于 operand，不应重复声明 qualifier。",
    )


def test_qualifier_contract_contains_only_orthogonal_semantics() -> None:
    assert_equal(
        {
            qualifier.value
            for qualifier in SemanticQualifier
        },
        {
            "product_cost_basis",
            "sales_cohort_attribution",
            "direct_response_channel",
            "same_window_sales_spend",
        },
        "Qualifier Contract 只能保留独立于 operand 的业务语义。",
    )


def test_channel_marketing_metrics_require_channel_partition() -> None:
    for metric_name in (
        "roi",
        "cac",
    ):
        signature = get_metric_signature_v2(metric_name)
        assert_true(signature is not None, f"{metric_name} missing.")

        assert_equal(
            signature.intrinsic_partition,
            IntrinsicPartition.CHANNEL,
            f"{metric_name} 必须内建 channel partition。",
        )


def test_no_duplicate_business_structures() -> None:
    catalog = load_metric_signature_catalog_v2()

    keys = [
        signature.structural_key()
        for signature in catalog.signatures
    ]

    assert_equal(
        len(keys),
        len(set(keys)),
        "19 Metrics 不得存在完全相同的 Semantic Signature。",
    )


def test_signature_catalog_contains_no_retrieval_keywords() -> None:
    forbidden_fields = {
        "aliases",
        "examples",
        "negative_examples",
        "keywords",
        "question_cues",
        "threshold",
        "gap_threshold",
        "tables",
        "filters",
        "sql",
    }

    catalog = load_metric_signature_catalog_v2()

    for signature in catalog.signatures:
        fields = set(
            signature.model_dump(
                mode="json"
            )
        )

        assert_true(
            not (
                fields
                & forbidden_fields
            ),
            (
                f"{signature.metric_name} Signature "
                "不得退化成 retrieval keyword contract。"
            ),
        )


def test_signature_fingerprint_is_deterministic() -> None:
    assert_equal(
        canonical_metric_signature_catalog_v2(),
        canonical_metric_signature_catalog_v2(),
        "Canonical Signature Catalog 必须 deterministic。",
    )

    fingerprint_a = metric_signature_catalog_fingerprint_v2()
    fingerprint_b = metric_signature_catalog_fingerprint_v2()

    assert_equal(
        fingerprint_a,
        fingerprint_b,
        "Signature fingerprint 必须 deterministic。",
    )

    assert_equal(
        len(fingerprint_a),
        64,
        "Signature SHA-256 应为 64 hex chars。",
    )


def test_existing_embedding_corpus_fingerprint_is_unchanged() -> None:
    assert_equal(
        metric_semantic_corpus_fingerprint_v2(),
        EXPECTED_EXISTING_SEMANTIC_CORPUS_FINGERPRINT,
        (
            "新增独立 Signature Catalog 不得改变现有 "
            "single-document semantic corpus。"
        ),
    )


def run_tests() -> None:
    tests = [
        test_signature_catalog_covers_exactly_19_metrics,
        test_signature_models_are_frozen_and_forbid_extra,
        test_divide_requires_denominator,
        test_non_divide_rejects_denominator,
        test_core_ratio_family_is_structurally_distinct,
        test_gross_margin_amount_and_rate_are_structurally_distinct,
        test_brand_and_channel_new_customer_are_structurally_distinct,
        test_repeat_customer_count_and_multi_order_are_structurally_distinct,
        test_refund_rate_carries_amount_and_cohort_semantics,
        test_member_share_carries_payment_time_snapshot,
        test_qualifier_contract_contains_only_orthogonal_semantics,
        test_channel_marketing_metrics_require_channel_partition,
        test_no_duplicate_business_structures,
        test_signature_catalog_contains_no_retrieval_keywords,
        test_signature_fingerprint_is_deterministic,
        test_existing_embedding_corpus_fingerprint_is_unchanged,
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
    print("Metric Semantic Signature V2 Test Summary")
    print(f"Total: {len(tests)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    catalog = load_metric_signature_catalog_v2()

    print(
        "Metric Signatures:",
        len(catalog.signatures),
    )
    print(
        "Signature Fingerprint:",
        metric_signature_catalog_fingerprint_v2(),
    )
    print(
        "Semantic Corpus Fingerprint:",
        metric_semantic_corpus_fingerprint_v2(),
    )

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    run_tests()
