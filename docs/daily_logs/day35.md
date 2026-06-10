# Day35

日期：2026-06-10

## 今日目标

扩展业务指标体系，增强业务问题识别能力。

---

## 完成内容

### 1. 新增业务指标

新增：
- order_count（订单数）
- sales_quantity（销量）

支持问题：
- 哪个品类订单最多
- 哪个品类成交最多
- 哪个品类销量最高
- 哪个品类卖出最多件

---

### 2. Rule Layer 增强

新增 keyword_group 规则匹配。
支持：
- 销售额Top5品类
- 销售额Top10品类
无需为每个 TopN 单独维护 Alias。

---

### 3. Alias 优化

调整销售额相关 Alias：
- 销售额
- 销售金额
从 order_paid_amount 中移除。避免与 item_sales_amount 产生业务歧义。

---

### 4. Trace 输出优化

调整：
- method = rule
- search_type = alias
- search_type = keyword_group
提升命中路径可解释性。

---

### 5. Golden Cases 扩展

新增：
- case_014
- case_015
- case_016
- case_017

当前：
Passed: 12
Failed: 0
Pass Rate: 100%

---

## 今日收获

开始从“指标识别”过渡到“业务意图识别”。
认识到：Metric ≠ Intent
销售额Top5品类 实际上包含：
- Metric
- Dimension
- Ranking