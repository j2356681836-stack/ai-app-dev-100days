from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from app.evaluation.generalization_cases_v2 import (
    LOCKED_HOLDOUT_CASES_V2,
    LOCKED_HOLDOUT_FINGERPRINT,
    SEMANTIC_ADVERSARIAL_CASES_V2,
)
from app.evaluation.golden_case_v2_evaluator import (
    build_summary,
    evaluate_case_v2,
    print_results,
    print_summary,
)


def select_generalization_cases(suite: str):
    if suite == "holdout":
        return LOCKED_HOLDOUT_CASES_V2

    if suite == "adversarial":
        return SEMANTIC_ADVERSARIAL_CASES_V2

    if suite == "all":
        return (
            *LOCKED_HOLDOUT_CASES_V2,
            *SEMANTIC_ADVERSARIAL_CASES_V2,
        )

    raise ValueError(
        f"Unknown generalization suite: {suite}"
    )


def run_generalization_evaluation(
    suite: str,
) -> list[dict]:
    return [
        evaluate_case_v2(case)
        for case in select_generalization_cases(suite)
    ]


def save_generalization_report(
    *,
    suite: str,
    results: list[dict],
) -> Path:
    output_dir = Path("docs/evaluation")
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    output_path = (
        output_dir
        / f"generalization_v2_{suite}_{timestamp}.json"
    )

    report = {
        "timestamp": timestamp,
        "evaluation": "day74_v2_generalization",
        "suite": suite,
        "locked_holdout_fingerprint": (
            LOCKED_HOLDOUT_FINGERPRINT
        ),
        "summary": build_summary(results),
        "results": results,
    }

    with output_path.open(
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            report,
            f,
            ensure_ascii=False,
            indent=2,
        )

    return output_path


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--suite",
        choices=("holdout", "adversarial", "all"),
        default="holdout",
    )

    parser.add_argument(
        "--strict",
        action="store_true",
        help=(
            "Exit 1 on failures. "
            "First Holdout run should omit --strict."
        ),
    )

    args = parser.parse_args()

    results = run_generalization_evaluation(
        args.suite
    )
    summary = build_summary(results)

    print_results(results)

    print("=" * 80)
    print("Day74 V2 Generalization Evaluation")
    print("Suite:", args.suite)
    print(
        "Locked Holdout Fingerprint:",
        LOCKED_HOLDOUT_FINGERPRINT,
    )

    print_summary(summary)

    output_path = save_generalization_report(
        suite=args.suite,
        results=results,
    )

    print()
    print(f"Saved to: {output_path}")

    if args.strict and summary["failed"] > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
