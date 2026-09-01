from decimal import Decimal

from app.delivery.contribution_investigation_recommendation_v1 import (
    ContributionInvestigationRecommendationV1,
)
from app.delivery.investigation_focus_scope_v1 import (
    build_contribution_investigation_focus_scope_v1,
)


def test_f02_focus_inherits_trusted_comparison_values() -> None:
    recommendation = ContributionInvestigationRecommendationV1(
        metric_name="gmv",
        dimension_name="channel",
        member_key="京东旗舰店",
        member_label="京东旗舰店",
        reference_value=Decimal("139004.92"),
        current_value=Decimal("243351.20"),
        delta=Decimal("104346.28"),
        contribution_rate=Decimal("0.2720"),
        overall_delta=Decimal("383605.84"),
        direction="positive",
        rationale="test fixture",
        can_confirm=("fixture",),
        cannot_confirm=("fixture",),
        contribution_evidence_id="ev_contrib_fixture",
    )

    focus = build_contribution_investigation_focus_scope_v1(
        recommendation
    )

    assert focus.reference_value == Decimal("139004.92")
    assert focus.current_value == Decimal("243351.20")
    assert focus.delta == Decimal("104346.28")
    assert (
        focus.current_value - focus.reference_value
        == focus.delta
    )

    print(
        "PASS: test_f02_focus_inherits_trusted_comparison_values"
    )
    print("PASS: focus delta = 104346.28")


if __name__ == "__main__":
    test_f02_focus_inherits_trusted_comparison_values()
