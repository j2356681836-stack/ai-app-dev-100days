from __future__ import annotations

from app.semantic_layer.analysis_mode_contract_v2 import (
    AnalysisModeV2,
    analysis_mode_allows_agentic_v2,
)
from app.semantic_layer.analysis_mode_resolution_v2 import (
    resolve_analysis_mode_v2,
)


def _assert_mode(
    question: str,
    expected: AnalysisModeV2,
) -> None:
    result = resolve_analysis_mode_v2(question)

    if result.analysis_mode != expected:
        raise AssertionError(
            f"{question!r}: expected={expected.value}; "
            f"actual={result.analysis_mode.value}; "
            f"signals={result.matched_signals}"
        )


def main() -> None:
    cases = (
        (
            "2025年上海地区GMV是多少？",
            AnalysisModeV2.FACT,
        ),
        (
            "2025年各渠道GMV是多少？",
            AnalysisModeV2.FACT,
        ),
        (
            "上海GMV主要来自哪些渠道？",
            AnalysisModeV2.COMPOSITION,
        ),
        (
            "2025年10月GMV相比9月表现怎么样？",
            AnalysisModeV2.COMPARISON,
        ),
        (
            "2025年10月GMV相比9月为什么下降？",
            AnalysisModeV2.DIAGNOSTIC,
        ),
        (
            "2025年10月GMV相比9月表现怎么样？"
            "如果我要继续调查，最值得先看哪个渠道？",
            AnalysisModeV2.INVESTIGATION,
        ),
        (
            "2025年各品类退款率中，哪个最值得优先关注？",
            AnalysisModeV2.INVESTIGATION,
        ),
        (
            "2025年表现最好的渠道是哪一个？",
            AnalysisModeV2.INVESTIGATION,
        ),
    )

    for question, expected in cases:
        _assert_mode(question, expected)

    for mode in (
        AnalysisModeV2.FACT,
        AnalysisModeV2.COMPOSITION,
        AnalysisModeV2.COMPARISON,
    ):
        if analysis_mode_allows_agentic_v2(mode):
            raise AssertionError(
                f"{mode.value} must not allow Agentic Investigation."
            )

    for mode in (
        AnalysisModeV2.DIAGNOSTIC,
        AnalysisModeV2.INVESTIGATION,
    ):
        if not analysis_mode_allows_agentic_v2(mode):
            raise AssertionError(
                f"{mode.value} must allow Agentic Investigation."
            )

    print("Day93 Analysis Mode Routing Acceptance: PASS")
    print(f"Cases: {len(cases)}")
    print("Agentic Gate: PASS")


if __name__ == "__main__":
    main()
