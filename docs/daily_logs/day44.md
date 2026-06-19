# Day44 学习日志

## 今日主题

Phase2：Business Semantic Layer & Text-to-SQL

Day44：Answer Layer V1

今日目标：让系统从只返回 SQL 和 table，升级为返回 SQL、table 和中文业务回答。

---

## 今日完成内容

### 1. 新增 Answer Layer V1

新增文件：app/text_to_sql/answer_generator.py

实现能力：
- 根据 SQL 查询结果 table 生成中文业务回答
- 支持 Top1 回答
- 支持 TopN 回答
- 支持 Ranking 回答
- 支持 ASC / DESC 排名描述
- 支持百分比字段展示
- 只基于 table 中已有结果生成回答，不做额外业务推断

核心函数：generate_answer(question, table, intent)

---

### 2. query_service 接入 answer

query_service.py 新增：
- import generate_answer
- SQL 执行后生成 table
- 根据 question、table、intent 生成 answer
- ask() 返回结果中新增 answer 字段

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
└─ 普通指标 → LLM SQL
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

---

### 3. evaluator 接入 expected_answer_points

evaluator.py 新增：
- check_expected_answer_points
- answer_point_mismatches
- evaluator passed 判断纳入 answer_point_mismatches
- evaluation report 输出 answer 和 answer_point_mismatches

expected_answer_points 不做整句完全匹配，而是检查回答中是否包含关键业务点。

示例：
expected_answer_points:
- 精华
- 10.0
- 防晒
- 4.55
- 面膜
- 4.48

这样可以避免中文表达变化导致误判，同时保证回答没有漏掉核心事实。

---

### 4. Golden Cases 增加 Answer 校验

本次为部分高价值 case 增加 expected_answer_points：
- case_018：哪个渠道销售额最高
- case_029：品类退款率Top3
- case_030：品类退款率从低到高排名
- case_031：销量最低的三个品类

当前 evaluator 结果：
Total: 26
Passed: 26
Failed: 0
Pass Rate: 100.0%

测试报告：docs/evaluation/evaluation_20260619_155151.json

---

## Risk Review

今日额外测试 5 个代表问题：
1. 哪个渠道销售额最高
2. 品类退款率Top3
3. 品类退款率从低到高排名
4. 各渠道ROI排名
5. 渠道ROI从低到高排名

覆盖能力：
- Top1
- TopN
- Ranking
- ASC / DESC 文案
- 普通指标 LLM SQL 路径
- ROI Template SQL 路径

测试结果：Answer Layer V1 能稳定生成事实型中文业务回答。

---

## 今日关键结论

### 1. Answer Layer V1 先用规则型是合理的

当前系统刚完成 SQL 结果校验和 expected_rows 多行结果校验。

如果直接让 LLM 根据 table 自由总结，可能出现：
- table 是对的，但 LLM 解释错
- LLM 添加 table 中没有的业务原因
- LLM 漏掉关键对象或数值
- LLM 把事实回答变成未经验证的分析推断

因此 Answer Layer V1 采用规则型生成，只基于 table 中已有数据回答。

---

### 2. Result Evaluator 和 Answer Evaluator 分工不同

Result Evaluator 负责证明：
- SQL 结果是否正确
- 排序是否正确
- 多行对象和值是否正确

Answer Evaluator 负责证明：
- 中文回答是否包含关键业务事实
- 回答是否忠实引用了 table 中的数据

二者不是重复工作，而是上下游关系：
可信 table
↓
可信 answer

---

### 3. expected_answer_points 和 Ragas / LLM-as-Judge 分工不同

expected_answer_points 是确定性检查：
- 快
- 稳定
- 便宜
- 可重复
- 不依赖 LLM Judge

但它不能评估：
- 回答是否自然
- 回答是否完整
- 回答是否有语义误导
- 回答是否真正相关

后续 Ragas / LLM-as-Judge 适合评估 answer relevance / faithfulness，但不能替代 SQL 和数值层面的 deterministic evaluator。

---

## 当前技术债

1. Answer Layer V1 主要支持 category / channel_name 聚合结果。
2. order_id 等明细对象字段暂不支持结构化回答。
3. 当前 answer 文案偏模板化，表达自然度有限。
4. expected_answer_points 只能检查关键点是否出现，不能判断完整语义质量。
5. 后续需要 Ragas / LLM-as-Judge 评估回答相关性和忠实度。
6. Answer Layer V1 暂不做业务原因推断，只生成事实型回答。

---

## 今日状态

Day44 已完成。

当前系统已经从 Text-to-SQL 进一步升级为：

自然语言问题
↓
SQL
↓
结构化结果
↓
中文业务回答
↓
Answer 关键点校验