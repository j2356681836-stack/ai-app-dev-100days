from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from app.evaluation.question_signature_adversarial_cases_v2 import (
    QUESTION_SIGNATURE_ADVERSARIAL_CASES_V2,
    question_signature_adversarial_fingerprint_v2,
)
from app.semantic_layer.question_signature_v2 import (
    QuestionSemanticSignatureV2,
    extract_question_semantic_signature_v2,
)


ExtractorFn = Callable[[str], QuestionSemanticSignatureV2]

FIRST_FRESH_ADVERSARIAL_FINGERPRINT_V2 = (
    "eda72cdc4762054ba2bfaa007b56ee422f0c99cdc2145a1eaea54f65e739a929"
)

def _compare_scalar(
    *,
    actual,
    expected,
) -> tuple[bool, bool]:
    """
    Returns:
    - exact: actual == expected
    - false_evidence: actual is non-null while expected is null,
      or actual is a different non-null value.
    """
    exact = actual == expected

    false_evidence = (
        actual is not None
        and actual != expected
    )

    return (
        exact,
        false_evidence,
    )


def evaluate_question_signature_adversarial_case_v2(
    case,
    *,
    extractor: ExtractorFn = extract_question_semantic_signature_v2,
) -> dict[str, Any]:
    actual = extractor(
        case.question
    )

    expected = case.expected

    operator_exact, operator_false = _compare_scalar(
        actual=actual.operator,
        expected=expected.operator,
    )
    left_exact, left_false = _compare_scalar(
        actual=actual.left_operand,
        expected=expected.left_operand,
    )
    right_exact, right_false = _compare_scalar(
        actual=actual.right_operand,
        expected=expected.right_operand,
    )
    partition_exact, partition_false = _compare_scalar(
        actual=actual.intrinsic_partition,
        expected=expected.intrinsic_partition,
    )

    actual_qualifiers = set(
        actual.qualifiers
    )
    expected_qualifiers = set(
        expected.qualifiers
    )

    qualifier_missing = sorted(
        qualifier.value
        for qualifier in (
            expected_qualifiers
            - actual_qualifiers
        )
    )
    qualifier_false = sorted(
        qualifier.value
        for qualifier in (
            actual_qualifiers
            - expected_qualifiers
        )
    )

    core_exact = (
        operator_exact
        and left_exact
        and right_exact
    )

    full_exact = (
        core_exact
        and partition_exact
        and not qualifier_missing
        and not qualifier_false
    )

    false_core_fields = [
        field
        for field, is_false in (
            (
                "operator",
                operator_false,
            ),
            (
                "left_operand",
                left_false,
            ),
            (
                "right_operand",
                right_false,
            ),
        )
        if is_false
    ]

    return {
        "case_id": case.case_id,
        "role": case.role.value,
        "family": case.family,
        "question": case.question,
        "expected": expected.model_dump(
            mode="json"
        ),
        "actual": actual.model_dump(
            mode="json"
        ),
        "operator_exact": operator_exact,
        "left_exact": left_exact,
        "right_exact": right_exact,
        "partition_exact": partition_exact,
        "core_exact": core_exact,
        "full_exact": full_exact,
        "false_core_fields": false_core_fields,
        "partition_false_evidence": partition_false,
        "qualifier_missing": qualifier_missing,
        "qualifier_false": qualifier_false,
    }


def _rate(
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
                correct / total * 100,
                2,
            )
        ),
    }


def run_question_signature_adversarial_eval_v2(
    *,
    extractor: ExtractorFn = extract_question_semantic_signature_v2,
) -> dict[str, Any]:
    current_fingerprint = (
        question_signature_adversarial_fingerprint_v2()
    )

    if (
        current_fingerprint
        != FIRST_FRESH_ADVERSARIAL_FINGERPRINT_V2
    ):
        raise ValueError(
            "This evaluator is reserved for the original Day74 "
            "first-fresh adversarial dataset and must not run "
            "against a migrated or observed case contract. "
            f"Expected={FIRST_FRESH_ADVERSARIAL_FINGERPRINT_V2}; "
            f"Actual={current_fingerprint}"
        )
        
    results = [
        evaluate_question_signature_adversarial_case_v2(
            case,
            extractor=extractor,
        )
        for case in QUESTION_SIGNATURE_ADVERSARIAL_CASES_V2
    ]

    total = len(results)

    role_counts = Counter(
        item["role"]
        for item in results
    )

    false_core_cases = [
        item["case_id"]
        for item in results
        if item[
            "false_core_fields"
        ]
    ]

    partition_false_cases = [
        item["case_id"]
        for item in results
        if item[
            "partition_false_evidence"
        ]
    ]

    qualifier_false_cases = [
        item["case_id"]
        for item in results
        if item[
            "qualifier_false"
        ]
    ]

    by_role: dict[
        str,
        list[dict[str, Any]],
    ] = defaultdict(list)

    by_family: dict[
        str,
        list[dict[str, Any]],
    ] = defaultdict(list)

    for item in results:
        by_role[
            item["role"]
        ].append(
            item
        )
        by_family[
            item["family"]
        ].append(
            item
        )

    def summarize_group(
        rows: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "total": len(rows),
            "core_exact": sum(
                1
                for row in rows
                if row[
                    "core_exact"
                ]
            ),
            "full_exact": sum(
                1
                for row in rows
                if row[
                    "full_exact"
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

    return {
        "evaluation": (
            "day74_gate5eb2_question_signature_fresh_adversarial"
        ),
        "dataset_role": (
            "fresh_adversarial_first_run_only"
        ),
        "case_count": total,
        "adversarial_fingerprint": (
            question_signature_adversarial_fingerprint_v2()
        ),
        "role_counts": dict(
            sorted(
                role_counts.items()
            )
        ),
        "summary": {
            "core_exact": _rate(
                sum(
                    1
                    for item in results
                    if item[
                        "core_exact"
                    ]
                ),
                total,
            ),
            "full_exact": _rate(
                sum(
                    1
                    for item in results
                    if item[
                        "full_exact"
                    ]
                ),
                total,
            ),
            "operator": _rate(
                sum(
                    1
                    for item in results
                    if item[
                        "operator_exact"
                    ]
                ),
                total,
            ),
            "left_operand": _rate(
                sum(
                    1
                    for item in results
                    if item[
                        "left_exact"
                    ]
                ),
                total,
            ),
            "right_operand": _rate(
                sum(
                    1
                    for item in results
                    if item[
                        "right_exact"
                    ]
                ),
                total,
            ),
            "false_core_evidence": {
                "count": len(
                    false_core_cases
                ),
                "case_ids": false_core_cases,
            },
            "partition_false_evidence": {
                "count": len(
                    partition_false_cases
                ),
                "case_ids": partition_false_cases,
            },
            "qualifier_false_evidence": {
                "count": len(
                    qualifier_false_cases
                ),
                "case_ids": qualifier_false_cases,
            },
        },
        "by_role": {
            role: summarize_group(
                rows
            )
            for role, rows in sorted(
                by_role.items()
            )
        },
        "by_family": {
            family: summarize_group(
                rows
            )
            for family, rows in sorted(
                by_family.items()
            )
        },
        "results": results,
        "runtime_integration": False,
        "candidate_decision": False,
        "extractor_mutation_allowed_during_first_run": False,
    }


def save_question_signature_adversarial_eval_v2(
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
            "question_signature_adversarial_v2_"
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
        run_question_signature_adversarial_eval_v2()
    )

    print("=" * 80)
    print(
        "Question Signature Fresh Adversarial V2"
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
    print(
        "Fingerprint:",
        report[
            "adversarial_fingerprint"
        ],
    )

    for name in (
        "core_exact",
        "full_exact",
        "operator",
        "left_operand",
        "right_operand",
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
        "False Core Evidence:",
        report[
            "summary"
        ][
            "false_core_evidence"
        ],
    )
    print(
        "Partition False Evidence:",
        report[
            "summary"
        ][
            "partition_false_evidence"
        ],
    )
    print(
        "Qualifier False Evidence:",
        report[
            "summary"
        ][
            "qualifier_false_evidence"
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

    path = (
        save_question_signature_adversarial_eval_v2(
            report
        )
    )

    print(
        "Saved to:",
        path,
    )


if __name__ == "__main__":
    main()
