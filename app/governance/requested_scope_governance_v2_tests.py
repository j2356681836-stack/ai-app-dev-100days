from app.governance.access_context import (
    AccessContext,
    AccessRole,
    OperationMode,
    SensitiveDataPolicy,
)
from app.governance.row_scope import (
    RowScopeReason,
    ScopeDimension,
    plan_row_scope,
)
from app.semantic_layer.requested_scope_resolution_v2 import (
    RequestedScopeDimensionV2,
    RequestedScopeResolutionStatusV2,
    RequestedScopeResolutionV2,
)


AUTHORIZED_REGIONS = frozenset(
    {
        "BEIJING",
        "SHANGHAI",
    }
)

AUTHORIZED_CHANNELS = frozenset(
    {
        "JD",
        "TMALL",
    }
)


def _context() -> AccessContext:
    return AccessContext(
        request_id="requested-scope-governance-v2",
        actor_id="scope-test-user",
        role=AccessRole.SCOPED_ANALYST,
        dataset_name="beauty_bi_v2",
        target_schema="beauty_bi_v2",
        operation_mode=OperationMode.OBSERVE_ADVISE,
        allowed_metrics=frozenset(
            {
                "gmv",
            }
        ),
        allowed_tables=frozenset(
            {
                "fact_orders",
                "dim_region",
                "dim_channel",
            }
        ),
        allowed_columns=frozenset(),
        denied_columns=frozenset(),
        allowed_region_codes=AUTHORIZED_REGIONS,
        allowed_channel_codes=AUTHORIZED_CHANNELS,
        sensitive_data_policy=SensitiveDataPolicy(),
        policy_version="requested_scope_test_policy_v1",
        scope_source="requested_scope_test",
    )


def _requested(
    *,
    regions: frozenset[str] = frozenset(),
    channels: frozenset[str] = frozenset(),
) -> RequestedScopeResolutionV2:
    return RequestedScopeResolutionV2(
        status=RequestedScopeResolutionStatusV2.RESOLVED,
        region_codes=regions,
        channel_codes=channels,
    )


def _codes_by_dimension(
    decision,
) -> dict[ScopeDimension, set[frozenset[str]]]:
    assert decision.plan is not None

    result: dict[
        ScopeDimension,
        set[frozenset[str]],
    ] = {}

    for requirement in decision.plan.requirements:
        result.setdefault(
            requirement.dimension,
            set(),
        ).add(
            requirement.allowed_codes
        )

    return result


def check(
    name: str,
    condition: bool,
) -> None:
    if not condition:
        raise AssertionError(
            f"FAILED: {name}"
        )

    print(
        f"PASS: {name}"
    )


def main() -> None:
    no_requested = plan_row_scope(
        context=_context(),
        source_tables=frozenset(
            {
                "fact_orders",
            }
        ),
    )

    no_requested_codes = _codes_by_dimension(
        no_requested
    )

    check(
        "无 Requested Scope 时保持全部 Authorized Scope",
        (
            no_requested.allowed
            and no_requested_codes[
                ScopeDimension.REGION
            ]
            == {
                AUTHORIZED_REGIONS,
            }
            and no_requested_codes[
                ScopeDimension.CHANNEL
            ]
            == {
                AUTHORIZED_CHANNELS,
            }
        ),
    )

    shanghai = plan_row_scope(
        context=_context(),
        source_tables=frozenset(
            {
                "fact_orders",
            }
        ),
        requested_scope=_requested(
            regions=frozenset(
                {
                    "SHANGHAI",
                }
            ),
        ),
    )

    shanghai_codes = _codes_by_dimension(
        shanghai
    )

    check(
        "Requested SHANGHAI 收窄 Region 且不改变 Channel",
        (
            shanghai.allowed
            and shanghai_codes[
                ScopeDimension.REGION
            ]
            == {
                frozenset(
                    {
                        "SHANGHAI",
                    }
                ),
            }
            and shanghai_codes[
                ScopeDimension.CHANNEL
            ]
            == {
                AUTHORIZED_CHANNELS,
            }
        ),
    )

    combined = plan_row_scope(
        context=_context(),
        source_tables=frozenset(
            {
                "fact_orders",
            }
        ),
        requested_scope=_requested(
            regions=frozenset(
                {
                    "SHANGHAI",
                }
            ),
            channels=frozenset(
                {
                    "TMALL",
                }
            ),
        ),
    )

    combined_codes = _codes_by_dimension(
        combined
    )

    check(
        "Region 与 Channel 同时按 Requested Scope 收窄",
        (
            combined.allowed
            and combined_codes[
                ScopeDimension.REGION
            ]
            == {
                frozenset(
                    {
                        "SHANGHAI",
                    }
                ),
            }
            and combined_codes[
                ScopeDimension.CHANNEL
            ]
            == {
                frozenset(
                    {
                        "TMALL",
                    }
                ),
            }
        ),
    )

    unauthorized = plan_row_scope(
        context=_context(),
        source_tables=frozenset(
            {
                "fact_orders",
            }
        ),
        requested_scope=_requested(
            regions=frozenset(
                {
                    "SHANGHAI",
                    "ZHEJIANG_HANGZHOU",
                }
            ),
        ),
    )

    check(
        "Requested Scope 含任一未授权值时整体拒绝",
        (
            not unauthorized.allowed
            and unauthorized.reason_code
            == RowScopeReason.REQUESTED_SCOPE_UNAUTHORIZED
            and unauthorized.plan is None
        ),
    )

    unsupported_dimension = plan_row_scope(
        context=_context(),
        source_tables=frozenset(
            {
                "fact_orders",
            }
        ),
        required_dimensions=frozenset(
            {
                ScopeDimension.CHANNEL,
            }
        ),
        requested_scope=_requested(
            regions=frozenset(
                {
                    "SHANGHAI",
                }
            ),
        ),
    )

    check(
        "Query Plan 无法应用显式 Requested Dimension 时拒绝",
        (
            not unsupported_dimension.allowed
            and unsupported_dimension.reason_code
            == (
                RowScopeReason
                .REQUESTED_SCOPE_DIMENSION_UNSUPPORTED
            )
            and unsupported_dimension.plan is None
        ),
    )

    unresolved = plan_row_scope(
        context=_context(),
        source_tables=frozenset(
            {
                "fact_orders",
            }
        ),
        requested_scope=RequestedScopeResolutionV2(
            status=(
                RequestedScopeResolutionStatusV2
                .UNRESOLVED_EXPLICIT_SCOPE
            ),
            unresolved_dimensions=frozenset(
                {
                    RequestedScopeDimensionV2.REGION,
                }
            ),
        ),
    )

    check(
        "Unresolved Explicit Scope 在 Governance 再次 fail closed",
        (
            not unresolved.allowed
            and unresolved.reason_code
            == RowScopeReason.REQUESTED_SCOPE_UNRESOLVED
            and unresolved.plan is None
        ),
    )

    print(
        "=" * 72
    )
    print(
        "Requested Scope Governance V2 tests passed."
    )


if __name__ == "__main__":
    main()
