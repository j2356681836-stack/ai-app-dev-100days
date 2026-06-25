# LangGraph Phase3 Design

## 背景

Phase2 当前已经完成 AI Data Analyst / Text-to-SQL 主链路。

当前主链路由 `query_service.py` 中的 `ask(question)` 串联完成：

Question
↓
Intent Parser
↓
Hybrid Search / Metric Recognition
↓
Query Plan Routing
↓
Template SQL / LLM SQL
↓
SQL Cleaner
↓
SQL Validator
↓
PostgreSQL
↓
Result Formatter
↓
Answer Generator
↓
Response

这条线性 pipeline 已经可以支撑 Phase2 的核心功能，但它存在一个明显边界：
遇到 clarification、SQL validation failure、SQL execution error、evaluation failure 时，当前流程主要是直接返回或抛错，还没有形成可分支、可回退、可重试的 workflow。
Phase3 引入 LangGraph 的目标不是推翻 Phase2，而是将 Phase2 已完成模块组织成可控 workflow。

---

## Phase3 设计原则

1. 不推翻 Phase2
2. 不重写所有模块
3. 复用现有 query_service.py 中已经跑通的函数
4. 先做 workflow design，再做最小 prototype
5. 优先处理 clarification、SQL validation / repair、eval-driven retry

LangGraph 的价值不是“换一个框架”，而是让当前系统从线性流程升级为：
可分支
可重试
可修复
可观察
可逐步扩展

---

## 当前 query_service.py 线性流程

当前 `ask(question)` 主要流程：
parse_intent(question)
↓
search_metric(question)
↓
get_query_plan_by_metric(metric_name)
↓
enrich_intent_with_query_plan(intent, query_plan)
↓
generate_template_sql_from_intent(metric_name, intent)
↓
如果 template_sql 存在：
    raw_sql = template_sql
    generation_method = "template"
否则：
    raw_sql = generate_sql(question, intent=intent)
    generation_method = "llm"
↓
clean_sql(raw_sql)
↓
validate_sql(sql)
↓
run_sql(sql)
↓
format_result(rows)
↓
to_table(rows)
↓
generate_answer(question, table, intent)
↓
return response

当前这条流程的优点：
结构清晰
端到端链路稳定
ROI / CAC 已经分流到 Template SQL
普通指标仍保留 LLM 灵活性
Answer Layer 和 Evaluation 已经接入

当前边界：
1. metric 未匹配时直接返回，尚未形成交互式 clarification loop
2. SQL validation 失败时直接抛错，尚未进入 repair loop
3. SQL execution 失败时尚未自动修复
4. Evaluation 失败后尚未触发 retry
5. 所有中间状态没有统一 state 管理

---

## LangGraph State 设计

Phase3 V1 先设计一个统一 state。

```python
class AnalystState(TypedDict, total=False):
    question: str

    intent: dict
    metric_result: dict
    metric_name: str
    query_plan: dict | None

    needs_clarification: bool
    clarification_options: list[dict]

    generation_method: str
    raw_sql: str
    sql: str

    sql_valid: bool
    sql_error: str | None

    rows: list[dict]
    table: dict
    answer: str

    evaluation_result: dict
    evaluation_passed: bool

    errors: list[str]
    retry_count: int
    max_retries: int
```

### State 字段说明

`question`：用户原始自然语言问题。
`intent`：Intent Parser / Intent Resolver 输出。包含 limit、ranking_type、sort_hint、dimension、final_sort_direction、sort_field。
`metric_result`：Hybrid Search 输出。用于判断是否 matched 或 needs_clarification。
`metric_name`：最终选中的业务指标。
`query_plan`：ROI / CAC 等复杂指标的 query plan。普通指标可能为 None。
`generation_method`：template 或 llm。用于后续 evaluation 和 debug。
`raw_sql`：Template SQL 或 LLM 原始 SQL。
`sql`：clean_sql 后的 SQL。
`sql_valid`：SQL Validator 结果。
`rows` / `table`：数据库执行结果和格式化后的表格。
`answer`：Answer Generator 输出。
`evaluation_result`：后续 eval-driven retry 使用。
`retry_count`：避免无限重试。

---

## LangGraph Nodes 设计

### 1. parse_intent_node

当前复用：`parse_intent(question)`
输入：question
输出：intent
作用：解析 limit、ranking_type、sort_hint、dimension。

---

### 2. search_metric_node

当前复用：`search_metric(question)`
输入：question
输出：metric_result
作用：通过 Alias / Keyword Group / Embedding / Clarification 识别指标。
可能结果：
matched
needs_clarification
error

条件分支：
matched → select_metric_node
needs_clarification → clarification_node
error → fail_node

---

### 3. clarification_node

Phase3 新增设计节点。

作用：当 Hybrid Search 低置信度或候选指标接近时，向用户返回候选项。
输入：metric_result.suggestions
输出：
clarification_options
needs_clarification = True

V1 可以先只返回候选，不做多轮对话。

Phase3 后续可以扩展为：
用户选择 metric
↓
继续 SQL generation

---

### 4. select_metric_node

当前逻辑来自 `query_service.py`：
```python
metrics = metric_result.get("metrics", [])
metric_name = metrics[0]["name"]
```

输入：metric_result
输出：metric_name
失败点：metrics 为空
条件分支：
metric_name exists → load_query_plan_node
metrics empty → fail_node


---

### 5. load_query_plan_node

当前复用：`get_query_plan_by_metric(metric_name)`

输入：metric_name
输出：query_plan
说明：
ROI / CAC 返回 query_plan。
普通指标可能返回 None。

---

### 6. resolve_intent_node

当前复用：`enrich_intent_with_query_plan(intent, query_plan)`

输入：
intent
query_plan
输出：enriched intent
作用：补充 final_sort_direction 和 sort_field。

---

### 7. generate_template_sql_node

当前复用：`generate_template_sql_from_intent(metric_name, intent)`

输入：
metric_name
intent

输出：
raw_sql 或 None
generation_method


条件分支：
raw_sql exists → clean_sql_node
raw_sql is None → generate_llm_sql_node

---

### 8. generate_llm_sql_node

当前复用：`generate_sql(question, intent=intent)`

输入：
question
intent

输出：
raw_sql
generation_method = "llm"

风险：
LLM 可能生成错误字段
LLM 可能编造状态值
LLM 可能输出 Markdown
LLM 可能忽略 intent

---

### 9. clean_sql_node

当前复用：`clean_sql(raw_sql)`

输入：raw_sql
输出：sql

---

### 10. validate_sql_node

当前复用：`validate_sql(sql)`

输入：sql
输出：sql_valid
条件分支：
sql_valid = True → run_sql_node
sql_valid = False → repair_sql_node 或 fail_node

Phase3 V1 可先设计 repair 分支，但不一定马上实现。

---

### 11. repair_sql_node

Phase3 新增设计节点。

目标：当 SQL validator 或 SQL execution 报错时，尝试修复 SQL。

输入：
question
intent
metric_name
sql
sql_error
retry_count

输出：
raw_sql / sql
retry_count + 1
条件限制：retry_count < max_retries

如果超过重试次数：fail_node

---

### 12. run_sql_node

当前复用：`run_sql(sql)`
输入：sql
输出：rows
可能失败：数据库连接失败
SQL 执行失败
字段不存在
表不存在

条件分支：
success → format_result_node
failure → repair_sql_node 或 fail_node

---

### 13. format_result_node

当前复用：
```python
format_result(run_sql(sql))
to_table(rows)
```

输入：rows
输出：table

---

### 14. generate_answer_node

当前复用：`generate_answer(question, table, intent)`

输入：
question
table
intent

输出：answer

---

### 15. evaluate_answer_node

Phase3 可以复用当前 Evaluation Workflow。

可选复用：
expected_answer_points
answer_judge
ragas_eval

Phase3 V1 不一定直接接全量 evaluator，但设计上应预留：
evaluation_result
evaluation_passed

作用：判断回答是否满足最低质量要求。

条件分支：
evaluation_passed = True → finish_node
evaluation_passed = False and retry_count < max_retries → repair / regenerate
evaluation_passed = False and retry_count >= max_retries → fail_node

---

### 16. finish_node

输出最终结果：
success = True
status = completed
question
generation_method
intent
sql
table
answer

---

### 17. fail_node

统一失败输出：
success = False
status = error / needs_clarification
message
errors
suggestions

---

## Conditional Edges 设计

### 1. Metric Search 分支

search_metric_node
├─ matched → select_metric_node
├─ needs_clarification → clarification_node
└─ error → fail_node

---

### 2. SQL 生成路径分支

generate_template_sql_node
├─ template_sql exists → clean_sql_node
└─ template_sql is None → generate_llm_sql_node

---

### 3. SQL Validation 分支

validate_sql_node
├─ valid → run_sql_node
└─ invalid → repair_sql_node

---

### 4. SQL Execution 分支

run_sql_node
├─ success → format_result_node
└─ error → repair_sql_node

---

### 5. Retry 分支

repair_sql_node
├─ retry_count < max_retries → clean_sql_node / validate_sql_node
└─ retry_count >= max_retries → fail_node

---

### 6. Evaluation 分支

evaluate_answer_node
├─ passed → finish_node
└─ failed → retry_or_finish_node

---

## Phase3 最小 Prototype 建议

Day49 只做设计，不大规模重构。
后续最小 prototype 可选：

### 方案 A：只包装现有 ask 流程

LangGraph state
↓
single node: ask_node
↓
finish

优点：
最安全
不破坏现有代码
快速验证 LangGraph 基础

缺点：没有发挥 graph 分支能力

---

### 方案 B：拆出 clarification 分支

parse_intent
↓
search_metric
↓
matched / needs_clarification

优点：
最贴合当前技术债
能体现 graph 条件分支价值

缺点：还没有 SQL repair loop

---

### 方案 C：拆出 SQL validation / repair 分支

generate_sql
↓
validate_sql
↓
valid / repair

优点：能体现 eval-driven engineering
缺点：
需要新增 repair prompt 或 repair function
风险略高

建议 Phase3 首个 prototype 采用：

方案 B：clarification 分支


原因：
1. 风险低
2. 和 Semantic Retrieval 技术债直接相关
3. 不需要改 SQL 生成链路
4. 能体现 LangGraph conditional edge 的价值

---

## 与 Phase2 技术债的关系

LangGraph Phase3 应优先承接以下 Phase2 技术债：
1. Semantic Retrieval Calibration
2. Clarification Loop
3. SQL Validation / Repair
4. Eval-driven Retry
5. Answer Quality Feedback


LangGraph 不应立即处理：
1. Beauty Dataset V2 完整重建
2. Dashboard
3. 全量指标体系扩展
4. 复杂 Insight Layer

这些属于后续 Phase3 / Phase4 延伸。

---

## 面试表达

可以这样解释为什么引入 LangGraph：

Phase2 的 query_service.py 是一条线性 pipeline，它已经能完成 Text-to-SQL 主链路。但真实 AI Agent 系统不是每一步都一次成功。指标识别可能需要 clarification，SQL 可能校验失败，执行可能报错，回答质量可能不达标。
所以 Phase3 我计划用 LangGraph 把线性流程拆成节点和条件边。Intent Parser、Metric Search、SQL Generator、Validator、Runner、Answer Generator 都可以复用 Phase2 已经完成的函数。LangGraph 的价值在于增加状态管理、分支、重试和修复能力，而不是推翻原来的系统。

---

## 当前结论

Phase3 LangGraph 的定位是：
复用 Phase2 模块
承接 Phase2 技术债
增加 workflow 状态管理
增加 conditional edges
增加 clarification / repair / retry loop

Day49 只完成设计，不进行大规模代码重构。

下一步：
1. 根据本设计文档确认 Phase3 第一版 prototype 范围
2. 优先实现 clarification branch
3. 保持 query_service.py 原主链路稳定

---

## Day49 Prototype 验证结果

Phase3 LangGraph 方案 B 已完成最小 prototype：

parse_intent
↓
search_metric
↓
route_metric_status
├─ matched → continue_pipeline
├─ needs_clarification → clarification
└─ error → fail

当前验证问题：
哪个渠道销售额最高
→ matched
→ continue_pipeline
→ generation_method = llm
→ completed

各渠道ROI排名
→ matched
→ continue_pipeline
→ generation_method = template
→ completed

最赚钱
→ needs_clarification
→ clarification branch
→ 不强行生成 SQL


当前回归结果：
evaluator.py：26/26 PASS
answer_judge.py --mode mock：6/6 PASS
ragas_eval.py --include-negative：6/6 expectation passed

结论：
LangGraph 方案 B 的最小分支验证通过。
当前 prototype 已经证明 clarification 可以从 query_service.py 的普通 if 判断升级为 LangGraph conditional edge。

---

## Day49 Graph Prototype 测试结果

Day49 已完成 Phase3 LangGraph 方案 B 的最小 prototype。

当前 graph 流程：
parse_intent
↓
search_metric
↓
route_metric_status
├─ matched → continue_pipeline
├─ needs_clarification → clarification
└─ error → fail

当前新增文件：
app/agents/analyst_graph.py
app/agents/analyst_graph_tests.py

当前验证结果：
python -m app.agents.analyst_graph_tests
Total: 3
Passed: 3
Failed: 0

测试覆盖路径：
哪个渠道销售额最高
→ matched
→ continue_pipeline
→ generation_method = llm
→ completed

各渠道ROI排名
→ matched
→ continue_pipeline
→ generation_method = template
→ completed

最赚钱
→ needs_clarification
→ clarification branch
→ 返回候选指标 suggestions


当前重要修正：
底层 hybrid_search 在 needs_clarification 时返回 options 字段。
Graph 层统一对外转换为 suggestions 字段。

该修正让上层接口更稳定：
底层 search module 可以保留 options
Graph / API / frontend 统一读取 suggestions

当前结论：
LangGraph 方案 B 已经验证通过。
当前 prototype 已经将 query_service.py 中的 metric status 判断，从普通 if 分支升级为 LangGraph conditional edge。

---

### 当前发现的 Retrieval 问题

Day49 测试中，“最赚钱”已正确进入 clarification branch，但 suggestions 排序暴露出 Hybrid Search 候选排序问题：CAC / 获客成本 与“最赚钱”的语义关联不应高于 ROI / 利润 / 销售额类指标。

该问题已记录为 Clarification Candidate Ranking Debt，后续应通过 retrieval evaluator 和 metric_text_builder 优化处理。

---

## 当前依赖风险

安装 LangGraph 后，当前环境出现依赖冲突：
langchain 0.3.30 requires langchain-core < 1.0.0, >= 0.3.85
langchain-openai 0.3.35 requires langchain-core < 1.0.0, >= 0.3.78
current langchain-core = 1.4.8

当前虽然 evaluator、answer_judge、ragas_eval 和 analyst_graph 仍能运行，但 `pip check` 已显示环境不一致。

该问题应记录为 Phase3 Dependency Management Debt。

后续处理原则：
1. 不继续在当前冲突环境中叠加复杂功能
2. Phase3 开始前需要统一 LangGraph / LangChain / Ragas / langchain-openai 的兼容版本
3. 建议新增 requirements.txt 或 requirements-lock.txt
4. 后续所有依赖变更必须先跑 pip check
5. pip check 不通过时不能视为环境健康
