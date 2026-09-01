from __future__ import annotations

from app.delivery.decision_console_runtime_v2 import (
    build_day89_local_access_context_v2,
)
from app.governance.access_context import (
    AccessContext,
    AccessRole,
    OperationMode,
    SensitiveDataPolicy,
)
from app.governance.sensitive_data import (
    ProtectionReason,
    ResultFieldBinding,
    ResultProtectionContract,
    ResultShape,
    SensitiveDataCategory,
    build_protection_fingerprint,
    protect_result_rows,
)
from app.semantic_layer.r12_cohort_query_plan_v2 import (
    build_r12_cohort_metric_family_v2,
)


def _context(
    *,
    allow_aggregate: bool = False,
    allow_cost: bool = False,
    minimum_group_size: int = 5,
) -> AccessContext:
    return AccessContext(
        request_id="day93-b5b2b-protection",
        actor_id="day93-test-user",
        role=AccessRole.SCOPED_ANALYST,
        dataset_name="beauty_bi_v2",
        target_schema="beauty_bi_v2",
        operation_mode=OperationMode.OBSERVE_ADVISE,
        allowed_metrics=frozenset({"r12_repurchase_amount"}),
        allowed_tables=frozenset({"fact_refunds"}),
        allowed_columns=frozenset({"fact_refunds.refund_amount"}),
        denied_columns=frozenset(),
        allowed_region_codes=frozenset({"SHANGHAI"}),
        allowed_channel_codes=frozenset({"TMALL"}),
        sensitive_data_policy=SensitiveDataPolicy(
            allow_cost_data=allow_cost,
            allow_aggregated_business_metrics=allow_aggregate,
            minimum_group_size=minimum_group_size,
        ),
        policy_version="day93_b5b2b_test_policy_v1",
        scope_source="server_test_fixture",
    )


def _aggregate_contract(
    *,
    result_shape: ResultShape = ResultShape.AGGREGATE,
    minimum_group_size_required: bool = True,
) -> ResultProtectionContract:
    return ResultProtectionContract(
        field_bindings=(
            ResultFieldBinding(
                output_field="r12_repurchase_amount",
                source_columns=frozenset({
                    "fact_refunds.refund_amount",
                }),
                category=(
                    SensitiveDataCategory
                    .AGGREGATED_BUSINESS_CONFIDENTIAL
                ),
            ),
        ),
        result_shape=result_shape,
        minimum_group_size_required=minimum_group_size_required,
        group_size_field=(
            "__group_size"
            if minimum_group_size_required
            else None
        ),
    )


def _raw_confidential_contract() -> ResultProtectionContract:
    return ResultProtectionContract(
        field_bindings=(
            ResultFieldBinding(
                output_field="refund_amount",
                source_columns=frozenset({
                    "fact_refunds.refund_amount",
                }),
                category=SensitiveDataCategory.BUSINESS_CONFIDENTIAL,
            ),
        ),
        result_shape=ResultShape.AGGREGATE,
    )


def test_aggregate_permission_defaults_fail_closed() -> None:
    result = protect_result_rows(
        context=_context(),
        rows=(
            {
                "r12_repurchase_amount": 1000,
                "__group_size": 100,
            },
        ),
        contract=_aggregate_contract(),
    )

    assert not result.success
    assert (
        result.reason_code
        == ProtectionReason.AGGREGATED_BUSINESS_METRIC_NOT_ALLOWED
    )


def test_detail_shape_cannot_use_aggregate_confidential_category() -> None:
    result = protect_result_rows(
        context=_context(allow_aggregate=True),
        rows=(
            {
                "r12_repurchase_amount": 1000,
                "__group_size": 100,
            },
        ),
        contract=_aggregate_contract(
            result_shape=ResultShape.DETAIL,
        ),
    )

    assert not result.success
    assert (
        result.reason_code
        == ProtectionReason
        .AGGREGATED_BUSINESS_AGGREGATION_NOT_PROVEN
    )


def test_missing_group_proof_is_rejected() -> None:
    result = protect_result_rows(
        context=_context(allow_aggregate=True),
        rows=(
            {
                "r12_repurchase_amount": 1000,
            },
        ),
        contract=_aggregate_contract(
            minimum_group_size_required=False,
        ),
    )

    assert not result.success
    assert (
        result.reason_code
        == ProtectionReason
        .AGGREGATED_BUSINESS_AGGREGATION_NOT_PROVEN
    )


def test_group_below_threshold_is_rejected() -> None:
    result = protect_result_rows(
        context=_context(allow_aggregate=True),
        rows=(
            {
                "r12_repurchase_amount": 1000,
                "__group_size": 4,
            },
        ),
        contract=_aggregate_contract(),
    )

    assert not result.success
    assert (
        result.reason_code
        == ProtectionReason.MINIMUM_GROUP_SIZE_VIOLATION
    )
    assert result.minimum_observed_group_size == 4


def test_group_at_threshold_is_allowed_and_control_field_hidden() -> None:
    result = protect_result_rows(
        context=_context(allow_aggregate=True),
        rows=(
            {
                "r12_repurchase_amount": 1000,
                "__group_size": 5,
            },
        ),
        contract=_aggregate_contract(),
    )

    assert result.success
    assert result.minimum_group_size_checked
    assert result.minimum_observed_group_size == 5
    assert result.rows == (
        {
            "r12_repurchase_amount": 1000,
        },
    )


def test_raw_business_confidential_remains_blocked() -> None:
    result = protect_result_rows(
        context=_context(
            allow_aggregate=True,
            allow_cost=False,
        ),
        rows=(
            {
                "refund_amount": 1000,
            },
        ),
        contract=_raw_confidential_contract(),
    )

    assert not result.success
    assert result.reason_code == ProtectionReason.COST_DATA_NOT_ALLOWED


def test_allow_cost_data_behavior_is_unchanged() -> None:
    result = protect_result_rows(
        context=_context(
            allow_aggregate=False,
            allow_cost=True,
        ),
        rows=(
            {
                "refund_amount": 1000,
            },
        ),
        contract=_raw_confidential_contract(),
    )

    assert result.success


def test_protection_fingerprint_includes_aggregate_permission() -> None:
    contract = _aggregate_contract()

    denied = build_protection_fingerprint(
        context=_context(allow_aggregate=False),
        contract=contract,
    )
    allowed = build_protection_fingerprint(
        context=_context(allow_aggregate=True),
        contract=contract,
    )

    assert denied != allowed


def test_decision_console_context_requires_explicit_opt_in() -> None:
    default_context = build_day89_local_access_context_v2(
        request_id="default-context",
    )
    r12_context = build_day89_local_access_context_v2(
        request_id="r12-context",
        allow_aggregated_business_metrics=True,
    )

    assert not (
        default_context.sensitive_data_policy
        .allow_aggregated_business_metrics
    )
    assert (
        r12_context.sensitive_data_policy
        .allow_aggregated_business_metrics
    )


def test_r12_amount_uses_contributor_group_size() -> None:
    plans = {
        plan.metric: plan
        for plan in build_r12_cohort_metric_family_v2()
    }

    for metric_name in (
        "r12_repurchase_amount",
        "r12_repurchase_spending",
    ):
        plan = plans[metric_name]

        binding = plan.result_contract.field_bindings[0]
        assert (
            binding.category
            == SensitiveDataCategory
            .AGGREGATED_BUSINESS_CONFIDENTIAL
        )

        final_stage = {
            stage.stage_id: stage
            for stage in plan.query_logic.stages
        }["final"]

        group_control = final_stage.hidden_control_fields[0]

        assert (
            group_control.expression
            == "COUNT(DISTINCT rc.customer_id)"
        )
        assert (
            group_control.semantics
            == "r12_repurchase_customer_count"
        )


TESTS = (
    test_aggregate_permission_defaults_fail_closed,
    test_detail_shape_cannot_use_aggregate_confidential_category,
    test_missing_group_proof_is_rejected,
    test_group_below_threshold_is_rejected,
    test_group_at_threshold_is_allowed_and_control_field_hidden,
    test_raw_business_confidential_remains_blocked,
    test_allow_cost_data_behavior_is_unchanged,
    test_protection_fingerprint_includes_aggregate_permission,
    test_decision_console_context_requires_explicit_opt_in,
    test_r12_amount_uses_contributor_group_size,
)


def run_acceptance() -> None:
    passed = 0
    failed = 0

    print("=" * 88)
    print("Day93 B5B-2B Aggregate Confidential Result Protection Acceptance")
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

    print("=" * 88)
    print("Summary")
    print(f"Total: {len(TESTS)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    run_acceptance()
