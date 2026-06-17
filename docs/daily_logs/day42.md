# Day42 学习日志

## 今日主题

普通指标 Prompt 接入 Intent Context

---

## 今日目标

Day38-Day41 已完成：ROI / CAC → Intent + Query Plan + Template SQL

但普通指标仍然是：普通指标 → LLM SQL

Day42 的目标是让普通指标虽然继续走 LLM，但 LLM 生成 SQL 时可以使用结构化 intent。

目标链路：
普通指标
↓
Intent Parser
↓
Intent Resolver
↓
Prompt Builder with Intent Context
↓
LLM SQL

---

## 今日完成内容

### 1. 验证普通指标当前链路

验证问题：
哪个渠道销售额最高
渠道销售额从低到高排名

验证结果：
generation_method = llm
intent 已返回
SQL 正常执行

其中：
哪个渠道销售额最高
→ 天猫
→ channel_sales_amount = 2445170.92
→ ORDER BY channel_sales_amount DESC
→ LIMIT 1

渠道销售额从低到高排名
→ 微信小程序、小红书、京东、抖音、天猫
→ ORDER BY channel_sales_amount ASC
说明普通指标当前仍走 LLM，但 query_service 已经返回 enriched intent。

---

### 2. prompt_builder 支持 intent 参数

修改文件：app/text_to_sql/prompt_builder.py
将：
```python
def build_prompt(user_question: str) -> str:
```

改为：
```python
def build_prompt(user_question: str, intent: dict | None = None) -> str:
```

新增：
```python
build_intent_context(intent)
```
用于将结构化 intent 转换为 Prompt 可读文本。

当前注入 Prompt 的字段：
dimension
ranking_type
limit
sort_hint
final_sort_direction
sort_field

---

### 3. Prompt 增加结构化意图上下文

Prompt 中新增：
结构化意图上下文：
- 分析维度 dimension
- 排名类型 ranking_type
- 返回行数 limit
- 用户排序提示 sort_hint
- 最终排序方向 final_sort_direction
- 排序字段 sort_field
```

作用：让普通指标 LLM 路径不再完全依赖自然语言猜测，而是能看到结构化意图。

---

### 4. Prompt 增加 Intent 使用规则

在 Prompt 规则中新增：
如果提供了结构化意图上下文，必须优先遵守其中的 dimension、ranking_type、limit、final_sort_direction。
如果 final_sort_direction = "asc"，排序必须使用 ASC。
如果 final_sort_direction = "desc"，排序必须使用 DESC。
如果 limit 为数字，SQL 必须添加对应 LIMIT。
如果 dimension = "channel"，分析维度必须使用 dim_channel.channel_name，输出字段别名必须是 channel_name，禁止使用 channel 作为字段别名。
如果 dimension = "category"，分析维度必须使用 dim_product.category，输出字段别名必须是 category。
如果 ranking_type = "ranking"，返回完整排名，不要添加 LIMIT，除非 limit 明确为数字。


---

### 5. sql_generator 支持 intent 参数

修改文件：app/text_to_sql/sql_generator.py
将：
```python
def generate_sql(question: str) -> str:
    prompt = build_prompt(question)
```
改为：
```python
def generate_sql(question: str, intent: dict | None = None) -> str:
    prompt = build_prompt(question, intent=intent)
```

---

### 6. query_service 在 LLM 路径传入 intent

修改文件：app/text_to_sql/query_service.py

原逻辑：raw_sql = generate_sql(question)
新逻辑：raw_sql = generate_sql(question, intent=intent)

现在普通指标链路变为：
question
↓
parse_intent
↓
enrich_intent_with_query_plan
↓
generate_sql(question, intent=intent)
↓
build_prompt(question, intent=intent)
↓
LLM SQL

---

## 今日遇到的问题

### 问题 1：case_018 字段别名漂移

修改 Prompt 后，evaluator 中：case_018：哪个渠道销售额最高 一度失败。
失败原因：LLM 生成 SQL：dc.channel_name AS channel，但 evaluator 期望字段为：channel_name
因此：expected channel_name = 天猫，actual channel_name = None
本质问题：Intent 中 dimension = channel被 LLM 误理解成输出字段别名 channel。
解决方式：在 Prompt 中明确：如果 dimension = "channel"，分析维度必须使用 dim_channel。channel_name，输出字段别名必须是 channel_name，禁止使用 channel 作为字段别名。

修复后 evaluator 恢复通过。

---

### 问题 2：Prompt 规则开始臃肿

当前 prompt_builder.py 中规则数量接近 30 条。

讨论结论：短期可接受，因为当前处于功能接入阶段。中期需要做 Prompt Builder 模块化，避免 Prompt 变成“规则垃圾桶”。
后续可拆分为：
global_rules
intent_rules
dimension_rules
metric_specific_rules
legacy_complex_metric_rules

长期方向：复杂业务规则应迁移到 Query Plan / Template / Metadata / Intent Resolver。Prompt 只保留通用 SQL 约束和当前任务相关规则


---

## 今日新增 Golden Cases

### case_027：渠道销售额从低到高排名

目的：验证普通指标 LLM 路径能使用：intent.final_sort_direction = asc
当前配置：

```python
"expected_generation_method": "llm",
"expected_intent": {
    "limit": None,
    "ranking_type": "ranking",
    "sort_hint": "asc",
    "dimension": "channel",
    "final_sort_direction": "asc",
    "sort_field": None,
},
"expected_order": {
    "field": "channel_name",
    "values": [
        "微信小程序",
        "小红书",
        "京东",
        "抖音",
        "天猫",
    ],
}
```

结果：PASSED

---

### case_028：渠道销售额Top3

目的：验证普通指标 LLM 路径能使用：intent.limit = 3，ranking_type = topn


当前配置：
```python
"expected_generation_method": "llm",
"expected_intent": {
    "limit": 3,
    "ranking_type": "topn",
    "sort_hint": None,
    "dimension": "channel",
    "final_sort_direction": None,
    "sort_field": None,
},
"expected_order": {
    "field": "channel_name",
    "values": [
        "天猫",
        "抖音",
        "京东",
    ],
}
```

结果：PASSED


---

## 今日新增测试

### prompt_builder_tests.py

新增文件：app/evaluation/prompt_builder_tests.py
作用：保护 Day42 的核心改动：build_prompt(question, intent)
确实将 intent context 注入 Prompt。

当前测试用例：
- 渠道销售额Top3
- 渠道销售额从低到高排名

当前校验内容：
结构化意图上下文
dimension: channel
ranking_type: topn
limit: 3
final_sort_direction: asc

测试结果：
Total: 2
Passed: 2
Failed: 0

输出报告：docs/evaluation/prompt_builder_tests_YYYYMMDD_HHMMSS.json

---

## 今日最终测试结果

query_plan_tests.py          2/2 PASS
intent_parser_tests.py       5/5 PASS
intent_resolver_tests.py     5/5 PASS
template_sql_tests.py       15/15 PASS
prompt_builder_tests.py      2/2 PASS
evaluator.py                23/23 PASS

Golden Cases：
21 Cases
↓
23 Cases

Pass Rate：
100%

---

## 当前系统架构

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
└─ 普通指标 → LLM SQL with Intent Context
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

## 当前两条 SQL 生成路径

### 复杂指标路径

ROI / CAC
↓
Intent
↓
Query Plan
↓
Template SQL


特点：
高风险复杂指标
跨事实表
业务口径强
不依赖 LLM 自由生成 SQL


---

### 普通指标路径

普通指标
↓
Intent
↓
Prompt Builder
↓
LLM SQL


特点：
SQL 相对简单
继续保留 LLM 灵活性
通过 Intent Context 约束维度、排序、TopN、LIMIT


---

## 今日关键收获

### 1. Intent 不等于 Template

普通指标不走 template，但仍然需要 intent。
原因：
Intent 负责理解用户问题
Template / LLM 负责生成 SQL
所以：
ROI / CAC → Intent + Query Plan + Template
普通指标 → Intent + Prompt + LLM

---

### 2. Intent Context 可以约束普通指标 LLM

对于：渠道销售额从低到高排名

Prompt 中明确提供：
dimension = channel
ranking_type = ranking
final_sort_direction = asc

可以帮助 LLM 生成：ORDER BY channel_sales_amount ASC

---

### 3. Prompt 接入 Intent 后要防止字段别名漂移

结构化 intent 中的枚举值：dimension = channel
不等于 SQL 输出别名：channel
必须明确映射：
dimension = channel
→ dim_channel.channel_name
→ alias = channel_name

---

### 4. Prompt 已经需要模块化

当前 prompt_builder.py 规则数量较多，后续不应继续无脑追加。

应逐步演进为：
build_role_section
build_context_section
build_intent_section
build_global_rules
build_dimension_rules
build_metric_rules
build_output_rules

---

## 当前技术债

### 1. Prompt Builder 规则臃肿

当前 Prompt 规则数量接近 30 条。
后续应做 Prompt Builder V2，将规则模块化。

---

### 2. 普通指标没有 query_plan

普通指标当前：sort_field = None

但仍能通过 Prompt 使用：
dimension
ranking_type
limit
final_sort_direction

后续可评估是否为部分普通指标建立轻量 query_plan。

---

### 3. TopN 默认排序方向仍不完全结构化

例如：渠道销售额Top3

当前 `sort_hint = None`，`final_sort_direction = None`。
LLM 仍能正确理解 Top3 通常是 DESC。
后续可以在 Intent Resolver 中考虑：
ranking_type = topn
+
metric/default sort 缺失
→ 是否默认 desc

但当前先不急于加规则，避免过度假设。

---

### 4. prompt_builder_tests 当前只检查 Prompt 片段

当前测试只验证 Prompt 是否包含 intent context。
后续可以扩展：
检查 dimension 映射规则
检查字段别名规则
检查 limit / ranking rules

