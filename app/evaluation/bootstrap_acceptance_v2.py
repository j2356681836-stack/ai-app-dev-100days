from __future__ import annotations

from collections import deque

from app.db.beauty_bi_v2.bootstrap_v2 import (
    BootstrapDependenciesV2,
    BootstrapFailClosedError,
    run_bootstrap_v2,
)
from app.db.beauty_bi_v2.startup_readiness_v2 import (
    DatasetPopulationStateV2,
    SchemaReadinessStateV2,
    StartupReadinessReportV2,
    StartupReadinessSnapshotV2,
    StartupReadinessStatusV2,
)


def _snapshot_for(
    status: StartupReadinessStatusV2,
) -> StartupReadinessSnapshotV2:
    mapping = {
        StartupReadinessStatusV2.DATABASE_UNAVAILABLE: dict(
            database_reachable=False,
            schema_state=SchemaReadinessStateV2.ABSENT,
            dataset_population_state=DatasetPopulationStateV2.EMPTY,
            formal_dataset_acceptance_passed=False,
            planner_statistics_ready=False,
            governed_query_runtime_ready=False,
            application_dependency_contract_ready=True,
        ),
        StartupReadinessStatusV2.INITIALIZATION_REQUIRED: dict(
            database_reachable=True,
            schema_state=SchemaReadinessStateV2.ABSENT,
            dataset_population_state=DatasetPopulationStateV2.EMPTY,
            formal_dataset_acceptance_passed=False,
            planner_statistics_ready=False,
            governed_query_runtime_ready=False,
            application_dependency_contract_ready=True,
        ),
        StartupReadinessStatusV2.SEED_REQUIRED: dict(
            database_reachable=True,
            schema_state=SchemaReadinessStateV2.EXPECTED,
            dataset_population_state=DatasetPopulationStateV2.EMPTY,
            formal_dataset_acceptance_passed=False,
            planner_statistics_ready=False,
            governed_query_runtime_ready=False,
            application_dependency_contract_ready=True,
        ),
        StartupReadinessStatusV2.INCONSISTENT: dict(
            database_reachable=True,
            schema_state=SchemaReadinessStateV2.DRIFTED,
            dataset_population_state=(
                DatasetPopulationStateV2.PARTIAL_OR_DRIFTED
            ),
            formal_dataset_acceptance_passed=False,
            planner_statistics_ready=False,
            governed_query_runtime_ready=False,
            application_dependency_contract_ready=True,
        ),
        StartupReadinessStatusV2.VALIDATION_REQUIRED: dict(
            database_reachable=True,
            schema_state=SchemaReadinessStateV2.EXPECTED,
            dataset_population_state=DatasetPopulationStateV2.COMPLETE,
            formal_dataset_acceptance_passed=False,
            planner_statistics_ready=False,
            governed_query_runtime_ready=False,
            application_dependency_contract_ready=True,
        ),
        StartupReadinessStatusV2.STATISTICS_REQUIRED: dict(
            database_reachable=True,
            schema_state=SchemaReadinessStateV2.EXPECTED,
            dataset_population_state=DatasetPopulationStateV2.COMPLETE,
            formal_dataset_acceptance_passed=True,
            planner_statistics_ready=False,
            governed_query_runtime_ready=False,
            application_dependency_contract_ready=True,
        ),
        StartupReadinessStatusV2.QUERY_RUNTIME_REQUIRED: dict(
            database_reachable=True,
            schema_state=SchemaReadinessStateV2.EXPECTED,
            dataset_population_state=DatasetPopulationStateV2.COMPLETE,
            formal_dataset_acceptance_passed=True,
            planner_statistics_ready=True,
            governed_query_runtime_ready=False,
            application_dependency_contract_ready=True,
        ),
        StartupReadinessStatusV2.APPLICATION_RUNTIME_REQUIRED: dict(
            database_reachable=True,
            schema_state=SchemaReadinessStateV2.EXPECTED,
            dataset_population_state=DatasetPopulationStateV2.COMPLETE,
            formal_dataset_acceptance_passed=True,
            planner_statistics_ready=True,
            governed_query_runtime_ready=True,
            application_dependency_contract_ready=False,
        ),
        StartupReadinessStatusV2.READY: dict(
            database_reachable=True,
            schema_state=SchemaReadinessStateV2.EXPECTED,
            dataset_population_state=DatasetPopulationStateV2.COMPLETE,
            formal_dataset_acceptance_passed=True,
            planner_statistics_ready=True,
            governed_query_runtime_ready=True,
            application_dependency_contract_ready=True,
        ),
    }

    return StartupReadinessSnapshotV2(
        **mapping[status]
    )


def _report_for(
    status: StartupReadinessStatusV2,
) -> StartupReadinessReportV2:
    return StartupReadinessReportV2(
        status=status,
        message=f"test status: {status.value}",
        next_action=f"test next action: {status.value}",
    )


class FakeRuntime:
    def __init__(
        self,
        statuses: tuple[StartupReadinessStatusV2, ...],
    ) -> None:
        self.statuses = deque(statuses)
        self.actions: list[str] = []

    def probe(self):
        if not self.statuses:
            raise AssertionError("No fake status remaining.")

        status = self.statuses.popleft()

        return (
            _snapshot_for(status),
            _report_for(status),
        )

    def initialize_schema(self) -> None:
        self.actions.append("initialize_schema")

    def seed_dataset(self) -> None:
        self.actions.append("seed_dataset")

    def analyze_dataset(self) -> None:
        self.actions.append("analyze_dataset")

    def provision_query_runtime(self):
        self.actions.append("provision_query_runtime")
        return {"action": "test"}


def _deps(runtime: FakeRuntime) -> BootstrapDependenciesV2:
    return BootstrapDependenciesV2(
        probe=runtime.probe,
        initialize_schema=runtime.initialize_schema,
        seed_dataset=runtime.seed_dataset,
        analyze_dataset=runtime.analyze_dataset,
        provision_query_runtime=(
            runtime.provision_query_runtime
        ),
    )


def test_ready_is_noop() -> None:
    runtime = FakeRuntime(
        (StartupReadinessStatusV2.READY,)
    )

    result = run_bootstrap_v2(_deps(runtime))

    assert result.status == StartupReadinessStatusV2.READY
    assert runtime.actions == []


def test_fresh_environment_reaches_ready() -> None:
    runtime = FakeRuntime(
        (
            StartupReadinessStatusV2.INITIALIZATION_REQUIRED,
            StartupReadinessStatusV2.SEED_REQUIRED,
            StartupReadinessStatusV2.STATISTICS_REQUIRED,
            StartupReadinessStatusV2.QUERY_RUNTIME_REQUIRED,
            StartupReadinessStatusV2.READY,
        )
    )

    result = run_bootstrap_v2(_deps(runtime))

    assert result.status == StartupReadinessStatusV2.READY
    assert runtime.actions == [
        "initialize_schema",
        "seed_dataset",
        "analyze_dataset",
        "provision_query_runtime",
    ]


def test_existing_dataset_only_needs_analyze() -> None:
    runtime = FakeRuntime(
        (
            StartupReadinessStatusV2.STATISTICS_REQUIRED,
            StartupReadinessStatusV2.READY,
        )
    )

    run_bootstrap_v2(_deps(runtime))

    assert runtime.actions == ["analyze_dataset"]


def test_query_role_only_is_provisioned() -> None:
    runtime = FakeRuntime(
        (
            StartupReadinessStatusV2.QUERY_RUNTIME_REQUIRED,
            StartupReadinessStatusV2.READY,
        )
    )

    run_bootstrap_v2(_deps(runtime))

    assert runtime.actions == ["provision_query_runtime"]


def _assert_fail_closed(
    status: StartupReadinessStatusV2,
) -> None:
    runtime = FakeRuntime((status,))

    try:
        run_bootstrap_v2(_deps(runtime))
    except BootstrapFailClosedError:
        pass
    else:
        raise AssertionError(
            f"{status.value} should fail closed."
        )

    assert runtime.actions == []


def test_database_unavailable_fails_closed() -> None:
    _assert_fail_closed(
        StartupReadinessStatusV2.DATABASE_UNAVAILABLE
    )


def test_inconsistent_fails_closed() -> None:
    _assert_fail_closed(
        StartupReadinessStatusV2.INCONSISTENT
    )


def test_validation_failure_fails_closed() -> None:
    _assert_fail_closed(
        StartupReadinessStatusV2.VALIDATION_REQUIRED
    )


def test_dependency_failure_fails_closed() -> None:
    _assert_fail_closed(
        StartupReadinessStatusV2.APPLICATION_RUNTIME_REQUIRED
    )


TESTS = (
    test_ready_is_noop,
    test_fresh_environment_reaches_ready,
    test_existing_dataset_only_needs_analyze,
    test_query_role_only_is_provisioned,
    test_database_unavailable_fails_closed,
    test_inconsistent_fails_closed,
    test_validation_failure_fails_closed,
    test_dependency_failure_fails_closed,
)


def main() -> None:
    passed = 0
    failed = 0

    print("=" * 72)
    print("Day90 Safe Bootstrap Acceptance V2")
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
