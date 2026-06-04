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
Semantic Search
↓
Context Builder
↓
Prompt Builder
↓
DeepSeek
↓
SQL Cleaner
↓
SQL


已验证问题：
- 哪个品类退款率最高
- 哪个品类销售额最高
- 哪个渠道销售额最高
- 各品类销售额排名

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

当前能力：自然语言问题 → 业务语义检索 → Prompt构建 → SQL生成 → SQL校验 → PostgreSQL执行 → 结构化

## Evaluation Framework

支持：

- Golden Questions
- SQL Evaluation
- Failure Case Analysis
- Prompt Optimization

评估流程：

Question
↓
SQL Generation
↓
SQL Validation
↓
Evaluation
↓
Failure Analysis
↓
Prompt Optimization

当前评估结果：

- Golden Questions：3
- Pass Rate：100%

## Text2SQL 示例

问题：哪个品类的退款率最高？

生成SQL：

```sql
SELECT
    dp.category,
    ROUND(
        COALESCE(SUM(fr.refund_amount), 0)
        / NULLIF(SUM(foi.item_paid_amount), 0)
        * 100,
        2
    ) AS refund_rate_pct
FROM fact_order_items foi
INNER JOIN dim_product dp
    ON foi.product_id = dp.product_id
INNER JOIN fact_orders fo
    ON foi.order_id = fo.order_id
LEFT JOIN fact_refunds fr
    ON foi.order_item_id = fr.order_item_id
WHERE fo.order_status = 'paid'
GROUP BY dp.category
ORDER BY refund_rate_pct DESC
LIMIT 1;

返回结果：
[
  {
    "category": "精华",
    "refund_rate_pct": 10.0
  }
]
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

Version: v0.4
完成度：Day29 / 100
当前实现：自然语言问题 → 业务语义检索 → Prompt构建 → SQL生成 → SQL校验 → PostgreSQL执行 → Table → Evaluation

