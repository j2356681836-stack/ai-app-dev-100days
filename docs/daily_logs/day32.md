# Day32

## 今日目标

接入 Embedding，完成第一版 Semantic Search。

---

## 完成内容

### BGE 接入

安装：sentence-transformers

加载：BAAI/bge-small-zh-v1.5

验证：成功生成512维向量。

---

### Semantic Search V2

实现：
Question
↓
Embedding
↓
Metric Retrieval

完成：Cosine Similarity 检索。

---

### Confidence Score

实现：Top1 Threshold + Top1 Gap Threshold 判断匹配可信度。

---

### Structured Result

实现：matched 和 needs_clarification 两种状态返回。

---

### Vector Cache

实现：

Metric Text
↓
Embedding
↓
Vector Cache

避免重复计算。

---

## 今日收获

理解：
Embedding ≠ Search
Embedding负责生成向量。
Vector Search负责检索。

理解：
Similarity ≠ Confidence
Embedding无法解决业务歧义。
Clarification用于处理模糊问题。

未来采用：Alias + Embedding + Clarification 的 Hybrid Search架构。