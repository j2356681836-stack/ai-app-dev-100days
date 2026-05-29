/* 
指标：品类销售额
口径：只统计 paid 订单，按商品品类汇总订单明细表中的 item_paid_amount
涉及表：fact_orders、fact_order_items、dim_product
-----------------------------------------------------------------
只统计已支付订单，把订单明细连到商品表，然后按商品品类分组。
计算每个品类卖了多少单、多少件、多少钱。
*/

select 
    p.category,     -- by品类
    count(distinct fo.order_id) as order_count,     -- 总单数
    sum(quantity) as total_quantity,    --总件数
    sum(item_paid_amount) as total_sales,   -- 总销售额
    round(sum(oi.item_paid_amount)/nullif(sum(oi.quantity),0),2) as avg_selling_price --件单价
from fact_orders fo
join fact_order_items oi on fo.order_id = oi.order_id
join dim_product p on oi.product_id = p.product_id
where fo.order_status = 'paid'
group by p.category
order by total_sales desc;

/*

 category | order_count | total_quantity | total_sales | avg_selling_price
----------+-------------+----------------+-------------+-------------------
 精华     |        5053 |           7039 |  3222179.06 |            457.76
 面霜     |        4946 |           6925 |  1983850.16 |            286.48
 防晒     |        5157 |           7260 |  1333192.46 |            183.64
 面膜     |        4947 |           6994 |   884490.86 |            126.46
 洁面     |        5065 |           7079 |   599283.72 |             84.66


订单数差不多，但是销售额差很多。说明差异不是客数问题，而是客单价/商品单价导致的。
精华产品因为平均成交单价最高，所以贡献了最高的销售额。

 */

