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

当前项目采用“双轨”架构，避免在 Candidate 尚未完成稳定晋级前原地替换已验证主链路。

### Day60 Latest Stable

```text
Natural Language Question
↓
V1 LangGraph Workflow
↓
Intent / Metric Recognition
↓
Query Plan Routing
↓
Template SQL / LLM SQL
↓
SQL Cleaner / Validator
↓
PostgreSQL
↓
Runtime Evaluation
├─ Passed → Result Formatter → Answer
├─ Retryable LLM Execution Error → Controlled SQL Repair
└─ Non-retryable → Fail
```

### Day81 Dataset V2 Candidate

```text
Natural Language Question
↓
Structured Semantic Decision
↓
Analytics Planning
↓
Query Plan / Time / Scope Binding
↓
Governed Planning Envelope
↓
Deterministic SQL Compilation
↓
PostgreSQL AST Enforcement
↓
Governed Read-only PostgreSQL Execution
↓
Result Protection
↓
Structured Audit / Hash-chain Persistence
↓
Governed Finalization
↓
Final Answer V2
```

V2 Candidate Graph 进一步将 Planning、Compilation、AST Gate、Execution Budget、Governed Execution 和 Final Answer 暴露为显式 LangGraph 节点。Repair SQL 仍只作为 untrusted candidate，必须继承原权限合同并重新经过 Scope / AST Enforcement；V2 自动 SQL Repair Runtime 当前保持 disabled。

当前发布边界：
- Latest Stable 仍为 Day60 / `beauty_bi_v1` / commit `6701323`；
- Day81 将 `beauty_bi_v2` 提升为 Candidate，而不是 New Stable；
- Phase4 在 Candidate 基线上继续建设 Evidence-based Business Insight Engine。

### Day82 Phase4 Contract Foundation

Day82 在 Dataset V2 Candidate 之上完成 Phase4 第一层合同基础：

```text
Time Comparison Contract
+
Insight Contract
+
Tool Contract
+
Business Decision Evaluation Contract
```

关键边界：
- Phase3 `FinalAnswerV2` 保持 deterministic factual answer，不被经营诊断逻辑改写；
- `TimeWindowResolverV2` 保持单时间窗口职责，Comparison 作为独立 Contract；
- Model 未来可以选择受控 Tool，但不能传 raw SQL 或重新定义 `metric_formula`；
- Fact / Anomaly / Contribution / Candidate Explanation / Unknown / Recommended Check 被结构化分离；
- Business Decision Evaluation 不使用简单平均掩盖事实错误或 epistemic 越界。


### Day83 Deterministic Anomaly Detection

Day83 在 Day82 Contract Foundation 之上完成确定性异常判断与 Insight 证据集成：

```text
TimeComparisonContractV2
↓
Active AnomalyPolicyV2
↓
Minimum Sample / Exposure Gate
↓
Deterministic Anomaly Detector
↓
AnomalyDecisionV2
↓
Anomaly Insight Adapter
↓
InsightContractV2.detected_anomalies
```

当前已实现：
- 同时保留 absolute change 与 relative change；
- sample gate 使用 `sample_metric_name + current/reference_sample_value`，不把样本语义写死为订单数；
- 明确区分 `ANOMALY / NORMAL / INSUFFICIENT_SAMPLE / NOT_COMPARABLE / POLICY_NOT_FOUND`；
- Policy 必须绑定 Metric、Comparison Type、Direction、Threshold、Sample Basis 与 Policy Version；
- 建立 `AnomalyPolicyCandidateV2 → ACTIVE → AnomalyPolicyV2` 生命周期；
- `TBD_CALIBRATION` Candidate 不能进入 Detector；
- 只有完整 ACTIVE Policy 才能确定性执行；
- `AnomalyDecisionV2` 通过 Adapter 转换为 evidence-backed anomaly statement，不直接改写 Day82 `InsightContractV2`。

Day83 Acceptance：

```text
Anomaly Detection V2：11/11 PASS
Anomaly Policy Candidate V2：8/8 PASS
Anomaly Insight Adapter V2：8/8 PASS
```

当前业务边界：
- 首批 8 个 Tier A Policy Candidate 覆盖 GMV、Gross Margin Rate、Refund Rate、Order Count 的 YoY / Campaign YoY / Baseline Deviation 候选组合；
- 8 个 Candidate 当前全部为 `TBD_CALIBRATION`；
- 当前没有把 Dataset Acceptance 区间、测试 fixture 或 LLM 判断冒充生产 anomaly threshold；
- Statistical threshold 用于产生 calibration candidate，正式阈值仍需 Business / Human Calibration 后才能升级为 ACTIVE；
- LLM 可以在后续 Investigation 中解释异常和选择调查方向，但不作为核心 anomaly truth source；
- Day83 不做 Contribution Analysis，也不声称 anomaly 原因或因果关系。

### Day84 Deterministic Contribution Analysis

Day84 在 Day83 anomaly evidence 之后完成第一版确定性 Contribution Analysis，并接入 `InsightContractV2.dimension_contributions`：

```text
Governed Current / Reference Evidence
↓
ContributionAnalysisV2
↓
member alignment
↓
member delta / contribution rate
↓
positive / negative contribution ranking
↓
reconciliation / unexplained remainder
↓
Contribution Insight Adapter
↓
InsightContractV2.dimension_contributions
```

当前第一版正式支持范围：

```text
Metric：GMV
Dimension：Channel
Comparison：绑定 TimeComparisonContractV2
Decomposition：ADDITIVE
```

关键边界：
- `contribution ≠ causality`，Contribution 只描述“变化由哪些维度成员贡献”，不自动升级为原因判断；
- `contribution_rate = member_delta / overall_delta`，允许大于 100% 或小于 0%，因为正负成员可能互相抵消；
- current / reference channel member 显式对齐，确认 ABSENT 才可按 0 处理；
- overall 与 dimension decomposition 必须共享同一 Effective Scope；
- `minimum_group_size` 属于 Result Protection，不等于 anomaly minimum sample；受保护结果不可被 Contribution 绕过；
- `GMV × channel` 使用与 `gmv_overall_v2` 一致的 GMV 计算语义，仅改变 result grain，适合作为首个 additive decomposition；
- ratio / derived metric、non-additive metric × dimension、cross-fact metric 不套用通用 additive contribution 公式，当前保持 fail-closed / unsupported；
- reconciliation 不闭合时，unexplained remainder 进入 `unknowns`，不由 LLM 补造原因；
- Contribution Result 绑定 `TimeComparisonContractV2` provenance，Adapter 会阻止 comparison mismatch；
- Day84 不接入 Agentic Planner / Investigation Loop，不提前进入 Day85 / Day86。

Day84 Acceptance：

```text
Contribution Analysis V2：16/16 PASS
Contribution Insight Adapter V2：11/11 PASS
```

Day84 的计划范围原本包含更多维度；实际 Closing 冻结为“先完成可证明安全的 `GMV × channel` 首版闭环”。其他维度 / Ratio / Cross-fact / First-event 的 Contribution Generalization 保持显式能力边界，不冒充已完成支持。


### Day85 Bounded Agentic Investigation Planner

Day85 在 Day82 Tool Contract、Day83 Anomaly Evidence 与 Day84 Contribution Evidence 之上完成第一版受控调查 Planner：

```text
Protected Insight / Evidence
+
Investigation State
+
Authorization-filtered Available Actions
↓
LLM Planner Proposal
↓
Deterministic Planner Validation
↓
PlannerDecisionV2
```

当前能力：
- `InvestigationStateV2` 结构化保存当前 Evidence、已完成动作、可选动作与上游 clarification requirement；
- Model 只允许提出 `SELECT_TOOL(action_id)` 或 `CLARIFY`，不能提交 raw SQL、metric formula、permission 或自行改写 Tool 参数；
- `available_actions` 必须先由系统在既有 Tool / Authorization / Scope Boundary 内形成，Planner 只在合法候选中选择；
- 已完成动作不能再次进入当前可选动作，避免 Planner 无意义重复调查；
- `SELECT_TOOL` 必须引用当前 Insight 中真实存在的 supporting evidence；
- 上游存在未解决语义前提时必须进入 clarification；没有未解决前提时，Model 不能凭空制造 clarification；
- Planner Proposal 即使结构合法，也必须经过 deterministic validator；模型拥有建议权，不拥有最终执行权；
- Executor 的真实执行权限 / Scope Enforcement 仍不能省略：Planner 校验“这个动作能不能选”，Executor 校验“这次实际请求能不能执行”；
- LLM Adapter 使用最小 Planner Context + 严格 Pydantic JSON parsing；非法 action、非法 evidence、额外字段、非 JSON / Markdown fenced JSON 均 fail-closed；
- Day85 不实现自动 retry / recovery / re-plan / stop loop，这些属于 Day86；
- 机器合同字段与 action / evidence ID 保持英文稳定标识符；面向人的 `rationale / clarification_prompt` 强制简体中文，避免中文 BI 项目在解释层退化成英文体验。

Day85 Acceptance：

```text
Investigation Planner V2：15/15 PASS
Investigation Planner LLM V2：16/16 PASS
```

Day85 Live DeepSeek Observed Probe：

```text
Model：deepseek-v4-pro
Observed Contract：PASS
Selected Action：drill_product_within_skincare
Observed Decision Quality：PASS
```

该 Live Probe 只记录真实模型 observed evidence，不等同 deterministic regression，也不声称模型长期稳定 100% 做出同样选择。

当前边界：
- Day85 只完成“基于 Evidence / State 在合法 Action Set 中选择下一步”的 Bounded Planner；
- 尚未把 Planner 接成完整 `Plan → Execute → Observe → Re-plan → Stop` 循环；
- tool failure recovery、alternative path、max depth、investigation budget、stopping condition 与 insufficient-evidence stop 留到 Day86；
- Planner 不重新定义 Metric、Query Plan、SQL、Authorization 或可信业务事实。

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


### Day81 Phase3 Closing Evidence

Day81 完成 Closing Gate 4/4：

- 完成 Dataset V2 Performance Baseline 与 PostgreSQL `EXPLAIN ANALYZE`；
- 定位 `PERF-GAP-001` 根因：Bulk Seed 后缺少 Planner Statistics；
- 对 V2 全部 16 张表执行 `ANALYZE` 后，代表性查询由约 19–20 秒下降到约 22–65 ms；
- Production 默认 `statement_timeout=5000ms`、`max_rows=200` 未放宽，4/4 代表性 SQL 与 deterministic V2 E2E 均通过；
- Permission / Security / Repair Closing Regression：58/58 PASS；
- Day60 V1 Stable Graph Regression：18/18 PASS；
- V2 deterministic / acceptance regression 除 live LLM observed semantic case 外全部通过；
- 60-case live Structured Parser observed regression：60/60 Core Exact、58/60 Full Exact、59/60 Acceptance、60/60 Multi-intent；
- 新登记 `SEM-REL-GAP-001`：live Structured Semantic Parser 存在 repeatability risk，不通过反复重跑掩盖；
- Candidate Decision Integration Probe 正确覆盖 `MATCHED / NEEDS_CLARIFICATION / UNSUPPORTED`；
- `beauty_bi_v2`：`draft → candidate`；
- Latest Stable 不变：Day60 / `beauty_bi_v1` / `6701323`；
- Phase3：CLOSED，Phase4 最早 Day82 开始。

性能修复不是通过新增索引或放宽 timeout 完成，而是通过补齐 PostgreSQL Planner Statistics，使 Planner 能基于真实数据规模重新选择执行计划。Dataset V2 后续 rebuild / bulk seed 必须把 `ANALYZE` 作为 Query Readiness 生命周期步骤。

### Day82 Phase4 Contract Acceptance

```text
Time Comparison Contract V2 Acceptance：6/6 PASS
Insight + Tool Contract V2 Acceptance：12/12 PASS
Business Decision Evaluation Contract V2 Acceptance：7/7 PASS
```

Day82 只建立 Contract Foundation；Day83 已完成 Anomaly Detection，Day84 已完成第一版 Contribution Analysis；Agentic Planner / Loop 与 Automated Judge 仍待后续。

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
| time_comparison_contract_acceptance_v2.py | 6/6 PASS |
| investigation_contracts_acceptance_v2.py | 12/12 PASS |
| business_decision_evaluation_contract_acceptance_v2.py | 7/7 PASS |
| anomaly_detection_acceptance_v2.py | 11/11 PASS |
| anomaly_policy_candidates_acceptance_v2.py | 8/8 PASS |
| anomaly_insight_adapter_acceptance_v2.py | 8/8 PASS |
| contribution_analysis_acceptance_v2.py | 16/16 PASS |
| contribution_insight_adapter_acceptance_v2.py | 11/11 PASS |
| investigation_planner_acceptance_v2.py | 15/15 PASS |
| investigation_planner_llm_acceptance_v2.py | 16/16 PASS |

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

Day61-Day81 已完成 Dataset V2 从数据基础、业务语义、可信查询合同、Generalization Evidence、Governed Execution、Final Answer、Candidate Graph 到 Performance / Full Regression / Candidate Decision 的 Phase3 Candidate Readiness 闭环。

当前状态：

```text
Design：completed
Status：candidate
Schema：16 tables
P01-P09 Business Pattern Acceptance：9/9 PASS
Metadata V2：19 metrics
Query Plans V2：49 plans
QueryLogic / StagedQueryLogic：41 / 8
Global History Plans：3
Planning / Compilation / AST Enforcement：45 enforced / 4 scope fail-closed
Governed Execution / Finalization：completed
V2 AI-chain / Final Answer：completed
Candidate Governed Graph：implemented
Security Evaluation：21/21 Controlled PASS
Performance Gate：PASS
Phase3 Closing Gate：4/4 PASS
Stable Promotion：deferred
```

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

Day81 Performance Evidence：

```text
Before ANALYZE
GMV Overall / Channel GMV / Refund Rate
≈ 19–20s

After ANALYZE
GMV Overall runner median        ≈ 32 ms
GMV Channel runner median        ≈ 43 ms
Refund Rate runner median        ≈ 56 ms
Multi-order runner median        ≈ 23 ms
Deterministic V2 E2E             ≈ 0.8s

Production Policy
statement_timeout = 5000 ms
max_rows = 200
Representative SQL = 4/4 PASS
Deterministic E2E = PASS
```

当前 Candidate 边界：
- Latest Stable 仍为 Day60 `beauty_bi_v1`，V2 尚未替换 Stable Graph；
- 49 个 Query Plan 中 45 个可完成 Planning / Compilation / AST Enforcement，4 个继续按 Scope Contract fail-closed；
- `SCOPE-GAP-001`：用户自然语言 Region / Channel Value Filter 尚未形成正式 Requested Scope Contract；
- Scope Canonical Value Validation 尚未实现；
- Post-sequence Scope Runtime 与 Multi-plan Execution Orchestration 尚未实现；
- V2 自动 SQL Repair Runtime 仍 disabled；
- LLM Token Usage Capture 与 Langfuse Safe Audit Mapping 尚未完成；
- `SEM-REL-GAP-001`：live Structured Semantic Parser repeatability 仍是显式可靠性债；
- Dataset rebuild / bulk seed 后必须执行 `ANALYZE`，再进入 Query / Performance Readiness。

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

Agent Workflow / Governed Analytics

状态：✅ 已完成（Day81 Closed）

### Phase3 Milestone Summary

Phase3 将 Phase2 的可演示 Text-to-SQL 原型升级为“稳定 V1 + 受治理 V2 Candidate”的双轨体系。

阶段关键成果：
- Day51 稳定 LangChain / LangGraph / Ragas 依赖组合，并冻结 `requirements-lock.txt`；
- 将 SQL cleaning、validation、execution、runtime evaluation 与一次受控 repair 接入 V1 LangGraph；
- 建立 Beauty BI Dataset V2：16 张表、确定性 Seed、P01-P09 Business Pattern Acceptance；
- 建立独立 Metadata V2：19 Metrics 与 49 Query Plans；
- 建立 Structured Semantic Parser、Candidate Decision、Clarification Narrowing 与 Embedding Ranking Boundary；
- 建立 Result Grain / Query Plan / Time / Scope Planning Boundary；
- 建立 Governed Planning Envelope、Deterministic SQL Compiler 与 SQLGlot PostgreSQL AST Enforcement；
- 建立专用只读 PostgreSQL Query Role、Execution Policy / Budget、Result Protection、Structured Audit、Hash-chain Audit Sink 与 Governed Finalization；
- 建立 Natural Language → Governed PostgreSQL → Final Answer V2 服务级证据链；
- 建立独立 Dataset V2 Candidate Governed Graph；
- 关闭 SEC-002 / SEC-008 / SEC-011，Security Evaluation 达到 21/21 Controlled PASS；
- Day81 通过 `ANALYZE` 修复 Bulk Seed 后缺失 Planner Statistics 导致的约 19–20 秒查询退化，并在 Production 5 秒 Policy 下完成性能验收；
- 完成 Permission / Security / Repair Regression、V1 Stable Regression 与 V2 Closing Regression；
- 完成 Dataset Candidate / New Stable Baseline Decision。

Phase3 Closing Decision：

```text
Phase3：CLOSED
Closing Gate：4/4 PASS

beauty_bi_v2：
draft → candidate

Latest Stable：
Day60 / beauty_bi_v1 / 6701323

Stable Promotion：
deferred
```

为什么不直接提升为 Stable：
- live Structured Semantic Parser 暴露 `SEM-REL-GAP-001` repeatability risk；
- 仍存在 Requested Scope、Scope Canonicalization、Post-sequence Scope Runtime、Multi-plan Execution 等显式能力边界；
- Candidate 允许已知、可记录且 fail-safe 的限制；Stable Promotion 保持更高门槛。

Phase3 最终定位：一个运行在 Beauty BI Dataset V2 上、具备可解释语义决策、确定性 SQL 合同、权限与 Scope Enforcement、受控执行、结果保护、审计、Final Answer 和 Candidate Graph 的 Governed Analytics Agent。

## Phase 4

Evidence-based Business Insight Engine + Public Delivery

状态：🚧 进行中（Day85 Bounded Agentic Investigation Planner 已完成）

当前 Day82-Day94 目标：
- ✅ Day82：Insight Contract / Tool Contract / Time Comparison / Business Decision Evaluation Contract；
- ✅ Day83：Deterministic Anomaly Detection / Policy Candidate / Insight Evidence Integration；
- ✅ Day84：Deterministic Contribution Analysis / GMV × Channel / Insight Evidence Integration；
- ✅ Day85：Bounded Agentic Investigation Planner / Structured LLM Proposal / Deterministic Validation；
- Day86：Agentic Investigation Loop；
- Day87：Evidence Pack；
- Insight Golden Cases / Evaluation；
- Streamlit Decision Console MVP；
- Docker Compose / One-command Startup；
- Observability / Unified Regression / CI / Delivery Performance；
- Cloud Deployment、Blind Test 与 Public Delivery。

Phase4 不以继续扩建 Text-to-SQL 为主，而是把已受治理的数据查询能力升级为“证据化经营异动诊断”。

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

## 当前已完成：Phase3

```text
Question
↓
Structured Semantic Decision
↓
Analytics Planning
↓
Query Plan / Time / Scope Binding
↓
Governed Planning Envelope
↓
Deterministic SQL Compilation
↓
PostgreSQL AST Enforcement
↓
Governed Read-only Execution
↓
Result Protection / Audit Finalization
↓
Final Answer V2
```

Phase3 最终产出不是替换 Day60 Stable，而是形成独立 `beauty_bi_v2` Candidate，并保留清晰的 Stable / Candidate 发布边界。

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

Version: v0.56
完成度：Day85 / 100
Phase3：CLOSED
Phase4：IN_PROGRESS（Day85 completed）

Latest Stable Baseline：

```text
Stable Day：Day60
Dataset：beauty_bi_v1
Commit：6701323
Python：3.10.3
Virtual Environment：venv_day51_a
```

Dataset V2 Candidate：

```text
Dataset：beauty_bi_v2
Candidate Day：Day81
Query Plans：49
Planning / Compilation / AST：45 enforced / 4 fail-closed
Security：21/21 Controlled PASS
Closing Gate：4/4 PASS
Stable Promotion：deferred
```

Day81 Performance：

```text
Root Cause：
Bulk Seed 后缺少 PostgreSQL Planner Statistics

Remediation：
ANALYZE beauty_bi_v2

Before：
代表性核心查询约 19–20s

After：
代表性 DB 查询约 22–65ms
Deterministic V2 E2E ≈ 0.8s

Production Policy：
statement_timeout=5000ms
max_rows=200
4/4 representative SQL PASS
```

Day81 Closing Regression：

```text
Permission / Security / Repair：58/58 PASS
V1 Stable Graph：18/18 PASS
V2 deterministic / acceptance suites：除 live observed semantic case 外通过
Observed Semantic Parser：
- Core Exact 60/60
- Full Exact 58/60
- Acceptance 59/60
- Multi-intent 60/60
```

Day82 Phase4 Contract Foundation：

```text
Time Comparison：6/6 PASS
Insight + Tool：12/12 PASS
Business Decision Evaluation：7/7 PASS
```

Day83 Deterministic Anomaly Detection：

```text
Anomaly Detection：11/11 PASS
Policy Candidate：8/8 PASS
Insight Adapter：8/8 PASS
Production Active Policy：0（8 个 Tier A Candidate 均为 TBD_CALIBRATION）
```

Day84 Deterministic Contribution Analysis：

```text
Contribution Analysis：16/16 PASS
Contribution Insight Adapter：11/11 PASS
Initial Supported Pair：GMV × Channel
Contribution Result：TimeComparisonContractV2-bound
Contribution ≠ Causality
```

Day85 Bounded Agentic Investigation Planner：

```text
Deterministic Planner Acceptance：15/15 PASS
LLM Planner Acceptance：16/16 PASS
Live DeepSeek Observed Contract：PASS
Live Observed Decision Quality：PASS
User-facing Planner Rationale：简体中文
Day86 Loop / Recovery / Stop：尚未实现
```

当前已知限制：
- `SEM-REL-GAP-001`：live Structured Semantic Parser repeatability；
- `SCOPE-GAP-001`：Requested Region / Channel Value Filter 尚未正式结构化；
- Scope Canonical Value Validation；
- 4 个 Query Plan 继续按 Scope Contract fail-closed；
- Post-sequence Scope Runtime；
- Multi-plan Execution Orchestration；
- V2 automatic SQL Repair Runtime disabled；
- real LLM token usage capture / Langfuse safe audit mapping pending。

下一步：Day86 进入 Agentic Investigation Loop，把 Day85 的 next-step decision 接入受控 Execute / Observe / Re-plan / Recovery / Stop，并继续受既有 Tool / Semantic / Governance Boundary 约束。
