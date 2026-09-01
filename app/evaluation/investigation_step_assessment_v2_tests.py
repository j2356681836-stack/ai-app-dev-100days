from decimal import Decimal

from app.agents.focused_change_breakdown_v2 import (
    FocusedChangeBreakdownResultV2,
    FocusedChangeDimensionV2,
    FocusedChangeMemberV2,
    FocusedChangeReconciliationStatusV2,
)
from app.agents.investigation_step_assessment_v2 import (
    ChangeConcentrationPatternV2,
    assess_investigation_step_v2,
)


def _category_result() -> FocusedChangeBreakdownResultV2:
    members = (
        ("护肤", "396169.58", "570911.52", "174741.94", "0.455525"),
        ("香氛", "190199.42", "283348.54", "93149.12", "0.242825"),
        ("彩妆", "174119.90", "248853.68", "74733.78", "0.194820"),
        ("防晒", "87276.30", "128257.30", "40981.00", "0.106830"),
    )

    return FocusedChangeBreakdownResultV2(
        dimension_name=FocusedChangeDimensionV2.CATEGORY,
        focus_member_key="__overall__",
        focus_member_label="整体GMV",
        reference_focus_value=Decimal("847765.20"),
        current_focus_value=Decimal("1231371.04"),
        focus_delta=Decimal("383605.84"),
        members=tuple(
            FocusedChangeMemberV2(
                member_key=label,
                member_label=label,
                reference_value=Decimal(reference),
                current_value=Decimal(current),
                delta=Decimal(delta),
                share_of_focus_delta=Decimal(share),
            )
            for label, reference, current, delta, share in members
        ),
        positive_change_ranking=("护肤", "香氛", "彩妆", "防晒"),
        negative_change_ranking=(),
        sum_member_delta=Decimal("383605.84"),
        unexplained_remainder=Decimal("0"),
        reconciliation_status=(
            FocusedChangeReconciliationStatusV2.RECONCILED
        ),
    )


def _city_result() -> FocusedChangeBreakdownResultV2:
    shares = (
        ("金华市", "0.1124"),
        ("深圳市", "0.1088"),
        ("北京市", "0.1021"),
        ("洛阳市", "0.0939"),
        ("南京市", "0.0700"),
        ("西安市", "0.0600"),
        ("杭州市", "0.0550"),
        ("青岛市", "0.0500"),
        ("成都市", "0.0500"),
        ("广州市", "0.0450"),
        ("上海市", "0.0450"),
        ("武汉市", "0.0400"),
        ("重庆市", "0.0400"),
        ("沈阳市", "0.0400"),
        ("绵阳市", "0.0400"),
        ("桂林市", "0.0478"),
    )

    members = tuple(
        FocusedChangeMemberV2(
            member_key=label,
            member_label=label,
            reference_value=Decimal("100"),
            current_value=(
                Decimal("100")
                + Decimal(share) * Decimal("100")
            ),
            delta=Decimal(share) * Decimal("100"),
            share_of_focus_delta=Decimal(share),
        )
        for label, share in shares
    )

    return FocusedChangeBreakdownResultV2(
        dimension_name=FocusedChangeDimensionV2.REGION,
        focus_member_key="__overall__",
        focus_member_label="整体GMV",
        reference_focus_value=Decimal("1000"),
        current_focus_value=Decimal("1100"),
        focus_delta=Decimal("100"),
        members=members,
        positive_change_ranking=tuple(
            label for label, _ in shares
        ),
        negative_change_ranking=(),
        sum_member_delta=Decimal("100"),
        unexplained_remainder=Decimal("0"),
        reconciliation_status=(
            FocusedChangeReconciliationStatusV2.RECONCILED
        ),
    )

def test_category_is_leading_but_not_dominant() -> None:
    assessment = assess_investigation_step_v2(
        result=_category_result(),
        is_overall_scope=True,
    )

    assert (
        assessment.pattern
        == ChangeConcentrationPatternV2.LEADING_NOT_DOMINANT
    )
    assert assessment.leader_member_label == "护肤"
    assert assessment.runner_up_member_label == "香氛"
    assert assessment.leader_share == Decimal("0.455525")
    assert assessment.leader_gap == Decimal("0.212700")
    assert assessment.top2_concentration == Decimal("0.698350")
    assert "45.55%" in assessment.conclusion
    assert "69.84%" in assessment.can_confirm[-1]
    assert "地理" in assessment.next_step_recommendation

    print("PASS: test_category_is_leading_but_not_dominant")
    print("PASS: leader = 护肤")
    print("PASS: top1 share ≈ 45.55%")
    print("PASS: top1-top2 gap ≈ 21.27pp")
    print("PASS: top2 concentration ≈ 69.84%")


def test_city_top_two_are_near_tie() -> None:
    assessment = assess_investigation_step_v2(
        result=_city_result(),
        is_overall_scope=True,
    )

    assert (
        assessment.pattern
        == ChangeConcentrationPatternV2.NEAR_TIE
    )
    assert assessment.leader_member_label == "金华市"
    assert assessment.runner_up_member_label == "深圳市"
    assert assessment.leader_gap is not None
    assert assessment.leader_gap == Decimal("0.0036")
    assert "没有明显单一主导" in assessment.conclusion
    assert "更高层级地理结构" in assessment.next_step_recommendation

    print("PASS: test_city_top_two_are_near_tie")


def main() -> None:
    test_category_is_leading_but_not_dominant()
    test_city_top_two_are_near_tie()


if __name__ == "__main__":
    main()
