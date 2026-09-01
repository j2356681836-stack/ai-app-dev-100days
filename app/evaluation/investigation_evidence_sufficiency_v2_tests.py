from decimal import Decimal

from app.agents.focused_change_breakdown_v2 import (
    FocusedChangeDimensionV2,
)
from app.agents.investigation_evidence_sufficiency_v2 import (
    InvestigationBudgetStageV2,
    InvestigationEvidenceSufficiencyV2,
    assess_investigation_evidence_sufficiency_v2,
)
from app.agents.investigation_step_assessment_v2 import (
    ChangeConcentrationPatternV2,
    InvestigationStepAssessmentV2,
)


def _assessment(
    pattern: ChangeConcentrationPatternV2,
) -> InvestigationStepAssessmentV2:
    return InvestigationStepAssessmentV2(
        policy_version="test",
        dimension_name=FocusedChangeDimensionV2.CATEGORY,
        pattern=pattern,
        leader_member_key="护肤",
        leader_member_label="护肤",
        leader_share=Decimal("0.4555"),
        runner_up_member_key="香氛",
        runner_up_member_label="香氛",
        runner_up_share=Decimal("0.2428"),
        leader_gap=Decimal("0.2127"),
        top2_concentration=Decimal("0.6983"),
        conclusion="护肤是当前最大的数值变化来源。",
        can_confirm=("变化额已经完成核对。",),
        cannot_confirm=("不能据此证明业务根因。",),
        next_step_recommendation="建议继续检查活动或地区证据。",
    )


def test_step_count_does_not_equal_conclusive() -> None:
    status = assess_investigation_evidence_sufficiency_v2(
        steps_used=2,
        assessment=_assessment(
            ChangeConcentrationPatternV2.LEADING_NOT_DOMINANT
        ),
        has_legal_next_action=True,
    )

    assert status.status == InvestigationEvidenceSufficiencyV2.DIRECTIONAL
    assert (
        status.budget_stage
        == InvestigationBudgetStageV2.SOFT_BUDGET_REACHED
    )
    assert status.extension_recommended is True
    assert status.suggested_additional_steps == 2

    print("PASS: test_step_count_does_not_equal_conclusive")
    print("PASS: soft budget exhausted != analysis complete")
    print("PASS: extension recommendation = 2 steps")


def test_hard_cap_stops_extension_but_keeps_stage_conclusion() -> None:
    status = assess_investigation_evidence_sufficiency_v2(
        steps_used=5,
        assessment=_assessment(
            ChangeConcentrationPatternV2.NEAR_TIE
        ),
        has_legal_next_action=True,
    )

    assert (
        status.status
        == InvestigationEvidenceSufficiencyV2.INCONCLUSIVE_ACTIONABLE
    )
    assert status.hard_cap_reached is True
    assert status.extension_recommended is False
    assert "护肤" in status.stage_conclusion

    print("PASS: test_hard_cap_stops_extension_but_keeps_stage_conclusion")


def test_explicit_sufficiency_can_stop_early() -> None:
    status = assess_investigation_evidence_sufficiency_v2(
        steps_used=1,
        assessment=_assessment(
            ChangeConcentrationPatternV2.DOMINANT
        ),
        has_legal_next_action=True,
        explicit_evidence_sufficient=True,
    )

    assert status.status == InvestigationEvidenceSufficiencyV2.CONCLUSIVE
    assert status.extension_recommended is False

    print("PASS: test_explicit_sufficiency_can_stop_early")



def test_soft_budget_without_legal_action_does_not_fake_extension() -> None:
    status = assess_investigation_evidence_sufficiency_v2(
        steps_used=2,
        assessment=_assessment(
            ChangeConcentrationPatternV2.LEADING_NOT_DOMINANT
        ),
        has_legal_next_action=False,
    )

    assert status.status == InvestigationEvidenceSufficiencyV2.DIRECTIONAL
    assert status.extension_recommended is False
    assert status.suggested_additional_steps == 0

    print(
        "PASS: "
        "test_soft_budget_without_legal_action_does_not_fake_extension"
    )


def main() -> None:
    test_step_count_does_not_equal_conclusive()
    test_hard_cap_stops_extension_but_keeps_stage_conclusion()
    test_explicit_sufficiency_can_stop_early()
    test_soft_budget_without_legal_action_does_not_fake_extension()


if __name__ == "__main__":
    main()
