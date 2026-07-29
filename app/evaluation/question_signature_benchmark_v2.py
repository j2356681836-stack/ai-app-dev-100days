from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from app.evaluation.semantic_fallback_calibration_cases_v2 import (
    SEMANTIC_FALLBACK_POSITIVE_CASES_V2,
)
from app.semantic_layer.metric_signature_v2 import (
    MetricSemanticSignatureV2,
    SignatureOperator,
    get_metric_signature_v2,
    metric_signature_catalog_fingerprint_v2,
)
from app.semantic_layer.question_signature_v2 import (
    QuestionOperator,
    extract_question_semantic_signature_v2,
)


def _expected_question_operator(
    metric_signature: MetricSemanticSignatureV2,
) -> QuestionOperator:
    if metric_signature.operator == SignatureOperator.SUM:
        return QuestionOperator.SUM

    if metric_signature.operator in {
        SignatureOperator.DISTINCT_COUNT,
        SignatureOperator.QUALIFIED_COUNT,
    }:
        return QuestionOperator.COUNT

    if metric_signature.operator == SignatureOperator.DIVIDE:
        return QuestionOperator.DIVIDE

    raise ValueError(
        f"Unsupported Metric Signature operator: "
        f"{metric_signature.operator}"
    )


def evaluate_question_signature_case_v2(
    case,
) -> dict[str, Any]:
    expected_metric_signature = (
        get_metric_signature_v2(
            case.metric_name
        )
    )

    if expected_metric_signature is None:
        raise ValueError(
            f"Missing Metric Signature: {case.metric_name}"
        )

    actual = (
        extract_question_semantic_signature_v2(
            case.question
        )
    )

    expected_operator = (
        _expected_question_operator(
            expected_metric_signature
        )
    )

    operator_correct = (
        actual.operator
        == expected_operator
    )

    left_correct = (
        actual.left_operand
        == expected_metric_signature.left_operand
    )

    if (
        expected_metric_signature.operator
        == SignatureOperator.DIVIDE
    ):
        right_applicable = True
        right_correct = (
            actual.right_operand
            == expected_metric_signature.right_operand
        )
    else:
        right_applicable = False
        right_correct = (
            actual.right_operand
            is None
        )

    core_exact = (
        operator_correct
        and left_correct
        and right_correct
    )

    false_core_fields: list[str] = []

    if (
        actual.operator is not None
        and not operator_correct
    ):
        false_core_fields.append(
            "operator"
        )

    if (
        actual.left_operand is not None
        and not left_correct
    ):
        false_core_fields.append(
            "left_operand"
        )

    if (
        actual.right_operand is not None
        and not right_correct
    ):
        false_core_fields.append(
            "right_operand"
        )

    expected_qualifiers = set(
        expected_metric_signature.qualifiers
    )

    qualifier_correct = sum(
        1
        for qualifier in actual.qualifiers
        if qualifier
        in expected_qualifiers
    )

    qualifier_false = [
        qualifier.value
        for qualifier in actual.qualifiers
        if qualifier
        not in expected_qualifiers
    ]

    partition_evaluable = (
        actual.intrinsic_partition
        is not None
    )

    partition_correct = (
        not partition_evaluable
        or actual.intrinsic_partition
        == expected_metric_signature.intrinsic_partition
    )

    return {
        "case_id": case.case_id,
        "metric_name": case.metric_name,
        "question": case.question,
        "expected_core": {
            "operator": expected_operator.value,
            "left_operand": (
                expected_metric_signature.left_operand.value
            ),
            "right_operand": (
                None
                if expected_metric_signature.right_operand is None
                else expected_metric_signature.right_operand.value
            ),
        },
        "actual_signature": actual.model_dump(
            mode="json"
        ),
        "operator_correct": operator_correct,
        "left_correct": left_correct,
        "right_applicable": right_applicable,
        "right_correct": right_correct,
        "core_exact": core_exact,
        "false_core_fields": false_core_fields,
        "qualifier_extracted": len(
            actual.qualifiers
        ),
        "qualifier_correct": qualifier_correct,
        "qualifier_false": qualifier_false,
        "partition_evaluable": partition_evaluable,
        "partition_correct": partition_correct,
    }


def _accuracy(
    correct: int,
    total: int,
) -> dict[str, Any]:
    return {
        "correct": correct,
        "total": total,
        "accuracy": (
            None
            if total == 0
            else round(
                correct
                / total
                * 100,
                2,
            )
        ),
    }


def run_question_signature_benchmark_v2(
) -> dict[str, Any]:
    results = [
        evaluate_question_signature_case_v2(
            case
        )
        for case in (
            SEMANTIC_FALLBACK_POSITIVE_CASES_V2
        )
    ]

    total = len(
        results
    )

    divide_results = [
        item
        for item in results
        if item[
            "right_applicable"
        ]
    ]

    qualifier_extracted = sum(
        item[
            "qualifier_extracted"
        ]
        for item in results
    )

    qualifier_correct = sum(
        item[
            "qualifier_correct"
        ]
        for item in results
    )

    partition_rows = [
        item
        for item in results
        if item[
            "partition_evaluable"
        ]
    ]

    false_core_cases = [
        item[
            "case_id"
        ]
        for item in results
        if item[
            "false_core_fields"
        ]
    ]

    by_metric: dict[
        str,
        list[dict[str, Any]],
    ] = defaultdict(list)

    for item in results:
        by_metric[
            item["metric_name"]
        ].append(
            item
        )

    per_metric = {
        metric_name: {
            "total": len(rows),
            "core_exact": sum(
                1
                for row in rows
                if row[
                    "core_exact"
                ]
            ),
            "failed_case_ids": [
                row[
                    "case_id"
                ]
                for row in rows
                if not row[
                    "core_exact"
                ]
            ],
        }
        for metric_name, rows in sorted(
            by_metric.items()
        )
    }

    return {
        "evaluation": (
            "day74_gate5eb_question_semantic_signature"
        ),
        "dataset_role": (
            "development_calibration_not_generalization"
        ),
        "case_count": total,
        "metric_signature_catalog_fingerprint": (
            metric_signature_catalog_fingerprint_v2()
        ),
        "summary": {
            "core_exact": _accuracy(
                sum(
                    1
                    for item in results
                    if item[
                        "core_exact"
                    ]
                ),
                total,
            ),
            "operator": _accuracy(
                sum(
                    1
                    for item in results
                    if item[
                        "operator_correct"
                    ]
                ),
                total,
            ),
            "left_operand": _accuracy(
                sum(
                    1
                    for item in results
                    if item[
                        "left_correct"
                    ]
                ),
                total,
            ),
            "right_operand_divide_only": _accuracy(
                sum(
                    1
                    for item in divide_results
                    if item[
                        "right_correct"
                    ]
                ),
                len(
                    divide_results
                ),
            ),
            "false_core_evidence_cases": {
                "count": len(
                    false_core_cases
                ),
                "case_ids": false_core_cases,
            },
            "qualifier_precision": _accuracy(
                qualifier_correct,
                qualifier_extracted,
            ),
            "partition_precision": _accuracy(
                sum(
                    1
                    for item in partition_rows
                    if item[
                        "partition_correct"
                    ]
                ),
                len(
                    partition_rows
                ),
            ),
        },
        "per_metric": per_metric,
        "results": results,
        "runtime_integration": False,
        "candidate_decision": False,
        "embedding_threshold_policy": None,
    }


def save_question_signature_benchmark_v2(
    report: dict[str, Any],
) -> Path:
    output_dir = Path(
        "docs/evaluation"
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    path = (
        output_dir
        / (
            "question_signature_benchmark_v2_"
            f"{timestamp}.json"
        )
    )

    payload = {
        "timestamp": timestamp,
        **report,
    }

    with path.open(
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            payload,
            f,
            ensure_ascii=False,
            indent=2,
        )

    return path


def main() -> None:
    report = (
        run_question_signature_benchmark_v2()
    )

    print("=" * 80)
    print(
        "Question Semantic Signature V2 Benchmark"
    )
    print(
        "Dataset Role:",
        report[
            "dataset_role"
        ],
    )
    print(
        "Cases:",
        report[
            "case_count"
        ],
    )

    for name in (
        "core_exact",
        "operator",
        "left_operand",
        "right_operand_divide_only",
        "qualifier_precision",
        "partition_precision",
    ):
        print(
            f"{name}:",
            report[
                "summary"
            ][
                name
            ],
        )

    print(
        "False Core Evidence Cases:",
        report[
            "summary"
        ][
            "false_core_evidence_cases"
        ],
    )

    print(
        "Runtime Integration:",
        report[
            "runtime_integration"
        ],
    )
    print(
        "Candidate Decision:",
        report[
            "candidate_decision"
        ],
    )
    print(
        "Embedding Threshold Policy:",
        report[
            "embedding_threshold_policy"
        ],
    )

    path = (
        save_question_signature_benchmark_v2(
            report
        )
    )

    print(
        "Saved to:",
        path,
    )


if __name__ == "__main__":
    main()
