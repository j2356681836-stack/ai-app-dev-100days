# Ragas Spike Report

## 背景

Day47 的目标是将项目从自研 Evaluation 体系，进一步对齐主流 AI Evaluation 工具。

在 Day45 之前，项目已经具备：

- deterministic evaluator
- expected_tables
- expected_columns
- expected_result
- expected_order
- expected_rows
- expected_intent
- expected_answer_points
- answer_eval_cases
- mock judge
- LLM-as-Judge
- positive / negative answer eval

本次目标不是替代现有 evaluator，而是完成：

answer_eval_cases.py
↓
Ragas-style dataset
↓
Ragas faithfulness evaluation
↓
ragas_eval report
↓

---

## 当前项目与 Ragas 的映射关系

Ragas 原生更常用于 RAG 场景，典型输入包括：
- user_input / question
- response / answer
- retrieved_contexts / contexts
- reference / ground_truth

当前项目不是传统文档 RAG，而是 Text-to-SQL AI Data Analyst。
因此本次采用如下映射：

用户问题 question
→ Ragas user_input / question

Answer Generator 输出 answer
→ Ragas response / answer

SQL 查询结果 table rows
→ Ragas retrieved_contexts / contexts

reference_answer
→ Ragas reference / ground_truth

也就是说，本次不是完整的文档 RAG Evaluation，而是：Ragas-style evaluation for Text-to-SQL grounded answers

目标是评估系统回答是否忠实于 SQL 查询结果。

---

## 实现文件

新增文件：`app/evaluation/ragas_eval.py`

输入数据来源：`app/evaluation/answer_eval_cases.py`

输出报告：
- `docs/evaluation/ragas_input_preview_*.json`
- `docs/evaluation/ragas_eval_*.json`

当前已生成报告：docs/evaluation/ragas_eval_20260623_144048.json

---

## ragas_eval.py 当前结构

当前 `ragas_eval.py` 分为五层。

### 1. 数据转换层

负责将 `answer_eval_cases.py` 转换成 Ragas 可使用的数据结构。

核心函数：
- `format_context_as_text`
- `case_to_ragas_sample`
- `build_ragas_samples`

其中最关键的映射是：context.rows → retrieved_contexts

例如：
查询结果字段：category, refund_rate_pct
第1行：category=精华, refund_rate_pct=10.0
第2行：category=防晒, refund_rate_pct=4.55
第3行：category=面膜, refund_rate_pct=4.48

---

### 2. Dataset 构建层

核心函数：`build_ragas_dataset`
负责将 Python list 转换为 Ragas 可评估的 dataset。
当前字段包括：
- `user_input`
- `response`
- `retrieved_contexts`
- `reference`

---

### 3. LLM 配置层

核心函数： `build_ragas_llm`
当前复用 DeepSeek 的 OpenAI-compatible API。
说明：Ragas 的 faithfulness 评估需要调用 LLM，因此每次运行通常需要联网，也会产生 API 调用成本。

---

### 4. Ragas 执行层

核心函数：`run_ragas_eval`
当前优先使用： `faithfulness`
暂未启用： `answer_relevancy`
原因：`answer_relevancy` 涉及 embedding 或额外模型配置，当前阶段优先跑通最小闭环。

---

### 5. 报告保存层

核心函数： `save_ragas_results`
输出到：docs/evaluation/ragas_eval_*.json

---

## 当前评估结果

本次共评估 6 个 answer eval cases：
answer_case_001：哪个渠道销售额最高
answer_case_002：品类退款率Top3
answer_case_003：品类退款率从低到高排名
answer_case_004：各渠道ROI排名
answer_case_005：渠道ROI从低到高排名
answer_case_006_bad：品类退款率Top3 错误回答负例

Ragas faithfulness 结果：
answer_case_001：0.5
answer_case_002：0.75
answer_case_003：1.0
answer_case_004：1.0
answer_case_005：1.0
answer_case_006_bad：0.25

---

## 结果分析

### answer_case_001：faithfulness = 0.5

问题：哪个渠道销售额最高
回答：渠道销售额排名第一的是：天猫 2445170.92。

context 中只有一行：channel_name=天猫, channel_sales_amount=2445170.92

Ragas 可能将回答拆成两个 claim：
1. 天猫的销售额是 2445170.92。
2. 天猫是销售额排名第一的渠道。

context 能支持第 1 个 claim，但由于只包含 top1 结果，没有其他渠道用于比较，因此 Ragas 可能认为“排名第一”缺少完整比较上下文。因此 faithfulness 不是 1.0。

结论：Top1 问题如果只给 Ragas top1 row，它可能无法完全验证“最高 / 第一”这类排序声明。

---

### answer_case_002：faithfulness = 0.75

问题：品类退款率Top3
回答：品类退款率Top3分别是：精华 10.0%，防晒 4.55%，面膜 4.48%。


context 中包含前三行：
精华 10.0
防晒 4.55
面膜 4.48

Ragas 能确认具体品类和值都来自 context，但 “Top3” 本身需要证明这些品类确实是全量候选中的前三。
由于 context 只包含 Top3 rows，而不是所有品类，因此 Ragas 可能认为 Top3 claim 缺少完整比较依据。

结论：TopN 问题中，Ragas 更适合验证回答事实是否来自 context，不一定适合单独验证排名正确性。

---

### answer_case_003 / 004 / 005：faithfulness = 1.0

这些 case 的 context 包含完整排名结果：
- 品类退款率从低到高排名
- 各渠道 ROI 排名
- 渠道 ROI 从低到高排名

回答中的对象、数值和顺序都能从 context 中找到。因此 Ragas 给出 1.0。
结论：Ragas 对完整排名类结果适配较好。

---

### answer_case_006_bad：faithfulness = 0.25

这是负例。

context：
精华 10.0
防晒 4.55
面膜 4.48

回答：品类退款率Top3分别是：面霜 10.0%，洁面 4.55%，面膜 4.48%。

回答中的“面霜”和“洁面”不存在于 context.rows，因此 Ragas 给出较低的 faithfulness 分数。

结论：Ragas 能识别明显不忠实于 context 的回答。

---

## Ragas 与 answer_judge.py 的对比

### answer_judge.py

当前自研 Judge 具备：
- mock mode
- llm mode
- faithfulness
- relevance
- completeness
- clarity
- expected_judge_passed
- positive / negative cases
- pass / fail 结果

优点：
1. 更贴合当前业务语义。
2. 可直接判断 case 是否通过。
3. 可以配合 expected_judge_passed 做负例测试。
4. Prompt 和 rubric 完全可控。
5. 适合项目内部回归测试。

限制：
1. 自研标准不够通用。
2. 与主流工具链对齐不足。
3. Judge 输出受自定义 prompt 影响较大。

---

### Ragas

当前接入能力：
- faithfulness metric
- Ragas-style dataset
- Ragas evaluation report
- 正例 / 负例对比

优点：
1. 属于主流 LLM Evaluation 工具。
2. 分数是连续值，不只是 pass / fail。
3. 能从 claim-level 角度评估回答是否被 context 支撑。
4. 可作为自研 Judge 的标准化对照。

限制：
1. 运行较慢，因为需要调用 LLM。
2. 通常需要联网和 API 成本。
3. 对 Top1 / TopN 这类截断结果，可能认为排序 claim 缺少完整比较上下文。
4. 当前项目不是传统文档 RAG，因此需要将 SQL table rows 映射为 retrieved_contexts。
5. 不适合替代 deterministic evaluator。

---

## 当前评估分层

最终 Evaluation 分层如下：

第一层：Deterministic Evaluator
负责 SQL / table / result / rows / intent / answer key facts

第二层：Prompt Builder Tests
负责 Prompt 静态结构与关键规则检查

第三层：answer_judge.py
负责项目内 answer quality pass / fail 判断

第四层：Ragas
负责标准化 LLM Evaluation 对照

各层职责：

SQL 表是否正确？
→ deterministic evaluator

SQL 字段是否正确？
→ deterministic evaluator

结果数值是否正确？
→ deterministic evaluator

排序是否正确？
→ deterministic evaluator expected_order / expected_rows

Prompt 中关键规则是否还存在？
→ prompt_builder_tests

回答是否包含关键事实？
→ expected_answer_points

回答是否忠实、相关、完整、清晰？
→ answer_judge.py

回答是否被 context 支撑？
→ Ragas faithfulness

---

## 为什么 Ragas 不适合每次开发都跑

Ragas faithfulness 需要调用 LLM，因此：
- 速度较慢
- 需要联网
- 有 API 成本
- 分数可能存在轻微波动
- 不适合作为每次小改动后的快速回归测试

建议使用方式：

日常开发：
- prompt_builder_tests.py
- evaluator.py
- answer_judge.py --mode mock

阶段性评估：
- answer_judge.py --mode llm
- ragas_eval.py

也就是说，Ragas 更适合版本评估、阶段总结、简历展示和关键回归，而不是每次代码修改都运行。

---

## Ragas 版本与依赖问题记录

Day47 接入 Ragas 时曾遇到依赖兼容问题。

尝试过：
- `ragas==0.4.3`
- `ragas==0.4.2`
- `ragas==0.4.1`
- `ragas==0.4.0`
- `ragas==0.3.9`

多次遇到：ModuleNotFoundError: No module named 'langchain_community.chat_models.vertexai'

原因：Ragas 与 LangChain 生态之间存在版本兼容问题。当前 LangChain 生态中 VertexAI 集成已经迁移到新的包路径，而部分 Ragas / LangChain 组合仍尝试导入旧路径。

最终解决方式：
- 清理冲突的 LangChain 相关依赖
- 重新安装兼容组合
- 成功恢复 `import ragas`
- 当前运行版本为 `ragas==0.4.3`

该问题说明：AI 工具链版本变化快，Ragas / LangChain 这类工具不仅要会用，还要理解依赖版本管理和兼容性排查。

---

## 当前技术债

1. 当前只启用了 `faithfulness`，尚未启用 `answer_relevancy`。
2. 当前将 SQL table rows 映射为 `retrieved_contexts`，不是传统文档 RAG。
3. Top1 / TopN 的 ranking claim 可能需要更完整的 comparison context 才能获得更高 Ragas 分数。
4. Ragas 运行较慢，不适合作为日常快速测试。
5. 后续可以尝试使用 Ragas 0.4.x 更推荐的 LLM wrapper 或 experiment workflow。
6. 可以考虑将 `ragas_eval.py` 增加 `--include-negative` 参数。
7. 可以考虑将 `ragas_eval.py` 增加 `--metrics` 参数，支持 faithfulness / answer_relevancy 切换。

---

## 当前结论

Ragas 已成功接入当前 AI Data Analyst 项目。

当前价值：
1. 对齐主流 LLM Evaluation 工具。
2. 能和自研 answer_judge.py 形成对照。
3. 帮助理解 faithfulness、grounded answer、retrieved_contexts 等主流评估概念。
4. 暴露了 Text-to-SQL 场景下使用 Ragas 的适配边界。

最终结论：
1. Ragas 不替代当前 deterministic evaluator；
2. Ragas 作为标准化 LLM Evaluation 工具，用于阶段性评估和简历展示。

---

## Ragas vs answer_judge

| 维度               | answer_judge.py                          | Ragas faithfulness                                                              |
| ---------------- | ---------------------------------------- | ------------------------------------------------------------------------------- |
| 评估定位             | 项目内自研 Answer Quality Judge               | 主流 LLM Evaluation 工具                                                            |
| 输入               | question、context、answer、reference、rubric | question / user_input、answer / response、contexts / retrieved_contexts、reference |
| 输出               | pass / fail + 四维 0/1 分                   | 连续分数，例如 0.25、0.5、0.75、1.0                                                       |
| 主要判断             | 是否忠实、相关、完整、清晰                            | answer claims 是否被 contexts 支撑                                                   |
| 是否支持负例预期         | 支持 `expected_judge_passed`               | 默认不直接支持，需要自己解释阈值                                                                |
| 对业务规则适配          | 高，可按项目 rubric 定制                         | 默认偏通用 RAG，需要适配 Text-to-SQL                                                      |
| 对 TopN / Ranking | 可以按项目规则判定                                | 对截断 TopK context 较敏感                                                            |
| 速度               | mock 很快，llm 模式较慢                         | 较慢，需要调用 LLM                                                                     |
| 成本               | mock 无成本，llm 有成本                         | 有 LLM API 成本                                                                    |
| 适合用途             | 日常回归、正负例测试                               | 阶段性评估、标准化对照、简历展示                                                                |
| 局限               | 自研标准，不够通用                                | 默认指标不完全适配 Text-to-SQL 排名语义                                                      |

---

## Ragas 分数解释策略

当前项目不直接使用 Ragas faithfulness 作为 pass / fail。

解释策略：
- `faithfulness >= 0.8`：高度忠实
- `0.5 <= faithfulness < 0.8`：部分忠实，需要结合问题类型解释
- `faithfulness < 0.5`：存在明显不忠实风险

注意：Top1 / TopN 类问题如果 context 只包含截断后的 TopK rows，Ragas 可能无法完全验证“最高”“Top3”等排序 claim，因此不能单独据此判定 answer 错误。

在当前 Text-to-SQL 项目中：
- 排序正确性由 `evaluator.py` 的 `expected_order` / `expected_rows` 负责。
- 回答关键事实由 `expected_answer_points` 和 `answer_judge.py` 负责。
- Ragas faithfulness 用于阶段性检查回答是否被 SQL result context 支撑。

因此，Ragas 不替代 deterministic evaluator，而是作为标准化 LLM Evaluation 对照。

---

## Context Enhancement 实验

在第一次 Ragas faithfulness 评估中，Top1 / Top3 类问题的分数偏低：
answer_case_001：0.5
answer_case_002：0.75
answer_case_003：1.0
answer_case_004：1.0
answer_case_005：1.0
answer_case_006_bad：0.25

分析后发现，原因不是 answer 本身错误，而是 Ragas 默认只看到 SQL 查询后的最终 rows，无法理解这些 rows 是通过 `ORDER BY` / `LIMIT` 得到的 TopN / Ranking 结果。

因此在 `ragas_eval.py` 中增强了 `retrieved_contexts` 的构造方式：
用户问题：品类退款率Top3
查询语义说明：该上下文来自 SQL 查询结果表，而不是普通文档片段。回答应只基于查询结果表中的字段和值。
用户问题要求 Top3，查询结果表示 SQL 排序后返回的前三行。
查询结果字段：category, refund_rate_pct
第1行：category=精华, refund_rate_pct=10.0
第2行：category=防晒, refund_rate_pct=4.55

增强后再次运行：python -m app.evaluation.ragas_eval --include-negative

结果变为：
answer_case_001：1.0
answer_case_002：1.0
answer_case_003：1.0
answer_case_004：1.0
answer_case_005：1.0
answer_case_006_bad：0.25

结论：在 Text-to-SQL 场景中，Ragas 的效果不仅取决于 metric 本身，也取决于 retrieved_contexts 如何构造。

对于 SQL 查询结果，不能只把 rows 当成普通文本传给 Ragas，还需要补充查询语义，例如：
- 该 context 来自 SQL 查询结果
- 行顺序代表排名顺序
- TopN rows 是排序后返回的前 N 行

这种 context enhancement 可以让 Ragas 更准确地评估回答是否忠实于 SQL 查询结果，同时不会把明显错误的负例误判为正确。
