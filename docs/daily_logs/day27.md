## 1. 接入 DeepSeek LLM

实现：
`
client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url=os.getenv("DEEPSEEK_BASE_URL"),
) 
`
并成功调用`client.chat.completions.create()`生成 SQL。

---
## 2. 完成 SQL Generator
创建：app/text_to_sql/sql_generator.py

实现流程：
Question
↓
Prompt Builder
↓
DeepSeek
↓
SQL

---
## 3. 完成 SQL Cleaner
创建：app/text_to_sql/sql_cleaner.py

处理：
```sql
SELECT ...
```
等模型输出格式，最终返回纯 SQL。

---
## 4. 优化 Semantic Context
补充：table_relationships.yaml

维护表关联关系：
- left_table: fact_order_items
  left_field: product_id
  right_table: dim_product
  right_field: product_id

---
## 5. Context Builder 支持关系注入
Prompt 中增加：
`=== Relationships ===
fact_order_items.product_id = dim_product.product_id
`
帮助模型正确 JOIN。

---
## 6. 验证退款率业务问题
测试问题：哪个品类退款率最高？

成功识别：
退款率
↓
refund_rate

成功识别：
品类
↓
dim_product.category

成功生成：
`LEFT JOIN fact_refunds` 以及 `WHERE order_status='paid'` 符合业务定义。