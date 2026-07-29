from app.semantic_layer.decision_resolver_v2 import (
    DecisionRankingType,
    DecisionResultGrain,
    DecisionSortDirection,
    MetricResolutionStatus,
    PlanResolutionStatus,
    resolve_decision_v2,
    resolve_metric_v2,
    resolve_result_grain_v2,
)
from app.semantic_layer.metric_loader_v2 import (
    get_metric_v2_by_name,
    load_metrics_v2,
    search_metric_candidates_v2,
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


def test_loader_reads_exact_19_v2_metrics() -> None:
    metrics = load_metrics_v2()

    assert_equal(
        len(metrics),
        19,
        "V2 Loader 应读取冻结的 19 Metrics。",
    )

    assert_true(
        get_metric_v2_by_name(
            "member_gmv_share"
        )
        is not None,
        "V2 Loader 必须能读取 V2-only Metric。",
    )


def test_rule_search_prefers_specific_margin_rate() -> None:
    candidates = search_metric_candidates_v2(
        "哪个品类毛利率最高？"
    )

    assert_equal(
        len(candidates),
        1,
        "更具体词应压过较短的“毛利”命中。",
    )

    assert_equal(
        candidates[0]["name"],
        "gross_margin_rate",
        "毛利率不得错误命中毛利额。",
    )


def test_rule_search_matches_roi_alias_case_insensitively() -> None:
    candidates = search_metric_candidates_v2(
        "各渠道roi排名"
    )

    assert_equal(
        candidates[0]["name"],
        "roi",
        "ROI / roi 应视为同一正式 alias。",
    )


def test_generic_new_customer_requires_clarification() -> None:
    decision = resolve_metric_v2(
        "今年新客多少？"
    )

    assert_equal(
        decision.status,
        MetricResolutionStatus.NEEDS_CLARIFICATION,
        "未限定新客口径必须澄清。",
    )

    assert_equal(
        set(decision.candidates),
        {
            "brand_paid_new_customer_count",
            "channel_paid_new_customer_count",
        },
        "新客澄清必须保留品牌 / 渠道两个口径。",
    )


def test_channel_new_customer_is_not_ambiguous() -> None:
    decision = resolve_decision_v2(
        "2025年各渠道支付新客有多少？"
    )

    assert_equal(
        decision.metric.metric_name,
        "channel_paid_new_customer_count",
        "明确渠道新客时不得进入品牌/渠道歧义。",
    )

    assert_equal(
        decision.plan.plan_name,
        "channel_paid_new_customer_count_channel_v2",
        "渠道新客应选择 Channel Plan。",
    )


def test_aus_semantic_rule() -> None:
    decision = resolve_decision_v2(
        "平均每单多少钱？"
    )

    assert_equal(
        decision.metric.metric_name,
        "aus",
        "每单金额语义应归 AUS。",
    )

    assert_equal(
        decision.plan.plan_name,
        "aus_overall_v2",
        "整体 AUS 应选择 overall Plan。",
    )


def test_ipt_semantic_rule() -> None:
    decision = resolve_decision_v2(
        "平均每单买几件？"
    )

    assert_equal(
        decision.metric.metric_name,
        "ipt",
        "每单购买件数语义应归 IPT。",
    )


def test_repeat_customer_semantic_rule() -> None:
    decision = resolve_decision_v2(
        "至少在两个不同日期购买过的客户有多少？"
    )

    assert_equal(
        decision.metric.metric_name,
        "repeat_customer_count",
        "不同支付日期语义应归跨日复购人数。",
    )


def test_multi_order_customer_semantic_rule() -> None:
    decision = resolve_decision_v2(
        "下过两单及以上的客户有多少？"
    )

    assert_equal(
        decision.metric.metric_name,
        "multi_order_customer_count",
        "两单口径应归 Multi-order Customer。",
    )


def test_result_grain_resolution() -> None:
    assert_equal(
        resolve_result_grain_v2(
            "各渠道GMV排名"
        ),
        DecisionResultGrain.CHANNEL,
        "渠道问题应解析 Channel Grain。",
    )

    assert_equal(
        resolve_result_grain_v2(
            "哪个地区销售额最高"
        ),
        DecisionResultGrain.REGION,
        "地区问题应解析 Region Grain。",
    )

    assert_equal(
        resolve_result_grain_v2(
            "2025年毛利额是多少"
        ),
        DecisionResultGrain.OVERALL,
        "未要求分组时应解析 Overall Grain。",
    )


def test_gmv_channel_plan_selection() -> None:
    decision = resolve_decision_v2(
        "各渠道GMV排名"
    )

    assert_equal(
        decision.metric.metric_name,
        "gmv",
        "GMV Metric 应正确命中。",
    )

    assert_equal(
        decision.intent.result_grain,
        DecisionResultGrain.CHANNEL,
        "GMV 应识别 Channel Result Grain。",
    )

    assert_equal(
        decision.plan.plan_name,
        "gmv_channel_v2",
        "GMV Channel 应选择精确 Plan。",
    )


def test_roi_region_is_unsupported_shape() -> None:
    decision = resolve_decision_v2(
        "各地区ROI排名"
    )

    assert_equal(
        decision.metric.metric_name,
        "roi",
        "ROI Metric 应保持正确。",
    )

    assert_equal(
        decision.intent.result_grain,
        DecisionResultGrain.REGION,
        "问题要求 Region Result Grain。",
    )

    assert_equal(
        decision.plan.status,
        PlanResolutionStatus.UNSUPPORTED_SHAPE,
        "Catalog 无 ROI Region Plan 时必须返回 unsupported_shape。",
    )


def test_refund_rate_category_is_unsupported_shape() -> None:
    decision = resolve_decision_v2(
        "哪个品类退款率最高？"
    )

    assert_equal(
        decision.metric.metric_name,
        "refund_rate",
        "Refund Rate Metric 应正确。",
    )

    assert_equal(
        decision.plan.status,
        PlanResolutionStatus.UNSUPPORTED_SHAPE,
        "当前 Catalog 无 Refund Rate Category Plan。",
    )


def test_top1_shape() -> None:
    decision = resolve_decision_v2(
        "哪个品类毛利率最高？"
    )

    assert_equal(
        decision.intent.limit,
        1,
        "最高问题应解析 limit=1。",
    )

    assert_equal(
        decision.intent.ranking_type,
        DecisionRankingType.TOP1,
        "最高问题应解析 Top1。",
    )

    assert_equal(
        decision.intent.sort_direction,
        DecisionSortDirection.DESC,
        "最高问题应解析 DESC。",
    )


def test_topn_shape() -> None:
    decision = resolve_decision_v2(
        "各渠道GMV Top3"
    )

    assert_equal(
        decision.intent.limit,
        3,
        "Top3 应解析 limit=3。",
    )

    assert_equal(
        decision.intent.ranking_type,
        DecisionRankingType.TOPN,
        "Top3 应解析 TopN。",
    )


def test_resolver_does_not_execute_sql_contract() -> None:
    decision = resolve_decision_v2(
        "2025年会员GMV占比是多少？"
    )

    payload = decision.model_dump(
        mode="json"
    )

    forbidden_fields = {
        "sql",
        "table",
        "rows",
        "answer",
        "governance",
        "access_context",
    }

    assert_true(
        forbidden_fields.isdisjoint(
            payload.keys()
        ),
        (
            "Day74 Resolver 输出不得混入 SQL / DB / "
            "Answer / Governance Runtime 职责。"
        ),
    )



def test_plan_default_sort_fills_ranking_direction() -> None:
    decision = resolve_decision_v2(
        "各渠道GMV排名"
    )

    assert_equal(
        decision.intent.sort_direction,
        DecisionSortDirection.DESC,
        "未显式排序时应使用 gmv_channel_v2 默认 DESC。",
    )


def test_plan_default_sort_can_be_ascending() -> None:
    decision = resolve_decision_v2(
        "各渠道获客成本排名"
    )

    assert_equal(
        decision.intent.sort_direction,
        DecisionSortDirection.ASC,
        "CAC Query Plan 默认排序应为 ASC，不能统一假设 DESC。",
    )


def test_explicit_sort_overrides_plan_default() -> None:
    decision = resolve_decision_v2(
        "渠道ROI从低到高排名"
    )

    assert_equal(
        decision.intent.sort_direction,
        DecisionSortDirection.ASC,
        "用户显式 ASC 必须覆盖 roi_channel_v2 默认 DESC。",
    )


def test_scalar_query_does_not_inherit_plan_sort() -> None:
    decision = resolve_decision_v2(
        "2025年毛利额是多少？"
    )

    assert_equal(
        decision.intent.ranking_type,
        DecisionRankingType.UNKNOWN,
        "测试前提：普通单值查询不是排名场景。",
    )

    assert_equal(
        decision.intent.sort_direction,
        None,
        "非排名单值查询不应暴露无意义的 Plan default_sort。",
    )


def test_generic_period_repeat_rate_matches() -> None:
    decision = resolve_decision_v2(
        "2025年整体复购率是多少？"
    )

    assert_equal(
        decision.metric.status,
        MetricResolutionStatus.MATCHED,
        "普通报告周期复购率应被当前 V2 Metric 支持。",
    )

    assert_equal(
        decision.metric.metric_name,
        "repeat_customer_rate",
        "普通报告周期复购率应映射 repeat_customer_rate。",
    )

    assert_equal(
        decision.plan.plan_name,
        "repeat_customer_rate_overall_v2",
        "整体复购率应选择正式 Overall Plan。",
    )


def test_new_customer_30_day_repeat_rate_is_not_overclaimed() -> None:
    decision = resolve_decision_v2(
        "双11新客30天复购率是多少？"
    )

    assert_equal(
        decision.metric.status,
        MetricResolutionStatus.UNSUPPORTED,
        (
            "新客30天复购率属于 Cohort 口径，"
            "不得冒充当前 period repeat_customer_rate。"
        ),
    )

    assert_equal(
        decision.plan.status,
        PlanResolutionStatus.NOT_APPLICABLE,
        "Unsupported Cohort Metric 不应继续选择 Query Plan。",
    )


def test_first_purchase_90_day_repeat_rate_is_not_overclaimed() -> None:
    decision = resolve_decision_v2(
        "首购后90天复购率是多少？"
    )

    assert_equal(
        decision.metric.status,
        MetricResolutionStatus.UNSUPPORTED,
        "首购后90天复购率应保持 unsupported。",
    )

def run_tests() -> None:
    tests = [
        test_loader_reads_exact_19_v2_metrics,
        test_rule_search_prefers_specific_margin_rate,
        test_rule_search_matches_roi_alias_case_insensitively,
        test_generic_new_customer_requires_clarification,
        test_channel_new_customer_is_not_ambiguous,
        test_aus_semantic_rule,
        test_ipt_semantic_rule,
        test_repeat_customer_semantic_rule,
        test_multi_order_customer_semantic_rule,
        test_result_grain_resolution,
        test_gmv_channel_plan_selection,
        test_roi_region_is_unsupported_shape,
        test_refund_rate_category_is_unsupported_shape,
        test_top1_shape,
        test_topn_shape,
        test_resolver_does_not_execute_sql_contract,
        test_plan_default_sort_fills_ranking_direction,
        test_plan_default_sort_can_be_ascending,
        test_explicit_sort_overrides_plan_default,
        test_scalar_query_does_not_inherit_plan_sort,
        test_generic_period_repeat_rate_matches,
        test_new_customer_30_day_repeat_rate_is_not_overclaimed,
        test_first_purchase_90_day_repeat_rate_is_not_overclaimed,
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
    print("Decision Resolver V2 Test Summary")
    print(f"Total: {len(tests)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    run_tests()
