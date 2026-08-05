from __future__ import annotations

import os
from datetime import date, datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import text

from app.db.governed_database import (
    get_governed_engine,
    load_governed_database_config,
)
from app.db.governed_sql_runner import run_governed_sql
from app.governance.access_context import (
    AccessContext,
    AccessRole,
    OperationMode,
    SensitiveDataPolicy,
)
from app.governance.audit_sink import verify_audit_log
from app.governance.governance_runtime import (
    GovernanceRuntimeConfig,
)
from app.governance.execution_policy import (
    GovernedExecutionPolicy,
)
from app.governance.governed_finalization import (
    FinalizationOutcome,
    FinalizationReason,
)
from app.governance.governed_planning_envelope_v2 import (
    GovernedPlanningStatusV2,
    build_governed_planning_envelope_v2,
)
from app.governance.governed_query_execution_v2 import (
    execute_governed_query_v2,
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


REFERENCE_DATE = date(2026, 8, 3)
FIXED_TIME = datetime(
    2026,
    8,
    5,
    15,
    30,
    tzinfo=timezone.utc,
)

SUCCESS_QUESTION = "2025年GMV是多少？"
EMPTY_WINDOW_QUESTION = "上月GMV是多少？"

# Integration-only execution budget. This does not change
# GovernedExecutionPolicy's production default of 5 seconds.
INTEGRATION_EXECUTION_POLICY = GovernedExecutionPolicy(
    statement_timeout_ms=30_000,
    max_rows=10,
)

V2_CHANNEL_CODES = frozenset(
    {
        "DOUYIN",
        "JD",
        "OFFICIAL_MALL",
        "TMALL",
        "WECHAT_MINI_PROGRAM",
        "XIAOHONGSHU",
    }
)

V2_REGION_CODES = frozenset(
    {
        "BEIJING",
        "CHONGQING",
        "GUANGDONG_GUANGZHOU",
        "GUANGDONG_SHENZHEN",
        "GUANGXI_GUILIN",
        "HENAN_LUOYANG",
        "HUBEI_WUHAN",
        "JIANGSU_NANJING",
        "LIAONING_SHENYANG",
        "SHAANXI_XIAN",
        "SHANDONG_QINGDAO",
        "SHANGHAI",
        "SICHUAN_CHENGDU",
        "SICHUAN_MIANYANG",
        "ZHEJIANG_HANGZHOU",
        "ZHEJIANG_JINHUA",
    }
)


def _runtime_config(
    audit_log_path: Path,
) -> GovernanceRuntimeConfig:
    return GovernanceRuntimeConfig(
        result_tokenization_secret=(
            "result-tokenization-secret-32-chars"
        ),
        audit_secret=(
            "audit-secret-32-characters-long"
        ),
        audit_log_path=audit_log_path,
        create_parent_directory=True,
        fsync_enabled=True,
    )


def _catalog_resources() -> tuple[
    frozenset[str],
    frozenset[str],
    frozenset[str],
]:
    catalog = load_query_plan_v2_catalog()

    metrics = frozenset(
        plan.metric
        for plan in catalog.query_plans
    )
    tables = frozenset(
        table
        for plan in catalog.query_plans
        for table in plan.resource_contract.required_tables
    )
    columns = frozenset(
        column
        for plan in catalog.query_plans
        for column in plan.resource_contract.required_columns
    )

    return metrics, tables, columns


def _integration_context() -> AccessContext:
    metrics, tables, columns = _catalog_resources()

    return AccessContext(
        request_id=(
            "governed-query-execution-v2-integration"
        ),
        actor_id="integration-user",
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
        allowed_region_codes=V2_REGION_CODES,
        allowed_channel_codes=V2_CHANNEL_CODES,
        sensitive_data_policy=SensitiveDataPolicy(),
        policy_version=(
            "governed_query_execution_v2_integration"
        ),
        scope_source=(
            "database_aligned_integration_fixture"
        ),
    )


def _ready_gmv_pair(
    *,
    context: AccessContext,
    question: str,
):
    plan = get_query_plan_v2_by_name(
        "gmv_overall_v2"
    )

    assert plan is not None, (
        "Missing Query Plan: gmv_overall_v2"
    )

    resolution = resolve_time_window_v2(
        question,
        reference_date=REFERENCE_DATE,
    )

    planning = build_governed_planning_envelope_v2(
        context=context,
        plan=plan,
        time_resolution=resolution,
    )

    assert (
        planning.status
        == GovernedPlanningStatusV2
        .READY_FOR_COMPILATION
    ), (
        "GMV planning failed. "
        f"status={planning.status.value}, "
        f"detail={planning.detail}"
    )
    assert planning.envelope is not None

    compilation = compile_governed_query_plan_v2(
        planning.envelope
    )

    assert (
        compilation.status
        == QueryPlanCompileStatusV2.COMPILED
    ), (
        "GMV compilation failed. "
        f"status={compilation.status.value}, "
        f"detail={compilation.detail}"
    )
    assert compilation.contract is not None

    compiled = compilation.contract

    expected_time_parameters = {
        "analysis_start_date",
        "analysis_end_date",
    }

    assert expected_time_parameters.issubset(
        set(compiled.parameter_mapping())
    )
    assert "__group_size" in (
        compiled.hidden_output_fields
    )

    return planning.envelope, compiled


def _assert_scope_codes_exist_in_database() -> None:
    engine = get_governed_engine()

    with engine.connect() as connection:
        channel_codes = frozenset(
            connection.execute(
                text(
                    """
                    SELECT channel_code
                    FROM beauty_bi_v2.dim_channel
                    """
                )
            ).scalars()
        )
        region_codes = frozenset(
            connection.execute(
                text(
                    """
                    SELECT region_code
                    FROM beauty_bi_v2.dim_region
                    """
                )
            ).scalars()
        )

    assert V2_CHANNEL_CODES.issubset(
        channel_codes
    ), (
        "Integration fixture contains unknown channel codes. "
        f"missing={sorted(V2_CHANNEL_CODES - channel_codes)}"
    )

    assert V2_REGION_CODES.issubset(
        region_codes
    ), (
        "Integration fixture contains unknown region codes. "
        f"missing={sorted(V2_REGION_CODES - region_codes)}"
    )


def test_real_service_uses_dedicated_query_role(
) -> None:
    config = load_governed_database_config()
    engine = get_governed_engine()

    with engine.connect() as connection:
        current_user = connection.execute(
            text("SELECT current_user")
        ).scalar_one()

    assert current_user == config.username, (
        "Governed Engine is not using AI_QUERY_POSTGRES_USER. "
        f"expected={config.username}, actual={current_user}"
    )

    admin_user = os.getenv("POSTGRES_USER")

    if admin_user is not None:
        assert current_user != admin_user, (
            "Governed Engine unexpectedly reused POSTGRES_USER."
        )

    _assert_scope_codes_exist_in_database()


def test_real_compiled_query_executes_and_releases_only_safe_rows(
) -> None:
    context = _integration_context()
    envelope, compiled = _ready_gmv_pair(
        context=context,
        question=SUCCESS_QUESTION,
    )

    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "audit.jsonl"

        result = execute_governed_query_v2(
            context=context,
            question=SUCCESS_QUESTION,
            envelope=envelope,
            compiled=compiled,
            runtime_config=_runtime_config(path),
            execution_policy=(
                INTEGRATION_EXECUTION_POLICY
            ),
            event_id=(
                "governed-query-real-postgres-success"
            ),
            occurred_at_utc=FIXED_TIME,
            written_at_utc=FIXED_TIME,
        )

        assert result.success, (
            "Real governed service did not succeed. "
            f"outcome={result.outcome.value}, "
            f"reason={result.reason_code.value}, "
            f"blocked_stage={result.blocked_stage}, "
            f"blocked_reason={result.blocked_reason}, "
            f"message={result.message}"
        )
        assert (
            result.outcome
            == FinalizationOutcome.SUCCEEDED
        )
        assert result.audit_persisted
        assert result.row_count == 1
        assert result.rows
        assert set(result.rows[0]) == {"gmv"}
        assert "__group_size" not in result.rows[0]
        assert result.rows[0]["gmv"] is not None

        verification = verify_audit_log(path)

        assert verification.success
        assert verification.record_count == 1


def test_real_empty_window_is_audited_and_blocked(
) -> None:
    context = _integration_context()
    envelope, compiled = _ready_gmv_pair(
        context=context,
        question=EMPTY_WINDOW_QUESTION,
    )

    preflight = run_governed_sql(
        sql=compiled.sql,
        parameters=compiled.parameter_mapping(),
        policy=INTEGRATION_EXECUTION_POLICY,
    )

    assert preflight.success
    assert preflight.rows == (
        {
            "gmv": None,
            "__group_size": 0,
        },
    )

    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "audit.jsonl"

        result = execute_governed_query_v2(
            context=context,
            question=EMPTY_WINDOW_QUESTION,
            envelope=envelope,
            compiled=compiled,
            runtime_config=_runtime_config(path),
            execution_policy=(
                INTEGRATION_EXECUTION_POLICY
            ),
            event_id=(
                "governed-query-real-postgres-empty-window"
            ),
            occurred_at_utc=FIXED_TIME,
            written_at_utc=FIXED_TIME,
        )

        assert not result.success
        assert (
            result.outcome
            == FinalizationOutcome.BLOCKED
        )
        assert (
            result.reason_code
            == FinalizationReason
            .RESULT_PROTECTION_BLOCKED
        )
        assert (
            result.blocked_reason
            == "minimum_group_size_violation"
        )
        assert result.audit_persisted
        assert result.rows == ()

        verification = verify_audit_log(path)

        assert verification.success
        assert verification.record_count == 1


def test_corrupted_audit_log_blocks_real_database_result(
) -> None:
    context = _integration_context()
    envelope, compiled = _ready_gmv_pair(
        context=context,
        question=SUCCESS_QUESTION,
    )

    preflight = run_governed_sql(
        sql=compiled.sql,
        parameters=compiled.parameter_mapping(),
        policy=INTEGRATION_EXECUTION_POLICY,
    )

    assert preflight.success, (
        "PostgreSQL preflight failed; audit-failure test would be "
        "ambiguous. "
        f"error_type={getattr(preflight.error_type, 'value', None)}, "
        f"message={preflight.message}"
    )
    assert preflight.rows
    assert (
        preflight.rows[0]["__group_size"] >= 5
    )

    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "audit.jsonl"
        path.write_text(
            '{"corrupted":true}\n',
            encoding="utf-8",
        )

        result = execute_governed_query_v2(
            context=context,
            question=SUCCESS_QUESTION,
            envelope=envelope,
            compiled=compiled,
            runtime_config=_runtime_config(path),
            execution_policy=(
                INTEGRATION_EXECUTION_POLICY
            ),
            event_id=(
                "governed-query-real-postgres-audit-fail"
            ),
            occurred_at_utc=FIXED_TIME,
            written_at_utc=FIXED_TIME,
        )

        assert not result.success
        assert (
            result.outcome
            == FinalizationOutcome.FAILED
        )
        assert (
            result.reason_code
            == FinalizationReason
            .AUDIT_PERSISTENCE_FAILED
        )
        assert not result.audit_persisted
        assert result.rows == ()
        assert result.row_count == 0


TESTS = (
    test_real_service_uses_dedicated_query_role,
    test_real_compiled_query_executes_and_releases_only_safe_rows,
    test_real_empty_window_is_audited_and_blocked,
    test_corrupted_audit_log_blocks_real_database_result,
)


def run_acceptance() -> None:
    passed = 0
    failed = 0

    print("=" * 80)
    print(
        "Governed Query Execution V2 "
        "PostgreSQL Integration Acceptance"
    )
    print(
        f"Cases: {len(TESTS)}"
    )

    for test in TESTS:
        print("=" * 80)
        print(test.__name__)

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
        "Governed Query Execution V2 "
        "PostgreSQL Integration Summary"
    )
    print(f"Total: {len(TESTS)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    run_acceptance()
