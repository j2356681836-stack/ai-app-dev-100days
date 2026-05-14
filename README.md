# AI App Dev 100 Days

100 天 AI 应用开发转型计划记录

## 核心技术栈
- 大模型 API (OpenAI / Anthropic)
- Pydantic (数据校验与结构化)
- PostgreSQL + pgvector (数据层与向量检索)
- FastAPI (后端与流式传输)

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
- [ ] 阶段二：动态上下文与混合检索层 (Day 21-50)
- [ ] 阶段三：原生 Agent 编排与工具调用 (Day 51-70)
- [ ] 阶段四：流式全栈体验与云原生高可用 (Day 71-100)