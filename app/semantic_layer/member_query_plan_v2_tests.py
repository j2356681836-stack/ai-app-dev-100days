from app.governance.access_context import (
    AccessContext,
    AccessRole,
    OperationMode,
    SensitiveDataPolicy,
)
from app.governance.authorization import (
    authorize_resources,
)
from app.governance.row_scope import (
    plan_row_scope,
)
from app.governance.row_scope_binding import (
    build_scoped_query_contract,
)
from app.governance.sensitive_data import (
    SensitiveDataCategory,
    protect_result_rows,
)
from app.semantic_layer.member_query_plan_v2 import (
    build_member_gmv_share_overall_plan,
)
from app.semantic_layer.query_plan_v2_models import (
    QueryLogic,
    StagedQueryLogic,
)


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(
            f"{message}\nExpected: {expected}\nActual: {actual}"
        )


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def build_context(plan) -> AccessContext:
    return AccessContext(
        request_id="req-day73-member-gmv-share-001",
        actor_id="analyst-001",
        role=AccessRole.SCOPED_ANALYST,
        dataset_name="beauty_bi_v2",
        target_schema="beauty_bi_v2",
        operation_mode=OperationMode.OBSERVE_ADVISE,
        allowed_metrics=frozenset(
            {"member_gmv_share"}
        ),
        allowed_tables=plan.resource_contract.required_tables,
        allowed_columns=plan.resource_contract.required_columns,
        denied_columns=frozenset(),
        allowed_region_codes=frozenset(
            {"SOUTH", "EAST"}
        ),
        allowed_channel_codes=frozenset(
            {"TMALL", "JD"}
        ),
        sensitive_data_policy=SensitiveDataPolicy(),
        policy_version="governance_v1",
        scope_source="day73_member_gmv_share_fixture",
    )


def test_member_share_uses_simple_query_logic() -> None:
    plan = build_member_gmv_share_overall_plan()

    assert_true(
        isinstance(plan.query_logic, QueryLogic),
        "会员 GMV 贡献率应使用普通 QueryLogic。",
    )

    assert_true(
        not isinstance(plan.query_logic, StagedQueryLogic),
        "会员 GMV 贡献率不应无必要使用 StagedQueryLogic。",
    )


def test_member_share_uses_payment_time_snapshot() -> None:
    plan = build_member_gmv_share_overall_plan()

    expression = plan.query_logic.outputs[0].expression

    assert_true(
        "fo.member_level_at_order IS NOT NULL" in expression,
        "会员身份必须使用支付时点 member_level_at_order。",
    )

    assert_true(
        "foi.item_paid_amount" in expression,
        "会员和总 GMV 都必须使用 item_paid_amount。",
    )


def test_member_share_does_not_require_membership_history_tables() -> None:
    plan = build_member_gmv_share_overall_plan()

    tables = plan.resource_contract.required_tables

    forbidden = {
        "fact_membership_tier_history",
        "dim_membership_account",
        "bridge_customer_membership",
    }

    assert_equal(
        tables & forbidden,
        frozenset(),
        "会员 GMV 贡献率不得依赖当前/历史会员表回填交易。",
    )


def test_member_snapshot_column_is_explicit_resource() -> None:
    plan = build_member_gmv_share_overall_plan()

    assert_true(
        "fact_orders.member_level_at_order"
        in plan.resource_contract.required_columns,
        "支付时点会员快照必须显式进入 required_columns。",
    )


def test_member_share_is_authorizable() -> None:
    plan = build_member_gmv_share_overall_plan()

    decision = authorize_resources(
        build_context(plan),
        required_tables=plan.resource_contract.required_tables,
        required_columns=plan.resource_contract.required_columns,
    )

    assert_equal(
        decision.allowed,
        True,
        "会员 GMV 贡献率资源合同应通过 Authorization。",
    )


def test_member_share_builds_row_scope_contract() -> None:
    plan = build_member_gmv_share_overall_plan()
    context = build_context(plan)

    scope_decision = plan_row_scope(
        context,
        source_tables=plan.scope_contract.source_tables,
        required_dimensions=plan.scope_contract.required_dimensions,
    )

    assert_equal(
        scope_decision.allowed,
        True,
        "会员 GMV 贡献率应能创建 RowScopePlan。",
    )

    binding = build_scoped_query_contract(
        scope_decision.plan,
        targets=plan.to_scope_targets(),
    )

    assert_equal(
        binding.allowed,
        True,
        "fact_order_items 应通过 fact_orders 继承 Scope。",
    )

    assert_equal(
        len(binding.contract.predicates),
        2,
        "应获得 Region + Channel Predicate。",
    )


def test_member_share_result_binding_is_ordinary_aggregate() -> None:
    plan = build_member_gmv_share_overall_plan()

    binding = plan.result_contract.field_bindings[0]

    assert_equal(
        binding.output_field,
        "member_gmv_share",
        "Result Binding 输出字段不正确。",
    )

    assert_equal(
        binding.category,
        SensitiveDataCategory.ORDINARY,
        "会员 GMV 占比聚合结果当前应为 ordinary。",
    )

    assert_equal(
        binding.source_columns,
        frozenset(
            {
                "fact_orders.member_level_at_order",
                "fact_order_items.item_paid_amount",
            }
        ),
        "Result Binding 必须记录会员快照与支付金额来源。",
    )


def test_member_share_result_protection_hides_group_size() -> None:
    plan = build_member_gmv_share_overall_plan()

    result = protect_result_rows(
        context=build_context(plan),
        rows=[
            {
                "member_gmv_share": 0.65,
                "__group_size": 100,
            }
        ],
        contract=plan.result_contract,
    )

    assert_equal(
        result.success,
        True,
        "会员 GMV 占比普通聚合结果应允许。",
    )

    assert_equal(
        result.rows,
        (
            {"member_gmv_share": 0.65},
        ),
        "__group_size 必须隐藏。",
    )


def test_member_share_uses_distinct_buyers_for_group_size() -> None:
    plan = build_member_gmv_share_overall_plan()

    hidden = plan.query_logic.hidden_control_fields[0]

    assert_equal(
        hidden.expression,
        "COUNT(DISTINCT fo.customer_id)",
        "Minimum Group Size 应按 distinct buyers。",
    )

    assert_equal(
        hidden.semantics,
        "distinct_buyers_in_analysis_period",
        "Group-size 语义应明确为分析期购买人数。",
    )


def test_member_share_is_overall_only_for_now() -> None:
    plan = build_member_gmv_share_overall_plan()

    assert_equal(
        plan.result_grain,
        "overall",
        "当前只冻结 overall Grain。",
    )

    assert_equal(
        plan.query_logic.group_by,
        (),
        "Overall Plan 不应 GROUP BY。",
    )


def run_tests() -> None:
    tests = [
        test_member_share_uses_simple_query_logic,
        test_member_share_uses_payment_time_snapshot,
        test_member_share_does_not_require_membership_history_tables,
        test_member_snapshot_column_is_explicit_resource,
        test_member_share_is_authorizable,
        test_member_share_builds_row_scope_contract,
        test_member_share_result_binding_is_ordinary_aggregate,
        test_member_share_result_protection_hides_group_size,
        test_member_share_uses_distinct_buyers_for_group_size,
        test_member_share_is_overall_only_for_now,
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
    print("Member GMV Share Query Plan V2 Test Summary")
    print(f"Total: {len(tests)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    run_tests()
