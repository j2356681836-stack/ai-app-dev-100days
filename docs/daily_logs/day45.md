# Day45 学习日志

## 今日主题

Phase2：Business Semantic Layer & Text-to-SQL

Day45：Answer Layer 加固 + Answer Quality Evaluation

今日实际完成原计划中的：
- Day45：Answer Layer 加固 + Ragas Feasibility Spike
- Day46：LLM-as-Judge Evaluation V1

由于今日已完成 Answer Quality Evaluation 的设计、case、mock judge、真实 LLM Judge 和负例验证，因此统一并入 Day45 记录。

---

## 今日学习目标

今天目标不是继续扩展 SQL case，而是让 Answer Layer 从“能生成中文回答”进一步升级为“能评估回答质量”。

重点问题：
- Answer Layer V1 的边界是什么？
- Ragas / LLM-as-Judge 评估什么？
- 它们和 deterministic evaluator 有什么区别？
- 如何验证 LLM Judge 不只是把正确答案判对，也能把错误答案判错？

---

## 完成内容一：Answer Layer V1 边界复查

测试问题：
- 哪个品类销量最高
- 哪个品类订单最多
- 哪个订单支付金额最高

测试结果：
哪个品类销量最高 → 品类销量排名第一的是：防晒 7260。
哪个品类订单最多 → 品类订单数排名第一的是：防晒 5157。
哪个订单支付金额最高 → 查询已完成，但暂时无法生成结构化业务回答。

结论：Answer Layer V1 当前主要服务 BI 聚合型问题。

当前稳定支持：
- category + refund_rate_pct
- category + sales_quantity
- category + order_count
- channel_name + channel_sales_amount
- channel_name + channel_refund_rate_pct
- channel_name + roi
- channel_name + cac

当前暂不重点支持：
- order_id + paid_amount
- product_id / product_name 明细结果
- customer_id 明细结果
- 一行多个指标
- 原因分析
- 策略建议
- 趋势解释

工程结论：Answer Layer V1 应优先稳定支持聚合型 BI 回答，不应为了覆盖 order_id 等明细字段而继续堆规则。明细型回答后续可作为 Answer Layer V2 单独设计。

---

## 完成内容二：Ragas / LLM-as-Judge 评估设计

新增文档：

docs/architecture/ragas_eval_design.md

文档明确：
- Ragas / LLM-as-Judge 不替代 deterministic evaluator
- deterministic evaluator 负责 SQL、数值、排序、intent、answer key points
- LLM-as-Judge 负责 answer quality
- 第一阶段采用 lightweight LLM-as-Judge
- Ragas 可作为后续对照实验或标准化评估框架

当前评估分层：
Deterministic Evaluator
↓
验证 SQL / result / rows / intent / answer key facts

LLM-as-Judge
↓
验证 answer faithfulness / relevance / completeness / clarity

---

## 完成内容三：Answer Eval Cases

新增文件：

app/evaluation/answer_eval_cases.py

当前 Answer Eval Cases：
- answer_case_001：哪个渠道销售额最高
- answer_case_002：品类退款率Top3
- answer_case_003：品类退款率从低到高排名
- answer_case_004：各渠道ROI排名
- answer_case_005：渠道ROI从低到高排名
- answer_case_006_bad：品类退款率Top3 错误回答负例

运行结果：Answer eval cases: 6
其中前 5 个为正例，第 6 个为负例。

---

## 完成内容四：Answer Judge V1

新增 / 扩展文件：app/evaluation/answer_judge.py

实现能力：
- build_judge_prompt
- clean_judge_json_text
- normalize_judge_payload
- mock_judge_case
- llm_judge_case
- run_answer_eval
- save_answer_eval_results
- 支持 --mode mock
- 支持 --mode llm
- 生成 answer_eval_*.json 报告

运行方式：
- python -m app.evaluation.answer_judge --mode mock
- python -m app.evaluation.answer_judge --mode llm

---

## 完成内容五：Mock Judge

mock judge 用于先跑通评估工程骨架。

它负责：
- 检查 expected_answer_points 是否都在 answer 中
- 检查 answer 是否为空
- 检查 answer 是否为 fallback
- 检查 answer 是否包含明显未支撑的因果 / 建议类词语

mock judge 运行结果：
Mode: mock
Total: 5
Passed: 5
Failed: 0
Pass Rate: 100.0%

---

## 完成内容六：真实 LLM-as-Judge

llm judge 使用 DeepSeek 作为 judge model。

实现流程：
answer_eval_cases
↓
build_judge_prompt
↓
DeepSeek Judge
↓
clean_judge_json_text
↓
json.loads
↓
normalize_judge_payload
↓
answer_eval report

LLM Judge 输出维度：
- faithfulness
- relevance
- completeness
- clarity

每个维度当前使用二值评分：
1 = 通过
0 = 不通过

正例测试结果：
Mode: llm
Total: 5
Passed: 5
Failed: 0
Pass Rate: 100.0%

---

## 完成内容七：负例测试

新增负例：answer_case_006_bad

负例 context：
精华 10.0
防晒 4.55
面膜 4.48

负例 answer：品类退款率Top3分别是：面霜 10.0%，洁面 4.55%，面膜 4.48%。

LLM Judge 判断：
```python
{
  "judge_passed": false,
  "expected_judge_passed": false,
  "passed": true,
  "scores": {
    "faithfulness": 0,
    "relevance": 1,
    "completeness": 0,
    "clarity": 1
  }
}
```

最终运行结果：
Mode: llm
Total: 6
Passed: 6
Failed: 0
Pass Rate: 100.0%

关键结论：负例被 Judge 判失败，但由于 expected_judge_passed = False，因此整体测试通过。

这说明：
- 测试通过 ≠ 所有 answer 都被 Judge 判通过
- 测试通过 = Judge 的判断符合预期

---

## 今日关键理解

### 1. Deterministic Evaluator 和 LLM Judge 不是替代关系

Deterministic Evaluator 负责：
- SQL 表是否正确
- SQL 字段是否正确
- 生成路径是否正确
- intent 是否正确
- result 是否正确
- rows 是否正确
- order 是否正确
- answer 是否包含关键事实点

LLM-as-Judge 负责：
- answer 是否忠实于 context
- answer 是否回答用户问题
- answer 是否完整
- answer 是否清晰
- answer 是否包含未被数据支撑的推断

---

### 2. 负例测试很重要

只有正例时，只能证明：正确答案能被判对
加入负例后，可以证明：错误答案能被判错

这让 answer_judge.py 不只是演示，而是更接近真正 evaluator。

---

### 3. 当前负例偏 deterministic，但仍然有价值

answer_case_006_bad 中对象名称错误，其实 deterministic evaluator 也可以通过expected_answer_points 检出。但它仍然适合作为 LLM Judge 的第一条负例，因为它验证了：LLM Judge 是否能识别 answer 与 context.rows 不一致。后续更有价值的负例应是：关键点都包含，但额外编造原因。

例如：
品类退款率Top3分别是：精华 10.0%，防晒 4.55%，面膜 4.48%。
精华退款率高可能是因为产品质量存在问题，建议立即整改。

这种情况 deterministic evaluator 可能通过，但 LLM Judge 应该判 faithfulness = 0。

当前技术债
- 当前是 lightweight LLM-as-Judge，不是正式 Ragas 接入。
- Judge 模型和 SQL 生成模型同为 DeepSeek，存在同源偏差。
- 当前评分是 0/1 二值评分，不够细腻。
- 当前 answer_eval_cases 只有 6 条，样本还小。
- 当前负例主要覆盖对象错误，还需要增加“编造原因型负例”。
- LLM Judge 返回 JSON 可能带 Markdown，需要 clean_judge_json_text 清洗。
- raw_judge_response 必须保留，方便排查 Judge 输出不稳定。
- Ragas 可后续作为对照实验，但不阻塞当前主线。

## 今日状态

Day45 已完成。

当前系统已具备：

自然语言问题
↓
SQL
↓
table
↓
answer
↓
deterministic evaluator
↓
LLM-as-Judge answer quality evaluator