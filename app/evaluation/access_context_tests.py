from pydantic import ValidationError

from app.governance.access_context import (
    AccessContext,
    AccessRole,
    OperationMode,
    SensitiveDataPolicy,
)


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(
            f"{message}\nExpected: {expected}\nActual: {actual}"
        )


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def build_valid_context(**overrides) -> AccessContext:
    """
    建立一份默认合法的 Access Context。

    单项失败测试只覆盖需要修改的字段，
    避免每条测试重复编写完整 Context。
    """
    data = {
        "request_id": "req-day67-001",
        "actor_id": "analyst-001",
        "role": AccessRole.SCOPED_ANALYST,
        "dataset_name": "beauty_bi_v2",
        "target_schema": "beauty_bi_v2",
        "operation_mode": OperationMode.OBSERVE_ADVISE,
        "allowed_metrics": frozenset(
            {
                "channel_sales_amount",
                "order_count",
            }
        ),
        "allowed_tables": frozenset(
            {
                "fact_orders",
                "fact_order_items",
                "dim_region",
            }
        ),
        "allowed_columns": frozenset(
            {
                "fact_orders.order_id",
                "fact_orders.shipping_region_id",
                "fact_order_items.item_paid_amount",
            }
        ),
        "denied_columns": frozenset(
            {
                "dim_customer.customer_code",
                "dim_membership_account.member_code",
            }
        ),
        "allowed_region_codes": frozenset(
            {
                "EAST_CHINA",
            }
        ),
        "allowed_channel_codes": frozenset(
            {
                "TMALL",
                "JD",
            }
        ),
        "sensitive_data_policy": SensitiveDataPolicy(),
        "policy_version": "access_policy_v1",
        "scope_source": "server_policy",
    }

    data.update(overrides)

    return AccessContext(**data)


def assert_validation_failed(
    overrides: dict,
    message: str,
) -> None:
    """
    验证传入字段会导致 Pydantic 合同校验失败。
    """
    try:
        build_valid_context(**overrides)
    except ValidationError:
        return

    raise AssertionError(message)


def test_valid_scoped_analyst_context() -> None:
    """
    合法的 scoped_analyst Context 应成功创建。
    """
    context = build_valid_context()

    assert_equal(
        context.role,
        AccessRole.SCOPED_ANALYST,
        "合法 Context 应保留 scoped_analyst 角色。",
    )

    assert_equal(
        context.target_schema,
        "beauty_bi_v2",
        "合法 Context 应绑定 beauty_bi_v2 Schema。",
    )

    assert_true(
        "EAST_CHINA" in context.allowed_region_codes,
        "合法 Context 应保留地区 Scope。",
    )


def test_public_schema_is_rejected() -> None:
    """
    V2 Access Context 不得授权访问 public Schema。
    """
    assert_validation_failed(
        {
            "target_schema": "public",
        },
        "target_schema=public 必须被拒绝。",
    )


def test_wrong_dataset_is_rejected() -> None:
    """
    当前 Access Context 只能绑定 Beauty BI V2。
    """
    assert_validation_failed(
        {
            "dataset_name": "beauty_bi_v1",
        },
        "非 beauty_bi_v2 Dataset 必须被拒绝。",
    )


def test_allowed_and_denied_columns_cannot_overlap() -> None:
    """
    同一个字段不能同时被允许和禁止。
    """
    column = "dim_customer.customer_code"

    assert_validation_failed(
        {
            "allowed_columns": frozenset(
                {
                    column,
                }
            ),
            "denied_columns": frozenset(
                {
                    column,
                }
            ),
        },
        "allowed_columns 与 denied_columns 重叠时必须失败。",
    )


def test_context_is_immutable() -> None:
    """
    Access Context 创建后，角色和 Scope 不允许被修改。
    """
    context = build_valid_context()

    try:
        context.role = AccessRole.EXECUTIVE_ANALYST
    except ValidationError:
        pass
    else:
        raise AssertionError(
            "AccessContext 创建后不允许修改 role。"
        )

    try:
        context.allowed_region_codes = frozenset(
            {
                "SOUTH_CHINA",
            }
        )
    except ValidationError:
        pass
    else:
        raise AssertionError(
            "AccessContext 创建后不允许替换地区 Scope。"
        )


def run_tests() -> None:
    tests = [
        test_valid_scoped_analyst_context,
        test_public_schema_is_rejected,
        test_wrong_dataset_is_rejected,
        test_allowed_and_denied_columns_cannot_overlap,
        test_context_is_immutable,
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
    print("Access Context Test Summary")
    print(f"Total: {len(tests)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    run_tests()