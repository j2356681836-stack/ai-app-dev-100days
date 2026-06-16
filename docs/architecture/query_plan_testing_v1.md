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

## 当前测试体系更新：Day41

Day41 新增了 Intent Resolver 能力，因此测试体系从原来的三层扩展为五类测试。

当前测试文件：
app/evaluation/query_plan_tests.py
app/evaluation/intent_parser_tests.py
app/evaluation/intent_resolver_tests.py
app/evaluation/template_sql_tests.py
app/evaluation/evaluator.py

---

## 五类测试职责

| 测试文件 | 层级 | 主要保护对象 |
|---|---|---|
| query_plan_tests.py | 配置层 | metadata/query_plans.yaml |
| intent_parser_tests.py | 基础意图解析层 | parse_intent |
| intent_resolver_tests.py | 意图融合层 | enrich_intent_with_query_plan |
| template_sql_tests.py | 模板 SQL 层 | template_sql_generator |
| evaluator.py | 端到端业务层 | query_service 主链路 |

---

## 1. query_plan_tests.py

作用：验证 `metadata/query_plans.yaml` 的结构、默认排序、业务规则和模板实现一致性。
当前保护：
- Query Plan 必填字段
- output.formula.alias
- output.formula.round
- output.formula.multiply_by_100
- default_sort.field
- default_sort.direction
- ROI 不乘以 100
- CAC 不乘以 100
- ROI 默认 desc
- CAC 默认 asc
- query_plan 中声明的 metric 必须有模板实现

当前结果：2/2 PASS

---

## 2. intent_parser_tests.py

作用：验证用户自然语言问题能否被解析为基础 intent。

当前保护：
- limit
- ranking_type
- sort_hint
- dimension

示例：

哪个渠道ROI最高
→ limit = 1
→ ranking_type = top1
→ sort_hint = desc
→ dimension = channel

各渠道ROI排名
→ limit = None
→ ranking_type = ranking
→ sort_hint = None
→ dimension = channel

当前结果：5/5 PASS

---

## 3. intent_resolver_tests.py

作用：验证基础 intent 与 query_plan 默认规则融合后的 enriched intent 是否正确。

当前保护：
intent.sort_hint
+
query_plan.default_sort.direction
↓
intent.final_sort_direction

核心规则：

用户显式排序方向 > 指标默认排序方向

示例：

各渠道ROI排名
→ sort_hint = None
→ query_plan.default_sort.direction = desc
→ final_sort_direction = desc

渠道ROI从低到高排名
→ sort_hint = asc
→ query_plan.default_sort.direction = desc
→ final_sort_direction = asc

各渠道获客成本排名
→ sort_hint = None
→ query_plan.default_sort.direction = asc
→ final_sort_direction = asc

当前结果：5/5 PASS

---

## 4. template_sql_tests.py

作用：验证 Template SQL Generator 是否能根据 query plan 和 intent 生成正确 SQL。

当前保护：
- parse_limit 兼容旧链路
- generate_template_sql 普通模板路由
- generate_template_sql_from_intent 新链路
- intent.limit → SQL LIMIT
- intent.final_sort_direction → SQL ORDER BY

新增 Day41 覆盖：渠道ROI从低到高排名 → ORDER BY roi ASC

当前结果：15/15 PASS

---

## 5. evaluator.py

作用：验证端到端业务主链路。

当前主链路：
Question
↓
Intent Parser
↓
Intent Resolver
↓
Hybrid Search / Metric Recognition
↓
Query Plan Routing
├─ ROI / CAC → Template SQL from Intent
└─ 普通指标 → LLM SQL
↓
SQL Cleaner
↓
SQL Validator
↓
PostgreSQL
↓
Result Formatter
↓
Evaluator

当前支持校验：
- expected_tables
- expected_columns
- expected_result
- expected_order
- expected_generation_method
- expected_intent

新增 Day41 Golden Case：case_026：渠道ROI从低到高排名

验证：
generation_method = template
final_sort_direction = asc
sort_field = roi
排序顺序 = 小红书、抖音、京东、微信小程序、天猫

当前结果：21/21 PASS

---

## Day41 当前完整回归结果

query_plan_tests.py          2/2 PASS
intent_parser_tests.py       5/5 PASS
intent_resolver_tests.py     5/5 PASS
template_sql_tests.py       15/15 PASS
evaluator.py                21/21 PASS

---

## 当前测试体系价值

现在测试体系可以分别定位问题来源：

配置错误 → query_plan_tests.py
基础意图解析错误 → intent_parser_tests.py
意图与指标默认规则融合错误 → intent_resolver_tests.py
模板 SQL 生成错误 → template_sql_tests.py
端到端业务结果错误 → evaluator.py

这比单独依赖 evaluator 更容易定位问题。

---

## 后续演进方向

### 1. Intent Parser V2

增强自然语言理解能力：
- 倒数前三
- 从高到低
- 从低到高
- 不排序
- 时间范围
- 地区 / 会员等级 / 城市等级

---

### 2. Intent Resolver V2

支持更复杂的排序决策：

用户显式排序
业务指标默认排序
特殊风险指标排序
多字段排序

---

### 3. Template SQL Tests V2

当前主要检查 SQL 字符串片段，后续可升级为：
- SQL Snapshot
- SQL 执行结果校验
- 多行 expected_rows 校验


---

## 写完文档后运行五层测试

`python -m app.evaluation.query_plan_tests`
`python -m app.evaluation.intent_parser_tests`
`python -m app.evaluation.intent_resolver_tests`
`python -m app.evaluation.template_sql_tests`
`python -m app.evaluation.evaluator`
