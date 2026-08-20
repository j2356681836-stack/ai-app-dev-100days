from __future__ import annotations

import inspect
from decimal import Decimal

from app.agents.contribution_analysis_v2 import (
    ContributionReconciliationStatusV2,
)
from app.delivery import monthly_contribution_delivery_v2 as module


def test_runtime_reuses_existing_monthly_overall_comparison() -> None:
    source = inspect.getsource(
        module.run_day89_monthly_gmv_channel_contribution_v2
    )

    assert "run_day89_monthly_gmv_report_v2(" in source
    assert source.count("run_day89_monthly_gmv_report_v2(") == 1


def test_runtime_adds_exactly_two_structured_channel_queries() -> None:
    source = inspect.getsource(
        module.run_day89_monthly_gmv_channel_contribution_v2
    )

    assert source.count(
        "invoke_governed_plan_delivery_v2("
    ) == 2
    assert "analysis_window=comparison.current_window" in source
    assert "analysis_window=comparison.reference_window" in source


def test_four_way_effective_scope_equivalence_is_required() -> None:
    linkage_source = inspect.getsource(
        module._validate_four_way_trust_linkage
    )
    plan_scope_source = inspect.getsource(
        module._validate_plan_scope_semantics_v2
    )

    assert "scope_summaries" in linkage_source
    assert "len(scope_summaries) != 1" in linkage_source
    assert "_validate_plan_scope_semantics_v2(" in linkage_source

    assert "scope_mode" in plan_scope_source
    assert "required_dimensions" in plan_scope_source
    assert "source_tables" in plan_scope_source


def test_instance_scope_fingerprint_is_not_compared_across_requests() -> None:
    linkage_source = inspect.getsource(
        module._validate_four_way_trust_linkage
    )

    # 注释可以解释 scope_binding_fingerprint 为什么不能跨 request 比较；
    # 真正防回归的是实现中不能再构造 fingerprint 集合或调用旧 helper。
    assert "scope_fingerprints" not in linkage_source
    assert "_scope_fingerprint(" not in linkage_source
    assert "scope_summaries" in linkage_source


def test_channel_member_key_comes_from_protected_result_not_ui() -> None:
    source = inspect.getsource(
        module._channel_observations
    )

    assert 'row.get("channel_name")' in source
    assert 'row.get("gmv")' in source
    assert "ContributionObservationV2(" in source
    assert "Streamlit" not in source


def test_contribution_evidence_has_four_parent_inputs() -> None:
    source = inspect.getsource(
        module.run_day89_monthly_gmv_channel_contribution_v2
    )

    assert "current_overall_evidence_id" in source
    assert "reference_overall_evidence_id" in source
    assert "current_dimension_evidence_id" in source
    assert "reference_dimension_evidence_id" in source


def test_contribution_reference_has_single_canonical_builder() -> None:
    source = inspect.getsource(
        module.run_day89_monthly_gmv_channel_contribution_v2
    )

    assert "build_dimension_contribution_material_v2(" in source
    assert "evidence_reference=contribution_ref" in source
    assert "_contribution_evidence_reference(" not in source


def test_delivery_uses_diagnostic_not_causal_mode() -> None:
    source = inspect.getsource(
        module.run_day89_monthly_gmv_channel_contribution_v2
    )

    # 生产 Runtime 必须构建 DIAGNOSTIC Insight，
    # 并交给既有 Contribution Insight Adapter。
    # 不用“源码里不能出现 causal 单词”这种脆弱断言，
    # 因为边界说明本身可以合法写成“不声明 causality”。
    assert (
        "analysis_mode=AnalysisModeV2.DIAGNOSTIC"
        in source
    )
    assert "attach_contribution_result_to_insight_v2(" in source
    assert "AnalysisModeV2.FACT" not in source


def test_console_receives_comparison_contribution_and_breakdown() -> None:
    source = inspect.getsource(
        module.run_day89_monthly_gmv_channel_contribution_v2
    )

    assert "metric_comparison_result=metric_comparison" in source
    assert "contribution_result=contribution" in source
    assert "breakdown_evidence_id=" in source


def test_supported_pair_remains_only_gmv_channel() -> None:
    import app.agents.contribution_analysis_v2 as contribution

    assert contribution._SUPPORTED_ADDITIVE_PAIRS_V2 == frozenset(
        {("gmv", "channel")}
    )


TESTS = (
    test_runtime_reuses_existing_monthly_overall_comparison,
    test_runtime_adds_exactly_two_structured_channel_queries,
    test_four_way_effective_scope_equivalence_is_required,
    test_instance_scope_fingerprint_is_not_compared_across_requests,
    test_channel_member_key_comes_from_protected_result_not_ui,
    test_contribution_evidence_has_four_parent_inputs,
    test_contribution_reference_has_single_canonical_builder,
    test_delivery_uses_diagnostic_not_causal_mode,
    test_console_receives_comparison_contribution_and_breakdown,
    test_supported_pair_remains_only_gmv_channel,
)


def run_acceptance() -> None:
    print("Day89 Monthly GMV Channel Contribution Acceptance")

    passed = 0
    failures: list[str] = []

    for test in TESTS:
        try:
            test()
            passed += 1
        except Exception as exc:  # noqa: BLE001
            failures.append(
                f"{test.__name__}: "
                f"{type(exc).__name__}: {exc}"
            )

    print(f"Total: {len(TESTS)}")
    print(f"Passed: {passed}")
    print(f"Failed: {len(failures)}")

    for failure in failures:
        print(f"- {failure}")

    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    run_acceptance()
