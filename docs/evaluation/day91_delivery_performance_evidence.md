# Day91 Delivery Performance Evidence

> 状态：Observed Evidence（单次 / 少量实测证据），不是 Benchmark / SLA / Capacity Claim。

## 1. 证据目的

Day91 需要证明一次真实 Investigation 的主要执行阶段可以被观测，并能够回答：

- 整体请求耗时多少；
- Planner / LLM / Tool / SQL 分别耗时多少；
- LLM Token Usage 是否可见；
- Agent 最终为什么停止；
- failure / recovery path 是否可观察；
- Observability 是否避免自动上传业务 Input / Output。

## 2. Live DeepSeek + PostgreSQL Investigation

来源：Day91 live end-to-end observability probe。

Trace 结构：

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

- Prompt tokens: 1,079
- Completion tokens: 286
- Total tokens: 1,365

Loop / Runtime：

- Selected action: `drill_region`
- Runtime status: `stopped`
- Directive: `stop`
- Stop reason: `no_legal_action`
- Round number: `1`

安全观测：

- Trace Input: `null`
- Trace Output: `undefined`
- 未自动上传 prompt / response / SQL / SQL parameters / rows / AccessContext / Evidence payload。

## 3. Deterministic PostgreSQL Investigation

来源：Day91 PostgreSQL integration trace（deterministic planner）。

```text
investigation_round                 0.40s
└─ investigation_step               0.07s
   ├─ tool_execution                0.07s
   │  └─ governed_query_execution   0.06s
   │     └─ sql_execution            0.05s
   ├─ evidence_update
   └─ loop_control
```

Integration result：

- Total: 1
- Passed: 1
- Failed: 0

## 4. Failure / Recovery Investigation

来源：Day91 failure / recovery observability probe，复用 Day86 真实 PostgreSQL failure-recovery integration。

```text
investigation_failure_recovery      1.36s
├─ tool_execution                   0.34s
│  └─ governed_query_execution      0.34s
│     └─ sql_execution              0.32s
├─ loop_control
├─ tool_execution                   0.07s
│  └─ governed_query_execution      0.07s
│     └─ sql_execution              0.05s
└─ loop_control
```

Failure Loop Control：

```text
action_id = drill_channel
status = failure
retryable = false
attempt_number = 1
directive = recover
```

Recovery Loop Control：

```text
action_id = drill_region
status = evidence
retryable = false
attempt_number = 1
directive = stop
stop_reason = evidence_sufficient
```

该证据证明 Day91 Observability 不只覆盖 happy path，也能看见治理阻断后的 non-retryable recovery、替代查询路径与最终停止原因。

## 5. 当前性能解释

这些证据支持以下 observed 结论：

1. 在 live Investigation 中，主要延迟来自 LLM Generation，而不是 PostgreSQL SQL Execution。
2. `planner` 与 `deepseek_chat_completion` 的耗时非常接近，说明该样本中 Planner 的 JSON parse / Pydantic validation / deterministic validation 不是主要耗时来源。
3. 成功路径 PostgreSQL SQL execution 在当前样本中处于几十毫秒量级；failure 路径首次 SQL 约 0.32s。当前证据不足以推导一般化数据库性能 SLA。
4. `evidence_update` 与 `loop_control` 在当前样本中耗时极低，但它们仍有独立观测价值，因为需要记录 Evidence 数量、REPLAN / RECOVER / STOP 与 stop reason。
5. `investigation_round` 比 `investigation_step` 更长，说明外围 runtime setup / binding preparation / planning-envelope compilation / delivery assembly 仍存在可观测但尚未进一步拆分的耗时。
6. Live LLM token usage 已可捕获；DeepSeek cost 尚未建立经验证的 pricing mapping，因此不将空 / 0 cost 显示冒充可信成本证据。

## 6. 证据边界

本文件记录的是 Day91 单次 / 少量运行的 observed evidence，不等同于：

- 性能 Benchmark；
- P95 / P99 latency；
- 并发能力；
- 容量测试；
- SLA / SLO；
- 云端部署性能；
- 成本预算承诺。

这些需要在后续专门的 performance / load / production validation 中建立。

另外：

```text
Token Usage = captured
Trusted Cost Evidence = not claimed
```

## 7. Day91 Delivery Performance Gate

- Real Investigation total latency captured: PASS
- Planner latency captured: PASS
- LLM Generation latency captured: PASS
- Tool / Governed Query / SQL latency captured: PASS
- LLM token usage captured: PASS
- Loop stop reason captured: PASS
- Failure / RECOVER / alternative path captured: PASS
- Final STOP / EVIDENCE_SUFFICIENT captured: PASS
- Safe metadata / no automatic business payload upload: PASS
- Cost mapping gap explicitly disclosed: PASS
- Performance evidence documented with non-SLA boundary: PASS
