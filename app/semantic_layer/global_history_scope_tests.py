from pydantic import ValidationError

from app.governance.row_scope import (
    ScopeDimension,
)
from app.semantic_layer.global_history_query_plan_v2_sample import (
    build_channel_paid_new_customer_count_channel_plan,
)
from app.semantic_layer.global_history_scope import (
    GlobalHistoryScopeReason,
    evaluate_global_history_scope,
)
from app.semantic_layer.query_plan_v2_models import (
    QueryPlanV2,
    ScopeMode,
)


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(
            f"{message}\nExpected: {expected}\nActual: {actual}"
        )


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def payload() -> dict:
    return (
        build_channel_paid_new_customer_count_channel_plan()
        .model_dump(mode="json")
    )


def test_sample_uses_global_history_mode() -> None:
    plan = (
        build_channel_paid_new_customer_count_channel_plan()
    )

    assert_equal(
        plan.scope_contract.scope_mode,
        ScopeMode.GLOBAL_HISTORY_REQUIRED,
        "渠道支付新客必须声明 global_history_required。",
    )

    assert_true(
        plan.scope_contract.history_contract
        is not None,
        "Global History Plan 必须包含 history_contract。",
    )


def test_channel_first_identity_is_customer_x_channel() -> None:
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
        (
            "V2 渠道支付新客 identity 必须是 "
            "customer × channel，不得退回 V1 品牌首单口径。"
        ),
    )


def test_history_stage_has_no_analysis_window() -> None:
    plan = (
        build_channel_paid_new_customer_count_channel_plan()
    )

    history_stage = (
        plan.query_logic.stages[0]
    )

    text = history_stage.filter_text()

    assert_true(
        ":analysis_start_date" not in text,
        "History Stage 不得先过滤分析开始日期。",
    )

    assert_true(
        ":analysis_end_date" not in text,
        "History Stage 不得先过滤分析结束日期。",
    )


def test_analysis_window_is_after_history() -> None:
    plan = (
        build_channel_paid_new_customer_count_channel_plan()
    )

    history = (
        plan.scope_contract.history_contract
    )

    assert_equal(
        history.history_stage_id,
        "channel_first_paid_history",
        "History Stage ID 不正确。",
    )

    assert_equal(
        history.analysis_window_stage_id,
        "windowed_channel_acquisition",
        "Analysis Window 必须在 first event 后应用。",
    )

    window_stage = (
        plan.query_logic.stages[1]
    )

    text = window_stage.filter_text()

    assert_true(
        ":analysis_start_date" in text,
        "Window Stage 必须使用 analysis_start_date。",
    )

    assert_true(
        ":analysis_end_date" in text,
        "Window Stage 必须使用 analysis_end_date。",
    )


def test_channel_scope_is_explicitly_safe_before_sequence() -> None:
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
        "Channel 应显式声明为 pre-sequence safe。",
    )

    binding = (
        history.pre_sequence_scope_bindings[0]
    )

    assert_equal(
        binding.partition_reference,
        "fo.channel_id",
        (
            "Channel Scope 只有因为 channel_id "
            "属于事件 identity partition 才能提前应用。"
        ),
    )


def test_region_scope_requires_post_sequence_enforcement() -> None:
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
        (
            "Region 不属于 channel-first identity，"
            "必须在首次事件确定后处理。"
        ),
    )


def test_current_engine_fails_closed_on_post_sequence_scope() -> None:
    plan = (
        build_channel_paid_new_customer_count_channel_plan()
    )

    decision = evaluate_global_history_scope(
        plan
    )

    assert_equal(
        decision.allowed,
        False,
        (
            "当前仅支持 physical-target predicate 的 Row Scope "
            "不能安全执行需要 post-sequence Region Scope 的首事件指标。"
        ),
    )

    assert_equal(
        decision.reason_code,
        (
            GlobalHistoryScopeReason
            .POST_SEQUENCE_SCOPE_REQUIRED
        ),
        "应明确返回 post_sequence_scope_required。",
    )

    assert_equal(
        decision.safe_pre_sequence_dimensions,
        frozenset(
            {ScopeDimension.CHANNEL}
        ),
        "Decision 应保留已证明安全的 Channel Scope。",
    )

    assert_equal(
        decision.unsupported_post_sequence_dimensions,
        frozenset(
            {ScopeDimension.REGION}
        ),
        "Decision 应明确指出 Region 需要后置执行。",
    )

    assert_equal(
        decision.retryable,
        False,
        "Scope placement 错误不得进入 SQL Repair。",
    )


def test_pre_sequence_binding_must_be_partition_key() -> None:
    data = payload()

    data["scope_contract"][
        "history_contract"
    ][
        "pre_sequence_scope_bindings"
    ][0][
        "partition_reference"
    ] = "fo.shipping_region_id"

    try:
        QueryPlanV2.model_validate(data)
    except ValidationError:
        return

    raise AssertionError(
        "Pre-sequence Scope 不能绑定到 sequence identity 外字段。"
    )


def test_global_history_mode_requires_history_contract() -> None:
    data = payload()

    data["scope_contract"][
        "history_contract"
    ] = None

    try:
        QueryPlanV2.model_validate(data)
    except ValidationError:
        return

    raise AssertionError(
        "global_history_required 不得缺少 history_contract。"
    )


def test_predicate_safe_rejects_history_contract() -> None:
    data = payload()

    data["scope_contract"][
        "scope_mode"
    ] = "predicate_safe"

    try:
        QueryPlanV2.model_validate(data)
    except ValidationError:
        return

    raise AssertionError(
        "predicate_safe Plan 不得偷偷携带 Global History Contract。"
    )


def test_history_window_stage_order_is_enforced() -> None:
    data = payload()

    data["scope_contract"][
        "history_contract"
    ][
        "history_stage_id"
    ] = "windowed_channel_acquisition"

    data["scope_contract"][
        "history_contract"
    ][
        "analysis_window_stage_id"
    ] = "channel_first_paid_history"

    try:
        QueryPlanV2.model_validate(data)
    except ValidationError:
        return

    raise AssertionError(
        "Analysis Window 不得先于 true-first-event sequencing。"
    )


def test_history_stage_rejects_window_parameters() -> None:
    data = payload()

    data["query_logic"]["stages"][0][
        "filters"
    ].append(
        (
            "CAST(fo.paid_at AS DATE) "
            ">= :analysis_start_date"
        )
    )

    try:
        QueryPlanV2.model_validate(data)
    except ValidationError:
        return

    raise AssertionError(
        "History Stage 一旦使用分析窗口参数必须拒绝。"
    )


def test_window_stage_requires_all_declared_parameters() -> None:
    data = payload()

    data["query_logic"]["stages"][1][
        "filters"
    ] = [
        (
            "CAST(cfp.first_channel_paid_at AS DATE) "
            ">= :analysis_start_date"
        )
    ]

    try:
        QueryPlanV2.model_validate(data)
    except ValidationError:
        return

    raise AssertionError(
        "Window Stage 缺少 analysis_end_date 必须拒绝。"
    )


def test_pre_post_dimensions_must_cover_required_scope() -> None:
    data = payload()

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
        "Global History pre/post dimensions 必须覆盖 required_dimensions。"
    )


def run_tests() -> None:
    tests = [
        test_sample_uses_global_history_mode,
        test_channel_first_identity_is_customer_x_channel,
        test_history_stage_has_no_analysis_window,
        test_analysis_window_is_after_history,
        test_channel_scope_is_explicitly_safe_before_sequence,
        test_region_scope_requires_post_sequence_enforcement,
        test_current_engine_fails_closed_on_post_sequence_scope,
        test_pre_sequence_binding_must_be_partition_key,
        test_global_history_mode_requires_history_contract,
        test_predicate_safe_rejects_history_contract,
        test_history_window_stage_order_is_enforced,
        test_history_stage_rejects_window_parameters,
        test_window_stage_requires_all_declared_parameters,
        test_pre_post_dimensions_must_cover_required_scope,
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
    print("Global History Contract V2 Test Summary")
    print(f"Total: {len(tests)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    run_tests()
