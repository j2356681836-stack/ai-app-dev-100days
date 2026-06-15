# Day40 学习日志

## 今日主题

Intent Parser V1 设计、测试、模板接入与 query_service 主链路接入

---

## 今日目标

Day38-Day39 已经完成：

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

但此前 `limit`、`TopN`、`Ranking` 等用户意图解析逻辑仍然主要位于：app/text_to_sql/template_sql_generator.py 。这不符合职责划分。
Day40 的目标是新增 Intent Parser V1，将用户问题中的结构化意图从 SQL 模板层中逐步抽离出来。

---

## 今日完成内容

### 1. 新增 Intent Parser V1

新增文件：app/semantic_layer/intent_parser.py

当前支持解析字段：
{
    "question": question,
    "limit": int | None,
    "ranking_type": "top1" | "topn" | "ranking" | "unknown",
    "sort_hint": "asc" | "desc" | None,
    "dimension": "channel" | "category" | None,
}

---

### 2. parse_limit

实现：
用户问题
↓
解析 LIMIT

当前支持：
哪个渠道ROI最高 → limit = 1
各渠道ROI排名 → limit = None
渠道ROI Top3 → limit = 3
渠道ROI前3 → limit = 3
获客成本最低的三个渠道 → limit = 3
获客成本最低的3个渠道 → limit = 3
获客成本前五渠道 → limit = 5

关键规则：明确数量优先于极值表达。

例如：获客成本最低的三个渠道

应解析为：
limit = 3
ranking_type = "topn"


而不是误判为：
limit = 1
ranking_type = "top1"

---

### 3. parse_sort_hint

实现：
    用户问题
    ↓
    解析用户显式表达的排序方向

当前支持：
最低 / 最小 / 最少 / 升序 / 从低到高 → asc
最高 / 最大 / 最多 / 降序 / 从高到低 → desc

注意：
sort_hint 只是用户显式表达的排序提示，不一定是最终排序方向。
最终排序方向还需要结合 metric 或 query_plan。

例如：获客成本前五渠道
当前解析为：
python
{
    "limit": 5,
    "sort_hint": None,
}

这是合理的，因为“前五”只表达数量，没有明确表达升序或降序。未来可结合 `cac` 的默认排序方向 `asc` 得出最终排序。

---

### 4. parse_dimension

实现：
渠道 → channel
品类 / 类目 → category

示例：
各渠道ROI排名 → dimension = channel
各品类退款率排名 → dimension = category

---

### 5. parse_ranking_type

实现：
limit == 1 → top1
limit > 1 → topn
包含 排名 / 排行 / 排序 / 各 → ranking
其他 → unknown

示例：
哪个渠道ROI最高 → top1
渠道ROI Top3 → topn
各渠道ROI排名 → ranking

---

## 今日 Python 学习点

### 1. 字典取值

错误写法：CHINESE_NUMBER_MAP("三")
正确写法：CHINESE_NUMBER_MAP["三"]
原因：CHINESE_NUMBER_MAP 是 dict，不是函数。

---

### 2. None 与数字比较

错误写法：
if limit > 1:
    return "topn"

当 `limit = None` 时会报错。

正确写法：
if limit is not None and limit > 1:
    return "topn"


---

### 3. 正则表达式中 [] 和 () 的区别

错误理解：r"[个|名|家|渠道|品类]"
这不是“多个词选一个”，而是“匹配任意一个字符”。

推荐写法：r"(个|名|家|渠道|品类)"
或者对于简单关键词判断，直接使用：
if "渠道" in question:
    return "channel"

---

## 6. 新增 Intent Parser 测试

新增文件：app/evaluation/intent_parser_tests.py

测试内容：
- limit
- ranking_type
- sort_hint
- dimension

当前测试用例：
哪个渠道ROI最高
各渠道ROI排名
渠道ROI Top3
获客成本最低的三个渠道
各品类退款率排名


当前结果：
Total: 5
Passed: 5
Failed: 0

---

## 7. Intent Parser 测试报告

`intent_parser_tests.py` 支持 JSON 报告输出。

运行：python -m app.evaluation.intent_parser_tests
输出：docs/evaluation/intent_parser_tests_YYYYMMDD_HHMMSS.json

报告内容包括：

json
{
  "test_suite": "intent_parser_tests",
  "timestamp": "...",
  "summary": {
    "total": 5,
    "passed": 5,
    "failed": 0,
    "pass_rate": 100.0
  },
  "results": []
}

---

## 8. template_sql_generator 接入 Intent 入口

修改文件：app/text_to_sql/template_sql_generator.py
新增：
    build_limit_clause_from_intent(intent)
    generate_roi_sql_from_intent(intent)
    generate_cac_sql_from_intent(intent)
    generate_template_sql_from_intent(metric_name, intent)


当前支持新链路：
    intent
    ↓
    generate_template_sql_from_intent
    ↓
    ROI / CAC Template SQL

---

## 9. Intent LIMIT 接入模板 SQL

原链路：
    question
    ↓
    build_limit_clause(question)
    ↓
    SQL LIMIT


新增链路：
    intent["limit"]
    ↓
    build_limit_clause_from_intent(intent)
    ↓
    SQL LIMIT

当前采用兼容式重构：
generate_roi_sql(question, limit_clause=None)
generate_cac_sql(question, limit_clause=None)

如果传入 `limit_clause`，优先使用 intent 生成的 LIMIT。
如果没有传入，则保持旧的 question 解析逻辑。
这样可以保证旧链路不被破坏。

---

## 10. template_sql_tests 扩展

修改文件：app/evaluation/template_sql_tests.py
新增：Template From Intent Tests
新增测试链路：
question
↓
parse_intent(question)
↓
generate_template_sql_from_intent(metric_name, intent)
↓
检查 SQL 关键片段

测试用例：
渠道ROI Top3
获客成本最低的三个渠道

当前结果：
Total: 14
Passed: 14
Failed: 0

并且 JSON 报告已更新，包含三段：
limit_tests
routing_tests
intent_template_tests


---

## 11. query_service 接入 Intent

修改文件：app/text_to_sql/query_service.py

接入：
parse_intent(question)
generate_template_sql_from_intent(metric_name, intent)


当前主链路变为：

question
↓
parse_intent(question)
↓
search_metric(question)
↓
metric_name
↓
generate_template_sql_from_intent(metric_name, intent)
├─ roi / cac → template
└─ 普通指标 → llm
↓
clean_sql
↓
validate_sql
↓
run_sql
↓
format_result

query_service 返回结果中新增："intent": intent

用于调试和评估。

---

## 12. evaluator 增加 expected_intent 校验

修改文件：app/evaluation/evaluator.py
新增：check_expected_intent

Golden Cases 中新增：expected_intent
用于验证 query_service 返回的 intent 是否符合预期。

当前 evaluator 已支持：
- expected_tables
- expected_columns
- expected_result
- expected_order
- expected_generation_method
- expected_intent

---

## 今日最终测试结果

### Intent Parser Tests

intent_parser_tests.py
Total: 5
Passed: 5
Failed: 0


### Template SQL Tests

template_sql_tests.py
Total: 14
Passed: 14
Failed: 0


### Evaluator

evaluator.py
Total: 20
Passed: 20
Failed: 0
Pass Rate: 100%

---

## 当前系统架构

Question
↓
Intent Parser
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

## 今日关键收获

### 1. Intent Parser 是语义层能力

`limit`、`ranking_type`、`dimension`、`sort_hint` 不属于 SQL 模板层，而属于用户意图理解层。

因此它应该位于：app/semantic_layer/intent_parser.py
而不是长期停留在：app/text_to_sql/template_sql_generator.py

---

### 2. 安全重构要保留旧入口

今天没有直接删除旧的：generate_template_sql(metric_name, question)
而是新增：generate_template_sql_from_intent(metric_name, intent)

这样可以在不破坏旧链路的情况下逐步迁移。

---

### 3. Intent 让问题定位更清晰

当 SQL 结果错误时，现在可以拆分排查：
1. intent 是否解析错
2. metric 是否识别错
3. template 是否生成错
4. SQL 是否执行错
5. result 是否格式化错

这比只看最终 SQL 更容易定位问题。

---

## 当前技术债

### 1. parse_limit 仍存在重复

目前：
    intent_parser.py 有 parse_limit
    template_sql_generator.py 里仍保留旧 parse_limit / build_limit_clause
这是为了兼容旧链路。
后续可以在主链路完全稳定后，逐步移除 template_sql_generator 中的 question 解析逻辑。

---

### 2. sort_hint 尚未参与最终排序决策

当前：intent.sort_hint
已经被解析和返回，但 ROI / CAC 的最终排序仍主要来自 query_plan。

后续应明确：
final_sort_direction = intent.sort_hint or query_plan.default_sort.direction


---

### 3. Intent Parser V1 仍是规则型

当前解析依赖关键词和正则表达式。

后续可逐步增强：
- 支持更多中文数量表达
- 支持“倒数前三”
- 支持“从高到低”
- 支持“不要排序，只看明细”
- 支持更多维度，如会员等级、城市等级、时间周期

---

### 4. expected_intent 只覆盖部分 Golden Cases

当前只给关键 ROI / CAC / Ranking cases 增加了 expected_intent。
后续可逐步扩展到更多 cases。

---

## 明日建议

Day41 

主题：Intent Parser V2：final_sort_direction 与 query_plan.default_sort 融合


目标：
intent.sort_hint
+
query_plan.default_sort.direction
↓
final_sort_direction


这样系统可以处理：
    获客成本最低的三个渠道 → asc
    渠道ROI最高 → desc
    各渠道ROI排名 → query_plan 默认 desc
并为未来支持用户显式排序方向打基础。