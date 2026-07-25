import json
import os
import argparse
from datetime import datetime
from pathlib import Path

from datasets import Dataset
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from ragas import evaluate
from ragas.metrics import faithfulness

from app.evaluation.answer_eval_cases import ANSWER_EVAL_CASES


load_dotenv()

DEEPSEEK_MODEL = os.getenv(
    "DEEPSEEK_MODEL",
    "deepseek-v4-pro",
).strip()

if not DEEPSEEK_MODEL:
    raise RuntimeError(
        "DEEPSEEK_MODEL cannot be empty."
    )

RAGAS_FAITHFULNESS_THRESHOLD = 0.8

def infer_query_semantics(question: str) -> str:
    """
    根据用户问题生成简短的查询语义说明。

    目的：
    让 Ragas 知道当前 contexts 来自 SQL 查询结果，
    并理解 TopN / Ranking / Top1 这类结果的排序语义。

    注意：
    这里只做解释性增强，不改变 SQL 或 answer。
    """
    semantics = [
        "该上下文来自 SQL 查询结果表，而不是普通文档片段。",
        "回答应只基于查询结果表中的字段和值。",
    ]

    if "从低到高" in question or "升序" in question:
        semantics.append("该查询结果已按用户要求从低到高排序。")
    elif "从高到低" in question or "降序" in question:
        semantics.append("该查询结果已按用户要求从高到低排序。")
    elif "最低" in question or "最少" in question or "最小" in question:
        semantics.append("该查询结果用于回答最低/最少/最小类问题，结果代表排序后的靠前记录。")
    elif "最高" in question or "最多" in question or "最大" in question or "第一" in question:
        semantics.append("该查询结果用于回答最高/最多/最大/第一类问题，结果代表排序后的第一条记录。")

    if "Top3" in question or "top3" in question or "前三" in question or "前3" in question:
        semantics.append("用户问题要求 Top3，查询结果表示 SQL 排序后返回的前三行。")
    elif "Top5" in question or "top5" in question or "前五" in question or "前5" in question:
        semantics.append("用户问题要求 Top5，查询结果表示 SQL 排序后返回的前五行。")
    elif "Top" in question or "top" in question:
        semantics.append("用户问题要求 TopN，查询结果表示 SQL 排序后返回的前 N 行。")

    if "排名" in question or "排行" in question or "排序" in question:
        semantics.append("用户问题要求排名，查询结果中的行顺序表示排名顺序。")

    return "\n".join(semantics)


def format_context_as_text(
    context: dict,
    question: str = "",
) -> str:
    """
    将 SQL 查询结果 context 转成 Ragas 可使用的文本上下文。

    当前项目不是传统文档 RAG。
    这里把 SQL table rows 映射为 retrieved_contexts，
    用于评估 answer 是否忠实于查询结果。

    Day47 增强：
    将 query semantics 一起写入 context，
    让 Ragas 更好理解 Top1 / TopN / Ranking 类问题。
    """
    columns = context.get("columns", [])
    rows = context.get("rows", [])

    lines = []

    if question:
        lines.append(f"用户问题：{question}")

    lines.append("查询语义说明：")
    lines.append(infer_query_semantics(question))

    if columns:
        lines.append("查询结果字段：" + ", ".join(columns))

    for index, row in enumerate(rows, start=1):
        row_text = ", ".join(
            f"{key}={value}"
            for key, value in row.items()
        )
        lines.append(f"第{index}行：{row_text}")

    return "\n".join(lines)


def case_to_ragas_sample(case: dict) -> dict:
    """
    将 answer_eval_case 转换为 Ragas 风格样本。

    字段说明：
    - question：用户问题
    - answer：系统回答
    - contexts：SQL table rows 转换后的上下文
    - ground_truth：参考回答
    """
    context_text = format_context_as_text(
        context=case.get("context", {}),
        question=case["question"],
    )

    return {
        "case_id": case["id"],
        "source_case_id": case.get("source_case_id"),
        "question": case["question"],
        "answer": case["answer"],
        "contexts": [context_text],
        "ground_truth": case.get("reference_answer", ""),
        "expected_judge_passed": case.get("expected_judge_passed", True),
    }


def build_ragas_samples(include_negative: bool = False) -> list[dict]:
    """
    构建 Ragas 风格评估数据。

    默认只使用正例。
    """
    samples = []

    for case in ANSWER_EVAL_CASES:
        expected_passed = case.get("expected_judge_passed", True)

        if not include_negative and expected_passed is False:
            continue

        samples.append(case_to_ragas_sample(case))

    return samples


def build_ragas_dataset(samples: list[dict]) -> Dataset:
    """
    转换为 HuggingFace Dataset。

    Ragas evaluate 主要使用：
    - question
    - answer
    - contexts
    - ground_truth
    """
    return Dataset.from_list(
        [
            {
                "question": sample["question"],
                "answer": sample["answer"],
                "contexts": sample["contexts"],
                "ground_truth": sample["ground_truth"],
            }
            for sample in samples
        ]
    )


def build_ragas_llm() -> ChatOpenAI:
    """
    构建 Ragas 使用的 LLM。

    这里复用 DeepSeek 的 OpenAI-compatible API。
    """
    return ChatOpenAI(
        model=DEEPSEEK_MODEL,
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url=os.getenv("DEEPSEEK_BASE_URL"),
        temperature=0,
    )


def build_ragas_embeddings() -> OpenAIEmbeddings:
    """
    构建 Ragas 使用的 embedding。

    注意：
    如果当前没有可用的 OpenAI embedding API key，
    answer_relevancy 可能会失败。
    第一阶段可先跑 faithfulness。
    """
    return OpenAIEmbeddings(
        api_key=os.getenv("OPENAI_API_KEY"),
        model="text-embedding-3-small",
    )


def run_ragas_eval(samples: list[dict]) -> list[dict]:
    """
    运行 Ragas evaluation。

    第一版先跑 faithfulness。
    answer_relevancy 依赖 embeddings，如果环境未配置 OPENAI_API_KEY，
    可先注释掉 answer_relevancy。
    """
    dataset = build_ragas_dataset(samples)
    llm = build_ragas_llm()

    result = evaluate(
        dataset=dataset,
        metrics=[
            faithfulness,
            # answer_relevancy,
        ],
        llm=llm,
    )

    result_rows = result.to_pandas().to_dict(orient="records")
    
    results = []

    for sample, row in zip(samples, result_rows):
        ragas_scores = {
            "faithfulness": row.get("faithfulness"),
        }

        expectation = evaluate_ragas_expectation(
            sample=sample,
            ragas_scores=ragas_scores,
        )

        results.append(
            {
                "case_id": sample["case_id"],
                "source_case_id": sample.get("source_case_id"),
                "question": sample["question"],
                "answer": sample["answer"],
                "contexts": sample["contexts"],
                "ground_truth": sample["ground_truth"],
                "expected_judge_passed": sample.get("expected_judge_passed", True),
                "ragas_scores": ragas_scores,
                "ragas_expectation": expectation,
            }
        )

    return results


def evaluate_ragas_expectation(
    sample: dict,
    ragas_scores: dict,
) -> dict:
    """
    根据 Ragas faithfulness 分数判断是否符合 case 预期。

    注意：
    Ragas 默认只输出连续分数，不知道正例 / 负例预期。
    这里使用项目内阈值，将 faithfulness 转换成 ragas_passed，
    再与 expected_judge_passed 对齐。
    """
    faithfulness_score = ragas_scores.get("faithfulness", 0)

    ragas_passed = faithfulness_score >= RAGAS_FAITHFULNESS_THRESHOLD
    expected_passed = sample.get("expected_judge_passed", True)

    expectation_passed = ragas_passed == expected_passed

    return {
        "faithfulness_threshold": RAGAS_FAITHFULNESS_THRESHOLD,
        "faithfulness_score": faithfulness_score,
        "ragas_passed": ragas_passed,
        "expected_passed": expected_passed,
        "expectation_passed": expectation_passed,
    }

    
def save_ragas_results(results: list[dict],include_negative: bool = False,) -> Path:
    """
    保存 Ragas 评估结果。
    """
    output_dir = Path("docs/evaluation")
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"ragas_eval_{timestamp}.json"

    report = {
        "timestamp": timestamp,
        "include_negative": include_negative,
        "total": len(results),
        "results": results,
    }

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    return output_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--include-negative",
        action="store_true",
        help="Include negative answer eval cases in Ragas evaluation.",
    )

    args = parser.parse_args()

    samples = build_ragas_samples(
        include_negative=args.include_negative,
    )

    print()
    print("=" * 80)
    print("Ragas Evaluation")
    print("=" * 80)
    print(f"Include negative cases: {args.include_negative}")

    results = run_ragas_eval(samples)
    output_path = save_ragas_results(
        results=results,
        include_negative=args.include_negative,
    )

    for result in results:
        print(result["case_id"], "-", result["question"])
        print("scores:", result["ragas_scores"])
        print("expectation:", result["ragas_expectation"])
        print("-" * 80)

    expectation_passed_count = sum(
        1
        for result in results
        if result["ragas_expectation"]["expectation_passed"]
    )

    print()
    print(f"Total: {len(results)}")
    print(f"Ragas expectation passed: {expectation_passed_count}/{len(results)}")
    print(f"Saved to: {output_path}")
