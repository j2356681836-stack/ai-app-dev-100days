# Day38 学习日志

## 今日主题

Query Plan Loader、Template SQL Generator、Query Service Routing 与模板链路回归验证

---

## 今日完成内容

### 1. Query Plan Loader

新增文件：app/semantic_layer/query_plan_loader.py

实现函数：
- load_query_plans
- get_query_plan_by_name
- get_query_plan_by_metric
- has_query_plan

完成验证：
- has_query_plan("roi") → True
- has_query_plan("cac") → True
- has_query_plan("channel_sales_amount") → False

说明：
- roi / cac 是高风险复杂指标，适合走 Query Plan / Template
- channel_sales_amount 是普通指标，继续走 LLM SQL 生成

---

### 2. Template SQL Generator V1

新增文件：app/text_to_sql/template_sql_generator.py

实现能力：
- parse_limit
- build_limit_clause
- generate_roi_sql
- generate_cac_sql
- generate_template_sql

---

### 3. LIMIT 解析能力

将原本简单的 Top1 判断升级为 parse_limit。

支持：
- 哪个渠道ROI最高 → LIMIT 1
- 各渠道ROI排名 → 无 LIMIT
- 渠道ROI Top3 → LIMIT 3
- 渠道ROI前3 → LIMIT 3
- 获客成本最低的三个渠道 → LIMIT 3
- 获客成本最低的3个渠道 → LIMIT 3
- 获客成本前五渠道 → LIMIT 5

关键规则：明确数量优先于极值表达。

例如：获客成本最低的三个渠道
应解析为：
- 排序方向：ASC
- LIMIT：3
而不是误判为 Top1。

---

### 4. ROI Template SQL

实现：generate_roi_sql(question)

固定 ROI 计算逻辑：
- ROI 不乘以 100
- 使用订单与投放的重叠日期窗口
- fact_orders 先按 channel_id 聚合销售额
- fact_marketing_spend 先按 channel_id 聚合营销花费
- 再 JOIN 聚合结果
- ROI 越高越好，默认 DESC
- 支持 Top1 / TopN / Ranking

验证结果：
- 哪个渠道ROI最高 → 天猫，roi = 1.68
- 各渠道ROI排名 → 天猫、微信小程序、京东、抖音、小红书
- 渠道ROI Top3 → 天猫、微信小程序、京东

---

### 5. CAC Template SQL

实现：generate_cac_sql(question)

固定 CAC 计算逻辑：
- CAC = marketing_spend_amount / acquired_customer_count
- CAC 越低越好，默认 ASC
- 使用订单与投放的重叠日期窗口
- 先在全量 paid 订单中计算真实首单
- 再判断真实首单是否落在时间窗口内
- 按真实首单 channel_id 统计获客客户数
- 按 channel_id 聚合营销花费
- 支持 Top1 / TopN / Ranking

验证结果：
- 哪个渠道获客成本最低 → 天猫，cac = 2284.40
- 各渠道获客成本排名 → 天猫、微信小程序、京东、抖音、小红书
- 获客成本最低的三个渠道 → 天猫、微信小程序、京东

---

### 6. generate_template_sql 统一入口

新增统一入口：generate_template_sql(metric_name, question)

当前支持：
- roi → generate_roi_sql
- cac → generate_cac_sql
- 其他指标 → None

验证：
- generate_template_sql("roi", "渠道ROI Top3") → 返回 ROI SQL
- generate_template_sql("cac", "获客成本最低的三个渠道") → 返回 CAC SQL
- generate_template_sql("channel_sales_amount", "哪个渠道销售额最高") → None

---

### 7. Query Service Routing 接入

修改：app/text_to_sql/query_service.py

原链路：
    question
    ↓
    generate_sql(question)
    ↓
    clean_sql
    ↓
    validate_sql
    ↓
    run_sql

新链路：
    question
    ↓
    search_metric(question)
    ↓
    metric_name
    ↓
    generate_template_sql(metric_name, question)
    ├─ roi / cac → template
    └─ 普通指标 → llm
    ↓
    clean_sql
    ↓
    validate_sql
    ↓
    run_sql

新增返回字段：generation_method

用于标识：
- template
- llm

验证结果：
- 哪个渠道ROI最高 → generation_method = template
- 哪个渠道获客成本最低 → generation_method = template
- 哪个渠道销售额最高 → generation_method = llm
- 渠道ROI Top3 → generation_method = template

---

### 8. Template SQL Tests

新增文件：app/evaluation/template_sql_tests.py

测试内容：
- parse_limit
- generate_template_sql
- ROI 模板关键结构
- CAC 模板关键结构
- 普通指标不走模板

测试结果：
- Total: 12
- Passed: 12
- Failed: 0

说明：
- template_sql_tests.py 用于保护模板层本身。
- evaluator.py 用于保护端到端业务链路。

---

### 9. Evaluator 增加 generation_method 校验

在 Golden Cases 中增加：expected_generation_method

用于确认：
- ROI / CAC 必须走 template
- 渠道销售额 / 渠道退款率继续走 llm

修改 evaluator.py：

新增：check_generation_method

Evaluator 当前支持：
- expected_tables
- expected_columns
- expected_result
- expected_order
- expected_generation_method

最终结果：
- Total: 20
- Passed: 20
- Failed: 0
- Pass Rate: 100%

---

## 今日收获

### 1. Query Plan Routing 已经真正进入主链路

今天之前：ROI / CAC 仍然依赖 Prompt 让 LLM 生成复杂 SQL
今天之后：
- ROI / CAC 走确定性 Template SQL
- 普通指标继续走 LLM

这显著降低了复杂指标的不稳定性。

---

### 2. Template 与 LLM 应该分工

当前系统已经开始形成分层：

LLM 负责：
- 识别用户问题对应的指标
- 普通指标 SQL 生成

Template 负责：
- ROI
- CAC
- 跨事实表指标
- 高风险口径

---

### 3. TopN 不能简单等同于 Top1

“最高”“最低”表达排序方向，不一定表示只取 1 条。

例如：获客成本最低的三个渠道

应该解析为：
- ORDER BY cac ASC
- LIMIT 3

而不是：LIMIT 1

---

### 4. query_plans.yaml 的意义

虽然当前 ROI / CAC SQL 仍然写在 template_sql_generator.py 中，但 query_plans.yaml 已经具备三层意义：
- 作为复杂指标 SQL 计划的结构化说明书
- 作为 query_service 分流依据
- 作为未来参数化模板的元数据来源

当前阶段：
- query_plans.yaml = 计划元数据
- template_sql_generator.py = 实际 SQL 生成代码

未来可以演进为：
    query_plans.yaml
    ↓
    通用 template generator
    ↓
    参数化生成 SQL

---

### 5. 两类测试互补

- template_sql_tests.py 保护模板层逻辑
- evaluator.py 保护端到端业务链路

二者不是调用关系，而是不同层级的测试。

---

## 当前系统架构

    自然语言问题
    ↓
    Hybrid Search / search_metric
    ↓
    metric_name
    ↓
    generate_template_sql(metric_name, question)
    ├─ roi / cac → Template SQL
    └─ 普通指标 → DeepSeek SQL
    ↓
    SQL Cleaner
    ↓
    SQL Validator
    ↓
    PostgreSQL
    ↓
    Table
    ↓
    Result-level Evaluation

---

## 当前技术债

### 1. query_plans.yaml 尚未被模板生成器深度使用

当前只是用于分流和结构化沉淀。后续可将：
- default_sort
- output formula
- dimension
- date_window
- steps
逐步从 YAML 中读取，而不是写死在 Python 模板函数里。

---

### 2. parse_limit 仍是过渡方案

当前 parse_limit 位于：template_sql_generator.py
后续应迁移到：intent_parser.py

并拆分为：
- limit
- sort_direction
- ranking_type

---

### 3. Query Plan 当前只支持 ROI / CAC

后续如果新增：
- 利润率
- 复购率
- LTV
- 转化率
- 会员成长指标
需要判断是否也纳入 Query Plan / Template。

---

## 今日最终状态

当前支持指标：
- item_sales_amount
- order_paid_amount
- refund_rate
- order_count
- sales_quantity
- channel_sales_amount
- channel_refund_rate
- roi
- cac

当前 Query Plan / Template：
- roi → template
- cac → template
- 其他指标 → llm

当前 Golden Dataset：
- 20 Cases
- 100% PASS

当前测试体系：
- template_sql_tests.py：12/12 PASS
- evaluator.py：20/20 PASS