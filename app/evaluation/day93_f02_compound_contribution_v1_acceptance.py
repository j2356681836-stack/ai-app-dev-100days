from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.agents.contribution_analysis_v2 import (
    ContributionObservationV2,
    analyze_additive_contribution_v2,
)
from app.delivery.contribution_investigation_recommendation_v1 import (
    build_contribution_investigation_recommendation_v1,
)
from app.delivery.decision_console_runtime_v2 import (
    _extract_day93_f02_adjacent_months_v1,
    _is_day93_f02_compound_gmv_channel_question_v1,
    build_monthly_mom_comparison_v2,
)


def _assert(name: str, condition: bool) -> None:
    if not condition:
        raise AssertionError(name)
    print(f"[PASS] {name}")


def _negative_contribution():
    comparison = build_monthly_mom_comparison_v2(
        anchor_date=date(2025, 10, 31)
    )

    return analyze_additive_contribution_v2(
        metric_name="gmv",
        dimension_name="channel",
        comparison=comparison,
        current_overall_value=Decimal("80"),
        reference_overall_value=Decimal("100"),
        current_members=(
            ContributionObservationV2(
                member_key="A",
                member_label="渠道A",
                value=Decimal("30"),
            ),
            ContributionObservationV2(
                member_key="B",
                member_label="渠道B",
                value=Decimal("50"),
            ),
        ),
        reference_members=(
            ContributionObservationV2(
                member_key="A",
                member_label="渠道A",
                value=Decimal("60"),
            ),
            ContributionObservationV2(
                member_key="B",
                member_label="渠道B",
                value=Decimal("40"),
            ),
        ),
    )


def _positive_contribution():
    comparison = build_monthly_mom_comparison_v2(
        anchor_date=date(2025, 10, 31)
    )

    return analyze_additive_contribution_v2(
        metric_name="gmv",
        dimension_name="channel",
        comparison=comparison,
        current_overall_value=Decimal("130"),
        reference_overall_value=Decimal("100"),
        current_members=(
            ContributionObservationV2(
                member_key="A",
                member_label="渠道A",
                value=Decimal("70"),
            ),
            ContributionObservationV2(
                member_key="B",
                member_label="渠道B",
                value=Decimal("60"),
            ),
        ),
        reference_members=(
            ContributionObservationV2(
                member_key="A",
                member_label="渠道A",
                value=Decimal("50"),
            ),
            ContributionObservationV2(
                member_key="B",
                member_label="渠道B",
                value=Decimal("50"),
            ),
        ),
    )


def run_acceptance() -> None:
    passed = 0

    question = (
        "2025年10月GMV相比9月表现怎么样？"
        "如果我要继续调查，最值得先看哪个渠道？"
    )

    _assert(
        "F02 compound question is detected",
        _is_day93_f02_compound_gmv_channel_question_v1(
            question
        ),
    )
    passed += 1

    _assert(
        "plain monthly comparison is not upgraded to F02",
        not _is_day93_f02_compound_gmv_channel_question_v1(
            "2025年10月GMV相比9月表现怎么样？"
        ),
    )
    passed += 1

    months = _extract_day93_f02_adjacent_months_v1(
        question
    )
    _assert(
        "adjacent month contract preserves Oct vs Sep",
        months
        == (
            date(2025, 10, 31),
            date(2025, 9, 30),
        ),
    )
    passed += 1

    _assert(
        "non-adjacent month comparison does not silently rewrite",
        _extract_day93_f02_adjacent_months_v1(
            "2025年10月GMV相比8月怎么样？"
            "继续调查最值得先看哪个渠道？"
        )
        is None,
    )
    passed += 1

    negative = _negative_contribution()
    negative_rec = (
        build_contribution_investigation_recommendation_v1(
            contribution=negative,
            contribution_evidence_id="ev_contrib_negative",
        )
    )

    _assert(
        "overall decline selects largest negative channel",
        (
            negative_rec is not None
            and negative_rec.member_key == "A"
            and negative_rec.direction == "negative"
            and negative_rec.delta == Decimal("-30")
        ),
    )
    passed += 1

    positive = _positive_contribution()
    positive_rec = (
        build_contribution_investigation_recommendation_v1(
            contribution=positive,
            contribution_evidence_id="ev_contrib_positive",
        )
    )

    _assert(
        "overall growth selects largest positive channel",
        (
            positive_rec is not None
            and positive_rec.member_key == "A"
            and positive_rec.direction == "positive"
            and positive_rec.delta == Decimal("20")
        ),
    )
    passed += 1

    comparison = build_monthly_mom_comparison_v2(
        anchor_date=date(2025, 10, 31)
    )
    unreconciled = analyze_additive_contribution_v2(
        metric_name="gmv",
        dimension_name="channel",
        comparison=comparison,
        current_overall_value=Decimal("80"),
        reference_overall_value=Decimal("100"),
        current_members=(
            ContributionObservationV2(
                member_key="A",
                member_label="渠道A",
                value=Decimal("40"),
            ),
        ),
        reference_members=(
            ContributionObservationV2(
                member_key="A",
                member_label="渠道A",
                value=Decimal("50"),
            ),
        ),
    )

    _assert(
        "unreconciled contribution does not publish recommendation",
        build_contribution_investigation_recommendation_v1(
            contribution=unreconciled,
            contribution_evidence_id="ev_unreconciled",
        )
        is None,
    )
    passed += 1

    print("=" * 72)
    print(
        "Day93 F02 Compound Comparison + Contribution "
        f"Acceptance: {passed}/7 PASS"
    )


if __name__ == "__main__":
    run_acceptance()
