from __future__ import annotations

from app.delivery.decision_console_runtime_v2 import (
    DAY89_LOCAL_CHANNEL_CODES,
    DAY89_LOCAL_REGION_CODES,
    DAY89_RUNTIME_VERSION,
    build_day89_channel_tool_binding_v2,
    build_day89_local_access_context_v2,
)
from app.governance.access_context import (
    AccessRole,
    OperationMode,
)
from app.semantic_layer.query_plan_v2_loader import (
    load_query_plan_v2_catalog,
)
from app.semantic_layer.channel_applicability_v2 import (
    ChannelBusinessRoleV2,
    channel_codes_for_role_v2,
)


EXPECTED_VERSION = "decision_console_runtime_v2_0"


def _catalog_resources():
    catalog = load_query_plan_v2_catalog()

    return (
        frozenset(
            plan.metric
            for plan in catalog.query_plans
        ),
        frozenset(
            table
            for plan in catalog.query_plans
            for table in plan.resource_contract.required_tables
        ),
        frozenset(
            column
            for plan in catalog.query_plans
            for column in plan.resource_contract.required_columns
        ),
    )


def test_version_is_expected() -> None:
    assert DAY89_RUNTIME_VERSION == EXPECTED_VERSION


def test_local_context_is_dataset_v2_observe_advise() -> None:
    context = build_day89_local_access_context_v2(
        request_id="day89-runtime-test",
    )

    assert context.dataset_name == "beauty_bi_v2"
    assert context.target_schema == "beauty_bi_v2"
    assert context.role == AccessRole.SCOPED_ANALYST
    assert context.operation_mode == OperationMode.OBSERVE_ADVISE


def test_local_context_resources_come_from_catalog() -> None:
    metrics, tables, columns = _catalog_resources()

    context = build_day89_local_access_context_v2(
        request_id="day89-runtime-test",
    )

    assert context.allowed_metrics == metrics
    assert context.allowed_tables == tables
    assert context.allowed_columns == columns


def test_ui_scope_is_server_owned() -> None:
    context = build_day89_local_access_context_v2(
        request_id="day89-runtime-test",
    )

    expected_sales_channels = (
        DAY89_LOCAL_CHANNEL_CODES
        & channel_codes_for_role_v2(
            ChannelBusinessRoleV2.SALES
        )
    )

    # Governance boundary remains server-owned, but the server-owned
    # authorization scope is now further narrowed by business applicability:
    #
    # Authorized Scope ∩ Metric Applicable Scope.
    #
    # Therefore GMV / sales-oriented Decision Console scope must not include
    # marketing-only channels such as Xiaohongshu.
    assert context.allowed_channel_codes == expected_sales_channels
    assert "XIAOHONGSHU" not in context.allowed_channel_codes
    assert context.allowed_region_codes == DAY89_LOCAL_REGION_CODES
    assert context.denied_columns == frozenset()


def test_sensitive_defaults_remain_restrictive() -> None:
    context = build_day89_local_access_context_v2(
        request_id="day89-runtime-test",
    )

    policy = context.sensitive_data_policy

    assert policy.allow_direct_identifiers is False
    assert policy.allow_free_text is False
    assert policy.allow_cost_data is False
    assert policy.minimum_group_size == 5


def test_channel_tool_binding_is_static_and_governed() -> None:
    binding = build_day89_channel_tool_binding_v2()

    assert binding.plan_name == "gmv_channel_v2"
    assert (
        binding.tool_contract.identity.name
        == "governed_gmv_channel_query"
    )
    assert binding.tool_contract.identity.version == "dataset_v2"
    assert (
        binding.tool_contract.executor_binding
        == "execute_governed_query_v2"
    )


def test_runtime_module_does_not_depend_on_evaluation_fixture() -> None:
    import inspect
    import app.delivery.decision_console_runtime_v2 as module

    source = inspect.getsource(module)

    assert "app.evaluation" not in source


TESTS = (
    test_version_is_expected,
    test_local_context_is_dataset_v2_observe_advise,
    test_local_context_resources_come_from_catalog,
    test_ui_scope_is_server_owned,
    test_sensitive_defaults_remain_restrictive,
    test_channel_tool_binding_is_static_and_governed,
    test_runtime_module_does_not_depend_on_evaluation_fixture,
)


def run_acceptance() -> None:
    print("Day89 Decision Console Runtime Composition Acceptance")

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
