/*
各品类退款率是否有明显差异？
退款率：
口径1：按订单数--退款订单数/总订单数
口径2：按商品件数--退款商品件数 / 销售商品件数
口径3：按销售金额--退款金额 / 销售金额
*/

/*
-- 退款订单数/总订单数
select 
    a.category as category,
    round(refund_order_count / nullif(order_count,0),2) as refound_rate --退款率
from 
(
select 
    p.category as category,     -- by品类
    count(distinct fo.order_id) as order_count     -- 总单数
from fact_orders fo
join fact_order_items oi on fo.order_id = oi.order_id
join dim_product p on oi.product_id = p.product_id
where fo.order_status = 'paid'
group by p.category
) a
left join 
(
select 
    p.category as category,
    count(distinct rf.order_id) as refund_order_count
from fact_refunds rf 
join fact_order_items oi
    on rf.order_id = oi.order_id and rf.order_item_id = oi.order_item_id
join dim_product p 
    on oi.product_id = p.product_id
where rf.refund_status = 'success'
group by p.category
) b 
on a.category = b.category
;
*/

/*
-- 退款金额 / 销售金额

SELECT
    p.category,

    ROUND(
        COALESCE(SUM(r.refund_amount), 0),
        2
    ) AS total_refund_amount,

    ROUND(
        SUM(oi.item_paid_amount),
        2
    ) AS total_sales_amount,

    ROUND(
        COALESCE(SUM(r.refund_amount), 0)
        / NULLIF(SUM(oi.item_paid_amount), 0)
        * 100,
        2
    ) AS refund_rate_pct

FROM fact_orders o

JOIN fact_order_items oi
    ON o.order_id = oi.order_id

JOIN dim_product p
    ON oi.product_id = p.product_id

LEFT JOIN fact_refunds r
    ON oi.order_item_id = r.order_item_id

WHERE o.order_status = 'paid'

GROUP BY p.category

ORDER BY refund_rate_pct DESC;
*/

/*
结果：

 category | total_refund_amount | total_sales_amount | refund_rate_pct 
----------+---------------------+--------------------+-----------------
 精华     |           322272.55 |         3222179.06 |           10.00
 防晒     |            60650.07 |         1333192.46 |            4.55
 面膜     |            39645.58 |          884490.86 |            4.48
 洁面     |            26793.41 |          599283.72 |            4.47
 面霜     |            86734.56 |         1983850.16 |            4.37

*/

