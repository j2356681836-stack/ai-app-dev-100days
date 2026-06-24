# Phase2 Architecture Review

## 背景

Phase2 的目标是构建一个具备业务语义理解能力的 AI Data Analyst / Text-to-SQL 系统。

系统要解决的问题不是“让大模型随便写一段 SQL”，而是让用户可以用自然语言提出业务问题，系统能够：
理解问题
识别业务指标
选择正确数据口径
生成 SQL
执行查询
返回结构化结果
生成中文业务回答
并通过 Evaluation 验证结果质量

当前系统已经从早期的 Prompt-only Text-to-SQL，演进为：
Business Semantic Layer
+ Intent Parser
+ Hybrid Metric Search
+ Query Plan Routing
+ Template SQL / LLM SQL 双路径
+ Answer Layer
+ Evaluation Workflow

---

## 当前主链路

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
Answer Generator
↓
Evaluation

---

## 1. Intent Parser

Intent Parser 负责从自然语言问题中解析结构化意图。

当前解析内容包括：
limit
ranking_type
sort_hint
dimension

示例：渠道ROI从低到高排名

可以解析为：
ranking_type = ranking
sort_hint = asc
dimension = channel

### 为什么需要 Intent Parser

如果直接把自然语言交给 LLM 生成 SQL，LLM 需要同时完成：
理解问题
判断排序方向
判断 TopN
判断分析维度
选择字段
生成 SQL

这会让 SQL 生成不稳定。

Intent Parser 的作用是先把一部分确定性语义结构化，让后续模块不再完全依赖 LLM 自由理解。

---

## 2. Intent Resolver

Intent Resolver 负责把用户显式意图和指标默认规则进行融合。

当前核心输出：
final_sort_direction
sort_field

排序决策规则：
用户显式 sort_hint
>
query_plan.default_sort.direction
>
None

示例：
各渠道ROI排名
→ 用户没有说从高到低
→ 使用 ROI 默认排序 desc

渠道ROI从低到高排名
→ 用户明确说从低到高
→ 使用 asc 覆盖默认 desc

### 为什么需要 Intent Resolver

因为不同指标的“好坏方向”不一样。

例如：
ROI 越高越好
CAC 越低越好
退款率通常越高越需要关注

如果只依赖用户问题字面表达，很容易遗漏指标默认排序逻辑。

---

## 3. Hybrid Search / Metric Recognition

Hybrid Search 负责识别用户问题对应的业务指标。

当前包括：
Alias Match
Keyword Group Match
Embedding Match
Clarification

### 各方式分工

Alias Match：适合明确、可控的业务说法
Keyword Group Match：适合组合关键词触发指标
Embedding Match：适合语义相近但没有直接命中 alias 的问题
Clarification：适合语义不清或多个指标候选接近的情况

### 为什么不是只用 Embedding

Embedding 能解决语义相似，但不能解决业务歧义。

例如：最赚钱

可能指：
销售额
利润
ROI
高价值商品
这种情况不能强行猜，应进入 clarification。

---

## 4. Query Plan Routing

Query Plan Routing 负责决定 SQL 生成路径。

当前策略：
ROI / CAC → Template SQL
普通指标 → LLM SQL

### 为什么 ROI / CAC 走 Template SQL

ROI 和 CAC 是复杂跨事实表指标。

它们容易出错的点包括：多事实表 JOIN 导致行膨胀
ROI 是否错误乘以 100
CAC 是否使用真实首单新客
排序方向是否符合业务口径

因此这类高风险指标不适合长期依赖 LLM 自由生成 SQL。

### 为什么普通指标仍走 LLM SQL

普通指标如：
品类退款率
渠道销售额
销量
订单数

虽然也需要约束，但它们的 SQL 结构相对稳定，继续走 LLM 可以保留灵活性，避免系统过度模板化。

当前策略不是“全部模板化”，而是：
高风险复杂指标确定性生成
普通指标 LLM 生成 + Intent Context 约束

---

## 5. Prompt Builder V2

Prompt Builder V2 负责为普通指标 LLM SQL 生成构造上下文和规则。

当前 Prompt 包含：
业务指标定义
相关表结构
表关系
Intent Context
字段别名规则
Ranking / TopN 规则
维度字段规则
SQL 生成约束

### Day46 的重要经验

Prompt Builder 的代码可以模块化，但最终输出给 LLM 的 prompt 形态必须稳定。

Day46 曾出现一次回归：AND r.refund_status = 'paid'
这是 LLM 自行编造的状态值，导致退款聚合为空。

最终修复方向：
1. 保持代码内部模块化
2. 最终 Prompt 输出形态接近 V1 连续规则
3. 明确禁止编造字段、表名、状态值和枚举值
4. 只能使用业务上下文中明确提供的 filters

结论：
Prompt 重构不是普通字符串重构。
Prompt 的标题、分组、编号方式都会影响 LLM 输出。

---

## 6. SQL Cleaner / SQL Validator

SQL Cleaner 负责清理 LLM 输出中的非 SQL 内容。
SQL Validator 负责阻止危险 SQL。
当前系统只允许查询类 SQL，不允许执行破坏性操作。

### 为什么需要 SQL Cleaner / Validator

LLM 输出可能包含：
Markdown 代码块
解释文字
多余格式
危险 SQL

因此 SQL 进入数据库前必须经过清理和校验。

---

## 7. PostgreSQL Execution & Result Formatter

SQL 通过校验后进入 PostgreSQL 执行。

Result Formatter 负责将数据库返回结果转换为统一的 Python 数据结构，方便后续 Answer Generator 和 Evaluator 使用。

当前系统使用的是美妆行业模拟 BI 数据集，包含：
商品
用户
订单
订单明细
退款
评价
营销投放

---

## 8. Answer Generator

Answer Generator 负责把 SQL 查询结果转换成中文业务回答。
当前 Answer Layer V1 采用规则型生成。

支持：
Top1 回答
TopN 回答
Ranking 回答
ASC / DESC 排名描述
百分比指标展示
基于 table 的事实型回答

### 为什么 Answer Layer V1 不直接用 LLM

因为当前阶段最重要的是避免：SQL 查询结果正确，但中文回答编造原因或策略建议。
所以 Answer Layer V1 只基于 table 中已有事实回答，不做未经验证的业务推断。

---

## 9. Evaluation Workflow

当前系统不是只看“能不能生成 SQL”，而是通过多层 Evaluation 保证质量。

当前包括：
Deterministic Evaluator
Prompt Builder Tests
Answer Judge
Ragas Evaluation

不同评估层负责不同问题：

SQL / 结果 / 排序是否正确
→ deterministic evaluator

Prompt 关键规则是否保留
→ prompt_builder_tests

回答质量是否符合预期
→ answer_judge

回答是否被 context 支撑
→ ragas_eval

---

## 当前系统能力总结

当前系统已经支持：
自然语言问题
→ 业务指标识别
→ 意图解析
→ Query Plan Routing
→ Template SQL / LLM SQL
→ SQL 校验
→ 数据库执行
→ 中文业务回答
→ 多层 Evaluation

当前覆盖指标：
item_sales_amount
order_paid_amount
refund_rate
order_count
sales_quantity
channel_sales_amount
channel_refund_rate
roi
cac

当前覆盖问题类型：
Top1
TopN
Ranking
正向排序
反向排序
品类维度
渠道维度
ROI / CAC 复杂指标
普通指标

---

## 当前设计取舍

### 1. 不直接让 LLM 全权生成 SQL

原因：LLM 容易选错字段、编造状态值、误解排序方向、错误处理复杂指标。

因此系统通过业务语义层、Intent、Query Plan 和 Evaluation 进行约束。

### 2. 不把所有指标都模板化

原因：全部模板化会降低灵活性，也会让系统变成规则工程。

因此只把 ROI / CAC 等复杂高风险指标模板化。

### 3. Answer Layer V1 先规则生成

原因：当前阶段优先保证回答忠实于 SQL table，不追求自然语言丰富度。

### 4. Ragas 作为对照，不作为唯一评分器

原因：
Ragas 默认更适合传统 RAG。
Text-to-SQL 需要补充 SQL result semantics。

---

## 面试表达版本

可以这样介绍 Phase2：
我做的不是一个简单的 Text-to-SQL Demo，而是一个带业务语义层和评估体系的 AI Data Analyst 系统。

用户输入自然语言问题后，系统先通过 Intent Parser 解析 limit、排序、维度等结构化意图，再通过 Hybrid Search 识别业务指标。如果是 ROI、CAC 这类复杂跨事实表指标，会走 Query Plan 和 Template SQL；如果是普通指标，则走 LLM SQL，但会注入 Intent Context 和业务语义规则进行约束。

SQL 生成后会经过 Cleaner、Validator 和 PostgreSQL 执行，再由 Answer Generator 基于查询结果生成中文回答。最后系统通过 deterministic evaluator、answer_judge 和 Ragas 做多层评估，分别检查 SQL 结果正确性、回答质量和 groundedness。


---

## 当前边界

当前系统仍有边界：
1. 普通指标还没有 query_plan，TopN 默认排序方向仍部分依赖 LLM。
2. Intent Parser V1 是规则型，对中文表达覆盖有限。
3. Answer Layer V1 主要支持聚合型 BI 问题，不支持复杂原因分析。
4. Ragas 当前只接入 faithfulness，还没有接入更多指标。
5. 当前数据集是模拟美妆 BI 数据，业务真实性仍可增强。

---

## 下一步

Phase2 剩余重点：
Day48：完成架构复盘与 Evaluation Workflow 文档
Day49：设计 LangGraph Phase3 入口
Day50：Phase2 总复盘、简历表达和 Phase3 交接



