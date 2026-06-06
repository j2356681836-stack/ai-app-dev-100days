# Day31

## 今日目标

理解 Embedding Search 的价值与局限，并设计 Semantic Search V2。

---

## 完成内容

### Alias Search 复盘

分析：
- Alias Search 优势
- Alias Search 上限

发现：

随着指标增长：
- Alias 数量爆炸
- 维护成本提升
- 指标歧义增加

---

### Embedding Search 学习

理解：
文本
↓
Embedding
↓
Vector
↓
Cosine Similarity

学习：Similarity ≠ Confidence

---

### Clarification 机制

设计：Top1 Similarity + Top1-Top2 Gap，判断是否需要用户澄清。

---

### Hybrid Search V1

设计：
Question
↓
Alias Search
↓
Embedding Search
↓
Clarification

---

### Metric Embedding Pipeline

设计：
Metric YAML
↓
Metric Text
↓
Embedding
↓
Vector Search

---

### Metric Text Builder

完成：build_metric_text()和build_all_metric_texts()，并且验证通过。

---

## 今日收获

真正理解：为什么需要 Embedding。

理解：
Embedding 解决语义接近问题。
Clarification 解决业务歧义问题。

企业级 AI BI Agent 不会只依赖 Embedding，而是采用：Alias + Embedding + Clarification 的 Hybrid Search。