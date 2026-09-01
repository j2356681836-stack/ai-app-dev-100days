from __future__ import annotations

from app.semantic_layer.analytics_planning_service_v2 import (
    AnalyticsPlanningStatusV2,
    resolve_analytics_planning_v2,
)
from app.semantic_layer.analysis_mode_resolution_v2 import (
    resolve_analysis_mode_v2,
)
from app.semantic_layer.question_semantic_parser_v2 import (
    QuestionSemanticParseStatusV2,
)
from app.semantic_layer.requested_scope_resolution_v2 import (
    RequestedScopeResolutionStatusV2,
    RequestedScopeResolutionV2,
)
from app.semantic_layer.result_grain_resolver_v2 import (
    ResultDimensionV2,
    ResultGrainResolutionStatusV2,
    apply_fact_overall_fallback_v2,
    apply_seed_overall_fallback_v2,
    resolve_result_grain_v2,
)
from app.semantic_layer.semantic_decision_service_v2 import (
    SemanticDecisionResultV2,
    SemanticDecisionStatusV2,
)


FG01 = (
    "2025年8月GMV相比7月表现怎么样？"
    "如果我要继续调查，最值得优先看哪个方向？"
)


def _matched_gmv_semantic(**kwargs) -> SemanticDecisionResultV2:
    return SemanticDecisionResultV2(
        status=SemanticDecisionStatusV2.MATCHED,
        parser_status=QuestionSemanticParseStatusV2.PARSED,
        metric_name="gmv",
        candidates=("gmv",),
    )


def _no_scope(question: str) -> RequestedScopeResolutionV2:
    return RequestedScopeResolutionV2(
        status=RequestedScopeResolutionStatusV2.NO_EXPLICIT_SCOPE,
    )


def test_fg01_resolves_overall_seed_without_target_grain() -> None:
    mode = resolve_analysis_mode_v2(FG01)
    assert mode.analysis_mode.value == "investigation"

    raw_grain = resolve_result_grain_v2(FG01)
    assert (
        raw_grain.status
        == ResultGrainResolutionStatusV2.UNSPECIFIED
    )
    assert raw_grain.dimensions == ()
    assert raw_grain.evidence == ()

    seed_grain = apply_seed_overall_fallback_v2(
        resolution=raw_grain,
        analysis_mode=mode.analysis_mode.value,
    )

    assert (
        seed_grain.status
        == ResultGrainResolutionStatusV2.RESOLVED
    )
    assert seed_grain.grain_key == "overall"
    assert (
        seed_grain.inference_method
        == "contextual_seed_overall"
    )

    print(
        "PASS: "
        "test_fg01_resolves_overall_seed_without_target_grain"
    )


def test_fg01_unified_planning_reaches_overall_query_plan() -> None:
    result = resolve_analytics_planning_v2(
        question=FG01,
        semantic_resolver=_matched_gmv_semantic,
        requested_scope_resolver=_no_scope,
    )

    assert (
        result.status
        == AnalyticsPlanningStatusV2.PLANNED_SINGLE
    )
    assert result.metric_name == "gmv"
    assert result.grain_resolution is not None
    assert result.grain_resolution.grain_key == "overall"
    assert (
        result.grain_resolution.inference_method
        == "contextual_seed_overall"
    )
    assert len(result.plan_names) == 1

    print(
        "PASS: "
        "test_fg01_unified_planning_reaches_overall_query_plan"
    )


def test_comparison_and_diagnostic_can_use_overall_seed() -> None:
    for question, expected_mode in (
        (
            "2025年8月GMV相比7月表现怎么样？",
            "comparison",
        ),
        (
            "2025年8月GMV为什么下降？",
            "diagnostic",
        ),
    ):
        mode = resolve_analysis_mode_v2(question)
        assert mode.analysis_mode.value == expected_mode

        raw = resolve_result_grain_v2(question)
        assert (
            raw.status
            == ResultGrainResolutionStatusV2.UNSPECIFIED
        )

        resolved = apply_seed_overall_fallback_v2(
            resolution=raw,
            analysis_mode=mode.analysis_mode.value,
        )

        assert resolved.grain_key == "overall"
        assert (
            resolved.inference_method
            == "contextual_seed_overall"
        )

    print(
        "PASS: "
        "test_comparison_and_diagnostic_can_use_overall_seed"
    )


def test_explicit_seed_dimension_is_never_overwritten() -> None:
    question = (
        "按渠道看2025年8月GMV相比7月怎么样？"
        "如果继续调查，最值得先看哪个方向？"
    )

    mode = resolve_analysis_mode_v2(question)
    assert mode.analysis_mode.value == "investigation"

    raw = resolve_result_grain_v2(question)
    assert (
        raw.status
        == ResultGrainResolutionStatusV2.RESOLVED
    )
    assert raw.dimensions == (ResultDimensionV2.CHANNEL,)
    assert raw.grain_key == "channel"

    resolved = apply_seed_overall_fallback_v2(
        resolution=raw,
        analysis_mode=mode.analysis_mode.value,
    )

    assert resolved == raw

    print(
        "PASS: "
        "test_explicit_investigation_dimension_is_never_overwritten"
    )


def test_ambiguous_multidimension_request_is_never_overwritten() -> None:
    raw = resolve_result_grain_v2(
        "各渠道和各地区的GMV"
    )

    assert (
        raw.status
        == ResultGrainResolutionStatusV2.AMBIGUOUS_REQUEST
    )

    resolved = apply_seed_overall_fallback_v2(
        resolution=raw,
        analysis_mode="investigation",
    )

    assert resolved == raw

    print(
        "PASS: "
        "test_ambiguous_multidimension_request_is_never_overwritten"
    )


def test_composition_without_structure_still_requires_grain() -> None:
    question = "GMV的构成怎么样？"

    mode = resolve_analysis_mode_v2(question)
    assert mode.analysis_mode.value == "composition"

    raw = resolve_result_grain_v2(question)
    assert (
        raw.status
        == ResultGrainResolutionStatusV2.UNSPECIFIED
    )

    resolved = apply_seed_overall_fallback_v2(
        resolution=raw,
        analysis_mode=mode.analysis_mode.value,
    )

    assert resolved == raw

    print(
        "PASS: "
        "test_composition_without_structure_still_requires_grain"
    )


def test_legacy_fact_wrapper_keeps_old_contract() -> None:
    raw = resolve_result_grain_v2(
        "看看GMV表现"
    )

    fact = apply_fact_overall_fallback_v2(
        resolution=raw,
        analysis_mode="fact",
    )
    assert fact.grain_key == "overall"
    assert (
        fact.inference_method
        == "contextual_fact_overall"
    )

    investigation = apply_fact_overall_fallback_v2(
        resolution=raw,
        analysis_mode="investigation",
    )
    assert investigation == raw

    print(
        "PASS: "
        "test_legacy_fact_wrapper_keeps_old_contract"
    )


def main() -> None:
    test_fg01_resolves_overall_seed_without_target_grain()
    test_fg01_unified_planning_reaches_overall_query_plan()
    test_comparison_and_diagnostic_can_use_overall_seed()
    test_explicit_seed_dimension_is_never_overwritten()
    test_ambiguous_multidimension_request_is_never_overwritten()
    test_composition_without_structure_still_requires_grain()
    test_legacy_fact_wrapper_keeps_old_contract()


if __name__ == "__main__":
    main()
