from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

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
from app.evaluation.performance_baseline_v2 import (
    _baseline_cases,
    _ready_pair,
)
from app.governance.execution_policy import (
    GovernedExecutionPolicy,
)
from app.governance.governed_analytics_service_v2 import (
    GovernedAnalyticsOutcomeV2,
    execute_governed_analytics_v2,
)


PRODUCTION_POLICY = GovernedExecutionPolicy()
ACCEPTANCE_VERSION = "production_policy_performance_v2_0"


def _run_sql_cases() -> list[dict]:
    results: list[dict] = []

    for case in _baseline_cases():
        envelope, compiled = _ready_pair(
            plan_name=case.plan_name,
            question=case.question,
        )

        result = run_governed_sql(
            sql=compiled.sql,
            parameters=compiled.parameter_mapping(),
            policy=PRODUCTION_POLICY,
        )

        item = {
            "case_id": case.case_id,
            "category": case.category,
            "plan_name": case.plan_name,
            "metric_name": envelope.metric_name,
            "success": result.success,
            "execution_time_ms": result.execution_time_ms,
            "statement_timeout_ms": result.statement_timeout_ms,
            "row_count": result.row_count,
            "error_type": (
                result.error_type.value
                if result.error_type is not None
                else None
            ),
            "message": result.message,
        }

        results.append(item)

        print(
            f"{case.case_id} | {case.plan_name} | "
            f"success={result.success} | "
            f"runner={result.execution_time_ms:.2f} ms | "
            f"timeout={result.statement_timeout_ms} ms"
        )

        if not result.success:
            raise AssertionError(
                "Production policy query failed. "
                f"case={case.case_id}, "
                f"plan={case.plan_name}, "
                f"error_type={item['error_type']}, "
                f"message={item['message']}"
            )

    return results


def _run_deterministic_e2e() -> dict:
    context = _integration_context()

    with TemporaryDirectory(
        prefix="day81_prod_policy_"
    ) as tmp:
        audit_path = Path(tmp) / "audit.jsonl"

        started = perf_counter()

        result = execute_governed_analytics_v2(
            context=context,
            question="2025年GMV是多少？",
            reference_date=REFERENCE_DATE,
            runtime_config=_runtime_config(audit_path),
            llm_call=_gmv_llm_call,
            execution_policy=PRODUCTION_POLICY,
            event_id="day81-production-policy-e2e",
            occurred_at_utc=FIXED_TIME,
            written_at_utc=FIXED_TIME,
        )

        elapsed_ms = (
            perf_counter() - started
        ) * 1_000

    if (
        result.outcome
        != GovernedAnalyticsOutcomeV2.ANSWERED
    ):
        raise AssertionError(
            "Deterministic V2 E2E failed under the production "
            "execution policy. "
            f"outcome={result.outcome.value}, "
            f"stop_stage={getattr(result.stop_stage, 'value', None)}, "
            f"detail={result.detail}"
        )

    print(
        "E2E | gmv_overall_v2 | "
        f"outcome={result.outcome.value} | "
        f"elapsed={elapsed_ms:.2f} ms"
    )

    return {
        "question": "2025年GMV是多少？",
        "plan_name": result.plan_name,
        "metric_name": result.metric_name,
        "outcome": result.outcome.value,
        "elapsed_ms": elapsed_ms,
        "external_llm_latency_included": False,
        "statement_timeout_ms": (
            PRODUCTION_POLICY.statement_timeout_ms
        ),
    }


def run_acceptance(
    *,
    report_dir: Path = Path("docs/evaluation"),
) -> Path:
    print("=" * 80)
    print(
        "Day81 Production 5s Policy Performance Acceptance"
    )
    print(
        "statement_timeout_ms="
        f"{PRODUCTION_POLICY.statement_timeout_ms}"
    )
    print(
        "max_rows="
        f"{PRODUCTION_POLICY.max_rows}"
    )

    assert (
        PRODUCTION_POLICY.statement_timeout_ms
        == 5_000
    ), (
        "Production default statement_timeout changed unexpectedly."
    )

    assert (
        PRODUCTION_POLICY.max_rows
        == 200
    ), (
        "Production default max_rows changed unexpectedly."
    )

    print("=" * 80)
    sql_results = _run_sql_cases()

    print("=" * 80)
    e2e = _run_deterministic_e2e()

    payload = {
        "acceptance_version": ACCEPTANCE_VERSION,
        "generated_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "dataset_name": "beauty_bi_v2",
        "dataset_status": "draft",
        "production_policy": {
            "statement_timeout_ms": (
                PRODUCTION_POLICY.statement_timeout_ms
            ),
            "max_rows": (
                PRODUCTION_POLICY.max_rows
            ),
            "policy_version": (
                PRODUCTION_POLICY.policy_version
            ),
        },
        "sql_cases": sql_results,
        "deterministic_e2e": e2e,
        "external_llm_latency_included": False,
        "note": (
            "This proves representative Dataset V2 queries succeed "
            "under the production database execution policy after "
            "Planner Statistics remediation. It is not an external "
            "LLM latency SLO."
        ),
    }

    report_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    timestamp = datetime.now(
        timezone.utc
    ).strftime("%Y%m%dT%H%M%SZ")

    report_path = (
        report_dir
        / (
            "production_policy_performance_v2_"
            f"{timestamp}.json"
        )
    )

    report_path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("=" * 80)
    print("Production Policy Acceptance Summary")
    print(f"SQL Cases: {len(sql_results)} / {len(sql_results)} PASS")
    print("Deterministic E2E: PASS")
    print(
        "Production statement_timeout: "
        f"{PRODUCTION_POLICY.statement_timeout_ms} ms"
    )
    print(f"Report: {report_path}")

    return report_path


if __name__ == "__main__":
    run_acceptance()
