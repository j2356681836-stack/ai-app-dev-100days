from pathlib import Path
import tempfile

import yaml
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
from app.governance.sensitive_data import (
    ProtectionReason,
    SensitiveDataCategory,
    protect_result_rows,
)
from app.governance.row_scope import (
    plan_row_scope,
)
from app.governance.row_scope_binding import (
    build_scoped_query_contract,
)
from app.semantic_layer.simple_query_plan_v2_builder import (
    SIMPLE_METRIC_SPECS,
    build_simple_query_plan_catalog,
    write_simple_query_plan_catalog,
)
from app.semantic_layer.query_plan_v2_models import (
    QueryPlanCatalogV2,
)


def assert_equal(
    actual,
    expected,
    message: str,
) -> None:
    if actual != expected:
        raise AssertionError(
            f"{message}\n"
            f"Expected: {expected}\n"
            f"Actual: {actual}"
        )


def assert_true(
    condition: bool,
    message: str,
) -> None:
    if not condition:
        raise AssertionError(message)


def build_context(
    plan,
    *,
    allow_cost_data: bool = False,
) -> AccessContext:
    return AccessContext(
        request_id=(
            "req-day73-simple-builder-001"
        ),
        actor_id="analyst-001",
        role=AccessRole.SCOPED_ANALYST,
        dataset_name="beauty_bi_v2",
        target_schema="beauty_bi_v2",
        operation_mode=(
            OperationMode.OBSERVE_ADVISE
        ),
        allowed_metrics=frozenset(
            {
                spec.metric
                for spec in SIMPLE_METRIC_SPECS
            }
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
        sensitive_data_policy=(
            SensitiveDataPolicy(
                allow_cost_data=allow_cost_data,
            )
        ),
        policy_version="governance_v1",
        scope_source=(
            "day73_simple_builder_fixture"
        ),
    )


def catalog():
    return build_simple_query_plan_catalog()


def test_builder_generates_39_plans() -> None:
    result = catalog()

    assert_equal(
        len(result.query_plans),
        39,
        "10 个 Simple Metrics 应生成 39 个 Plan。",
    )


def test_plan_names_are_unique() -> None:
    result = catalog()

    names = [
        plan.name
        for plan in result.query_plans
    ]

    assert_equal(
        len(names),
        len(set(names)),
        "Query Plan name 必须唯一。",
    )


def test_aus_category_is_not_generated() -> None:
    names = {
        plan.name
        for plan in catalog().query_plans
    }

    assert_true(
        "aus_category_v2" not in names,
        "AUS 首版不得生成 Category Plan。",
    )

    assert_true(
        {
            "aus_overall_v2",
            "aus_channel_v2",
            "aus_region_v2",
        }.issubset(names),
        "AUS 应支持 overall/channel/region。",
    )


def test_every_other_simple_metric_has_four_grains() -> None:
    result = catalog()

    by_metric = {}

    for plan in result.query_plans:
        by_metric.setdefault(
            plan.metric,
            set(),
        ).add(
            plan.result_grain
        )

    for spec in SIMPLE_METRIC_SPECS:
        expected = set(
            spec.supported_grains
        )

        assert_equal(
            by_metric[spec.metric],
            expected,
            f"{spec.metric} Grain Matrix 不正确。",
        )


def test_only_category_plans_require_dim_product() -> None:
    for plan in catalog().query_plans:
        has_product = (
            "dim_product"
            in plan.resource_contract.required_tables
        )

        assert_equal(
            has_product,
            plan.result_grain == "category",
            (
                f"{plan.name} 的 dim_product "
                "资源声明不符合最小权限。"
            ),
        )


def test_all_plans_are_authorizable() -> None:
    for plan in catalog().query_plans:
        context = build_context(plan)

        decision = authorize_resources(
            context,
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
            (
                f"{plan.name} 应能通过 "
                "Day68 Authorization。"
            ),
        )


def test_all_plans_build_row_scope_contract() -> None:
    for plan in catalog().query_plans:
        context = build_context(plan)

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
            (
                f"{plan.name} 应能创建 "
                "RowScopePlan。"
            ),
        )

        binding = build_scoped_query_contract(
            scope_decision.plan,
            targets=(
                plan.to_scope_targets()
            ),
        )

        assert_equal(
            binding.allowed,
            True,
            (
                f"{plan.name} 应能绑定 "
                "ScopedQueryContract。"
            ),
        )

        assert_equal(
            len(binding.contract.predicates),
            2,
            (
                f"{plan.name} 应获得 "
                "Region + Channel Predicate。"
            ),
        )


def test_category_order_metric_uses_distinct_order() -> None:
    plan = next(
        plan
        for plan in catalog().query_plans
        if plan.name
        == "order_count_category_v2"
    )

    expression = next(
        output.expression
        for output in plan.query_logic.outputs
        if output.field == "order_count"
    )

    assert_equal(
        expression,
        "COUNT(DISTINCT fo.order_id)",
        "Category Order Count 必须按订单去重。",
    )


def test_category_buyer_metric_uses_distinct_customer() -> None:
    plan = next(
        plan
        for plan in catalog().query_plans
        if plan.name
        == "buyer_count_category_v2"
    )

    expression = next(
        output.expression
        for output in plan.query_logic.outputs
        if output.field == "buyer_count"
    )

    assert_equal(
        expression,
        "COUNT(DISTINCT fo.customer_id)",
        "Category Buyer Count 必须按客户去重。",
    )


def test_category_frequency_uses_distinct_orders_and_buyers() -> None:
    plan = next(
        plan
        for plan in catalog().query_plans
        if plan.name
        == "purchase_frequency_category_v2"
    )

    expression = next(
        output.expression
        for output in plan.query_logic.outputs
        if output.field == "purchase_frequency"
    )

    assert_true(
        "COUNT(DISTINCT fo.order_id)"
        in expression,
        "Category FREQ 分子必须是 distinct order。",
    )

    assert_true(
        "COUNT(DISTINCT fo.customer_id)"
        in expression,
        "Category FREQ 分母必须是 distinct buyer。",
    )


def test_overall_plan_has_no_dimension_output() -> None:
    plan = next(
        plan
        for plan in catalog().query_plans
        if plan.name == "gmv_overall_v2"
    )

    fields = {
        output.field
        for output in plan.query_logic.outputs
    }

    assert_equal(
        fields,
        {"gmv"},
        "Overall Plan 不应伪造维度输出。",
    )

    assert_equal(
        plan.query_logic.group_by,
        (),
        "Overall Plan 不应 GROUP BY 维度。",
    )


def test_all_plans_enable_minimum_group_size() -> None:
    for plan in catalog().query_plans:
        assert_equal(
            (
                plan.result_contract
                .minimum_group_size_required
            ),
            True,
            (
                f"{plan.name} 应启用 "
                "Minimum Group Size。"
            ),
        )

        assert_equal(
            plan.result_contract.group_size_field,
            "__group_size",
            (
                f"{plan.name} 隐藏控制字段 "
                "必须统一。"
            ),
        )


def test_catalog_is_immutable() -> None:
    result = catalog()

    try:
        result.status = "candidate"
    except ValidationError:
        return

    raise AssertionError(
        "生成后的 QueryPlanCatalogV2 必须不可修改。"
    )



def test_writer_is_byte_deterministic() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        first_path = Path(temp_dir) / "first.yaml"
        second_path = Path(temp_dir) / "second.yaml"

        write_simple_query_plan_catalog(
            first_path
        )
        write_simple_query_plan_catalog(
            second_path
        )

        first = first_path.read_bytes()
        second = second_path.read_bytes()

        assert_equal(
            first,
            second,
            "同一 Spec 两次生成的 YAML 字节必须完全一致。",
        )


def test_written_yaml_round_trips_into_contract() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "query_plans.yaml"

        write_simple_query_plan_catalog(
            path
        )

        payload = yaml.safe_load(
            path.read_text(encoding="utf-8")
        )

        catalog = (
            QueryPlanCatalogV2.model_validate(
                payload
            )
        )

        assert_equal(
            len(catalog.query_plans),
            39,
            "落盘 YAML 重新加载后仍应包含 39 个 Plan。",
        )



def test_gross_margin_results_are_business_confidential() -> None:
    for plan_name in (
        "gross_margin_overall_v2",
        "gross_margin_rate_overall_v2",
    ):
        plan = next(
            plan
            for plan in catalog().query_plans
            if plan.name == plan_name
        )

        metric_binding = next(
            binding
            for binding in plan.result_contract.field_bindings
            if binding.output_field == plan.metric
        )

        assert_equal(
            metric_binding.category,
            SensitiveDataCategory.BUSINESS_CONFIDENTIAL,
            f"{plan_name} 必须按 Business Confidential 保护。",
        )


def test_gross_margin_is_denied_by_default() -> None:
    plan = next(
        plan
        for plan in catalog().query_plans
        if plan.name == "gross_margin_overall_v2"
    )

    result = protect_result_rows(
        context=build_context(plan),
        rows=[{
            "gross_margin": 100.0,
            "__group_size": 10,
        }],
        contract=plan.result_contract,
    )

    assert_equal(
        result.success,
        False,
        "默认 allow_cost_data=false 时毛利额必须拒绝。",
    )

    assert_equal(
        result.reason_code,
        ProtectionReason.COST_DATA_NOT_ALLOWED,
        "毛利额默认拒绝应返回 cost_data_not_allowed。",
    )


def test_gross_margin_can_be_explicitly_allowed() -> None:
    plan = next(
        plan
        for plan in catalog().query_plans
        if plan.name == "gross_margin_overall_v2"
    )

    result = protect_result_rows(
        context=build_context(
            plan,
            allow_cost_data=True,
        ),
        rows=[{
            "gross_margin": 100.0,
            "__group_size": 10,
        }],
        contract=plan.result_contract,
    )

    assert_equal(
        result.success,
        True,
        "可信策略显式允许成本数据时毛利额应可返回。",
    )


def test_gmv_remains_ordinary() -> None:
    plan = next(
        plan
        for plan in catalog().query_plans
        if plan.name == "gmv_overall_v2"
    )

    metric_binding = next(
        binding
        for binding in plan.result_contract.field_bindings
        if binding.output_field == "gmv"
    )

    assert_equal(
        metric_binding.category,
        SensitiveDataCategory.ORDINARY,
        "GMV 当前合同应保持 ordinary。",
    )

    result = protect_result_rows(
        context=build_context(plan),
        rows=[{
            "gmv": 1000.0,
            "__group_size": 10,
        }],
        contract=plan.result_contract,
    )

    assert_equal(
        result.success,
        True,
        "普通 GMV 聚合结果默认应允许。",
    )


def run_tests() -> None:
    tests = [
        test_builder_generates_39_plans,
        test_plan_names_are_unique,
        test_aus_category_is_not_generated,
        test_every_other_simple_metric_has_four_grains,
        test_only_category_plans_require_dim_product,
        test_all_plans_are_authorizable,
        test_all_plans_build_row_scope_contract,
        test_category_order_metric_uses_distinct_order,
        test_category_buyer_metric_uses_distinct_customer,
        test_category_frequency_uses_distinct_orders_and_buyers,
        test_overall_plan_has_no_dimension_output,
        test_all_plans_enable_minimum_group_size,
        test_catalog_is_immutable,
        test_writer_is_byte_deterministic,
        test_written_yaml_round_trips_into_contract,
        test_gross_margin_results_are_business_confidential,
        test_gross_margin_is_denied_by_default,
        test_gross_margin_can_be_explicitly_allowed,
        test_gmv_remains_ordinary,
    ]

    passed = 0
    failed = 0

    for test in tests:
        print("=" * 80)
        print(
            f"Running: {test.__name__}"
        )

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
        "Simple Query Plan V2 Builder "
        "Test Summary"
    )
    print(f"Total: {len(tests)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    run_tests()
