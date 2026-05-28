import os
import random
from datetime import datetime, timedelta, date

import numpy as np
from dotenv import load_dotenv
from faker import Faker
from sqlalchemy import URL, create_engine, text
from tqdm import tqdm


fake = Faker("zh_CN")
random.seed(42)
np.random.seed(42)


def get_engine():
    load_dotenv()

    database_url = URL.create(
        drivername="postgresql+psycopg",
        username=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        database=os.getenv("POSTGRES_DB"),
    )

    return create_engine(database_url, pool_pre_ping=True)


def reset_tables(conn):
    print("正在清空旧数据...")

    conn.execute(text("""
        TRUNCATE TABLE
            fact_reviews,
            fact_marketing_spend,
            fact_refunds,
            fact_order_items,
            fact_orders,
            dim_channel,
            dim_customer,
            dim_product
        RESTART IDENTITY CASCADE;
    """))


def seed_channels(conn):
    print("正在插入渠道数据...")

    channels = [
        ("天猫", "电商平台"),
        ("京东", "电商平台"),
        ("抖音", "内容电商"),
        ("小红书", "内容种草"),
        ("微信小程序", "私域"),
    ]

    for name, channel_type in channels:
        conn.execute(
            text("""
                INSERT INTO dim_channel (channel_name, channel_type)
                VALUES (:channel_name, :channel_type)   
            """),       # : 命名参数占位符
            {"channel_name": name, "channel_type": channel_type},   # 参数绑定代替SQL注入
        )


def seed_products(conn, product_count=100):
    print("正在插入商品数据...")

    categories = {
        "防晒": ["防晒霜", "防晒喷雾", "防晒乳"],
        "面膜": ["补水面膜", "修护面膜", "清洁面膜"],
        "精华": ["美白精华", "抗老精华", "修护精华"],
        "洁面": ["氨基酸洁面", "控油洁面", "敏感肌洁面"],
        "面霜": ["保湿面霜", "抗老面霜", "修护面霜"],
    }

    brands = ["花颜", "清润纪", "肌研社", "东方植萃", "PureLab"]

    product_id = 1

    for category, sub_categories in categories.items():
        for i in range(product_count // len(categories)):
            sub_category = random.choice(sub_categories)
            brand = random.choice(brands)

            # 植入业务规律：精华价格更高，防晒中等，洁面较低
            if category == "精华":
                price = round(random.uniform(199, 699), 2)
            elif category == "防晒":
                price = round(random.uniform(89, 299), 2)
            elif category == "面膜":
                price = round(random.uniform(69, 199), 2)
            elif category == "面霜":
                price = round(random.uniform(129, 499), 2)
            else:
                price = round(random.uniform(49, 159), 2)

            sku_code = f"SKU{product_id:04d}"       # 按4位整数格式输出，不够前面补0
            product_name = f"{brand}{sub_category}{product_id}"

            conn.execute(
                text("""
                    INSERT INTO dim_product
                    (sku_code, product_name, brand, category, sub_category, price, launch_date, is_active)
                    VALUES
                    (:sku_code, :product_name, :brand, :category, :sub_category, :price, :launch_date, TRUE)
                """),
                {
                    "sku_code": sku_code,
                    "product_name": product_name,
                    "brand": brand,
                    "category": category,
                    "sub_category": sub_category,
                    "price": price,
                    "launch_date": fake.date_between(start_date="-2y", end_date="-30d"),
                },
            )

            product_id += 1


def seed_customers(conn, customer_count=2000):
    print("正在插入用户数据...")

    gender_options = ["女", "男", "未知"]
    age_groups = ["18-24", "25-30", "31-35", "36-45", "46+"]
    city_tiers = ["一线", "新一线", "二线", "三线及以下"]
    member_levels = ["普通会员", "银卡会员", "金卡会员", "黑金会员"]

    for _ in tqdm(range(customer_count), desc="customers"):     # desc：进度条名字customers
        conn.execute(
            text("""
                INSERT INTO dim_customer
                (gender, age_group, city_tier, register_date, member_level)
                VALUES
                (:gender, :age_group, :city_tier, :register_date, :member_level)
            """),
            {
                "gender": random.choices(gender_options, weights=[75, 15, 10])[0],
                "age_group": random.choices(age_groups, weights=[25, 35, 25, 12, 3])[0],
                "city_tier": random.choices(city_tiers, weights=[25, 30, 25, 20])[0],
                "register_date": fake.date_between(start_date="-3y", end_date="-30d"),
                "member_level": random.choices(member_levels, weights=[55, 25, 15, 5])[0],
            },      
            # weights：权重，对应值出现的概率
            # random.choices：可以设置权重weights，但返回列表，通过 [0]：返回列表第一个元素
            # random.choice：不能设置权重
            # fake.date_between(start_date="-3y", end_date="-30d")：过去三年到三十天前之间生成随机日期
        )


def fetch_id_maps(conn):
    products = conn.execute(
        text("SELECT product_id, category, price FROM dim_product")
    ).mappings().all()
        # .mappings()转为python可访问的形式
        # .all()将所有数据一次性取出来

    customers = conn.execute(
        text("SELECT customer_id, member_level FROM dim_customer")
    ).mappings().all()

    channels = conn.execute(
        text("SELECT channel_id, channel_name FROM dim_channel")
    ).mappings().all()

    return list(products), list(customers), list(channels)


def random_order_date():
     # 随机生成一个“最近180天内”的订单时间
    start = datetime.now() - timedelta(days=180)   
    random_days = random.randint(0, 179)
    random_seconds = random.randint(0, 86400)
    return start + timedelta(days=random_days, seconds=random_seconds)


def choose_product(products, order_date):
    """
    植入业务规律：
    6-8 月防晒销量更高。
    """
    month = order_date.month

    # 如果订单月份是 6、7、8 月，那么有 45% 的概率选择防晒类商品
    if month in [6, 7, 8]:
        sunscreen_products = [p for p in products if p["category"] == "防晒"]
        if random.random() < 0.45:
            return random.choice(sunscreen_products)

    return random.choice(products)


def seed_orders(conn, order_count=20000):
    print("正在插入订单与订单明细...")

    products, customers, channels = fetch_id_maps(conn)

    order_status_options = ["paid", "cancelled"]
    created_order_items = []

    for i in tqdm(range(order_count), desc="orders"):
        customer = random.choice(customers)
        channel = random.choices(
            channels,
            weights=[
                30 if c["channel_name"] == "天猫" else
                20 if c["channel_name"] == "京东" else
                25 if c["channel_name"] == "抖音" else
                15 if c["channel_name"] == "小红书" else
                10
                for c in channels
            ],
        )[0]

        order_date = random_order_date()
        order_status = random.choices(order_status_options, weights=[94, 6])[0]

        item_count = random.choices([1, 2, 3], weights=[65, 25, 10])[0]

        order_items = []
        gross_amount = 0

        for _ in range(item_count):
            product = choose_product(products, order_date)
            quantity = random.choices([1, 2, 3], weights=[75, 20, 5])[0]
            unit_price = float(product["price"])
            item_gross_amount = round(unit_price * quantity, 2)

            order_items.append({
                "product_id": product["product_id"],
                "category": product["category"],
                "quantity": quantity,
                "unit_price": unit_price,
                "item_gross_amount": item_gross_amount,
            })

            gross_amount += item_gross_amount

        discount_rate = random.choices(
            [0, 0.05, 0.1, 0.15],
            weights=[40, 30, 20, 10],
        )[0]

        discount_amount = round(gross_amount * discount_rate, 2)
        paid_amount = round(gross_amount - discount_amount, 2)

        if order_status == "cancelled":
            paid_amount = 0

        order_no = f"ORD{i + 1:08d}"

        order_id = conn.execute(
            text("""
                INSERT INTO fact_orders
                (order_no, customer_id, channel_id, order_date, order_status,
                 gross_amount, discount_amount, paid_amount)
                VALUES
                (:order_no, :customer_id, :channel_id, :order_date, :order_status,
                 :gross_amount, :discount_amount, :paid_amount)
                RETURNING order_id
            """),
            {
                "order_no": order_no,
                "customer_id": customer["customer_id"],
                "channel_id": channel["channel_id"],
                "order_date": order_date,
                "order_status": order_status,
                "gross_amount": round(gross_amount, 2),
                "discount_amount": discount_amount,
                "paid_amount": paid_amount,
            },
        ).scalar_one()

        for item in order_items:
            item_discount_amount = round(item["item_gross_amount"] * discount_rate, 2)
            item_paid_amount = round(item["item_gross_amount"] - item_discount_amount, 2)

            if order_status == "cancelled":
                item_paid_amount = 0

            order_item_id = conn.execute(
                text("""
                    INSERT INTO fact_order_items
                    (order_id, product_id, quantity, unit_price,
                     item_gross_amount, item_discount_amount, item_paid_amount)
                    VALUES
                    (:order_id, :product_id, :quantity, :unit_price,
                     :item_gross_amount, :item_discount_amount, :item_paid_amount)
                    RETURNING order_item_id
                """),
                {
                    "order_id": order_id,
                    "product_id": item["product_id"],
                    "quantity": item["quantity"],
                    "unit_price": item["unit_price"],
                    "item_gross_amount": item["item_gross_amount"],
                    "item_discount_amount": item_discount_amount,
                    "item_paid_amount": item_paid_amount,
                },
            ).scalar_one()

            if order_status == "paid":
                created_order_items.append({
                    "order_id": order_id,
                    "order_item_id": order_item_id,
                    "product_id": item["product_id"],
                    "category": item["category"],
                    "item_paid_amount": item_paid_amount,
                    "order_date": order_date,
                })

    return created_order_items


def seed_refunds(conn, order_items):
    print("正在插入退款数据...")

    refund_reasons = ["不适合肤质", "过敏", "物流破损", "买错商品", "效果不符合预期"]

    for item in tqdm(order_items, desc="refunds"):
        # 植入业务规律：精华类退款率更高
        if item["category"] == "精华":
            refund_prob = 0.14
        else:
            refund_prob = 0.06

        if random.random() < refund_prob:
            refund_amount = round(item["item_paid_amount"] * random.uniform(0.5, 1.0), 2)
            refund_date = item["order_date"] + timedelta(days=random.randint(1, 21))

            conn.execute(
                text("""
                    INSERT INTO fact_refunds
                    (order_id, order_item_id, refund_date, refund_amount, refund_status, refund_reason)
                    VALUES
                    (:order_id, :order_item_id, :refund_date, :refund_amount, 'success', :refund_reason)
                """),
                {
                    "order_id": item["order_id"],
                    "order_item_id": item["order_item_id"],
                    "refund_date": refund_date,
                    "refund_amount": refund_amount,
                    "refund_reason": random.choice(refund_reasons),
                },
            )


def seed_marketing_spend(conn):
    print("正在插入投放费用数据...")

    channels = conn.execute(
        text("SELECT channel_id, channel_name FROM dim_channel")
    ).mappings().all()

    start_date = date.today() - timedelta(days=180)

    for day_offset in tqdm(range(180), desc="marketing"):
        spend_date = start_date + timedelta(days=day_offset)

        for channel in channels:
            name = channel["channel_name"]

            base_spend = {
                "天猫": 8000,
                "京东": 6000,
                "抖音": 10000,
                "小红书": 7000,
                "微信小程序": 3000,
            }[name]

            # 植入业务规律：
            # 最近 60 天小红书投放费用逐步上涨，方便后面分析 ROI 下滑
            if name == "小红书" and day_offset > 120:
                growth_factor = 1 + (day_offset - 120) / 60 * 0.7
            else:
                growth_factor = 1

            spend_amount = round(base_spend * growth_factor * random.uniform(0.8, 1.2), 2)

            conn.execute(
                text("""
                    INSERT INTO fact_marketing_spend
                    (channel_id, spend_date, campaign_name, spend_amount)
                    VALUES
                    (:channel_id, :spend_date, :campaign_name, :spend_amount)
                """),
                {
                    "channel_id": channel["channel_id"],
                    "spend_date": spend_date,
                    "campaign_name": f"{name}日常投放",
                    "spend_amount": spend_amount,
                },
            )


def seed_reviews(conn, review_count=5000):
    print("正在插入评价数据...")

    order_items = conn.execute(
        text("""
            SELECT
                oi.order_item_id,
                oi.product_id,
                o.customer_id,
                o.order_date,
                p.category
            FROM fact_order_items oi
            JOIN fact_orders o ON oi.order_id = o.order_id
            JOIN dim_product p ON oi.product_id = p.product_id
            WHERE o.order_status = 'paid'
            ORDER BY random()
            LIMIT :review_count
        """),
        {"review_count": review_count},
    ).mappings().all()

    positive_reviews = [
        "使用感很好，会回购",
        "包装精致，效果不错",
        "很适合我的肤质",
        "物流快，产品满意",
    ]

    negative_reviews = [
        "使用后有点不适",
        "效果一般，不会回购",
        "感觉不太适合我",
        "性价比一般",
    ]

    for item in tqdm(order_items, desc="reviews"):
        if item["category"] == "精华":
            rating = random.choices([1, 2, 3, 4, 5], weights=[8, 10, 20, 32, 30])[0]
        else:
            rating = random.choices([1, 2, 3, 4, 5], weights=[3, 5, 15, 35, 42])[0]

        if rating >= 4:
            sentiment = "positive"
            review_text = random.choice(positive_reviews)
        elif rating == 3:
            sentiment = "neutral"
            review_text = "整体还可以，但没有特别惊喜"
        else:
            sentiment = "negative"
            review_text = random.choice(negative_reviews)

        review_date = item["order_date"] + timedelta(days=random.randint(3, 30))

        conn.execute(
            text("""
                INSERT INTO fact_reviews
                (order_item_id, product_id, customer_id, review_date, rating, review_text, sentiment)
                VALUES
                (:order_item_id, :product_id, :customer_id, :review_date, :rating, :review_text, :sentiment)
            """),
            {
                "order_item_id": item["order_item_id"],
                "product_id": item["product_id"],
                "customer_id": item["customer_id"],
                "review_date": review_date,
                "rating": rating,
                "review_text": review_text,
                "sentiment": sentiment,
            },
        )


def print_table_counts(conn):
    print("\n数据生成完成，当前表数据量：")

    tables = [
        "dim_product",
        "dim_customer",
        "dim_channel",
        "fact_orders",
        "fact_order_items",
        "fact_refunds",
        "fact_marketing_spend",
        "fact_reviews",
    ]

    for table in tables:
        count = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one()
        print(f"{table}: {count}")


def main():
    engine = get_engine()

    with engine.begin() as conn:
        reset_tables(conn)
        seed_channels(conn)
        seed_products(conn, product_count=100)
        seed_customers(conn, customer_count=2000)
        order_items = seed_orders(conn, order_count=20000)
        seed_refunds(conn, order_items)
        seed_marketing_spend(conn)
        seed_reviews(conn, review_count=5000)
        print_table_counts(conn)

    engine.dispose()


if __name__ == "__main__":
    main()