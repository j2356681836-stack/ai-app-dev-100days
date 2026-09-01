from __future__ import annotations

from app.semantic_layer.repeat_query_plan_v2_family import (
    build_repeat_customer_rate_overall_plan,
)
from app.semantic_layer.simple_query_plan_v2_builder import (
    SIMPLE_METRIC_SPECS,
    build_simple_query_plan,
)


def _spec(metric: str):
    return next(
        item
        for item in SIMPLE_METRIC_SPECS
        if item.metric == metric
    )


def test_freq_all_grains_use_numeric_division() -> None:
    spec = _spec("purchase_frequency")

    for grain in spec.supported_grains:
        plan = build_simple_query_plan(spec, grain)
        expression = plan["query_logic"]["outputs"][-1]["expression"]

        assert (
            expression
            == "CAST(COUNT(DISTINCT fo.order_id) AS NUMERIC) "
            "/ NULLIF(COUNT(DISTINCT fo.customer_id), 0)"
        ), (grain, expression)


def test_ipt_all_grains_use_numeric_division() -> None:
    spec = _spec("ipt")

    for grain in spec.supported_grains:
        plan = build_simple_query_plan(spec, grain)
        expression = plan["query_logic"]["outputs"][-1]["expression"]

        assert (
            expression
            == "CAST(SUM(foi.quantity) AS NUMERIC) "
            "/ NULLIF(COUNT(DISTINCT fo.order_id), 0)"
        ), (grain, expression)


def test_repeat_rate_uses_numeric_division() -> None:
    plan = build_repeat_customer_rate_overall_plan()

    final_stage = next(
        stage
        for stage in plan.query_logic.stages
        if stage.stage_id == "final"
    )

    expression = next(
        output.expression
        for output in final_stage.outputs
        if output.field == "repeat_customer_rate"
    )

    assert expression == (
        "CAST(COUNT(*) FILTER "
        "(WHERE cps.purchase_day_count >= 2) "
        "AS NUMERIC) / NULLIF(COUNT(*), 0)"
    )


def test_semantic_contract_matches_query_expression() -> None:
    for metric in ("purchase_frequency", "ipt"):
        spec = _spec(metric)

        for grain in spec.supported_grains:
            plan = build_simple_query_plan(spec, grain)
            output_expression = (
                plan["query_logic"]["outputs"][-1]["expression"]
            )
            semantic_expression = (
                plan["semantic_contract"]["metric_expression"]
            )

            assert semantic_expression == output_expression

    repeat = build_repeat_customer_rate_overall_plan()
    final_stage = next(
        stage
        for stage in repeat.query_logic.stages
        if stage.stage_id == "final"
    )
    output_expression = next(
        output.expression
        for output in final_stage.outputs
        if output.field == "repeat_customer_rate"
    )

    assert (
        repeat.semantic_contract.metric_expression
        == output_expression
    )


TESTS = (
    test_freq_all_grains_use_numeric_division,
    test_ipt_all_grains_use_numeric_division,
    test_repeat_rate_uses_numeric_division,
    test_semantic_contract_matches_query_expression,
)


def run_acceptance() -> None:
    passed = 0
    failed = 0

    print("=" * 80)
    print("Day93 Ratio Numeric Semantics Acceptance")
    print(f"Cases: {len(TESTS)}")

    for test in TESTS:
        try:
            test()
        except Exception as exc:
            failed += 1
            print(f"[FAIL] {test.__name__}")
            print(f"{type(exc).__name__}: {exc}")
        else:
            passed += 1
            print(f"[PASS] {test.__name__}")

    print("=" * 80)
    print("Day93 Ratio Numeric Semantics Acceptance Summary")
    print(f"Total: {len(TESTS)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    run_acceptance()
