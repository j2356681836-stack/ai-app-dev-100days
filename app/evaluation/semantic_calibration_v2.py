from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, model_validator

from app.evaluation.generalization_cases_v2 import (
    SEMANTIC_ADVERSARIAL_CASES_V2,
)
from app.evaluation.golden_case_v2_models import MetricDecisionStatus
from app.evaluation.golden_cases_v2 import GOLDEN_CASES_V2
from app.evaluation.semantic_fallback_calibration_cases_v2 import (
    SEMANTIC_FALLBACK_POSITIVE_CASES_V2,
)
from app.semantic_layer.metric_boundary_v2 import (
    BoundaryOutcome,
    evaluate_metric_boundary_v2,
)
from app.semantic_layer.metric_loader_v2 import load_metrics_v2
from app.semantic_layer.metric_semantic_search_v2 import (
    rank_metric_candidates_by_embedding_v2,
)


class CalibrationExpectationType(str, Enum):
    MATCHED = "matched"
    NEEDS_CLARIFICATION = "needs_clarification"
    UNSUPPORTED = "unsupported"
    NEGATIVE_OTHER_METRIC = "negative_other_metric"
    NEGATIVE_UNSUPPORTED_SEMANTICS = "negative_unsupported_semantics"
    NEGATIVE_UNSUPPORTED_SHAPE = "negative_unsupported_shape"
    NEGATIVE_AMBIGUITY = "negative_ambiguity"
    NEGATIVE_UNCLASSIFIED = "negative_unclassified"


class SemanticCalibrationCaseV2(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str
    source: str
    question: str
    expectation_type: CalibrationExpectationType

    expected_metric: str | None = None
    acceptable_candidates: tuple[str, ...] = ()
    source_metric: str | None = None
    result_grain: str | None = None
    relation_reason: str | None = None

    @model_validator(mode="after")
    def validate_expectation(self) -> "SemanticCalibrationCaseV2":
        t = self.expectation_type

        if t == CalibrationExpectationType.MATCHED:
            if not self.expected_metric:
                raise ValueError("matched requires expected_metric.")
            return self

        if t == CalibrationExpectationType.NEEDS_CLARIFICATION:
            if len(self.acceptable_candidates) < 2:
                raise ValueError("clarification requires >=2 candidates.")
            return self

        if t == CalibrationExpectationType.UNSUPPORTED:
            return self

        if not self.source_metric:
            raise ValueError("metadata negative relation requires source_metric.")

        if t == CalibrationExpectationType.NEGATIVE_OTHER_METRIC:
            if not self.expected_metric:
                raise ValueError("negative_other_metric requires expected_metric.")
            if self.expected_metric == self.source_metric:
                raise ValueError("other metric must differ from source metric.")
            return self

        if t == CalibrationExpectationType.NEGATIVE_UNSUPPORTED_SHAPE:
            if self.expected_metric != self.source_metric:
                raise ValueError(
                    "unsupported_shape should still expect source metric."
                )
            if not self.result_grain:
                raise ValueError("unsupported_shape requires result_grain.")
            return self

        if t == CalibrationExpectationType.NEGATIVE_AMBIGUITY:
            if len(self.acceptable_candidates) < 2:
                raise ValueError("negative_ambiguity requires candidates.")
            return self

        return self


def _normalize(text: str) -> str:
    return "".join(text.casefold().split())


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_plan_matrix() -> set[tuple[str, str]]:
    path = (
        _project_root()
        / "metadata"
        / "beauty_bi_v2"
        / "query_plans.yaml"
    )
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return {
        (str(plan["metric"]), str(plan["result_grain"]))
        for plan in data["query_plans"]
    }


def _build_positive_example_map(
    metrics: tuple[dict, ...],
) -> dict[str, tuple[str, ...]]:
    mapping: dict[str, set[str]] = {}
    for metric in metrics:
        for question in metric.get("examples", []):
            mapping.setdefault(
                _normalize(str(question)),
                set(),
            ).add(metric["name"])
    return {
        key: tuple(sorted(values))
        for key, values in mapping.items()
    }


def infer_explicit_result_grain_v2(question: str) -> str | None:
    q = _normalize(question)

    patterns = (
        (
            "region",
            (
                r"(各|按|分|不同|哪个|哪些)(地区|区域)",
                r"(地区|区域)(排名|排行|对比|分别)",
            ),
        ),
        (
            "channel",
            (
                r"(各|按|分|不同|哪个|哪些)(渠道|平台)",
                r"(渠道|平台)(排名|排行|对比|分别)",
            ),
        ),
        (
            "category",
            (
                r"(各|按|分|不同|哪个|哪些)(品类|类目)",
                r"(品类|类目)(排名|排行|对比|分别)",
            ),
        ),
    )

    for grain, grain_patterns in patterns:
        if any(re.search(pattern, q) for pattern in grain_patterns):
            return grain

    return None


def _golden_metric_case_to_calibration(
    *,
    case,
    source: str,
) -> SemanticCalibrationCaseV2:
    expected = case.expected_metric

    if expected.status == MetricDecisionStatus.MATCHED:
        return SemanticCalibrationCaseV2(
            case_id=f"{source}__{case.case_id}",
            source=source,
            question=case.question,
            expectation_type=CalibrationExpectationType.MATCHED,
            expected_metric=expected.metric_name,
        )

    if expected.status == MetricDecisionStatus.NEEDS_CLARIFICATION:
        return SemanticCalibrationCaseV2(
            case_id=f"{source}__{case.case_id}",
            source=source,
            question=case.question,
            expectation_type=CalibrationExpectationType.NEEDS_CLARIFICATION,
            acceptable_candidates=expected.acceptable_candidates,
        )

    return SemanticCalibrationCaseV2(
        case_id=f"{source}__{case.case_id}",
        source=source,
        question=case.question,
        expectation_type=CalibrationExpectationType.UNSUPPORTED,
    )


def _classify_metadata_negative(
    *,
    metric_name: str,
    question: str,
    positive_example_map: dict[str, tuple[str, ...]],
    plan_matrix: set[tuple[str, str]],
) -> SemanticCalibrationCaseV2:
    boundary = evaluate_metric_boundary_v2(question)
    normalized = _normalize(question)

    if boundary.outcome == BoundaryOutcome.UNSUPPORTED:
        return SemanticCalibrationCaseV2(
            case_id="placeholder",
            source="metadata_negative",
            question=question,
            expectation_type=(
                CalibrationExpectationType.NEGATIVE_UNSUPPORTED_SEMANTICS
            ),
            source_metric=metric_name,
            relation_reason=boundary.reason_code,
        )

    if boundary.outcome == BoundaryOutcome.NEEDS_CLARIFICATION:
        return SemanticCalibrationCaseV2(
            case_id="placeholder",
            source="metadata_negative",
            question=question,
            expectation_type=CalibrationExpectationType.NEGATIVE_AMBIGUITY,
            source_metric=metric_name,
            acceptable_candidates=boundary.candidates,
            relation_reason=boundary.reason_code,
        )

    positive_metrics = tuple(
        m
        for m in positive_example_map.get(normalized, ())
        if m != metric_name
    )

    if len(positive_metrics) == 1:
        return SemanticCalibrationCaseV2(
            case_id="placeholder",
            source="metadata_negative",
            question=question,
            expectation_type=CalibrationExpectationType.NEGATIVE_OTHER_METRIC,
            expected_metric=positive_metrics[0],
            source_metric=metric_name,
            relation_reason="exact_positive_example_of_other_metric",
        )

    grain = infer_explicit_result_grain_v2(question)

    if grain is not None and (metric_name, grain) not in plan_matrix:
        return SemanticCalibrationCaseV2(
            case_id="placeholder",
            source="metadata_negative",
            question=question,
            expectation_type=(
                CalibrationExpectationType.NEGATIVE_UNSUPPORTED_SHAPE
            ),
            expected_metric=metric_name,
            source_metric=metric_name,
            result_grain=grain,
            relation_reason="source_metric_has_no_plan_for_explicit_grain",
        )

    return SemanticCalibrationCaseV2(
        case_id="placeholder",
        source="metadata_negative",
        question=question,
        expectation_type=CalibrationExpectationType.NEGATIVE_UNCLASSIFIED,
        source_metric=metric_name,
        relation_reason="insufficient_contract_evidence_for_global_label",
    )


def build_semantic_calibration_cases_v2(
) -> tuple[SemanticCalibrationCaseV2, ...]:
    cases: list[SemanticCalibrationCaseV2] = []
    exact_question_keys: set[str] = set()

    for case in GOLDEN_CASES_V2.cases:
        item = _golden_metric_case_to_calibration(
            case=case,
            source="visible",
        )
        cases.append(item)
        exact_question_keys.add(_normalize(item.question))

    for case in SEMANTIC_ADVERSARIAL_CASES_V2:
        item = _golden_metric_case_to_calibration(
            case=case,
            source="semantic_adversarial",
        )
        cases.append(item)
        exact_question_keys.add(_normalize(item.question))

    for case in SEMANTIC_FALLBACK_POSITIVE_CASES_V2:
        item = SemanticCalibrationCaseV2(
            case_id=f"semantic_fallback__{case.case_id}",
            source="semantic_fallback_positive",
            question=case.question,
            expectation_type=CalibrationExpectationType.MATCHED,
            expected_metric=case.metric_name,
        )
        cases.append(item)
        exact_question_keys.add(_normalize(item.question))

    metrics = load_metrics_v2()
    positive_example_map = _build_positive_example_map(metrics)
    plan_matrix = _load_plan_matrix()

    for metric in metrics:
        metric_name = metric["name"]

        for index, question in enumerate(metric.get("examples", []), start=1):
            normalized = _normalize(str(question))
            if normalized in exact_question_keys:
                continue

            item = SemanticCalibrationCaseV2(
                case_id=f"metadata_example__{metric_name}__{index:02d}",
                source="metadata_example",
                question=str(question),
                expectation_type=CalibrationExpectationType.MATCHED,
                expected_metric=metric_name,
            )
            cases.append(item)
            exact_question_keys.add(normalized)

        for index, question in enumerate(
            metric.get("negative_examples", []),
            start=1,
        ):
            relation = _classify_metadata_negative(
                metric_name=metric_name,
                question=str(question),
                positive_example_map=positive_example_map,
                plan_matrix=plan_matrix,
            )
            cases.append(
                relation.model_copy(
                    update={
                        "case_id": (
                            f"metadata_negative__{metric_name}__{index:02d}"
                        )
                    }
                )
            )

    ids = [case.case_id for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("Semantic Calibration case_id values must be unique.")

    return tuple(cases)


SEMANTIC_CALIBRATION_CASES_V2 = build_semantic_calibration_cases_v2()


def _candidate_at(candidates: list[dict[str, Any]], index: int):
    return None if len(candidates) <= index else candidates[index]


def evaluate_semantic_calibration_case_v2(
    case: SemanticCalibrationCaseV2,
    *,
    top_k: int = 6,
) -> dict[str, Any]:
    boundary = evaluate_metric_boundary_v2(case.question)

    retrieval = rank_metric_candidates_by_embedding_v2(
        case.question,
        top_k=top_k,
    )

    candidates = retrieval["candidates"]
    top1 = _candidate_at(candidates, 0)
    top2 = _candidate_at(candidates, 1)

    top1_score = None if top1 is None else top1["score"]
    top2_score = None if top2 is None else top2["score"]
    gap = (
        None
        if top1_score is None or top2_score is None
        else top1_score - top2_score
    )

    t = case.expectation_type

    if t in {
        CalibrationExpectationType.MATCHED,
        CalibrationExpectationType.NEGATIVE_OTHER_METRIC,
        CalibrationExpectationType.NEGATIVE_UNSUPPORTED_SHAPE,
    }:
        top1_correct = (
            top1 is not None
            and top1["name"] == case.expected_metric
        )
    elif t in {
        CalibrationExpectationType.NEEDS_CLARIFICATION,
        CalibrationExpectationType.NEGATIVE_AMBIGUITY,
    }:
        top1_correct = (
            top1 is not None
            and top1["name"] in case.acceptable_candidates
        )
    else:
        top1_correct = None

    if t == CalibrationExpectationType.MATCHED:
        expected_boundary = BoundaryOutcome.CONTINUE.value
    elif t == CalibrationExpectationType.NEEDS_CLARIFICATION:
        expected_boundary = BoundaryOutcome.NEEDS_CLARIFICATION.value
    elif t == CalibrationExpectationType.UNSUPPORTED:
        expected_boundary = BoundaryOutcome.UNSUPPORTED.value
    elif t == CalibrationExpectationType.NEGATIVE_UNSUPPORTED_SEMANTICS:
        expected_boundary = BoundaryOutcome.UNSUPPORTED.value
    elif t == CalibrationExpectationType.NEGATIVE_AMBIGUITY:
        expected_boundary = BoundaryOutcome.NEEDS_CLARIFICATION.value
    else:
        expected_boundary = None

    boundary_correct = (
        None
        if expected_boundary is None
        else boundary.outcome.value == expected_boundary
    )

    source_metric_top1 = (
        None
        if case.source_metric is None or top1 is None
        else top1["name"] == case.source_metric
    )

    return {
        "case_id": case.case_id,
        "source": case.source,
        "question": case.question,
        "expectation": case.model_dump(mode="json"),
        "boundary": boundary.model_dump(mode="json"),
        "boundary_expected_outcome": expected_boundary,
        "boundary_correct": boundary_correct,
        "retrieval_status": retrieval["retrieval_status"],
        "top1_metric": None if top1 is None else top1["name"],
        "top1_score": top1_score,
        "top2_metric": None if top2 is None else top2["name"],
        "top2_score": top2_score,
        "gap": gap,
        "top1_correct": top1_correct,
        "source_metric_top1": source_metric_top1,
        "candidates": candidates,
    }


def run_semantic_calibration_v2(
    *,
    top_k: int = 6,
) -> list[dict[str, Any]]:
    return [
        evaluate_semantic_calibration_case_v2(case, top_k=top_k)
        for case in SEMANTIC_CALIBRATION_CASES_V2
    ]


def build_calibration_summary_v2(
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    source_counts = Counter(item["source"] for item in results)
    expectation_counts = Counter(
        item["expectation"]["expectation_type"]
        for item in results
    )

    scored_top1 = [
        item for item in results
        if item["top1_correct"] is not None
    ]
    correct_top1 = sum(
        1 for item in scored_top1
        if item["top1_correct"]
    )

    boundary_scored = [
        item for item in results
        if item["boundary_correct"] is not None
    ]
    boundary_correct = sum(
        1 for item in boundary_scored
        if item["boundary_correct"]
    )

    fallback = [
        item
        for item in results
        if item["source"] == "semantic_fallback_positive"
    ]
    fallback_correct = sum(
        1 for item in fallback
        if item["top1_correct"]
    )

    unclassified = [
        item
        for item in results
        if (
            item["expectation"]["expectation_type"]
            == CalibrationExpectationType.NEGATIVE_UNCLASSIFIED.value
        )
    ]
    unclassified_source_top1 = sum(
        1
        for item in unclassified
        if item["source_metric_top1"] is True
    )

    return {
        "total": len(results),
        "source_counts": dict(sorted(source_counts.items())),
        "expectation_counts": dict(sorted(expectation_counts.items())),
        "raw_top1_labeled": {
            "total": len(scored_top1),
            "correct": correct_top1,
            "accuracy": (
                None
                if not scored_top1
                else round(correct_top1 / len(scored_top1) * 100, 2)
            ),
        },
        "semantic_fallback_positive": {
            "total": len(fallback),
            "correct": fallback_correct,
            "accuracy": (
                None
                if not fallback
                else round(fallback_correct / len(fallback) * 100, 2)
            ),
        },
        "boundary": {
            "total": len(boundary_scored),
            "correct": boundary_correct,
            "accuracy": (
                None
                if not boundary_scored
                else round(boundary_correct / len(boundary_scored) * 100, 2)
            ),
        },
        "negative_unclassified_diagnostic": {
            "total": len(unclassified),
            "source_metric_top1": unclassified_source_top1,
        },
        "threshold_policy": None,
        "gap_policy": None,
    }


def save_semantic_calibration_report_v2(
    results: list[dict[str, Any]],
) -> Path:
    output_dir = Path("docs/evaluation")
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"semantic_calibration_v2_{timestamp}.json"

    payload = {
        "timestamp": timestamp,
        "evaluation": "day74_v2_semantic_calibration_gate5c1",
        "summary": build_calibration_summary_v2(results),
        "results": results,
    }

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    return output_path


def print_calibration_summary_v2(
    results: list[dict[str, Any]],
) -> None:
    summary = build_calibration_summary_v2(results)

    print("=" * 80)
    print("Semantic Calibration V2 Gate 5C.1 Summary")
    print("Total:", summary["total"])
    print("Source Counts:", summary["source_counts"])
    print("Expectation Counts:", summary["expectation_counts"])
    print("Raw Top1 Labeled:", summary["raw_top1_labeled"])
    print(
        "Semantic Fallback Positive:",
        summary["semantic_fallback_positive"],
    )
    print("Boundary:", summary["boundary"])
    print(
        "Negative Unclassified Diagnostic:",
        summary["negative_unclassified_diagnostic"],
    )
    print("Threshold Policy:", summary["threshold_policy"])
    print("Gap Policy:", summary["gap_policy"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--top-k", type=int, default=6)
    args = parser.parse_args()

    if args.top_k < 2:
        raise ValueError(
            "Calibration top_k must be >= 2 because Top1/Top2 gap is required."
        )

    results = run_semantic_calibration_v2(top_k=args.top_k)
    print_calibration_summary_v2(results)
    output_path = save_semantic_calibration_report_v2(results)
    print("Saved to:", output_path)


if __name__ == "__main__":
    main()
