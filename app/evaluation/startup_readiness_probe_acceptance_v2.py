from __future__ import annotations

from datetime import datetime

from app.db.beauty_bi_v2.startup_readiness_probe_v2 import (
    EXPECTED_TABLES,
    classify_dataset_population_v2,
    classify_schema_state_v2,
    planner_statistics_ready_v2,
)
from app.db.beauty_bi_v2.startup_readiness_v2 import (
    DatasetPopulationStateV2,
    SchemaReadinessStateV2,
)


def _complete_counts(value: int) -> dict[str, int]:
    return {
        table_name: value
        for table_name in EXPECTED_TABLES
    }


def _stats(
    *,
    analyzed: bool = True,
    modified_table: str | None = None,
) -> list[dict]:
    now = datetime(2026, 8, 21, 0, 0, 0)

    return [
        {
            "relname": table_name,
            "last_analyze": now if analyzed else None,
            "last_autoanalyze": None,
            "n_mod_since_analyze": (
                1 if table_name == modified_table else 0
            ),
        }
        for table_name in sorted(EXPECTED_TABLES)
    ]


def test_absent_schema() -> None:
    state = classify_schema_state_v2(
        schema_exists=False,
        actual_tables=set(),
    )
    assert state == SchemaReadinessStateV2.ABSENT


def test_exact_schema() -> None:
    state = classify_schema_state_v2(
        schema_exists=True,
        actual_tables=set(EXPECTED_TABLES),
    )
    assert state == SchemaReadinessStateV2.EXPECTED


def test_missing_table_is_drift() -> None:
    actual = set(EXPECTED_TABLES)
    actual.remove("fact_orders")

    state = classify_schema_state_v2(
        schema_exists=True,
        actual_tables=actual,
    )
    assert state == SchemaReadinessStateV2.DRIFTED


def test_unexpected_table_is_drift() -> None:
    actual = set(EXPECTED_TABLES)
    actual.add("unexpected_table")

    state = classify_schema_state_v2(
        schema_exists=True,
        actual_tables=actual,
    )
    assert state == SchemaReadinessStateV2.DRIFTED


def test_all_zero_is_empty() -> None:
    state = classify_dataset_population_v2(
        _complete_counts(0)
    )
    assert state == DatasetPopulationStateV2.EMPTY


def test_all_positive_is_complete() -> None:
    state = classify_dataset_population_v2(
        _complete_counts(1)
    )
    assert state == DatasetPopulationStateV2.COMPLETE


def test_partial_population_fails_closed() -> None:
    counts = _complete_counts(1)
    counts["fact_reviews"] = 0

    state = classify_dataset_population_v2(counts)

    assert (
        state
        == DatasetPopulationStateV2.PARTIAL_OR_DRIFTED
    )


def test_missing_count_is_drift() -> None:
    counts = _complete_counts(1)
    counts.pop("dim_date")

    state = classify_dataset_population_v2(counts)

    assert (
        state
        == DatasetPopulationStateV2.PARTIAL_OR_DRIFTED
    )


def test_statistics_ready() -> None:
    assert planner_statistics_ready_v2(
        _stats()
    ) is True


def test_missing_analyze_is_not_ready() -> None:
    assert planner_statistics_ready_v2(
        _stats(analyzed=False)
    ) is False


def test_modified_since_analyze_is_not_ready() -> None:
    assert planner_statistics_ready_v2(
        _stats(modified_table="fact_orders")
    ) is False


TESTS = (
    test_absent_schema,
    test_exact_schema,
    test_missing_table_is_drift,
    test_unexpected_table_is_drift,
    test_all_zero_is_empty,
    test_all_positive_is_complete,
    test_partial_population_fails_closed,
    test_missing_count_is_drift,
    test_statistics_ready,
    test_missing_analyze_is_not_ready,
    test_modified_since_analyze_is_not_ready,
)


def main() -> None:
    passed = 0
    failed = 0

    print("=" * 72)
    print("Day90 Startup Readiness Probe Acceptance V2")
    print("=" * 72)

    for test in TESTS:
        try:
            test()
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(
                f"[FAIL] {test.__name__}: "
                f"{type(exc).__name__}: {exc}"
            )
        else:
            passed += 1
            print(f"[PASS] {test.__name__}")

    print("-" * 72)
    print(f"Total: {len(TESTS)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
