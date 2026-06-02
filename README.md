# AI-Architect-100Days

一个从零构建的企业级 AI BI Agent 项目。

目标是在 100 天内完成：

- Business Semantic Layer
    
- Retrieval-Augmented Text-to-SQL
    
- LangGraph 多 Agent 编排
    
- Eval-Driven AI Engineering
    
- 企业级可观测性与可靠性体系
    

最终构建：

“自然语言 → SQL → 企业业务分析”的 AI 数据分析系统。

---

## 当前系统架构

用户自然语言提问  
↓  
Business Semantic Retrieval  
↓  
检索相关 Schema 与业务指标定义  
↓  
Text-to-SQL 动态生成  
↓  
PostgreSQL + pgvector  
↓  
业务分析结果返回

当前核心组件：

- PostgreSQL + pgvector
    
- SQLAlchemy 2.0
    
- Structured Outputs
    
- Pydantic V2
    
- Langfuse
    
- Synthetic Beauty BI Dataset

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

## 当前业务数据集

项目当前已构建企业级美妆业务模拟数据集：

### 当前数据规模

- 100 个商品
- 2000 个用户
- 20000 个订单
- 29051 条订单商品
- 2008 条退款记录
- 5000 条用户评价
- 180 天营销投放数据

### 已植入业务规律

- 夏季防晒销量增长
- 小红书 ROI 逐渐下降
- 精华类商品退款率更高
- 会员用户复购行为增强

该数据集并非随机生成，而是主动植入业务规律，  用于后续系统能力验证：
- Text-to-SQL
- Business Semantic Layer
- Retrieval Evaluation
- AI BI Agent

---
## 当前阶段进度

第二阶段：Business Semantic Layer + Text-to-SQL
### 当前核心方向

正在构建：Retrieval-Augmented Text-to-SQL System
重点包括：

- Schema Retrieval
- Business Metric Retrieval
- SQL Safety Validation
- Hallucination Prevention

---
## 当前已完成能力

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
## 当前目标

构建企业级 AI BI Agent：

- 用户输入自然语言 ->
- 检索业务 schema ->
- 动态生成 SQL ->
- 执行 SQL ->
- 返回业务分析结果

---

## 阶段进度

- [ ] 阶段一：API 确定性、鲁棒性与可观测性 (Day 1-20)

    - Day 1 ：创建环境

    - Day 2 ：原生 JSON 模式的陷阱

        - Key 缺失导致代码崩溃。解决方案：使用 `.get()` 而不是直接 `[]` 寻址

        - 大模型喜欢加markdown/思考链，通过正则函数进行清洗

    - Day 3 ：Pydantic 模型转换为 JSON Schema

        -（pydantic.dev/docs/validation/api/pydantic/fields/）

        - Field 的用法

        - description 是进一步给大模型描述字段的定义/输出标准

    - Day 4 : Field Validators进行数据清洗。

        -（pydantic.dev/docs/validation/api/pydantic/functional_validators）

        - Annotated/装饰器两种写法的区别

        - before/after的区别

        - 自定义ValueError

    - Day 5 : Model Validators

        -（pydantic.dev/docs/validation/api/pydantic/functional_validators）

        - Model Validators下可以访问所有字段

        - 不在Enum枚举列表中的会被大模型拦截

    - Day 6 :

        - raise:拉响警报，中断代码，报告错误； return：继续执行，最后报错，难以排查

        - API 本身没有记忆。控制循环时，重试需要在原来的信息上追加（append）消息到上下文中

        - 传给大模型的content必须是字符串，不能是python对象

        - 遇到项目：1.先写框架；2.状态流转图；3.破坏和默写 。理清逻辑后再去落实语法

        - 强类型约束高于自然语言提示词。结构化输出（Structured Outputs）底层机制中Pydantic Schema 的权重远远高于 System Prompt（系统提示词）。在处理大模型幻觉时：

            - 1.增加泄洪口；

            - 2.进行拦截；

            - 3.把约束条件写进 Pydantic 的 Field中，强制转换成 JSON Schema 规则。

        - 大模型只做客观提取，业务逻辑留在代码库里

    - Day 7 :

        - 类可以作为参数传递给函数

        - 对不同类型的内容进行处理

    - Day 8 ：异步并发 (asyncio)

        - 同步：一个任务完成再执行第二个，等待耗时长；异步：将多个任务同时进行

        - 所有的网络请求操作，都必须被 await 标记

        - 在 Windows 环境下跑异步程序，退出时会遇到 Event loop is closed 报错，通过引入asyncio.WindowsSelectorEventLoopPolicy()把底层的异步发动机从默认的V8降级成V6解决

        - 通过asyncio.gather()将多组任务打包成并发任务

        - 通过if __name__ == "__main__"设置隔离，防止在import时直接触发执行调用大模型消耗token，加了隔离仅引入工具不会触发执行

    - Day 9 ：Semaphore与Tenacity，异步并发的限制

        - Semaphore(1)一个任务结束再到下一个，相当于同步

        - 异步最大并发数（Semaphore 的大小）阈值边界取决于客户端和服务端中最弱的一环

    - Day 10-14 : 异步高并发与确定性提取管线

        - 放弃了传统的批处理模式，采用**单条数据生命周期管线 (Lifecycle Pipeline)**。每条输入文本在独立的协程中完成“双路并发请求 -> 内存组装 -> 抢占锁 -> 异步流式落盘”的完整闭环，确保内存占用极低且吞吐量最大化。

        - 核心技术栈与防御机制

            - **Pydantic V2:** 锁死大模型输出 Schema，提供细粒度校验。

            - **Semaphore 限流:** 限制最大并发数为 10，避免触发大模型厂商 429 封禁。

            - **Tenacity 指数退避:** 针对 `ValidationError` 与网络异常，执行最高 5 次、延迟递增的自动重试。

            - **Lock 互斥写:** 引入 `asyncio.Lock` 保护 `aiofiles` 落盘动作。

        - 破坏性压测结论 (Chaos Testing)

            - 在关闭互斥锁、并发量 40、总数据量 800 条的极端压测下，系统出现严重的 JSON 字节交错与解码失败 (`JSONDecodeError`)。

            - 引入互斥锁后，在同等压力下，系统实现 100% 结构化数据完整落盘，性能损耗（微秒级）可忽略不计。

    - Day 15 : 可观测性基石

        - **监控架构：** 废弃原生 OpenAI 客户端，引入 Langfuse Wrapper (`langfuse.openai`) 拦截底层请求。

        - **链路追踪 (Tracing)：** 利用 `@observe()` 装饰器，实现异步并发环境下的父子链路绑定 (`single_text` -> 并发双路 `reflection` -> `LLM`)，解决并发请求日志交错导致无法溯源的问题。

        - **核心指标：** 实现 Prompt 文本、Token 开销、USD 成本及毫秒级 Latency 的 100% 云端可视化。

  

    ### Phase 1 结项：生产级大模型 ETL 引擎

    本阶段构建了一个具备“防御能力”和“数据强校验”的异步并发提取系统。

  

    * **工程极限压测：** 投入 120 条包含复杂情绪与混乱数学逻辑的美妆用户长文本。

    * **数据拦截率：** 成功提取并落盘 104 条。精准拦截 16 条财务逻辑悖论数据（如打折后总价不符），证明 Pydantic Validator 的阻断机制 100% 可靠。

    * **可观测性 (Langfuse V4)：** 采用 `propagate_attributes` 实现异步协程下的业务标签隔离。成功捕获大模型在遭遇 Schema 错误时的 `Retry -> Self-Correction -> Success` 完整反思链路。

    * **结论：** 成功将大模型从“随机文本生成器”规训为“带强类型约束的 JSON 函数”。

- [ ] 阶段二：动态上下文与混合检索层 (Day 21-50)

## Phase 2: 业务语义层与 Eval 驱动的混合检索 (Day 21-50)

  
### 架构痛点与重构决策

在构建美妆领域的 Text-to-SQL Agent 时，企业数据库动辄包含 500+ 张表和上万个隐性业务规则（如：“高客单价”到底指大于 500 还是 1000？）。

* **被遗弃方案：** 将所有 DDL 和业务口径硬编码进 System Prompt。这不仅会瞬间打爆 Token 上限，还会导致大模型产生严重的 SQL 拼接幻觉。

* **当前架构 (RAG + SQL)：** 引入带 `pgvector` 扩展的 PostgreSQL 作为统一的“向量化数据字典”。


### 基础设施落地

* 利用 Docker Compose 实现 `ankane/pgvector:latest` 容器化部署（PostgreSQL 15.4）。

* 跑通 Python 异步/同步驱动与本地容器的网络直连，成功在数据库内部注册 `vector` 扩展，为后续美妆业务黑话的向量化存储（Embedding）打下基石。

### 已完成业务规律验证：

- 精华类商品退款率约为其它品类的 2 倍以上
- 已发现会员复购规则在当前数据模型下存在验证困难，后续将引入会员等级历史建模

### Semantic Layer (In Progress)

## 当前进度

### 已完成

#### 数据层

- PostgreSQL 环境搭建
- 星型模型建模
- 模拟业务数据生成

#### SQL分析层

- 销售分析
- 退款分析
- 用户分析

#### 语义层（Semantic Layer）

完成：
- 业务指标元数据管理
- 数据表元数据管理
- 表关系元数据管理

支持：
- 指标检索
- 表检索
- 关系检索

实现：

用户问题
→ Semantic Search
→ Context Builder
→ Prompt Builder

---

### 下一阶段

Day27：
实现 SQL Generator V0

目标：
自然语言问题
→ LLM
→ PostgreSQL SQL


- [ ] 阶段三：原生 Agent 编排与工具调用 (Day 51-70)

- [ ] 阶段四：流式全栈体验与云原生高可用 (Day 71-100)
