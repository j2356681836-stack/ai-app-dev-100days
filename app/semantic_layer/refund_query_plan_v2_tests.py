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
    ProtectionReason,
    SensitiveDataCategory,
    protect_result_rows,
)
from app.semantic_layer.query_plan_v2_models import (
    StagedQueryLogic,
)
from app.semantic_layer.refund_query_plan_v2 import (
    build_refund_rate_overall_plan,
)


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(
            f"{message}\nExpected: {expected}\nActual: {actual}"
        )


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def build_context(
    plan,
    *,
    allow_cost_data: bool = False,
) -> AccessContext:
    return AccessContext(
        request_id="req-day73-refund-rate-001",
        actor_id="analyst-001",
        role=AccessRole.SCOPED_ANALYST,
        dataset_name="beauty_bi_v2",
        target_schema="beauty_bi_v2",
        operation_mode=OperationMode.OBSERVE_ADVISE,
        allowed_metrics=frozenset(
            {"refund_rate"}
        ),
        allowed_tables=(
            plan.resource_contract.required_tables
        ),
        allowed_columns=(
            plan.resource_contract.required_columns
        ),
        denied_columns=frozenset(),
        allowed_region_codes=frozenset(
            {"SOUTH", "EAST"}
        ),
        allowed_channel_codes=frozenset(
            {"TMALL", "JD"}
        ),
        sensitive_data_policy=SensitiveDataPolicy(
            allow_cost_data=allow_cost_data,
        ),
        policy_version="governance_v1",
        scope_source="day73_refund_rate_fixture",
    )


def test_refund_rate_uses_staged_logic() -> None:
    plan = build_refund_rate_overall_plan()

    assert_true(
        isinstance(
            plan.query_logic,
            StagedQueryLogic,
        ),
        "退款率必须使用 StagedQueryLogic。",
    )

    assert_equal(
        len(plan.query_logic.stages),
        2,
        "退款率应由 Item Refund Summary + Final 两阶段组成。",
    )


def test_refund_rate_is_attributed_to_paid_at() -> None:
    plan = build_refund_rate_overall_plan()

    assert_equal(
        plan.semantic_contract.date_attribution,
        "fact_orders.paid_at",
        "销售退款率必须按原订单 paid_at 归属。",
    )

    assert_true(
        "fact_refunds.refund_completed_at"
        not in plan.resource_contract.required_columns,
        (
            "销售 cohort 退款率不应把 refund_completed_at "
            "当作必要时间字段。"
        ),
    )


def test_stage_one_uses_left_join_for_refunds() -> None:
    plan = build_refund_rate_overall_plan()
    stage = plan.query_logic.stages[0]

    refund_join = next(
        join
        for join in stage.joins
        if join.table == "fact_refunds"
    )

    assert_equal(
        refund_join.join_type,
        "left",
        (
            "退款事实必须 LEFT JOIN，"
            "否则无退款销售 item 会从 GMV 分母消失。"
        ),
    )


def test_refund_join_uses_item_and_order_keys() -> None:
    plan = build_refund_rate_overall_plan()
    stage = plan.query_logic.stages[0]

    refund_join = next(
        join
        for join in stage.joins
        if join.table == "fact_refunds"
    )

    conditions = {
        (
            condition.left,
            condition.right,
        )
        for condition in refund_join.conditions
    }

    assert_equal(
        conditions,
        {
            (
                "foi.order_item_id",
                "fr.order_item_id",
            ),
            (
                "foi.order_id",
                "fr.order_id",
            ),
        },
        "退款 Join 必须使用 order_item + order 复合关系。",
    )


def test_completed_status_is_inside_aggregate_not_where() -> None:
    plan = build_refund_rate_overall_plan()
    stage = plan.query_logic.stages[0]

    assert_equal(
        stage.filters,
        ("fo.paid_at IS NOT NULL",),
        (
            "refund_status 不得进入 WHERE；"
            "否则会错误删除无退款/非 completed item。"
        ),
    )

    expression = next(
        output.expression
        for output in stage.outputs
        if output.field
        == "completed_refund_amount"
    )

    assert_true(
        "fr.refund_status = 'completed'"
        in expression,
        "completed-only 条件必须进入退款金额聚合。",
    )

    assert_true(
        "SUM(fr.refund_amount) FILTER"
        in expression,
        "completed refund 应通过 FILTER 聚合。",
    )


def test_stage_one_preaggregates_to_order_item_grain() -> None:
    plan = build_refund_rate_overall_plan()
    stage = plan.query_logic.stages[0]

    assert_true(
        "foi.order_item_id"
        in stage.group_by,
        "退款必须先聚合到 order_item Grain。",
    )

    assert_equal(
        len(
            [
                output
                for output in stage.outputs
                if output.field
                == "item_paid_amount"
            ]
        ),
        1,
        "每个 Item Summary 只能保留一份原始 item_paid_amount。",
    )


def test_final_ratio_uses_preaggregated_fields() -> None:
    plan = build_refund_rate_overall_plan()
    final_stage = plan.query_logic.stages[-1]

    expression = final_stage.outputs[0].expression

    assert_equal(
        expression,
        (
            "SUM(irs.completed_refund_amount) "
            "/ NULLIF("
            "SUM(irs.item_paid_amount), 0)"
        ),
        "最终退款率必须用预聚合退款额 / 原始 Item GMV。",
    )


def test_refund_rate_is_authorizable() -> None:
    plan = build_refund_rate_overall_plan()

    decision = authorize_resources(
        build_context(
            plan,
            allow_cost_data=True,
        ),
        required_tables=(
            plan.resource_contract.required_tables
        ),
        required_columns=(
            plan.resource_contract.required_columns
        ),
    )

    assert_equal(
        decision.allowed,
        True,
        "退款率资源合同应能通过 Authorization。",
    )


def test_refund_rate_builds_row_scope_contract() -> None:
    plan = build_refund_rate_overall_plan()
    context = build_context(
        plan,
        allow_cost_data=True,
    )

    scope_decision = plan_row_scope(
        context,
        source_tables=(
            plan.scope_contract.source_tables
        ),
        required_dimensions=(
            plan.scope_contract.required_dimensions
        ),
    )

    assert_equal(
        scope_decision.allowed,
        True,
        "退款率应能创建 RowScopePlan。",
    )

    binding = build_scoped_query_contract(
        scope_decision.plan,
        targets=plan.to_scope_targets(),
    )

    assert_equal(
        binding.allowed,
        True,
        (
            "fact_order_items 应通过 fact_orders "
            "继承 Region + Channel Scope。"
        ),
    )

    assert_equal(
        len(binding.contract.predicates),
        2,
        "退款率必须获得 Region + Channel Predicate。",
    )


def test_refund_rate_binding_is_business_confidential() -> None:
    plan = build_refund_rate_overall_plan()
    binding = plan.result_contract.field_bindings[0]

    assert_equal(
        binding.category,
        SensitiveDataCategory.BUSINESS_CONFIDENTIAL,
        "退款率因使用 refund_amount，应按经营敏感结果保护。",
    )

    assert_true(
        "fact_refunds.refund_amount"
        in binding.source_columns,
        "Result Binding 必须记录 refund_amount 来源。",
    )


def test_refund_rate_is_denied_by_default() -> None:
    plan = build_refund_rate_overall_plan()

    result = protect_result_rows(
        context=build_context(plan),
        rows=[
            {
                "refund_rate": 0.08,
                "__group_size": 100,
            }
        ],
        contract=plan.result_contract,
    )

    assert_equal(
        result.success,
        False,
        "默认策略必须拒绝经营敏感退款率结果。",
    )

    assert_equal(
        result.reason_code,
        ProtectionReason.COST_DATA_NOT_ALLOWED,
        (
            "当前 Day71 统一 Business Confidential "
            "策略应返回 cost_data_not_allowed。"
        ),
    )


def test_refund_rate_can_be_explicitly_allowed() -> None:
    plan = build_refund_rate_overall_plan()

    result = protect_result_rows(
        context=build_context(
            plan,
            allow_cost_data=True,
        ),
        rows=[
            {
                "refund_rate": 0.08,
                "__group_size": 100,
            }
        ],
        contract=plan.result_contract,
    )

    assert_equal(
        result.success,
        True,
        "显式允许 Business Confidential 后退款率应可返回。",
    )

    assert_equal(
        result.rows,
        (
            {"refund_rate": 0.08},
        ),
        "__group_size 必须从最终结果隐藏。",
    )


def test_group_size_uses_distinct_buyers() -> None:
    plan = build_refund_rate_overall_plan()
    hidden = (
        plan.query_logic
        .stages[-1]
        .hidden_control_fields[0]
    )

    assert_equal(
        hidden.expression,
        "COUNT(DISTINCT irs.customer_id)",
        "Minimum Group Size 必须按 sales cohort distinct buyers。",
    )

    assert_equal(
        hidden.semantics,
        "distinct_buyers_in_sales_cohort",
        "Group Size 语义必须明确为销售 cohort 购买人数。",
    )


def test_refund_rate_is_overall_only_for_now() -> None:
    plan = build_refund_rate_overall_plan()

    assert_equal(
        plan.result_grain,
        "overall",
        "当前仅冻结 Overall Refund Rate。",
    )


def run_tests() -> None:
    tests = [
        test_refund_rate_uses_staged_logic,
        test_refund_rate_is_attributed_to_paid_at,
        test_stage_one_uses_left_join_for_refunds,
        test_refund_join_uses_item_and_order_keys,
        test_completed_status_is_inside_aggregate_not_where,
        test_stage_one_preaggregates_to_order_item_grain,
        test_final_ratio_uses_preaggregated_fields,
        test_refund_rate_is_authorizable,
        test_refund_rate_builds_row_scope_contract,
        test_refund_rate_binding_is_business_confidential,
        test_refund_rate_is_denied_by_default,
        test_refund_rate_can_be_explicitly_allowed,
        test_group_size_uses_distinct_buyers,
        test_refund_rate_is_overall_only_for_now,
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
    print("Refund Rate Query Plan V2 Test Summary")
    print(f"Total: {len(tests)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    run_tests()
