# Day94 最终证据摘要

状态：本地冻结完成 / Public Delivery Hard Gate 待完成
阶段：Phase4 — Evidence-based Agentic Business Investigation + Public Delivery
日期：2026-09-02

---

## 1. 文档目的

本文汇总 Day94 用于判断 Phase4 是否具备最终交付条件的核心证据。

证据类型区分为：

```text
Deterministic Regression
PostgreSQL Integration
Observed Live Evidence
Manual UX Acceptance
历史 Security / Performance Baseline
Public Delivery Evidence
```

必须明确：

```text
Local PASS
≠
Public Delivery PASS

Observed live probe
≠
Deterministic regression

历史 baseline
≠
Day94 当日完整重跑
```

在最新 Day94 `main` 完成 Public Delivery Hard Gate 之前，Phase4 不能标记为 CLOSED。

---

## 2. 当前发布状态

```text
Phase1                      CLOSED
Phase2                      CLOSED
Phase3                      CLOSED
Phase4                      CLOSING

Dataset V2                  candidate
Latest Stable               Day60 / beauty_bi_v1 / 6701323
Stable Promotion            deferred
Production Active Anomaly   0
```

Day94 当前本地状态：

```text
Presentation & Verification Freeze   CLOSED
Business Artifact Final Acceptance   PASS
Final Regression Gate A              PASS
Final Regression Gate B1             PASS
Final Regression Gate B2             PASS
Trust & Verification Acceptance      PASS
Reproducibility Integration Gate     PASS

Public Delivery Hard Gate            PENDING
```

---

## 3. Day94 Final Regression

### 3.1 Gate A — Deterministic / Presentation / Export

覆盖内容：

- Unified Regression；
- hybrid comparison semantic acceptance；
- Investigation Report contract；
- technical report export；
- Business Word / Excel export；
- Business Artifact UX；
- UI wiring；
- Decision Console export wiring；
- Presentation consistency；
- Fact Composition public freeze；
- Periodic UX / UI delivery；
- Evidence Drawer / delivery wiring；
- `pip check`。

结果：

```text
Gate A = PASS
```

Gate A 期间曾出现 Export Wiring Acceptance 失败。

最终判断属于：

```text
STALE ACCEPTANCE
```

而不是产品回归。

原因是旧 Acceptance 仍冻结：

```text
Markdown + HTML 作为主导出
旧 evidence_lineage 展示职责
```

而当前正式产品合同已经调整为：

```text
Word / Excel
→ Business Primary

Markdown
→ Technical / Portfolio Optional

HTML
→ renderer retained
→ 不进入 Business UI 主交付
```

因此只刷新 Evaluation，不重新修改 Runtime / UI / Report Payload / Exporter 业务逻辑。

---

### 3.2 Gate B1 — Composition / PostgreSQL

执行：

```text
F01 Full Composition Contract
Fact Composition PostgreSQL Integration
```

结果：

```text
F01 Full Composition Contract             PASS
Fact Composition PostgreSQL Integration   PASS
```

覆盖证据链：

```text
Composition Contract
→ Query Plan
→ PostgreSQL
→ trusted Overall
→ member sum
→ unexplained remainder
→ reconciliation
```

---

### 3.3 Gate B2 — Periodic / R12 / Evidence / Trust

执行：

```text
Periodic Business Report PostgreSQL Integration
Daily / Weekly PostgreSQL Integration
Periodic Runtime PostgreSQL Integration
Periodic R12 Integration Acceptance
R12 Runtime Readiness Acceptance
Evidence Pack PostgreSQL Integration
Breakdown Trusted Summary PostgreSQL Integration
```

结果：

```text
7 项全部 PASS
```

该 Gate 最终覆盖：

```text
Periodic Report reproducibility
R12 readiness / reconciliation
Evidence Pack PostgreSQL lineage
Trusted Summary / Overall reconciliation
```

---

## 4. Trust & Verification Acceptance

### 4.1 代表性 FACT Case

问题：

```text
2025年上海地区GMV是多少？
```

Trusted Overall：

```text
GMV = 1,015,873.29
```

当前公开 additive Composition：

```text
渠道构成
→ reconciled
→ trusted Overall = 1,015,873.29
→ unexplained remainder = 0.00

品类构成
→ reconciled
→ trusted Overall = 1,015,873.29
→ unexplained remainder = 0.00
```

跨维度验证：

```text
Channel Overall
=
Category Overall
=
Independent trusted Overall
```

结果：

```text
PASS
```

业务 UI 不通过当前可见 breakdown rows 重新求和生成新的 Overall Truth。

Overall 使用独立 Governed Evidence，Composition 只负责与该 trusted Overall 做 reconciliation。

---

### 4.2 People Composition 发布决策

状态：

```text
DEFERRED / NOT PUBLICLY RELEASED
```

原因：

legacy People path 当前使用 payment-time membership 语义。

最终确认的业务定义要求：

```text
Old Customer
→ 在分析窗口之前已存在于 requested channel scope
→ 使用分析窗口开始前最近一次 membership snapshot

New Customer
→ 第一次购买发生在当前分析窗口内
→ lifecycle history 使用 requested channel scope
→ 不再按 membership tier 拆分
```

预期业务结构：

```text
老客｜铂金会员
老客｜黄金会员
老客｜白银会员
老客｜青铜会员
老客｜非会员
老客汇总
新客
汇总
```

正确修复会涉及：

```text
lifecycle history
temporal membership snapshot
stage-aware per-target scope
Delivery subtotal
Governance regression
```

Day94 Closing 决策：

```text
语义未满足最终业务定义
→ 不公开发布
```

而不是展示“数值可以算出来，但回答的其实不是同一个业务问题”的结果。

---

## 5. Presentation / Business Artifact Acceptance

人工验收：

```text
FACT            PASS
COMPARISON      PASS
INVESTIGATION   PASS
PERIODIC        PASS
```

### FACT

最终结构：

```text
业务问题
→ 核心结果
→ 渠道 / 品类构成
→ trusted 汇总
→ 业务口径与可信边界
```

### COMPARISON

最终结构：

```text
业务问题
→ 核心对比
→ 关键发现
→ 业务口径与可信边界
```

纯 Comparison 不会静默升级成 Investigation。

### INVESTIGATION

最终业务报告结构：

```text
决策摘要
→ 核心对比
→ 调查明细
→ trusted summary / reconciliation
→ 可以确认
→ 暂不能确认 / 因果边界
→ 下一步建议
→ 业务口径与可信边界
```

业务报告不再直接暴露：

```text
reconciled
```

这类工程 enum，而是转换成业务可读表达。

### PERIODIC

最终业务报告结构：

```text
报表范围
→ 本期经营摘要
→ 经营概览
→ 销售驱动
→ 客户健康
→ 驱动关系验证
→ 本期限制
→ 指标说明
```

经营摘要有意优先展示：

```text
当前值
变化额
变化率
```

完整参考期值保留在下一层 KPI 明细，避免摘要重复整张报表。

---

## 6. Periodic Business Report Acceptance

支持手动生成：

```text
Daily   → DOD
Weekly  → natural-week WOW
Monthly → MOM
```

最终本地验收：

```text
Daily    PASS
Weekly   PASS
Monthly  PASS
```

Shared anchor behavior：

```text
PASS
```

代表性 Monthly：

```text
Anchor = 2025-10-31

Reference GMV = 847,765.20
Current GMV   = 1,231,371.04
Delta         = +383,605.84
Delta Rate    = +45.25%
```

Driver Relationship：

```text
GMV = Buyer Count × Spending
→ reconciled

Spending = AUS × FREQ
→ reconciled
```

ratio / derived metric 不通过错误相加各维度 ratio 做 reconciliation。

---

## 7. Business Decision Quality Evidence

Phase4 使用六维 Business Decision Evaluation：

```text
factual correctness
diagnostic relevance
prioritization
actionability
epistemic discipline
evidence sufficiency
```

Day88 历史 observed calibration：

```text
Live Judge overall            PASS
Human Expert Proxy overall    PARTIAL
Disagreement                  prioritization
Critical disagreement         0
```

该 disagreement 形成一个重要规则：

```text
“业务规模最大”
≠
“最值得优先调查”
```

Investigation prioritization 必须与当前 business objective 直接相关，并有比较性 Evidence 支撑。

Day93 进一步完成：

```text
F02 Human Calibration              PASS
FG01 Post-Failure Regression       PASS
FG02 Fresh Generalization          PASS
```

Fresh Evidence Discipline：

```text
用于调试 / 修复的 Case
→ 不再保持 Fresh 身份

修复冻结后首次执行的新未见 Case
→ 才可作为 Fresh Generalization Evidence
```

---

## 8. Security / Governance Evidence

### 8.1 继承的 Security Baseline

Phase3 Closing Security Baseline：

```text
Security Evaluation      21/21 Controlled PASS
Unexpected FAIL          0
Known Gap                0
```

覆盖：

```text
Metric Authorization
Table / Column Authorization
Region / Channel Row Scope
Dedicated read-only PostgreSQL role
read-only transaction
statement_timeout
max_rows
Result Protection
HMAC-based sensitive reference protection
Structured Audit Event
Hash-chain Audit Sink
Governed Finalization
PostgreSQL AST Enforcement
Repair Candidate Governance
```

证据分类必须明确：

```text
这是 Phase3 / Day80-Day81 的继承安全基线
不是声称 Day94 又完整重跑了一遍 Security Suite
```

Day94 没有重新扩张 Governance 设计。

但 Day94 Final PostgreSQL / Trust Integration Gate 已在最终 Presentation / Export Freeze 后重新通过。

---

## 9. Performance Evidence

### 9.1 Dataset V2 Query Performance Baseline

历史性能问题：

```text
Bulk Seed
→ PostgreSQL Planner Statistics 缺失
→ Query Plan 退化
→ 代表性查询约 19–20s
```

修复：

```text
ANALYZE beauty_bi_v2
```

修复后代表性 DB 查询：

```text
GMV Overall        ≈ 32 ms
GMV Channel        ≈ 43 ms
Refund Rate        ≈ 56 ms
Multi-order        ≈ 23 ms
```

Deterministic V2 E2E：

```text
≈ 0.8s
```

Production Runtime Policy：

```text
statement_timeout = 5000 ms
max_rows = 200
```

因此冻结 Dataset lifecycle：

```text
Create / Rebuild
→ Seed
→ Formal Acceptance
→ ANALYZE
→ Query / Performance Readiness
```

---

### 9.2 Observed Investigation Latency

Day91 一次真实 Trace：

```text
investigation_round                 ≈ 7.44s
investigation_step                  ≈ 6.93s
planner                             ≈ 6.83s
deepseek_chat_completion            ≈ 6.81s
tool_execution                      ≈ 0.09s
sql_execution                       ≈ 0.06s
```

Observed token usage：

```text
Prompt      1,079
Completion    286
Total       1,365
```

当前可以支持的判断：

```text
在该真实样本中，
主要 latency 来自 LLM Generation，
不是 PostgreSQL SQL Execution。
```

不能外推为：

```text
P95
P99
SLA
Capacity Benchmark
```

---

## 10. Reproducibility Evidence

### 10.1 Fresh Docker Environment

Day90 Fresh-volume Gate：

```text
empty isolated volume
→ initialize schema
→ deterministic seed
→ formal acceptance
→ ANALYZE
→ provision query role
→ Bootstrap READY
→ Decision Console healthy
→ real GMV query PASS
```

该证据证明：

```text
Infrastructure Setup
Data Semantics
Query Runtime Readiness
Business Result Execution
```

可以在全新环境中重复建立。

不声称：

```text
byte-for-byte reproducibility
```

---

### 10.2 CI

Minimal Deterministic CI：

```text
GitHub Actions
→ Ubuntu
→ Python 3.10
→ requirements-lock.txt
→ pip check
→ Unified Regression
```

Day92 Public Baseline：

```text
Unified Regression V2
13 modules / 99 cases PASS
```

Day94 Local Final Regression 比 Day92 Public Baseline 更完整，因为已经额外包含最终：

```text
Presentation
Export
Business Artifact
Trust
Composition
Periodic / R12
Evidence
```

Closing Gate。

---

## 11. Evidence / Provenance Architecture

Evidence 类型：

```text
Direct Governed Evidence
Derived Evidence
Investigation Observation Evidence
```

Direct Governed Evidence 必须满足：

```text
Governed Execution Success
+
Result Protection
+
Audit Persistence
+
Governed Finalization
```

Derived Evidence 保留 parent lineage，例如：

```text
Anomaly
Contribution
```

Investigation Observation：

```text
EVIDENCE
NO_DATA
FAILURE
```

关键边界：

```text
NO_DATA
≠
0

FAILURE
不能支撑业务数值 Fact
```

---

## 12. Export / Report Payload Consistency

最终交付合同：

```text
Decision Console
Word
Excel
Markdown
```

使用同一份 structured Report Payload。

Export Layer 不允许：

```text
重新查询
重新调用 LLM 生成另一套结论
重新定义 Metric
独立重算业务真值
自行修复 reconciliation
```

这样可以避免：

```text
Console 一套结论
Word 一套结论
Excel 又一套结论
```

最终业务事实只有一个受治理来源。

---

## 13. 当前 Known Boundaries

当前明确 Deferred / Unsupported：

```text
People Composition final lifecycle semantics
Evidence-aware adaptive routing
Campaign × Channel
Campaign × Category
Channel × Category
causal uplift / counterfactual
Scheduler / Subscription / Automatic Distribution
durable multi-investigation persistence
Multi-plan execution orchestration
V2 automatic SQL Repair Runtime
Production anomaly-policy calibration
Dataset V2 Stable Promotion
```

其他 reliability debt 继续以 `PROJECT_STATE.md` 为唯一事实源。

---

## 14. Public Delivery Hard Gate

当前状态：

```text
PENDING
```

Phase4 Closing 前必须完成：

```text
1. Day94 local final freeze 提交到 main
2. Push latest main
3. Render latest-main redeploy
4. 公网 comparison-aware Investigation smoke
5. 公网 Monthly historical anchor first-submit smoke
6. 公网 History / Verification / Investigation UI smoke
7. 对剩余 TIME reliability boundary 给出明确验证 / 关闭证据
8. 确认 Cloud Behavior 与 Local Freeze 一致
```

只有全部通过后：

```text
Public Delivery Hard Gate = PASS
Phase4 Closing Decision = CLOSED
```

---

## 15. Day94 当前证据结论

当前可以正式确认：

```text
Local Product Freeze                 PASS
Local Final Regression               PASS
Trust & Verification                 PASS
Business Artifact                    PASS
PostgreSQL Integration               PASS
Periodic / R12                       PASS
Evidence / Trusted Summary           PASS
Reproducibility Integration          PASS
```

仍未完成：

```text
Public Delivery Hard Gate            PENDING
Phase4                               CLOSING
```

因此 Day94 当前结论是：

```text
READY FOR FINAL PUBLIC DELIVERY VALIDATION
```

而不是：

```text
Phase4 CLOSED
```
