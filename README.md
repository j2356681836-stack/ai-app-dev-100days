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

# 学习记录

本仓库 README 只保留公开项目说明、当前系统能力、核心架构、测试结果与阶段进度。
详细学习记录、阶段复盘、交接说明和面试训练材料不在公开仓库中维护。

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

当前系统已从早期的单次 Text-to-SQL 链路，升级为业务语义层驱动的双路径 SQL 生成架构。

用户问题
↓
Intent Parser
↓
Intent Resolver
↓
Hybrid Search / Metric Recognition
├── Alias Match
├── Keyword Group Match
├── Embedding Match
└── Clarification
↓
Query Plan Routing
├── ROI / CAC → Template SQL
└── 普通指标 → LLM SQL with Intent Context
↓
SQL Cleaner
↓
SQL Validator
↓
PostgreSQL
↓
Result Formatter
↓
Answer Layer
↓
Evaluation Workflow


Phase3 已完成 LangGraph clarification branch 最小 prototype：
parse_intent
↓
search_metric
↓
route_metric_status
├── matched → continue_pipeline
├── needs_clarification → clarification
└── error → fail

当前 LangGraph 仅作为 workflow prototype，不替代 Phase2 主链路。

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
    AS refund_rate_pct
FROM fact_order_items foi
JOIN dim_product dp
    ON foi.product_id = dp.product_id
JOIN fact_orders fo
    ON foi.order_id = fo.order_id
LEFT JOIN fact_refunds fr
    ON foi.order_item_id = fr.order_item_id
WHERE fo.order_status = 'paid'
GROUP BY dp.category
ORDER BY refund_rate_pct DESC;

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

当前系统支持：
Question
↓
Intent Parser
↓
Intent Resolver
↓
Hybrid Search / Metric Recognition
↓
Query Plan Routing
├── ROI / CAC → Template SQL
└── 普通指标 → LLM SQL with Intent Context
↓
SQL Cleaner
↓
SQL Validator
↓
PostgreSQL
↓
Table
↓
Answer

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
- Top1
- TopN
- Ranking
- ASC / DESC 排序
- 品类维度分析
- 渠道维度分析
- 普通指标 LLM SQL
- ROI / CAC Template SQL
- clarification 分支

已验证问题示例：
- 哪个品类退款率最高
- 品类退款率 Top3
- 品类退款率从低到高排名
- 销量最低的三个品类
- 哪个渠道销售额最高
- 各渠道销售额排名
- 哪个渠道 ROI 最高
- 各渠道 ROI 排名
- 渠道 ROI 从低到高排名
- 哪个渠道获客成本最低
- 各渠道获客成本排名
- 最赚钱（进入 clarification）

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
用户问题：品类退款率Top3
系统返回：品类退款率Top3分别是：精华 10.0%，防晒 4.55%，面膜 4.48%。

当前原则：
- 只基于 SQL table 结果生成回答
- 不编造原因
- 不做未经验证的业务推断
- Answer 通过 expected_answer_points 做关键事实校验

---

## Evaluation Workflow

当前项目不是只依赖人工观察 SQL 是否能运行，而是构建了多层 Evaluation Workflow。

当前评估体系：
- deterministic evaluator：校验 SQL 结果、字段、数值、排序、intent、generation_method 和 answer key facts
- prompt_builder_tests：校验 Prompt 关键规则是否保留
- answer_judge：通过 mock / LLM-as-Judge 评估回答质量
- Ragas evaluation：评估回答是否被 SQL 查询结果上下文支撑
- analyst_graph_tests：验证 LangGraph workflow 分支是否正确

当前测试结果：

| 测试模块 | 结果 |
|---|---:|
| query_plan_tests.py | 2/2 PASS |
| intent_parser_tests.py | 5/5 PASS |
| intent_resolver_tests.py | 5/5 PASS |
| template_sql_tests.py | 15/15 PASS |
| prompt_builder_tests.py | 5/5 PASS |
| retrieval_evaluator.py --strict | 6/6 PASS |
| evaluator.py | 26/26 PASS |
| answer_judge.py --mode mock | 6/6 PASS |
| answer_judge.py --mode llm | 6/6 PASS |
| ragas_eval.py --include-negative | 6/6 expectation passed |
| analyst_graph_tests.py | 3/3 PASS |
| sql_repair_graph_tests.py | 4/4 PASS |

当前定位：
- deterministic evaluator 负责业务结果正确性
- answer_judge 负责回答质量
- Ragas 负责上下文忠实度
- graph tests 负责 workflow 分支稳定性

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
- BGE Small（用于 Embedding Search）
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

状态：✅ 已完成

完成内容：
- PostgreSQL 环境搭建
- 星型模型设计
- 美妆业务模拟数据集
- Business Metrics
- Table Dictionary
- Relationship Dictionary
- Hybrid Search
- Clarification Layer
- Intent Parser
- Intent Resolver
- Query Plan Routing
- ROI / CAC Template SQL
- 普通指标 LLM SQL with Intent Context
- Prompt Builder V2
- SQL Cleaner
- SQL Validator
- SQL Runner
- Result Formatter
- Answer Layer V1
- Deterministic Evaluation
- LLM-as-Judge Answer Evaluation
- Ragas Evaluation
- LangGraph Clarification Branch Prototype

当前能力：
自然语言问题
→ Intent Parser
→ Intent Resolver
→ Hybrid Search
→ Query Plan Routing
→ Template SQL / LLM SQL
→ SQL 校验
→ PostgreSQL 执行
→ Result Formatter
→ Answer Layer
→ Evaluation Workflow

Phase2 当前定位：可演示、可解释、可评估的 AI Data Analyst / Text-to-SQL 原型

当前边界：
不是完整企业级 BI Copilot
尚未实现 SQL repair loop
尚未实现 eval-driven retry
尚未实现完整 Business Insight Layer
当前 LangGraph 仅完成 clarification branch prototype

---

### Evaluation Framework V5

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
- Ragas Faithfulness Evaluation
- LangGraph Branch Tests
- 正例 / 负例 answer eval
- Evaluation JSON 报告输出

当前评估结果：
- Golden Questions：26
- deterministic evaluator：26/26 PASS
- query_plan_tests.py：2/2 PASS
- intent_parser_tests.py：5/5 PASS
- intent_resolver_tests.py：5/5 PASS
- template_sql_tests.py：15/15 PASS
- prompt_builder_tests.py：5/5 PASS
- answer_eval_cases：6
- answer_judge mock：6/6 PASS
- LLM-as-Judge：6/6 PASS
- Ragas：6/6 expectation passed
- analyst_graph_tests.py：3/3 PASS

---

### Phase2 Milestone Summary

Phase2 完成了 Business Semantic Layer、Text-to-SQL、Answer Layer、Evaluation Workflow 和 LangGraph clarification branch prototype 的核心闭环。

阶段关键成果：
- 构建美妆业务模拟 BI 数据集，覆盖商品、用户、订单、订单明细、退款、评价和营销投放数据。
- 建立业务语义层，管理业务指标、表字段解释、表关系和复杂指标 Query Plan。
- 实现 Hybrid Search，结合 alias、keyword group、embedding 和 clarification 识别用户想查询的业务指标。
- 实现 Intent Parser / Intent Resolver，支持解析 Top1、TopN、Ranking、排序方向和分析维度。
- 实现 Query Plan Routing，使 ROI / CAC 等复杂指标走 Template SQL，普通指标走 LLM SQL with Intent Context。
- 实现 Answer Layer V1，将 SQL 查询结果转换为事实型中文回答。
- 建立多层 Evaluation Workflow，覆盖 deterministic evaluator、prompt_builder_tests、answer_judge、Ragas evaluation 和 graph branch tests。
- 完成 LangGraph clarification branch 最小 prototype，为 Phase3 workflow 化打下基础。

当前测试结果：
- evaluator.py：26/26 PASS
- query_plan_tests.py：2/2 PASS
- intent_parser_tests.py：5/5 PASS
- intent_resolver_tests.py：5/5 PASS
- template_sql_tests.py：15/15 PASS
- prompt_builder_tests.py：5/5 PASS
- answer_judge.py --mode mock：6/6 PASS
- answer_judge.py --mode llm：6/6 PASS
- ragas_eval.py --include-negative：6/6 expectation passed
- analyst_graph_tests.py：3/3 PASS

当前边界：
- 当前系统是可演示、可解释、可评估的 AI Data Analyst / Text-to-SQL 原型。
- 当前还不是完整企业级 BI Copilot。
- 尚未实现 SQL repair loop。
- 尚未实现 eval-driven retry。
- 尚未实现完整 Business Insight Layer。
- Phase3 Day51 已完成 dependency lock，当前依赖环境已通过 `pip check` 与核心回归测试。
-当前 retrieval / clarification 能力已经可以评估模糊问题的候选质量，但 reranker 仍是轻量规则型实现。后续随着指标体系扩展，需要继续扩大 retrieval eval cases，并评估是否引入更系统的 rerank 策略。

---

## Phase 3

Agent Workflow

状态：🟡 进行中

Phase3 当前进展：
- Day51 完成 Dependency Lock / Phase3 Environment Stabilization
- Day52 完成 Retrieval Evaluator / Clarification Candidate Ranking
- Day53 完成 LangGraph SQL Validation / Repair Design
- Day54 完成 SQL Repair Node Minimal Prototype
- Day55 完成 SQL Repair Graph Test Harness
- Day56 完成 Eval-driven Retry Design V1

当前稳定依赖基线：
- `langchain==0.3.30`
- `langchain-core==0.3.86`
- `langchain-openai==0.3.35`
- `langchain-community==0.3.31`
- `langgraph==0.6.11`
- `ragas==0.4.3`
- `sentence-transformers==5.5.1`

Phase3 后续重点：
- Eval-driven Retry Design
- Multi-step Analysis / Business Insight Layer
- Phase3 First Milestone Review

当前原则：
- 不推翻 Phase2 主链路
- 复用 Phase2 已完成模块
- 先稳定依赖环境，再继续扩展 LangGraph 功能

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

## 当前已完成：Phase2

Question
↓
Intent Parser
↓
Intent Resolver
↓
Hybrid Search / Metric Recognition
↓
Query Plan Routing
├── ROI / CAC → Template SQL
└── 普通指标 → LLM SQL with Intent Context
↓
SQL Validation
↓
PostgreSQL
↓
Answer Layer
↓
Evaluation Workflow

## 正在进行：Phase3

Question
↓
LangGraph Workflow
↓
Intent / Metric Recognition
↓
Clarification Branch
↓
SQL Generation
↓
SQL Validation / Repair
↓
Execution
↓
Evaluation-driven Retry
↓
Answer

## 最终目标

Question
↓
Multi-Agent Workflow
↓
Business Semantic Layer
↓
SQL / Tool Calling
↓
Execution
↓
Business Analysis
↓
Dashboard / Answer

---

# 学习记录

公开版架构说明将在后续整理。

记录内容：
- 每日学习日志
- 项目进展
- 架构演进
- 踩坑记录
- 技术总结

---

# 当前版本

Version: v0.31
完成度：Day56 / 100
当前实现：

自然语言问题
→ Intent Parser
→ Intent Resolver
→ Hybrid Search
→ Query Plan Routing
→ Template SQL / LLM SQL with Intent Context
→ SQL Cleaner
→ SQL Validator
→ PostgreSQL
→ Result Formatter
→ Answer Layer V1
→ Deterministic Evaluation
→ LLM-as-Judge Answer Evaluation
→ Ragas Evaluation
→ LangGraph Clarification Branch Prototype
→ SQL Repair Graph Test Harness

当前阶段：
Phase2 已完成
Phase3 进行中
下一步：Eval Result Node Skeleton


