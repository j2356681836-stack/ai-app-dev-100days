# Day30

## 今日目标

扩展 Evaluation 数据集，并验证 Semantic Search 的业务表达能力。

---

## 完成内容

### Golden Questions 扩展

从 3 条扩展到 8 条有效测试问题。

覆盖：
- 标准表达
- 同义词表达
- TopN
- 业务黑话

---

### Evaluation V2

发现新的 Failure Cases：
- 卖得最好的是哪个品类
- 哪个品类退货最严重

定位：Semantic Search 未识别业务表达。

---

### Semantic Search V1

新增：
- business_metrics.yaml
- aliases

实现：Alias Match替代部分硬编码关键词。

---

### Failure Cases

记录：
- 哪个品类卖爆了
- 哪个品类最赚钱
- 销量冠军是谁

分类：
- 当前不支持
- 未来增强
- 需要澄清

---

## Evaluation

Total: 8
Passed: 8
Failed: 0
Pass Rate: 100%

---

## 今日收获

理解：Alias Search 可以解决部分业务黑话。但随着指标数量增加：
- Alias 数量爆炸
- 维护成本上升
- 指标歧义增加
因此未来需要：Embedding Search + Hybrid Search