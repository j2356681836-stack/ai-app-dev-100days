# Prompt Builder V2 设计说明

## 背景

在 Phase2 的 Text-to-SQL 系统中，`prompt_builder.py` 负责把用户问题、业务上下文和结构化意图拼接成最终 SQL 生成 Prompt。

在 Day45 之前，`build_prompt()` 中直接维护了大量 SQL 生成规则，包括：
- 全局 SQL 规则
- 字段别名规则
- 排序和 TopN 规则
- 分析维度规则
- ROI / CAC 复杂指标规则
- Intent Context 约束规则

这种写法短期能工作，但长期存在明显问题：
1. `build_prompt()` 职责过重。
2. 新增规则只能继续往一个大字符串中堆。
3. 不同类型的规则边界不清晰。
4. ROI / CAC 已经迁移到 Template SQL，但 Prompt 中仍残留复杂指标规则。
5. 后续进入 Phase3 Tool / Agent Workflow 前，Prompt Builder 需要先完成结构收束。

因此 Day46 对 Prompt Builder 进行了 V2 模块化重构。

---

## 重构目标

Prompt Builder V2 的目标不是改变 SQL 生成行为，而是完成结构性重构。

本次重构遵守以下原则：
1. 不改变 `build_prompt()` 的函数签名。
2. 不改变 `query_service.py` 的调用方式。
3. 不改变 `sql_generator.py` 的调用方式。
4. 不删除 ROI / CAC legacy rules。
5. 不新增新的业务规则。
6. 保持 evaluator 100% PASS。
7. 提升 Prompt Builder 的可读性和可维护性。

---

## 当前函数结构

重构后，`prompt_builder.py` 的核心结构为：

build_prompt()
├─ build_intent_context()
├─ build_sql_generation_rules()
│  ├─ build_global_rules()
│  ├─ build_field_alias_rules()
│  ├─ build_ranking_rules()
│  ├─ build_dimension_rules()
│  └─ build_legacy_complex_metric_rules()

---

## 各模块职责

### build_intent_context

负责把结构化 intent 转换为 Prompt 中可读的文本。

包含字段：
- `dimension`
- `ranking_type`
- `limit`
- `sort_hint`
- `final_sort_direction`
- `sort_field`

它的作用是把 Intent Parser / Intent Resolver 的结果显式交给 LLM，减少 LLM 对用户问题的自由猜测。

---

### build_global_rules

负责所有 SQL 都应该遵守的基础规则。

包括：
- 使用提供的业务定义
- 使用提供的表
- 不编造字段
- 只返回 SQL
- 使用 filters 作为 WHERE 条件
- 必要时 JOIN 包含 filter 字段的表
- 聚合除法使用 `NULLIF`
- 可选事实表使用 `LEFT JOIN`
- 英文字段别名
- 多事实表先聚合再 JOIN，避免多对多行膨胀

这些规则属于通用 SQL 生成安全约束。

---

### build_field_alias_rules

负责字段别名与输出字段命名稳定性。

包括：
- 指标字段别名优先使用指标技术名
- 百分比类指标使用 `_pct` 后缀
- `refund_rate` 输出为 `refund_rate_pct`
- `channel_refund_rate` 输出为 `channel_refund_rate_pct`
- ROI 不是百分比，不乘以 100
- `dim_channel.channel_name` 必须输出为 `channel_name`
- `dim_product.category` 必须输出为 `category`

这些规则服务于 evaluator、Answer Layer 和前端展示稳定性。

---

### build_ranking_rules

负责排序、TopN、Ranking 和 limit 相关规则。

包括：
- 最高 / 最低 / 最多 / 最少 / 第一 等极值问题必须 `ORDER BY` 并 `LIMIT 1`
- 如果提供结构化意图，优先遵守 `dimension`、`ranking_type`、`limit`、`final_sort_direction`
- `final_sort_direction = asc` 时使用 `ASC`
- `final_sort_direction = desc` 时使用 `DESC`
- `limit` 为数字时添加对应 `LIMIT`
- `ranking_type = ranking` 时返回完整排名，不添加 LIMIT，除非 limit 明确为数字

注意：当前普通指标没有 query_plan，因此部分 TopN 默认排序方向仍依赖 LLM 对业务语义的理解。后续如果给普通指标补充 query_plan，可进一步减少这类不确定性。

---

### build_dimension_rules

负责分析维度相关规则。

包括：
- 商品相关指标默认使用 `dim_product.category`
- `dimension = channel` 时使用 `dim_channel.channel_name`
- `dimension = channel` 时输出字段别名为 `channel_name`
- `dimension = category` 时使用 `dim_product.category`
- `dimension = category` 时输出字段别名为 `category`

这些规则保证 LLM 不会随意选择 `product_name`、`channel` 等不稳定或不符合当前评估体系的字段。

---

### build_legacy_complex_metric_rules

负责 ROI / CAC 历史兼容规则。

ROI / CAC 当前主路径已经是：Query Plan + Template SQL
因此这些规则不再是未来复杂指标的主要实现方式，而是保留在 Prompt 中作为历史兼容保护。

包括：
- ROI 需要先分别聚合销售额和营销成本，再计算 `sales_amount / spend_amount`
- ROI 未指定日期时使用订单和营销消耗的重叠时间窗口
- CAC 使用真实首单新客口径
- CAC 未指定日期时使用订单和营销消耗的重叠时间窗口
- ROI CTE 结构必须使用 `channel_sales` 和 `channel_spend`

命名为 `legacy_complex_metric_rules` 的原因：
1. 它只覆盖 ROI / CAC 两类复杂指标，不是所有指标的通用规则。
2. ROI / CAC 已经迁移到 Query Plan + Template SQL。
3. Prompt 中保留这些规则只是为了降低回归风险。
4. 后续不应继续把复杂指标逻辑堆到 Prompt 中。

---

## Prompt、Intent、Query Plan、Template SQL 的边界

### Intent Parser

负责理解用户问题中的结构化信息。

例如：
- 分析维度：渠道 / 品类
- 排名类型：TopN / Ranking / Top1
- 返回行数：Top3 / Top5
- 排序提示：从低到高 / 从高到低

Intent Parser 不负责生成 SQL。

---

### Query Plan

负责描述复杂指标应该怎么查。

例如：
- ROI 的分子是什么
- ROI 的分母是什么
- 需要哪些事实表
- 默认按什么字段排序
- 复杂指标应该走 Template SQL 还是 LLM SQL

Query Plan 不负责生成自然语言回答。

---

### Template SQL

负责复杂指标的确定性 SQL 生成。

当前主要用于：
- `roi`
- `cac`

这类指标涉及多事实表、时间窗口、先聚合再 JOIN 等复杂逻辑，不适合长期依赖 LLM 自由生成。

---

### Prompt Builder

负责把以下信息组织成 LLM 可理解的 SQL 生成 Prompt：
- 用户问题
- 业务上下文
- 结构化意图
- SQL 生成规则

Prompt Builder 不应该承担所有业务逻辑。它应该约束 LLM，而不是替代 Query Plan、Template SQL 或 Intent Parser。

---

### Answer Layer

负责把 SQL 执行后的 table 转换为中文业务回答。

Answer Layer 不负责：
- 生成 SQL
- 修正 SQL
- 判断指标含义
- 编造原因分析
- 给出策略建议

当前 Answer Layer V1 只基于 table 中已有事实生成回答。

---

## 为什么不能继续堆 Prompt 规则

继续堆 Prompt 规则会带来几个问题：
1. Prompt 越来越长，LLM 未必稳定遵守所有规则。
2. 不同职责混在一起，难以判断问题出在哪里。
3. 新增一个指标可能影响旧指标。
4. 测试只能覆盖结果，无法保护 Prompt 内部结构。
5. Phase3 进入 Tool / Agent 后，Prompt 需要更加模块化，否则难以复用。

因此，Prompt Builder V2 的核心价值不是让 Prompt 更强，而是让 Prompt 更可控。

---

## Day46 回归发现：Prompt 输出形态也是行为的一部分

在第一次 Prompt Builder V2 重构中，虽然代码结构更清晰，且 `prompt_builder_tests.py` 通过，但 `evaluator.py` 中 `case_030` 出现回归。

回归现象：
case_030：品类退款率从低到高排名
expected：面霜 4.37，洁面 4.47，面膜 4.48，防晒 4.55，精华 10.0
actual：防晒 0.0，面霜 0.0，洁面 0.0，面膜 0.0，精华 0.0

定位发现，LLM 生成 SQL 时自行添加了不存在的状态过滤条件：
```sql
AND r.refund_status = 'paid'
```
这导致退款金额聚合为空，最终所有品类退款率都变成 0.0。

这个问题说明：
1. Prompt 的代码结构重构不等于行为稳定。
2. Prompt 的标题、分组、编号方式都会影响 LLM 输出。
3. `prompt_builder_tests.py` 只能检查 Prompt 中是否包含关键规则，不能完全保证 LLM SQL 结果正确。
4. `evaluator.py` 的 result-level evaluation 能捕捉 Prompt 回归带来的业务结果错误。

最终修复策略：
1. 保留 Prompt Builder V2 的模块化函数。
2. 让 `build_sql_generation_rules()` 最终输出尽量接近 V1 的连续规则形态。
3. 在全局规则中增加“不编造状态值或枚举值”的约束。
4. 同步更新 `build_global_rules()` 和 `build_sql_generation_rules()`，避免当前生效规则和模块化规则源不一致。

新增规则：
1. 不要编造字段、表名、状态值或枚举值。不得自行假设 order_status、refund_status、channel_name、category 等字段的取值。
2. 必须使用指标中的 filters 作为 WHERE 条件。只能使用业务上下文中明确给出的 filters，不要自行新增 status 过滤条件。

本次回归后的测试结果：
prompt_builder_tests：5/5 PASS
evaluator：26/26 PASS
answer_judge mock：6/6 PASS

结论：Prompt Builder V2 的正确方向不是“让 Prompt 看起来更结构化”，而是：代码内部模块化，便于维护；最终 Prompt 输出形态保持稳定，降低 LLM SQL 回归风险。

---

## 当前测试结果

Prompt Builder Tests：
Total: 5
Passed: 5
Failed: 0

Evaluator：
Total: 26
Passed: 26
Failed: 0
Pass Rate: 100.0%

说明本次重构没有破坏当前主链路。

---

## 当前技术债

1. 普通指标仍缺少 query_plan，因此 TopN 默认排序方向部分依赖 LLM 语义理解。
2. ROI / CAC legacy rules 仍保留在 Prompt 中，后续可以考虑进一步下沉到 Query Plan / Template SQL。
3. Prompt Builder Tests 当前主要检查关键字符串存在，不检查 Prompt 结构语义。
4. Prompt 仍然依赖 `build_context(user_question)` 返回的业务上下文质量。
5. 后续进入 Phase3 Tool 化时，需要明确 SQL Tool 的输入输出结构。
6. 现在 build_global_rules() 和 build_sql_generation_rules() 里有重复规则，短期可以接受，但后续应该减少重复维护。

---

## 后续方向

短期：
- 保持 Prompt Builder V2 结构稳定
- 不继续随意往 Prompt 中堆规则
- 如需新增规则，先判断它属于 Intent、Query Plan、Template SQL、Prompt 还是 Answer Layer

中期：
- 给更多普通指标补充 query_plan
- 降低 LLM 对默认排序方向的自由判断
- 将复杂指标规则进一步迁移出 Prompt

长期：
- 将当前 Text-to-SQL 能力封装为 Phase3 Agent Tool
- 在 LangGraph 中用状态机管理 intent、clarification、sql_generation、execution、answer 和 evaluation