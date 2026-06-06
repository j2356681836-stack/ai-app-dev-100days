# Semantic Search V2 Design

## 背景

当前系统使用 Alias Search 识别业务指标。

优点：
- 准确
- 可控
- 易调试

问题：
- aliases 维护成本高
- 无法覆盖所有用户表达
- 相似指标容易产生歧义

---

## 目标

构建 Hybrid Search：Alias Search + Embedding Search + Clarification

---

## 流程

Question
↓
Alias Match
↓
命中：返回 Metric
↓
未命中：Embedding Search
↓
高置信度：返回 Metric
↓
低置信度：进入 Clarification

---

## 置信度规则

初版使用：
- Top1 Score Threshold
- Top1 - Top2 Gap Threshold

示例：
如果：Top1 >= 0.85且Top1 - Top2 >= 0.10，则认为匹配可信。否则进入澄清。

---

## 当前不处理的问题

- 不直接支持利润
- 不直接支持 ROI
- 不直接支持渠道分析
- 模糊表达不强行猜测

---

## 未来落地步骤

1. 准备 metric embedding text
2. 使用 BGE 生成向量
3. 将 metric 向量存入本地文件或 pgvector
4. 实现 embedding_search
5. 与 alias_search 合并为 hybrid_search
6. 接入 clarification 状态