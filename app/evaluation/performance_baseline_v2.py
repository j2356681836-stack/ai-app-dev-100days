from __future__ import annotations

import argparse
import json
import statistics
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from typing import Any

from sqlalchemy import text

from app.db.governed_database import get_governed_engine
from app.db.governed_sql_runner import run_governed_sql
from app.evaluation.governed_analytics_postgresql_integration_v2 import (
    FIXED_TIME,
    REFERENCE_DATE,
    _gmv_llm_call,
)
from app.evaluation.governed_query_execution_integration_v2 import (
    _integration_context,
    _runtime_config,
)
from app.governance.execution_policy import (
    GovernedExecutionPolicy,
)
from app.governance.governed_analytics_service_v2 import (
    execute_governed_analytics_v2,
)
from app.governance.governed_planning_envelope_v2 import (
    GovernedPlanningStatusV2,
    build_governed_planning_envelope_v2,
)
from app.semantic_layer.query_plan_compiler_v2 import (
    QueryPlanCompileStatusV2,
    compile_governed_query_plan_v2,
)
from app.semantic_layer.query_plan_v2_loader import (
    get_query_plan_v2_by_name,
    load_query_plan_v2_catalog,
)
from app.semantic_layer.query_plan_v2_models import (
    ScopeMode,
    StagedQueryLogic,
)
from app.semantic_layer.time_window_resolver_v2 import (
    resolve_time_window_v2,
)


PERFORMANCE_POLICY = GovernedExecutionPolicy(
    statement_timeout_ms=60_000,
    max_rows=5_000,
)

BASELINE_VERSION = "performance_baseline_v2_0"


@dataclass(frozen=True)
class PerformanceCase:
    case_id: str
    category: str
    plan_name: str
    question: str


def _ready_pair(
    *,
    plan_name: str,
    question: str,
):
    context = _integration_context()

    plan = get_query_plan_v2_by_name(
        plan_name
    )

    if plan is None:
        raise RuntimeError(
            f"Missing Query Plan: {plan_name}"
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

    if (
        planning.status
        != GovernedPlanningStatusV2.READY_FOR_COMPILATION
        or planning.envelope is None
    ):
        raise RuntimeError(
            "Governed Planning not ready. "
            f"plan={plan_name}, "
            f"status={planning.status.value}, "
            f"detail={planning.detail}"
        )

    compilation = compile_governed_query_plan_v2(
        planning.envelope
    )

    if (
        compilation.status
        != QueryPlanCompileStatusV2.COMPILED
        or compilation.contract is None
    ):
        raise RuntimeError(
            "Compilation failed. "
            f"plan={plan_name}, "
            f"status={compilation.status.value}, "
            f"detail={compilation.detail}"
        )

    return (
        planning.envelope,
        compilation.contract,
    )


def _select_executable_staged_case() -> PerformanceCase:
    """
    Select one currently executable StagedQueryLogic without assuming a
    remembered plan name.

    Preference:
    1. predicate_safe before global_history_required;
    2. overall grain before grouped grain;
    3. lexical plan name for deterministic selection.

    Known fail-closed plans are naturally skipped because the function
    requires Governed Planning + Compilation to succeed.
    """
    catalog = load_query_plan_v2_catalog()

    candidates = [
        plan
        for plan in catalog.query_plans
        if isinstance(
            plan.query_logic,
            StagedQueryLogic,
        )
        and plan.name
        not in {
            "refund_rate_overall_v2",
        }
    ]

    candidates.sort(
        key=lambda plan: (
            (
                0
                if plan.scope_contract.scope_mode
                == ScopeMode.PREDICATE_SAFE
                else 1
            ),
            (
                0
                if plan.result_grain == "overall"
                else 1
            ),
            plan.name,
        )
    )

    failures: list[str] = []

    for plan in candidates:
        try:
            _ready_pair(
                plan_name=plan.name,
                question="2025年",
            )
        except Exception as exc:
            failures.append(
                f"{plan.name}: {type(exc).__name__}: {exc}"
            )
            continue

        return PerformanceCase(
            case_id="PERF-004",
            category="staged_query",
            plan_name=plan.name,
            question="2025年",
        )

    raise RuntimeError(
        "No executable StagedQueryLogic was found. "
        f"failures={failures}"
    )


def _baseline_cases() -> tuple[PerformanceCase, ...]:
    staged = _select_executable_staged_case()

    return (
        PerformanceCase(
            case_id="PERF-001",
            category="simple_aggregate",
            plan_name="gmv_overall_v2",
            question="2025年GMV是多少？",
        ),
        PerformanceCase(
            case_id="PERF-002",
            category="group_by",
            plan_name="gmv_channel_v2",
            question="2025年各渠道GMV是多少？",
        ),
        PerformanceCase(
            case_id="PERF-003",
            category="complex_metric",
            plan_name="refund_rate_overall_v2",
            question="2025年退款率是多少？",
        ),
        staged,
    )


def _database_context() -> dict[str, Any]:
    engine = get_governed_engine()

    with engine.connect() as connection:
        database_name = connection.execute(
            text(
                "SELECT current_database()"
            )
        ).scalar_one()

        database_size_bytes = connection.execute(
            text(
                "SELECT pg_database_size(current_database())"
            )
        ).scalar_one()

        table_stats = [
            dict(row)
            for row in connection.execute(
                text(
                    """
                    SELECT
                        relname AS table_name,
                        n_live_tup::bigint AS estimated_rows,
                        pg_total_relation_size(
                            format('%I.%I', schemaname, relname)
                        ) AS total_bytes
                    FROM pg_stat_user_tables
                    WHERE schemaname = 'beauty_bi_v2'
                    ORDER BY relname
                    """
                )
            ).mappings()
        ]

        indexes = [
            dict(row)
            for row in connection.execute(
                text(
                    """
                    SELECT
                        tablename AS table_name,
                        indexname AS index_name,
                        indexdef AS index_definition
                    FROM pg_indexes
                    WHERE schemaname = 'beauty_bi_v2'
                    ORDER BY tablename, indexname
                    """
                )
            ).mappings()
        ]

    return {
        "database_name": database_name,
        "database_size_bytes": int(
            database_size_bytes
        ),
        "tables": table_stats,
        "indexes": indexes,
        "table_count": len(table_stats),
        "index_count": len(indexes),
    }


def _walk_plan_nodes(
    plan: dict[str, Any],
) -> list[dict[str, Any]]:
    nodes = [
        {
            "node_type": plan.get("Node Type"),
            "relation_name": plan.get("Relation Name"),
            "index_name": plan.get("Index Name"),
            "actual_rows": plan.get("Actual Rows"),
            "actual_loops": plan.get("Actual Loops"),
            "plan_rows": plan.get("Plan Rows"),
            "startup_cost": plan.get("Startup Cost"),
            "total_cost": plan.get("Total Cost"),
            "sort_method": plan.get("Sort Method"),
            "shared_hit_blocks": plan.get(
                "Shared Hit Blocks"
            ),
            "shared_read_blocks": plan.get(
                "Shared Read Blocks"
            ),
            "temp_read_blocks": plan.get(
                "Temp Read Blocks"
            ),
            "temp_written_blocks": plan.get(
                "Temp Written Blocks"
            ),
        }
    ]

    for child in plan.get(
        "Plans",
        [],
    ):
        nodes.extend(
            _walk_plan_nodes(
                child
            )
        )

    return nodes


def _run_explain_analyze(
    *,
    sql: str,
    parameters: dict[str, Any],
) -> dict[str, Any]:
    """
    PostgreSQL-internal timing evidence.

    This is deliberately separate from run_governed_sql(). It answers:
    "How much time did PostgreSQL itself report for this SELECT plan?"
    """
    engine = get_governed_engine()

    transaction = None

    try:
        with engine.connect() as connection:
            transaction = connection.begin()

            connection.execute(
                text(
                    "SET TRANSACTION READ ONLY"
                )
            )
            connection.execute(
                text(
                    "SELECT set_config("
                    "'statement_timeout', "
                    ":timeout, true)"
                ),
                {
                    "timeout": "60000ms",
                },
            )
            connection.execute(
                text(
                    "SELECT set_config("
                    "'search_path', "
                    ":search_path, true)"
                ),
                {
                    "search_path": (
                        "beauty_bi_v2,pg_catalog"
                    ),
                },
            )

            raw = connection.execute(
                text(
                    "EXPLAIN "
                    "(ANALYZE, BUFFERS, FORMAT JSON) "
                    + sql
                ),
                parameters,
            ).scalar_one()

            transaction.rollback()
            transaction = None

    finally:
        if (
            transaction is not None
            and getattr(
                transaction,
                "is_active",
                False,
            )
        ):
            transaction.rollback()

    if isinstance(
        raw,
        str,
    ):
        raw = json.loads(
            raw
        )

    if (
        not isinstance(
            raw,
            list,
        )
        or not raw
        or not isinstance(
            raw[0],
            dict,
        )
    ):
        raise RuntimeError(
            "Unexpected EXPLAIN JSON payload."
        )

    root = raw[0]
    plan = root["Plan"]
    nodes = _walk_plan_nodes(
        plan
    )

    scans = [
        node
        for node in nodes
        if (
            node["node_type"] is not None
            and "Scan" in node["node_type"]
        )
    ]

    sorts = [
        node
        for node in nodes
        if node["node_type"] == "Sort"
    ]

    return {
        "planning_time_ms": root.get(
            "Planning Time"
        ),
        "postgres_execution_time_ms": root.get(
            "Execution Time"
        ),
        "top_node_type": plan.get(
            "Node Type"
        ),
        "top_actual_rows": plan.get(
            "Actual Rows"
        ),
        "top_shared_hit_blocks": plan.get(
            "Shared Hit Blocks"
        ),
        "top_shared_read_blocks": plan.get(
            "Shared Read Blocks"
        ),
        "top_temp_read_blocks": plan.get(
            "Temp Read Blocks"
        ),
        "top_temp_written_blocks": plan.get(
            "Temp Written Blocks"
        ),
        "node_count": len(nodes),
        "scan_nodes": scans,
        "sort_nodes": sorts,
    }


def _run_governed_repeats(
    *,
    sql: str,
    parameters: dict[str, Any],
    repeats: int,
) -> dict[str, Any]:
    samples: list[float] = []
    last_result = None

    for _ in range(
        repeats
    ):
        result = run_governed_sql(
            sql=sql,
            parameters=parameters,
            policy=PERFORMANCE_POLICY,
        )
        last_result = result

        samples.append(
            result.execution_time_ms
        )

        if not result.success:
            break

    assert last_result is not None

    return {
        "success": last_result.success,
        "error_type": (
            last_result.error_type.value
            if last_result.error_type is not None
            else None
        ),
        "message": last_result.message,
        "row_count": last_result.row_count,
        "observed_row_count": (
            last_result.observed_row_count
        ),
        "samples_ms": samples,
        "median_ms": statistics.median(
            samples
        ),
        "min_ms": min(
            samples
        ),
        "max_ms": max(
            samples
        ),
        "statement_timeout_ms": (
            PERFORMANCE_POLICY.statement_timeout_ms
        ),
    }


def _measure_case(
    case: PerformanceCase,
    *,
    repeats: int,
) -> dict[str, Any]:
    envelope, compiled = _ready_pair(
        plan_name=case.plan_name,
        question=case.question,
    )

    parameters = (
        compiled.parameter_mapping()
    )

    governed = _run_governed_repeats(
        sql=compiled.sql,
        parameters=parameters,
        repeats=repeats,
    )

    explain = None

    if governed["success"]:
        explain = _run_explain_analyze(
            sql=compiled.sql,
            parameters=parameters,
        )

    return {
        **asdict(
            case
        ),
        "metric_name": envelope.metric_name,
        "result_grain": envelope.result_grain,
        "required_tables": sorted(
            envelope.required_tables
        ),
        "required_columns_count": len(
            envelope.required_columns
        ),
        "compiled_stage_ids": list(
            compiled.compiled_stage_ids
        ),
        "parameter_names": list(
            compiled.parameter_names
        ),
        "governed_runner": governed,
        "explain_analyze": explain,
    }


def _measure_deterministic_e2e() -> dict[str, Any]:
    """
    Deterministic service-level E2E measurement.

    Important:
    `_gmv_llm_call` is a local deterministic fixture, so this measures
    V2 orchestration + governance + database + protection + audit +
    Final Answer, but NOT external LLM network latency.
    """
    context = _integration_context()

    with TemporaryDirectory(
        prefix="day81_perf_"
    ) as tmp:
        audit_path = (
            Path(tmp)
            / "audit.jsonl"
        )

        started = perf_counter()

        result = execute_governed_analytics_v2(
            context=context,
            question="2025年GMV是多少？",
            reference_date=REFERENCE_DATE,
            runtime_config=_runtime_config(
                audit_path
            ),
            llm_call=_gmv_llm_call,
            execution_policy=PERFORMANCE_POLICY,
            event_id="day81-performance-e2e",
            occurred_at_utc=FIXED_TIME,
            written_at_utc=FIXED_TIME,
        )

        elapsed_ms = (
            perf_counter()
            - started
        ) * 1_000

    return {
        "question": "2025年GMV是多少？",
        "deterministic_llm_fixture": True,
        "external_llm_latency_included": False,
        "elapsed_ms": elapsed_ms,
        "outcome": result.outcome.value,
        "stop_stage": (
            result.stop_stage.value
            if result.stop_stage is not None
            else None
        ),
        "plan_name": result.plan_name,
        "metric_name": result.metric_name,
        "finalization_outcome": (
            result.finalization_outcome
        ),
        "final_answer_status": (
            result.final_answer_status.value
            if result.final_answer_status is not None
            else None
        ),
    }


def _interpret_case(
    item: dict[str, Any],
) -> dict[str, Any]:
    governed = item[
        "governed_runner"
    ]
    explain = item[
        "explain_analyze"
    ]

    if not governed[
        "success"
    ]:
        return {
            "classification": (
                "runner_failed"
            ),
            "reason": (
                governed[
                    "error_type"
                ]
            ),
        }

    if explain is None:
        return {
            "classification": (
                "missing_explain"
            ),
        }

    runner_ms = float(
        governed[
            "median_ms"
        ]
    )
    postgres_ms = float(
        explain[
            "postgres_execution_time_ms"
        ]
        or 0.0
    )

    overhead_ms = max(
        0.0,
        runner_ms
        - postgres_ms,
    )

    db_share = (
        None
        if runner_ms <= 0
        else round(
            postgres_ms
            / runner_ms
            * 100,
            2,
        )
    )

    if (
        db_share is not None
        and db_share >= 80
    ):
        classification = (
            "postgres_dominant"
        )
    elif (
        db_share is not None
        and db_share >= 50
    ):
        classification = (
            "mixed_but_postgres_majority"
        )
    else:
        classification = (
            "runtime_overhead_significant"
        )

    return {
        "classification": classification,
        "governed_runner_median_ms": (
            runner_ms
        ),
        "postgres_execution_time_ms": (
            postgres_ms
        ),
        "approx_non_postgres_boundary_ms": (
            overhead_ms
        ),
        "postgres_share_of_runner_pct": (
            db_share
        ),
    }


def run_performance_baseline(
    *,
    repeats: int,
    report_dir: Path,
) -> Path:
    if repeats < 1:
        raise ValueError(
            "repeats must be >= 1."
        )

    print("=" * 80)
    print(
        "Day81 Dataset V2 Performance Baseline"
    )
    print(
        "Diagnostic statement timeout: "
        f"{PERFORMANCE_POLICY.statement_timeout_ms} ms"
    )
    print(
        "Production default remains unchanged."
    )

    db_context = _database_context()
    cases = _baseline_cases()

    results = []

    for case in cases:
        print("=" * 80)
        print(
            f"{case.case_id} | "
            f"{case.category} | "
            f"{case.plan_name}"
        )

        started = perf_counter()

        try:
            result = _measure_case(
                case,
                repeats=repeats,
            )
        except Exception as exc:
            elapsed_ms = (
                perf_counter()
                - started
            ) * 1_000

            result = {
                **asdict(
                    case
                ),
                "measurement_failed": True,
                "error": (
                    f"{type(exc).__name__}: {exc}"
                ),
                "measurement_elapsed_ms": (
                    elapsed_ms
                ),
            }

            print(
                "[MEASUREMENT FAILED]"
            )
            print(
                result["error"]
            )
        else:
            result[
                "measurement_failed"
            ] = False
            result[
                "interpretation"
            ] = _interpret_case(
                result
            )

            print(
                "Governed Runner median: "
                f"{result['governed_runner']['median_ms']:.2f} ms"
            )

            explain = result[
                "explain_analyze"
            ]

            if explain is not None:
                print(
                    "PostgreSQL EXPLAIN execution: "
                    f"{explain['postgres_execution_time_ms']:.2f} ms"
                )
                print(
                    "Classification: "
                    f"{result['interpretation']['classification']}"
                )

        results.append(
            result
        )

    print("=" * 80)
    print(
        "Deterministic V2 E2E"
    )
    e2e = _measure_deterministic_e2e()

    print(
        f"E2E elapsed: {e2e['elapsed_ms']:.2f} ms"
    )
    print(
        "External LLM latency included: "
        f"{e2e['external_llm_latency_included']}"
    )

    payload = {
        "baseline_version": (
            BASELINE_VERSION
        ),
        "generated_at_utc": (
            datetime.now(
                timezone.utc
            ).isoformat()
        ),
        "dataset_name": "beauty_bi_v2",
        "dataset_status": "draft",
        "diagnostic_policy": {
            "statement_timeout_ms": (
                PERFORMANCE_POLICY.statement_timeout_ms
            ),
            "max_rows": (
                PERFORMANCE_POLICY.max_rows
            ),
            "production_default_changed": False,
        },
        "methodology": {
            "repeats": repeats,
            "governed_runner_timer_scope": (
                "connection acquisition + read-only transaction + "
                "session-local governance config + SQL execution + "
                "bounded fetch + rollback"
            ),
            "postgres_timer_scope": (
                "EXPLAIN ANALYZE reported PostgreSQL execution time"
            ),
            "e2e_scope": (
                "deterministic semantic fixture + analytics planning + "
                "governance + compilation + AST + PostgreSQL + "
                "result protection + audit + final answer"
            ),
            "external_llm_latency_included": False,
            "optimization_performed": False,
        },
        "database_context": db_context,
        "cases": results,
        "deterministic_e2e": e2e,
    }

    report_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    timestamp = datetime.now(
        timezone.utc
    ).strftime(
        "%Y%m%dT%H%M%SZ"
    )

    report_path = (
        report_dir
        / (
            "performance_baseline_v2_"
            f"{timestamp}.json"
        )
    )

    report_path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    print("=" * 80)
    print(
        f"Report: {report_path}"
    )

    failed_measurements = [
        item["case_id"]
        for item in results
        if item.get(
            "measurement_failed"
        )
    ]

    if failed_measurements:
        print(
            "Measurement failures: "
            f"{failed_measurements}"
        )
    else:
        print(
            "Performance measurements completed: "
            f"{len(results)}/{len(results)}"
        )

    return report_path


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--repeats",
        type=int,
        default=1,
        help=(
            "Governed Runner repetitions per case. "
            "Default=1 because some current V2 queries are expensive."
        ),
    )

    parser.add_argument(
        "--report-dir",
        default="docs/evaluation",
    )

    args = parser.parse_args()

    run_performance_baseline(
        repeats=args.repeats,
        report_dir=Path(
            args.report_dir
        ),
    )


if __name__ == "__main__":
    main()
