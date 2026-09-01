from pathlib import Path
import tempfile

import yaml

from app.governance.sensitive_data import (
    SensitiveDataCategory,
)
from app.semantic_layer.query_plan_v2_catalog_builder import (
    build_query_plan_v2_catalog,
    write_query_plan_v2_catalog,
)
from app.semantic_layer.query_plan_v2_models import (
    QueryLogic,
    QueryPlanCatalogV2,
    ScopeDimension,
    ScopeMode,
    StageJoin,
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
    "r12_base_customer_count",
    "r12_repurchase_customer_count",
    "r12_repurchase_rate",
    "r12_repurchase_amount",
    "r12_repurchase_spending",
}

NEW_PLAN_NAMES = {
    "refund_rate_overall_v2",
    "refund_rate_channel_v2",
    "refund_rate_region_v2",
    "refund_rate_category_v2",
    "roi_channel_v2",
    "cac_channel_v2",
    "brand_paid_new_customer_count_overall_v2",
    "channel_paid_new_customer_count_channel_v2",
    "order_count_customer_lifecycle_membership_v2",
}


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(
            f"{message}\nExpected: {expected}\nActual: {actual}"
        )


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def catalog():
    return build_query_plan_v2_catalog()


def by_name(name: str):
    return next(
        plan
        for plan in catalog().query_plans
        if plan.name == name
    )


def test_catalog_has_59_plans() -> None:
    assert_equal(
        len(catalog().query_plans),
        59,
        "完整 V2 Catalog 应包含 59 个 Query Plan。",
    )


def test_catalog_has_exact_24_metrics() -> None:
    metrics = {
        plan.metric
        for plan in catalog().query_plans
    }

    assert_equal(
        metrics,
        EXPECTED_METRICS,
        "完整 Catalog 必须精确覆盖 Metadata V2 的 24 个 metric。",
    )


def test_plan_names_are_unique() -> None:
    names = [
        plan.name
        for plan in catalog().query_plans
    ]

    assert_equal(
        len(names),
        len(set(names)),
        "完整 Catalog 的 Plan name 必须唯一。",
    )


def test_logic_type_counts_are_correct() -> None:
    plans = catalog().query_plans

    query_logic_count = sum(
        isinstance(
            plan.query_logic,
            QueryLogic,
        )
        for plan in plans
    )

    staged_count = sum(
        isinstance(
            plan.query_logic,
            StagedQueryLogic,
        )
        for plan in plans
    )

    assert_equal(
        query_logic_count,
        42,
        "39 Simple + 1 Member 应形成 42 个 QueryLogic Plan。",
    )

    assert_equal(
        staged_count,
        17,
        (
            "3 Repeat + 5 R12 + 4 Refund + ROI + CAC + Brand New + "
            "Channel New + Order Customer Composition 应形成 17 个 StagedQueryLogic Plan。"
        ),
    )


def test_declared_candidate_plan_set_is_present() -> None:
    names = {
        plan.name
        for plan in catalog().query_plans
    }

    assert_true(
        NEW_PLAN_NAMES.issubset(names),
        "声明的候选 Plan 必须全部进入 Canonical Catalog。",
    )


def test_global_history_plan_set_is_exact() -> None:
    plans = [
        plan
        for plan in catalog().query_plans
        if (
            plan.scope_contract.scope_mode
            == ScopeMode.GLOBAL_HISTORY_REQUIRED
        )
    ]

    assert_equal(
        {
            plan.name
            for plan in plans
        },
        {
            "cac_channel_v2",
            "brand_paid_new_customer_count_overall_v2",
            "channel_paid_new_customer_count_channel_v2",
        },
        "Global History Plan 集合不正确。",
    )


def test_cross_fact_stage_joins_are_preserved() -> None:
    for plan_name in (
        "roi_channel_v2",
        "cac_channel_v2",
    ):
        plan = by_name(plan_name)

        assert_true(
            any(
                isinstance(join, StageJoin)
                for stage in plan.query_logic.stages
                for join in stage.joins
            ),
            f"{plan_name} 必须保留 StageJoin。",
        )


def test_refund_grain_family_preserves_preaggregation_semantics() -> None:
    expected = {
        "refund_rate_overall_v2": (
            "overall",
            None,
        ),
        "refund_rate_channel_v2": (
            "channel",
            "channel_name",
        ),
        "refund_rate_region_v2": (
            "region",
            "region_name",
        ),
        "refund_rate_category_v2": (
            "category",
            "category",
        ),
    }

    for plan_name, (
        expected_grain,
        dimension_field,
    ) in expected.items():
        plan = by_name(plan_name)

        assert_equal(
            plan.result_grain,
            expected_grain,
            f"{plan_name} Grain 不正确。",
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
            f"{plan_name} 必须 LEFT JOIN refund events。",
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
            f"{plan_name} 必须先按 Item 聚合 completed refund。",
        )

        assert_true(
            "fr.refund_status = 'completed'"
            in expression,
            f"{plan_name} 必须保持 completed-only 分子。",
        )

        final_stage = plan.query_logic.stages[-1]
        final_fields = {
            output.field
            for output in final_stage.outputs
        }

        assert_true(
            "refund_rate" in final_fields,
            f"{plan_name} 必须输出 refund_rate。",
        )

        if dimension_field is not None:
            assert_true(
                dimension_field in final_fields,
                f"{plan_name} 必须输出 {dimension_field}。",
            )


def test_global_history_identities_are_preserved() -> None:
    cac = by_name("cac_channel_v2")
    channel_new = by_name(
        "channel_paid_new_customer_count_channel_v2"
    )
    brand_new = by_name(
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
        "CAC 必须使用 customer × channel identity。",
    )

    assert_equal(
        (
            channel_new.scope_contract
            .history_contract
            .sequence_partition_by
        ),
        expected_channel_identity,
        "渠道新客必须使用 customer × channel identity。",
    )

    assert_equal(
        (
            brand_new.scope_contract
            .history_contract
            .sequence_partition_by
        ),
        ("fo.customer_id",),
        "品牌新客必须使用 customer identity。",
    )


def test_global_history_scope_placement_is_preserved() -> None:
    cac = by_name("cac_channel_v2")
    channel_new = by_name(
        "channel_paid_new_customer_count_channel_v2"
    )
    brand_new = by_name(
        "brand_paid_new_customer_count_overall_v2"
    )

    assert_equal(
        (
            cac.scope_contract
            .history_contract
            .pre_sequence_scope_dimensions()
        ),
        frozenset(
            {ScopeDimension.CHANNEL}
        ),
        "CAC Channel 必须保持 pre-sequence safe。",
    )

    assert_equal(
        (
            channel_new.scope_contract
            .history_contract
            .post_sequence_scope_dimensions
        ),
        frozenset(
            {ScopeDimension.REGION}
        ),
        "渠道新客 Region 必须保持 post-sequence。",
    )

    assert_equal(
        (
            brand_new.scope_contract
            .history_contract
            .post_sequence_scope_dimensions
        ),
        frozenset(
            {
                ScopeDimension.REGION,
                ScopeDimension.CHANNEL,
            }
        ),
        "品牌新客 Region + Channel 必须全部后置。",
    )


def test_cross_fact_time_windows_are_preserved() -> None:
    expected = (
        "fact_orders.paid_at",
        "fact_marketing_spend.spend_date",
    )

    for plan_name in (
        "roi_channel_v2",
        "cac_channel_v2",
    ):
        assert_equal(
            (
                by_name(plan_name)
                .semantic_contract
                .time_window_columns
            ),
            expected,
            f"{plan_name} 必须保持 Cross-fact shared time window。",
        )


def test_sensitive_metric_bindings_are_preserved() -> None:
    for plan_name in (
        "refund_rate_overall_v2",
        "refund_rate_channel_v2",
        "refund_rate_region_v2",
        "refund_rate_category_v2",
    ):
        plan = by_name(plan_name)

        binding = next(
            item
            for item in plan.result_contract.field_bindings
            if item.output_field == "refund_rate"
        )

        assert_equal(
            binding.category,
            (
                SensitiveDataCategory
                .AGGREGATED_BUSINESS_CONFIDENTIAL
            ),
            (
                f"{plan_name} 必须使用独立的 "
                "Aggregated Business Confidential 类别。"
            ),
        )

    for plan_name, field in (
        ("roi_channel_v2", "roi"),
        ("cac_channel_v2", "cac"),
    ):
        plan = by_name(plan_name)

        binding = next(
            item
            for item in plan.result_contract.field_bindings
            if item.output_field == field
        )

        assert_equal(
            binding.category,
            SensitiveDataCategory.BUSINESS_CONFIDENTIAL,
            f"{plan_name} 必须继续保持 raw/cost Business Confidential。",
        )


def test_aus_category_remains_absent() -> None:
    names = {
        plan.name
        for plan in catalog().query_plans
    }

    assert_true(
        "aus_category_v2" not in names,
        "完整 Catalog 仍不得出现 aus_category_v2。",
    )


def test_writer_is_byte_deterministic() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        first = Path(temp_dir) / "first.yaml"
        second = Path(temp_dir) / "second.yaml"

        write_query_plan_v2_catalog(first)
        write_query_plan_v2_catalog(second)

        assert_equal(
            first.read_bytes(),
            second.read_bytes(),
            "完整 Catalog 多次生成必须字节完全一致。",
        )


def test_written_yaml_round_trips_with_59_plans() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "query_plans.yaml"

        write_query_plan_v2_catalog(path)

        payload = yaml.safe_load(
            path.read_text(
                encoding="utf-8"
            )
        )

        loaded = (
            QueryPlanCatalogV2
            .model_validate(payload)
        )

        assert_equal(
            len(loaded.query_plans),
            59,
            "完整 YAML Round-trip 后仍应有 59 plans。",
        )

        assert_equal(
            {
                plan.metric
                for plan in loaded.query_plans
            },
            EXPECTED_METRICS,
            "Round-trip 后仍必须覆盖 24 Metrics。",
        )


def test_all_seventeen_staged_plans_survive_serialization() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "query_plans.yaml"

        write_query_plan_v2_catalog(path)

        payload = yaml.safe_load(
            path.read_text(
                encoding="utf-8"
            )
        )

        loaded = (
            QueryPlanCatalogV2
            .model_validate(payload)
        )

        assert_equal(
            sum(
                isinstance(
                    plan.query_logic,
                    StagedQueryLogic,
                )
                for plan in loaded.query_plans
            ),
            17,
            "YAML Round-trip 后 17 个 Staged Plan 必须保持类型。",
        )


def test_complete_catalog_identity_is_frozen() -> None:
    result = catalog()

    assert_equal(
        result.query_plan_version,
        "beauty_bi_query_plan_v2_0",
        "Query Plan version 不正确。",
    )

    assert_equal(
        result.dataset_name,
        "beauty_bi_v2",
        "Dataset identity 不正确。",
    )

    assert_equal(
        result.metadata_version,
        "beauty_bi_metadata_v2_0",
        "Metadata identity 不正确。",
    )

    assert_equal(
        result.status,
        "draft",
        "Day73 Dataset V2 Catalog 仍应保持 draft。",
    )


def run_tests() -> None:
    tests = [
        test_catalog_has_59_plans,
        test_catalog_has_exact_24_metrics,
        test_plan_names_are_unique,
        test_logic_type_counts_are_correct,
        test_declared_candidate_plan_set_is_present,
        test_global_history_plan_set_is_exact,
        test_cross_fact_stage_joins_are_preserved,
        test_refund_grain_family_preserves_preaggregation_semantics,
        test_global_history_identities_are_preserved,
        test_global_history_scope_placement_is_preserved,
        test_cross_fact_time_windows_are_preserved,
        test_sensitive_metric_bindings_are_preserved,
        test_aus_category_remains_absent,
        test_writer_is_byte_deterministic,
        test_written_yaml_round_trips_with_59_plans,
        test_all_seventeen_staged_plans_survive_serialization,
        test_complete_catalog_identity_is_frozen,
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
    print("Query Plan V2 Catalog Builder Test Summary")
    print(f"Total: {len(tests)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    run_tests()
