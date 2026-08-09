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
- Business Insight Layer 尚未实现；Dataset V2 已形成独立的 Governed Candidate Graph，连接 Planning / Compilation / AST / Governed Execution / Final Answer；Day60 V1 Stable Graph 保持不变，V2 自动 SQL Repair Runtime 仍 disabled

---

## Governed Analytics Contract

Phase3 Day67-Day72 已完成 Access Context、Threat Model、Metric / Table / Column Scope、Region / Channel Row Scope、Execution Governance / Agent Budget、Sensitive Data Protection / Audit Finalization，以及 Security Evaluation / Minimum Load Baseline。

当前已实现：
- 建立不可变 `AccessContext`；
- 建立 `scoped_analyst`、`executive_analyst` 和 `governance_auditor` 三个最小角色；
- 固定当前 Dataset / Schema 边界为 `beauty_bi_v2`；
- 固定 Agent 操作模式为只读 `observe_advise`；
- 支持 Metric、Table、Column、Region 和 Channel Scope 的合同表达；
- 支持 identifiers、free text、cost data 和 minimum group size 的敏感数据策略；
- 建立 Prompt Injection、越权表列访问、cross-schema、row-scope bypass、repair bypass、标识符泄漏、自由文本泄漏和超大结果集 Threat Model；
- Alias Search 与 Embedding Search 支持授权指标候选过滤；
- 未授权指标不参与相似度、Top1 / Top2、Confidence、Clarification 或 Trace；
- 显式空 Metric Scope fail-closed，Authorization Failure 为 non-retryable；
- 建立不可变 `AuthorizationDecision`；
- 实现 Metric、Table、Column 和统一 Resource Authorization 原语；
- 使用 `table.column` 规范验证字段权限、字段来源表和显式禁止列；
- `access_context_tests.py`：5/5 PASS；
- `metric_scope_tests.py`：7/7 PASS；
- `resource_scope_tests.py`：10/10 PASS；
- 建立不可变 `RowScopePlan`，冻结 Region / Channel Anchor 与间接事实表 Scope Path；
- 空 Region / Channel Scope fail-closed，不代表全量权限；
- 建立 `ScopeTarget`、可信 SQL Alias、参数化 `ScopedPredicate` 与 `ScopedQueryContract`；
- 建立 Plan / Contract Fingerprint，保护权限意图及其 SQL 落点；
- `row_scope_tests.py`：13/13 PASS；
- `row_scope_binding_tests.py`：13/13 PASS；
- 建立不可变 `GovernedExecutionPolicy` 与结构化 `GovernedExecutionResult`；
- 建立独立 `beauty_bi_query` PostgreSQL 查询 Role，固定非 Superuser、不可建库、不可建 Role、默认事务只读和连接上限；
- 建立独立 Governed Engine，支持 `pool_size`、`max_overflow`、`pool_timeout` 与 `pool_recycle`；
- 建立参数化 Governed SQL Runner，支持 read-only transaction、transaction-local `statement_timeout`、`search_path` 和 `fetchmany(max_rows + 1)`；
- 超大结果 fail-closed，不返回静默截断的部分结果；
- 真实 PostgreSQL 已验证 V2 SELECT、参数绑定、statement timeout、max rows、写权限拒绝、Public V1 隔离和连接池状态清理；
- 建立 Step / Retry / Prompt Token / Completion Token / Total Token Budget 合同与 Policy Fingerprint；
- `execution_governance_tests.py`：12/12 PASS；
- `execution_governance_integration_tests.py`：9/9 PASS；
- `execution_budget_tests.py`：16/16 PASS；
- 建立 Dataset V2 Sensitive Field Catalog 与可信 `ResultFieldBinding`；
- 建立 HMAC-SHA256 + Secret + Namespace 的确定性标识符令牌化；
- 建立 Direct Identifier、Free Text、Cost Data 与 Minimum Group Size 策略；
- 建立 Exact Result Shape，额外或缺失字段 fail-closed；
- 建立不复制原始问题、SQL、参数和结果行的 Structured Audit Event；
- 建立 HMAC Actor Reference；Day72 将 Question / Generated SQL / Executed SQL / Repair Fingerprint 升级为 keyed HMAC-SHA256 + Audit Secret + Domain Separation；
- 建立 Governance Runtime Secret Contract；
- 建立 append-only Hash-chain JSONL Audit Sink、并发锁、完整性验证与 fsync；
- 建立 Governed Finalization，Audit Persistence 成功前不释放结果；
- `sensitive_data_tests.py`：21/21 PASS；
- `audit_event_tests.py`：当前 26/26 PASS（Day71 历史基线为 20/20，Day72 增加 HMAC confidentiality hardening tests）；
- `audit_sink_tests.py`：16/16 PASS；
- `governed_finalization_tests.py`：14/14 PASS。

当前治理结构：

```text
Trusted Access Context
├─ allowed_metrics
│  ↓
│  Alias / Embedding Candidate Filter
├─ allowed_tables / allowed_columns / denied_columns
│  ↓
│  AuthorizationDecision
└─ allowed_region_codes / allowed_channel_codes
   ↓
   RowScopePlan
   ↓
   ScopeTarget + Parameterized Predicate Contract

GovernedExecutionPolicy
+
SQL + Parameters
↓
Dedicated Query Role / Governed Engine
↓
Read-only Transaction
↓
Statement Timeout / Max Rows / Bounded Fetch
↓
GovernedExecutionResult

ExecutionBudgetPolicy
↓
Step / Retry / Token Usage Budget

GovernedExecutionResult
+
Trusted ResultProtectionContract
↓
HMAC Tokenization / Sensitive Policy / Minimum Group Size
↓
Protected Rows / Blocked Result
↓
Structured Audit Event
↓
Hash-chain JSONL Audit Sink
↓
Governed Finalization
```

Day77 进一步建立执行前治理链：

```text
Semantic Decision
↓
Result Grain Resolution
↓
Query Plan Selection
↓
Time Window Resolution / Binding
↓
Metric / Resource Authorization
↓
Row Scope Binding
↓
Governed Planning Envelope
↓
Deterministic Parameterized SQL Compilation
↓
SQLGlot PostgreSQL AST Enforcement
```

Day78 进一步连接真实执行与结果释放边界：

```text
AST-Enforced Compiled SQL Contract
↓
Governed Query Execution Service
↓
Dedicated Read-only PostgreSQL Role
↓
GovernedExecutionResult（内部原始执行事实）
↓
Result Protection / Minimum Group Size
↓
Structured Audit Event / Hash-chain Audit Sink
↓
GovernedFinalizationResult（唯一允许跨服务边界的结果）
```

Day79 进一步连接 V2 Service-level AI-chain 与 Final Answer：

```text
Natural Language Question
↓
Semantic Decision
↓
Analytics Planning
↓
Result Grain / Query Plan
↓
Time / Scope Binding
↓
Governed Planning Envelope
↓
Deterministic SQL Compilation
↓
PostgreSQL AST Enforcement
↓
Governed PostgreSQL Execution
↓
Result Protection / Audit Finalization
↓
Final Answer V2
```


Day80 进一步建立 Dataset V2 Candidate Governed Graph：

```text
Natural Language Question
↓
Analytics Planning
↓
Query Plan Loading
↓
Time Resolution
↓
Governed Planning Envelope
↓
Deterministic SQL Compilation
↓
Graph-visible PostgreSQL AST Gate
↓
Governed Query Execution
↓
Result Protection / Audit Finalization
↓
Final Answer V2
```

Day80 同时补齐 Runtime Governance：

```text
Server-trusted AccessContext
+
ExecutionBudgetPolicy / ExecutionBudgetState
↓
V2 Candidate Graph
↓
Step Budget fail-closed
↓
Final SQL Scope Predicate AST Preservation
↓
Governed Execution Boundary
```

Repair 安全边界：

```text
Raw Repair Output
↓
RepairedSqlCandidateV2（untrusted）
↓
绑定原 Governed Envelope
↓
绑定原 Compiled Contract
↓
Parameter / Output / Stage / Resource Contract
↓
Row Scope Predicate Preservation
↓
PostgreSQL AST Enforcement
```

当前 V2 自动 SQL Repair Runtime 仍保持 disabled；Day80 关闭的是 Repair Bypass 治理缺口，不是重新启用自动修复。

Day80 验证：
- Governed Analyst Graph V2 Step 1：4/4 PASS；
- Compiled SQL Runtime Scope Predicate V2：5/5 PASS；
- Compiled SQL AST Enforcement V2 Acceptance：9/9 PASS；
- Repaired SQL Candidate Governance V2：7/7 PASS；
- Governed Analyst Graph V2 Budget / Security：4/4 PASS；
- Governed Analyst Graph V2 Step 1 Regression：4/4 PASS；
- Day80 Security Evaluation：21/21 Controlled PASS / 0 Unexpected FAIL / 0 Known Gap / 0 Skipped；
- SEC-002 Graph-level Prompt Injection Enforcement：CLOSED；
- SEC-008 Final SQL Region / Channel Predicate Validation：CLOSED；
- SEC-011 Repaired SQL Actual Predicate Preservation：CLOSED（governance boundary；automatic Repair Runtime disabled）。

当前验证：
- Governed Planning Envelope：9/9 PASS；
- Query Plan Compiler V2：8/8 PASS；
- Compiled SQL AST Enforcement V2：9/9 PASS；
- Catalog-wide：49 Plans，其中 45 个 Plan `READY_FOR_COMPILATION → COMPILED → AST ENFORCED`，4 个 Plan按 Scope Contract fail-closed；
- Governed Query Execution V2 Service Acceptance：6/6 PASS；
- Governed Query Execution V2 PostgreSQL Integration：4/4 PASS；
- Day78 Closing Regression：42/42 PASS；
- Final Answer V2：5/5 PASS；
- Question Semantic Parser V2：43/43 PASS；
- Governed Analytics Service V2：4/4 PASS；
- Governed Analytics PostgreSQL End-to-End Integration：4/4 PASS；
- Day79 已观察专项 / 集成测试合计：56/56 PASS。

当前边界：
- Day60 V1 Stable Graph 保持不变，仍使用原 V1 Query Plan / SQL Runtime；Day80 没有原地替换 Stable Graph；
- Dataset V2 已建立独立 Candidate Governed Graph，并接入 `AccessContext`、Planning Envelope、Compiler、Graph-visible AST Gate、Governed Runner、Step Budget、Finalization 与 Final Answer V2；
- Role 到 Metric / Table / Column Policy 的动态解析尚未实现，当前 Graph 消费 server-trusted `AccessContext`；
- V2 Final SQL 已执行 AST 级 Table / Column / Output / Parameter / Scope Predicate Enforcement；
- `RepairedSqlCandidateV2` 已建立治理边界，Repair Candidate 必须复用原 Envelope / Compiled Contract 并重新通过 Scope / AST Enforcement；
- V2 自动 SQL Repair Runtime 仍 disabled；现有 Governed Execution Failure 继续遵守 non-retryable 合同；
- Step Budget 已进入 V2 Candidate Graph State；真实 LLM Token Usage Capture 尚未接入；
- Langfuse 尚未接入安全 Audit 摘要；
- `PLANNED_MULTIPLE` 已能正确区分于 `MULTIPLE_INTENTS`，但当前 V2 不执行多 Query Plan orchestration；
- Final Answer Scope Disclosure 来自实际 Bound `ScopedQueryContract`，不从问题文本重新猜测；
- 用户自然语言 Region / Channel Value Filter 尚未形成正式 Requested Scope Contract（`SCOPE-GAP-001`）；
- Scope Canonical Value Validation 尚未实现；
- `PERF-GAP-001` 保持开放，完整 Performance Baseline 留待 Day81；
- Dataset V2 仍为 `draft`；Candidate / New Stable Baseline Decision 留待 Day81。

---

## Dataset V2 Semantic Contract

Phase3 Day73 完成 Metadata V2 与 Query Plans V2，Dataset V2 从“数据已验收”推进到“业务语义与可信查询合同已冻结”。

当前静态语义合同：

```text
Metadata V2
→ 19 Metrics

Query Plans V2
→ 49 Static Plans
→ 41 QueryLogic
→ 8 StagedQueryLogic
→ 3 Global History Plans

Canonical Catalog Builder
→ Deterministic YAML
→ Semantic Equality Gate
→ Canonical Byte Equality Gate
```

Query Plan V2 当前可显式声明：
- `required_tables` / `required_columns`；
- trusted physical aliases 与 `ScopeTarget`；
- `ResultFieldBinding` 与敏感结果分类；
- Exact Result Shape 与 Minimum Group Size；
- Staged Query Logic 与 `StageJoin`；
- Cross-fact shared time window；
- Global History first-event identity；
- pre-sequence / post-sequence Scope placement。

复杂指标当前覆盖：
- Refund Rate：退款事件先按 `order_item` 聚合，避免 GMV 分母 fan-out；
- ROI：Sales 与 Marketing Spend 分别聚合后再组合；
- CAC：`customer × channel` 完整历史首次支付 + 同窗营销费用；
- Brand Paid New Customer：`customer` 品牌历史首次支付；
- Channel Paid New Customer：`customer × channel` 渠道历史首次支付；
- Repeat / Multi-order：保持跨日复购与两单客户语义分离；
- Member GMV Share：使用 payment-time membership snapshot。

当前边界：
- 49 个 Plan 的 Resource Contract 已建立；当前 45 个 Plan 可完成治理规划、确定性编译与 AST Enforcement，4 个 Plan 因 Scope Contract 不满足保持 fail-closed；
- ROI / CAC 因 `fact_marketing_spend` 无 Region Anchor 保持 fail-closed；
- Brand / Channel New Customer / CAC 的 post-sequence Scope 当前仅形成结构合同，尚未接入在线 Runtime；
- Dataset V2 仍为 `draft`，Graph integration 继续关闭。

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
| access_context_tests.py | 5/5 PASS |
| metric_scope_tests.py | 7/7 PASS |
| resource_scope_tests.py | 10/10 PASS |
| row_scope_tests.py | 13/13 PASS |
| row_scope_binding_tests.py | 13/13 PASS |
| execution_governance_tests.py | 12/12 PASS |
| execution_governance_integration_tests.py | 9/9 PASS |
| execution_budget_tests.py | 16/16 PASS |
| sensitive_data_tests.py | 21/21 PASS |
| audit_event_tests.py | 26/26 PASS |
| audit_sink_tests.py | 16/16 PASS |
| governed_finalization_tests.py | 14/14 PASS |
| governed_query_execution_acceptance_v2.py | 6/6 PASS |
| governed_query_execution_integration_v2.py | 4/4 PASS |
| query_plan_v2_catalog_builder_tests.py | 17/17 PASS |
| query_plan_v2_tests.py | 22/22 PASS |
| deepseek_client_tests.py | 3/3 PASS |
| question_semantic_parser_v2_tests.py | 43/43 PASS |
| final_answer_v2_tests.py | 5/5 PASS |
| governed_analytics_service_v2_tests.py | 4/4 PASS |
| governed_analytics_postgresql_integration_v2.py | 4/4 PASS |
| question_semantic_parser_regression_v2_tests.py | 7/7 PASS |
| candidate_decision_v2_tests.py | 18/18 PASS |
| candidate_decision_v2_catalog_tests.py | 7/7 PASS |
| candidate_decision_ranking_v2_tests.py | 6/6 PASS |
| candidate_decision_narrowing_v2_tests.py | 3/3 PASS |
| candidate_decision_narrowing_average_v2_tests.py | 3/3 PASS |
| candidate_decision_pipeline_v2_tests.py | 5/5 PASS |
| candidate_decision_parser_pipeline_v2_tests.py | 6/6 PASS |
| semantic_decision_service_v2_tests.py | 6/6 PASS |
| semantic_decision_acceptance_v2.py | 8/8 PASS |
| llm_transport_migration_tests.py | 2/2 PASS |

### Day74 Dataset V2 Generalization Evidence

| Evidence | 结果 | 定位 |
|---|---:|---|
| Visible Golden Baseline | 30/30 | Development / Regression |
| Initial Locked Holdout | 1/19 | Initial Rule Baseline，已观察 |
| Semantic Adversarial | 6/14 | Initial Adversarial Baseline，已观察 |
| Question Signature Fresh Adversarial First Run | 4/60 | Regex Parser Fresh Baseline |
| Structured Semantic Parser Regression | 56/60 Core Exact | Observed Regression，不是 Fresh |
| Structured Semantic Parser Full Exact | 28/60 | Qualifier Contract 尚待收束 |
| Multi-intent Guard | 59/60 | Observed Regression |

当前结论：
- Visible Regression PASS 不代表 Generalization PASS；
- Embedding 用作 Candidate Recall，不作为 Final Metric Selector；
- Structured Semantic Parser 显著改善自然语言结构理解；
- Initial Locked Holdout 和 60-case Signature Adversarial 均已被观察，后续只作为 Regression Evidence；
- Final Fresh Generalization Gate 必须在 Structured Parser / Candidate Decision 冻结后使用新的未见数据。

### Day75 Semantic Decision Finalization Evidence

| Evidence | 结果 | 定位 |
|---|---:|---|
| Structured Parser Static Contract | 41/41 | Finalized Parser Contract |
| Structured Parser Observed Regression Core Exact | 60/60 | Regression，不是 Fresh |
| Structured Parser Observed Regression Full Exact | 59/60 | QSADV-053 为 intentional multi-intent collision |
| Structured Parser Acceptance | 60/60 | Observed Regression Acceptance |
| Candidate / Semantic Decision Regression | 62/62 | Structural / Narrowing / Ranking / Pipeline / Service |
| Final Semantic Decision Acceptance | 8/8 | 集成验收，不是 End-to-End SQL Answer Gate |

当前结论：
- Candidate Decision 已冻结为 `MATCHED / NEEDS_CLARIFICATION / UNSUPPORTED` 三态；
- Authorization 必须在结构候选判断前过滤，未授权指标不得进入候选池；
- Clarification Narrowing 只在有可靠 family-level evidence 时缩小候选，不能凭空增加 Metric；
- Embedding 只排序 `NEEDS_CLARIFICATION` 的已有候选，不能修改最终状态或越权注入候选；
- Day75 证明的是 Semantic Decision Readiness，不等于 V2 End-to-End Answer Correctness；
- Final Fresh Generalization、Query Plan / SQL / Governance / Database Result / Final Answer 的完整 V2 证据链仍待后续 Gate。

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

Day61-Day80 已完成 Dataset V2 从设计、Schema、确定性 Seed、P01-P09 正式业务规律验收、Metadata V2 / Query Plans V2 静态语义合同，到 Semantic Decision、Result Grain / Query Plan Planning、执行前治理、确定性 SQL 编译、PostgreSQL AST Enforcement、服务级 Governed Execution / Result Protection / Audit Finalization、Natural Language → Governed PostgreSQL → Final Answer V2，以及独立 Dataset V2 Candidate Governed Graph。Dataset 当前仍保持 `draft`；Day60 V1 Stable Graph 未被替换，Candidate / New Stable Baseline Decision 留待 Day81。

当前已完成：
- 建立独立目录 `app/db/beauty_bi_v2/`；
- 建立并升级 `dataset_manifest.yaml`，集中管理版本、日期窗口、随机种子、生成合同和 small Profile Acceptance Contract；
- 建立 `manifest_loader.py`，集中校验固定维度、身份关系、交易生成合同和 Day66 Acceptance Contract；
- 建立 16 张 Beauty BI V2 P0 Schema 表；
- 完成固定维度、身份关系、营销、订单、订单明细、退款、评价和 R12 会员等级历史的确定性 Seed；
- 建立 `acceptance_observer.py`，同时保留 observation 模式和 formal acceptance 模式；
- 完成 P01-P09 逐项观察、统计口径校准和正式阈值冻结；
- 完成 Manifest Loader 校验与 P01-P09 Formal Acceptance；
- 建立独立 `metadata/beauty_bi_v2/`；
- 冻结 Metadata V2 的 19 个业务指标；
- 建立 Query Plan V2 结构合同，覆盖 Resource、Scope、Result、Staged、Cross-fact 与 Global History 语义；
- 建立 49-plan Canonical Static Catalog：41 QueryLogic / 8 StagedQueryLogic / 3 Global History Plans；
- 建立唯一 Canonical Writer、Semantic Equality Gate 与 Canonical Byte Equality Gate；
- 完成 Golden Cases V2 Visible Baseline，并建立 Development / Regression / Locked Holdout / Adversarial 评估分层；
- 完成 Initial Locked Holdout 与 Semantic Adversarial Baseline；
- 建立 V2 独立 Semantic Retrieval，确认 BGE 适合作为 Candidate Recall，而非 Final Metric Selector；
- 建立 19 Metric Semantic Signatures 与 Question Semantic Signature Contract；
- 完成 Fresh Regex Signature Baseline，并据此重构为 Structured Semantic Parser + Deterministic Evidence + Contract Validator；
- 建立最小 Shared DeepSeek LLM Transport，并迁移 SQL Generator / Repairer；
- Day75 收束 Question Signature Qualifier Contract，并冻结 Structured Parser；同一已观察 60-case Regression 达到 60/60 Core Exact、59/60 Full Exact、60/60 Acceptance，Multi-intent 60/60；
- 建立 Structural Compatibility、`MATCHED / NEEDS_CLARIFICATION / UNSUPPORTED` Candidate Decision、授权前置过滤、Clarification Narrowing 与 Embedding Ranking Boundary；
- 建立统一 Candidate Decision Pipeline 与 Semantic Decision Service，Candidate / Semantic Decision 回归合计 62/62 PASS，Final Acceptance 8/8 PASS；
- Final Fresh 首次运行已完成并暴露 1 条真实 Parser Gap；修复后的 16/16 仅作为 Observed Regression，不重新声明 Fresh PASS；
- 已建立 Result Grain Resolver、Query Plan Selector、Analytics Planning Service、Time Window Resolution / Binding、Query Plan Scope Binding、Governed Planning Envelope、Deterministic Query Plan Compiler 与 Compiled SQL AST Enforcement；
- 49 个 Plan 中 45 个达到 `READY_FOR_COMPILATION → COMPILED → AST ENFORCED`，4 个因 Scope Contract 不满足保持 fail-closed；
- Governed PostgreSQL Execution、Result Protection / Audit Finalization 已完成服务级真实数据库集成；Day79 已完成 Final Answer V2 与真实 PostgreSQL AI-chain End-to-End Regression；Day80 已完成 Dataset V2 Candidate Graph Runtime Governance Integration，并关闭 SEC-002 / SEC-008 / SEC-011；完整 Performance Baseline 与 Candidate Decision 仍待 Day81；
- Day78 真实 `gmv_overall_v2`（2025 全年 + 有效 Region / Channel Scope）执行约 18.96 秒，未满足生产默认 5 秒 Execution SLO，登记为 `PERF-GAP-001`；
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

Day66 正式验证结果：

| 验证项 | 结果 |
|---|---:|
| Day66 Manifest validation | PASS |
| P01 Customer Purchase Long Tail | PASS |
| P02 Membership R12 Transition | PASS |
| P03 Identity / Channel Binding Overlap | PASS |
| P04 New Customer Scope Difference | PASS |
| P05 Product Sales Long Tail | PASS |
| P06 Season and Region Demand | PASS |
| P07 Marketing Diminishing Returns | PASS |
| P08 Promotion and Margin Trade-off | PASS |
| P09 Refund, Review and Quality Relation | PASS |
| Business Pattern Acceptance | 9/9 PASS |
| Database writes during acceptance | 0 |

Day73 Semantic Contract 验证：

| 验证项 | 结果 |
|---|---:|
| Metadata V2 | 19 Metrics |
| Query Plans V2 | 48 Plans |
| QueryLogic / StagedQueryLogic | 40 / 8 |
| Global History Plans | 3 |
| Catalog Builder Tests | 17/17 PASS |
| Static Runtime Tests | 22/22 PASS |
| Dataset Status | draft |
| Graph Integration | disabled |

Day75 Semantic Decision 验证：

| 验证项 | 结果 |
|---|---:|
| Structured Parser Static Contract | 41/41 PASS |
| Structured Parser Regression Contract | 7/7 PASS |
| Observed 60-case Core Exact | 60/60 |
| Observed 60-case Full Exact | 59/60 |
| Observed 60-case Acceptance | 60/60 |
| Candidate / Semantic Decision Regression | 62/62 PASS |
| Final Semantic Decision Acceptance | 8/8 PASS |
| Final Fresh Generalization | pending |
| Graph Integration | disabled |

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
P01-P09 Observation & Calibration：completed
Acceptance Contract：frozen（small Profile）
P01-P09 Formal Business Pattern Acceptance：passed（9/9）
Candidate Readiness Gates：in_progress
Metadata V2：completed（19 metrics）
Query Plans V2：completed（49 plans；41 QueryLogic / 8 StagedQueryLogic）
Golden Cases V2：completed
Generalization Evaluation：first fresh run completed / not clean PASS；修复后的 replay 已被观察，仅作为 Regression Evidence，不声明 Final Fresh PASS
Semantic Retrieval V2：completed
Metric Semantic Signature：completed
Question Semantic Signature：completed
Structured Semantic Parser：frozen / observed regression validated
Candidate Decision：implemented / frozen
Semantic Decision Service：implemented / final acceptance passed
Governed Planning / SQL Compilation / AST Enforcement：completed（45 enforced / 4 fail-closed）
Governed Execution / Result Protection / Audit Finalization：completed（Day78 Closing Gate 1/4 PASS）
V2 AI-chain / Final Answer Regression：completed（Day79 Closing Gate 2/4 PASS）
Graph Runtime Governance Integration：completed（Day80 Closing Gate 3/4 PASS）
Final SQL Scope Predicate Enforcement：completed（SEC-008 CLOSED）
Repaired SQL Candidate Governance：completed（SEC-011 CLOSED；automatic Repair Runtime disabled）
Graph-level Prompt Injection / AccessContext Isolation：completed（SEC-002 CLOSED）
Execution Budget → V2 Graph State：completed（Step Budget）
Security Evaluation：21/21 Controlled PASS / 0 Known Gap
Performance Baseline：in_progress（`PERF-GAP-001` 已观察；完整 EXPLAIN ANALYZE / DB Size / End-to-End Baseline 待 Day81）
Graph integration：V2 Candidate Graph implemented / Stable promotion pending
```

Beauty BI V1 继续作为 Latest Stable Baseline。Day80 已完成 V2 Candidate Graph Runtime Governance Integration，并关闭 Day72 的 3 条 Runtime Governance Known Gap；但 Performance Baseline、V1/V2 Full Regression 与 Dataset Candidate / New Stable Baseline Decision 尚未完成，因此 Dataset V2 仍不能标记为 Candidate 或 Stable。

# 技术栈

## Backend

- Python 3.10.3
- FastAPI（规划中）

## Database

- PostgreSQL
- pgvector
- SQLAlchemy 2.0
- SQLGlot 30.13.0（PostgreSQL AST Enforcement）

## AI

- DeepSeek API（模型名通过 `DEEPSEEK_MODEL` 配置，当前验证为 `deepseek-v4-pro`）
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
├── governance/
│   ├── access_context.py
│   ├── authorization.py
│   ├── row_scope.py
│   ├── row_scope_binding.py
│   ├── execution_policy.py
│   ├── execution_budget.py
│   ├── sensitive_data.py
│   ├── audit_event.py
│   ├── governance_runtime.py
│   ├── audit_sink.py
│   ├── governed_finalization.py
│   └── governed_query_execution_v2.py
├── db/
│   ├── governed_database.py
│   ├── governed_sql_runner.py
│   ├── provision_query_role.py
│   └── beauty_bi_v2/
│       ├── __init__.py
│       ├── dataset_manifest.yaml
│       ├── schema.sql
│       ├── init_schema.py
│       ├── db_check.py
│       ├── manifest_loader.py
│       ├── seed_dimensions.py
│       ├── seed_transactions.py
│       └── acceptance_observer.py
├── llm/
│   └── deepseek_client.py
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

说明：Phase3 原计划时间盒为 Day51-75；由于 Candidate Readiness Closing Gate 尚未完成，当前按 Gate 顺延，Day75 不作为强制阶段结束点。Phase3 正式关闭后，本节将压缩为 Phase3 Milestone Summary。

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
- Day66 完成 Dataset V2 P01-P09 Acceptance Gates & Calibration
- Day67 完成 Governed Analytics Access Context / Threat Model / Contract Tests
- Day68 完成 Metric Candidate Filtering / AuthorizationDecision / Table & Column Scope Tests
- Day69 完成 Region / Channel Row Scope Planning / Scope Target Binding / Parameterized Predicate Contract
- Day70 完成 Dedicated Query Role / Governed SQL Runner / Execution Budget
- Day71 完成 Sensitive Data Protection / Structured Audit Event / Hash-chain Audit Sink / Governed Finalization
- Day72 完成 21-case Security Evaluation / Audit Event v2 HMAC Hardening / 10、25、50 并发 Minimum Load Test
- Day73 完成 Metadata V2 / 48-plan Query Plans V2 / Staged & Global History Contracts / Canonical Catalog Regression
- Day74 完成 Golden Cases V2 / Initial Generalization Baseline / Semantic Signature / Structured Semantic Parser Architecture
- Day75 完成 Structured Parser Finalization / Candidate Decision / Clarification Narrowing / Semantic Decision Service / Final Acceptance
- Day76 完成 Candidate Readiness Architecture Review / Result Grain & Query Plan Planning Boundary
- Day77 完成 Final Fresh First Run Review / 49-plan Canonical Catalog / Governed Planning Envelope / Deterministic SQL Compiler / PostgreSQL AST Enforcement
- Day78 完成 AST-Enforced Compiled SQL → Governed Runner → Result Protection / Audit Finalization 服务闭环与真实 PostgreSQL 集成
- Day79 完成 V2 Service-level AI-chain / Final Answer V2 / Multi-intent vs Multi-grain Boundary Fix / Real PostgreSQL End-to-End Regression，Closing Gate 2/4 PASS

Day61-Day66 Dataset V2 成果：
- 完成 V1 Coverage Review 与 V2 P0 / P1 / P2 边界；
- 确定 V1 `public` 与 V2 `beauty_bi_v2` schema 隔离；
- 完成 Version Model、Candidate Schema Map、Generation Contract 和 Acceptance Gates 设计；
- 建立 V2 Manifest，固定业务窗口、观察尾窗、活动日历、随机种子、生成合同和 small Profile Acceptance Contract；
- 完成 16 张 P0 Schema 表及数据库约束验证；
- 完成固定维度、身份关系和交易事实的确定性 Seed；
- 完成 3412 条营销费用、40000 张订单、66889 条订单明细、5925 条退款、16535 条评价和 6564 条会员等级历史；
- 完成订单、履约、退款、评价和会员等级的事件时间顺序；
- 完成独立随机流、稳定业务键、原子写库和数据库逐行比较；
- 完成 P01-P09 observation、口径校准、阈值冻结和 formal acceptance；
- `manifest_loader.py` Day66 校验通过；
- `acceptance_observer.py` 正式验收 9/9 PASS，验收过程数据库写入为 0；
- V2 当前仍为 `draft`；Metadata V2、Query Plans V2、Golden Cases V2、Semantic Decision Layer、执行前治理、服务级 Governed Execution / Finalization、Final Answer Regression 与 Candidate Graph Runtime Governance 已完成；完整 Performance Baseline、Full Regression 与 Candidate / Stable Decision 尚未完成。

当前稳定依赖基线：
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
- 继续完成 Dataset V2 Candidate Readiness：Day81 Performance Baseline → Permission / Security / Repair Full Regression → V1/V2 Full Regression → Candidate / New Stable Baseline Decision → Phase3 Closing
- Phase4 Evidence-based Business Insight Engine 仅在 Phase3 Candidate Readiness Gate 关闭后开始

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

Version: v0.51
完成度：Day80 / 100

当前 Stable Graph：

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

Day67-Day72 Governed Analytics 能力：

```text
allowed_metric_names
↓
Alias / Embedding Candidate Filtering
↓
Confidence / Rerank / Clarification

AccessContext
+
required metric / tables / columns
↓
AuthorizationDecision

AccessContext
+
trusted source tables / scope dimensions
↓
RowScopePlan
+
ScopeTarget / SQL Alias
↓
Parameterized ScopedQueryContract

GovernedExecutionPolicy
+
SQL / Parameters
↓
Dedicated Query Role
↓
Read-only / Timeout / Max Rows
↓
GovernedExecutionResult

ExecutionBudgetPolicy
↓
Step / Retry / Token Budget
```

Day72 进一步建立：

```text
Adversarial Security Cases
↓
18 Controlled PASS / 0 Unexpected Fail
↓
3 Known Gap → Day75

Audit Event v2
↓
Keyed HMAC-SHA256 Text Fingerprints
↓
Domain Separation / Safe Validation Error

Governed SQL Runtime
↓
10 / 25 / 50 Concurrent Requests
↓
p50 / p95 / Error Rate / Peak Connections
```

Day73 进一步建立：

```text
Metadata V2
→ 19 Metrics
→ Independent beauty_bi_v2 Metadata Version

Query Plan V2
→ 48 Static Plans
→ 40 QueryLogic
→ 8 StagedQueryLogic
→ 3 Global History Plans

Canonical Catalog Builder
→ Deterministic YAML
→ Semantic Equality Gate
→ Canonical Byte Equality Gate

Governance-aware Query Contract
→ Resource Authorization
→ Scope Target / Trusted Alias
→ Result Field Binding
→ Minimum Group Size
→ Cross-fact / Global History fail-closed semantics
```

Day74 进一步建立：

```text
Golden Cases V2
↓
Visible Baseline 30/30
↓
Initial Locked Holdout / Semantic Adversarial Baseline

V2 Semantic Retrieval
↓
Authorized Candidate Recall Evidence

Metric Semantic Signature
+
Question Semantic Signature
↓
Structured Semantic Parser
↓
Observed Regression Core Exact 56/60
```

Day75 进一步建立：

```text
Question
↓
Structured Semantic Parser
↓
Parser Guard
↓
Authorization-filtered Structural Compatibility
↓
Candidate Decision
├─ MATCHED
├─ NEEDS_CLARIFICATION
└─ UNSUPPORTED
↓
Clarification Narrowing
↓
Embedding Ranking（仅排序 clarification candidates）
↓
Semantic Decision Result
```

Day75 验证：
- Structured Parser Static Contract：41/41 PASS
- Observed 60-case Regression：60/60 Core Exact / 59/60 Full Exact / 60/60 Acceptance
- Candidate / Semantic Decision Regression：62/62 PASS
- Final Semantic Decision Acceptance：8/8 PASS

Day76-Day77 进一步建立：

```text
Semantic Decision
→ Result Grain
→ Query Plan Selection
→ Time / Scope Binding
→ Governed Planning Envelope
→ Deterministic SQL Compiler
→ PostgreSQL AST Enforcement
```

Day77 验证：
- Query Plan Catalog：49 Plans / 19 Metrics / 41 QueryLogic / 8 StagedQueryLogic / 3 Global History Plans；
- Governed Planning Envelope：9/9 PASS；
- Query Plan Compiler V2：8/8 PASS；
- Compiled SQL AST Enforcement V2：9/9 PASS；
- Catalog-wide：45 个 Plan 完成 Planning / Compilation / AST Enforcement，4 个 Plan按 Scope Contract fail-closed；
- Final Fresh 首次运行中的真实 Parser Gap 已通过通用机制修复；修复后的 replay 属于 Observed Regression，不重新声明 Fresh PASS。

Day78 进一步建立：

```text
Compiled SQL Contract
→ Internal AST Enforcement
→ Governed SQL Runner
→ Result Protection
→ Audit Persistence
→ Governed Finalization Result
```

Day78 验证：
- Compiled SQL AST Enforcement：9/9 PASS；
- Governed Finalization：14/14 PASS；
- Governed Query Execution V2 Service Acceptance：6/6 PASS；
- Execution Governance PostgreSQL Integration：9/9 PASS；
- Governed Query Execution V2 PostgreSQL Integration：4/4 PASS；
- Closing Regression：42/42 PASS。

Day78 已知边界：
- 集成验收使用显式 30 秒执行预算，仅用于证明真实治理链闭环；生产默认 5 秒策略未修改；
- `gmv_overall_v2` 在 2025 全年 + 当前有效 Scope 下实测约 18.96 秒，登记为 `PERF-GAP-001`；
- 空数据窗口当前通过 `minimum_group_size_violation` fail-closed，Answer Layer 尚未区分“无数据”和“低于最小样本阈值”；
- Integration Fixture 必须使用 V2 Canonical Scope Codes（如 `JD` / `TMALL` 与城市级 Region Codes），AST 结构夹具中的虚拟 Scope 值不能用于真实数据库验收。

Day79 进一步建立：

```text
Natural Language Question
→ Semantic Decision
→ Analytics Planning
→ Query Plan
→ Time / Scope Binding
→ Governed Planning Envelope
→ Deterministic SQL Compilation
→ PostgreSQL AST Enforcement
→ Governed PostgreSQL Execution
→ Result Protection / Audit Finalization
→ Final Answer V2
```

Day79 验证：
- Final Answer V2：5/5 PASS；
- Question Semantic Parser V2：43/43 PASS；
- Governed Analytics Service V2：4/4 PASS；
- Governed Analytics PostgreSQL End-to-End Integration：4/4 PASS；
- Day79 已观察专项 / 集成测试合计：56/56 PASS。

Day79 当前边界：
- `PLANNED_MULTIPLE` 已可正确区分于 `MULTIPLE_INTENTS`，但服务级 V2 暂不执行多 Query Plan orchestration；
- Final Answer 的 Scope Disclosure 来自实际 Bound `ScopedQueryContract`；
- 用户问题中的 Region / Channel Value Filter 尚未形成正式 Requested Scope Contract（`SCOPE-GAP-001`）；
- Day79 尚未完成 Dataset V2 Graph Runtime Governance；该项已在 Day80 Closing Gate 3/4 关闭；
- `PERF-GAP-001` 保持开放，完整 Performance Baseline 留待 Day81。


Day80 进一步建立：

```text
Dataset V2 Candidate Graph
→ Analytics Planning
→ Governed Planning
→ Deterministic Compilation
→ Graph-visible AST Gate
→ Governed Query Execution
→ Final Answer V2

ExecutionBudgetPolicy / ExecutionBudgetState
→ Graph Step Budget

Repaired SQL
→ RepairedSqlCandidateV2
→ Original Envelope / Compiled Contract Linkage
→ Scope Predicate Preservation
→ PostgreSQL AST Enforcement
```

Day80 验证：
- Governed Analyst Graph V2 Step 1：4/4 PASS；
- Compiled SQL Runtime Scope Predicate V2：5/5 PASS；
- Compiled SQL AST Enforcement V2 Acceptance：9/9 PASS；
- Repaired SQL Candidate Governance V2：7/7 PASS；
- Governed Analyst Graph V2 Budget / Security：4/4 PASS；
- Governed Analyst Graph V2 Step 1 Regression：4/4 PASS；
- Security Evaluation：21/21 Controlled PASS，0 Unexpected FAIL，0 Known Gap，0 Skipped。

Day80 当前边界：
- Day60 V1 Stable Graph 未修改；
- Dataset V2 Candidate Graph 已完成，但尚未提升为 Stable；
- SEC-002 / SEC-008 / SEC-011 已关闭；
- 自动 V2 SQL Repair Runtime 仍 disabled，Repair Candidate Governance 已准备完成；
- Step Budget 已进入 V2 Graph State；LLM Token Usage Capture 仍未接入；
- `PERF-GAP-001`、`SCOPE-GAP-001`、Scope Canonical Value Validation 与 Multi-plan Orchestration 保持开放；
- Day81 负责 Performance / Full Regression / Candidate Decision / Phase3 Closing。

当前边界：
- Structured Parser 与 Candidate / Semantic Decision Layer 已冻结，但 60-case 结果仍是已观察 Regression，不是 Final Fresh Generalization；
- Final Fresh 首次运行已完成，但不是 clean PASS；修复后的 replay 已被观察，只保留为 Regression Evidence；
- Semantic Decision → Result Grain → Query Plan → Time / Scope → Compiled SQL → AST Enforcement → Governed PostgreSQL Execution → Result Protection / Audit Finalization → Final Answer V2 已形成独立服务级证据链；Day80 又建立了独立 Dataset V2 Candidate Governed Graph 端到端治理证据；
- `PERF-GAP-001` 已观察，但完整 Performance Baseline 尚未关闭；Graph Runtime Enforcement 与 Repair Candidate Governance 已在 Day80 完成；
- Dataset V2 仍为 `draft`；
- Stable Graph 仍未接入 Dataset V2。

当前 AI 主链路稳定测试基线：
- `sql_cleaner_tests.py`：6/6 PASS
- `sql_repair_graph_tests.py`：9/9 PASS
- `analyst_graph_tests.py`：9/9 PASS
- `retrieval_evaluator.py --strict`：6/6 PASS
- `evaluator.py`：26/26 PASS
- `answer_judge.py --mode mock`：6/6 PASS
- `answer_judge.py --mode llm`：6/6 PASS
- `ragas_eval.py --include-negative`：6/6 expectation passed
- `pip check`：No broken requirements found

Dataset V2 Day73 Semantic Contract 验证：
- `query_plan_v2_catalog_builder_tests.py`：17/17 PASS
- `query_plan_v2_tests.py`：22/22 PASS
- Static Query Plan Catalog：48 Plans / 19 Metrics
- QueryLogic / StagedQueryLogic：40 / 8
- Global History Plans：3
- Dataset Status：draft
- Graph Integration：V2 Candidate Graph implemented / Stable promotion pending

Dataset V2 Day74 Generalization / Semantic Decision Evidence：
- Visible Golden Baseline：30/30
- Initial Locked Holdout：1/19 = 5.26%（已观察，仅保留 Initial Rule Baseline）
- Semantic Adversarial：6/14 = 42.86%（已观察）
- Regex Fresh Signature Baseline：4/60 = 6.67%
- Structured Semantic Parser Regression：56/60 Core Exact = 93.33%
- Full Exact：28/60 = 46.67%
- Multi-intent Guard：59/60
- `deepseek_client_tests.py`：3/3 PASS
- `question_semantic_parser_v2_tests.py`：9/9 PASS
- `question_semantic_parser_regression_v2_tests.py`：3/3 PASS
- `llm_transport_migration_tests.py`：2/2 PASS
- Closing Governance Regression：Audit Sink 16/16 + Governed Finalization 14/14 PASS
- Candidate Decision：not started
- Final Fresh Generalization：pending
- Dataset Status：draft
- Graph Integration：disabled

Dataset V2 Day75 Semantic Decision Evidence：
- Question Signature Qualifier Contract：normalized / frozen
- Structured Parser Static Contract：41/41 PASS
- Structured Parser Regression Contract：7/7 PASS
- Observed 60-case Core Exact：60/60
- Observed 60-case Full Exact：59/60
- Observed 60-case Acceptance：60/60
- Candidate / Semantic Decision Regression：62/62 PASS
- Final Semantic Decision Acceptance：8/8 PASS
- Candidate Decision：implemented / frozen
- Final Fresh Generalization：pending
- Performance Baseline：not started
- V2 AI-chain Regression：not started
- Graph Integration：disabled

Dataset V2 Day66 验证：
- `manifest_loader.py`：Day66 Manifest validation PASS
- `acceptance_observer.py`：P01-P09 Formal Acceptance 9/9 PASS
- Business Pattern Acceptance：PASS
- Database writes：0
- Dataset Status：draft
- Dataset Candidate：NO

Governed Analytics Day67-Day72 当前验证：
- `access_context_tests.py`：5/5 PASS
- `metric_scope_tests.py`：7/7 PASS
- `resource_scope_tests.py`：10/10 PASS
- `row_scope_tests.py`：13/13 PASS
- `row_scope_binding_tests.py`：13/13 PASS
- `execution_governance_tests.py`：12/12 PASS
- `execution_governance_integration_tests.py`：9/9 PASS
- `execution_budget_tests.py`：16/16 PASS
- `sensitive_data_tests.py`：21/21 PASS
- `audit_event_tests.py`：26/26 PASS
- `audit_sink_tests.py`：16/16 PASS
- `governed_finalization_tests.py`：14/14 PASS
- `retrieval_evaluator.py --strict`：6/6 PASS
- Core Governance + Retrieval：168/168 PASS
- `analyst_graph_tests.py`：9/9 PASS
- `sql_repair_graph_tests.py`：9/9 PASS
- Stable Graph Regression：18/18 PASS
- Security Evaluation：21 cases / 21 Controlled PASS / 0 Unexpected FAIL / 0 Known Gap
- Minimum Load Test：255/255 requests succeeded / 0% error rate
- 50 concurrency：p50 100.53 ms / p95 141.34 ms / max 147.30 ms / peak connections 10
- `pip check`：No broken requirements found

Day72 历史安全边界及 Day80 关闭结果：
- SEC-002 Graph-level Prompt Injection Enforcement：Day72 Known Gap → Day80 CLOSED
- SEC-008 Final SQL Region Predicate Validation：Day72 Known Gap → Day80 CLOSED
- SEC-011 Repaired SQL Actual Predicate Preservation：Day72 Known Gap → Day80 CLOSED（governance boundary；automatic Repair Runtime disabled）
- Audit Text Fingerprint Confidentiality：已通过 `audit_event_v2` HMAC hardening 关闭
- Day60 V1 Stable Graph 仍保持原实现；Day80 新增的是独立 Dataset V2 Candidate Governed Graph
- Dataset V2 仍为 `draft`，Stable promotion 留待 Day81

当前阶段：
- Phase2 已完成
- Phase3 第一里程碑已完成
- Dataset V2 P01-P09 Acceptance 已完成
- Day67 Access Context & Threat Model 已完成
- Day68 Metric / Table / Column Scope 独立治理原语已完成
- Day69 Region / Channel Row Scope 独立治理合同已完成
- Day70 Execution Governance 与 Agent Budget 独立治理原语已完成
- Day71 Sensitive Data Protection、Audit Event、Audit Sink 与 Governed Finalization 独立治理原语已完成
- Day72 Security Evaluation、Audit HMAC Hardening 与 Minimum Load Baseline 已完成
- Day73 Metadata V2 与初始 48-plan Query Plans V2 Static Catalog 已完成
- Day74 Golden Cases V2、Initial Generalization Evidence、Semantic Signature 与 Structured Semantic Parser Architecture 已完成
- Day75 Structured Parser Finalization、Candidate / Semantic Decision Layer 与 Final Acceptance 已完成
- Day76 Result Grain / Query Plan Planning Boundary 与架构复核已完成
- Day77 49-plan Canonical Catalog、Governed Planning Envelope、Deterministic SQL Compiler 与 PostgreSQL AST Enforcement 已完成
- Day78 Governed Execution / Result Protection / Audit Finalization 已完成，Closing Gate 1/4 PASS
- Day79 V2 AI-chain / Final Answer Regression 已完成，Closing Gate 2/4 PASS
- Day80 Dataset V2 Candidate Graph Runtime Governance Integration 已完成，Closing Gate 3/4 PASS
- Phase3 继续进行，Candidate Readiness Closing Gate 尚未关闭

下一步：Day81 Closing Gate 4/4 — Performance Baseline → Permission / Security / Repair Full Regression → V1/V2 Full Regression → Dataset Candidate / New Stable Baseline Decision → Phase3 Closing
