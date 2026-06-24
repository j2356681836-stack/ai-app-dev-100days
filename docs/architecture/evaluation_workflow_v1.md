# Evaluation Workflow V1

## 背景

当前项目不是只追求“能生成 SQL”，而是要证明：
SQL 是否正确
查询结果是否正确
排序是否正确
用户意图是否被正确理解
中文回答是否忠实于结果
回答是否存在幻觉

因此 Phase2 逐步形成了 Evaluation Workflow V1。

当前 Evaluation 不是单层判断，而是多层分工：
Deterministic Evaluator
Prompt Builder Tests
Answer Judge
Ragas Evaluation

---

## 当前 Evaluation 总览

Question
↓
Text-to-SQL Pipeline
↓
SQL
↓
PostgreSQL Result Table
↓
Answer
↓
Evaluation Workflow

当前评估命令：
python -m app.evaluation.evaluator
python -m app.evaluation.answer_judge --mode mock
python -m app.evaluation.ragas_eval --include-negative

当前稳定结果：
evaluator.py：26/26 PASS
answer_judge.py --mode mock：6/6 PASS
ragas_eval.py --include-negative：6/6 expectation passed

---

## 1. Deterministic Evaluator

对应文件：
app/evaluation/evaluator.py
app/evaluation/golden_questions.py

### 评估目标

Deterministic Evaluator 负责检查系统输出中的确定性部分。

当前支持：
expected_tables
expected_columns
expected_result
expected_order
expected_rows
expected_generation_method
expected_intent
expected_answer_points

### 负责什么

Deterministic Evaluator 主要负责：
SQL 是否用了正确的表
SQL 是否输出了正确字段
Top1 结果是否正确
Ranking 顺序是否正确
多行结果值是否正确
SQL 生成路径是否正确
Intent 是否符合预期
Answer 是否包含关键事实点

### 示例

对于问题：品类退款率Top3

不仅要检查 SQL 结构，还要检查：
第1行：精华 10.0
第2行：防晒 4.55
第3行：面膜 4.48

这类结果由：expected_rows

负责。

### 为什么需要 Deterministic Evaluator

因为 SQL / 数值 / 排序是可以确定验证的，不应该交给 LLM 模糊判断。

例如：
天猫是否是渠道销售额第一
ROI 排序是否正确
退款率数值是否为 10.0
CAC 是否走 template

这些都应该用规则和标准答案校验。

### 当前结果

Golden Questions：26
evaluator.py：26/26 PASS
Pass Rate：100%

---

## 2. Prompt Builder Tests

对应文件：
app/evaluation/prompt_builder_tests.py
app/text_to_sql/prompt_builder.py

### 评估目标

Prompt Builder Tests 负责检查 Prompt Builder V2 的关键规则是否还存在。

当前检查内容包括：
Intent Context 注入
Dimension 规则
Ranking 规则
Field Alias 规则
ROI / CAC legacy rules

### 为什么需要 Prompt Builder Tests

Prompt 是 Text-to-SQL 中非常容易被改坏的部分。

Day46 的经验说明：Prompt Builder 代码模块化后，即使静态测试通过，也可能因为最终 prompt 输出形态变化导致 LLM 行为变化。

曾经出现的问题：AND r.refund_status = 'paid'

这是 LLM 编造的状态值，导致退款率结果错误。

最终增加规则：
不要编造字段、表名、状态值或枚举值。
不得自行假设 order_status、refund_status、channel_name、category 等字段的取值。
只能使用业务上下文中明确给出的 filters。

### Prompt Builder Tests 的边界

Prompt Builder Tests 只能检查：
关键 prompt 片段是否存在
关键规则是否丢失

它不能证明：LLM 一定会生成正确 SQL
所以 Prompt Builder Tests 必须和端到端 `evaluator.py` 配合。

### 当前结果

prompt_builder_tests.py：5/5 PASS

---

## 3. Answer Judge

对应文件：
app/evaluation/answer_eval_cases.py
app/evaluation/answer_judge.py

### 评估目标

Answer Judge 负责评估中文回答质量。

当前评估维度：
faithfulness
relevance
completeness
clarity

当前支持：
mock judge
LLM-as-Judge
positive cases
negative cases
expected_judge_passed
raw_judge_response
answer_eval JSON report

### 为什么需要 Answer Judge

Deterministic Evaluator 可以检查关键事实点是否出现，但很难判断完整回答质量。

例如：
回答是否忠实于表格结果
回答是否回答了用户问题
回答是否遗漏关键信息
回答是否编造了原因

这些更适合由 Judge 评估。

### 正例 / 负例机制

当前 answer eval cases 包含：
5 个正例
1 个负例

负例示例：

正确 context：
精华 10.0
防晒 4.55
面膜 4.48

错误 answer：
面霜 10.0
洁面 4.55
面膜 4.48

该 case 的预期是：expected_judge_passed = False

也就是说：
Judge 判它失败
→ 测试通过


### mock judge 与 LLM-as-Judge 的分工

mock judge：
速度快
稳定
无 API 成本
适合日常回归

LLM-as-Judge：
更接近真实语义判断
有 API 成本
可能有波动
适合阶段性验证

当前日常推荐：python -m app.evaluation.answer_judge --mode mock

阶段性验证可以使用：python -m app.evaluation.answer_judge --mode llm

### 当前结果

answer_eval_cases：6
answer_judge.py --mode mock：6/6 PASS
answer_judge.py --mode llm：6/6 PASS


---

## 4. Ragas Evaluation

对应文件：
app/evaluation/ragas_eval.py
docs/architecture/ragas_spike_report.md


### 评估目标

Ragas Evaluation 负责引入主流 LLM Evaluation 工具，作为标准化对照。

当前使用指标：faithfulness

当前输入映射：
question → user_input
answer → response
SQL result context.rows → retrieved_contexts
reference_answer → reference

### 为什么需要 Ragas

自研 Answer Judge 贴合项目，但不够标准化。

Ragas 的价值是：
对齐主流 LLM Evaluation 工具
提供标准化 faithfulness 评分
帮助面试表达 groundedness / claim support
作为自研 Judge 的外部对照

### Ragas 在 Text-to-SQL 中的适配问题

Ragas 默认更适合传统 RAG。

当前项目是 Text-to-SQL，因此 context 不是普通文档，而是 SQL 查询结果。
如果只把 SQL rows 传给 Ragas，Top1 / TopN / Ranking 问题可能得分偏低。

原因：
Ragas 只看到最终 rows
不知道这些 rows 是通过 ORDER BY / LIMIT 得到的结果
无法完整验证“最高”“Top3”“排名”这类 claim

初始结果：
answer_case_001：0.5
answer_case_002：0.75
answer_case_003：1.0
answer_case_004：1.0
answer_case_005：1.0
answer_case_006_bad：0.25

### Context Enhancement

为了解决这个问题，`ragas_eval.py` 增强了 `retrieved_contexts`。

新增 query semantics：
该上下文来自 SQL 查询结果表，而不是普通文档片段。
回答应只基于查询结果表中的字段和值。
用户问题要求 Top3，查询结果表示 SQL 排序后返回的前三行。
排名类问题中，查询结果中的行顺序表示排名顺序。

增强后结果：
answer_case_001：1.0
answer_case_002：1.0
answer_case_003：1.0
answer_case_004：1.0
answer_case_005：1.0
answer_case_006_bad：0.25

结论：
context enhancement 提升了正例评分；
负例仍保持低分；
说明增强让 Ragas 更理解 SQL result semantics，没有导致明显误判。

### Threshold-based Expectation Check

Ragas 默认只输出分数，不知道正例 / 负例预期。

因此当前项目增加阈值判断：
faithfulness >= 0.8 → ragas_passed = True
faithfulness < 0.8 → ragas_passed = False

再与：expected_judge_passed

对齐：expectation_passed = ragas_passed == expected_passed

当前结果：ragas_eval.py --include-negative：6/6 expectation passed

### Ragas 的边界

Ragas 不负责：
SQL 是否正确
排序是否正确
数值是否正确
业务指标口径是否正确

这些仍然由 deterministic evaluator 负责。

Ragas 负责：answer 是否被 context 支撑
也就是 groundedness / faithfulness 对照评估。

---

## Evaluation 分层总结

当前系统的评估分工：
SQL 表、字段、结果、排序、intent
→ Deterministic Evaluator

Prompt 关键规则是否保留
→ Prompt Builder Tests

Answer 是否忠实、相关、完整、清晰
→ Answer Judge

Answer claims 是否被 context 支撑
→ Ragas Evaluation

更简化地说：
SQL 对不对
→ evaluator.py

Prompt 有没有被改坏
→ prompt_builder_tests.py

回答质量对不对
→ answer_judge.py

回答是否有外部标准化 groundedness 对照
→ ragas_eval.py

---

## 为什么不是只用一种 Evaluation

### 不能只用 deterministic evaluator

它适合检查确定事实，但不擅长语义质量判断。

例如：
回答是否自然
是否完整回答问题
是否存在隐性幻觉

这些需要 Judge。

### 不能只用 LLM-as-Judge

LLM Judge 不适合判断精确数值、排序和 SQL 结构。

例如：
第三行退款率是否是 4.48
ROI 是否按正确方向排序
SQL 是否使用了正确表

这些应该由 deterministic evaluator 负责。

### 不能只用 Ragas

Ragas 默认更适合传统 RAG。
在 Text-to-SQL 中，如果 context 构造不合理，Ragas 会低估 TopN / Ranking 类回答。
因此 Ragas 是对照工具，不是唯一裁判。

---

## 日常开发推荐流程

日常小改动：
python -m app.evaluation.evaluator
python -m app.evaluation.answer_judge --mode mock

涉及 Prompt 改动：
python -m app.evaluation.prompt_builder_tests
python -m app.evaluation.evaluator

涉及 Answer / Evaluation 改动：
python -m app.evaluation.answer_judge --mode mock
python -m app.evaluation.ragas_eval --include-negative

阶段性回归：
python -m app.evaluation.evaluator
python -m app.evaluation.prompt_builder_tests
python -m app.evaluation.answer_judge --mode mock
python -m app.evaluation.answer_judge --mode llm
python -m app.evaluation.ragas_eval --include-negative

---

## 当前 Evaluation Workflow 的价值

当前 Evaluation Workflow V1 的价值是：
1. 能发现 SQL 结构错误
2. 能发现结果数值错误
3. 能发现排序错误
4. 能发现 intent 理解错误
5. 能发现 Prompt 回归
6. 能发现 answer 关键事实缺失
7. 能验证 answer 正例和负例
8. 能用 Ragas 做标准化 groundedness 对照

这使项目从：能生成 SQL
升级为：能评估 SQL 和回答质量

---

## 面试表达版本

可以这样解释 Evaluation Workflow：我没有只靠肉眼看 SQL 是否正确，而是做了分层 Evaluation。

第一层是 deterministic evaluator，用 Golden Questions 检查 SQL 表、字段、结果值、排序、生成路径和 intent。比如 expected_rows 可以验证 TopN 结果中的每一行对象和值。

第二层是 Answer Judge，用 mock 和 LLM-as-Judge 评估回答是否忠实、相关、完整、清晰，并支持正负例测试。这样不仅能证明正确回答能通过，也能证明错误回答会被判错。

第三层是 Ragas Evaluation。我把 SQL 查询结果 rows 映射为 retrieved_contexts，用 Ragas faithfulness 做标准化 groundedness 对照。因为项目是 Text-to-SQL，不是传统 RAG，所以我还补充了 query semantics，让 Ragas 理解 TopN 和 Ranking 结果来自 SQL 的 ORDER BY / LIMIT。

---

## 当前边界与后续方向

当前边界：
1. Golden Questions 只有 26 条，覆盖范围仍有限。
2. Answer Eval Cases 只有 6 条，样本较少。
3. Ragas 当前只接入 faithfulness。
4. Ragas 运行较慢，不适合作为每次小改动的快速测试。
5. LLM-as-Judge 当前使用 DeepSeek，与 SQL 生成模型同源，存在 judge bias 风险。

后续方向：
1. 扩展 Golden Dataset。
2. 增加更多负例类型，例如编造原因型负例。
3. 尝试 Ragas answer_relevancy。
4. 在 Phase3 LangGraph 中引入 eval-driven retry / repair loop。
5. 将 Evaluation Workflow 接入更完整的 Agent 工作流。