from pathlib import Path
import tempfile

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
from app.semantic_layer.global_history_scope import (
    GlobalHistoryScopeReason,
    evaluate_global_history_scope,
)
from app.semantic_layer.query_plan_v2_catalog_builder import (
    build_query_plan_v2_catalog,
    project_query_plan_v2_path,
    write_query_plan_v2_catalog,
)
from app.semantic_layer.query_plan_v2_loader import (
    get_query_plan_v2_by_name,
    get_query_plans_v2_by_metric,
    load_query_plan_v2_catalog,
)
from app.semantic_layer.query_plan_v2_models import (
    QueryLogic,
    ScopeMode,
    StagedQueryLogic,
)


EXPECTED_METRICS = {
    "gmv",
    "gross_margin",
    "gross_margin_rate",
    "refund_rate",
    "roi",
    "cac",
    "brand_paid_new_customer_count",
    "channel_paid_new_customer_count",
    "repeat_customer_rate",
    "member_gmv_share",
    "buyer_count",
    "order_count",
    "units_sold",
    "spending_per_buyer",
    "ipt",
    "aus",
    "purchase_frequency",
    "repeat_customer_count",
    "multi_order_customer_count",
}

NEW_CONFIDENTIAL = {
    "refund_rate_overall_v2": "refund_rate",
    "roi_channel_v2": "roi",
    "cac_channel_v2": "cac",
}

GLOBAL_HISTORY_PLANS = {
    "cac_channel_v2",
    "brand_paid_new_customer_count_overall_v2",
    "channel_paid_new_customer_count_channel_v2",
}


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
        request_id="req-day73-static-runtime-048",
        actor_id="analyst-001",
        role=AccessRole.SCOPED_ANALYST,
        dataset_name="beauty_bi_v2",
        target_schema="beauty_bi_v2",
        operation_mode=OperationMode.OBSERVE_ADVISE,
        allowed_metrics=frozenset(
            EXPECTED_METRICS
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
        scope_source="day73_static_runtime_048",
    )


def test_runtime_catalog_loads_48_plans() -> None:
    assert_equal(
        len(
            load_query_plan_v2_catalog()
            .query_plans
        ),
        48,
        "Runtime Loader 必须加载 48 个静态 Plan。",
    )


def test_runtime_catalog_has_exact_19_metrics() -> None:
    metrics = {
        plan.metric
        for plan in (
            load_query_plan_v2_catalog()
            .query_plans
        )
    }

    assert_equal(
        metrics,
        EXPECTED_METRICS,
        "Runtime Metric 集合必须精确覆盖 19 Metrics。",
    )


def test_static_catalog_semantically_matches_canonical_builder() -> None:
    assert_equal(
        load_query_plan_v2_catalog(),
        build_query_plan_v2_catalog(),
        (
            "Runtime Loader 得到的静态 Catalog "
            "必须与 Canonical Builder 在模型语义上完全一致。"
        ),
    )


def test_static_yaml_bytes_match_canonical_writer() -> None:
    production_path = (
        project_query_plan_v2_path()
    )

    assert_true(
        production_path.exists(),
        (
            "生产 V2 query_plans.yaml 必须存在："
            f"{production_path}"
        ),
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        canonical_path = (
            Path(temp_dir)
            / "query_plans.yaml"
        )

        write_query_plan_v2_catalog(
            canonical_path
        )

        assert_equal(
            production_path.read_bytes(),
            canonical_path.read_bytes(),
            (
                "生产静态 query_plans.yaml 必须与 "
                "Canonical Writer 的字节输出完全一致。"
            ),
        )


def test_runtime_logic_type_counts() -> None:
    plans = (
        load_query_plan_v2_catalog()
        .query_plans
    )

    assert_equal(
        sum(
            isinstance(
                plan.query_logic,
                QueryLogic,
            )
            for plan in plans
        ),
        40,
        "Runtime 应包含 40 个 QueryLogic Plan。",
    )

    assert_equal(
        sum(
            isinstance(
                plan.query_logic,
                StagedQueryLogic,
            )
            for plan in plans
        ),
        8,
        "Runtime 应包含 8 个 StagedQueryLogic Plan。",
    )


def test_metric_lookup_covers_new_metrics() -> None:
    assert_equal(
        len(
            get_query_plans_v2_by_metric(
                "gmv"
            )
        ),
        4,
        "GMV 应继续返回 4 个 Plan。",
    )

    for metric in (
        "refund_rate",
        "roi",
        "cac",
        "brand_paid_new_customer_count",
        "channel_paid_new_customer_count",
    ):
        plans = (
            get_query_plans_v2_by_metric(
                metric
            )
        )

        assert_equal(
            len(plans),
            1,
            f"{metric} 当前应有 1 个正式静态 Plan。",
        )

        assert_true(
            isinstance(
                plans[0].query_logic,
                StagedQueryLogic,
            ),
            f"{metric} 必须保持 StagedQueryLogic。",
        )


def test_all_48_static_plans_are_resource_authorizable() -> None:
    for plan in (
        load_query_plan_v2_catalog()
        .query_plans
    ):
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
            f"{plan.name} 应通过 Table/Column Authorization。",
        )


def test_legacy_43_and_refund_have_current_row_scope_paths() -> None:
    excluded = {
        "roi_channel_v2",
        "cac_channel_v2",
        "brand_paid_new_customer_count_overall_v2",
        "channel_paid_new_customer_count_channel_v2",
    }

    plans = [
        plan
        for plan in (
            load_query_plan_v2_catalog()
            .query_plans
        )
        if plan.name not in excluded
    ]

    assert_equal(
        len(plans),
        44,
        "当前应有旧 43 + Refund 共 44 个 Path-safe Plan。",
    )

    for plan in plans:
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
            f"{plan.name} 应存在当前 Region + Channel Scope Path。",
        )

        binding = build_scoped_query_contract(
            decision.plan,
            targets=plan.to_scope_targets(),
        )

        assert_equal(
            binding.allowed,
            True,
            f"{plan.name} ScopeTarget 应绑定成功。",
        )

        assert_equal(
            len(binding.contract.predicates),
            2,
            f"{plan.name} 应获得 Region + Channel Predicate。",
        )


def test_roi_and_cac_region_paths_fail_closed() -> None:
    for plan_name in (
        "roi_channel_v2",
        "cac_channel_v2",
    ):
        plan = get_query_plan_v2_by_name(
            plan_name
        )

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
            f"{plan_name} 必须因 Marketing Region Path 缺失而拒绝。",
        )

        assert_equal(
            decision.reason_code,
            RowScopeReason.UNSUPPORTED_SCOPE_PATH,
            f"{plan_name} 应返回 unsupported_scope_path。",
        )

        assert_true(
            "region:fact_marketing_spend"
            in decision.unsupported_scope_paths,
            (
                f"{plan_name} 必须明确指出 "
                "region:fact_marketing_spend。"
            ),
        )

        assert_equal(
            decision.retryable,
            False,
            f"{plan_name} Scope Path 错误不得 Repair。",
        )


def test_global_history_plans_fail_closed_on_scope_placement() -> None:
    for plan_name in GLOBAL_HISTORY_PLANS:
        plan = get_query_plan_v2_by_name(
            plan_name
        )

        assert_equal(
            plan.scope_contract.scope_mode,
            ScopeMode.GLOBAL_HISTORY_REQUIRED,
            f"{plan_name} 必须是 global_history_required。",
        )

        decision = (
            evaluate_global_history_scope(
                plan
            )
        )

        assert_equal(
            decision.allowed,
            False,
            f"{plan_name} 当前必须因 post-sequence Scope fail closed。",
        )

        assert_equal(
            decision.reason_code,
            (
                GlobalHistoryScopeReason
                .POST_SEQUENCE_SCOPE_REQUIRED
            ),
            f"{plan_name} 应返回 post_sequence_scope_required。",
        )

        assert_equal(
            decision.retryable,
            False,
            f"{plan_name} Global History 拒绝不得 Repair。",
        )


def test_brand_and_channel_new_have_physical_paths_but_unsafe_placement() -> None:
    for plan_name in (
        "brand_paid_new_customer_count_overall_v2",
        "channel_paid_new_customer_count_channel_v2",
    ):
        plan = get_query_plan_v2_by_name(
            plan_name
        )

        path_decision = plan_row_scope(
            build_context(plan),
            source_tables=(
                plan.scope_contract.source_tables
            ),
            required_dimensions=(
                plan.scope_contract.required_dimensions
            ),
        )

        assert_equal(
            path_decision.allowed,
            True,
            f"{plan_name} fact_orders 物理 Scope Path 应存在。",
        )

        assert_equal(
            (
                evaluate_global_history_scope(
                    plan
                ).allowed
            ),
            False,
            (
                f"{plan_name} 必须证明 Path 存在不代表 "
                "pre-sequence placement 安全。"
            ),
        )


def test_global_history_identities_survive_static_catalog() -> None:
    cac = get_query_plan_v2_by_name(
        "cac_channel_v2"
    )
    channel_new = get_query_plan_v2_by_name(
        "channel_paid_new_customer_count_channel_v2"
    )
    brand_new = get_query_plan_v2_by_name(
        "brand_paid_new_customer_count_overall_v2"
    )

    expected_channel_identity = (
        "fo.customer_id",
        "fo.channel_id",
    )

    assert_equal(
        (
            cac.scope_contract
            .history_contract
            .sequence_partition_by
        ),
        expected_channel_identity,
        "Static CAC 必须保持 customer × channel identity。",
    )

    assert_equal(
        (
            channel_new.scope_contract
            .history_contract
            .sequence_partition_by
        ),
        expected_channel_identity,
        "Static Channel New 必须保持 customer × channel identity。",
    )

    assert_equal(
        (
            brand_new.scope_contract
            .history_contract
            .sequence_partition_by
        ),
        ("fo.customer_id",),
        "Static Brand New 必须保持 customer identity。",
    )


def test_cross_fact_time_windows_survive_static_catalog() -> None:
    expected = (
        "fact_orders.paid_at",
        "fact_marketing_spend.spend_date",
    )

    for plan_name in (
        "roi_channel_v2",
        "cac_channel_v2",
    ):
        plan = get_query_plan_v2_by_name(
            plan_name
        )

        assert_equal(
            (
                plan.semantic_contract
                .time_window_columns
            ),
            expected,
            f"{plan_name} 必须保持 shared cross-fact window。",
        )


def test_refund_semantics_survive_static_catalog() -> None:
    plan = get_query_plan_v2_by_name(
        "refund_rate_overall_v2"
    )

    first_stage = (
        plan.query_logic.stages[0]
    )

    refund_join = next(
        join
        for join in first_stage.joins
        if getattr(join, "table", None)
        == "fact_refunds"
    )

    assert_equal(
        refund_join.join_type,
        "left",
        "Static Refund Rate 必须保持 LEFT JOIN。",
    )

    expression = next(
        output.expression
        for output in first_stage.outputs
        if output.field
        == "completed_refund_amount"
    )

    assert_true(
        "SUM(fr.refund_amount) FILTER"
        in expression,
        "Static Refund Rate 必须保留 Item-level refund preaggregation。",
    )

    assert_true(
        "fr.refund_status = 'completed'"
        in expression,
        "Static Refund Rate 必须保持 completed-only。",
    )


def test_aus_category_remains_absent() -> None:
    assert_equal(
        get_query_plan_v2_by_name(
            "aus_category_v2"
        ),
        None,
        "Runtime 不得出现 aus_category_v2。",
    )


def test_repeat_and_member_semantics_survive_static_catalog() -> None:
    repeat_plan = get_query_plan_v2_by_name(
        "repeat_customer_count_overall_v2"
    )

    multi_plan = get_query_plan_v2_by_name(
        "multi_order_customer_count_overall_v2"
    )

    assert_true(
        "purchase_day_count >= 2"
        in (
            repeat_plan.query_logic
            .stages[-1]
            .outputs[0]
            .expression
        ),
        "Static Repeat Plan 必须保持跨日口径。",
    )

    assert_true(
        "paid_order_count >= 2"
        in (
            multi_plan.query_logic
            .stages[-1]
            .outputs[0]
            .expression
        ),
        "Static Multi-order Plan 必须保持两单口径。",
    )

    member = get_query_plan_v2_by_name(
        "member_gmv_share_overall_v2"
    )

    assert_true(
        "fact_orders.member_level_at_order"
        in member.resource_contract.required_columns,
        "Member Plan 必须保持 payment-time snapshot。",
    )


def test_new_confidential_bindings_survive_static_catalog() -> None:
    for plan_name, field in (
        NEW_CONFIDENTIAL.items()
    ):
        plan = get_query_plan_v2_by_name(
            plan_name
        )

        binding = next(
            item
            for item in (
                plan.result_contract.field_bindings
            )
            if item.output_field == field
        )

        assert_equal(
            binding.category,
            SensitiveDataCategory.BUSINESS_CONFIDENTIAL,
            f"{plan_name} 必须保持 Business Confidential。",
        )


def test_new_confidential_metrics_are_denied_by_default() -> None:
    samples = {
        "refund_rate_overall_v2": {
            "refund_rate": 0.08,
            "__group_size": 100,
        },
        "roi_channel_v2": {
            "channel_name": "示例渠道",
            "roi": 3.2,
            "__group_size": 100,
        },
        "cac_channel_v2": {
            "channel_name": "示例渠道",
            "cac": 120.0,
            "__group_size": 100,
        },
    }

    for plan_name, rows in samples.items():
        plan = get_query_plan_v2_by_name(
            plan_name
        )

        result = protect_result_rows(
            context=build_context(plan),
            rows=[rows],
            contract=plan.result_contract,
        )

        assert_equal(
            result.success,
            False,
            f"{plan_name} 默认必须拒绝经营敏感结果。",
        )

        assert_equal(
            result.reason_code,
            ProtectionReason.COST_DATA_NOT_ALLOWED,
            f"{plan_name} 应返回 cost_data_not_allowed。",
        )


def test_new_confidential_metrics_can_be_explicitly_allowed() -> None:
    samples = {
        "refund_rate_overall_v2": {
            "refund_rate": 0.08,
            "__group_size": 100,
        },
        "roi_channel_v2": {
            "channel_name": "示例渠道",
            "roi": 3.2,
            "__group_size": 100,
        },
        "cac_channel_v2": {
            "channel_name": "示例渠道",
            "cac": 120.0,
            "__group_size": 100,
        },
    }

    for plan_name, rows in samples.items():
        plan = get_query_plan_v2_by_name(
            plan_name
        )

        result = protect_result_rows(
            context=build_context(
                plan,
                allow_cost_data=True,
            ),
            rows=[rows],
            contract=plan.result_contract,
        )

        assert_equal(
            result.success,
            True,
            f"{plan_name} 显式允许后应通过保护层。",
        )

        assert_true(
            "__group_size"
            not in result.rows[0],
            f"{plan_name} 必须隐藏 __group_size。",
        )


def test_brand_and_channel_new_results_are_ordinary() -> None:
    samples = {
        "brand_paid_new_customer_count_overall_v2": {
            "brand_paid_new_customer_count": 120,
            "__group_size": 120,
        },
        "channel_paid_new_customer_count_channel_v2": {
            "channel_name": "示例渠道",
            "channel_paid_new_customer_count": 80,
            "__group_size": 80,
        },
    }

    for plan_name, row in samples.items():
        plan = get_query_plan_v2_by_name(
            plan_name
        )

        result = protect_result_rows(
            context=build_context(plan),
            rows=[row],
            contract=plan.result_contract,
        )

        assert_equal(
            result.success,
            True,
            f"{plan_name} ordinary aggregate 应通过保护层。",
        )

        assert_true(
            "__group_size"
            not in result.rows[0],
            f"{plan_name} 必须隐藏 __group_size。",
        )


def test_all_48_plans_enable_minimum_group_size() -> None:
    for plan in (
        load_query_plan_v2_catalog()
        .query_plans
    ):
        assert_equal(
            (
                plan.result_contract
                .minimum_group_size_required
            ),
            True,
            f"{plan.name} 必须启用 Minimum Group Size。",
        )

        assert_equal(
            (
                plan.result_contract
                .group_size_field
            ),
            "__group_size",
            f"{plan.name} 必须使用 __group_size。",
        )


def test_runtime_catalog_and_plans_are_immutable() -> None:
    catalog = load_query_plan_v2_catalog()

    try:
        catalog.status = "candidate"
    except ValidationError:
        pass
    else:
        raise AssertionError(
            "Runtime Catalog 必须不可修改。"
        )

    plan = get_query_plan_v2_by_name(
        "cac_channel_v2"
    )

    try:
        plan.result_grain = "changed"
    except ValidationError:
        return

    raise AssertionError(
        "Runtime QueryPlanV2 必须不可修改。"
    )


def run_tests() -> None:
    tests = [
        test_runtime_catalog_loads_48_plans,
        test_runtime_catalog_has_exact_19_metrics,
        test_static_catalog_semantically_matches_canonical_builder,
        test_static_yaml_bytes_match_canonical_writer,
        test_runtime_logic_type_counts,
        test_metric_lookup_covers_new_metrics,
        test_all_48_static_plans_are_resource_authorizable,
        test_legacy_43_and_refund_have_current_row_scope_paths,
        test_roi_and_cac_region_paths_fail_closed,
        test_global_history_plans_fail_closed_on_scope_placement,
        test_brand_and_channel_new_have_physical_paths_but_unsafe_placement,
        test_global_history_identities_survive_static_catalog,
        test_cross_fact_time_windows_survive_static_catalog,
        test_refund_semantics_survive_static_catalog,
        test_aus_category_remains_absent,
        test_repeat_and_member_semantics_survive_static_catalog,
        test_new_confidential_bindings_survive_static_catalog,
        test_new_confidential_metrics_are_denied_by_default,
        test_new_confidential_metrics_can_be_explicitly_allowed,
        test_brand_and_channel_new_results_are_ordinary,
        test_all_48_plans_enable_minimum_group_size,
        test_runtime_catalog_and_plans_are_immutable,
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
    print("Static Query Plan V2 Runtime Test Summary")
    print(f"Total: {len(tests)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    run_tests()
