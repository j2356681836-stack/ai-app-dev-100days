from pydantic import ValidationError

from app.governance.access_context import (
    AccessContext,
    AccessRole,
    OperationMode,
    SensitiveDataPolicy,
)
from app.governance.row_scope import (
    ScopeDimension,
    plan_row_scope,
)
from app.governance.row_scope_binding import (
    ScopeBindingReason,
    ScopeTarget,
    TableAliasBinding,
    build_scoped_query_contract,
    verify_scope_contract_reuse,
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
        "request_id": "req-day69-binding-001",
        "actor_id": "analyst-001",
        "role": AccessRole.SCOPED_ANALYST,
        "dataset_name": "beauty_bi_v2",
        "target_schema": "beauty_bi_v2",
        "operation_mode": OperationMode.OBSERVE_ADVISE,
        "allowed_metrics": frozenset(
            {"gmv", "refund_rate", "roi"}
        ),
        "allowed_tables": frozenset(
            {
                "fact_orders",
                "fact_order_items",
                "fact_refunds",
                "fact_marketing_spend",
                "dim_region",
                "dim_channel",
            }
        ),
        "allowed_columns": frozenset(
            {
                "fact_orders.shipping_region_id",
                "fact_orders.channel_id",
                "fact_order_items.order_id",
                "fact_refunds.order_item_id",
                "fact_marketing_spend.channel_id",
                "dim_region.region_id",
                "dim_region.region_code",
                "dim_channel.channel_id",
                "dim_channel.channel_code",
            }
        ),
        "denied_columns": frozenset(),
        "allowed_region_codes": frozenset(
            {"SOUTH", "EAST"}
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


def make_target(
    target_id: str,
    source_table: str,
    aliases: dict[str, str],
) -> ScopeTarget:
    return ScopeTarget(
        target_id=target_id,
        source_table=source_table,
        table_aliases=tuple(
            TableAliasBinding(
                table_name=table_name,
                alias=alias,
            )
            for table_name, alias in aliases.items()
        ),
    )


def build_order_plan(
    *,
    context: AccessContext | None = None,
    dimensions=None,
):
    context = context or build_context()
    dimensions = dimensions or {
        ScopeDimension.REGION,
        ScopeDimension.CHANNEL,
    }

    decision = plan_row_scope(
        context,
        source_tables={"fact_orders"},
        required_dimensions=dimensions,
    )

    assert_true(
        decision.allowed,
        "测试前置条件：订单 RowScopePlan 应创建成功。",
    )

    return decision.plan


def find_predicate(contract, dimension: ScopeDimension):
    matches = [
        predicate
        for predicate in contract.predicates
        if predicate.dimension == dimension
    ]

    assert_equal(
        len(matches),
        1,
        "应该存在且仅存在一个目标维度 Predicate。",
    )

    return matches[0]


def parameter_dict(contract) -> dict[str, str]:
    return {
        parameter.name: parameter.value
        for parameter in contract.parameters
    }


def test_order_predicates_are_parameterized() -> None:
    plan = build_order_plan()

    decision = build_scoped_query_contract(
        plan,
        targets=(
            make_target(
                "orders_main",
                "fact_orders",
                {"fact_orders": "fo"},
            ),
        ),
    )

    assert_equal(
        decision.allowed,
        True,
        "订单 Scope Predicate 合同应该创建成功。",
    )

    region_predicate = find_predicate(
        decision.contract,
        ScopeDimension.REGION,
    )

    channel_predicate = find_predicate(
        decision.contract,
        ScopeDimension.CHANNEL,
    )

    assert_true(
        "fo.shipping_region_id" in region_predicate.sql_fragment,
        "Region Predicate 应使用订单配送地区别名。",
    )

    assert_true(
        "beauty_bi_v2.dim_region" in region_predicate.sql_fragment,
        "Region Predicate 应显式绑定 V2 Schema。",
    )

    assert_true(
        "fo.channel_id" in channel_predicate.sql_fragment,
        "Channel Predicate 应使用订单渠道别名。",
    )

    values = parameter_dict(decision.contract)

    assert_equal(
        set(values.values()),
        {"EAST", "SOUTH", "JD", "TMALL"},
        "所有允许业务编码都应进入参数合同。",
    )

    for value in values.values():
        assert_true(
            value not in region_predicate.sql_fragment
            and value not in channel_predicate.sql_fragment,
            "业务编码不得直接插值进 SQL Fragment。",
        )


def test_parameter_order_is_deterministic() -> None:
    plan = build_order_plan(
        context=build_context(
            allowed_region_codes=frozenset(
                {"SOUTH", "EAST", "NORTH"}
            )
        ),
        dimensions={ScopeDimension.REGION},
    )

    decision = build_scoped_query_contract(
        plan,
        targets=(
            make_target(
                "orders_main",
                "fact_orders",
                {"fact_orders": "fo"},
            ),
        ),
    )

    values = [
        parameter.value
        for parameter in decision.contract.parameters
    ]

    assert_equal(
        values,
        ["EAST", "NORTH", "SOUTH"],
        "参数顺序必须按业务编码稳定排序。",
    )


def test_refund_scope_uses_declared_order_alias() -> None:
    decision = plan_row_scope(
        build_context(),
        source_tables={"fact_refunds"},
        required_dimensions={ScopeDimension.REGION},
    )

    assert_true(
        decision.allowed,
        "测试前置条件：退款 RowScopePlan 应创建成功。",
    )

    binding = build_scoped_query_contract(
        decision.plan,
        targets=(
            make_target(
                "refunds_main",
                "fact_refunds",
                {
                    "fact_refunds": "fr",
                    "fact_order_items": "foi",
                    "fact_orders": "fo",
                },
            ),
        ),
    )

    assert_equal(
        binding.allowed,
        True,
        "退款 Scope Predicate 应支持两跳继承路径。",
    )

    predicate = binding.contract.predicates[0]

    assert_true(
        "fo.shipping_region_id" in predicate.sql_fragment,
        "退款 Region Predicate 最终必须使用订单配送地区别名。",
    )


def test_missing_path_alias_fails_closed() -> None:
    decision = plan_row_scope(
        build_context(),
        source_tables={"fact_refunds"},
        required_dimensions={ScopeDimension.CHANNEL},
    )

    binding = build_scoped_query_contract(
        decision.plan,
        targets=(
            make_target(
                "refunds_main",
                "fact_refunds",
                {
                    "fact_refunds": "fr",
                    "fact_order_items": "foi",
                },
            ),
        ),
    )

    assert_equal(
        binding.allowed,
        False,
        "缺少 fact_orders alias 时必须拒绝。",
    )

    assert_equal(
        binding.reason_code,
        ScopeBindingReason.MISSING_PATH_ALIAS,
        "应返回 missing_path_alias。",
    )

    assert_equal(
        binding.missing_path_aliases,
        frozenset({"refunds_main:fact_orders"}),
        "应指出具体缺失的路径别名。",
    )

    assert_equal(
        binding.retryable,
        False,
        "Scope Binding Failure 不得进入 SQL Repair。",
    )


def test_missing_source_target_fails_closed() -> None:
    decision = plan_row_scope(
        build_context(),
        source_tables={
            "fact_orders",
            "fact_marketing_spend",
        },
        required_dimensions={ScopeDimension.CHANNEL},
    )

    assert_true(
        decision.allowed,
        "两个来源都支持 Channel Scope。",
    )

    binding = build_scoped_query_contract(
        decision.plan,
        targets=(
            make_target(
                "orders_sales",
                "fact_orders",
                {"fact_orders": "fo"},
            ),
        ),
    )

    assert_equal(
        binding.allowed,
        False,
        "营销费用来源没有 Target 时必须拒绝。",
    )

    assert_equal(
        binding.reason_code,
        ScopeBindingReason.MISSING_SCOPE_TARGET,
        "应返回 missing_scope_target。",
    )

    assert_equal(
        binding.missing_source_tables,
        frozenset({"fact_marketing_spend"}),
        "应指出缺少营销费用 ScopeTarget。",
    )


def test_extra_source_target_fails_closed() -> None:
    plan = build_order_plan(
        dimensions={ScopeDimension.CHANNEL},
    )

    binding = build_scoped_query_contract(
        plan,
        targets=(
            make_target(
                "orders_main",
                "fact_orders",
                {"fact_orders": "fo"},
            ),
            make_target(
                "spend_main",
                "fact_marketing_spend",
                {"fact_marketing_spend": "fms"},
            ),
        ),
    )

    assert_equal(
        binding.allowed,
        False,
        "Plan 外来源不得被悄悄加入合同。",
    )

    assert_equal(
        binding.reason_code,
        ScopeBindingReason.EXTRA_SCOPE_TARGET,
        "应返回 extra_scope_target。",
    )


def test_multiple_query_targets_get_separate_predicates() -> None:
    decision = plan_row_scope(
        build_context(),
        source_tables={
            "fact_orders",
            "fact_marketing_spend",
        },
        required_dimensions={ScopeDimension.CHANNEL},
    )

    binding = build_scoped_query_contract(
        decision.plan,
        targets=(
            make_target(
                "channel_sales",
                "fact_orders",
                {"fact_orders": "fo"},
            ),
            make_target(
                "channel_spend",
                "fact_marketing_spend",
                {"fact_marketing_spend": "fms"},
            ),
        ),
    )

    assert_equal(
        binding.allowed,
        True,
        "两个 CTE 来源都应分别获得 Channel Predicate。",
    )

    fragments = {
        predicate.target_id: predicate.sql_fragment
        for predicate in binding.contract.predicates
    }

    assert_true(
        "fo.channel_id" in fragments["channel_sales"],
        "销售 CTE 应约束订单渠道。",
    )

    assert_true(
        "fms.channel_id" in fragments["channel_spend"],
        "费用 CTE 应约束营销渠道。",
    )

    assert_equal(
        len(binding.contract.predicates),
        2,
        "两个来源应形成两个独立 Predicate。",
    )


def test_contract_fingerprint_is_stable() -> None:
    plan = build_order_plan()

    target = make_target(
        "orders_main",
        "fact_orders",
        {"fact_orders": "fo"},
    )

    first = build_scoped_query_contract(
        plan,
        targets=(target,),
    )

    second = build_scoped_query_contract(
        plan,
        targets=(target,),
    )

    assert_equal(
        first.contract.contract_fingerprint,
        second.contract.contract_fingerprint,
        "相同 Plan 和 Target 必须生成稳定 fingerprint。",
    )


def test_alias_change_changes_contract_fingerprint() -> None:
    plan = build_order_plan()

    first = build_scoped_query_contract(
        plan,
        targets=(
            make_target(
                "orders_main",
                "fact_orders",
                {"fact_orders": "fo"},
            ),
        ),
    )

    changed = build_scoped_query_contract(
        plan,
        targets=(
            make_target(
                "orders_main",
                "fact_orders",
                {"fact_orders": "orders"},
            ),
        ),
    )

    assert_true(
        first.contract.contract_fingerprint
        != changed.contract.contract_fingerprint,
        "SQL alias 绑定变化后合同 fingerprint 必须变化。",
    )


def test_initial_and_repair_can_reuse_same_contract() -> None:
    plan = build_order_plan()

    binding = build_scoped_query_contract(
        plan,
        targets=(
            make_target(
                "orders_main",
                "fact_orders",
                {"fact_orders": "fo"},
            ),
        ),
    )

    initial_check = verify_scope_contract_reuse(
        plan,
        binding.contract,
    )

    repair_check = verify_scope_contract_reuse(
        plan,
        binding.contract,
    )

    assert_equal(
        initial_check.allowed,
        True,
        "Initial SQL 应能复用原合同。",
    )

    assert_equal(
        repair_check.allowed,
        True,
        "Repaired SQL 应继续复用原合同。",
    )

    assert_equal(
        initial_check.contract.contract_fingerprint,
        repair_check.contract.contract_fingerprint,
        "Initial / Repaired SQL 的合同 fingerprint 必须一致。",
    )


def test_changed_plan_cannot_reuse_old_contract() -> None:
    original_plan = build_order_plan()

    original_binding = build_scoped_query_contract(
        original_plan,
        targets=(
            make_target(
                "orders_main",
                "fact_orders",
                {"fact_orders": "fo"},
            ),
        ),
    )

    changed_plan = build_order_plan(
        context=build_context(
            allowed_region_codes=frozenset({"NORTH"})
        )
    )

    reuse = verify_scope_contract_reuse(
        changed_plan,
        original_binding.contract,
    )

    assert_equal(
        reuse.allowed,
        False,
        "权限变化后不得复用旧合同。",
    )

    assert_equal(
        reuse.reason_code,
        ScopeBindingReason.PLAN_CONTRACT_MISMATCH,
        "应返回 plan_contract_mismatch。",
    )


def test_invalid_alias_is_rejected_by_contract_model() -> None:
    try:
        make_target(
            "orders_main",
            "fact_orders",
            {"fact_orders": "fo;drop"},
        )
    except ValidationError:
        return

    raise AssertionError(
        "不合法 SQL alias 应在 ScopeTarget 创建时被拒绝。"
    )


def test_contract_is_immutable() -> None:
    plan = build_order_plan()

    binding = build_scoped_query_contract(
        plan,
        targets=(
            make_target(
                "orders_main",
                "fact_orders",
                {"fact_orders": "fo"},
            ),
        ),
    )

    try:
        binding.contract.plan_fingerprint = "changed"
    except ValidationError:
        return

    raise AssertionError(
        "ScopedQueryContract 创建后必须不可修改。"
    )


def run_tests() -> None:
    tests = [
        test_order_predicates_are_parameterized,
        test_parameter_order_is_deterministic,
        test_refund_scope_uses_declared_order_alias,
        test_missing_path_alias_fails_closed,
        test_missing_source_target_fails_closed,
        test_extra_source_target_fails_closed,
        test_multiple_query_targets_get_separate_predicates,
        test_contract_fingerprint_is_stable,
        test_alias_change_changes_contract_fingerprint,
        test_initial_and_repair_can_reuse_same_contract,
        test_changed_plan_cannot_reuse_old_contract,
        test_invalid_alias_is_rejected_by_contract_model,
        test_contract_is_immutable,
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
    print("Row Scope Binding Test Summary")
    print(f"Total: {len(tests)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    run_tests()
