from app.governance.access_context import (
    AccessContext,
    AccessRole,
    OperationMode,
    SensitiveDataPolicy,
)
from app.governance.authorization import (
    AuthorizationReason,
    authorize_columns,
    authorize_metric,
    authorize_resources,
    authorize_tables,
)


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(
            f"{message}\nExpected: {expected}\nActual: {actual}"
        )


def build_context(**overrides) -> AccessContext:
    data = {
        "request_id": "req-day68-001",
        "actor_id": "analyst-001",
        "role": AccessRole.SCOPED_ANALYST,
        "dataset_name": "beauty_bi_v2",
        "target_schema": "beauty_bi_v2",
        "operation_mode": OperationMode.OBSERVE_ADVISE,
        "allowed_metrics": frozenset(
            {
                "gmv",
                "order_count",
                "refund_rate",
            }
        ),
        "allowed_tables": frozenset(
            {
                "fact_orders",
                "fact_order_items",
                "fact_refunds",
                "fact_reviews",
            }
        ),
        "allowed_columns": frozenset(
            {
                "fact_orders.order_paid_amount",
                "fact_orders.paid_at",
                "fact_order_items.item_paid_amount",
                "fact_order_items.quantity",
                "fact_refunds.refund_amount",
                "fact_reviews.rating",
            }
        ),
        "denied_columns": frozenset(
            {
                "fact_order_items.item_cost_amount",
                "fact_reviews.review_text",
            }
        ),
        "allowed_region_codes": frozenset({"EAST"}),
        "allowed_channel_codes": frozenset({"TMALL"}),
        "sensitive_data_policy": SensitiveDataPolicy(),
        "policy_version": "governance_v1",
        "scope_source": "test_fixture",
    }

    data.update(overrides)
    return AccessContext(**data)


def test_allowed_metric_passes() -> None:
    decision = authorize_metric(build_context(), "gmv")

    assert_equal(decision.allowed, True, "授权指标应该通过。")
    assert_equal(
        decision.reason_code,
        AuthorizationReason.ALLOWED,
        "通过的指标应该返回 allowed reason。",
    )


def test_denied_metric_is_non_retryable() -> None:
    decision = authorize_metric(
        build_context(),
        "gross_margin",
    )

    assert_equal(decision.allowed, False, "未授权指标应该被拒绝。")
    assert_equal(
        decision.reason_code,
        AuthorizationReason.METRIC_NOT_ALLOWED,
        "应该返回 metric_not_allowed。",
    )
    assert_equal(
        decision.denied_metrics,
        frozenset({"gross_margin"}),
        "应该返回被拒绝的指标。",
    )
    assert_equal(
        decision.retryable,
        False,
        "Authorization Failure 不得进入 Repair。",
    )


def test_allowed_tables_and_columns_pass() -> None:
    decision = authorize_resources(
        build_context(),
        required_tables={
            "fact_orders",
            "fact_order_items",
        },
        required_columns={
            "fact_orders.order_paid_amount",
            "fact_order_items.item_paid_amount",
        },
    )

    assert_equal(
        decision.allowed,
        True,
        "全部资源均授权时应该通过。",
    )


def test_missing_table_is_denied() -> None:
    decision = authorize_tables(
        build_context(),
        {
            "fact_orders",
            "bridge_customer_membership",
        },
    )

    assert_equal(
        decision.allowed,
        False,
        "存在未授权表时应该拒绝。",
    )
    assert_equal(
        decision.denied_tables,
        frozenset({"bridge_customer_membership"}),
        "应该返回完整的未授权表集合。",
    )


def test_missing_column_is_denied() -> None:
    decision = authorize_columns(
        build_context(),
        {
            "fact_orders.order_paid_amount",
            "fact_orders.customer_id",
        },
    )

    assert_equal(
        decision.allowed,
        False,
        "存在未授权列时应该拒绝。",
    )
    assert_equal(
        decision.reason_code,
        AuthorizationReason.COLUMN_NOT_ALLOWED,
        "应该返回 column_not_allowed。",
    )
    assert_equal(
        decision.denied_columns,
        frozenset({"fact_orders.customer_id"}),
        "应该返回未授权列。",
    )


def test_explicitly_denied_column_is_denied() -> None:
    decision = authorize_columns(
        build_context(),
        {
            "fact_order_items.item_cost_amount",
        },
    )

    assert_equal(
        decision.allowed,
        False,
        "显式禁止列必须被拒绝。",
    )
    assert_equal(
        decision.reason_code,
        AuthorizationReason.EXPLICITLY_DENIED_COLUMN,
        "显式禁止列应该优先返回对应 reason。",
    )
    assert_equal(
        decision.explicitly_denied_columns,
        frozenset(
            {"fact_order_items.item_cost_amount"}
        ),
        "应该返回显式禁止列。",
    )


def test_allowed_table_does_not_allow_all_columns() -> None:
    decision = authorize_resources(
        build_context(),
        required_tables={"fact_order_items"},
        required_columns={
            "fact_order_items.unit_cost_at_order",
        },
    )

    assert_equal(
        decision.allowed,
        False,
        "允许表不应隐式开放该表所有列。",
    )
    assert_equal(
        decision.reason_code,
        AuthorizationReason.COLUMN_NOT_ALLOWED,
        "未授权成本列应该返回 column_not_allowed。",
    )
    assert_equal(
        decision.denied_columns,
        frozenset(
            {"fact_order_items.unit_cost_at_order"}
        ),
        "应该返回未授权成本列。",
    )


def test_multiple_violations_are_all_returned() -> None:
    decision = authorize_resources(
        build_context(),
        required_tables={
            "fact_orders",
            "fact_order_items",
            "fact_reviews",
            "bridge_customer_membership",
            "dim_customer",
        },
        required_columns={
            "fact_orders.order_paid_amount",
            "fact_order_items.item_cost_amount",
            "fact_reviews.review_text",
            "dim_customer.customer_code",
        },
    )

    assert_equal(
        decision.allowed,
        False,
        "多个越权资源存在时应该拒绝。",
    )
    assert_equal(
        decision.denied_tables,
        frozenset(
            {
                "bridge_customer_membership",
                "dim_customer",
            }
        ),
        "应该一次返回全部未授权表。",
    )
    assert_equal(
        decision.explicitly_denied_columns,
        frozenset(
            {
                "fact_order_items.item_cost_amount",
                "fact_reviews.review_text",
            }
        ),
        "应该一次返回全部显式禁止列。",
    )
    assert_equal(
        decision.denied_columns,
        frozenset({"dim_customer.customer_code"}),
        "应该同时返回其他未授权列。",
    )
    assert_equal(
        decision.retryable,
        False,
        "多个 Authorization Failure 仍然不可 Repair。",
    )


def test_column_table_must_be_declared() -> None:
    decision = authorize_resources(
        build_context(),
        required_tables={"fact_orders"},
        required_columns={
            "fact_orders.order_paid_amount",
            "fact_reviews.rating",
        },
    )

    assert_equal(
        decision.allowed,
        False,
        "列所属表未声明时必须拒绝。",
    )
    assert_equal(
        decision.reason_code,
        AuthorizationReason.INVALID_RESOURCE_DECLARATION,
        "资源声明不一致时应返回 invalid_resource_declaration。",
    )
    assert_equal(
        decision.denied_tables,
        frozenset({"fact_reviews"}),
        "应该指出未声明的列来源表。",
    )


def test_column_scope_also_checks_table_scope() -> None:
    context = build_context(
        allowed_tables=frozenset({"fact_orders"}),
        allowed_columns=frozenset(
            {
                "fact_orders.order_paid_amount",
                "dim_customer.customer_code",
            }
        ),
    )

    decision = authorize_columns(
        context,
        {"dim_customer.customer_code"},
    )

    assert_equal(
        decision.allowed,
        False,
        "列即使误配为 allowed，其来源表未授权时仍必须拒绝。",
    )
    assert_equal(
        decision.reason_code,
        AuthorizationReason.TABLE_NOT_ALLOWED,
        "列来源表未授权时应返回 table_not_allowed。",
    )
    assert_equal(
        decision.denied_tables,
        frozenset({"dim_customer"}),
        "应该返回未授权的列来源表。",
    )


def run_tests() -> None:
    tests = [
        test_allowed_metric_passes,
        test_denied_metric_is_non_retryable,
        test_allowed_tables_and_columns_pass,
        test_missing_table_is_denied,
        test_missing_column_is_denied,
        test_explicitly_denied_column_is_denied,
        test_allowed_table_does_not_allow_all_columns,
        test_multiple_violations_are_all_returned,
        test_column_table_must_be_declared,
        test_column_scope_also_checks_table_scope,
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
    print("Resource Scope Test Summary")
    print(f"Total: {len(tests)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    run_tests()
