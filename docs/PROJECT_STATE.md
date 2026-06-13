# AI-Architect-100Days

## 项目目标

构建企业级 AI BI Agent：

用户自然语言
→ Business Semantic Layer
→ Text-to-SQL
→ SQL Execution
→ Business Analysis
→ Agent Workflow

目标岗位：

- GenAI Engineer
- AI Agent Engineer
- AI Data Engineer

---
## 学习计划

### 第一阶段：API 确定性与监控基石 (Day 1-20)

**核心目标：** 把大模型从“聊天机器人”规训为一个“绝对稳定、可追踪的 JSON 生成函数”。

- **Day 1-7：原生 API 与异步高并发。** 使用 Python `asyncio` 调用 OpenAI/Anthropic 原生接口。强制使用 Structured Outputs 提取非结构化文本。引入 `tenacity` 实现指数退避重试，解决 429 和 500 报错。
- **Day 8-14：Schema 驱动开发。** 熟练使用 Pydantic V2。利用 `@field_validator` 处理大模型的脏数据（如去除 Markdown 标记、修正数据类型），完成美妆基础实体（如订单、商品、评价）的模型构建。
- **Day 15-20：可观测性 (Observability) 接入。** 全面接入 Langfuse。要求每一笔 API 调用的 Prompt、耗时、Token 成本和 Pydantic 校验结果，必须在控制台形成完整的 Trace 链路。
- **交付物：** 一个高并发、带自动重试、且所有出入参被严格清洗并记录在案的结构化数据提取 API。

---
### 第二阶段：业务语义层与 Eval 驱动的混合检索 (Day 21-50)

**核心目标：** 攻克企业级 Text-to-SQL 幻觉，将“美妆行业知识”预埋进数据库，并用数学指标衡量回答质量。

- **Day 21-30：高阶 SQL 与数据字典向量化。** 在 PostgreSQL 中构建美妆业务的高阶视图（如：同环比、ROI 聚合表）。**核心动作：** 将公司 500+ 表的表名、字段定义和业务口径解释存入 `pgvector`。
- **Day 31-40：精准路由的 Text-to-SQL 闭环。** 实现双层架构：Agent 收到自然语言后，先去 pgvector 检索相关的表结构（DDL）和业务定义，拼装成动态上下文，再让大模型生成 SQL。绝对禁止全量 DDL 注入。
- **Day 41-50：引入 Ragas 评估体系。** 停止肉眼看结果。构建 100 条美妆业务的 Golden Dataset（标准问答对）。使用 Ragas 计算你系统的 Faithfulness（忠实度）和 Answer Relevance（回答相关性），确保准确率稳步向 90% 逼近。
- **交付物：** 一个能在复杂业务黑话下，先查字典、再写 SQL、并能跑出客观评分报告的混合数据检索引擎。

---
### 第三阶段：状态机编排与原生 Agent大脑 (Day 51-75)

**核心目标：** 放弃单次线性流，掌握图结构逻辑，赋予系统自我纠错和多步推理的能力。

- **Day 51-60：LangGraph 基础与状态管理。** 学习 LangGraph 的核心理念（State, Nodes, Edges）。用纯代码构建一个循环图：让系统能够维护上下文历史，并根据条件分支执行不同的函数。
- **Day 61-70：Multi-Agent 协同与 Tool Calling 进阶。** 将第二阶段的 pgvector 检索和 Text-to-SQL 封装为独立的 Tool。让一个“路由 Agent”负责意图识别，将任务分发给“查库 Agent”或“查文档 Agent”。
- **Day 71-75：反思与自愈 (Reflection & Self-correction)。** 在 LangGraph 中加入“自我批评”节点。例如：SQL Agent 生成的 SQL 运行报错了，Graph 会自动将报错信息传回给模型重新修改代码，直到成功或达到最大重试次数再抛出异常。
- **交付物：** 一个能在遇到错误时自动兜底、根据意图自主切换工具的 LangGraph 复杂状态机系统。

---
### 第四阶段：交付部署与自动化优化 (Day 76-90)
  
**核心目标：** 解决技术栈割裂问题，用最少的前端代码交付最高级的业务决策台。

- **Day 76-82：Streamlit 企业级决策台。** 放弃 Vercel 复杂的全栈生态，直接使用纯 Python 的 Streamlit 开发前端。快速构建出包含数据看板、Chat 对话框和图表渲染的“美妆大盘决策台”，无缝对接你的 LangGraph 后端。
- **Day 83-86：DSPy 提示词自动寻优。** 砍掉不切实际的 DPO 训练。引入 DSPy，通过你在第二阶段准备的 Golden Dataset，让程序自动对大模型的 Prompt 进行微调和版本控制，榨干开源/闭源模型的推理能力。
- **Day 87-90：Serverless 云端部署。** 编写极简的 `requirements.txt` 和 `.env` 隔离机制。对接 Render 或 Zeabur，实现代码 Push 到 GitHub 后自动构建并对外发布，配置生产环境的 API 限流。
- **交付物：** 一个可通过公网访问、界面专业的企业级美妆数据 AI 助理。

---
#### 第五阶段：面试冲刺与价值放大 (Day 91-100)

**核心目标：** 将 90 天的技术积累转化为降维打击的求职资本。

- **Day 91-95：作品集与架构图包装。** 完善 GitHub 仓库的 README。画出你系统的状态机流转图和 Ragas 准确率提升曲线。
- **Day 96-100：工程化面试靶向训练。** 梳理项目中真实踩过的坑（如：并发 429 怎么处理的？大模型死循环了怎么阻断？脏数据怎么用 Pydantic 洗掉的？），用 STAR 法则写进简历。


---
## 当前阶段

Phase 2：Business Semantic Layer & Text-to-SQL

进度：Day21 ~ Day50

当前日期：Day37 / 100

---
## 已完成能力

### Phase1：LLM Reliability

#### API Reliability

- AsyncOpenAI
- asyncio.gather
- Semaphore
- Retry
- Structured Outputs

#### Data Validation

- Pydantic V2
- field_validator
- Nested Schema
- JSON Self-Healing

#### Observability

- Langfuse Tracing
- Parent/Child Span
- Token Monitoring

---

### Phase2：Business Semantic Layer

#### 数据层

- PostgreSQL
- pgvector
- SQLAlchemy 2.0
- Beauty BI Schema

#### 业务元数据

- business_metrics.yaml
- table_dictionary.yaml
- table_relationships.yaml

#### Retrieval

- metric_loader.py
- table_loader.py
- relationship_loader.py

#### Semantic Layer

- clarification.py
- semantic_search.py
- semantic_search_v2.py
- context_builder.py
- hybrid_search.py
- metric_text_builder.py
- vector_store.py

#### Text-to-SQL

- prompt_builder.py
- query_service.py
- result_formatter.py
- sql_generator.py（DeepSeek）
- sql_cleaner.py
- sql_validator.py

## 当前能力：

自然语言
↓
Semantic Search
↓
Context Builder
↓
Prompt Builder
↓
DeepSeek
↓
SQL Cleaner
↓
SQL Validator
↓
PostgreSQL
↓
Table
↓
Evaluation

### 当前Rule能力

支持：
- alias
- keyword_group
- 更具体 alias 优先

返回：
method = rule
search_type:
- alias
- keyword_group

新增能力：
- 当多个 rule 同时命中时，优先保留 match_score 更高的结果
- 用于解决“退款率”与“渠道退款率”等泛化词和具体词冲突

### Golden Dataset

当前：
20 Cases
100% PASS

当前覆盖：
- 品类销售额
- 品类退款率
- 订单数
- 销量
- 渠道销售额
- 渠道退款率
- ROI
- CAC

当前 Evaluation 能力：
- expected_tables
- expected_columns
- expected_result
- expected_order
- expected_generation_method
- tolerance 数值误差

### Metric Query Plan

当前状态：V1 已接入主链路。

已完成：
- metadata/query_plans.yaml
- app/semantic_layer/query_plan_loader.py
- app/text_to_sql/template_sql_generator.py

当前支持：
- roi_channel_v1
- cac_channel_v1

当前路由：
- roi → template
- cac → template
- 其他普通指标 → llm

当前模板能力：
- ROI Template SQL
- CAC Template SQL
- Top1 / TopN / Ranking LIMIT 解析
- generate_template_sql 统一入口

---
## 当前项目结构

app/
├── api/
├── agents/
├── db/
├── semantic_layer/
├── text_to_sql/
├── evaluation/
data/
docs/
metadata/

---

## 当前数据库

### 数据规模

- 100 Products
- 2000 Customers
- 20000 Orders
- 29051 Order Items
- 2008 Refunds
- 5000 Reviews

### 已植入业务规律

- 夏季防晒销量增长
- 小红书渠道成本增长
- 精华退款率更高

### 待增强业务规律

- 会员等级成长体系
- 会员等级历史表
- 复购行为增强

### 当前指标

item_sales_amount
order_paid_amount
refund_rate
order_count
sales_quantity
channel_sales_amount
channel_refund_rate
roi
cac

---

## 当前系统架构

Question
↓
Hybrid Search / Metric Recognition
├─ Alias Match
├─ Embedding Match
└─ Clarification
↓
Query Plan Routing
├─ ROI / CAC → Template SQL
└─ 普通指标 → LLM SQL
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

## 当前待办（Next Milestone）

### Day39-Day45 规划

目标：完成 Query Plan 稳定化，并进入 Intent Parser V1。
说明：
Day38 已完成 Query Plan Routing 主链路接入，ROI / CAC 已走 Template SQL。
后续计划保持 Phase2 主线不变，重点从“复杂指标稳定生成 SQL”升级到“业务意图识别”。

---

#### Day39

Query Plan 参数化 V1

目标：
减少 template_sql_generator.py 中的硬编码，让部分信息从 query_plans.yaml 读取。

学习内容：
- query_plans.yaml 与 template_sql_generator.py 的职责边界
- 从 plan 读取 default_sort
- 从 plan 读取 output alias
- 从 plan 读取 multiply_by_100
- 从 plan 读取 query_type
- 专用模板与参数化模板的取舍

交付：
- generate_template_sql 引入 query_plan 参数
- ROI / CAC 部分参数从 query_plans.yaml 读取
- template_sql_tests 扩展
- evaluator 20/20 PASS

验收：
- ROI / CAC 结果不变
- generation_method 仍为 template
- 普通指标仍走 llm

---

#### Day40

Intent Parser V1 设计

目标：
从 parse_limit 过渡到独立 Intent Parser 设计。

学习内容：
- limit 与 sort_direction 的拆分
- Top1 / TopN / Ranking 的区别
- ROI 越高越好，CAC 越低越好
- 指标默认排序方向
- 用户问题中的业务意图结构化

交付：
- docs/architecture/intent_parser_v1.md
- Intent Schema 设计
- intent examples
- parse_limit 迁移方案

示例输出：

```json
{
  "metric": "cac",
  "dimension": "channel",
  "ranking": {
    "enabled": true,
    "limit": 3,
    "direction": "asc"
  }
}

---

#### Day41

Intent Parser V1 实现

目标：实现 Rule-based Intent Parser。

学习内容：
- parse_metric
- parse_dimension
- parse_limit
- parse_sort_direction
- parse_ranking
- Intent Trace

交付：
- app/semantic_layer/intent_parser.py
- intent parser 测试脚本
- Top1 / TopN / Ranking 测试集

验收：
- 哪个渠道ROI最高 → metric=roi, limit=1, direction=desc
- 获客成本最低的三个渠道 → metric=cac, limit=3, direction=asc
- 各渠道销售额排名 → metric=channel_sales_amount, limit=None, direction=desc

---

#### Day42

Intent Parser 接入 Query Plan Template

目标：让 template_sql_generator 不再直接解析 question，而是使用 intent。

学习内容：
- intent 与 SQL Template 的接口
- limit 从 intent 传入
- sort_direction 从 intent 传入
- query_service 中 intent 的位置

交付：
- generate_roi_sql(intent)
- generate_cac_sql(intent)
- template_sql_tests 改造为 intent-based
- evaluator 回归

验收：
- ROI / CAC Top1、TopN、Ranking 全部稳定
- 20/20 PASS

---

#### Day43

普通指标 Intent 接入设计

目标：让普通指标也能使用 Intent 中的 dimension / ranking 信息，减少 Prompt 负担。

学习内容：
- 品类维度
- 渠道维度
- TopN
- 默认维度规则
- Prompt Builder 如何使用 intent

交付：
- prompt_builder 增加 intent context
- 普通指标仍走 LLM，但 Prompt 更结构化
- Golden Cases 回归

验收：
- 销售额Top5品类稳定
- 各渠道销售额排名稳定
- 品类退款率前三稳定
---

#### Day44

Result-level Evaluation V2

目标：扩展 evaluator 支持多行 expected_rows 和数值校验。

学习内容：
- expected_rows
- 多行结果校验
- 排名顺序 + 数值联合校验
- 失败报告优化

交付：
- expected_rows 支持
- 渠道指标完整结果级校验
- evaluation report 优化

验收：
- 渠道销售额排名每行数值可校验
- ROI 排名每行数值可校验
- CAC 排名每行数值可校验

---

#### Day45

Phase2 中段验收与重构缓冲

目标：对 Day36-Day44 的渠道分析、Query Plan、Intent Parser、Evaluation 做一次阶段验收。

学习内容：
- 回顾新增指标
- 回顾 Query Plan 架构
- 回顾 Evaluation 演进
- 检查代码重复
- 检查 metadata 职责边界
- 梳理技术债

交付：
- Phase2 Midpoint Review
- architecture update
- README / PROJECT_STATE 全量校准
- evaluator 完整报告

验收：
- Golden Cases ≥ 20
- Pass Rate 100%
- ROI / CAC Template 稳定
- Intent Parser V1 可用
- 技术债清单清晰

---

## 开发日志

### Day24

完成：
- 品类销售额分析
- 品类退款率分析
- Business SQL验证

发现：
- 会员等级快照设计不足
- 缺少等级历史表

---

### Day25

完成：
- business_metrics.yaml
- table_dictionary.yaml
- metric_loader.py
- table_loader.py
- semantic_search.py

---

### Day26

完成：
- table_relationships.yaml
- relationship_loader.py
- context_builder.py
- prompt_builder.py

---

### Day27

完成：
- DeepSeek API接入
- sql_generator.py
- sql_cleaner.py

实现：自然语言→ SQL

验证问题：
- 哪个品类退款率最高？
- 哪个品类销售额最高？
均成功生成SQL

---

### Day28

完成：
- SQL Validation
- SQL Execution
- PostgreSQL Runner

实现：自然语言问题 → 业务语义检索 → Prompt 构建 → SQL 生成 → SQL 校验 → PostgreSQL 执行 → 结构化结果返回

问题：
哪个品类退款率最高？
返回：
category = 精华
refund_rate_pct = 10.0

下一步：
Evaluation Framework
Failure Cases
Prompt Optimization

---

### Day29

完成：

- Result Formatter
- SQL → Table
- Golden Questions
- Evaluator
- Evaluation Report
- Failure Case Analysis
- Prompt Optimization V1

实现：

Question
↓
SQL
↓
PostgreSQL
↓
Table
↓
Evaluation

发现问题：

- 模糊问题导致分析维度错误
- category 被错误替换为 product_name

解决：
- 新增 Evaluation V1
- 增加 expected_columns 校验
- Prompt 增加默认 category 规则

结果：
Pass Rate
66.67%
↓
100%

---

### Day30

完成：
- Golden Questions 扩展
- Evaluation V2
- Semantic Search V1
- Alias Search
- Failure Cases 分类

发现问题：
- 业务黑话无法识别
- Alias 可解决部分问题
- Alias 无法无限扩展

解决：
- business_metrics.yaml 增加 aliases
- metric_loader 支持 Alias Match

结果：
Pass Rate：
71.43%
↓
100%

---

### Day31

完成：
- Semantic Search V2 架构设计
- Hybrid Search 方案设计
- Clarification 机制设计
- Metric Embedding Pipeline 设计
- Metric Text Builder 开发

产出：
- semantic_search_v2.md
- metric_embedding_design.md
- metric_text_builder.py

关键收获：Alias Search：

优点：
- 准确
- 可控
缺点：
- 难扩展

Embedding Search：

优点：
- 语义理解能力强
缺点：
- 无法解决业务歧义

因此未来采用： Alias + Embedding + Clarification 的 Hybrid Search方案

---

### Day32

完成：
- BGE Embedding 接入
- Semantic Search V2 实现
- Cosine Similarity 检索实现
- Confidence Score 判断
- Metric Vector Cache 实现

产出：
- embedding_service.py
- semantic_search_v2.py
- vector_store.py

关键收获：
- Embedding：负责语义表达。
- Vector Search：负责检索。
- Confidence：负责判断是否可信。
- Clarification：负责处理业务歧义。

当前系统能力：Alias Search + Embedding Search 已具备独立运行能力。

---

### Day33

完成：
- 新增 Hybrid Search（Alias Search + Embedding Search）
- 新增 Clarification Layer
- 支持语义歧义问题识别
- Context Builder接入Hybrid Search
- Query Service支持needs_clarification状态
- 完成Semantic Layer到Text2SQL主链路打通
- Evaluation回归测试8/8通过

---

### Day34

完成：
- Semantic Search Calibration
- Metric Text 增强
- Confidence 阈值校准
- Search Trace 可解释性增强
- Calibration Report 文档沉淀
- Evaluation 回归测试 8/8 通过

关键调整：
- TOP1_THRESHOLD = 0.50
- GAP_THRESHOLD = 0.08
- hybrid_search.py 只负责 Alias / Embedding / Clarification

新增文档：
- docs/architecture/semantic_search_calibration.md

当前能力：
Question
↓
Alias Search
↓
Embedding Search
↓
Confidence Check
↓
Clarification / Matched
↓
Search Trace

---

### Day35

完成：
- 新增订单数（order_count）指标
- 新增销量（sales_quantity）指标
- 引入 keyword_group 规则匹配
- 支持 TopN 类业务问题
- 扩展 Golden Cases 至 12 条
- Evaluator 保持 100% 通过率

新增 keyword_group 规则匹配

---

### Day36

完成：
- 渠道数据层核对
- 验证 dim_channel 与 fact_marketing_spend 已存在
- 验证渠道营销数据完整性
- 补充 table_dictionary.yaml 中渠道相关表
- 补充 table_relationships.yaml 中渠道关系
- 验证 table_loader 与 relationship_loader 能读取新增元数据
- 新增 channel_sales_amount 指标
- 新增 channel_refund_rate 指标
- 新增 roi 指标
- 修复 Rule Layer 短 alias / 长 alias 冲突
- Prompt Builder 增加跨事实表先聚合再 JOIN 规则
- Prompt Builder 修正 ROI 不乘以 100
- Prompt Builder 增加 ROI 重叠日期窗口规则
- Golden Cases 扩展到 18 条
- Evaluator 18/18 通过

实现：

自然语言
↓
Rule Layer / Embedding Search
↓
Context Builder
↓
Prompt Builder
↓
DeepSeek
↓
SQL Cleaner
↓
SQL Validator
↓
PostgreSQL
↓
Table
↓
Evaluation

新增支持问题：
- 哪个渠道销售额最高
- 各渠道销售额排名
- 哪个渠道退款率最高
- 各渠道退款率排名
- 哪个渠道ROI最高
- 各渠道ROI排名
- 哪个渠道投放最划算

关键结果：

渠道销售额最高：
- 天猫
- channel_sales_amount = 2445170.92

渠道退款率最高：
- 抖音
- channel_refund_rate_pct = 6.86

渠道 ROI 最高：
- 天猫
- roi ≈ 1.68

发现问题：
1. table_dictionary.yaml 和 table_relationships.yaml 未包含渠道表，导致语义层无法使用渠道数据。
2. business_metrics.yaml 未定义渠道指标，导致“哪个渠道销售额最高”触发 clarification。
3. “哪个渠道退款率最高” 同时命中 refund_rate 与 channel_refund_rate。
4. ROI 初始 SQL 直接 JOIN fact_orders 与 fact_marketing_spend，导致多对多行膨胀。
5. ROI 曾被错误乘以 100。
6. ROI 曾未使用订单与营销投放的重叠时间窗口。
7. Evaluator 暴露出字段别名不稳定问题。

解决：
1. 补充渠道表元数据与关系。
2. 新增渠道销售额、渠道退款率、ROI 指标。
3. metric_loader.search_metrics 增加 match_score，优先保留更具体 alias。
4. Prompt Builder 增加跨事实表指标规则。
5. Prompt Builder 明确 ROI 不乘以 100。
6. Prompt Builder 明确 ROI 使用重叠日期窗口。
7. Prompt Builder 明确字段别名优先使用指标技术名。

结果：

Golden Dataset：
12 Cases
↓
18 Cases

Pass Rate：
100%

---

### Day37

完成：
- CAC 指标建设
- CAC 手写 SQL 验证
- 明确真实首单新客口径
- 新增 cac 指标
- query_service 支持渠道获客成本问题
- Golden Cases 扩展至 20 条
- Evaluator 保持 100% PASS
- 新增 Result-level Evaluation V1
- 新增 Ranking Result Evaluation V1
- 新增 expected_result 校验
- 新增 expected_order 校验
- 新增 Metric Query Plan V1 设计
- 新增 metadata/query_plans.yaml
- 完成 roi_channel_v1 与 cac_channel_v1 读取验证

实现：

自然语言
↓
Hybrid Search
↓
Context Builder
↓
Prompt Builder / Query Plan Metadata
↓
SQL Generator
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

新增支持：
- 哪个渠道获客成本最低
- 各渠道获客成本排名
- 哪个渠道拉新效率最高

关键结果：
CAC 最低渠道：
- 天猫
- cac = 2284.40

CAC 排名：
- 天猫
- 微信小程序
- 京东
- 抖音
- 小红书

发现问题：
1. CAC 不能简单使用 COUNT(DISTINCT customer_id)。
2. CAC 不能使用窗口内首单，应使用真实首单新客。
3. ROI / CAC 复杂 SQL 多次暴露 Prompt-only 不稳定。
4. 结构级 Evaluation 无法证明业务答案正确。
5. 排名类问题需要校验返回顺序。

解决：
1. CAC 采用真实首单新客口径。
2. prompt_builder 增加 CAC 首单口径约束。
3. evaluator 增加 expected_result。
4. evaluator 增加 expected_order。
5. 新增 query_plans.yaml，开始将复杂指标 SQL 计划结构化。

结果：
Golden Dataset：
18 Cases
↓
20 Cases

Evaluation：
结构级检查
↓
结构级 + 结果级 + 排名顺序检查

Pass Rate：100%

---

### Day38

完成：
- 新增 query_plan_loader.py
- metadata/query_plans.yaml 接入 loader
- 新增 template_sql_generator.py
- 实现 ROI Template SQL
- 实现 CAC Template SQL
- 实现 parse_limit 与 build_limit_clause
- 支持 Top1 / TopN / Ranking
- 实现 generate_template_sql 统一入口
- query_service 接入 Query Plan Routing
- ROI / CAC 走 template
- 普通指标继续走 llm
- query_service 返回 generation_method
- 新增 template_sql_tests.py
- evaluator 增加 expected_generation_method
- Evaluator 20/20 通过

实现：
  Question
  ↓
  Hybrid Search
  ↓
  Metric Name
  ↓
  Template Routing
  ├─ roi / cac → Template SQL
  └─ ordinary metrics → LLM SQL
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

新增支持：
- 渠道ROI Top3
- 获客成本最低的三个渠道
- ROI / CAC template generation
- generation_method validation

关键结果：

Template SQL Tests：
- 12/12 PASS

Golden Dataset：
- 20 Cases
- 100% PASS

发现问题：
1. 仅用 should_limit_one 无法支持 TopN。
2. “最低的三个渠道” 不能被误判为 LIMIT 1。
3. query_plans.yaml 与 template_sql_generator.py 之间存在一定重复，但当前阶段是合理过渡。
4. 需要验证 ROI / CAC 确实走 template，而不是 LLM 恰好生成正确 SQL。

解决：
1. 用 parse_limit 替代 should_limit_one。
2. 明确数量表达优先于极值表达。
3. 增加 generate_template_sql 统一入口。
4. query_service 增加 generation_method。
5. evaluator 增加 expected_generation_method。

结果：
- Query Plan Routing 已接入主链路。
- ROI / CAC 已从 Prompt-only 生成升级为 Template SQL。
- 普通指标保持 LLM 生成。
- Evaluator 保持 100% PASS。
