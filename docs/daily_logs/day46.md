# Day46 学习日志

## 今日主题

Phase2：Business Semantic Layer & Text-to-SQL

Day46：Prompt Builder V2 / 模块化收束

---

## 今日目标

今天的目标不是新增指标，也不是继续扩展 Answer Layer，而是处理 Phase2 当前一个明显技术债：

prompt_builder.py 规则越来越多
↓
build_prompt() 职责过重
↓
Prompt 维护成本升高
↓
后续进入 Phase3 Tool / Agent Workflow 前需要先做结构收束

核心目标：
1. 重构 `prompt_builder.py`，让规则结构更清晰。
2. 扩展 `prompt_builder_tests.py`，增强 Prompt 静态保护。
3. 保持 `evaluator.py` 端到端结果稳定。
4. 记录 Prompt 工程中的回归经验。

---

## 完成内容一：Prompt Builder V2 模块化重构

修改文件： `app/text_to_sql/prompt_builder.py`

原本 `build_prompt()` 中直接维护大量 SQL 生成规则，包括：
- 全局 SQL 规则
- 字段别名规则
- 排序与 TopN 规则
- 分析维度规则
- ROI / CAC 复杂指标规则
- Intent Context 规则

Day46 将 Prompt Builder 拆分为以下函数：

build_prompt()
├─ build_intent_context()
├─ build_global_rules()
├─ build_field_alias_rules()
├─ build_ranking_rules()
├─ build_dimension_rules()
├─ build_legacy_complex_metric_rules()
└─ build_sql_generation_rules()

其中：
- `build_global_rules()`：负责通用 SQL 安全规则
- `build_field_alias_rules()`：负责字段别名和输出字段稳定性
- `build_ranking_rules()`：负责 TopN、Ranking、ASC / DESC、LIMIT
- `build_dimension_rules()`：负责 channel / category 维度规则
- `build_legacy_complex_metric_rules()`：负责 ROI / CAC 历史兼容规则
- `build_sql_generation_rules()`：负责最终汇总输出给 LLM 的 SQL 生成规则

---

## 完成内容二：明确 legacy_complex_metric_rules 命名原因

今天明确：ROI / CAC 规则不应该继续命名为 `metric_rules`。
原因：metric_rules 会让人误以为它适用于所有指标。但当前这组规则只覆盖 ROI / CAC 这类复杂跨事实表指标。

当前复杂指标策略：
- `roi` → Query Plan + Template SQL
- `cac` → Query Plan + Template SQL
- 普通指标 → Intent Context + LLM SQL

因此 Prompt 中保留的 ROI / CAC 规则只是历史兼容保护，不是未来复杂指标的主要实现方式。
所以更准确的命名是：build_legacy_complex_metric_rules()

它表达三层含义：
1. `complex_metric`：只服务 ROI / CAC 这类复杂指标。
2. `legacy`：这是历史遗留 Prompt 保护规则。
3. `rules`：当前暂时保留，避免重构时引入回归风险。

---

## 完成内容三：扩展 prompt_builder_tests

修改文件：`app/evaluation/prompt_builder_tests.py`
测试从原来的 2 个 case 扩展为 5 个 case。

当前覆盖：
1. 渠道销售额 TopN
2. 渠道销售额从低到高排名
3. 品类退款率 Top3
4. 各渠道 ROI 排名
5. 各渠道获客成本排名

覆盖的 Prompt 规则包括：
- `dimension`
- `ranking_type`
- `limit`
- `final_sort_direction`
- `dim_channel.channel_name`
- `dim_product.category`
- `refund_rate_pct`
- `LEFT JOIN`
- `NULLIF`
- `date_window CTE`
- `channel_sales`
- `channel_spend`
- `ROW_NUMBER() OVER`
- `acquired_customer_count`

测试结果：
Prompt Builder Tests
Total: 5
Passed: 5
Failed: 0

---

## 完成内容四：发现 case_030 Prompt 回归

在第一次 Prompt Builder V2 重构后，`prompt_builder_tests.py` 通过，但 `evaluator.py` 中 `case_030` 出现回归。

失败 case：case_030：品类退款率从低到高排名

预期结果：
面霜 4.37
洁面 4.47
面膜 4.48
防晒 4.55
精华 10.0

实际结果：
防晒 0.0
面霜 0.0
洁面 0.0
面膜 0.0
精华 0.0

定位 SQL 后发现，LLM 自行添加了错误过滤条件：
```sql
AND r.refund_status = 'paid'
```

这导致退款金额聚合为空，最终所有品类退款率都变成 0。

---

## 完成内容五：修复“不编造状态值 / 枚举值”问题

问题本质：LLM 没有编造字段，但编造了字段取值。

之前 Prompt 只强调：不要编造字段。
但没有明确要求：不要编造状态值或枚举值。

因此 Day46 补充了新的全局规则。

新增 / 修改规则：
1. 不要编造字段、表名、状态值或枚举值。不得自行假设 order_status、refund_status、channel_name、category 等字段的取值。
2. 必须使用指标中的 filters 作为 WHERE 条件。只能使用业务上下文中明确给出的 filters，不要自行新增 status 过滤条件。


同步修改位置：
- `build_global_rules()`
- `build_sql_generation_rules()`

同步修改原因：
当前 `build_prompt()` 实际使用 `build_sql_generation_rules()`，但 `build_global_rules()` 仍然是 Prompt Builder V2 模块化结构的一部分。为了避免后续维护时两边规则不一致，需要同步更新。

---

## 完成内容六：确定 Prompt Builder V2 的正确策略

第一次重构时，Prompt 输出结构变为多个分组：

全局 SQL 规则：
字段别名规则：
排序与返回行数规则：
分析维度规则：
复杂指标历史兼容规则：

这对人类更清晰，但改变了 LLM 看到的 Prompt 表层结构，导致 SQL 生成出现波动。
最终策略调整为：代码内部模块化；最终 Prompt 输出形态尽量保持 V1 的连续规则结构。


也就是：
对开发者：结构更清晰，便于维护。
对 LLM：输入形态更稳定，降低回归风险。

这是 Day46 最重要的工程经验。

---

## 完成内容七：更新架构文档

更新文件： `docs/architecture/prompt_builder_v2.md`

新增重点内容：
- Prompt Builder V2 背景
- 函数结构说明
- Prompt / Intent / Query Plan / Template SQL / Answer Layer 的边界
- 为什么不能继续堆 Prompt 规则
- Day46 回归发现：Prompt 输出形态也是行为的一部分
- `case_030` 回归原因
- “不编造状态值 / 枚举值”规则
- Prompt Builder V2 最终策略：内部模块化，外部输出稳定

---

## 今日最终测试结果

### prompt_builder_tests

Total: 5
Passed: 5
Failed: 0

### evaluator

Total: 26
Passed: 26
Failed: 0
Pass Rate: 100.0%

### answer_judge mock

Mode: mock
Total: 6
Passed: 6
Failed: 0
Pass Rate: 100.0%

---

## 今日关键理解

### 1. Prompt 重构不是普通字符串重构

在传统 Python 代码中，重构通常意味着：
结构更清晰
测试通过
行为不变

但在 LLM 应用中，Prompt 的文本结构本身就是行为的一部分。

Prompt 的以下变化都可能影响 LLM 输出：
- 标题
- 分组
- 编号方式
- 规则顺序
- 规则距离用户问题的远近
- 规则表达方式

因此 Prompt Builder 重构必须同时考虑：

代码可维护性
+
LLM 输入稳定性

---

### 2. prompt_builder_tests 和 evaluator 分工不同

`prompt_builder_tests.py` 是 Prompt 静态检查。它检查：Prompt 中是否包含关键约束。
但它不调用 LLM，也不执行 SQL，因此无法发现 LLM 是否真正遵守了这些约束。

`evaluator.py` 是端到端结果检查。它检查：question → intent → SQL → execution → table → answer → evaluation

因此能发现：
- SQL 能执行但结果错了
- 排名顺序错了
- 多行结果值错了
- answer 关键事实点缺失

这次 `case_030` 就说明：prompt_builder_tests 通过，只能说明规则还在；evaluator 通过，才能说明最终业务结果稳定。

---

### 3. 字段值也不能让 LLM 编造

今天发现的问题不是编造字段，而是编造字段取值。

例如：
```sql
AND r.refund_status = 'paid'
```
字段 `refund_status` 可能存在，但 `'paid'` 这个取值没有来自业务上下文或 metric filters。

因此 Text-to-SQL Prompt 中需要明确限制：不得自行假设字段取值、状态值或枚举值。
这是比“不要编造字段”更细的一层安全约束。

---

## 当前技术债

1. `build_global_rules()` 和 `build_sql_generation_rules()` 之间仍存在部分规则重复维护。
2. 当前为了保持 LLM 输入稳定，`build_sql_generation_rules()` 仍输出接近 V1 的连续规则列表。
3. `prompt_builder_tests.py` 已扩展到 5 个 case，但还可以补充“不编造枚举值 / 状态值”的专项断言。
4. ROI / CAC legacy rules 仍保留在 Prompt 中，后续可继续下沉到 Query Plan / Template SQL。
5. 普通指标仍缺少 query_plan，TopN 默认排序方向仍部分依赖 LLM 语义理解。
6. Prompt Builder V2 当前主要完成结构收束，还没有进一步抽象为可配置规则系统。

---

## 今日状态

Day46 已完成。

当前系统状态：

Question
↓
Intent Parser
↓
Intent Resolver
↓
Hybrid Search / Metric Recognition
↓
Query Plan Routing
↓
Template SQL / LLM SQL with Intent Context
↓
Prompt Builder V2
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
Deterministic Evaluator
↓
LLM-as-Judge Answer Evaluation

Day46 的核心成果：Prompt Builder V2 不是让 Prompt 更复杂，而是在保持 LLM 输入稳定性的前提下，让 Prompt 规则结构更可维护、更可控。
