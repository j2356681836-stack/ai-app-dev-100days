from __future__ import annotations

from decimal import Decimal
from pathlib import Path

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
from app.delivery.focused_change_breakdown_delivery_v2 import (
    _expected_member_field_v2,
)


ROOT = Path(__file__).resolve().parents[2]
RUNTIME_SOURCE = (
    ROOT / "app" / "delivery" / "investigation_runtime_v2.py"
).read_text(encoding="utf-8")
UI_SOURCE = (
    ROOT / "app" / "ui" / "decision_console_app.py"
).read_text(encoding="utf-8")


def _channel_result() -> FocusedChangeBreakdownResultV2:
    return FocusedChangeBreakdownResultV2(
        dimension_name=FocusedChangeDimensionV2.CHANNEL,
        focus_member_key="__overall__",
        focus_member_label="整体GMV",
        reference_focus_value=Decimal("100"),
        current_focus_value=Decimal("150"),
        focus_delta=Decimal("50"),
        members=(
            FocusedChangeMemberV2(
                member_key="JD",
                member_label="京东旗舰店",
                reference_value=Decimal("20"),
                current_value=Decimal("50"),
                delta=Decimal("30"),
                share_of_focus_delta=Decimal("0.60"),
            ),
            FocusedChangeMemberV2(
                member_key="TMALL",
                member_label="天猫旗舰店",
                reference_value=Decimal("80"),
                current_value=Decimal("100"),
                delta=Decimal("20"),
                share_of_focus_delta=Decimal("0.40"),
            ),
        ),
        positive_change_ranking=("JD", "TMALL"),
        negative_change_ranking=(),
        sum_member_delta=Decimal("50"),
        unexplained_remainder=Decimal("0"),
        reconciliation_status=(
            FocusedChangeReconciliationStatusV2.RECONCILED
        ),
    )


def test_channel_is_a_first_class_focused_change_dimension() -> None:
    assert FocusedChangeDimensionV2.CHANNEL.value == "channel"
    assert (
        _expected_member_field_v2(
            FocusedChangeDimensionV2.CHANNEL
        )
        == "channel_name"
    )

    print(
        "PASS: "
        "test_channel_is_a_first_class_focused_change_dimension"
    )


def test_runtime_maps_drill_channel_to_change_companion() -> None:
    assert (
        '"drill_channel": FocusedChangeDimensionV2.CHANNEL'
        in RUNTIME_SOURCE
    )
    assert "build_global_change_breakdown_delivery_v2" in RUNTIME_SOURCE
    assert "overall_reference_value" in RUNTIME_SOURCE
    assert "overall_current_value" in RUNTIME_SOURCE

    print(
        "PASS: "
        "test_runtime_maps_drill_channel_to_change_companion"
    )


def test_channel_assessment_uses_business_channel_semantics() -> None:
    assessment = assess_investigation_step_v2(
        result=_channel_result(),
        is_overall_scope=True,
    )

    assert (
        assessment.pattern
        == ChangeConcentrationPatternV2.DOMINANT
    )
    assert "渠道" in assessment.conclusion
    assert "渠道" in assessment.next_step_recommendation
    assert "旧城市粒度" not in assessment.next_step_recommendation
    assert "不能证明业务因果" in assessment.cannot_confirm[0]

    print(
        "PASS: "
        "test_channel_assessment_uses_business_channel_semantics"
    )


def test_ui_uses_two_period_channel_change_instead_of_snapshot() -> None:
    assert '"drill_channel": "channel"' in UI_SOURCE
    assert '"channel": "渠道"' in UI_SOURCE
    assert (
        "UserInvestigationDomainV2.CHANNEL"
        in UI_SOURCE
    )
    assert "AnalyticalGrainV2.CHANNEL" in UI_SOURCE

    print(
        "PASS: "
        "test_ui_uses_two_period_channel_change_instead_of_snapshot"
    )


def main() -> None:
    test_channel_is_a_first_class_focused_change_dimension()
    test_runtime_maps_drill_channel_to_change_companion()
    test_channel_assessment_uses_business_channel_semantics()
    test_ui_uses_two_period_channel_change_instead_of_snapshot()


if __name__ == "__main__":
    main()
