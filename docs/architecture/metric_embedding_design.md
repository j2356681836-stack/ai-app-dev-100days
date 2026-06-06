# Metric Embedding Design

## 背景

未来 Semantic Search V2 将引入 Embedding Search。
Embedding 不仅使用指标名称。而是使用完整业务描述。

---

## Metric Text Structure

指标名称：{chinese_name}
定义：{definition}
公式：{formula}
别名：{aliases}

---

## 示例

指标名称：退款率
定义：退款金额占销售金额比例
公式：SUM(refund_amount) / SUM(item_paid_amount)
别名：
    退款率
    退货率
    退货最严重
    退得最厉害

---

## Embedding Pipeline

Metric YAML
↓
Metric Text
↓
BGE Embedding
↓
Vector
↓
Vector Search