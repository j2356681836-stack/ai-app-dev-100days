# Day41 学习日志

## 今日主题

final_sort_direction 设计与实现：用户排序意图与指标默认排序规则融合

---

## 今日目标

Day40 已完成 Intent Parser V1，并将 intent 接入 query_service 主链路。

Day41 的目标是解决 Day40 留下的技术债：
intent.sort_hint
+
query_plan.default_sort.direction
↓
final_sort_direction

也就是让系统明确判断：最终 ORDER BY 应该使用 ASC 还是 DESC？

---

## 今日完成内容

### 1. 新增 resolve_sort_direction

修改文件：app/semantic_layer/intent_parser.py
新增函数：resolve_sort_direction(intent, query_plan)
作用：根据用户问题中的排序提示和 query plan 中的指标默认排序，决定最终排序方向。
规则：用户显式排序方向 > 指标默认排序方向 > None
也就是：

如果 intent.sort_hint 有值：
    使用 intent.sort_hint
否则如果 query_plan 有 default_sort.direction：
    使用 query_plan.default_sort.direction
否则：
    返回 None

示例：
获客成本最低的三个渠道
→ sort_hint = asc
→ final_sort_direction = asc

各渠道ROI排名
→ sort_hint = None
→ ROI 默认 desc
→ final_sort_direction = desc

渠道ROI从低到高排名
→ sort_hint = asc
→ ROI 默认 desc
→ final_sort_direction = asc

---

### 2. 新增 enrich_intent_with_query_plan

修改文件：app/semantic_layer/intent_parser.py
新增函数：enrich_intent_with_query_plan(intent, query_plan)
作用：使用 query plan 补全 intent。
当前补充字段：
{
    "final_sort_direction": "asc" | "desc" | None,
    "sort_field": str | None,
}

示例：
{
    "question": "渠道ROI从低到高排名",
    "limit": None,
    "ranking_type": "ranking",
    "sort_hint": "asc",
    "dimension": "channel",
    "final_sort_direction": "asc",
    "sort_field": "roi",
}

---

### 3. query_service 接入 enriched intent

修改文件：app/text_to_sql/query_service.py
原链路：
question
↓
parse_intent(question)
↓
search_metric(question)
↓
metric_name
↓
generate_template_sql_from_intent(metric_name, intent)

新链路：
question
↓
parse_intent(question)
↓
search_metric(question)
↓
metric_name
↓
get_query_plan_by_metric(metric_name)
↓
enrich_intent_with_query_plan(intent, query_plan)
↓
generate_template_sql_from_intent(metric_name, enriched_intent)

query_service 返回的 intent 现在包含：
{
    "sort_hint": ...,
    "final_sort_direction": ...,
    "sort_field": ...,
}

---

### 4. Template SQL 使用 intent 排序信息

修改文件：app/text_to_sql/template_sql_generator.py
新增函数：build_order_by_clause_from_intent(intent, plan)
作用：优先使用 intent 中的排序信息构建 SQL ORDER BY。
优先级：
intent.sort_field
intent.final_sort_direction
↓
如果缺失，则回退 query_plan.default_sort

示例：
python
intent = {
    "sort_field": "roi",
    "final_sort_direction": "asc",
}

生成：ORDER BY roi ASC

---

### 5. generate_roi_sql / generate_cac_sql 支持 order_by_clause 参数

修改：
generate_roi_sql(question, limit_clause=None, order_by_clause=None)
generate_cac_sql(question, limit_clause=None, order_by_clause=None)

兼容逻辑：
如果外部传入 order_by_clause：
    使用外部传入的 ORDER BY

否则：
    保持旧逻辑，从 query_plan.default_sort 构建 ORDER BY

这样旧入口不被破坏，新入口可以使用 intent 生成排序。

---

### 6. 新增反向排序能力

新增问题能力：渠道ROI从低到高排名
虽然 ROI 默认排序是：DESC；但用户显式表达：从低到高
因此最终排序方向应为：ASC
生成 SQL 中应包含：ORDER BY roi ASC

返回结果顺序：
小红书
抖音
京东
微信小程序
天猫

---

### 7. template_sql_tests 扩展

修改文件：app/evaluation/template_sql_tests.py
新增 intent template 测试 case：渠道ROI从低到高排名 → ORDER BY roi ASC
修复过程：
最初 `template_sql_tests.py` 中该 case 失败，因为测试链路是：
parse_intent
↓
generate_template_sql_from_intent

但真实主链路是：
parse_intent
↓
enrich_intent_with_query_plan
↓
generate_template_sql_from_intent

因此修复测试链路，让 template_sql_tests 模拟完整 intent enrichment。

修复后：
template_sql_tests.py
Total: 15
Passed: 15
Failed: 0

---

### 8. Golden Cases 扩展到 21

修改文件：app/evaluation/golden_questions.py
新增：case_026：渠道ROI从低到高排名
校验内容：
"expected_generation_method": "template",
"expected_intent": {
    "limit": None,
    "ranking_type": "ranking",
    "sort_hint": "asc",
    "dimension": "channel",
    "final_sort_direction": "asc",
    "sort_field": "roi",
},
"expected_order": {
    "field": "channel_name",
    "values": [
        "小红书",
        "抖音",
        "京东",
        "微信小程序",
        "天猫",
    ],
}

Evaluator 结果：
Total: 21
Passed: 21
Failed: 0
Pass Rate: 100%

---

### 9. 新增 Intent Resolver 测试

新增文件：app/evaluation/intent_resolver_tests.py
作用：
    专门验证：
    parse_intent
    +
    query_plan.default_sort
    ↓
    enriched_intent

当前测试覆盖：
各渠道ROI排名
渠道ROI从低到高排名
各渠道获客成本排名
获客成本最低的三个渠道
哪个渠道销售额最高

核心规则：用户显式排序方向 > 指标默认排序方向

测试结果：
Total: 5
Passed: 5
Failed: 0

并输出 JSON 报告：docs/evaluation/intent_resolver_tests_YYYYMMDD_HHMMSS.json

---

### 10. 更新 Query Plan Testing 文档

修改文件：docs/architecture/query_plan_testing_v1.md
将测试体系从原来的三层扩展为五类测试：
query_plan_tests.py
intent_parser_tests.py
intent_resolver_tests.py
template_sql_tests.py
evaluator.py

当前测试职责：
配置层：query_plan_tests.py
基础意图解析层：intent_parser_tests.py
意图融合层：intent_resolver_tests.py
模板 SQL 层：template_sql_tests.py
端到端业务层：evaluator.py

---

## 今日最终测试结果

### Query Plan Tests
query_plan_tests.py
Total: 2
Passed: 2
Failed: 0

### Intent Parser Tests
intent_parser_tests.py
Total: 5
Passed: 5
Failed: 0

### Intent Resolver Tests
intent_resolver_tests.py
Total: 5
Passed: 5
Failed: 0

### Template SQL Tests
template_sql_tests.py
Total: 15
Passed: 15
Failed: 0

### Evaluator
evaluator.py
Total: 21
Passed: 21
Failed: 0
Pass Rate: 100%

---

## 当前系统架构
Question
↓
Intent Parser
↓
Intent Resolver
↓
Metric Recognition / Hybrid Search
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

---

## 当前 Intent 结构

当前 enriched intent 示例：
{
    "question": "渠道ROI从低到高排名",
    "limit": None,
    "ranking_type": "ranking",
    "sort_hint": "asc",
    "dimension": "channel",
    "final_sort_direction": "asc",
    "sort_field": "roi",
}

字段说明：
sort_hint：用户问题中显式表达的排序方向。
default_sort：query_plans.yaml 中定义的指标默认排序规则。
final_sort_direction：系统最终决定使用的排序方向。
sort_field：系统最终排序使用的字段。

---

## 今日关键收获

### 1. sort_hint 和 default_sort 来源不同

sort_hint 来自用户问题。
default_sort 来自 query_plans.yaml。

例如：渠道ROI从低到高排名

用户显式说“从低到高”，所以：
python
sort_hint = "asc"

即使 ROI 默认是：
python
default_sort.direction = "desc"

最终也应该尊重用户显式表达：
python
final_sort_direction = "asc"

---

### 2. resolve_sort_direction 本质是排序决策函数

它解决的问题是：当用户排序意图和指标默认排序规则同时存在时，系统应该听谁的？
当前规则：用户显式排序方向优先。

---

### 3. 测试链路必须跟上主链路

今天 template_sql_tests 一开始失败，原因不是主链路错了，而是测试链路少了：
enrich_intent_with_query_plan

这个问题说明：测试必须模拟真实主链路，否则可能出现测试失败但业务链路正确的情况。

---

### 4. evaluator 已经进入综合评估阶段

当前 evaluator 不只验证 SQL 是否能跑，还验证：
SQL 结构
业务结果
排名顺序
生成方式
intent 解析结果

这比早期只看 SQL 是否执行成功可靠得多。

---

## 当前测试体系
query_plan_tests.py          2/2 PASS
intent_parser_tests.py       5/5 PASS
intent_resolver_tests.py     5/5 PASS
template_sql_tests.py       15/15 PASS
evaluator.py                21/21 PASS

测试报告目录：
docs/evaluation/
├── evaluation_*.json
├── query_plan_tests_*.json
├── template_sql_tests_*.json
├── intent_parser_tests_*.json
├── intent_resolver_tests_*.json

---

## 当前技术债

### 1. 普通指标尚未完全使用 query_plan

普通指标如：
channel_sales_amount
channel_refund_rate

目前仍主要走 LLM SQL，没有 query_plan。

因此：sort_field = None
但普通指标仍可以从用户问题中解析：sort_hint = "desc"
后续如果普通指标也纳入 query_plan，可以进一步统一排序处理。

---

### 2. sort_hint 规则仍较简单

当前支持：
最低 / 最小 / 最少 / 升序 / 从低到高 → asc
最高 / 最大 / 最多 / 降序 / 从高到低 → desc

后续可以支持：
倒数前三
后五名
由高到低
由低到高
最差
最好

---

### 3. template_sql_generator 中仍保留旧 question 解析逻辑

当前为兼容保留：
build_limit_clause(question)
generate_template_sql(metric_name, question)

后续当 intent-based 链路完全稳定后，可以逐步减少旧逻辑。

---

### 4. final_sort_direction 目前主要用于模板指标

ROI / CAC 已使用：
intent.final_sort_direction
intent.sort_field

普通 LLM 指标尚未将 intent 注入 prompt。
后续可让 prompt_builder 使用 intent，减少普通指标 SQL 生成的不稳定。

---
