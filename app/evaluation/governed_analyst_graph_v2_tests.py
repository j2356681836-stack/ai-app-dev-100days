from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import app.agents.governed_graph_nodes_v2 as nodes
from app.agents.governed_analyst_graph_v2 import (
    ask_with_governed_graph_v2,
)
from app.governance.access_context import (
    AccessContext,
    AccessRole,
    OperationMode,
    SensitiveDataPolicy,
)
from app.governance.compiled_sql_ast_enforcer_v2 import (
    CompiledSqlAstStatusV2,
)
from app.governance.governance_runtime import (
    GovernanceRuntimeConfig,
)
from app.governance.governed_planning_envelope_v2 import (
    GovernedPlanningStatusV2,
)
from app.semantic_layer.analytics_planning_service_v2 import (
    AnalyticsPlanningStatusV2,
)
from app.semantic_layer.query_plan_compiler_v2 import (
    QueryPlanCompileStatusV2,
)
from app.text_to_sql.final_answer_v2 import (
    FinalAnswerStatusV2,
)


REFERENCE_DATE = date(
    2026,
    8,
    9,
)


def assert_equal(
    actual,
    expected,
    message: str,
) -> None:
    if actual != expected:
        raise AssertionError(
            f"{message}\nExpected: {expected}\nActual: {actual}"
        )


@contextmanager
def patch_node_dependencies(
    **replacements,
):
    originals = {}

    try:
        for name, replacement in replacements.items():
            originals[name] = getattr(
                nodes,
                name,
            )
            setattr(
                nodes,
                name,
                replacement,
            )

        yield

    finally:
        for name, original in originals.items():
            setattr(
                nodes,
                name,
                original,
            )


def _context() -> AccessContext:
    return AccessContext(
        request_id="day80-step1-request",
        actor_id="day80-test-actor",
        role=AccessRole.SCOPED_ANALYST,
        dataset_name="beauty_bi_v2",
        target_schema="beauty_bi_v2",
        operation_mode=OperationMode.OBSERVE_ADVISE,
        allowed_metrics=frozenset(
            {
                "gmv",
                "roi",
            }
        ),
        allowed_tables=frozenset(),
        allowed_columns=frozenset(),
        denied_columns=frozenset(),
        allowed_region_codes=frozenset(
            {
                "SHANGHAI",
            }
        ),
        allowed_channel_codes=frozenset(
            {
                "JD",
                "TMALL",
            }
        ),
        sensitive_data_policy=SensitiveDataPolicy(),
        policy_version="day80_test_policy_v1",
        scope_source="day80_step1_test",
    )


def _runtime_config() -> GovernanceRuntimeConfig:
    return GovernanceRuntimeConfig(
        result_tokenization_secret=(
            "day80-tokenization-secret"
        ),
        audit_secret=(
            "day80-audit-secret-value"
        ),
        audit_log_path=Path(
            "day80_step1_test_audit.jsonl"
        ),
        fsync_enabled=False,
    )


def _analytics_single():
    return SimpleNamespace(
        status=(
            AnalyticsPlanningStatusV2
            .PLANNED_SINGLE
        ),
        semantic_decision=SimpleNamespace(
            candidates=("gmv",),
        ),
        metric_name="gmv",
        plan_names=("gmv_overall_v2",),
        detail=None,
    )


def _analytics_multiple():
    return SimpleNamespace(
        status=(
            AnalyticsPlanningStatusV2
            .PLANNED_MULTIPLE
        ),
        semantic_decision=SimpleNamespace(
            candidates=("gmv",),
        ),
        metric_name="gmv",
        plan_names=(
            "gmv_channel_v2",
            "gmv_region_v2",
        ),
        detail=None,
    )


def _plan():
    return SimpleNamespace(
        name="gmv_overall_v2",
        metric="gmv",
    )


def _time_resolution():
    return SimpleNamespace(
        status="resolved",
    )


def _envelope():
    return SimpleNamespace(
        metric_name="gmv",
        plan_name="gmv_overall_v2",
        envelope_fingerprint=(
            "a" * 64
        ),
    )


def _compiled():
    return SimpleNamespace(
        contract_fingerprint=(
            "b" * 64
        ),
        sql_fingerprint=(
            "c" * 64
        ),
    )


def _governed_ready():
    return SimpleNamespace(
        status=(
            GovernedPlanningStatusV2
            .READY_FOR_COMPILATION
        ),
        ready=True,
        envelope=_envelope(),
        detail=None,
    )


def _governed_blocked():
    return SimpleNamespace(
        status=(
            GovernedPlanningStatusV2
            .SCOPE_BINDING_NOT_READY
        ),
        ready=False,
        envelope=None,
        detail="scope binding blocked",
    )


def _compiled_success():
    return SimpleNamespace(
        success=True,
        status=(
            QueryPlanCompileStatusV2.COMPILED
        ),
        contract=_compiled(),
        detail=None,
    )


def _ast_success():
    return SimpleNamespace(
        success=True,
        status=(
            CompiledSqlAstStatusV2.ENFORCED
        ),
        contract=SimpleNamespace(),
        detail=None,
    )


def _ast_failed():
    return SimpleNamespace(
        success=False,
        status=(
            CompiledSqlAstStatusV2
            .COLUMN_CONTRACT_MISMATCH
        ),
        contract=None,
        detail="column contract mismatch",
    )


def _finalization_success():
    return SimpleNamespace(
        outcome=SimpleNamespace(
            value="succeeded",
        ),
    )


def _final_answer_success():
    return SimpleNamespace(
        status=FinalAnswerStatusV2.ANSWERED,
        answer="2025年GMV为 11,430,211.41。",
        scope_disclosure=SimpleNamespace(
            summary=(
                "地区代码：SHANGHAI；"
                "渠道代码：JD、TMALL"
            )
        ),
    )


def _common_patches(
    *,
    executor_calls: list[str],
) -> dict[str, Any]:
    def fake_resolve_analytics_planning_v2(
        **kwargs,
    ):
        return _analytics_single()

    def fake_get_query_plan_v2_by_name(
        plan_name: str,
    ):
        return _plan()

    def fake_resolve_time_window_v2(
        question: str,
        *,
        reference_date: date,
    ):
        return _time_resolution()

    def fake_build_governed_planning_envelope_v2(
        **kwargs,
    ):
        return _governed_ready()

    def fake_compile_governed_query_plan_v2(
        envelope,
    ):
        return _compiled_success()

    def fake_enforce_compiled_sql_ast_v2(
        **kwargs,
    ):
        return _ast_success()

    def fake_execute_governed_query_v2(
        **kwargs,
    ):
        executor_calls.append(
            "execute"
        )
        return _finalization_success()

    def fake_generate_final_answer_v2(
        **kwargs,
    ):
        return _final_answer_success()

    return {
        "resolve_analytics_planning_v2": (
            fake_resolve_analytics_planning_v2
        ),
        "get_query_plan_v2_by_name": (
            fake_get_query_plan_v2_by_name
        ),
        "resolve_time_window_v2": (
            fake_resolve_time_window_v2
        ),
        "build_governed_planning_envelope_v2": (
            fake_build_governed_planning_envelope_v2
        ),
        "compile_governed_query_plan_v2": (
            fake_compile_governed_query_plan_v2
        ),
        "enforce_compiled_sql_ast_v2": (
            fake_enforce_compiled_sql_ast_v2
        ),
        "execute_governed_query_v2": (
            fake_execute_governed_query_v2
        ),
        "generate_final_answer_v2": (
            fake_generate_final_answer_v2
        ),
    }


def test_planned_single_reaches_final_answer() -> None:
    executor_calls: list[str] = []

    with patch_node_dependencies(
        **_common_patches(
            executor_calls=executor_calls,
        )
    ):
        result = ask_with_governed_graph_v2(
            context=_context(),
            question="2025年GMV是多少？",
            reference_date=REFERENCE_DATE,
            runtime_config=_runtime_config(),
        )

    assert_equal(
        result.get("success"),
        True,
        "PLANNED_SINGLE should reach a successful Final Answer.",
    )
    assert_equal(
        result.get("outcome"),
        "answered",
        "Successful path should return answered.",
    )
    assert_equal(
        result.get("ast_status"),
        "enforced",
        "Successful path must expose Graph-visible AST evidence.",
    )
    assert_equal(
        executor_calls,
        ["execute"],
        "Successful path should execute exactly once.",
    )

    if "sql" in result or "rows" in result:
        raise AssertionError(
            "Public Graph result must not expose raw SQL or rows."
        )


def test_governed_planning_block_stops_before_compilation() -> None:
    executor_calls: list[str] = []
    compile_calls: list[str] = []

    patches = _common_patches(
        executor_calls=executor_calls,
    )

    def fake_build_governed_planning_envelope_v2(
        **kwargs,
    ):
        return _governed_blocked()

    def fail_if_compiled(
        envelope,
    ):
        compile_calls.append(
            "compile"
        )
        raise AssertionError(
            "Blocked governed planning must not reach compilation."
        )

    patches[
        "build_governed_planning_envelope_v2"
    ] = fake_build_governed_planning_envelope_v2
    patches[
        "compile_governed_query_plan_v2"
    ] = fail_if_compiled

    with patch_node_dependencies(
        **patches
    ):
        result = ask_with_governed_graph_v2(
            context=_context(),
            question="ROI是多少？",
            reference_date=REFERENCE_DATE,
            runtime_config=_runtime_config(),
        )

    assert_equal(
        result.get("outcome"),
        "blocked",
        "Governed Planning failure should fail closed.",
    )
    assert_equal(
        result.get("stop_stage"),
        "governed_planning",
        "Stop stage should be governed_planning.",
    )
    assert_equal(
        compile_calls,
        [],
        "Compilation must not be called after planning block.",
    )
    assert_equal(
        executor_calls,
        [],
        "Database executor must not be called after planning block.",
    )


def test_ast_failure_stops_before_postgresql() -> None:
    executor_calls: list[str] = []

    patches = _common_patches(
        executor_calls=executor_calls,
    )

    def fake_enforce_compiled_sql_ast_v2(
        **kwargs,
    ):
        return _ast_failed()

    patches[
        "enforce_compiled_sql_ast_v2"
    ] = fake_enforce_compiled_sql_ast_v2

    with patch_node_dependencies(
        **patches
    ):
        result = ask_with_governed_graph_v2(
            context=_context(),
            question="2025年GMV是多少？",
            reference_date=REFERENCE_DATE,
            runtime_config=_runtime_config(),
        )

    assert_equal(
        result.get("outcome"),
        "blocked",
        "AST failure must fail closed.",
    )
    assert_equal(
        result.get("stop_stage"),
        "runtime_ast_enforcement",
        "AST failure must expose the runtime AST stop stage.",
    )
    assert_equal(
        result.get("ast_status"),
        "column_contract_mismatch",
        "AST evidence should preserve the deterministic failure status.",
    )
    assert_equal(
        executor_calls,
        [],
        "PostgreSQL execution must not occur after AST failure.",
    )


def test_planned_multiple_stops_before_plan_load() -> None:
    executor_calls: list[str] = []
    plan_load_calls: list[str] = []

    patches = _common_patches(
        executor_calls=executor_calls,
    )

    def fake_resolve_analytics_planning_v2(
        **kwargs,
    ):
        return _analytics_multiple()

    def fail_if_plan_loaded(
        plan_name: str,
    ):
        plan_load_calls.append(
            plan_name
        )
        raise AssertionError(
            "PLANNED_MULTIPLE must stop before Query Plan loading."
        )

    patches[
        "resolve_analytics_planning_v2"
    ] = fake_resolve_analytics_planning_v2
    patches[
        "get_query_plan_v2_by_name"
    ] = fail_if_plan_loaded

    with patch_node_dependencies(
        **patches
    ):
        result = ask_with_governed_graph_v2(
            context=_context(),
            question="分别按渠道和地区看2025年GMV",
            reference_date=REFERENCE_DATE,
            runtime_config=_runtime_config(),
        )

    assert_equal(
        result.get("success"),
        False,
        "PLANNED_MULTIPLE is not executable in Day80 Step 1.",
    )
    assert_equal(
        result.get("stop_stage"),
        "analytics_planning",
        "PLANNED_MULTIPLE must stop at Analytics Planning.",
    )
    assert_equal(
        result.get("analytics_planning_status"),
        "planned_multiple",
        "Graph must preserve the semantic planning status.",
    )
    assert_equal(
        plan_load_calls,
        [],
        "PLANNED_MULTIPLE must not load a single Query Plan.",
    )
    assert_equal(
        executor_calls,
        [],
        "PLANNED_MULTIPLE must not reach PostgreSQL.",
    )


TESTS = (
    test_planned_single_reaches_final_answer,
    test_governed_planning_block_stops_before_compilation,
    test_ast_failure_stops_before_postgresql,
    test_planned_multiple_stops_before_plan_load,
)


def main() -> None:
    passed = 0
    failed = 0

    print("=" * 80)
    print(
        "Governed Analyst Graph V2 Step 1 Contract Tests"
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
        "Governed Analyst Graph V2 Step 1 Summary"
    )
    print(f"Total: {len(TESTS)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
