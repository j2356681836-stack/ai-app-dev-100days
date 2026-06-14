# Day39 学习日志

## 今日主题

Query Plan 参数化 V1 与测试体系加固

---

## 今日目标

Day38 已完成 Query Plan Routing：
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

Day39 的目标是：
- 让 query_plans.yaml 不再只是分流依据
- 让其开始参与 Template SQL 生成
- 为 Query Plan / Template / 主链路建立更清晰的测试分层
- 输出可追踪的 JSON 测试报告

---

## 今日完成内容

### 1. Template SQL Generator 参数化

修改文件：app/text_to_sql/template_sql_generator.py
新增或调整：
- get_template_config
- build_order_by_clause
- build_formula_expression
当前从 metadata/query_plans.yaml 读取：
- output.formula.alias
- output.formula.round
- output.formula.multiply_by_100
- default_sort.field
- default_sort.direction

### 2. ROI / CAC 模板读取 Query Plan 配置

ROI 当前从 query plan 读取：
- alias = roi
- round = 2
- multiply_by_100 = false
- default_sort.field = roi
- default_sort.direction = desc

生成 SQL 保持：
- ROUND(cs.sales_amount / NULLIF(csp.spend_amount, 0), 2) AS roi
- ORDER BY roi DESC

CAC 当前从 query plan 读取：
- alias = cac
- round = 2
- multiply_by_100 = false
- default_sort.field = cac
- default_sort.direction = asc

生成 SQL 保持：
- ROUND(cs.marketing_spend_amount / NULLIF(ac.acquired_customer_count, 0), 2) AS cac
- ORDER BY cac ASC

### 3. Query Plan 配置测试

新增或增强文件：app/evaluation/query_plan_tests.py

当前检查内容：

#### 配置结构检查

检查 top-level 必填字段：
- name
- metric
- query_type
- grain
- output
- default_sort

检查 output.formula 必填字段：
- alias
- round
- multiply_by_100

检查 default_sort 必填字段：
- field
- direction

#### 排序方向检查

允许：
- asc
- desc

#### alias 与 default_sort.field 一致性检查

当前 V1 要求：
- output.formula.alias == default_sort.field
- Query Plan 与模板实现一致性检查

确保：
    query_plans.yaml 中声明的 metric
    ↓
    generate_template_sql(metric, question)
    ↓
    可以生成 SQL
避免只写配置但忘记实现模板函数。

#### 业务规则检查

ROI：
- multiply_by_100 必须是 false
- default_sort.direction 必须是 desc

CAC：
- multiply_by_100 必须是 false
- default_sort.direction 必须是 asc

今日做过一次故意改错实验：
    将 cac.multiply_by_100 改为 true
    ↓
    query_plan_tests 失败
    ↓
    提示：cac should not multiply by 100
    ↓
    改回 false 后测试通过

说明测试已经能保护业务口径。

### 4. Query Plan 测试报告保存

query_plan_tests.py 新增 JSON 报告输出。

运行：python -m app.evaluation.query_plan_tests
输出：docs/evaluation/query_plan_tests_YYYYMMDD_HHMMSS.json

报告包含：
- test_suite
- timestamp
- summary
- results

当前结果：
- Total: 2
- Passed: 2
- Failed: 0
- Pass Rate: 100%

--- 

### 5. Template SQL 测试报告保存

修改文件：app/evaluation/template_sql_tests.py ，新增 JSON 报告输出。
运行：python -m app.evaluation.template_sql_tests
输出：docs/evaluation/template_sql_tests_YYYYMMDD_HHMMSS.json

报告包含：
- test_suite
- timestamp
- summary
- sections.limit_tests
- sections.routing_tests

当前结果：
- Total: 12
- Passed: 12
- Failed: 0
- Pass Rate: 100%

---

### 6. Query Plan Testing 文档

新增文档：docs/architecture/query_plan_testing_v1.md
文档说明：
为什么需要 Query Plan 测试体系
三层测试职责边界
query_plan_tests.py 检查什么
template_sql_tests.py 检查什么
evaluator.py 检查什么

--- 

## 今日关键收获

1. query_plans.yaml 已经开始参与 SQL 生成

Day38 时：query_plans.yaml 主要是分流依据和设计沉淀
Day39 后：query_plans.yaml 已开始驱动 alias、round、multiply_by_100、default_sort

2. 配置也需要测试

query_plans.yaml 不是普通配置，而是业务口径配置。

例如：
multiply_by_100: false 对于 ROI / CAC 是业务正确性的关键。所以必须用测试保护，而不是靠记忆。

3. 测试分层比单一 evaluator 更可靠

仅有 evaluator 可以验证最终结果，但不容易定位问题。
现在三层测试分别保护：
- 配置是否正确
- 模板是否正确
- 端到端结果是否正确
这更接近真实企业项目的测试方式。

---

## 当前技术债

### 1. Query Plan 参数化仍是 V1

当前已参数化：
- alias
- round
- multiply_by_100
- default_sort.field
- default_sort.direction

尚未参数化：
- date_window
- CTE steps
- join keys
- formula expression
- dimension
- filters


### 2. template_sql_tests 主要是字符串包含检查

当前通过检查 SQL 关键片段判断模板是否正确。
后续可升级为：
- SQL Snapshot
- SQL AST 检查
- 模板 SQL 执行结果校验

### 3. parse_limit 应迁移到 Intent Parser

当前 parse_limit 位于：template_sql_generator.py
后续应迁移到：intent_parser.py
并拆分：
- metric
- dimension
- sort_direction
- limit
- ranking_type

---

## 当前三层测试体系

- 配置层：query_plan_tests.py → 保护 metadata/query_plans.yaml
- 模板层：template_sql_tests.py → 保护 template_sql_generator.py
- 端到端业务层：evaluator.py → 保护 query_service 主链路

当前结果：
- query_plan_tests.py      2/2 PASS
- template_sql_tests.py   12/12 PASS
- evaluator.py            20/20 PASS

---

## 今日最终状态

当前支持复杂模板指标：
- roi
- cac

当前 Query Plan 支持：
- roi_channel_v1
- cac_channel_v1

当前测试结果：
- query_plan_tests.py      2/2 PASS
- template_sql_tests.py   12/12 PASS
- evaluator.py            20/20 PASS

当前报告目录：
docs/evaluation/
├── evaluation_*.json
├── query_plan_tests_*.json
├── template_sql_tests_*.json