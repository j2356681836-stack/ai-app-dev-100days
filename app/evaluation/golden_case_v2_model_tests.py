from pydantic import ValidationError

from app.evaluation.golden_case_v2_models import (
    ExpectedGovernanceDecision,
    ExpectedIntentDecision,
    ExpectedMetricDecision,
    ExpectedPlanDecision,
    GoldenCaseCatalogV2,
    GoldenCaseCategory,
    GoldenCaseSplit,
    GoldenCaseV2,
    GovernanceOutcome,
    MetricDecisionStatus,
    PlanDecisionStatus,
    RankingType,
    ResultGrain,
    ScopeDimension,
    SortDirection,
)


def assert_equal(
    actual,
    expected,
    message: str,
) -> None:
    if actual != expected:
        raise AssertionError(
            f"{message}\nExpected: {expected}\nActual: {actual}"
        )


def assert_true(
    condition: bool,
    message: str,
) -> None:
    if not condition:
        raise AssertionError(message)


def expect_validation_error(
    factory,
    message: str,
) -> None:
    try:
        factory()
    except ValidationError:
        return

    raise AssertionError(message)


def build_allowed_case() -> GoldenCaseV2:
    return GoldenCaseV2(
        case_id="dev_roi_channel_001",
        split=GoldenCaseSplit.DEVELOPMENT,
        category=GoldenCaseCategory.CANONICAL,
        question="各渠道 ROI 排名",
        description="明确 ROI + Channel Grain。",
        expected_metric=ExpectedMetricDecision(
            status=MetricDecisionStatus.MATCHED,
            metric_name="roi",
        ),
        expected_intent=ExpectedIntentDecision(
            result_grain=ResultGrain.CHANNEL,
            ranking_type=RankingType.RANKING,
            sort_direction=SortDirection.DESC,
        ),
        expected_plan=ExpectedPlanDecision(
            status=PlanDecisionStatus.SELECTED,
            plan_name="roi_channel_v2",
        ),
        expected_governance=ExpectedGovernanceDecision(
            outcome=GovernanceOutcome.ALLOWED,
        ),
    )


def test_valid_allowed_case() -> None:
    case = build_allowed_case()

    assert_equal(
        case.expected_metric.metric_name,
        "roi",
        "Allowed Case 应保留匹配指标。",
    )

    assert_equal(
        case.expected_plan.plan_name,
        "roi_channel_v2",
        "Allowed Case 应保留 Query Plan。",
    )


def test_valid_clarification_case() -> None:
    case = GoldenCaseV2(
        case_id="dev_new_customer_ambiguity_001",
        split=GoldenCaseSplit.DEVELOPMENT,
        category=GoldenCaseCategory.AMBIGUITY,
        question="今年新客多少？",
        expected_metric=ExpectedMetricDecision(
            status=MetricDecisionStatus.NEEDS_CLARIFICATION,
            acceptable_candidates=(
                "brand_paid_new_customer_count",
                "channel_paid_new_customer_count",
            ),
        ),
        expected_intent=ExpectedIntentDecision(
            result_grain=None,
        ),
        expected_plan=ExpectedPlanDecision(
            status=PlanDecisionStatus.NOT_APPLICABLE,
        ),
        expected_governance=ExpectedGovernanceDecision(
            outcome=GovernanceOutcome.NOT_EVALUATED,
        ),
    )

    assert_equal(
        case.expected_metric.status,
        MetricDecisionStatus.NEEDS_CLARIFICATION,
        "歧义问题必须能成为合法 Golden Case。",
    )


def test_valid_governance_denial_case() -> None:
    case = GoldenCaseV2(
        case_id="adv_roi_region_scope_001",
        split=GoldenCaseSplit.ADVERSARIAL,
        category=GoldenCaseCategory.GOVERNANCE,
        question="华东各渠道 ROI 排名",
        expected_metric=ExpectedMetricDecision(
            status=MetricDecisionStatus.MATCHED,
            metric_name="roi",
        ),
        expected_intent=ExpectedIntentDecision(
            result_grain=ResultGrain.CHANNEL,
            scope_dimensions=frozenset(
                {ScopeDimension.REGION}
            ),
            ranking_type=RankingType.RANKING,
            sort_direction=SortDirection.DESC,
        ),
        expected_plan=ExpectedPlanDecision(
            status=PlanDecisionStatus.SELECTED,
            plan_name="roi_channel_v2",
        ),
        expected_governance=ExpectedGovernanceDecision(
            outcome=GovernanceOutcome.DENIED,
            reason_code="unsupported_scope_path",
        ),
    )

    assert_equal(
        case.expected_governance.outcome,
        GovernanceOutcome.DENIED,
        "正确 fail-closed 必须能表示为 PASS 目标。",
    )


def test_valid_unsupported_shape_case() -> None:
    case = GoldenCaseV2(
        case_id="adv_roi_region_grain_001",
        split=GoldenCaseSplit.ADVERSARIAL,
        category=GoldenCaseCategory.UNSUPPORTED_SEMANTICS,
        question="各地区 ROI 排名",
        expected_metric=ExpectedMetricDecision(
            status=MetricDecisionStatus.MATCHED,
            metric_name="roi",
        ),
        expected_intent=ExpectedIntentDecision(
            result_grain=ResultGrain.REGION,
            ranking_type=RankingType.RANKING,
            sort_direction=SortDirection.DESC,
        ),
        expected_plan=ExpectedPlanDecision(
            status=PlanDecisionStatus.UNSUPPORTED_SHAPE,
        ),
        expected_governance=ExpectedGovernanceDecision(
            outcome=GovernanceOutcome.NOT_EVALUATED,
        ),
    )

    assert_equal(
        case.expected_plan.status,
        PlanDecisionStatus.UNSUPPORTED_SHAPE,
        "Metric matched 但 Grain 不支持时必须能单独表达。",
    )


def test_valid_overall_with_region_scope() -> None:
    case = GoldenCaseV2(
        case_id="dev_gmv_region_filter_001",
        split=GoldenCaseSplit.DEVELOPMENT,
        category=GoldenCaseCategory.GRAIN_SELECTION,
        question="华东 GMV 是多少？",
        expected_metric=ExpectedMetricDecision(
            status=MetricDecisionStatus.MATCHED,
            metric_name="gmv",
        ),
        expected_intent=ExpectedIntentDecision(
            result_grain=ResultGrain.OVERALL,
            scope_dimensions=frozenset(
                {ScopeDimension.REGION}
            ),
            ranking_type=RankingType.UNKNOWN,
        ),
        expected_plan=ExpectedPlanDecision(
            status=PlanDecisionStatus.SELECTED,
            plan_name="gmv_overall_v2",
        ),
        expected_governance=ExpectedGovernanceDecision(
            outcome=GovernanceOutcome.ALLOWED,
        ),
    )

    assert_equal(
        case.expected_intent.result_grain,
        ResultGrain.OVERALL,
        "Region Filter 不应被误写成 Region Result Grain。",
    )

    assert_true(
        ScopeDimension.REGION
        in case.expected_intent.scope_dimensions,
        "Region Filter 应独立记录在 scope_dimensions。",
    )


def test_matched_metric_requires_metric_name() -> None:
    expect_validation_error(
        lambda: ExpectedMetricDecision(
            status=MetricDecisionStatus.MATCHED,
        ),
        "matched 必须要求 metric_name。",
    )


def test_matched_metric_rejects_candidate_list() -> None:
    expect_validation_error(
        lambda: ExpectedMetricDecision(
            status=MetricDecisionStatus.MATCHED,
            metric_name="roi",
            acceptable_candidates=(
                "roi",
                "cac",
            ),
        ),
        "matched 不应同时保留 ambiguity candidate list。",
    )


def test_clarification_requires_two_candidates() -> None:
    expect_validation_error(
        lambda: ExpectedMetricDecision(
            status=MetricDecisionStatus.NEEDS_CLARIFICATION,
            acceptable_candidates=("roi",),
        ),
        "Clarification 至少应存在两个候选。",
    )


def test_clarification_rejects_duplicate_candidates() -> None:
    expect_validation_error(
        lambda: ExpectedMetricDecision(
            status=MetricDecisionStatus.NEEDS_CLARIFICATION,
            acceptable_candidates=(
                "roi",
                "roi",
            ),
        ),
        "Clarification candidates 必须唯一。",
    )


def test_unsupported_metric_rejects_preselected_metric() -> None:
    expect_validation_error(
        lambda: ExpectedMetricDecision(
            status=MetricDecisionStatus.UNSUPPORTED,
            metric_name="roi",
        ),
        "unsupported Metric 不能预先选择 metric_name。",
    )


def test_selected_plan_requires_plan_name() -> None:
    expect_validation_error(
        lambda: ExpectedPlanDecision(
            status=PlanDecisionStatus.SELECTED,
        ),
        "selected Plan 必须要求 plan_name。",
    )


def test_denied_governance_requires_reason_code() -> None:
    expect_validation_error(
        lambda: ExpectedGovernanceDecision(
            outcome=GovernanceOutcome.DENIED,
        ),
        "denied Governance 必须要求 reason_code。",
    )


def test_allowed_governance_rejects_reason_code() -> None:
    expect_validation_error(
        lambda: ExpectedGovernanceDecision(
            outcome=GovernanceOutcome.ALLOWED,
            reason_code="unexpected",
        ),
        "allowed Governance 不应携带 denial reason_code。",
    )


def test_top1_requires_limit_one() -> None:
    expect_validation_error(
        lambda: ExpectedIntentDecision(
            result_grain=ResultGrain.CHANNEL,
            limit=3,
            ranking_type=RankingType.TOP1,
        ),
        "top1 必须要求 limit=1。",
    )


def test_topn_requires_limit_greater_than_one() -> None:
    expect_validation_error(
        lambda: ExpectedIntentDecision(
            result_grain=ResultGrain.CHANNEL,
            limit=1,
            ranking_type=RankingType.TOPN,
        ),
        "topn 必须要求 limit>1。",
    )


def test_ranking_rejects_limit() -> None:
    expect_validation_error(
        lambda: ExpectedIntentDecision(
            result_grain=ResultGrain.CHANNEL,
            limit=5,
            ranking_type=RankingType.RANKING,
        ),
        "完整 ranking 不应同时声明 LIMIT。",
    )


def test_clarification_cannot_select_plan() -> None:
    expect_validation_error(
        lambda: GoldenCaseV2(
            case_id="invalid_clarification_plan",
            split=GoldenCaseSplit.DEVELOPMENT,
            category=GoldenCaseCategory.AMBIGUITY,
            question="今年新客多少？",
            expected_metric=ExpectedMetricDecision(
                status=MetricDecisionStatus.NEEDS_CLARIFICATION,
                acceptable_candidates=(
                    "brand_paid_new_customer_count",
                    "channel_paid_new_customer_count",
                ),
            ),
            expected_intent=ExpectedIntentDecision(),
            expected_plan=ExpectedPlanDecision(
                status=PlanDecisionStatus.SELECTED,
                plan_name="brand_paid_new_customer_count_overall_v2",
            ),
            expected_governance=ExpectedGovernanceDecision(
                outcome=GovernanceOutcome.NOT_EVALUATED,
            ),
        ),
        "Clarification Case 不得提前选择 Query Plan。",
    )


def test_unsupported_shape_cannot_claim_governance_denial() -> None:
    expect_validation_error(
        lambda: GoldenCaseV2(
            case_id="invalid_shape_governance",
            split=GoldenCaseSplit.ADVERSARIAL,
            category=GoldenCaseCategory.UNSUPPORTED_SEMANTICS,
            question="各地区 ROI 排名",
            expected_metric=ExpectedMetricDecision(
                status=MetricDecisionStatus.MATCHED,
                metric_name="roi",
            ),
            expected_intent=ExpectedIntentDecision(
                result_grain=ResultGrain.REGION,
                ranking_type=RankingType.RANKING,
            ),
            expected_plan=ExpectedPlanDecision(
                status=PlanDecisionStatus.UNSUPPORTED_SHAPE,
            ),
            expected_governance=ExpectedGovernanceDecision(
                outcome=GovernanceOutcome.DENIED,
                reason_code="unsupported_scope_path",
            ),
        ),
        "Unsupported Shape 应在 Governance 前停止。",
    )


def test_selected_plan_requires_result_grain() -> None:
    expect_validation_error(
        lambda: GoldenCaseV2(
            case_id="invalid_selected_plan_without_grain",
            split=GoldenCaseSplit.DEVELOPMENT,
            category=GoldenCaseCategory.CANONICAL,
            question="GMV 是多少？",
            expected_metric=ExpectedMetricDecision(
                status=MetricDecisionStatus.MATCHED,
                metric_name="gmv",
            ),
            expected_intent=ExpectedIntentDecision(
                result_grain=None,
            ),
            expected_plan=ExpectedPlanDecision(
                status=PlanDecisionStatus.SELECTED,
                plan_name="gmv_overall_v2",
            ),
            expected_governance=ExpectedGovernanceDecision(
                outcome=GovernanceOutcome.ALLOWED,
            ),
        ),
        "Plan Selected 时必须显式冻结 Result Grain。",
    )


def test_catalog_rejects_duplicate_case_ids() -> None:
    case = build_allowed_case()

    expect_validation_error(
        lambda: GoldenCaseCatalogV2(
            cases=(
                case,
                case,
            ),
        ),
        "Golden Case Catalog 必须拒绝重复 case_id。",
    )


def test_catalog_is_immutable() -> None:
    catalog = GoldenCaseCatalogV2(
        cases=(build_allowed_case(),)
    )

    try:
        catalog.version = "changed"
    except ValidationError:
        return

    raise AssertionError(
        "GoldenCaseCatalogV2 必须不可变。"
    )



def test_selected_plan_can_skip_governance_evaluation() -> None:
    case = GoldenCaseV2(
        case_id="dev_semantic_only_001",
        split=GoldenCaseSplit.DEVELOPMENT,
        category=GoldenCaseCategory.CANONICAL,
        question="各渠道 GMV 排名",
        expected_metric=ExpectedMetricDecision(
            status=MetricDecisionStatus.MATCHED,
            metric_name="gmv",
        ),
        expected_intent=ExpectedIntentDecision(
            result_grain=ResultGrain.CHANNEL,
            ranking_type=RankingType.RANKING,
            sort_direction=SortDirection.DESC,
        ),
        expected_plan=ExpectedPlanDecision(
            status=PlanDecisionStatus.SELECTED,
            plan_name="gmv_channel_v2",
        ),
        expected_governance=ExpectedGovernanceDecision(
            outcome=GovernanceOutcome.NOT_EVALUATED,
        ),
    )

    assert_equal(
        case.expected_governance.outcome,
        GovernanceOutcome.NOT_EVALUATED,
        (
            "纯语义 Golden Case 应允许在 Plan Selection 后停止，"
            "不强制伪造 Governance 结论。"
        ),
    )

def run_tests() -> None:
    tests = [
        test_valid_allowed_case,
        test_valid_clarification_case,
        test_valid_governance_denial_case,
        test_valid_unsupported_shape_case,
        test_valid_overall_with_region_scope,
        test_matched_metric_requires_metric_name,
        test_matched_metric_rejects_candidate_list,
        test_clarification_requires_two_candidates,
        test_clarification_rejects_duplicate_candidates,
        test_unsupported_metric_rejects_preselected_metric,
        test_selected_plan_requires_plan_name,
        test_denied_governance_requires_reason_code,
        test_allowed_governance_rejects_reason_code,
        test_top1_requires_limit_one,
        test_topn_requires_limit_greater_than_one,
        test_ranking_rejects_limit,
        test_clarification_cannot_select_plan,
        test_unsupported_shape_cannot_claim_governance_denial,
        test_selected_plan_requires_result_grain,
        test_catalog_rejects_duplicate_case_ids,
        test_catalog_is_immutable,
        test_selected_plan_can_skip_governance_evaluation,
    ]

    passed = 0
    failed = 0

    for test in tests:
        print("=" * 80)
        print(f"Running: {test.__name__}")

        try:
            test()
            passed += 1
            print("[PASS]")
        except Exception as exc:
            failed += 1
            print("[FAIL]")
            print(exc)

    print("=" * 80)
    print("Golden Case V2 Model Test Summary")
    print(f"Total: {len(tests)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    run_tests()
