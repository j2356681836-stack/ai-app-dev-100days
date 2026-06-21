# Ragas / LLM-as-Judge Evaluation Design

## 1. 背景

当前 AI-Architect-100Days 项目已经完成从自然语言问题到中文业务回答的基础链路。

当前主链路：
Question
↓
Intent Parser
↓
Intent Resolver
↓
Hybrid Search / Metric Recognition
↓
Query Plan Routing
├─ ROI / CAC → Template SQL
└─ 普通指标 → LLM SQL with Intent Context
↓
SQL Cleaner
↓
SQL Validator
↓
PostgreSQL
↓
Result Formatter
↓
Answer Generator
↓
Evaluator

当前 evaluator 已支持：
- expected_tables
- expected_columns
- expected_result
- expected_order
- expected_rows
- expected_generation_method
- expected_intent
- expected_answer_points

这些能力可以验证：
- SQL 是否使用正确表
- SQL 是否包含正确字段
- SQL 生成路径是否正确
- 用户 intent 是否解析正确
- 结果数值是否正确
- 排名顺序是否正确
- 多行结果是否正确
- 中文回答是否包含关键事实点

但是 deterministic evaluator 仍然无法充分评估：
- 中文回答是否自然
- 中文回答是否完整
- 中文回答是否真正回答了用户问题
- 中文回答是否忠实于 table
- 中文回答是否存在语义误导
- 中文回答是否有未经数据支撑的推断
因此需要引入 Answer Quality Evaluation。

---

## 2. 为什么需要双层评估

本项目不使用 Ragas / LLM-as-Judge 替代现有 evaluator。原因是二者评估对象不同。

### 2.1 Deterministic Evaluator

负责验证确定性事实。

包括：
- SQL 表结构
- SQL 字段
- 生成路径
- intent
- result
- rows
- order
- answer key points

适合回答：
- SQL 用没用对表？
- 字段有没有漂移？
- 第一行结果对不对？
- 多行数值对不对？
- 排序顺序对不对？
- answer 有没有包含关键对象和数值？

优势：
- 速度快
- 成本低
- 可重复
- 结果稳定
- 适合 CI / 回归测试

不足：
- 不理解自然语言质量
- 不判断回答是否自然
- 不判断回答是否完整
- 不判断回答是否语义相关
- 不判断回答是否有误导性表达

---

### 2.2 Answer Quality Evaluator

由 Ragas 或 LLM-as-Judge 实现，负责验证回答质量。

适合回答：
- answer 是否忠实于 table？
- answer 是否回答了用户问题？
- answer 是否遗漏关键内容？
- answer 是否表达清楚？
- answer 是否包含 table 中没有的推断？

优势：
- 能评估语义质量
- 能评估忠实度
- 能评估相关性
- 能发现 deterministic check 难以发现的问题

不足：
- 依赖 LLM
- 有成本
- 有延迟
- 存在 judge bias
- 评分可能不完全稳定
- 不适合作为 SQL / 数值正确性的唯一依据

---

## 3. 本项目中的评估分工

### 3.1 Deterministic Evaluator 

负责：
- SQL correctness
- Result correctness
- Intent correctness
- Routing correctness
- Answer key facts

具体包括：
- expected_tables
- expected_columns
- expected_result
- expected_order
- expected_rows
- expected_generation_method
- expected_intent
- expected_answer_points

---

### 3.2 Ragas / LLM-as-Judge 负责

- Answer quality
- Answer faithfulness
- Answer relevance
- Answer clarity
- Answer completeness

维度：
- Faithfulness
- answer 中的内容是否都能被 table / context 支撑。
- Relevance
- answer 是否直接回答了用户问题。
- Factual Correctness
- answer 是否与 reference answer 或 expected facts 一致。
- Completeness
- answer 是否覆盖了关键业务点。
- Clarity
- answer 是否表达清楚，是否适合业务用户阅读。

---

4. Ragas 在本项目中评估什么

Ragas / LLM-as-Judge 的输入应包括：

```python
{
    "question": "...",
    "context": {
        "columns": [...],
        "rows": [...]
    },
    "answer": "...",
    "reference_answer": "...",
    "expected_answer_points": [...]
}
```

其中：
- question：用户原始问题
- context：SQL 查询结果 table
- answer：Answer Layer 生成的中文回答
- reference_answer：可选的标准回答
- expected_answer_points：确定性关键事实点

Ragas / LLM-as-Judge 主要评估：
- answer 是否忠实于 context.rows
- answer 是否直接回答 question
- answer 是否和 reference_answer 语义一致
- answer 是否遗漏重要事实
- answer 是否表达清楚

---

5. Ragas 不评估什么

Ragas / LLM-as-Judge 不负责：
- SQL 是否正确
- SQL 是否安全
- SQL 是否用了正确表
- SQL 是否用了正确字段
- SQL 是否走 template / llm 正确路径
- result 数值是否精确
- expected_rows 是否匹配
- intent 是否解析正确
- ranking order 是否正确
这些仍然由 deterministic evaluator 负责。

原因：LLM Judge 对数值精度、排序细节和 SQL 结构不够稳定，不适合作为底层事实正确性的唯一判定者。

---

6. 第一阶段 Spike 范围

第一阶段不做全量评估，只选 3-5 个 Answer Cases。

case：
- 哪个渠道销售额最高
- 品类退款率Top3
- 品类退款率从低到高排名
- 各渠道ROI排名
- 渠道ROI从低到高排名

覆盖：
- Top1
- TopN
- Ranking
- ASC
- DESC
- LLM SQL path
- Template SQL path

---

## 7. 第一阶段指标设计

第一阶段可以先不强依赖 Ragas 包，先实现轻量 LLM-as-Judge。

每个 case 输出：
```python
{
    "case_id": "...",
    "question": "...",
    "answer": "...",
    "scores": {
        "faithfulness": 1,
        "relevance": 1,
        "completeness": 1,
        "clarity": 1
    },
    "issues": [],
    "judge_reason": "..."
}
```

评分标准：
1 = 通过
0 = 不通过

后续再升级为 0-5 或 0-1 分数。

---

## 8. Rubric 初版

### Faithfulness

判断 answer 中的所有对象、数值、排序方向是否都能从 context.rows 中找到。

通过标准：
- answer 没有引入 table 中不存在的对象
- answer 没有引入 table 中不存在的数值
- answer 没有添加未经数据支撑的业务原因

失败示例：精华退款率最高，可能是因为用户对功效预期较高。
如果 context 只有退款率数据，没有用户预期数据，则这句话不忠实。

---

### Relevance

判断 answer 是否直接回答 question。

通过标准：
- 用户问最高，回答必须指出最高对象和值
- 用户问 Top3，回答必须列出前三
- 用户问从低到高，回答必须体现升序
- 用户问排名，回答必须给出排名结果

---

### Completeness

判断 answer 是否覆盖关键业务点。

通过标准：
- Top1 至少包含对象和值
- TopN 必须包含所有 TopN 对象和值
- Ranking 必须覆盖 expected rows 中的对象和值
- 不应遗漏关键指标数值

---

### Clarity

判断 answer 是否适合业务用户阅读。

通过标准：
- 表达清楚
- 没有明显重复词
- 没有字段名式表达过多
- 中文可读

---

## 9. 为什么不直接用 LLM 生成最终业务分析

当前 Answer Layer V1 是事实型回答层。

它只负责：把可信 table 转成中文事实回答
暂不负责：
- 原因分析
- 策略建议
- 趋势解释
- 业务归因

原因是这些能力需要更多数据支撑，例如：
- 用户行为
- 评价文本
- 活动信息
- 商品成本
- 会员生命周期
- 时间趋势

如果没有这些数据，直接让 LLM 输出分析原因，会增加幻觉风险。
后续可以新增 Business Insight Layer，但必须建立在更丰富数据和更严格评估之上。

---

## 10. 最终设计结论

本项目采用双层评估体系：
Deterministic Evaluator
↓
验证 SQL / result / rows / intent / answer key facts

Ragas / LLM-as-Judge
↓
验证 answer quality / faithfulness / relevance / clarity

两者互补，不互相替代。
当前目标不是让 LLM Judge 判断一切，而是把确定性评估和语义质量评估分层管理。