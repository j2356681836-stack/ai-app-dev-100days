from app.governance.access_context import (
    AccessContext,
    AccessRole,
    OperationMode,
    SensitiveDataPolicy,
)
from app.governance.row_scope import (
    RowScopeReason,
    ScopeDimension,
    plan_row_scope,
)


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(
            f"{message}\nExpected: {expected}\nActual: {actual}"
        )


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def build_context(**overrides) -> AccessContext:
    data = {
        "request_id": "req-day69-001",
        "actor_id": "analyst-001",
        "role": AccessRole.SCOPED_ANALYST,
        "dataset_name": "beauty_bi_v2",
        "target_schema": "beauty_bi_v2",
        "operation_mode": OperationMode.OBSERVE_ADVISE,
        "allowed_metrics": frozenset({"gmv", "refund_rate"}),
        "allowed_tables": frozenset(
            {
                "fact_orders",
                "fact_order_items",
                "fact_refunds",
                "fact_reviews",
                "fact_marketing_spend",
                "dim_region",
                "dim_channel",
            }
        ),
        "allowed_columns": frozenset(
            {
                "fact_orders.shipping_region_id",
                "fact_orders.channel_id",
                "fact_orders.order_paid_amount",
                "fact_order_items.order_id",
                "fact_refunds.order_item_id",
                "fact_reviews.order_item_id",
                "fact_marketing_spend.channel_id",
                "dim_region.region_id",
                "dim_region.region_code",
                "dim_channel.channel_id",
                "dim_channel.channel_code",
            }
        ),
        "denied_columns": frozenset(),
        "allowed_region_codes": frozenset(
            {"EAST", "SOUTH"}
        ),
        "allowed_channel_codes": frozenset(
            {"TMALL", "JD"}
        ),
        "sensitive_data_policy": SensitiveDataPolicy(),
        "policy_version": "governance_v1",
        "scope_source": "test_fixture",
    }

    data.update(overrides)
    return AccessContext(**data)


def find_requirement(
    decision,
    dimension: ScopeDimension,
    source_table: str,
):
    assert_true(
        decision.plan is not None,
        "通过的决策必须包含 Row Scope Plan。",
    )

    matches = [
        requirement
        for requirement in decision.plan.requirements
        if (
            requirement.dimension == dimension
            and requirement.source_table == source_table
        )
    ]

    assert_equal(
        len(matches),
        1,
        "应该存在且仅存在一个匹配的 Scope Requirement。",
    )

    return matches[0]


def test_order_region_uses_shipping_region() -> None:
    decision = plan_row_scope(
        build_context(),
        source_tables={"fact_orders"},
        required_dimensions={ScopeDimension.REGION},
    )

    assert_equal(
        decision.allowed,
        True,
        "订单 Region Scope 应该能够生成。",
    )

    requirement = find_requirement(
        decision,
        ScopeDimension.REGION,
        "fact_orders",
    )

    assert_equal(
        requirement.anchor_table,
        "fact_orders",
        "订单 Region Scope 应锚定 fact_orders。",
    )

    assert_equal(
        requirement.anchor_column,
        "shipping_region_id",
        "订单 Region Scope 必须使用 shipping_region_id。",
    )

    assert_true(
        "home_region_id" not in str(requirement),
        "订单 Region Scope 不得使用客户常住地区。",
    )


def test_order_channel_uses_direct_anchor() -> None:
    decision = plan_row_scope(
        build_context(),
        source_tables={"fact_orders"},
        required_dimensions={ScopeDimension.CHANNEL},
    )

    requirement = find_requirement(
        decision,
        ScopeDimension.CHANNEL,
        "fact_orders",
    )

    assert_equal(
        requirement.anchor_column,
        "channel_id",
        "订单 Channel Scope 应使用 fact_orders.channel_id。",
    )

    assert_equal(
        requirement.join_path,
        (),
        "fact_orders 已有直接渠道锚点，不需要继承 Join。",
    )


def test_order_items_inherit_both_scopes() -> None:
    decision = plan_row_scope(
        build_context(),
        source_tables={"fact_order_items"},
    )

    assert_equal(
        decision.allowed,
        True,
        "订单明细应能继承 Region 和 Channel Scope。",
    )

    for dimension in (
        ScopeDimension.REGION,
        ScopeDimension.CHANNEL,
    ):
        requirement = find_requirement(
            decision,
            dimension,
            "fact_order_items",
        )

        assert_equal(
            len(requirement.join_path),
            1,
            "订单明细应通过一跳关联 fact_orders。",
        )

        join = requirement.join_path[0]

        assert_equal(
            (
                join.left_table,
                join.left_column,
                join.right_table,
                join.right_column,
            ),
            (
                "fact_order_items",
                "order_id",
                "fact_orders",
                "order_id",
            ),
            "订单明细的 Scope 继承路径不正确。",
        )


def test_refunds_inherit_through_items_and_orders() -> None:
    decision = plan_row_scope(
        build_context(),
        source_tables={"fact_refunds"},
    )

    assert_equal(
        decision.allowed,
        True,
        "退款事实应能继承 Region 和 Channel Scope。",
    )

    requirement = find_requirement(
        decision,
        ScopeDimension.CHANNEL,
        "fact_refunds",
    )

    assert_equal(
        len(requirement.join_path),
        2,
        "退款应通过订单明细再关联订单。",
    )

    assert_equal(
        requirement.join_path[0].left_table,
        "fact_refunds",
        "退款 Scope Path 应从 fact_refunds 开始。",
    )

    assert_equal(
        requirement.join_path[-1].right_table,
        "fact_orders",
        "退款 Scope Path 应最终到达 fact_orders。",
    )


def test_reviews_inherit_through_items_and_orders() -> None:
    decision = plan_row_scope(
        build_context(),
        source_tables={"fact_reviews"},
    )

    requirement = find_requirement(
        decision,
        ScopeDimension.REGION,
        "fact_reviews",
    )

    assert_equal(
        len(requirement.join_path),
        2,
        "评价应通过订单明细再关联订单。",
    )

    assert_equal(
        requirement.anchor_column,
        "shipping_region_id",
        "评价 Region Scope 最终应锚定订单配送地区。",
    )


def test_marketing_spend_channel_is_direct() -> None:
    decision = plan_row_scope(
        build_context(),
        source_tables={"fact_marketing_spend"},
        required_dimensions={ScopeDimension.CHANNEL},
    )

    assert_equal(
        decision.allowed,
        True,
        "营销费用应支持直接 Channel Scope。",
    )

    requirement = find_requirement(
        decision,
        ScopeDimension.CHANNEL,
        "fact_marketing_spend",
    )

    assert_equal(
        requirement.anchor_column,
        "channel_id",
        "营销费用 Channel Scope 应使用 channel_id。",
    )

    assert_equal(
        requirement.join_path,
        (),
        "营销费用已有直接渠道锚点。",
    )


def test_marketing_spend_region_fails_closed() -> None:
    decision = plan_row_scope(
        build_context(),
        source_tables={"fact_marketing_spend"},
        required_dimensions={ScopeDimension.REGION},
    )

    assert_equal(
        decision.allowed,
        False,
        "营销费用没有 Region 锚点时必须拒绝。",
    )

    assert_equal(
        decision.reason_code,
        RowScopeReason.UNSUPPORTED_SCOPE_PATH,
        "应返回 unsupported_scope_path。",
    )

    assert_equal(
        decision.unsupported_scope_paths,
        frozenset({"region:fact_marketing_spend"}),
        "应该明确返回缺失的 Region Scope Path。",
    )

    assert_equal(
        decision.retryable,
        False,
        "Row Scope Failure 不得进入 SQL Repair。",
    )


def test_roi_like_sources_fail_under_region_scope() -> None:
    decision = plan_row_scope(
        build_context(),
        source_tables={
            "fact_orders",
            "fact_marketing_spend",
        },
        required_dimensions={
            ScopeDimension.REGION,
            ScopeDimension.CHANNEL,
        },
    )

    assert_equal(
        decision.allowed,
        False,
        "地区受限时不能混用地区订单与全局营销费用。",
    )

    assert_true(
        "region:fact_marketing_spend"
        in decision.unsupported_scope_paths,
        "ROI/CAC 类来源应指出营销费用缺少地区路径。",
    )


def test_dim_customer_cannot_replace_order_region() -> None:
    decision = plan_row_scope(
        build_context(),
        source_tables={"dim_customer"},
        required_dimensions={ScopeDimension.REGION},
    )

    assert_equal(
        decision.allowed,
        False,
        "客户画像维度不能替代订单经营 Region Scope。",
    )

    assert_equal(
        decision.reason_code,
        RowScopeReason.INVALID_SOURCE_TABLE,
        "维度表不能作为当前 Row Scope 分析事实来源。",
    )

    assert_equal(
        decision.invalid_source_tables,
        frozenset({"dim_customer"}),
        "应该返回不合法的 source table。",
    )


def test_empty_region_scope_means_no_access() -> None:
    context = build_context(
        allowed_region_codes=frozenset()
    )

    decision = plan_row_scope(
        context,
        source_tables={"fact_orders"},
        required_dimensions={ScopeDimension.REGION},
    )

    assert_equal(
        decision.allowed,
        False,
        "空 Region Scope 不得解释为全量地区。",
    )

    assert_equal(
        decision.reason_code,
        RowScopeReason.EMPTY_SCOPE,
        "空 Region Scope 应返回 empty_scope。",
    )

    assert_equal(
        decision.empty_scope_dimensions,
        frozenset({ScopeDimension.REGION}),
        "应该指出缺少 Region 权限。",
    )


def test_empty_channel_scope_means_no_access() -> None:
    context = build_context(
        allowed_channel_codes=frozenset()
    )

    decision = plan_row_scope(
        context,
        source_tables={"fact_orders"},
        required_dimensions={ScopeDimension.CHANNEL},
    )

    assert_equal(
        decision.allowed,
        False,
        "空 Channel Scope 不得解释为全量渠道。",
    )

    assert_equal(
        decision.empty_scope_dimensions,
        frozenset({ScopeDimension.CHANNEL}),
        "应该指出缺少 Channel 权限。",
    )


def test_empty_required_dimensions_is_rejected() -> None:
    decision = plan_row_scope(
        build_context(),
        source_tables={"fact_orders"},
        required_dimensions=frozenset(),
    )

    assert_equal(
        decision.allowed,
        False,
        "调用方不得通过空 dimensions 绕过 Row Scope。",
    )

    assert_equal(
        decision.reason_code,
        RowScopeReason.INVALID_SCOPE_DECLARATION,
        "空 dimensions 应返回 invalid_scope_declaration。",
    )


def test_plan_fingerprint_is_stable_and_scope_sensitive() -> None:
    first = plan_row_scope(
        build_context(),
        source_tables={"fact_orders"},
    )

    second = plan_row_scope(
        build_context(),
        source_tables={"fact_orders"},
    )

    changed = plan_row_scope(
        build_context(
            allowed_region_codes=frozenset({"NORTH"})
        ),
        source_tables={"fact_orders"},
    )

    assert_equal(
        first.plan.plan_fingerprint,
        second.plan.plan_fingerprint,
        "相同 Context 和来源必须生成相同 fingerprint。",
    )

    assert_true(
        first.plan.plan_fingerprint
        != changed.plan.plan_fingerprint,
        "权限集合变化后 fingerprint 必须变化。",
    )


def run_tests() -> None:
    tests = [
        test_order_region_uses_shipping_region,
        test_order_channel_uses_direct_anchor,
        test_order_items_inherit_both_scopes,
        test_refunds_inherit_through_items_and_orders,
        test_reviews_inherit_through_items_and_orders,
        test_marketing_spend_channel_is_direct,
        test_marketing_spend_region_fails_closed,
        test_roi_like_sources_fail_under_region_scope,
        test_dim_customer_cannot_replace_order_region,
        test_empty_region_scope_means_no_access,
        test_empty_channel_scope_means_no_access,
        test_empty_required_dimensions_is_rejected,
        test_plan_fingerprint_is_stable_and_scope_sensitive,
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
    print("Row Scope Test Summary")
    print(f"Total: {len(tests)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    run_tests()
