from __future__ import annotations

from app.evaluation.compiled_sql_ast_enforcer_acceptance_v2 import (
    _ready_pair,
    _rebuild_compiled,
)
from app.governance.compiled_sql_ast_enforcer_v2 import (
    CompiledSqlAstStatusV2,
    enforce_compiled_sql_ast_v2,
)


def _placement_for_dimension(
    envelope,
    dimension: str,
):
    matches = [
        placement
        for placement in envelope.scope_binding.placements
        if placement.dimension.value == dimension
    ]

    if not matches:
        raise AssertionError(
            f"No Scope placement found for dimension={dimension}"
        )

    return matches[0]


def _weaken_with_or_true(
    sql: str,
    predicate: str,
) -> str:
    if predicate not in sql:
        raise AssertionError(
            "Expected governed predicate was not found in compiled SQL."
        )

    return sql.replace(
        predicate,
        f"({predicate} OR TRUE)",
        1,
    )


def test_original_compiled_scope_predicates_are_enforced() -> None:
    envelope, compiled = _ready_pair(
        plan_name="gmv_overall_v2",
        question="2025年GMV是多少？",
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


def test_region_scope_or_true_is_denied() -> None:
    """
    This candidate preserves:
    - the same governed physical tables;
    - the same physical columns;
    - the same named parameters;
    - the same output contract.

    But `region_scope OR TRUE` makes the actual Region restriction
    ineffective. Resource/parameter presence alone must not pass.
    """
    envelope, compiled = _ready_pair(
        plan_name="gmv_overall_v2",
        question="2025年GMV是多少？",
    )

    placement = _placement_for_dimension(
        envelope,
        "region",
    )

    malicious_sql = _weaken_with_or_true(
        compiled.sql,
        placement.sql_fragment,
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
        .SCOPE_PREDICATE_MISMATCH
    )


def test_channel_scope_or_true_is_denied() -> None:
    envelope, compiled = _ready_pair(
        plan_name="gmv_overall_v2",
        question="2025年GMV是多少？",
    )

    placement = _placement_for_dimension(
        envelope,
        "channel",
    )

    malicious_sql = _weaken_with_or_true(
        compiled.sql,
        placement.sql_fragment,
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
        .SCOPE_PREDICATE_MISMATCH
    )


def test_harmless_parentheses_do_not_break_scope_identity() -> None:
    """
    The gate compares normalized AST predicates, not raw substrings.
    Harmless parentheses must not be treated as a Scope bypass.
    """
    envelope, compiled = _ready_pair(
        plan_name="gmv_overall_v2",
        question="2025年GMV是多少？",
    )

    placement = _placement_for_dimension(
        envelope,
        "region",
    )

    parenthesized_sql = compiled.sql.replace(
        placement.sql_fragment,
        f"({placement.sql_fragment})",
        1,
    )
    candidate = _rebuild_compiled(
        compiled,
        sql=parenthesized_sql,
    )

    decision = enforce_compiled_sql_ast_v2(
        envelope=envelope,
        compiled=candidate,
    )

    assert decision.success
    assert (
        decision.status
        == CompiledSqlAstStatusV2.ENFORCED
    )


def test_staged_scope_predicate_weakening_is_denied() -> None:
    """
    Verify that Scope placement is checked inside its governed CTE
    stage, not merely somewhere in the full SQL text.
    """
    envelope, compiled = _ready_pair(
        plan_name="repeat_customer_rate_overall_v2",
        question="上月跨日复购率",
    )

    staged_placements = [
        placement
        for placement in envelope.scope_binding.placements
        if placement.stage_id is not None
    ]

    if not staged_placements:
        raise AssertionError(
            "Expected at least one staged Scope placement."
        )

    placement = staged_placements[0]

    malicious_sql = _weaken_with_or_true(
        compiled.sql,
        placement.sql_fragment,
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
        .SCOPE_PREDICATE_MISMATCH
    )


TESTS = (
    test_original_compiled_scope_predicates_are_enforced,
    test_region_scope_or_true_is_denied,
    test_channel_scope_or_true_is_denied,
    test_harmless_parentheses_do_not_break_scope_identity,
    test_staged_scope_predicate_weakening_is_denied,
)


def main() -> None:
    passed = 0
    failed = 0

    print("=" * 80)
    print(
        "Compiled SQL Runtime Scope Predicate V2 Tests"
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
        "Compiled SQL Runtime Scope Predicate V2 Summary"
    )
    print(f"Total: {len(TESTS)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
