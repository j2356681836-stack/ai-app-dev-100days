# Metric Query Plan V1

## 背景

当前 Text-to-SQL 链路主要依赖 Prompt 约束 LLM 生成 SQL。

对于简单指标，例如：
- 渠道销售额
- 渠道退款率
- 品类销售额
- 品类退款率
Prompt + Semantic Layer 基本可以生成可执行 SQL。

但对于复杂指标，例如：
- ROI
- CAC
仅依赖 LLM 自由生成 SQL 存在稳定性风险。

---

## 已暴露问题

### 1. 跨事实表直接 JOIN 导致多对多放大

ROI 同时依赖：
- fact_orders
- fact_marketing_spend

如果直接按 channel_id JOIN 两张事实表，再 SUM，会产生笛卡尔积。

正确方式：
先按 channel_id 聚合订单销售额
↓
先按 channel_id 聚合营销花费
↓
再 JOIN 聚合结果
↓
计算 ROI

### 2. 指标表达形式不稳定

ROI 是倍数，不是百分比。

错误：roi_pct = ROI * 100
正确：roi = sales_amount / spend_amount

### 3. 日期窗口不稳定

ROI 和 CAC 都需要订单数据与营销投放数据处于同一分析时间窗口。
当用户没有指定时间范围时，应使用两张表的重叠时间窗口：
`start_date = GREATEST(MIN(order_date), MIN(spend_date))`
`end_date = LEAST(MAX(order_date), MAX(spend_date))`

### 4. CAC 获客客户数口径容易错误

CAC 的获客客户数不能简单使用：COUNT(DISTINCT customer_id)
也不能使用：窗口内首单

应使用真实首单新客口径：
先在全量 paid 订单中找到每个客户的真实首单
↓
再判断真实首单是否落在分析时间窗口内
↓
按真实首单 channel_id 归因获客渠道

---

## 设计目标

Metric Query Plan V1 的目标：
- LLM 负责识别用户意图
- 系统负责生成高风险指标 SQL 骨架

具体目标：
- 降低 ROI / CAC 对 Prompt 的依赖
- 固化跨事实表指标的聚合顺序
- 固化日期窗口逻辑
- 固化字段别名
- 固化默认排序方向
- 提升 Evaluator 稳定性

---

## Query Plan 分层

### LLM 负责

- 识别用户问题对应的 metric
- 识别是否是 Top1 问题
- 识别是否是排名问题
- 识别用户是否指定时间范围

### Query Plan 负责

- 指标计算路径
- 事实表聚合顺序
- JOIN 方式
- 默认排序方向
- 输出字段别名
- 日期窗口策略

### SQL Template 负责

- 生成稳定 SQL 骨架
- 避免 LLM 编造复杂 SQL
- 避免多对多行膨胀
- 避免字段别名错误

---

## 指标分类

### simple_metric

适用于：
- item_sales_amount
- order_paid_amount
- order_count
- sales_quantity
- channel_sales_amount

特点：
- 单主事实表
- 聚合逻辑简单
- LLM 生成 SQL 风险较低

### ratio_metric

适用于：
- refund_rate
- channel_refund_rate

特点：
- 需要分子和分母
- 通常需要 LEFT JOIN 可选事实表
- 百分比类指标需要乘以 100
- 字段别名使用 metric_name + _pct

### cross_fact_metric

适用于：
- roi

特点：
- 涉及多张事实表
- 必须先分别聚合事实表
- 再 JOIN 聚合结果
- 不应直接 JOIN 明细事实表
- 通常需要日期窗口对齐

### acquisition_metric

适用于：
- cac

特点：
- 涉及营销成本
- 涉及真实首单新客
- 需要窗口对齐
- 排序方向通常是 ASC
- 获客客户数口径需要严格定义

---

## V1 不做什么

Metric Query Plan V1 暂不处理：
- 任意时间筛选
- 多维度组合分析
- 多指标同时查询
- 自动图表生成
- 多轮追问
- 用户自定义指标

V1 只解决： ROI / CAC 这类高风险指标的 SQL 稳定性问题

---

## 后续演进方向

### V1

文档化 Query Plan，明确复杂指标 SQL 生成规则。

### V2

将 ROI / CAC 的 SQL Template 代码化。

### V3

让 query_service 根据 metric_name 自动选择：
- 普通指标 → LLM 生成 SQL
- 高风险指标 → SQL Template 生成 SQL

### V4

Intent Parser 输出：

{
  "metric": "roi",
  "dimension": "channel",
  "ranking": {
    "type": "top",
    "value": 1
  }
}

再由 Query Plan 生成 SQL。


---

## 4. 新建后做什么？

检查：
- ROI 的问题是否都被覆盖？
- CAC 的真实首单口径是否表达清楚？
- 为什么 Top1 / Ranking 不应该完全交给 LLM 是否说清楚？
- 这个设计是否能解释后续为什么要做 SQL Template？