/*
会员用户是否比普通用户更容易复购？

复购用户：
口径1：买过两次以上：订单数 >= 2
口径2：不同日期购买两次以上：购买天数 >= 2
口径3：30天内再次购买：存在第二笔订单且距离首单 <= 30天

*/

-- 订单数 >= 2
WITH customer_orders AS (
    SELECT
        c.customer_id,
        c.member_level,
        COUNT(o.order_id) AS paid_order_count
    FROM dim_customer c
    LEFT JOIN fact_orders o
        ON c.customer_id = o.customer_id
       AND o.order_status = 'paid'
    GROUP BY
        c.customer_id,
        c.member_level
)

SELECT
    member_level,
    COUNT(*) AS total_customers,
    ROUND(AVG(paid_order_count), 2) AS avg_order_count,
    MAX(paid_order_count) AS max_order_count,
    MIN(paid_order_count) AS min_order_count
FROM customer_orders
GROUP BY member_level
ORDER BY avg_order_count DESC;

/*
 member_level | total_customers | avg_order_count | max_order_count | min_order_count 
--------------+-----------------+-----------------+-----------------+-----------------
 银卡会员     |             522 |            9.57 |              19 |               1
 普通会员     |            1099 |            9.36 |              23 |               2
 金卡会员     |             275 |            9.25 |              20 |               1
 黑金会员     |             104 |            8.82 |              20 |               2
(4 rows)

会员复购增强规律未被当前数据集有效体现。
1. 当前仅保存会员等级快照，
2. 缺少会员等级变更历史；
3. 同时订单生成逻辑未显著拉开各等级购买频次差异。
*/