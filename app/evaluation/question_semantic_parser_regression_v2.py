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
from app.semantic_layer.question_semantic_parser_v2 import (
    QuestionSemanticParseResultV2,
    QuestionSemanticParseStatusV2,
    parse_question_semantics_v2,
)
from app.semantic_layer.question_signature_v2 import (
    QuestionSemanticSignatureV2,
)


ParserFn = Callable[[str], QuestionSemanticParseResultV2]

PRE_NORMALIZATION_ADVERSARIAL_FINGERPRINT_V2 = (
    "eda72cdc4762054ba2bfaa007b56ee422f0c99cdc2145a1eaea54f65e739a929"
)

NORMALIZED_ADVERSARIAL_FINGERPRINT_V2 = (
    "9533ecc9c95172cd8565d6f3a8b925422e74048b188291c3c9f2f25745958bec"
)


def _empty_signature() -> QuestionSemanticSignatureV2:
    return QuestionSemanticSignatureV2()


def evaluate_parser_regression_case_v2(
    case,
    *,
    parser: ParserFn = parse_question_semantics_v2,
) -> dict[str, Any]:
    result = parser(
        case.question
    )

    actual = (
        result.signature
        if result.signature is not None
        else _empty_signature()
    )

    expected = case.expected

    core_exact = (
        actual.operator
        == expected.operator
        and actual.left_operand
        == expected.left_operand
        and actual.right_operand
        == expected.right_operand
    )

    partition_exact = (
        actual.intrinsic_partition
        == expected.intrinsic_partition
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

    full_exact = (
        core_exact
        and partition_exact
        and not qualifier_missing
        and not qualifier_false
    )

    expected_multi_intent = (
        case.role.value
        == "collision"
    )

    multi_intent_correct = (
        (
            result.status
            == QuestionSemanticParseStatusV2.MULTIPLE_INTENTS
        )
        == expected_multi_intent
    )

    expected_status = (
        QuestionSemanticParseStatusV2.MULTIPLE_INTENTS
        if expected_multi_intent
        else QuestionSemanticParseStatusV2.PARSED
    )

    if expected_multi_intent:
        acceptance_pass = (
            result.status
            == QuestionSemanticParseStatusV2.MULTIPLE_INTENTS
            and result.signature is None
        )
    else:
        acceptance_pass = (
            result.status
            == QuestionSemanticParseStatusV2.PARSED
            and result.signature is not None
            and full_exact
        )

    return {
        "case_id": case.case_id,
        "role": case.role.value,
        "family": case.family,
        "question": case.question,
        "status": result.status.value,
        "expected_status": expected_status.value,
        "expected_multi_intent": expected_multi_intent,
        "multi_intent_correct": multi_intent_correct,
        "acceptance_pass": acceptance_pass,
        "core_exact": core_exact,
        "full_exact": full_exact,
        "partition_exact": partition_exact,
        "qualifier_missing": qualifier_missing,
        "qualifier_false": qualifier_false,
        "expected": expected.model_dump(
            mode="json"
        ),
        "actual": actual.model_dump(
            mode="json"
        ),
        "deterministic_evidence": (
            result.deterministic_evidence.model_dump(
                mode="json"
            )
        ),
        "conflicts": list(
            result.conflicts
        ),
        "error": result.error,
        "raw_response": result.raw_response,
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


def run_question_semantic_parser_regression_v2(
    *,
    parser: ParserFn = parse_question_semantics_v2,
) -> dict[str, Any]:
    current_fingerprint = (
        question_signature_adversarial_fingerprint_v2()
    )

    if (
        current_fingerprint
        != NORMALIZED_ADVERSARIAL_FINGERPRINT_V2
    ):
        raise ValueError(
            "Normalized adversarial regression fingerprint drifted. "
            f"Expected={NORMALIZED_ADVERSARIAL_FINGERPRINT_V2}; "
            f"Actual={current_fingerprint}"
        )

    results = [
        evaluate_parser_regression_case_v2(
            case,
            parser=parser,
        )
        for case in QUESTION_SIGNATURE_ADVERSARIAL_CASES_V2
    ]

    total = len(
        results
    )

    status_counts = Counter(
        row[
            "status"
        ]
        for row in results
    )

    by_role: dict[
        str,
        list[dict[str, Any]],
    ] = defaultdict(list)

    for row in results:
        by_role[
            row["role"]
        ].append(
            row
        )

    def summarize_rows(
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
            "acceptance_pass": sum(
                1
                for row in rows
                if row[
                    "acceptance_pass"
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
            "full_failed_case_ids": [
                row[
                    "case_id"
                ]
                for row in rows
                if not row[
                    "full_exact"
                ]
            ],
            "acceptance_failed_case_ids": [
                row[
                    "case_id"
                ]
                for row in rows
                if not row[
                    "acceptance_pass"
                ]
            ],
        }

    return {
        "evaluation": (
            "question_semantic_parser_v2_normalized_regression"
        ),
        "dataset_role": (
            "observed_adversarial_regression_not_fresh_generalization"
        ),
        "case_count": total,
        "source_adversarial_fingerprint": (
            question_signature_adversarial_fingerprint_v2()
        ),
        "normalized_adversarial_fingerprint": (
            NORMALIZED_ADVERSARIAL_FINGERPRINT_V2
        ),
        "pre_normalization_adversarial_fingerprint": (
            PRE_NORMALIZATION_ADVERSARIAL_FINGERPRINT_V2
        ),
        "summary": {
            "core_exact": _rate(
                sum(
                    1
                    for row in results
                    if row[
                        "core_exact"
                    ]
                ),
                total,
            ),
            "full_exact": _rate(
                sum(
                    1
                    for row in results
                    if row[
                        "full_exact"
                    ]
                ),
                total,
            ),
            "acceptance_pass": _rate(
                sum(
                    1
                    for row in results
                    if row[
                        "acceptance_pass"
                    ]
                ),
                total,
            ),
            "multi_intent_guard": _rate(
                sum(
                    1
                    for row in results
                    if row[
                        "multi_intent_correct"
                    ]
                ),
                total,
            ),
            "parse_failures": sum(
                1
                for row in results
                if row[
                    "status"
                ]
                == QuestionSemanticParseStatusV2.PARSE_FAILED.value
            ),
            "evidence_conflicts": sum(
                1
                for row in results
                if row[
                    "status"
                ]
                == QuestionSemanticParseStatusV2.EVIDENCE_CONFLICT.value
            ),
            "status_counts": dict(
                sorted(
                    status_counts.items()
                )
            ),
        },
        "by_role": {
            role: summarize_rows(
                rows
            )
            for role, rows in sorted(
                by_role.items()
            )
        },
        "results": results,
        "runtime_integration": False,
        "candidate_decision": False,
        "fresh_generalization_claim": False,
    }


def save_question_semantic_parser_regression_v2(
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
            "question_semantic_parser_regression_v2_"
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
        run_question_semantic_parser_regression_v2()
    )

    print("=" * 80)
    print(
        "Question Structured Semantic Parser V2 Regression"
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
        "Source Fingerprint:",
        report[
            "source_adversarial_fingerprint"
        ],
    )
    print(
        "Core Exact:",
        report[
            "summary"
        ][
            "core_exact"
        ],
    )
    print(
        "Full Exact:",
        report[
            "summary"
        ][
            "full_exact"
        ],
    )
    print(
        "Multi-intent Guard:",
        report[
            "summary"
        ][
            "multi_intent_guard"
        ],
    )
    print(
        "Parse Failures:",
        report[
            "summary"
        ][
            "parse_failures"
        ],
    )
    print(
        "Evidence Conflicts:",
        report[
            "summary"
        ][
            "evidence_conflicts"
        ],
    )
    print(
        "Status Counts:",
        report[
            "summary"
        ][
            "status_counts"
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
        "Fresh Generalization Claim:",
        report[
            "fresh_generalization_claim"
        ],
    )

    path = (
        save_question_semantic_parser_regression_v2(
            report
        )
    )

    print(
        "Saved to:",
        path,
    )


if __name__ == "__main__":
    main()
