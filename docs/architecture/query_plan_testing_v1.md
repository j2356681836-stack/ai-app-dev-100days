# Query Plan Testing V1

## 背景

Day38 完成了 Query Plan Routing：

    Question
    ↓
    Metric Recognition
    ↓
    Query Plan Routing
    ├─ ROI / CAC → Template SQL
    └─ 普通指标 → LLM SQL
    ↓
    SQL Execution
    ↓
    Result-level Evaluation

Day39 在此基础上完成 Query Plan 参数化：
- output.formula.alias
- output.formula.round
- output.formula.multiply_by_100
- default_sort.field
- default_sort.direction

这些配置开始从 metadata/query_plans.yaml 中读取。
因此，需要为 Query Plan 建立独立测试体系，避免配置、模板和主链路之间出现不一致。

---

### 测试分层

当前测试体系分为三层：
    配置层
    ↓
    模板层
    ↓
    端到端业务层

---

#### 1. 配置层测试：query_plan_tests.py

文件：app/evaluation/query_plan_tests.py
作用：验证 metadata/query_plans.yaml 是否符合 Query Plan V1 的结构和业务规则。

当前检查内容：

##### 1.1 必填字段检查

Top-level 必填字段：
- name
- metric
- query_type
- grain
- output
- default_sort

output.formula 必填字段：
- alias
- round
- multiply_by_100

default_sort 必填字段：
- field
- direction

##### 1.2 排序方向检查

允许值：
- asc
- desc
如果出现其他值，则测试失败。

##### 1.3 alias 与 default_sort.field 一致性

当前 V1 要求：output.formula.alias == default_sort.field
原因：当前 ROI / CAC 都是按最终输出指标排序。

例如：
output:
  formula:
    alias: roi

default_sort:
  field: roi
  direction: desc

##### 1.4 Query Plan 与模板实现一致性

检查：
query_plans.yaml 中声明的 metric
↓
generate_template_sql(metric, question)
↓
必须能生成 SQL

避免出现：
- 配置中声明了 ltv
- 但 template_sql_generator.py 没有实现 ltv 模板

##### 1.5 业务规则检查

当前覆盖 ROI / CAC。

ROI：
- multiply_by_100 必须是 false
- default_sort.direction 必须是 desc

原因：ROI 是倍数，不是百分比，且越高越好。

CAC：
- multiply_by_100 必须是 false
- default_sort.direction 必须是 asc

原因：CAC 是金额，不是百分比，且越低越好。

##### 1.6 输出报告

运行：python -m app.evaluation.query_plan_tests
输出：docs/evaluation/query_plan_tests_YYYYMMDD_HHMMSS.json
报告包含：
- test_suite
- timestamp
- summary
- results

---

#### 2. 模板层测试：template_sql_tests.py

文件：app/evaluation/template_sql_tests.py
作用：验证 Template SQL Generator 的局部逻辑。

当前检查内容：

##### 2.1 parse_limit

检查自然语言中的 Top1 / TopN / Ranking 解析。

示例：
- 哪个渠道ROI最高 → 1
- 各渠道ROI排名 → None
- 渠道ROI Top3 → 3
- 渠道ROI前3 → 3
- 获客成本最低的三个渠道 → 3
- 获客成本最低的3个渠道 → 3
- 获客成本前五渠道 → 5

关键规则：明确数量优先于极值表达

例如：获客成本最低的三个渠道
应解析为：LIMIT 3
而不是：LIMIT 1

##### 2.2 generate_template_sql

检查不同 metric 的模板分流：
- roi → ROI Template SQL
- cac → CAC Template SQL
- 普通指标 → None

当前验证：
- ROI 模板包含 date_window
- ROI 模板包含 channel_sales
- ROI 模板包含 channel_spend
- ROI 模板包含 ORDER BY roi DESC
- CAC 模板包含 first_paid_order
- CAC 模板包含 acquired_customers
- CAC 模板包含 ORDER BY cac ASC
- 普通指标不走模板

##### 2.3 输出报告

运行：python -m app.evaluation.template_sql_tests
输出：docs/evaluation/template_sql_tests_YYYYMMDD_HHMMSS.json
报告包含：
- test_suite
- timestamp
- summary
- sections.limit_tests
- sections.routing_tests

---

#### 3. 端到端业务测试：evaluator.py

文件：app/evaluation/evaluator.py
作用：验证自然语言问题最终能否返回正确业务结果。
当前检查内容：
- expected_tables
- expected_columns
- expected_result
- expected_order
- expected_generation_method

##### 3.1 expected_tables

验证生成 SQL 是否使用了预期表。

##### 3.2 expected_columns

验证生成 SQL 是否包含预期字段。

##### 3.3 expected_result

验证 Top1 结果是否正确。

例如：
- 哪个渠道ROI最高 → 天猫，roi = 1.68
- 哪个渠道获客成本最低 → 天猫，cac = 2284.40

##### 3.4 expected_order

验证排名顺序是否正确。

例如 ROI 排名：
- 天猫
- 微信小程序
- 京东
- 抖音
- 小红书

CAC 排名：
- 天猫
- 微信小程序
- 京东
- 抖音
- 小红书

##### 3.5 expected_generation_method

验证 SQL 生成路径是否符合预期。

当前要求：
- roi → template
- cac → template
- channel_sales_amount → llm
- channel_refund_rate → llm
这样可以避免 ROI / CAC 退回 LLM 但刚好结果正确的问题。

##### 3.6 输出报告

运行：python -m app.evaluation.evaluator
输出：docs/evaluation/evaluation_YYYYMMDD_HHMMSS.json

---

### 当前测试结果

- query_plan_tests.py      2/2 PASS
- template_sql_tests.py   12/12 PASS
- evaluator.py            20/20 PASS

### 三层测试职责边界

| 测试文件                  | 层级     | 主要保护对象                    |
| --------------------- | ------ | ------------------------- |
| query_plan_tests.py   | 配置层    | query_plans.yaml          |
| template_sql_tests.py | 模板层    | template_sql_generator.py |
| evaluator.py          | 端到端业务层 | query_service 主链路         |

---

### 为什么需要三层测试

query_plan_tests.py 能发现：
- query_plans.yaml 缺字段
- default_sort.direction 写错
- ROI / CAC multiply_by_100 写错
- 配置中声明了模板但代码未实现

template_sql_tests.py 能发现：
- parse_limit 解析错误
- TopN 被误判为 Top1
- ROI / CAC 没有生成正确模板结构
- 普通指标误走模板

evaluator.py 能发现：
- search_metric 识别错误
- query_service 分流错误
- SQL 无法执行
- 业务结果错误
- 排名顺序错误
- generation_method 不符合预期

---

### 当前技术债

#### 1. template_sql_tests 仍主要检查字符串包含

当前模板测试主要检查 SQL 是否包含关键片段。

后续可升级为：
- SQL AST 检查
- SQL 执行结果检查
- expected SQL snapshot

#### 2. Query Plan 参数化仍不完整

当前从 query_plans.yaml 读取：
- alias
- round
- multiply_by_100
- default_sort
但 SQL 主体结构仍然写在 Python 模板函数中。

后续可逐步参数化：
- date_window
- CTE steps
- join keys
- formula expression
- dimension

#### 3. parse_limit 应迁移到 Intent Parser

当前 parse_limit 位于：template_sql_generator.py
后续应迁移到：intent_parser.py
并拆分为：
- metric
- dimension
- sort_direction
- limit
- ranking_type

--- 

### 后续演进方向

#### V2：Intent Parser 接入

将用户问题解析为结构化 intent：
{
  "metric": "cac",
  "dimension": "channel",
  "sort_direction": "asc",
  "limit": 3,
  "ranking_type": "topn"
}

Template SQL Generator 不再直接解析 question，而是消费 intent。

#### V3：Query Plan 深度参数化

将更多 SQL 结构从 Python 模板移动到 query_plans.yaml：
- steps
- date_window
- joins
- formula
- dimensions
- filters

#### V4：CI / Dashboard

未来可将三个测试报告汇总为：docs/evaluation/latest_summary.json ，并进一步生成 dashboard。


---

## 写完文档后运行三层测试

`python -m app.evaluation.query_plan_tests`
`python -m app.evaluation.template_sql_tests`
`python -m app.evaluation.evaluator`

确认仍然：
- query_plan_tests.py      2/2 PASS
- template_sql_tests.py   12/12 PASS
- evaluator.py            20/20 PASS