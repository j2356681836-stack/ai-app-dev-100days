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

当前日期：Day35 / 100

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

当前能力：

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

---
## 当前系统架构

Question
↓
Hybrid Search
├─ Alias Match
├─ Embedding Match
└─ Clarification
↓
Context Builder
↓
Prompt Builder
↓
SQL Generator
↓
SQL Runner

---
## 当前待办（Next Milestone）

### Day36-Day40 规划

目标：渠道分析能力建设

新增数据表：
- dim_channel
- fact_marketing_spend

新增业务指标：
- channel_sales_amount（渠道销售额）
- channel_refund_rate（渠道退款率）
- roi（投资回报率）
- cac（获客成本）

---

#### Day36

渠道维度建模

学习内容：
- dim_channel 表结构分析
- fact_marketing_spend 表结构设计
- 渠道分析场景理解
交付：
- 渠道数据字典
- 渠道指标定义文档

---

#### Day37

渠道销售分析

新增指标：
- channel_sales_amount
- channel_refund_rate
支持问题：
- 哪个渠道销售额最高
- 哪个渠道卖得最好
- 哪个渠道退款率最高
交付：
- business_metrics.yaml 扩展
- Golden Cases 扩展

---

#### Day38

ROI 指标建设

新增指标：ROI
计算逻辑：ROI = 销售额 / 营销成本
支持问题：
- 哪个渠道 ROI 最高
- 哪个渠道投放最划算
交付：
- ROI SQL 模板
- ROI 指标定义

---

#### Day39

CAC 指标建设

新增指标：CAC
计算逻辑：CAC = 营销成本 / 获客客户数
支持问题：
- 哪个渠道获客成本最低
- 哪个渠道拉新效率最高
交付：
- CAC SQL 模板
- CAC 指标定义

---

#### Day40

渠道分析能力验收

新增 Golden Cases：
- 渠道销售额
- 渠道退款率
- ROI
- CAC

目标：
- Evaluator 100%通过
- 渠道分析闭环完成

---

### Day41-Day45 规划

目标：Intent Parser V1

从“指标识别”升级为“业务意图识别”。

识别内容：
- Metric
- Dimension
- Ranking

示例：
销售额Top5品类
解析为：
{
  "metric": "item_sales_amount",
  "dimension": "category",
  "ranking": {
    "type": "top",
    "value": 5
  }
}

交付：
- Intent Schema
- Intent Parser V1
- TopN 解析能力
- Ranking 解析能力

---

### Day46-Day50 规划

目标：Phase2 收尾与验收
完善：
- Hybrid Search
- Intent Parser
- Golden Dataset
- Evaluator
形成完整闭环：
自然语言
↓
业务语义识别
↓
指标识别
↓
维度识别
↓
SQL生成
↓
SQL执行
↓
结果返回

目标：
- Golden Cases ≥ 30
- Evaluator 稳定运行
- Phase2 验收完成

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

