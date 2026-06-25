# AI-Architect-100Days

从零构建企业级 AI BI Agent。

目标是在 100 天内完成：

- Business Semantic Layer
- Retrieval-Augmented Text-to-SQL
- AI Agent Workflow
- Eval-Driven AI Engineering
- 企业级可观测性与可靠性体系

最终实现：自然语言 → SQL → 企业业务分析

---

# 项目背景

传统 BI 分析依赖：
- SQL 编写
- 数据分析师
- 指标口径理解

而企业中往往存在：
- 数百张表
- 上千个字段
- 大量隐性业务规则

例如：
- 销售额到底使用 gross_amount 还是 paid_amount？
- 退款率按订单数计算还是按金额计算？
- 高价值用户的定义是什么？

因此本项目尝试构建：一个具备业务语义理解能力的 AI BI Agent。

---

# 当前系统架构

用户问题
↓
Business Semantic Search
↓
Business Context Builder
↓
Prompt Builder
↓
DeepSeek
↓
SQL Cleaner
↓
PostgreSQL SQL

---

# Demo

用户输入：哪个品类退款率最高？

系统自动检索：
- 退款率定义
- 商品维度表
- 退款事实表
- 订单事实表
- 表关联关系

生成 SQL：
SELECT
    dp.category,
    SUM(fr.refund_amount)
    /
    NULLIF(SUM(foi.item_paid_amount), 0)
    AS refund_rate
FROM fact_order_items foi
JOIN dim_product dp
    ON foi.product_id = dp.product_id
JOIN fact_orders fo
    ON foi.order_id = fo.order_id
LEFT JOIN fact_refunds fr
    ON foi.order_item_id = fr.order_item_id
WHERE fo.order_status = 'paid'
GROUP BY dp.category
ORDER BY refund_rate DESC;


---

# 当前能力

## Business Semantic Layer

支持：

- 业务指标检索
- 数据表检索
- 表关系检索

元数据管理：

metadata/
├── business_metrics.yaml
├── query_plans.yaml
├── table_dictionary.yaml
├── table_relationships.yaml

---

## Context Builder

自动注入：

### 指标定义

例如：

退款率
定义：退款金额占销售金额比例
公式：SUM(refund_amount) / SUM(item_paid_amount)

### 数据表

例如：
fact_refunds
dim_product
fact_order_items
fact_orders

### 表关系

例如：
fact_order_items.order_id = fact_orders.order_id
fact_order_items.product_id = dim_product.product_id
fact_refunds.order_item_id = fact_order_items.order_item_id

---

## Text-to-SQL

支持：

Question
↓
Hybrid Search
↓
Metric Recognition
↓
Query Plan Routing
├── ROI / CAC → Template SQL
└── 普通指标 → LLM SQL
↓
SQL Cleaner
↓
SQL Validator
↓
PostgreSQL
↓
Table

已验证问题：
- 哪个品类退款率最高
- 哪个品类销售额最高
- 哪个渠道销售额最高
- 各品类销售额排名

---

## Answer Layer V1

当前系统已支持将 SQL 查询结果转换为中文业务回答。

支持类型：

- Top1 回答
- TopN 回答
- Ranking 回答
- ASC / DESC 排名描述
- 百分比指标展示
- 基于 table 的事实型回答

示例：

用户问题：

品类退款率Top3

系统返回：

品类退款率Top3分别是：精华 10.0%，防晒 4.55%，面膜 4.48%。

当前原则：

- 只基于 SQL table 结果生成回答
- 不编造原因
- 不做未经验证的业务推断
- Answer 通过 expected_answer_points 做关键事实校验

---

# 数据库设计

当前使用：
- PostgreSQL 15
- pgvector
- SQLAlchemy 2.0

数据模型：
dim_product
dim_customer
dim_channel
fact_orders
fact_order_items
fact_refunds
fact_reviews

采用：星型模型（Star Schema）

---

# 当前数据集

项目当前构建了美妆行业模拟 BI 数据集。

## 数据规模

| 数据 | 数量 |
|--------|--------|
| 商品 | 100 |
| 用户 | 2000 |
| 订单 | 20000 |
| 订单商品 | 29051 |
| 退款记录 | 2008 |
| 用户评价 | 5000 |
| 营销数据 | 180天 |

---

## 已植入业务规律

### 商品规律

- 夏季防晒销量增长
- 精华退款率显著高于其它品类

### 渠道规律

- 小红书 ROI 持续下降

### 用户规律

- 会员用户购买频率更高

---

# 技术栈

## Backend

- Python 3.12
- FastAPI（规划中）

## Database

- PostgreSQL
- pgvector
- SQLAlchemy 2.0

## AI

- DeepSeek API
- BGE Small（规划接入）
- Pydantic V2
- Langfuse

## Engineering

- Docker
- AsyncIO
- Tenacity
- Structured Outputs

---

# 项目结构

app/
├── api/
├── agents/
├── db/
├── semantic_layer/
├── text_to_sql/
├── evaluation/
metadata/
├── business_metrics.yaml
├── query_plans.yaml
├── table_dictionary.yaml
├── table_relationships.yaml
docs/
├── PROJECT_STATE.md
├── daily_logs/
├── architecture/

---

# 当前进度

## Phase 1

LLM Reliability

状态：✅ 已完成
完成内容：
- Structured Outputs
- Pydantic Validation
- AsyncIO
- Semaphore
- Retry
- Langfuse Tracing

---

## Phase 2

Business Semantic Layer + Text-to-SQL

状态：🟡 进行中
已完成：
- PostgreSQL环境搭建
- 星型模型设计
- 测试数据生成（Seed）
- 业务指标分析
- Business Metrics
- Table Dictionary
- Relationship Dictionary
- Semantic Search
- Context Builder
- Prompt Builder
- DeepSeek SQL Generation
- SQL Cleaner
- SQL Validator
- Database Engine
- SQL Runner
- Result Formatter
- Query Service

当前能力：自然语言问题 → 业务语义检索 → Query Plan Routing → Template / LLM SQL生成 → SQL校验 → PostgreSQL执行 → 结构化结果返回 → Result-level Evaluation

## Evaluation Framework V5

当前支持：
- Golden Questions
- SQL 结构级检查
- Top1 `expected_result` 校验
- Ranking `expected_order` 校验
- 多行 `expected_rows` 校验
- `generation_method` 校验
- `expected_intent` 校验
- `expected_answer_points` 校验
- Prompt Builder Tests
- Answer Quality Evaluation
- Mock Judge
- LLM-as-Judge
- 正例 / 负例 answer eval
- Evaluation JSON 报告输出

当前评估结果：
- Golden Questions：26
- deterministic evaluator：26/26 PASS
- prompt_builder_tests：5/5 PASS
- answer_eval_cases：6
- answer_judge mock：6/6 PASS
- LLM-as-Judge：6/6 PASS
- query_plan_tests.py：2/2 PASS
- intent_parser_tests.py：5/5 PASS
- intent_resolver_tests.py：5/5 PASS
- template_sql_tests.py：15/15 PASS

---

## Day31：Semantic Search V2 设计

完成：
- Alias Search 局限分析
- Embedding Search 原理学习
- Clarification 机制设计
- Hybrid Search 架构设计
- Metric Embedding Pipeline 设计
- Metric Text Builder 实现

新增文档：
- docs/architecture/semantic_search_v2.md
- docs/architecture/metric_embedding_design.md

新增模块：
- app/semantic_layer/metric_text_builder.py

当前状态：
Metric YAML
↓
Metric Text

已完成

下一步：

Metric Text
↓
Embedding Vector
↓
Similarity Search

---

## Day32：Embedding Search 与 Vector Cache

完成：
- 接入 BGE-small-zh-v1.5
- 实现 Embedding Service
- 实现 Semantic Search V2
- 实现 Cosine Similarity 检索
- 实现 Confidence 判断
- 实现结构化返回
- 实现 Metric Vector Cache

新增模块：
- app/semantic_layer/embedding_service.py
- app/semantic_layer/semantic_search_v2.py
- app/semantic_layer/vector_store.py

当前能力：
Question
↓
Embedding
↓
Vector Search
↓
Confidence Check

下一步：

Hybrid Search
(Alias + Embedding + Clarification)

---

Day33：Hybrid Search 接入主链路

完成内容：
- 新增 Hybrid Search（Alias Search + Embedding Search）
- 新增 Clarification Layer
- 支持语义歧义问题识别
- Context Builder接入Hybrid Search
- Query Service支持needs_clarification状态
- 完成Semantic Layer到Text2SQL主链路打通
- Evaluation回归测试8/8通过

示例：
用户问题：最赚钱
系统返回：问题存在歧义，请选择您想查询的指标：
- 商品明细实付销售额
- 退款率
- 订单实付金额

当前系统状态：
Question
↓
Hybrid Search
↓
Context Builder
↓
Prompt Builder
↓
SQL Generator
↓
SQL Runner
---

### Day34 Semantic Search Calibration

完成内容：
- Semantic Search Calibration
- Metric Text 优化
- Confidence Threshold 调整
- Search Trace 可解释性增强
- Calibration Report 文档

关键收获：
- Confidence 判断应统一维护
- Embedding 命中不代表结果可信
- Search Trace 有助于定位检索问题

---

### Day35

完成内容：
- 新增订单数（order_count）指标
- 新增销量（sales_quantity）指标
- 引入 keyword_group 规则匹配
- 支持 TopN 类业务问题
- 扩展 Golden Cases 至 12 条
- Evaluator 保持 100% 通过率

---

### Day36

完成内容：
- 渠道数据层核对
- 补充 dim_channel 与 fact_marketing_spend 元数据
- 补充渠道表关系
- 新增 channel_sales_amount 指标
- 新增 channel_refund_rate 指标
- 新增 roi 指标
- 修复 Rule Layer 短 alias / 长 alias 冲突
- Prompt Builder 增加跨事实表指标规则
- Prompt Builder 增加 ROI 专用规则
- Golden Cases 扩展至 18 条
- Evaluator 保持 100% 通过率

关键收获：
- 数据库存在表，不代表语义层已具备业务理解能力。
- 跨事实表指标必须先分别聚合，再 JOIN 聚合结果。
- ROI 是倍数，不是百分比，不应乘以 100。
- Prompt 可以提升正确率，但高风险指标后续应模板化。

当前系统新增支持：
- 哪个渠道销售额最高
- 各渠道销售额排名
- 哪个渠道退款率最高
- 各渠道退款率排名
- 哪个渠道 ROI 最高
- 各渠道 ROI 排名
- 哪个渠道投放最划算

---

### Day37

完成内容：
- 完成 CAC 指标建设
- 明确 CAC 真实首单新客口径
- 新增 cac 指标
- 完成 CAC 手写 SQL 验证
- 完成 CAC 主链路验证
- Golden Cases 扩展至 20 条
- Evaluator 保持 100% 通过率
- 新增 expected_result 结果级校验
- 新增 expected_order 排名顺序校验
- 新增 Metric Query Plan V1 设计文档
- 新增 metadata/query_plans.yaml
- 完成 roi_channel_v1 与 cac_channel_v1 读取验证

关键收获：
- CAC 的核心是获客客户数口径，而不是公式本身。
- 真实首单新客口径比窗口内首单更严谨。
- 结构级 Evaluation 不能证明业务结果正确。
- Result-level Evaluation 可以验证 Top1 对象、关键数值与排名顺序。
- ROI / CAC 等复杂指标不应长期依赖 LLM 自由生成 SQL。
- Query Plan / SQL Template 是后续提升稳定性的方向。

当前系统新增支持：
- 哪个渠道获客成本最低
- 各渠道获客成本排名
- 哪个渠道拉新效率最高

当前技术债：
- query_plans.yaml 尚未接入主链路
- ROI / CAC 仍暂时依赖 Prompt 生成 SQL
- 后续需要 template_sql_generator.py

---

### Day38

完成内容：

- 新增 query_plan_loader.py
- 支持读取 metadata/query_plans.yaml
- 新增 template_sql_generator.py
- 实现 ROI Template SQL
- 实现 CAC Template SQL
- 实现 parse_limit，支持 Top1 / TopN / Ranking
- 实现 generate_template_sql 统一入口
- query_service 接入 Query Plan Routing
- ROI / CAC 走 template
- 普通指标继续走 LLM
- query_service 返回 generation_method
- 新增 template_sql_tests.py
- evaluator 增加 expected_generation_method 校验
- Evaluator 保持 20/20 通过

关键收获：

- ROI / CAC 等复杂指标不应长期依赖 LLM 自由生成 SQL。
- Query Plan Routing 可以让高风险指标走确定性模板。
- 普通指标继续走 LLM，避免过度模板化。
- TopN 解析需要优先识别明确数量，再处理最高/最低等极值词。
- template_sql_tests 与 evaluator 分别保护模板层和端到端业务链路。

当前系统新增能力：

- ROI / CAC Template SQL
- TopN Template SQL
- Query Plan Routing
- generation_method 评估

---

### Day39

完成内容：

- Query Plan 参数化 V1
- template_sql_generator.py 开始读取 query_plans.yaml
- alias 从 query plan 读取
- round 从 query plan 读取
- multiply_by_100 从 query plan 读取
- default_sort.field 从 query plan 读取
- default_sort.direction 从 query plan 读取
- 新增 build_formula_expression
- 增强 query_plan_tests.py
- query_plan_tests 支持配置结构校验
- query_plan_tests 支持模板实现一致性校验
- query_plan_tests 支持 ROI / CAC 业务规则校验
- query_plan_tests 支持 JSON 报告输出
- template_sql_tests 支持 JSON 报告输出
- 新增 docs/architecture/query_plan_testing_v1.md

当前测试结果：

- query_plan_tests.py：2/2 PASS
- template_sql_tests.py：12/12 PASS
- evaluator.py：20/20 PASS

关键收获：

- query_plans.yaml 已经从“分流依据”升级为“模板 SQL 参数来源”。
- ROI / CAC 的 multiply_by_100、排序方向等业务口径需要测试保护。
- 配置层、模板层、端到端业务层应分别测试。
- 后续学习模式调整为 B 模式：AI 给骨架和 TODO，用户补关键逻辑，AI 再 review。

---

### Day40

完成内容：

- 新增 `app/semantic_layer/intent_parser.py`
- 实现 Intent Parser V1
- 支持解析 `limit`
- 支持解析 `ranking_type`
- 支持解析 `sort_hint`
- 支持解析 `dimension`
- 新增 `app/evaluation/intent_parser_tests.py`
- `intent_parser_tests.py` 支持 JSON 报告输出
- `template_sql_generator.py` 新增 intent-based template 入口
- 新增 `generate_template_sql_from_intent`
- intent.limit 接入 ROI / CAC 模板 SQL 的 LIMIT 生成
- `template_sql_tests.py` 扩展到 14 个测试
- template SQL 测试报告新增 `intent_template_tests`
- `query_service.py` 接入 `parse_intent`
- query_service 返回 `intent`
- evaluator 增加 `expected_intent` 校验
- evaluator 保持 20/20 PASS

当前主链路：

```text
Question
↓
Intent Parser
↓
Metric Recognition / Hybrid Search
↓
Query Plan Routing
├─ ROI / CAC → Template SQL from Intent
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
Evaluator
```

当前测试结果：

- intent_parser_tests.py：5/5 PASS
- template_sql_tests.py：14/14 PASS
- evaluator.py：20/20 PASS

关键收获：

- Intent Parser 属于语义层，不应长期放在 SQL 模板层。
- limit / ranking_type / dimension / sort_hint 应先结构化，再交给 SQL 生成层使用。
- query_service 返回 intent 后，问题排查可以区分“意图解析错误”和“SQL 生成错误”。
- intent-based template 入口采用兼容式重构，保留旧入口，降低主链路风险。

---

### Day41

完成内容：
- 新增 `resolve_sort_direction`
- 新增 `enrich_intent_with_query_plan`
- query_service 接入 enriched intent
- intent 增加 `final_sort_direction`
- intent 增加 `sort_field`
- template_sql_generator 新增 `build_order_by_clause_from_intent`
- ROI / CAC 模板 SQL 支持从 intent 生成 ORDER BY
- 支持用户显式排序方向覆盖指标默认排序方向
- 新增问题能力：`渠道ROI从低到高排名`
- Golden Cases 从 20 扩展到 21
- 新增 `intent_resolver_tests.py`
- 更新 `docs/architecture/query_plan_testing_v1.md`
- template_sql_tests 扩展到 15 个测试

当前主链路：
Question
↓
Intent Parser
↓
Intent Resolver
↓
Metric Recognition / Hybrid Search
↓
Query Plan Routing
├─ ROI / CAC → Template SQL from Intent
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
Evaluator

当前测试结果：
- query_plan_tests.py：2/2 PASS
- intent_parser_tests.py：5/5 PASS
- intent_resolver_tests.py：5/5 PASS
- template_sql_tests.py：15/15 PASS
- evaluator.py：21/21 PASS

关键收获：
- `sort_hint` 来自用户问题。
- `default_sort` 来自 query_plans.yaml。
- `final_sort_direction` 是二者融合后的最终排序方向。
- 用户显式排序方向优先于指标默认排序方向。
- 测试链路必须模拟真实主链路，否则可能出现测试失败但主链路正确的情况。

---

### Day42

完成内容：
- prompt_builder 支持 intent 参数
- 新增 build_intent_context
- Prompt 中加入结构化意图上下文
- sql_generator 支持 intent 参数
- query_service 在 LLM 路径传入 enriched intent
- 普通指标 LLM SQL 接入 Intent Context
- 修复普通指标字段别名漂移问题
- 新增 case_027：渠道销售额从低到高排名
- 新增 case_028：渠道销售额Top3
- Golden Cases 从 21 扩展到 23
- 新增 prompt_builder_tests.py
- prompt_builder_tests 输出 JSON 测试报告

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
├─ ROI / CAC → Template SQL from Intent
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
Evaluator

当前测试结果：
- query_plan_tests.py：2/2 PASS
- intent_parser_tests.py：5/5 PASS
- intent_resolver_tests.py：5/5 PASS
- template_sql_tests.py：15/15 PASS
- prompt_builder_tests.py：2/2 PASS
- evaluator.py：23/23 PASS

关键收获：
- Intent 不等于 Template。
- 普通指标不走 Template，但仍然需要 Intent Context 来约束 LLM。
- Prompt 接入 Intent 后，需要明确区分 dimension 枚举值和 SQL 输出字段别名。
- prompt_builder.py 已开始臃肿，后续需要做 Prompt Builder V2 模块化。

---

### Day43

完成内容：

- 合并完成原 Day43 普通指标 Intent Cases 收尾
- 合并完成原 Day44 Result-level Evaluation V2
- 新增 case_029：品类退款率Top3
- 新增 case_030：品类退款率从低到高排名
- 新增 case_031：销量最低的三个品类
- Golden Cases 扩展至 26
- 普通指标 LLM 路径继续验证 Intent Context
- 新增 expected_rows 多行结果值校验
- evaluator 支持 rows_mismatches
- evaluator 保持 26/26 PASS

关键收获：

- 普通指标虽然可以由 LLM 生成 SQL，但仍需要 intent 来提升可控性、可解释性和可评估性。
- expected_order 只能检查顺序，expected_result 只检查首行，expected_rows 可以检查多行对象和多行数值。
- Result-level Evaluation V2 为后续 Answer Layer 提供可信结果基础。

---

### Day44

完成内容：

- 新增 Answer Layer V1
- 新增 app/text_to_sql/answer_generator.py
- query_service 返回 answer
- evaluator 新增 expected_answer_points
- evaluator 新增 answer_point_mismatches
- Golden Cases 增加 answer 关键点校验
- 完成 5 个代表问题 Answer Risk Review
- evaluator 保持 26/26 PASS

关键收获：

- Answer Layer V1 不直接使用 LLM，而是先采用规则型生成，避免“SQL 对但回答幻觉”。
- Result Evaluator 负责校验数据正确性，Answer Evaluator 负责校验回答是否包含关键事实。
- expected_answer_points 是确定性校验，后续 Ragas / LLM-as-Judge 用于回答质量和忠实度评估。

---

### Day45

完成内容：

- 合并完成原 Day45：Answer Layer 加固 + Ragas Feasibility Spike
- 合并完成原 Day46：LLM-as-Judge Evaluation V1
- 完成 Answer Layer V1 边界复查
- 新增 docs/architecture/ragas_eval_design.md
- 新增 app/evaluation/answer_eval_cases.py
- 新增 / 扩展 app/evaluation/answer_judge.py
- 支持 mock judge
- 支持真实 LLM-as-Judge
- 支持 --mode mock / --mode llm
- 支持 clean_judge_json_text
- 支持 normalize_judge_payload
- 支持 expected_judge_passed
- 支持正例与负例 answer eval
- 生成 answer_eval_*.json 报告

关键收获：

- Deterministic Evaluator 和 LLM-as-Judge 是双层评估关系，不是替代关系。
- deterministic evaluator 负责 SQL、数值、排序、intent 和 answer key facts。
- LLM-as-Judge 负责回答是否忠实、相关、完整、清晰。
- 负例测试证明 Judge 不只是能把正确答案判对，也能把错误答案判错。
- Ragas 可作为后续标准化评估框架，但当前 lightweight LLM-as-Judge 已经跑通核心评估闭环。

---

### Day47

完成内容：
- 完成 Ragas Evaluation Integration V1
- 新增 `app/evaluation/ragas_eval.py`
- 接入 Ragas `faithfulness`
- 将 `answer_eval_cases.py` 转换为 Ragas-style dataset
- 将 SQL 查询结果 `context.rows` 映射为 Ragas 的 `retrieved_contexts`
- 新增 `--include-negative` 参数，支持正例 / 负例评估
- 增加 Ragas threshold-based expectation check
- 增强 Ragas context，使其理解 Text-to-SQL 查询语义
- 在 `retrieved_contexts` 中补充 query semantics
- 新增 / 更新 `docs/architecture/ragas_spike_report.md`
- 回归 `evaluator.py` 通过
- 回归 `answer_judge.py --mode mock` 通过
- 回归 `ragas_eval.py --include-negative` 通过

当前测试结果：
evaluator.py：26/26 PASS
answer_judge.py --mode mock：6/6 PASS
ragas_eval.py --include-negative：6/6 expectation passed

关键收获：
- Ragas 的 `faithfulness` 不是业务正确性评分，而是判断 answer 中的 claim 是否能被 `retrieved_contexts` 支撑。
- 在 Text-to-SQL 场景中，不能简单把 SQL rows 当作普通文档片段传给 Ragas。
- 对 Top1 / TopN / Ranking 类问题，Ragas 默认不知道 SQL 已经通过 `ORDER BY` / `LIMIT` 得到结果，因此可能低估回答质量。
- 通过在 `retrieved_contexts` 中加入 query semantics，可以让 Ragas 更好理解 SQL 查询结果语义。
- context enhancement 后，正例 faithfulness 提升到 1.0，负例 `answer_case_006_bad` 仍保持 0.25。
- Ragas 不替代 deterministic evaluator，而是作为标准化 LLM Evaluation 对照，用于阶段性评估、质量验证和面试展示。

---

### Day48

完成 Phase2 Evaluation & Architecture Review，并统一整理 Phase2 技术债与 Phase3 承接计划。

完成内容：
- 新增 `docs/architecture/phase2_architecture_review.md`
- 新增 `docs/architecture/evaluation_workflow_v1.md`
- 新增 `docs/architecture/phase2_technical_debt_and_phase3_plan.md`
- 梳理 Phase2 当前 AI Data Analyst / Text-to-SQL 主链路
- 梳理 Evaluation Workflow V1
- 梳理 deterministic evaluator / answer_judge / Ragas 的分工
- 复盘 Ragas 在 Text-to-SQL 场景中的适配方式
- 统一登记 Phase2 技术债
- 明确 Phase3 LangGraph 需要承接 retrieval、clarification、SQL repair、eval-driven retry 等问题

当前 Day48 形成的核心文档：
docs/architecture/phase2_architecture_review.md
docs/architecture/evaluation_workflow_v1.md
docs/architecture/phase2_technical_debt_and_phase3_plan.md

当前关键结论：
- Phase2 已经证明业务语义层、Text-to-SQL、Answer Layer 和 Evaluation Workflow 主链路可行。
- 当前系统仍有 Semantic Retrieval Calibration、数据真实性、指标体系扩展、普通指标 query_plan、Answer Insight Layer 等技术债。
- 阶段内没有解决的问题不能只留在对话记忆中，必须进入技术债或后续计划。
- Phase3 不应推翻 Phase2，而应通过 LangGraph workflow 复用 Phase2 模块，并逐步增强 clarification、retry、repair 和 evaluation-driven workflow。

---

### Day49

完成 Phase3 LangGraph Entry Design，并实现 LangGraph 方案 B 最小 prototype。

完成内容：
- 新增 `docs/architecture/langgraph_phase3_design.md`
- 梳理当前 `query_service.py` 线性主链路
- 将主链路拆解为 LangGraph nodes / state / conditional edges
- 重构 `query_service.py`，新增 `ask_with_resolved_metric()`
- 新增 `app/agents/analyst_graph.py`
- 新增 `app/agents/analyst_graph_tests.py`
- 实现 LangGraph clarification branch
- 将 `metric_result.status` 从普通 if 判断升级为 LangGraph conditional edge
- 完成普通指标路径、Template SQL 路径、clarification 路径测试
- 发现并记录 LangGraph / LangChain / Ragas 依赖冲突问题
- 发现并记录 clarification suggestions 候选排序问题

当前 LangGraph prototype 流程：
parse_intent
↓
search_metric
↓
route_metric_status
├─ matched → continue_pipeline
├─ needs_clarification → clarification
└─ error → fail

当前测试结果：
evaluator.py：26/26 PASS
answer_judge.py --mode mock：6/6 PASS
ragas_eval.py --include-negative：6/6 expectation passed
analyst_graph_tests.py：3/3 PASS

关键结论：
- Phase3 不推翻 Phase2，而是用 LangGraph workflow 复用 Phase2 已完成模块。
- 当前方案 B 已验证：普通指标走 LLM SQL，复杂指标走 Template SQL，歧义问题进入 clarification branch。
- LangGraph 当前只完成最小 prototype，不继续扩展 SQL repair / eval-driven retry。
- 依赖冲突已记录为 Dependency Management Debt，后续需要统一 LangGraph / LangChain / Ragas 版本。
- “最赚钱”候选排序问题已记录为 Clarification Candidate Ranking Debt，后续需要通过 retrieval evaluator 和 metric_text_builder 优化。

---

## Phase 3

Agent Workflow

状态：⬜ 未开始
规划：
- LangGraph
- Tool Calling
- Planner Agent
- SQL Agent
- Analysis Agent

---

## Phase 4

Production AI BI Agent

状态：⬜ 未开始
规划：
- FastAPI
- Streaming
- Evaluation System
- Observability
- Cloud Deployment

---

# Roadmap

当前：

Question
↓
Semantic Search
↓
Context Builder
↓
Prompt Builder
↓
DeepSeek
↓
SQL

下一阶段：

Question
↓
Semantic Search
↓
Context Builder
↓
DeepSeek
↓
SQL
↓
PostgreSQL
↓
Result


最终目标：

Question
↓
Multi-Agent
↓
SQL
↓
Execution
↓
Business Analysis
↓
Answer

---

# 学习记录

详细开发过程见：docs/PROJECT_STATE.md

记录内容：

- 每日学习日志
- 项目进展
- 架构演进
- 踩坑记录
- 技术总结

---

# 当前版本

Version: v0.24
完成度：Day49 / 100
当前实现：自然语言问题 → Intent Parser → Intent Resolver → Hybrid Search → Query Plan Routing → Prompt Builder V2 → Template SQL / LLM SQL with Intent Context → SQL执行 → Result-level Evaluation V2 → Answer Layer V1 → LLM-as-Judge Answer Evaluation → Ragas Evaluation → Phase2 Architecture Review / Technical Debt Register → LangGraph Clarification Branch Prototype


