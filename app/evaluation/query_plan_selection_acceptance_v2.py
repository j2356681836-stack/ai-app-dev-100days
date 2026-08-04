from __future__ import annotations

from dataclasses import dataclass

from app.semantic_layer.query_plan_selector_v2 import (
    QueryPlanSelectionStatusV2,
    resolve_and_select_query_plan_v2,
)


@dataclass(frozen=True)
class QueryPlanSelectionAcceptanceCaseV2:
    case_id: str
    question: str
    metric_name: str
    expected_status: QueryPlanSelectionStatusV2
    expected_grain_keys: tuple[str, ...] = ()
    expected_plan_names: tuple[str, ...] = ()
    expected_available_grains: frozenset[str] | None = None


CASES = (
    QueryPlanSelectionAcceptanceCaseV2(
        case_id="QPS-001",
        question="本月GMV是多少？",
        metric_name="gmv",
        expected_status=(
            QueryPlanSelectionStatusV2.MATCHED
        ),
        expected_grain_keys=(
            "overall",
        ),
        expected_plan_names=(
            "gmv_overall_v2",
        ),
    ),
    QueryPlanSelectionAcceptanceCaseV2(
        case_id="QPS-002",
        question="各渠道GMV是多少？",
        metric_name="gmv",
        expected_status=(
            QueryPlanSelectionStatusV2.MATCHED
        ),
        expected_grain_keys=(
            "channel",
        ),
        expected_plan_names=(
            "gmv_channel_v2",
        ),
    ),
    QueryPlanSelectionAcceptanceCaseV2(
        case_id="QPS-003",
        question="按不同地区看GMV",
        metric_name="gmv",
        expected_status=(
            QueryPlanSelectionStatusV2.MATCHED
        ),
        expected_grain_keys=(
            "region",
        ),
        expected_plan_names=(
            "gmv_region_v2",
        ),
    ),
    QueryPlanSelectionAcceptanceCaseV2(
        case_id="QPS-004",
        question="每个品类的GMV是多少？",
        metric_name="gmv",
        expected_status=(
            QueryPlanSelectionStatusV2.MATCHED
        ),
        expected_grain_keys=(
            "category",
        ),
        expected_plan_names=(
            "gmv_category_v2",
        ),
    ),
    QueryPlanSelectionAcceptanceCaseV2(
        case_id="QPS-005",
        question="按渠道和地区交叉看GMV",
        metric_name="gmv",
        expected_status=(
            QueryPlanSelectionStatusV2.MATCHED
        ),
        expected_grain_keys=(
            "channel_region",
        ),
        expected_plan_names=(
            "gmv_channel_region_v2",
        ),
    ),
    QueryPlanSelectionAcceptanceCaseV2(
        case_id="QPS-006",
        question="按渠道和地区看GMV",
        metric_name="gmv",
        expected_status=(
            QueryPlanSelectionStatusV2.MATCHED
        ),
        expected_grain_keys=(
            "channel_region",
        ),
        expected_plan_names=(
            "gmv_channel_region_v2",
        ),
    ),
    QueryPlanSelectionAcceptanceCaseV2(
        case_id="QPS-007",
        question="分别按渠道和地区看GMV",
        metric_name="gmv",
        expected_status=(
            QueryPlanSelectionStatusV2
            .MATCHED_MULTIPLE
        ),
        expected_grain_keys=(
            "channel",
            "region",
        ),
        expected_plan_names=(
            "gmv_channel_v2",
            "gmv_region_v2",
        ),
    ),
    QueryPlanSelectionAcceptanceCaseV2(
        case_id="QPS-008",
        question="各渠道和各地区的GMV",
        metric_name="gmv",
        expected_status=(
            QueryPlanSelectionStatusV2
            .AMBIGUOUS_GRAIN
        ),
    ),
    QueryPlanSelectionAcceptanceCaseV2(
        case_id="QPS-009",
        question="看看GMV表现",
        metric_name="gmv",
        expected_status=(
            QueryPlanSelectionStatusV2
            .MISSING_GRAIN
        ),
    ),
    QueryPlanSelectionAcceptanceCaseV2(
        case_id="QPS-010",
        question="按地区看ROI",
        metric_name="roi",
        expected_status=(
            QueryPlanSelectionStatusV2
            .UNSUPPORTED_GRAIN
        ),
        expected_grain_keys=(
            "region",
        ),
        expected_available_grains=frozenset(
            {
                "channel",
            }
        ),
    ),
    QueryPlanSelectionAcceptanceCaseV2(
        case_id="QPS-011",
        question="整体未知指标是多少？",
        metric_name="unknown_metric",
        expected_status=(
            QueryPlanSelectionStatusV2
            .METRIC_NOT_FOUND
        ),
        expected_grain_keys=(
            "overall",
        ),
    ),
)


def _evaluate_case(
    case: QueryPlanSelectionAcceptanceCaseV2,
) -> tuple[bool, str]:
    result = (
        resolve_and_select_query_plan_v2(
            question=case.question,
            metric_name=case.metric_name,
        )
    )

    problems: list[str] = []

    if result.status != case.expected_status:
        problems.append(
            "status expected="
            f"{case.expected_status.value} "
            f"actual={result.status.value}"
        )

    if (
        result.requested_grain_keys
        != case.expected_grain_keys
    ):
        problems.append(
            "grain_keys expected="
            f"{case.expected_grain_keys} "
            "actual="
            f"{result.requested_grain_keys}"
        )

    if result.plan_names != case.expected_plan_names:
        problems.append(
            "plan_names expected="
            f"{case.expected_plan_names} "
            f"actual={result.plan_names}"
        )

    if (
        case.expected_available_grains
        is not None
        and frozenset(
            result.available_grains
        )
        != case.expected_available_grains
    ):
        problems.append(
            "available_grains expected="
            f"{sorted(case.expected_available_grains)} "
            "actual="
            f"{sorted(result.available_grains)}"
        )

    if problems:
        return (
            False,
            "; ".join(problems),
        )

    return (
        True,
        "ok",
    )


def run_acceptance() -> None:
    passed = 0
    failed = 0

    print("=" * 80)
    print(
        "Query Plan Selection V2 "
        "Composite Grain Acceptance"
    )
    print(
        f"Cases: {len(CASES)}"
    )

    for case in CASES:
        print("=" * 80)
        print(
            f"{case.case_id}: "
            f"{case.question}"
        )

        try:
            ok, detail = _evaluate_case(
                case
            )
        except Exception as exc:
            ok = False
            detail = (
                "exception: "
                f"{type(exc).__name__}: {exc}"
            )

        if ok:
            passed += 1
            print("[PASS]")
        else:
            failed += 1
            print("[FAIL]")
            print(detail)

    print("=" * 80)
    print(
        "Query Plan Selection V2 "
        "Composite Grain Acceptance Summary"
    )
    print(
        f"Total: {len(CASES)}"
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
