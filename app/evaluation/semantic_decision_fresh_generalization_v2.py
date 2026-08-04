from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from app.evaluation.semantic_decision_fresh_cases_v2 import (
    SEMANTIC_DECISION_FRESH_CASES_V2,
    SemanticDecisionFreshCaseV2,
    semantic_decision_fresh_cases_fingerprint_v2,
)
from app.semantic_layer.question_semantic_parser_v2 import (
    QuestionSemanticParseResultV2,
    parse_question_semantics_v2,
)
from app.semantic_layer.semantic_decision_service_v2 import (
    SemanticDecisionResultV2,
    resolve_semantic_decision_v2,
)


ParserFn = Callable[[str], QuestionSemanticParseResultV2]


def signature_payload(
    result: QuestionSemanticParseResultV2,
) -> dict[str, Any] | None:
    if result.signature is None:
        return None

    signature = result.signature
    return {
        "operator": None if signature.operator is None else signature.operator.value,
        "left_operand": (
            None if signature.left_operand is None else signature.left_operand.value
        ),
        "right_operand": (
            None if signature.right_operand is None else signature.right_operand.value
        ),
        "intrinsic_partition": (
            None
            if signature.intrinsic_partition is None
            else signature.intrinsic_partition.value
        ),
        "qualifiers": sorted(item.value for item in signature.qualifiers),
    }


def expected_signature_payload(
    case: SemanticDecisionFreshCaseV2,
) -> dict[str, Any] | None:
    expected = case.expected_signature
    if expected is None:
        return None

    return {
        "operator": None if expected.operator is None else expected.operator.value,
        "left_operand": (
            None if expected.left_operand is None else expected.left_operand.value
        ),
        "right_operand": (
            None if expected.right_operand is None else expected.right_operand.value
        ),
        "intrinsic_partition": (
            None
            if expected.intrinsic_partition is None
            else expected.intrinsic_partition.value
        ),
        "qualifiers": sorted(item.value for item in expected.qualifiers),
    }


def replay_llm_call(raw_response: str | None) -> Callable[..., str]:
    def replay(**_: Any) -> str:
        return "{}" if raw_response is None else raw_response

    return replay


def evaluate_parser(
    case: SemanticDecisionFreshCaseV2,
    *,
    parser: ParserFn,
) -> tuple[QuestionSemanticParseResultV2, list[str]]:
    parsed = parser(case.question)
    problems: list[str] = []

    if parsed.status != case.expected_parser_status:
        problems.append(
            "parser_status expected="
            f"{case.expected_parser_status.value} actual={parsed.status.value}"
        )

    expected = expected_signature_payload(case)
    actual = signature_payload(parsed)
    if actual != expected:
        problems.append(f"signature expected={expected} actual={actual}")

    return parsed, problems


def evaluate_semantic_decision(
    case: SemanticDecisionFreshCaseV2,
    *,
    parsed: QuestionSemanticParseResultV2,
) -> tuple[SemanticDecisionResultV2, list[str]]:
    result = resolve_semantic_decision_v2(
        question=case.question,
        allowed_metric_names=(
            None if not case.allowed_metric_names else set(case.allowed_metric_names)
        ),
        llm_call=replay_llm_call(parsed.raw_response),
    )

    problems: list[str] = []

    if result.parser_status != case.expected_parser_status:
        problems.append(
            "service_parser_status expected="
            f"{case.expected_parser_status.value} actual={result.parser_status.value}"
        )

    if result.status != case.expected_semantic_status:
        problems.append(
            "semantic_status expected="
            f"{case.expected_semantic_status.value} actual={result.status.value}"
        )

    if result.metric_name != case.expected_metric_name:
        problems.append(
            f"metric_name expected={case.expected_metric_name} actual={result.metric_name}"
        )

    if case.expected_semantic_status.value == "matched":
        expected_candidates = {
            case.expected_metric_name
        }
    elif (
        case.expected_semantic_status.value
        == "needs_clarification"
    ):
        expected_candidates = set(
            case.expected_candidates
        )
    else:
        expected_candidates = set()

    actual_candidates = set(
        result.candidates
    )

    if actual_candidates != expected_candidates:
        problems.append(
            "candidates expected="
            f"{sorted(expected_candidates)} "
            f"actual={sorted(actual_candidates)}"
        )

    if (
        case.expected_ranking_applied is not None
        and result.ranking_applied != case.expected_ranking_applied
    ):
        problems.append(
            "ranking_applied expected="
            f"{case.expected_ranking_applied} actual={result.ranking_applied}"
        )

    if result.status.value != "matched" and result.metric_name is not None:
        problems.append("non-MATCHED result must not expose metric_name")

    if result.status.value != "needs_clarification" and result.ranking_applied:
        problems.append("embedding ranking must only apply to clarification")

    return result, problems


def evaluate_fresh_case_v2(
    case: SemanticDecisionFreshCaseV2,
    *,
    parser: ParserFn = parse_question_semantics_v2,
) -> dict[str, Any]:
    parsed, parser_problems = evaluate_parser(case, parser=parser)
    semantic_result, semantic_problems = evaluate_semantic_decision(
        case,
        parsed=parsed,
    )
    problems = [*parser_problems, *semantic_problems]

    return {
        "case_id": case.case_id,
        "role": case.role.value,
        "family": case.family,
        "question": case.question,
        "allowed_metric_names": sorted(case.allowed_metric_names),
        "pass": not problems,
        "problems": problems,
        "expected": {
            "parser_status": case.expected_parser_status.value,
            "signature": expected_signature_payload(case),
            "semantic_status": case.expected_semantic_status.value,
            "metric_name": case.expected_metric_name,
            "candidates": sorted(case.expected_candidates),
            "ranking_applied": case.expected_ranking_applied,
        },
        "actual": {
            "parser_status": parsed.status.value,
            "signature": signature_payload(parsed),
            "semantic_status": semantic_result.status.value,
            "metric_name": semantic_result.metric_name,
            "candidates": list(semantic_result.candidates),
            "ranking_applied": semantic_result.ranking_applied,
            "ranking_method": semantic_result.ranking_method,
            "parser_error": semantic_result.parser_error,
            "parser_conflicts": list(semantic_result.parser_conflicts),
        },
        "deterministic_evidence": parsed.deterministic_evidence.model_dump(
            mode="json"
        ),
        "raw_response": parsed.raw_response,
        "note": case.note,
    }


def matching_previous_reports(
    *,
    output_dir: Path,
    case_fingerprint: str,
) -> list[Path]:
    matches: list[Path] = []

    for path in sorted(
        output_dir.glob("semantic_decision_fresh_generalization_v2_*.json")
    ):
        try:
            with path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except Exception:
            continue

        if payload.get("case_fingerprint") == case_fingerprint:
            matches.append(path)

    return matches


def run_semantic_decision_fresh_generalization_v2(
    *,
    allow_regression: bool = False,
    parser: ParserFn = parse_question_semantics_v2,
) -> dict[str, Any]:
    output_dir = Path("docs/evaluation")
    output_dir.mkdir(parents=True, exist_ok=True)

    case_fingerprint = semantic_decision_fresh_cases_fingerprint_v2()
    previous_reports = matching_previous_reports(
        output_dir=output_dir,
        case_fingerprint=case_fingerprint,
    )

    if previous_reports and not allow_regression:
        raise RuntimeError(
            "This Fresh Holdout fingerprint has already been observed. "
            "Replay it only as regression with --allow-regression. "
            f"Previous reports={[str(path) for path in previous_reports]}"
        )

    is_first_observation = not previous_reports
    results: list[dict[str, Any]] = []

    for case in SEMANTIC_DECISION_FRESH_CASES_V2:
        try:
            row = evaluate_fresh_case_v2(case, parser=parser)
        except Exception as exc:
            row = {
                "case_id": case.case_id,
                "role": case.role.value,
                "family": case.family,
                "question": case.question,
                "allowed_metric_names": sorted(case.allowed_metric_names),
                "pass": False,
                "problems": [f"exception: {type(exc).__name__}: {exc}"],
                "expected": {
                    "parser_status": case.expected_parser_status.value,
                    "signature": expected_signature_payload(case),
                    "semantic_status": case.expected_semantic_status.value,
                    "metric_name": case.expected_metric_name,
                    "candidates": sorted(case.expected_candidates),
                    "ranking_applied": case.expected_ranking_applied,
                },
                "actual": None,
                "deterministic_evidence": None,
                "raw_response": None,
                "note": case.note,
            }
        results.append(row)

    total = len(results)
    passed = sum(1 for row in results if row["pass"])
    failed = total - passed

    by_role: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in results:
        by_role[row["role"]].append(row)

    role_summary = {
        role: {
            "total": len(rows),
            "passed": sum(1 for row in rows if row["pass"]),
            "failed_case_ids": [row["case_id"] for row in rows if not row["pass"]],
        }
        for role, rows in sorted(by_role.items())
    }

    status_counts = Counter(
        "unknown" if row.get("actual") is None else row["actual"]["semantic_status"]
        for row in results
    )

    return {
        "evaluation": "semantic_decision_v2_final_fresh_generalization",
        "dataset_role": (
            "fresh_holdout_first_observation"
            if is_first_observation
            else "observed_holdout_regression_replay"
        ),
        "case_fingerprint": case_fingerprint,
        "attempt_number": len(previous_reports) + 1,
        "previous_matching_report_count": len(previous_reports),
        "fresh_generalization_claim": is_first_observation,
        "case_count": total,
        "summary": {
            "passed": passed,
            "failed": failed,
            "accuracy": round(passed / total * 100, 2),
            "failed_case_ids": [row["case_id"] for row in results if not row["pass"]],
            "semantic_status_counts": dict(sorted(status_counts.items())),
        },
        "by_role": role_summary,
        "results": results,
        "production_code_modified_for_attempt": False,
        "stable_graph_integration": False,
    }


def save_semantic_decision_fresh_generalization_v2(
    report: dict[str, Any],
) -> Path:
    output_dir = Path("docs/evaluation")
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = output_dir / f"semantic_decision_fresh_generalization_v2_{timestamp}.json"

    with path.open("w", encoding="utf-8") as handle:
        json.dump(
            {"timestamp": timestamp, **report},
            handle,
            ensure_ascii=False,
            indent=2,
        )

    return path


def main() -> None:
    cli = argparse.ArgumentParser(
        description=(
            "Run Semantic Decision V2 Fresh Generalization. A previously "
            "observed fingerprint requires --allow-regression."
        )
    )
    cli.add_argument(
        "--allow-regression",
        action="store_true",
        help="Replay an already observed Holdout fingerprint as regression only.",
    )
    args = cli.parse_args()

    report = run_semantic_decision_fresh_generalization_v2(
        allow_regression=args.allow_regression,
    )
    path = save_semantic_decision_fresh_generalization_v2(report)

    print("=" * 80)
    print("Semantic Decision V2 Final Fresh Generalization")
    print("Dataset Role:", report["dataset_role"])
    print("Case Fingerprint:", report["case_fingerprint"])
    print("Attempt:", report["attempt_number"])
    print("Fresh Generalization Claim:", report["fresh_generalization_claim"])
    print("Total:", report["case_count"])
    print("Passed:", report["summary"]["passed"])
    print("Failed:", report["summary"]["failed"])
    print("Failed Case IDs:", report["summary"]["failed_case_ids"])
    print("Saved to:", path)

    if report["summary"]["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
