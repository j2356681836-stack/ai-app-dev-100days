from __future__ import annotations

from app.db.beauty_bi_v2.startup_readiness_v2 import (
    DatasetPopulationStateV2,
    SchemaReadinessStateV2,
    StartupReadinessSnapshotV2,
    StartupReadinessStatusV2,
    classify_startup_readiness_v2,
)


def _snapshot(
    *,
    database_reachable: bool = True,
    schema_state: SchemaReadinessStateV2 = SchemaReadinessStateV2.EXPECTED,
    dataset_population_state: DatasetPopulationStateV2 = (
        DatasetPopulationStateV2.COMPLETE
    ),
    formal_dataset_acceptance_passed: bool = True,
    planner_statistics_ready: bool = True,
    governed_query_runtime_ready: bool = True,
    application_dependency_contract_ready: bool = True,
) -> StartupReadinessSnapshotV2:
    return StartupReadinessSnapshotV2(
        database_reachable=database_reachable,
        schema_state=schema_state,
        dataset_population_state=dataset_population_state,
        formal_dataset_acceptance_passed=formal_dataset_acceptance_passed,
        planner_statistics_ready=planner_statistics_ready,
        governed_query_runtime_ready=governed_query_runtime_ready,
        application_dependency_contract_ready=(
            application_dependency_contract_ready
        ),
    )


def test_database_unavailable() -> None:
    result = classify_startup_readiness_v2(
        _snapshot(database_reachable=False)
    )
    assert (
        result.status
        == StartupReadinessStatusV2.DATABASE_UNAVAILABLE
    )
    assert result.automatic_repair_allowed is False


def test_schema_absent_requires_initialization() -> None:
    result = classify_startup_readiness_v2(
        _snapshot(
            schema_state=SchemaReadinessStateV2.ABSENT,
            dataset_population_state=DatasetPopulationStateV2.EMPTY,
            formal_dataset_acceptance_passed=False,
            planner_statistics_ready=False,
            governed_query_runtime_ready=False,
        )
    )
    assert (
        result.status
        == StartupReadinessStatusV2.INITIALIZATION_REQUIRED
    )


def test_empty_dataset_requires_seed() -> None:
    result = classify_startup_readiness_v2(
        _snapshot(
            dataset_population_state=DatasetPopulationStateV2.EMPTY,
            formal_dataset_acceptance_passed=False,
            planner_statistics_ready=False,
            governed_query_runtime_ready=False,
        )
    )
    assert result.status == StartupReadinessStatusV2.SEED_REQUIRED


def test_schema_drift_fails_closed() -> None:
    result = classify_startup_readiness_v2(
        _snapshot(schema_state=SchemaReadinessStateV2.DRIFTED)
    )
    assert result.status == StartupReadinessStatusV2.INCONSISTENT
    assert result.automatic_repair_allowed is False


def test_partial_dataset_fails_closed() -> None:
    result = classify_startup_readiness_v2(
        _snapshot(
            dataset_population_state=(
                DatasetPopulationStateV2.PARTIAL_OR_DRIFTED
            ),
            formal_dataset_acceptance_passed=False,
            planner_statistics_ready=False,
            governed_query_runtime_ready=False,
        )
    )
    assert result.status == StartupReadinessStatusV2.INCONSISTENT


def test_contradictory_snapshot_fails_closed() -> None:
    result = classify_startup_readiness_v2(
        _snapshot(
            schema_state=SchemaReadinessStateV2.ABSENT,
            dataset_population_state=DatasetPopulationStateV2.COMPLETE,
        )
    )
    assert result.status == StartupReadinessStatusV2.INCONSISTENT


def test_validation_required_before_analyze() -> None:
    result = classify_startup_readiness_v2(
        _snapshot(formal_dataset_acceptance_passed=False)
    )
    assert (
        result.status
        == StartupReadinessStatusV2.VALIDATION_REQUIRED
    )


def test_statistics_required_after_acceptance() -> None:
    result = classify_startup_readiness_v2(
        _snapshot(planner_statistics_ready=False)
    )
    assert (
        result.status
        == StartupReadinessStatusV2.STATISTICS_REQUIRED
    )


def test_query_runtime_required_after_statistics() -> None:
    result = classify_startup_readiness_v2(
        _snapshot(governed_query_runtime_ready=False)
    )
    assert (
        result.status
        == StartupReadinessStatusV2.QUERY_RUNTIME_REQUIRED
    )


def test_application_runtime_requires_dependency_contract() -> None:
    result = classify_startup_readiness_v2(
        _snapshot(application_dependency_contract_ready=False)
    )
    assert (
        result.status
        == StartupReadinessStatusV2.APPLICATION_RUNTIME_REQUIRED
    )


def test_ready_does_not_request_reinitialization() -> None:
    result = classify_startup_readiness_v2(_snapshot())
    assert result.status == StartupReadinessStatusV2.READY
    assert result.automatic_repair_allowed is False
    assert "不需要重新 Seed" in result.next_action


TESTS = (
    test_database_unavailable,
    test_schema_absent_requires_initialization,
    test_empty_dataset_requires_seed,
    test_schema_drift_fails_closed,
    test_partial_dataset_fails_closed,
    test_contradictory_snapshot_fails_closed,
    test_validation_required_before_analyze,
    test_statistics_required_after_acceptance,
    test_query_runtime_required_after_statistics,
    test_application_runtime_requires_dependency_contract,
    test_ready_does_not_request_reinitialization,
)


def main() -> None:
    passed = 0
    failed = 0

    print("=" * 72)
    print("Day90 Startup Readiness Contract Acceptance V2")
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
