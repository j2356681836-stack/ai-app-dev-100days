from __future__ import annotations

import re
from enum import Enum

from pydantic import BaseModel, ConfigDict, model_validator


class ResultDimensionV2(str, Enum):
    CHANNEL = "channel"
    REGION = "region"
    CATEGORY = "category"


class ResultGrainResolutionStatusV2(str, Enum):
    RESOLVED = "resolved"
    UNSPECIFIED = "unspecified"
    MULTI_PLAN_REQUEST = "multi_plan_request"
    AMBIGUOUS_REQUEST = "ambiguous_request"


class ResultGrainEvidenceV2(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    dimension: ResultDimensionV2
    matched_text: str
    start: int
    end: int
    rule: str


_DIMENSION_ORDER = {
    ResultDimensionV2.CHANNEL: 0,
    ResultDimensionV2.REGION: 1,
    ResultDimensionV2.CATEGORY: 2,
}


def canonical_dimensions_v2(
    dimensions: tuple[ResultDimensionV2, ...],
) -> tuple[ResultDimensionV2, ...]:
    return tuple(
        sorted(
            set(dimensions),
            key=lambda item: _DIMENSION_ORDER[item],
        )
    )


def grain_key_from_dimensions_v2(
    dimensions: tuple[ResultDimensionV2, ...],
) -> str:
    canonical = canonical_dimensions_v2(
        dimensions
    )

    if not canonical:
        return "overall"

    return "_".join(
        item.value
        for item in canonical
    )


class ResultGrainResolutionV2(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    status: ResultGrainResolutionStatusV2
    dimensions: tuple[ResultDimensionV2, ...] = ()
    grain_key: str | None = None
    evidence: tuple[ResultGrainEvidenceV2, ...] = ()
    inference_method: str | None = None
    error: str | None = None

    @model_validator(mode="after")
    def validate_resolution(
        self,
    ) -> "ResultGrainResolutionV2":
        canonical = canonical_dimensions_v2(
            self.dimensions
        )

        if canonical != self.dimensions:
            raise ValueError(
                "dimensions must be unique and canonical."
            )

        if (
            self.status
            == ResultGrainResolutionStatusV2.RESOLVED
        ):
            expected_key = grain_key_from_dimensions_v2(
                self.dimensions
            )

            if self.grain_key != expected_key:
                raise ValueError(
                    "RESOLVED grain_key must match dimensions."
                )

            if self.inference_method not in {
                "explicit_overall",
                "implicit_overall",
                "explicit_single",
                "explicit_composite",
            }:
                raise ValueError(
                    "RESOLVED result requires a supported "
                    "inference_method."
                )

            return self

        if self.grain_key is not None:
            raise ValueError(
                "Non-RESOLVED result must not expose grain_key."
            )

        if (
            self.status
            in {
                ResultGrainResolutionStatusV2
                .MULTI_PLAN_REQUEST,
                ResultGrainResolutionStatusV2
                .AMBIGUOUS_REQUEST,
            }
            and len(self.dimensions) < 2
        ):
            raise ValueError(
                "Multi-dimensional non-resolved status "
                "requires at least two dimensions."
            )

        if (
            self.status
            == ResultGrainResolutionStatusV2.UNSPECIFIED
            and self.dimensions
        ):
            raise ValueError(
                "UNSPECIFIED result must not expose dimensions."
            )

        return self


_EXPLICIT_DIMENSION_PATTERNS: dict[
    ResultDimensionV2,
    tuple[tuple[str, str], ...],
] = {
    ResultDimensionV2.CHANNEL: (
        (
            r"(?:按|分)(?:不同|各|每个)?(?:渠道|平台)",
            "grouped_channel_expression",
        ),
        (
            r"(?:各|每个|不同)(?:渠道|平台)",
            "grouped_channel_expression",
        ),
        (
            r"(?:渠道|平台)(?:维度|分布|对比|排行|排名)",
            "channel_analysis_expression",
        ),
    ),
    ResultDimensionV2.REGION: (
        (
            r"(?:按|分)(?:不同|各|每个)?(?:地区|区域)",
            "grouped_region_expression",
        ),
        (
            r"(?:各|每个|不同)(?:地区|区域)",
            "grouped_region_expression",
        ),
        (
            r"(?:地区|区域)(?:维度|分布|对比|排行|排名)",
            "region_analysis_expression",
        ),
    ),
    ResultDimensionV2.CATEGORY: (
        (
            r"(?:按|分)(?:不同|各|每个)?(?:品类|类别)",
            "grouped_category_expression",
        ),
        (
            r"(?:各|每个|不同)(?:品类|类别)",
            "grouped_category_expression",
        ),
        (
            r"(?:品类|类别)(?:维度|分布|对比|排行|排名)",
            "category_analysis_expression",
        ),
    ),
}


_BARE_DIMENSION_PATTERNS = {
    ResultDimensionV2.CHANNEL: r"渠道|平台",
    ResultDimensionV2.REGION: r"地区|区域",
    ResultDimensionV2.CATEGORY: r"品类|类别",
}


_EXPLICIT_OVERALL_PATTERN = re.compile(
    r"整体|总体|全局|全盘|总览"
)


_MULTI_PLAN_MARKER = re.compile(
    r"分别|各自|分开|两张|两份|两个结果"
)


_COMPOSITE_MARKER = re.compile(
    (
        r"交叉|组合|联合|共同|二维|多维|维度组合"
        r"|按.{0,12}(?:和|与|、).{0,12}"
        r"(?:看|分析|统计|汇总|分组)"
    )
)


_SCALAR_REQUEST_PATTERN = re.compile(
    (
        r"是多少"
        r"|有多少"
        r"|多少(?:元|人|位|个|笔|单|件|倍|%|％)?"
        r"|总共"
        r"|一共"
        r"|合计"
        r"|总计"
    )
)


def _collect_explicit_dimension_evidence_v2(
    text: str,
) -> tuple[ResultGrainEvidenceV2, ...]:
    evidence: list[
        ResultGrainEvidenceV2
    ] = []

    for dimension, rules in (
        _EXPLICIT_DIMENSION_PATTERNS.items()
    ):
        for pattern, rule in rules:
            for match in re.finditer(
                pattern,
                text,
                flags=re.IGNORECASE,
            ):
                evidence.append(
                    ResultGrainEvidenceV2(
                        dimension=dimension,
                        matched_text=match.group(0),
                        start=match.start(),
                        end=match.end(),
                        rule=rule,
                    )
                )

    return _deduplicate_evidence_v2(
        evidence
    )


def _collect_bare_dimension_evidence_v2(
    text: str,
) -> tuple[ResultGrainEvidenceV2, ...]:
    evidence: list[
        ResultGrainEvidenceV2
    ] = []

    for dimension, pattern in (
        _BARE_DIMENSION_PATTERNS.items()
    ):
        for match in re.finditer(
            pattern,
            text,
            flags=re.IGNORECASE,
        ):
            evidence.append(
                ResultGrainEvidenceV2(
                    dimension=dimension,
                    matched_text=match.group(0),
                    start=match.start(),
                    end=match.end(),
                    rule="multi_dimension_token",
                )
            )

    return _deduplicate_evidence_v2(
        evidence
    )


def _deduplicate_evidence_v2(
    evidence: list[ResultGrainEvidenceV2],
) -> tuple[ResultGrainEvidenceV2, ...]:
    unique: dict[
        tuple[ResultDimensionV2, int, int],
        ResultGrainEvidenceV2,
    ] = {}

    for item in evidence:
        key = (
            item.dimension,
            item.start,
            item.end,
        )
        unique.setdefault(
            key,
            item,
        )

    return tuple(
        sorted(
            unique.values(),
            key=lambda item: (
                item.start,
                item.end,
                _DIMENSION_ORDER[
                    item.dimension
                ],
            ),
        )
    )


def _dimensions_from_evidence_v2(
    evidence: tuple[
        ResultGrainEvidenceV2,
        ...,
    ],
) -> tuple[ResultDimensionV2, ...]:
    return canonical_dimensions_v2(
        tuple(
            item.dimension
            for item in evidence
        )
    )


def resolve_result_grain_v2(
    question: str,
) -> ResultGrainResolutionV2:
    """
    Resolve the requested output shape.

    Distinctions:
    - single grain: one grouped result;
    - composite grain: one result grouped by multiple dimensions;
    - multi-plan request: separate result sets for each dimension;
    - ambiguous request: multiple dimensions without enough wording
      to decide composite versus separate outputs.

    This component does not choose a Metric, apply Row Scope,
    parse a time window, or generate SQL.
    """
    text = str(
        question
    ).strip()

    bare_evidence = (
        _collect_bare_dimension_evidence_v2(
            text
        )
    )
    bare_dimensions = (
        _dimensions_from_evidence_v2(
            bare_evidence
        )
    )

    if len(bare_dimensions) >= 2:
        if _MULTI_PLAN_MARKER.search(
            text
        ):
            return ResultGrainResolutionV2(
                status=(
                    ResultGrainResolutionStatusV2
                    .MULTI_PLAN_REQUEST
                ),
                dimensions=bare_dimensions,
                grain_key=None,
                evidence=bare_evidence,
                inference_method=(
                    "multi_plan_explicit"
                ),
                error=None,
            )

        if _COMPOSITE_MARKER.search(
            text
        ):
            return ResultGrainResolutionV2(
                status=(
                    ResultGrainResolutionStatusV2
                    .RESOLVED
                ),
                dimensions=bare_dimensions,
                grain_key=(
                    grain_key_from_dimensions_v2(
                        bare_dimensions
                    )
                ),
                evidence=bare_evidence,
                inference_method=(
                    "explicit_composite"
                ),
                error=None,
            )

        return ResultGrainResolutionV2(
            status=(
                ResultGrainResolutionStatusV2
                .AMBIGUOUS_REQUEST
            ),
            dimensions=bare_dimensions,
            grain_key=None,
            evidence=bare_evidence,
            inference_method=None,
            error=(
                "Multiple dimensions are present, but the "
                "question does not say whether to cross-group "
                "them or return separate result sets."
            ),
        )

    explicit_evidence = (
        _collect_explicit_dimension_evidence_v2(
            text
        )
    )
    explicit_dimensions = (
        _dimensions_from_evidence_v2(
            explicit_evidence
        )
    )

    if len(explicit_dimensions) == 1:
        return ResultGrainResolutionV2(
            status=(
                ResultGrainResolutionStatusV2
                .RESOLVED
            ),
            dimensions=explicit_dimensions,
            grain_key=(
                grain_key_from_dimensions_v2(
                    explicit_dimensions
                )
            ),
            evidence=explicit_evidence,
            inference_method="explicit_single",
            error=None,
        )

    if _EXPLICIT_OVERALL_PATTERN.search(
        text
    ):
        return ResultGrainResolutionV2(
            status=(
                ResultGrainResolutionStatusV2
                .RESOLVED
            ),
            dimensions=(),
            grain_key="overall",
            evidence=(),
            inference_method="explicit_overall",
            error=None,
        )

    if _SCALAR_REQUEST_PATTERN.search(
        text
    ):
        return ResultGrainResolutionV2(
            status=(
                ResultGrainResolutionStatusV2
                .RESOLVED
            ),
            dimensions=(),
            grain_key="overall",
            evidence=(),
            inference_method="implicit_overall",
            error=None,
        )

    return ResultGrainResolutionV2(
        status=(
            ResultGrainResolutionStatusV2
            .UNSPECIFIED
        ),
        dimensions=(),
        grain_key=None,
        evidence=(),
        inference_method=None,
        error=(
            "Question does not safely identify "
            "a result grain."
        ),
    )


if __name__ == "__main__":
    samples = (
        "本月GMV是多少？",
        "各渠道GMV是多少？",
        "按地区看GMV",
        "每个品类的GMV",
        "按渠道和地区交叉看GMV",
        "按渠道和地区看GMV",
        "分别按渠道和地区看GMV",
        "各渠道和各地区的GMV",
        "看看GMV表现",
    )

    for sample in samples:
        print("=" * 80)
        print(sample)
        print(
            resolve_result_grain_v2(
                sample
            ).model_dump(
                mode="json"
            )
        )
