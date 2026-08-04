from __future__ import annotations

from collections import Counter

from app.governance.access_context import (
    AccessContext,
    AccessRole,
    OperationMode,
    SensitiveDataPolicy,
)
from app.governance.query_plan_scope_binding_v2 import (
    QueryPlanScopeBindingStatusV2,
    bind_query_plan_scope_v2,
)
from app.governance.row_scope import (
    RowScopeReason,
    ScopeDimension,
)
from app.semantic_layer.query_plan_v2_loader import (
    get_query_plan_v2_by_name,
    load_query_plan_v2_catalog,
)


def _context(
    *,
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
) -> AccessContext:
    return AccessContext(
        request_id="query-plan-scope-binding-v2",
        actor_id="acceptance-user",
        role=AccessRole.SCOPED_ANALYST,
        dataset_name="beauty_bi_v2",
        target_schema="beauty_bi_v2",
        operation_mode=(
            OperationMode.OBSERVE_ADVISE
        ),
        allowed_metrics=frozenset(),
        allowed_tables=frozenset(),
        allowed_columns=frozenset(),
        denied_columns=frozenset(),
        allowed_region_codes=allowed_region_codes,
        allowed_channel_codes=allowed_channel_codes,
        sensitive_data_policy=(
            SensitiveDataPolicy()
        ),
        policy_version="scope_policy_v2_acceptance",
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


def test_simple_query_scope_is_bound() -> None:
    decision = bind_query_plan_scope_v2(
        context=_context(),
        plan=_plan(
            "gmv_overall_v2"
        ),
    )

    assert decision.allowed
    assert (
        decision.status
        == QueryPlanScopeBindingStatusV2.BOUND
    )
    assert decision.contract is not None

    placements = decision.contract.placements

    assert len(
        placements
    ) == 2

    assert {
        placement.dimension
        for placement in placements
    } == {
        ScopeDimension.CHANNEL,
        ScopeDimension.REGION,
    }

    assert {
        placement.stage_id
        for placement in placements
    } == {
        None,
    }

    assert {
        placement.anchor_reference
        for placement in placements
    } == {
        "fo.channel_id",
        "fo.shipping_region_id",
    }


def test_staged_query_scope_records_stage() -> None:
    decision = bind_query_plan_scope_v2(
        context=_context(),
        plan=_plan(
            "refund_rate_overall_v2"
        ),
    )

    assert decision.allowed
    assert decision.contract is not None

    assert {
        placement.stage_id
        for placement
        in decision.contract.placements
    } == {
        "item_refund_summary",
    }


def test_composite_grain_scope_is_bound() -> None:
    decision = bind_query_plan_scope_v2(
        context=_context(),
        plan=_plan(
            "gmv_channel_region_v2"
        ),
    )

    assert decision.allowed
    assert decision.contract is not None

    assert {
        placement.anchor_reference
        for placement
        in decision.contract.placements
    } == {
        "fo.channel_id",
        "fo.shipping_region_id",
    }


def test_roi_region_path_fails_closed() -> None:
    decision = bind_query_plan_scope_v2(
        context=_context(),
        plan=_plan(
            "roi_channel_v2"
        ),
    )

    assert not decision.allowed
    assert (
        decision.status
        == QueryPlanScopeBindingStatusV2
        .ROW_SCOPE_DENIED
    )
    assert decision.row_scope_decision is not None
    assert (
        decision.row_scope_decision.reason_code
        == RowScopeReason.UNSUPPORTED_SCOPE_PATH
    )
    assert (
        "region:fact_marketing_spend"
        in decision.row_scope_decision
        .unsupported_scope_paths
    )


def test_channel_first_event_scope_fails_closed() -> None:
    decision = bind_query_plan_scope_v2(
        context=_context(),
        plan=_plan(
            "channel_paid_new_customer_count_channel_v2"
        ),
    )

    assert not decision.allowed
    assert (
        decision.status
        == QueryPlanScopeBindingStatusV2
        .POST_SEQUENCE_SCOPE_NOT_READY
    )
    assert decision.pre_sequence_dimensions == frozenset(
        {
            ScopeDimension.CHANNEL,
        }
    )
    assert decision.post_sequence_dimensions == frozenset(
        {
            ScopeDimension.REGION,
        }
    )


def test_brand_first_event_scope_fails_closed() -> None:
    decision = bind_query_plan_scope_v2(
        context=_context(),
        plan=_plan(
            "brand_paid_new_customer_count_overall_v2"
        ),
    )

    assert not decision.allowed
    assert (
        decision.status
        == QueryPlanScopeBindingStatusV2
        .POST_SEQUENCE_SCOPE_NOT_READY
    )
    assert not decision.pre_sequence_dimensions
    assert decision.post_sequence_dimensions == frozenset(
        {
            ScopeDimension.CHANNEL,
            ScopeDimension.REGION,
        }
    )


def test_empty_scope_is_denied() -> None:
    decision = bind_query_plan_scope_v2(
        context=_context(
            allowed_region_codes=frozenset(),
        ),
        plan=_plan(
            "gmv_overall_v2"
        ),
    )

    assert not decision.allowed
    assert (
        decision.status
        == QueryPlanScopeBindingStatusV2
        .ROW_SCOPE_DENIED
    )
    assert decision.row_scope_decision is not None
    assert (
        decision.row_scope_decision.reason_code
        == RowScopeReason.EMPTY_SCOPE
    )


def test_catalog_wide_statuses() -> None:
    catalog = load_query_plan_v2_catalog()
    counts: Counter[str] = Counter()
    unexpected: list[str] = []

    expected_special = {
        "roi_channel_v2": (
            QueryPlanScopeBindingStatusV2
            .ROW_SCOPE_DENIED
        ),
        "cac_channel_v2": (
            QueryPlanScopeBindingStatusV2
            .POST_SEQUENCE_SCOPE_NOT_READY
        ),
        "brand_paid_new_customer_count_overall_v2": (
            QueryPlanScopeBindingStatusV2
            .POST_SEQUENCE_SCOPE_NOT_READY
        ),
        "channel_paid_new_customer_count_channel_v2": (
            QueryPlanScopeBindingStatusV2
            .POST_SEQUENCE_SCOPE_NOT_READY
        ),
    }

    for plan in catalog.query_plans:
        decision = bind_query_plan_scope_v2(
            context=_context(),
            plan=plan,
        )

        counts[
            decision.status.value
        ] += 1

        expected = expected_special.get(
            plan.name,
            QueryPlanScopeBindingStatusV2.BOUND,
        )

        if decision.status != expected:
            unexpected.append(
                f"{plan.name}: expected={expected.value}, "
                f"actual={decision.status.value}, "
                f"detail={decision.detail}"
            )

    assert not unexpected, "\n".join(
        unexpected
    )

    assert counts == Counter(
        {
            "bound": 45,
            "row_scope_denied": 1,
            "post_sequence_scope_not_ready": 3,
        }
    )


TESTS = (
    test_simple_query_scope_is_bound,
    test_staged_query_scope_records_stage,
    test_composite_grain_scope_is_bound,
    test_roi_region_path_fails_closed,
    test_channel_first_event_scope_fails_closed,
    test_brand_first_event_scope_fails_closed,
    test_empty_scope_is_denied,
    test_catalog_wide_statuses,
)


def run_acceptance() -> None:
    passed = 0
    failed = 0

    print("=" * 80)
    print(
        "Query Plan Scope Binding V2 Acceptance"
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
        "Query Plan Scope Binding V2 "
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
