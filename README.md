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
- Golden Questions：20
- Pass Rate：100%
- Template SQL Tests：12/12 PASS
- 支持 SQL 结构级检查
- 支持 Top1 结果级校验
- 支持排名顺序校验
- 支持 generation_method 校验

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

## Evaluation Framework V2

支持：
- Golden Questions
- Failure Case Analysis
- Prompt Optimization
- Semantic Alias Search

支持业务表达：
- 销售额最高
- 卖得最好
- 退款率最高
- 退货最严重
- 订单最多
- 销量最高
- 渠道销售额最高
- 渠道销售额排名
- 渠道退款率最高
- 渠道退款率排名
- 渠道 ROI 最高
- 渠道 ROI 排名
- 哪个渠道投放最划算
- 渠道 CAC 最低
- 渠道获客成本最低
- 渠道获客成本排名
- 哪个渠道拉新效率最高

当前暂不支持：
- 利润分析
- 复杂时间筛选
- 多轮追问
- 生产环境动态数据校验
- SQL Template / Query Plan主链路接入
- Intent Parser
- 多指标组合分析

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

Version: v0.12
完成度：Day38 / 100
当前实现：自然语言问题 → 业务语义检索 → Prompt构建 → SQL生成 → SQL校验 → PostgreSQL执行 → Table → Result-level Evaluation

