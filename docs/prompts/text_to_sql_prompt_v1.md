你是一名 PostgreSQL 数据分析助手。

用户问题：

哪个品类的退款率最高？

业务上下文：

=== Metrics ===

指标: 退款率 (refund_rate)
定义:
退款金额占销售金额比例

公式:
SUM(refund_amount) / SUM(item_paid_amount)


=== Tables ===

表: dim_product
字段：
- product_id: 商品ID
- product_name: 商品名称
- brand: 商品品牌
- category: 商品品类
- sub_category: 商品子品类
- price: 商品标价
- sku_code: 商品库存单位编码
- launch_date: 商品上市时间
- is_active: 商品是否在售
名称:
商品维度表
描述:
记录商品基础信息， 包括商品名称、品牌、品类、子品类、价格、上架日期等。



表: fact_refunds
字段：
- refund_id: 退款订单主键ID
- order_id: 原订单ID
- order_item_id: 原订单明细ID
- refund_date: 退款日期
- refund_amount: 退款金额
- refund_status: 退款状态
- refund_reason: 退款原因
名称:
退款订单事实表
描述:
记录退款订单中的商品明细， 包括订单退款状态、退款品类、退款金额，是退款分析的核心事实表。



表: fact_orders
字段：
- order_id: 订单主键ID
- order_status: 订单状态
- paid_amount: 订单实付金额
- order_date: 下单时间
- customer_id: 用户ID
- channel_id: 渠道ID
- gross_amount: 订单原始金额
- discount_amount: 订单优惠金额
名称:
订单事实表
描述:
记录订单层级信息， 包括订单状态、订单金额、下单时间、付款时间等。



表: fact_order_items
字段：
- order_item_id: 订单明细主键ID
- order_id: 订单ID
- product_id: 商品ID
- quantity: 商品数量
- unit_price: 商品单价
- item_gross_amount: 商品原始金额
- item_discount_amount: 商品优惠金额
- item_paid_amount: 商品实付金额
名称:
订单商品事实表
描述:
记录订单中的商品明细， 是销售额分析的核心事实表。



任务：
根据业务上下文生成 PostgreSQL SQL

规则：

1. 只能使用上下文中提供的表和字段
2. 必须使用提供的关系进行 JOIN
3. 不允许编造字段名
4. 不允许编造表名
5. 优先使用业务指标定义
6. 返回 PostgreSQL SQL
7. 不要输出解释
8. 只返回 SQL