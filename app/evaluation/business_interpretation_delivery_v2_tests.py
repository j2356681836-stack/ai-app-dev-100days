from datetime import date
from decimal import Decimal

from app.agents.focused_change_breakdown_v2 import (
    FocusedChangeDimensionV2,
)
from app.agents.investigation_step_assessment_v2 import (
    ChangeConcentrationPatternV2,
)
from app.delivery.decision_console_view_v2 import (
    ProtectedBreakdownViewV2,
)
from app.delivery.focused_change_breakdown_delivery_v2 import (
    ChangeBreakdownScopeKindV2,
    build_global_change_breakdown_delivery_v2,
)
from app.semantic_layer.time_comparison_contract_v2 import (
    AlignmentModeV2,
    ComparisonTypeV2,
    PeriodModeV2,
    TimeComparisonContractV2,
    TimeWindowReferenceV2,
)


FULL_SCOPE = (
    "地区代码：BEIJING、CHONGQING、GUANGDONG_GUANGZHOU、"
    "GUANGDONG_SHENZHEN、GUANGXI_GUILIN、HENAN_LUOYANG、"
    "HUBEI_WUHAN、JIANGSU_NANJING、LIAONING_SHENYANG、"
    "SHAANXI_XIAN、SHANDONG_QINGDAO、SHANGHAI、"
    "SICHUAN_CHENGDU、SICHUAN_MIANYANG、ZHEJIANG_HANGZHOU、"
    "ZHEJIANG_JINHUA；渠道代码：DOUYIN、JD、OFFICIAL_MALL、"
    "TMALL、WECHAT_MINI_PROGRAM、XIAOHONGSHU"
)


def _window(
    start: date,
    end: date,
) -> TimeWindowReferenceV2:
    return TimeWindowReferenceV2(
        start_date=start,
        end_date=end,
    )


def _breakdown(
    *,
    evidence_id: str,
    window: TimeWindowReferenceV2,
    rows: tuple[dict, ...],
) -> ProtectedBreakdownViewV2:
    return ProtectedBreakdownViewV2(
        evidence_id=evidence_id,
        metric_name="gmv",
        result_grain="category",
        analysis_window=window,
        scope_summary=FULL_SCOPE,
        field_names=("category", "gmv"),
        rows=rows,
        row_count=len(rows),
        dataset_name="beauty_bi_v2",
        plan_name="gmv_category_v2",
        tool_name="governed_gmv_category_query",
        tool_version="dataset_v2",
        audit_event_id=f"audit-{evidence_id}",
    )


def test_delivery_contains_business_scope_and_assessment() -> None:
    reference_window = _window(
        date(2025, 9, 1),
        date(2025, 9, 30),
    )
    current_window = _window(
        date(2025, 10, 1),
        date(2025, 10, 31),
    )

    comparison = TimeComparisonContractV2(
        comparison_type=ComparisonTypeV2.MOM,
        period_mode=PeriodModeV2.COMPLETED_PERIOD,
        alignment_mode=AlignmentModeV2.CALENDAR_ALIGNED,
        current_window=current_window,
        reference_window=reference_window,
    )

    reference = _breakdown(
        evidence_id="ev-ref",
        window=reference_window,
        rows=(
            {"category": "护肤", "gmv": Decimal("396169.58")},
            {"category": "香氛", "gmv": Decimal("190199.42")},
            {"category": "彩妆", "gmv": Decimal("174119.90")},
            {"category": "防晒", "gmv": Decimal("87276.30")},
        ),
    )

    current = _breakdown(
        evidence_id="ev-cur",
        window=current_window,
        rows=(
            {"category": "护肤", "gmv": Decimal("570911.52")},
            {"category": "香氛", "gmv": Decimal("283348.54")},
            {"category": "彩妆", "gmv": Decimal("248853.68")},
            {"category": "防晒", "gmv": Decimal("128257.30")},
        ),
    )

    delivery = build_global_change_breakdown_delivery_v2(
        current_breakdown=current,
        reference_breakdown=reference,
        comparison=comparison,
        overall_reference_value=Decimal("847765.20"),
        overall_current_value=Decimal("1231371.04"),
        dimension=FocusedChangeDimensionV2.CATEGORY,
    )

    assert delivery.scope_kind == ChangeBreakdownScopeKindV2.OVERALL

    assert delivery.business_scope is not None
    assert (
        delivery.business_scope.channel_summary
        == "全部授权渠道（6个）"
    )
    assert (
        delivery.business_scope.geography_summary
        == "全部可用城市（16个）"
    )

    assert delivery.assessment is not None
    assert (
        delivery.assessment.pattern
        == ChangeConcentrationPatternV2.LEADING_NOT_DOMINANT
    )
    assert delivery.assessment.leader_member_label == "护肤"
    assert "本轮" not in delivery.assessment.conclusion
    assert "地理" in delivery.assessment.next_step_recommendation

    print(
        "PASS: "
        "test_delivery_contains_business_scope_and_assessment"
    )
    print("PASS: compact business scope is attached in Delivery")
    print("PASS: deterministic post-step conclusion is attached in Delivery")


if __name__ == "__main__":
    test_delivery_contains_business_scope_and_assessment()
