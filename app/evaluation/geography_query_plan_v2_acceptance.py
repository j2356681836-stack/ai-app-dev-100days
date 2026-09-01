from __future__ import annotations

from datetime import date

from app.delivery.decision_console_runtime_v2 import (
    build_day89_local_access_context_v2,
)
from app.governance.governed_planning_envelope_v2 import (
    GovernedPlanningStatusV2,
    build_governed_planning_envelope_v2,
)
from app.governance.compiled_sql_ast_enforcer_v2 import (
    CompiledSqlAstStatusV2,
    enforce_compiled_sql_ast_v2,
)
from app.semantic_layer.query_plan_compiler_v2 import (
    QueryPlanCompileStatusV2,
    compile_governed_query_plan_v2,
)
from app.semantic_layer.query_plan_v2_loader import (
    get_query_plan_v2_by_name,
    load_query_plan_v2_catalog,
)
from app.semantic_layer.time_window_resolver_v2 import (
    resolve_time_window_v2,
)


REFERENCE_DATE = date(2025, 11, 15)

EXPECTED = {
    "gmv_area_v2": {
        "grain": "area",
        "visible_fields": (
            "region_group",
            "gmv",
        ),
        "dimension_column": "dim_region.region_group",
        "sql_fragment": "dr.region_group AS region_group",
    },
    "gmv_province_v2": {
        "grain": "province",
        "visible_fields": (
            "province_name",
            "gmv",
        ),
        "dimension_column": "dim_region.province_name",
        "sql_fragment": "dr.province_name AS province_name",
    },
    "gmv_city_v2": {
        "grain": "city",
        "visible_fields": (
            "region_name",
            "gmv",
        ),
        "dimension_column": "dim_region.region_name",
        "sql_fragment": "dr.region_name AS region_name",
    },
}


def _plan(name: str):
    plan = get_query_plan_v2_by_name(
        name
    )

    if plan is None:
        raise AssertionError(
            f"Missing Query Plan: {name}"
        )

    return plan


def test_catalog_contains_new_hierarchy_and_legacy_region() -> None:
    catalog = load_query_plan_v2_catalog()
    names = {
        plan.name
        for plan in catalog.query_plans
    }

    assert len(catalog.query_plans) == 59

    for name in EXPECTED:
        assert name in names

    assert "gmv_region_v2" in names
    assert _plan("gmv_region_v2").result_grain == "region"

    print(
        "PASS: "
        "test_catalog_contains_new_hierarchy_and_legacy_region"
    )
    print("PASS: catalog plans = 59")
    print("PASS: legacy gmv_region_v2 retained")


def test_hierarchy_query_plan_contracts() -> None:
    for plan_name, expected in EXPECTED.items():
        plan = _plan(plan_name)

        assert plan.metric == "gmv"
        assert plan.result_grain == expected["grain"]

        logic = plan.query_logic

        assert tuple(
            output.field
            for output in logic.outputs
        ) == expected["visible_fields"]

        assert "__group_size" in {
            item.field
            for item in logic.hidden_control_fields
        }

        assert (
            expected["dimension_column"]
            in plan.resource_contract.required_columns
        )

        assert (
            plan.scope_contract.scope_mode.value
            == "predicate_safe"
        )
        assert {
            item.value
            for item in plan.scope_contract.required_dimensions
        } == {
            "channel",
            "region",
        }

        assert (
            plan.result_contract.minimum_group_size_required
            is True
        )
        assert (
            plan.result_contract.group_size_field
            == "__group_size"
        )

    print("PASS: test_hierarchy_query_plan_contracts")


def test_hierarchy_plans_compile_and_ast_enforce() -> None:
    context = build_day89_local_access_context_v2(
        request_id="day93-geography-query-plan-acceptance",
    )

    resolution = resolve_time_window_v2(
        "2025年10月GMV是多少？",
        reference_date=REFERENCE_DATE,
    )

    for plan_name, expected in EXPECTED.items():
        plan = _plan(plan_name)

        planning = build_governed_planning_envelope_v2(
            context=context,
            plan=plan,
            time_resolution=resolution,
        )

        assert (
            planning.status
            == GovernedPlanningStatusV2.READY_FOR_COMPILATION
        ), (
            f"{plan_name} planning failed: "
            f"{planning.status.value}; "
            f"{planning.detail}"
        )
        assert planning.envelope is not None

        compiled = compile_governed_query_plan_v2(
            planning.envelope
        )

        assert (
            compiled.status
            == QueryPlanCompileStatusV2.COMPILED
        ), (
            f"{plan_name} compile failed: "
            f"{compiled.status.value}; "
            f"{compiled.detail}"
        )
        assert compiled.contract is not None

        contract = compiled.contract

        assert (
            contract.visible_output_fields
            == expected["visible_fields"]
        )
        assert "__group_size" in contract.hidden_output_fields
        assert expected["sql_fragment"] in contract.sql

        ast_decision = enforce_compiled_sql_ast_v2(
            envelope=planning.envelope,
            compiled=contract,
        )

        assert (
            ast_decision.status
            == CompiledSqlAstStatusV2.ENFORCED
        ), (
            f"{plan_name} AST enforcement failed: "
            f"{ast_decision.status.value}; "
            f"{ast_decision.detail}"
        )

        print(
            f"PASS: {plan_name} "
            "READY -> COMPILED -> AST ENFORCED"
        )

    print("PASS: test_hierarchy_plans_compile_and_ast_enforce")


def main() -> None:
    test_catalog_contains_new_hierarchy_and_legacy_region()
    test_hierarchy_query_plan_contracts()
    test_hierarchy_plans_compile_and_ast_enforce()


if __name__ == "__main__":
    main()
