from app.semantic_layer.analysis_mode_resolution_v2 import (
    AnalysisModeV2,
    resolve_analysis_mode_v2,
)
from app.semantic_layer.result_grain_resolver_v2 import (
    ResultGrainResolutionStatusV2,
    apply_fact_overall_fallback_v2,
    resolve_result_grain_v2,
)


FACT_PARAPHRASES = (
    "2025年上海GMV是多少？",
    "2025年上海GMV如何？",
    "2025年上海GMV表现如何？",
    "2025年上海GMV情况怎么样？",
    "2025年上海GMV大概是什么水平？",
    "看看2025年上海GMV",
)


def _planning_grain(question: str):
    mode = resolve_analysis_mode_v2(question)
    raw = resolve_result_grain_v2(question)

    return (
        mode,
        raw,
        apply_fact_overall_fallback_v2(
            resolution=raw,
            analysis_mode=mode.analysis_mode.value,
        ),
    )


def test_fact_paraphrases_resolve_overall() -> None:
    for question in FACT_PARAPHRASES:
        mode, _, final = _planning_grain(question)

        assert mode.analysis_mode == AnalysisModeV2.FACT
        assert (
            final.status
            == ResultGrainResolutionStatusV2.RESOLVED
        )
        assert final.grain_key == "overall"
        assert final.dimensions == ()

    # 第一条本来就能通过 scalar signal；
    # 其余表达需要 Context Fallback。
    first = _planning_grain(FACT_PARAPHRASES[0])[2]
    assert first.inference_method == "implicit_overall"

    for question in FACT_PARAPHRASES[1:]:
        final = _planning_grain(question)[2]
        assert (
            final.inference_method
            == "contextual_fact_overall"
        )


def test_explicit_dimension_is_never_overwritten() -> None:
    mode, raw, final = _planning_grain(
        "2025年上海各渠道GMV如何？"
    )

    assert mode.analysis_mode == AnalysisModeV2.FACT
    assert raw.status == ResultGrainResolutionStatusV2.RESOLVED
    assert raw.grain_key == "channel"
    assert final == raw


def test_non_fact_modes_do_not_receive_overall_fallback() -> None:
    cases = (
        "2025年上海GMV主要来自哪些渠道？",
        "2025年10月GMV相比9月怎么样？",
        "2025年上海GMV为什么下降？",
        "2025年上海哪个渠道最值得优先关注？",
    )

    for question in cases:
        mode = resolve_analysis_mode_v2(question)
        raw = resolve_result_grain_v2(question)
        final = apply_fact_overall_fallback_v2(
            resolution=raw,
            analysis_mode=mode.analysis_mode.value,
        )

        assert mode.analysis_mode != AnalysisModeV2.FACT

        if (
            raw.status
            == ResultGrainResolutionStatusV2.UNSPECIFIED
        ):
            assert final.status == raw.status
            assert final.grain_key is None
        else:
            assert final == raw


def test_ambiguous_or_multi_plan_is_never_overwritten() -> None:
    cases = (
        "各渠道和各地区的GMV",
        "分别按渠道和地区看GMV",
    )

    for question in cases:
        mode = resolve_analysis_mode_v2(question)
        raw = resolve_result_grain_v2(question)
        final = apply_fact_overall_fallback_v2(
            resolution=raw,
            analysis_mode=mode.analysis_mode.value,
        )

        assert final == raw
        assert raw.status in {
            ResultGrainResolutionStatusV2.AMBIGUOUS_REQUEST,
            ResultGrainResolutionStatusV2.MULTI_PLAN_REQUEST,
        }


def main() -> None:
    test_fact_paraphrases_resolve_overall()
    print(
        "PASS: FACT paraphrases 稳定落到 Overall，"
        "不再依赖“多少”字面词"
    )

    test_explicit_dimension_is_never_overwritten()
    print("PASS: 显式 Channel Grain 不会被 Overall fallback 覆盖")

    test_non_fact_modes_do_not_receive_overall_fallback()
    print(
        "PASS: Composition / Comparison / Diagnostic / "
        "Investigation 不会误用 FACT fallback"
    )

    test_ambiguous_or_multi_plan_is_never_overwritten()
    print("PASS: Ambiguous / Multi-plan 请求保持原 fail-safe 语义")

    print("=" * 72)
    print("Semantic Generalization Acceptance V2 passed.")


if __name__ == "__main__":
    main()
