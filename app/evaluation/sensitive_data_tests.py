from pydantic import ValidationError

from app.governance.access_context import (
    AccessContext,
    AccessRole,
    OperationMode,
    SensitiveDataPolicy,
)
from app.governance.sensitive_data import (
    ProtectionAction,
    ProtectionReason,
    ResultFieldBinding,
    ResultProtectionContract,
    ResultShape,
    SensitiveDataCategory,
    build_contract_fingerprint,
    build_raw_field_binding,
    classify_v2_source_column,
    protect_result_rows,
)


TOKEN_SECRET = "day71-test-secret-32-characters"


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(
            f"{message}\nExpected: {expected}\nActual: {actual}"
        )


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def build_context(
    *,
    allow_direct_identifiers: bool = False,
    allow_free_text: bool = False,
    allow_cost_data: bool = False,
    minimum_group_size: int = 5,
) -> AccessContext:
    return AccessContext(
        request_id="req-day71-001",
        actor_id="analyst-001",
        role=AccessRole.SCOPED_ANALYST,
        dataset_name="beauty_bi_v2",
        target_schema="beauty_bi_v2",
        operation_mode=OperationMode.OBSERVE_ADVISE,
        allowed_metrics=frozenset({"order_count"}),
        allowed_tables=frozenset({
            "dim_customer",
            "fact_orders",
            "fact_reviews",
            "fact_order_items",
        }),
        allowed_columns=frozenset({
            "dim_customer.customer_code",
            "fact_orders.order_count",
            "fact_reviews.review_text",
            "fact_order_items.item_cost_amount",
        }),
        denied_columns=frozenset(),
        allowed_region_codes=frozenset({"EAST"}),
        allowed_channel_codes=frozenset({"TMALL"}),
        sensitive_data_policy=SensitiveDataPolicy(
            allow_direct_identifiers=(
                allow_direct_identifiers
            ),
            allow_free_text=allow_free_text,
            allow_cost_data=allow_cost_data,
            minimum_group_size=minimum_group_size,
        ),
        policy_version="access_policy_v1",
        scope_source="server_test_fixture",
    )


def ordinary_binding() -> ResultFieldBinding:
    return ResultFieldBinding(
        output_field="category",
        source_columns=frozenset({
            "dim_product.category",
        }),
        category=SensitiveDataCategory.ORDINARY,
    )


def pseudonymous_binding(
    *,
    output_field: str = "customer_code",
    namespace: str = "customer",
) -> ResultFieldBinding:
    return ResultFieldBinding(
        output_field=output_field,
        source_columns=frozenset({
            "dim_customer.customer_code",
        }),
        category=(
            SensitiveDataCategory
            .PSEUDONYMOUS_IDENTIFIER
        ),
        token_namespace=namespace,
    )


def test_v2_sensitive_catalog_classification() -> None:
    assert_equal(
        classify_v2_source_column(
            "dim_customer.customer_code"
        ),
        SensitiveDataCategory.PSEUDONYMOUS_IDENTIFIER,
        "customer_code must be pseudonymous.",
    )

    assert_equal(
        classify_v2_source_column(
            "fact_reviews.review_text"
        ),
        SensitiveDataCategory.FREE_TEXT,
        "review_text must be free text.",
    )

    assert_equal(
        classify_v2_source_column(
            "fact_order_items.item_cost_amount"
        ),
        SensitiveDataCategory.BUSINESS_CONFIDENTIAL,
        "item_cost_amount must be confidential.",
    )

    assert_equal(
        classify_v2_source_column(
            "dim_product.category"
        ),
        SensitiveDataCategory.ORDINARY,
        "Unlisted ordinary fields should remain ordinary.",
    )


def test_raw_binding_uses_catalog() -> None:
    binding = build_raw_field_binding(
        output_field="customer_code",
        source_column="dim_customer.customer_code",
        token_namespace="customer",
    )

    assert_equal(
        binding.category,
        SensitiveDataCategory.PSEUDONYMOUS_IDENTIFIER,
        "Raw binding must use catalog classification.",
    )


def test_contract_is_immutable() -> None:
    contract = ResultProtectionContract(
        field_bindings=(ordinary_binding(),),
        result_shape=ResultShape.AGGREGATE,
    )

    try:
        contract.policy_version = "changed"
    except ValidationError:
        return

    raise AssertionError(
        "ResultProtectionContract must be immutable."
    )


def test_ordinary_result_passes_unchanged() -> None:
    contract = ResultProtectionContract(
        field_bindings=(ordinary_binding(),),
        result_shape=ResultShape.AGGREGATE,
    )

    result = protect_result_rows(
        context=build_context(),
        rows=[{"category": "精华"}],
        contract=contract,
    )

    assert_equal(
        result.success,
        True,
        "Ordinary result should pass.",
    )

    assert_equal(
        result.rows,
        ({"category": "精华"},),
        "Ordinary value should remain unchanged.",
    )

    assert_equal(
        result.applied_protections[0].action,
        ProtectionAction.ALLOW,
        "Ordinary field should use allow action.",
    )


def test_pseudonymous_identifier_is_tokenized() -> None:
    contract = ResultProtectionContract(
        field_bindings=(pseudonymous_binding(),),
        result_shape=ResultShape.DETAIL,
    )

    result = protect_result_rows(
        context=build_context(),
        rows=[{"customer_code": "CUS-000001"}],
        contract=contract,
        tokenization_secret=TOKEN_SECRET,
    )

    token = result.rows[0]["customer_code"]

    assert_true(
        token.startswith("TOK_"),
        "Token must use the stable TOK_ prefix.",
    )

    assert_true(
        "CUS-000001" not in token,
        "Token must not expose the original identifier.",
    )


def test_tokenization_is_deterministic() -> None:
    contract = ResultProtectionContract(
        field_bindings=(pseudonymous_binding(),),
        result_shape=ResultShape.DETAIL,
    )

    first = protect_result_rows(
        context=build_context(),
        rows=[{"customer_code": "CUS-000001"}],
        contract=contract,
        tokenization_secret=TOKEN_SECRET,
    )

    second = protect_result_rows(
        context=build_context(),
        rows=[{"customer_code": "CUS-000001"}],
        contract=contract,
        tokenization_secret=TOKEN_SECRET,
    )

    assert_equal(
        first.rows,
        second.rows,
        "Same namespace, secret and value need stable tokens.",
    )


def test_token_namespace_prevents_cross_domain_linkage() -> None:
    customer_contract = ResultProtectionContract(
        field_bindings=(
            pseudonymous_binding(namespace="customer"),
        ),
        result_shape=ResultShape.DETAIL,
    )

    order_contract = ResultProtectionContract(
        field_bindings=(
            pseudonymous_binding(namespace="order"),
        ),
        result_shape=ResultShape.DETAIL,
    )

    customer_result = protect_result_rows(
        context=build_context(),
        rows=[{"customer_code": "10001"}],
        contract=customer_contract,
        tokenization_secret=TOKEN_SECRET,
    )

    order_result = protect_result_rows(
        context=build_context(),
        rows=[{"customer_code": "10001"}],
        contract=order_contract,
        tokenization_secret=TOKEN_SECRET,
    )

    assert_true(
        customer_result.rows != order_result.rows,
        "Different namespaces must produce different tokens.",
    )


def test_missing_tokenization_secret_fails_closed() -> None:
    contract = ResultProtectionContract(
        field_bindings=(pseudonymous_binding(),),
        result_shape=ResultShape.DETAIL,
    )

    result = protect_result_rows(
        context=build_context(),
        rows=[{"customer_code": "CUS-000001"}],
        contract=contract,
    )

    assert_equal(
        result.success,
        False,
        "Missing secret must fail.",
    )

    assert_equal(
        result.reason_code,
        ProtectionReason.MISSING_TOKENIZATION_SECRET,
        "Missing secret must have a stable reason.",
    )

    assert_equal(
        result.rows,
        (),
        "Failure must not return raw or partial rows.",
    )

    assert_equal(
        result.retryable,
        False,
        "Masking failure must not enter SQL Repair.",
    )


def test_free_text_is_denied_by_default() -> None:
    contract = ResultProtectionContract(
        field_bindings=(
            ResultFieldBinding(
                output_field="review_text",
                source_columns=frozenset({
                    "fact_reviews.review_text",
                }),
                category=SensitiveDataCategory.FREE_TEXT,
            ),
        ),
        result_shape=ResultShape.DETAIL,
    )

    result = protect_result_rows(
        context=build_context(),
        rows=[{"review_text": "联系电话 13800000000"}],
        contract=contract,
    )

    assert_equal(
        result.reason_code,
        ProtectionReason.FREE_TEXT_NOT_ALLOWED,
        "Free text should be denied by default.",
    )

    assert_equal(
        result.rows,
        (),
        "Denied free text must not leak.",
    )


def test_free_text_can_be_explicitly_allowed() -> None:
    contract = ResultProtectionContract(
        field_bindings=(
            ResultFieldBinding(
                output_field="review_text",
                source_columns=frozenset({
                    "fact_reviews.review_text",
                }),
                category=SensitiveDataCategory.FREE_TEXT,
            ),
        ),
        result_shape=ResultShape.DETAIL,
    )

    result = protect_result_rows(
        context=build_context(allow_free_text=True),
        rows=[{"review_text": "受控模拟评价"}],
        contract=contract,
    )

    assert_equal(
        result.success,
        True,
        "Trusted policy may allow free text.",
    )


def test_cost_data_is_denied_by_default() -> None:
    contract = ResultProtectionContract(
        field_bindings=(
            ResultFieldBinding(
                output_field="item_cost_amount",
                source_columns=frozenset({
                    "fact_order_items.item_cost_amount",
                }),
                category=(
                    SensitiveDataCategory
                    .BUSINESS_CONFIDENTIAL
                ),
            ),
        ),
        result_shape=ResultShape.DETAIL,
    )

    result = protect_result_rows(
        context=build_context(),
        rows=[{"item_cost_amount": 88.50}],
        contract=contract,
    )

    assert_equal(
        result.reason_code,
        ProtectionReason.COST_DATA_NOT_ALLOWED,
        "Cost data should be denied by default.",
    )


def test_cost_data_can_be_explicitly_allowed() -> None:
    contract = ResultProtectionContract(
        field_bindings=(
            ResultFieldBinding(
                output_field="item_cost_amount",
                source_columns=frozenset({
                    "fact_order_items.item_cost_amount",
                }),
                category=(
                    SensitiveDataCategory
                    .BUSINESS_CONFIDENTIAL
                ),
            ),
        ),
        result_shape=ResultShape.DETAIL,
    )

    result = protect_result_rows(
        context=build_context(allow_cost_data=True),
        rows=[{"item_cost_amount": 88.50}],
        contract=contract,
    )

    assert_equal(
        result.success,
        True,
        "Trusted policy may allow cost data.",
    )


def test_direct_identifier_is_denied_by_default() -> None:
    contract = ResultProtectionContract(
        field_bindings=(
            ResultFieldBinding(
                output_field="email",
                source_columns=frozenset({
                    "dim_customer.email",
                }),
                category=(
                    SensitiveDataCategory.DIRECT_IDENTIFIER
                ),
            ),
        ),
        result_shape=ResultShape.DETAIL,
    )

    result = protect_result_rows(
        context=build_context(),
        rows=[{"email": "user@example.com"}],
        contract=contract,
    )

    assert_equal(
        result.reason_code,
        (
            ProtectionReason
            .DIRECT_IDENTIFIER_NOT_ALLOWED
        ),
        "Direct identifier should be denied by default.",
    )


def test_direct_identifier_can_be_explicitly_allowed() -> None:
    contract = ResultProtectionContract(
        field_bindings=(
            ResultFieldBinding(
                output_field="email",
                source_columns=frozenset({
                    "dim_customer.email",
                }),
                category=(
                    SensitiveDataCategory.DIRECT_IDENTIFIER
                ),
            ),
        ),
        result_shape=ResultShape.DETAIL,
    )

    result = protect_result_rows(
        context=build_context(
            allow_direct_identifiers=True
        ),
        rows=[{"email": "user@example.com"}],
        contract=contract,
    )

    assert_equal(
        result.success,
        True,
        "Trusted policy may allow direct identifiers.",
    )


def test_unexpected_result_field_fails_closed() -> None:
    contract = ResultProtectionContract(
        field_bindings=(ordinary_binding(),),
        result_shape=ResultShape.AGGREGATE,
    )

    result = protect_result_rows(
        context=build_context(),
        rows=[{
            "category": "精华",
            "customer_code": "CUS-000001",
        }],
        contract=contract,
        tokenization_secret=TOKEN_SECRET,
    )

    assert_equal(
        result.reason_code,
        ProtectionReason.INVALID_RESULT_SHAPE,
        "Extra SQL output fields must fail closed.",
    )

    assert_equal(
        result.rows,
        (),
        "Unexpected field failure cannot return partial rows.",
    )


def test_missing_result_field_fails_closed() -> None:
    contract = ResultProtectionContract(
        field_bindings=(ordinary_binding(),),
        result_shape=ResultShape.AGGREGATE,
    )

    result = protect_result_rows(
        context=build_context(),
        rows=[{}],
        contract=contract,
    )

    assert_equal(
        result.reason_code,
        ProtectionReason.INVALID_RESULT_SHAPE,
        "Missing expected fields must fail closed.",
    )


def test_small_group_rejects_entire_result() -> None:
    contract = ResultProtectionContract(
        field_bindings=(ordinary_binding(),),
        result_shape=ResultShape.AGGREGATE,
        minimum_group_size_required=True,
        group_size_field="__group_size",
    )

    result = protect_result_rows(
        context=build_context(minimum_group_size=5),
        rows=[
            {
                "category": "精华",
                "__group_size": 8,
            },
            {
                "category": "防晒",
                "__group_size": 3,
            },
        ],
        contract=contract,
    )

    assert_equal(
        result.reason_code,
        ProtectionReason.MINIMUM_GROUP_SIZE_VIOLATION,
        "A small group must reject the entire result.",
    )

    assert_equal(
        result.minimum_observed_group_size,
        3,
        "Minimum observed group size should be recorded.",
    )

    assert_equal(
        result.rows,
        (),
        "Partial ranking rows must not be returned.",
    )


def test_invalid_group_size_cannot_prove_safety() -> None:
    contract = ResultProtectionContract(
        field_bindings=(ordinary_binding(),),
        result_shape=ResultShape.AGGREGATE,
        minimum_group_size_required=True,
        group_size_field="__group_size",
    )

    result = protect_result_rows(
        context=build_context(),
        rows=[{
            "category": "精华",
            "__group_size": "5",
        }],
        contract=contract,
    )

    assert_equal(
        result.reason_code,
        (
            ProtectionReason
            .MINIMUM_GROUP_SIZE_NOT_PROVEN
        ),
        "String group size must not be trusted.",
    )


def test_group_size_control_field_is_removed() -> None:
    contract = ResultProtectionContract(
        field_bindings=(ordinary_binding(),),
        result_shape=ResultShape.AGGREGATE,
        minimum_group_size_required=True,
        group_size_field="__group_size",
    )

    result = protect_result_rows(
        context=build_context(minimum_group_size=5),
        rows=[{
            "category": "精华",
            "__group_size": 8,
        }],
        contract=contract,
    )

    assert_equal(
        result.success,
        True,
        "Group at threshold or above should pass.",
    )

    assert_equal(
        result.rows,
        ({"category": "精华"},),
        "Hidden group size field must not leave governance.",
    )


def test_input_rows_are_not_mutated() -> None:
    raw_rows = [{
        "customer_code": "CUS-000001",
    }]

    contract = ResultProtectionContract(
        field_bindings=(pseudonymous_binding(),),
        result_shape=ResultShape.DETAIL,
    )

    protect_result_rows(
        context=build_context(),
        rows=raw_rows,
        contract=contract,
        tokenization_secret=TOKEN_SECRET,
    )

    assert_equal(
        raw_rows,
        [{"customer_code": "CUS-000001"}],
        "Protection must not mutate raw input rows.",
    )


def test_contract_fingerprint_is_stable_and_sensitive() -> None:
    first = ResultProtectionContract(
        field_bindings=(ordinary_binding(),),
        result_shape=ResultShape.AGGREGATE,
    )

    same = ResultProtectionContract(
        field_bindings=(ordinary_binding(),),
        result_shape=ResultShape.AGGREGATE,
    )

    changed = ResultProtectionContract(
        field_bindings=(pseudonymous_binding(),),
        result_shape=ResultShape.DETAIL,
    )

    assert_equal(
        build_contract_fingerprint(first),
        build_contract_fingerprint(same),
        "Equivalent contracts need stable fingerprints.",
    )

    assert_true(
        build_contract_fingerprint(first)
        != build_contract_fingerprint(changed),
        "Contract changes must change the fingerprint.",
    )


def run_tests() -> None:
    tests = [
        test_v2_sensitive_catalog_classification,
        test_raw_binding_uses_catalog,
        test_contract_is_immutable,
        test_ordinary_result_passes_unchanged,
        test_pseudonymous_identifier_is_tokenized,
        test_tokenization_is_deterministic,
        test_token_namespace_prevents_cross_domain_linkage,
        test_missing_tokenization_secret_fails_closed,
        test_free_text_is_denied_by_default,
        test_free_text_can_be_explicitly_allowed,
        test_cost_data_is_denied_by_default,
        test_cost_data_can_be_explicitly_allowed,
        test_direct_identifier_is_denied_by_default,
        test_direct_identifier_can_be_explicitly_allowed,
        test_unexpected_result_field_fails_closed,
        test_missing_result_field_fails_closed,
        test_small_group_rejects_entire_result,
        test_invalid_group_size_cannot_prove_safety,
        test_group_size_control_field_is_removed,
        test_input_rows_are_not_mutated,
        test_contract_fingerprint_is_stable_and_sensitive,
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
    print("Sensitive Data Protection Test Summary")
    print(f"Total: {len(tests)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    run_tests()
