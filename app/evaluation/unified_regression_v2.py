from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class RegressionCaseV2:
    category: str
    name: str
    module: str


REGRESSION_CASES_V2: tuple[RegressionCaseV2, ...] = (
    # Core / Semantic
    RegressionCaseV2(
        category="semantic",
        name="Question Semantic Parser Regression",
        module=(
            "app.evaluation."
            "question_semantic_parser_regression_v2_tests"
        ),
    ),
    RegressionCaseV2(
        category="semantic",
        name="Candidate Decision Pipeline Regression",
        module=(
            "app.semantic_layer."
            "candidate_decision_pipeline_v2_tests"
        ),
    ),
    RegressionCaseV2(
        category="semantic",
        name="Embedding Shared Client Regression",
        module=(
            "app.llm."
            "embedding_client_tests"
        ),
    ),
    RegressionCaseV2(
        category="semantic",
        name="Embedding Service Regression",
        module=(
            "app.semantic_layer."
            "embedding_service_tests"
        ),
    ),
    RegressionCaseV2(
        category="semantic",
        name="Metric Semantic Cloud Runtime Regression",
        module=(
            "app.semantic_layer."
            "metric_semantic_cloud_runtime_v2_tests"
        ),
    ),

    # Governance / Security
    RegressionCaseV2(
        category="governance",
        name="Governed Query Execution Acceptance",
        module=(
            "app.evaluation."
            "governed_query_execution_acceptance_v2"
        ),
    ),
    RegressionCaseV2(
        category="governance",
        name="Governed Finalization Tests",
        module=(
            "app.evaluation."
            "governed_finalization_tests"
        ),
    ),
    RegressionCaseV2(
        category="governance",
        name="Audit Sink Tests",
        module=(
            "app.evaluation."
            "audit_sink_tests"
        ),
    ),

    # Agent / Investigation
    RegressionCaseV2(
        category="agent",
        name="Investigation Runtime Acceptance",
        module=(
            "app.evaluation."
            "investigation_runtime_acceptance_v2"
        ),
    ),
    RegressionCaseV2(
        category="agent",
        name="Investigation Tool Executor Acceptance",
        module=(
            "app.evaluation."
            "investigation_tool_executor_acceptance_v2"
        ),
    ),

    # Delivery
    RegressionCaseV2(
        category="delivery",
        name="Decision Console Runtime Acceptance",
        module=(
            "app.evaluation."
            "decision_console_runtime_acceptance_v2"
        ),
    ),
    RegressionCaseV2(
        category="delivery",
        name="Runtime Delivery Binding Registry Regression",
        module=(
            "app.delivery."
            "runtime_delivery_binding_registry_v2_tests"
        ),
    ),
    RegressionCaseV2(
        category="delivery",
        name="Decision Console FACT KPI Projection Regression",
        module=(
            "app.evaluation."
            "decision_console_fact_kpi_projection_v2_tests"
        ),
    ),
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the deterministic Unified Regression V2 gate."
        )
    )

    parser.add_argument(
        "--category",
        choices=(
            "semantic",
            "governance",
            "agent",
            "delivery",
        ),
        help=(
            "Only run one regression category. "
            "Default: run all categories."
        ),
    )

    parser.add_argument(
        "--list",
        action="store_true",
        help="List regression cases without running them.",
    )

    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop after the first failed module.",
    )

    return parser


def _selected_cases(
    category: str | None,
) -> tuple[RegressionCaseV2, ...]:
    if category is None:
        return REGRESSION_CASES_V2

    return tuple(
        case
        for case in REGRESSION_CASES_V2
        if case.category == category
    )


def _regression_environment() -> dict[str, str]:
    """
    Build a deterministic regression environment.

    Important:
    - Langfuse Observability is disabled for the unified regression gate;
    - live LLM / external observability must not be a deterministic CI gate;
    - each child test still receives the caller's normal project environment.
    """
    env = os.environ.copy()

    env["LANGFUSE_OBSERVABILITY_ENABLED"] = "false"
    env.setdefault("PYTHONUTF8", "1")

    return env


def _run_case(
    case: RegressionCaseV2,
) -> int:
    command = [
        sys.executable,
        "-m",
        case.module,
    ]

    print()
    print("=" * 80)
    print(
        f"[RUN] category={case.category} "
        f"name={case.name}"
    )
    print(f"[MODULE] {case.module}")
    print("=" * 80)

    completed = subprocess.run(
        command,
        env=_regression_environment(),
        check=False,
    )

    if completed.returncode == 0:
        print(
            f"[PASS] {case.name}"
        )
    else:
        print(
            f"[FAIL] {case.name} "
            f"(exit_code={completed.returncode})"
        )

    return completed.returncode


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    cases = _selected_cases(args.category)

    if args.list:
        print("Unified Regression V2 Cases")
        for case in cases:
            print(
                f"- [{case.category}] "
                f"{case.name}: {case.module}"
            )
        return

    passed = 0
    failed = 0
    failed_cases: list[str] = []

    for case in cases:
        return_code = _run_case(case)

        if return_code == 0:
            passed += 1
            continue

        failed += 1
        failed_cases.append(case.name)

        if args.fail_fast:
            break

    total = passed + failed

    print()
    print("=" * 80)
    print("Unified Regression V2 Summary")
    print(f"Total modules: {total}")
    print(f"Passed modules: {passed}")
    print(f"Failed modules: {failed}")

    if failed_cases:
        print(
            "Failed cases: "
            + ", ".join(failed_cases)
        )

    print("=" * 80)

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
