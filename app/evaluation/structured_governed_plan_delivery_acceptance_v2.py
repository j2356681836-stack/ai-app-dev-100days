from __future__ import annotations

import inspect

from app.delivery.runtime_delivery_bridge_v2 import (
    invoke_governed_plan_delivery_v2,
)


def test_structured_path_skips_natural_language_semantic_planning() -> None:
    source = inspect.getsource(
        invoke_governed_plan_delivery_v2
    )

    assert "build_governed_analyst_graph_v2" not in source
    assert "resolve_analytics_planning_v2" not in source
    assert "parse_question_semantics_v2" not in source


def test_structured_path_keeps_governance_and_execution() -> None:
    source = inspect.getsource(
        invoke_governed_plan_delivery_v2
    )

    assert "build_governed_planning_envelope_v2" in source
    assert "compile_governed_query_plan_v2" in source
    assert "execute_governed_query_v2" in source
    assert "generate_final_answer_v2" in source
    assert "build_runtime_delivery_from_governed_state_v2" in source


def test_structured_path_requires_approved_binding() -> None:
    source = inspect.getsource(
        invoke_governed_plan_delivery_v2
    )

    assert "approved_tool_binding.plan_name != plan_name" in source


TESTS = (
    test_structured_path_skips_natural_language_semantic_planning,
    test_structured_path_keeps_governance_and_execution,
    test_structured_path_requires_approved_binding,
)


def run_acceptance() -> None:
    print("Day89 Structured Governed Plan Delivery Acceptance")

    passed = 0
    failures: list[str] = []

    for test in TESTS:
        try:
            test()
            passed += 1
        except Exception as exc:  # noqa: BLE001
            failures.append(
                f"{test.__name__}: "
                f"{type(exc).__name__}: {exc}"
            )

    print(f"Total: {len(TESTS)}")
    print(f"Passed: {passed}")
    print(f"Failed: {len(failures)}")

    for failure in failures:
        print(f"- {failure}")

    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    run_acceptance()
