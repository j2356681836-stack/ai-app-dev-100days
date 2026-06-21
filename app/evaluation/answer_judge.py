import json
import argparse
import os
from dotenv import load_dotenv
from openai import OpenAI
from datetime import datetime
from pathlib import Path

from app.evaluation.answer_eval_cases import ANSWER_EVAL_CASES


load_dotenv()

client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url=os.getenv("DEEPSEEK_BASE_URL"),
)

def build_judge_prompt(case: dict) -> str:
    """
    构造 LLM-as-Judge Prompt。

    Day45 先只生成 prompt，不调用真实 LLM。
    Day46 可以复用这个 prompt 接入真实模型。
    """
    return f"""
你是一名严格的 AI BI Answer 评估员。

请根据用户问题、SQL 查询结果上下文、系统回答和评分标准，
判断系统回答是否忠实、相关、完整、清晰。

用户问题：
{case["question"]}

SQL 查询结果上下文：
{json.dumps(case["context"], ensure_ascii=False, indent=2)}

系统回答：
{case["answer"]}

参考回答：
{case.get("reference_answer", "")}

评分标准：
{json.dumps(case["rubric"], ensure_ascii=False, indent=2)}

请输出 JSON，格式如下：
{{
  "scores": {{
    "faithfulness": 1,
    "relevance": 1,
    "completeness": 1,
    "clarity": 1
  }},
  "issues": [],
  "judge_reason": "简要说明判断理由"
}}

评分规则：
- 每个维度只能是 1 或 0
- 1 表示通过
- 0 表示不通过
- 如果回答中出现上下文没有支持的原因解释，faithfulness 必须为 0
- 如果回答没有直接回答问题，relevance 必须为 0
- 如果回答遗漏关键对象或关键数值，completeness 必须为 0
- 如果回答表达混乱或不可读，clarity 必须为 0
""".strip()


def clean_judge_json_text(text: str) -> str:
    """
    清理 LLM Judge 返回的 JSON 文本。

    常见情况：
    - ```json ... ```
    - ``` ... ```
    - 前后有解释文字
    """
    cleaned = text.strip()

    if cleaned.startswith("```json"):
        cleaned = cleaned.removeprefix("```json").strip()

    if cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```").strip()

    if cleaned.endswith("```"):
        cleaned = cleaned.removesuffix("```").strip()

    start = cleaned.find("{")
    end = cleaned.rfind("}")

    if start != -1 and end != -1 and end > start:
        cleaned = cleaned[start : end + 1]

    return cleaned


def check_expected_points(answer: str, expected_points: list[str]) -> list[str]:
    """
    检查 answer 是否包含所有关键事实点。
    """
    missing_points = []

    for point in expected_points:
        if str(point) not in answer:
            missing_points.append(str(point))

    return missing_points


def evaluate_judge_expectation(case: dict, actual_passed: bool) -> tuple[bool, bool]:
    """
    判断 Judge 的实际结果是否符合该 case 的预期。

    返回：
    - expected_passed: 该 case 期望 judge 是否通过
    - test_passed: judge 结果是否符合预期
    """
    expected_passed = case.get("expected_judge_passed", True)
    test_passed = actual_passed == expected_passed

    return expected_passed, test_passed


def mock_judge_case(case: dict) -> dict:
    """
    Day45 mock judge。

    目的：
    - 跑通 answer quality eval 流程
    - 不调用真实 LLM
    - Day46 再替换为真实 LLM Judge
    """
    answer = case.get("answer", "")
    expected_points = case.get("expected_answer_points", [])
    missing_points = check_expected_points(answer, expected_points)

    scores = {
        "faithfulness": 1,
        "relevance": 1,
        "completeness": 1,
        "clarity": 1,
    }

    issues = []

    unsupported_reason_keywords = [
        "因为",
        "可能是因为",
        "原因是",
        "说明",
        "建议",
        "需要关注",
    ]

    if any(keyword in answer for keyword in unsupported_reason_keywords):
        scores["faithfulness"] = 0
        issues.append("answer contains unsupported causal or advisory statement")

    if not answer or "无法生成结构化业务回答" in answer:
        scores["relevance"] = 0
        scores["clarity"] = 0
        issues.append("answer is empty or fallback answer")

    if missing_points:
        scores["completeness"] = 0
        issues.append(
            {
                "missing_answer_points": missing_points
            }
        )

    passed = all(score == 1 for score in scores.values())
    expected_passed, test_passed = evaluate_judge_expectation(
        case=case,
        actual_passed=passed,
    )

    if passed:
        judge_reason = "回答忠实于上下文，直接回答问题，包含关键对象和值，表达清晰。"
    else:
        judge_reason = "回答存在质量问题，详见 issues。"

    return {
        "case_id": case["id"],
        "source_case_id": case.get("source_case_id"),
        "question": case["question"],
        "answer": answer,
        "mode": "mock",
        "judge_passed": passed,
        "expected_judge_passed": expected_passed,
        "passed": test_passed,
        "scores": scores,
        "issues": issues,
        "judge_reason": judge_reason,
    }


def llm_judge_case(case: dict) -> dict:
    """
    使用真实 LLM-as-Judge 评估 answer quality。
    """
    prompt = build_judge_prompt(case)

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            temperature=0,
        )

        raw_text = response.choices[0].message.content or ""
        cleaned_text = clean_judge_json_text(raw_text)
        payload = json.loads(cleaned_text)
        normalized = normalize_judge_payload(payload)

        scores = normalized["scores"]
        issues = normalized["issues"]
        judge_reason = normalized["judge_reason"]

        passed = all(score == 1 for score in scores.values())
        expected_passed, test_passed = evaluate_judge_expectation(
            case=case,
            actual_passed=passed,
        )

        return {
            "case_id": case["id"],
            "source_case_id": case.get("source_case_id"),
            "question": case["question"],
            "answer": case["answer"],
            "mode": "llm",
            "judge_passed": passed,
            "expected_judge_passed": expected_passed,
            "passed": test_passed,
            "scores": scores,
            "issues": issues,
            "judge_reason": judge_reason,
            "raw_judge_response": raw_text,
        }

    except Exception as e:
        return {
            "case_id": case["id"],
            "source_case_id": case.get("source_case_id"),
            "question": case["question"],
            "answer": case.get("answer", ""),
            "mode": "llm",
            "judge_passed": False,
            "expected_judge_passed": case.get("expected_judge_passed", True),
            "passed": case.get("expected_judge_passed", True) is False,
            "scores": {
                "faithfulness": 0,
                "relevance": 0,
                "completeness": 0,
                "clarity": 0,
            },
            "issues": [
                {
                    "reason": "llm judge failed",
                    "error": str(e),
                }
            ],
            "judge_reason": "LLM Judge 调用或 JSON 解析失败。",
            "raw_judge_response": None,
        }


def normalize_judge_payload(payload: dict) -> dict:
    """
    规范化 LLM Judge 返回结果。

    确保 scores 中包含固定四个维度。
    缺失或非法时默认判 0。
    """
    required_score_fields = [
        "faithfulness",
        "relevance",
        "completeness",
        "clarity",
    ]

    raw_scores = payload.get("scores", {})
    scores = {}

    for field in required_score_fields:
        value = raw_scores.get(field, 0)

        if value not in [0, 1]:
            value = 0

        scores[field] = value

    issues = payload.get("issues", [])

    if not isinstance(issues, list):
        issues = [str(issues)]

    judge_reason = payload.get("judge_reason", "")

    return {
        "scores": scores,
        "issues": issues,
        "judge_reason": judge_reason,
    }


def run_answer_eval(mode: str = "mock") -> list[dict]:
    """
    批量运行 answer quality evaluation。
    """
    results = []

    for case in ANSWER_EVAL_CASES:
        print(f"Judging: {case['id']} - {case['question']}")

        if mode == "llm":
            result = llm_judge_case(case)
        else:
            result = mock_judge_case(case)

        results.append(result)

        if result["passed"]:
            print("✅ PASSED")
        else:
            print("❌ FAILED")
            print(f"Issues: {result['issues']}")

        print("-" * 60)

    return results


def save_answer_eval_results(results: list[dict], mode: str = "mock") -> Path:
    """
    保存 answer eval 报告。
    """
    output_dir = Path("docs/evaluation")
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"answer_eval_{timestamp}.json"

    total = len(results)
    passed = sum(1 for item in results if item["passed"])
    failed = total - passed
    pass_rate = round(passed / total * 100, 2) if total else 0

    report = {
        "timestamp": timestamp,
        "mode": mode,
        "summary": {
            "total": total,
            "passed": passed,
            "failed": failed,
            "pass_rate": pass_rate,
        },
        "results": results,
    }

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    return output_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=["mock", "llm"],
        default="mock",
        help="Answer judge mode: mock or llm",
    )
    args = parser.parse_args()

    evaluation_results = run_answer_eval(mode=args.mode)

    total = len(evaluation_results)
    passed = sum(1 for item in evaluation_results if item["passed"])
    failed = total - passed
    pass_rate = round(passed / total * 100, 2) if total else 0

    output_path = save_answer_eval_results(
        results=evaluation_results,
        mode=args.mode,
    )

    print("\nAnswer Evaluation Summary")
    print(f"Mode: {args.mode}")
    print(f"Total: {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Pass Rate: {pass_rate}%")
    print(f"Saved to: {output_path}")