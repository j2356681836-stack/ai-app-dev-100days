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

当前系统已从 Phase2 的线性 Text-to-SQL 链路，升级为由 LangGraph 控制 SQL 运行时状态、失败路由和受控修复的工作流。

```text
用户问题
↓
Intent Parser
↓
Hybrid Search / Metric Recognition
├── needs_clarification → Clarification → END
├── error → Fail → END
└── matched
    ↓
    Metric Selection
    ├── metrics 为空 → Metric Fail → END
    └── metric selected
        ↓
        Query Plan Loading
        ↓
        Intent Resolution
        ↓
        SQL Generation
        ├── ROI / CAC → Template SQL
        └── 普通指标 → LLM SQL with Intent Context
        ↓
        SQL Cleaner
        ├── empty SQL → Runtime Evaluation
        └── cleaned SQL
            ↓
            SQL Validator
            ├── validation error → Runtime Evaluation
            └── valid
                ↓
                PostgreSQL Execution
                ↓
                Runtime Evaluation
                ├── passed → Result Formatter → Answer Layer → Finish
                ├── retryable LLM execution error → SQL Repair → SQL Cleaner
                └── non-retryable → SQL Fail
```

当前在线 Graph 负责：
- clarification 与 metric failure 分支
- Template / LLM SQL 双路径
- SQL cleaning、validation 和 execution
- 统一 `evaluation_result`
- LLM SQL execution error 的一次受控修复
- validation error、Template execution error、empty result 和 max retries 的失败路由

离线 Evaluation Workflow 继续负责：
- deterministic evaluator
- retrieval evaluator
- prompt builder tests
- answer judge
- Ragas evaluation

兼容边界：
- LangGraph 正式入口为 `ask_with_graph()`
- `query_service.ask()` 继续保留 Phase2 线性兼容路径
- Ragas、answer judge 和完整 evaluator 不进入在线 Graph

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
```text
metadata/
├── business_metrics.yaml
├── query_plans.yaml
├── table_dictionary.yaml
├── table_relationships.yaml
```
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

```text
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
```

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

## LangGraph SQL Runtime Workflow

Phase3 Day59 完成 SQL Runtime Integration，Day60 完成代码清理、正式测试迁移和第一里程碑回归。

当前能力：
- matched 路径不再依赖 `continue_pipeline_node`
- Query Plan loading、Intent resolution 和 SQL generation 已拆为独立 nodes
- SQL cleaning、validation、execution 和 result formatting 已接入正式 Graph
- `evaluate_runtime_result_node` 统一生成 `evaluation_result`
- `route_evaluation_result` 只读取评估结果并返回下一条路径
- LLM SQL execution error 可进入一次受控 repair
- repair 后必须重新经过 clean、validate 和 run
- validation error 不进入 repair
- Template SQL execution error 不进入 LLM repair
- empty result 当前不自动 retry
- 达到修复上限后返回 `max_retries_exceeded`
- matched 但 metrics 为空时进入 `metric_fail`
- compiled Graph 已覆盖 9 条端到端路径

Day60 清理结果：
- 删除不可达的 `continue_pipeline_node`
- 删除未使用的 `ask_with_resolved_metric` import
- 删除旧 `route_execution / retry_or_fail`
- 删除临时 `day59_node_smoke_test.py`
- 将 SQL Cleaner normalization 固化为正式测试

当前边界：
- 最多自动 repair 一次
- 真实 LLM repair 准确率尚未进行大规模评估
- Business Insight Layer、权限和审计尚未实现

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
- retrieval evaluator：校验 metric retrieval、clarification 和候选质量
- SQL Cleaner tests：校验 SQL 结尾分号与 normalization
- SQL repair contract tests：校验 runtime evaluation、retry guard 和 repair state transition
- compiled Graph tests：校验正式 LangGraph 路径
- answer judge：通过 mock / LLM-as-Judge 评估回答质量
- Ragas evaluation：评估回答是否被 SQL 查询结果上下文支撑

### Day60 已验证基线

| 测试模块 | 结果 |
|---|---:|
| sql_cleaner_tests.py | 6/6 PASS |
| sql_repair_graph_tests.py | 9/9 PASS |
| analyst_graph_tests.py | 9/9 PASS |
| retrieval_evaluator.py --strict | 6/6 PASS |
| evaluator.py | 26/26 PASS |
| answer_judge.py --mode mock | 6/6 PASS |
| answer_judge.py --mode llm | 6/6 PASS |
| ragas_eval.py --include-negative | 6/6 expectation passed |
| pip check | No broken requirements found |

### 最近专项测试记录

以下测试用于保护 Query Plan、Intent 和 Prompt 的局部实现；它们不是 Day60 完整回归中单独重跑的结果。

| 测试模块 | 最近记录 |
|---|---:|
| query_plan_tests.py | 2/2 PASS |
| intent_parser_tests.py | 5/5 PASS |
| intent_resolver_tests.py | 5/5 PASS |
| template_sql_tests.py | 15/15 PASS |
| prompt_builder_tests.py | 5/5 PASS |

当前定位：
- deterministic evaluator 负责业务结果正确性
- answer_judge 负责回答质量
- Ragas 负责上下文忠实度
- graph tests 负责 workflow 分支稳定性
- 专项测试负责快速定位 Metadata、Intent、Template 和 Prompt 问题

---

# 数据库设计

当前使用：
- PostgreSQL 15
- pgvector
- SQLAlchemy 2.0

Beauty BI V1 稳定数据模型：
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

项目当前使用 Beauty BI V1 作为稳定运行与回归数据集。

## Beauty BI V1 数据规模

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

## Beauty BI V1 已植入业务规律

### 商品规律

- 夏季防晒销量增长
- 精华退款率显著高于其它品类

### 渠道规律

- 小红书 ROI 持续下降

### 用户规律

- 会员用户购买频率更高

---

## Beauty BI Dataset V2 当前状态

Day61 完成 Dataset V2 Design Baseline，Day62 完成 Manifest Skeleton 与 Schema Foundation，Day63 完成 Transaction Facts DDL 与约束验证，Day64 完成 Fixed Dimensions & Identity Seed，Day65 完成 Time-driven Transaction Seed 与原子写库。

当前已完成：
- 建立独立目录 `app/db/beauty_bi_v2/`；
- 建立 `dataset_manifest.yaml`，绑定版本、固定日期、随机种子、业务口径与生成参数；
- 建立 `manifest_loader.py`，集中校验固定维度、身份关系和交易生成合同；
- 建立 16 张 Beauty BI V2 P0 Schema 表；
- 完成 10 张固定维度与身份基础表的确定性 Seed；
- 完成独立交易生成模块 `seed_transactions.py`；
- 完成营销费用、订单、订单明细、履约、退款、评价和 R12 会员等级历史；
- 使用独立 deterministic RNG streams，保证重复生成结果一致；
- 使用单一数据库事务写入五张剩余交易事实表；
- 完成业务键解析、外键检查、金额公式、时间顺序、等级区间与数据库逐行比较；
- 保持 V1 `public` Schema 不变，Graph integration 继续关闭。

small Profile 当前入库规模：

| 表 | 行数 |
|---|---:|
| `dim_date` | 762 |
| `dim_region` | 16 |
| `dim_channel` | 6 |
| `dim_product` | 100 |
| `dim_campaign` | 8 |
| `dim_promotion` | 8 |
| `dim_customer` | 5000 |
| `dim_membership_account` | 3250 |
| `bridge_customer_membership` | 3000 |
| `fact_membership_channel_binding_history` | 5053 |
| `fact_marketing_spend` | 3412 |
| `fact_orders` | 40000 |
| `fact_order_items` | 66889 |
| `fact_refunds` | 5925 |
| `fact_reviews` | 16535 |
| `fact_membership_tier_history` | 6564 |

Day65 关键验证：
- 订单状态：38056 delivered / 1944 cancelled；
- 完成退款：5013；
- 评价：16535；
- 会员等级变化：3250 initial / 2728 upgrade / 586 downgrade；
- 2026 年 1 月新支付订单：0；
- 观察尾窗送达、退款和评价事件存在；
- 订单头金额与明细汇总一致；
- 退款金额与数量不超过购买上限；
- 评价不存在未来退款信息泄漏；
- `member_level_at_order` 与支付时点有效等级一致；
- 每个会员账户只有一个开放等级区间，历史区间无重叠；
- 原子写库和数据库逐行业务字段比较通过。

当前状态：

```text
Design：completed
Status：draft
Manifest Skeleton：completed
Manifest Loader：completed
Schema Foundation：completed（11 tables）
Transaction Facts DDL：completed（5 tables）
V2 Schema Total：16 tables
Fixed Dimensions & Identity Seed：completed（10 tables）
Time-driven Transaction Seed：completed
fact_membership_tier_history Seed：completed
Day62 Foundation Validation：passed
Day63 Transaction Facts Validation：passed
Day64 Deterministic Seed Validation：passed
Day65 Transaction Seed Validation：passed
Full Acceptance Gates：not_run
Metadata V2：not started
Golden Cases V2：not started
Graph integration：disabled
```

Beauty BI V1 继续作为 Latest Stable Baseline。Day65 写库成功不等于 Dataset V2 已成为 Candidate 或 Stable；P01–P09 正式 Acceptance、Metadata V2、Golden Cases V2 和 AI 主链路回归仍未完成。

---

# 技术栈# 技术栈

## Backend

- Python 3.10.3
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

```text
app/
├── api/
├── agents/
├── db/
│   └── beauty_bi_v2/
│       ├── __init__.py
│       ├── dataset_manifest.yaml
│       ├── schema.sql
│       ├── init_schema.py
│       ├── db_check.py
│       ├── manifest_loader.py
│       ├── seed_dimensions.py
│       └── seed_transactions.py
├── semantic_layer/
├── text_to_sql/
└── evaluation/
metadata/
├── business_metrics.yaml
├── query_plans.yaml
├── table_dictionary.yaml
└── table_relationships.yaml
docs/
```
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

Phase2 关闭时能力：
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

Phase2 关闭时定位：可演示、可解释、可评估的 AI Data Analyst / Text-to-SQL 原型

Phase2 关闭时边界：
不是完整企业级 BI Copilot
尚未实现 SQL repair loop
尚未实现 eval-driven retry
尚未实现完整 Business Insight Layer
LangGraph 仅完成 clarification branch prototype

---

### Evaluation Framework V5

Phase2 关闭时支持：
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

Phase2 关闭时评估结果：
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
- 当前 retrieval / clarification 能力已经可以评估模糊问题的候选质量，但 reranker 仍是轻量规则型实现。后续随着指标体系扩展，需要继续扩大 retrieval eval cases，并评估是否引入更系统的 rerank 策略。

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
- Day57 完成 Eval Result Node Skeleton
- Day58 完成 Phase3 First Milestone Review / Graph Integration Design
- Day59 完成 SQL Runtime Evaluation Graph Integration
- Day60 完成 End-to-End Graph Regression / Phase3 First Milestone Close
- Day61 完成 Beauty BI Dataset V2 Design Baseline
- Day62 完成 Dataset V2 Manifest Skeleton / Schema Foundation
- Day63 完成 Dataset V2 Transaction Facts DDL / Constraint Validation
- Day64 完成 Dataset V2 Fixed Dimensions & Identity Seed
- Day65 完成 Dataset V2 Time-driven Transaction Seed / Atomic Database Write

Day61-Day65 Dataset V2 成果：
- 完成 V1 Coverage Review 与 V2 P0 / P1 / P2 边界；
- 确定 V1 `public` 与 V2 `beauty_bi_v2` schema 隔离；
- 完成 Version Model、Candidate Schema Map、Generation Contract 和 Acceptance Gates 设计；
- 建立 V2 Manifest，固定业务窗口、观察尾窗、活动日历、随机种子和生成合同；
- 完成 16 张 P0 Schema 表及数据库约束验证；
- 完成 10 张固定维度与身份基础表的确定性 Seed；
- 完成 3412 条营销费用、40000 张订单、66889 条订单明细、5925 条退款、16535 条评价和 6564 条会员等级历史；
- 完成订单、履约、退款、评价和会员等级的事件时间顺序；
- 完成独立随机流、稳定业务键、原子写库和数据库逐行比较；
- V2 当前仍为 `draft`，尚未执行 P01–P09 正式 Acceptance、Metadata V2、Golden Cases V2 或 Graph 接入。

当前稳定依赖基线：当前稳定依赖基线：
- Python `3.10.3`
- `langchain==0.3.30`
- `langchain-core==0.3.86`
- `langchain-openai==0.3.35`
- `langchain-community==0.3.31`
- `langgraph==0.6.11`
- `ragas==0.4.3`
- `sentence-transformers==5.5.1`
- 完整锁文件：`requirements-lock.txt`

Phase3 后续重点：
- Dataset V2 P01–P09 Acceptance Calibration 与正式 Gate
- Governed Analytics / Permission / Audit
- Tool Calling / Tool Contract
- Workflow、Single Agent 与 Multi-Agent 架构决策
- Minimal Reflection Experiment 与 Phase3 端到端关闭

当前原则：
- 不推翻 Phase2 主链路
- 复用 Phase2 已完成模块
- 让失败、评估和重试通过显式 State 与 Conditional Edge 管理
- 在线 runtime checks 与离线 Evaluation 保持分层
- V1 稳定基线与 V2 开发版本保持隔离
- 不为展示 Multi-Agent 而机械拆分

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

```text
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
```

## 正在进行：Phase3

```text
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
```

## 最终目标

```text
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
```

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

# Latest Stable Baseline

- Stable Day：Day60
- Validation Date：2026-07-14
- Git Commit：`6701323`
- Python Version：3.10.3
- Virtual Environment：`venv_day51_a`
- Dataset Version：`beauty_bi_v1`
- Dependency Lock：`requirements-lock.txt`

说明：
- 当前已验证环境仍为 `venv_day51_a`。
- 项目根目录中的旧 `venv` 尚未作为稳定环境验证。
- 环境命名迁移已记录为后续维护项，不在 Day60 直接覆盖或改名。

---

# 当前版本

Version: v0.36
完成度：Day65 / 100

当前实现：

```text
自然语言问题
→ LangGraph Workflow
→ Intent Parser
→ Hybrid Search / Metric Recognition
→ Clarification / Metric Selection
→ Query Plan Loading
→ Intent Resolution
→ Template SQL / LLM SQL with Intent Context
→ SQL Cleaner
→ SQL Validator
→ PostgreSQL Execution
→ Runtime Evaluation
├─ Passed → Result Formatter → Answer Layer → Finish
├─ Retryable LLM Error → SQL Repair → SQL Cleaner
└─ Non-retryable → SQL Fail
```

当前测试基线：
- `sql_cleaner_tests.py`：6/6 PASS
- `sql_repair_graph_tests.py`：9/9 PASS
- `analyst_graph_tests.py`：9/9 PASS
- `retrieval_evaluator.py --strict`：6/6 PASS
- `evaluator.py`：26/26 PASS
- `answer_judge.py --mode mock`：6/6 PASS
- `answer_judge.py --mode llm`：6/6 PASS
- `ragas_eval.py --include-negative`：6/6 expectation passed
- `pip check`：No broken requirements found

当前阶段：
- Phase2 已完成
- Phase3 第一里程碑已完成
- Phase3 继续进行

下一步：Day66 Acceptance Gates & Calibration
