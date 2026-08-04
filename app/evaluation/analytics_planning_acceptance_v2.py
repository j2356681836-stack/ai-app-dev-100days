from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.semantic_layer.analytics_planning_service_v2 import (
    AnalyticsPlanningStatusV2,
    resolve_analytics_planning_v2,
)
from app.semantic_layer.question_semantic_parser_v2 import (
    QuestionSemanticParseStatusV2,
)
from app.semantic_layer.semantic_decision_service_v2 import (
    SemanticDecisionResultV2,
    SemanticDecisionStatusV2,
)


@dataclass(frozen=True)
class AnalyticsPlanningAcceptanceCaseV2:
    case_id: str
    question: str
    semantic_result: SemanticDecisionResultV2
    expected_status: AnalyticsPlanningStatusV2
    expected_metric_name: str | None = None
    expected_plan_names: tuple[str, ...] = ()
    expect_grain_resolution: bool = False
    expect_plan_selection: bool = False


def _semantic(
    *,
    status: SemanticDecisionStatusV2,
    metric_name: str | None = None,
    candidates: tuple[str, ...] = (),
    parser_status: QuestionSemanticParseStatusV2 = (
        QuestionSemanticParseStatusV2.PARSED
    ),
    parser_error: str | None = None,
    parser_conflicts: tuple[str, ...] = (),
) -> SemanticDecisionResultV2:
    return SemanticDecisionResultV2(
        status=status,
        parser_status=parser_status,
        metric_name=metric_name,
        candidates=candidates,
        ranking_applied=False,
        ranking_method=None,
        parser_error=parser_error,
        parser_conflicts=parser_conflicts,
    )


CASES = (
    AnalyticsPlanningAcceptanceCaseV2(
        case_id="APV2-001",
        question="本月GMV是多少？",
        semantic_result=_semantic(
            status=SemanticDecisionStatusV2.MATCHED,
            metric_name="gmv",
            candidates=("gmv",),
        ),
        expected_status=(
            AnalyticsPlanningStatusV2.PLANNED_SINGLE
        ),
        expected_metric_name="gmv",
        expected_plan_names=("gmv_overall_v2",),
        expect_grain_resolution=True,
        expect_plan_selection=True,
    ),
    AnalyticsPlanningAcceptanceCaseV2(
        case_id="APV2-002",
        question="按渠道和地区交叉看GMV",
        semantic_result=_semantic(
            status=SemanticDecisionStatusV2.MATCHED,
            metric_name="gmv",
            candidates=("gmv",),
        ),
        expected_status=(
            AnalyticsPlanningStatusV2.PLANNED_SINGLE
        ),
        expected_metric_name="gmv",
        expected_plan_names=(
            "gmv_channel_region_v2",
        ),
        expect_grain_resolution=True,
        expect_plan_selection=True,
    ),
    AnalyticsPlanningAcceptanceCaseV2(
        case_id="APV2-003",
        question="分别按渠道和地区看GMV",
        semantic_result=_semantic(
            status=SemanticDecisionStatusV2.MATCHED,
            metric_name="gmv",
            candidates=("gmv",),
        ),
        expected_status=(
            AnalyticsPlanningStatusV2.PLANNED_MULTIPLE
        ),
        expected_metric_name="gmv",
        expected_plan_names=(
            "gmv_channel_v2",
            "gmv_region_v2",
        ),
        expect_grain_resolution=True,
        expect_plan_selection=True,
    ),
    AnalyticsPlanningAcceptanceCaseV2(
        case_id="APV2-004",
        question="各渠道和各地区的GMV",
        semantic_result=_semantic(
            status=SemanticDecisionStatusV2.MATCHED,
            metric_name="gmv",
            candidates=("gmv",),
        ),
        expected_status=(
            AnalyticsPlanningStatusV2.AMBIGUOUS_GRAIN
        ),
        expected_metric_name="gmv",
        expect_grain_resolution=True,
        expect_plan_selection=True,
    ),
    AnalyticsPlanningAcceptanceCaseV2(
        case_id="APV2-005",
        question="看看GMV表现",
        semantic_result=_semantic(
            status=SemanticDecisionStatusV2.MATCHED,
            metric_name="gmv",
            candidates=("gmv",),
        ),
        expected_status=(
            AnalyticsPlanningStatusV2.MISSING_GRAIN
        ),
        expected_metric_name="gmv",
        expect_grain_resolution=True,
        expect_plan_selection=True,
    ),
    AnalyticsPlanningAcceptanceCaseV2(
        case_id="APV2-006",
        question="按地区看ROI",
        semantic_result=_semantic(
            status=SemanticDecisionStatusV2.MATCHED,
            metric_name="roi",
            candidates=("roi",),
        ),
        expected_status=(
            AnalyticsPlanningStatusV2.UNSUPPORTED_GRAIN
        ),
        expected_metric_name="roi",
        expect_grain_resolution=True,
        expect_plan_selection=True,
    ),
    AnalyticsPlanningAcceptanceCaseV2(
        case_id="APV2-007",
        question="平均消费是多少？",
        semantic_result=_semantic(
            status=(
                SemanticDecisionStatusV2
                .NEEDS_CLARIFICATION
            ),
            candidates=(
                "spending_per_buyer",
                "aus",
            ),
        ),
        expected_status=(
            AnalyticsPlanningStatusV2
            .NEEDS_METRIC_CLARIFICATION
        ),
    ),
    AnalyticsPlanningAcceptanceCaseV2(
        case_id="APV2-008",
        question="每位买家平均购买件数",
        semantic_result=_semantic(
            status=SemanticDecisionStatusV2.UNSUPPORTED,
        ),
        expected_status=(
            AnalyticsPlanningStatusV2.UNSUPPORTED_METRIC
        ),
    ),
    AnalyticsPlanningAcceptanceCaseV2(
        case_id="APV2-009",
        question="分别看GMV和订单数",
        semantic_result=_semantic(
            status=SemanticDecisionStatusV2.MULTIPLE_INTENTS,
            parser_status=(
                QuestionSemanticParseStatusV2
                .MULTIPLE_INTENTS
            ),
            parser_error="separate_requests_marker",
        ),
        expected_status=(
            AnalyticsPlanningStatusV2.MULTIPLE_INTENTS
        ),
    ),
    AnalyticsPlanningAcceptanceCaseV2(
        case_id="APV2-010",
        question="无法解析的问题",
        semantic_result=_semantic(
            status=SemanticDecisionStatusV2.PARSE_FAILED,
            parser_status=(
                QuestionSemanticParseStatusV2
                .PARSE_FAILED
            ),
            parser_error="invalid_structured_response",
        ),
        expected_status=(
            AnalyticsPlanningStatusV2.PARSE_FAILED
        ),
    ),
    AnalyticsPlanningAcceptanceCaseV2(
        case_id="APV2-011",
        question="证据冲突的问题",
        semantic_result=_semantic(
            status=(
                SemanticDecisionStatusV2
                .EVIDENCE_CONFLICT
            ),
            parser_status=(
                QuestionSemanticParseStatusV2
                .EVIDENCE_CONFLICT
            ),
            parser_conflicts=(
                "operator_conflict",
            ),
        ),
        expected_status=(
            AnalyticsPlanningStatusV2.EVIDENCE_CONFLICT
        ),
    ),
)


def _fake_semantic_resolver(
    result: SemanticDecisionResultV2,
):
    call_count = 0

    def resolver(**_: Any) -> SemanticDecisionResultV2:
        nonlocal call_count
        call_count += 1

        if call_count > 1:
            raise AssertionError(
                "Semantic resolver was called more than once."
            )

        return result

    def get_call_count() -> int:
        return call_count

    return (
        resolver,
        get_call_count,
    )


def _evaluate_case(
    case: AnalyticsPlanningAcceptanceCaseV2,
) -> tuple[bool, str]:
    fake_resolver, get_call_count = (
        _fake_semantic_resolver(
            case.semantic_result
        )
    )

    result = resolve_analytics_planning_v2(
        question=case.question,
        semantic_resolver=fake_resolver,
    )

    problems: list[str] = []

    if result.status != case.expected_status:
        problems.append(
            "status expected="
            f"{case.expected_status.value} "
            f"actual={result.status.value}"
        )

    if result.metric_name != case.expected_metric_name:
        problems.append(
            "metric_name expected="
            f"{case.expected_metric_name} "
            f"actual={result.metric_name}"
        )

    if result.plan_names != case.expected_plan_names:
        problems.append(
            "plan_names expected="
            f"{case.expected_plan_names} "
            f"actual={result.plan_names}"
        )

    if (
        (result.grain_resolution is not None)
        != case.expect_grain_resolution
    ):
        problems.append(
            "grain_resolution presence expected="
            f"{case.expect_grain_resolution}"
        )

    if (
        (result.plan_selection is not None)
        != case.expect_plan_selection
    ):
        problems.append(
            "plan_selection presence expected="
            f"{case.expect_plan_selection}"
        )

    if get_call_count() != 1:
        problems.append(
            "semantic resolver call_count expected=1 "
            f"actual={get_call_count()}"
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
        "Analytics Planning Service V2 Acceptance"
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
        "Analytics Planning Service V2 "
        "Acceptance Summary"
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
