from __future__ import annotations

from collections import Counter
from datetime import date

from sqlalchemy import text

from app.governance.access_context import (
    AccessContext,
    AccessRole,
    OperationMode,
    SensitiveDataPolicy,
)
from app.governance.governed_planning_envelope_v2 import (
    GovernedPlanningStatusV2,
    build_governed_planning_envelope_v2,
)
from app.semantic_layer.query_plan_compiler_v2 import (
    QueryPlanCompileStatusV2,
    _assert_safe_fragment,
    compile_governed_query_plan_v2,
)
from app.semantic_layer.query_plan_v2_loader import (
    get_query_plan_v2_by_name,
    load_query_plan_v2_catalog,
)
from app.semantic_layer.time_window_resolver_v2 import (
    resolve_time_window_v2,
)


REFERENCE_DATE = date(
    2026,
    8,
    3,
)


def _catalog_resources():
    catalog = load_query_plan_v2_catalog()

    metrics = frozenset(
        plan.metric
        for plan in catalog.query_plans
    )
    tables = frozenset(
        table
        for plan in catalog.query_plans
        for table in (
            plan.resource_contract.required_tables
        )
    )
    columns = frozenset(
        column
        for plan in catalog.query_plans
        for column in (
            plan.resource_contract.required_columns
        )
    )

    return (
        catalog,
        metrics,
        tables,
        columns,
    )


def _context() -> AccessContext:
    (
        _,
        metrics,
        tables,
        columns,
    ) = _catalog_resources()

    return AccessContext(
        request_id="query-plan-compiler-v2",
        actor_id="acceptance-user",
        role=AccessRole.SCOPED_ANALYST,
        dataset_name="beauty_bi_v2",
        target_schema="beauty_bi_v2",
        operation_mode=(
            OperationMode.OBSERVE_ADVISE
        ),
        allowed_metrics=metrics,
        allowed_tables=tables,
        allowed_columns=columns,
        denied_columns=frozenset(),
        allowed_region_codes=frozenset(
            {
                "north",
                "south",
            }
        ),
        allowed_channel_codes=frozenset(
            {
                "tmall",
                "jd",
            }
        ),
        sensitive_data_policy=(
            SensitiveDataPolicy()
        ),
        policy_version=(
            "query_plan_compiler_v2_acceptance"
        ),
        scope_source="acceptance_fixture",
    )


def _plan(
    name: str,
):
    plan = get_query_plan_v2_by_name(
        name
    )

    if plan is None:
        raise AssertionError(
            f"Missing Query Plan: {name}"
        )

    return plan


def _ready_envelope(
    *,
    plan_name: str,
    question: str,
):
    plan = _plan(
        plan_name
    )
    resolution = resolve_time_window_v2(
        question,
        reference_date=REFERENCE_DATE,
    )
    planning = (
        build_governed_planning_envelope_v2(
            context=_context(),
            plan=plan,
            time_resolution=resolution,
        )
    )

    assert (
        planning.status
        == GovernedPlanningStatusV2
        .READY_FOR_COMPILATION
    ), (
        f"{plan_name} did not reach compilation: "
        f"{planning.status.value}; "
        f"{planning.detail}"
    )
    assert planning.envelope is not None

    return planning.envelope


def _compile(
    *,
    plan_name: str,
    question: str,
):
    decision = compile_governed_query_plan_v2(
        _ready_envelope(
            plan_name=plan_name,
            question=question,
        )
    )

    assert decision.success, (
        f"{decision.status.value}: "
        f"{decision.detail}"
    )
    assert (
        decision.status
        == QueryPlanCompileStatusV2.COMPILED
    )
    assert decision.contract is not None

    return decision.contract


def test_simple_gmv_compilation() -> None:
    contract = _compile(
        plan_name="gmv_overall_v2",
        question="GMV是多少？",
    )

    sql = contract.sql

    assert sql.startswith(
        "SELECT"
    )
    assert (
        "FROM beauty_bi_v2.fact_order_items AS foi"
        in sql
    )
    assert (
        "INNER JOIN beauty_bi_v2.fact_orders AS fo"
        in sql
    )
    assert (
        "fo.paid_at IS NOT NULL"
        in sql
    )
    assert (
        "CAST(fo.paid_at AS DATE) "
        "BETWEEN :analysis_start_date "
        "AND :analysis_end_date"
        in sql
    )
    assert (
        "beauty_bi_v2.dim_channel"
        in sql
    )
    assert (
        "beauty_bi_v2.dim_region"
        in sql
    )
    assert (
        "SUM(foi.item_paid_amount) AS gmv"
        in sql
    )
    assert (
        "COUNT(DISTINCT fo.customer_id) "
        "AS __group_size"
        in sql
    )
    assert sql.endswith(
        "ORDER BY gmv DESC"
    )

    parameters = contract.parameter_mapping()

    assert parameters[
        "analysis_start_date"
    ] == date(
        2026,
        5,
        4,
    )
    assert parameters[
        "analysis_end_date"
    ] == REFERENCE_DATE

    assert contract.visible_output_fields == (
        "gmv",
    )
    assert contract.hidden_output_fields == (
        "__group_size",
    )
    assert not contract.compiled_stage_ids


def test_grouped_composite_compilation() -> None:
    contract = _compile(
        plan_name="gmv_channel_region_v2",
        question="按渠道和地区交叉看GMV",
    )

    sql = contract.sql

    assert (
        "GROUP BY"
        in sql
    )
    assert (
        "dc.channel_id"
        in sql
    )
    assert (
        "dr.region_id"
        in sql
    )
    assert (
        "ORDER BY gmv DESC"
        in sql
    )


def test_repeat_staged_compilation() -> None:
    contract = _compile(
        plan_name=(
            "repeat_customer_rate_overall_v2"
        ),
        question="上月跨日复购率",
    )

    sql = contract.sql

    assert sql.startswith(
        "WITH"
    )
    assert (
        "customer_purchase_summary AS ("
        in sql
    )
    assert (
        "final AS ("
        in sql
    )
    assert (
        "CAST(fo.paid_at AS DATE) "
        "BETWEEN :analysis_start_date "
        "AND :analysis_end_date"
        in sql
    )

    first_stage_sql, final_stage_sql = (
        sql.split(
            "final AS (",
            1,
        )
    )

    assert "scope_" in first_stage_sql
    assert "scope_" not in final_stage_sql
    assert contract.compiled_stage_ids == (
        "customer_purchase_summary",
        "final",
    )
    assert contract.visible_output_fields == (
        "repeat_customer_rate",
    )
    assert contract.hidden_output_fields == (
        "__group_size",
    )


def test_refund_staged_compilation() -> None:
    contract = _compile(
        plan_name="refund_rate_overall_v2",
        question="2026年7月退款率",
    )

    sql = contract.sql

    assert (
        "item_refund_summary AS ("
        in sql
    )
    assert (
        "LEFT JOIN beauty_bi_v2.fact_refunds AS fr"
        in sql
    )
    assert (
        "CAST(fo.paid_at AS DATE) "
        "BETWEEN :analysis_start_date "
        "AND :analysis_end_date"
        in sql
    )
    assert (
        "compiled_final.refund_rate "
        "AS refund_rate"
        in sql
    )


def test_sqlalchemy_named_parameter_contract() -> None:
    contract = _compile(
        plan_name="gmv_channel_v2",
        question="2026年7月各渠道GMV",
    )

    clause = text(
        contract.sql
    )

    assert set(
        clause._bindparams
    ) == set(
        contract.parameter_names
    )
    assert set(
        contract.parameter_mapping()
    ) == set(
        contract.parameter_names
    )


def test_compilation_is_deterministic() -> None:
    envelope = _ready_envelope(
        plan_name="gross_margin_region_v2",
        question="上月各地区毛利",
    )

    first = compile_governed_query_plan_v2(
        envelope
    )
    second = compile_governed_query_plan_v2(
        envelope
    )

    assert first.success
    assert second.success
    assert first.contract is not None
    assert second.contract is not None

    assert first.contract.sql == second.contract.sql
    assert (
        first.contract.sql_fingerprint
        == second.contract.sql_fingerprint
    )
    assert (
        first.contract.contract_fingerprint
        == second.contract.contract_fingerprint
    )
    assert (
        first.contract.parameters
        == second.contract.parameters
    )


def test_unsafe_fragment_guard() -> None:
    try:
        _assert_safe_fragment(
            "SUM(fo.amount); DROP TABLE x",
            location="acceptance_malicious_fragment",
            allowed_parameters=frozenset(),
        )
    except ValueError:
        pass
    else:
        raise AssertionError(
            "Unsafe fragment was not rejected."
        )

    try:
        _assert_safe_fragment(
            "SUM(fo.amount) -- comment",
            location="acceptance_comment_fragment",
            allowed_parameters=frozenset(),
        )
    except ValueError:
        pass
    else:
        raise AssertionError(
            "SQL comment fragment was not rejected."
        )


def test_catalog_wide_ready_plan_compilation() -> None:
    (
        catalog,
        _,
        _,
        _,
    ) = _catalog_resources()

    context = _context()
    resolution = resolve_time_window_v2(
        "查看指标表现",
        reference_date=REFERENCE_DATE,
    )

    planning_counts: Counter[str] = Counter()
    compile_counts: Counter[str] = Counter()
    failures: list[str] = []

    for plan in catalog.query_plans:
        planning = (
            build_governed_planning_envelope_v2(
                context=context,
                plan=plan,
                time_resolution=resolution,
            )
        )

        planning_counts[
            planning.status.value
        ] += 1

        if (
            planning.status
            != GovernedPlanningStatusV2
            .READY_FOR_COMPILATION
        ):
            continue

        if planning.envelope is None:
            failures.append(
                f"{plan.name}: ready without envelope"
            )
            continue

        compiled = (
            compile_governed_query_plan_v2(
                planning.envelope
            )
        )

        compile_counts[
            compiled.status.value
        ] += 1

        if not compiled.success:
            failures.append(
                f"{plan.name}: "
                f"{compiled.status.value}: "
                f"{compiled.detail}"
            )
            continue

        if compiled.contract is None:
            failures.append(
                f"{plan.name}: compiled without contract"
            )

    assert not failures, "\n".join(
        failures
    )

    assert planning_counts == Counter(
        {
            "ready_for_compilation": 45,
            "scope_binding_not_ready": 4,
        }
    )
    assert compile_counts == Counter(
        {
            "compiled": 45,
        }
    )


TESTS = (
    test_simple_gmv_compilation,
    test_grouped_composite_compilation,
    test_repeat_staged_compilation,
    test_refund_staged_compilation,
    test_sqlalchemy_named_parameter_contract,
    test_compilation_is_deterministic,
    test_unsafe_fragment_guard,
    test_catalog_wide_ready_plan_compilation,
)


def run_acceptance() -> None:
    passed = 0
    failed = 0

    print("=" * 80)
    print(
        "Query Plan Compiler V2 Acceptance"
    )
    print(
        f"Cases: {len(TESTS)}"
    )

    for test in TESTS:
        print("=" * 80)
        print(
            test.__name__
        )

        try:
            test()
        except Exception as exc:
            failed += 1
            print("[FAIL]")
            print(
                f"{type(exc).__name__}: {exc}"
            )
        else:
            passed += 1
            print("[PASS]")

    print("=" * 80)
    print(
        "Query Plan Compiler V2 "
        "Acceptance Summary"
    )
    print(
        f"Total: {len(TESTS)}"
    )
    print(
        f"Passed: {passed}"
    )
    print(
        f"Failed: {failed}"
    )

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    run_acceptance()
