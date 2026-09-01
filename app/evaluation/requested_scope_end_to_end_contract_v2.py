from datetime import date

from app.delivery.decision_console_runtime_v2 import (
    build_day89_local_access_context_v2,
)
from app.governance.governed_planning_envelope_v2 import (
    GovernedPlanningStatusV2,
    build_governed_planning_envelope_v2,
)
from app.governance.row_scope import ScopeDimension
from app.semantic_layer.analytics_planning_service_v2 import (
    AnalyticsPlanningStatusV2,
    resolve_analytics_planning_v2,
)
from app.semantic_layer.query_plan_v2_loader import (
    get_query_plan_v2_by_name,
)
from app.semantic_layer.requested_scope_resolution_v2 import (
    RequestedScopeResolutionStatusV2,
)
from app.semantic_layer.time_window_resolver_v2 import (
    resolve_time_window_v2,
)


QUESTION = "2025年上海地区GMV是多少？"
REFERENCE_DATE = date(2026, 8, 27)


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


def _scope_parameter_values(
    envelope,
    dimension: ScopeDimension,
) -> set[str]:
    contract = (
        envelope
        .scope_binding
        .scoped_query_contract
    )

    parameter_map = {
        item.name: item.value
        for item in contract.parameters
    }

    values: set[str] = set()

    for predicate in contract.predicates:
        if predicate.dimension != dimension:
            continue

        for name in predicate.parameter_names:
            values.add(
                parameter_map[name]
            )

    return values


def main() -> None:
    context = build_day89_local_access_context_v2(
        request_id="scope-e2e-contract-v2",
    )

    analytics = resolve_analytics_planning_v2(
        question=QUESTION,
        allowed_metric_names=context.allowed_metrics,
    )

    check(
        "Analytics Planning 形成单一 GMV Plan",
        (
            analytics.status
            == AnalyticsPlanningStatusV2.PLANNED_SINGLE
            and analytics.metric_name == "gmv"
            and len(analytics.plan_names) == 1
        ),
    )

    check(
        "Requested Scope 保留 SHANGHAI",
        (
            analytics.requested_scope_resolution.status
            == RequestedScopeResolutionStatusV2.RESOLVED
            and analytics.requested_scope_resolution.region_codes
            == frozenset(
                {
                    "SHANGHAI",
                }
            )
        ),
    )

    plan = get_query_plan_v2_by_name(
        analytics.plan_names[0]
    )

    check(
        "Query Plan 存在",
        plan is not None,
    )

    if plan is None:
        raise AssertionError(
            "Missing Query Plan."
        )

    time_resolution = resolve_time_window_v2(
        QUESTION,
        reference_date=REFERENCE_DATE,
    )

    governed = build_governed_planning_envelope_v2(
        context=context,
        plan=plan,
        time_resolution=time_resolution,
        requested_scope=(
            analytics.requested_scope_resolution
        ),
    )

    check(
        "Requested Scope 通过 Governed Planning",
        (
            governed.status
            == GovernedPlanningStatusV2
            .READY_FOR_COMPILATION
            and governed.ready
            and governed.envelope is not None
        ),
    )

    if governed.envelope is None:
        raise AssertionError(
            "Governed envelope is missing."
        )

    envelope = governed.envelope

    check(
        "Envelope 保存 Requested Scope",
        (
            envelope.requested_scope
            == analytics.requested_scope_resolution
        ),
    )

    region_values = _scope_parameter_values(
        envelope,
        ScopeDimension.REGION,
    )

    channel_values = _scope_parameter_values(
        envelope,
        ScopeDimension.CHANNEL,
    )

    check(
        "最终 Region SQL Scope 只包含 SHANGHAI",
        (
            region_values
            == {
                "SHANGHAI",
            }
        ),
    )

    check(
        "未请求具体 Channel 时继续使用 Authorized Channel Scope",
        (
            channel_values
            == set(
                context.allowed_channel_codes
            )
        ),
    )

    print(
        "=" * 72
    )
    print(
        "Requested Scope End-to-End Contract V2 passed."
    )


if __name__ == "__main__":
    main()
