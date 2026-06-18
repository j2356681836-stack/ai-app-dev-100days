# AI-Architect-100Days

## 项目目标

构建企业级 AI BI Agent：

用户自然语言
→ Business Semantic Layer
→ Text-to-SQL
→ SQL Execution
→ Business Analysis
→ Agent Workflow

目标岗位：

- GenAI Engineer
- AI Agent Engineer
- AI Data Engineer

---
## 学习计划

### 第一阶段：API 确定性与监控基石 (Day 1-20)

**核心目标：** 把大模型从“聊天机器人”规训为一个“绝对稳定、可追踪的 JSON 生成函数”。

- **Day 1-7：原生 API 与异步高并发。** 使用 Python `asyncio` 调用 OpenAI/Anthropic 原生接口。强制使用 Structured Outputs 提取非结构化文本。引入 `tenacity` 实现指数退避重试，解决 429 和 500 报错。
- **Day 8-14：Schema 驱动开发。** 熟练使用 Pydantic V2。利用 `@field_validator` 处理大模型的脏数据（如去除 Markdown 标记、修正数据类型），完成美妆基础实体（如订单、商品、评价）的模型构建。
- **Day 15-20：可观测性 (Observability) 接入。** 全面接入 Langfuse。要求每一笔 API 调用的 Prompt、耗时、Token 成本和 Pydantic 校验结果，必须在控制台形成完整的 Trace 链路。
- **交付物：** 一个高并发、带自动重试、且所有出入参被严格清洗并记录在案的结构化数据提取 API。

---
### 第二阶段：业务语义层与 Eval 驱动的混合检索 (Day 21-50)

**核心目标：** 攻克企业级 Text-to-SQL 幻觉，将“美妆行业知识”预埋进数据库，并用数学指标衡量回答质量。

- **Day 21-30：高阶 SQL 与数据字典向量化。** 在 PostgreSQL 中构建美妆业务的高阶视图（如：同环比、ROI 聚合表）。**核心动作：** 将公司 500+ 表的表名、字段定义和业务口径解释存入 `pgvector`。
- **Day 31-40：精准路由的 Text-to-SQL 闭环。** 实现双层架构：Agent 收到自然语言后，先去 pgvector 检索相关的表结构（DDL）和业务定义，拼装成动态上下文，再让大模型生成 SQL。绝对禁止全量 DDL 注入。
- **Day 41-50：引入 Ragas 评估体系。** 停止肉眼看结果。构建 100 条美妆业务的 Golden Dataset（标准问答对）。使用 Ragas 计算你系统的 Faithfulness（忠实度）和 Answer Relevance（回答相关性），确保准确率稳步向 90% 逼近。
- **交付物：** 一个能在复杂业务黑话下，先查字典、再写 SQL、并能跑出客观评分报告的混合数据检索引擎。

---
### 第三阶段：状态机编排与原生 Agent大脑 (Day 51-75)

**核心目标：** 放弃单次线性流，掌握图结构逻辑，赋予系统自我纠错和多步推理的能力。

- **Day 51-60：LangGraph 基础与状态管理。** 学习 LangGraph 的核心理念（State, Nodes, Edges）。用纯代码构建一个循环图：让系统能够维护上下文历史，并根据条件分支执行不同的函数。
- **Day 61-70：Multi-Agent 协同与 Tool Calling 进阶。** 将第二阶段的 pgvector 检索和 Text-to-SQL 封装为独立的 Tool。让一个“路由 Agent”负责意图识别，将任务分发给“查库 Agent”或“查文档 Agent”。
- **Day 71-75：反思与自愈 (Reflection & Self-correction)。** 在 LangGraph 中加入“自我批评”节点。例如：SQL Agent 生成的 SQL 运行报错了，Graph 会自动将报错信息传回给模型重新修改代码，直到成功或达到最大重试次数再抛出异常。
- **交付物：** 一个能在遇到错误时自动兜底、根据意图自主切换工具的 LangGraph 复杂状态机系统。

---
### 第四阶段：交付部署与自动化优化 (Day 76-90)
  
**核心目标：** 解决技术栈割裂问题，用最少的前端代码交付最高级的业务决策台。

- **Day 76-82：Streamlit 企业级决策台。** 放弃 Vercel 复杂的全栈生态，直接使用纯 Python 的 Streamlit 开发前端。快速构建出包含数据看板、Chat 对话框和图表渲染的“美妆大盘决策台”，无缝对接你的 LangGraph 后端。
- **Day 83-86：DSPy 提示词自动寻优。** 砍掉不切实际的 DPO 训练。引入 DSPy，通过你在第二阶段准备的 Golden Dataset，让程序自动对大模型的 Prompt 进行微调和版本控制，榨干开源/闭源模型的推理能力。
- **Day 87-90：Serverless 云端部署。** 编写极简的 `requirements.txt` 和 `.env` 隔离机制。对接 Render 或 Zeabur，实现代码 Push 到 GitHub 后自动构建并对外发布，配置生产环境的 API 限流。
- **交付物：** 一个可通过公网访问、界面专业的企业级美妆数据 AI 助理。

---
#### 第五阶段：面试冲刺与价值放大 (Day 91-100)

**核心目标：** 将 90 天的技术积累转化为降维打击的求职资本。

- **Day 91-95：作品集与架构图包装。** 完善 GitHub 仓库的 README。画出你系统的状态机流转图和 Ragas 准确率提升曲线。
- **Day 96-100：工程化面试靶向训练。** 梳理项目中真实踩过的坑（如：并发 429 怎么处理的？大模型死循环了怎么阻断？脏数据怎么用 Pydantic 洗掉的？），用 STAR 法则写进简历。


---
## 当前阶段

Phase 2：Business Semantic Layer & Text-to-SQL

进度：Day21 ~ Day50

当前日期：Day43 / 100

---
## 已完成能力

### Phase1：LLM Reliability

#### API Reliability

- AsyncOpenAI
- asyncio.gather
- Semaphore
- Retry
- Structured Outputs

#### Data Validation

- Pydantic V2
- field_validator
- Nested Schema
- JSON Self-Healing

#### Observability

- Langfuse Tracing
- Parent/Child Span
- Token Monitoring

---

### Phase2：Business Semantic Layer

#### 数据层

- PostgreSQL
- pgvector
- SQLAlchemy 2.0
- Beauty BI Schema

#### 业务元数据

- business_metrics.yaml
- table_dictionary.yaml
- table_relationships.yaml

#### Retrieval

- metric_loader.py
- table_loader.py
- relationship_loader.py

#### Semantic Layer

- clarification.py
- semantic_search.py
- semantic_search_v2.py
- context_builder.py
- hybrid_search.py
- metric_text_builder.py
- vector_store.py

#### Text-to-SQL

- prompt_builder.py
- query_service.py
- result_formatter.py
- sql_generator.py（DeepSeek）
- sql_cleaner.py
- sql_validator.py

## 当前能力：

当前系统已形成双路径 SQL 生成架构：
Question
↓
Intent Parser
↓
Intent Resolver
↓
Hybrid Search / Metric Recognition
├─ Alias Match
├─ Keyword Group Match
├─ Embedding Match
└─ Clarification
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

当前核心能力：
1. 业务指标识别
   - alias match
   - keyword_group match
   - embedding match
   - clarification
   - 更具体 alias 优先

2. Intent Parser V1
   - 解析 limit
   - 解析 ranking_type
   - 解析 sort_hint
   - 解析 dimension

3. Intent Resolver V1
   - 融合用户排序意图与 query_plan 默认排序
   - 生成 final_sort_direction
   - 生成 sort_field

4. Query Plan Routing
   - ROI / CAC 走 Template SQL
   - 普通指标继续走 LLM SQL

5. Intent-based Template SQL
   - ROI Template SQL
   - CAC Template SQL
   - intent.limit → SQL LIMIT
   - intent.final_sort_direction → SQL ORDER BY

6. LLM SQL with Intent Context
   - 普通指标继续走 LLM
   - Prompt 注入 dimension
   - Prompt 注入 ranking_type
   - Prompt 注入 limit
   - Prompt 注入 final_sort_direction
   - Prompt 明确字段别名规则

7. Evaluation Framework
   - 结构级校验
   - 结果级校验
   - 排名顺序校验
   - generation_method 校验
   - expected_intent 校验

### 当前Rule能力

支持：
- alias
- keyword_group
- 更具体 alias 优先

返回：
method = rule
search_type:
- alias
- keyword_group

新增能力：
- 当多个 rule 同时命中时，优先保留 match_score 更高的结果
- 用于解决“退款率”与“渠道退款率”等泛化词和具体词冲突

### Golden Dataset / Evaluation

当前测试体系：
query_plan_tests.py          2/2 PASS
intent_parser_tests.py       5/5 PASS
intent_resolver_tests.py     5/5 PASS
template_sql_tests.py       15/15 PASS
prompt_builder_tests.py      2/2 PASS
evaluator.py                26/26 PASS

当前 Golden Cases：26 Cases
Pass Rate：100%

当前覆盖指标：
- item_sales_amount
- order_paid_amount
- refund_rate
- order_count
- sales_quantity
- channel_sales_amount
- channel_refund_rate
- roi
- cac

当前覆盖问题类型：
- 品类销售额
- 品类退款率
- 订单数
- 销量
- 渠道销售额
- 渠道退款率
- ROI
- CAC
- Top1
- TopN
- Ranking
- 反向排序：渠道ROI从低到高排名
- 普通指标 TopN
- 普通指标反向排序

当前 Evaluation 能力：
- expected_tables
- expected_columns
- expected_result
- expected_order
- expected_rows
- expected_generation_method
- expected_intent
- tolerance 数值误差
- rows_mismatches 报告

当前测试报告目录：
docs/evaluation/
├── evaluation_*.json
├── query_plan_tests_*.json
├── template_sql_tests_*.json
├── intent_parser_tests_*.json
├── intent_resolver_tests_*.json
├── prompt_builder_tests_*.json

### Metric Query Plan

当前状态：V1 已接入主链路，并开始与 Intent Resolver 协同。

已完成：
- metadata/query_plans.yaml
- app/semantic_layer/query_plan_loader.py
- app/text_to_sql/template_sql_generator.py
- app/semantic_layer/intent_parser.py
- app/evaluation/query_plan_tests.py
- app/evaluation/template_sql_tests.py
- app/evaluation/intent_resolver_tests.py

当前支持 Query Plan：
- roi_channel_v1
- cac_channel_v1

当前路由：
roi → template
cac → template
其他普通指标 → llm

当前 query_plans.yaml 参数化范围：
- output.formula.alias
- output.formula.round
- output.formula.multiply_by_100
- default_sort.field
- default_sort.direction

当前 Template SQL 能力：
- ROI Template SQL
- CAC Template SQL
- generate_template_sql
- generate_template_sql_from_intent
- build_limit_clause_from_intent
- build_order_by_clause_from_intent

当前 Intent-based Template 能力：
intent.limit
↓
SQL LIMIT

intent.sort_field
+
intent.final_sort_direction
↓
SQL ORDER BY

当前排序决策规则：
intent.sort_hint
>
query_plan.default_sort.direction
>
None

示例：
各渠道ROI排名
→ sort_hint = None
→ query_plan.default_sort.direction = desc
→ final_sort_direction = desc

渠道ROI从低到高排名
→ sort_hint = asc
→ query_plan.default_sort.direction = desc
→ final_sort_direction = asc

各渠道获客成本排名
→ sort_hint = None
→ query_plan.default_sort.direction = asc
→ final_sort_direction = asc

---

## 当前项目结构

app/
├── api/
├── agents/
├── db/
├── semantic_layer/
├── text_to_sql/
├── evaluation/
data/
docs/
metadata/

---

## 当前数据库

### 数据规模

- 100 Products
- 2000 Customers
- 20000 Orders
- 29051 Order Items
- 2008 Refunds
- 5000 Reviews

### 已植入业务规律

- 夏季防晒销量增长
- 小红书渠道成本增长
- 精华退款率更高

### 待增强业务规律

- 会员等级成长体系
- 会员等级历史表
- 复购行为增强

### 当前指标

item_sales_amount
order_paid_amount
refund_rate
order_count
sales_quantity
channel_sales_amount
channel_refund_rate
roi
cac

---

## 当前系统架构

Question
↓
Intent Parser
├─ parse_limit
├─ parse_ranking_type
├─ parse_sort_hint
└─ parse_dimension
↓
Intent Resolver
├─ resolve_sort_direction
└─ enrich_intent_with_query_plan
↓
Hybrid Search / Metric Recognition
├─ Alias Match
├─ Keyword Group Match
├─ Embedding Match
└─ Clarification
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

当前主链路特点：
- ROI / CAC 复杂指标不再依赖 LLM 自由生成 SQL。
- ROI / CAC 使用 Query Plan + Template SQL。
- Template SQL 已消费 intent.limit 和 intent.final_sort_direction。
- 普通指标仍走 LLM，但 Prompt 已注入 Intent Context。
- evaluator 已能校验业务结果、排序顺序、生成路径和 intent。

---

## 当前待办（Next Milestone）

### Day44-Day50 规划

---

Day44：Answer Layer V1

目标：
- SQL Table → 中文业务回答
- 让系统不仅返回 table，还能生成业务解释
- 优先使用规则型 Answer Layer，避免过早引入新的 LLM 不确定性

学习安排：
1. 设计 answer_generator.py 的输入输出
2. 实现 Top1 / TopN / Ranking 三类基础回答
3. query_service 返回 answer
4. Golden Cases 增加 expected_answer_points
5. evaluator 增加 answer point 校验
6. 复盘 Answer Layer 与 SQL Result Evaluator 的关系

交付：
- app/text_to_sql/answer_generator.py
- query_service 返回 answer
- evaluator 支持 expected_answer_points
- 3-5 个 answer cases
- evaluator 100% PASS

---

Day45：Answer Layer V1 加固 + Ragas Feasibility Spike

目标
- 加固 Answer Layer
- 明确 Ragas 在本项目中评估什么、不评估什么
- 不让 Ragas 替代 deterministic evaluator

学习安排：
1. 扩展 answer cases
2. 分析规则型 Answer Layer 的边界
3. 编写 ragas_eval_design.md
4. 明确 Ragas 只评估 answer relevance / faithfulness
5. 明确 SQL、数值、排序仍由自研 evaluator 评估
6. 设计小规模 Ragas / LLM-as-Judge 输入格式

交付：

- docs/architecture/ragas_eval_design.md
- answer cases 扩展
- Ragas / LLM-as-Judge 评估边界说明

---

Day46：Ragas / LLM-as-Judge Evaluation V1

目标：
- 对 Answer Layer 进行回答质量评估
- 形成 deterministic eval + answer quality eval 双层体系

学习安排：
1. 新增 answer_eval_cases.py
2. 实现小规模 LLM-as-Judge 或 Ragas spike
3. 设计 answer quality rubric
4. 生成 answer_eval 报告
5. 对比 deterministic evaluator 与 LLM Judge 的分工
6. 记录 LLM-as-Judge 的风险与偏差

交付：
- app/evaluation/answer_eval_cases.py
- app/evaluation/answer_judge.py 或 ragas_eval_spike.py
- docs/evaluation/answer_eval_*.json
- deterministic eval + answer quality eval 双层设计

---

Day47：Prompt Builder V2 / 模块化收束

目标：
- 解决 prompt_builder.py 规则臃肿
- 不继续堆规则
- 为 Phase3 Tool 化做准备

学习安排：
1. 拆分 build_global_rules
2. 拆分 build_intent_rules
3. 拆分 build_dimension_rules
4. 拆分 build_metric_rules
5. prompt_builder_tests 扩展
6. 复盘 Prompt 规则、Intent、Query Plan 的边界

交付：
- prompt_builder.py 模块化
- prompt_builder_tests 扩展
- docs/architecture/prompt_builder_v2.md

---

Day48：Phase2 Midpoint Review

目标：
- 整理 Phase2 当前能力
- 形成面试表达材料
- 梳理技术债和架构演进

学习安排：
1. 梳理 Phase2 架构图文字版
2. 梳理主链路模块职责
3. 梳理 Evaluation 体系演进
4. 梳理 Query Plan / Template SQL 价值
5. 梳理普通指标 LLM 路径 tradeoff
6. 输出面试表达材料

交付：
- docs/architecture/phase2_midpoint_review.md
- 架构图文字版
- 技术债清单
- 面试表达草稿

---

Day49：Phase2 Final Review / Phase3 准备

目标：
- 判断是否进入 LangGraph
- 把 Text-to-SQL 能力封装为 Tool
- 准备 Phase3 Agent Workflow

学习安排：
1. 设计 sql_agent_tool 输入输出
2. 明确 Tool 返回结构
3. 明确 error / clarification / success 三类状态
4. 设计 Phase3 LangGraph State
5. 编写 phase3_entry_plan.md
6. README / PROJECT_STATE 全量校准

交付：
- docs/architecture/sql_agent_tool_design.md
- docs/architecture/phase3_entry_plan.md
- README 更新
- PROJECT_STATE 全量校准

---

Day50：Phase2 缓冲与阶段复习

目标：
- 如果 Day44-Day49 有未完成内容，用 Day50 补齐
- 如果已完成，则进行 Phase2 阶段复习和面试表达训练
- 不再新增大功能，避免 Phase2 失控

学习安排：
1. 回归所有测试
2. 清理文档状态
3. 整理 Phase2 技术债
4. 整理项目亮点
5. 准备 Phase3 新窗口交接文档
6. 进行 Phase2 面试问答训练

交付：
- 全量测试通过
- PROJECT_STATE 校准
- README 校准
- chatgpt_handover.md 更新
- Phase3 开始前检查清单

---

## 开发日志

### Day24

完成：
- 品类销售额分析
- 品类退款率分析
- Business SQL验证

发现：
- 会员等级快照设计不足
- 缺少等级历史表

---

### Day25

完成：
- business_metrics.yaml
- table_dictionary.yaml
- metric_loader.py
- table_loader.py
- semantic_search.py

---

### Day26

完成：
- table_relationships.yaml
- relationship_loader.py
- context_builder.py
- prompt_builder.py

---

### Day27

完成：
- DeepSeek API接入
- sql_generator.py
- sql_cleaner.py

实现：自然语言→ SQL

验证问题：
- 哪个品类退款率最高？
- 哪个品类销售额最高？
均成功生成SQL

---

### Day28

完成：
- SQL Validation
- SQL Execution
- PostgreSQL Runner

实现：自然语言问题 → 业务语义检索 → Prompt 构建 → SQL 生成 → SQL 校验 → PostgreSQL 执行 → 结构化结果返回

问题：
哪个品类退款率最高？
返回：
category = 精华
refund_rate_pct = 10.0

下一步：
Evaluation Framework
Failure Cases
Prompt Optimization

---

### Day29

完成：

- Result Formatter
- SQL → Table
- Golden Questions
- Evaluator
- Evaluation Report
- Failure Case Analysis
- Prompt Optimization V1

实现：

Question
↓
SQL
↓
PostgreSQL
↓
Table
↓
Evaluation

发现问题：

- 模糊问题导致分析维度错误
- category 被错误替换为 product_name

解决：
- 新增 Evaluation V1
- 增加 expected_columns 校验
- Prompt 增加默认 category 规则

结果：
Pass Rate
66.67%
↓
100%

---

### Day30

完成：
- Golden Questions 扩展
- Evaluation V2
- Semantic Search V1
- Alias Search
- Failure Cases 分类

发现问题：
- 业务黑话无法识别
- Alias 可解决部分问题
- Alias 无法无限扩展

解决：
- business_metrics.yaml 增加 aliases
- metric_loader 支持 Alias Match

结果：
Pass Rate：
71.43%
↓
100%

---

### Day31

完成：
- Semantic Search V2 架构设计
- Hybrid Search 方案设计
- Clarification 机制设计
- Metric Embedding Pipeline 设计
- Metric Text Builder 开发

产出：
- semantic_search_v2.md
- metric_embedding_design.md
- metric_text_builder.py

关键收获：Alias Search：

优点：
- 准确
- 可控
缺点：
- 难扩展

Embedding Search：

优点：
- 语义理解能力强
缺点：
- 无法解决业务歧义

因此未来采用： Alias + Embedding + Clarification 的 Hybrid Search方案

---

### Day32

完成：
- BGE Embedding 接入
- Semantic Search V2 实现
- Cosine Similarity 检索实现
- Confidence Score 判断
- Metric Vector Cache 实现

产出：
- embedding_service.py
- semantic_search_v2.py
- vector_store.py

关键收获：
- Embedding：负责语义表达。
- Vector Search：负责检索。
- Confidence：负责判断是否可信。
- Clarification：负责处理业务歧义。

当前系统能力：Alias Search + Embedding Search 已具备独立运行能力。

---

### Day33

完成：
- 新增 Hybrid Search（Alias Search + Embedding Search）
- 新增 Clarification Layer
- 支持语义歧义问题识别
- Context Builder接入Hybrid Search
- Query Service支持needs_clarification状态
- 完成Semantic Layer到Text2SQL主链路打通
- Evaluation回归测试8/8通过

---

### Day34

完成：
- Semantic Search Calibration
- Metric Text 增强
- Confidence 阈值校准
- Search Trace 可解释性增强
- Calibration Report 文档沉淀
- Evaluation 回归测试 8/8 通过

关键调整：
- TOP1_THRESHOLD = 0.50
- GAP_THRESHOLD = 0.08
- hybrid_search.py 只负责 Alias / Embedding / Clarification

新增文档：
- docs/architecture/semantic_search_calibration.md

当前能力：
Question
↓
Alias Search
↓
Embedding Search
↓
Confidence Check
↓
Clarification / Matched
↓
Search Trace

---

### Day35

完成：
- 新增订单数（order_count）指标
- 新增销量（sales_quantity）指标
- 引入 keyword_group 规则匹配
- 支持 TopN 类业务问题
- 扩展 Golden Cases 至 12 条
- Evaluator 保持 100% 通过率

新增 keyword_group 规则匹配

---

### Day36

完成：
- 渠道数据层核对
- 验证 dim_channel 与 fact_marketing_spend 已存在
- 验证渠道营销数据完整性
- 补充 table_dictionary.yaml 中渠道相关表
- 补充 table_relationships.yaml 中渠道关系
- 验证 table_loader 与 relationship_loader 能读取新增元数据
- 新增 channel_sales_amount 指标
- 新增 channel_refund_rate 指标
- 新增 roi 指标
- 修复 Rule Layer 短 alias / 长 alias 冲突
- Prompt Builder 增加跨事实表先聚合再 JOIN 规则
- Prompt Builder 修正 ROI 不乘以 100
- Prompt Builder 增加 ROI 重叠日期窗口规则
- Golden Cases 扩展到 18 条
- Evaluator 18/18 通过

实现：

自然语言
↓
Rule Layer / Embedding Search
↓
Context Builder
↓
Prompt Builder
↓
DeepSeek
↓
SQL Cleaner
↓
SQL Validator
↓
PostgreSQL
↓
Table
↓
Evaluation

新增支持问题：
- 哪个渠道销售额最高
- 各渠道销售额排名
- 哪个渠道退款率最高
- 各渠道退款率排名
- 哪个渠道ROI最高
- 各渠道ROI排名
- 哪个渠道投放最划算

关键结果：

渠道销售额最高：
- 天猫
- channel_sales_amount = 2445170.92

渠道退款率最高：
- 抖音
- channel_refund_rate_pct = 6.86

渠道 ROI 最高：
- 天猫
- roi ≈ 1.68

发现问题：
1. table_dictionary.yaml 和 table_relationships.yaml 未包含渠道表，导致语义层无法使用渠道数据。
2. business_metrics.yaml 未定义渠道指标，导致“哪个渠道销售额最高”触发 clarification。
3. “哪个渠道退款率最高” 同时命中 refund_rate 与 channel_refund_rate。
4. ROI 初始 SQL 直接 JOIN fact_orders 与 fact_marketing_spend，导致多对多行膨胀。
5. ROI 曾被错误乘以 100。
6. ROI 曾未使用订单与营销投放的重叠时间窗口。
7. Evaluator 暴露出字段别名不稳定问题。

解决：
1. 补充渠道表元数据与关系。
2. 新增渠道销售额、渠道退款率、ROI 指标。
3. metric_loader.search_metrics 增加 match_score，优先保留更具体 alias。
4. Prompt Builder 增加跨事实表指标规则。
5. Prompt Builder 明确 ROI 不乘以 100。
6. Prompt Builder 明确 ROI 使用重叠日期窗口。
7. Prompt Builder 明确字段别名优先使用指标技术名。

结果：

Golden Dataset：
12 Cases
↓
18 Cases

Pass Rate：
100%

---

### Day37

完成：
- CAC 指标建设
- CAC 手写 SQL 验证
- 明确真实首单新客口径
- 新增 cac 指标
- query_service 支持渠道获客成本问题
- Golden Cases 扩展至 20 条
- Evaluator 保持 100% PASS
- 新增 Result-level Evaluation V1
- 新增 Ranking Result Evaluation V1
- 新增 expected_result 校验
- 新增 expected_order 校验
- 新增 Metric Query Plan V1 设计
- 新增 metadata/query_plans.yaml
- 完成 roi_channel_v1 与 cac_channel_v1 读取验证

实现：

自然语言
↓
Hybrid Search
↓
Context Builder
↓
Prompt Builder / Query Plan Metadata
↓
SQL Generator
↓
SQL Cleaner
↓
SQL Validator
↓
PostgreSQL
↓
Table
↓
Result-level Evaluation

新增支持：
- 哪个渠道获客成本最低
- 各渠道获客成本排名
- 哪个渠道拉新效率最高

关键结果：
CAC 最低渠道：
- 天猫
- cac = 2284.40

CAC 排名：
- 天猫
- 微信小程序
- 京东
- 抖音
- 小红书

发现问题：
1. CAC 不能简单使用 COUNT(DISTINCT customer_id)。
2. CAC 不能使用窗口内首单，应使用真实首单新客。
3. ROI / CAC 复杂 SQL 多次暴露 Prompt-only 不稳定。
4. 结构级 Evaluation 无法证明业务答案正确。
5. 排名类问题需要校验返回顺序。

解决：
1. CAC 采用真实首单新客口径。
2. prompt_builder 增加 CAC 首单口径约束。
3. evaluator 增加 expected_result。
4. evaluator 增加 expected_order。
5. 新增 query_plans.yaml，开始将复杂指标 SQL 计划结构化。

结果：
Golden Dataset：
18 Cases
↓
20 Cases

Evaluation：
结构级检查
↓
结构级 + 结果级 + 排名顺序检查

Pass Rate：100%

---

### Day38

完成：
- 新增 query_plan_loader.py
- metadata/query_plans.yaml 接入 loader
- 新增 template_sql_generator.py
- 实现 ROI Template SQL
- 实现 CAC Template SQL
- 实现 parse_limit 与 build_limit_clause
- 支持 Top1 / TopN / Ranking
- 实现 generate_template_sql 统一入口
- query_service 接入 Query Plan Routing
- ROI / CAC 走 template
- 普通指标继续走 llm
- query_service 返回 generation_method
- 新增 template_sql_tests.py
- evaluator 增加 expected_generation_method
- Evaluator 20/20 通过

实现：
  Question
  ↓
  Hybrid Search
  ↓
  Metric Name
  ↓
  Template Routing
  ├─ roi / cac → Template SQL
  └─ ordinary metrics → LLM SQL
  ↓
  SQL Cleaner
  ↓
  SQL Validator
  ↓
  PostgreSQL
  ↓
  Table
  ↓
  Result-level Evaluation

新增支持：
- 渠道ROI Top3
- 获客成本最低的三个渠道
- ROI / CAC template generation
- generation_method validation

关键结果：
Template SQL Tests：
- 12/12 PASS

Golden Dataset：
- 20 Cases
- 100% PASS

发现问题：
1. 仅用 should_limit_one 无法支持 TopN。
2. “最低的三个渠道” 不能被误判为 LIMIT 1。
3. query_plans.yaml 与 template_sql_generator.py 之间存在一定重复，但当前阶段是合理过渡。
4. 需要验证 ROI / CAC 确实走 template，而不是 LLM 恰好生成正确 SQL。

解决：
1. 用 parse_limit 替代 should_limit_one。
2. 明确数量表达优先于极值表达。
3. 增加 generate_template_sql 统一入口。
4. query_service 增加 generation_method。
5. evaluator 增加 expected_generation_method。

结果：
- Query Plan Routing 已接入主链路。
- ROI / CAC 已从 Prompt-only 生成升级为 Template SQL。
- 普通指标保持 LLM 生成。
- Evaluator 保持 100% PASS。

---

### Day39

完成：
- template_sql_generator.py 读取 query_plans.yaml
- ROI / CAC 的 output alias 从 query plan 读取
- ROI / CAC 的 round 从 query plan 读取
- ROI / CAC 的 multiply_by_100 从 query plan 读取
- ROI / CAC 的 default_sort 从 query plan 读取
- 新增 build_formula_expression
- query_plan_tests.py 增强为 Query Plan 配置测试
- query_plan_tests.py 支持配置结构校验
- query_plan_tests.py 支持模板实现一致性校验
- query_plan_tests.py 支持业务规则校验
- query_plan_tests.py 输出 JSON 报告
- template_sql_tests.py 输出 JSON 报告
- 新增 Query Plan Testing V1 文档

当前测试体系：

配置层：
- query_plan_tests.py
- 2/2 PASS
- 输出 docs/evaluation/query_plan_tests_*.json

模板层：
- template_sql_tests.py
- 12/12 PASS
- 输出 docs/evaluation/template_sql_tests_*.json

端到端业务层：
- evaluator.py
- 20/20 PASS
- 输出 docs/evaluation/evaluation_*.json

当前 Query Plan 参数化范围：

- output.formula.alias
- output.formula.round
- output.formula.multiply_by_100
- default_sort.field
- default_sort.direction

关键结论：

- query_plans.yaml 已开始参与 SQL Template 生成。
- ROI / CAC 的业务口径必须通过测试保护。
- 三层测试体系可以分别定位配置、模板和主链路问题。
- 从 Day40 开始，学习方式调整为 B 模式：函数骨架 + TODO + 用户补逻辑 + code review。

---

### Day40

完成：

- 新增 `app/semantic_layer/intent_parser.py`
- 实现 Intent Parser V1
- 支持解析 limit
- 支持解析 ranking_type
- 支持解析 sort_hint
- 支持解析 dimension
- 新增 `app/evaluation/intent_parser_tests.py`
- intent_parser_tests 支持 JSON 报告输出
- `template_sql_generator.py` 新增 intent-based 入口
- 新增 `build_limit_clause_from_intent`
- 新增 `generate_roi_sql_from_intent`
- 新增 `generate_cac_sql_from_intent`
- 新增 `generate_template_sql_from_intent`
- ROI / CAC 模板 SQL 支持从 intent.limit 生成 LIMIT
- `template_sql_tests.py` 扩展到 14 个测试
- template_sql_tests JSON 报告增加 intent_template_tests section
- `query_service.py` 接入 parse_intent
- query_service 返回 intent
- evaluator 增加 expected_intent 校验
- Golden Cases 保持 20/20 PASS

当前主链路：

Question
↓
Intent Parser
↓
Hybrid Search / Metric Recognition
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
Table
↓
Result-level Evaluation

当前 Intent Parser V1 输出：

{
    "question": question,
    "limit": int | None,
    "ranking_type": "top1" | "topn" | "ranking" | "unknown",
    "sort_hint": "asc" | "desc" | None,
    "dimension": "channel" | "category" | None,
}

当前测试结果：

intent_parser_tests.py      5/5 PASS
template_sql_tests.py      14/14 PASS
evaluator.py               20/20 PASS

当前测试报告：

docs/evaluation/
├── evaluation_*.json
├── query_plan_tests_*.json
├── template_sql_tests_*.json
├── intent_parser_tests_*.json

关键结论：

- Intent Parser 已正式接入 query_service 主链路。
- ROI / CAC 模板 SQL 已开始消费 intent.limit。
- query_service 返回 intent 后，系统可评估用户问题是否被正确理解。
- evaluator 已从“结果正确性评估”扩展到“意图解析 + 生成路径 + 业务结果”的综合评估。
- 后续应将最终排序方向逻辑抽象为 final_sort_direction。

技术债：

1. `template_sql_generator.py` 中仍保留旧的 question 解析逻辑，后续可逐步迁移到 Intent Parser。
2. `sort_hint` 当前尚未真正参与最终排序方向决策。
3. Intent Parser V1 仍是规则型，后续需要支持更多中文表达。
4. expected_intent 当前只覆盖关键 cases，后续可逐步扩展。

---

### Day41

完成：
- 新增 `resolve_sort_direction`
- 新增 `enrich_intent_with_query_plan`
- query_service 接入 enriched intent
- intent 增加 `final_sort_direction`
- intent 增加 `sort_field`
- template_sql_generator 新增 `build_order_by_clause_from_intent`
- ROI / CAC 模板 SQL 支持从 intent 生成 ORDER BY
- generate_roi_sql 支持外部传入 order_by_clause
- generate_cac_sql 支持外部传入 order_by_clause
- 支持用户显式排序方向覆盖指标默认排序方向
- 新增问题能力：`渠道ROI从低到高排名`
- 新增 Golden Case：case_026
- Golden Cases 从 20 扩展到 21
- 新增 `intent_resolver_tests.py`
- 更新 `docs/architecture/query_plan_testing_v1.md`
- template_sql_tests 扩展到 15 个测试

当前排序决策规则：

intent.sort_hint
>
query_plan.default_sort.direction
>
None

示例：

各渠道ROI排名
→ sort_hint = None
→ query_plan.default_sort.direction = desc
→ final_sort_direction = desc

渠道ROI从低到高排名
→ sort_hint = asc
→ query_plan.default_sort.direction = desc
→ final_sort_direction = asc

各渠道获客成本排名
→ sort_hint = None
→ query_plan.default_sort.direction = asc
→ final_sort_direction = asc

当前 enriched intent 示例：
{
    "question": "渠道ROI从低到高排名",
    "limit": None,
    "ranking_type": "ranking",
    "sort_hint": "asc",
    "dimension": "channel",
    "final_sort_direction": "asc",
    "sort_field": "roi",
}

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
└─ 普通指标 → LLM SQL
↓
SQL Cleaner
↓
SQL Validator
↓
PostgreSQL
↓
Table
↓
Result-level Evaluation

当前测试体系：
query_plan_tests.py          2/2 PASS
intent_parser_tests.py       5/5 PASS
intent_resolver_tests.py     5/5 PASS
template_sql_tests.py       15/15 PASS
evaluator.py                21/21 PASS

当前测试报告：
docs/evaluation/
├── evaluation_*.json
├── query_plan_tests_*.json
├── template_sql_tests_*.json
├── intent_parser_tests_*.json
├── intent_resolver_tests_*.json

关键结论：
- `sort_hint` 表示用户显式排序方向。
- `default_sort` 表示指标默认排序规则。
- `final_sort_direction` 表示系统最终排序决策。
- 用户显式排序方向应优先于指标默认排序方向。
- intent-based template 现在已同时消费 `limit` 和 `final_sort_direction`。
- evaluator 已支持校验 expected_intent，可验证用户问题是否被正确理解。

技术债：
1. 普通指标仍主要走 LLM，尚未充分利用 intent。
2. 普通指标尚未纳入 query_plan，因此 `sort_field` 可能为 None。
3. template_sql_generator 中仍保留旧 question 解析逻辑。
4. sort_hint 规则仍需支持更多中文表达。

---

### Day42

完成：
- prompt_builder 支持 intent 参数
- 新增 build_intent_context
- Prompt 中加入结构化意图上下文
- Prompt 增加 intent 使用规则
- sql_generator 支持 intent 参数
- query_service 在 LLM 路径传入 enriched intent
- 普通指标 LLM SQL 接入 Intent Context
- 修复普通指标字段别名漂移问题
- 新增 Golden Case：case_027 渠道销售额从低到高排名
- 新增 Golden Case：case_028 渠道销售额Top3
- Golden Cases 从 21 扩展到 23
- 新增 prompt_builder_tests.py
- prompt_builder_tests 输出 JSON 报告
- evaluator 保持 23/23 PASS

当前普通指标 LLM 路径：
question
↓
parse_intent
↓
enrich_intent_with_query_plan
↓
generate_sql(question, intent=intent)
↓
build_prompt(question, intent=intent)
↓
LLM SQL

当前双路径 SQL 生成：
ROI / CAC → Intent + Query Plan + Template SQL
普通指标 → Intent + Prompt + LLM SQL

新增验证：
case_027：渠道销售额从低到高排名
→ generation_method = llm
→ final_sort_direction = asc
→ ORDER BY channel_sales_amount ASC
→ 23/23 PASS

case_028：渠道销售额Top3
→ generation_method = llm
→ limit = 3
→ LIMIT 3
→ 23/23 PASS


发现问题：
1. Prompt 接入 Intent 后，LLM 将 dimension = channel 误用为字段别名 channel。
2. prompt_builder.py 规则数量接近 30 条，开始出现臃肿风险。
3. 普通指标没有 query_plan，因此 sort_field 仍为 None。
4. TopN 默认排序方向仍主要依赖 LLM 语义理解。

解决：
1. Prompt 明确 dimension = channel 时必须使用 dim_channel.channel_name。
2. Prompt 明确 channel 维度输出字段别名必须是 channel_name，禁止使用 channel。
3. 新增 prompt_builder_tests.py，保护 intent context 注入。
4. 新增普通指标 Golden Cases，验证 LLM 路径是否受 Intent Context 约束。

结果：
query_plan_tests.py          2/2 PASS
intent_parser_tests.py       5/5 PASS
intent_resolver_tests.py     5/5 PASS
template_sql_tests.py       15/15 PASS
prompt_builder_tests.py      2/2 PASS
evaluator.py                23/23 PASS

关键结论：
- Intent 不等于 Template。
- 普通指标不走 Template，但仍然需要 Intent Context。
- Intent 负责理解用户问题，Template / LLM 负责生成 SQL。
- Prompt 接入 Intent 后，需要明确字段映射，避免 LLM 将 intent 枚举值当作 SQL 字段别名。
- prompt_builder.py 后续需要模块化，避免继续堆规则。

技术债：
1. prompt_builder.py 规则臃肿，需要 Prompt Builder V2。
2. 普通指标尚未纳入 query_plan，sort_field 仍可能为 None。
3. TopN 默认排序方向是否要在 Intent Resolver 中兜底，后续需要评估。
4. prompt_builder_tests 当前只检查 Prompt 片段，后续可扩展字段别名规则检查。

---

### Day43

完成：

- 合并完成原 Day43：普通指标 Intent Cases 收尾
- 合并完成原 Day44：Result-level Evaluation V2
- 新增 case_029：品类退款率Top3
- 新增 case_030：品类退款率从低到高排名
- 新增 case_031：销量最低的三个品类
- Golden Cases 扩展至 26
- 普通指标 LLM 路径继续验证 Intent Context
- 新增 expected_order 覆盖普通指标排序结果
- 新增 check_expected_rows
- evaluator 支持 expected_rows 多行结果校验
- evaluator 支持 rows_mismatches 报告
- evaluator 保持 26/26 PASS

当前新增验证：

case_029：品类退款率Top3
→ generation_method = llm
→ limit = 3
→ ranking_type = topn
→ dimension = category
→ ORDER BY refund_rate_pct DESC
→ LIMIT 3
→ expected_rows 校验前三行品类与退款率数值

case_030：品类退款率从低到高排名
→ generation_method = llm
→ ranking_type = ranking
→ sort_hint = asc
→ final_sort_direction = asc
→ dimension = category
→ ORDER BY refund_rate_pct ASC
→ expected_rows 校验完整品类退款率升序结果

case_031：销量最低的三个品类
→ generation_method = llm
→ limit = 3
→ ranking_type = topn
→ sort_hint = asc
→ final_sort_direction = asc
→ dimension = category
→ ORDER BY sales_quantity ASC
→ LIMIT 3
→ expected_rows 校验前三行品类与销量数值

当前测试结果：

Total: 26
Passed: 26
Failed: 0
Pass Rate: 100.0%

关键结论：

1. 普通指标接入 Intent Context 的价值不是让简单 SQL 从错变对，而是提升系统的可控性、可解释性、可评估性和可扩展性。
2. 普通指标仍走 LLM SQL，但 intent 可以约束 dimension、limit、ranking_type、sort_hint 和 final_sort_direction。
3. expected_rows 可以同时校验多行对象、顺序和数值，是 Result-level Evaluation V2 的核心能力。
4. expected_result、expected_order、expected_rows 不互相删除，而是分层使用。
5. Result-level Evaluation V2 为 Answer Layer 提供可信数据基础。

技术债：

1. 普通指标目前没有 query_plan，因此 sort_field 通常为 None。
2. 普通指标 TopN 默认排序方向仍部分依赖 LLM 语义理解。
3. 后续可考虑为普通指标增加 lightweight query_plan / default_sort。
4. evaluator 测试报告保存逻辑仍有重复，后续可统一 report writer。
5. prompt_builder.py 规则臃肿，后续需要 Prompt Builder V2 模块化。

---

## 当前交接摘要（Day42结束）

当前处于：
Phase2：Business Semantic Layer & Text-to-SQL
Day43 / 100

当前系统主线：
自然语言问题
↓
Intent Parser
↓
Intent Resolver
↓
Hybrid Search / Metric Recognition
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

当前关键模块：
app/semantic_layer/intent_parser.py
app/semantic_layer/query_plan_loader.py
app/semantic_layer/hybrid_search.py
app/text_to_sql/template_sql_generator.py
app/text_to_sql/query_service.py
app/text_to_sql/prompt_builder.py
app/text_to_sql/sql_generator.py
app/evaluation/evaluator.py
app/evaluation/golden_questions.py

当前新增测试：
app/evaluation/query_plan_tests.py
app/evaluation/intent_parser_tests.py
app/evaluation/intent_resolver_tests.py
app/evaluation/template_sql_tests.py
app/evaluation/prompt_builder_tests.py  
app/evaluation/evaluator.py

当前测试结果：
- query_plan_tests.py：2/2 PASS
- intent_parser_tests.py：5/5 PASS
- intent_resolver_tests.py：5/5 PASS
- template_sql_tests.py：15/15 PASS
- prompt_builder_tests.py：2/2 PASS
- evaluator.py：26/26 PASS


当前支持指标：
item_sales_amount
order_paid_amount
refund_rate
order_count
sales_quantity
channel_sales_amount
channel_refund_rate
roi
cac

当前复杂指标策略：
roi → Query Plan + Template SQL
cac → Query Plan + Template SQL
其他普通指标 → LLM SQL

当前 intent 输出字段：

```python
{
    "question": question,
    "limit": int | None,
    "ranking_type": "top1" | "topn" | "ranking" | "unknown",
    "sort_hint": "asc" | "desc" | None,
    "dimension": "channel" | "category" | None,
    "final_sort_direction": "asc" | "desc" | None,
    "sort_field": str | None,
}
```

当前最重要的设计结论：
1. ROI / CAC 这类复杂跨事实表指标不应长期依赖 LLM 自由生成 SQL。
2. Query Plan Routing 负责把高风险复杂指标分流到 Template SQL。
3. Intent Parser 负责解析用户问题中的 limit / ranking / dimension / sort_hint。
4. Intent Resolver 负责融合用户排序意图和指标默认排序规则。
5. Template SQL 当前已消费 intent.limit 和 intent.final_sort_direction。
6. 普通指标仍走 LLM，下一步要把 enriched intent 注入 Prompt。
7. evaluator 已从“SQL 是否能执行”升级为“结构 + 结果 + 排名 + 生成路径 + intent”的综合评估。

当前主要技术债：
1. 普通指标尚未充分利用 intent。
2. prompt_builder 还没有接收 enriched intent。
3. 普通指标没有 query_plan，因此 sort_field 可能为 None。
4. template_sql_generator 仍保留旧 question 解析逻辑。
5. evaluation 测试文件中 JSON report 保存逻辑有重复。
6. Intent Parser V1 仍是规则型，对中文表达覆盖有限。

下一步 Day44：Answer Layer V1

目标：
- SQL Table → 中文业务回答
- 让系统不仅返回 table，还能生成业务解释
- 优先使用规则型 Answer Layer，避免过早引入新的 LLM 不确定性

学习安排：
1. 设计 answer_generator.py 的输入输出
2. 实现 Top1 / TopN / Ranking 三类基础回答
3. query_service 返回 answer
4. Golden Cases 增加 expected_answer_points
5. evaluator 增加 answer point 校验
6. 复盘 Answer Layer 与 SQL Result Evaluator 的关系

交付：
- app/text_to_sql/answer_generator.py
- query_service 返回 answer
- evaluator 支持 expected_answer_points
- 3-5 个 answer cases
- evaluator 100% PASS
