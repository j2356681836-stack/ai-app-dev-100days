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
from app.semantic_layer.brand_new_customer_query_plan_v2 import (
    build_brand_paid_new_customer_count_overall_plan,
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
        request_id="req-day73-brand-new-001",
        actor_id="analyst-001",
        role=AccessRole.SCOPED_ANALYST,
        dataset_name="beauty_bi_v2",
        target_schema="beauty_bi_v2",
        operation_mode=OperationMode.OBSERVE_ADVISE,
        allowed_metrics=frozenset(
            {"brand_paid_new_customer_count"}
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
        scope_source="day73_brand_new_fixture",
    )


def plan_payload() -> dict:
    return (
        build_brand_paid_new_customer_count_overall_plan()
        .model_dump(mode="json")
    )


def test_brand_new_customer_uses_three_stages() -> None:
    plan = (
        build_brand_paid_new_customer_count_overall_plan()
    )

    assert_true(
        isinstance(
            plan.query_logic,
            StagedQueryLogic,
        ),
        "品牌支付新客必须使用 StagedQueryLogic。",
    )

    assert_equal(
        [
            stage.stage_id
            for stage in plan.query_logic.stages
        ],
        [
            "brand_order_sequence",
            "true_brand_first_paid",
            "windowed_brand_acquisition",
        ],
        "品牌新客应按排序、真实首单、分析窗口三阶段执行。",
    )


def test_brand_identity_is_customer_only() -> None:
    plan = (
        build_brand_paid_new_customer_count_overall_plan()
    )

    history = (
        plan.scope_contract.history_contract
    )

    assert_equal(
        history.sequence_partition_by,
        ("fo.customer_id",),
        (
            "品牌新客 identity 必须只有 customer_id，"
            "不得混入 channel_id。"
        ),
    )


def test_brand_sequence_order_is_deterministic() -> None:
    plan = (
        build_brand_paid_new_customer_count_overall_plan()
    )

    history = (
        plan.scope_contract.history_contract
    )

    assert_equal(
        history.sequence_order_by,
        (
            "fo.paid_at",
            "fo.order_id",
        ),
        "同一支付时刻必须用 order_id 提供稳定首单 tie-break。",
    )

    expression = (
        plan.query_logic.stages[0]
        .outputs[-1]
        .expression
    )

    assert_true(
        "PARTITION BY fo.customer_id"
        in expression,
        "ROW_NUMBER 必须按 customer 分区。",
    )

    assert_true(
        "ORDER BY fo.paid_at ASC, fo.order_id ASC"
        in expression,
        "ROW_NUMBER 必须按 paid_at + order_id 稳定排序。",
    )


def test_history_stage_has_no_analysis_window() -> None:
    plan = (
        build_brand_paid_new_customer_count_overall_plan()
    )

    text = (
        plan.query_logic.stages[0]
        .filter_text()
    )

    assert_true(
        ":analysis_start_date" not in text,
        "品牌完整历史排序前不得过滤分析开始日期。",
    )

    assert_true(
        ":analysis_end_date" not in text,
        "品牌完整历史排序前不得过滤分析结束日期。",
    )


def test_true_first_stage_keeps_first_event_dimensions() -> None:
    plan = (
        build_brand_paid_new_customer_count_overall_plan()
    )

    stage = plan.query_logic.stages[1]

    assert_equal(
        stage.filters,
        ("bos.event_rank = 1",),
        "真实品牌首单必须只保留 event_rank = 1。",
    )

    fields = {
        output.field
        for output in stage.outputs
    }

    assert_true(
        {
            "customer_id",
            "first_paid_at",
            "first_channel_id",
            "first_shipping_region_id",
        }.issubset(fields),
        (
            "真实首单必须保存 Channel / Region 归属，"
            "供未来 post-sequence Scope 使用。"
        ),
    )


def test_analysis_window_is_applied_after_true_first() -> None:
    plan = (
        build_brand_paid_new_customer_count_overall_plan()
    )

    stage = plan.query_logic.stages[2]
    text = stage.filter_text()

    assert_true(
        "bfp.first_paid_at" in text,
        "分析窗口必须作用于真实品牌首单时间。",
    )

    assert_true(
        ":analysis_start_date" in text,
        "Window Stage 必须使用 analysis_start_date。",
    )

    assert_true(
        ":analysis_end_date" in text,
        "Window Stage 必须使用 analysis_end_date。",
    )


def test_no_scope_dimension_is_safe_before_brand_sequence() -> None:
    plan = (
        build_brand_paid_new_customer_count_overall_plan()
    )

    history = (
        plan.scope_contract.history_contract
    )

    assert_equal(
        history.pre_sequence_scope_dimensions(),
        frozenset(),
        (
            "品牌首单 identity 只有 customer，"
            "Region / Channel 都不能提前过滤。"
        ),
    )


def test_region_and_channel_are_post_sequence() -> None:
    plan = (
        build_brand_paid_new_customer_count_overall_plan()
    )

    history = (
        plan.scope_contract.history_contract
    )

    assert_equal(
        history.post_sequence_scope_dimensions,
        frozenset(
            {
                ScopeDimension.REGION,
                ScopeDimension.CHANNEL,
            }
        ),
        "品牌新客 Region + Channel 都必须后置。",
    )


def test_global_history_gate_fails_closed() -> None:
    plan = (
        build_brand_paid_new_customer_count_overall_plan()
    )

    decision = evaluate_global_history_scope(
        plan
    )

    assert_equal(
        decision.allowed,
        False,
        (
            "当前 Row Scope Engine 不能安全执行品牌首单的 "
            "post-sequence Region/Channel Scope。"
        ),
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
        decision.unsupported_post_sequence_dimensions,
        frozenset(
            {
                ScopeDimension.REGION,
                ScopeDimension.CHANNEL,
            }
        ),
        "Decision 必须明确两个后置 Scope。",
    )

    assert_equal(
        decision.retryable,
        False,
        "Scope placement 语义错误不得 Repair。",
    )


def test_physical_row_scope_paths_exist_but_are_not_semantically_safe() -> None:
    """
    Important distinction:
    fact_orders technically supports both predicates.
    That does not mean they are safe before brand-first sequencing.
    """
    plan = (
        build_brand_paid_new_customer_count_overall_plan()
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
        "fact_orders 本身应存在 Region + Channel Scope Path。",
    )

    binding = build_scoped_query_contract(
        decision.plan,
        targets=plan.to_scope_targets(),
    )

    assert_equal(
        binding.allowed,
        True,
        "物理 Predicate Path 应能成功绑定。",
    )

    assert_equal(
        len(binding.contract.predicates),
        2,
        "物理层应存在 Region + Channel 两个 Predicate。",
    )

    history_decision = (
        evaluate_global_history_scope(plan)
    )

    assert_equal(
        history_decision.allowed,
        False,
        (
            "即使 Path 存在，Placement 不安全仍必须 fail closed。"
        ),
    )


def test_resource_contract_is_authorizable() -> None:
    plan = (
        build_brand_paid_new_customer_count_overall_plan()
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
        "品牌新客 Table/Column Resource Contract 应可授权。",
    )


def test_channel_cannot_be_falsely_marked_pre_sequence_safe() -> None:
    data = plan_payload()

    data["scope_contract"][
        "history_contract"
    ][
        "pre_sequence_scope_bindings"
    ] = [
        {
            "dimension": "channel",
            "partition_reference": "fo.channel_id",
        }
    ]

    data["scope_contract"][
        "history_contract"
    ][
        "post_sequence_scope_dimensions"
    ] = [
        "region",
    ]

    try:
        QueryPlanV2.model_validate(data)
    except ValidationError:
        return

    raise AssertionError(
        (
            "channel_id 不属于品牌 sequence_partition_by，"
            "不得伪装成 pre-sequence safe。"
        )
    )


def test_result_is_ordinary_and_group_size_is_hidden() -> None:
    plan = (
        build_brand_paid_new_customer_count_overall_plan()
    )

    result = protect_result_rows(
        context=build_context(plan),
        rows=[
            {
                "brand_paid_new_customer_count": 120,
                "__group_size": 120,
            }
        ],
        contract=plan.result_contract,
    )

    assert_equal(
        result.success,
        True,
        "品牌新客计数本身是 ordinary 结果。",
    )

    assert_equal(
        result.rows,
        (
            {
                "brand_paid_new_customer_count": 120,
            },
        ),
        "__group_size 必须隐藏。",
    )


def test_group_size_equals_brand_new_customer_population() -> None:
    plan = (
        build_brand_paid_new_customer_count_overall_plan()
    )

    final_stage = plan.query_logic.stages[-1]
    metric = final_stage.outputs[0]
    hidden = final_stage.hidden_control_fields[0]

    assert_equal(
        metric.expression,
        "COUNT(DISTINCT bfp.customer_id)",
        "品牌新客数必须按 distinct customer 统计。",
    )

    assert_equal(
        hidden.expression,
        metric.expression,
        (
            "Overall 品牌新客最小群组控制应基于同一新客 population。"
        ),
    )


def test_brand_new_customer_is_overall_only_for_now() -> None:
    plan = (
        build_brand_paid_new_customer_count_overall_plan()
    )

    assert_equal(
        plan.result_grain,
        "overall",
        "当前只冻结 Overall 品牌支付新客数。",
    )


def run_tests() -> None:
    tests = [
        test_brand_new_customer_uses_three_stages,
        test_brand_identity_is_customer_only,
        test_brand_sequence_order_is_deterministic,
        test_history_stage_has_no_analysis_window,
        test_true_first_stage_keeps_first_event_dimensions,
        test_analysis_window_is_applied_after_true_first,
        test_no_scope_dimension_is_safe_before_brand_sequence,
        test_region_and_channel_are_post_sequence,
        test_global_history_gate_fails_closed,
        test_physical_row_scope_paths_exist_but_are_not_semantically_safe,
        test_resource_contract_is_authorizable,
        test_channel_cannot_be_falsely_marked_pre_sequence_safe,
        test_result_is_ordinary_and_group_size_is_hidden,
        test_group_size_equals_brand_new_customer_population,
        test_brand_new_customer_is_overall_only_for_now,
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
        "Brand Paid New Customer Query Plan V2 Test Summary"
    )
    print(f"Total: {len(tests)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    run_tests()
