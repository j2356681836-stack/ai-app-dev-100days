from __future__ import annotations

from collections import Counter
from datetime import date

from app.governance.access_context import (
    AccessContext,
    AccessRole,
    OperationMode,
    SensitiveDataPolicy,
)
from app.governance.authorization import (
    AuthorizationReason,
)
from app.governance.governed_planning_envelope_v2 import (
    GovernedPlanningBlockedStageV2,
    GovernedPlanningStatusV2,
    build_governed_planning_envelope_v2,
    query_plan_fingerprint_v2,
)
from app.governance.query_plan_scope_binding_v2 import (
    QueryPlanScopeBindingStatusV2,
)
from app.semantic_layer.query_plan_v2_loader import (
    get_query_plan_v2_by_name,
    load_query_plan_v2_catalog,
)
from app.semantic_layer.time_window_resolver_v2 import (
    resolve_time_window_v2,
)


REFERENCE_DATE = date(
    2026,
    8,
    3,
)


def _catalog_resources():
    catalog = load_query_plan_v2_catalog()

    metrics = frozenset(
        plan.metric
        for plan in catalog.query_plans
    )
    tables = frozenset(
        table
        for plan in catalog.query_plans
        for table in (
            plan.resource_contract.required_tables
        )
    )
    columns = frozenset(
        column
        for plan in catalog.query_plans
        for column in (
            plan.resource_contract.required_columns
        )
    )

    return (
        catalog,
        metrics,
        tables,
        columns,
    )


def _context(
    *,
    allowed_metrics: frozenset[str] | None = None,
    allowed_tables: frozenset[str] | None = None,
    allowed_columns: frozenset[str] | None = None,
    denied_columns: frozenset[str] = frozenset(),
    allowed_region_codes: frozenset[str] = frozenset(
        {
            "north",
            "south",
        }
    ),
    allowed_channel_codes: frozenset[str] = frozenset(
        {
            "tmall",
            "jd",
        }
    ),
    dataset_name: str = "beauty_bi_v2",
    target_schema: str = "beauty_bi_v2",
) -> AccessContext:
    (
        _,
        catalog_metrics,
        catalog_tables,
        catalog_columns,
    ) = _catalog_resources()

    effective_columns = (
        catalog_columns
        if allowed_columns is None
        else allowed_columns
    )

    effective_columns = (
        effective_columns
        - denied_columns
    )

    return AccessContext(
        request_id="governed-planning-envelope-v2",
        actor_id="acceptance-user",
        role=AccessRole.SCOPED_ANALYST,
        dataset_name=dataset_name,
        target_schema=target_schema,
        operation_mode=(
            OperationMode.OBSERVE_ADVISE
        ),
        allowed_metrics=(
            catalog_metrics
            if allowed_metrics is None
            else allowed_metrics
        ),
        allowed_tables=(
            catalog_tables
            if allowed_tables is None
            else allowed_tables
        ),
        allowed_columns=effective_columns,
        denied_columns=denied_columns,
        allowed_region_codes=allowed_region_codes,
        allowed_channel_codes=allowed_channel_codes,
        sensitive_data_policy=(
            SensitiveDataPolicy()
        ),
        policy_version="governed_planning_policy_v2_acceptance",
        scope_source="acceptance_fixture",
    )


def _plan(
    name: str,
):
    plan = get_query_plan_v2_by_name(
        name
    )

    if plan is None:
        raise AssertionError(
            f"Missing Query Plan: {name}"
        )

    return plan


def _resolution(
    question: str,
):
    return resolve_time_window_v2(
        question,
        reference_date=REFERENCE_DATE,
    )


def test_ready_envelope() -> None:
    plan = _plan(
        "gmv_overall_v2"
    )

    decision = (
        build_governed_planning_envelope_v2(
            context=_context(),
            plan=plan,
            time_resolution=_resolution(
                "GMV是多少？"
            ),
        )
    )

    assert decision.ready
    assert (
        decision.status
        == GovernedPlanningStatusV2
        .READY_FOR_COMPILATION
    )
    assert decision.envelope is not None

    envelope = decision.envelope

    assert (
        envelope.query_plan_fingerprint
        == query_plan_fingerprint_v2(
            plan
        )
    )
    assert (
        envelope.required_tables
        == plan.resource_contract.required_tables
    )
    assert (
        envelope.required_columns
        == plan.resource_contract.required_columns
    )
    assert envelope.notice_required
    assert envelope.user_notice == (
        "未检测到明确的时间范围。"
        "本次按默认策略查询最近3个月："
        "2026-05-04 至 2026-08-03。"
    )
    assert (
        envelope.result_protection_contract
        == plan.result_contract
    )


def test_metric_authorization_denied() -> None:
    plan = _plan(
        "gmv_overall_v2"
    )
    context = _context(
        allowed_metrics=frozenset(),
    )

    decision = (
        build_governed_planning_envelope_v2(
            context=context,
            plan=plan,
            time_resolution=_resolution(
                "GMV是多少？"
            ),
        )
    )

    assert not decision.ready
    assert (
        decision.status
        == GovernedPlanningStatusV2
        .METRIC_AUTHORIZATION_DENIED
    )
    assert (
        decision.blocked_stage
        == GovernedPlanningBlockedStageV2
        .METRIC_AUTHORIZATION
    )
    assert decision.metric_authorization is not None
    assert (
        decision.metric_authorization.reason_code
        == AuthorizationReason.METRIC_NOT_ALLOWED
    )
    assert decision.resource_authorization is None
    assert decision.time_binding_decision is None
    assert decision.scope_binding_decision is None
    assert decision.envelope is None


def test_table_authorization_denied() -> None:
    plan = _plan(
        "gmv_overall_v2"
    )
    denied_table = next(
        iter(
            plan.resource_contract.required_tables
        )
    )
    (
        _,
        _,
        all_tables,
        _,
    ) = _catalog_resources()

    context = _context(
        allowed_tables=(
            all_tables
            - {
                denied_table,
            }
        ),
    )

    decision = (
        build_governed_planning_envelope_v2(
            context=context,
            plan=plan,
            time_resolution=_resolution(
                "GMV是多少？"
            ),
        )
    )

    assert not decision.ready
    assert (
        decision.status
        == GovernedPlanningStatusV2
        .RESOURCE_AUTHORIZATION_DENIED
    )
    assert decision.resource_authorization is not None
    assert (
        decision.resource_authorization.reason_code
        == AuthorizationReason.TABLE_NOT_ALLOWED
    )
    assert denied_table in (
        decision.resource_authorization.denied_tables
    )
    assert decision.time_binding_decision is None
    assert decision.scope_binding_decision is None
    assert decision.envelope is None


def test_explicit_column_denial() -> None:
    plan = _plan(
        "gmv_overall_v2"
    )
    denied_column = next(
        iter(
            plan.resource_contract.required_columns
        )
    )

    decision = (
        build_governed_planning_envelope_v2(
            context=_context(
                denied_columns=frozenset(
                    {
                        denied_column,
                    }
                )
            ),
            plan=plan,
            time_resolution=_resolution(
                "GMV是多少？"
            ),
        )
    )

    assert not decision.ready
    assert (
        decision.status
        == GovernedPlanningStatusV2
        .RESOURCE_AUTHORIZATION_DENIED
    )
    assert decision.resource_authorization is not None
    assert (
        decision.resource_authorization.reason_code
        == AuthorizationReason
        .EXPLICITLY_DENIED_COLUMN
    )
    assert denied_column in (
        decision.resource_authorization
        .explicitly_denied_columns
    )
    assert decision.envelope is None


def test_ambiguous_time_stops_before_scope() -> None:
    plan = _plan(
        "gmv_overall_v2"
    )

    decision = (
        build_governed_planning_envelope_v2(
            context=_context(),
            plan=plan,
            time_resolution=_resolution(
                "本月和上月GMV"
            ),
        )
    )

    assert not decision.ready
    assert (
        decision.status
        == GovernedPlanningStatusV2
        .TIME_BINDING_NOT_READY
    )
    assert (
        decision.blocked_stage
        == GovernedPlanningBlockedStageV2
        .TIME_BINDING
    )
    assert decision.time_binding_decision is not None
    assert not decision.time_binding_decision.allowed
    assert decision.scope_binding_decision is None
    assert decision.envelope is None


def test_roi_scope_denied_after_authorization_and_time() -> None:
    plan = _plan(
        "roi_channel_v2"
    )

    decision = (
        build_governed_planning_envelope_v2(
            context=_context(),
            plan=plan,
            time_resolution=_resolution(
                "2026年7月各渠道ROI"
            ),
        )
    )

    assert not decision.ready
    assert (
        decision.status
        == GovernedPlanningStatusV2
        .SCOPE_BINDING_NOT_READY
    )
    assert decision.metric_authorization is not None
    assert decision.metric_authorization.allowed
    assert decision.resource_authorization is not None
    assert decision.resource_authorization.allowed
    assert decision.time_binding_decision is not None
    assert decision.time_binding_decision.allowed
    assert decision.scope_binding_decision is not None
    assert (
        decision.scope_binding_decision.status
        == QueryPlanScopeBindingStatusV2
        .ROW_SCOPE_DENIED
    )
    assert decision.envelope is None


def test_global_history_scope_denied() -> None:
    plan = _plan(
        "cac_channel_v2"
    )

    decision = (
        build_governed_planning_envelope_v2(
            context=_context(),
            plan=plan,
            time_resolution=_resolution(
                "最近三个月各渠道CAC"
            ),
        )
    )

    assert not decision.ready
    assert (
        decision.status
        == GovernedPlanningStatusV2
        .SCOPE_BINDING_NOT_READY
    )
    assert decision.scope_binding_decision is not None
    assert (
        decision.scope_binding_decision.status
        == QueryPlanScopeBindingStatusV2
        .POST_SEQUENCE_SCOPE_NOT_READY
    )
    assert decision.envelope is None


def test_column_authorization_denied() -> None:
    plan = _plan(
        "gmv_overall_v2"
    )

    denied_column = next(
        iter(
            plan.resource_contract.required_columns
        )
    )

    (
        _,
        _,
        _,
        all_columns,
    ) = _catalog_resources()

    context = _context(
        allowed_columns=(
            all_columns
            - {
                denied_column,
            }
        ),
    )

    decision = (
        build_governed_planning_envelope_v2(
            context=context,
            plan=plan,
            time_resolution=_resolution(
                "GMV是多少？"
            ),
        )
    )

    assert not decision.ready

    assert (
        decision.status
        == GovernedPlanningStatusV2
        .RESOURCE_AUTHORIZATION_DENIED
    )

    assert (
        decision.blocked_stage
        == GovernedPlanningBlockedStageV2
        .RESOURCE_AUTHORIZATION
    )

    assert decision.metric_authorization is not None
    assert decision.metric_authorization.allowed

    assert decision.resource_authorization is not None

    assert (
        decision.resource_authorization.reason_code
        == AuthorizationReason.COLUMN_NOT_ALLOWED
    )

    assert denied_column in (
        decision.resource_authorization.denied_columns
    )

    assert not (
        decision.resource_authorization
        .explicitly_denied_columns
    )

    assert decision.time_binding_decision is None
    assert decision.scope_binding_decision is None
    assert decision.envelope is None


def test_catalog_wide_governed_statuses() -> None:
    (
        catalog,
        _,
        _,
        _,
    ) = _catalog_resources()

    context = _context()
    resolution = _resolution(
        "查看指标表现"
    )

    counts: Counter[str] = Counter()
    unexpected: list[str] = []

    expected_special = {
        "roi_channel_v2": (
            GovernedPlanningStatusV2
            .SCOPE_BINDING_NOT_READY
        ),
        "cac_channel_v2": (
            GovernedPlanningStatusV2
            .SCOPE_BINDING_NOT_READY
        ),
        "brand_paid_new_customer_count_overall_v2": (
            GovernedPlanningStatusV2
            .SCOPE_BINDING_NOT_READY
        ),
        "channel_paid_new_customer_count_channel_v2": (
            GovernedPlanningStatusV2
            .SCOPE_BINDING_NOT_READY
        ),
    }

    for plan in catalog.query_plans:
        decision = (
            build_governed_planning_envelope_v2(
                context=context,
                plan=plan,
                time_resolution=resolution,
            )
        )

        counts[
            decision.status.value
        ] += 1

        expected = expected_special.get(
            plan.name,
            GovernedPlanningStatusV2
            .READY_FOR_COMPILATION,
        )

        if decision.status != expected:
            unexpected.append(
                f"{plan.name}: expected={expected.value}, "
                f"actual={decision.status.value}, "
                f"detail={decision.detail}"
            )

        if (
            decision.status
            == GovernedPlanningStatusV2
            .READY_FOR_COMPILATION
            and decision.envelope is None
        ):
            unexpected.append(
                f"{plan.name}: ready without envelope"
            )

        if (
            decision.status
            != GovernedPlanningStatusV2
            .READY_FOR_COMPILATION
            and decision.envelope is not None
        ):
            unexpected.append(
                f"{plan.name}: blocked with envelope"
            )

    assert not unexpected, "\n".join(
        unexpected
    )

    assert counts == Counter(
        {
            "ready_for_compilation": 45,
            "scope_binding_not_ready": 4,
        }
    )


TESTS = (
    test_ready_envelope,
    test_metric_authorization_denied,
    test_table_authorization_denied,
    test_explicit_column_denial,
    test_ambiguous_time_stops_before_scope,
    test_roi_scope_denied_after_authorization_and_time,
    test_global_history_scope_denied,
    test_column_authorization_denied,
    test_catalog_wide_governed_statuses,
)


def run_acceptance() -> None:
    passed = 0
    failed = 0

    print("=" * 80)
    print(
        "Governed Planning Envelope V2 Acceptance"
    )
    print(
        f"Cases: {len(TESTS)}"
    )

    for test in TESTS:
        print("=" * 80)
        print(
            test.__name__
        )

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
        "Governed Planning Envelope V2 "
        "Acceptance Summary"
    )
    print(
        f"Total: {len(TESTS)}"
    )
    print(
        f"Passed: {passed}"
    )
    print(
        f"Failed: {failed}"
    )

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    run_acceptance()
