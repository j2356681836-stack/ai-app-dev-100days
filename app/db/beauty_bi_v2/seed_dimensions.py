from datetime import date, datetime, time, timedelta
from typing import Any

from app.db.beauty_bi_v2.manifest_loader import (
    get_active_scale_profile,
    load_and_validate_day64_manifest,
    parse_manifest_date,
    parse_manifest_datetime,
    parse_manifest_time,
)

from sqlalchemy import text
from app.db.database import engine
from decimal import (
    Decimal,
    ROUND_FLOOR,
    ROUND_HALF_UP,
)
from collections import Counter
import random

import argparse


def build_holiday_lookup(
    manifest: dict[str, Any],
) -> dict[date, str]:
    """
    将 Manifest 中的节假日区间展开为：

    {
        date(2024, 1, 1): "元旦",
        date(2024, 1, 2): "元旦",
        ...
    }
    """
    periods = manifest[
        "business_calendar"
    ][
        "holidays"
    ][
        "periods"
    ]

    holiday_lookup: dict[date, str] = {}

    for index, period in enumerate(periods):
        start_date = parse_manifest_date(
            period["start_date"],
            (
                "business_calendar.holidays."
                f"periods[{index}].start_date"
            ),
        )

        end_date = parse_manifest_date(
            period["end_date"],
            (
                "business_calendar.holidays."
                f"periods[{index}].end_date"
            ),
        )

        holiday_name = period["holiday_name"].strip()
        current_date = start_date

        while current_date <= end_date:
            holiday_lookup[current_date] = holiday_name
            current_date += timedelta(days=1)

    return holiday_lookup


def build_dim_date_rows(
    manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    根据 Manifest 生成 dim_date 的全部行。

    日期范围：
    business_start_date
    至
    event_observation_end_date

    两端均包含。
    """
    generation = manifest["generation"]

    start_date = parse_manifest_date(
        generation["business_start_date"],
        "generation.business_start_date",
    )

    end_date = parse_manifest_date(
        generation["event_observation_end_date"],
        "generation.event_observation_end_date",
    )

    holiday_lookup = build_holiday_lookup(manifest)

    rows: list[dict[str, Any]] = []
    current_date = start_date

    while current_date <= end_date:
        iso_calendar = current_date.isocalendar()

        # ISO weekday：
        # Monday = 1
        # Sunday = 7
        day_of_week = current_date.isoweekday()

        holiday_name = holiday_lookup.get(current_date)
        is_holiday = holiday_name is not None

        row = {
            "date_key": int(
                current_date.strftime("%Y%m%d")
            ),
            "full_date": current_date,
            "year": current_date.year,
            "quarter": (
                current_date.month - 1
            ) // 3 + 1,
            "month": current_date.month,
            "month_name": f"{current_date.month}月",
            "week_of_year": iso_calendar.week,
            "day_of_month": current_date.day,
            "day_of_week": day_of_week,
            "is_weekend": day_of_week in (6, 7),
            "is_holiday": is_holiday,
            "holiday_name": holiday_name,
        }

        rows.append(row)
        current_date += timedelta(days=1)

    return rows


def validate_dim_date_rows(
    rows: list[dict[str, Any]],
    manifest: dict[str, Any],
) -> None:
    """
    在写入数据库前检查生成结果。
    """
    if not rows:
        raise ValueError("dim_date 生成结果不能为空。")

    generation = manifest["generation"]

    expected_start_date = parse_manifest_date(
        generation["business_start_date"],
        "generation.business_start_date",
    )

    expected_end_date = parse_manifest_date(
        generation["event_observation_end_date"],
        "generation.event_observation_end_date",
    )

    expected_count = (
        expected_end_date - expected_start_date
    ).days + 1

    if len(rows) != expected_count:
        raise ValueError(
            "dim_date 行数不符合预期："
            f"expected={expected_count}, "
            f"actual={len(rows)}"
        )

    if rows[0]["full_date"] != expected_start_date:
        raise ValueError(
            "dim_date 第一行日期不正确："
            f"expected={expected_start_date}, "
            f"actual={rows[0]['full_date']}"
        )

    if rows[-1]["full_date"] != expected_end_date:
        raise ValueError(
            "dim_date 最后一行日期不正确："
            f"expected={expected_end_date}, "
            f"actual={rows[-1]['full_date']}"
        )


    date_keys = [row["date_key"] for row in rows]
    full_dates = [row["full_date"] for row in rows]

    if len(set(date_keys)) != len(date_keys):
        raise ValueError(
            "dim_date 存在重复 date_key。"
        )

    if len(set(full_dates)) != len(full_dates):
        raise ValueError(
            "dim_date 存在重复 full_date。"
        )

    for row in rows:
        if row["is_holiday"]:
            if not row["holiday_name"]:
                raise ValueError(
                    "节假日必须包含 holiday_name："
                    f"{row['full_date']}"
                )
        elif row["holiday_name"] is not None:
            raise ValueError(
                "非节假日的 holiday_name 必须为 None："
                f"{row['full_date']}"
            )


def insert_dim_date_rows(
    rows: list[dict[str, Any]],
) -> None:
    """
    将 dim_date 数据批量写入 PostgreSQL。

    安全策略：
    1. 生成结果不能为空；
    2. 目标表必须为空；
    3. 在同一个事务中完成检查、插入和验证；
    4. 任意异常都会自动回滚。
    """
    if not rows:
        raise ValueError(
            "不能插入空的 dim_date 数据。"
        )

    insert_sql = text(
        """
        INSERT INTO beauty_bi_v2.dim_date (
            date_key,
            full_date,
            year,
            quarter,
            month,
            month_name,
            week_of_year,
            day_of_month,
            day_of_week,
            is_weekend,
            is_holiday,
            holiday_name
        )
        VALUES (
            :date_key,
            :full_date,
            :year,
            :quarter,
            :month,
            :month_name,
            :week_of_year,
            :day_of_month,
            :day_of_week,
            :is_weekend,
            :is_holiday,
            :holiday_name
        )
        """
    )

    with engine.begin() as connection:
        existing_count = connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM beauty_bi_v2.dim_date
                """
            )
        ).scalar_one()

        if existing_count != 0:
            raise RuntimeError(
                "beauty_bi_v2.dim_date 已存在数据，"
                "为避免重复写入，本次 Seed 已停止。"
                f" existing_count={existing_count}"
            )

        # 第二个参数传入 list[dict] 时，
        # SQLAlchemy 会进行批量执行。
        connection.execute(
            insert_sql,
            rows,
        )

        actual_count, min_date, max_date = (
            connection.execute(
                text(
                    """
                    SELECT
                        COUNT(*),
                        MIN(full_date),
                        MAX(full_date)
                    FROM beauty_bi_v2.dim_date
                    """
                )
            ).one()
        )

        if actual_count != len(rows):
            raise RuntimeError(
                "dim_date 插入后的行数不符合预期："
                f"expected={len(rows)}, "
                f"actual={actual_count}"
            )

        expected_min_date = rows[0]["full_date"]
        expected_max_date = rows[-1]["full_date"]

        if (
            min_date != expected_min_date
            or max_date != expected_max_date
        ):
            raise RuntimeError(
                "dim_date 插入后的日期边界不正确："
                f"expected="
                f"{expected_min_date} -> {expected_max_date}, "
                f"actual={min_date} -> {max_date}"
            )

    print("dim_date database seed passed.")
    print(f"Inserted rows: {actual_count}")
    print(f"Date range: {min_date} -> {max_date}")


def build_dim_region_rows(
    manifest: dict[str, Any],
) -> list[dict[str, str]]:
    """
    从 Manifest 生成 dim_region 数据。
    """
    regions = manifest[
        "fixed_dimensions"
    ][
        "regions"
    ]

    rows: list[dict[str, str]] = []

    for region in regions:
        row = {
            "region_code": region[
                "region_code"
            ].strip(),
            "region_name": region[
                "region_name"
            ].strip(),
            "province_name": region[
                "province_name"
            ].strip(),
            "region_group": region[
                "region_group"
            ].strip(),
            "city_tier": region[
                "city_tier"
            ].strip(),
        }

        rows.append(row)

    return rows


def validate_dim_region_rows(
    rows: list[dict[str, str]],
    manifest: dict[str, Any],
) -> None:
    """
    在写入数据库前检查 dim_region 生成结果。
    """
    if not rows:
        raise ValueError(
            "dim_region 生成结果不能为空。"
        )

    expected_count = len(
        manifest[
            "fixed_dimensions"
        ][
            "regions"
        ]
    )

    if len(rows) != expected_count:
        raise ValueError(
            "dim_region 行数不符合预期："
            f"expected={expected_count}, "
            f"actual={len(rows)}"
        )

    region_codes = [
        row["region_code"]
        for row in rows
    ]

    region_names = [
        row["region_name"]
        for row in rows
    ]

    if len(set(region_codes)) != len(region_codes):
        raise ValueError(
            "dim_region 存在重复 region_code。"
        )

    if len(set(region_names)) != len(region_names):
        raise ValueError(
            "dim_region 存在重复 region_name。"
        )

    required_fields = {
        "region_code",
        "region_name",
        "province_name",
        "region_group",
        "city_tier",
    }

    for index, row in enumerate(rows):
        if set(row.keys()) != required_fields:
            raise ValueError(
                f"dim_region 第 {index} 行字段不正确。"
            )

        for field_name, value in row.items():
            if not isinstance(value, str) or not value:
                raise ValueError(
                    f"dim_region 第 {index} 行 "
                    f"{field_name} 必须是非空字符串。"
                )


def insert_dim_region_rows(
    rows: list[dict[str, str]],
) -> None:
    """
    将 dim_region 批量写入 PostgreSQL。
    """
    if not rows:
        raise ValueError(
            "不能插入空的 dim_region 数据。"
        )

    insert_sql = text(
        """
        INSERT INTO beauty_bi_v2.dim_region (
            region_code,
            region_name,
            province_name,
            region_group,
            city_tier
        )
        VALUES (
            :region_code,
            :region_name,
            :province_name,
            :region_group,
            :city_tier
        )
        """
    )

    with engine.begin() as connection:
        existing_count = connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM beauty_bi_v2.dim_region
                """
            )
        ).scalar_one()

        if existing_count != 0:
            raise RuntimeError(
                "beauty_bi_v2.dim_region 已存在数据，"
                "为避免重复写入，本次 Seed 已停止。"
                f" existing_count={existing_count}"
            )

        connection.execute(
            insert_sql,
            rows,
        )

        (
            actual_count,
            distinct_code_count,
            distinct_name_count,
        ) = connection.execute(
            text(
                """
                SELECT
                    COUNT(*),
                    COUNT(DISTINCT region_code),
                    COUNT(DISTINCT region_name)
                FROM beauty_bi_v2.dim_region
                """
            )
        ).one()

        if actual_count != len(rows):
            raise RuntimeError(
                "dim_region 插入后的行数不正确："
                f"expected={len(rows)}, "
                f"actual={actual_count}"
            )

        if distinct_code_count != actual_count:
            raise RuntimeError(
                "dim_region 数据库中存在重复 "
                "region_code。"
            )

        if distinct_name_count != actual_count:
            raise RuntimeError(
                "dim_region 数据库中存在重复 "
                "region_name。"
            )

    print("dim_region database seed passed.")
    print(f"Inserted rows: {actual_count}")


def seed_dim_date(
    manifest: dict[str, Any],
) -> None:
    rows = build_dim_date_rows(manifest)
    validate_dim_date_rows(rows, manifest)

    holiday_rows = [
        row
        for row in rows
        if row["is_holiday"]
    ]

    print("dim_date generation passed.")
    print(f"Total rows: {len(rows)}")
    print(f"First row: {rows[0]}")
    print(f"Last row: {rows[-1]}")
    print(f"Holiday rows: {len(holiday_rows)}")
    print(f"First holiday row: {holiday_rows[0]}")

    insert_dim_date_rows(rows)


def seed_dim_region(
    manifest: dict[str, Any],
) -> None:
    rows = build_dim_region_rows(manifest)
    validate_dim_region_rows(rows, manifest)

    print("dim_region generation passed.")
    print(f"Total rows: {len(rows)}")
    print(f"First row: {rows[0]}")
    print(f"Last row: {rows[-1]}")

    insert_dim_region_rows(rows)


def build_dim_channel_rows(
    manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    从 Manifest 生成 dim_channel 数据。
    """
    channels = manifest[
        "fixed_dimensions"
    ][
        "channels"
    ]

    rows: list[dict[str, Any]] = []

    for channel in channels:
        row = {
            "channel_code": channel[
                "channel_code"
            ].strip(),
            "channel_name": channel[
                "channel_name"
            ].strip(),
            "channel_type": channel[
                "channel_type"
            ].strip(),
            "is_sales_channel": channel[
                "is_sales_channel"
            ],
            "is_marketing_channel": channel[
                "is_marketing_channel"
            ],
            "is_active": channel["is_active"],
        }

        rows.append(row)

    return rows


def validate_dim_channel_rows(
    rows: list[dict[str, Any]],
    manifest: dict[str, Any],
) -> None:
    """
    在写入数据库前检查 dim_channel 数据。
    """
    if not rows:
        raise ValueError(
            "dim_channel 生成结果不能为空。"
        )

    expected_count = len(
        manifest[
            "fixed_dimensions"
        ][
            "channels"
        ]
    )

    if len(rows) != expected_count:
        raise ValueError(
            "dim_channel 行数不符合预期："
            f"expected={expected_count}, "
            f"actual={len(rows)}"
        )

    required_fields = {
        "channel_code",
        "channel_name",
        "channel_type",
        "is_sales_channel",
        "is_marketing_channel",
        "is_active",
    }

    channel_codes = [
        row["channel_code"]
        for row in rows
    ]

    channel_names = [
        row["channel_name"]
        for row in rows
    ]

    if len(set(channel_codes)) != len(channel_codes):
        raise ValueError(
            "dim_channel 存在重复 channel_code。"
        )

    if len(set(channel_names)) != len(channel_names):
        raise ValueError(
            "dim_channel 存在重复 channel_name。"
        )

    for index, row in enumerate(rows):
        if set(row.keys()) != required_fields:
            raise ValueError(
                f"dim_channel 第 {index} 行字段不正确。"
            )

        for field_name in {
            "channel_code",
            "channel_name",
            "channel_type",
        }:
            value = row[field_name]

            if not isinstance(value, str) or not value:
                raise ValueError(
                    f"dim_channel 第 {index} 行 "
                    f"{field_name} 必须是非空字符串。"
                )

        for field_name in {
            "is_sales_channel",
            "is_marketing_channel",
            "is_active",
        }:
            if not isinstance(row[field_name], bool):
                raise ValueError(
                    f"dim_channel 第 {index} 行 "
                    f"{field_name} 必须是布尔值。"
                )

        if not (
            row["is_sales_channel"]
            or row["is_marketing_channel"]
        ):
            raise ValueError(
                f"dim_channel 第 {index} 行至少必须是"
                "销售渠道或营销渠道之一。"
            )


def insert_dim_channel_rows(
    rows: list[dict[str, Any]],
) -> None:
    """
    将 dim_channel 批量写入 PostgreSQL。
    """
    if not rows:
        raise ValueError(
            "不能插入空的 dim_channel 数据。"
        )

    insert_sql = text(
        """
        INSERT INTO beauty_bi_v2.dim_channel (
            channel_code,
            channel_name,
            channel_type,
            is_sales_channel,
            is_marketing_channel,
            is_active
        )
        VALUES (
            :channel_code,
            :channel_name,
            :channel_type,
            :is_sales_channel,
            :is_marketing_channel,
            :is_active
        )
        """
    )

    with engine.begin() as connection:
        existing_count = connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM beauty_bi_v2.dim_channel
                """
            )
        ).scalar_one()

        if existing_count != 0:
            raise RuntimeError(
                "beauty_bi_v2.dim_channel 已存在数据，"
                "为避免重复写入，本次 Seed 已停止。"
                f" existing_count={existing_count}"
            )

        connection.execute(
            insert_sql,
            rows,
        )

        (
            actual_count,
            distinct_code_count,
            sales_channel_count,
            marketing_channel_count,
            active_channel_count,
        ) = connection.execute(
            text(
                """
                SELECT
                    COUNT(*),
                    COUNT(DISTINCT channel_code),
                    COUNT(*) FILTER (
                        WHERE is_sales_channel
                    ),
                    COUNT(*) FILTER (
                        WHERE is_marketing_channel
                    ),
                    COUNT(*) FILTER (
                        WHERE is_active
                    )
                FROM beauty_bi_v2.dim_channel
                """
            )
        ).one()

        if actual_count != len(rows):
            raise RuntimeError(
                "dim_channel 插入后的行数不正确："
                f"expected={len(rows)}, "
                f"actual={actual_count}"
            )

        if distinct_code_count != actual_count:
            raise RuntimeError(
                "dim_channel 数据库中存在重复 "
                "channel_code。"
            )

    print("dim_channel database seed passed.")
    print(f"Inserted rows: {actual_count}")
    print(f"Sales channels: {sales_channel_count}")
    print(
        f"Marketing channels: "
        f"{marketing_channel_count}"
    )
    print(f"Active channels: {active_channel_count}")


def seed_dim_channel(
    manifest: dict[str, Any],
) -> None:
    rows = build_dim_channel_rows(manifest)

    validate_dim_channel_rows(
        rows,
        manifest,
    )

    print("dim_channel generation passed.")
    print(f"Total rows: {len(rows)}")
    print(f"First row: {rows[0]}")
    print(f"Last row: {rows[-1]}")

    insert_dim_channel_rows(rows)


def allocate_product_counts(
    manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    使用最大余数法，将当前 Profile 的商品总数
    按子品类权重分配。

    目标：
    1. 分配结果总数严格等于 Profile.products；
    2. 同一 Manifest 每次得到相同结果；
    3. 小数余数相同时，按 Manifest 中的原始顺序决定。
    """
    _, profile = get_active_scale_profile(manifest)

    total_product_count = profile["products"]

    subcategories = manifest[
        "product_generation"
    ][
        "subcategories"
    ]

    allocations: list[dict[str, Any]] = []

    for index, item in enumerate(subcategories):
        weight = Decimal(str(item["weight"]))

        exact_count = (
            Decimal(total_product_count)
            * weight
        )

        base_count = int(
            exact_count.to_integral_value(
                rounding=ROUND_FLOOR,
            )
        )

        remainder = (
            exact_count
            - Decimal(base_count)
        )

        allocations.append(
            {
                "category": item[
                    "category"
                ].strip(),
                "subcategory": item[
                    "subcategory"
                ].strip(),
                "weight": weight,
                "exact_count": exact_count,
                "allocated_count": base_count,
                "_remainder": remainder,
                "_manifest_index": index,
            }
        )

    base_total = sum(
        item["allocated_count"]
        for item in allocations
    )

    remaining_count = (
        total_product_count
        - base_total
    )

    if remaining_count < 0:
        raise ValueError(
            "商品基础分配数量超过 Profile 商品总数："
            f"base_total={base_total}, "
            f"total_product_count={total_product_count}"
        )

    remainder_order = sorted(
        range(len(allocations)),
        key=lambda index: (
            -allocations[index]["_remainder"],
            allocations[index]["_manifest_index"],
        ),
    )

    if remaining_count > len(remainder_order):
        raise ValueError(
            "最大余数法无法完成商品数量分配："
            f"remaining_count={remaining_count}, "
            f"subcategory_count={len(remainder_order)}"
        )

    for index in remainder_order[:remaining_count]:
        allocations[index][
            "allocated_count"
        ] += 1

    for item in allocations:
        item.pop("_remainder")
        item.pop("_manifest_index")

    return allocations


def allocate_launch_cohort_counts(
    manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    使用最大余数法，将商品总数分配到各上市批次。
    """
    _, profile = get_active_scale_profile(manifest)

    total_product_count = profile["products"]

    launch_cohorts = manifest[
        "product_generation"
    ][
        "launch_cohorts"
    ]

    allocations: list[dict[str, Any]] = []

    for index, cohort in enumerate(launch_cohorts):
        ratio = Decimal(str(cohort["ratio"]))

        exact_count = (
            Decimal(total_product_count)
            * ratio
        )

        base_count = int(
            exact_count.to_integral_value(
                rounding=ROUND_FLOOR,
            )
        )

        allocations.append(
            {
                "cohort_name": cohort[
                    "cohort_name"
                ].strip(),
                "start_date": parse_manifest_date(
                    cohort["start_date"],
                    (
                        "product_generation."
                        f"launch_cohorts[{index}]."
                        "start_date"
                    ),
                ),
                "end_date": parse_manifest_date(
                    cohort["end_date"],
                    (
                        "product_generation."
                        f"launch_cohorts[{index}]."
                        "end_date"
                    ),
                ),
                "allocated_count": base_count,
                "_remainder": (
                    exact_count
                    - Decimal(base_count)
                ),
                "_manifest_index": index,
            }
        )

    base_total = sum(
        item["allocated_count"]
        for item in allocations
    )

    remaining_count = (
        total_product_count
        - base_total
    )

    remainder_order = sorted(
        range(len(allocations)),
        key=lambda index: (
            -allocations[index]["_remainder"],
            allocations[index]["_manifest_index"],
        ),
    )

    if remaining_count > len(remainder_order):
        raise ValueError(
            "上市批次数量无法完成分配："
            f"remaining_count={remaining_count}"
        )

    for index in remainder_order[:remaining_count]:
        allocations[index][
            "allocated_count"
        ] += 1

    for item in allocations:
        item.pop("_remainder")
        item.pop("_manifest_index")

    return allocations


def build_dim_product_rows(
    manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    根据 Manifest 确定性生成 dim_product 行。

    本函数使用局部 Random 实例，不修改全局随机状态。
    """
    _, profile = get_active_scale_profile(manifest)

    total_product_count = profile["products"]

    product_config = manifest[
        "product_generation"
    ]

    random_seed = manifest[
        "generation"
    ][
        "random_seed"
    ]

    if (
        isinstance(random_seed, bool)
        or not isinstance(random_seed, int)
    ):
        raise ValueError(
            "generation.random_seed 必须是整数。"
        )

    rng = random.Random(random_seed)

    product_allocations = (
        allocate_product_counts(manifest)
    )

    validate_product_count_allocations(
        product_allocations,
        manifest,
    )

    product_specs: list[tuple[str, str]] = []

    for allocation in product_allocations:
        product_specs.extend(
            [
                (
                    allocation["category"],
                    allocation["subcategory"],
                )
            ]
            * allocation["allocated_count"]
        )

    if len(product_specs) != total_product_count:
        raise ValueError(
            "商品规格展开后的数量不正确："
            f"expected={total_product_count}, "
            f"actual={len(product_specs)}"
        )

    brands = [
        brand.strip()
        for brand in product_config["brands"]
    ]

    # 先轮流分配品牌，再打乱。
    # 这样品牌数量最多只相差 1。
    brand_pool = [
        brands[index % len(brands)]
        for index in range(total_product_count)
    ]

    rng.shuffle(brand_pool)

    cohort_pool: list[dict[str, Any]] = []

    for allocation in (
        allocate_launch_cohort_counts(manifest)
    ):
        cohort_pool.extend(
            [allocation]
            * allocation["allocated_count"]
        )

    if len(cohort_pool) != total_product_count:
        raise ValueError(
            "上市批次展开后的数量不正确。"
        )

    rng.shuffle(cohort_pool)

    active_ratio = Decimal(
        str(product_config["active_ratio"])
    )

    active_count = int(
        (
            Decimal(total_product_count)
            * active_ratio
        ).quantize(
            Decimal("1"),
            rounding=ROUND_HALF_UP,
        )
    )

    active_pool = (
        [True] * active_count
        + [False]
        * (total_product_count - active_count)
    )

    rng.shuffle(active_pool)

    subcategory_config = {
        (
            item["category"].strip(),
            item["subcategory"].strip(),
        ): item
        for item in product_config[
            "subcategories"
        ]
    }

    sku_prefix = product_config[
        "sku_prefix"
    ].strip()

    rows: list[dict[str, Any]] = []

    for product_number, (
        category,
        subcategory,
    ) in enumerate(
        product_specs,
        start=1,
    ):
        config = subcategory_config[
            (category, subcategory)
        ]

        # 当前 Manifest 的价格上下限均为整数。
        # 这里生成整元吊牌价，再保存为两位小数。
        price_min = int(
            config["list_price_min"]
        )

        price_max = int(
            config["list_price_max"]
        )

        list_price = Decimal(
            rng.randint(
                price_min,
                price_max,
            )
        ).quantize(
            Decimal("0.01")
        )

        cohort = cohort_pool[
            product_number - 1
        ]

        cohort_day_count = (
            cohort["end_date"]
            - cohort["start_date"]
        ).days

        launch_date = (
            cohort["start_date"]
            + timedelta(
                days=rng.randint(
                    0,
                    cohort_day_count,
                )
            )
        )

        brand = brand_pool[
            product_number - 1
        ]

        sku_code = (
            f"{sku_prefix}"
            f"{product_number:06d}"
        )

        product_name = (
            f"{brand} "
            f"{subcategory} "
            f"{product_number:06d}"
        )

        rows.append(
            {
                "sku_code": sku_code,
                "product_name": product_name,
                "brand": brand,
                "category": category,
                "subcategory": subcategory,
                "list_price": list_price,
                "launch_date": launch_date,
                "is_active": active_pool[
                    product_number - 1
                ],
            }
        )

    return rows


def validate_dim_product_rows(
    rows: list[dict[str, Any]],
    manifest: dict[str, Any],
) -> None:
    """
    校验完整的 dim_product 生成结果。
    """
    if not rows:
        raise ValueError(
            "dim_product 生成结果不能为空。"
        )

    _, profile = get_active_scale_profile(manifest)

    expected_total = profile["products"]

    if len(rows) != expected_total:
        raise ValueError(
            "dim_product 行数不正确："
            f"expected={expected_total}, "
            f"actual={len(rows)}"
        )

    required_fields = {
        "sku_code",
        "product_name",
        "brand",
        "category",
        "subcategory",
        "list_price",
        "launch_date",
        "is_active",
    }

    sku_codes = [
        row["sku_code"]
        for row in rows
    ]

    if len(set(sku_codes)) != len(sku_codes):
        raise ValueError(
            "dim_product 存在重复 sku_code。"
        )

    product_names = [
        row["product_name"]
        for row in rows
    ]

    if len(set(product_names)) != len(
        product_names
    ):
        raise ValueError(
            "dim_product 存在重复 product_name。"
        )

    product_config = manifest[
        "product_generation"
    ]

    valid_brands = {
        brand.strip()
        for brand in product_config["brands"]
    }

    subcategory_config = {
        (
            item["category"].strip(),
            item["subcategory"].strip(),
        ): item
        for item in product_config[
            "subcategories"
        ]
    }

    actual_subcategory_counts: Counter[
        tuple[str, str]
    ] = Counter()

    actual_cohort_counts: Counter[str] = (
        Counter()
    )

    cohort_allocations = (
        allocate_launch_cohort_counts(manifest)
    )

    for index, row in enumerate(rows):
        if set(row.keys()) != required_fields:
            raise ValueError(
                f"dim_product 第 {index} 行字段不正确。"
            )

        for field_name in {
            "sku_code",
            "product_name",
            "brand",
            "category",
            "subcategory",
        }:
            value = row[field_name]

            if (
                not isinstance(value, str)
                or not value.strip()
            ):
                raise ValueError(
                    f"dim_product 第 {index} 行 "
                    f"{field_name} 必须是非空字符串。"
                )

        if row["brand"] not in valid_brands:
            raise ValueError(
                f"dim_product 第 {index} 行品牌无效："
                f"{row['brand']}"
            )

        category_key = (
            row["category"],
            row["subcategory"],
        )

        if category_key not in subcategory_config:
            raise ValueError(
                "dim_product 出现未配置的"
                "品类与子品类组合："
                f"{category_key}"
            )

        list_price = row["list_price"]

        if (
            isinstance(list_price, bool)
            or not isinstance(
                list_price,
                Decimal,
            )
            or list_price <= 0
        ):
            raise ValueError(
                f"dim_product 第 {index} 行 "
                "list_price 必须是正 Decimal。"
            )

        price_config = subcategory_config[
            category_key
        ]

        price_min = Decimal(
            str(
                price_config[
                    "list_price_min"
                ]
            )
        )

        price_max = Decimal(
            str(
                price_config[
                    "list_price_max"
                ]
            )
        )

        if not price_min <= list_price <= price_max:
            raise ValueError(
                f"dim_product 第 {index} 行价格"
                "超出子品类区间："
                f"{list_price}"
            )

        launch_date = row["launch_date"]

        if not isinstance(launch_date, date):
            raise ValueError(
                f"dim_product 第 {index} 行 "
                "launch_date 必须是 date。"
            )

        matched_cohorts = [
            cohort
            for cohort in cohort_allocations
            if (
                cohort["start_date"]
                <= launch_date
                <= cohort["end_date"]
            )
        ]

        if len(matched_cohorts) != 1:
            raise ValueError(
                f"dim_product 第 {index} 行上市日期"
                "无法唯一匹配上市批次："
                f"{launch_date}"
            )

        actual_cohort_counts[
            matched_cohorts[0]["cohort_name"]
        ] += 1

        if not isinstance(
            row["is_active"],
            bool,
        ):
            raise ValueError(
                f"dim_product 第 {index} 行 "
                "is_active 必须是布尔值。"
            )

        actual_subcategory_counts[
            category_key
        ] += 1

    expected_subcategory_counts = Counter(
        {
            (
                allocation["category"],
                allocation["subcategory"],
            ): allocation["allocated_count"]
            for allocation in (
                allocate_product_counts(manifest)
            )
        }
    )

    if (
        actual_subcategory_counts
        != expected_subcategory_counts
    ):
        raise ValueError(
            "dim_product 子品类数量分布不正确："
            f"expected={expected_subcategory_counts}, "
            f"actual={actual_subcategory_counts}"
        )

    expected_cohort_counts = Counter(
        {
            allocation["cohort_name"]:
                allocation["allocated_count"]
            for allocation in cohort_allocations
        }
    )

    if actual_cohort_counts != expected_cohort_counts:
        raise ValueError(
            "dim_product 上市批次数量不正确："
            f"expected={expected_cohort_counts}, "
            f"actual={actual_cohort_counts}"
        )

    expected_active_count = int(
        (
            Decimal(expected_total)
            * Decimal(
                str(product_config["active_ratio"])
            )
        ).quantize(
            Decimal("1"),
            rounding=ROUND_HALF_UP,
        )
    )

    actual_active_count = sum(
        row["is_active"]
        for row in rows
    )

    if actual_active_count != expected_active_count:
        raise ValueError(
            "dim_product 有效商品数量不正确："
            f"expected={expected_active_count}, "
            f"actual={actual_active_count}"
        )

    brand_counts = Counter(
        row["brand"]
        for row in rows
    )

    if (
        max(brand_counts.values())
        - min(brand_counts.values())
        > 1
    ):
        raise ValueError(
            "dim_product 品牌数量分配不均衡："
            f"{brand_counts}"
        )


def preview_dim_product_rows(
    manifest: dict[str, Any],
) -> None:
    rows = build_dim_product_rows(manifest)

    validate_dim_product_rows(
        rows,
        manifest,
    )

    # 再生成一次，验证确定性。
    repeated_rows = build_dim_product_rows(
        manifest
    )

    if rows != repeated_rows:
        raise ValueError(
            "dim_product 重复生成结果不一致，"
            "确定性校验失败。"
        )

    brand_counts = Counter(
        row["brand"]
        for row in rows
    )

    category_counts = Counter(
        row["category"]
        for row in rows
    )

    active_count = sum(
        row["is_active"]
        for row in rows
    )

    print("dim_product row preview passed.")
    print(f"Total rows: {len(rows)}")
    print(f"Active rows: {active_count}")
    print(
        f"Inactive rows: "
        f"{len(rows) - active_count}"
    )
    print(f"Brand counts: {dict(brand_counts)}")
    print(
        f"Category counts: "
        f"{dict(category_counts)}"
    )
    print(f"First row: {rows[0]}")
    print(f"Last row: {rows[-1]}")
    print("Deterministic check: passed.")


def insert_dim_product_rows(
    rows: list[dict[str, Any]],
) -> None:
    """
    将 dim_product 批量写入 PostgreSQL。

    安全策略：
    1. 生成结果不能为空；
    2. 目标表必须为空；
    3. 检查、插入和写后验证位于同一事务；
    4. 写入后逐字段比对数据库结果；
    5. 任意异常自动回滚。
    """
    if not rows:
        raise ValueError(
            "不能插入空的 dim_product 数据。"
        )

    insert_sql = text(
        """
        INSERT INTO beauty_bi_v2.dim_product (
            sku_code,
            product_name,
            brand,
            category,
            subcategory,
            list_price,
            launch_date,
            is_active
        )
        VALUES (
            :sku_code,
            :product_name,
            :brand,
            :category,
            :subcategory,
            :list_price,
            :launch_date,
            :is_active
        )
        """
    )

    select_sql = text(
        """
        SELECT
            sku_code,
            product_name,
            brand,
            category,
            subcategory,
            list_price,
            launch_date,
            is_active
        FROM beauty_bi_v2.dim_product
        ORDER BY sku_code
        """
    )

    with engine.begin() as connection:
        existing_count = connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM beauty_bi_v2.dim_product
                """
            )
        ).scalar_one()

        if existing_count != 0:
            raise RuntimeError(
                "beauty_bi_v2.dim_product 已存在数据，"
                "为避免重复写入，本次 Seed 已停止。"
                f" existing_count={existing_count}"
            )

        connection.execute(
            insert_sql,
            rows,
        )

        (
            actual_count,
            distinct_sku_count,
            active_count,
            inactive_count,
            min_launch_date,
            max_launch_date,
            min_list_price,
            max_list_price,
        ) = connection.execute(
            text(
                """
                SELECT
                    COUNT(*),
                    COUNT(DISTINCT sku_code),
                    COUNT(*) FILTER (
                        WHERE is_active
                    ),
                    COUNT(*) FILTER (
                        WHERE NOT is_active
                    ),
                    MIN(launch_date),
                    MAX(launch_date),
                    MIN(list_price),
                    MAX(list_price)
                FROM beauty_bi_v2.dim_product
                """
            )
        ).one()

        if actual_count != len(rows):
            raise RuntimeError(
                "dim_product 插入后的行数不正确："
                f"expected={len(rows)}, "
                f"actual={actual_count}"
            )

        if distinct_sku_count != actual_count:
            raise RuntimeError(
                "dim_product 数据库中存在重复 "
                "sku_code。"
            )

        if active_count + inactive_count != actual_count:
            raise RuntimeError(
                "dim_product 有效状态统计不完整："
                f"active={active_count}, "
                f"inactive={inactive_count}, "
                f"total={actual_count}"
            )

        database_rows = [
            dict(row)
            for row in connection.execute(
                select_sql
            ).mappings().all()
        ]

        expected_rows = sorted(
            rows,
            key=lambda row: row["sku_code"],
        )

        if database_rows != expected_rows:
            for expected_row, actual_row in zip(
                expected_rows,
                database_rows,
            ):
                if expected_row != actual_row:
                    raise RuntimeError(
                        "dim_product 数据库写入结果"
                        "与生成结果不一致："
                        f"expected={expected_row}, "
                        f"actual={actual_row}"
                    )

            raise RuntimeError(
                "dim_product 数据库写入结果"
                "与生成结果不一致。"
            )

    print("dim_product database seed passed.")
    print(f"Inserted rows: {actual_count}")
    print(f"Active rows: {active_count}")
    print(f"Inactive rows: {inactive_count}")
    print(
        "Launch date range: "
        f"{min_launch_date} -> {max_launch_date}"
    )
    print(
        "List price range: "
        f"{min_list_price} -> {max_list_price}"
    )
    print("Database row comparison: passed.")


def seed_dim_product(
    manifest: dict[str, Any],
) -> None:
    rows = build_dim_product_rows(manifest)

    validate_dim_product_rows(
        rows,
        manifest,
    )

    repeated_rows = build_dim_product_rows(
        manifest
    )

    if rows != repeated_rows:
        raise ValueError(
            "dim_product 重复生成结果不一致，"
            "确定性校验失败。"
        )

    active_count = sum(
        row["is_active"]
        for row in rows
    )

    print("dim_product generation passed.")
    print(f"Total rows: {len(rows)}")
    print(f"Active rows: {active_count}")
    print(
        f"Inactive rows: "
        f"{len(rows) - active_count}"
    )
    print(f"First row: {rows[0]}")
    print(f"Last row: {rows[-1]}")
    print("Deterministic check: passed.")

    insert_dim_product_rows(rows)


def validate_product_count_allocations(
    allocations: list[dict[str, Any]],
    manifest: dict[str, Any],
) -> None:
    """
    验证商品数量分配结果。
    """
    if not allocations:
        raise ValueError(
            "商品数量分配结果不能为空。"
        )

    _, profile = get_active_scale_profile(manifest)

    expected_total = profile["products"]

    actual_total = sum(
        item["allocated_count"]
        for item in allocations
    )

    if actual_total != expected_total:
        raise ValueError(
            "商品分配总数不符合预期："
            f"expected={expected_total}, "
            f"actual={actual_total}"
        )

    expected_subcategory_count = len(
        manifest[
            "product_generation"
        ][
            "subcategories"
        ]
    )

    if len(allocations) != expected_subcategory_count:
        raise ValueError(
            "商品分配结果的子品类数量不正确："
            f"expected={expected_subcategory_count}, "
            f"actual={len(allocations)}"
        )

    keys: set[tuple[str, str]] = set()

    for index, item in enumerate(allocations):
        key = (
            item["category"],
            item["subcategory"],
        )

        if key in keys:
            raise ValueError(
                "商品分配结果存在重复品类组合："
                f"{key}"
            )

        allocated_count = item[
            "allocated_count"
        ]

        if (
            isinstance(allocated_count, bool)
            or not isinstance(allocated_count, int)
            or allocated_count <= 0
        ):
            raise ValueError(
                f"商品分配结果第 {index} 项数量"
                "必须是正整数："
                f"{allocated_count!r}"
            )

        keys.add(key)


def preview_dim_product_allocation(
    manifest: dict[str, Any],
) -> None:
    allocations = allocate_product_counts(
        manifest
    )

    validate_product_count_allocations(
        allocations,
        manifest,
    )

    total_count = sum(
        item["allocated_count"]
        for item in allocations
    )

    print(
        "dim_product allocation preview passed."
    )
    print(f"Total products: {total_count}")

    for item in allocations:
        print(
            f"{item['category']}/"
            f"{item['subcategory']}: "
            f"weight={item['weight']}, "
            f"exact={item['exact_count']}, "
            f"allocated={item['allocated_count']}"
        )


def build_dim_campaign_rows(
    manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    从 Manifest 生成 dim_campaign 数据。

    campaign_id 由 PostgreSQL Identity 自动生成，
    因此不包含在生成结果中。
    """
    campaigns = manifest[
        "business_calendar"
    ][
        "campaigns"
    ]

    rows: list[dict[str, Any]] = []

    for index, campaign in enumerate(campaigns):
        field_prefix = (
            f"business_calendar.campaigns[{index}]"
        )

        rows.append(
            {
                "campaign_code": campaign[
                    "campaign_code"
                ].strip(),
                "campaign_family": campaign[
                    "campaign_family"
                ].strip(),
                "campaign_name": campaign[
                    "campaign_name"
                ].strip(),
                "campaign_type": campaign[
                    "campaign_type"
                ].strip(),
                "start_date": parse_manifest_date(
                    campaign["start_date"],
                    f"{field_prefix}.start_date",
                ),
                "end_date": parse_manifest_date(
                    campaign["end_date"],
                    f"{field_prefix}.end_date",
                ),
                "status_cutoff": (
                    parse_manifest_datetime(
                        campaign["status_cutoff"],
                        f"{field_prefix}.status_cutoff",
                    )
                ),
                "objective": campaign[
                    "objective"
                ].strip(),
                "is_active": True,
            }
        )

    return rows


def validate_dim_campaign_rows(
    rows: list[dict[str, Any]],
    manifest: dict[str, Any],
) -> None:
    """
    在写入数据库前校验 dim_campaign 生成结果。
    """
    if not rows:
        raise ValueError(
            "dim_campaign 生成结果不能为空。"
        )

    expected_count = len(
        manifest[
            "business_calendar"
        ][
            "campaigns"
        ]
    )

    if len(rows) != expected_count:
        raise ValueError(
            "dim_campaign 行数不符合预期："
            f"expected={expected_count}, "
            f"actual={len(rows)}"
        )

    required_fields = {
        "campaign_code",
        "campaign_family",
        "campaign_name",
        "campaign_type",
        "start_date",
        "end_date",
        "status_cutoff",
        "objective",
        "is_active",
    }

    string_fields = {
        "campaign_code",
        "campaign_family",
        "campaign_name",
        "campaign_type",
        "objective",
    }

    allowed_campaign_types = {
        "always_on",
        "major_promotion",
    }

    campaign_codes: set[str] = set()
    campaign_names: set[str] = set()

    actual_type_counts: Counter[str] = Counter()
    actual_family_counts: Counter[str] = Counter()

    for index, row in enumerate(rows):
        if set(row.keys()) != required_fields:
            raise ValueError(
                f"dim_campaign 第 {index} 行字段不正确。"
            )

        for field_name in string_fields:
            value = row[field_name]

            if (
                not isinstance(value, str)
                or not value.strip()
            ):
                raise ValueError(
                    f"dim_campaign 第 {index} 行 "
                    f"{field_name} 必须是非空字符串。"
                )

        campaign_code = row["campaign_code"]
        campaign_name = row["campaign_name"]
        campaign_type = row["campaign_type"]

        if campaign_code in campaign_codes:
            raise ValueError(
                "dim_campaign 存在重复 "
                f"campaign_code：{campaign_code}"
            )

        if campaign_name in campaign_names:
            raise ValueError(
                "dim_campaign 存在重复 "
                f"campaign_name：{campaign_name}"
            )

        if campaign_type not in allowed_campaign_types:
            raise ValueError(
                f"dim_campaign 第 {index} 行 "
                "campaign_type 不在允许范围内："
                f"{campaign_type!r}"
            )

        start_date = row["start_date"]
        end_date = row["end_date"]
        status_cutoff = row["status_cutoff"]

        if not isinstance(start_date, date):
            raise ValueError(
                f"dim_campaign 第 {index} 行 "
                "start_date 必须是 date。"
            )

        if not isinstance(end_date, date):
            raise ValueError(
                f"dim_campaign 第 {index} 行 "
                "end_date 必须是 date。"
            )

        if not isinstance(
            status_cutoff,
            datetime,
        ):
            raise ValueError(
                f"dim_campaign 第 {index} 行 "
                "status_cutoff 必须是 datetime。"
            )

        if start_date > end_date:
            raise ValueError(
                f"dim_campaign 第 {index} 行 "
                "end_date 不能早于 start_date。"
            )

        campaign_start_timestamp = (
            datetime.combine(
                start_date,
                datetime.min.time(),
            )
        )

        if status_cutoff >= campaign_start_timestamp:
            raise ValueError(
                f"dim_campaign 第 {index} 行 "
                "status_cutoff 必须早于活动开始日零点："
                f"status_cutoff={status_cutoff}, "
                "campaign_start="
                f"{campaign_start_timestamp}"
            )

        if not isinstance(row["is_active"], bool):
            raise ValueError(
                f"dim_campaign 第 {index} 行 "
                "is_active 必须是布尔值。"
            )

        if not row["is_active"]:
            raise ValueError(
                f"dim_campaign 第 {index} 行 "
                "当前生成规则要求 is_active=True。"
            )

        campaign_codes.add(campaign_code)
        campaign_names.add(campaign_name)

        actual_type_counts[campaign_type] += 1
        actual_family_counts[
            row["campaign_family"]
        ] += 1

    source_campaigns = manifest[
        "business_calendar"
    ][
        "campaigns"
    ]

    expected_type_counts = Counter(
        campaign["campaign_type"].strip()
        for campaign in source_campaigns
    )

    expected_family_counts = Counter(
        campaign["campaign_family"].strip()
        for campaign in source_campaigns
    )

    if actual_type_counts != expected_type_counts:
        raise ValueError(
            "dim_campaign 活动类型数量不正确："
            f"expected={expected_type_counts}, "
            f"actual={actual_type_counts}"
        )

    if actual_family_counts != expected_family_counts:
        raise ValueError(
            "dim_campaign 活动家族数量不正确："
            f"expected={expected_family_counts}, "
            f"actual={actual_family_counts}"
        )


def preview_dim_campaign_rows(
    manifest: dict[str, Any],
) -> None:
    rows = build_dim_campaign_rows(manifest)

    validate_dim_campaign_rows(
        rows,
        manifest,
    )

    repeated_rows = build_dim_campaign_rows(
        manifest
    )

    if rows != repeated_rows:
        raise ValueError(
            "dim_campaign 重复生成结果不一致。"
        )

    type_counts = Counter(
        row["campaign_type"]
        for row in rows
    )

    family_counts = Counter(
        row["campaign_family"]
        for row in rows
    )

    print("dim_campaign row preview passed.")
    print(f"Total rows: {len(rows)}")
    print(f"Type counts: {dict(type_counts)}")
    print(f"Family counts: {dict(family_counts)}")
    print(f"First row: {rows[0]}")
    print(f"Last row: {rows[-1]}")
    print("Deterministic check: passed.")


def insert_dim_campaign_rows(
    rows: list[dict[str, Any]],
) -> None:
    """
    将 dim_campaign 批量写入 PostgreSQL。

    安全策略：
    1. 生成结果不能为空；
    2. 目标表必须为空；
    3. 检查、插入和写后验证位于同一事务；
    4. 将数据库结果与生成结果逐行比较；
    5. 任意异常自动回滚。
    """
    if not rows:
        raise ValueError(
            "不能插入空的 dim_campaign 数据。"
        )

    insert_sql = text(
        """
        INSERT INTO beauty_bi_v2.dim_campaign (
            campaign_code,
            campaign_family,
            campaign_name,
            campaign_type,
            start_date,
            end_date,
            status_cutoff,
            objective,
            is_active
        )
        VALUES (
            :campaign_code,
            :campaign_family,
            :campaign_name,
            :campaign_type,
            :start_date,
            :end_date,
            :status_cutoff,
            :objective,
            :is_active
        )
        """
    )

    select_sql = text(
        """
        SELECT
            campaign_code,
            campaign_family,
            campaign_name,
            campaign_type,
            start_date,
            end_date,
            status_cutoff,
            objective,
            is_active
        FROM beauty_bi_v2.dim_campaign
        ORDER BY campaign_code
        """
    )

    with engine.begin() as connection:
        existing_count = connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM beauty_bi_v2.dim_campaign
                """
            )
        ).scalar_one()

        if existing_count != 0:
            raise RuntimeError(
                "beauty_bi_v2.dim_campaign 已存在数据，"
                "为避免重复写入，本次 Seed 已停止。"
                f" existing_count={existing_count}"
            )

        connection.execute(
            insert_sql,
            rows,
        )

        (
            actual_count,
            distinct_code_count,
            distinct_name_count,
            always_on_count,
            major_promotion_count,
            active_count,
            inactive_count,
            min_start_date,
            max_end_date,
        ) = connection.execute(
            text(
                """
                SELECT
                    COUNT(*),
                    COUNT(DISTINCT campaign_code),
                    COUNT(DISTINCT campaign_name),
                    COUNT(*) FILTER (
                        WHERE campaign_type = 'always_on'
                    ),
                    COUNT(*) FILTER (
                        WHERE campaign_type = 'major_promotion'
                    ),
                    COUNT(*) FILTER (
                        WHERE is_active
                    ),
                    COUNT(*) FILTER (
                        WHERE NOT is_active
                    ),
                    MIN(start_date),
                    MAX(end_date)
                FROM beauty_bi_v2.dim_campaign
                """
            )
        ).one()

        if actual_count != len(rows):
            raise RuntimeError(
                "dim_campaign 插入后的行数不正确："
                f"expected={len(rows)}, "
                f"actual={actual_count}"
            )

        if distinct_code_count != actual_count:
            raise RuntimeError(
                "dim_campaign 数据库中存在重复 "
                "campaign_code。"
            )

        if distinct_name_count != actual_count:
            raise RuntimeError(
                "dim_campaign 数据库中存在重复 "
                "campaign_name。"
            )

        expected_type_counts = Counter(
            row["campaign_type"]
            for row in rows
        )

        if (
            always_on_count
            != expected_type_counts["always_on"]
        ):
            raise RuntimeError(
                "dim_campaign always_on 数量不正确："
                "expected="
                f"{expected_type_counts['always_on']}, "
                f"actual={always_on_count}"
            )

        if (
            major_promotion_count
            != expected_type_counts[
                "major_promotion"
            ]
        ):
            raise RuntimeError(
                "dim_campaign major_promotion "
                "数量不正确："
                "expected="
                f"{expected_type_counts['major_promotion']}, "
                f"actual={major_promotion_count}"
            )

        expected_active_count = sum(
            row["is_active"]
            for row in rows
        )

        if active_count != expected_active_count:
            raise RuntimeError(
                "dim_campaign 启用活动数量不正确："
                f"expected={expected_active_count}, "
                f"actual={active_count}"
            )

        if active_count + inactive_count != actual_count:
            raise RuntimeError(
                "dim_campaign 活动状态统计不完整："
                f"active={active_count}, "
                f"inactive={inactive_count}, "
                f"total={actual_count}"
            )

        invalid_cutoff_count = connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM beauty_bi_v2.dim_campaign
                WHERE status_cutoff >= start_date::timestamp
                """
            )
        ).scalar_one()

        if invalid_cutoff_count != 0:
            raise RuntimeError(
                "dim_campaign 数据库中存在不合法的 "
                "status_cutoff："
                f"invalid_count={invalid_cutoff_count}"
            )

        database_rows = [
            dict(row)
            for row in connection.execute(
                select_sql
            ).mappings().all()
        ]

        expected_rows = sorted(
            rows,
            key=lambda row: row["campaign_code"],
        )

        if database_rows != expected_rows:
            for expected_row, actual_row in zip(
                expected_rows,
                database_rows,
            ):
                if expected_row != actual_row:
                    raise RuntimeError(
                        "dim_campaign 数据库写入结果"
                        "与生成结果不一致："
                        f"expected={expected_row}, "
                        f"actual={actual_row}"
                    )

            raise RuntimeError(
                "dim_campaign 数据库写入结果"
                "与生成结果不一致。"
            )

    print("dim_campaign database seed passed.")
    print(f"Inserted rows: {actual_count}")
    print(f"Always-on rows: {always_on_count}")
    print(
        "Major promotion rows: "
        f"{major_promotion_count}"
    )
    print(f"Active rows: {active_count}")
    print(f"Inactive rows: {inactive_count}")
    print(
        "Campaign date range: "
        f"{min_start_date} -> {max_end_date}"
    )
    print("Status cutoff check: passed.")
    print("Database row comparison: passed.")


def seed_dim_campaign(
    manifest: dict[str, Any],
) -> None:
    rows = build_dim_campaign_rows(manifest)

    validate_dim_campaign_rows(
        rows,
        manifest,
    )

    repeated_rows = build_dim_campaign_rows(
        manifest
    )

    if rows != repeated_rows:
        raise ValueError(
            "dim_campaign 重复生成结果不一致，"
            "确定性校验失败。"
        )

    type_counts = Counter(
        row["campaign_type"]
        for row in rows
    )

    print("dim_campaign generation passed.")
    print(f"Total rows: {len(rows)}")
    print(f"Type counts: {dict(type_counts)}")
    print(f"First row: {rows[0]}")
    print(f"Last row: {rows[-1]}")
    print("Deterministic check: passed.")

    insert_dim_campaign_rows(rows)


def build_dim_promotion_rows(
    manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    从 Manifest 生成 dim_promotion 数据。

    promotion_id 由 PostgreSQL Identity 自动生成。

    campaign_code 是 Manifest 的关联校验字段，
    不属于 dim_promotion 数据库字段，因此不写入结果。
    """
    promotions = manifest[
        "fixed_dimensions"
    ][
        "promotions"
    ]

    rows: list[dict[str, Any]] = []

    for index, promotion in enumerate(promotions):
        field_prefix = (
            f"fixed_dimensions.promotions[{index}]"
        )

        target_member_level = promotion[
            "target_member_level"
        ]

        if isinstance(target_member_level, str):
            target_member_level = (
                target_member_level.strip()
            )

        discount_rate = Decimal(
            str(promotion["discount_rate"])
        ).quantize(
            Decimal("0.0001")
        )

        rows.append(
            {
                "promotion_code": promotion[
                    "promotion_code"
                ].strip(),
                "promotion_name": promotion[
                    "promotion_name"
                ].strip(),
                "promotion_type": promotion[
                    "promotion_type"
                ].strip(),
                "discount_rate": discount_rate,
                "start_date": parse_manifest_date(
                    promotion["start_date"],
                    f"{field_prefix}.start_date",
                ),
                "end_date": parse_manifest_date(
                    promotion["end_date"],
                    f"{field_prefix}.end_date",
                ),
                "target_member_level": (
                    target_member_level
                ),
                "is_active": promotion[
                    "is_active"
                ],
            }
        )

    return rows


def validate_dim_promotion_rows(
    rows: list[dict[str, Any]],
    manifest: dict[str, Any],
) -> None:
    """
    在写入数据库前校验 dim_promotion 生成结果。
    """
    if not rows:
        raise ValueError(
            "dim_promotion 生成结果不能为空。"
        )

    source_promotions = manifest[
        "fixed_dimensions"
    ][
        "promotions"
    ]

    expected_count = len(source_promotions)

    if len(rows) != expected_count:
        raise ValueError(
            "dim_promotion 行数不符合预期："
            f"expected={expected_count}, "
            f"actual={len(rows)}"
        )

    required_fields = {
        "promotion_code",
        "promotion_name",
        "promotion_type",
        "discount_rate",
        "start_date",
        "end_date",
        "target_member_level",
        "is_active",
    }

    allowed_promotion_types = {
        "product_discount",
        "campaign_price",
    }

    promotion_codes: set[str] = set()
    promotion_names: set[str] = set()

    actual_type_counts: Counter[str] = Counter()

    for index, row in enumerate(rows):
        if set(row.keys()) != required_fields:
            raise ValueError(
                f"dim_promotion 第 {index} 行字段不正确："
                f"{sorted(row.keys())}"
            )

        for field_name in {
            "promotion_code",
            "promotion_name",
            "promotion_type",
        }:
            value = row[field_name]

            if (
                not isinstance(value, str)
                or not value.strip()
            ):
                raise ValueError(
                    f"dim_promotion 第 {index} 行 "
                    f"{field_name} 必须是非空字符串。"
                )

        promotion_code = row[
            "promotion_code"
        ]

        promotion_name = row[
            "promotion_name"
        ]

        promotion_type = row[
            "promotion_type"
        ]

        if promotion_code == "NO_PROMOTION":
            raise ValueError(
                "dim_promotion 不能包含 "
                "NO_PROMOTION 记录。"
            )

        if promotion_code in promotion_codes:
            raise ValueError(
                "dim_promotion 存在重复 "
                f"promotion_code：{promotion_code}"
            )

        if promotion_name in promotion_names:
            raise ValueError(
                "dim_promotion 存在重复 "
                f"promotion_name：{promotion_name}"
            )

        if (
            promotion_type
            not in allowed_promotion_types
        ):
            raise ValueError(
                f"dim_promotion 第 {index} 行 "
                "promotion_type 不在允许范围内："
                f"{promotion_type!r}"
            )

        discount_rate = row[
            "discount_rate"
        ]

        if (
            isinstance(discount_rate, bool)
            or not isinstance(
                discount_rate,
                Decimal,
            )
            or not (
                Decimal("0")
                < discount_rate
                < Decimal("1")
            )
        ):
            raise ValueError(
                f"dim_promotion 第 {index} 行 "
                "discount_rate 必须是 "
                "(0, 1) 范围内的 Decimal："
                f"{discount_rate!r}"
            )

        if (
            discount_rate
            != discount_rate.quantize(
                Decimal("0.0001")
            )
        ):
            raise ValueError(
                f"dim_promotion 第 {index} 行 "
                "discount_rate 最多只能有四位小数："
                f"{discount_rate}"
            )

        start_date = row["start_date"]
        end_date = row["end_date"]

        if not isinstance(start_date, date):
            raise ValueError(
                f"dim_promotion 第 {index} 行 "
                "start_date 必须是 date。"
            )

        if not isinstance(end_date, date):
            raise ValueError(
                f"dim_promotion 第 {index} 行 "
                "end_date 必须是 date。"
            )

        if start_date > end_date:
            raise ValueError(
                f"dim_promotion 第 {index} 行 "
                "end_date 不能早于 start_date。"
            )

        target_member_level = row[
            "target_member_level"
        ]

        if target_member_level is not None:
            if (
                not isinstance(
                    target_member_level,
                    str,
                )
                or not target_member_level.strip()
            ):
                raise ValueError(
                    f"dim_promotion 第 {index} 行 "
                    "target_member_level 必须是 "
                    "None 或非空字符串。"
                )

        if not isinstance(
            row["is_active"],
            bool,
        ):
            raise ValueError(
                f"dim_promotion 第 {index} 行 "
                "is_active 必须是布尔值。"
            )

        promotion_codes.add(
            promotion_code
        )

        promotion_names.add(
            promotion_name
        )

        actual_type_counts[
            promotion_type
        ] += 1

    expected_type_counts = Counter(
        promotion[
            "promotion_type"
        ].strip()
        for promotion in source_promotions
    )

    if actual_type_counts != expected_type_counts:
        raise ValueError(
            "dim_promotion 类型数量不正确："
            f"expected={expected_type_counts}, "
            f"actual={actual_type_counts}"
        )

    expected_active_count = sum(
        promotion["is_active"]
        for promotion in source_promotions
    )

    actual_active_count = sum(
        row["is_active"]
        for row in rows
    )

    if actual_active_count != expected_active_count:
        raise ValueError(
            "dim_promotion 启用状态数量不正确："
            f"expected={expected_active_count}, "
            f"actual={actual_active_count}"
        )

    expected_targeted_count = sum(
        promotion[
            "target_member_level"
        ] is not None
        for promotion in source_promotions
    )

    actual_targeted_count = sum(
        row[
            "target_member_level"
        ] is not None
        for row in rows
    )

    if (
        actual_targeted_count
        != expected_targeted_count
    ):
        raise ValueError(
            "dim_promotion 会员定向促销数量不正确："
            f"expected={expected_targeted_count}, "
            f"actual={actual_targeted_count}"
        )


def preview_dim_promotion_rows(
    manifest: dict[str, Any],
) -> None:
    rows = build_dim_promotion_rows(
        manifest
    )

    validate_dim_promotion_rows(
        rows,
        manifest,
    )

    repeated_rows = build_dim_promotion_rows(
        manifest
    )

    if rows != repeated_rows:
        raise ValueError(
            "dim_promotion 重复生成结果不一致，"
            "确定性校验失败。"
        )

    type_counts = Counter(
        row["promotion_type"]
        for row in rows
    )

    active_count = sum(
        row["is_active"]
        for row in rows
    )

    targeted_count = sum(
        row["target_member_level"] is not None
        for row in rows
    )

    discount_rates = [
        row["discount_rate"]
        for row in rows
    ]

    print("dim_promotion row preview passed.")
    print(f"Total rows: {len(rows)}")
    print(f"Type counts: {dict(type_counts)}")
    print(f"Active rows: {active_count}")
    print(
        f"Inactive rows: "
        f"{len(rows) - active_count}"
    )
    print(
        "Member-targeted rows: "
        f"{targeted_count}"
    )
    print(
        "Discount rate range: "
        f"{min(discount_rates)} -> "
        f"{max(discount_rates)}"
    )
    print(f"First row: {rows[0]}")
    print(f"Last row: {rows[-1]}")
    print("Deterministic check: passed.")


def insert_dim_promotion_rows(
    rows: list[dict[str, Any]],
) -> None:
    """
    将 dim_promotion 批量写入 PostgreSQL。

    安全策略：
    1. 生成结果不能为空；
    2. 目标表必须为空；
    3. 检查、插入和写后验证位于同一事务；
    4. 数据库结果与生成结果逐行比较；
    5. 任意异常自动回滚。
    """
    if not rows:
        raise ValueError(
            "不能插入空的 dim_promotion 数据。"
        )

    insert_sql = text(
        """
        INSERT INTO beauty_bi_v2.dim_promotion (
            promotion_code,
            promotion_name,
            promotion_type,
            discount_rate,
            start_date,
            end_date,
            target_member_level,
            is_active
        )
        VALUES (
            :promotion_code,
            :promotion_name,
            :promotion_type,
            :discount_rate,
            :start_date,
            :end_date,
            :target_member_level,
            :is_active
        )
        """
    )

    select_sql = text(
        """
        SELECT
            promotion_code,
            promotion_name,
            promotion_type,
            discount_rate,
            start_date,
            end_date,
            target_member_level,
            is_active
        FROM beauty_bi_v2.dim_promotion
        ORDER BY promotion_code
        """
    )

    with engine.begin() as connection:
        existing_count = connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM beauty_bi_v2.dim_promotion
                """
            )
        ).scalar_one()

        if existing_count != 0:
            raise RuntimeError(
                "beauty_bi_v2.dim_promotion 已存在数据，"
                "为避免重复写入，本次 Seed 已停止。"
                f" existing_count={existing_count}"
            )

        connection.execute(
            insert_sql,
            rows,
        )

        (
            actual_count,
            distinct_code_count,
            distinct_name_count,
            product_discount_count,
            campaign_price_count,
            active_count,
            inactive_count,
            targeted_count,
            min_discount_rate,
            max_discount_rate,
            min_start_date,
            max_end_date,
        ) = connection.execute(
            text(
                """
                SELECT
                    COUNT(*),
                    COUNT(DISTINCT promotion_code),
                    COUNT(DISTINCT promotion_name),
                    COUNT(*) FILTER (
                        WHERE promotion_type =
                            'product_discount'
                    ),
                    COUNT(*) FILTER (
                        WHERE promotion_type =
                            'campaign_price'
                    ),
                    COUNT(*) FILTER (
                        WHERE is_active
                    ),
                    COUNT(*) FILTER (
                        WHERE NOT is_active
                    ),
                    COUNT(*) FILTER (
                        WHERE target_member_level
                            IS NOT NULL
                    ),
                    MIN(discount_rate),
                    MAX(discount_rate),
                    MIN(start_date),
                    MAX(end_date)
                FROM beauty_bi_v2.dim_promotion
                """
            )
        ).one()

        if actual_count != len(rows):
            raise RuntimeError(
                "dim_promotion 插入后的行数不正确："
                f"expected={len(rows)}, "
                f"actual={actual_count}"
            )

        if distinct_code_count != actual_count:
            raise RuntimeError(
                "dim_promotion 数据库中存在重复 "
                "promotion_code。"
            )

        if distinct_name_count != actual_count:
            raise RuntimeError(
                "dim_promotion 数据库中存在重复 "
                "promotion_name。"
            )

        expected_type_counts = Counter(
            row["promotion_type"]
            for row in rows
        )

        if (
            product_discount_count
            != expected_type_counts[
                "product_discount"
            ]
        ):
            raise RuntimeError(
                "dim_promotion product_discount "
                "数量不正确："
                "expected="
                f"{expected_type_counts['product_discount']}, "
                f"actual={product_discount_count}"
            )

        if (
            campaign_price_count
            != expected_type_counts[
                "campaign_price"
            ]
        ):
            raise RuntimeError(
                "dim_promotion campaign_price "
                "数量不正确："
                "expected="
                f"{expected_type_counts['campaign_price']}, "
                f"actual={campaign_price_count}"
            )

        expected_active_count = sum(
            row["is_active"]
            for row in rows
        )

        if active_count != expected_active_count:
            raise RuntimeError(
                "dim_promotion 启用数量不正确："
                f"expected={expected_active_count}, "
                f"actual={active_count}"
            )

        if active_count + inactive_count != actual_count:
            raise RuntimeError(
                "dim_promotion 状态统计不完整："
                f"active={active_count}, "
                f"inactive={inactive_count}, "
                f"total={actual_count}"
            )

        expected_targeted_count = sum(
            row["target_member_level"] is not None
            for row in rows
        )

        if targeted_count != expected_targeted_count:
            raise RuntimeError(
                "dim_promotion 会员定向数量不正确："
                f"expected={expected_targeted_count}, "
                f"actual={targeted_count}"
            )

        invalid_discount_count = connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM beauty_bi_v2.dim_promotion
                WHERE discount_rate <= 0
                   OR discount_rate >= 1
                """
            )
        ).scalar_one()

        if invalid_discount_count != 0:
            raise RuntimeError(
                "dim_promotion 数据库中存在非法 "
                "discount_rate："
                f"invalid_count={invalid_discount_count}"
            )

        invalid_date_count = connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM beauty_bi_v2.dim_promotion
                WHERE start_date > end_date
                """
            )
        ).scalar_one()

        if invalid_date_count != 0:
            raise RuntimeError(
                "dim_promotion 数据库中存在非法日期区间："
                f"invalid_count={invalid_date_count}"
            )

        no_promotion_count = connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM beauty_bi_v2.dim_promotion
                WHERE promotion_code = 'NO_PROMOTION'
                """
            )
        ).scalar_one()

        if no_promotion_count != 0:
            raise RuntimeError(
                "dim_promotion 中不应存在 "
                "NO_PROMOTION 记录。"
            )

        database_rows = [
            dict(row)
            for row in connection.execute(
                select_sql
            ).mappings().all()
        ]

        expected_rows = sorted(
            rows,
            key=lambda row: row["promotion_code"],
        )

        if database_rows != expected_rows:
            for expected_row, actual_row in zip(
                expected_rows,
                database_rows,
            ):
                if expected_row != actual_row:
                    raise RuntimeError(
                        "dim_promotion 数据库写入结果"
                        "与生成结果不一致："
                        f"expected={expected_row}, "
                        f"actual={actual_row}"
                    )

            raise RuntimeError(
                "dim_promotion 数据库写入结果"
                "与生成结果不一致。"
            )

    print("dim_promotion database seed passed.")
    print(f"Inserted rows: {actual_count}")
    print(
        "Product discount rows: "
        f"{product_discount_count}"
    )
    print(
        "Campaign price rows: "
        f"{campaign_price_count}"
    )
    print(f"Active rows: {active_count}")
    print(f"Inactive rows: {inactive_count}")
    print(
        "Member-targeted rows: "
        f"{targeted_count}"
    )
    print(
        "Discount rate range: "
        f"{min_discount_rate} -> "
        f"{max_discount_rate}"
    )
    print(
        "Promotion date range: "
        f"{min_start_date} -> {max_end_date}"
    )
    print("Discount rate check: passed.")
    print("Date range check: passed.")
    print("NO_PROMOTION check: passed.")
    print("Database row comparison: passed.")


def seed_dim_promotion(
    manifest: dict[str, Any],
) -> None:
    rows = build_dim_promotion_rows(
        manifest
    )

    validate_dim_promotion_rows(
        rows,
        manifest,
    )

    repeated_rows = build_dim_promotion_rows(
        manifest
    )

    if rows != repeated_rows:
        raise ValueError(
            "dim_promotion 重复生成结果不一致，"
            "确定性校验失败。"
        )

    type_counts = Counter(
        row["promotion_type"]
        for row in rows
    )

    active_count = sum(
        row["is_active"]
        for row in rows
    )

    targeted_count = sum(
        row["target_member_level"] is not None
        for row in rows
    )

    print("dim_promotion generation passed.")
    print(f"Total rows: {len(rows)}")
    print(f"Type counts: {dict(type_counts)}")
    print(f"Active rows: {active_count}")
    print(
        f"Inactive rows: "
        f"{len(rows) - active_count}"
    )
    print(
        "Member-targeted rows: "
        f"{targeted_count}"
    )
    print(f"First row: {rows[0]}")
    print(f"Last row: {rows[-1]}")
    print("Deterministic check: passed.")

    insert_dim_promotion_rows(rows)


def allocate_weighted_counts(
    total_count: int,
    weighted_items: list[tuple[str, Any]],
    allocation_name: str,
) -> dict[str, int]:
    """
    使用最大余数法，将总数按权重确定性分配。

    weighted_items 示例：

    [
        ("legacy", 0.30),
        ("first_seen_2024", 0.35),
        ("first_seen_2025", 0.35),
    ]
    """
    if (
        isinstance(total_count, bool)
        or not isinstance(total_count, int)
        or total_count <= 0
    ):
        raise ValueError(
            f"{allocation_name} 的 total_count "
            "必须是正整数。"
        )

    if not weighted_items:
        raise ValueError(
            f"{allocation_name} 的权重配置不能为空。"
        )

    allocations: list[dict[str, Any]] = []
    keys: set[str] = set()

    for index, (
        item_key,
        raw_weight,
    ) in enumerate(weighted_items):
        if (
            not isinstance(item_key, str)
            or not item_key.strip()
        ):
            raise ValueError(
                f"{allocation_name} 第 {index} 项"
                "必须使用非空字符串键。"
            )

        item_key = item_key.strip()

        if item_key in keys:
            raise ValueError(
                f"{allocation_name} 存在重复键："
                f"{item_key}"
            )

        try:
            weight = Decimal(
                str(raw_weight)
            )
        except Exception as exc:
            raise ValueError(
                f"{allocation_name}[{item_key}] "
                "权重无法转换为 Decimal："
                f"{raw_weight!r}"
            ) from exc

        if (
            weight <= Decimal("0")
            or weight > Decimal("1")
        ):
            raise ValueError(
                f"{allocation_name}[{item_key}] "
                "权重必须位于 (0, 1]："
                f"{weight}"
            )

        exact_count = (
            Decimal(total_count)
            * weight
        )

        base_count = int(
            exact_count.to_integral_value(
                rounding=ROUND_FLOOR,
            )
        )

        allocations.append(
            {
                "item_key": item_key,
                "allocated_count": base_count,
                "_remainder": (
                    exact_count
                    - Decimal(base_count)
                ),
                "_source_index": index,
            }
        )

        keys.add(item_key)

    base_total = sum(
        item["allocated_count"]
        for item in allocations
    )

    remaining_count = (
        total_count - base_total
    )

    if remaining_count < 0:
        raise ValueError(
            f"{allocation_name} 基础分配数量"
            "超过总数："
            f"base_total={base_total}, "
            f"total_count={total_count}"
        )

    remainder_order = sorted(
        range(len(allocations)),
        key=lambda index: (
            -allocations[index]["_remainder"],
            allocations[index]["_source_index"],
        ),
    )

    if remaining_count > len(
        remainder_order
    ):
        raise ValueError(
            f"{allocation_name} 无法完成"
            "最大余数分配："
            f"remaining_count={remaining_count}"
        )

    for index in remainder_order[
        :remaining_count
    ]:
        allocations[index][
            "allocated_count"
        ] += 1

    result = {
        item["item_key"]:
            item["allocated_count"]
        for item in allocations
    }

    if sum(result.values()) != total_count:
        raise ValueError(
            f"{allocation_name} 分配总数不正确："
            f"expected={total_count}, "
            f"actual={sum(result.values())}"
        )

    return result


def allocate_customer_home_region_counts(
    manifest: dict[str, Any],
) -> dict[str, int]:
    """
    先按 city_tier 权重分配客户，
    再在同一等级内按 Manifest 顺序均匀分配地区。
    """
    _, profile = get_active_scale_profile(
        manifest
    )

    total_customer_count = profile[
        "customers"
    ]

    region_distribution = manifest[
        "customer_generation"
    ][
        "home_region_distribution"
    ]

    city_tier_weights = region_distribution[
        "city_tier_weights"
    ]

    city_tier_counts = (
        allocate_weighted_counts(
            total_count=total_customer_count,
            weighted_items=[
                (
                    city_tier,
                    weight,
                )
                for city_tier, weight
                in city_tier_weights.items()
            ],
            allocation_name=(
                "customer home region city tier"
            ),
        )
    )

    regions = manifest[
        "fixed_dimensions"
    ][
        "regions"
    ]

    region_counts: dict[str, int] = {}

    for city_tier, tier_count in (
        city_tier_counts.items()
    ):
        region_codes = [
            region["region_code"].strip()
            for region in regions
            if (
                region["city_tier"].strip()
                == city_tier
            )
        ]

        if not region_codes:
            raise ValueError(
                "客户地区分配找不到对应城市等级："
                f"{city_tier}"
            )

        base_count, remainder = divmod(
            tier_count,
            len(region_codes),
        )

        for index, region_code in enumerate(
            region_codes
        ):
            region_counts[region_code] = (
                base_count
                + (
                    1
                    if index < remainder
                    else 0
                )
            )

    if (
        sum(region_counts.values())
        != total_customer_count
    ):
        raise ValueError(
            "客户地区分配总数不正确："
            f"expected={total_customer_count}, "
            f"actual={sum(region_counts.values())}"
        )

    return region_counts


def build_dim_customer_rows(
    manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    确定性生成 dim_customer 暂存行。

    生成阶段使用 home_region_code。
    正式写库时再转换为 home_region_id。
    """
    _, profile = get_active_scale_profile(
        manifest
    )

    total_customer_count = profile[
        "customers"
    ]

    config = manifest[
        "customer_generation"
    ]

    random_seed = manifest[
        "generation"
    ][
        "random_seed"
    ]

    rng = random.Random(random_seed)

    first_seen_cohorts = config[
        "first_seen_cohorts"
    ]

    cohort_counts = allocate_weighted_counts(
        total_count=total_customer_count,
        weighted_items=[
            (
                cohort[
                    "cohort_name"
                ].strip(),
                cohort["ratio"],
            )
            for cohort in first_seen_cohorts
        ],
        allocation_name=(
            "customer first_seen cohort"
        ),
    )

    cohort_pool: list[
        dict[str, Any]
    ] = []

    for index, cohort in enumerate(
        first_seen_cohorts
    ):
        cohort_name = cohort[
            "cohort_name"
        ].strip()

        start_date = parse_manifest_date(
            cohort["start_date"],
            (
                "customer_generation."
                f"first_seen_cohorts[{index}]."
                "start_date"
            ),
        )

        end_date = parse_manifest_date(
            cohort["end_date"],
            (
                "customer_generation."
                f"first_seen_cohorts[{index}]."
                "end_date"
            ),
        )

        cohort_pool.extend(
            [
                {
                    "cohort_name": cohort_name,
                    "start_date": start_date,
                    "end_date": end_date,
                }
            ]
            * cohort_counts[cohort_name]
        )

    if (
        len(cohort_pool)
        != total_customer_count
    ):
        raise ValueError(
            "客户 first_seen 批次池数量不正确。"
        )

    rng.shuffle(cohort_pool)

    status_distribution = config[
        "customer_status_distribution"
    ]

    status_counts = allocate_weighted_counts(
        total_count=total_customer_count,
        weighted_items=[
            (status, probability)
            for status, probability
            in status_distribution.items()
        ],
        allocation_name="customer status",
    )

    status_pool: list[str] = []

    for status, count in (
        status_counts.items()
    ):
        status_pool.extend(
            [status] * count
        )

    rng.shuffle(status_pool)

    region_counts = (
        allocate_customer_home_region_counts(
            manifest
        )
    )

    region_pool: list[str] = []

    for region_code, count in (
        region_counts.items()
    ):
        region_pool.extend(
            [region_code] * count
        )

    if (
        len(region_pool)
        != total_customer_count
    ):
        raise ValueError(
            "客户地区池数量不正确。"
        )

    rng.shuffle(region_pool)

    customer_code_prefix = config[
        "customer_code_prefix"
    ].strip()

    customer_code_width = config[
        "customer_code_width"
    ]

    rows: list[dict[str, Any]] = []

    for customer_number in range(
        1,
        total_customer_count + 1,
    ):
        cohort = cohort_pool[
            customer_number - 1
        ]

        cohort_day_count = (
            cohort["end_date"]
            - cohort["start_date"]
        ).days

        first_seen_date = (
            cohort["start_date"]
            + timedelta(
                days=rng.randint(
                    0,
                    cohort_day_count,
                )
            )
        )

        customer_code = (
            f"{customer_code_prefix}"
            f"{customer_number:0{customer_code_width}d}"
        )

        rows.append(
            {
                "customer_code": customer_code,
                "first_seen_date": (
                    first_seen_date
                ),
                "home_region_code": region_pool[
                    customer_number - 1
                ],
                "customer_status": status_pool[
                    customer_number - 1
                ],
            }
        )

    return rows


def validate_dim_customer_rows(
    rows: list[dict[str, Any]],
    manifest: dict[str, Any],
) -> None:
    """
    校验 dim_customer 暂存行。
    """
    if not rows:
        raise ValueError(
            "dim_customer 生成结果不能为空。"
        )

    _, profile = get_active_scale_profile(
        manifest
    )

    expected_count = profile["customers"]

    if len(rows) != expected_count:
        raise ValueError(
            "dim_customer 行数不正确："
            f"expected={expected_count}, "
            f"actual={len(rows)}"
        )

    required_fields = {
        "customer_code",
        "first_seen_date",
        "home_region_code",
        "customer_status",
    }

    config = manifest[
        "customer_generation"
    ]

    customer_code_prefix = config[
        "customer_code_prefix"
    ].strip()

    customer_code_width = config[
        "customer_code_width"
    ]

    customer_codes: set[str] = set()

    source_cohorts = config[
        "first_seen_cohorts"
    ]

    parsed_cohorts: list[
        dict[str, Any]
    ] = []

    for index, cohort in enumerate(
        source_cohorts
    ):
        parsed_cohorts.append(
            {
                "cohort_name": cohort[
                    "cohort_name"
                ].strip(),
                "start_date": (
                    parse_manifest_date(
                        cohort["start_date"],
                        (
                            "customer_generation."
                            f"first_seen_cohorts"
                            f"[{index}].start_date"
                        ),
                    )
                ),
                "end_date": (
                    parse_manifest_date(
                        cohort["end_date"],
                        (
                            "customer_generation."
                            f"first_seen_cohorts"
                            f"[{index}].end_date"
                        ),
                    )
                ),
            }
        )

    expected_cohort_counts = (
        allocate_weighted_counts(
            total_count=expected_count,
            weighted_items=[
                (
                    cohort[
                        "cohort_name"
                    ].strip(),
                    cohort["ratio"],
                )
                for cohort in source_cohorts
            ],
            allocation_name=(
                "customer first_seen cohort"
            ),
        )
    )

    actual_cohort_counts: Counter[str] = (
        Counter()
    )

    expected_status_counts = (
        allocate_weighted_counts(
            total_count=expected_count,
            weighted_items=[
                (status, probability)
                for status, probability
                in config[
                    "customer_status_distribution"
                ].items()
            ],
            allocation_name="customer status",
        )
    )

    actual_status_counts: Counter[str] = (
        Counter()
    )

    regions = manifest[
        "fixed_dimensions"
    ][
        "regions"
    ]

    region_lookup = {
        region["region_code"].strip(): {
            "city_tier": region[
                "city_tier"
            ].strip(),
        }
        for region in regions
    }

    expected_region_counts = (
        allocate_customer_home_region_counts(
            manifest
        )
    )

    actual_region_counts: Counter[str] = (
        Counter()
    )

    actual_city_tier_counts: Counter[str] = (
        Counter()
    )

    for index, row in enumerate(rows):
        if set(row.keys()) != required_fields:
            raise ValueError(
                f"dim_customer 第 {index} 行"
                "字段不正确："
                f"{sorted(row.keys())}"
            )

        expected_customer_code = (
            f"{customer_code_prefix}"
            f"{index + 1:0{customer_code_width}d}"
        )

        customer_code = row[
            "customer_code"
        ]

        if (
            not isinstance(customer_code, str)
            or not customer_code.strip()
        ):
            raise ValueError(
                f"dim_customer 第 {index} 行 "
                "customer_code 必须是非空字符串。"
            )

        if customer_code != expected_customer_code:
            raise ValueError(
                f"dim_customer 第 {index} 行"
                "客户编码不符合确定性序列："
                f"expected={expected_customer_code}, "
                f"actual={customer_code}"
            )

        if customer_code in customer_codes:
            raise ValueError(
                "dim_customer 存在重复 "
                f"customer_code：{customer_code}"
            )

        first_seen_date = row[
            "first_seen_date"
        ]

        if (
            not isinstance(first_seen_date, date)
            or isinstance(
                first_seen_date,
                datetime,
            )
        ):
            raise ValueError(
                f"dim_customer 第 {index} 行 "
                "first_seen_date 必须是 date。"
            )

        matched_cohorts = [
            cohort
            for cohort in parsed_cohorts
            if (
                cohort["start_date"]
                <= first_seen_date
                <= cohort["end_date"]
            )
        ]

        if len(matched_cohorts) != 1:
            raise ValueError(
                f"dim_customer 第 {index} 行 "
                "first_seen_date 无法唯一匹配批次："
                f"{first_seen_date}"
            )

        actual_cohort_counts[
            matched_cohorts[0][
                "cohort_name"
            ]
        ] += 1

        home_region_code = row[
            "home_region_code"
        ]

        if home_region_code not in region_lookup:
            raise ValueError(
                f"dim_customer 第 {index} 行 "
                "引用了不存在的 region_code："
                f"{home_region_code!r}"
            )

        actual_region_counts[
            home_region_code
        ] += 1

        city_tier = region_lookup[
            home_region_code
        ][
            "city_tier"
        ]

        actual_city_tier_counts[
            city_tier
        ] += 1

        customer_status = row[
            "customer_status"
        ]

        if (
            not isinstance(customer_status, str)
            or not customer_status.strip()
        ):
            raise ValueError(
                f"dim_customer 第 {index} 行 "
                "customer_status 必须是非空字符串。"
            )

        if (
            customer_status
            not in expected_status_counts
        ):
            raise ValueError(
                f"dim_customer 第 {index} 行 "
                "customer_status 未在 Manifest 配置："
                f"{customer_status!r}"
            )

        actual_status_counts[
            customer_status
        ] += 1

        customer_codes.add(
            customer_code
        )

    if (
        dict(actual_cohort_counts)
        != expected_cohort_counts
    ):
        raise ValueError(
            "dim_customer first_seen 批次数量"
            "不正确："
            f"expected={expected_cohort_counts}, "
            f"actual={dict(actual_cohort_counts)}"
        )

    if (
        dict(actual_status_counts)
        != expected_status_counts
    ):
        raise ValueError(
            "dim_customer 状态数量不正确："
            f"expected={expected_status_counts}, "
            f"actual={dict(actual_status_counts)}"
        )

    if (
        dict(actual_region_counts)
        != expected_region_counts
    ):
        raise ValueError(
            "dim_customer 地区数量分布不正确："
            f"expected={expected_region_counts}, "
            f"actual={dict(actual_region_counts)}"
        )

    expected_city_tier_counts = (
        allocate_weighted_counts(
            total_count=expected_count,
            weighted_items=[
                (
                    city_tier,
                    weight,
                )
                for city_tier, weight
                in config[
                    "home_region_distribution"
                ][
                    "city_tier_weights"
                ].items()
            ],
            allocation_name=(
                "customer home region city tier"
            ),
        )
    )

    if (
        dict(actual_city_tier_counts)
        != expected_city_tier_counts
    ):
        raise ValueError(
            "dim_customer 城市等级数量不正确："
            f"expected="
            f"{expected_city_tier_counts}, "
            f"actual="
            f"{dict(actual_city_tier_counts)}"
        )


def preview_dim_customer_rows(
    manifest: dict[str, Any],
) -> None:
    rows = build_dim_customer_rows(
        manifest
    )

    validate_dim_customer_rows(
        rows,
        manifest,
    )

    repeated_rows = build_dim_customer_rows(
        manifest
    )

    if rows != repeated_rows:
        raise ValueError(
            "dim_customer 重复生成结果不一致，"
            "确定性校验失败。"
        )

    status_counts = Counter(
        row["customer_status"]
        for row in rows
    )

    regions = manifest[
        "fixed_dimensions"
    ][
        "regions"
    ]

    region_tier_lookup = {
        region["region_code"].strip():
            region["city_tier"].strip()
        for region in regions
    }

    city_tier_counts = Counter(
        region_tier_lookup[
            row["home_region_code"]
        ]
        for row in rows
    )

    cohort_counts: Counter[str] = Counter()

    for row in rows:
        for cohort in manifest[
            "customer_generation"
        ][
            "first_seen_cohorts"
        ]:
            start_date = parse_manifest_date(
                cohort["start_date"],
                "customer cohort start_date",
            )

            end_date = parse_manifest_date(
                cohort["end_date"],
                "customer cohort end_date",
            )

            if (
                start_date
                <= row["first_seen_date"]
                <= end_date
            ):
                cohort_counts[
                    cohort["cohort_name"].strip()
                ] += 1

                break

    print("dim_customer row preview passed.")
    print(f"Total rows: {len(rows)}")
    print(
        "First-seen cohort counts: "
        f"{dict(cohort_counts)}"
    )
    print(
        "City-tier counts: "
        f"{dict(city_tier_counts)}"
    )
    print(
        "Customer status counts: "
        f"{dict(status_counts)}"
    )
    print(f"First row: {rows[0]}")
    print(f"Last row: {rows[-1]}")
    print("Deterministic check: passed.")


def insert_dim_customer_rows(
    rows: list[dict[str, Any]],
) -> None:
    """
    将 dim_customer 批量写入 PostgreSQL。

    生成阶段使用稳定业务键 home_region_code；
    写库阶段在同一事务中将其解析为 home_region_id。

    安全策略：
    1. 生成结果不能为空；
    2. dim_customer 必须为空；
    3. 所有 region_code 必须能唯一解析；
    4. 检查、插入和写后验证位于同一事务；
    5. 数据库结果与生成结果逐行比较；
    6. 任意异常自动回滚。
    """
    if not rows:
        raise ValueError(
            "不能插入空的 dim_customer 数据。"
        )

    insert_sql = text(
        """
        INSERT INTO beauty_bi_v2.dim_customer (
            customer_code,
            first_seen_date,
            home_region_id,
            customer_status
        )
        VALUES (
            :customer_code,
            :first_seen_date,
            :home_region_id,
            :customer_status
        )
        """
    )

    select_sql = text(
        """
        SELECT
            customer.customer_code,
            customer.first_seen_date,
            region.region_code AS home_region_code,
            customer.customer_status
        FROM beauty_bi_v2.dim_customer AS customer
        INNER JOIN beauty_bi_v2.dim_region AS region
            ON region.region_id =
                customer.home_region_id
        ORDER BY customer.customer_code
        """
    )

    with engine.begin() as connection:
        existing_count = connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM beauty_bi_v2.dim_customer
                """
            )
        ).scalar_one()

        if existing_count != 0:
            raise RuntimeError(
                "beauty_bi_v2.dim_customer 已存在数据，"
                "为避免重复写入，本次 Seed 已停止。"
                f" existing_count={existing_count}"
            )

        region_records = connection.execute(
            text(
                """
                SELECT
                    region_id,
                    region_code,
                    city_tier
                FROM beauty_bi_v2.dim_region
                ORDER BY region_code
                """
            )
        ).mappings().all()

        if not region_records:
            raise RuntimeError(
                "beauty_bi_v2.dim_region 为空，"
                "无法解析客户的 home_region_id。"
            )

        region_lookup = {
            record["region_code"]: {
                "region_id": record["region_id"],
                "city_tier": record["city_tier"],
            }
            for record in region_records
        }

        required_region_codes = {
            row["home_region_code"]
            for row in rows
        }

        missing_region_codes = (
            required_region_codes
            - region_lookup.keys()
        )

        if missing_region_codes:
            raise RuntimeError(
                "dim_customer 引用了数据库中"
                "不存在的 region_code："
                f"{sorted(missing_region_codes)}"
            )

        database_insert_rows: list[
            dict[str, Any]
        ] = []

        for row in rows:
            home_region_code = row[
                "home_region_code"
            ]

            database_insert_rows.append(
                {
                    "customer_code": row[
                        "customer_code"
                    ],
                    "first_seen_date": row[
                        "first_seen_date"
                    ],
                    "home_region_id": (
                        region_lookup[
                            home_region_code
                        ][
                            "region_id"
                        ]
                    ),
                    "customer_status": row[
                        "customer_status"
                    ],
                }
            )

        connection.execute(
            insert_sql,
            database_insert_rows,
        )

        (
            actual_count,
            distinct_code_count,
            distinct_region_count,
            min_first_seen_date,
            max_first_seen_date,
        ) = connection.execute(
            text(
                """
                SELECT
                    COUNT(*),
                    COUNT(DISTINCT customer_code),
                    COUNT(DISTINCT home_region_id),
                    MIN(first_seen_date),
                    MAX(first_seen_date)
                FROM beauty_bi_v2.dim_customer
                """
            )
        ).one()

        if actual_count != len(rows):
            raise RuntimeError(
                "dim_customer 插入后的行数不正确："
                f"expected={len(rows)}, "
                f"actual={actual_count}"
            )

        if distinct_code_count != actual_count:
            raise RuntimeError(
                "dim_customer 数据库中存在重复 "
                "customer_code。"
            )

        expected_region_count = len(
            required_region_codes
        )

        if (
            distinct_region_count
            != expected_region_count
        ):
            raise RuntimeError(
                "dim_customer 使用的地区数量不正确："
                f"expected={expected_region_count}, "
                f"actual={distinct_region_count}"
            )

        expected_min_first_seen_date = min(
            row["first_seen_date"]
            for row in rows
        )

        expected_max_first_seen_date = max(
            row["first_seen_date"]
            for row in rows
        )

        if (
            min_first_seen_date
            != expected_min_first_seen_date
            or max_first_seen_date
            != expected_max_first_seen_date
        ):
            raise RuntimeError(
                "dim_customer 首次出现日期范围不正确："
                "expected="
                f"{expected_min_first_seen_date} -> "
                f"{expected_max_first_seen_date}, "
                "actual="
                f"{min_first_seen_date} -> "
                f"{max_first_seen_date}"
            )

        actual_status_counts = Counter(
            {
                record["customer_status"]:
                    record["row_count"]
                for record in connection.execute(
                    text(
                        """
                        SELECT
                            customer_status,
                            COUNT(*) AS row_count
                        FROM beauty_bi_v2.dim_customer
                        GROUP BY customer_status
                        ORDER BY customer_status
                        """
                    )
                ).mappings().all()
            }
        )

        expected_status_counts = Counter(
            row["customer_status"]
            for row in rows
        )

        if (
            actual_status_counts
            != expected_status_counts
        ):
            raise RuntimeError(
                "dim_customer 状态数量不正确："
                f"expected={expected_status_counts}, "
                f"actual={actual_status_counts}"
            )

        actual_region_counts = Counter(
            {
                record["region_code"]:
                    record["row_count"]
                for record in connection.execute(
                    text(
                        """
                        SELECT
                            region.region_code,
                            COUNT(*) AS row_count
                        FROM beauty_bi_v2.dim_customer
                            AS customer
                        INNER JOIN
                            beauty_bi_v2.dim_region
                            AS region
                            ON region.region_id =
                                customer.home_region_id
                        GROUP BY region.region_code
                        ORDER BY region.region_code
                        """
                    )
                ).mappings().all()
            }
        )

        expected_region_counts = Counter(
            row["home_region_code"]
            for row in rows
        )

        if (
            actual_region_counts
            != expected_region_counts
        ):
            raise RuntimeError(
                "dim_customer 地区数量不正确："
                f"expected={expected_region_counts}, "
                f"actual={actual_region_counts}"
            )

        actual_city_tier_counts = Counter(
            {
                record["city_tier"]:
                    record["row_count"]
                for record in connection.execute(
                    text(
                        """
                        SELECT
                            region.city_tier,
                            COUNT(*) AS row_count
                        FROM beauty_bi_v2.dim_customer
                            AS customer
                        INNER JOIN
                            beauty_bi_v2.dim_region
                            AS region
                            ON region.region_id =
                                customer.home_region_id
                        GROUP BY region.city_tier
                        ORDER BY region.city_tier
                        """
                    )
                ).mappings().all()
            }
        )

        expected_city_tier_counts = Counter(
            region_lookup[
                row["home_region_code"]
            ][
                "city_tier"
            ]
            for row in rows
        )

        if (
            actual_city_tier_counts
            != expected_city_tier_counts
        ):
            raise RuntimeError(
                "dim_customer 城市等级数量不正确："
                "expected="
                f"{expected_city_tier_counts}, "
                f"actual={actual_city_tier_counts}"
            )

        database_rows = [
            dict(row)
            for row in connection.execute(
                select_sql
            ).mappings().all()
        ]

        expected_rows = sorted(
            rows,
            key=lambda row: row["customer_code"],
        )

        if database_rows != expected_rows:
            for expected_row, actual_row in zip(
                expected_rows,
                database_rows,
            ):
                if expected_row != actual_row:
                    raise RuntimeError(
                        "dim_customer 数据库写入结果"
                        "与生成结果不一致："
                        f"expected={expected_row}, "
                        f"actual={actual_row}"
                    )

            raise RuntimeError(
                "dim_customer 数据库写入结果"
                "与生成结果不一致。"
            )

    print("dim_customer database seed passed.")
    print(f"Inserted rows: {actual_count}")
    print(
        "Distinct regions: "
        f"{distinct_region_count}"
    )
    print(
        "First-seen date range: "
        f"{min_first_seen_date} -> "
        f"{max_first_seen_date}"
    )
    print(
        "Customer status counts: "
        f"{dict(actual_status_counts)}"
    )
    print(
        "City-tier counts: "
        f"{dict(actual_city_tier_counts)}"
    )
    print("Region foreign-key resolution: passed.")
    print("Database row comparison: passed.")


def seed_dim_customer(
    manifest: dict[str, Any],
) -> None:
    rows = build_dim_customer_rows(
        manifest
    )

    validate_dim_customer_rows(
        rows,
        manifest,
    )

    repeated_rows = build_dim_customer_rows(
        manifest
    )

    if rows != repeated_rows:
        raise ValueError(
            "dim_customer 重复生成结果不一致，"
            "确定性校验失败。"
        )

    status_counts = Counter(
        row["customer_status"]
        for row in rows
    )

    regions = manifest[
        "fixed_dimensions"
    ][
        "regions"
    ]

    region_tier_lookup = {
        region["region_code"].strip():
            region["city_tier"].strip()
        for region in regions
    }

    city_tier_counts = Counter(
        region_tier_lookup[
            row["home_region_code"]
        ]
        for row in rows
    )

    print("dim_customer generation passed.")
    print(f"Total rows: {len(rows)}")
    print(
        "Customer status counts: "
        f"{dict(status_counts)}"
    )
    print(
        "City-tier counts: "
        f"{dict(city_tier_counts)}"
    )
    print(f"First row: {rows[0]}")
    print(f"Last row: {rows[-1]}")
    print("Deterministic check: passed.")

    insert_dim_customer_rows(rows)


def build_dim_membership_account_rows(
    manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    确定性生成 dim_membership_account 暂存行。

    生成阶段使用稳定业务键 join_channel_code。
    正式写库时再转换成 join_channel_id。
    """
    _, profile = get_active_scale_profile(
        manifest
    )

    total_membership_count = profile[
        "membership_accounts"
    ]

    config = manifest[
        "membership_generation"
    ]

    random_seed = manifest[
        "generation"
    ][
        "random_seed"
    ]

    rng = random.Random(random_seed)

    joined_at_cohorts = config[
        "joined_at_cohorts"
    ]

    cohort_counts = allocate_weighted_counts(
        total_count=total_membership_count,
        weighted_items=[
            (
                cohort["cohort_name"].strip(),
                cohort["ratio"],
            )
            for cohort in joined_at_cohorts
        ],
        allocation_name=(
            "membership joined_at cohort"
        ),
    )

    cohort_pool: list[
        dict[str, Any]
    ] = []

    for index, cohort in enumerate(
        joined_at_cohorts
    ):
        cohort_name = cohort[
            "cohort_name"
        ].strip()

        start_date = parse_manifest_date(
            cohort["start_date"],
            (
                "membership_generation."
                f"joined_at_cohorts[{index}]."
                "start_date"
            ),
        )

        end_date = parse_manifest_date(
            cohort["end_date"],
            (
                "membership_generation."
                f"joined_at_cohorts[{index}]."
                "end_date"
            ),
        )

        cohort_pool.extend(
            [
                {
                    "cohort_name": cohort_name,
                    "start_date": start_date,
                    "end_date": end_date,
                }
            ]
            * cohort_counts[cohort_name]
        )

    if (
        len(cohort_pool)
        != total_membership_count
    ):
        raise ValueError(
            "会员 joined_at 批次池数量不正确："
            f"expected={total_membership_count}, "
            f"actual={len(cohort_pool)}"
        )

    rng.shuffle(cohort_pool)

    join_channel_weights = config[
        "join_channel_weights"
    ]

    join_channel_counts = (
        allocate_weighted_counts(
            total_count=total_membership_count,
            weighted_items=[
                (
                    channel_code.strip(),
                    weight,
                )
                for channel_code, weight
                in join_channel_weights.items()
            ],
            allocation_name=(
                "membership join channel"
            ),
        )
    )

    join_channel_pool: list[str] = []

    for channel_code, count in (
        join_channel_counts.items()
    ):
        join_channel_pool.extend(
            [channel_code] * count
        )

    if (
        len(join_channel_pool)
        != total_membership_count
    ):
        raise ValueError(
            "会员首次入会渠道池数量不正确："
            f"expected={total_membership_count}, "
            f"actual={len(join_channel_pool)}"
        )

    rng.shuffle(join_channel_pool)

    membership_status_distribution = (
        manifest[
            "business_patterns"
        ][
            "P03_membership_customer_overlap"
        ][
            "parameters"
        ][
            "membership_status_distribution"
        ]
    )

    membership_status_counts = (
        allocate_weighted_counts(
            total_count=total_membership_count,
            weighted_items=[
                (
                    membership_status.strip(),
                    probability,
                )
                for membership_status, probability
                in membership_status_distribution.items()
            ],
            allocation_name=(
                "membership account status"
            ),
        )
    )

    membership_status_pool: list[str] = []

    for membership_status, count in (
        membership_status_counts.items()
    ):
        membership_status_pool.extend(
            [membership_status] * count
        )

    if (
        len(membership_status_pool)
        != total_membership_count
    ):
        raise ValueError(
            "会员账户状态池数量不正确："
            f"expected={total_membership_count}, "
            f"actual={len(membership_status_pool)}"
        )

    rng.shuffle(membership_status_pool)

    joined_time_window = config[
        "joined_time_window"
    ]

    joined_start_time = parse_manifest_time(
        joined_time_window["start_time"],
        (
            "membership_generation."
            "joined_time_window.start_time"
        ),
    )

    joined_end_time = parse_manifest_time(
        joined_time_window["end_time"],
        (
            "membership_generation."
            "joined_time_window.end_time"
        ),
    )

    start_second_of_day = (
        joined_start_time.hour * 3600
        + joined_start_time.minute * 60
        + joined_start_time.second
    )

    end_second_of_day = (
        joined_end_time.hour * 3600
        + joined_end_time.minute * 60
        + joined_end_time.second
    )

    member_code_prefix = config[
        "member_code_prefix"
    ].strip()

    member_code_width = config[
        "member_code_width"
    ]

    rows: list[dict[str, Any]] = []

    for member_number in range(
        1,
        total_membership_count + 1,
    ):
        cohort = cohort_pool[
            member_number - 1
        ]

        cohort_day_count = (
            cohort["end_date"]
            - cohort["start_date"]
        ).days

        joined_date = (
            cohort["start_date"]
            + timedelta(
                days=rng.randint(
                    0,
                    cohort_day_count,
                )
            )
        )

        joined_second_of_day = rng.randint(
            start_second_of_day,
            end_second_of_day,
        )

        joined_at = (
            datetime.combine(
                joined_date,
                datetime.min.time(),
            )
            + timedelta(
                seconds=joined_second_of_day
            )
        )

        member_code = (
            f"{member_code_prefix}"
            f"{member_number:0{member_code_width}d}"
        )

        rows.append(
            {
                "member_code": member_code,
                "joined_at": joined_at,
                "join_channel_code": (
                    join_channel_pool[
                        member_number - 1
                    ]
                ),
                "membership_status": (
                    membership_status_pool[
                        member_number - 1
                    ]
                ),
            }
        )

    return rows


def validate_dim_membership_account_rows(
    rows: list[dict[str, Any]],
    manifest: dict[str, Any],
) -> None:
    """
    校验 dim_membership_account 暂存行。
    """
    if not rows:
        raise ValueError(
            "dim_membership_account "
            "生成结果不能为空。"
        )

    _, profile = get_active_scale_profile(
        manifest
    )

    expected_count = profile[
        "membership_accounts"
    ]

    if len(rows) != expected_count:
        raise ValueError(
            "dim_membership_account "
            "行数不正确："
            f"expected={expected_count}, "
            f"actual={len(rows)}"
        )

    required_fields = {
        "member_code",
        "joined_at",
        "join_channel_code",
        "membership_status",
    }

    config = manifest[
        "membership_generation"
    ]

    member_code_prefix = config[
        "member_code_prefix"
    ].strip()

    member_code_width = config[
        "member_code_width"
    ]

    member_codes: set[str] = set()

    joined_at_cohorts = config[
        "joined_at_cohorts"
    ]

    parsed_cohorts: list[
        dict[str, Any]
    ] = []

    for index, cohort in enumerate(
        joined_at_cohorts
    ):
        parsed_cohorts.append(
            {
                "cohort_name": cohort[
                    "cohort_name"
                ].strip(),
                "start_date": parse_manifest_date(
                    cohort["start_date"],
                    (
                        "membership_generation."
                        f"joined_at_cohorts[{index}]."
                        "start_date"
                    ),
                ),
                "end_date": parse_manifest_date(
                    cohort["end_date"],
                    (
                        "membership_generation."
                        f"joined_at_cohorts[{index}]."
                        "end_date"
                    ),
                ),
            }
        )

    expected_cohort_counts = (
        allocate_weighted_counts(
            total_count=expected_count,
            weighted_items=[
                (
                    cohort[
                        "cohort_name"
                    ].strip(),
                    cohort["ratio"],
                )
                for cohort in joined_at_cohorts
            ],
            allocation_name=(
                "membership joined_at cohort"
            ),
        )
    )

    actual_cohort_counts: Counter[str] = (
        Counter()
    )

    expected_channel_counts = (
        allocate_weighted_counts(
            total_count=expected_count,
            weighted_items=[
                (
                    channel_code.strip(),
                    weight,
                )
                for channel_code, weight
                in config[
                    "join_channel_weights"
                ].items()
            ],
            allocation_name=(
                "membership join channel"
            ),
        )
    )

    actual_channel_counts: Counter[str] = (
        Counter()
    )

    membership_status_distribution = (
        manifest[
            "business_patterns"
        ][
            "P03_membership_customer_overlap"
        ][
            "parameters"
        ][
            "membership_status_distribution"
        ]
    )

    expected_status_counts = (
        allocate_weighted_counts(
            total_count=expected_count,
            weighted_items=[
                (
                    membership_status.strip(),
                    probability,
                )
                for membership_status, probability
                in membership_status_distribution.items()
            ],
            allocation_name=(
                "membership account status"
            ),
        )
    )

    actual_status_counts: Counter[str] = (
        Counter()
    )

    valid_channel_codes = {
        channel["channel_code"].strip()
        for channel in manifest[
            "fixed_dimensions"
        ][
            "channels"
        ]
        if (
            channel["is_active"]
            and channel[
                "supports_membership_binding"
            ]
        )
    }

    joined_time_window = config[
        "joined_time_window"
    ]

    joined_start_time = parse_manifest_time(
        joined_time_window["start_time"],
        (
            "membership_generation."
            "joined_time_window.start_time"
        ),
    )

    joined_end_time = parse_manifest_time(
        joined_time_window["end_time"],
        (
            "membership_generation."
            "joined_time_window.end_time"
        ),
    )

    for index, row in enumerate(rows):
        if set(row.keys()) != required_fields:
            raise ValueError(
                "dim_membership_account "
                f"第 {index} 行字段不正确："
                f"{sorted(row.keys())}"
            )

        expected_member_code = (
            f"{member_code_prefix}"
            f"{index + 1:0{member_code_width}d}"
        )

        member_code = row[
            "member_code"
        ]

        if (
            not isinstance(member_code, str)
            or not member_code.strip()
        ):
            raise ValueError(
                "dim_membership_account "
                f"第 {index} 行 member_code "
                "必须是非空字符串。"
            )

        if member_code != expected_member_code:
            raise ValueError(
                "dim_membership_account "
                f"第 {index} 行会员编码"
                "不符合确定性序列："
                f"expected={expected_member_code}, "
                f"actual={member_code}"
            )

        if member_code in member_codes:
            raise ValueError(
                "dim_membership_account "
                "存在重复 member_code："
                f"{member_code}"
            )

        joined_at = row[
            "joined_at"
        ]

        if not isinstance(
            joined_at,
            datetime,
        ):
            raise ValueError(
                "dim_membership_account "
                f"第 {index} 行 joined_at "
                "必须是 datetime。"
            )

        if joined_at.tzinfo is not None:
            raise ValueError(
                "dim_membership_account "
                f"第 {index} 行 joined_at "
                "不能包含时区信息。"
            )

        joined_time = joined_at.time()

        if not (
            joined_start_time
            <= joined_time
            <= joined_end_time
        ):
            raise ValueError(
                "dim_membership_account "
                f"第 {index} 行 joined_at "
                "超出日内时间窗口："
                f"{joined_at}"
            )

        matched_cohorts = [
            cohort
            for cohort in parsed_cohorts
            if (
                cohort["start_date"]
                <= joined_at.date()
                <= cohort["end_date"]
            )
        ]

        if len(matched_cohorts) != 1:
            raise ValueError(
                "dim_membership_account "
                f"第 {index} 行 joined_at "
                "无法唯一匹配入会批次："
                f"{joined_at}"
            )

        actual_cohort_counts[
            matched_cohorts[0][
                "cohort_name"
            ]
        ] += 1

        join_channel_code = row[
            "join_channel_code"
        ]

        if (
            not isinstance(
                join_channel_code,
                str,
            )
            or not join_channel_code.strip()
        ):
            raise ValueError(
                "dim_membership_account "
                f"第 {index} 行 "
                "join_channel_code "
                "必须是非空字符串。"
            )

        if (
            join_channel_code
            not in valid_channel_codes
        ):
            raise ValueError(
                "dim_membership_account "
                f"第 {index} 行引用了"
                "无效的首次入会渠道："
                f"{join_channel_code!r}"
            )

        if (
            join_channel_code
            not in expected_channel_counts
        ):
            raise ValueError(
                "dim_membership_account "
                f"第 {index} 行首次入会渠道"
                "未配置权重："
                f"{join_channel_code!r}"
            )

        actual_channel_counts[
            join_channel_code
        ] += 1

        membership_status = row[
            "membership_status"
        ]

        if (
            not isinstance(
                membership_status,
                str,
            )
            or not membership_status.strip()
        ):
            raise ValueError(
                "dim_membership_account "
                f"第 {index} 行 "
                "membership_status "
                "必须是非空字符串。"
            )

        if (
            membership_status
            not in expected_status_counts
        ):
            raise ValueError(
                "dim_membership_account "
                f"第 {index} 行会员状态"
                "未在 P03 中配置："
                f"{membership_status!r}"
            )

        actual_status_counts[
            membership_status
        ] += 1

        member_codes.add(
            member_code
        )

    if (
        dict(actual_cohort_counts)
        != expected_cohort_counts
    ):
        raise ValueError(
            "dim_membership_account "
            "入会批次数量不正确："
            f"expected={expected_cohort_counts}, "
            f"actual={dict(actual_cohort_counts)}"
        )

    if (
        dict(actual_channel_counts)
        != expected_channel_counts
    ):
        raise ValueError(
            "dim_membership_account "
            "首次入会渠道数量不正确："
            f"expected={expected_channel_counts}, "
            f"actual={dict(actual_channel_counts)}"
        )

    if (
        dict(actual_status_counts)
        != expected_status_counts
    ):
        raise ValueError(
            "dim_membership_account "
            "会员状态数量不正确："
            f"expected={expected_status_counts}, "
            f"actual={dict(actual_status_counts)}"
        )


def preview_dim_membership_account_rows(
    manifest: dict[str, Any],
) -> None:
    rows = build_dim_membership_account_rows(
        manifest
    )

    validate_dim_membership_account_rows(
        rows,
        manifest,
    )

    repeated_rows = (
        build_dim_membership_account_rows(
            manifest
        )
    )

    if rows != repeated_rows:
        raise ValueError(
            "dim_membership_account "
            "重复生成结果不一致，"
            "确定性校验失败。"
        )

    config = manifest[
        "membership_generation"
    ]

    cohort_counts: Counter[str] = Counter()

    for row in rows:
        joined_date = row[
            "joined_at"
        ].date()

        for index, cohort in enumerate(
            config["joined_at_cohorts"]
        ):
            start_date = parse_manifest_date(
                cohort["start_date"],
                (
                    "membership_generation."
                    f"joined_at_cohorts[{index}]."
                    "start_date"
                ),
            )

            end_date = parse_manifest_date(
                cohort["end_date"],
                (
                    "membership_generation."
                    f"joined_at_cohorts[{index}]."
                    "end_date"
                ),
            )

            if (
                start_date
                <= joined_date
                <= end_date
            ):
                cohort_counts[
                    cohort[
                        "cohort_name"
                    ].strip()
                ] += 1

                break

    ordered_cohort_counts = {
        cohort["cohort_name"].strip():
            cohort_counts[
                cohort[
                    "cohort_name"
                ].strip()
            ]
        for cohort in config[
            "joined_at_cohorts"
        ]
    }

    actual_channel_counts = Counter(
        row["join_channel_code"]
        for row in rows
    )

    ordered_channel_counts = {
        channel_code.strip():
            actual_channel_counts[
                channel_code.strip()
            ]
        for channel_code in config[
            "join_channel_weights"
        ].keys()
    }

    actual_status_counts = Counter(
        row["membership_status"]
        for row in rows
    )

    status_distribution = manifest[
        "business_patterns"
    ][
        "P03_membership_customer_overlap"
    ][
        "parameters"
    ][
        "membership_status_distribution"
    ]

    ordered_status_counts = {
        membership_status.strip():
            actual_status_counts[
                membership_status.strip()
            ]
        for membership_status
        in status_distribution.keys()
    }

    joined_at_values = [
        row["joined_at"]
        for row in rows
    ]

    print(
        "dim_membership_account "
        "row preview passed."
    )
    print(f"Total rows: {len(rows)}")
    print(
        "Joined-at cohort counts: "
        f"{ordered_cohort_counts}"
    )
    print(
        "Join-channel counts: "
        f"{ordered_channel_counts}"
    )
    print(
        "Membership status counts: "
        f"{ordered_status_counts}"
    )
    print(
        "Joined-at range: "
        f"{min(joined_at_values)} -> "
        f"{max(joined_at_values)}"
    )
    print(f"First row: {rows[0]}")
    print(f"Last row: {rows[-1]}")
    print("Deterministic check: passed.")


def insert_dim_membership_account_rows(
    rows: list[dict[str, Any]],
) -> None:
    """
    将 dim_membership_account 批量写入 PostgreSQL。

    生成阶段使用稳定业务键 join_channel_code；
    写库阶段在同一事务中将其解析为 join_channel_id。

    安全策略：
    1. 生成结果不能为空；
    2. 目标表必须为空；
    3. 所有 join_channel_code 必须能唯一解析；
    4. 首次入会渠道必须处于启用状态；
    5. 检查、插入和写后验证位于同一事务；
    6. 数据库结果与生成结果逐行比较；
    7. 任意异常自动回滚。
    """
    if not rows:
        raise ValueError(
            "不能插入空的 "
            "dim_membership_account 数据。"
        )

    insert_sql = text(
        """
        INSERT INTO
            beauty_bi_v2.dim_membership_account (
                member_code,
                joined_at,
                join_channel_id,
                membership_status
            )
        VALUES (
            :member_code,
            :joined_at,
            :join_channel_id,
            :membership_status
        )
        """
    )

    select_sql = text(
        """
        SELECT
            account.member_code,
            account.joined_at,
            channel.channel_code
                AS join_channel_code,
            account.membership_status
        FROM
            beauty_bi_v2.dim_membership_account
                AS account
        INNER JOIN
            beauty_bi_v2.dim_channel
                AS channel
            ON channel.channel_id =
                account.join_channel_id
        ORDER BY
            account.member_code
        """
    )

    with engine.begin() as connection:
        existing_count = connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM
                    beauty_bi_v2.
                    dim_membership_account
                """
            )
        ).scalar_one()

        if existing_count != 0:
            raise RuntimeError(
                "beauty_bi_v2."
                "dim_membership_account "
                "已存在数据，为避免重复写入，"
                "本次 Seed 已停止。"
                f" existing_count={existing_count}"
            )

        channel_records = connection.execute(
            text(
                """
                SELECT
                    channel_id,
                    channel_code,
                    is_active
                FROM beauty_bi_v2.dim_channel
                ORDER BY channel_code
                """
            )
        ).mappings().all()

        if not channel_records:
            raise RuntimeError(
                "beauty_bi_v2.dim_channel 为空，"
                "无法解析 join_channel_id。"
            )

        channel_lookup = {
            record["channel_code"]: {
                "channel_id": record[
                    "channel_id"
                ],
                "is_active": record[
                    "is_active"
                ],
            }
            for record in channel_records
        }

        required_channel_codes = {
            row["join_channel_code"]
            for row in rows
        }

        missing_channel_codes = (
            required_channel_codes
            - channel_lookup.keys()
        )

        if missing_channel_codes:
            raise RuntimeError(
                "dim_membership_account "
                "引用了数据库中不存在的渠道："
                f"{sorted(missing_channel_codes)}"
            )

        inactive_channel_codes = {
            channel_code
            for channel_code
            in required_channel_codes
            if not channel_lookup[
                channel_code
            ][
                "is_active"
            ]
        }

        if inactive_channel_codes:
            raise RuntimeError(
                "dim_membership_account "
                "不能使用已停用的首次入会渠道："
                f"{sorted(inactive_channel_codes)}"
            )

        database_insert_rows: list[
            dict[str, Any]
        ] = []

        for row in rows:
            join_channel_code = row[
                "join_channel_code"
            ]

            database_insert_rows.append(
                {
                    "member_code": row[
                        "member_code"
                    ],
                    "joined_at": row[
                        "joined_at"
                    ],
                    "join_channel_id": (
                        channel_lookup[
                            join_channel_code
                        ][
                            "channel_id"
                        ]
                    ),
                    "membership_status": row[
                        "membership_status"
                    ],
                }
            )

        connection.execute(
            insert_sql,
            database_insert_rows,
        )

        (
            actual_count,
            distinct_member_code_count,
            distinct_join_channel_count,
            min_joined_at,
            max_joined_at,
        ) = connection.execute(
            text(
                """
                SELECT
                    COUNT(*),
                    COUNT(
                        DISTINCT member_code
                    ),
                    COUNT(
                        DISTINCT join_channel_id
                    ),
                    MIN(joined_at),
                    MAX(joined_at)
                FROM
                    beauty_bi_v2.
                    dim_membership_account
                """
            )
        ).one()

        if actual_count != len(rows):
            raise RuntimeError(
                "dim_membership_account "
                "插入后的行数不正确："
                f"expected={len(rows)}, "
                f"actual={actual_count}"
            )

        if (
            distinct_member_code_count
            != actual_count
        ):
            raise RuntimeError(
                "dim_membership_account "
                "数据库中存在重复 member_code。"
            )

        expected_join_channel_count = len(
            required_channel_codes
        )

        if (
            distinct_join_channel_count
            != expected_join_channel_count
        ):
            raise RuntimeError(
                "dim_membership_account "
                "首次入会渠道数量不正确："
                "expected="
                f"{expected_join_channel_count}, "
                "actual="
                f"{distinct_join_channel_count}"
            )

        expected_min_joined_at = min(
            row["joined_at"]
            for row in rows
        )

        expected_max_joined_at = max(
            row["joined_at"]
            for row in rows
        )

        if (
            min_joined_at
            != expected_min_joined_at
            or max_joined_at
            != expected_max_joined_at
        ):
            raise RuntimeError(
                "dim_membership_account "
                "入会时间范围不正确："
                "expected="
                f"{expected_min_joined_at} -> "
                f"{expected_max_joined_at}, "
                "actual="
                f"{min_joined_at} -> "
                f"{max_joined_at}"
            )

        actual_channel_counts = Counter(
            {
                record["channel_code"]:
                    record["row_count"]
                for record in connection.execute(
                    text(
                        """
                        SELECT
                            channel.channel_code,
                            COUNT(*) AS row_count
                        FROM
                            beauty_bi_v2.
                            dim_membership_account
                                AS account
                        INNER JOIN
                            beauty_bi_v2.dim_channel
                                AS channel
                            ON channel.channel_id =
                                account.join_channel_id
                        GROUP BY
                            channel.channel_code
                        ORDER BY
                            channel.channel_code
                        """
                    )
                ).mappings().all()
            }
        )

        expected_channel_counts = Counter(
            row["join_channel_code"]
            for row in rows
        )

        if (
            actual_channel_counts
            != expected_channel_counts
        ):
            raise RuntimeError(
                "dim_membership_account "
                "首次入会渠道分布不正确："
                f"expected={expected_channel_counts}, "
                f"actual={actual_channel_counts}"
            )

        actual_status_counts = Counter(
            {
                record["membership_status"]:
                    record["row_count"]
                for record in connection.execute(
                    text(
                        """
                        SELECT
                            membership_status,
                            COUNT(*) AS row_count
                        FROM
                            beauty_bi_v2.
                            dim_membership_account
                        GROUP BY
                            membership_status
                        ORDER BY
                            membership_status
                        """
                    )
                ).mappings().all()
            }
        )

        expected_status_counts = Counter(
            row["membership_status"]
            for row in rows
        )

        if (
            actual_status_counts
            != expected_status_counts
        ):
            raise RuntimeError(
                "dim_membership_account "
                "会员状态分布不正确："
                f"expected={expected_status_counts}, "
                f"actual={actual_status_counts}"
            )

        invalid_joined_at_count = (
            connection.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM
                        beauty_bi_v2.
                        dim_membership_account
                    WHERE
                        joined_at::time
                            < TIME '08:00:00'
                        OR joined_at::time
                            > TIME '22:59:59'
                    """
                )
            ).scalar_one()
        )

        if invalid_joined_at_count != 0:
            raise RuntimeError(
                "dim_membership_account "
                "数据库中存在超出日内窗口的 "
                "joined_at："
                f"invalid_count="
                f"{invalid_joined_at_count}"
            )

        database_rows = [
            dict(row)
            for row in connection.execute(
                select_sql
            ).mappings().all()
        ]

        expected_rows = sorted(
            rows,
            key=lambda row: row["member_code"],
        )

        if database_rows != expected_rows:
            for expected_row, actual_row in zip(
                expected_rows,
                database_rows,
            ):
                if expected_row != actual_row:
                    raise RuntimeError(
                        "dim_membership_account "
                        "数据库写入结果"
                        "与生成结果不一致："
                        f"expected={expected_row}, "
                        f"actual={actual_row}"
                    )

            raise RuntimeError(
                "dim_membership_account "
                "数据库写入结果"
                "与生成结果不一致。"
            )

    print(
        "dim_membership_account "
        "database seed passed."
    )
    print(f"Inserted rows: {actual_count}")
    print(
        "Distinct join channels: "
        f"{distinct_join_channel_count}"
    )
    print(
        "Joined-at range: "
        f"{min_joined_at} -> "
        f"{max_joined_at}"
    )
    print(
        "Join-channel counts: "
        f"{dict(actual_channel_counts)}"
    )
    print(
        "Membership status counts: "
        f"{dict(actual_status_counts)}"
    )
    print(
        "Joined-at time-window check: passed."
    )
    print(
        "Channel foreign-key resolution: passed."
    )
    print("Database row comparison: passed.")


def seed_dim_membership_account(
    manifest: dict[str, Any],
) -> None:
    rows = build_dim_membership_account_rows(
        manifest
    )

    validate_dim_membership_account_rows(
        rows,
        manifest,
    )

    repeated_rows = (
        build_dim_membership_account_rows(
            manifest
        )
    )

    if rows != repeated_rows:
        raise ValueError(
            "dim_membership_account "
            "重复生成结果不一致，"
            "确定性校验失败。"
        )

    config = manifest[
        "membership_generation"
    ]

    cohort_counts: Counter[str] = Counter()

    for row in rows:
        joined_date = row[
            "joined_at"
        ].date()

        for index, cohort in enumerate(
            config["joined_at_cohorts"]
        ):
            start_date = parse_manifest_date(
                cohort["start_date"],
                (
                    "membership_generation."
                    f"joined_at_cohorts[{index}]."
                    "start_date"
                ),
            )

            end_date = parse_manifest_date(
                cohort["end_date"],
                (
                    "membership_generation."
                    f"joined_at_cohorts[{index}]."
                    "end_date"
                ),
            )

            if (
                start_date
                <= joined_date
                <= end_date
            ):
                cohort_counts[
                    cohort[
                        "cohort_name"
                    ].strip()
                ] += 1
                break

    ordered_cohort_counts = {
        cohort["cohort_name"].strip():
            cohort_counts[
                cohort[
                    "cohort_name"
                ].strip()
            ]
        for cohort in config[
            "joined_at_cohorts"
        ]
    }

    actual_channel_counts = Counter(
        row["join_channel_code"]
        for row in rows
    )

    ordered_channel_counts = {
        channel_code.strip():
            actual_channel_counts[
                channel_code.strip()
            ]
        for channel_code in config[
            "join_channel_weights"
        ].keys()
    }

    actual_status_counts = Counter(
        row["membership_status"]
        for row in rows
    )

    status_distribution = manifest[
        "business_patterns"
    ][
        "P03_membership_customer_overlap"
    ][
        "parameters"
    ][
        "membership_status_distribution"
    ]

    ordered_status_counts = {
        membership_status.strip():
            actual_status_counts[
                membership_status.strip()
            ]
        for membership_status
        in status_distribution.keys()
    }

    print(
        "dim_membership_account "
        "generation passed."
    )
    print(f"Total rows: {len(rows)}")
    print(
        "Joined-at cohort counts: "
        f"{ordered_cohort_counts}"
    )
    print(
        "Join-channel counts: "
        f"{ordered_channel_counts}"
    )
    print(
        "Membership status counts: "
        f"{ordered_status_counts}"
    )
    print(f"First row: {rows[0]}")
    print(f"Last row: {rows[-1]}")
    print("Deterministic check: passed.")

    insert_dim_membership_account_rows(
        rows
    )


def build_bridge_customer_membership_rows(
    manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    确定性生成 customer-membership 映射暂存行。

    生成阶段使用稳定业务键：
    - customer_code
    - member_code

    正式写库时再解析为：
    - customer_id
    - membership_account_id
    """
    _, profile = get_active_scale_profile(
        manifest
    )

    parameters = manifest[
        "business_patterns"
    ][
        "P03_membership_customer_overlap"
    ][
        "parameters"
    ]

    mapped_customer_ratio = parameters[
        "mapped_customer_ratio"
    ]

    mapped_count = round(
        profile["customers"]
        * mapped_customer_ratio
    )

    customer_rows = build_dim_customer_rows(
        manifest
    )

    membership_rows = (
        build_dim_membership_account_rows(
            manifest
        )
    )

    if mapped_count > len(customer_rows):
        raise ValueError(
            "身份映射数量超过客户生成结果："
            f"mapped_count={mapped_count}, "
            f"customer_count={len(customer_rows)}"
        )

    if mapped_count > len(membership_rows):
        raise ValueError(
            "身份映射数量超过会员账户生成结果："
            f"mapped_count={mapped_count}, "
            "membership_account_count="
            f"{len(membership_rows)}"
        )

    customer_candidates = [
        {
            "customer_code": row[
                "customer_code"
            ],
            "first_seen_date": row[
                "first_seen_date"
            ],
        }
        for row in customer_rows
    ]

    membership_candidates = [
        {
            "member_code": row[
                "member_code"
            ],
            "joined_at": row[
                "joined_at"
            ],
        }
        for row in membership_rows
    ]

    random_seed = manifest[
        "generation"
    ][
        "random_seed"
    ]

    rng = random.Random(random_seed)

    # 使用同一个局部随机实例按顺序洗牌。
    # 这样两侧均可复现，但不会形成按编号直接对应。
    rng.shuffle(customer_candidates)
    rng.shuffle(membership_candidates)

    selected_customers = customer_candidates[
        :mapped_count
    ]

    selected_memberships = (
        membership_candidates[
            :mapped_count
        ]
    )

    config = manifest[
        "identity_mapping_generation"
    ]

    mapping_status = config[
        "mapping_status"
    ].strip()

    rows: list[dict[str, Any]] = []

    for customer, membership in zip(
        selected_customers,
        selected_memberships,
        strict=True,
    ):
        customer_first_seen_ts = (
            datetime.combine(
                customer["first_seen_date"],
                datetime.min.time(),
            )
        )

        effective_from_ts = max(
            customer_first_seen_ts,
            membership["joined_at"],
        )

        rows.append(
            {
                "customer_code": customer[
                    "customer_code"
                ],
                "member_code": membership[
                    "member_code"
                ],
                "effective_from_ts": (
                    effective_from_ts
                ),
                "effective_to_ts": None,
                "mapping_status": mapping_status,
            }
        )

    return rows


def validate_bridge_customer_membership_rows(
    rows: list[dict[str, Any]],
    manifest: dict[str, Any],
) -> None:
    """
    校验 customer-membership 映射暂存行。
    """
    if not rows:
        raise ValueError(
            "bridge_customer_membership "
            "生成结果不能为空。"
        )

    _, profile = get_active_scale_profile(
        manifest
    )

    parameters = manifest[
        "business_patterns"
    ][
        "P03_membership_customer_overlap"
    ][
        "parameters"
    ]

    expected_count = round(
        profile["customers"]
        * parameters["mapped_customer_ratio"]
    )

    if len(rows) != expected_count:
        raise ValueError(
            "bridge_customer_membership "
            "行数不正确："
            f"expected={expected_count}, "
            f"actual={len(rows)}"
        )

    required_fields = {
        "customer_code",
        "member_code",
        "effective_from_ts",
        "effective_to_ts",
        "mapping_status",
    }

    customer_rows = build_dim_customer_rows(
        manifest
    )

    membership_rows = (
        build_dim_membership_account_rows(
            manifest
        )
    )

    customer_lookup = {
        row["customer_code"]: row
        for row in customer_rows
    }

    membership_lookup = {
        row["member_code"]: row
        for row in membership_rows
    }

    expected_mapping_status = manifest[
        "identity_mapping_generation"
    ][
        "mapping_status"
    ].strip()

    customer_codes: set[str] = set()
    member_codes: set[str] = set()
    mapping_pairs: set[
        tuple[str, str]
    ] = set()

    for index, row in enumerate(rows):
        if set(row.keys()) != required_fields:
            raise ValueError(
                "bridge_customer_membership "
                f"第 {index} 行字段不正确："
                f"{sorted(row.keys())}"
            )

        customer_code = row[
            "customer_code"
        ]

        member_code = row[
            "member_code"
        ]

        if (
            not isinstance(customer_code, str)
            or not customer_code.strip()
        ):
            raise ValueError(
                "bridge_customer_membership "
                f"第 {index} 行 customer_code "
                "必须是非空字符串。"
            )

        if (
            not isinstance(member_code, str)
            or not member_code.strip()
        ):
            raise ValueError(
                "bridge_customer_membership "
                f"第 {index} 行 member_code "
                "必须是非空字符串。"
            )

        if customer_code not in customer_lookup:
            raise ValueError(
                "bridge_customer_membership "
                f"第 {index} 行引用了"
                "不存在的 customer_code："
                f"{customer_code!r}"
            )

        if member_code not in membership_lookup:
            raise ValueError(
                "bridge_customer_membership "
                f"第 {index} 行引用了"
                "不存在的 member_code："
                f"{member_code!r}"
            )

        if customer_code in customer_codes:
            raise ValueError(
                "开放身份映射中一个客户"
                "不能对应多个会员账户："
                f"{customer_code}"
            )

        if member_code in member_codes:
            raise ValueError(
                "开放身份映射中一个会员账户"
                "不能对应多个客户："
                f"{member_code}"
            )

        pair = (
            customer_code,
            member_code,
        )

        if pair in mapping_pairs:
            raise ValueError(
                "bridge_customer_membership "
                "存在重复映射对："
                f"{pair}"
            )

        effective_from_ts = row[
            "effective_from_ts"
        ]

        if not isinstance(
            effective_from_ts,
            datetime,
        ):
            raise ValueError(
                "bridge_customer_membership "
                f"第 {index} 行 "
                "effective_from_ts "
                "必须是 datetime。"
            )

        if effective_from_ts.tzinfo is not None:
            raise ValueError(
                "bridge_customer_membership "
                f"第 {index} 行 "
                "effective_from_ts "
                "不能包含时区信息。"
            )

        customer_first_seen_ts = (
            datetime.combine(
                customer_lookup[
                    customer_code
                ][
                    "first_seen_date"
                ],
                datetime.min.time(),
            )
        )

        membership_joined_at = (
            membership_lookup[
                member_code
            ][
                "joined_at"
            ]
        )

        expected_effective_from_ts = max(
            customer_first_seen_ts,
            membership_joined_at,
        )

        if (
            effective_from_ts
            != expected_effective_from_ts
        ):
            raise ValueError(
                "bridge_customer_membership "
                f"第 {index} 行映射开始时间"
                "不符合 max 规则："
                "expected="
                f"{expected_effective_from_ts}, "
                f"actual={effective_from_ts}"
            )

        effective_to_ts = row[
            "effective_to_ts"
        ]

        if effective_to_ts is not None:
            raise ValueError(
                "Day64 初始身份映射必须保持开放，"
                "effective_to_ts 应为 None："
                f"index={index}, "
                f"actual={effective_to_ts}"
            )

        mapping_status = row[
            "mapping_status"
        ]

        if (
            not isinstance(mapping_status, str)
            or not mapping_status.strip()
        ):
            raise ValueError(
                "bridge_customer_membership "
                f"第 {index} 行 mapping_status "
                "必须是非空字符串。"
            )

        if (
            mapping_status
            != expected_mapping_status
        ):
            raise ValueError(
                "bridge_customer_membership "
                f"第 {index} 行 mapping_status "
                "不正确："
                f"expected={expected_mapping_status}, "
                f"actual={mapping_status}"
            )

        customer_codes.add(
            customer_code
        )

        member_codes.add(
            member_code
        )

        mapping_pairs.add(pair)

    expected_unmapped_customer_count = (
        profile["customers"]
        - expected_count
    )

    actual_unmapped_customer_count = (
        len(customer_lookup)
        - len(customer_codes)
    )

    if (
        actual_unmapped_customer_count
        != expected_unmapped_customer_count
    ):
        raise ValueError(
            "未映射客户数量不正确："
            f"expected="
            f"{expected_unmapped_customer_count}, "
            f"actual="
            f"{actual_unmapped_customer_count}"
        )

    expected_membership_only_count = (
        profile["membership_accounts"]
        - expected_count
    )

    actual_membership_only_count = (
        len(membership_lookup)
        - len(member_codes)
    )

    if (
        actual_membership_only_count
        != expected_membership_only_count
    ):
        raise ValueError(
            "仅会员账户数量不正确："
            f"expected="
            f"{expected_membership_only_count}, "
            f"actual="
            f"{actual_membership_only_count}"
        )


def preview_bridge_customer_membership_rows(
    manifest: dict[str, Any],
) -> None:
    rows = (
        build_bridge_customer_membership_rows(
            manifest
        )
    )

    validate_bridge_customer_membership_rows(
        rows,
        manifest,
    )

    repeated_rows = (
        build_bridge_customer_membership_rows(
            manifest
        )
    )

    if rows != repeated_rows:
        raise ValueError(
            "bridge_customer_membership "
            "重复生成结果不一致，"
            "确定性校验失败。"
        )

    _, profile = get_active_scale_profile(
        manifest
    )

    mapped_customer_count = len(rows)

    unmapped_customer_count = (
        profile["customers"]
        - mapped_customer_count
    )

    membership_only_count = (
        profile["membership_accounts"]
        - mapped_customer_count
    )

    effective_from_values = [
        row["effective_from_ts"]
        for row in rows
    ]

    customer_rows = build_dim_customer_rows(
        manifest
    )

    membership_rows = (
        build_dim_membership_account_rows(
            manifest
        )
    )

    customer_lookup = {
        row["customer_code"]: row
        for row in customer_rows
    }

    membership_lookup = {
        row["member_code"]: row
        for row in membership_rows
    }

    effective_from_source_counts = Counter()

    for row in rows:
        customer_first_seen_ts = (
            datetime.combine(
                customer_lookup[
                    row["customer_code"]
                ][
                    "first_seen_date"
                ],
                datetime.min.time(),
            )
        )

        membership_joined_at = (
            membership_lookup[
                row["member_code"]
            ][
                "joined_at"
            ]
        )

        if (
            customer_first_seen_ts
            > membership_joined_at
        ):
            effective_from_source_counts[
                "customer_first_seen"
            ] += 1
        else:
            effective_from_source_counts[
                "member_joined_at"
            ] += 1

    print(
        "bridge_customer_membership "
        "row preview passed."
    )
    print(
        "Mapped customer-membership pairs: "
        f"{mapped_customer_count}"
    )
    print(
        "Customers without membership mapping: "
        f"{unmapped_customer_count}"
    )
    print(
        "Membership accounts without "
        "customer mapping: "
        f"{membership_only_count}"
    )
    print(
        "Effective-from source counts: "
        f"{dict(effective_from_source_counts)}"
    )
    print(
        "Effective-from range: "
        f"{min(effective_from_values)} -> "
        f"{max(effective_from_values)}"
    )
    print(f"First row: {rows[0]}")
    print(f"Last row: {rows[-1]}")
    print(
        "Open mappings: "
        f"{mapped_customer_count}"
    )
    print("Deterministic check: passed.")


def insert_bridge_customer_membership_rows(
    rows: list[dict[str, Any]],
) -> None:
    """
    将 customer-membership 身份映射写入 PostgreSQL。

    生成阶段使用稳定业务键：
    - customer_code
    - member_code

    写库阶段解析为：
    - customer_id
    - membership_account_id

    安全策略：
    1. 生成结果不能为空；
    2. 目标表必须为空；
    3. 所有客户和会员编码必须能唯一解析；
    4. 检查、插入和验证位于同一事务；
    5. 校验开放关系的一对一约束；
    6. 校验 effective_from_ts 的跨表时间规则；
    7. 数据库结果与生成结果逐行比较；
    8. 任意异常自动回滚。
    """
    if not rows:
        raise ValueError(
            "不能插入空的 "
            "bridge_customer_membership 数据。"
        )

    insert_sql = text(
        """
        INSERT INTO
            beauty_bi_v2.bridge_customer_membership (
                customer_id,
                membership_account_id,
                effective_from_ts,
                effective_to_ts,
                mapping_status
            )
        VALUES (
            :customer_id,
            :membership_account_id,
            :effective_from_ts,
            :effective_to_ts,
            :mapping_status
        )
        """
    )

    select_sql = text(
        """
        SELECT
            customer.customer_code,
            account.member_code,
            mapping.effective_from_ts,
            mapping.effective_to_ts,
            mapping.mapping_status
        FROM
            beauty_bi_v2.bridge_customer_membership
                AS mapping
        INNER JOIN
            beauty_bi_v2.dim_customer
                AS customer
            ON customer.customer_id =
                mapping.customer_id
        INNER JOIN
            beauty_bi_v2.dim_membership_account
                AS account
            ON account.membership_account_id =
                mapping.membership_account_id
        ORDER BY
            customer.customer_code,
            account.member_code
        """
    )

    with engine.begin() as connection:
        existing_count = connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM
                    beauty_bi_v2.
                    bridge_customer_membership
                """
            )
        ).scalar_one()

        if existing_count != 0:
            raise RuntimeError(
                "beauty_bi_v2."
                "bridge_customer_membership "
                "已存在数据，为避免重复写入，"
                "本次 Seed 已停止。"
                f" existing_count={existing_count}"
            )

        customer_records = connection.execute(
            text(
                """
                SELECT
                    customer_id,
                    customer_code,
                    first_seen_date
                FROM beauty_bi_v2.dim_customer
                ORDER BY customer_code
                """
            )
        ).mappings().all()

        if not customer_records:
            raise RuntimeError(
                "beauty_bi_v2.dim_customer 为空，"
                "无法解析 customer_id。"
            )

        membership_records = connection.execute(
            text(
                """
                SELECT
                    membership_account_id,
                    member_code,
                    joined_at
                FROM
                    beauty_bi_v2.
                    dim_membership_account
                ORDER BY member_code
                """
            )
        ).mappings().all()

        if not membership_records:
            raise RuntimeError(
                "beauty_bi_v2."
                "dim_membership_account 为空，"
                "无法解析 membership_account_id。"
            )

        customer_lookup = {
            record["customer_code"]: {
                "customer_id": record[
                    "customer_id"
                ],
                "first_seen_date": record[
                    "first_seen_date"
                ],
            }
            for record in customer_records
        }

        membership_lookup = {
            record["member_code"]: {
                "membership_account_id": record[
                    "membership_account_id"
                ],
                "joined_at": record[
                    "joined_at"
                ],
            }
            for record in membership_records
        }

        required_customer_codes = {
            row["customer_code"]
            for row in rows
        }

        required_member_codes = {
            row["member_code"]
            for row in rows
        }

        missing_customer_codes = (
            required_customer_codes
            - customer_lookup.keys()
        )

        if missing_customer_codes:
            raise RuntimeError(
                "bridge_customer_membership "
                "引用了数据库中不存在的客户："
                f"{sorted(missing_customer_codes)}"
            )

        missing_member_codes = (
            required_member_codes
            - membership_lookup.keys()
        )

        if missing_member_codes:
            raise RuntimeError(
                "bridge_customer_membership "
                "引用了数据库中不存在的会员账户："
                f"{sorted(missing_member_codes)}"
            )

        database_insert_rows: list[
            dict[str, Any]
        ] = []

        for row in rows:
            customer_code = row[
                "customer_code"
            ]

            member_code = row[
                "member_code"
            ]

            database_insert_rows.append(
                {
                    "customer_id": (
                        customer_lookup[
                            customer_code
                        ][
                            "customer_id"
                        ]
                    ),
                    "membership_account_id": (
                        membership_lookup[
                            member_code
                        ][
                            "membership_account_id"
                        ]
                    ),
                    "effective_from_ts": row[
                        "effective_from_ts"
                    ],
                    "effective_to_ts": row[
                        "effective_to_ts"
                    ],
                    "mapping_status": row[
                        "mapping_status"
                    ],
                }
            )

        connection.execute(
            insert_sql,
            database_insert_rows,
        )

        (
            actual_count,
            distinct_customer_count,
            distinct_membership_count,
            open_mapping_count,
            closed_mapping_count,
            active_mapping_count,
            min_effective_from_ts,
            max_effective_from_ts,
        ) = connection.execute(
            text(
                """
                SELECT
                    COUNT(*),
                    COUNT(DISTINCT customer_id),
                    COUNT(
                        DISTINCT membership_account_id
                    ),
                    COUNT(*) FILTER (
                        WHERE effective_to_ts IS NULL
                    ),
                    COUNT(*) FILTER (
                        WHERE effective_to_ts IS NOT NULL
                    ),
                    COUNT(*) FILTER (
                        WHERE mapping_status = 'active'
                    ),
                    MIN(effective_from_ts),
                    MAX(effective_from_ts)
                FROM
                    beauty_bi_v2.
                    bridge_customer_membership
                """
            )
        ).one()

        if actual_count != len(rows):
            raise RuntimeError(
                "bridge_customer_membership "
                "插入后的行数不正确："
                f"expected={len(rows)}, "
                f"actual={actual_count}"
            )

        if distinct_customer_count != actual_count:
            raise RuntimeError(
                "开放身份映射中存在一个客户"
                "对应多个会员账户的情况："
                f"rows={actual_count}, "
                "distinct_customers="
                f"{distinct_customer_count}"
            )

        if (
            distinct_membership_count
            != actual_count
        ):
            raise RuntimeError(
                "开放身份映射中存在一个会员账户"
                "对应多个客户的情况："
                f"rows={actual_count}, "
                "distinct_memberships="
                f"{distinct_membership_count}"
            )

        if open_mapping_count != actual_count:
            raise RuntimeError(
                "Day64 身份映射必须全部开放："
                f"expected={actual_count}, "
                f"actual={open_mapping_count}"
            )

        if closed_mapping_count != 0:
            raise RuntimeError(
                "Day64 不应生成已关闭身份映射："
                f"closed_count={closed_mapping_count}"
            )

        expected_active_count = sum(
            row["mapping_status"] == "active"
            for row in rows
        )

        if (
            active_mapping_count
            != expected_active_count
        ):
            raise RuntimeError(
                "bridge_customer_membership "
                "active 状态数量不正确："
                f"expected={expected_active_count}, "
                f"actual={active_mapping_count}"
            )

        expected_min_effective_from_ts = min(
            row["effective_from_ts"]
            for row in rows
        )

        expected_max_effective_from_ts = max(
            row["effective_from_ts"]
            for row in rows
        )

        if (
            min_effective_from_ts
            != expected_min_effective_from_ts
            or max_effective_from_ts
            != expected_max_effective_from_ts
        ):
            raise RuntimeError(
                "bridge_customer_membership "
                "生效时间范围不正确："
                "expected="
                f"{expected_min_effective_from_ts} -> "
                f"{expected_max_effective_from_ts}, "
                "actual="
                f"{min_effective_from_ts} -> "
                f"{max_effective_from_ts}"
            )

        invalid_effective_from_count = (
            connection.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM
                        beauty_bi_v2.
                        bridge_customer_membership
                            AS mapping
                    INNER JOIN
                        beauty_bi_v2.dim_customer
                            AS customer
                        ON customer.customer_id =
                            mapping.customer_id
                    INNER JOIN
                        beauty_bi_v2.
                        dim_membership_account
                            AS account
                        ON account.
                            membership_account_id =
                            mapping.
                            membership_account_id
                    WHERE
                        mapping.effective_from_ts
                        <> GREATEST(
                            customer.first_seen_date
                                ::timestamp,
                            account.joined_at
                        )
                    """
                )
            ).scalar_one()
        )

        if invalid_effective_from_count != 0:
            raise RuntimeError(
                "bridge_customer_membership "
                "数据库中存在不符合 max 时间规则"
                "的映射："
                f"invalid_count="
                f"{invalid_effective_from_count}"
            )

        invalid_interval_count = (
            connection.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM
                        beauty_bi_v2.
                        bridge_customer_membership
                    WHERE
                        effective_to_ts IS NOT NULL
                        AND effective_to_ts
                            <= effective_from_ts
                    """
                )
            ).scalar_one()
        )

        if invalid_interval_count != 0:
            raise RuntimeError(
                "bridge_customer_membership "
                "数据库中存在非法有效区间："
                f"invalid_count="
                f"{invalid_interval_count}"
            )

        unmapped_customer_count = (
            connection.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM beauty_bi_v2.dim_customer
                        AS customer
                    LEFT JOIN
                        beauty_bi_v2.
                        bridge_customer_membership
                            AS mapping
                        ON mapping.customer_id =
                            customer.customer_id
                        AND mapping.effective_to_ts
                            IS NULL
                    WHERE
                        mapping.customer_membership_id
                            IS NULL
                    """
                )
            ).scalar_one()
        )

        membership_only_count = (
            connection.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM
                        beauty_bi_v2.
                        dim_membership_account
                            AS account
                    LEFT JOIN
                        beauty_bi_v2.
                        bridge_customer_membership
                            AS mapping
                        ON
                            mapping.
                            membership_account_id =
                            account.
                            membership_account_id
                        AND mapping.effective_to_ts
                            IS NULL
                    WHERE
                        mapping.customer_membership_id
                            IS NULL
                    """
                )
            ).scalar_one()
        )

        expected_unmapped_customer_count = (
            len(customer_records)
            - len(rows)
        )

        expected_membership_only_count = (
            len(membership_records)
            - len(rows)
        )

        if (
            unmapped_customer_count
            != expected_unmapped_customer_count
        ):
            raise RuntimeError(
                "数据库中的未映射客户数量不正确："
                f"expected="
                f"{expected_unmapped_customer_count}, "
                f"actual={unmapped_customer_count}"
            )

        if (
            membership_only_count
            != expected_membership_only_count
        ):
            raise RuntimeError(
                "数据库中的仅会员账户数量不正确："
                f"expected="
                f"{expected_membership_only_count}, "
                f"actual={membership_only_count}"
            )

        database_rows = [
            dict(row)
            for row in connection.execute(
                select_sql
            ).mappings().all()
        ]

        expected_rows = sorted(
            rows,
            key=lambda row: (
                row["customer_code"],
                row["member_code"],
            ),
        )

        if database_rows != expected_rows:
            for expected_row, actual_row in zip(
                expected_rows,
                database_rows,
                strict=True,
            ):
                if expected_row != actual_row:
                    raise RuntimeError(
                        "bridge_customer_membership "
                        "数据库写入结果"
                        "与生成结果不一致："
                        f"expected={expected_row}, "
                        f"actual={actual_row}"
                    )

            raise RuntimeError(
                "bridge_customer_membership "
                "数据库写入结果与生成结果不一致。"
            )

    print(
        "bridge_customer_membership "
        "database seed passed."
    )
    print(f"Inserted rows: {actual_count}")
    print(
        "Distinct customers: "
        f"{distinct_customer_count}"
    )
    print(
        "Distinct membership accounts: "
        f"{distinct_membership_count}"
    )
    print(
        "Open mappings: "
        f"{open_mapping_count}"
    )
    print(
        "Closed mappings: "
        f"{closed_mapping_count}"
    )
    print(
        "Active mappings: "
        f"{active_mapping_count}"
    )
    print(
        "Customers without membership mapping: "
        f"{unmapped_customer_count}"
    )
    print(
        "Membership accounts without "
        "customer mapping: "
        f"{membership_only_count}"
    )
    print(
        "Effective-from range: "
        f"{min_effective_from_ts} -> "
        f"{max_effective_from_ts}"
    )
    print(
        "Identity foreign-key resolution: passed."
    )
    print(
        "One-to-one open mapping check: passed."
    )
    print(
        "Effective-from max rule check: passed."
    )
    print("Database row comparison: passed.")


def seed_bridge_customer_membership(
    manifest: dict[str, Any],
) -> None:
    rows = (
        build_bridge_customer_membership_rows(
            manifest
        )
    )

    validate_bridge_customer_membership_rows(
        rows,
        manifest,
    )

    repeated_rows = (
        build_bridge_customer_membership_rows(
            manifest
        )
    )

    if rows != repeated_rows:
        raise ValueError(
            "bridge_customer_membership "
            "重复生成结果不一致，"
            "确定性校验失败。"
        )

    _, profile = get_active_scale_profile(
        manifest
    )

    mapped_count = len(rows)

    print(
        "bridge_customer_membership "
        "generation passed."
    )
    print(
        "Mapped customer-membership pairs: "
        f"{mapped_count}"
    )
    print(
        "Customers without membership mapping: "
        f"{profile['customers'] - mapped_count}"
    )
    print(
        "Membership accounts without "
        "customer mapping: "
        f"{profile['membership_accounts'] - mapped_count}"
    )
    print(f"First row: {rows[0]}")
    print(f"Last row: {rows[-1]}")
    print("Deterministic check: passed.")

    insert_bridge_customer_membership_rows(
        rows
    )


def random_datetime_between(
    rng: random.Random,
    start_ts: datetime,
    end_ts: datetime,
    field_name: str,
) -> datetime:
    """
    在闭区间 [start_ts, end_ts] 中，
    按秒确定性抽取一个 datetime。
    """
    if start_ts.tzinfo is not None:
        raise ValueError(
            f"{field_name}.start_ts 不能包含时区。"
        )

    if end_ts.tzinfo is not None:
        raise ValueError(
            f"{field_name}.end_ts 不能包含时区。"
        )

    if start_ts > end_ts:
        raise ValueError(
            f"{field_name} 时间区间不合法："
            f"{start_ts} -> {end_ts}"
        )

    total_seconds = int(
        (end_ts - start_ts).total_seconds()
    )

    return start_ts + timedelta(
        seconds=rng.randint(
            0,
            total_seconds,
        )
    )


def build_membership_channel_binding_rows(
    manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    确定性生成会员渠道绑定历史暂存行。

    生成阶段使用稳定业务键：
    - member_code
    - channel_code

    正式写库时再解析为数据库外键。
    """
    membership_rows = (
        build_dim_membership_account_rows(
            manifest
        )
    )

    parameters = manifest[
        "business_patterns"
    ][
        "P03_membership_customer_overlap"
    ][
        "parameters"
    ]

    config = manifest[
        "channel_binding_generation"
    ]

    binding_distribution = parameters[
        "channel_binding_count_distribution"
    ]

    account_count_allocations = (
        allocate_weighted_counts(
            total_count=len(membership_rows),
            weighted_items=[
                (
                    str(binding_count),
                    probability,
                )
                for binding_count, probability
                in binding_distribution.items()
            ],
            allocation_name=(
                "membership channel binding count"
            ),
        )
    )

    binding_count_pool: list[int] = []

    for binding_count in (
        binding_distribution.keys()
    ):
        allocated_account_count = (
            account_count_allocations[
                str(binding_count)
            ]
        )

        binding_count_pool.extend(
            [binding_count]
            * allocated_account_count
        )

    if (
        len(binding_count_pool)
        != len(membership_rows)
    ):
        raise ValueError(
            "会员绑定数量池行数不正确："
            f"expected={len(membership_rows)}, "
            f"actual={len(binding_count_pool)}"
        )

    random_seed = manifest[
        "generation"
    ][
        "random_seed"
    ]

    rng = random.Random(random_seed)

    rng.shuffle(binding_count_pool)

    bindable_channel_codes = [
        channel["channel_code"].strip()
        for channel in manifest[
            "fixed_dimensions"
        ][
            "channels"
        ]
        if (
            channel["is_active"]
            and channel[
                "supports_membership_binding"
            ]
        )
    ]

    business_end_date = parse_manifest_date(
        manifest[
            "generation"
        ][
            "business_end_date"
        ],
        "generation.business_end_date",
    )

    observation_end_date = (
        parse_manifest_date(
            manifest[
                "generation"
            ][
                "event_observation_end_date"
            ],
            (
                "generation."
                "event_observation_end_date"
            ),
        )
    )

    business_end_ts = datetime.combine(
        business_end_date,
        datetime.max.time(),
    ).replace(
        microsecond=0
    )

    observation_end_ts = datetime.combine(
        observation_end_date,
        datetime.max.time(),
    ).replace(
        microsecond=0
    )

    close_delay_seconds = config[
        "inactive_account_min_close_delay_seconds"
    ]

    status_mapping = config[
        "binding_status_by_membership_status"
    ]

    source_mapping = config[
        "binding_source_by_channel_role"
    ]

    rows: list[dict[str, Any]] = []

    for account_index, account in enumerate(
        membership_rows
    ):
        member_code = account[
            "member_code"
        ]

        joined_at = account[
            "joined_at"
        ]

        join_channel_code = account[
            "join_channel_code"
        ]

        membership_status = account[
            "membership_status"
        ]

        binding_count = binding_count_pool[
            account_index
        ]

        additional_channel_count = (
            binding_count - 1
        )

        additional_candidates = [
            channel_code
            for channel_code
            in bindable_channel_codes
            if channel_code
            != join_channel_code
        ]

        additional_channel_codes = (
            rng.sample(
                additional_candidates,
                k=additional_channel_count,
            )
        )

        account_rows: list[
            dict[str, Any]
        ] = [
            {
                "member_code": member_code,
                "channel_code": (
                    join_channel_code
                ),
                "effective_from_ts": joined_at,
                "effective_to_ts": None,
                "binding_status": (
                    status_mapping[
                        membership_status
                    ]
                ),
                "binding_source": (
                    source_mapping[
                        "join_channel"
                    ]
                ),
            }
        ]

        for channel_code in (
            additional_channel_codes
        ):
            effective_from_ts = (
                random_datetime_between(
                    rng=rng,
                    start_ts=joined_at,
                    end_ts=business_end_ts,
                    field_name=(
                        "additional channel "
                        "effective_from_ts"
                    ),
                )
            )

            account_rows.append(
                {
                    "member_code": member_code,
                    "channel_code": channel_code,
                    "effective_from_ts": (
                        effective_from_ts
                    ),
                    "effective_to_ts": None,
                    "binding_status": (
                        status_mapping[
                            membership_status
                        ]
                    ),
                    "binding_source": (
                        source_mapping[
                            "additional_channel"
                        ]
                    ),
                }
            )

        if membership_status == "inactive":
            latest_effective_from_ts = max(
                row["effective_from_ts"]
                for row in account_rows
            )

            earliest_close_ts = (
                latest_effective_from_ts
                + timedelta(
                    seconds=close_delay_seconds
                )
            )

            account_close_ts = (
                random_datetime_between(
                    rng=rng,
                    start_ts=earliest_close_ts,
                    end_ts=observation_end_ts,
                    field_name=(
                        "inactive account close"
                    ),
                )
            )

            for row in account_rows:
                row["effective_to_ts"] = (
                    account_close_ts
                )

        rows.extend(account_rows)

    return rows


def validate_membership_channel_binding_rows(
    rows: list[dict[str, Any]],
    manifest: dict[str, Any],
) -> None:
    """
    校验会员渠道绑定历史暂存行。
    """
    if not rows:
        raise ValueError(
            "会员渠道绑定历史生成结果不能为空。"
        )

    membership_rows = (
        build_dim_membership_account_rows(
            manifest
        )
    )

    membership_lookup = {
        row["member_code"]: row
        for row in membership_rows
    }

    parameters = manifest[
        "business_patterns"
    ][
        "P03_membership_customer_overlap"
    ][
        "parameters"
    ]

    config = manifest[
        "channel_binding_generation"
    ]

    binding_distribution = parameters[
        "channel_binding_count_distribution"
    ]

    expected_account_count_allocations = (
        allocate_weighted_counts(
            total_count=len(membership_rows),
            weighted_items=[
                (
                    str(binding_count),
                    probability,
                )
                for binding_count, probability
                in binding_distribution.items()
            ],
            allocation_name=(
                "membership channel binding count"
            ),
        )
    )

    expected_binding_count_distribution = {
        int(binding_count):
            account_count
        for binding_count, account_count
        in expected_account_count_allocations.items()
    }

    expected_total_rows = sum(
        binding_count * account_count
        for binding_count, account_count
        in expected_binding_count_distribution.items()
    )

    if len(rows) != expected_total_rows:
        raise ValueError(
            "渠道绑定历史总行数不正确："
            f"expected={expected_total_rows}, "
            f"actual={len(rows)}"
        )

    required_fields = {
        "member_code",
        "channel_code",
        "effective_from_ts",
        "effective_to_ts",
        "binding_status",
        "binding_source",
    }

    bindable_channel_codes = {
        channel["channel_code"].strip()
        for channel in manifest[
            "fixed_dimensions"
        ][
            "channels"
        ]
        if (
            channel["is_active"]
            and channel[
                "supports_membership_binding"
            ]
        )
    }

    business_end_ts = datetime.combine(
        parse_manifest_date(
            manifest[
                "generation"
            ][
                "business_end_date"
            ],
            "generation.business_end_date",
        ),
        datetime.max.time(),
    ).replace(
        microsecond=0
    )

    observation_end_ts = datetime.combine(
        parse_manifest_date(
            manifest[
                "generation"
            ][
                "event_observation_end_date"
            ],
            (
                "generation."
                "event_observation_end_date"
            ),
        ),
        datetime.max.time(),
    ).replace(
        microsecond=0
    )

    close_delay_seconds = config[
        "inactive_account_min_close_delay_seconds"
    ]

    status_mapping = config[
        "binding_status_by_membership_status"
    ]

    source_mapping = config[
        "binding_source_by_channel_role"
    ]

    rows_by_member: dict[
        str,
        list[dict[str, Any]],
    ] = {}

    account_channel_pairs: set[
        tuple[str, str]
    ] = set()

    for index, row in enumerate(rows):
        if set(row.keys()) != required_fields:
            raise ValueError(
                "渠道绑定历史 "
                f"第 {index} 行字段不正确："
                f"{sorted(row.keys())}"
            )

        member_code = row[
            "member_code"
        ]

        channel_code = row[
            "channel_code"
        ]

        if member_code not in membership_lookup:
            raise ValueError(
                "渠道绑定历史引用了"
                "不存在的 member_code："
                f"{member_code!r}"
            )

        if channel_code not in bindable_channel_codes:
            raise ValueError(
                "渠道绑定历史引用了"
                "不可绑定渠道："
                f"{channel_code!r}"
            )

        pair = (
            member_code,
            channel_code,
        )

        if pair in account_channel_pairs:
            raise ValueError(
                "同一会员和渠道不能生成"
                "多条初始绑定记录："
                f"{pair}"
            )

        effective_from_ts = row[
            "effective_from_ts"
        ]

        if not isinstance(
            effective_from_ts,
            datetime,
        ):
            raise ValueError(
                "effective_from_ts "
                "必须是 datetime："
                f"index={index}"
            )

        if effective_from_ts.tzinfo is not None:
            raise ValueError(
                "effective_from_ts "
                "不能包含时区："
                f"index={index}"
            )

        effective_to_ts = row[
            "effective_to_ts"
        ]

        if effective_to_ts is not None:
            if not isinstance(
                effective_to_ts,
                datetime,
            ):
                raise ValueError(
                    "effective_to_ts 必须是 "
                    "None 或 datetime："
                    f"index={index}"
                )

            if effective_to_ts.tzinfo is not None:
                raise ValueError(
                    "effective_to_ts "
                    "不能包含时区："
                    f"index={index}"
                )

            if (
                effective_to_ts
                <= effective_from_ts
            ):
                raise ValueError(
                    "渠道绑定结束时间必须晚于"
                    "开始时间："
                    f"index={index}"
                )

            if (
                effective_to_ts
                > observation_end_ts
            ):
                raise ValueError(
                    "渠道绑定结束时间超过"
                    "观察窗口："
                    f"index={index}"
                )

        rows_by_member.setdefault(
            member_code,
            [],
        ).append(row)

        account_channel_pairs.add(pair)

    if (
        set(rows_by_member.keys())
        != set(membership_lookup.keys())
    ):
        missing_member_codes = (
            set(membership_lookup.keys())
            - set(rows_by_member.keys())
        )

        raise ValueError(
            "存在没有渠道绑定记录的会员账户："
            f"{sorted(missing_member_codes)}"
        )

    actual_binding_count_distribution = Counter(
        len(account_rows)
        for account_rows
        in rows_by_member.values()
    )

    if (
        dict(actual_binding_count_distribution)
        != expected_binding_count_distribution
    ):
        raise ValueError(
            "会员绑定渠道数量分布不正确："
            "expected="
            f"{expected_binding_count_distribution}, "
            "actual="
            f"{dict(actual_binding_count_distribution)}"
        )

    for member_code, account_rows in (
        rows_by_member.items()
    ):
        account = membership_lookup[
            member_code
        ]

        joined_at = account[
            "joined_at"
        ]

        join_channel_code = account[
            "join_channel_code"
        ]

        membership_status = account[
            "membership_status"
        ]

        join_channel_rows = [
            row
            for row in account_rows
            if (
                row["channel_code"]
                == join_channel_code
            )
        ]

        if len(join_channel_rows) != 1:
            raise ValueError(
                "每个会员必须且只能包含一条"
                "首次入会渠道绑定："
                f"member_code={member_code}"
            )

        join_channel_row = (
            join_channel_rows[0]
        )

        if (
            join_channel_row[
                "effective_from_ts"
            ]
            != joined_at
        ):
            raise ValueError(
                "首次入会渠道绑定必须从 "
                "joined_at 生效："
                f"member_code={member_code}"
            )

        if (
            join_channel_row[
                "binding_source"
            ]
            != source_mapping[
                "join_channel"
            ]
        ):
            raise ValueError(
                "首次入会渠道的 "
                "binding_source 不正确："
                f"member_code={member_code}"
            )

        for row in account_rows:
            expected_status = status_mapping[
                membership_status
            ]

            if (
                row["binding_status"]
                != expected_status
            ):
                raise ValueError(
                    "渠道绑定状态与会员账户状态"
                    "不一致："
                    f"member_code={member_code}"
                )

            if (
                row["channel_code"]
                != join_channel_code
            ):
                if (
                    row["binding_source"]
                    != source_mapping[
                        "additional_channel"
                    ]
                ):
                    raise ValueError(
                        "额外渠道的 binding_source "
                        "不正确："
                        f"member_code={member_code}"
                    )

                if not (
                    joined_at
                    <= row["effective_from_ts"]
                    <= business_end_ts
                ):
                    raise ValueError(
                        "额外渠道开始时间"
                        "超出允许范围："
                        f"member_code={member_code}"
                    )

        if membership_status == "active":
            if any(
                row["effective_to_ts"]
                is not None
                for row in account_rows
            ):
                raise ValueError(
                    "active 会员账户不能生成"
                    "已关闭渠道绑定："
                    f"member_code={member_code}"
                )

        elif membership_status == "inactive":
            close_values = {
                row["effective_to_ts"]
                for row in account_rows
            }

            if None in close_values:
                raise ValueError(
                    "inactive 会员账户不能保留"
                    "开放渠道绑定："
                    f"member_code={member_code}"
                )

            if len(close_values) != 1:
                raise ValueError(
                    "同一 inactive 会员账户的"
                    "渠道绑定必须使用同一关闭时间："
                    f"member_code={member_code}"
                )

            account_close_ts = next(
                iter(close_values)
            )

            latest_effective_from_ts = max(
                row["effective_from_ts"]
                for row in account_rows
            )

            if (
                account_close_ts
                < latest_effective_from_ts
                + timedelta(
                    seconds=close_delay_seconds
                )
            ):
                raise ValueError(
                    "inactive 账户关闭时间"
                    "未满足最小延迟："
                    f"member_code={member_code}"
                )


def preview_membership_channel_binding_rows(
    manifest: dict[str, Any],
) -> None:
    rows = (
        build_membership_channel_binding_rows(
            manifest
        )
    )

    validate_membership_channel_binding_rows(
        rows,
        manifest,
    )

    repeated_rows = (
        build_membership_channel_binding_rows(
            manifest
        )
    )

    if rows != repeated_rows:
        raise ValueError(
            "会员渠道绑定历史重复生成"
            "结果不一致，确定性校验失败。"
        )

    membership_rows = (
        build_dim_membership_account_rows(
            manifest
        )
    )

    rows_by_member: dict[
        str,
        list[dict[str, Any]],
    ] = {}

    for row in rows:
        rows_by_member.setdefault(
            row["member_code"],
            [],
        ).append(row)

    binding_count_distribution = Counter(
        len(account_rows)
        for account_rows
        in rows_by_member.values()
    )

    source_counts = Counter(
        row["binding_source"]
        for row in rows
    )

    open_binding_count = sum(
        row["effective_to_ts"] is None
        for row in rows
    )

    closed_binding_count = (
        len(rows) - open_binding_count
    )

    account_status_counts = Counter(
        row["membership_status"]
        for row in membership_rows
    )

    effective_from_values = [
        row["effective_from_ts"]
        for row in rows
    ]

    inactive_close_by_member = {
        row["member_code"]:
            row["effective_to_ts"]
        for row in rows
        if row["effective_to_ts"] is not None
    }

    print(
        "membership channel binding "
        "row preview passed."
    )
    print(f"Total rows: {len(rows)}")
    print(
        "Accounts by binding count: "
        f"{dict(binding_count_distribution)}"
    )
    print(
        "Binding source counts: "
        f"{dict(source_counts)}"
    )
    print(
        "Membership account status counts: "
        f"{dict(account_status_counts)}"
    )
    print(
        "Open binding rows: "
        f"{open_binding_count}"
    )
    print(
        "Closed binding rows: "
        f"{closed_binding_count}"
    )
    print(
        "Effective-from range: "
        f"{min(effective_from_values)} -> "
        f"{max(effective_from_values)}"
    )

    if inactive_close_by_member:
        inactive_close_values = list(
            inactive_close_by_member.values()
        )

        print(
            "Inactive account close range: "
            f"{min(inactive_close_values)} -> "
            f"{max(inactive_close_values)}"
        )

    print(f"First row: {rows[0]}")
    print(f"Last row: {rows[-1]}")
    print(
        "Join-channel inclusion check: passed."
    )
    print(
        "Inactive open-binding check: passed."
    )
    print("Deterministic check: passed.")


def insert_membership_channel_binding_rows(
    rows: list[dict[str, Any]],
    manifest: dict[str, Any],
) -> None:
    """
    将会员渠道绑定历史写入 PostgreSQL。

    生成阶段使用稳定业务键：
    - member_code
    - channel_code

    写库阶段解析为：
    - membership_account_id
    - channel_id

    安全策略：
    1. 目标表必须为空；
    2. 所有会员账户和渠道必须能够解析；
    3. 所有会员账户都必须至少存在一条绑定；
    4. 检查、插入和验证位于同一事务；
    5. 校验账户状态、开放关系和时间规则；
    6. 数据库结果与生成结果逐行比较；
    7. 任意异常自动回滚。
    """
    if not rows:
        raise ValueError(
            "不能插入空的会员渠道绑定历史。"
        )

    generation = manifest[
        "generation"
    ]

    config = manifest[
        "channel_binding_generation"
    ]

    business_end_ts = datetime.combine(
        parse_manifest_date(
            generation["business_end_date"],
            "generation.business_end_date",
        ),
        datetime.max.time(),
    ).replace(
        microsecond=0
    )

    observation_end_ts = datetime.combine(
        parse_manifest_date(
            generation[
                "event_observation_end_date"
            ],
            (
                "generation."
                "event_observation_end_date"
            ),
        ),
        datetime.max.time(),
    ).replace(
        microsecond=0
    )

    close_delay_seconds = config[
        "inactive_account_min_close_delay_seconds"
    ]

    status_mapping = config[
        "binding_status_by_membership_status"
    ]

    source_mapping = config[
        "binding_source_by_channel_role"
    ]

    insert_sql = text(
        """
        INSERT INTO
            beauty_bi_v2.
            fact_membership_channel_binding_history (
                membership_account_id,
                channel_id,
                effective_from_ts,
                effective_to_ts,
                binding_status,
                binding_source
            )
        VALUES (
            :membership_account_id,
            :channel_id,
            :effective_from_ts,
            :effective_to_ts,
            :binding_status,
            :binding_source
        )
        """
    )

    select_sql = text(
        """
        SELECT
            account.member_code,
            channel.channel_code,
            binding.effective_from_ts,
            binding.effective_to_ts,
            binding.binding_status,
            binding.binding_source
        FROM
            beauty_bi_v2.
            fact_membership_channel_binding_history
                AS binding
        INNER JOIN
            beauty_bi_v2.dim_membership_account
                AS account
            ON account.membership_account_id =
                binding.membership_account_id
        INNER JOIN
            beauty_bi_v2.dim_channel
                AS channel
            ON channel.channel_id =
                binding.channel_id
        ORDER BY
            account.member_code,
            channel.channel_code,
            binding.effective_from_ts
        """
    )

    with engine.begin() as connection:
        existing_count = connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM
                    beauty_bi_v2.
                    fact_membership_channel_binding_history
                """
            )
        ).scalar_one()

        if existing_count != 0:
            raise RuntimeError(
                "beauty_bi_v2."
                "fact_membership_channel_binding_history "
                "已存在数据，为避免重复写入，"
                "本次 Seed 已停止。"
                f" existing_count={existing_count}"
            )

        membership_records = (
            connection.execute(
                text(
                    """
                    SELECT
                        account.membership_account_id,
                        account.member_code,
                        account.joined_at,
                        account.membership_status,
                        join_channel.channel_code
                            AS join_channel_code
                    FROM
                        beauty_bi_v2.
                        dim_membership_account
                            AS account
                    INNER JOIN
                        beauty_bi_v2.dim_channel
                            AS join_channel
                        ON join_channel.channel_id =
                            account.join_channel_id
                    ORDER BY
                        account.member_code
                    """
                )
            ).mappings().all()
        )

        if not membership_records:
            raise RuntimeError(
                "beauty_bi_v2."
                "dim_membership_account 为空，"
                "无法解析 membership_account_id。"
            )

        channel_records = connection.execute(
            text(
                """
                SELECT
                    channel_id,
                    channel_code,
                    is_active
                FROM
                    beauty_bi_v2.dim_channel
                ORDER BY
                    channel_code
                """
            )
        ).mappings().all()

        if not channel_records:
            raise RuntimeError(
                "beauty_bi_v2.dim_channel 为空，"
                "无法解析 channel_id。"
            )

        membership_lookup = {
            record["member_code"]: {
                "membership_account_id": (
                    record[
                        "membership_account_id"
                    ]
                ),
                "joined_at": record[
                    "joined_at"
                ],
                "membership_status": record[
                    "membership_status"
                ],
                "join_channel_code": record[
                    "join_channel_code"
                ],
            }
            for record in membership_records
        }

        channel_lookup = {
            record["channel_code"]: {
                "channel_id": record[
                    "channel_id"
                ],
                "is_active": record[
                    "is_active"
                ],
            }
            for record in channel_records
        }

        required_member_codes = {
            row["member_code"]
            for row in rows
        }

        database_member_codes = set(
            membership_lookup.keys()
        )

        if (
            required_member_codes
            != database_member_codes
        ):
            database_accounts_without_binding = (
                database_member_codes
                - required_member_codes
            )

            unknown_generated_accounts = (
                required_member_codes
                - database_member_codes
            )

            raise RuntimeError(
                "生成结果与数据库会员账户集合"
                "不完全一致："
                "database_accounts_without_binding="
                f"{sorted(database_accounts_without_binding)}, "
                "unknown_generated_accounts="
                f"{sorted(unknown_generated_accounts)}"
            )

        required_channel_codes = {
            row["channel_code"]
            for row in rows
        }

        missing_channel_codes = (
            required_channel_codes
            - channel_lookup.keys()
        )

        if missing_channel_codes:
            raise RuntimeError(
                "渠道绑定历史引用了数据库中"
                "不存在的渠道："
                f"{sorted(missing_channel_codes)}"
            )

        inactive_channel_codes = {
            channel_code
            for channel_code
            in required_channel_codes
            if not channel_lookup[
                channel_code
            ][
                "is_active"
            ]
        }

        if inactive_channel_codes:
            raise RuntimeError(
                "渠道绑定历史不能使用"
                "已停用渠道："
                f"{sorted(inactive_channel_codes)}"
            )

        database_insert_rows: list[
            dict[str, Any]
        ] = []

        for row in rows:
            member_code = row[
                "member_code"
            ]

            channel_code = row[
                "channel_code"
            ]

            database_insert_rows.append(
                {
                    "membership_account_id": (
                        membership_lookup[
                            member_code
                        ][
                            "membership_account_id"
                        ]
                    ),
                    "channel_id": (
                        channel_lookup[
                            channel_code
                        ][
                            "channel_id"
                        ]
                    ),
                    "effective_from_ts": row[
                        "effective_from_ts"
                    ],
                    "effective_to_ts": row[
                        "effective_to_ts"
                    ],
                    "binding_status": row[
                        "binding_status"
                    ],
                    "binding_source": row[
                        "binding_source"
                    ],
                }
            )

        connection.execute(
            insert_sql,
            database_insert_rows,
        )

        (
            actual_count,
            distinct_member_count,
            distinct_channel_count,
            distinct_pair_count,
            open_binding_count,
            closed_binding_count,
            active_binding_count,
            inactive_binding_count,
            join_source_count,
            additional_source_count,
            min_effective_from_ts,
            max_effective_from_ts,
            min_effective_to_ts,
            max_effective_to_ts,
        ) = connection.execute(
            text(
                """
                SELECT
                    COUNT(*),
                    COUNT(
                        DISTINCT membership_account_id
                    ),
                    COUNT(
                        DISTINCT channel_id
                    ),
                    COUNT(
                        DISTINCT (
                            membership_account_id,
                            channel_id
                        )
                    ),
                    COUNT(*) FILTER (
                        WHERE effective_to_ts IS NULL
                    ),
                    COUNT(*) FILTER (
                        WHERE effective_to_ts IS NOT NULL
                    ),
                    COUNT(*) FILTER (
                        WHERE binding_status = 'active'
                    ),
                    COUNT(*) FILTER (
                        WHERE binding_status = 'inactive'
                    ),
                    COUNT(*) FILTER (
                        WHERE binding_source =
                            'join_channel'
                    ),
                    COUNT(*) FILTER (
                        WHERE binding_source =
                            'additional_channel'
                    ),
                    MIN(effective_from_ts),
                    MAX(effective_from_ts),
                    MIN(effective_to_ts),
                    MAX(effective_to_ts)
                FROM
                    beauty_bi_v2.
                    fact_membership_channel_binding_history
                """
            )
        ).one()

        if actual_count != len(rows):
            raise RuntimeError(
                "渠道绑定历史插入后的"
                "行数不正确："
                f"expected={len(rows)}, "
                f"actual={actual_count}"
            )

        expected_member_count = len(
            required_member_codes
        )

        if (
            distinct_member_count
            != expected_member_count
        ):
            raise RuntimeError(
                "渠道绑定历史覆盖的"
                "会员账户数量不正确："
                f"expected={expected_member_count}, "
                f"actual={distinct_member_count}"
            )

        expected_channel_count = len(
            required_channel_codes
        )

        if (
            distinct_channel_count
            != expected_channel_count
        ):
            raise RuntimeError(
                "渠道绑定历史使用的渠道数量"
                "不正确："
                f"expected={expected_channel_count}, "
                f"actual={distinct_channel_count}"
            )

        expected_pair_count = len(
            {
                (
                    row["member_code"],
                    row["channel_code"],
                )
                for row in rows
            }
        )

        if distinct_pair_count != expected_pair_count:
            raise RuntimeError(
                "数据库中的会员—渠道组合数量"
                "不正确："
                f"expected={expected_pair_count}, "
                f"actual={distinct_pair_count}"
            )

        # Day64 初始数据中，每个会员—渠道组合
        # 只生成一条历史记录。
        if distinct_pair_count != actual_count:
            raise RuntimeError(
                "数据库中存在重复的"
                "会员—渠道初始记录："
                f"rows={actual_count}, "
                f"distinct_pairs={distinct_pair_count}"
            )

        expected_open_count = sum(
            row["effective_to_ts"] is None
            for row in rows
        )

        expected_closed_count = (
            len(rows) - expected_open_count
        )

        if (
            open_binding_count
            != expected_open_count
        ):
            raise RuntimeError(
                "开放渠道绑定行数不正确："
                f"expected={expected_open_count}, "
                f"actual={open_binding_count}"
            )

        if (
            closed_binding_count
            != expected_closed_count
        ):
            raise RuntimeError(
                "关闭渠道绑定行数不正确："
                f"expected={expected_closed_count}, "
                f"actual={closed_binding_count}"
            )

        expected_status_counts = Counter(
            row["binding_status"]
            for row in rows
        )

        if (
            active_binding_count
            != expected_status_counts["active"]
        ):
            raise RuntimeError(
                "active 渠道绑定数量不正确："
                "expected="
                f"{expected_status_counts['active']}, "
                f"actual={active_binding_count}"
            )

        if (
            inactive_binding_count
            != expected_status_counts[
                "inactive"
            ]
        ):
            raise RuntimeError(
                "inactive 渠道绑定数量不正确："
                "expected="
                f"{expected_status_counts['inactive']}, "
                f"actual={inactive_binding_count}"
            )

        expected_source_counts = Counter(
            row["binding_source"]
            for row in rows
        )

        if (
            join_source_count
            != expected_source_counts[
                source_mapping[
                    "join_channel"
                ]
            ]
        ):
            raise RuntimeError(
                "首次入会渠道来源数量不正确："
                "expected="
                f"{expected_source_counts[source_mapping['join_channel']]}, "
                f"actual={join_source_count}"
            )

        if (
            additional_source_count
            != expected_source_counts[
                source_mapping[
                    "additional_channel"
                ]
            ]
        ):
            raise RuntimeError(
                "额外渠道来源数量不正确："
                "expected="
                f"{expected_source_counts[source_mapping['additional_channel']]}, "
                f"actual={additional_source_count}"
            )

        expected_min_effective_from_ts = min(
            row["effective_from_ts"]
            for row in rows
        )

        expected_max_effective_from_ts = max(
            row["effective_from_ts"]
            for row in rows
        )

        if (
            min_effective_from_ts
            != expected_min_effective_from_ts
            or max_effective_from_ts
            != expected_max_effective_from_ts
        ):
            raise RuntimeError(
                "渠道绑定开始时间范围不正确："
                "expected="
                f"{expected_min_effective_from_ts} -> "
                f"{expected_max_effective_from_ts}, "
                "actual="
                f"{min_effective_from_ts} -> "
                f"{max_effective_from_ts}"
            )

        expected_effective_to_values = [
            row["effective_to_ts"]
            for row in rows
            if row["effective_to_ts"] is not None
        ]

        if expected_effective_to_values:
            expected_min_effective_to_ts = min(
                expected_effective_to_values
            )

            expected_max_effective_to_ts = max(
                expected_effective_to_values
            )

            if (
                min_effective_to_ts
                != expected_min_effective_to_ts
                or max_effective_to_ts
                != expected_max_effective_to_ts
            ):
                raise RuntimeError(
                    "渠道绑定关闭时间范围不正确："
                    "expected="
                    f"{expected_min_effective_to_ts} -> "
                    f"{expected_max_effective_to_ts}, "
                    "actual="
                    f"{min_effective_to_ts} -> "
                    f"{max_effective_to_ts}"
                )

        invalid_join_source_count = (
            connection.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM
                        beauty_bi_v2.
                        fact_membership_channel_binding_history
                            AS binding
                    INNER JOIN
                        beauty_bi_v2.
                        dim_membership_account
                            AS account
                        ON account.
                            membership_account_id =
                            binding.
                            membership_account_id
                    WHERE
                        binding.binding_source =
                            :join_source
                        AND (
                            binding.channel_id
                                <> account.join_channel_id
                            OR binding.effective_from_ts
                                <> account.joined_at
                        )
                    """
                ),
                {
                    "join_source": source_mapping[
                        "join_channel"
                    ],
                },
            ).scalar_one()
        )

        if invalid_join_source_count != 0:
            raise RuntimeError(
                "数据库中存在不符合规则的"
                "首次入会渠道绑定："
                f"invalid_count="
                f"{invalid_join_source_count}"
            )

        accounts_without_one_join_binding = (
            connection.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM (
                        SELECT
                            account.
                                membership_account_id
                        FROM
                            beauty_bi_v2.
                            dim_membership_account
                                AS account
                        LEFT JOIN
                            beauty_bi_v2.
                            fact_membership_channel_binding_history
                                AS binding
                            ON binding.
                                membership_account_id =
                                account.
                                membership_account_id
                        GROUP BY
                            account.
                                membership_account_id
                        HAVING
                            COUNT(*) FILTER (
                                WHERE
                                    binding.binding_source =
                                        :join_source
                            ) <> 1
                    ) AS invalid_accounts
                    """
                ),
                {
                    "join_source": source_mapping[
                        "join_channel"
                    ],
                },
            ).scalar_one()
        )

        if (
            accounts_without_one_join_binding
            != 0
        ):
            raise RuntimeError(
                "存在未包含且仅包含一条"
                "首次入会渠道绑定的会员账户："
                f"invalid_account_count="
                f"{accounts_without_one_join_binding}"
            )

        invalid_additional_source_count = (
            connection.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM
                        beauty_bi_v2.
                        fact_membership_channel_binding_history
                            AS binding
                    INNER JOIN
                        beauty_bi_v2.
                        dim_membership_account
                            AS account
                        ON account.
                            membership_account_id =
                            binding.
                            membership_account_id
                    WHERE
                        binding.binding_source =
                            :additional_source
                        AND (
                            binding.channel_id =
                                account.join_channel_id
                            OR binding.effective_from_ts
                                < account.joined_at
                            OR binding.effective_from_ts
                                > :business_end_ts
                        )
                    """
                ),
                {
                    "additional_source": (
                        source_mapping[
                            "additional_channel"
                        ]
                    ),
                    "business_end_ts": (
                        business_end_ts
                    ),
                },
            ).scalar_one()
        )

        if (
            invalid_additional_source_count
            != 0
        ):
            raise RuntimeError(
                "数据库中存在不符合规则的"
                "额外渠道绑定："
                f"invalid_count="
                f"{invalid_additional_source_count}"
            )

        invalid_account_status_count = (
            connection.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM
                        beauty_bi_v2.
                        fact_membership_channel_binding_history
                            AS binding
                    INNER JOIN
                        beauty_bi_v2.
                        dim_membership_account
                            AS account
                        ON account.
                            membership_account_id =
                            binding.
                            membership_account_id
                    WHERE
                        (
                            account.membership_status =
                                'active'
                            AND (
                                binding.binding_status
                                    <> :active_status
                                OR binding.effective_to_ts
                                    IS NOT NULL
                            )
                        )
                        OR
                        (
                            account.membership_status =
                                'inactive'
                            AND (
                                binding.binding_status
                                    <> :inactive_status
                                OR binding.effective_to_ts
                                    IS NULL
                            )
                        )
                    """
                ),
                {
                    "active_status": status_mapping[
                        "active"
                    ],
                    "inactive_status": status_mapping[
                        "inactive"
                    ],
                },
            ).scalar_one()
        )

        if invalid_account_status_count != 0:
            raise RuntimeError(
                "数据库中的渠道绑定状态"
                "与会员账户状态不一致："
                f"invalid_count="
                f"{invalid_account_status_count}"
            )

        invalid_inactive_account_count = (
            connection.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM (
                        SELECT
                            account.
                                membership_account_id
                        FROM
                            beauty_bi_v2.
                            dim_membership_account
                                AS account
                        INNER JOIN
                            beauty_bi_v2.
                            fact_membership_channel_binding_history
                                AS binding
                            ON binding.
                                membership_account_id =
                                account.
                                membership_account_id
                        WHERE
                            account.membership_status =
                                'inactive'
                        GROUP BY
                            account.
                                membership_account_id
                        HAVING
                            COUNT(*) FILTER (
                                WHERE
                                    binding.effective_to_ts
                                        IS NULL
                            ) <> 0
                            OR COUNT(
                                DISTINCT
                                binding.effective_to_ts
                            ) <> 1
                            OR MIN(
                                binding.effective_to_ts
                            ) < (
                                MAX(
                                    binding.
                                        effective_from_ts
                                )
                                + (
                                    :close_delay_seconds
                                    * INTERVAL '1 second'
                                )
                            )
                            OR MAX(
                                binding.effective_to_ts
                            ) > :observation_end_ts
                    ) AS invalid_accounts
                    """
                ),
                {
                    "close_delay_seconds": (
                        close_delay_seconds
                    ),
                    "observation_end_ts": (
                        observation_end_ts
                    ),
                },
            ).scalar_one()
        )

        if (
            invalid_inactive_account_count
            != 0
        ):
            raise RuntimeError(
                "数据库中的 inactive 账户"
                "关闭规则不正确："
                f"invalid_account_count="
                f"{invalid_inactive_account_count}"
            )

        database_rows = [
            dict(row)
            for row in connection.execute(
                select_sql
            ).mappings().all()
        ]

        expected_rows = sorted(
            rows,
            key=lambda row: (
                row["member_code"],
                row["channel_code"],
                row["effective_from_ts"],
            ),
        )

        if database_rows != expected_rows:
            for expected_row, actual_row in zip(
                expected_rows,
                database_rows,
                strict=True,
            ):
                if expected_row != actual_row:
                    raise RuntimeError(
                        "渠道绑定历史数据库结果"
                        "与生成结果不一致："
                        f"expected={expected_row}, "
                        f"actual={actual_row}"
                    )

            raise RuntimeError(
                "渠道绑定历史数据库结果"
                "与生成结果不一致。"
            )

    print(
        "membership channel binding "
        "database seed passed."
    )
    print(f"Inserted rows: {actual_count}")
    print(
        "Distinct membership accounts: "
        f"{distinct_member_count}"
    )
    print(
        "Distinct channels: "
        f"{distinct_channel_count}"
    )
    print(
        "Open binding rows: "
        f"{open_binding_count}"
    )
    print(
        "Closed binding rows: "
        f"{closed_binding_count}"
    )
    print(
        "Binding source counts: "
        f"{dict(expected_source_counts)}"
    )
    print(
        "Binding status counts: "
        f"{dict(expected_status_counts)}"
    )
    print(
        "Effective-from range: "
        f"{min_effective_from_ts} -> "
        f"{max_effective_from_ts}"
    )

    if min_effective_to_ts is not None:
        print(
            "Inactive account close range: "
            f"{min_effective_to_ts} -> "
            f"{max_effective_to_ts}"
        )

    print(
        "Membership foreign-key resolution: "
        "passed."
    )
    print(
        "Channel foreign-key resolution: passed."
    )
    print(
        "Join-channel inclusion check: passed."
    )
    print(
        "Inactive open-binding check: passed."
    )
    print("Database row comparison: passed.")


def seed_membership_channel_binding(
    manifest: dict[str, Any],
) -> None:
    rows = (
        build_membership_channel_binding_rows(
            manifest
        )
    )

    validate_membership_channel_binding_rows(
        rows,
        manifest,
    )

    repeated_rows = (
        build_membership_channel_binding_rows(
            manifest
        )
    )

    if rows != repeated_rows:
        raise ValueError(
            "会员渠道绑定历史重复生成"
            "结果不一致，确定性校验失败。"
        )

    rows_by_member: dict[
        str,
        list[dict[str, Any]],
    ] = {}

    for row in rows:
        rows_by_member.setdefault(
            row["member_code"],
            [],
        ).append(row)

    binding_count_distribution = Counter(
        len(account_rows)
        for account_rows
        in rows_by_member.values()
    )

    source_counts = Counter(
        row["binding_source"]
        for row in rows
    )

    status_counts = Counter(
        row["binding_status"]
        for row in rows
    )

    open_binding_count = sum(
        row["effective_to_ts"] is None
        for row in rows
    )

    closed_binding_count = (
        len(rows) - open_binding_count
    )

    print(
        "membership channel binding "
        "generation passed."
    )
    print(f"Total rows: {len(rows)}")
    print(
        "Accounts by binding count: "
        f"{dict(binding_count_distribution)}"
    )
    print(
        "Binding source counts: "
        f"{dict(source_counts)}"
    )
    print(
        "Binding status counts: "
        f"{dict(status_counts)}"
    )
    print(
        "Open binding rows: "
        f"{open_binding_count}"
    )
    print(
        "Closed binding rows: "
        f"{closed_binding_count}"
    )
    print(f"First row: {rows[0]}")
    print(f"Last row: {rows[-1]}")
    print("Deterministic check: passed.")

    insert_membership_channel_binding_rows(
        rows,
        manifest,
    )

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Seed Beauty BI V2 fixed dimensions."
        )
    )

    parser.add_argument(
        "target",
        choices={
            "dim_date",
            "dim_region",
            "dim_channel",
            "dim_product_preview",
            "dim_product_rows_preview",
            "dim_product",
            "dim_campaign_preview",
            "dim_campaign",
            "dim_promotion_preview",
            "dim_promotion",
            "dim_customer_preview",
            "dim_customer",
            "dim_membership_account_preview",
            "dim_membership_account",
            "bridge_customer_membership_preview",
            "bridge_customer_membership",
            "membership_channel_binding_preview",
            "membership_channel_binding",
        },
        help="选择本次需要生成的维度表。",
    )

    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    loaded_manifest = (
        load_and_validate_day64_manifest()
    )

    if args.target == "dim_date":
        seed_dim_date(loaded_manifest)
    elif args.target == "dim_region":
        seed_dim_region(loaded_manifest)
    elif args.target == "dim_channel":
        seed_dim_channel(loaded_manifest)
    elif args.target == "dim_product_preview":
        preview_dim_product_allocation(loaded_manifest)
    elif args.target == "dim_product_rows_preview":
        preview_dim_product_rows(loaded_manifest)
    elif args.target == "dim_product":
        seed_dim_product(loaded_manifest)
    elif args.target == "dim_campaign_preview":
        preview_dim_campaign_rows(loaded_manifest)
    elif args.target == "dim_campaign":
        seed_dim_campaign(loaded_manifest)
    elif args.target == "dim_promotion_preview":
        preview_dim_promotion_rows(loaded_manifest)
    elif args.target == "dim_promotion":
        seed_dim_promotion(loaded_manifest)
    elif args.target == "dim_customer_preview":
        preview_dim_customer_rows(loaded_manifest)
    elif args.target == "dim_customer":
        seed_dim_customer(loaded_manifest)
    elif (args.target == "dim_membership_account_preview"):
        preview_dim_membership_account_rows(loaded_manifest)
    elif (args.target == "dim_membership_account"):
        seed_dim_membership_account(loaded_manifest)
    elif (args.target == "bridge_customer_membership_preview"):
        preview_bridge_customer_membership_rows(loaded_manifest)
    elif (args.target  == "bridge_customer_membership"):
        seed_bridge_customer_membership(loaded_manifest)
    elif (args.target == "membership_channel_binding_preview"):
        preview_membership_channel_binding_rows(loaded_manifest)
    elif (args.target == "membership_channel_binding"):
        seed_membership_channel_binding(loaded_manifest)