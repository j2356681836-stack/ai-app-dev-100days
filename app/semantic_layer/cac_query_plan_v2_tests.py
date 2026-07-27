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
from app.semantic_layer.cac_query_plan_v2 import (
    build_cac_channel_plan,
)
from app.semantic_layer.global_history_scope import (
    GlobalHistoryScopeReason,
    evaluate_global_history_scope,
)
from app.semantic_layer.query_plan_v2_models import (
    QueryPlanV2,
    StageJoin,
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


def build_context(
    plan,
    *,
    allow_cost_data: bool = False,
) -> AccessContext:
    return AccessContext(
        request_id="req-day73-cac-001",
        actor_id="analyst-001",
        role=AccessRole.SCOPED_ANALYST,
        dataset_name="beauty_bi_v2",
        target_schema="beauty_bi_v2",
        operation_mode=OperationMode.OBSERVE_ADVISE,
        allowed_metrics=frozenset({"cac"}),
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
        scope_source="day73_cac_fixture",
    )


def plan_payload() -> dict:
    return build_cac_channel_plan().model_dump(
        mode="json"
    )


def test_cac_uses_four_stage_logic() -> None:
    plan = build_cac_channel_plan()

    assert_true(
        isinstance(
            plan.query_logic,
            StagedQueryLogic,
        ),
        "CAC 必须使用 StagedQueryLogic。",
    )

    assert_equal(
        [
            stage.stage_id
            for stage in plan.query_logic.stages
        ],
        [
            "channel_first_paid_history",
            "windowed_channel_acquisition",
            "channel_spend",
            "final",
        ],
        "CAC 应按完整历史、窗口获客、窗口费用、最终比率四阶段执行。",
    )


def test_cac_uses_customer_x_channel_identity() -> None:
    plan = build_cac_channel_plan()

    history = (
        plan.scope_contract.history_contract
    )

    assert_equal(
        history.sequence_partition_by,
        (
            "fo.customer_id",
            "fo.channel_id",
        ),
        (
            "V2 CAC 分母必须基于 customer × channel 新客，"
            "不能退回 V1 品牌首单归因。"
        ),
    )


def test_history_stage_has_no_analysis_window() -> None:
    plan = build_cac_channel_plan()

    history_stage = plan.query_logic.stages[0]
    text = history_stage.filter_text()

    assert_true(
        ":analysis_start_date" not in text,
        "完整历史 Stage 不得先使用分析开始日期。",
    )

    assert_true(
        ":analysis_end_date" not in text,
        "完整历史 Stage 不得先使用分析结束日期。",
    )


def test_acquisition_window_is_after_first_event() -> None:
    plan = build_cac_channel_plan()

    stage = plan.query_logic.stages[1]
    text = stage.filter_text()

    assert_true(
        ":analysis_start_date" in text,
        "首次事件确定后必须应用 analysis_start_date。",
    )

    assert_true(
        ":analysis_end_date" in text,
        "首次事件确定后必须应用 analysis_end_date。",
    )

    assert_true(
        "first_channel_paid_at" in text,
        "分析窗口必须作用于真实渠道首次支付时间。",
    )


def test_spend_uses_same_analysis_window_parameters() -> None:
    plan = build_cac_channel_plan()

    acquisition_text = (
        plan.query_logic.stages[1]
        .filter_text()
    )

    spend_text = (
        plan.query_logic.stages[2]
        .filter_text()
    )

    for parameter in (
        ":analysis_start_date",
        ":analysis_end_date",
    ):
        assert_true(
            parameter in acquisition_text,
            "Acquisition Stage 必须使用统一分析日期参数。",
        )

        assert_true(
            parameter in spend_text,
            "Spend Stage 必须使用统一分析日期参数。",
        )


def test_cac_declares_cross_fact_time_window() -> None:
    plan = build_cac_channel_plan()

    assert_equal(
        plan.semantic_contract.time_window_columns,
        (
            "fact_orders.paid_at",
            "fact_marketing_spend.spend_date",
        ),
        "CAC 必须显式声明订单与费用共享时间窗口。",
    )


def test_cac_final_stage_joins_acquisition_and_spend() -> None:
    plan = build_cac_channel_plan()
    final_stage = plan.query_logic.stages[-1]

    stage_joins = [
        join
        for join in final_stage.joins
        if isinstance(join, StageJoin)
    ]

    assert_equal(
        len(stage_joins),
        1,
        "CAC Final Stage 应 JOIN 一个 Spend Stage。",
    )

    join = stage_joins[0]

    assert_equal(
        join.stage_id,
        "channel_spend",
        "CAC Final Stage 必须 JOIN channel_spend。",
    )

    assert_equal(
        (
            join.conditions[0].left,
            join.conditions[0].right,
        ),
        (
            "wca.channel_id",
            "csp.channel_id",
        ),
        "Acquisition 与 Spend 必须按 channel_id 合并。",
    )


def test_cac_formula_is_spend_over_channel_new_customers() -> None:
    plan = build_cac_channel_plan()

    expression = (
        plan.query_logic.stages[-1]
        .outputs[1]
        .expression
    )

    assert_equal(
        expression,
        (
            "csp.marketing_spend_amount "
            "/ NULLIF("
            "wca.channel_paid_new_customer_count, 0)"
        ),
        "CAC 必须是 Spend / Channel Paid New Customers。",
    )


def test_cac_default_sort_is_lower_first() -> None:
    plan = build_cac_channel_plan()

    assert_equal(
        plan.default_sort.direction,
        "asc",
        "CAC 默认应从低到高排序。",
    )


def test_cac_resource_contract_is_authorizable() -> None:
    plan = build_cac_channel_plan()

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
        "CAC Table/Column Resource Contract 应可授权。",
    )


def test_global_history_gate_fails_closed_for_region() -> None:
    plan = build_cac_channel_plan()

    decision = evaluate_global_history_scope(
        plan
    )

    assert_equal(
        decision.allowed,
        False,
        "CAC 的 Region Scope 需要后置执行，当前必须 fail closed。",
    )

    assert_equal(
        decision.reason_code,
        (
            GlobalHistoryScopeReason
            .POST_SEQUENCE_SCOPE_REQUIRED
        ),
        "应返回 post_sequence_scope_required。",
    )

    assert_equal(
        decision.safe_pre_sequence_dimensions,
        frozenset(
            {ScopeDimension.CHANNEL}
        ),
        "Channel 应保留为 pre-sequence safe。",
    )

    assert_equal(
        decision.unsupported_post_sequence_dimensions,
        frozenset(
            {ScopeDimension.REGION}
        ),
        "Region 必须明确标记为 post-sequence required。",
    )

    assert_equal(
        decision.retryable,
        False,
        "Global History Scope Placement 错误不得 Repair。",
    )


def test_row_scope_path_gate_fails_for_marketing_region() -> None:
    plan = build_cac_channel_plan()

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
        "Marketing Spend 无 Region Anchor 时 CAC 必须 fail closed。",
    )

    assert_equal(
        decision.reason_code,
        RowScopeReason.UNSUPPORTED_SCOPE_PATH,
        "应返回 unsupported_scope_path。",
    )

    assert_true(
        "region:fact_marketing_spend"
        in decision.unsupported_scope_paths,
        "应明确指出 fact_marketing_spend 缺少 Region Path。",
    )

    assert_equal(
        decision.retryable,
        False,
        "Scope Path 错误不得进入 SQL Repair。",
    )


def test_channel_targets_can_bind_independently() -> None:
    plan = build_cac_channel_plan()

    channel_only = plan_row_scope(
        build_context(
            plan,
            allow_cost_data=True,
        ),
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
        "订单与费用事实都应支持 Channel Scope。",
    )

    binding = build_scoped_query_contract(
        channel_only.plan,
        targets=plan.to_scope_targets(),
    )

    assert_equal(
        binding.allowed,
        True,
        "两个事实 Target 应能分别绑定 Channel Predicate。",
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
        in fragments["cac_channel_acquisition"],
        "Acquisition Predicate 必须落到订单 channel_id。",
    )

    assert_true(
        "fms.channel_id"
        in fragments["cac_channel_spend"],
        "Spend Predicate 必须落到营销费用 channel_id。",
    )


def test_history_stage_rejects_window_parameter() -> None:
    data = plan_payload()

    data["query_logic"]["stages"][0][
        "filters"
    ].append(
        "fo.paid_at >= :analysis_start_date"
    )

    try:
        QueryPlanV2.model_validate(data)
    except ValidationError:
        return

    raise AssertionError(
        "CAC History Stage 使用分析窗口参数必须拒绝。"
    )


def test_cac_binding_is_business_confidential() -> None:
    plan = build_cac_channel_plan()

    binding = next(
        binding
        for binding in (
            plan.result_contract.field_bindings
        )
        if binding.output_field == "cac"
    )

    assert_equal(
        binding.category,
        SensitiveDataCategory.BUSINESS_CONFIDENTIAL,
        "CAC 使用 spend_amount，应按经营敏感结果保护。",
    )

    assert_true(
        "fact_marketing_spend.spend_amount"
        in binding.source_columns,
        "CAC Result Binding 必须记录 spend_amount 来源。",
    )


def test_cac_is_denied_by_default() -> None:
    plan = build_cac_channel_plan()

    result = protect_result_rows(
        context=build_context(plan),
        rows=[
            {
                "channel_name": "示例渠道",
                "cac": 120.0,
                "__group_size": 100,
            }
        ],
        contract=plan.result_contract,
    )

    assert_equal(
        result.success,
        False,
        "默认策略必须拒绝 Business Confidential CAC。",
    )

    assert_equal(
        result.reason_code,
        ProtectionReason.COST_DATA_NOT_ALLOWED,
        "当前统一经营敏感策略应返回 cost_data_not_allowed。",
    )


def test_cac_can_be_explicitly_allowed() -> None:
    plan = build_cac_channel_plan()

    result = protect_result_rows(
        context=build_context(
            plan,
            allow_cost_data=True,
        ),
        rows=[
            {
                "channel_name": "示例渠道",
                "cac": 120.0,
                "__group_size": 100,
            }
        ],
        contract=plan.result_contract,
    )

    assert_equal(
        result.success,
        True,
        "显式允许经营敏感数据后 CAC 应可返回。",
    )

    assert_equal(
        result.rows,
        (
            {
                "channel_name": "示例渠道",
                "cac": 120.0,
            },
        ),
        "__group_size 必须隐藏。",
    )


def test_cac_is_channel_only_for_now() -> None:
    plan = build_cac_channel_plan()

    assert_equal(
        plan.result_grain,
        "channel",
        "当前只冻结 Channel CAC。",
    )


def run_tests() -> None:
    tests = [
        test_cac_uses_four_stage_logic,
        test_cac_uses_customer_x_channel_identity,
        test_history_stage_has_no_analysis_window,
        test_acquisition_window_is_after_first_event,
        test_spend_uses_same_analysis_window_parameters,
        test_cac_declares_cross_fact_time_window,
        test_cac_final_stage_joins_acquisition_and_spend,
        test_cac_formula_is_spend_over_channel_new_customers,
        test_cac_default_sort_is_lower_first,
        test_cac_resource_contract_is_authorizable,
        test_global_history_gate_fails_closed_for_region,
        test_row_scope_path_gate_fails_for_marketing_region,
        test_channel_targets_can_bind_independently,
        test_history_stage_rejects_window_parameter,
        test_cac_binding_is_business_confidential,
        test_cac_is_denied_by_default,
        test_cac_can_be_explicitly_allowed,
        test_cac_is_channel_only_for_now,
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
    print("CAC Query Plan V2 Test Summary")
    print(f"Total: {len(tests)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    run_tests()
