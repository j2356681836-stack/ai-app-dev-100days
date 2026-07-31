from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from app.evaluation.question_semantic_parser_regression_v2 import (
    NORMALIZED_ADVERSARIAL_FINGERPRINT_V2,
    evaluate_parser_regression_case_v2,
)
from app.evaluation.question_signature_adversarial_cases_v2 import (
    QUESTION_SIGNATURE_ADVERSARIAL_CASES_V2,
    question_signature_adversarial_fingerprint_v2,
)


TARGET_CASE_IDS = (
    "QSADV-004",
    "QSADV-005",
    "QSADV-006",
    "QSADV-047",
)

RUNS_PER_CASE = 5


def _canonical_json(
    value: Any,
) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(
            ",",
            ":",
        ),
    )


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
                correct
                / total
                * 100,
                2,
            )
        ),
    }


def _observed_classification(
    passed: int,
    total: int,
) -> str:
    if passed == total:
        return "all_pass"
    if passed == 0:
        return "all_fail"
    return "mixed"


def _load_target_cases() -> dict[str, Any]:
    case_map = {
        case.case_id: case
        for case
        in QUESTION_SIGNATURE_ADVERSARIAL_CASES_V2
    }

    missing = [
        case_id
        for case_id
        in TARGET_CASE_IDS
        if case_id
        not in case_map
    ]

    if missing:
        raise ValueError(
            "Repeatability target cases missing: "
            + ", ".join(
                missing
            )
        )

    return {
        case_id: case_map[
            case_id
        ]
        for case_id
        in TARGET_CASE_IDS
    }


def _summarize_case_runs(
    *,
    case,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    total = len(
        rows
    )

    core_pass = sum(
        1
        for row in rows
        if row[
            "core_exact"
        ]
    )

    full_pass = sum(
        1
        for row in rows
        if row[
            "full_exact"
        ]
    )

    acceptance_pass = sum(
        1
        for row in rows
        if row[
            "acceptance_pass"
        ]
    )

    status_counts = Counter(
        row[
            "status"
        ]
        for row in rows
    )

    signature_counter = Counter(
        _canonical_json(
            row[
                "actual"
            ]
        )
        for row in rows
    )

    qualifier_missing_counts = Counter(
        qualifier
        for row in rows
        for qualifier in row[
            "qualifier_missing"
        ]
    )

    qualifier_false_counts = Counter(
        qualifier
        for row in rows
        for qualifier in row[
            "qualifier_false"
        ]
    )

    actual_signature_variants = [
        {
            "count": count,
            "signature": json.loads(
                signature_json
            ),
        }
        for (
            signature_json,
            count,
        )
        in sorted(
            signature_counter.items(),
            key=lambda item: (
                -item[1],
                item[0],
            ),
        )
    ]

    return {
        "case_id": case.case_id,
        "role": case.role.value,
        "family": case.family,
        "question": case.question,
        "runs": total,
        "core_exact": _rate(
            core_pass,
            total,
        ),
        "full_exact": _rate(
            full_pass,
            total,
        ),
        "acceptance_pass": _rate(
            acceptance_pass,
            total,
        ),
        "observed_acceptance_classification": (
            _observed_classification(
                acceptance_pass,
                total,
            )
        ),
        "status_counts": dict(
            sorted(
                status_counts.items()
            )
        ),
        "actual_signature_variant_count": len(
            actual_signature_variants
        ),
        "actual_signature_variants": (
            actual_signature_variants
        ),
        "qualifier_missing_counts": dict(
            sorted(
                qualifier_missing_counts.items()
            )
        ),
        "qualifier_false_counts": dict(
            sorted(
                qualifier_false_counts.items()
            )
        ),
    }


def run_question_semantic_parser_repeatability_v2(
    *,
    runs_per_case: int = RUNS_PER_CASE,
) -> dict[str, Any]:
    if runs_per_case <= 0:
        raise ValueError(
            "runs_per_case must be greater than 0."
        )

    current_fingerprint = (
        question_signature_adversarial_fingerprint_v2()
    )

    if (
        current_fingerprint
        != NORMALIZED_ADVERSARIAL_FINGERPRINT_V2
    ):
        raise ValueError(
            "Normalized adversarial fingerprint drifted. "
            f"Expected={NORMALIZED_ADVERSARIAL_FINGERPRINT_V2}; "
            f"Actual={current_fingerprint}"
        )

    target_cases = (
        _load_target_cases()
    )

    runs_by_case: dict[
        str,
        list[dict[str, Any]],
    ] = {
        case_id: []
        for case_id
        in TARGET_CASE_IDS
    }

    all_runs: list[
        dict[str, Any]
    ] = []

    # Run by round rather than running one case
    # five consecutive times. This reduces simple
    # temporal clustering in this small probe.
    for round_index in range(
        1,
        runs_per_case + 1,
    ):
        for case_id in TARGET_CASE_IDS:
            case = target_cases[
                case_id
            ]

            row = (
                evaluate_parser_regression_case_v2(
                    case
                )
            )

            run_row = {
                "round": round_index,
                **row,
            }

            runs_by_case[
                case_id
            ].append(
                run_row
            )

            all_runs.append(
                run_row
            )

    case_summaries = [
        _summarize_case_runs(
            case=target_cases[
                case_id
            ],
            rows=runs_by_case[
                case_id
            ],
        )
        for case_id
        in TARGET_CASE_IDS
    ]

    classification_counts = Counter(
        row[
            "observed_acceptance_classification"
        ]
        for row in case_summaries
    )

    return {
        "evaluation": (
            "question_semantic_parser_v2_repeatability_probe"
        ),
        "dataset_role": (
            "observed_adversarial_repeatability_probe_not_fresh_generalization"
        ),
        "source_adversarial_fingerprint": (
            current_fingerprint
        ),
        "normalized_adversarial_fingerprint": (
            NORMALIZED_ADVERSARIAL_FINGERPRINT_V2
        ),
        "target_case_ids": list(
            TARGET_CASE_IDS
        ),
        "runs_per_case": (
            runs_per_case
        ),
        "total_calls": (
            len(
                all_runs
            )
        ),
        "summary": {
            "target_cases": len(
                TARGET_CASE_IDS
            ),
            "classification_counts": dict(
                sorted(
                    classification_counts.items()
                )
            ),
            "all_pass_case_ids": [
                row[
                    "case_id"
                ]
                for row
                in case_summaries
                if row[
                    "observed_acceptance_classification"
                ]
                == "all_pass"
            ],
            "all_fail_case_ids": [
                row[
                    "case_id"
                ]
                for row
                in case_summaries
                if row[
                    "observed_acceptance_classification"
                ]
                == "all_fail"
            ],
            "mixed_case_ids": [
                row[
                    "case_id"
                ]
                for row
                in case_summaries
                if row[
                    "observed_acceptance_classification"
                ]
                == "mixed"
            ],
        },
        "cases": case_summaries,
        "runs": all_runs,
        "runtime_integration": False,
        "candidate_decision": False,
        "fresh_generalization_claim": False,
        "statistical_stability_claim": False,
    }


def save_repeatability_report_v2(
    report: dict[str, Any],
) -> Path:
    timestamp = (
        datetime.now().strftime(
            "%Y%m%d_%H%M%S"
        )
    )

    output_dir = Path(
        "docs/evaluation"
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    path = output_dir / (
        "question_semantic_parser_repeatability_v2_"
        f"{timestamp}.json"
    )

    payload = {
        "timestamp": timestamp,
        **report,
    }

    path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return path


def main() -> None:
    report = (
        run_question_semantic_parser_repeatability_v2()
    )

    path = (
        save_repeatability_report_v2(
            report
        )
    )

    print(
        "Question Structured Semantic Parser "
        "V2 Repeatability Probe"
    )
    print(
        "Dataset Role:",
        report[
            "dataset_role"
        ],
    )
    print(
        "Source Fingerprint:",
        report[
            "source_adversarial_fingerprint"
        ],
    )
    print(
        "Runs Per Case:",
        report[
            "runs_per_case"
        ],
    )
    print(
        "Total Calls:",
        report[
            "total_calls"
        ],
    )

    print()

    for row in report[
        "cases"
    ]:
        print(
            row[
                "case_id"
            ],
            "| Core:",
            (
                f"{row['core_exact']['correct']}"
                f"/{row['core_exact']['total']}"
            ),
            "| Full:",
            (
                f"{row['full_exact']['correct']}"
                f"/{row['full_exact']['total']}"
            ),
            "| Acceptance:",
            (
                f"{row['acceptance_pass']['correct']}"
                f"/{row['acceptance_pass']['total']}"
            ),
            "| Classification:",
            row[
                "observed_acceptance_classification"
            ],
            "| Signature Variants:",
            row[
                "actual_signature_variant_count"
            ],
        )

    print()

    print(
        "All Pass:",
        report[
            "summary"
        ][
            "all_pass_case_ids"
        ],
    )
    print(
        "All Fail:",
        report[
            "summary"
        ][
            "all_fail_case_ids"
        ],
    )
    print(
        "Mixed:",
        report[
            "summary"
        ][
            "mixed_case_ids"
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
    print(
        "Statistical Stability Claim:",
        report[
            "statistical_stability_claim"
        ],
    )
    print(
        "Saved to:",
        path,
    )


if __name__ == "__main__":
    main()