# Query Plan Routing V1

## 背景

当前 query_service 的主链路是：

question
↓
generate_sql(question)
↓
clean_sql
↓
validate_sql
↓
run_sql
↓
format_result

该链路完全依赖 LLM 根据 Prompt 生成 SQL。对于简单指标，该方式可接受。
但对于 ROI / CAC 等复杂指标，LLM 自由生成 SQL 存在稳定性问题：
- 跨事实表直接 JOIN
- 日期窗口不稳定
- ROI 被错误乘以 100
- CTE 字段别名引用错误
- CAC 首单口径错误

因此需要引入 Query Plan Routing。

---

## 目标

Query Plan Routing V1 的目标：
- 先识别 metric
- 再判断 metric 是否存在 query_plan
- 如果存在 query_plan，则优先走 Template SQL
- 如果不存在 query_plan，则继续走原 LLM SQL 生成

---

## V1 路由流程

question
↓
search_metric(question)
↓
metric_name
↓
get_query_plan_by_metric(metric_name)
↓
if query_plan exists:
    generate_sql_from_template(question, query_plan)
else:
    generate_sql(question)
↓
clean_sql
↓
validate_sql
↓
run_sql
↓
format_result

---

## 为什么不直接替换 generate_sql？

因为当前系统已有很多普通指标依赖 LLM SQL 生成：
- item_sales_amount
- refund_rate
- order_count
- sales_quantity
- channel_sales_amount
- channel_refund_rate

这些指标目前运行稳定，不应被 Query Plan 改动影响。

Query Plan V1 只接管高风险复杂指标：
- roi
- cac

---

## metric 分流规则

1. 走 Query Plan

当 metric_name 命中：
- roi
- cac
且 metadata/query_plans.yaml 中存在对应 plan

2. 走 LLM SQL

当 metric_name 没有 query_plan，例如：
- channel_sales_amount
- channel_refund_rate
- item_sales_amount
- refund_rate
继续使用原 generate_sql(question)。

---

## V1 不做什么

Query Plan Routing V1 暂不处理：
- 多指标问题
- 用户自定义时间范围
- 多维度分析
- 多轮追问
- 图表生成
- 自动解释结果

---

## 风险控制

接入后必须保证：
- ROI / CAC 输出结果与当前 Golden Dataset 一致
- 普通指标不受影响
- Evaluator 20/20 PASS
- query_service 返回结构保持不变

---

## 后续演进

### V1

只完成分流设计和 loader。

### V2

实现 template_sql_generator.py。

### V3

query_service 接入：
- 有 query_plan → template
- 无 query_plan → LLM

### V4

配合 Intent Parser，支持 TopN、Ranking、时间范围等参数化模板。

