# Day29

## 今日目标

建立 Evaluation Framework，验证 Text-to-SQL 系统可靠性。

---

## 完成内容

### SQL → Table

实现标准化结果结构：
- columns
- rows
- row_count

---

### Evaluation Framework V1

新增：
- golden_questions.py
- evaluator.py

实现：
- 批量问题评估
- SQL验证
- Pass Rate统计

---

### Failure Case Analysis

发现问题：

问题：
退款率最高的是啥？

生成SQL：SELECT dp.product_name
期望：SELECT dp.category

---

定位过程：
1. 检查 Context
2. 检查 Prompt
3. 检查 SQL

结论：Prompt约束不足。

---

### Prompt Optimization

新增规则：

用户未指定分析维度时：
- 默认使用：dim_product.category
- 不要默认使用：dim_product.product_name

---

## 最终结果

Evaluation：
- Total: 3
- Passed: 3
- Failed: 0
- Pass Rate: 100%

---

## 今日收获
第一次建立 Evaluation → Failure Analysis → Prompt Optimization 闭环。
理解：AI 工程的核心不是让一个问题答对，而是让大量问题持续答对。