# Day36 学习日志

## 今日主题

渠道分析能力建设：渠道数据层、渠道指标、ROI 指标接入与回归验证

---

## 今日完成内容

### 1. 渠道数据层核对

完成对 PostgreSQL 中渠道相关表的事实核对：
- dim_channel
- fact_marketing_spend
- fact_orders.channel_id
- dim_customer
- fact_orders

确认：
- dim_channel 已存在
- fact_marketing_spend 已存在
- fact_orders 已通过 channel_id 关联 dim_channel
- fact_marketing_spend 已通过 channel_id 关联 dim_channel
- 营销投放数据为 900 条
- 5 个渠道，每个渠道 180 条投放记录

当前渠道包括：
- 天猫
- 京东
- 抖音
- 小红书
- 微信小程序

---

### 2. 渠道元数据补齐

补充 metadata/table_dictionary.yaml：
- dim_channel
- fact_marketing_spend

补充 metadata/table_relationships.yaml：
- fact_orders.channel_id = dim_channel.channel_id
- fact_marketing_spend.channel_id = dim_channel.channel_id

完成验证：
- table_loader 可读取 dim_channel 与 fact_marketing_spend
- relationship_loader 可读取新增渠道关系

---

### 3. 新增渠道销售额与渠道退款率指标

补充 metadata/business_metrics.yaml：
- channel_sales_amount
- channel_refund_rate

支持问题：
- 哪个渠道销售额最高
- 各渠道销售额排名
- 哪个渠道退款率最高
- 各渠道退款率排名

---

### 4. 修复 Rule Layer 短 alias / 长 alias 冲突

发现问题：

“哪个渠道退款率最高” 同时命中：
- refund_rate
- channel_refund_rate

根因：
metric_loader.search_metrics 使用简单字符串包含匹配，
导致短 alias「退款率」和长 alias「渠道退款率」同时命中。

解决：
在 metric_loader.search_metrics 中加入 match_score，
当多个规则命中时，优先保留更具体的匹配结果。

验证通过：
- 哪个渠道退款率最高 → channel_refund_rate
- 哪个品类退款率最高 → refund_rate
- 哪个渠道销售额最高 → channel_sales_amount
- 哪个品类销售额最高 → item_sales_amount

---

### 5. 渠道指标主链路打通

验证 context_builder：
- channel_sales_amount 可注入 fact_orders、dim_channel
- channel_refund_rate 可注入 fact_orders、fact_order_items、fact_refunds、dim_channel

验证 query_service：
- 哪个渠道销售额最高 → 天猫，2445170.92
- 哪个渠道退款率最高 → 抖音，6.86%

---

### 6. ROI 指标建设

新增 roi 指标。

ROI 业务口径：ROI = 渠道销售额 / 渠道营销投放成本

关键约束：
- ROI 不乘以 100
- ROI 字段别名使用 roi
- 销售额和营销成本必须使用相同分析时间窗口
- 跨事实表指标必须先分别聚合，再 JOIN 聚合结果
- 禁止直接 JOIN fact_orders 和 fact_marketing_spend 后再 SUM

手写 SQL 验证结果：

| channel_name | channel_type | channel_sales_amount | marketing_spend_amount | roi |
|---|---|---:|---:|---:|
| 天猫 | 电商平台 | 2434556.85 | 1448311.27 | 1.68 |
| 微信小程序 | 私域 | 813384.83 | 538818.73 | 1.51 |
| 京东 | 电商平台 | 1572104.28 | 1089606.16 | 1.44 |
| 抖音 | 内容电商 | 1994334.69 | 1781949.43 | 1.12 |
| 小红书 | 内容种草 | 1176887.18 | 1397513.06 | 0.84 |

主链路验证：
- 哪个渠道ROI最高 → 天猫，roi = 1.68
- 各渠道ROI排名 → 天猫、微信小程序、京东、抖音、小红书

---

### 7. Prompt Builder 调整

为支持 ROI 和跨事实表指标，调整 prompt_builder.py：

新增约束：
- 跨事实表指标必须先分别聚合再 JOIN
- ROI 必须先聚合销售额和营销成本，再计算 ROI
- ROI 不乘以 100
- 百分比指标才乘以 100
- 字段别名优先使用指标技术名
- 未指定时间范围时，ROI 必须使用订单表与营销投放表的重叠日期窗口

---

### 8. Golden Dataset 扩展与回归测试

Golden Cases 从 12 条扩展到 18 条。

新增：
- case_018：哪个渠道销售额最高
- case_019：各渠道销售额排名
- case_020：哪个渠道退款率最高
- case_021：各渠道退款率排名
- case_022：哪个渠道ROI最高
- case_023：各渠道ROI排名

Evaluator 结果：
- Total: 18
- Passed: 18
- Failed: 0
- Pass Rate: 100.0%

---

## 今日关键问题与解决

### 问题 1：渠道表存在，但系统无法回答渠道问题

原因：
- table_dictionary.yaml 和 table_relationships.yaml 未补充渠道相关元数据
- business_metrics.yaml 未定义渠道指标

解决：
- 补充渠道表字典
- 补充渠道表关系
- 新增 channel_sales_amount 和 channel_refund_rate

---

### 问题 2：渠道退款率与通用退款率冲突

原因：
- Rule Layer 使用简单 alias 包含匹配
- “渠道退款率” 同时包含 “退款率”

解决：
- 在 metric_loader.search_metrics 中增加 match_score
- 多个 rule 命中时优先保留更具体的 alias

---

### 问题 3：ROI SQL 直接 JOIN 两张事实表导致结果错误

原因：
- fact_orders 和 fact_marketing_spend 都是事实表
- 直接按 channel_id JOIN 会产生多对多行膨胀
- SUM 后结果被放大

解决：
- Prompt 增加跨事实表指标规则
- 必须先分别按 channel_id 聚合，再 JOIN 聚合结果

---

### 问题 4：ROI 被错误乘以 100

原因：
- 原 Prompt 将所有比率类指标都要求乘以 100
- ROI 是倍数，不是百分比

解决：
- 明确百分比指标才乘以 100
- ROI 不乘以 100，字段别名使用 roi

---

### 问题 5：ROI 日期窗口不稳定

原因：
- 模型曾编造示例日期
- 或未使用订单与投放的重叠时间窗口

解决：
- Prompt 明确禁止编造日期
- 未指定日期时，必须使用 date_window CTE 计算重叠时间窗口

---

## 今日收获

1. 数据库有表，不代表语义层能用。
2. 指标新增不仅是写 YAML，还会暴露 Rule Layer 的冲突问题。
3. 跨事实表指标不能直接 JOIN 后聚合，必须先聚合再 JOIN。
4. ROI 与退款率不同，ROI 是倍数，不是百分比。
5. Prompt 可以修复部分问题，但不等于工业级稳定。
6. 高风险指标后续应考虑 SQL Template / Query Plan。
7. Evaluator 的价值在于回归测试，能发现旧能力是否被新修改影响。

---

## 当前技术债

### 1. ROI 仍依赖 Prompt 约束

当前 ROI 已可生成正确 SQL，但仍依赖 LLM 遵守复杂 Prompt。

后续建议：
- 为 ROI / CAC 等高风险指标引入 SQL Template
- 或设计 Metric Query Plan

---

### 2. Evaluator 仍是结构级评估

当前 evaluator 主要检查：
- SQL 是否执行成功
- 是否包含预期表
- 是否包含预期字段

尚未检查：
- Top1 结果是否正确
- 数值是否正确
- 排序是否正确

后续建议：
- 增加 expected_result
- 引入结果级 Evaluation

---

## 今日最终状态

Phase2 当前主链路：

自然语言问题
↓
Hybrid Search
↓
Context Builder
↓
Prompt Builder
↓
DeepSeek SQL Generation
↓
SQL Cleaner
↓
SQL Validator
↓
PostgreSQL Execution
↓
Result Formatter
↓
Evaluator

当前 Golden Cases：
- 18 Cases
- 100% Pass Rate
