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
    ScopeDimension,
    plan_row_scope,
)
from app.governance.row_scope_binding import (
    build_scoped_query_contract,
)
from app.governance.sensitive_data import (
    protect_result_rows,
)
from app.semantic_layer.channel_new_customer_query_plan_v2 import (
    build_channel_paid_new_customer_count_channel_plan,
)
from app.semantic_layer.global_history_scope import (
    GlobalHistoryScopeReason,
    evaluate_global_history_scope,
)
from app.semantic_layer.query_plan_v2_models import (
    QueryPlanV2,
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
        request_id="req-day73-channel-new-001",
        actor_id="analyst-001",
        role=AccessRole.SCOPED_ANALYST,
        dataset_name="beauty_bi_v2",
        target_schema="beauty_bi_v2",
        operation_mode=OperationMode.OBSERVE_ADVISE,
        allowed_metrics=frozenset(
            {"channel_paid_new_customer_count"}
        ),
        allowed_tables=plan.resource_contract.required_tables,
        allowed_columns=plan.resource_contract.required_columns,
        denied_columns=frozenset(),
        allowed_region_codes=frozenset(
            {"EAST", "SOUTH"}
        ),
        allowed_channel_codes=frozenset(
            {"TMALL", "JD"}
        ),
        sensitive_data_policy=SensitiveDataPolicy(),
        policy_version="governance_v1",
        scope_source="day73_channel_new_fixture",
    )


def plan_payload() -> dict:
    return (
        build_channel_paid_new_customer_count_channel_plan()
        .model_dump(mode="json")
    )


def test_channel_new_customer_uses_three_stages() -> None:
    plan = (
        build_channel_paid_new_customer_count_channel_plan()
    )

    assert_true(
        isinstance(
            plan.query_logic,
            StagedQueryLogic,
        ),
        "渠道支付新客必须使用 StagedQueryLogic。",
    )

    assert_equal(
        [
            stage.stage_id
            for stage in plan.query_logic.stages
        ],
        [
            "channel_first_paid_history",
            "windowed_channel_acquisition",
            "final",
        ],
        "渠道新客应按完整历史、窗口获客、最终展示三阶段执行。",
    )


def test_identity_is_customer_x_channel() -> None:
    plan = (
        build_channel_paid_new_customer_count_channel_plan()
    )

    history = (
        plan.scope_contract.history_contract
    )

    assert_equal(
        history.sequence_partition_by,
        (
            "fo.customer_id",
            "fo.channel_id",
        ),
        "渠道支付新客 identity 必须是 customer × channel。",
    )


def test_channel_first_paid_is_determined_before_window() -> None:
    plan = (
        build_channel_paid_new_customer_count_channel_plan()
    )

    history_stage = plan.query_logic.stages[0]
    window_stage = plan.query_logic.stages[1]

    history_text = history_stage.filter_text()
    window_text = window_stage.filter_text()

    assert_true(
        ":analysis_start_date" not in history_text,
        "完整渠道历史不得先过滤 analysis_start_date。",
    )

    assert_true(
        ":analysis_end_date" not in history_text,
        "完整渠道历史不得先过滤 analysis_end_date。",
    )

    assert_true(
        "first_channel_paid_at" in window_text,
        "分析窗口必须作用于真实渠道首次支付时间。",
    )

    assert_true(
        ":analysis_start_date" in window_text,
        "Window Stage 必须使用 analysis_start_date。",
    )

    assert_true(
        ":analysis_end_date" in window_text,
        "Window Stage 必须使用 analysis_end_date。",
    )


def test_channel_scope_is_safe_before_sequence() -> None:
    plan = (
        build_channel_paid_new_customer_count_channel_plan()
    )

    history = (
        plan.scope_contract.history_contract
    )

    assert_equal(
        history.pre_sequence_scope_dimensions(),
        frozenset(
            {ScopeDimension.CHANNEL}
        ),
        "Channel 应为 pre-sequence safe。",
    )

    binding = (
        history.pre_sequence_scope_bindings[0]
    )

    assert_equal(
        binding.partition_reference,
        "fo.channel_id",
        (
            "Channel Scope 的安全性必须来自 channel_id "
            "属于 sequence identity。"
        ),
    )


def test_region_scope_is_post_sequence() -> None:
    plan = (
        build_channel_paid_new_customer_count_channel_plan()
    )

    history = (
        plan.scope_contract.history_contract
    )

    assert_equal(
        history.post_sequence_scope_dimensions,
        frozenset(
            {ScopeDimension.REGION}
        ),
        "Region 必须在渠道首次事件确定后处理。",
    )


def test_global_history_gate_fails_closed_for_region() -> None:
    plan = (
        build_channel_paid_new_customer_count_channel_plan()
    )

    decision = evaluate_global_history_scope(
        plan
    )

    assert_equal(
        decision.allowed,
        False,
        "当前 Engine 无法安全执行 post-sequence Region Scope。",
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
        "Decision 应保留安全的 Channel Scope。",
    )

    assert_equal(
        decision.unsupported_post_sequence_dimensions,
        frozenset(
            {ScopeDimension.REGION}
        ),
        "Decision 应明确 Region 需要后置执行。",
    )

    assert_equal(
        decision.retryable,
        False,
        "Scope placement 问题不得进入 SQL Repair。",
    )


def test_physical_region_and_channel_paths_exist() -> None:
    """
    fact_orders has both physical paths.
    Only Region placement is semantically unsafe before first-event logic.
    """
    plan = (
        build_channel_paid_new_customer_count_channel_plan()
    )

    decision = plan_row_scope(
        build_context(plan),
        source_tables=(
            plan.scope_contract.source_tables
        ),
        required_dimensions=(
            plan.scope_contract.required_dimensions
        ),
    )

    assert_equal(
        decision.allowed,
        True,
        "fact_orders 本身应具有 Region + Channel Scope Path。",
    )

    binding = build_scoped_query_contract(
        decision.plan,
        targets=plan.to_scope_targets(),
    )

    assert_equal(
        binding.allowed,
        True,
        "物理 Row Scope Predicate 应能成功绑定。",
    )

    assert_equal(
        len(binding.contract.predicates),
        2,
        "物理层应存在 Region + Channel 两个 Predicate。",
    )

    assert_equal(
        evaluate_global_history_scope(plan).allowed,
        False,
        (
            "有 Predicate Path 不能替代 Global History "
            "Placement Safety。"
        ),
    )


def test_resource_contract_is_authorizable() -> None:
    plan = (
        build_channel_paid_new_customer_count_channel_plan()
    )

    decision = authorize_resources(
        build_context(plan),
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
        "渠道新客 Table/Column Resource Contract 应可授权。",
    )


def test_channel_cannot_be_removed_from_partition() -> None:
    data = plan_payload()

    data["scope_contract"][
        "history_contract"
    ][
        "sequence_partition_by"
    ] = [
        "fo.customer_id",
    ]

    try:
        QueryPlanV2.model_validate(data)
    except ValidationError:
        return

    raise AssertionError(
        (
            "当 Channel 声明为 pre-sequence safe 时，"
            "channel_id 必须保留在 sequence partition。"
        )
    )


def test_region_cannot_be_marked_pre_sequence_safe() -> None:
    data = plan_payload()

    data["scope_contract"][
        "history_contract"
    ][
        "pre_sequence_scope_bindings"
    ].append(
        {
            "dimension": "region",
            "partition_reference": "fo.shipping_region_id",
        }
    )

    data["scope_contract"][
        "history_contract"
    ][
        "post_sequence_scope_dimensions"
    ] = []

    try:
        QueryPlanV2.model_validate(data)
    except ValidationError:
        return

    raise AssertionError(
        (
            "shipping_region_id 不属于渠道 first-event identity，"
            "Region 不得伪装成 pre-sequence safe。"
        )
    )


def test_result_is_ordinary_and_group_size_is_hidden() -> None:
    plan = (
        build_channel_paid_new_customer_count_channel_plan()
    )

    result = protect_result_rows(
        context=build_context(plan),
        rows=[
            {
                "channel_name": "示例渠道",
                "channel_paid_new_customer_count": 80,
                "__group_size": 80,
            }
        ],
        contract=plan.result_contract,
    )

    assert_equal(
        result.success,
        True,
        "渠道新客计数是 ordinary 结果。",
    )

    assert_equal(
        result.rows,
        (
            {
                "channel_name": "示例渠道",
                "channel_paid_new_customer_count": 80,
            },
        ),
        "__group_size 必须隐藏。",
    )


def test_group_size_equals_channel_new_customer_population() -> None:
    plan = (
        build_channel_paid_new_customer_count_channel_plan()
    )

    final_stage = plan.query_logic.stages[-1]
    metric = final_stage.outputs[1]
    hidden = final_stage.hidden_control_fields[0]

    assert_equal(
        metric.expression,
        "wca.channel_paid_new_customer_count",
        "Final Metric 必须直接使用窗口获客人数。",
    )

    assert_equal(
        hidden.expression,
        metric.expression,
        (
            "每渠道最小群组控制应基于同一渠道新客 population。"
        ),
    )


def test_channel_new_customer_is_channel_grain() -> None:
    plan = (
        build_channel_paid_new_customer_count_channel_plan()
    )

    assert_equal(
        plan.result_grain,
        "channel",
        "渠道支付新客正式候选必须是 Channel Grain。",
    )


def test_brand_and_channel_identity_are_not_confused() -> None:
    plan = (
        build_channel_paid_new_customer_count_channel_plan()
    )

    expression = (
        plan.query_logic.stages[0]
        .outputs[-1]
        .expression
    )

    assert_equal(
        expression,
        "MIN(fo.paid_at)",
        (
            "渠道首付按 customer × channel 聚合后取 MIN(paid_at)；"
            "它不是品牌 ROW_NUMBER(customer) 首单模型。"
        ),
    )


def run_tests() -> None:
    tests = [
        test_channel_new_customer_uses_three_stages,
        test_identity_is_customer_x_channel,
        test_channel_first_paid_is_determined_before_window,
        test_channel_scope_is_safe_before_sequence,
        test_region_scope_is_post_sequence,
        test_global_history_gate_fails_closed_for_region,
        test_physical_region_and_channel_paths_exist,
        test_resource_contract_is_authorizable,
        test_channel_cannot_be_removed_from_partition,
        test_region_cannot_be_marked_pre_sequence_safe,
        test_result_is_ordinary_and_group_size_is_hidden,
        test_group_size_equals_channel_new_customer_population,
        test_channel_new_customer_is_channel_grain,
        test_brand_and_channel_identity_are_not_confused,
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
    print(
        "Channel Paid New Customer Query Plan V2 Test Summary"
    )
    print(f"Total: {len(tests)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    run_tests()
