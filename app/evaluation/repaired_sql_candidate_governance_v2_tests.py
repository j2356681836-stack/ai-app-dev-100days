from __future__ import annotations

from app.evaluation.compiled_sql_ast_enforcer_acceptance_v2 import (
    _ready_pair,
)
from app.governance.compiled_sql_ast_enforcer_v2 import (
    CompiledSqlAstStatusV2,
    enforce_repaired_sql_candidate_v2,
)
from app.governance.repaired_sql_candidate_v2 import (
    build_repaired_sql_candidate_v2,
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


def _candidate(
    *,
    envelope,
    compiled,
    sql: str,
):
    return build_repaired_sql_candidate_v2(
        envelope=envelope,
        source_compiled=compiled,
        repaired_sql=sql,
        repair_attempt=1,
    )


def test_identical_repair_candidate_is_enforced() -> None:
    envelope, compiled = _ready_pair(
        plan_name="gmv_overall_v2",
        question="2025年GMV是多少？",
    )

    candidate = _candidate(
        envelope=envelope,
        compiled=compiled,
        sql=compiled.sql,
    )

    decision = enforce_repaired_sql_candidate_v2(
        envelope=envelope,
        source_compiled=compiled,
        candidate=candidate,
    )

    assert decision.success
    assert (
        decision.status
        == CompiledSqlAstStatusV2.ENFORCED
    )
    assert decision.contract is not None
    assert (
        decision.contract.candidate_fingerprint
        == candidate.candidate_fingerprint
    )


def test_harmless_parentheses_repair_candidate_is_enforced() -> None:
    envelope, compiled = _ready_pair(
        plan_name="gmv_overall_v2",
        question="2025年GMV是多少？",
    )

    placement = _placement_for_dimension(
        envelope,
        "region",
    )

    repaired_sql = compiled.sql.replace(
        placement.sql_fragment,
        f"({placement.sql_fragment})",
        1,
    )

    candidate = _candidate(
        envelope=envelope,
        compiled=compiled,
        sql=repaired_sql,
    )

    decision = enforce_repaired_sql_candidate_v2(
        envelope=envelope,
        source_compiled=compiled,
        candidate=candidate,
    )

    assert decision.success
    assert (
        decision.status
        == CompiledSqlAstStatusV2.ENFORCED
    )


def test_region_scope_weakening_is_denied() -> None:
    envelope, compiled = _ready_pair(
        plan_name="gmv_overall_v2",
        question="2025年GMV是多少？",
    )

    placement = _placement_for_dimension(
        envelope,
        "region",
    )

    repaired_sql = compiled.sql.replace(
        placement.sql_fragment,
        f"({placement.sql_fragment} OR TRUE)",
        1,
    )

    candidate = _candidate(
        envelope=envelope,
        compiled=compiled,
        sql=repaired_sql,
    )

    decision = enforce_repaired_sql_candidate_v2(
        envelope=envelope,
        source_compiled=compiled,
        candidate=candidate,
    )

    assert not decision.success
    assert (
        decision.status
        == CompiledSqlAstStatusV2
        .SCOPE_PREDICATE_MISMATCH
    )


def test_channel_scope_weakening_is_denied() -> None:
    envelope, compiled = _ready_pair(
        plan_name="gmv_overall_v2",
        question="2025年GMV是多少？",
    )

    placement = _placement_for_dimension(
        envelope,
        "channel",
    )

    repaired_sql = compiled.sql.replace(
        placement.sql_fragment,
        f"({placement.sql_fragment} OR TRUE)",
        1,
    )

    candidate = _candidate(
        envelope=envelope,
        compiled=compiled,
        sql=repaired_sql,
    )

    decision = enforce_repaired_sql_candidate_v2(
        envelope=envelope,
        source_compiled=compiled,
        candidate=candidate,
    )

    assert not decision.success
    assert (
        decision.status
        == CompiledSqlAstStatusV2
        .SCOPE_PREDICATE_MISMATCH
    )


def test_parameter_contract_mutation_is_denied() -> None:
    envelope, compiled = _ready_pair(
        plan_name="gmv_overall_v2",
        question="2025年GMV是多少？",
    )

    if not compiled.parameter_names:
        raise AssertionError(
            "Expected compiled parameters."
        )

    parameter_name = compiled.parameter_names[0]

    repaired_sql = compiled.sql.replace(
        f":{parameter_name}",
        "NULL",
        1,
    )

    candidate = _candidate(
        envelope=envelope,
        compiled=compiled,
        sql=repaired_sql,
    )

    decision = enforce_repaired_sql_candidate_v2(
        envelope=envelope,
        source_compiled=compiled,
        candidate=candidate,
    )

    assert not decision.success
    assert (
        decision.status
        == CompiledSqlAstStatusV2
        .PARAMETER_CONTRACT_MISMATCH
    )


def test_source_contract_linkage_tampering_is_denied() -> None:
    envelope, compiled = _ready_pair(
        plan_name="gmv_overall_v2",
        question="2025年GMV是多少？",
    )

    candidate = _candidate(
        envelope=envelope,
        compiled=compiled,
        sql=compiled.sql,
    )

    tampered = candidate.model_copy(
        update={
            "source_compiled_contract_fingerprint": (
                "0" * 64
            )
        }
    )

    decision = enforce_repaired_sql_candidate_v2(
        envelope=envelope,
        source_compiled=compiled,
        candidate=tampered,
    )

    assert not decision.success
    assert (
        decision.status
        == CompiledSqlAstStatusV2
        .INVALID_CONTRACT_LINKAGE
    )


def test_sql_mutation_after_candidate_creation_is_denied() -> None:
    envelope, compiled = _ready_pair(
        plan_name="gmv_overall_v2",
        question="2025年GMV是多少？",
    )

    candidate = _candidate(
        envelope=envelope,
        compiled=compiled,
        sql=compiled.sql,
    )

    tampered = candidate.model_copy(
        update={
            "repaired_sql": (
                compiled.sql
                + "\n"
            )
        }
    )

    decision = enforce_repaired_sql_candidate_v2(
        envelope=envelope,
        source_compiled=compiled,
        candidate=tampered,
    )

    assert not decision.success
    assert (
        decision.status
        == CompiledSqlAstStatusV2
        .SQL_FINGERPRINT_MISMATCH
    )


TESTS = (
    test_identical_repair_candidate_is_enforced,
    test_harmless_parentheses_repair_candidate_is_enforced,
    test_region_scope_weakening_is_denied,
    test_channel_scope_weakening_is_denied,
    test_parameter_contract_mutation_is_denied,
    test_source_contract_linkage_tampering_is_denied,
    test_sql_mutation_after_candidate_creation_is_denied,
)


def main() -> None:
    passed = 0
    failed = 0

    print("=" * 80)
    print(
        "Repaired SQL Candidate Governance V2 Tests"
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
        "Repaired SQL Candidate Governance V2 Summary"
    )
    print(f"Total: {len(TESTS)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
