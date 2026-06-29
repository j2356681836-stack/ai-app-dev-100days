import argparse
import json
from datetime import datetime
from pathlib import Path

from app.evaluation.retrieval_eval_cases import RETRIEVAL_EVAL_CASES
from app.semantic_layer.hybrid_search import search_metric


def extract_metric_names(result: dict) -> list[str]:
    """
    从 matched 或 clarification 结果中提取 metric_name 列表。

    matched:
        result["metrics"] -> [{"name": "..."}]

    needs_clarification:
        result["options"] / result["suggestions"] -> [{"metric_name": "..."}]
    """

    items = (
        result.get("metrics")
        or result.get("suggestions")
        or result.get("options")
        or []
    )

    names = []

    for item in items:
        name = item.get("name") or item.get("metric_name")
        if name:
            names.append(name)

    return names


def extract_metric_labels(result: dict) -> list[str]:
    items = (
        result.get("metrics")
        or result.get("suggestions")
        or result.get("options")
        or []
    )

    labels = []

    for item in items:
        label = item.get("chinese_name") or item.get("metric_label")
        if label:
            labels.append(label)

    return labels


def extract_search_types(result: dict) -> list[str]:
    """
    hybrid_search 的 trace 有两种形态：

    rule path:
        trace = [{"search_type": "alias"}]

    embedding path:
        trace = {"search_type": "embedding"}
    """

    trace = result.get("trace")

    if isinstance(trace, list):
        return [
            item.get("search_type")
            for item in trace
            if item.get("search_type")
        ]

    if isinstance(trace, dict):
        search_type = trace.get("search_type")
        return [search_type] if search_type else []

    return []


def get_rank(metric_names: list[str], metric_name: str) -> int | None:
    try:
        return metric_names.index(metric_name) + 1
    except ValueError:
        return None


def evaluate_case(case: dict) -> dict:
    question = case["question"]
    result = search_metric(question)

    metric_names = extract_metric_names(result)
    metric_labels = extract_metric_labels(result)
    search_types = extract_search_types(result)

    errors = []

    expected_status = case.get("expected_status")
    actual_status = result.get("status")

    if expected_status and actual_status != expected_status:
        errors.append(
            {
                "type": "status_mismatch",
                "expected": expected_status,
                "actual": actual_status,
            }
        )

    expected_method = case.get("expected_method")
    actual_method = result.get("method")

    if expected_method and actual_method != expected_method:
        errors.append(
            {
                "type": "method_mismatch",
                "expected": expected_method,
                "actual": actual_method,
            }
        )

    expected_search_type_in = case.get("expected_search_type_in", [])

    if expected_search_type_in:
        if not any(item in expected_search_type_in for item in search_types):
            errors.append(
                {
                    "type": "search_type_mismatch",
                    "expected_in": expected_search_type_in,
                    "actual": search_types,
                }
            )

    expected_top_option = case.get("expected_top_option")

    if expected_top_option:
        actual_top_option = metric_names[0] if metric_names else None

        if actual_top_option != expected_top_option:
            errors.append(
                {
                    "type": "top_option_mismatch",
                    "expected": expected_top_option,
                    "actual": actual_top_option,
                }
            )

    must_include_options = case.get("must_include_options", [])

    for metric_name in must_include_options:
        if metric_name not in metric_names:
            errors.append(
                {
                    "type": "missing_required_option",
                    "metric_name": metric_name,
                    "actual_options": metric_names,
                }
            )

    must_include_any_options = case.get("must_include_any_options", [])

    if must_include_any_options:
        if not any(metric_name in metric_names for metric_name in must_include_any_options):
            errors.append(
                {
                    "type": "missing_any_required_option",
                    "expected_any": must_include_any_options,
                    "actual_options": metric_names,
                }
            )

    forbidden_options = case.get("forbidden_options", [])

    for metric_name in forbidden_options:
        if metric_name in metric_names:
            errors.append(
                {
                    "type": "forbidden_option_present",
                    "metric_name": metric_name,
                    "rank": get_rank(metric_names, metric_name),
                    "actual_options": metric_names,
                }
            )

    not_in_top_n = case.get("not_in_top_n", {})

    for metric_name, top_n in not_in_top_n.items():
        rank = get_rank(metric_names, metric_name)

        if rank is not None and rank <= top_n:
            errors.append(
                {
                    "type": "option_rank_too_high",
                    "metric_name": metric_name,
                    "rank": rank,
                    "not_allowed_in_top_n": top_n,
                    "actual_options": metric_names,
                }
            )

    passed = len(errors) == 0

    return {
        "case_id": case["case_id"],
        "question": question,
        "description": case.get("description", ""),
        "passed": passed,
        "errors": errors,
        "actual": {
            "status": actual_status,
            "method": actual_method,
            "search_types": search_types,
            "metric_names": metric_names,
            "metric_labels": metric_labels,
            "trace": result.get("trace"),
        },
    }


def save_report(results: list[dict]) -> Path:
    output_dir = Path("docs/evaluation")
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"retrieval_eval_{timestamp}.json"

    report = {
        "total": len(results),
        "passed": sum(1 for item in results if item["passed"]),
        "failed": sum(1 for item in results if not item["passed"]),
        "results": results,
    }

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    return output_path


def run(strict: bool = False):
    results = []

    for case in RETRIEVAL_EVAL_CASES:
        print("=" * 80)
        print(f"Evaluating: {case['case_id']} - {case['question']}")

        result = evaluate_case(case)
        results.append(result)

        if result["passed"]:
            print("✅ PASSED")
        else:
            print("❌ FAILED")
            for error in result["errors"]:
                print("-", error)

        print("Actual options:", result["actual"]["metric_names"])
        print("Trace:", result["actual"]["trace"])

    output_path = save_report(results)

    passed = sum(1 for item in results if item["passed"])
    failed = sum(1 for item in results if not item["passed"])

    print("=" * 80)
    print("Retrieval Evaluation Summary")
    print(f"Total: {len(results)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Saved to: {output_path}")

    if strict and failed > 0:
        raise SystemExit(1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with non-zero status if any retrieval case fails.",
    )

    args = parser.parse_args()
    run(strict=args.strict)


if __name__ == "__main__":
    main()