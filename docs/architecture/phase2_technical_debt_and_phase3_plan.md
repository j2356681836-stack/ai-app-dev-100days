# Phase2 Technical Debt and Phase3 Plan

## 背景

Phase2 已经完成 AI Data Analyst / Text-to-SQL 主链路，并形成了较完整的 Evaluation Workflow V1。

当前系统已经具备：
Business Semantic Layer
Intent Parser / Intent Resolver
Hybrid Search
Query Plan Routing
Template SQL / LLM SQL 双路径
SQL Cleaner / SQL Validator
PostgreSQL Execution
Answer Layer V1
Deterministic Evaluator
Answer Judge
Ragas Evaluation

但 Phase2 还不是一个完整可落地的企业级 AI Data Analyst 产品。

当前项目已经可以证明：
自然语言问题可以经过业务语义层生成 SQL
SQL 可以执行并返回结构化结果
结果可以转成中文回答
系统可以通过多层 Evaluation 进行质量验证

但仍然存在多类技术债和产品能力缺口。

本文件用于统一记录：
1. Phase2 当前遗留问题
2. 当前影响
3. 当前规避方式
4. 是否必须在 Phase2 解决
5. 后续 Phase3 / Phase4 承接计划

核心原则：
阶段内没有解决的问题，不能靠记忆留着。
要么当日解决，要么写入技术债，要么放入后续计划。

---

# 总体判断

当前 Phase2 的重点是证明：
业务语义层 + Text-to-SQL + Evaluation Workflow

这条主线可行。

Phase2 不应该在最后几天继续大规模扩展数据集、指标体系或重构主链路。

更合理的策略是：
Phase2 Day48-Day50：
- 完成架构复盘
- 完成技术债登记
- 完成面试表达
- 完成 Phase3 交接

Phase3：
- 引入 LangGraph / workflow
- 在 workflow 中逐步解决 retrieval、clarification、retry、repair、analysis 等问题

Phase4：
- 完善数据集、指标体系、dashboard、部署和产品化能力

---

# 技术债分级

## P0：必须记录，Phase2 收尾前要明确

这类问题不一定要马上修，但必须明确进入文档和后续计划。
1. Semantic Retrieval Calibration
2. Dataset & Business Realism
3. Metric System 扩展
4. Evaluation Coverage 扩展
5. Phase3 LangGraph 承接路径

## P1：Phase3 优先处理

这类问题会影响系统从 Text-to-SQL demo 升级为 AI Data Analyst workflow。
1. Retrieval Eval Dataset
2. Retrieval Evaluator
3. Clarification Loop
4. Eval-driven retry / repair
5. 普通指标 lightweight query_plan
6. Answer / Insight Layer 升级

## P2：Phase4 或产品化阶段处理

这类问题重要，但不适合在 Phase2 最后几天解决。
1. Beauty Dataset V2 完整建设
2. Dashboard / Chart / Streamlit
3. 更真实的业务分析
4. 更多 BI 指标体系
5. 多租户 / 权限 / 部署 / 可观测性

---

# 1. Semantic Retrieval / Embedding Calibration Debt

## 当前问题

Phase2 中曾发现：多个指标 embedding score 偏低，top1 与 top2 的 gap 偏小
这说明当前 embedding search 对部分业务指标的区分度不足。

尤其在以下场景中风险较高：
用户问题较短
业务表达模糊
指标之间语义接近
alias / keyword_group 没有直接命中

例如：
最赚钱
哪个渠道最划算
拉新效率最高
退货最严重

这类问题不能仅凭 embedding 相似度直接决定指标。

---

## 当前影响

如果 embedding 判断不稳定，可能导致：
1. 错选 metric
2. 错误进入 SQL 生成
3. 返回不符合业务语义的结果
4. 用户以为系统理解了问题，但实际指标口径错误

这类错误比 SQL 语法错误更危险，因为 SQL 可能能跑通，但业务含义是错的。

---

## 当前规避方式

当前系统没有让 embedding 成为唯一决策层。

当前 Hybrid Search 策略是：
Alias Match
↓
Keyword Group Match
↓
Embedding Search
↓
Confidence / Gap 判断
↓
Clarification

当前保护机制：
1. rule layer 优先
2. alias / keyword_group 命中明确时优先使用规则结果
3. embedding 只作为规则无法覆盖时的语义召回增强
4. top1 score 不足时不直接采用
5. top1 / top2 gap 不足时不直接采用
6. 低置信度或候选接近时进入 clarification

当前定位：Embedding 是受控 fallback，不是唯一 truth source。

---

## 为什么 Phase2 不立即彻底解决

原因：
1. 当前核心 Golden Cases 已稳定通过
2. 当前主链路已有 rule layer 和 clarification 保护
3. Phase2 剩余时间有限
4. 大规模调整 embedding / threshold 可能引发新回归
5. 该问题更适合通过独立 retrieval eval dataset 系统校准

---

## 后续计划

Phase3 应新增：
app/evaluation/retrieval_eval_cases.py
app/evaluation/retrieval_evaluator.py

评估内容：
用户问题
expected_metric
expected_search_type
expected_clarification
top1_score
top2_score
gap
matched_metric

后续校准目标：
1. 系统校准 TOP1_THRESHOLD
2. 系统校准 GAP_THRESHOLD
3. 评估 metric_text_builder 文本质量
4. 记录 alias / keyword_group / embedding / clarification 的命中效果
5. 明确哪些问题必须 clarification

---

# 2. Dataset & Business Realism Debt

## 当前问题

当前 V1 美妆数据集可以支撑 Phase2 Text-to-SQL 主链路验证，但不足以支撑一个完整可落地的 AI Data Analyst 产品。

当前数据集主要证明：
SQL 查询链路可行
指标计算可行
业务规律可以被查询到
Evaluation 可以验证结果

但数据真实性和业务复杂度仍有限。

---

## 当前不足

当前数据层存在以下不足：
1. 会员等级历史缺失
2. 用户生命周期数据不足
3. 复购行为不够丰富
4. 留存分析支撑不足
5. LTV 分析支撑不足
6. 商品生命周期不足
7. 渠道转化链路较粗
8. 营销投放与转化归因较弱
9. 缺少库存 / 毛利 / 利润数据
10. 缺少更真实的活动 / 大促 / 季节性冲击

当前业务规律主要包括：
夏季防晒销量增长
精华退款率显著较高
小红书 ROI 持续下降
会员用户购买频率更高

这些规律适合验证系统功能，但还不足以支持复杂业务分析。

---

## 当前影响

当前系统更偏向：AI 查数助手

还没有完全达到：AI Data Analyst

原因是 AI Data Analyst 不只是查指标，还需要支持：
趋势分析
归因分析
人群分析
复购分析
渠道效率分析
商品生命周期分析
经营建议

而这些能力需要更丰富的数据基础。

---

## 为什么 Phase2 不立即重建数据集

原因：
1. 数据集重建会影响已有 Golden Cases
2. 会引发 metadata、metrics、query_plans、eval cases 连锁更新
3. Phase2 当前重点是 Text-to-SQL 架构与 Evaluation
4. Beauty Dataset V2 更适合作为 Phase3 / Phase4 的独立设计

---

## 后续计划

后续应设计：Beauty Dataset V2

原则：
1. 不直接覆盖当前 V1
2. 使用独立 schema 或独立 seed 版本
3. 保留 V1 用于稳定回归
4. V2 用于更真实的 Agent 分析能力

V2 应重点增强：
用户生命周期
会员等级历史
复购 / 留存 / LTV
商品生命周期
渠道漏斗
活动营销
毛利 / 利润
库存
经营异常

---

# 3. Metric System / Business Semantic Layer Debt

## 当前问题

当前指标体系已经覆盖 Phase2 主链路所需的核心指标：
item_sales_amount
order_paid_amount
refund_rate
order_count
sales_quantity
channel_sales_amount
channel_refund_rate
roi
cac

但距离真实 BI / AI Data Analyst 项目仍然不足。

---

## 当前缺少的指标类型

后续可扩展：
GMV
实付 GMV
净销售额
客单价
转化率
复购率
留存率
LTV
ARPU
新客数
老客数
新老客占比
会员等级分布
会员升级率
商品动销率
商品毛利率
库存周转
利润
渠道转化漏斗
活动 ROI
投放转化率
退款金额
退款订单数
评价满意度
差评率

---

## 当前影响

当前指标足以支撑：
销售
退款
渠道 ROI
CAC
TopN / Ranking

但不足以支撑：
完整经营分析
用户增长分析
会员运营分析
商品生命周期分析
渠道漏斗分析
利润分析

因此当前系统可以展示 AI Data Analyst 的核心技术链路，但还不是完整企业经营分析平台。

---

## 后续计划

Phase3 / Phase4 应逐步扩展 metric system：
1. 先扩展用户与会员指标
2. 再扩展复购 / 留存 / LTV
3. 再扩展商品生命周期
4. 再扩展渠道漏斗
5. 最后扩展利润 / 库存 / 经营诊断

指标扩展时必须同步更新：
business_metrics.yaml
table_dictionary.yaml
table_relationships.yaml
query_plans.yaml
golden_questions.py
evaluation cases
answer templates

原则：每扩展一个指标，必须同时扩展 Evaluation。

---

# 4. Query Plan / SQL Generation Debt

## 当前问题

当前 Query Plan 主要覆盖：ROI / CAC
普通指标仍然走：LLM SQL with Intent Context

这在 Phase2 是合理的，但仍存在技术债。

---

## 当前不足

普通指标缺少 lightweight query_plan，因此：
1. 普通指标 sort_field 通常为 None
2. 普通指标 default_sort 仍部分依赖 LLM 语义理解
3. 普通指标 allowed_dimensions 没有统一结构化配置
4. 普通指标 allowed_filters 没有统一配置
5. Prompt 中仍需要维护较多普通指标规则

---

## 当前影响

普通指标目前通过：
Intent Context
Prompt Builder rules
Evaluator

维持稳定。

但随着指标数量增加，继续依赖 prompt rules 会导致：
Prompt 越来越长
规则重复维护
LLM 行为更难预测
普通指标排序方向不够统一

---

## 后续计划

Phase3 或 Phase4 应考虑：lightweight query_plan for ordinary metrics

不是把普通指标全部模板化，而是把以下信息结构化：
metric_name
default_sort
allowed_dimensions
allowed_filters
required_tables
output_alias
value_format

目标：普通指标继续走 LLM SQL，但让 LLM 受到更明确的 query plan 约束。

---

# 5. Intent Parser / Intent Resolver Debt

## 当前问题

当前 Intent Parser V1 是规则型实现。

支持：
limit
ranking_type
sort_hint
dimension

当前 Intent Resolver 支持：
final_sort_direction
sort_field

但规则覆盖仍有限。

---

## 当前不足

当前可能缺少：
更多中文 TopN 表达
更多比较类表达
更多时间范围表达
更多过滤条件表达
更多维度表达
多意图问题
复杂约束问题

例如：
最近三个月哪个渠道 ROI 下降最快
618 期间哪个品类退款最多
会员用户复购率最高的品类
新客贡献最高的渠道

当前 Intent Parser V1 不足以稳定解析这些问题。

---

## 后续计划

Phase3 中，Intent Parser 可以继续作为确定性节点存在，但应逐步增强：
1. 时间范围解析
2. filter 条件解析
3. comparison intent
4. trend intent
5. analysis intent
6. clarification intent

在 LangGraph 中，Intent Parser 可以作为第一个节点，并在低置信度时进入 clarification。

---

# 6. Prompt Builder V2 Debt

## 当前问题

Prompt Builder V2 已完成代码模块化，但仍存在维护风险。

当前结构：
build_prompt()
├─ build_intent_context()
├─ build_global_rules()
├─ build_field_alias_rules()
├─ build_ranking_rules()
├─ build_dimension_rules()
├─ build_legacy_complex_metric_rules()
└─ build_sql_generation_rules()

Day46 说明：Prompt 输出形态会影响 LLM 行为。

---

## 当前不足

当前仍存在：
1. build_global_rules 和 build_sql_generation_rules 部分规则重复
2. prompt_builder_tests 还可以补充“不编造状态值 / 枚举值”的专项断言
3. ROI / CAC legacy rules 仍保留在 Prompt 中
4. Prompt 规则仍偏硬编码

---

## 当前规避

当前采用：
代码内部模块化
最终 prompt 输出形态尽量保持稳定
prompt_builder_tests + evaluator 双层回归

---

## 后续计划

Phase2 收尾前可考虑补一个低风险测试：
prompt_builder_tests 增加“不编造状态值 / 枚举值”断言

Phase3 / Phase4 后续再考虑：
Prompt rule registry
config-driven prompt rules
普通指标 query_plan 下沉更多规则

---

# 7. Answer Layer / Business Insight Layer Debt

## 当前问题

当前 Answer Layer V1 是规则型事实回答。

支持：
Top1
TopN
Ranking
ASC / DESC
百分比展示
基于 table 的事实型回答

当前原则：
只基于 SQL table 回答
不编造原因
不做未经验证的业务推断

---

## 当前不足

当前 Answer Layer 不支持：
原因分析
趋势解释
策略建议
多指标综合分析
图表解释
异常归因
经营诊断

因此当前系统更像：AI 查数助手
还不是完整：AI 业务分析师

---

## 为什么 Phase2 不直接做 Insight Layer

原因：
1. 当前数据集不足以支撑可靠归因
2. 当前指标体系还不够完整
3. 直接让 LLM 解释原因容易幻觉
4. Insight Layer 需要更强 Evaluation 支撑

---

## 后续计划

Phase3 / Phase4 可设计：
Business Insight Layer

但必须遵守：
1. 所有结论必须基于可验证数据
2. 原因分析必须区分“数据事实”和“可能假设”
3. 策略建议必须有指标支撑
4. Insight 也必须进入 Evaluation

---

# 8. Evaluation System Debt

## 当前能力

当前 Evaluation Workflow V1 包括：
Deterministic Evaluator
Prompt Builder Tests
Answer Judge
Ragas Evaluation

当前结果：
evaluator.py：26/26 PASS
prompt_builder_tests.py：5/5 PASS
answer_judge.py mock：6/6 PASS
answer_judge.py llm：6/6 PASS
ragas_eval.py --include-negative：6/6 expectation passed

---

## 当前不足

当前 Evaluation 仍有不足：
1. Golden Cases 只有 26 条
2. Answer Eval Cases 只有 6 条
3. 负例类型较少
4. Ragas 当前只接入 faithfulness
5. 尚未接入 answer_relevancy
6. 尚未建立 retrieval evaluator
7. 尚未评估 Insight Layer
8. report writer 逻辑存在重复

---

## 后续计划

Phase3 应优先补：
retrieval_eval_cases.py
retrieval_evaluator.py
更多 answer negative cases
编造原因型负例

Phase4 可补：
更完整的 Ragas metrics
dashboard / insight eval
evaluation dashboard

---

# 9. Ragas Evaluation Debt

## 当前问题

Ragas 已在 Day47 接入，但当前只使用：
faithfulness

还没有接入：
answer_relevancy
context_precision
context_recall

---

## 当前原因

当前项目不是传统文档 RAG，而是 Text-to-SQL。
因此 Ragas 的上下文不是文档 chunk，而是：SQL result rows
这要求先完成 context adaptation，再考虑更多指标。

---

## 当前处理方式

当前已经完成：
SQL rows → retrieved_contexts
query semantics enhancement
threshold-based expectation check
positive / negative cases

当前结论：Ragas 是标准化对照，不是唯一评分器。

---

## 后续计划

后续可考虑：
1. 尝试 answer_relevancy
2. 对比 Ragas 与 answer_judge 的分歧案例
3. 扩大 Ragas eval cases
4. 评估是否需要自定义 Ragas metric

但这些不应阻塞 Phase2 收尾。

---

# 10. LangGraph / Agent Workflow 承接债

## 当前问题

当前主链路仍然是线性 pipeline：query_service.py

它可以完成当前任务，但还没有形成 agentic workflow。

当前缺少：
1. workflow state
2. graph nodes
3. conditional edges
4. retry loop
5. SQL repair loop
6. clarification loop
7. eval-driven retry
8. multi-step analysis

---

## 为什么 Phase3 需要 LangGraph

Phase2 已经证明各个模块可以工作。

Phase3 的重点不是推翻 Phase2，而是把现有模块组织成 workflow：
parse_intent
resolve_metric
clarify_if_needed
build_query_plan
generate_sql
validate_sql
run_sql
repair_if_failed
generate_answer
evaluate_answer
retry_if_needed

LangGraph 的价值是：
让系统从单次线性调用升级为可分支、可回退、可重试、可解释的工作流。

---

## Phase3 设计原则

Phase3 不应一开始大规模重构。

建议：
1. 先写 langgraph_phase3_design.md
2. 再做最小 graph prototype
3. 复用现有 query_service 中的函数
4. 不一次性推翻当前主链路
5. 先接入 clarification / validation / repair 中的一个闭环

---

# Phase3 建议优先级

## Phase3 P0
1. LangGraph Phase3 design
2. 将 query_service 拆解为节点设计
3. 设计 state schema
4. 设计 clarification node
5. 设计 SQL validation / repair node

## Phase3 P1
1. Retrieval evaluator
2. Retrieval calibration
3. Ordinary metric lightweight query_plan
4. 更多 answer negative cases
5. Insight Layer design

## Phase3 P2
1. Beauty Dataset V2 design
2. 更多业务指标
3. Dashboard / chart
4. Ragas answer_relevancy
5. Evaluation dashboard

---

# 对 PROJECT_STATE 的同步要求

`PROJECT_STATE.md` 中应同步记录摘要，不需要复制本文件全文。

建议同步内容包括：
1. 当前主要技术债
2. Phase3 承接计划
3. Day49 计划中明确 LangGraph 需要考虑 retrieval / clarification / eval-driven retry
4. Day50 总结中明确 Phase2 未解决问题不会丢弃

---

# 当前结论

Phase2 当前成果是成立的：业务语义层 + Text-to-SQL + Answer Layer + Evaluation Workflow
但 Phase2 不是终点。

当前最重要的结论是：
Phase2 证明系统主链路可行；
Phase3 负责把系统升级为 workflow；
Phase4 负责增强数据、指标、分析和产品化。

所有遗留问题必须进入技术债和后续计划，不能只留在对话记忆中。
