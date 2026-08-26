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


### Day86 Bounded Agentic Investigation Loop

Day86 将 Day85 的“下一步选择”接成第一版完整受控调查循环：

```text
Planner Decision
↓
Trusted Tool Binding
↓
Governed Executor
↓
Protected Observation / Evidence
↓
State Update
↓
RETRY / REPLAN / RECOVER / STOP
↓
Next Planner Decision
```

当前能力：
- 建立 `InvestigationLoopStateV2`，保存 Planner State、Observation History、当前轮调查步数与 Budget Policy；
- Tool 执行结果结构化为 `EVIDENCE / NO_DATA / FAILURE`；
- `NO_DATA` 表示当前 Scope / Time Window 下执行成功但没有数据，不等于 0，也不等于执行失败；
- `RETRY` 仅在真实 Executor 明确返回 `retryable=True` 且 Retry Budget 仍有额度时允许；
- `REPLAN` 在成功 Observation / 新 Evidence 改变 State 后重新选择调查方向；
- `RECOVER` 在当前路径 non-retryable failure 结束但仍有合法替代路径时进入；
- `STOP` 显式区分 evidence sufficient、investigation budget exhausted、no legal action、retry budget exhausted、non-retryable failure；
- Observation / Evidence 必须先写回 State，再允许 Planner 进行下一次决策；
- 已结束动作进入 `completed_action_ids`，不继续出现在当前 `available_actions`；Retry 中的动作保持未完成；
- Planner 再规划仍只能从刷新后的 `available_actions` 中选择，不能修改系统预绑定 Tool Contract / 参数；
- 新增系统侧 `TrustedToolExecutionBindingV2`，Planner 不接触 raw SQL、Envelope、Compiled Contract 或权限对象；
- Investigation Tool 真实复用 Phase3 `execute_governed_query_v2()`，经过 AST Enforcement、read-only PostgreSQL、Result Protection、Audit 与 Governed Finalization；
- 只有 Finalization 已允许释放的 protected rows 才能进入 Investigation Evidence；
- 建立 Round Budget + Session Budget：本轮 Budget 用完不等于调查完成；只有用户明确要求继续且 Session 总预算仍有额度时才能开启下一 Round；
- continuation 保留 Evidence、Observation History、completed actions 与剩余合法动作，只重置新一轮 step count；
- 系统不能在没有用户明确 continuation 请求时自动续轮。

Day86 Acceptance：

```text
Investigation Loop Core：39/39 PASS
Investigation Tool Executor Adapter：9/9 PASS
Real PostgreSQL Tool Integration：1/1 PASS
Real PostgreSQL Two-step End-to-End Loop：1/1 PASS
Real PostgreSQL Failure → Recovery → Alternative Path：1/1 PASS
```

真实 End-to-End 已验证：

```text
异常 Evidence
→ Planner 选择渠道
→ Governed PostgreSQL
→ 渠道 Evidence
→ State Update
→ Re-plan 选择区域
→ Governed PostgreSQL
→ 区域 Evidence
→ Evidence Sufficient
→ STOP
```

真实 Recovery 已验证：

```text
Planner 选择渠道
→ Governed PostgreSQL 被执行治理边界阻断
→ FAILURE / retryable=False
→ State Update
→ RECOVER
→ Planner 改选仍合法的区域路径
→ Governed PostgreSQL 成功
→ Evidence
→ STOP
```

当前边界：
- Day86 已完成单个 Investigation Session 内的 bounded loop，不代表已经实现跨请求持久化；
- `InvestigationSessionStateV2` 当前是结构化状态合同，不自动提供数据库 State Store / TTL / Checkpoint；
- 一个 Conversation 内多 Investigation 的 Registry、暂停 / 恢复与 Follow-up Routing 尚未实现；
- 用户自然语言“继续”到 continuation intent 的完整交互层尚未实现；后续 Decision Console 可利用 `can_continue / uninvestigated_action_ids / stop_reason`；
- Day86 Loop 本身不承担 Evidence Pack；Day87 已在其上增加独立 Evidence Delivery 层，仍不把 Agent 输出升级为因果结论；
- Latest Stable 仍保持 Day60 / `beauty_bi_v1` / `6701323`，Day86 不触发 Stable Promotion。


### Day87 Evidence Pack & Evidence Delivery

Day87 将 Phase4 的分析结论升级为可追溯的 Evidence Delivery：

```text
Business Semantic Metric Definition
+
Governed PostgreSQL / Protected Result / Audit
→ Direct Evidence

Direct Evidence
→ Anomaly / Contribution
→ Derived Evidence + Parent Lineage

Investigation Observation
→ EVIDENCE / NO_DATA / FAILURE Evidence

以上 Evidence
→ EvidencePackV2
→ Claim-type / Epistemic Gate
→ Evidence Sufficiency
→ EvidencePackDeliveryV2
```

当前能力：
- `EvidenceRecordV2` 统一表达直接证据、派生证据与调查 Observation；
- Governed Query Evidence 只接受成功、已 Audit Persistence、已通过 Result Protection 的释放结果；
- Evidence provenance 绑定 Query Plan / Envelope / Compiler / SQL / Time / Scope / Audit fingerprints，而不是复制 raw SQL / raw parameters；
- 真实 PostgreSQL 已验证 protected channel GMV result 可以形成 Confirmed Fact 与 Evidence Pack；
- Anomaly / Contribution 保留 parent evidence lineage，不伪装成直接 SQL 事实；
- `NO_DATA` / `FAILURE` 可以记录调查边界，但不能冒充业务 Confirmed Fact；
- Confirmed Fact / Detected Anomaly / Dimension Contribution 分别受 Evidence Type Gate 约束；
- Candidate Hypothesis 进入 Evidence Pack 时必须有 supporting evidence；完全无证据的方向保持 Unknown + Recommended Check；
- Metric Definition Snapshot 从 Dataset V2 Business Metrics Catalog 构建，LLM 不能自行定义指标公式；
- Evidence Sufficiency 使用 `SUFFICIENT_FOR_CURRENT_SCOPE / PARTIAL / INSUFFICIENT`，不输出没有统计依据的伪精确 numeric confidence；
- Contribution / correlation 继续不能自动升级为 causal attribution。

Day87 Acceptance：

```text
Evidence Pack Contract：14/14 PASS
Governed Evidence Builder：10/10 PASS
Real PostgreSQL Evidence Pack：1/1 PASS
Derived Evidence Lineage：10/10 PASS
Investigation Observation Evidence：10/10 PASS
Evidence Delivery / Sufficiency：10/10 PASS
```

当前边界：
- Evidence Delivery 尚未成为完整生产 Agent / LangGraph 的自动 final output；
- Day88 才建立 Insight Golden / Automated / Business Decision Evaluation；
- Day89 才接入 Decision Console；
- Latest Stable 仍保持 Day60 / `beauty_bi_v1` / `6701323`，Day87 不触发 Stable Promotion。



### Day88 Insight Evaluation / Human Calibration

Day88 在 Day87 `EvidencePackDeliveryV2` 之上建立多层 Business Insight Evaluation：

```text
Insight Golden Case
+
EvidencePackDeliveryV2
↓
Deterministic Automated Evaluation
↓
Business Decision Judge
↓
Human Expert Proxy Review
↓
Judge ↔ Human Calibration
↓
Versioned Business Decision Rubric
```

当前能力：
- Golden Case 显式区分 `REGRESSION / HOLDOUT / FRESH_GENERALIZATION`，已观察 / 用于开发的 Case 不继续冒充 Fresh；
- 建立 8 个 Visible Regression Cases，覆盖 activity review / ROI / margin / refund / CAC / region / membership / promotion；
- Automated Evaluation 确定性检查 Metric、Analysis Mode、Evidence Sufficiency、required / forbidden sections；
- `READY_FOR_BUSINESS_REVIEW` 只代表结构与证据 Gate 通过，不等于最终 Business Decision PASS；
- Business Decision Judge 评估 factual correctness / diagnostic relevance / prioritization / actionability / epistemic discipline / evidence sufficiency；
- Judge 不能自行填写 `overall_status`，不能引用 Evidence Pack 中不存在的 evidence ID；
- deterministic gate 失败时不会调用 LLM Judge；
- Human Expert Proxy 与 Judge 独立评分，逐维保存 agreement / disagreement；
- Rubric 版本化，历史 Evaluation 保留原 `rubric_version`，新标准不覆盖旧结果。

Day88 Acceptance：

```text
Insight Golden Case Contract：12/12 PASS
Visible Regression Golden Cases：12/12 PASS
Automated Insight Evaluator：6/6 PASS
Business Decision Judge + Human Calibration：10/10 PASS
Rubric Versioning + Observed Calibration Evidence：7/7 PASS

Deterministic / Contract Acceptance：
47/47 PASS
```

真实 PostgreSQL + DeepSeek observed evaluation：

```text
Case：INS-OBS-001
Evidence Class：REGRESSION

Fact：
2025年当前授权范围内
GMV 最高渠道 = 天猫旗舰店
GMV = 2,586,549.37

Deterministic Precheck：
READY_FOR_BUSINESS_REVIEW

Live Judge：
6 dimensions PASS
overall = PASS

Human Expert Proxy：
prioritization = PARTIAL
overall = PARTIAL

Calibration：
5 agreement / 1 disagreement
critical disagreement = 0
review required = true
```

该 disagreement 促成 `business_decision_rubric_v2_0`：
“业务规模最大”不能自动等价于“最值得优先调查”；`prioritization = PASS` 需要与用户 business objective 直接相关，并有比较性 Evidence 支撑。

当前边界：
- Day88 公开 Case 均为 Regression，不声称 Fresh Generalization；
- 一次 Live Judge PASS 不证明模型长期 repeatability；
- Human Expert Proxy 不被当作绝对 Ground Truth；
- Day89 才将 Evidence / Evaluation 接入 Streamlit Decision Console；
- Dataset V2 仍保持 Candidate，Latest Stable 仍是 Day60 V1。



### Day89 Decision Console / Runtime HITL / Periodic Business Delivery

Day89 将 Day87 Evidence Delivery、Day84 Contribution、Day86 Investigation Loop 与 Day88 Evaluation Boundary 接入统一 Streamlit Decision Console，形成第一版面向业务交付的产品界面：

```text
Business Question / Report Definition
↓
Governed Evidence / Investigation
↓
Decision Console Delivery Layer
├─ Business Decision View
├─ Analyst Investigation View
└─ Engineering / Audit View
```

当前正式接通两个入口：

```text
Ad-hoc Investigation
→ 自然语言问题
→ Governed Seed Evidence
→ Bounded Agentic Investigation
→ Evidence / Trace / HITL

Periodic Business Report
→ Daily / Weekly / Monthly
→ Deterministic Time Comparison
→ Governed PostgreSQL
→ Evidence / Contribution / Reconciliation
```

当前能力：
- KPI Cards：current / reference / delta / delta%；
- Protected Breakdown：只展示 Result Protection 允许释放的聚合结果；
- Data Verification：Metric Definition / Time Window / Effective Scope / Evidence / Audit reference；
- `GMV × channel` Contribution Ranking 与 Reconciliation；
- Production Active Anomaly Policy 仍为 0，页面明确展示“未评估 / 未激活”，不因数值变化伪造 anomaly；
- Evidence Drawer、Investigation Trace、Evidence Sufficiency 与 Executive Decision Brief Preview；
- 三层 Progressive Disclosure：Business / Analyst / Engineering；
- Runtime HITL Explicit Continue：Round Budget 用完后，只有用户明确继续且 Session Budget 允许，才开启下一轮；
- Runtime HITL Clarification：用户只能从 server-owned Resolution Contract 的合法选项中选择，不能用自由文本绕过 prerequisite；
- UI / Session State 不保存 raw SQL、compiled context、Governed Envelope 或 blocked raw rows。

Periodic Report 当前时间语义：

```text
Daily
→ 当前完整自然日 vs 前一日
→ DOD

Weekly
→ 当前自然周（Monday-Sunday）vs 前一完整自然周
→ WOW

Monthly
→ 当前完整自然月 vs 前一完整自然月
→ MOM
```

Daily 首次真实验证还形成了 `PARTIAL_READY` 交付语义：

```text
Overall Comparison 可安全释放
+
Channel Breakdown 触发 Result Protection
↓
保留可信 KPI / Overall Evidence
不释放被保护 Channel rows
不计算 Contribution
```

Weekly / Monthly 在当前代表性窗口可形成完整 `READY`，包含 Overall Comparison、Channel Breakdown、Contribution 与 Reconciliation。

Day89 Final Delivery Gate：

```text
Final Delivery Gate：95/95 PASS
Real PostgreSQL Final Gate：5/5 PASS
```

真实 PostgreSQL Final Gate 覆盖：
- Explicit Continue；
- Clarification Resume；
- Daily Privacy-aware `PARTIAL_READY`；
- Weekly Full Periodic Delivery；
- Monthly Unified Periodic Delivery。

Day89 继续保持：
- Dataset V2 = Candidate；
- Latest Stable = Day60 / `beauty_bi_v1` / `6701323`；
- Contribution 不升级为因果解释；
- Scheduler / Email Subscription / Report History / Multi-tenant Reporting 不进入当前主线；
- Docker / One-command Startup 留到 Day90；
- Observability / Unified Regression / CI 留到 Day91；
- Cloud Deployment 留到 Day92。

### Day90 Reproducible Docker Runtime / One-command Startup

Day90 将 Day89 Decision Console 与 Governed Runtime 放入可重复启动的 Docker Compose 交付链：

```text
beauty_db
PostgreSQL / pgvector / persistent volume
↓ healthcheck
bootstrap
Probe → state → allowed action → re-Probe → READY
↓ service_completed_successfully
decision_console
Streamlit / Investigation / Periodic Report
```

Startup lifecycle：

```text
Database Start
→ Schema Init
→ deterministic Seed
→ Formal Data Acceptance
→ ANALYZE
→ Governed Query Role Readiness
→ Application Readiness
→ Decision Console Ready
```

当前实现：
- Docker Compose 管理 PostgreSQL、one-shot Bootstrap 与 Streamlit Decision Console；
- `.env.example` 提供 owner / query role / governance secret / DeepSeek / Streamlit 配置模板；
- Bootstrap 根据结构化 readiness state 只执行当前唯一允许的恢复动作，异常 / 漂移状态 fail-closed；
- Dataset rebuild / bulk seed 后自动要求 `ANALYZE`，避免 Planner Statistics 缺失造成 Query Readiness 假阳性；
- PostgreSQL 查询 Runtime 继续使用独立只读 Query Role，不因容器化绕过 Scope / AST / Result Protection / Audit；
- `.dockerignore` 排除真实 `.env`、本地 venv、私有文档与 runtime artifacts；
- Decision Console 容器通过真实页面 / 业务查询验证 application readiness，不只依赖 Web server health endpoint。

Day90 Fresh-volume Reproducibility Gate：

```text
empty isolated volume
→ initialize_schema
→ seed_dataset
→ formal acceptance
→ analyze_dataset
→ provision_query_runtime
→ Bootstrap READY
→ Decision Console healthy
→ real GMV query PASS
```

Day90 Acceptance：

```text
Startup Readiness Contract：11/11 PASS
Startup Readiness Probe：11/11 PASS
Bootstrap Contract：8/8 PASS
Fresh-volume Bootstrap：PASS
Fresh Decision Console：PASS
Fresh Real Business Query：PASS
```

当前部署边界：
- 当前 Docker image 仍使用完整 development dependency snapshot，尚未拆分最小 Production Runtime dependencies；
- Cloud Deployment、Observability / Unified CI、Blind Test 分别留到 Day91-Day93；
- Fresh Gate 证明 infrastructure / data semantics / business result 可复现，不声称 byte-for-byte reproducibility；
- Latest Stable 仍保持 Day60，Dataset V2 继续保持 Candidate。


### Day91 Observability / Unified Regression / Minimal CI / Delivery Performance

Day91 将 Day89-Day90 已能运行的 Decision Console / Investigation Runtime 从“能运行”升级为“可追踪、可统一回归、可在提交时自动守门”的工程链：

```text
Investigation Round
└─ Investigation Step
   ├─ Planner
   │  └─ DeepSeek Generation
   ├─ Tool Execution
   │  └─ Governed Query Execution
   │     └─ SQL Execution
   ├─ Evidence Update
   └─ Loop Control
```

Observability 采用 Safe Allowlist Boundary：
- Langfuse 只接收显式允许的结构化 metadata；
- 默认不上传 raw question / prompt / completion text；
- 不上传 raw SQL / SQL parameters / raw rows / blocked rows；
- 不上传 `AccessContext`、Governed Envelope、Compiled Contract 或 secret；
- Trace Input 保持 `null`，Output 保持 `undefined`；
- `LANGFUSE_OBSERVABILITY_ENABLED=false` 时退化为 no-op，不让 Observability 成为核心 Runtime 的硬依赖行为。

真实 DeepSeek + PostgreSQL Investigation Trace：

```text
investigation_round                 7.44s
└─ investigation_step               6.93s
   ├─ planner                       6.83s
   │  └─ deepseek_chat_completion   6.81s
   ├─ tool_execution                0.09s
   │  └─ governed_query_execution   0.09s
   │     └─ sql_execution            0.06s
   ├─ evidence_update
   └─ loop_control
```

LLM Usage：

```text
Prompt Tokens：1,079
Completion Tokens：286
Total Tokens：1,365
```

该样本显示主要 latency 来自 LLM Generation，而不是 PostgreSQL SQL Execution。当前只将其作为 observed evidence，不外推为 P95 / P99 / SLA。

Failure / Recovery Observability 进一步验证：

```text
drill_channel
→ Governed PostgreSQL / Governance Boundary
→ FAILURE
→ retryable = false
→ RECOVER
→ drill_region
→ Governed PostgreSQL
→ EVIDENCE
→ STOP
→ evidence_sufficient
```

Loop Control 的真实 metadata：

```text
Step 1：
status = failure
retryable = false
directive = recover

Step 2：
status = evidence
directive = stop
stop_reason = evidence_sufficient
```

统一回归入口：

```text
python -m app.evaluation.unified_regression_v2
```

当前 deterministic Unified Regression：

```text
Semantic                               7/7 PASS
Governed Query Execution               6/6 PASS
Governed Finalization                 14/14 PASS
Audit Sink                            16/16 PASS
Investigation Runtime                  5/5 PASS
Investigation Tool Executor            9/9 PASS
Decision Console Runtime               7/7 PASS

Total：
7 modules
64 cases
PASS
```

Minimal CI：
- GitHub Actions；
- Ubuntu runner；
- Python 3.10.20；
- 从 `requirements-lock.txt` 安装；
- `pip check`；
- deterministic Unified Regression；
- live DeepSeek / Langfuse Cloud / PostgreSQL / Docker 不作为基础 CI hard gate；
- `.env` 不存在的 CI-like preflight 本地 PASS；
- GitHub Actions 真实运行 PASS；
- workflow 使用 `actions/checkout@v7` / `actions/setup-python@v7`。

Day91 依赖合同：
- `langfuse==4.14.3` 进入 direct dependency；
- 当前真实 `venv_day51_a` 重新生成 UTF-8 `requirements-lock.txt`；
- `pip check` PASS；
- `.env.example` 增加 Observability / Langfuse 配置占位符；
- Observability 默认关闭。

Day91 Delivery Performance Evidence：

```text
docs/evaluation/day91_delivery_performance_evidence.md
```

当前明确边界：
- Token Usage 已完成真实 capture；
- DeepSeek cost 尚未建立已验证的价格映射，因此不声称已获得可信 cost evidence；
- Token Usage 尚未接入在线 `ExecutionBudgetState`；
- Day90 已构建的 Docker image 早于 Day91 Langfuse dependency 变更，Day92 Cloud Deployment 必须从当前 lock 重新 build / validate；
- 当前性能证据是 observed evidence，不是容量测试或 SLA；
- Latest Stable 仍保持 Day60 / `beauty_bi_v1` / `6701323`；
- Dataset V2 继续保持 Candidate。


### Day92 Cloud Deployment / Public Demo

Day92 将 Decision Console 正式部署到 Render，并完成真实公网业务查询验证：

```text
GitHub main
↓ Auto Deploy
Render Docker Web Service
↓ Internal Network
Render PostgreSQL
↓
beauty_bi_query read-only role
↓
Governed Query / Result Protection / Audit Finalization
↓
Public Decision Console
```

Public Demo：

```text
https://beauty-bi-agent-demo.onrender.com
```

当前云端运行边界：
- Web Service 与 PostgreSQL 均位于 Singapore Region；
- 应用使用 Render Internal Database Host，不使用 External Database URL 作为 Runtime Host；
- 数据库：`beauty_agent`；
- 应用查询角色：`beauty_bi_query`；
- Query Role 保持独立只读权限；
- secret 仅通过 Render Environment 注入，不进入 Git / image / README；
- `statement_timeout`、`max_rows`、connection pool、Investigation Round / Session Budget、Result Protection 与 Audit Finalization 继续生效；
- Observability 继续是 non-blocking side channel，不能改变业务 Runtime correctness。

Day92 公开 Smoke：

```text
2025年GMV是多少？
→ 11,430,211.41
→ PASS

2025年各渠道的GMV是多少
→ protected channel breakdown
→ independent overall = 11,430,211.41
→ PASS

Monthly MOM / 2025-07-31
current GMV = 719,931.12
reference GMV = 1,257,216.31
delta = -537,285.19
delta rate = -42.74%
channel contribution / reconciliation = available
→ PASS
```

Day92 同时关闭了数个只有真实 Cloud Runtime 才暴露的问题：
- Cloud Embedding shared client 未进入 Git；
- explicit metric semantic path 的历史隐藏风险；
- actual Query Plan 与 Approved Tool Binding 的多 Plan 选择边界；
- Overall scalar 与 breakdown / multi-field result 的 UI projection 边界；
- Cloud PostgreSQL Query Role password 与 Render secret drift。

最终 Query Role credential 对齐后，公网 Governed Result 正常释放。临时安全诊断只输出 host / database / query user / error category 等 allowlisted metadata，不记录密码、URL、SQL、parameters 或 rows，根因关闭后已从 production code 清理。

Day92 Regression：

```text
Unified Regression V2：
13 modules / 99 cases PASS

pip check：
PASS

git diff --check：
PASS

GitHub Actions：
Day92 formal repair commit observed PASS
```

当前 Day92 后仍明确保留：
- Blind / Fresh Generalization → Day93；
- Phase4 Full Regression / Public Delivery Hard Gate → Day94；
- Periodic Report date-widget year state 需要进一步收束；
- metric-level semantic clarification 仍需用户可选择的安全 UX；
- public edge rate-limit / observability final readiness 继续在 Day94 hardening review；
- Dataset V2 继续是 Candidate，Latest Stable 仍是 Day60 V1。


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

Day82 只建立 Contract Foundation；Day83-Day87 已继续完成 Anomaly、Contribution、Planner、Investigation Loop 与 Evidence Pack；Automated / Business Decision Evaluation 留到 Day88。

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
| investigation_loop_acceptance_v2.py | 39/39 PASS |
| investigation_tool_executor_acceptance_v2.py | 9/9 PASS |
| investigation_tool_executor_postgresql_integration_v2.py | 1/1 PASS |
| investigation_loop_postgresql_end_to_end_v2.py | 1/1 PASS |
| investigation_loop_failure_recovery_postgresql_v2.py | 1/1 PASS |
| evidence_pack_acceptance_v2.py | 14/14 PASS |
| evidence_pack_builder_acceptance_v2.py | 10/10 PASS |
| evidence_pack_postgresql_integration_v2.py | 1/1 PASS |
| derived_evidence_builder_acceptance_v2.py | 10/10 PASS |
| evidence_pack_observation_acceptance_v2.py | 10/10 PASS |
| evidence_pack_delivery_acceptance_v2.py | 10/10 PASS |
| insight_golden_case_contract_acceptance_v2.py | 12/12 PASS |
| insight_golden_cases_acceptance_v2.py | 12/12 PASS |
| automated_insight_evaluator_acceptance_v2.py | 6/6 PASS |
| business_decision_judge_calibration_acceptance_v2.py | 10/10 PASS |
| business_decision_rubric_calibration_acceptance_v2.py | 7/7 PASS |
| unified_regression_v2.py | 13 modules / 99 cases PASS（Day92） |

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

## Application / Runtime

- Python 3.10.x（Latest Stable host baseline：3.10.3；Day90 Docker：Python 3.10 compatibility line）
- Streamlit 1.61.1（Decision Console）
- FastAPI（Phase1 API Foundation；当前 Decision Console 主交付路径不依赖 FastAPI）

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

- Docker / Docker Compose
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
│       ├── analyze_dataset.py
│       ├── startup_readiness_v2.py
│       ├── startup_readiness_probe_v2.py
│       ├── bootstrap_v2.py
│       ├── manifest_loader.py
│       ├── seed_dimensions.py
│       ├── seed_transactions.py
│       └── acceptance_observer.py
├── llm/
│   └── deepseek_client.py
├── observability/
│   └── langfuse_observability_v2.py
├── semantic_layer/
├── text_to_sql/
├── ui/
│   └── decision_console_app.py
└── evaluation/
metadata/
├── business_metrics.yaml
├── query_plans.yaml
├── table_dictionary.yaml
└── table_relationships.yaml
docs/
├── evaluation/
│   └── day91_delivery_performance_evidence.md
.github/
└── workflows/
    └── ci.yml
Dockerfile
docker-compose.yml
.env.example
.dockerignore
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

状态：🚧 进行中（Day92 Cloud Deployment / Public Demo 已完成）

当前 Day82-Day94 目标：
- ✅ Day82：Insight Contract / Tool Contract / Time Comparison / Business Decision Evaluation Contract；
- ✅ Day83：Deterministic Anomaly Detection / Policy Candidate / Insight Evidence Integration；
- ✅ Day84：Deterministic Contribution Analysis / GMV × Channel / Insight Evidence Integration；
- ✅ Day85：Bounded Agentic Investigation Planner / Structured LLM Proposal / Deterministic Validation；
- ✅ Day86：Agentic Investigation Loop / Governed Tool Execution / Re-plan / Recovery / Stop / Budget；
- ✅ Day87：Evidence Pack / Provenance / Derived Lineage / Observation Evidence / Sufficiency / Delivery；
- ✅ Day88：Insight Golden Cases / Automated Evaluation / Business Decision Judge / Human Calibration / Rubric Versioning；
- ✅ Day89：Streamlit Decision Console / Runtime HITL / Daily-Weekly-Monthly Periodic Delivery / Final Delivery Gate；
- ✅ Day90：Docker Compose / One-command Startup / Fresh-volume Reproducibility；
- ✅ Day91：Observability / Unified Regression / CI / Delivery Performance；
- ✅ Day92：Cloud Deployment / Public Demo / Public Business Smoke；
- Day93：Blind Test / Human Expert Proxy Review；
- Day94：Phase4 Full Regression / Public Delivery Hard Gate。

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
Question / Business Anomaly
↓
Business Semantic Layer
↓
Deterministic Trust Plane
↓
Bounded Agentic Investigation
↓
Controlled Tool / SQL Execution
↓
Evidence-based Business Analysis
↓
Decision Console / Answer / Audit Trace
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

Version: v0.60
完成度：Day92 / 100
Phase3：CLOSED
Phase4：IN_PROGRESS（Day92 completed）

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
```

Day86 Bounded Agentic Investigation Loop：

```text
Loop Core：39/39 PASS
Tool Executor Adapter：9/9 PASS
Real PostgreSQL Tool Integration：1/1 PASS
Real PostgreSQL Two-step E2E Loop：1/1 PASS
Real PostgreSQL Failure → Recovery：1/1 PASS
Round / Session Budget：implemented
Cross-request State Persistence / Multi-Investigation Registry：not implemented
```

Day87 Evidence Pack & Delivery：

```text
Evidence Pack Contract：14/14 PASS
Governed Evidence Builder：10/10 PASS
Real PostgreSQL Evidence Pack：1/1 PASS
Derived Evidence Lineage：10/10 PASS
Investigation Observation Evidence：10/10 PASS
Evidence Delivery / Sufficiency：10/10 PASS
Metric Definition Snapshot：Dataset V2 metadata-bound
Numeric LLM Confidence：not used
```

Day88 Insight Evaluation & Human Calibration：

```text
Insight Golden Case Contract：12/12 PASS
Visible Regression Golden Cases：12/12 PASS
Automated Insight Evaluator：6/6 PASS
Business Decision Judge + Human Calibration：10/10 PASS
Rubric Versioning + Observed Calibration Evidence：7/7 PASS
Deterministic / Contract Acceptance：47/47 PASS

Real PostgreSQL + Live DeepSeek Observed Probe：PASS
Judge overall：PASS
Human Expert Proxy overall：PARTIAL
Disagreement：prioritization
Rubric：v1_0 → v2_0
Fresh Generalization：not claimed
```


Day89 Decision Console / Runtime HITL / Periodic Delivery：

```text
Decision Console：Business / Analyst / Engineering 三视图
Ad-hoc Investigation：Governed Seed → Bounded Investigation → Evidence / Trace
Runtime HITL Explicit Continue：implemented
Runtime HITL Clarification Response：implemented
Periodic：
- Daily / DOD：implemented；支持 privacy-aware PARTIAL_READY
- Weekly / WOW：implemented
- Monthly / MOM：implemented
Contribution：GMV × Channel + Reconciliation
Anomaly UI：Active Policy = 0 时保持“未评估 / 未激活”
Final Delivery Gate：95/95 PASS
Real PostgreSQL Final Gate：5/5 PASS
```

Day90 Docker / Reproducible Startup：

```text
Startup Readiness Contract：11/11 PASS
Startup Readiness Probe：11/11 PASS
Bootstrap Contract：8/8 PASS
Docker Linux Image Build：PASS
Existing-environment Investigation E2E：PASS
Existing-environment Monthly Report E2E：PASS
Fresh Bootstrap：initialize → seed → ANALYZE → query role → READY
Fresh Decision Console：healthy
Fresh Real GMV Query：PASS
Fresh Test Volume Cleanup：PASS
```

Day91 Observability / Unified Regression / CI：

```text
Safe Langfuse Observability：PASS
Real Investigation End-to-End Trace：PASS
DeepSeek Generation Usage：1,079 prompt + 286 completion = 1,365 tokens
Failure → RECOVER → Alternative PostgreSQL → STOP：PASS
Unified Regression：7 modules / 64 cases PASS
GitHub Actions Deterministic CI：PASS
Delivery Performance Evidence：documented
```


Day92 Cloud Deployment / Public Demo：

```text
Render Auto Deploy：PASS
Public Decision Console：PASS
Cloud Query Role Login / Read：PASS
Overall GMV Public Smoke：PASS
Channel GMV Public Smoke：PASS
Monthly MOM Public Smoke：PASS
Unified Regression：13 modules / 99 cases PASS
Final Git State：main == origin/main / working tree clean
Final Day92 Commit：50f15f2
```

当前已知限制：
- `SEM-REL-GAP-001`：live Structured Semantic Parser repeatability；
- `TIME-REL-GAP-001`：显式年份表达存在 whitespace / silent fallback 风险；Day88 只修 observed probe fixture，生产 Time Resolver 尚待 Public Delivery 前关闭；
- Periodic Report Date Widget：Day92 公网手工测试观察到年份切换后的首次日期选择可能回到当前年份，必须在 Day94 Hard Gate 前收束；
- Semantic Metric Clarification UX：模糊指标问题可以 fail-closed，但尚未把 metric-level `NEEDS_CLARIFICATION` 投影成 server-owned selectable choices；
- Cloud Observability / public edge rate-limit：Day92 不把它们冒充已完成 production hardening，Day94 只根据真实证据做最终声明；
- `SCOPE-GAP-001`：Requested Region / Channel Value Filter 尚未正式结构化；
- Scope Canonical Value Validation；
- 4 个 Query Plan 继续按 Scope Contract fail-closed；
- Post-sequence Scope Runtime；
- Multi-plan Execution Orchestration；
- V2 automatic SQL Repair Runtime disabled；
- real LLM token usage 已由 Day91 Langfuse Generation Capture 完成；可信 cost mapping 尚未验证，Token Usage 尚未接入在线 Execution Budget；Observability ↔ Audit 的进一步 correlation 仍可增强。

下一步：Day93 进入 Blind Test / Human Expert Proxy Review，使用真正 unseen business cases 通过公网 Decision Console 验证 Business Decision Quality、Judge ↔ Human calibration 与 success / partial / failure / unsupported 的诚实交付。
