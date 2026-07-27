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
    protect_result_rows,
)
from app.semantic_layer.query_plan_v2_models import (
    StagedQueryLogic,
)
from app.semantic_layer.repeat_query_plan_v2_family import (
    build_multi_order_customer_count_overall_plan,
    build_repeat_customer_count_overall_plan,
    build_repeat_customer_rate_overall_plan,
    build_repeat_metric_family,
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
        request_id="req-day73-repeat-family-001",
        actor_id="analyst-001",
        role=AccessRole.SCOPED_ANALYST,
        dataset_name="beauty_bi_v2",
        target_schema="beauty_bi_v2",
        operation_mode=OperationMode.OBSERVE_ADVISE,
        allowed_metrics=frozenset(
            {
                "repeat_customer_count",
                "multi_order_customer_count",
                "repeat_customer_rate",
            }
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
        scope_source="day73_repeat_family_fixture",
    )


def test_family_has_three_plans() -> None:
    plans = build_repeat_metric_family()

    assert_equal(
        len(plans),
        3,
        "复购指标族应包含 3 个 Query Plan。",
    )

    assert_equal(
        {
            plan.metric
            for plan in plans
        },
        {
            "repeat_customer_count",
            "multi_order_customer_count",
            "repeat_customer_rate",
        },
        "复购指标族 metric 集合不正确。",
    )


def test_all_repeat_plans_use_staged_logic() -> None:
    for plan in build_repeat_metric_family():
        assert_true(
            isinstance(plan.query_logic, StagedQueryLogic),
            f"{plan.name} 必须使用 StagedQueryLogic。",
        )

        assert_equal(
            len(plan.query_logic.stages),
            2,
            f"{plan.name} 应包含两个 Stage。",
        )


def test_shared_stage_freezes_customer_period_grain() -> None:
    for plan in build_repeat_metric_family():
        stage = plan.query_logic.stages[0]

        assert_equal(
            stage.stage_id,
            "customer_purchase_summary",
            "第一阶段必须是 customer purchase summary。",
        )

        assert_equal(
            stage.group_by,
            ("fo.customer_id",),
            "第一阶段必须一客户一行。",
        )

        fields = {
            output.field: output.expression
            for output in stage.outputs
        }

        assert_equal(
            fields["purchase_day_count"],
            "COUNT(DISTINCT CAST(fo.paid_at AS DATE))",
            "跨日口径必须按 distinct paid date。",
        )

        assert_equal(
            fields["paid_order_count"],
            "COUNT(DISTINCT fo.order_id)",
            "多单口径必须按 distinct paid order。",
        )


def test_repeat_count_uses_purchase_day_threshold() -> None:
    plan = build_repeat_customer_count_overall_plan()

    expression = plan.query_logic.stages[-1].outputs[0].expression

    assert_true(
        "purchase_day_count >= 2" in expression,
        "跨日复购人数必须使用 purchase_day_count >= 2。",
    )

    assert_true(
        "paid_order_count >= 2" not in expression,
        "跨日复购人数不得偷换成两单口径。",
    )


def test_multi_order_count_uses_order_threshold() -> None:
    plan = build_multi_order_customer_count_overall_plan()

    expression = plan.query_logic.stages[-1].outputs[0].expression

    assert_true(
        "paid_order_count >= 2" in expression,
        "两单及以上人数必须使用 paid_order_count >= 2。",
    )

    assert_true(
        "purchase_day_count >= 2" not in expression,
        "两单及以上人数不得偷换成跨日口径。",
    )


def test_repeat_rate_uses_repeat_customers_over_buyers() -> None:
    plan = build_repeat_customer_rate_overall_plan()

    expression = plan.query_logic.stages[-1].outputs[0].expression

    assert_true(
        "purchase_day_count >= 2" in expression,
        "复购率分子必须是跨日复购客户。",
    )

    assert_true(
        "NULLIF(COUNT(*), 0)" in expression,
        "复购率分母必须是分析期购买客户数。",
    )


def test_repeat_family_is_authorizable() -> None:
    for plan in build_repeat_metric_family():
        decision = authorize_resources(
            build_context(plan),
            required_tables=plan.resource_contract.required_tables,
            required_columns=plan.resource_contract.required_columns,
        )

        assert_equal(
            decision.allowed,
            True,
            f"{plan.name} 应通过 Authorization。",
        )


def test_repeat_family_builds_row_scope_contract() -> None:
    for plan in build_repeat_metric_family():
        context = build_context(plan)

        scope_decision = plan_row_scope(
            context,
            source_tables=plan.scope_contract.source_tables,
            required_dimensions=plan.scope_contract.required_dimensions,
        )

        assert_equal(
            scope_decision.allowed,
            True,
            f"{plan.name} 应能创建 RowScopePlan。",
        )

        binding = build_scoped_query_contract(
            scope_decision.plan,
            targets=plan.to_scope_targets(),
        )

        assert_equal(
            binding.allowed,
            True,
            f"{plan.name} 应能绑定 ScopeTarget。",
        )

        assert_equal(
            len(binding.contract.predicates),
            2,
            f"{plan.name} 应获得 Region + Channel Predicate。",
        )


def test_group_size_is_buyer_count_for_all_repeat_plans() -> None:
    for plan in build_repeat_metric_family():
        hidden = plan.query_logic.stages[-1].hidden_control_fields

        assert_equal(
            len(hidden),
            1,
            f"{plan.name} 应只有一个隐藏 group-size 字段。",
        )

        assert_equal(
            hidden[0].field,
            "__group_size",
            f"{plan.name} 应使用 __group_size。",
        )

        assert_equal(
            hidden[0].expression,
            "COUNT(*)",
            f"{plan.name} 的 group size 应是 customer summary 行数。",
        )

        assert_equal(
            hidden[0].semantics,
            "distinct_buyers_in_analysis_period",
            f"{plan.name} 的 group size 应表达购买人数。",
        )


def test_repeat_family_result_protection_hides_group_size() -> None:
    samples = {
        "repeat_customer_count": 25,
        "multi_order_customer_count": 40,
        "repeat_customer_rate": 0.25,
    }

    for plan in build_repeat_metric_family():
        result = protect_result_rows(
            context=build_context(plan),
            rows=[
                {
                    plan.metric: samples[plan.metric],
                    "__group_size": 100,
                }
            ],
            contract=plan.result_contract,
        )

        assert_equal(
            result.success,
            True,
            f"{plan.name} 普通聚合结果应允许。",
        )

        assert_equal(
            result.rows,
            (
                {
                    plan.metric: samples[plan.metric],
                },
            ),
            f"{plan.name} 必须隐藏 __group_size。",
        )


def test_business_invariant_examples_are_consistent() -> None:
    """
    Contract-level business invariant fixture.

    This does not execute SQL. It freezes the expected logical relation:
    cross-day repeat customers are always a subset of multi-order customers,
    and multi-order customers are always a subset of buyers.
    """
    repeat_customer_count = 25
    multi_order_customer_count = 40
    buyer_count = 100
    repeat_customer_rate = 0.25

    assert_true(
        repeat_customer_count
        <= multi_order_customer_count
        <= buyer_count,
        "复购人数业务不变量必须成立。",
    )

    assert_equal(
        repeat_customer_rate,
        repeat_customer_count / buyer_count,
        "复购率必须等于跨日复购人数 / 购买人数。",
    )


def test_all_repeat_plans_are_overall_only_for_now() -> None:
    for plan in build_repeat_metric_family():
        assert_equal(
            plan.result_grain,
            "overall",
            f"{plan.name} 当前只冻结 overall Grain。",
        )


def run_tests() -> None:
    tests = [
        test_family_has_three_plans,
        test_all_repeat_plans_use_staged_logic,
        test_shared_stage_freezes_customer_period_grain,
        test_repeat_count_uses_purchase_day_threshold,
        test_multi_order_count_uses_order_threshold,
        test_repeat_rate_uses_repeat_customers_over_buyers,
        test_repeat_family_is_authorizable,
        test_repeat_family_builds_row_scope_contract,
        test_group_size_is_buyer_count_for_all_repeat_plans,
        test_repeat_family_result_protection_hides_group_size,
        test_business_invariant_examples_are_consistent,
        test_all_repeat_plans_are_overall_only_for_now,
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
    print("Repeat Query Plan V2 Family Test Summary")
    print(f"Total: {len(tests)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    run_tests()
