from __future__ import annotations

from app.delivery.decision_console_runtime_v2 import (
    _resolve_day94_gmv_comparison_seed_v2,
)
from app.semantic_layer.analysis_mode_contract_v2 import (
    AnalysisModeV2,
)
from app.semantic_layer.comparison_intent_semantic_v2 import (
    ComparisonIntentSemanticStatusV2,
    resolve_gmv_adjacent_month_comparison_intent_v2,
)


def _fake_llm(
    *,
    analysis_mode: str,
    current_year: int,
    current_month: int,
    reference_year: int,
    reference_month: int,
):
    payload = (
        "{"
        '"metric_name":"gmv",'
        f'"analysis_mode":"{analysis_mode}",'
        f'"current_year":{current_year},'
        f'"current_month":{current_month},'
        f'"reference_year":{reference_year},'
        f'"reference_month":{reference_month}'
        "}"
    )

    def call(**kwargs) -> str:
        return payload

    return call


def test_llm_normalizes_reference_before_comparison_word() -> None:
    question = "2025年10月GMV和9月相比如何？"

    result = resolve_gmv_adjacent_month_comparison_intent_v2(
        question,
        llm_call=_fake_llm(
            analysis_mode="comparison",
            current_year=2025,
            current_month=10,
            reference_year=2025,
            reference_month=9,
        ),
    )

    assert result.status == ComparisonIntentSemanticStatusV2.READY
    assert result.analysis_mode == AnalysisModeV2.COMPARISON
    assert str(result.current_anchor_date) == "2025-10-31"
    assert str(result.reference_anchor_date) == "2025-09-30"


def test_llm_normalizes_semantic_investigation_wording() -> None:
    question = (
        "2025年10月GMV和9月相比如何？"
        "如果有变化，应该看什么方向？"
    )

    result = resolve_gmv_adjacent_month_comparison_intent_v2(
        question,
        llm_call=_fake_llm(
            analysis_mode="investigation",
            current_year=2025,
            current_month=10,
            reference_year=2025,
            reference_month=9,
        ),
    )

    assert result.status == ComparisonIntentSemanticStatusV2.READY
    assert result.analysis_mode == AnalysisModeV2.INVESTIGATION


def test_hybrid_resolver_preserves_day93_deterministic_fast_path() -> None:
    question = (
        "2025年8月GMV相比7月表现怎么样？"
        "如果我要继续调查，最值得优先看哪个方向？"
    )

    def must_not_call_llm(**kwargs) -> str:
        raise AssertionError(
            "High-confidence Day93 fast path should not call LLM."
        )

    result = _resolve_day94_gmv_comparison_seed_v2(
        question,
        comparison_intent_llm_call=must_not_call_llm,
    )

    assert result is not None

    (
        current_anchor,
        reference_anchor,
        _scope,
        analysis_mode,
        route_source,
    ) = result

    assert str(current_anchor) == "2025-08-31"
    assert str(reference_anchor) == "2025-07-31"
    assert analysis_mode == AnalysisModeV2.INVESTIGATION
    assert route_source == "day93_deterministic_fast_path"


def test_hybrid_resolver_recovers_reversed_word_order() -> None:
    question = "2025年10月GMV和9月相比如何？"

    result = _resolve_day94_gmv_comparison_seed_v2(
        question,
        comparison_intent_llm_call=_fake_llm(
            analysis_mode="comparison",
            current_year=2025,
            current_month=10,
            reference_year=2025,
            reference_month=9,
        ),
    )

    assert result is not None
    assert str(result[0]) == "2025-10-31"
    assert str(result[1]) == "2025-09-30"
    assert result[3] == AnalysisModeV2.COMPARISON
    assert "llm_semantic_normalization" in result[4]


def test_hybrid_resolver_recovers_investigation_semantics() -> None:
    question = (
        "2025年10月GMV和9月相比如何？"
        "如果有变化，应该看什么方向？"
    )

    result = _resolve_day94_gmv_comparison_seed_v2(
        question,
        comparison_intent_llm_call=_fake_llm(
            analysis_mode="investigation",
            current_year=2025,
            current_month=10,
            reference_year=2025,
            reference_month=9,
        ),
    )

    assert result is not None
    assert result[3] == AnalysisModeV2.INVESTIGATION


def test_non_adjacent_llm_claim_is_rejected() -> None:
    question = "2025年10月GMV和8月相比如何？"

    result = resolve_gmv_adjacent_month_comparison_intent_v2(
        question,
        llm_call=_fake_llm(
            analysis_mode="comparison",
            current_year=2025,
            current_month=10,
            reference_year=2025,
            reference_month=8,
        ),
    )

    assert (
        result.status
        == ComparisonIntentSemanticStatusV2.VALIDATION_FAILED
    )


def test_llm_cannot_invent_current_month() -> None:
    question = "2025年10月GMV和9月相比如何？"

    result = resolve_gmv_adjacent_month_comparison_intent_v2(
        question,
        llm_call=_fake_llm(
            analysis_mode="comparison",
            current_year=2025,
            current_month=11,
            reference_year=2025,
            reference_month=10,
        ),
    )

    assert (
        result.status
        == ComparisonIntentSemanticStatusV2.VALIDATION_FAILED
    )


def test_llm_failure_does_not_break_clear_pure_comparison_fallback() -> None:
    question = "2025年10月GMV相比9月如何？"

    def broken_llm(**kwargs) -> str:
        raise RuntimeError("synthetic llm failure")

    result = _resolve_day94_gmv_comparison_seed_v2(
        question,
        comparison_intent_llm_call=broken_llm,
    )

    assert result is not None
    assert str(result[0]) == "2025-10-31"
    assert str(result[1]) == "2025-09-30"
    assert result[3] == AnalysisModeV2.COMPARISON
    assert (
        result[4]
        == "day94_deterministic_comparison_fallback"
    )


TESTS = (
    test_llm_normalizes_reference_before_comparison_word,
    test_llm_normalizes_semantic_investigation_wording,
    test_hybrid_resolver_preserves_day93_deterministic_fast_path,
    test_hybrid_resolver_recovers_reversed_word_order,
    test_hybrid_resolver_recovers_investigation_semantics,
    test_non_adjacent_llm_claim_is_rejected,
    test_llm_cannot_invent_current_month,
    test_llm_failure_does_not_break_clear_pure_comparison_fallback,
)


def run_acceptance() -> None:
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

    print("Day94 Hybrid Comparison Semantic Acceptance Summary")
    print(f"Total: {len(TESTS)}")
    print(f"Passed: {passed}")
    print(f"Failed: {len(failures)}")

    for failure in failures:
        print(f"- {failure}")

    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    run_acceptance()
