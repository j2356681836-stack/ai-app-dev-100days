from __future__ import annotations

from collections import Counter
from datetime import date

from app.governance.access_context import (
    AccessContext,
    AccessRole,
    OperationMode,
    SensitiveDataPolicy,
)
from app.governance.compiled_sql_ast_enforcer_v2 import (
    CompiledSqlAstStatusV2,
    enforce_compiled_sql_ast_v2,
)
from app.governance.governed_planning_envelope_v2 import (
    GovernedPlanningStatusV2,
    build_governed_planning_envelope_v2,
)
from app.semantic_layer.query_plan_compiler_v2 import (
    CompiledQueryPlanContractV2,
    QueryPlanCompileStatusV2,
    _compiled_contract_fingerprint,
    _sha256_text,
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

    return (
        catalog,
        frozenset(
            plan.metric
            for plan in catalog.query_plans
        ),
        frozenset(
            table
            for plan in catalog.query_plans
            for table in (
                plan.resource_contract.required_tables
            )
        ),
        frozenset(
            column
            for plan in catalog.query_plans
            for column in (
                plan.resource_contract.required_columns
            )
        ),
    )


def _context() -> AccessContext:
    (
        _,
        metrics,
        tables,
        columns,
    ) = _catalog_resources()

    return AccessContext(
        request_id="compiled-sql-ast-enforcer-v2",
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
            "compiled_sql_ast_enforcer_v2_acceptance"
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


def _ready_pair(
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
        f"{plan_name} compilation failed: "
        f"{compiled.status.value}; "
        f"{compiled.detail}"
    )
    assert compiled.contract is not None

    return (
        planning.envelope,
        compiled.contract,
    )


def _rebuild_compiled(
    original: CompiledQueryPlanContractV2,
    *,
    sql: str | None = None,
    compiled_stage_ids: (
        tuple[str, ...]
        | None
    ) = None,
) -> CompiledQueryPlanContractV2:
    effective_sql = (
        original.sql
        if sql is None
        else sql
    )
    effective_stage_ids = (
        original.compiled_stage_ids
        if compiled_stage_ids is None
        else compiled_stage_ids
    )
    sql_fingerprint = _sha256_text(
        effective_sql
    )

    contract_fingerprint = (
        _compiled_contract_fingerprint(
            request_id=original.request_id,
            plan_name=original.plan_name,
            metric_name=original.metric_name,
            result_grain=original.result_grain,
            target_schema=original.target_schema,
            envelope_fingerprint=(
                original.envelope_fingerprint
            ),
            query_plan_fingerprint=(
                original.query_plan_fingerprint
            ),
            time_binding_fingerprint=(
                original.time_binding_fingerprint
            ),
            scope_binding_fingerprint=(
                original.scope_binding_fingerprint
            ),
            sql_fingerprint=sql_fingerprint,
            parameters=original.parameters,
            visible_output_fields=(
                original.visible_output_fields
            ),
            hidden_output_fields=(
                original.hidden_output_fields
            ),
            compiled_stage_ids=(
                effective_stage_ids
            ),
        )
    )

    return CompiledQueryPlanContractV2(
        request_id=original.request_id,
        plan_name=original.plan_name,
        metric_name=original.metric_name,
        result_grain=original.result_grain,
        target_schema=original.target_schema,
        envelope_fingerprint=(
            original.envelope_fingerprint
        ),
        query_plan_fingerprint=(
            original.query_plan_fingerprint
        ),
        time_binding_fingerprint=(
            original.time_binding_fingerprint
        ),
        scope_binding_fingerprint=(
            original.scope_binding_fingerprint
        ),
        sql=effective_sql,
        parameters=original.parameters,
        parameter_names=(
            original.parameter_names
        ),
        visible_output_fields=(
            original.visible_output_fields
        ),
        hidden_output_fields=(
            original.hidden_output_fields
        ),
        compiled_stage_ids=(
            effective_stage_ids
        ),
        sql_fingerprint=sql_fingerprint,
        contract_fingerprint=(
            contract_fingerprint
        ),
    )


def test_simple_ast_enforcement() -> None:
    envelope, compiled = _ready_pair(
        plan_name="gmv_overall_v2",
        question="GMV是多少？",
    )

    decision = enforce_compiled_sql_ast_v2(
        envelope=envelope,
        compiled=compiled,
    )

    assert decision.success
    assert (
        decision.status
        == CompiledSqlAstStatusV2.ENFORCED
    )
    assert decision.contract is not None

    contract = decision.contract

    assert (
        contract.observed_physical_tables
        == envelope.required_tables
    )
    assert (
        contract.observed_physical_columns
        == envelope.required_columns
    )
    assert not contract.observed_cte_names
    assert contract.observed_output_fields == (
        "gmv",
        "__group_size",
    )
    assert contract.observed_parameter_names == frozenset(
        compiled.parameter_names
    )


def test_staged_ast_enforcement() -> None:
    envelope, compiled = _ready_pair(
        plan_name=(
            "repeat_customer_rate_overall_v2"
        ),
        question="上月跨日复购率",
    )

    decision = enforce_compiled_sql_ast_v2(
        envelope=envelope,
        compiled=compiled,
    )

    assert decision.success
    assert decision.contract is not None
    assert decision.contract.observed_cte_names == (
        "customer_purchase_summary",
        "final",
    )
    assert decision.contract.observed_output_fields == (
        "repeat_customer_rate",
        "__group_size",
    )
    assert "Count" in (
        decision.contract
        .observed_function_classes
    )


def test_count_star_is_allowed() -> None:
    envelope, compiled = _ready_pair(
        plan_name=(
            "repeat_customer_count_overall_v2"
        ),
        question="上月跨日复购人数",
    )

    assert "COUNT(*)" in compiled.sql

    decision = enforce_compiled_sql_ast_v2(
        envelope=envelope,
        compiled=compiled,
    )

    assert decision.success


def test_outside_schema_is_denied() -> None:
    envelope, compiled = _ready_pair(
        plan_name="gmv_overall_v2",
        question="GMV是多少？",
    )

    marker = "\nWHERE\n"

    assert marker in compiled.sql

    malicious_sql = compiled.sql.replace(
        marker,
        (
            "\nCROSS JOIN "
            "pg_catalog.pg_class AS pc"
            + marker
        ),
        1,
    )
    malicious = _rebuild_compiled(
        compiled,
        sql=malicious_sql,
    )

    decision = enforce_compiled_sql_ast_v2(
        envelope=envelope,
        compiled=malicious,
    )

    assert not decision.success
    assert (
        decision.status
        == CompiledSqlAstStatusV2
        .SCHEMA_NOT_ALLOWED
    )


def test_undeclared_column_is_denied() -> None:
    envelope, compiled = _ready_pair(
        plan_name="gmv_overall_v2",
        question="GMV是多少？",
    )

    malicious_sql = compiled.sql.replace(
        "foi.item_paid_amount",
        "foi.secret_amount",
        1,
    )
    malicious = _rebuild_compiled(
        compiled,
        sql=malicious_sql,
    )

    decision = enforce_compiled_sql_ast_v2(
        envelope=envelope,
        compiled=malicious,
    )

    assert not decision.success
    assert (
        decision.status
        == CompiledSqlAstStatusV2
        .COLUMN_CONTRACT_MISMATCH
    )


def test_wildcard_projection_is_denied() -> None:
    envelope, compiled = _ready_pair(
        plan_name="gmv_overall_v2",
        question="GMV是多少？",
    )

    _, from_part = compiled.sql.split(
        "FROM ",
        1,
    )
    malicious_sql = (
        "SELECT *\nFROM "
        + from_part
    )
    malicious = _rebuild_compiled(
        compiled,
        sql=malicious_sql,
    )

    decision = enforce_compiled_sql_ast_v2(
        envelope=envelope,
        compiled=malicious,
    )

    assert not decision.success
    assert (
        decision.status
        == CompiledSqlAstStatusV2
        .WILDCARD_NOT_ALLOWED
    )


def test_unknown_function_is_denied() -> None:
    envelope, compiled = _ready_pair(
        plan_name="gmv_overall_v2",
        question="GMV是多少？",
    )

    malicious_sql = compiled.sql.replace(
        "SUM(foi.item_paid_amount)",
        "PG_SLEEP(1)",
        1,
    )
    malicious = _rebuild_compiled(
        compiled,
        sql=malicious_sql,
    )

    decision = enforce_compiled_sql_ast_v2(
        envelope=envelope,
        compiled=malicious,
    )

    assert not decision.success
    assert (
        decision.status
        == CompiledSqlAstStatusV2
        .FUNCTION_NOT_ALLOWED
    )


def test_cte_contract_mismatch_is_denied() -> None:
    envelope, compiled = _ready_pair(
        plan_name=(
            "repeat_customer_rate_overall_v2"
        ),
        question="上月跨日复购率",
    )

    malicious = _rebuild_compiled(
        compiled,
        compiled_stage_ids=(
            "wrong_stage",
            "final",
        ),
    )

    decision = enforce_compiled_sql_ast_v2(
        envelope=envelope,
        compiled=malicious,
    )

    assert not decision.success
    assert (
        decision.status
        == CompiledSqlAstStatusV2
        .CTE_CONTRACT_MISMATCH
    )


def test_catalog_wide_ast_enforcement() -> None:
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
    enforcement_counts: Counter[str] = Counter()
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

        compiled = compile_governed_query_plan_v2(
            planning.envelope
        )

        if (
            compiled.status
            != QueryPlanCompileStatusV2.COMPILED
            or compiled.contract is None
        ):
            failures.append(
                f"{plan.name}: compile failed: "
                f"{compiled.status.value}: "
                f"{compiled.detail}"
            )
            continue

        enforced = enforce_compiled_sql_ast_v2(
            envelope=planning.envelope,
            compiled=compiled.contract,
        )
        enforcement_counts[
            enforced.status.value
        ] += 1

        if not enforced.success:
            failures.append(
                f"{plan.name}: "
                f"{enforced.status.value}: "
                f"{enforced.detail}"
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
    assert enforcement_counts == Counter(
        {
            "enforced": 45,
        }
    )


TESTS = (
    test_simple_ast_enforcement,
    test_staged_ast_enforcement,
    test_count_star_is_allowed,
    test_outside_schema_is_denied,
    test_undeclared_column_is_denied,
    test_wildcard_projection_is_denied,
    test_unknown_function_is_denied,
    test_cte_contract_mismatch_is_denied,
    test_catalog_wide_ast_enforcement,
)


def run_acceptance() -> None:
    passed = 0
    failed = 0

    print("=" * 80)
    print(
        "Compiled SQL AST Enforcement V2 Acceptance"
    )
    print(
        f"SQLGlot: {__import__('sqlglot').__version__}"
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
        "Compiled SQL AST Enforcement V2 "
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
