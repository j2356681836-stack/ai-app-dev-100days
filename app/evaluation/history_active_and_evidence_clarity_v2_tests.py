from __future__ import annotations

import ast
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

APP_PATH = (
    Path(__file__).resolve().parents[1]
    / "ui"
    / "decision_console_app.py"
)
SOURCE = APP_PATH.read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)


def _function(name: str) -> ast.FunctionDef:
    for node in TREE.body:
        if (
            isinstance(node, ast.FunctionDef)
            and node.name == name
        ):
            return node
    raise AssertionError(f"Missing function: {name}")


def test_new_ready_history_item_becomes_active_before_snapshot_sync() -> None:
    submit = _function("_submit_investigation")
    source = ast.get_source_segment(SOURCE, submit)

    assert source is not None

    append_pos = source.find(
        "append_analysis_history_item_v1"
    )
    activate_pos = source.find(
        "activate_analysis_history_item_v1"
    )
    snapshot_pos = source.find(
        "_sync_active_history_investigation_snapshot_v1"
    )

    assert append_pos >= 0
    assert activate_pos > append_pos
    assert snapshot_pos > activate_pos
    assert "history_id=history_item.history_id" in source

    print(
        "PASS: "
        "test_new_ready_history_item_becomes_active_before_snapshot_sync"
    )


def test_directional_ui_separates_numerical_and_causal_claims() -> None:
    render = _function("_render_agentic_business_section")
    source = ast.get_source_segment(SOURCE, render)

    assert source is not None
    assert "数值分解层面已经形成较明确的方向" in source
    assert "业务原因层面仍未确认" in source
    assert "反事实或实验对照" in source

    print(
        "PASS: "
        "test_directional_ui_separates_numerical_and_causal_claims"
    )


def test_campaign_dominant_wording_is_explicitly_numerical() -> None:
    result = FocusedChangeBreakdownResultV2(
        dimension_name=FocusedChangeDimensionV2.CAMPAIGN,
        focus_member_key="overall",
        focus_member_label="整体",
        reference_focus_value=100,
        current_focus_value=150,
        focus_delta=50,
        members=(
            FocusedChangeMemberV2(
                member_key="campaign",
                member_label="2025 双十一",
                reference_value=0,
                current_value=60,
                delta=60,
                share_of_focus_delta=1.2,
            ),
            FocusedChangeMemberV2(
                member_key="non_campaign",
                member_label="非活动订单",
                reference_value=100,
                current_value=90,
                delta=-10,
                share_of_focus_delta=-0.2,
            ),
        ),
        positive_change_ranking=("campaign",),
        negative_change_ranking=("non_campaign",),
        sum_member_delta=50,
        unexplained_remainder=0,
        reconciliation_status=(
            FocusedChangeReconciliationStatusV2.RECONCILED
        ),
    )

    assessment = assess_investigation_step_v2(
        result=result,
        is_overall_scope=True,
    )

    assert (
        assessment.pattern
        == ChangeConcentrationPatternV2.DOMINANT
    )
    assert "单一主导的数值来源" in assessment.conclusion
    assert "业务根因" not in assessment.conclusion

    print(
        "PASS: "
        "test_campaign_dominant_wording_is_explicitly_numerical"
    )


def main() -> None:
    test_new_ready_history_item_becomes_active_before_snapshot_sync()
    test_directional_ui_separates_numerical_and_causal_claims()
    test_campaign_dominant_wording_is_explicitly_numerical()


if __name__ == "__main__":
    main()
