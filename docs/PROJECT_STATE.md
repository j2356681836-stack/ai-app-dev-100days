# AI-Architect-100Days

# 长期目标


100 天内完成：

- 企业级 LLM Reliability

- Business Semantic Layer

- Text-to-SQL

- LangGraph Agent

- Eval-Driven Development

- FastAPI Deployment

最终目标：

成为可就业的 GenAI Engineer / AI Agent Engineer

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
## 已完成（Phase 1）

### API Reliability

- AsyncOpenAI
- asyncio.gather
- Semaphore concurrency control
- tenacity retry
- structured outputs
### Data Validation

- Pydantic V2
- field_validator
- nested schema validation
- self-healing JSON repair
### Observability

- Langfuse tracing
- parent-child spans
- token monitoring
- tagging
---
## 当前阶段

第二阶段：Business Semantic Layer + Text-to-SQL

---
## 当前系统状态

当前已完成：
### 基础设施

- Docker 化 PostgreSQL + pgvector
    
- SQLAlchemy 2.0 数据连接
    
- Synthetic Business Dataset
    
- Beauty BI Schema
    
### AI Reliability

- Structured Outputs
    
- Pydantic V2 强校验
    
- Retry + Self-healing
    
- Langfuse Observability
    
---
### 当前核心方向

正在构建：

Retrieval-Augmented Text-to-SQL System

重点包括：

- Schema Retrieval
    
- Business Metric Retrieval
    
- SQL Safety Validation
    
- Hallucination Prevention

---
## 当前架构演进

项目当前正在从**phase/day 学习结构**逐渐演进为**企业级模块化工程结构**

目标结构：
	app/  
	├── db/  
	├── semantic_layer/  
	├── text_to_sql/  
	├── agents/  
	├── api/  
	└── evaluation/

其中：
- phase 目录保留学习实验记录
    
- app 目录作为正式系统核心

---
## 当前技术栈

### Backend

- Python 3.12
- FastAPI（准备接入）

### AI Stack

- OpenAI SDK
- Langfuse
- Pydantic V2

### Database（Phase 2）

- PostgreSQL + pgvector
- SQLAlchemy 2.0
- Synthetic Business Dataset
- Beauty BI Schema

---

## 当前数据库:

- 100 products
- 2000 customers
- 20000 orders
- 29051 order items
- 2008 refunds
- 5000 reviews
- 180 days marketing spend

业务规律植入:

- 夏季防晒销售额增长
- 小红书渠道投放费用上涨
- 精华退款率更高
- 会员用户复购行为增强

---
## 当前目标

构建企业级 AI BI Agent：

- 用户输入自然语言 ->
- 检索业务 schema ->
- 动态生成 SQL ->
- 执行 SQL ->
- 返回业务分析结果

---
## 当前重点问题

- 如何构建 business semantic layer
- 如何提升 retrieval precision
- 如何做 SQL safety
- 如何避免 hallucination

---
## 当前阶段交付物

目标：

企业级 Text-to-SQL 系统

---
发现：
会员复购增强规律未被当前数据集有效体现。

原因：
当前仅保存会员等级快照，
缺少会员等级变更历史；
同时订单生成逻辑未显著拉开各等级购买频次差异。

后续：
重构 seed.py，
增加会员等级升级逻辑和等级历史表。

---
### Day 24 业务指标验证与业务语义理解

完成内容：

- 品类销售额分析 SQL
- 品类退款率分析 SQL
- 理解 Fact / Dimension 数据模型
- 理解 INNER JOIN 与 LEFT JOIN 在业务统计中的区别

业务规律验证：

- 成功验证：
  - 精华类商品退款率显著高于其它品类（约10%，其它品类约4.5%）

- 未成功验证：
  - 当前数据集未能有效体现“会员用户复购行为增强”

发现问题：

- 当前会员等级仅保存最新快照
- 缺少会员等级历史表
- 会员等级与订单行为关联度不足

核心认知：

- SQL正确 ≠ 业务口径正确
- 业务口径正确 ≠ 指标有分析价值

下一步：

- 构建第一版 Business Semantic Metadata
- 建立 business_metrics.yaml
- 开始 Schema Retrieval 原型开发

---
### Day 25 Semantic Layer Metadata Foundation

完成内容：

- 建立 business_metrics.yaml
- 建立 table_dictionary.yaml
- 定义指标元数据结构：
  - name
  - chinese_name
  - grain
  - source_field
  - definition
  - formula
  - tables
  - filters

完成组件：

- metric_loader.py
  - load_metrics()
  - get_metric_by_name()
  - search_metrics()

- table_loader.py
  - load_tables()
  - get_table_by_name()
  - search_tables()

- semantic_search.py
  - Semantic Search V0

实现能力：

- Metric Retrieval
- Schema Retrieval

核心认知：

- 同一业务指标可能存在多个业务口径
- 指标定义需要结构化存储
- Text-to-SQL 应建立在 Retrieval 之上，而非直接生成 SQL

下一步：

- Context Builder
- Retrieval-Augmented Text-to-SQL

---
## Day26（语义层与 Prompt Builder）

### 已完成

#### 元数据建设

新增：

- metadata/business_metrics.yaml
- metadata/table_dictionary.yaml
- metadata/table_relationships.yaml

完成业务指标、数据表、表关系的结构化定义。

---

#### Loader 模块

完成：
- metric_loader.py
- table_loader.py
- relationship_loader.py

支持：
- 指标加载
- 指标检索
- 表加载
- 表检索
- 表关系加载

---

#### Semantic Search

完成：semantic_search.py

实现：

用户问题
→ 指标检索
→ 数据表检索

---

#### Context Builder

完成：

context_builder.py

实现自动构建业务上下文：

- 指标定义
- 指标公式
- 表说明
- 字段说明
- 表关联关系

---

#### Prompt Builder

完成：

prompt_builder.py

生成标准 Text-to-SQL Prompt：

用户问题
+
业务上下文
+
SQL生成规则

---

### 当前能力

已实现：

自然语言问题
→ 业务语义检索
→ 上下文构建
→ Prompt生成

下一步：

Prompt
→ LLM
→ SQL生成