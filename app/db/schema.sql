-- Day 22: Beauty BI Database Schema
-- 目标：建立美妆业务分析所需的核心表结构

DROP TABLE IF EXISTS fact_reviews CASCADE;
DROP TABLE IF EXISTS fact_marketing_spend CASCADE;
DROP TABLE IF EXISTS fact_refunds CASCADE;
DROP TABLE IF EXISTS fact_order_items CASCADE;
DROP TABLE IF EXISTS fact_orders CASCADE;
DROP TABLE IF EXISTS dim_channel CASCADE;
DROP TABLE IF EXISTS dim_customer CASCADE;
DROP TABLE IF EXISTS dim_product CASCADE;

-- 1. 商品维度表
CREATE TABLE dim_product (
    product_id SERIAL PRIMARY KEY,
    sku_code VARCHAR(50) NOT NULL UNIQUE,
    product_name VARCHAR(200) NOT NULL,
    brand VARCHAR(100) NOT NULL,
    category VARCHAR(50) NOT NULL,
    sub_category VARCHAR(50),
    price NUMERIC(12, 2) NOT NULL,
    launch_date DATE,
    is_active BOOLEAN DEFAULT TRUE
);

-- 2. 用户维度表
CREATE TABLE dim_customer (
    customer_id SERIAL PRIMARY KEY,
    gender VARCHAR(20),
    age_group VARCHAR(20),
    city_tier VARCHAR(20),
    register_date DATE NOT NULL,
    member_level VARCHAR(50)
);

-- 3. 渠道维度表
CREATE TABLE dim_channel (
    channel_id SERIAL PRIMARY KEY,
    channel_name VARCHAR(100) NOT NULL UNIQUE,
    channel_type VARCHAR(50) NOT NULL
);

-- 4. 订单事实表：一行代表一个订单
CREATE TABLE fact_orders (
    order_id SERIAL PRIMARY KEY,
    order_no VARCHAR(100) NOT NULL UNIQUE,
    customer_id INT NOT NULL REFERENCES dim_customer(customer_id),
    channel_id INT NOT NULL REFERENCES dim_channel(channel_id),
    order_date TIMESTAMP NOT NULL,
    order_status VARCHAR(50) NOT NULL,
    gross_amount NUMERIC(12, 2) NOT NULL,
    discount_amount NUMERIC(12, 2) DEFAULT 0,
    paid_amount NUMERIC(12, 2) NOT NULL
);

-- 5. 订单明细表：一行代表订单里的一个商品
CREATE TABLE fact_order_items (
    order_item_id SERIAL PRIMARY KEY,
    order_id INT NOT NULL REFERENCES fact_orders(order_id),
    product_id INT NOT NULL REFERENCES dim_product(product_id),
    quantity INT NOT NULL,
    unit_price NUMERIC(12, 2) NOT NULL,
    item_gross_amount NUMERIC(12, 2) NOT NULL,
    item_discount_amount NUMERIC(12, 2) DEFAULT 0,
    item_paid_amount NUMERIC(12, 2) NOT NULL
);

-- 6. 退款明细表
CREATE TABLE fact_refunds (
    refund_id SERIAL PRIMARY KEY,
    order_id INT NOT NULL REFERENCES fact_orders(order_id),
    order_item_id INT REFERENCES fact_order_items(order_item_id),
    refund_date TIMESTAMP NOT NULL,
    refund_amount NUMERIC(12, 2) NOT NULL,
    refund_status VARCHAR(50) NOT NULL,
    refund_reason VARCHAR(200)
);

-- 7. 渠道投放费用表
CREATE TABLE fact_marketing_spend (
    spend_id SERIAL PRIMARY KEY,
    channel_id INT NOT NULL REFERENCES dim_channel(channel_id),
    spend_date DATE NOT NULL,
    campaign_name VARCHAR(200),
    spend_amount NUMERIC(12, 2) NOT NULL
);

-- 8. 用户评价表
CREATE TABLE fact_reviews (
    review_id SERIAL PRIMARY KEY,
    order_item_id INT NOT NULL REFERENCES fact_order_items(order_item_id),
    product_id INT NOT NULL REFERENCES dim_product(product_id),
    customer_id INT NOT NULL REFERENCES dim_customer(customer_id),
    review_date TIMESTAMP NOT NULL,
    rating INT NOT NULL CHECK (rating BETWEEN 1 AND 5),
    review_text TEXT,
    sentiment VARCHAR(50)
);