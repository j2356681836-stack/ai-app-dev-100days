# Day37 学习日志

## 今日主题

CAC 指标建设、结果级 Evaluation 升级、Ranking Evaluation、Query Plan YAML V1

---

## 今日完成内容

### 1. CAC 业务口径设计

完成 CAC 指标口径设计。

CAC 定义：CAC = 渠道营销投放成本 / 渠道获客客户数

其中获客客户数采用真实首单新客口径：
先在全量 paid 订单中找到每个客户的真实首单
↓
再判断该真实首单是否落在分析时间窗口内
↓
按真实首单 channel_id 归因获客渠道

明确不采用：COUNT(DISTINCT customer_id) 和 窗口时间内首单

---

### 2. CAC 手写 SQL 验证

完成 CAC 标准 SQL 验证。

关键 SQL 逻辑：
- 使用 date_window 计算 fact_orders 与 fact_marketing_spend 的重叠时间窗口
- first_paid_order 在全量 paid 订单中计算真实首单
- acquired_customers 在真实首单基础上判断是否落在时间窗口内
- channel_spend 按 channel_id 聚合营销成本
- CAC = marketing_spend_amount / acquired_customer_count
- CAC 越低越好，排序方向为 ASC

标准结果：
| channel_name | channel_type | marketing_spend_amount | acquired_customer_count |     cac |
| ------------ | ------------ | ---------------------: | ----------------------: | ------: |
| 天猫           | 电商平台         |             1448311.27 |                     634 | 2284.40 |
| 微信小程序        | 私域           |              538818.73 |                     196 | 2749.08 |
| 京东           | 电商平台         |             1089606.16 |                     370 | 2944.88 |
| 抖音           | 内容电商         |             1781949.43 |                     508 | 3507.77 |
| 小红书          | 内容种草         |             1397513.06 |                     292 | 4786.00 |

---

### 3. 新增 CAC 指标

补充 metadata/business_metrics.yaml：

cac

支持问题：
- 哪个渠道CAC最低
- 哪个渠道获客成本最低
- 哪个渠道拉新成本最低
- 哪个渠道拉新效率最高
- 各渠道CAC排名
- 各渠道获客成本排名

完成验证：
- YAML 读取正常
- search_metric 正确命中 cac
- context_builder 注入 cac 指标上下文
- query_service 返回正确结果

---

### 4. 修正 CAC 首单口径

发现问题：模型生成的 SQL 曾存在“先按时间窗口过滤订单，再计算 ROW_NUMBER”的风险。

该逻辑实际计算的是：窗口内首单而不是真实首单

修正：
- business_metrics.yaml 中强化 CAC 定义
- prompt_builder.py 增加 CAC 专用规则
- 明确必须先计算全量 paid 订单真实首单
- 再判断真实首单是否落在 date_window 内
- 禁止先按时间窗口过滤订单后再计算 ROW_NUMBER

---

### 5. CAC 主链路验证

验证 query_service：
    哪个渠道获客成本最低
    → 天猫，cac = 2284.40
    各渠道获客成本排名
    → 天猫、微信小程序、京东、抖音、小红书
最终结果与手写 SQL 一致。

---

### 6. Golden Cases 扩展

新增 CAC 相关 Golden Cases：
- case_024：哪个渠道获客成本最低
- case_025：各渠道获客成本排名

Golden Cases：
    18 Cases
    ↓
    20 Cases

Evaluator：
    Total: 20
    Passed: 20
    Failed: 0
    Pass Rate: 100%

--- 

### 7. Result-level Evaluation V1

升级 evaluator.py。新增 expected_result 支持。

新增能力：
- 检查结果第一行是否符合预期
- 支持字符串字段精确匹配
- 支持数值字段 tolerance 误差匹配

新增函数：
- values_equal
- check_expected_result

用于验证：
- Top1 对象是否正确
- 关键数值是否正确

示例：
"expected_result": {
    "channel_name": "天猫",
    "cac": 2284.40,
}

---

### 8. Ranking Result Evaluation V1

继续升级 evaluator.py，新增 expected_order 支持。

新增能力：
- 检查排名类问题的返回顺序
- 对 table["rows"] 中指定字段进行顺序校验

新增函数：check_expected_order

用于验证：
- 各渠道销售额排名
- 各渠道退款率排名
- 各渠道 ROI 排名
- 各渠道获客成本排名

示例：
"expected_order": {
    "field": "channel_name",
    "values": [
        "天猫",
        "微信小程序",
        "京东",
        "抖音",
        "小红书",
    ],
}

最终 evaluator 仍保持：20/20 PASS

---

### 9. 暴露复杂指标 Prompt 不稳定问题

在 evaluator 回归过程中，ROI 曾出现 SQL 生成不稳定：
- CTE 字段别名引用错误
- 将 spend_amount 错误写成 cs.spend_amount
- SQL 执行失败

修复：
- prompt_builder.py 补充 ROI CTE 别名约束
- 明确 channel_sales 只包含 sales_amount
- channel_spend 只包含 spend_amount
- ROI 必须使用 cs.sales_amount / csp.spend_amount

工程结论：ROI / CAC 这类复杂跨事实表指标不适合长期依赖 LLM 自由生成 SQL。

---

### 10. Metric Query Plan V1 设计

开始 Day39 方向的设计工作。

新增架构设计方向：
- LLM 负责识别业务意图
- 系统负责使用 Query Plan / SQL Template 生成复杂指标 SQL

新增文件：docs/architecture/metric_query_plan_v1.md

明确：
- ROI Query Plan
- CAC Query Plan
- simple_metric
- ratio_metric
- cross_fact_metric
- acquisition_metric
- Query Plan 与 business_metrics.yaml 的职责边界

---

### 11. 新增 query_plans.yaml

新增运行时元数据文件：metadata/query_plans.yaml

当前包含：
- roi_channel_v1
- cac_channel_v1

完成 YAML 读取验证：['roi_channel_v1', 'cac_channel_v1']

完成单个 plan 读取验证：
- roi → cross_fact_metric → default_sort desc
- cac → acquisition_metric → default_sort asc
当前暂未接入主链路。

---

## 今日关键收获

### 1. CAC 的核心不是公式，而是获客客户数口径

获客客户数
≠
下单客户数
≠
活跃客户数
≠
窗口内首单客户数

本项目采用：真实首单新客口径

---

### 2. Result-level Evaluation 很有必要

结构级 evaluator 只能说明：
- SQL 能跑
- 用了预期表
- 有预期字段

结果级 evaluator 可以进一步验证：
- Top1 是否正确
- 关键数值是否正确
- 排名顺序是否正确

---

### 3. 固定 seed 数据适合 expected_result

当前项目是固定模拟数据集，因此可以进行结果级验证。

真实生产数据不适合写死具体数值，更适合做：
- 结果范围校验
- 排序方向校验
- 非空校验
- 数据合理性校验

---

### 4. Prompt 不是工业级稳定性的最终答案

ROI / CAC 多次暴露出 Prompt-only Text-to-SQL 的不稳定：
- 聚合顺序不稳定
- 时间窗口不稳定
- 字段别名不稳定
- CTE 引用不稳定

后续应引入：SQL Template / Metric Query Plan

---

## 当前技术债

### 1. query_plans.yaml 尚未接入主链路

当前只是完成元数据设计与读取验证。

后续需要：
- query_plan_loader.py
- template_sql_generator.py
- query_service 分流逻辑

### 2. business_metrics.yaml 中 ROI / CAC 仍包含较多 SQL 细节

短期保留，保证当前 Prompt 链路稳定。

后续当 Query Plan 接入后，可以瘦身为：
- 指标名称
- aliases
- definition
- grain
- query_plan 引用

---

### 3. evaluator 结果级能力仍是 V1

当前支持：
- Top1 第一行结果校验
- 排名顺序校验

暂不支持：
- 多行数值精确校验
- 排序字段自动验证
- 生产环境动态数据合理性校验

---

## 今日最终状态

当前指标：
- item_sales_amount
- order_paid_amount
- refund_rate
- order_count
- sales_quantity
- channel_sales_amount
- channel_refund_rate
- roi
- cac

当前 Golden Dataset：
- 20 Cases
- 100% PASS

当前 Evaluation 能力：
- SQL 结构级检查
- expected_tables
- expected_columns
- expected_result
- expected_order
- tolerance 数值误差
- evaluation report 保存

当前 Query Plan：
- roi_channel_v1
- cac_channel_v1
