from pydantic import ValidationError

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
    RowScopeReason,
    ScopeDimension,
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
    QueryPlanV2,
    StageJoin,
    StagedQueryLogic,
)
from app.semantic_layer.roi_query_plan_v2 import (
    build_roi_channel_plan,
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
        request_id="req-day73-roi-001",
        actor_id="analyst-001",
        role=AccessRole.SCOPED_ANALYST,
        dataset_name="beauty_bi_v2",
        target_schema="beauty_bi_v2",
        operation_mode=OperationMode.OBSERVE_ADVISE,
        allowed_metrics=frozenset({"roi"}),
        allowed_tables=plan.resource_contract.required_tables,
        allowed_columns=plan.resource_contract.required_columns,
        denied_columns=frozenset(),
        allowed_region_codes=frozenset(
            {"EAST", "SOUTH"}
        ),
        allowed_channel_codes=frozenset(
            {"TMALL", "JD"}
        ),
        sensitive_data_policy=SensitiveDataPolicy(
            allow_cost_data=allow_cost_data,
        ),
        policy_version="governance_v1",
        scope_source="day73_roi_fixture",
    )


def plan_payload() -> dict:
    return build_roi_channel_plan().model_dump(
        mode="json"
    )


def test_roi_uses_three_stage_cross_fact_logic() -> None:
    plan = build_roi_channel_plan()

    assert_true(
        isinstance(
            plan.query_logic,
            StagedQueryLogic,
        ),
        "ROI 必须使用 StagedQueryLogic。",
    )

    assert_equal(
        [
            stage.stage_id
            for stage in plan.query_logic.stages
        ],
        [
            "channel_sales",
            "channel_spend",
            "final",
        ],
        "ROI 应先独立聚合 Sales / Spend，再合并。",
    )


def test_final_stage_uses_stage_join() -> None:
    plan = build_roi_channel_plan()
    final_stage = plan.query_logic.stages[-1]

    stage_joins = [
        join
        for join in final_stage.joins
        if isinstance(join, StageJoin)
    ]

    assert_equal(
        len(stage_joins),
        1,
        "Final Stage 应有一个 Derived Stage Join。",
    )

    join = stage_joins[0]

    assert_equal(
        join.stage_id,
        "channel_spend",
        "Final Stage 必须 JOIN channel_spend。",
    )

    assert_equal(
        (
            join.conditions[0].left,
            join.conditions[0].right,
        ),
        (
            "cs.channel_id",
            "csp.channel_id",
        ),
        "Sales / Spend 必须按 channel_id 合并。",
    )


def test_roi_freezes_shared_time_window_columns() -> None:
    plan = build_roi_channel_plan()

    assert_equal(
        plan.semantic_contract.time_window_columns,
        (
            "fact_orders.paid_at",
            "fact_marketing_spend.spend_date",
        ),
        "ROI 必须显式声明两个事实源共享分析时间窗。",
    )


def test_sales_and_spend_use_same_date_parameters() -> None:
    plan = build_roi_channel_plan()

    sales_stage = plan.query_logic.stages[0]
    spend_stage = plan.query_logic.stages[1]

    sales_filter = " ".join(
        sales_stage.filters
    )

    spend_filter = " ".join(
        spend_stage.filters
    )

    for parameter in (
        ":analysis_start_date",
        ":analysis_end_date",
    ):
        assert_true(
            parameter in sales_filter,
            "Sales Stage 必须使用统一分析日期参数。",
        )

        assert_true(
            parameter in spend_filter,
            "Spend Stage 必须使用统一分析日期参数。",
        )


def test_sales_and_spend_are_preaggregated_by_channel() -> None:
    plan = build_roi_channel_plan()

    sales_stage = plan.query_logic.stages[0]
    spend_stage = plan.query_logic.stages[1]

    assert_equal(
        sales_stage.group_by,
        ("fo.channel_id",),
        "Sales 必须先聚合到 Channel Grain。",
    )

    assert_equal(
        spend_stage.group_by,
        ("fms.channel_id",),
        "Spend 必须先聚合到 Channel Grain。",
    )


def test_roi_formula_is_ratio_not_percent() -> None:
    plan = build_roi_channel_plan()

    expression = (
        plan.query_logic
        .stages[-1]
        .outputs[1]
        .expression
    )

    assert_equal(
        expression,
        (
            "cs.channel_gmv "
            "/ NULLIF("
            "csp.marketing_spend_amount, 0)"
        ),
        "ROI 必须是 GMV / Spend 的倍数。",
    )

    assert_true(
        "* 100" not in expression,
        "ROI V2 不得乘以 100。",
    )


def test_roi_only_uses_shared_sales_marketing_channels() -> None:
    plan = build_roi_channel_plan()

    filters = set(
        plan.query_logic
        .stages[-1]
        .filters
    )

    assert_true(
        {
            "dc.is_active = TRUE",
            "dc.is_sales_channel = TRUE",
            "dc.is_marketing_channel = TRUE",
        }.issubset(filters),
        "ROI 只比较启用且同时支持销售/营销的渠道。",
    )


def test_roi_resource_contract_is_authorizable() -> None:
    plan = build_roi_channel_plan()

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
        "ROI Table/Column Resource Contract 应可授权。",
    )


def test_roi_region_scope_fails_closed() -> None:
    plan = build_roi_channel_plan()

    decision = plan_row_scope(
        build_context(
            plan,
            allow_cost_data=True,
        ),
        source_tables=(
            plan.scope_contract.source_tables
        ),
        required_dimensions=(
            plan.scope_contract.required_dimensions
        ),
    )

    assert_equal(
        decision.allowed,
        False,
        "营销费用无 Region Anchor 时 ROI 必须 fail closed。",
    )

    assert_equal(
        decision.reason_code,
        RowScopeReason.UNSUPPORTED_SCOPE_PATH,
        "ROI 应返回 unsupported_scope_path。",
    )

    assert_true(
        "region:fact_marketing_spend"
        in decision.unsupported_scope_paths,
        "ROI 必须明确指出营销费用缺少 Region Path。",
    )

    assert_equal(
        decision.retryable,
        False,
        "ROI Row Scope 拒绝不得进入 SQL Repair。",
    )


def test_roi_targets_support_independent_channel_binding() -> None:
    """
    This validates target completeness only.

    It does NOT bypass the plan's Region requirement. The production plan
    still declares Region + Channel and therefore fails closed today.
    """
    plan = build_roi_channel_plan()
    context = build_context(
        plan,
        allow_cost_data=True,
    )

    channel_only = plan_row_scope(
        context,
        source_tables=(
            plan.scope_contract.source_tables
        ),
        required_dimensions={
            ScopeDimension.CHANNEL,
        },
    )

    assert_equal(
        channel_only.allowed,
        True,
        "两个事实来源都应支持 Channel Scope。",
    )

    binding = build_scoped_query_contract(
        channel_only.plan,
        targets=plan.to_scope_targets(),
    )

    assert_equal(
        binding.allowed,
        True,
        "Sales / Spend 两个 Target 都应能独立绑定 Channel Predicate。",
    )

    fragments = {
        predicate.target_id:
            predicate.sql_fragment
        for predicate in (
            binding.contract.predicates
        )
    }

    assert_true(
        "fo.channel_id"
        in fragments["roi_channel_sales"],
        "Sales Predicate 必须落到订单 channel_id。",
    )

    assert_true(
        "fms.channel_id"
        in fragments["roi_channel_spend"],
        "Spend Predicate 必须落到营销 channel_id。",
    )

    assert_equal(
        len(binding.contract.predicates),
        2,
        "Channel-only 验证应生成两个独立 Predicate。",
    )


def test_stage_join_forward_reference_is_rejected() -> None:
    payload = plan_payload()

    payload["query_logic"]["stages"][2][
        "joins"
    ][0]["stage_id"] = "future_stage"

    try:
        QueryPlanV2.model_validate(payload)
    except ValidationError:
        return

    raise AssertionError(
        "StageJoin 不得引用不存在或未来 Stage。"
    )


def test_stage_join_unknown_output_field_is_rejected() -> None:
    payload = plan_payload()

    payload["query_logic"]["stages"][2][
        "joins"
    ][0]["conditions"][0]["right"] = (
        "csp.not_exposed"
    )

    try:
        QueryPlanV2.model_validate(payload)
    except ValidationError:
        return

    raise AssertionError(
        "StageJoin 不得引用 referenced stage 未暴露的字段。"
    )


def test_roi_binding_is_business_confidential() -> None:
    plan = build_roi_channel_plan()

    binding = next(
        binding
        for binding in (
            plan.result_contract.field_bindings
        )
        if binding.output_field == "roi"
    )

    assert_equal(
        binding.category,
        SensitiveDataCategory.BUSINESS_CONFIDENTIAL,
        "ROI 因使用 spend_amount，应按经营敏感结果保护。",
    )

    assert_true(
        "fact_marketing_spend.spend_amount"
        in binding.source_columns,
        "ROI Result Binding 必须记录 spend_amount 来源。",
    )


def test_roi_is_denied_by_default() -> None:
    plan = build_roi_channel_plan()

    result = protect_result_rows(
        context=build_context(plan),
        rows=[
            {
                "channel_name": "示例渠道",
                "roi": 3.2,
                "__group_size": 100,
            }
        ],
        contract=plan.result_contract,
    )

    assert_equal(
        result.success,
        False,
        "默认策略必须拒绝 Business Confidential ROI。",
    )

    assert_equal(
        result.reason_code,
        ProtectionReason.COST_DATA_NOT_ALLOWED,
        "当前统一经营敏感策略应返回 cost_data_not_allowed。",
    )


def test_roi_can_be_explicitly_allowed() -> None:
    plan = build_roi_channel_plan()

    result = protect_result_rows(
        context=build_context(
            plan,
            allow_cost_data=True,
        ),
        rows=[
            {
                "channel_name": "示例渠道",
                "roi": 3.2,
                "__group_size": 100,
            }
        ],
        contract=plan.result_contract,
    )

    assert_equal(
        result.success,
        True,
        "显式允许经营敏感数据后 ROI 应可返回。",
    )

    assert_equal(
        result.rows,
        (
            {
                "channel_name": "示例渠道",
                "roi": 3.2,
            },
        ),
        "__group_size 必须隐藏。",
    )


def test_roi_is_channel_only_for_now() -> None:
    plan = build_roi_channel_plan()

    assert_equal(
        plan.result_grain,
        "channel",
        "当前只冻结 Channel ROI。",
    )


def run_tests() -> None:
    tests = [
        test_roi_uses_three_stage_cross_fact_logic,
        test_final_stage_uses_stage_join,
        test_roi_freezes_shared_time_window_columns,
        test_sales_and_spend_use_same_date_parameters,
        test_sales_and_spend_are_preaggregated_by_channel,
        test_roi_formula_is_ratio_not_percent,
        test_roi_only_uses_shared_sales_marketing_channels,
        test_roi_resource_contract_is_authorizable,
        test_roi_region_scope_fails_closed,
        test_roi_targets_support_independent_channel_binding,
        test_stage_join_forward_reference_is_rejected,
        test_stage_join_unknown_output_field_is_rejected,
        test_roi_binding_is_business_confidential,
        test_roi_is_denied_by_default,
        test_roi_can_be_explicitly_allowed,
        test_roi_is_channel_only_for_now,
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
    print("ROI Query Plan V2 Test Summary")
    print(f"Total: {len(tests)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    run_tests()
