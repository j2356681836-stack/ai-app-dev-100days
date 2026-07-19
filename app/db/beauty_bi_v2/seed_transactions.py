from __future__ import annotations

import argparse
import bisect
import calendar
import hashlib
import math
import random
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_UP
from typing import Any, Iterable

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.db.beauty_bi_v2.manifest_loader import (
    get_active_scale_profile,
    load_and_validate_day65_manifest,
    parse_manifest_date,
    parse_manifest_time,
)
from app.db.database import engine


TARGET_FACT_TABLES = (
    "fact_marketing_spend",
    "fact_orders",
    "fact_order_items",
    "fact_refunds",
    "fact_reviews",
    "fact_membership_tier_history",
)


RNG_STREAM_NAMES = (
    "marketing_spend",
    "customer_profiles",
    "product_profiles",
    "daily_order_allocation",
    "order_lifecycle",
    "order_entities",
    "order_items",
    "fulfillment",
    "refunds",
    "reviews",
    "membership_tiers",
)


@dataclass(frozen=True)
class GenerationWindow:
    """
    Day65 交易生成使用的固定时间窗口。
    """

    business_start_date: date
    business_end_date: date
    observation_end_date: date
    tier_evaluation_time: time

    @property
    def business_day_count(self) -> int:
        return (
            self.business_end_date
            - self.business_start_date
        ).days + 1

    @property
    def observation_day_count(self) -> int:
        return (
            self.observation_end_date
            - self.business_start_date
        ).days + 1


@dataclass(frozen=True)
class ReferenceData:
    """
    Day64 已写入数据库、Day65 生成器需要读取的参考数据。

    这里同时保留数据库 ID 和稳定业务键。
    后续生成阶段优先使用稳定业务键表达关系，
    写入事实表时再解析数据库外键。
    """

    dates: tuple[dict[str, Any], ...]
    regions: tuple[dict[str, Any], ...]
    channels: tuple[dict[str, Any], ...]
    products: tuple[dict[str, Any], ...]
    campaigns: tuple[dict[str, Any], ...]
    promotions: tuple[dict[str, Any], ...]
    customers: tuple[dict[str, Any], ...]
    membership_accounts: tuple[dict[str, Any], ...]
    customer_membership_mappings: tuple[
        dict[str, Any],
        ...,
    ]
    membership_channel_bindings: tuple[
        dict[str, Any],
        ...,
    ]


def stable_stream_seed(
    base_seed: int,
    stream_name: str,
) -> int:
    """
    从 Manifest 主随机种子派生独立随机流种子。

    不能使用 Python 内置 hash()，因为它可能在不同进程
    之间变化。SHA-256 能保证同一输入稳定得到同一结果。
    """
    if (
        isinstance(base_seed, bool)
        or not isinstance(base_seed, int)
    ):
        raise ValueError(
            "generation.random_seed 必须是整数。"
        )

    if (
        not isinstance(stream_name, str)
        or not stream_name.strip()
    ):
        raise ValueError(
            "stream_name 必须是非空字符串。"
        )

    payload = (
        f"beauty_bi_v2:{base_seed}:"
        f"{stream_name.strip()}"
    ).encode("utf-8")

    digest = hashlib.sha256(payload).digest()

    return int.from_bytes(
        digest[:8],
        byteorder="big",
        signed=False,
    )


def build_rng(
    manifest: dict[str, Any],
    stream_name: str,
) -> random.Random:
    """
    创建局部、独立、可复现的随机源。

    每个事实主题使用独立随机流，避免某个模块增加一次随机
    抽样后，导致后续所有模块的数据整体漂移。
    """
    base_seed = manifest[
        "generation"
    ][
        "random_seed"
    ]

    return random.Random(
        stable_stream_seed(
            base_seed=base_seed,
            stream_name=stream_name,
        )
    )


def build_generation_window(
    manifest: dict[str, Any],
) -> GenerationWindow:
    generation = manifest["generation"]
    membership_policy = manifest[
        "membership_policy"
    ]

    window = GenerationWindow(
        business_start_date=parse_manifest_date(
            generation["business_start_date"],
            "generation.business_start_date",
        ),
        business_end_date=parse_manifest_date(
            generation["business_end_date"],
            "generation.business_end_date",
        ),
        observation_end_date=parse_manifest_date(
            generation[
                "event_observation_end_date"
            ],
            (
                "generation."
                "event_observation_end_date"
            ),
        ),
        tier_evaluation_time=parse_manifest_time(
            membership_policy[
                "evaluation_time"
            ],
            (
                "membership_policy."
                "evaluation_time"
            ),
        ),
    )

    if not (
        window.business_start_date
        <= window.business_end_date
        <= window.observation_end_date
    ):
        raise ValueError(
            "Day65 时间窗口不合法："
            "business_start_date "
            "<= business_end_date "
            "<= observation_end_date。"
        )

    return window


def _read_rows(
    connection: Connection,
    sql: str,
) -> tuple[dict[str, Any], ...]:
    return tuple(
        dict(row)
        for row in connection.execute(
            text(sql)
        ).mappings().all()
    )


def load_reference_data(
    connection: Connection,
) -> ReferenceData:
    """
    一次性读取 Day65 生成所需的 Day64 基线数据。

    本函数只读 beauty_bi_v2，不读取或修改 public schema。
    """
    dates = _read_rows(
        connection,
        """
        SELECT
            date_key,
            full_date,
            year,
            quarter,
            month,
            week_of_year,
            day_of_week,
            is_weekend,
            is_holiday,
            holiday_name
        FROM beauty_bi_v2.dim_date
        ORDER BY full_date
        """,
    )

    regions = _read_rows(
        connection,
        """
        SELECT
            region_id,
            region_code,
            region_name,
            province_name,
            region_group,
            city_tier
        FROM beauty_bi_v2.dim_region
        ORDER BY region_code
        """,
    )

    channels = _read_rows(
        connection,
        """
        SELECT
            channel_id,
            channel_code,
            channel_name,
            channel_type,
            is_sales_channel,
            is_marketing_channel,
            is_active
        FROM beauty_bi_v2.dim_channel
        ORDER BY channel_code
        """,
    )

    products = _read_rows(
        connection,
        """
        SELECT
            product_id,
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
        """,
    )

    campaigns = _read_rows(
        connection,
        """
        SELECT
            campaign_id,
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
        """,
    )

    promotions = _read_rows(
        connection,
        """
        SELECT
            promotion_id,
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
        """,
    )

    customers = _read_rows(
        connection,
        """
        SELECT
            customer.customer_id,
            customer.customer_code,
            customer.first_seen_date,
            customer.customer_status,
            region.region_id AS home_region_id,
            region.region_code AS home_region_code,
            region.region_group AS home_region_group,
            region.city_tier AS home_city_tier
        FROM beauty_bi_v2.dim_customer
            AS customer
        INNER JOIN beauty_bi_v2.dim_region
            AS region
            ON region.region_id =
                customer.home_region_id
        ORDER BY customer.customer_code
        """,
    )

    membership_accounts = _read_rows(
        connection,
        """
        SELECT
            account.membership_account_id,
            account.member_code,
            account.joined_at,
            account.membership_status,
            channel.channel_id
                AS join_channel_id,
            channel.channel_code
                AS join_channel_code
        FROM
            beauty_bi_v2.dim_membership_account
                AS account
        INNER JOIN beauty_bi_v2.dim_channel
            AS channel
            ON channel.channel_id =
                account.join_channel_id
        ORDER BY account.member_code
        """,
    )

    customer_membership_mappings = _read_rows(
        connection,
        """
        SELECT
            mapping.customer_membership_id,
            customer.customer_id,
            customer.customer_code,
            account.membership_account_id,
            account.member_code,
            mapping.effective_from_ts,
            mapping.effective_to_ts,
            mapping.mapping_status
        FROM
            beauty_bi_v2.bridge_customer_membership
                AS mapping
        INNER JOIN beauty_bi_v2.dim_customer
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
            mapping.effective_from_ts
        """,
    )

    membership_channel_bindings = _read_rows(
        connection,
        """
        SELECT
            binding.binding_history_id,
            account.membership_account_id,
            account.member_code,
            channel.channel_id,
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
        INNER JOIN beauty_bi_v2.dim_channel
            AS channel
            ON channel.channel_id =
                binding.channel_id
        ORDER BY
            account.member_code,
            channel.channel_code,
            binding.effective_from_ts
        """,
    )

    return ReferenceData(
        dates=dates,
        regions=regions,
        channels=channels,
        products=products,
        campaigns=campaigns,
        promotions=promotions,
        customers=customers,
        membership_accounts=membership_accounts,
        customer_membership_mappings=(
            customer_membership_mappings
        ),
        membership_channel_bindings=(
            membership_channel_bindings
        ),
    )


def _validate_unique_values(
    rows: Iterable[dict[str, Any]],
    field_name: str,
    dataset_name: str,
) -> None:
    values = [
        row[field_name]
        for row in rows
    ]

    if len(values) != len(set(values)):
        raise RuntimeError(
            f"{dataset_name} 存在重复 "
            f"{field_name}。"
        )


def _validate_exact_count(
    actual_count: int,
    expected_count: int,
    dataset_name: str,
) -> None:
    if actual_count != expected_count:
        raise RuntimeError(
            f"{dataset_name} 行数不正确："
            f"expected={expected_count}, "
            f"actual={actual_count}"
        )


def validate_reference_data(
    reference_data: ReferenceData,
    manifest: dict[str, Any],
    window: GenerationWindow,
) -> None:
    """
    验证 Day64 数据库基线是否足以支持 Day65 交易生成。
    """
    _, profile = get_active_scale_profile(
        manifest
    )

    _validate_exact_count(
        len(reference_data.dates),
        window.observation_day_count,
        "dim_date",
    )

    _validate_exact_count(
        len(reference_data.regions),
        len(
            manifest[
                "fixed_dimensions"
            ][
                "regions"
            ]
        ),
        "dim_region",
    )

    _validate_exact_count(
        len(reference_data.channels),
        len(
            manifest[
                "fixed_dimensions"
            ][
                "channels"
            ]
        ),
        "dim_channel",
    )

    _validate_exact_count(
        len(reference_data.products),
        profile["products"],
        "dim_product",
    )

    _validate_exact_count(
        len(reference_data.campaigns),
        len(
            manifest[
                "business_calendar"
            ][
                "campaigns"
            ]
        ),
        "dim_campaign",
    )

    _validate_exact_count(
        len(reference_data.promotions),
        len(
            manifest[
                "fixed_dimensions"
            ][
                "promotions"
            ]
        ),
        "dim_promotion",
    )

    _validate_exact_count(
        len(reference_data.customers),
        profile["customers"],
        "dim_customer",
    )

    _validate_exact_count(
        len(
            reference_data.membership_accounts
        ),
        profile["membership_accounts"],
        "dim_membership_account",
    )

    mapped_customer_ratio = manifest[
        "business_patterns"
    ][
        "P03_membership_customer_overlap"
    ][
        "parameters"
    ][
        "mapped_customer_ratio"
    ]

    expected_mapping_count = round(
        profile["customers"]
        * mapped_customer_ratio
    )

    _validate_exact_count(
        len(
            reference_data.
            customer_membership_mappings
        ),
        expected_mapping_count,
        "bridge_customer_membership",
    )

    if not reference_data.dates:
        raise RuntimeError(
            "dim_date 不能为空。"
        )

    if (
        reference_data.dates[0][
            "full_date"
        ]
        != window.business_start_date
    ):
        raise RuntimeError(
            "dim_date 起始日期不正确："
            f"expected="
            f"{window.business_start_date}, "
            "actual="
            f"{reference_data.dates[0]['full_date']}"
        )

    if (
        reference_data.dates[-1][
            "full_date"
        ]
        != window.observation_end_date
    ):
        raise RuntimeError(
            "dim_date 结束日期不正确："
            f"expected="
            f"{window.observation_end_date}, "
            "actual="
            f"{reference_data.dates[-1]['full_date']}"
        )

    expected_dates = [
        window.business_start_date
        + timedelta(days=offset)
        for offset in range(
            window.observation_day_count
        )
    ]

    actual_dates = [
        row["full_date"]
        for row in reference_data.dates
    ]

    if actual_dates != expected_dates:
        raise RuntimeError(
            "dim_date 日期序列不连续。"
        )

    _validate_unique_values(
        reference_data.regions,
        "region_code",
        "dim_region",
    )

    _validate_unique_values(
        reference_data.channels,
        "channel_code",
        "dim_channel",
    )

    _validate_unique_values(
        reference_data.products,
        "sku_code",
        "dim_product",
    )

    _validate_unique_values(
        reference_data.campaigns,
        "campaign_code",
        "dim_campaign",
    )

    _validate_unique_values(
        reference_data.promotions,
        "promotion_code",
        "dim_promotion",
    )

    _validate_unique_values(
        reference_data.customers,
        "customer_code",
        "dim_customer",
    )

    _validate_unique_values(
        reference_data.membership_accounts,
        "member_code",
        "dim_membership_account",
    )

    active_sales_channels = [
        row
        for row in reference_data.channels
        if (
            row["is_active"]
            and row["is_sales_channel"]
        )
    ]

    active_marketing_channels = [
        row
        for row in reference_data.channels
        if (
            row["is_active"]
            and row["is_marketing_channel"]
        )
    ]

    if not active_sales_channels:
        raise RuntimeError(
            "数据库中没有启用的销售渠道。"
        )

    if not active_marketing_channels:
        raise RuntimeError(
            "数据库中没有启用的营销渠道。"
        )

    active_products = [
        row
        for row in reference_data.products
        if row["is_active"]
    ]

    if not active_products:
        raise RuntimeError(
            "数据库中没有启用的商品。"
        )

    always_on_campaigns = [
        row
        for row in reference_data.campaigns
        if (
            row["is_active"]
            and row["campaign_type"]
                == "always_on"
        )
    ]

    if not always_on_campaigns:
        raise RuntimeError(
            "数据库中没有启用的 "
            "always_on Campaign。"
        )

    current_date = window.business_start_date

    while current_date <= window.business_end_date:
        matched_campaigns = [
            row
            for row in always_on_campaigns
            if (
                row["start_date"]
                <= current_date
                <= row["end_date"]
            )
        ]

        if len(matched_campaigns) != 1:
            raise RuntimeError(
                "业务日期必须且只能命中一个 "
                "always_on Campaign："
                f"date={current_date}, "
                f"matched="
                f"{[row['campaign_code'] for row in matched_campaigns]}"
            )

        current_date += timedelta(days=1)

    open_mappings = [
        row
        for row in (
            reference_data.
            customer_membership_mappings
        )
        if row["effective_to_ts"] is None
    ]

    if len(open_mappings) != len(
        reference_data.
        customer_membership_mappings
    ):
        raise RuntimeError(
            "Day65 当前只支持 Day64 生成的"
            "开放 customer-membership 映射。"
        )

    mapped_customer_codes = [
        row["customer_code"]
        for row in open_mappings
    ]

    mapped_member_codes = [
        row["member_code"]
        for row in open_mappings
    ]

    if (
        len(set(mapped_customer_codes))
        != len(mapped_customer_codes)
    ):
        raise RuntimeError(
            "开放身份映射中一个客户"
            "对应多个会员账户。"
        )

    if (
        len(set(mapped_member_codes))
        != len(mapped_member_codes)
    ):
        raise RuntimeError(
            "开放身份映射中一个会员账户"
            "对应多个客户。"
        )

    binding_member_codes = {
        row["member_code"]
        for row in (
            reference_data.
            membership_channel_bindings
        )
    }

    expected_member_codes = {
        row["member_code"]
        for row in (
            reference_data.
            membership_accounts
        )
    }

    if binding_member_codes != expected_member_codes:
        raise RuntimeError(
            "会员渠道绑定历史未完整覆盖"
            "全部会员账户："
            "missing="
            f"{sorted(expected_member_codes - binding_member_codes)}, "
            "unknown="
            f"{sorted(binding_member_codes - expected_member_codes)}"
        )

    binding_pairs = [
        (
            row["member_code"],
            row["channel_code"],
        )
        for row in (
            reference_data.
            membership_channel_bindings
        )
    ]

    if len(binding_pairs) != len(
        set(binding_pairs)
    ):
        raise RuntimeError(
            "Day64 渠道绑定历史中存在重复的"
            "会员—渠道初始组合。"
        )

    # 验证不同业务主题的随机流相互独立，
    # 同时同一主题重复派生结果保持一致。
    derived_seeds = [
        stable_stream_seed(
            manifest["generation"]["random_seed"],
            stream_name,
        )
        for stream_name in RNG_STREAM_NAMES
    ]

    if len(derived_seeds) != len(
        set(derived_seeds)
    ):
        raise RuntimeError(
            "Day65 随机流派生种子发生碰撞。"
        )

    first_rng = build_rng(
        manifest,
        RNG_STREAM_NAMES[0],
    )

    repeated_rng = build_rng(
        manifest,
        RNG_STREAM_NAMES[0],
    )

    first_values = [
        first_rng.random()
        for _ in range(5)
    ]

    repeated_values = [
        repeated_rng.random()
        for _ in range(5)
    ]

    if first_values != repeated_values:
        raise RuntimeError(
            "Day65 局部随机流确定性校验失败。"
        )


def get_target_table_counts(
    connection: Connection,
) -> dict[str, int]:
    counts: dict[str, int] = {}

    for table_name in TARGET_FACT_TABLES:
        counts[table_name] = (
            connection.execute(
                text(
                    "SELECT COUNT(*) "
                    f"FROM beauty_bi_v2.{table_name}"
                )
            ).scalar_one()
        )

    return counts


def assert_target_tables_empty(
    connection: Connection,
) -> dict[str, int]:
    """
    Day65 第一次写入前，六张目标事实表必须全部为空。

    当前模块不执行自动清表，防止误删已生成结果。
    """
    counts = get_target_table_counts(
        connection
    )

    nonempty_tables = {
        table_name: row_count
        for table_name, row_count
        in counts.items()
        if row_count != 0
    }

    if nonempty_tables:
        raise RuntimeError(
            "Day65 目标事实表不是全空，"
            "为避免覆盖数据，Preflight 已停止："
            f"{nonempty_tables}"
        )

    return counts


def run_preflight(
    manifest: dict[str, Any],
) -> None:
    """
    Day65 交易生成的第一道真实数据库检查。

    本步骤只读数据库，不生成、不插入、不清理任何数据。
    """
    window = build_generation_window(
        manifest
    )

    with engine.connect() as connection:
        reference_data = load_reference_data(
            connection
        )

        validate_reference_data(
            reference_data=reference_data,
            manifest=manifest,
            window=window,
        )

        target_counts = (
            assert_target_tables_empty(
                connection
            )
        )

    active_sales_channel_count = sum(
        row["is_active"]
        and row["is_sales_channel"]
        for row in reference_data.channels
    )

    active_marketing_channel_count = sum(
        row["is_active"]
        and row["is_marketing_channel"]
        for row in reference_data.channels
    )

    active_product_count = sum(
        row["is_active"]
        for row in reference_data.products
    )

    print(
        "Beauty BI V2 transaction "
        "preflight passed."
    )
    print(
        "Business window: "
        f"{window.business_start_date} -> "
        f"{window.business_end_date}"
    )
    print(
        "Observation window end: "
        f"{window.observation_end_date}"
    )
    print(
        "Tier evaluation time: "
        f"{window.tier_evaluation_time}"
    )
    print(
        "Reference row counts: "
        f"dates={len(reference_data.dates)}, "
        f"regions={len(reference_data.regions)}, "
        f"channels={len(reference_data.channels)}, "
        f"products={len(reference_data.products)}, "
        f"campaigns={len(reference_data.campaigns)}, "
        f"promotions={len(reference_data.promotions)}, "
        f"customers={len(reference_data.customers)}, "
        "membership_accounts="
        f"{len(reference_data.membership_accounts)}, "
        "identity_mappings="
        f"{len(reference_data.customer_membership_mappings)}, "
        "channel_bindings="
        f"{len(reference_data.membership_channel_bindings)}"
    )
    print(
        "Active generation entities: "
        f"sales_channels="
        f"{active_sales_channel_count}, "
        f"marketing_channels="
        f"{active_marketing_channel_count}, "
        f"products={active_product_count}"
    )
    print(
        "Target fact table counts: "
        f"{target_counts}"
    )
    print(
        "Schema isolation: beauty_bi_v2 only."
    )
    print(
        "Deterministic RNG stream check: passed."
    )



WEEKDAY_CONFIG_KEYS = {
    1: "monday",
    2: "tuesday",
    3: "wednesday",
    4: "thursday",
    5: "friday",
    6: "saturday",
    7: "sunday",
}


def quantize_money(
    value: Decimal,
) -> Decimal:
    """
    将金额统一为 NUMERIC(..., 2) 对应的两位小数。
    """
    return value.quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )


def build_marketing_spend_rows(
    manifest: dict[str, Any],
    reference_data: ReferenceData,
    window: GenerationWindow,
) -> list[dict[str, Any]]:
    """
    按 Manifest 生成 fact_marketing_spend 暂存行。

    暂存行使用稳定业务键：
    - channel_code
    - campaign_code

    正式写库时再解析 channel_id 和 campaign_id。
    """
    config = manifest[
        "marketing_spend_generation"
    ]

    active_marketing_channels = sorted(
        (
            row
            for row in reference_data.channels
            if (
                row["is_active"]
                and row["is_marketing_channel"]
            )
        ),
        key=lambda row: row["channel_code"],
    )

    active_campaigns = sorted(
        (
            row
            for row in reference_data.campaigns
            if row["is_active"]
        ),
        key=lambda row: row["campaign_code"],
    )

    always_on_campaigns = [
        row
        for row in active_campaigns
        if row["campaign_type"] == "always_on"
    ]

    major_campaigns = [
        row
        for row in active_campaigns
        if row["campaign_type"]
            == "major_promotion"
    ]

    date_lookup = {
        row["full_date"]: row
        for row in reference_data.dates
    }

    base_spend = {
        channel_code: Decimal(str(value))
        for channel_code, value
        in config[
            "base_daily_spend_by_channel"
        ].items()
    }

    annual_multiplier = {
        int(year): Decimal(str(value))
        for year, value
        in config[
            "annual_multiplier"
        ].items()
    }

    weekday_multiplier = {
        weekday_name: Decimal(str(value))
        for weekday_name, value
        in config[
            "weekday_multiplier"
        ].items()
    }

    holiday_multiplier = Decimal(
        str(config["holiday_multiplier"])
    )

    campaign_incremental_multiplier = {
        family: Decimal(str(value))
        for family, value
        in config[
            "campaign_incremental_multiplier"
        ].items()
    }

    noise_config = config[
        "deterministic_noise"
    ]

    noise_minimum = Decimal(
        str(noise_config["minimum_multiplier"])
    )

    noise_maximum = Decimal(
        str(noise_config["maximum_multiplier"])
    )

    always_on_component = Decimal(
        str(
            config[
                "amount"
            ][
                "always_on_campaign_component"
            ]
        )
    )

    minimum_spend_amount = Decimal(
        str(
            config[
                "amount"
            ][
                "minimum_spend_amount"
            ]
        )
    )

    rng = build_rng(
        manifest,
        "marketing_spend",
    )

    rows: list[dict[str, Any]] = []

    current_date = window.business_start_date

    while current_date <= window.business_end_date:
        date_row = date_lookup.get(
            current_date
        )

        if date_row is None:
            raise ValueError(
                "营销费用生成缺少 dim_date："
                f"{current_date}"
            )

        matched_always_on = [
            campaign
            for campaign in always_on_campaigns
            if (
                campaign["start_date"]
                <= current_date
                <= campaign["end_date"]
            )
        ]

        if len(matched_always_on) != 1:
            raise ValueError(
                "营销费用日期必须且只能命中一个 "
                "always_on Campaign："
                f"date={current_date}, "
                f"matched="
                f"{[row['campaign_code'] for row in matched_always_on]}"
            )

        matched_major_campaigns = [
            campaign
            for campaign in major_campaigns
            if (
                campaign["start_date"]
                <= current_date
                <= campaign["end_date"]
            )
        ]

        daily_campaigns = (
            matched_always_on
            + matched_major_campaigns
        )

        weekday_name = WEEKDAY_CONFIG_KEYS[
            current_date.isoweekday()
        ]

        date_holiday_multiplier = (
            holiday_multiplier
            if date_row["is_holiday"]
            else Decimal("1")
        )

        for channel in active_marketing_channels:
            channel_code = channel[
                "channel_code"
            ]

            for campaign in daily_campaigns:
                if (
                    campaign["campaign_type"]
                    == "always_on"
                ):
                    campaign_component = (
                        always_on_component
                    )
                else:
                    campaign_family = campaign[
                        "campaign_family"
                    ]

                    campaign_component = (
                        Decimal("1")
                        + (
                            campaign_incremental_multiplier[
                                campaign_family
                            ]
                        )
                    )

                noise_float = rng.uniform(
                    float(noise_minimum),
                    float(noise_maximum),
                )

                noise_multiplier = Decimal(
                    str(noise_float)
                )

                raw_amount = (
                    base_spend[channel_code]
                    * annual_multiplier[
                        current_date.year
                    ]
                    * weekday_multiplier[
                        weekday_name
                    ]
                    * date_holiday_multiplier
                    * campaign_component
                    * noise_multiplier
                )

                spend_amount = max(
                    quantize_money(raw_amount),
                    quantize_money(
                        minimum_spend_amount
                    ),
                )

                rows.append(
                    {
                        "spend_date": current_date,
                        "channel_code": (
                            channel_code
                        ),
                        "campaign_code": (
                            campaign[
                                "campaign_code"
                            ]
                        ),
                        "spend_amount": (
                            spend_amount
                        ),
                    }
                )

        current_date += timedelta(days=1)

    return rows


def build_expected_marketing_spend_grains(
    reference_data: ReferenceData,
    window: GenerationWindow,
) -> set[tuple[date, str, str]]:
    """
    根据数据库中的启用渠道和活动窗口，
    构造营销费用应出现的完整 Grain 集合。
    """
    channel_codes = sorted(
        row["channel_code"]
        for row in reference_data.channels
        if (
            row["is_active"]
            and row["is_marketing_channel"]
        )
    )

    campaigns = [
        row
        for row in reference_data.campaigns
        if row["is_active"]
    ]

    expected_grains: set[
        tuple[date, str, str]
    ] = set()

    current_date = window.business_start_date

    while current_date <= window.business_end_date:
        active_campaign_codes = sorted(
            row["campaign_code"]
            for row in campaigns
            if (
                row["start_date"]
                <= current_date
                <= row["end_date"]
            )
        )

        for channel_code in channel_codes:
            for campaign_code in (
                active_campaign_codes
            ):
                expected_grains.add(
                    (
                        current_date,
                        channel_code,
                        campaign_code,
                    )
                )

        current_date += timedelta(days=1)

    return expected_grains


def validate_marketing_spend_rows(
    rows: list[dict[str, Any]],
    manifest: dict[str, Any],
    reference_data: ReferenceData,
    window: GenerationWindow,
) -> None:
    """
    写库前校验营销费用暂存行。
    """
    if not rows:
        raise ValueError(
            "fact_marketing_spend "
            "生成结果不能为空。"
        )

    required_fields = {
        "spend_date",
        "channel_code",
        "campaign_code",
        "spend_amount",
    }

    valid_channels = {
        row["channel_code"]: row
        for row in reference_data.channels
        if (
            row["is_active"]
            and row["is_marketing_channel"]
        )
    }

    valid_campaigns = {
        row["campaign_code"]: row
        for row in reference_data.campaigns
        if row["is_active"]
    }

    actual_grains: set[
        tuple[date, str, str]
    ] = set()

    always_on_counts_by_date: Counter[
        date
    ] = Counter()

    major_counts_by_date: Counter[
        date
    ] = Counter()

    for index, row in enumerate(rows):
        if set(row.keys()) != required_fields:
            raise ValueError(
                "fact_marketing_spend "
                f"第 {index} 行字段不正确："
                f"{sorted(row.keys())}"
            )

        spend_date = row["spend_date"]

        if (
            not isinstance(spend_date, date)
            or not (
                window.business_start_date
                <= spend_date
                <= window.business_end_date
            )
        ):
            raise ValueError(
                "fact_marketing_spend "
                f"第 {index} 行 spend_date "
                "超出业务窗口："
                f"{spend_date!r}"
            )

        channel_code = row[
            "channel_code"
        ]

        if channel_code not in valid_channels:
            raise ValueError(
                "fact_marketing_spend "
                f"第 {index} 行引用了"
                "非启用营销渠道："
                f"{channel_code!r}"
            )

        campaign_code = row[
            "campaign_code"
        ]

        if campaign_code not in valid_campaigns:
            raise ValueError(
                "fact_marketing_spend "
                f"第 {index} 行引用了"
                "非启用 Campaign："
                f"{campaign_code!r}"
            )

        campaign = valid_campaigns[
            campaign_code
        ]

        if not (
            campaign["start_date"]
            <= spend_date
            <= campaign["end_date"]
        ):
            raise ValueError(
                "营销费用日期超出 Campaign "
                "有效窗口："
                f"index={index}, "
                f"date={spend_date}, "
                f"campaign={campaign_code}"
            )

        spend_amount = row[
            "spend_amount"
        ]

        if (
            isinstance(spend_amount, bool)
            or not isinstance(
                spend_amount,
                Decimal,
            )
            or spend_amount <= 0
        ):
            raise ValueError(
                "fact_marketing_spend "
                f"第 {index} 行 spend_amount "
                "必须是正 Decimal。"
            )

        if spend_amount != quantize_money(
            spend_amount
        ):
            raise ValueError(
                "fact_marketing_spend "
                f"第 {index} 行 spend_amount "
                "必须保留两位小数："
                f"{spend_amount}"
            )

        grain = (
            spend_date,
            channel_code,
            campaign_code,
        )

        if grain in actual_grains:
            raise ValueError(
                "fact_marketing_spend "
                "存在重复 Grain："
                f"{grain}"
            )

        actual_grains.add(grain)

        if (
            campaign["campaign_type"]
            == "always_on"
        ):
            always_on_counts_by_date[
                spend_date
            ] += 1
        elif (
            campaign["campaign_type"]
            == "major_promotion"
        ):
            major_counts_by_date[
                spend_date
            ] += 1

    expected_grains = (
        build_expected_marketing_spend_grains(
            reference_data=reference_data,
            window=window,
        )
    )

    if actual_grains != expected_grains:
        missing_grains = sorted(
            expected_grains - actual_grains
        )

        unexpected_grains = sorted(
            actual_grains - expected_grains
        )

        raise ValueError(
            "fact_marketing_spend Grain "
            "集合不完整："
            f"missing={missing_grains[:10]}, "
            f"unexpected="
            f"{unexpected_grains[:10]}"
        )

    marketing_channel_count = len(
        valid_channels
    )

    current_date = window.business_start_date

    while current_date <= window.business_end_date:
        if (
            always_on_counts_by_date[
                current_date
            ]
            != marketing_channel_count
        ):
            raise ValueError(
                "每个业务日期必须为每个营销渠道"
                "生成一条 always_on 费用："
                f"date={current_date}, "
                "expected="
                f"{marketing_channel_count}, "
                "actual="
                f"{always_on_counts_by_date[current_date]}"
            )

        current_date += timedelta(days=1)

    repeated_rows = build_marketing_spend_rows(
        manifest=manifest,
        reference_data=reference_data,
        window=window,
    )

    comparison_key = lambda row: (
        row["spend_date"],
        row["channel_code"],
        row["campaign_code"],
    )

    actual_rows = sorted(
        rows,
        key=comparison_key,
    )

    expected_rows = sorted(
        repeated_rows,
        key=comparison_key,
    )

    if actual_rows != expected_rows:
        for expected_row, actual_row in zip(
            expected_rows,
            actual_rows,
            strict=True,
        ):
            if expected_row != actual_row:
                raise ValueError(
                    "fact_marketing_spend "
                    "数据库内容与确定性生成结果"
                    "不一致："
                    f"expected={expected_row}, "
                    f"actual={actual_row}"
                )

        raise ValueError(
            "fact_marketing_spend "
            "数据库内容与确定性生成结果"
            "不一致。"
        )


def build_daily_channel_demand_multipliers(
    rows: list[dict[str, Any]],
    manifest: dict[str, Any],
) -> dict[tuple[date, str], Decimal]:
    """
    根据每日渠道营销费用计算订单生成阶段使用的需求乘数。

    该乘数不写入数据库，只在后续订单权重计算中消费。
    """
    config = manifest[
        "marketing_spend_generation"
    ]

    response = config[
        "demand_response"
    ]

    base_spend = {
        channel_code: Decimal(str(value))
        for channel_code, value
        in config[
            "base_daily_spend_by_channel"
        ].items()
    }

    response_strength = {
        channel_code: Decimal(str(value))
        for channel_code, value
        in response[
            "response_strength_by_channel"
        ].items()
    }

    minimum_multiplier = Decimal(
        str(
            response[
                "minimum_demand_multiplier"
            ]
        )
    )

    maximum_multiplier = Decimal(
        str(
            response[
                "maximum_demand_multiplier"
            ]
        )
    )

    totals: defaultdict[
        tuple[date, str],
        Decimal,
    ] = defaultdict(
        lambda: Decimal("0")
    )

    for row in rows:
        totals[
            (
                row["spend_date"],
                row["channel_code"],
            )
        ] += row["spend_amount"]

    multipliers: dict[
        tuple[date, str],
        Decimal,
    ] = {}

    for grain, total_spend in totals.items():
        _, channel_code = grain

        baseline = base_spend[
            channel_code
        ]

        excess_ratio = max(
            (
                total_spend
                / baseline
                - Decimal("1")
            ),
            Decimal("0"),
        )

        raw_multiplier = (
            Decimal("1")
            + response_strength[channel_code]
            * Decimal(
                str(
                    math.log1p(
                        float(excess_ratio)
                    )
                )
            )
        )

        bounded_multiplier = min(
            max(
                raw_multiplier,
                minimum_multiplier,
            ),
            maximum_multiplier,
        )

        multipliers[grain] = (
            bounded_multiplier.quantize(
                Decimal("0.000001"),
                rounding=ROUND_HALF_UP,
            )
        )

    return multipliers


def preview_marketing_spend(
    manifest: dict[str, Any],
) -> None:
    window = build_generation_window(
        manifest
    )

    with engine.connect() as connection:
        reference_data = load_reference_data(
            connection
        )

        validate_reference_data(
            reference_data=reference_data,
            manifest=manifest,
            window=window,
        )

        existing_count = connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM beauty_bi_v2.
                    fact_marketing_spend
                """
            )
        ).scalar_one()

        if existing_count != 0:
            raise RuntimeError(
                "fact_marketing_spend 已存在数据，"
                "无法执行空表 Preview："
                f"existing_count={existing_count}"
            )

    rows = build_marketing_spend_rows(
        manifest=manifest,
        reference_data=reference_data,
        window=window,
    )

    validate_marketing_spend_rows(
        rows=rows,
        manifest=manifest,
        reference_data=reference_data,
        window=window,
    )

    demand_multipliers = (
        build_daily_channel_demand_multipliers(
            rows=rows,
            manifest=manifest,
        )
    )

    campaign_type_lookup = {
        row["campaign_code"]:
            row["campaign_type"]
        for row in reference_data.campaigns
    }

    type_counts = Counter(
        campaign_type_lookup[
            row["campaign_code"]
        ]
        for row in rows
    )

    channel_counts = Counter(
        row["channel_code"]
        for row in rows
    )

    channel_spend = defaultdict(
        lambda: Decimal("0")
    )

    for row in rows:
        channel_spend[
            row["channel_code"]
        ] += row["spend_amount"]

    multiplier_values = list(
        demand_multipliers.values()
    )

    print(
        "fact_marketing_spend "
        "row preview passed."
    )
    print(f"Total rows: {len(rows)}")
    print(
        "Campaign type counts: "
        f"{dict(type_counts)}"
    )
    print(
        "Channel row counts: "
        f"{dict(channel_counts)}"
    )
    print(
        "Channel spend totals: "
        f"{dict(channel_spend)}"
    )
    print(
        "Spend date range: "
        f"{rows[0]['spend_date']} -> "
        f"{rows[-1]['spend_date']}"
    )
    print(
        "Demand multiplier range: "
        f"{min(multiplier_values)} -> "
        f"{max(multiplier_values)}"
    )
    print(f"First row: {rows[0]}")
    print(f"Last row: {rows[-1]}")
    print(
        "Observation-tail spend rows: 0"
    )
    print("Deterministic check: passed.")


def insert_marketing_spend_rows(
    rows: list[dict[str, Any]],
    window: GenerationWindow,
) -> None:
    """
    将营销费用写入 PostgreSQL。

    生成阶段使用 channel_code / campaign_code；
    写库阶段在同一事务中解析数据库外键。
    """
    if not rows:
        raise ValueError(
            "不能插入空的营销费用数据。"
        )

    insert_sql = text(
        """
        INSERT INTO
            beauty_bi_v2.fact_marketing_spend (
                spend_date,
                channel_id,
                campaign_id,
                spend_amount
            )
        VALUES (
            :spend_date,
            :channel_id,
            :campaign_id,
            :spend_amount
        )
        """
    )

    select_sql = text(
        """
        SELECT
            spend.spend_date,
            channel.channel_code,
            campaign.campaign_code,
            spend.spend_amount
        FROM
            beauty_bi_v2.fact_marketing_spend
                AS spend
        INNER JOIN beauty_bi_v2.dim_channel
            AS channel
            ON channel.channel_id =
                spend.channel_id
        INNER JOIN beauty_bi_v2.dim_campaign
            AS campaign
            ON campaign.campaign_id =
                spend.campaign_id
        ORDER BY
            spend.spend_date,
            channel.channel_code,
            campaign.campaign_code
        """
    )

    with engine.begin() as connection:
        existing_count = connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM beauty_bi_v2.
                    fact_marketing_spend
                """
            )
        ).scalar_one()

        if existing_count != 0:
            raise RuntimeError(
                "beauty_bi_v2."
                "fact_marketing_spend "
                "已存在数据，为避免重复写入，"
                "本次 Seed 已停止。"
                f" existing_count={existing_count}"
            )

        channel_records = _read_rows(
            connection,
            """
            SELECT
                channel_id,
                channel_code,
                is_marketing_channel,
                is_active
            FROM beauty_bi_v2.dim_channel
            ORDER BY channel_code
            """,
        )

        campaign_records = _read_rows(
            connection,
            """
            SELECT
                campaign_id,
                campaign_code,
                campaign_type,
                start_date,
                end_date,
                is_active
            FROM beauty_bi_v2.dim_campaign
            ORDER BY campaign_code
            """,
        )

        channel_lookup = {
            row["channel_code"]: row
            for row in channel_records
        }

        campaign_lookup = {
            row["campaign_code"]: row
            for row in campaign_records
        }

        database_insert_rows: list[
            dict[str, Any]
        ] = []

        for row in rows:
            channel = channel_lookup.get(
                row["channel_code"]
            )

            if (
                channel is None
                or not channel[
                    "is_marketing_channel"
                ]
                or not channel["is_active"]
            ):
                raise RuntimeError(
                    "营销费用无法解析为"
                    "启用营销渠道："
                    f"{row['channel_code']}"
                )

            campaign = campaign_lookup.get(
                row["campaign_code"]
            )

            if (
                campaign is None
                or not campaign["is_active"]
            ):
                raise RuntimeError(
                    "营销费用无法解析为"
                    "启用 Campaign："
                    f"{row['campaign_code']}"
                )

            if not (
                campaign["start_date"]
                <= row["spend_date"]
                <= campaign["end_date"]
            ):
                raise RuntimeError(
                    "营销费用日期超出"
                    "数据库 Campaign 窗口："
                    f"{row}"
                )

            database_insert_rows.append(
                {
                    "spend_date": row[
                        "spend_date"
                    ],
                    "channel_id": channel[
                        "channel_id"
                    ],
                    "campaign_id": campaign[
                        "campaign_id"
                    ],
                    "spend_amount": row[
                        "spend_amount"
                    ],
                }
            )

        connection.execute(
            insert_sql,
            database_insert_rows,
        )

        (
            actual_count,
            distinct_grain_count,
            distinct_channel_count,
            distinct_campaign_count,
            min_spend_date,
            max_spend_date,
            min_spend_amount,
            max_spend_amount,
            total_spend_amount,
        ) = connection.execute(
            text(
                """
                SELECT
                    COUNT(*),
                    COUNT(
                        DISTINCT (
                            spend_date,
                            channel_id,
                            campaign_id
                        )
                    ),
                    COUNT(DISTINCT channel_id),
                    COUNT(DISTINCT campaign_id),
                    MIN(spend_date),
                    MAX(spend_date),
                    MIN(spend_amount),
                    MAX(spend_amount),
                    SUM(spend_amount)
                FROM
                    beauty_bi_v2.
                    fact_marketing_spend
                """
            )
        ).one()

        if actual_count != len(rows):
            raise RuntimeError(
                "fact_marketing_spend "
                "插入后的行数不正确："
                f"expected={len(rows)}, "
                f"actual={actual_count}"
            )

        if distinct_grain_count != actual_count:
            raise RuntimeError(
                "fact_marketing_spend "
                "数据库中存在重复 Grain。"
            )

        invalid_channel_count = (
            connection.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM
                        beauty_bi_v2.
                        fact_marketing_spend
                            AS spend
                    INNER JOIN
                        beauty_bi_v2.dim_channel
                            AS channel
                        ON channel.channel_id =
                            spend.channel_id
                    WHERE
                        NOT channel.
                            is_marketing_channel
                        OR NOT channel.is_active
                    """
                )
            ).scalar_one()
        )

        if invalid_channel_count != 0:
            raise RuntimeError(
                "数据库营销费用中存在"
                "非启用营销渠道："
                f"invalid_count="
                f"{invalid_channel_count}"
            )

        invalid_campaign_date_count = (
            connection.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM
                        beauty_bi_v2.
                        fact_marketing_spend
                            AS spend
                    INNER JOIN
                        beauty_bi_v2.dim_campaign
                            AS campaign
                        ON campaign.campaign_id =
                            spend.campaign_id
                    WHERE
                        NOT campaign.is_active
                        OR spend.spend_date
                            < campaign.start_date
                        OR spend.spend_date
                            > campaign.end_date
                    """
                )
            ).scalar_one()
        )

        if invalid_campaign_date_count != 0:
            raise RuntimeError(
                "数据库营销费用中存在"
                "无效 Campaign 日期："
                f"invalid_count="
                f"{invalid_campaign_date_count}"
            )

        observation_tail_count = (
            connection.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM
                        beauty_bi_v2.
                        fact_marketing_spend
                    WHERE spend_date
                        > :business_end_date
                    """
                ),
                {
                    "business_end_date":
                        window.business_end_date,
                },
            ).scalar_one()
        )

        if observation_tail_count != 0:
            raise RuntimeError(
                "2026-01 观察尾窗中"
                "不应存在营销费用："
                f"actual={observation_tail_count}"
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
                row["spend_date"],
                row["channel_code"],
                row["campaign_code"],
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
                        "fact_marketing_spend "
                        "数据库结果与生成结果"
                        "不一致："
                        f"expected={expected_row}, "
                        f"actual={actual_row}"
                    )

            raise RuntimeError(
                "fact_marketing_spend "
                "数据库结果与生成结果不一致。"
            )

    print(
        "fact_marketing_spend "
        "database seed passed."
    )
    print(f"Inserted rows: {actual_count}")
    print(
        "Distinct channels: "
        f"{distinct_channel_count}"
    )
    print(
        "Distinct campaigns: "
        f"{distinct_campaign_count}"
    )
    print(
        "Spend date range: "
        f"{min_spend_date} -> "
        f"{max_spend_date}"
    )
    print(
        "Spend amount range: "
        f"{min_spend_amount} -> "
        f"{max_spend_amount}"
    )
    print(
        "Total spend amount: "
        f"{total_spend_amount}"
    )
    print(
        "Observation-tail spend check: passed."
    )
    print(
        "Channel foreign-key resolution: passed."
    )
    print(
        "Campaign foreign-key resolution: passed."
    )
    print("Database row comparison: passed.")


def seed_marketing_spend(
    manifest: dict[str, Any],
) -> None:
    window = build_generation_window(
        manifest
    )

    with engine.connect() as connection:
        reference_data = load_reference_data(
            connection
        )

        validate_reference_data(
            reference_data=reference_data,
            manifest=manifest,
            window=window,
        )

    rows = build_marketing_spend_rows(
        manifest=manifest,
        reference_data=reference_data,
        window=window,
    )

    validate_marketing_spend_rows(
        rows=rows,
        manifest=manifest,
        reference_data=reference_data,
        window=window,
    )

    print(
        "fact_marketing_spend "
        "generation passed."
    )
    print(f"Total rows: {len(rows)}")
    print(f"First row: {rows[0]}")
    print(f"Last row: {rows[-1]}")
    print("Deterministic check: passed.")

    insert_marketing_spend_rows(
        rows,
        window,
    )



@dataclass(frozen=True)
class CustomerSimulationProfile:
    """
    不写入正式 BI 表的客户隐藏生成画像。
    """

    customer_code: str
    purchase_propensity: Decimal
    primary_sales_channel: str
    refund_propensity_multiplier: Decimal
    review_propensity_multiplier: Decimal
    rating_bias: Decimal


@dataclass(frozen=True)
class ProductSimulationProfile:
    """
    不写入正式 BI 表的商品隐藏生成画像。
    """

    sku_code: str
    demand_weight: Decimal
    quality_score: Decimal
    unit_cost_ratio: Decimal
    unit_cost: Decimal


def _bounded_decimal(
    value: float,
    minimum: Decimal,
    maximum: Decimal,
    decimal_places: str,
) -> Decimal:
    bounded_value = min(
        max(
            Decimal(str(value)),
            minimum,
        ),
        maximum,
    )

    return bounded_value.quantize(
        Decimal(decimal_places),
        rounding=ROUND_HALF_UP,
    )


def _weighted_choice(
    rng: random.Random,
    weighted_items: list[
        tuple[str, Decimal]
    ],
) -> str:
    """
    使用显式累计权重抽样，避免依赖全局随机状态。
    """
    if not weighted_items:
        raise ValueError(
            "weighted_items 不能为空。"
        )

    total_weight = sum(
        weight
        for _, weight in weighted_items
    )

    if total_weight <= 0:
        raise ValueError(
            "weighted_items 总权重必须大于 0。"
        )

    threshold = (
        Decimal(str(rng.random()))
        * total_weight
    )

    cumulative = Decimal("0")

    for item_key, weight in weighted_items:
        cumulative += weight

        if threshold < cumulative:
            return item_key

    return weighted_items[-1][0]


def build_customer_simulation_profiles(
    manifest: dict[str, Any],
    reference_data: ReferenceData,
) -> dict[str, CustomerSimulationProfile]:
    """
    为全部客户生成稳定、可复现的隐藏画像。
    """
    config = manifest[
        "simulation_profiles"
    ][
        "customer"
    ]

    purchase_config = config[
        "purchase_propensity"
    ]

    channel_config = config[
        "primary_sales_channel"
    ]

    refund_config = config[
        "refund_propensity"
    ]

    review_config = config[
        "review_propensity"
    ]

    rating_config = config[
        "rating_bias"
    ]

    purchase_minimum = Decimal(
        str(
            purchase_config[
                "minimum_weight"
            ]
        )
    )

    purchase_maximum = Decimal(
        str(
            purchase_config[
                "maximum_weight"
            ]
        )
    )

    refund_minimum = Decimal(
        str(
            refund_config[
                "minimum_multiplier"
            ]
        )
    )

    refund_maximum = Decimal(
        str(
            refund_config[
                "maximum_multiplier"
            ]
        )
    )

    review_minimum = Decimal(
        str(
            review_config[
                "minimum_multiplier"
            ]
        )
    )

    review_maximum = Decimal(
        str(
            review_config[
                "maximum_multiplier"
            ]
        )
    )

    rating_minimum = Decimal(
        str(rating_config["minimum"])
    )

    rating_maximum = Decimal(
        str(rating_config["maximum"])
    )

    configured_channel_weights = {
        channel_code: Decimal(str(weight))
        for channel_code, weight
        in channel_config["weights"].items()
    }

    active_sales_channel_codes = {
        row["channel_code"]
        for row in reference_data.channels
        if (
            row["is_active"]
            and row["is_sales_channel"]
        )
    }

    if (
        set(configured_channel_weights)
        != active_sales_channel_codes
    ):
        raise ValueError(
            "客户主销售渠道画像必须完整覆盖"
            "数据库中的启用销售渠道："
            f"expected="
            f"{sorted(active_sales_channel_codes)}, "
            f"actual="
            f"{sorted(configured_channel_weights)}"
        )

    weighted_channels = sorted(
        configured_channel_weights.items(),
        key=lambda item: item[0],
    )

    rng = build_rng(
        manifest,
        "customer_profiles",
    )

    profiles: dict[
        str,
        CustomerSimulationProfile,
    ] = {}

    for customer in sorted(
        reference_data.customers,
        key=lambda row: row["customer_code"],
    ):
        customer_code = customer[
            "customer_code"
        ]

        purchase_propensity = (
            _bounded_decimal(
                rng.lognormvariate(
                    purchase_config[
                        "lognormal_mu"
                    ],
                    purchase_config[
                        "lognormal_sigma"
                    ],
                ),
                purchase_minimum,
                purchase_maximum,
                "0.000001",
            )
        )

        primary_sales_channel = (
            _weighted_choice(
                rng,
                weighted_channels,
            )
        )

        refund_propensity = (
            _bounded_decimal(
                rng.uniform(
                    float(refund_minimum),
                    float(refund_maximum),
                ),
                refund_minimum,
                refund_maximum,
                "0.000001",
            )
        )

        review_propensity = (
            _bounded_decimal(
                rng.uniform(
                    float(review_minimum),
                    float(review_maximum),
                ),
                review_minimum,
                review_maximum,
                "0.000001",
            )
        )

        rating_bias = _bounded_decimal(
            rng.uniform(
                float(rating_minimum),
                float(rating_maximum),
            ),
            rating_minimum,
            rating_maximum,
            "0.000001",
        )

        profiles[customer_code] = (
            CustomerSimulationProfile(
                customer_code=customer_code,
                purchase_propensity=(
                    purchase_propensity
                ),
                primary_sales_channel=(
                    primary_sales_channel
                ),
                refund_propensity_multiplier=(
                    refund_propensity
                ),
                review_propensity_multiplier=(
                    review_propensity
                ),
                rating_bias=rating_bias,
            )
        )

    return profiles


def build_product_simulation_profiles(
    manifest: dict[str, Any],
    reference_data: ReferenceData,
) -> dict[str, ProductSimulationProfile]:
    """
    为全部商品生成稳定、可复现的隐藏画像。
    """
    config = manifest[
        "simulation_profiles"
    ][
        "product"
    ]

    demand_config = config[
        "demand_weight"
    ]

    quality_config = config[
        "quality_score"
    ]

    cost_config = config[
        "unit_cost_ratio"
    ]

    demand_minimum = Decimal(
        str(
            demand_config[
                "minimum_weight"
            ]
        )
    )

    demand_maximum = Decimal(
        str(
            demand_config[
                "maximum_weight"
            ]
        )
    )

    quality_minimum = Decimal(
        str(quality_config["minimum"])
    )

    quality_maximum = Decimal(
        str(quality_config["maximum"])
    )

    cost_minimum = Decimal(
        str(cost_config["minimum"])
    )

    cost_maximum = Decimal(
        str(cost_config["maximum"])
    )

    rng = build_rng(
        manifest,
        "product_profiles",
    )

    profiles: dict[
        str,
        ProductSimulationProfile,
    ] = {}

    for product in sorted(
        reference_data.products,
        key=lambda row: row["sku_code"],
    ):
        sku_code = product["sku_code"]

        demand_weight = _bounded_decimal(
            rng.lognormvariate(
                demand_config[
                    "lognormal_mu"
                ],
                demand_config[
                    "lognormal_sigma"
                ],
            ),
            demand_minimum,
            demand_maximum,
            "0.000001",
        )

        quality_score = _bounded_decimal(
            rng.normalvariate(
                quality_config["mean"],
                quality_config[
                    "standard_deviation"
                ],
            ),
            quality_minimum,
            quality_maximum,
            "0.000001",
        )

        unit_cost_ratio = _bounded_decimal(
            rng.uniform(
                float(cost_minimum),
                float(cost_maximum),
            ),
            cost_minimum,
            cost_maximum,
            "0.000001",
        )

        unit_cost = quantize_money(
            Decimal(str(product["list_price"]))
            * unit_cost_ratio
        )

        profiles[sku_code] = (
            ProductSimulationProfile(
                sku_code=sku_code,
                demand_weight=demand_weight,
                quality_score=quality_score,
                unit_cost_ratio=unit_cost_ratio,
                unit_cost=unit_cost,
            )
        )

    return profiles


def validate_simulation_profiles(
    customer_profiles: dict[
        str,
        CustomerSimulationProfile,
    ],
    product_profiles: dict[
        str,
        ProductSimulationProfile,
    ],
    manifest: dict[str, Any],
    reference_data: ReferenceData,
) -> None:
    """
    校验隐藏画像覆盖、范围和确定性。
    """
    customer_codes = {
        row["customer_code"]
        for row in reference_data.customers
    }

    product_codes = {
        row["sku_code"]
        for row in reference_data.products
    }

    if (
        set(customer_profiles)
        != customer_codes
    ):
        raise ValueError(
            "客户隐藏画像未完整覆盖客户维度。"
        )

    if (
        set(product_profiles)
        != product_codes
    ):
        raise ValueError(
            "商品隐藏画像未完整覆盖商品维度。"
        )

    customer_config = manifest[
        "simulation_profiles"
    ][
        "customer"
    ]

    product_config = manifest[
        "simulation_profiles"
    ][
        "product"
    ]

    active_sales_channels = {
        row["channel_code"]
        for row in reference_data.channels
        if (
            row["is_active"]
            and row["is_sales_channel"]
        )
    }

    for profile in customer_profiles.values():
        if not (
            Decimal(
                str(
                    customer_config[
                        "purchase_propensity"
                    ][
                        "minimum_weight"
                    ]
                )
            )
            <= profile.purchase_propensity
            <= Decimal(
                str(
                    customer_config[
                        "purchase_propensity"
                    ][
                        "maximum_weight"
                    ]
                )
            )
        ):
            raise ValueError(
                "客户购买倾向超出 Manifest "
                f"范围：{profile}"
            )

        if (
            profile.primary_sales_channel
            not in active_sales_channels
        ):
            raise ValueError(
                "客户主销售渠道无效："
                f"{profile}"
            )

        if not (
            Decimal(
                str(
                    customer_config[
                        "refund_propensity"
                    ][
                        "minimum_multiplier"
                    ]
                )
            )
            <= (
                profile.
                refund_propensity_multiplier
            )
            <= Decimal(
                str(
                    customer_config[
                        "refund_propensity"
                    ][
                        "maximum_multiplier"
                    ]
                )
            )
        ):
            raise ValueError(
                "客户退款倾向超出范围。"
            )

        if not (
            Decimal(
                str(
                    customer_config[
                        "review_propensity"
                    ][
                        "minimum_multiplier"
                    ]
                )
            )
            <= (
                profile.
                review_propensity_multiplier
            )
            <= Decimal(
                str(
                    customer_config[
                        "review_propensity"
                    ][
                        "maximum_multiplier"
                    ]
                )
            )
        ):
            raise ValueError(
                "客户评价倾向超出范围。"
            )

        if not (
            Decimal(
                str(
                    customer_config[
                        "rating_bias"
                    ][
                        "minimum"
                    ]
                )
            )
            <= profile.rating_bias
            <= Decimal(
                str(
                    customer_config[
                        "rating_bias"
                    ][
                        "maximum"
                    ]
                )
            )
        ):
            raise ValueError(
                "客户评分偏差超出范围。"
            )

    product_lookup = {
        row["sku_code"]: row
        for row in reference_data.products
    }

    for profile in product_profiles.values():
        if not (
            Decimal(
                str(
                    product_config[
                        "demand_weight"
                    ][
                        "minimum_weight"
                    ]
                )
            )
            <= profile.demand_weight
            <= Decimal(
                str(
                    product_config[
                        "demand_weight"
                    ][
                        "maximum_weight"
                    ]
                )
            )
        ):
            raise ValueError(
                "商品需求权重超出范围。"
            )

        if not (
            Decimal(
                str(
                    product_config[
                        "quality_score"
                    ][
                        "minimum"
                    ]
                )
            )
            <= profile.quality_score
            <= Decimal(
                str(
                    product_config[
                        "quality_score"
                    ][
                        "maximum"
                    ]
                )
            )
        ):
            raise ValueError(
                "商品质量分超出范围。"
            )

        if not (
            Decimal(
                str(
                    product_config[
                        "unit_cost_ratio"
                    ][
                        "minimum"
                    ]
                )
            )
            <= profile.unit_cost_ratio
            <= Decimal(
                str(
                    product_config[
                        "unit_cost_ratio"
                    ][
                        "maximum"
                    ]
                )
            )
        ):
            raise ValueError(
                "商品成本率超出范围。"
            )

        expected_cost = quantize_money(
            Decimal(
                str(
                    product_lookup[
                        profile.sku_code
                    ][
                        "list_price"
                    ]
                )
            )
            * profile.unit_cost_ratio
        )

        if profile.unit_cost != expected_cost:
            raise ValueError(
                "商品单位成本不符合"
                "吊牌价 × 成本率："
                f"{profile}"
            )

    repeated_customer_profiles = (
        build_customer_simulation_profiles(
            manifest=manifest,
            reference_data=reference_data,
        )
    )

    repeated_product_profiles = (
        build_product_simulation_profiles(
            manifest=manifest,
            reference_data=reference_data,
        )
    )

    if (
        customer_profiles
        != repeated_customer_profiles
    ):
        raise ValueError(
            "客户隐藏画像确定性校验失败。"
        )

    if (
        product_profiles
        != repeated_product_profiles
    ):
        raise ValueError(
            "商品隐藏画像确定性校验失败。"
        )


def load_marketing_spend_rows(
    connection: Connection,
) -> list[dict[str, Any]]:
    """
    从数据库读取已完成写入的营销费用，
    用于后续订单需求权重。
    """
    return [
        dict(row)
        for row in connection.execute(
            text(
                """
                SELECT
                    spend.spend_date,
                    channel.channel_code,
                    campaign.campaign_code,
                    spend.spend_amount
                FROM
                    beauty_bi_v2.
                    fact_marketing_spend
                        AS spend
                INNER JOIN
                    beauty_bi_v2.dim_channel
                        AS channel
                    ON channel.channel_id =
                        spend.channel_id
                INNER JOIN
                    beauty_bi_v2.dim_campaign
                        AS campaign
                    ON campaign.campaign_id =
                        spend.campaign_id
                ORDER BY
                    spend.spend_date,
                    channel.channel_code,
                    campaign.campaign_code
                """
            )
        ).mappings().all()
    ]


def allocate_largest_remainder(
    total_count: int,
    weighted_items: list[
        tuple[Any, Decimal]
    ],
    allocation_name: str,
) -> dict[Any, int]:
    """
    对任意正权重集合执行稳定的最大余数分配。
    """
    if (
        isinstance(total_count, bool)
        or not isinstance(total_count, int)
        or total_count <= 0
    ):
        raise ValueError(
            f"{allocation_name}.total_count "
            "必须是正整数。"
        )

    if not weighted_items:
        raise ValueError(
            f"{allocation_name} 权重不能为空。"
        )

    keys = [
        item_key
        for item_key, _ in weighted_items
    ]

    if len(keys) != len(set(keys)):
        raise ValueError(
            f"{allocation_name} 存在重复键。"
        )

    total_weight = sum(
        weight
        for _, weight in weighted_items
    )

    if total_weight <= 0:
        raise ValueError(
            f"{allocation_name} 总权重"
            "必须大于 0。"
        )

    allocations: list[
        dict[str, Any]
    ] = []

    for source_index, (
        item_key,
        weight,
    ) in enumerate(weighted_items):
        if weight <= 0:
            raise ValueError(
                f"{allocation_name} 包含"
                "非正权重："
                f"key={item_key!r}, "
                f"weight={weight}"
            )

        exact_count = (
            Decimal(total_count)
            * weight
            / total_weight
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
                "remainder": (
                    exact_count
                    - Decimal(base_count)
                ),
                "source_index": source_index,
            }
        )

    remaining_count = (
        total_count
        - sum(
            item["allocated_count"]
            for item in allocations
        )
    )

    remainder_order = sorted(
        range(len(allocations)),
        key=lambda index: (
            -allocations[index][
                "remainder"
            ],
            allocations[index][
                "source_index"
            ],
        ),
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
            f"{allocation_name} 最大余数"
            "分配后总数不正确。"
        )

    return result


def allocate_annual_order_counts(
    manifest: dict[str, Any],
) -> dict[int, int]:
    """
    先按 Manifest 年度权重严格分配订单总量。
    """
    _, profile = get_active_scale_profile(
        manifest
    )

    annual_weights = manifest[
        "order_generation"
    ][
        "date_allocation"
    ][
        "annual_weights"
    ]

    normalized_weights = sorted(
        (
            (
                int(raw_year),
                Decimal(str(weight)),
            )
            for raw_year, weight
            in annual_weights.items()
        ),
        key=lambda item: item[0],
    )

    return allocate_largest_remainder(
        total_count=profile[
            "expected_orders"
        ],
        weighted_items=normalized_weights,
        allocation_name=(
            "annual order allocation"
        ),
    )


def build_daily_order_allocations(
    manifest: dict[str, Any],
    reference_data: ReferenceData,
    window: GenerationWindow,
    marketing_spend_rows: list[
        dict[str, Any]
    ],
) -> list[dict[str, Any]]:
    """
    将年度订单目标精确分配到每个业务日期。

    权重组成：
    weekday
    × holiday
    × major campaign
    × average channel marketing response
    × deterministic noise
    """
    config = manifest[
        "order_generation"
    ][
        "date_allocation"
    ]

    annual_counts = (
        allocate_annual_order_counts(
            manifest
        )
    )

    weekday_multipliers = {
        weekday_name: Decimal(str(value))
        for weekday_name, value
        in config[
            "weekday_multipliers"
        ].items()
    }

    holiday_multiplier = Decimal(
        str(config["holiday_multiplier"])
    )

    campaign_multipliers = {
        family: Decimal(str(value))
        for family, value
        in config[
            "campaign_family_multipliers"
        ].items()
    }

    noise_config = config[
        "deterministic_noise"
    ]

    noise_minimum = Decimal(
        str(
            noise_config[
                "minimum_multiplier"
            ]
        )
    )

    noise_maximum = Decimal(
        str(
            noise_config[
                "maximum_multiplier"
            ]
        )
    )

    default_demand_multiplier = Decimal(
        str(
            manifest[
                "simulation_profiles"
            ][
                "demand_context"
            ][
                "default_multiplier"
            ]
        )
    )

    marketing_multipliers = (
        build_daily_channel_demand_multipliers(
            rows=marketing_spend_rows,
            manifest=manifest,
        )
    )

    active_marketing_channel_codes = sorted(
        row["channel_code"]
        for row in reference_data.channels
        if (
            row["is_active"]
            and row["is_marketing_channel"]
        )
    )

    if not active_marketing_channel_codes:
        raise ValueError(
            "订单日期分配缺少启用的营销渠道。"
        )

    date_lookup = {
        row["full_date"]: row
        for row in reference_data.dates
    }

    major_campaigns = [
        row
        for row in reference_data.campaigns
        if (
            row["is_active"]
            and row["campaign_type"]
                == "major_promotion"
        )
    ]

    rng = build_rng(
        manifest,
        "daily_order_allocation",
    )

    day_specs_by_year: defaultdict[
        int,
        list[dict[str, Any]],
    ] = defaultdict(list)

    current_date = window.business_start_date

    while current_date <= window.business_end_date:
        date_row = date_lookup.get(
            current_date
        )

        if date_row is None:
            raise ValueError(
                "订单日期分配缺少 dim_date："
                f"{current_date}"
            )

        active_major_campaigns = [
            campaign
            for campaign in major_campaigns
            if (
                campaign["start_date"]
                <= current_date
                <= campaign["end_date"]
            )
        ]

        if len(active_major_campaigns) > 1:
            raise ValueError(
                "同一业务日期命中了多个"
                "主要活动，当前 P0 单一活动"
                "归因无法处理："
                f"date={current_date}, "
                f"campaigns="
                f"{[row['campaign_code'] for row in active_major_campaigns]}"
            )

        if active_major_campaigns:
            campaign_family = (
                active_major_campaigns[0][
                    "campaign_family"
                ]
            )

            campaign_multiplier = (
                campaign_multipliers[
                    campaign_family
                ]
            )
        else:
            campaign_family = None
            campaign_multiplier = (
                Decimal("1")
            )

        channel_multiplier_values = [
            marketing_multipliers.get(
                (
                    current_date,
                    channel_code,
                ),
                default_demand_multiplier,
            )
            for channel_code
            in active_marketing_channel_codes
        ]

        average_marketing_multiplier = (
            sum(channel_multiplier_values)
            / Decimal(
                len(
                    channel_multiplier_values
                )
            )
        )

        weekday_name = WEEKDAY_CONFIG_KEYS[
            current_date.isoweekday()
        ]

        date_holiday_multiplier = (
            holiday_multiplier
            if date_row["is_holiday"]
            else Decimal("1")
        )

        noise_multiplier = Decimal(
            str(
                rng.uniform(
                    float(noise_minimum),
                    float(noise_maximum),
                )
            )
        )

        raw_weight = (
            weekday_multipliers[
                weekday_name
            ]
            * date_holiday_multiplier
            * campaign_multiplier
            * average_marketing_multiplier
            * noise_multiplier
        )

        day_specs_by_year[
            current_date.year
        ].append(
            {
                "order_date": current_date,
                "is_holiday": date_row[
                    "is_holiday"
                ],
                "campaign_family": (
                    campaign_family
                ),
                "weekday_multiplier": (
                    weekday_multipliers[
                        weekday_name
                    ]
                ),
                "holiday_multiplier": (
                    date_holiday_multiplier
                ),
                "campaign_multiplier": (
                    campaign_multiplier
                ),
                "marketing_multiplier": (
                    average_marketing_multiplier
                ),
                "noise_multiplier": (
                    noise_multiplier
                ),
                "raw_weight": raw_weight,
            }
        )

        current_date += timedelta(days=1)

    rows: list[dict[str, Any]] = []

    for year in sorted(day_specs_by_year):
        year_specs = day_specs_by_year[
            year
        ]

        daily_counts = (
            allocate_largest_remainder(
                total_count=annual_counts[year],
                weighted_items=[
                    (
                        item["order_date"],
                        item["raw_weight"],
                    )
                    for item in year_specs
                ],
                allocation_name=(
                    f"daily order allocation {year}"
                ),
            )
        )

        for item in year_specs:
            rows.append(
                {
                    "order_date": item[
                        "order_date"
                    ],
                    "year": year,
                    "is_holiday": item[
                        "is_holiday"
                    ],
                    "campaign_family": item[
                        "campaign_family"
                    ],
                    "weekday_multiplier": (
                        item[
                            "weekday_multiplier"
                        ].quantize(
                            Decimal("0.000001"),
                            rounding=ROUND_HALF_UP,
                        )
                    ),
                    "holiday_multiplier": (
                        item[
                            "holiday_multiplier"
                        ].quantize(
                            Decimal("0.000001"),
                            rounding=ROUND_HALF_UP,
                        )
                    ),
                    "campaign_multiplier": (
                        item[
                            "campaign_multiplier"
                        ].quantize(
                            Decimal("0.000001"),
                            rounding=ROUND_HALF_UP,
                        )
                    ),
                    "marketing_multiplier": (
                        item[
                            "marketing_multiplier"
                        ].quantize(
                            Decimal("0.000001"),
                            rounding=ROUND_HALF_UP,
                        )
                    ),
                    "noise_multiplier": (
                        item[
                            "noise_multiplier"
                        ].quantize(
                            Decimal("0.000001"),
                            rounding=ROUND_HALF_UP,
                        )
                    ),
                    "raw_weight": item[
                        "raw_weight"
                    ].quantize(
                        Decimal("0.000001"),
                        rounding=ROUND_HALF_UP,
                    ),
                    "allocated_orders": (
                        daily_counts[
                            item["order_date"]
                        ]
                    ),
                }
            )

    return rows


def validate_daily_order_allocations(
    rows: list[dict[str, Any]],
    manifest: dict[str, Any],
    reference_data: ReferenceData,
    window: GenerationWindow,
    marketing_spend_rows: list[
        dict[str, Any]
    ],
) -> None:
    """
    校验订单日期分配的总量、年度目标、
    日期覆盖与确定性。
    """
    if not rows:
        raise ValueError(
            "订单日期分配结果不能为空。"
        )

    _, profile = get_active_scale_profile(
        manifest
    )

    expected_total = profile[
        "expected_orders"
    ]

    if (
        sum(
            row["allocated_orders"]
            for row in rows
        )
        != expected_total
    ):
        raise ValueError(
            "订单日期分配总量不正确："
            f"expected={expected_total}, "
            "actual="
            f"{sum(row['allocated_orders'] for row in rows)}"
        )

    if len(rows) != window.business_day_count:
        raise ValueError(
            "订单日期分配行数不正确："
            f"expected="
            f"{window.business_day_count}, "
            f"actual={len(rows)}"
        )

    expected_dates = [
        window.business_start_date
        + timedelta(days=offset)
        for offset in range(
            window.business_day_count
        )
    ]

    actual_dates = [
        row["order_date"]
        for row in rows
    ]

    if actual_dates != expected_dates:
        raise ValueError(
            "订单日期分配未连续覆盖"
            "完整业务窗口。"
        )

    if len(actual_dates) != len(
        set(actual_dates)
    ):
        raise ValueError(
            "订单日期分配存在重复日期。"
        )

    if any(
        (
            isinstance(
                row["allocated_orders"],
                bool,
            )
            or not isinstance(
                row["allocated_orders"],
                int,
            )
            or row["allocated_orders"] <= 0
        )
        for row in rows
    ):
        raise ValueError(
            "每个业务日期必须分配"
            "至少一张订单。"
        )

    expected_annual_counts = (
        allocate_annual_order_counts(
            manifest
        )
    )

    actual_annual_counts = Counter()

    for row in rows:
        actual_annual_counts[
            row["year"]
        ] += row["allocated_orders"]

    if (
        dict(actual_annual_counts)
        != expected_annual_counts
    ):
        raise ValueError(
            "订单年度分配不正确："
            f"expected="
            f"{expected_annual_counts}, "
            f"actual="
            f"{dict(actual_annual_counts)}"
        )

    repeated_rows = (
        build_daily_order_allocations(
            manifest=manifest,
            reference_data=reference_data,
            window=window,
            marketing_spend_rows=(
                marketing_spend_rows
            ),
        )
    )

    if rows != repeated_rows:
        raise ValueError(
            "订单日期分配确定性校验失败。"
        )


def _decimal_range(
    values: list[Decimal],
) -> str:
    return (
        f"{min(values)} -> {max(values)}"
    )


def preview_simulation_profiles(
    manifest: dict[str, Any],
) -> None:
    window = build_generation_window(
        manifest
    )

    with engine.connect() as connection:
        reference_data = load_reference_data(
            connection
        )

        validate_reference_data(
            reference_data=reference_data,
            manifest=manifest,
            window=window,
        )

    customer_profiles = (
        build_customer_simulation_profiles(
            manifest=manifest,
            reference_data=reference_data,
        )
    )

    product_profiles = (
        build_product_simulation_profiles(
            manifest=manifest,
            reference_data=reference_data,
        )
    )

    validate_simulation_profiles(
        customer_profiles=customer_profiles,
        product_profiles=product_profiles,
        manifest=manifest,
        reference_data=reference_data,
    )

    customer_values = list(
        customer_profiles.values()
    )

    product_values = list(
        product_profiles.values()
    )

    channel_counts = Counter(
        profile.primary_sales_channel
        for profile in customer_values
    )

    print(
        "simulation profile preview passed."
    )
    print(
        "Customer profiles: "
        f"{len(customer_profiles)}"
    )
    print(
        "Primary sales-channel counts: "
        f"{dict(channel_counts)}"
    )
    print(
        "Purchase propensity range: "
        f"{_decimal_range([profile.purchase_propensity for profile in customer_values])}"
    )
    print(
        "Refund propensity range: "
        f"{_decimal_range([profile.refund_propensity_multiplier for profile in customer_values])}"
    )
    print(
        "Review propensity range: "
        f"{_decimal_range([profile.review_propensity_multiplier for profile in customer_values])}"
    )
    print(
        "Rating bias range: "
        f"{_decimal_range([profile.rating_bias for profile in customer_values])}"
    )
    print(
        "Product profiles: "
        f"{len(product_profiles)}"
    )
    print(
        "Demand weight range: "
        f"{_decimal_range([profile.demand_weight for profile in product_values])}"
    )
    print(
        "Quality score range: "
        f"{_decimal_range([profile.quality_score for profile in product_values])}"
    )
    print(
        "Unit-cost ratio range: "
        f"{_decimal_range([profile.unit_cost_ratio for profile in product_values])}"
    )
    print(
        "Unit-cost amount range: "
        f"{_decimal_range([profile.unit_cost for profile in product_values])}"
    )
    print(
        "Hidden profiles persisted to BI tables: no"
    )
    print("Deterministic check: passed.")


def preview_order_allocation(
    manifest: dict[str, Any],
) -> None:
    window = build_generation_window(
        manifest
    )

    with engine.connect() as connection:
        reference_data = load_reference_data(
            connection
        )

        validate_reference_data(
            reference_data=reference_data,
            manifest=manifest,
            window=window,
        )

        marketing_spend_rows = (
            load_marketing_spend_rows(
                connection
            )
        )

        downstream_counts = {
            table_name: (
                connection.execute(
                    text(
                        "SELECT COUNT(*) "
                        f"FROM beauty_bi_v2."
                        f"{table_name}"
                    )
                ).scalar_one()
            )
            for table_name in (
                "fact_orders",
                "fact_order_items",
                "fact_refunds",
                "fact_reviews",
                "fact_membership_tier_history",
            )
        }

    nonempty_downstream_tables = {
        table_name: row_count
        for table_name, row_count
        in downstream_counts.items()
        if row_count != 0
    }

    if nonempty_downstream_tables:
        raise RuntimeError(
            "订单分配 Preview 要求订单及"
            "下游事实表为空："
            f"{nonempty_downstream_tables}"
        )

    validate_marketing_spend_rows(
        rows=marketing_spend_rows,
        manifest=manifest,
        reference_data=reference_data,
        window=window,
    )

    customer_profiles = (
        build_customer_simulation_profiles(
            manifest=manifest,
            reference_data=reference_data,
        )
    )

    product_profiles = (
        build_product_simulation_profiles(
            manifest=manifest,
            reference_data=reference_data,
        )
    )

    validate_simulation_profiles(
        customer_profiles=customer_profiles,
        product_profiles=product_profiles,
        manifest=manifest,
        reference_data=reference_data,
    )

    rows = build_daily_order_allocations(
        manifest=manifest,
        reference_data=reference_data,
        window=window,
        marketing_spend_rows=(
            marketing_spend_rows
        ),
    )

    validate_daily_order_allocations(
        rows=rows,
        manifest=manifest,
        reference_data=reference_data,
        window=window,
        marketing_spend_rows=(
            marketing_spend_rows
        ),
    )

    annual_counts = Counter()

    for row in rows:
        annual_counts[
            row["year"]
        ] += row["allocated_orders"]

    major_rows = [
        row
        for row in rows
        if row["campaign_family"] is not None
    ]

    normal_rows = [
        row
        for row in rows
        if row["campaign_family"] is None
    ]

    major_average = (
        Decimal(
            sum(
                row["allocated_orders"]
                for row in major_rows
            )
        )
        / Decimal(len(major_rows))
    )

    normal_average = (
        Decimal(
            sum(
                row["allocated_orders"]
                for row in normal_rows
            )
        )
        / Decimal(len(normal_rows))
    )

    top_dates = sorted(
        rows,
        key=lambda row: (
            -row["allocated_orders"],
            row["order_date"],
        ),
    )[:10]

    print(
        "daily order allocation preview passed."
    )
    print(
        "Target orders: "
        f"{sum(row['allocated_orders'] for row in rows)}"
    )
    print(
        "Annual order counts: "
        f"{dict(annual_counts)}"
    )
    print(
        "Business date rows: "
        f"{len(rows)}"
    )
    print(
        "Daily order range: "
        f"{min(row['allocated_orders'] for row in rows)} -> "
        f"{max(row['allocated_orders'] for row in rows)}"
    )
    print(
        "Major-promotion daily average: "
        f"{major_average.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)}"
    )
    print(
        "Non-promotion daily average: "
        f"{normal_average.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)}"
    )
    print(
        "Marketing multiplier range: "
        f"{_decimal_range([row['marketing_multiplier'] for row in rows])}"
    )
    print(
        "Top order dates: "
        f"{[(row['order_date'], row['allocated_orders'], row['campaign_family']) for row in top_dates]}"
    )
    print(f"First row: {rows[0]}")
    print(f"Last row: {rows[-1]}")
    print(
        "Observation-tail new order rows: 0"
    )
    print(
        "Customer profiles available: "
        f"{len(customer_profiles)}"
    )
    print(
        "Product profiles available: "
        f"{len(product_profiles)}"
    )
    print("Exact-total check: passed.")
    print("Deterministic check: passed.")



def build_cumulative_weights(
    weighted_rows: list[
        tuple[Any, Decimal]
    ],
    field_name: str,
) -> tuple[list[Any], list[float]]:
    """
    将正 Decimal 权重转换为可供 bisect 使用的累计权重。
    """
    if not weighted_rows:
        raise ValueError(
            f"{field_name} 权重集合不能为空。"
        )

    items: list[Any] = []
    cumulative_weights: list[float] = []
    cumulative = Decimal("0")

    for item, weight in weighted_rows:
        if weight <= 0:
            raise ValueError(
                f"{field_name} 包含非正权重："
                f"{weight}"
            )

        cumulative += weight
        items.append(item)
        cumulative_weights.append(
            float(cumulative)
        )

    return items, cumulative_weights


def choose_from_cumulative_weights(
    rng: random.Random,
    items: list[Any],
    cumulative_weights: list[float],
) -> Any:
    """
    从预构建的累计权重中抽样。
    """
    if (
        not items
        or len(items)
        != len(cumulative_weights)
    ):
        raise ValueError(
            "累计权重输入不合法。"
        )

    threshold = rng.random() * (
        cumulative_weights[-1]
    )

    index = bisect.bisect_right(
        cumulative_weights,
        threshold,
    )

    if index >= len(items):
        index = len(items) - 1

    return items[index]


def build_creation_dayparts(
    manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    解析订单创建时间的半开日间区间。
    """
    config = manifest[
        "order_generation"
    ][
        "creation_time_distribution"
    ]

    dayparts: list[dict[str, Any]] = []

    for item in config["dayparts"]:
        start_hour = int(
            item["start_hour"]
        )

        end_hour = int(
            item["end_hour"]
        )

        dayparts.append(
            {
                "daypart_name": (
                    item[
                        "name"
                    ].strip()
                ),
                "start_second": (
                    start_hour * 3600
                ),
                "end_second": (
                    end_hour * 3600
                ),
                "weight": Decimal(
                    str(item["weight"])
                ),
            }
        )

    return dayparts


def choose_order_created_at(
    rng: random.Random,
    order_date: date,
    dayparts: list[dict[str, Any]],
) -> tuple[datetime, str]:
    """
    按 daypart 权重选择日内时间，再在半开区间内按秒抽样。
    """
    selected_daypart_name = (
        _weighted_choice(
            rng,
            [
                (
                    item["daypart_name"],
                    item["weight"],
                )
                for item in dayparts
            ],
        )
    )

    selected_daypart = next(
        item
        for item in dayparts
        if (
            item["daypart_name"]
            == selected_daypart_name
        )
    )

    start_second = selected_daypart[
        "start_second"
    ]

    end_second = selected_daypart[
        "end_second"
    ]

    selected_second = rng.randrange(
        start_second,
        end_second,
    )

    created_at = (
        datetime.combine(
            order_date,
            datetime.min.time(),
        )
        + timedelta(
            seconds=selected_second
        )
    )

    return (
        created_at,
        selected_daypart_name,
    )


def build_customer_membership_lookup(
    reference_data: ReferenceData,
) -> dict[
    str,
    list[dict[str, Any]],
]:
    """
    按 customer_code 组织身份映射历史。
    """
    lookup: dict[
        str,
        list[dict[str, Any]],
    ] = defaultdict(list)

    for row in (
        reference_data.
        customer_membership_mappings
    ):
        lookup[
            row["customer_code"]
        ].append(row)

    for customer_code in lookup:
        lookup[customer_code].sort(
            key=lambda row: (
                row["effective_from_ts"]
            )
        )

    return dict(lookup)


def resolve_member_code_at_timestamp(
    customer_code: str,
    event_ts: datetime | None,
    mapping_lookup: dict[
        str,
        list[dict[str, Any]],
    ],
) -> str | None:
    """
    返回事件时点生效的品牌会员账户编码。
    """
    if event_ts is None:
        return None

    candidates = [
        row
        for row in mapping_lookup.get(
            customer_code,
            [],
        )
        if (
            row["effective_from_ts"]
            <= event_ts
            and (
                row["effective_to_ts"]
                is None
                or event_ts
                    < row[
                        "effective_to_ts"
                    ]
            )
            and row["mapping_status"]
                == "active"
        )
    ]

    if len(candidates) > 1:
        raise ValueError(
            "同一客户在支付时点命中多个"
            "品牌会员账户："
            f"customer_code={customer_code}, "
            f"event_ts={event_ts}"
        )

    if not candidates:
        return None

    return candidates[0]["member_code"]


def build_daily_channel_context(
    marketing_spend_rows: list[
        dict[str, Any]
    ],
    manifest: dict[str, Any],
) -> dict[
    tuple[date, str],
    Decimal,
]:
    """
    构造订单渠道抽样使用的每日渠道需求上下文。
    """
    return build_daily_channel_demand_multipliers(
        rows=marketing_spend_rows,
        manifest=manifest,
    )


def build_eligible_customer_weight_cache(
    order_dates: list[date],
    reference_data: ReferenceData,
    customer_profiles: dict[
        str,
        CustomerSimulationProfile,
    ],
) -> dict[
    date,
    tuple[
        list[dict[str, Any]],
        list[float],
    ],
]:
    """
    为每个业务日期预构建可下单客户及累计购买权重。

    只有 active 且 first_seen_date 不晚于订单日期的客户
    才能进入候选集合。
    """
    active_customers = sorted(
        (
            row
            for row in reference_data.customers
            if row["customer_status"] == "active"
        ),
        key=lambda row: (
            row["first_seen_date"],
            row["customer_code"],
        ),
    )

    cache: dict[
        date,
        tuple[
            list[dict[str, Any]],
            list[float],
        ],
    ] = {}

    eligible_customers: list[
        dict[str, Any]
    ] = []

    weighted_rows: list[
        tuple[
            dict[str, Any],
            Decimal,
        ]
    ] = []

    customer_index = 0

    for order_date in sorted(
        set(order_dates)
    ):
        while (
            customer_index
            < len(active_customers)
            and active_customers[
                customer_index
            ][
                "first_seen_date"
            ]
            <= order_date
        ):
            customer = active_customers[
                customer_index
            ]

            eligible_customers.append(
                customer
            )

            weighted_rows.append(
                (
                    customer,
                    customer_profiles[
                        customer[
                            "customer_code"
                        ]
                    ].purchase_propensity,
                )
            )

            customer_index += 1

        if not eligible_customers:
            raise ValueError(
                "订单日期没有可用的 active "
                "客户候选："
                f"{order_date}"
            )

        items, cumulative_weights = (
            build_cumulative_weights(
                weighted_rows,
                (
                    "eligible customer "
                    f"{order_date}"
                ),
            )
        )

        cache[order_date] = (
            list(items),
            list(cumulative_weights),
        )

    return cache


def choose_sales_channel(
    rng: random.Random,
    order_date: date,
    customer_profile: (
        CustomerSimulationProfile
    ),
    active_sales_channels: list[
        dict[str, Any]
    ],
    daily_channel_context: dict[
        tuple[date, str],
        Decimal,
    ],
    manifest: dict[str, Any],
) -> str:
    """
    按客户主渠道偏好 × 每日营销上下文选择销售渠道。
    """
    profile_config = manifest[
        "simulation_profiles"
    ][
        "customer"
    ][
        "primary_sales_channel"
    ]

    preferred_multiplier = Decimal(
        str(
            profile_config[
                "preferred_channel_multiplier"
            ]
        )
    )

    non_preferred_multiplier = Decimal(
        str(
            profile_config[
                "non_preferred_channel_multiplier"
            ]
        )
    )

    default_multiplier = Decimal(
        str(
            manifest[
                "simulation_profiles"
            ][
                "demand_context"
            ][
                "default_multiplier"
            ]
        )
    )

    weighted_channels: list[
        tuple[str, Decimal]
    ] = []

    for channel in active_sales_channels:
        channel_code = channel[
            "channel_code"
        ]

        preference_multiplier = (
            preferred_multiplier
            if (
                channel_code
                == (
                    customer_profile.
                    primary_sales_channel
                )
            )
            else non_preferred_multiplier
        )

        context_multiplier = (
            daily_channel_context.get(
                (
                    order_date,
                    channel_code,
                ),
                default_multiplier,
            )
        )

        weighted_channels.append(
            (
                channel_code,
                preference_multiplier
                * context_multiplier,
            )
        )

    return _weighted_choice(
        rng,
        weighted_channels,
    )


def choose_shipping_region(
    rng: random.Random,
    customer: dict[str, Any],
    reference_data: ReferenceData,
    manifest: dict[str, Any],
) -> tuple[str, str]:
    """
    按 home / same_region_group / other 分布选择收货地区。
    """
    distribution = manifest[
        "order_generation"
    ][
        "entity_selection"
    ][
        "shipping_region"
    ][
        "distribution"
    ]

    source = _weighted_choice(
        rng,
        [
            (
                source_name,
                Decimal(str(weight)),
            )
            for source_name, weight
            in distribution.items()
        ],
    )

    home_region_code = customer[
        "home_region_code"
    ]

    home_region_group = customer[
        "home_region_group"
    ]

    if source == "home_region":
        return (
            home_region_code,
            source,
        )

    if source == "same_region_group":
        candidates = [
            row["region_code"]
            for row in reference_data.regions
            if (
                row["region_group"]
                    == home_region_group
                and row["region_code"]
                    != home_region_code
            )
        ]

        if not candidates:
            return (
                home_region_code,
                "home_region_fallback",
            )

        return (
            rng.choice(
                sorted(candidates)
            ),
            source,
        )

    if source == "other_region":
        candidates = [
            row["region_code"]
            for row in reference_data.regions
            if (
                row["region_group"]
                    != home_region_group
            )
        ]

        if not candidates:
            raise ValueError(
                "没有可用的跨区域"
                "收货地区候选。"
            )

        return (
            rng.choice(
                sorted(candidates)
            ),
            source,
        )

    raise ValueError(
        "未知 shipping region source："
        f"{source}"
    )


def resolve_major_campaign_for_date(
    order_date: date,
    reference_data: ReferenceData,
) -> dict[str, Any] | None:
    """
    返回订单日期唯一生效的 major_promotion。
    """
    candidates = [
        row
        for row in reference_data.campaigns
        if (
            row["is_active"]
            and row["campaign_type"]
                == "major_promotion"
            and row["start_date"]
                <= order_date
                <= row["end_date"]
        )
    ]

    if len(candidates) > 1:
        raise ValueError(
            "订单日期命中多个主要活动："
            f"date={order_date}, "
            f"campaigns="
            f"{[row['campaign_code'] for row in candidates]}"
        )

    if not candidates:
        return None

    return candidates[0]


def choose_campaign_attribution(
    rng: random.Random,
    order_date: date,
    reference_data: ReferenceData,
    manifest: dict[str, Any],
) -> str | None:
    """
    大促窗口内按概率归因至主要活动，否则为 NULL。
    """
    campaign = (
        resolve_major_campaign_for_date(
            order_date,
            reference_data,
        )
    )

    if campaign is None:
        return None

    probability = manifest[
        "order_generation"
    ][
        "entity_selection"
    ][
        "campaign_attribution"
    ][
        "major_campaign_attribution_probability"
    ]

    if rng.random() < probability:
        return campaign[
            "campaign_code"
        ]

    return None


def build_order_header_event_rows(
    manifest: dict[str, Any],
    reference_data: ReferenceData,
    window: GenerationWindow,
    daily_allocations: list[
        dict[str, Any]
    ],
    marketing_spend_rows: list[
        dict[str, Any]
    ],
    customer_profiles: dict[
        str,
        CustomerSimulationProfile,
    ],
) -> list[dict[str, Any]]:
    """
    生成 40000 个订单头事件。

    当前阶段不生成商品金额、履约时间和会员等级快照，
    因而只用于 Preview，不写入 fact_orders。
    """
    order_config = manifest[
        "order_generation"
    ]

    lifecycle = order_config[
        "lifecycle"
    ]

    order_code_config = order_config[
        "order_code"
    ]

    code_prefix = order_code_config[
        "prefix"
    ].strip()

    code_width = order_code_config[
        "width"
    ]

    successful_payment_probability = (
        lifecycle[
            "successful_payment_probability"
        ]
    )

    payment_delay = lifecycle[
        "payment_delay_minutes"
    ]

    cancellation_delay = lifecycle[
        "cancellation_delay_minutes"
    ]

    paid_status = lifecycle[
        "paid_status_before_delivery"
    ].strip()

    cancelled_status = lifecycle[
        "unpaid_final_status"
    ].strip()

    payment_cutoff_ts = (
        datetime.combine(
            window.business_end_date,
            datetime.max.time(),
        ).replace(
            microsecond=0
        )
    )

    dayparts = build_creation_dayparts(
        manifest
    )

    customer_cache = (
        build_eligible_customer_weight_cache(
            order_dates=[
                row["order_date"]
                for row in daily_allocations
            ],
            reference_data=reference_data,
            customer_profiles=customer_profiles,
        )
    )

    active_sales_channels = sorted(
        (
            row
            for row in reference_data.channels
            if (
                row["is_active"]
                and row["is_sales_channel"]
            )
        ),
        key=lambda row: row["channel_code"],
    )

    daily_channel_context = (
        build_daily_channel_context(
            marketing_spend_rows=(
                marketing_spend_rows
            ),
            manifest=manifest,
        )
    )

    membership_lookup = (
        build_customer_membership_lookup(
            reference_data
        )
    )

    lifecycle_rng = build_rng(
        manifest,
        "order_lifecycle",
    )

    entity_rng = build_rng(
        manifest,
        "order_entities",
    )

    rows: list[dict[str, Any]] = []

    order_number = 1

    for daily_row in daily_allocations:
        order_date = daily_row[
            "order_date"
        ]

        eligible_customers, (
            cumulative_customer_weights
        ) = customer_cache[order_date]

        for _ in range(
            daily_row["allocated_orders"]
        ):
            (
                order_created_at,
                creation_daypart,
            ) = choose_order_created_at(
                rng=lifecycle_rng,
                order_date=order_date,
                dayparts=dayparts,
            )

            customer = (
                choose_from_cumulative_weights(
                    rng=entity_rng,
                    items=eligible_customers,
                    cumulative_weights=(
                        cumulative_customer_weights
                    ),
                )
            )

            customer_code = customer[
                "customer_code"
            ]

            customer_profile = (
                customer_profiles[
                    customer_code
                ]
            )

            channel_code = (
                choose_sales_channel(
                    rng=entity_rng,
                    order_date=order_date,
                    customer_profile=(
                        customer_profile
                    ),
                    active_sales_channels=(
                        active_sales_channels
                    ),
                    daily_channel_context=(
                        daily_channel_context
                    ),
                    manifest=manifest,
                )
            )

            (
                shipping_region_code,
                shipping_region_source,
            ) = choose_shipping_region(
                rng=entity_rng,
                customer=customer,
                reference_data=reference_data,
                manifest=manifest,
            )

            campaign_code = (
                choose_campaign_attribution(
                    rng=entity_rng,
                    order_date=order_date,
                    reference_data=reference_data,
                    manifest=manifest,
                )
            )

            payment_succeeds = (
                lifecycle_rng.random()
                < successful_payment_probability
            )

            paid_at: datetime | None = None
            cancelled_at: datetime | None = None
            cancellation_reason: (
                str | None
            ) = None

            if payment_succeeds:
                candidate_paid_at = (
                    order_created_at
                    + timedelta(
                        minutes=(
                            lifecycle_rng.randint(
                                payment_delay[
                                    "minimum"
                                ],
                                payment_delay[
                                    "maximum"
                                ],
                            )
                        )
                    )
                )

                if (
                    candidate_paid_at
                    <= payment_cutoff_ts
                ):
                    paid_at = candidate_paid_at
                    order_status = paid_status
                else:
                    order_status = (
                        cancelled_status
                    )
                    cancelled_at = (
                        payment_cutoff_ts
                    )
                    cancellation_reason = (
                        "payment_cutoff_overflow"
                    )
            else:
                order_status = cancelled_status

                cancelled_at = (
                    order_created_at
                    + timedelta(
                        minutes=(
                            lifecycle_rng.randint(
                                cancellation_delay[
                                    "minimum"
                                ],
                                cancellation_delay[
                                    "maximum"
                                ],
                            )
                        )
                    )
                )

                cancellation_reason = (
                    "payment_failed"
                )

            member_code_at_payment = (
                resolve_member_code_at_timestamp(
                    customer_code=customer_code,
                    event_ts=paid_at,
                    mapping_lookup=(
                        membership_lookup
                    ),
                )
            )

            order_code = (
                f"{code_prefix}"
                f"{order_number:0{code_width}d}"
            )

            rows.append(
                {
                    "order_code": order_code,
                    "customer_code": (
                        customer_code
                    ),
                    "channel_code": (
                        channel_code
                    ),
                    "shipping_region_code": (
                        shipping_region_code
                    ),
                    "campaign_code": (
                        campaign_code
                    ),
                    "order_created_at": (
                        order_created_at
                    ),
                    "creation_daypart": (
                        creation_daypart
                    ),
                    "paid_at": paid_at,
                    "cancelled_at": (
                        cancelled_at
                    ),
                    "order_status": (
                        order_status
                    ),
                    "cancellation_reason": (
                        cancellation_reason
                    ),
                    "member_code_at_payment": (
                        member_code_at_payment
                    ),
                    "shipping_region_source": (
                        shipping_region_source
                    ),
                }
            )

            order_number += 1

    return rows


def validate_order_header_event_rows(
    rows: list[dict[str, Any]],
    manifest: dict[str, Any],
    reference_data: ReferenceData,
    window: GenerationWindow,
    daily_allocations: list[
        dict[str, Any]
    ],
    marketing_spend_rows: list[
        dict[str, Any]
    ],
    customer_profiles: dict[
        str,
        CustomerSimulationProfile,
    ],
) -> None:
    """
    校验订单头事件的数量、时间、实体和确定性。
    """
    _, profile = get_active_scale_profile(
        manifest
    )

    expected_count = profile[
        "expected_orders"
    ]

    if len(rows) != expected_count:
        raise ValueError(
            "订单头事件数量不正确："
            f"expected={expected_count}, "
            f"actual={len(rows)}"
        )

    order_codes = [
        row["order_code"]
        for row in rows
    ]

    if len(order_codes) != len(
        set(order_codes)
    ):
        raise ValueError(
            "订单头事件存在重复 order_code。"
        )

    valid_customers = {
        row["customer_code"]: row
        for row in reference_data.customers
    }

    valid_channels = {
        row["channel_code"]
        for row in reference_data.channels
        if (
            row["is_active"]
            and row["is_sales_channel"]
        )
    }

    valid_regions = {
        row["region_code"]
        for row in reference_data.regions
    }

    valid_campaigns = {
        row["campaign_code"]: row
        for row in reference_data.campaigns
        if row["is_active"]
    }

    valid_member_codes = {
        row["member_code"]
        for row in (
            reference_data.
            membership_accounts
        )
    }

    allocation_counts = {
        row["order_date"]:
            row["allocated_orders"]
        for row in daily_allocations
    }

    actual_date_counts = Counter()

    paid_count = 0
    cancelled_count = 0
    paid_tail_count = 0

    for index, row in enumerate(rows):
        customer = valid_customers.get(
            row["customer_code"]
        )

        if customer is None:
            raise ValueError(
                "订单引用不存在的客户："
                f"index={index}"
            )

        if customer[
            "customer_status"
        ] != "active":
            raise ValueError(
                "订单引用非 active 客户："
                f"index={index}, "
                f"customer="
                f"{row['customer_code']}"
            )

        created_at = row[
            "order_created_at"
        ]

        if (
            created_at.date()
            < customer["first_seen_date"]
        ):
            raise ValueError(
                "订单早于客户首次出现日期："
                f"index={index}"
            )

        if not (
            window.business_start_date
            <= created_at.date()
            <= window.business_end_date
        ):
            raise ValueError(
                "订单创建时间超出业务窗口："
                f"index={index}, "
                f"created_at={created_at}"
            )

        actual_date_counts[
            created_at.date()
        ] += 1

        if row[
            "channel_code"
        ] not in valid_channels:
            raise ValueError(
                "订单引用非启用销售渠道："
                f"index={index}"
            )

        if row[
            "shipping_region_code"
        ] not in valid_regions:
            raise ValueError(
                "订单引用无效收货地区："
                f"index={index}"
            )

        campaign_code = row[
            "campaign_code"
        ]

        if campaign_code is not None:
            campaign = valid_campaigns.get(
                campaign_code
            )

            if (
                campaign is None
                or campaign[
                    "campaign_type"
                ]
                != "major_promotion"
                or not (
                    campaign["start_date"]
                    <= created_at.date()
                    <= campaign["end_date"]
                )
            ):
                raise ValueError(
                    "订单主要活动归因无效："
                    f"index={index}, "
                    f"campaign={campaign_code}"
                )

        paid_at = row["paid_at"]
        cancelled_at = row[
            "cancelled_at"
        ]

        if row["order_status"] == "paid":
            paid_count += 1

            if paid_at is None:
                raise ValueError(
                    "paid 订单必须包含 paid_at。"
                )

            if paid_at < created_at:
                raise ValueError(
                    "paid_at 早于 "
                    "order_created_at。"
                )

            if (
                paid_at.date()
                > window.business_end_date
            ):
                paid_tail_count += 1

            if cancelled_at is not None:
                raise ValueError(
                    "paid 订单不能包含"
                    " cancelled_at。"
                )

            member_code = row[
                "member_code_at_payment"
            ]

            if (
                member_code is not None
                and member_code
                    not in valid_member_codes
            ):
                raise ValueError(
                    "订单支付会员编码无效："
                    f"index={index}"
                )

        elif (
            row["order_status"]
            == "cancelled"
        ):
            cancelled_count += 1

            if paid_at is not None:
                raise ValueError(
                    "cancelled 订单不能"
                    "包含 paid_at。"
                )

            if (
                cancelled_at is None
                or cancelled_at < created_at
            ):
                raise ValueError(
                    "cancelled 订单的"
                    "取消时间无效。"
                )

            if (
                row[
                    "member_code_at_payment"
                ]
                is not None
            ):
                raise ValueError(
                    "未支付订单不能生成"
                    "支付时点会员编码。"
                )

        else:
            raise ValueError(
                "订单头 Preview 出现"
                "未知最终状态："
                f"{row['order_status']}"
            )

    if paid_count == 0:
        raise ValueError(
            "订单头事件没有支付成功订单。"
        )

    if cancelled_count == 0:
        raise ValueError(
            "订单头事件没有取消订单。"
        )

    if paid_tail_count != 0:
        raise ValueError(
            "2026-01 观察尾窗出现"
            "新支付订单："
            f"{paid_tail_count}"
        )

    if (
        dict(actual_date_counts)
        != allocation_counts
    ):
        raise ValueError(
            "订单头日期数量与"
            "日级分配结果不一致。"
        )

    repeated_rows = (
        build_order_header_event_rows(
            manifest=manifest,
            reference_data=reference_data,
            window=window,
            daily_allocations=(
                daily_allocations
            ),
            marketing_spend_rows=(
                marketing_spend_rows
            ),
            customer_profiles=(
                customer_profiles
            ),
        )
    )

    if rows != repeated_rows:
        raise ValueError(
            "订单头事件确定性校验失败。"
        )


def preview_order_headers(
    manifest: dict[str, Any],
) -> None:
    """
    预览订单头事件，不写入 fact_orders。
    """
    window = build_generation_window(
        manifest
    )

    with engine.connect() as connection:
        reference_data = load_reference_data(
            connection
        )

        validate_reference_data(
            reference_data=reference_data,
            manifest=manifest,
            window=window,
        )

        marketing_spend_rows = (
            load_marketing_spend_rows(
                connection
            )
        )

        order_count = connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM beauty_bi_v2.fact_orders
                """
            )
        ).scalar_one()

        order_item_count = (
            connection.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM
                        beauty_bi_v2.
                        fact_order_items
                    """
                )
            ).scalar_one()
        )

    if (
        order_count != 0
        or order_item_count != 0
    ):
        raise RuntimeError(
            "订单头 Preview 要求订单与"
            "订单明细表为空："
            f"orders={order_count}, "
            f"items={order_item_count}"
        )

    validate_marketing_spend_rows(
        rows=marketing_spend_rows,
        manifest=manifest,
        reference_data=reference_data,
        window=window,
    )

    customer_profiles = (
        build_customer_simulation_profiles(
            manifest=manifest,
            reference_data=reference_data,
        )
    )

    product_profiles = (
        build_product_simulation_profiles(
            manifest=manifest,
            reference_data=reference_data,
        )
    )

    validate_simulation_profiles(
        customer_profiles=customer_profiles,
        product_profiles=product_profiles,
        manifest=manifest,
        reference_data=reference_data,
    )

    daily_allocations = (
        build_daily_order_allocations(
            manifest=manifest,
            reference_data=reference_data,
            window=window,
            marketing_spend_rows=(
                marketing_spend_rows
            ),
        )
    )

    validate_daily_order_allocations(
        rows=daily_allocations,
        manifest=manifest,
        reference_data=reference_data,
        window=window,
        marketing_spend_rows=(
            marketing_spend_rows
        ),
    )

    rows = build_order_header_event_rows(
        manifest=manifest,
        reference_data=reference_data,
        window=window,
        daily_allocations=(
            daily_allocations
        ),
        marketing_spend_rows=(
            marketing_spend_rows
        ),
        customer_profiles=(
            customer_profiles
        ),
    )

    validate_order_header_event_rows(
        rows=rows,
        manifest=manifest,
        reference_data=reference_data,
        window=window,
        daily_allocations=(
            daily_allocations
        ),
        marketing_spend_rows=(
            marketing_spend_rows
        ),
        customer_profiles=(
            customer_profiles
        ),
    )

    status_counts = Counter(
        row["order_status"]
        for row in rows
    )

    channel_counts = Counter(
        row["channel_code"]
        for row in rows
    )

    daypart_counts = Counter(
        row["creation_daypart"]
        for row in rows
    )

    shipping_source_counts = Counter(
        row["shipping_region_source"]
        for row in rows
    )

    campaign_attributed_count = sum(
        row["campaign_code"] is not None
        for row in rows
    )

    paid_member_count = sum(
        (
            row["paid_at"] is not None
            and row[
                "member_code_at_payment"
            ] is not None
        )
        for row in rows
    )

    cancellation_reason_counts = Counter(
        row["cancellation_reason"]
        for row in rows
        if (
            row["cancellation_reason"]
            is not None
        )
    )

    paid_at_values = [
        row["paid_at"]
        for row in rows
        if row["paid_at"] is not None
    ]

    cancelled_at_values = [
        row["cancelled_at"]
        for row in rows
        if row["cancelled_at"] is not None
    ]

    print(
        "order header event preview passed."
    )
    print(f"Total orders: {len(rows)}")
    print(
        "Order status counts: "
        f"{dict(status_counts)}"
    )
    print(
        "Sales channel counts: "
        f"{dict(channel_counts)}"
    )
    print(
        "Creation daypart counts: "
        f"{dict(daypart_counts)}"
    )
    print(
        "Shipping source counts: "
        f"{dict(shipping_source_counts)}"
    )
    print(
        "Major-campaign attributed orders: "
        f"{campaign_attributed_count}"
    )
    print(
        "Paid orders with membership mapping: "
        f"{paid_member_count}"
    )
    print(
        "Cancellation reason counts: "
        f"{dict(cancellation_reason_counts)}"
    )
    order_created_values = [
        row["order_created_at"]
        for row in rows
    ]

    print(
        "Order-created range: "
        f"{min(order_created_values)} -> "
        f"{max(order_created_values)}"
    )
    print(
        "Paid-at range: "
        f"{min(paid_at_values)} -> "
        f"{max(paid_at_values)}"
    )
    print(
        "Cancelled-at range: "
        f"{min(cancelled_at_values)} -> "
        f"{max(cancelled_at_values)}"
    )
    print(
        "Observation-tail paid orders: 0"
    )
    print(
        "Amounts generated: no"
    )
    print(
        "Delivered-at generated: no"
    )
    print(
        "Member-level snapshot generated: no"
    )
    print(f"First row: {rows[0]}")
    print(f"Last row: {rows[-1]}")
    print("Exact-total check: passed.")
    print("Deterministic check: passed.")



def choose_distribution_value(
    rng: random.Random,
    distribution: dict[Any, Any],
    field_name: str,
) -> Any:
    """
    从 Manifest 概率分布中抽取一个键。
    """
    weighted_items = [
        (
            item_value,
            Decimal(str(probability)),
        )
        for item_value, probability
        in distribution.items()
    ]

    selected_value = _weighted_choice(
        rng,
        weighted_items,
    )

    if selected_value not in distribution:
        raise ValueError(
            f"{field_name} 抽样结果无效："
            f"{selected_value!r}"
        )

    return selected_value


def build_promotion_contract_lookup(
    manifest: dict[str, Any],
    reference_data: ReferenceData,
) -> dict[str, dict[str, Any]]:
    """
    合并 Manifest 中的 campaign_code 与数据库促销维度。

    dim_promotion 不持久化 campaign_code，因此交易生成必须从
    Manifest 恢复这条稳定业务关联。
    """
    database_lookup = {
        row["promotion_code"]: row
        for row in reference_data.promotions
    }

    result: dict[str, dict[str, Any]] = {}

    for index, promotion in enumerate(
        manifest[
            "fixed_dimensions"
        ][
            "promotions"
        ]
    ):
        promotion_code = promotion[
            "promotion_code"
        ].strip()

        database_row = database_lookup.get(
            promotion_code
        )

        if database_row is None:
            raise ValueError(
                "Manifest 促销在数据库中不存在："
                f"{promotion_code}"
            )

        parsed_start_date = parse_manifest_date(
            promotion["start_date"],
            (
                "fixed_dimensions.promotions"
                f"[{index}].start_date"
            ),
        )

        parsed_end_date = parse_manifest_date(
            promotion["end_date"],
            (
                "fixed_dimensions.promotions"
                f"[{index}].end_date"
            ),
        )

        manifest_discount_rate = Decimal(
            str(promotion["discount_rate"])
        ).quantize(
            Decimal("0.0001")
        )

        if (
            database_row["promotion_type"]
            != promotion[
                "promotion_type"
            ].strip()
            or database_row["discount_rate"]
                != manifest_discount_rate
            or database_row["start_date"]
                != parsed_start_date
            or database_row["end_date"]
                != parsed_end_date
            or database_row["is_active"]
                != promotion["is_active"]
        ):
            raise ValueError(
                "Manifest 与数据库促销维度"
                "内容不一致："
                f"{promotion_code}"
            )

        result[promotion_code] = {
            **database_row,
            "campaign_code": promotion[
                "campaign_code"
            ].strip(),
        }

    if set(result) != set(database_lookup):
        raise ValueError(
            "Manifest 与数据库促销编码集合"
            "不一致。"
        )

    return result


def build_product_context_candidates(
    order_date: date,
    shipping_region_group: str,
    reference_data: ReferenceData,
    product_profiles: dict[
        str,
        ProductSimulationProfile,
    ],
    manifest: dict[str, Any],
) -> list[
    tuple[dict[str, Any], Decimal]
]:
    """
    构造订单时点可购买商品及上下文权重。

    商品权重：
    hidden demand weight
    × seasonal multiplier
    × region multiplier
    """
    context_config = manifest[
        "simulation_profiles"
    ][
        "demand_context"
    ]

    default_multiplier = Decimal(
        str(
            context_config[
                "default_multiplier"
            ]
        )
    )

    maximum_combined_multiplier = Decimal(
        str(
            context_config[
                "maximum_combined_multiplier"
            ]
        )
    )

    candidates: list[
        tuple[dict[str, Any], Decimal]
    ] = []

    for product in reference_data.products:
        if not product["is_active"]:
            continue

        if (
            product["launch_date"]
            > order_date
        ):
            continue

        seasonal_multiplier = (
            default_multiplier
        )

        for rule in context_config[
            "seasonal_rules"
        ]:
            if (
                product["category"]
                == rule["category"].strip()
                and order_date.month
                    in rule["months"]
            ):
                seasonal_multiplier *= Decimal(
                    str(rule["multiplier"])
                )

        region_multiplier = (
            default_multiplier
        )

        for rule in context_config[
            "region_rules"
        ]:
            if (
                product["category"]
                == rule["category"].strip()
                and shipping_region_group
                    in {
                        value.strip()
                        for value in (
                            rule[
                                "region_groups"
                            ]
                        )
                    }
            ):
                region_multiplier *= Decimal(
                    str(rule["multiplier"])
                )

        combined_context_multiplier = min(
            (
                seasonal_multiplier
                * region_multiplier
            ),
            maximum_combined_multiplier,
        )

        profile = product_profiles[
            product["sku_code"]
        ]

        final_weight = (
            profile.demand_weight
            * combined_context_multiplier
        )

        if final_weight <= 0:
            raise ValueError(
                "商品上下文权重必须为正："
                f"sku={product['sku_code']}"
            )

        candidates.append(
            (
                product,
                final_weight,
            )
        )

    if not candidates:
        raise ValueError(
            "订单时点没有可用商品："
            f"date={order_date}, "
            "shipping_region_group="
            f"{shipping_region_group}"
        )

    return candidates


def choose_distinct_products(
    rng: random.Random,
    weighted_candidates: list[
        tuple[dict[str, Any], Decimal]
    ],
    item_count: int,
) -> list[dict[str, Any]]:
    """
    按权重无放回选择商品，保证同一订单不重复 SKU。
    """
    if item_count > len(
        weighted_candidates
    ):
        raise ValueError(
            "订单明细数量超过可选商品数："
            f"item_count={item_count}, "
            "candidate_count="
            f"{len(weighted_candidates)}"
        )

    remaining = list(
        weighted_candidates
    )

    selected_products: list[
        dict[str, Any]
    ] = []

    for _ in range(item_count):
        items, cumulative_weights = (
            build_cumulative_weights(
                remaining,
                "order item product",
            )
        )

        selected_product = (
            choose_from_cumulative_weights(
                rng=rng,
                items=items,
                cumulative_weights=(
                    cumulative_weights
                ),
            )
        )

        selected_products.append(
            selected_product
        )

        selected_code = (
            selected_product[
                "sku_code"
            ]
        )

        remaining = [
            (
                product,
                weight,
            )
            for product, weight in remaining
            if (
                product["sku_code"]
                != selected_code
            )
        ]

    return selected_products


def resolve_pricing_campaign(
    order_date: date,
    reference_data: ReferenceData,
) -> dict[str, Any]:
    """
    定价优先使用当日主要活动；没有主要活动时使用 always_on。
    """
    major_campaign = (
        resolve_major_campaign_for_date(
            order_date=order_date,
            reference_data=reference_data,
        )
    )

    if major_campaign is not None:
        return major_campaign

    always_on_candidates = [
        row
        for row in reference_data.campaigns
        if (
            row["is_active"]
            and row["campaign_type"]
                == "always_on"
            and row["start_date"]
                <= order_date
                <= row["end_date"]
        )
    ]

    if len(always_on_candidates) != 1:
        raise ValueError(
            "订单定价日期必须且只能命中"
            "一个 always_on Campaign："
            f"date={order_date}, "
            f"matched="
            f"{[row['campaign_code'] for row in always_on_candidates]}"
        )

    return always_on_candidates[0]


def choose_item_promotion(
    rng: random.Random,
    order_date: date,
    reference_data: ReferenceData,
    promotion_lookup: dict[
        str,
        dict[str, Any],
    ],
    manifest: dict[str, Any],
) -> dict[str, Any] | None:
    """
    根据当日定价 Campaign 类型决定促销应用概率。

    P0 每个 Campaign 对应一个固定促销方案，且每条明细最多
    使用一个主要促销。
    """
    pricing_campaign = (
        resolve_pricing_campaign(
            order_date=order_date,
            reference_data=reference_data,
        )
    )

    campaign_type = pricing_campaign[
        "campaign_type"
    ]

    probability = manifest[
        "order_generation"
    ][
        "item_generation"
    ][
        "promotion_application"
    ][
        "probability_by_campaign_type"
    ][
        campaign_type
    ]

    if rng.random() >= probability:
        return None

    candidates = [
        promotion
        for promotion in promotion_lookup.values()
        if (
            promotion["is_active"]
            and promotion[
                "campaign_code"
            ]
            == pricing_campaign[
                "campaign_code"
            ]
            and promotion["start_date"]
                <= order_date
                <= promotion["end_date"]
        )
    ]

    if len(candidates) != 1:
        raise ValueError(
            "定价 Campaign 必须且只能"
            "对应一个有效促销："
            f"campaign="
            f"{pricing_campaign['campaign_code']}, "
            f"date={order_date}, "
            f"matched="
            f"{[row['promotion_code'] for row in candidates]}"
        )

    return candidates[0]


def build_order_item_rows_and_totals(
    order_rows: list[dict[str, Any]],
    manifest: dict[str, Any],
    reference_data: ReferenceData,
    product_profiles: dict[
        str,
        ProductSimulationProfile,
    ],
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    """
    生成订单明细，并由明细汇总订单头金额。

    返回：
    1. order item 暂存行；
    2. 增加 order_*_amount 的订单头暂存行。
    """
    item_config = manifest[
        "order_generation"
    ][
        "item_generation"
    ]

    item_count_distribution = (
        item_config[
            "item_count_distribution"
        ]
    )

    quantity_distribution = (
        item_config[
            "quantity_distribution"
        ]
    )

    promotion_lookup = (
        build_promotion_contract_lookup(
            manifest=manifest,
            reference_data=reference_data,
        )
    )

    region_group_lookup = {
        row["region_code"]:
            row["region_group"]
        for row in reference_data.regions
    }

    product_context_cache: dict[
        tuple[date, str],
        list[
            tuple[
                dict[str, Any],
                Decimal,
            ]
        ],
    ] = {}

    item_rng = build_rng(
        manifest,
        "order_items",
    )

    item_rows: list[
        dict[str, Any]
    ] = []

    enriched_order_rows: list[
        dict[str, Any]
    ] = []

    for order in order_rows:
        order_date = order[
            "order_created_at"
        ].date()

        shipping_region_code = order[
            "shipping_region_code"
        ]

        shipping_region_group = (
            region_group_lookup.get(
                shipping_region_code
            )
        )

        if shipping_region_group is None:
            raise ValueError(
                "订单收货地区无法解析"
                " region_group："
                f"{shipping_region_code}"
            )

        context_key = (
            order_date,
            shipping_region_group,
        )

        weighted_candidates = (
            product_context_cache.get(
                context_key
            )
        )

        if weighted_candidates is None:
            weighted_candidates = (
                build_product_context_candidates(
                    order_date=order_date,
                    shipping_region_group=(
                        shipping_region_group
                    ),
                    reference_data=(
                        reference_data
                    ),
                    product_profiles=(
                        product_profiles
                    ),
                    manifest=manifest,
                )
            )

            product_context_cache[
                context_key
            ] = weighted_candidates

        item_count = int(
            choose_distribution_value(
                rng=item_rng,
                distribution=(
                    item_count_distribution
                ),
                field_name=(
                    "item_count_distribution"
                ),
            )
        )

        selected_products = (
            choose_distinct_products(
                rng=item_rng,
                weighted_candidates=(
                    weighted_candidates
                ),
                item_count=item_count,
            )
        )

        order_list_amount = Decimal("0")
        order_discount_amount = (
            Decimal("0")
        )
        order_paid_amount = Decimal("0")

        for line_number, product in enumerate(
            selected_products,
            start=1,
        ):
            quantity = int(
                choose_distribution_value(
                    rng=item_rng,
                    distribution=(
                        quantity_distribution
                    ),
                    field_name=(
                        "quantity_distribution"
                    ),
                )
            )

            promotion = (
                choose_item_promotion(
                    rng=item_rng,
                    order_date=order_date,
                    reference_data=(
                        reference_data
                    ),
                    promotion_lookup=(
                        promotion_lookup
                    ),
                    manifest=manifest,
                )
            )

            unit_list_price = quantize_money(
                Decimal(
                    str(
                        product[
                            "list_price"
                        ]
                    )
                )
            )

            if promotion is None:
                promotion_code = None
                unit_paid_price = (
                    unit_list_price
                )
            else:
                promotion_code = promotion[
                    "promotion_code"
                ]

                unit_paid_price = (
                    quantize_money(
                        unit_list_price
                        * promotion[
                            "discount_rate"
                        ]
                    )
                )

            product_profile = (
                product_profiles[
                    product["sku_code"]
                ]
            )

            unit_cost_at_order = (
                product_profile.unit_cost
            )

            item_list_amount = (
                quantize_money(
                    unit_list_price
                    * quantity
                )
            )

            item_paid_amount = (
                quantize_money(
                    unit_paid_price
                    * quantity
                )
            )

            item_discount_amount = (
                quantize_money(
                    item_list_amount
                    - item_paid_amount
                )
            )

            item_cost_amount = (
                quantize_money(
                    unit_cost_at_order
                    * quantity
                )
            )

            item_rows.append(
                {
                    "order_code": order[
                        "order_code"
                    ],
                    "line_number": (
                        line_number
                    ),
                    "sku_code": product[
                        "sku_code"
                    ],
                    "promotion_code": (
                        promotion_code
                    ),
                    "quantity": quantity,
                    "unit_list_price": (
                        unit_list_price
                    ),
                    "unit_paid_price": (
                        unit_paid_price
                    ),
                    "item_list_amount": (
                        item_list_amount
                    ),
                    "item_discount_amount": (
                        item_discount_amount
                    ),
                    "item_paid_amount": (
                        item_paid_amount
                    ),
                    "unit_cost_at_order": (
                        unit_cost_at_order
                    ),
                    "item_cost_amount": (
                        item_cost_amount
                    ),
                    "product_category": (
                        product["category"]
                    ),
                    "product_subcategory": (
                        product[
                            "subcategory"
                        ]
                    ),
                }
            )

            order_list_amount += (
                item_list_amount
            )

            order_discount_amount += (
                item_discount_amount
            )

            order_paid_amount += (
                item_paid_amount
            )

        enriched_order_rows.append(
            {
                **order,
                "order_list_amount": (
                    quantize_money(
                        order_list_amount
                    )
                ),
                "order_discount_amount": (
                    quantize_money(
                        order_discount_amount
                    )
                ),
                "order_paid_amount": (
                    quantize_money(
                        order_paid_amount
                    )
                ),
            }
        )

    return (
        item_rows,
        enriched_order_rows,
    )


def validate_order_item_rows_and_totals(
    item_rows: list[dict[str, Any]],
    enriched_order_rows: list[
        dict[str, Any]
    ],
    original_order_rows: list[
        dict[str, Any]
    ],
    manifest: dict[str, Any],
    reference_data: ReferenceData,
    product_profiles: dict[
        str,
        ProductSimulationProfile,
    ],
) -> None:
    """
    校验订单明细 Grain、公式、促销和订单头汇总。
    """
    if not item_rows:
        raise ValueError(
            "订单明细生成结果不能为空。"
        )

    if (
        len(enriched_order_rows)
        != len(original_order_rows)
    ):
        raise ValueError(
            "订单金额汇总后的订单行数"
            "发生变化。"
        )

    original_order_lookup = {
        row["order_code"]: row
        for row in original_order_rows
    }

    enriched_order_lookup = {
        row["order_code"]: row
        for row in enriched_order_rows
    }

    if (
        set(enriched_order_lookup)
        != set(original_order_lookup)
    ):
        raise ValueError(
            "订单金额汇总后的订单编码"
            "集合发生变化。"
        )

    product_lookup = {
        row["sku_code"]: row
        for row in reference_data.products
    }

    promotion_lookup = (
        build_promotion_contract_lookup(
            manifest=manifest,
            reference_data=reference_data,
        )
    )

    item_count_distribution = manifest[
        "order_generation"
    ][
        "item_generation"
    ][
        "item_count_distribution"
    ]

    quantity_distribution = manifest[
        "order_generation"
    ][
        "item_generation"
    ][
        "quantity_distribution"
    ]

    minimum_item_count = min(
        item_count_distribution
    )

    maximum_item_count = max(
        item_count_distribution
    )

    valid_quantities = set(
        quantity_distribution
    )

    item_rows_by_order: defaultdict[
        str,
        list[dict[str, Any]],
    ] = defaultdict(list)

    item_grains: set[
        tuple[str, int]
    ] = set()

    for index, row in enumerate(item_rows):
        grain = (
            row["order_code"],
            row["line_number"],
        )

        if grain in item_grains:
            raise ValueError(
                "订单明细存在重复暂存 Grain："
                f"{grain}"
            )

        item_grains.add(grain)

        order = original_order_lookup.get(
            row["order_code"]
        )

        if order is None:
            raise ValueError(
                "订单明细引用不存在的订单："
                f"index={index}"
            )

        product = product_lookup.get(
            row["sku_code"]
        )

        if product is None:
            raise ValueError(
                "订单明细引用不存在的商品："
                f"index={index}"
            )

        if not product["is_active"]:
            raise ValueError(
                "订单明细引用非 active 商品："
                f"index={index}"
            )

        if (
            product["launch_date"]
            > order[
                "order_created_at"
            ].date()
        ):
            raise ValueError(
                "订单明细引用尚未上市商品："
                f"index={index}"
            )

        if (
            row["quantity"]
            not in valid_quantities
        ):
            raise ValueError(
                "订单明细数量不在配置分布中："
                f"index={index}"
            )

        if (
            row["unit_list_price"]
            != quantize_money(
                Decimal(
                    str(
                        product[
                            "list_price"
                        ]
                    )
                )
            )
        ):
            raise ValueError(
                "订单明细吊牌价快照"
                "与商品维度不一致："
                f"index={index}"
            )

        profile = product_profiles[
            row["sku_code"]
        ]

        if (
            row["unit_cost_at_order"]
            != profile.unit_cost
        ):
            raise ValueError(
                "订单明细成本快照"
                "与隐藏画像不一致："
                f"index={index}"
            )

        promotion_code = row[
            "promotion_code"
        ]

        if promotion_code is None:
            expected_paid_price = row[
                "unit_list_price"
            ]
        else:
            promotion = (
                promotion_lookup.get(
                    promotion_code
                )
            )

            if promotion is None:
                raise ValueError(
                    "订单明细引用不存在的促销："
                    f"index={index}"
                )

            order_date = order[
                "order_created_at"
            ].date()

            if not (
                promotion["is_active"]
                and promotion["start_date"]
                    <= order_date
                    <= promotion["end_date"]
            ):
                raise ValueError(
                    "订单明细促销不在有效窗口："
                    f"index={index}"
                )

            expected_paid_price = (
                quantize_money(
                    row["unit_list_price"]
                    * promotion[
                        "discount_rate"
                    ]
                )
            )

        if (
            row["unit_paid_price"]
            != expected_paid_price
        ):
            raise ValueError(
                "订单明细实付单价不正确："
                f"index={index}"
            )

        if (
            row["unit_paid_price"]
            > row["unit_list_price"]
        ):
            raise ValueError(
                "订单明细实付单价超过吊牌价："
                f"index={index}"
            )

        expected_list_amount = (
            quantize_money(
                row["unit_list_price"]
                * row["quantity"]
            )
        )

        expected_paid_amount = (
            quantize_money(
                row["unit_paid_price"]
                * row["quantity"]
            )
        )

        expected_discount_amount = (
            quantize_money(
                expected_list_amount
                - expected_paid_amount
            )
        )

        expected_cost_amount = (
            quantize_money(
                row["unit_cost_at_order"]
                * row["quantity"]
            )
        )

        if (
            row["item_list_amount"]
            != expected_list_amount
            or row["item_paid_amount"]
                != expected_paid_amount
            or row[
                "item_discount_amount"
            ]
                != expected_discount_amount
            or row["item_cost_amount"]
                != expected_cost_amount
        ):
            raise ValueError(
                "订单明细金额公式不正确："
                f"index={index}"
            )

        item_rows_by_order[
            row["order_code"]
        ].append(row)

    if set(item_rows_by_order) != set(
        original_order_lookup
    ):
        raise ValueError(
            "并非每张订单都生成了订单明细。"
        )

    for order_code, rows in (
        item_rows_by_order.items()
    ):
        if not (
            minimum_item_count
            <= len(rows)
            <= maximum_item_count
        ):
            raise ValueError(
                "订单明细数量超出配置范围："
                f"order={order_code}, "
                f"count={len(rows)}"
            )

        line_numbers = [
            row["line_number"]
            for row in rows
        ]

        if line_numbers != list(
            range(1, len(rows) + 1)
        ):
            raise ValueError(
                "订单明细 line_number "
                "不是连续序列："
                f"order={order_code}"
            )

        sku_codes = [
            row["sku_code"]
            for row in rows
        ]

        if len(sku_codes) != len(
            set(sku_codes)
        ):
            raise ValueError(
                "同一订单出现重复商品："
                f"order={order_code}"
            )

        enriched_order = (
            enriched_order_lookup[
                order_code
            ]
        )

        expected_order_list_amount = (
            quantize_money(
                sum(
                    (
                        row[
                            "item_list_amount"
                        ]
                        for row in rows
                    ),
                    Decimal("0"),
                )
            )
        )

        expected_order_discount_amount = (
            quantize_money(
                sum(
                    (
                        row[
                            "item_discount_amount"
                        ]
                        for row in rows
                    ),
                    Decimal("0"),
                )
            )
        )

        expected_order_paid_amount = (
            quantize_money(
                sum(
                    (
                        row[
                            "item_paid_amount"
                        ]
                        for row in rows
                    ),
                    Decimal("0"),
                )
            )
        )

        if (
            enriched_order[
                "order_list_amount"
            ]
            != expected_order_list_amount
            or enriched_order[
                "order_discount_amount"
            ]
                != (
                    expected_order_discount_amount
                )
            or enriched_order[
                "order_paid_amount"
            ]
                != expected_order_paid_amount
        ):
            raise ValueError(
                "订单头金额不等于明细汇总："
                f"order={order_code}"
            )

        if (
            enriched_order[
                "order_discount_amount"
            ]
            != (
                enriched_order[
                    "order_list_amount"
                ]
                - enriched_order[
                    "order_paid_amount"
                ]
            )
        ):
            raise ValueError(
                "订单头金额关系不正确："
                f"order={order_code}"
            )

    (
        repeated_item_rows,
        repeated_enriched_orders,
    ) = build_order_item_rows_and_totals(
        order_rows=original_order_rows,
        manifest=manifest,
        reference_data=reference_data,
        product_profiles=product_profiles,
    )

    if item_rows != repeated_item_rows:
        raise ValueError(
            "订单明细确定性校验失败。"
        )

    if (
        enriched_order_rows
        != repeated_enriched_orders
    ):
        raise ValueError(
            "订单头金额确定性校验失败。"
        )


def preview_order_items(
    manifest: dict[str, Any],
) -> None:
    """
    预览订单明细和订单金额，不写入数据库。
    """
    window = build_generation_window(
        manifest
    )

    with engine.connect() as connection:
        reference_data = load_reference_data(
            connection
        )

        validate_reference_data(
            reference_data=reference_data,
            manifest=manifest,
            window=window,
        )

        marketing_spend_rows = (
            load_marketing_spend_rows(
                connection
            )
        )

        order_count = connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM beauty_bi_v2.fact_orders
                """
            )
        ).scalar_one()

        order_item_count = (
            connection.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM
                        beauty_bi_v2.
                        fact_order_items
                    """
                )
            ).scalar_one()
        )

    if (
        order_count != 0
        or order_item_count != 0
    ):
        raise RuntimeError(
            "订单明细 Preview 要求"
            "订单与明细表为空："
            f"orders={order_count}, "
            f"items={order_item_count}"
        )

    validate_marketing_spend_rows(
        rows=marketing_spend_rows,
        manifest=manifest,
        reference_data=reference_data,
        window=window,
    )

    customer_profiles = (
        build_customer_simulation_profiles(
            manifest=manifest,
            reference_data=reference_data,
        )
    )

    product_profiles = (
        build_product_simulation_profiles(
            manifest=manifest,
            reference_data=reference_data,
        )
    )

    validate_simulation_profiles(
        customer_profiles=customer_profiles,
        product_profiles=product_profiles,
        manifest=manifest,
        reference_data=reference_data,
    )

    daily_allocations = (
        build_daily_order_allocations(
            manifest=manifest,
            reference_data=reference_data,
            window=window,
            marketing_spend_rows=(
                marketing_spend_rows
            ),
        )
    )

    validate_daily_order_allocations(
        rows=daily_allocations,
        manifest=manifest,
        reference_data=reference_data,
        window=window,
        marketing_spend_rows=(
            marketing_spend_rows
        ),
    )

    order_rows = (
        build_order_header_event_rows(
            manifest=manifest,
            reference_data=reference_data,
            window=window,
            daily_allocations=(
                daily_allocations
            ),
            marketing_spend_rows=(
                marketing_spend_rows
            ),
            customer_profiles=(
                customer_profiles
            ),
        )
    )

    validate_order_header_event_rows(
        rows=order_rows,
        manifest=manifest,
        reference_data=reference_data,
        window=window,
        daily_allocations=(
            daily_allocations
        ),
        marketing_spend_rows=(
            marketing_spend_rows
        ),
        customer_profiles=(
            customer_profiles
        ),
    )

    (
        item_rows,
        enriched_order_rows,
    ) = build_order_item_rows_and_totals(
        order_rows=order_rows,
        manifest=manifest,
        reference_data=reference_data,
        product_profiles=product_profiles,
    )

    validate_order_item_rows_and_totals(
        item_rows=item_rows,
        enriched_order_rows=(
            enriched_order_rows
        ),
        original_order_rows=order_rows,
        manifest=manifest,
        reference_data=reference_data,
        product_profiles=product_profiles,
    )

    item_count_by_order = Counter(
        row_count
        for row_count in (
            Counter(
                row["order_code"]
                for row in item_rows
            ).values()
        )
    )

    quantity_counts = Counter(
        row["quantity"]
        for row in item_rows
    )

    promotion_counts = Counter(
        (
            row["promotion_code"]
            if row["promotion_code"]
                is not None
            else "NO_PROMOTION"
        )
        for row in item_rows
    )

    category_quantity = Counter()

    for row in item_rows:
        category_quantity[
            row["product_category"]
        ] += row["quantity"]

    total_list_amount = sum(
        (
            row["order_list_amount"]
            for row in enriched_order_rows
        ),
        Decimal("0"),
    )

    total_discount_amount = sum(
        (
            row[
                "order_discount_amount"
            ]
            for row in enriched_order_rows
        ),
        Decimal("0"),
    )

    total_paid_amount = sum(
        (
            row["order_paid_amount"]
            for row in enriched_order_rows
        ),
        Decimal("0"),
    )

    total_cost_amount = sum(
        (
            row["item_cost_amount"]
            for row in item_rows
        ),
        Decimal("0"),
    )

    paid_order_amount = sum(
        (
            row["order_paid_amount"]
            for row in enriched_order_rows
            if row["paid_at"] is not None
        ),
        Decimal("0"),
    )

    cancelled_order_amount = sum(
        (
            row["order_paid_amount"]
            for row in enriched_order_rows
            if row["paid_at"] is None
        ),
        Decimal("0"),
    )

    print(
        "order item preview passed."
    )
    print(
        "Orders with amounts: "
        f"{len(enriched_order_rows)}"
    )
    print(
        "Total order items: "
        f"{len(item_rows)}"
    )
    print(
        "Item-count distribution by order: "
        f"{dict(item_count_by_order)}"
    )
    print(
        "Quantity distribution by item: "
        f"{dict(quantity_counts)}"
    )
    print(
        "Promotion counts: "
        f"{dict(promotion_counts)}"
    )
    print(
        "Category quantity totals: "
        f"{dict(category_quantity)}"
    )
    print(
        "Order list amount total: "
        f"{quantize_money(total_list_amount)}"
    )
    print(
        "Order discount amount total: "
        f"{quantize_money(total_discount_amount)}"
    )
    print(
        "Order paid amount total: "
        f"{quantize_money(total_paid_amount)}"
    )
    print(
        "Item cost amount total: "
        f"{quantize_money(total_cost_amount)}"
    )
    print(
        "Paid-order amount total: "
        f"{quantize_money(paid_order_amount)}"
    )
    print(
        "Cancelled-order amount total "
        "(excluded from GMV): "
        f"{quantize_money(cancelled_order_amount)}"
    )
    print(
        "Order amount relation: passed."
    )
    print(
        "Item amount formulas: passed."
    )
    print(
        "Duplicate product within order: 0"
    )
    print(
        "Database writes performed: no"
    )
    print(f"First item: {item_rows[0]}")
    print(f"Last item: {item_rows[-1]}")
    print(
        "First enriched order: "
        f"{enriched_order_rows[0]}"
    )
    print(
        "Last enriched order: "
        f"{enriched_order_rows[-1]}"
    )
    print("Deterministic check: passed.")



def build_fulfillment_order_rows(
    order_rows: list[dict[str, Any]],
    manifest: dict[str, Any],
    reference_data: ReferenceData,
    window: GenerationWindow,
) -> list[dict[str, Any]]:
    """
    为支付成功订单生成发货与送达事件。

    shipped_at 是生成过程中的暂存事件，不写入 fact_orders；
    delivered_at 与最终 order_status 会写入订单事实表。
    """
    config = manifest[
        "fulfillment_generation"
    ]

    shipping_delay = config[
        "shipping_delay_hours"
    ]

    delivery_delay = config[
        "delivery_delay_days"
    ]

    remote_config = config[
        "remote_region_extra_delay_days"
    ]

    congestion_config = config[
        "campaign_congestion"
    ]

    observation_config = config[
        "observation_window"
    ]

    remote_region_groups = {
        value.strip()
        for value in remote_config[
            "region_groups"
        ]
    }

    region_group_lookup = {
        row["region_code"]:
            row["region_group"]
        for row in reference_data.regions
    }

    probability_by_family = (
        congestion_config[
            "extra_delay_probability_by_campaign_family"
        ]
    )

    congestion_extra_delay = (
        congestion_config[
            "extra_delay_days"
        ]
    )

    delivered_status = config[
        "final_status"
    ][
        "delivered_event_status"
    ].strip()

    incomplete_status = observation_config[
        "incomplete_after_observation_end_status"
    ].strip()

    observation_end_ts = (
        datetime.combine(
            window.observation_end_date,
            datetime.max.time(),
        ).replace(
            microsecond=0
        )
    )

    rng = build_rng(
        manifest,
        "fulfillment",
    )

    enriched_rows: list[
        dict[str, Any]
    ] = []

    for order in order_rows:
        if order["paid_at"] is None:
            enriched_rows.append(
                {
                    **order,
                    "shipped_at": None,
                    "delivered_at": None,
                    "base_delivery_delay_days": None,
                    "remote_extra_delay_days": 0,
                    "campaign_extra_delay_days": 0,
                    "fulfillment_campaign_family": None,
                }
            )
            continue

        paid_at = order["paid_at"]

        shipping_delay_seconds = rng.randint(
            int(
                shipping_delay[
                    "minimum"
                ]
                * 3600
            ),
            int(
                shipping_delay[
                    "maximum"
                ]
                * 3600
            ),
        )

        shipped_at = (
            paid_at
            + timedelta(
                seconds=shipping_delay_seconds
            )
        )

        base_delivery_delay_days = (
            rng.randint(
                delivery_delay[
                    "minimum"
                ],
                delivery_delay[
                    "maximum"
                ],
            )
        )

        shipping_region_group = (
            region_group_lookup.get(
                order[
                    "shipping_region_code"
                ]
            )
        )

        if shipping_region_group is None:
            raise ValueError(
                "履约无法解析收货地区组："
                f"{order['shipping_region_code']}"
            )

        remote_extra_delay_days = 0

        if (
            remote_config["enabled"]
            and shipping_region_group
                in remote_region_groups
        ):
            remote_extra_delay_days = (
                rng.randint(
                    remote_config[
                        "minimum"
                    ],
                    remote_config[
                        "maximum"
                    ],
                )
            )

        major_campaign = (
            resolve_major_campaign_for_date(
                order_date=(
                    order[
                        "order_created_at"
                    ].date()
                ),
                reference_data=reference_data,
            )
        )

        campaign_family: str | None = None
        campaign_extra_delay_days = 0

        if (
            congestion_config["enabled"]
            and major_campaign is not None
        ):
            campaign_family = (
                major_campaign[
                    "campaign_family"
                ]
            )

            probability = (
                probability_by_family[
                    campaign_family
                ]
            )

            if rng.random() < probability:
                campaign_extra_delay_days = (
                    rng.randint(
                        congestion_extra_delay[
                            "minimum"
                        ],
                        congestion_extra_delay[
                            "maximum"
                        ],
                    )
                )

        total_delivery_delay_days = (
            base_delivery_delay_days
            + remote_extra_delay_days
            + campaign_extra_delay_days
        )

        candidate_delivered_at = (
            shipped_at
            + timedelta(
                days=(
                    total_delivery_delay_days
                )
            )
        )

        if (
            candidate_delivered_at
            <= observation_end_ts
        ):
            delivered_at = (
                candidate_delivered_at
            )
            order_status = (
                delivered_status
            )
        else:
            delivered_at = None
            order_status = (
                incomplete_status
            )

        enriched_rows.append(
            {
                **order,
                "shipped_at": shipped_at,
                "delivered_at": delivered_at,
                "order_status": order_status,
                "base_delivery_delay_days": (
                    base_delivery_delay_days
                ),
                "remote_extra_delay_days": (
                    remote_extra_delay_days
                ),
                "campaign_extra_delay_days": (
                    campaign_extra_delay_days
                ),
                "fulfillment_campaign_family": (
                    campaign_family
                ),
            }
        )

    return enriched_rows


def validate_fulfillment_order_rows(
    rows: list[dict[str, Any]],
    source_order_rows: list[
        dict[str, Any]
    ],
    manifest: dict[str, Any],
    reference_data: ReferenceData,
    window: GenerationWindow,
) -> None:
    """
    校验履约时间、状态推进、观察尾窗和确定性。
    """
    if len(rows) != len(
        source_order_rows
    ):
        raise ValueError(
            "履约处理后订单行数发生变化。"
        )

    source_lookup = {
        row["order_code"]: row
        for row in source_order_rows
    }

    if {
        row["order_code"]
        for row in rows
    } != set(source_lookup):
        raise ValueError(
            "履约处理后订单编码集合"
            "发生变化。"
        )

    config = manifest[
        "fulfillment_generation"
    ]

    shipping_delay = config[
        "shipping_delay_hours"
    ]

    delivery_delay = config[
        "delivery_delay_days"
    ]

    remote_config = config[
        "remote_region_extra_delay_days"
    ]

    congestion_config = config[
        "campaign_congestion"
    ]

    delivered_status = config[
        "final_status"
    ][
        "delivered_event_status"
    ].strip()

    incomplete_status = config[
        "observation_window"
    ][
        "incomplete_after_observation_end_status"
    ].strip()

    observation_end_ts = (
        datetime.combine(
            window.observation_end_date,
            datetime.max.time(),
        ).replace(
            microsecond=0
        )
    )

    region_group_lookup = {
        row["region_code"]:
            row["region_group"]
        for row in reference_data.regions
    }

    remote_region_groups = {
        value.strip()
        for value in remote_config[
            "region_groups"
        ]
    }

    delivered_count = 0
    incomplete_count = 0
    cancelled_count = 0
    observation_tail_delivery_count = 0

    for index, row in enumerate(rows):
        source_order = source_lookup[
            row["order_code"]
        ]

        for field_name in {
            "customer_code",
            "channel_code",
            "shipping_region_code",
            "campaign_code",
            "order_created_at",
            "paid_at",
            "cancelled_at",
            "order_list_amount",
            "order_discount_amount",
            "order_paid_amount",
        }:
            if (
                row[field_name]
                != source_order[field_name]
            ):
                raise ValueError(
                    "履约处理错误修改了"
                    "非履约字段："
                    f"index={index}, "
                    f"field={field_name}"
                )

        paid_at = row["paid_at"]
        shipped_at = row[
            "shipped_at"
        ]
        delivered_at = row[
            "delivered_at"
        ]

        if paid_at is None:
            cancelled_count += 1

            if (
                row["order_status"]
                != "cancelled"
                or shipped_at is not None
                or delivered_at is not None
                or row[
                    "base_delivery_delay_days"
                ] is not None
                or row[
                    "remote_extra_delay_days"
                ] != 0
                or row[
                    "campaign_extra_delay_days"
                ] != 0
                or row[
                    "fulfillment_campaign_family"
                ] is not None
            ):
                raise ValueError(
                    "取消订单不能进入履约："
                    f"index={index}"
                )

            continue

        if shipped_at is None:
            raise ValueError(
                "支付订单必须生成"
                " shipped_at："
                f"index={index}"
            )

        shipping_delay_seconds = int(
            (
                shipped_at - paid_at
            ).total_seconds()
        )

        if not (
            shipping_delay[
                "minimum"
            ] * 3600
            <= shipping_delay_seconds
            <= shipping_delay[
                "maximum"
            ] * 3600
        ):
            raise ValueError(
                "发货延迟超出 Manifest "
                "范围："
                f"index={index}, "
                f"seconds="
                f"{shipping_delay_seconds}"
            )

        base_delay_days = row[
            "base_delivery_delay_days"
        ]

        if not (
            delivery_delay["minimum"]
            <= base_delay_days
            <= delivery_delay["maximum"]
        ):
            raise ValueError(
                "基础配送延迟超出范围："
                f"index={index}"
            )

        region_group = (
            region_group_lookup[
                row[
                    "shipping_region_code"
                ]
            ]
        )

        remote_extra = row[
            "remote_extra_delay_days"
        ]

        if (
            remote_config["enabled"]
            and region_group
                in remote_region_groups
        ):
            if not (
                remote_config["minimum"]
                <= remote_extra
                <= remote_config[
                    "maximum"
                ]
            ):
                raise ValueError(
                    "偏远地区额外延迟"
                    "不正确："
                    f"index={index}"
                )
        elif remote_extra != 0:
            raise ValueError(
                "非偏远地区不应生成"
                "偏远额外延迟："
                f"index={index}"
            )

        campaign_extra = row[
            "campaign_extra_delay_days"
        ]

        campaign_family = row[
            "fulfillment_campaign_family"
        ]

        expected_campaign = (
            resolve_major_campaign_for_date(
                order_date=(
                    row[
                        "order_created_at"
                    ].date()
                ),
                reference_data=reference_data,
            )
        )

        expected_campaign_family = (
            expected_campaign[
                "campaign_family"
            ]
            if expected_campaign
                is not None
            else None
        )

        if (
            campaign_family
            != expected_campaign_family
        ):
            raise ValueError(
                "履约活动家族与订单日期"
                "不一致："
                f"index={index}"
            )

        if campaign_extra != 0:
            if (
                campaign_family is None
                or not (
                    congestion_config[
                        "extra_delay_days"
                    ][
                        "minimum"
                    ]
                    <= campaign_extra
                    <= congestion_config[
                        "extra_delay_days"
                    ][
                        "maximum"
                    ]
                )
            ):
                raise ValueError(
                    "大促拥堵额外延迟"
                    "不正确："
                    f"index={index}"
                )

        expected_total_delay_days = (
            base_delay_days
            + remote_extra
            + campaign_extra
        )

        candidate_delivered_at = (
            shipped_at
            + timedelta(
                days=(
                    expected_total_delay_days
                )
            )
        )

        if (
            candidate_delivered_at
            <= observation_end_ts
        ):
            delivered_count += 1

            if (
                row["order_status"]
                    != delivered_status
                or delivered_at
                    != candidate_delivered_at
            ):
                raise ValueError(
                    "观察窗口内履约状态"
                    "或送达时间不正确："
                    f"index={index}"
                )

            if delivered_at < shipped_at:
                raise ValueError(
                    "delivered_at 早于"
                    " shipped_at："
                    f"index={index}"
                )

            if (
                delivered_at.date()
                > window.business_end_date
            ):
                observation_tail_delivery_count += 1
        else:
            incomplete_count += 1

            if (
                row["order_status"]
                    != incomplete_status
                or delivered_at is not None
            ):
                raise ValueError(
                    "观察窗口外未完成订单"
                    "状态不正确："
                    f"index={index}"
                )

    if (
        delivered_count
        + incomplete_count
        + cancelled_count
        != len(rows)
    ):
        raise ValueError(
            "履约状态统计不完整。"
        )

    repeated_rows = (
        build_fulfillment_order_rows(
            order_rows=source_order_rows,
            manifest=manifest,
            reference_data=reference_data,
            window=window,
        )
    )

    if rows != repeated_rows:
        raise ValueError(
            "履约事件确定性校验失败。"
        )


def preview_fulfillment(
    manifest: dict[str, Any],
) -> None:
    """
    预览订单履约，不写入数据库。
    """
    window = build_generation_window(
        manifest
    )

    with engine.connect() as connection:
        reference_data = load_reference_data(
            connection
        )

        validate_reference_data(
            reference_data=reference_data,
            manifest=manifest,
            window=window,
        )

        marketing_spend_rows = (
            load_marketing_spend_rows(
                connection
            )
        )

        order_count = connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM beauty_bi_v2.fact_orders
                """
            )
        ).scalar_one()

        order_item_count = (
            connection.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM
                        beauty_bi_v2.
                        fact_order_items
                    """
                )
            ).scalar_one()
        )

    if (
        order_count != 0
        or order_item_count != 0
    ):
        raise RuntimeError(
            "履约 Preview 要求订单和"
            "订单明细表为空："
            f"orders={order_count}, "
            f"items={order_item_count}"
        )

    validate_marketing_spend_rows(
        rows=marketing_spend_rows,
        manifest=manifest,
        reference_data=reference_data,
        window=window,
    )

    customer_profiles = (
        build_customer_simulation_profiles(
            manifest=manifest,
            reference_data=reference_data,
        )
    )

    product_profiles = (
        build_product_simulation_profiles(
            manifest=manifest,
            reference_data=reference_data,
        )
    )

    validate_simulation_profiles(
        customer_profiles=customer_profiles,
        product_profiles=product_profiles,
        manifest=manifest,
        reference_data=reference_data,
    )

    daily_allocations = (
        build_daily_order_allocations(
            manifest=manifest,
            reference_data=reference_data,
            window=window,
            marketing_spend_rows=(
                marketing_spend_rows
            ),
        )
    )

    validate_daily_order_allocations(
        rows=daily_allocations,
        manifest=manifest,
        reference_data=reference_data,
        window=window,
        marketing_spend_rows=(
            marketing_spend_rows
        ),
    )

    order_rows = (
        build_order_header_event_rows(
            manifest=manifest,
            reference_data=reference_data,
            window=window,
            daily_allocations=(
                daily_allocations
            ),
            marketing_spend_rows=(
                marketing_spend_rows
            ),
            customer_profiles=(
                customer_profiles
            ),
        )
    )

    validate_order_header_event_rows(
        rows=order_rows,
        manifest=manifest,
        reference_data=reference_data,
        window=window,
        daily_allocations=(
            daily_allocations
        ),
        marketing_spend_rows=(
            marketing_spend_rows
        ),
        customer_profiles=(
            customer_profiles
        ),
    )

    (
        item_rows,
        enriched_order_rows,
    ) = build_order_item_rows_and_totals(
        order_rows=order_rows,
        manifest=manifest,
        reference_data=reference_data,
        product_profiles=product_profiles,
    )

    validate_order_item_rows_and_totals(
        item_rows=item_rows,
        enriched_order_rows=(
            enriched_order_rows
        ),
        original_order_rows=order_rows,
        manifest=manifest,
        reference_data=reference_data,
        product_profiles=product_profiles,
    )

    fulfillment_rows = (
        build_fulfillment_order_rows(
            order_rows=(
                enriched_order_rows
            ),
            manifest=manifest,
            reference_data=reference_data,
            window=window,
        )
    )

    validate_fulfillment_order_rows(
        rows=fulfillment_rows,
        source_order_rows=(
            enriched_order_rows
        ),
        manifest=manifest,
        reference_data=reference_data,
        window=window,
    )

    status_counts = Counter(
        row["order_status"]
        for row in fulfillment_rows
    )

    shipping_delay_hours = [
        Decimal(
            str(
                (
                    row["shipped_at"]
                    - row["paid_at"]
                ).total_seconds()
                / 3600
            )
        ).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )
        for row in fulfillment_rows
        if row["shipped_at"] is not None
    ]

    delivery_delay_days = [
        (
            row[
                "base_delivery_delay_days"
            ]
            + row[
                "remote_extra_delay_days"
            ]
            + row[
                "campaign_extra_delay_days"
            ]
        )
        for row in fulfillment_rows
        if row["shipped_at"] is not None
    ]

    remote_delay_order_count = sum(
        row[
            "remote_extra_delay_days"
        ] > 0
        for row in fulfillment_rows
    )

    congestion_delay_order_count = sum(
        row[
            "campaign_extra_delay_days"
        ] > 0
        for row in fulfillment_rows
    )

    delivered_values = [
        row["delivered_at"]
        for row in fulfillment_rows
        if row["delivered_at"] is not None
    ]

    observation_tail_count = sum(
        (
            row["delivered_at"] is not None
            and row[
                "delivered_at"
            ].date()
                > window.business_end_date
        )
        for row in fulfillment_rows
    )

    incomplete_count = sum(
        (
            row["paid_at"] is not None
            and row["delivered_at"] is None
        )
        for row in fulfillment_rows
    )

    print(
        "fulfillment preview passed."
    )
    print(
        "Order status counts after fulfillment: "
        f"{dict(status_counts)}"
    )
    print(
        "Shipping delay hours range: "
        f"{min(shipping_delay_hours)} -> "
        f"{max(shipping_delay_hours)}"
    )
    print(
        "Total delivery delay days range: "
        f"{min(delivery_delay_days)} -> "
        f"{max(delivery_delay_days)}"
    )
    print(
        "Remote-region delayed orders: "
        f"{remote_delay_order_count}"
    )
    print(
        "Campaign-congestion delayed orders: "
        f"{congestion_delay_order_count}"
    )
    print(
        "Delivered-at range: "
        f"{min(delivered_values)} -> "
        f"{max(delivered_values)}"
    )
    print(
        "Observation-tail deliveries: "
        f"{observation_tail_count}"
    )
    print(
        "Paid but incomplete at observation end: "
        f"{incomplete_count}"
    )
    print(
        "Cancelled orders entering fulfillment: 0"
    )
    print(
        "Order and item database writes performed: no"
    )
    print(
        "First fulfilled order: "
        f"{next(row for row in fulfillment_rows if row['delivered_at'] is not None)}"
    )
    print(
        "Last order: "
        f"{fulfillment_rows[-1]}"
    )
    print(
        "Fact-orders time constraints: passed."
    )
    print("Deterministic check: passed.")



def calculate_quality_refund_risk_multiplier(
    quality_score: Decimal,
    manifest: dict[str, Any],
) -> Decimal:
    """
    将商品质量分线性映射为退款风险乘数。

    低质量分对应较高退款风险，高质量分对应较低退款风险。
    """
    mapping = manifest[
        "simulation_profiles"
    ][
        "product"
    ][
        "quality_mappings"
    ][
        "refund_risk"
    ]

    low_score = Decimal(
        str(mapping["low_quality_score"])
    )

    high_score = Decimal(
        str(mapping["high_quality_score"])
    )

    low_multiplier = Decimal(
        str(mapping["low_quality_multiplier"])
    )

    high_multiplier = Decimal(
        str(mapping["high_quality_multiplier"])
    )

    bounded_score = min(
        max(quality_score, low_score),
        high_score,
    )

    if high_score == low_score:
        raise ValueError(
            "退款质量映射的高低质量分"
            "不能相同。"
        )

    position = (
        bounded_score - low_score
    ) / (
        high_score - low_score
    )

    multiplier = (
        low_multiplier
        + position
        * (
            high_multiplier
            - low_multiplier
        )
    )

    probability_config = manifest[
        "refund_generation"
    ][
        "probability_model"
    ][
        "quality_risk_multiplier"
    ]

    minimum_multiplier = Decimal(
        str(
            probability_config[
                "minimum"
            ]
        )
    )

    maximum_multiplier = Decimal(
        str(
            probability_config[
                "maximum"
            ]
        )
    )

    return min(
        max(
            multiplier,
            minimum_multiplier,
        ),
        maximum_multiplier,
    ).quantize(
        Decimal("0.000001"),
        rounding=ROUND_HALF_UP,
    )


def calculate_item_refund_probability(
    item_row: dict[str, Any],
    order_row: dict[str, Any],
    customer_profiles: dict[
        str,
        CustomerSimulationProfile,
    ],
    product_profiles: dict[
        str,
        ProductSimulationProfile,
    ],
    manifest: dict[str, Any],
) -> tuple[
    Decimal,
    Decimal,
    Decimal,
    bool,
]:
    """
    计算订单明细退款概率。

    final probability
    = base
    × product quality risk
    × customer refund propensity
    × deep-discount multiplier
    """
    probability_model = manifest[
        "refund_generation"
    ][
        "probability_model"
    ]

    base_probability = Decimal(
        str(
            probability_model[
                "base_item_refund_probability"
            ]
        )
    )

    product_profile = product_profiles[
        item_row["sku_code"]
    ]

    quality_multiplier = (
        calculate_quality_refund_risk_multiplier(
            quality_score=(
                product_profile.quality_score
            ),
            manifest=manifest,
        )
    )

    customer_multiplier = (
        customer_profiles[
            order_row["customer_code"]
        ].refund_propensity_multiplier
    )

    customer_bounds = probability_model[
        "customer_refund_propensity_multiplier"
    ]

    customer_multiplier = min(
        max(
            customer_multiplier,
            Decimal(
                str(
                    customer_bounds[
                        "minimum"
                    ]
                )
            ),
        ),
        Decimal(
            str(
                customer_bounds[
                    "maximum"
                ]
            )
        ),
    )

    deep_discount_config = (
        probability_model[
            "deep_discount"
        ]
    )

    discount_rate = (
        item_row["item_discount_amount"]
        / item_row["item_list_amount"]
        if item_row["item_list_amount"] > 0
        else Decimal("0")
    )

    deep_discount_applied = (
        discount_rate
        >= Decimal(
            str(
                deep_discount_config[
                    "threshold"
                ]
            )
        )
    )

    deep_discount_multiplier = (
        Decimal(
            str(
                deep_discount_config[
                    "multiplier"
                ]
            )
        )
        if deep_discount_applied
        else Decimal("1")
    )

    raw_probability = (
        base_probability
        * quality_multiplier
        * customer_multiplier
        * deep_discount_multiplier
    )

    final_bounds = probability_model[
        "final_probability"
    ]

    final_probability = min(
        max(
            raw_probability,
            Decimal(
                str(
                    final_bounds[
                        "minimum"
                    ]
                )
            ),
        ),
        Decimal(
            str(
                final_bounds[
                    "maximum"
                ]
            )
        ),
    ).quantize(
        Decimal("0.000001"),
        rounding=ROUND_HALF_UP,
    )

    return (
        final_probability,
        quality_multiplier,
        customer_multiplier.quantize(
            Decimal("0.000001"),
            rounding=ROUND_HALF_UP,
        ),
        deep_discount_applied,
    )


def build_refund_rows(
    order_rows: list[dict[str, Any]],
    item_rows: list[dict[str, Any]],
    customer_profiles: dict[
        str,
        CustomerSimulationProfile,
    ],
    product_profiles: dict[
        str,
        ProductSimulationProfile,
    ],
    manifest: dict[str, Any],
    window: GenerationWindow,
) -> list[dict[str, Any]]:
    """
    为满足资格的订单明细生成最多一条退款事件。

    数据库持久化字段以外，额外保留：
    - refund_resolved_at
    - refund_probability
    - quality_risk_multiplier
    - customer_refund_multiplier
    - deep_discount_applied

    这些字段只服务于后续评价与校验，不写入 fact_refunds。
    """
    config = manifest[
        "refund_generation"
    ]

    request_delay = config[
        "request_delay_days"
    ]

    quantity_config = config[
        "quantity"
    ]

    resolution = config[
        "resolution"
    ]

    reason_distribution = config[
        "reason_distribution"
    ]

    observation_end_ts = (
        datetime.combine(
            window.observation_end_date,
            datetime.max.time(),
        ).replace(
            microsecond=0
        )
    )

    order_lookup = {
        row["order_code"]: row
        for row in order_rows
    }

    rng = build_rng(
        manifest,
        "refunds",
    )

    rows: list[dict[str, Any]] = []

    for item in item_rows:
        order = order_lookup[
            item["order_code"]
        ]

        if (
            order["paid_at"] is None
            or order["delivered_at"] is None
            or order["order_status"]
                != "delivered"
        ):
            continue

        (
            refund_probability,
            quality_multiplier,
            customer_multiplier,
            deep_discount_applied,
        ) = calculate_item_refund_probability(
            item_row=item,
            order_row=order,
            customer_profiles=(
                customer_profiles
            ),
            product_profiles=(
                product_profiles
            ),
            manifest=manifest,
        )

        if (
            Decimal(str(rng.random()))
            >= refund_probability
        ):
            continue

        request_delay_days = rng.randint(
            request_delay["minimum"],
            request_delay["maximum"],
        )

        refund_requested_at = (
            order["delivered_at"]
            + timedelta(
                days=request_delay_days
            )
        )

        # 申请本身发生在观察窗口外时，
        # 该事件不会进入可观测数据集。
        if (
            refund_requested_at
            > observation_end_ts
        ):
            continue

        purchased_quantity = item[
            "quantity"
        ]

        if purchased_quantity == 1:
            refund_quantity = 1
            full_quantity_refund = True
        elif (
            rng.random()
            < quantity_config[
                "full_quantity_probability"
            ]
        ):
            refund_quantity = (
                purchased_quantity
            )
            full_quantity_refund = True
        else:
            refund_quantity = rng.randint(
                quantity_config[
                    "partial_quantity_strategy"
                ][
                    "minimum"
                ],
                purchased_quantity - 1,
            )
            full_quantity_refund = False

        refund_amount = quantize_money(
            item["unit_paid_price"]
            * refund_quantity
        )

        refund_reason = (
            choose_distribution_value(
                rng=rng,
                distribution=(
                    reason_distribution
                ),
                field_name=(
                    "refund reason distribution"
                ),
            )
        )

        final_status = (
            choose_distribution_value(
                rng=rng,
                distribution=(
                    resolution[
                        "final_status_distribution"
                    ]
                ),
                field_name=(
                    "refund final status"
                ),
            )
        )

        delay_seconds = rng.randint(
            resolution[
                "delay_hours"
            ][
                "minimum"
            ] * 3600,
            resolution[
                "delay_hours"
            ][
                "maximum"
            ] * 3600,
        )

        candidate_resolved_at = (
            refund_requested_at
            + timedelta(
                seconds=delay_seconds
            )
        )

        if (
            candidate_resolved_at
            > observation_end_ts
        ):
            refund_status = "requested"
            refund_resolved_at = None
            refund_completed_at = None
        else:
            refund_status = final_status
            refund_resolved_at = (
                candidate_resolved_at
            )

            refund_completed_at = (
                candidate_resolved_at
                if final_status == "completed"
                else None
            )

        rows.append(
            {
                "order_code": item[
                    "order_code"
                ],
                "line_number": item[
                    "line_number"
                ],
                "sku_code": item[
                    "sku_code"
                ],
                "customer_code": order[
                    "customer_code"
                ],
                "product_category": item[
                    "product_category"
                ],
                "product_subcategory": item[
                    "product_subcategory"
                ],
                "refund_requested_at": (
                    refund_requested_at
                ),
                "refund_resolved_at": (
                    refund_resolved_at
                ),
                "refund_completed_at": (
                    refund_completed_at
                ),
                "refund_status": (
                    refund_status
                ),
                "refund_amount": (
                    refund_amount
                ),
                "refund_quantity": (
                    refund_quantity
                ),
                "refund_reason": (
                    refund_reason
                ),
                "purchased_quantity": (
                    purchased_quantity
                ),
                "unit_paid_price": item[
                    "unit_paid_price"
                ],
                "item_paid_amount": item[
                    "item_paid_amount"
                ],
                "full_quantity_refund": (
                    full_quantity_refund
                ),
                "refund_probability": (
                    refund_probability
                ),
                "quality_risk_multiplier": (
                    quality_multiplier
                ),
                "customer_refund_multiplier": (
                    customer_multiplier
                ),
                "deep_discount_applied": (
                    deep_discount_applied
                ),
            }
        )

    return rows


def validate_refund_rows(
    refund_rows: list[
        dict[str, Any]
    ],
    order_rows: list[dict[str, Any]],
    item_rows: list[dict[str, Any]],
    customer_profiles: dict[
        str,
        CustomerSimulationProfile,
    ],
    product_profiles: dict[
        str,
        ProductSimulationProfile,
    ],
    manifest: dict[str, Any],
    window: GenerationWindow,
) -> None:
    """
    校验退款资格、概率、数量、金额、时间、状态和确定性。
    """
    order_lookup = {
        row["order_code"]: row
        for row in order_rows
    }

    item_lookup = {
        (
            row["order_code"],
            row["line_number"],
        ): row
        for row in item_rows
    }

    config = manifest[
        "refund_generation"
    ]

    request_delay = config[
        "request_delay_days"
    ]

    resolution_delay = config[
        "resolution"
    ][
        "delay_hours"
    ]

    final_probability_bounds = config[
        "probability_model"
    ][
        "final_probability"
    ]

    minimum_probability = Decimal(
        str(
            final_probability_bounds[
                "minimum"
            ]
        )
    )

    maximum_probability = Decimal(
        str(
            final_probability_bounds[
                "maximum"
            ]
        )
    )

    observation_end_ts = (
        datetime.combine(
            window.observation_end_date,
            datetime.max.time(),
        ).replace(
            microsecond=0
        )
    )

    grains: set[
        tuple[str, int]
    ] = set()

    completed_amount_by_item: (
        defaultdict[
            tuple[str, int],
            Decimal,
        ]
    ) = defaultdict(
        lambda: Decimal("0")
    )

    for index, refund in enumerate(
        refund_rows
    ):
        grain = (
            refund["order_code"],
            refund["line_number"],
        )

        if grain in grains:
            raise ValueError(
                "同一订单明细生成了"
                "多个退款事件："
                f"{grain}"
            )

        grains.add(grain)

        item = item_lookup.get(grain)

        if item is None:
            raise ValueError(
                "退款引用不存在的订单明细："
                f"index={index}, "
                f"grain={grain}"
            )

        order = order_lookup[
            refund["order_code"]
        ]

        if (
            order["paid_at"] is None
            or order["delivered_at"] is None
            or order["order_status"]
                != "delivered"
        ):
            raise ValueError(
                "退款引用不具备资格的"
                "订单明细："
                f"index={index}"
            )

        expected_probability_data = (
            calculate_item_refund_probability(
                item_row=item,
                order_row=order,
                customer_profiles=(
                    customer_profiles
                ),
                product_profiles=(
                    product_profiles
                ),
                manifest=manifest,
            )
        )

        (
            expected_probability,
            expected_quality_multiplier,
            expected_customer_multiplier,
            expected_deep_discount,
        ) = expected_probability_data

        if (
            refund["refund_probability"]
                != expected_probability
            or refund[
                "quality_risk_multiplier"
            ]
                != expected_quality_multiplier
            or refund[
                "customer_refund_multiplier"
            ]
                != expected_customer_multiplier
            or refund[
                "deep_discount_applied"
            ]
                != expected_deep_discount
        ):
            raise ValueError(
                "退款概率上下文不一致："
                f"index={index}"
            )

        if not (
            minimum_probability
            <= refund[
                "refund_probability"
            ]
            <= maximum_probability
        ):
            raise ValueError(
                "退款概率超出最终边界："
                f"index={index}"
            )

        request_delay_delta = (
            refund["refund_requested_at"]
            - order["delivered_at"]
        )

        if not (
            timedelta(
                days=request_delay["minimum"]
            )
            <= request_delay_delta
            <= timedelta(
                days=request_delay["maximum"]
            )
        ):
            raise ValueError(
                "退款申请时间超出"
                " Manifest 范围："
                f"index={index}, "
                f"delay={request_delay_delta}"
            )

        if (
            refund["refund_requested_at"]
            > observation_end_ts
        ):
            raise ValueError(
                "退款申请时间超过"
                "观察窗口："
                f"index={index}"
            )

        refund_quantity = refund[
            "refund_quantity"
        ]

        if not (
            1
            <= refund_quantity
            <= item["quantity"]
        ):
            raise ValueError(
                "退款数量超过购买数量："
                f"index={index}"
            )

        if (
            refund[
                "full_quantity_refund"
            ]
            != (
                refund_quantity
                == item["quantity"]
            )
        ):
            raise ValueError(
                "退款全量标记与数量"
                "不一致："
                f"index={index}"
            )

        expected_amount = quantize_money(
            item["unit_paid_price"]
            * refund_quantity
        )

        if (
            refund["refund_amount"]
                != expected_amount
            or refund["refund_amount"]
                > item["item_paid_amount"]
            or refund["refund_amount"]
                <= 0
        ):
            raise ValueError(
                "退款金额不符合"
                "实付单价 × 退款数量："
                f"index={index}"
            )

        refund_status = refund[
            "refund_status"
        ]

        refund_resolved_at = refund[
            "refund_resolved_at"
        ]

        refund_completed_at = refund[
            "refund_completed_at"
        ]

        if refund_status == "requested":
            if (
                refund_resolved_at is not None
                or refund_completed_at
                    is not None
            ):
                raise ValueError(
                    "requested 退款不能"
                    "包含解决或完成时间："
                    f"index={index}"
                )

        elif refund_status == "completed":
            if (
                refund_resolved_at is None
                or refund_completed_at
                    != refund_resolved_at
            ):
                raise ValueError(
                    "completed 退款必须"
                    "保存完成时间："
                    f"index={index}"
                )

        elif refund_status in {
            "rejected",
            "cancelled",
        }:
            if (
                refund_resolved_at is None
                or refund_completed_at
                    is not None
            ):
                raise ValueError(
                    "非 completed 终态"
                    "解决时间不正确："
                    f"index={index}"
                )

        else:
            raise ValueError(
                "退款状态无效："
                f"index={index}, "
                f"status={refund_status}"
            )

        if refund_resolved_at is not None:
            resolution_delta = (
                refund_resolved_at
                - refund[
                    "refund_requested_at"
                ]
            )

            if not (
                timedelta(
                    hours=(
                        resolution_delay[
                            "minimum"
                        ]
                    )
                )
                <= resolution_delta
                <= timedelta(
                    hours=(
                        resolution_delay[
                            "maximum"
                        ]
                    )
                )
            ):
                raise ValueError(
                    "退款处理延迟超出"
                    " Manifest 范围："
                    f"index={index}"
                )

            if (
                refund_resolved_at
                > observation_end_ts
            ):
                raise ValueError(
                    "退款解决时间超过"
                    "观察窗口："
                    f"index={index}"
                )

        if (
            not isinstance(
                refund["refund_reason"],
                str,
            )
            or not refund[
                "refund_reason"
            ].strip()
            or refund[
                "refund_reason"
            ]
                not in config[
                    "reason_distribution"
                ]
        ):
            raise ValueError(
                "退款原因无效："
                f"index={index}"
            )

        if refund_status == "completed":
            completed_amount_by_item[
                grain
            ] += refund["refund_amount"]

    for grain, completed_amount in (
        completed_amount_by_item.items()
    ):
        if (
            completed_amount
            > item_lookup[grain][
                "item_paid_amount"
            ]
        ):
            raise ValueError(
                "订单明细累计完成退款"
                "超过实付金额："
                f"grain={grain}"
            )

    repeated_rows = build_refund_rows(
        order_rows=order_rows,
        item_rows=item_rows,
        customer_profiles=(
            customer_profiles
        ),
        product_profiles=(
            product_profiles
        ),
        manifest=manifest,
        window=window,
    )

    if refund_rows != repeated_rows:
        raise ValueError(
            "退款事件确定性校验失败。"
        )


def preview_refunds(
    manifest: dict[str, Any],
) -> None:
    """
    预览退款事实，不写入数据库。
    """
    window = build_generation_window(
        manifest
    )

    with engine.connect() as connection:
        reference_data = load_reference_data(
            connection
        )

        validate_reference_data(
            reference_data=reference_data,
            manifest=manifest,
            window=window,
        )

        marketing_spend_rows = (
            load_marketing_spend_rows(
                connection
            )
        )

        transaction_counts = {
            table_name: (
                connection.execute(
                    text(
                        "SELECT COUNT(*) "
                        f"FROM beauty_bi_v2."
                        f"{table_name}"
                    )
                ).scalar_one()
            )
            for table_name in (
                "fact_orders",
                "fact_order_items",
                "fact_refunds",
                "fact_reviews",
                "fact_membership_tier_history",
            )
        }

    nonempty_tables = {
        table_name: count
        for table_name, count
        in transaction_counts.items()
        if count != 0
    }

    if nonempty_tables:
        raise RuntimeError(
            "退款 Preview 要求订单及"
            "下游事实表为空："
            f"{nonempty_tables}"
        )

    validate_marketing_spend_rows(
        rows=marketing_spend_rows,
        manifest=manifest,
        reference_data=reference_data,
        window=window,
    )

    customer_profiles = (
        build_customer_simulation_profiles(
            manifest=manifest,
            reference_data=reference_data,
        )
    )

    product_profiles = (
        build_product_simulation_profiles(
            manifest=manifest,
            reference_data=reference_data,
        )
    )

    validate_simulation_profiles(
        customer_profiles=customer_profiles,
        product_profiles=product_profiles,
        manifest=manifest,
        reference_data=reference_data,
    )

    daily_allocations = (
        build_daily_order_allocations(
            manifest=manifest,
            reference_data=reference_data,
            window=window,
            marketing_spend_rows=(
                marketing_spend_rows
            ),
        )
    )

    validate_daily_order_allocations(
        rows=daily_allocations,
        manifest=manifest,
        reference_data=reference_data,
        window=window,
        marketing_spend_rows=(
            marketing_spend_rows
        ),
    )

    order_rows = (
        build_order_header_event_rows(
            manifest=manifest,
            reference_data=reference_data,
            window=window,
            daily_allocations=(
                daily_allocations
            ),
            marketing_spend_rows=(
                marketing_spend_rows
            ),
            customer_profiles=(
                customer_profiles
            ),
        )
    )

    validate_order_header_event_rows(
        rows=order_rows,
        manifest=manifest,
        reference_data=reference_data,
        window=window,
        daily_allocations=(
            daily_allocations
        ),
        marketing_spend_rows=(
            marketing_spend_rows
        ),
        customer_profiles=(
            customer_profiles
        ),
    )

    (
        item_rows,
        enriched_order_rows,
    ) = build_order_item_rows_and_totals(
        order_rows=order_rows,
        manifest=manifest,
        reference_data=reference_data,
        product_profiles=product_profiles,
    )

    validate_order_item_rows_and_totals(
        item_rows=item_rows,
        enriched_order_rows=(
            enriched_order_rows
        ),
        original_order_rows=order_rows,
        manifest=manifest,
        reference_data=reference_data,
        product_profiles=product_profiles,
    )

    fulfillment_rows = (
        build_fulfillment_order_rows(
            order_rows=(
                enriched_order_rows
            ),
            manifest=manifest,
            reference_data=reference_data,
            window=window,
        )
    )

    validate_fulfillment_order_rows(
        rows=fulfillment_rows,
        source_order_rows=(
            enriched_order_rows
        ),
        manifest=manifest,
        reference_data=reference_data,
        window=window,
    )

    refund_rows = build_refund_rows(
        order_rows=fulfillment_rows,
        item_rows=item_rows,
        customer_profiles=(
            customer_profiles
        ),
        product_profiles=(
            product_profiles
        ),
        manifest=manifest,
        window=window,
    )

    validate_refund_rows(
        refund_rows=refund_rows,
        order_rows=fulfillment_rows,
        item_rows=item_rows,
        customer_profiles=(
            customer_profiles
        ),
        product_profiles=(
            product_profiles
        ),
        manifest=manifest,
        window=window,
    )

    eligible_order_codes = {
        row["order_code"]
        for row in fulfillment_rows
        if row["delivered_at"] is not None
    }

    eligible_item_count = sum(
        row["order_code"]
            in eligible_order_codes
        for row in item_rows
    )

    status_counts = Counter(
        row["refund_status"]
        for row in refund_rows
    )

    reason_counts = Counter(
        row["refund_reason"]
        for row in refund_rows
    )

    quantity_counts = Counter(
        row["refund_quantity"]
        for row in refund_rows
    )

    full_quantity_count = sum(
        row["full_quantity_refund"]
        for row in refund_rows
    )

    deep_discount_count = sum(
        row["deep_discount_applied"]
        for row in refund_rows
    )

    request_values = [
        row["refund_requested_at"]
        for row in refund_rows
    ]

    completed_values = [
        row["refund_completed_at"]
        for row in refund_rows
        if (
            row["refund_completed_at"]
            is not None
        )
    ]

    probabilities = [
        row["refund_probability"]
        for row in refund_rows
    ]

    total_requested_amount = sum(
        (
            row["refund_amount"]
            for row in refund_rows
        ),
        Decimal("0"),
    )

    total_completed_amount = sum(
        (
            row["refund_amount"]
            for row in refund_rows
            if (
                row["refund_status"]
                == "completed"
            )
        ),
        Decimal("0"),
    )

    category_requested_counts = Counter(
        row["product_category"]
        for row in refund_rows
    )

    category_completed_amounts: (
        defaultdict[str, Decimal]
    ) = defaultdict(
        lambda: Decimal("0")
    )

    for row in refund_rows:
        if (
            row["refund_status"]
            == "completed"
        ):
            category_completed_amounts[
                row["product_category"]
            ] += row["refund_amount"]

    observation_tail_requests = sum(
        (
            row["refund_requested_at"].date()
            > window.business_end_date
        )
        for row in refund_rows
    )

    print("refund preview passed.")
    print(
        "Eligible delivered order items: "
        f"{eligible_item_count}"
    )
    print(
        "Generated refund events: "
        f"{len(refund_rows)}"
    )
    print(
        "Refund event rate: "
        f"{(Decimal(len(refund_rows)) / Decimal(eligible_item_count) * Decimal('100')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)}%"
    )
    print(
        "Refund status counts: "
        f"{dict(status_counts)}"
    )
    print(
        "Refund reason counts: "
        f"{dict(reason_counts)}"
    )
    print(
        "Refund quantity counts: "
        f"{dict(quantity_counts)}"
    )
    print(
        "Full-quantity refund events: "
        f"{full_quantity_count}"
    )
    print(
        "Deep-discount refund events: "
        f"{deep_discount_count}"
    )
    print(
        "Refund probability range: "
        f"{min(probabilities)} -> "
        f"{max(probabilities)}"
    )
    print(
        "Refund request range: "
        f"{min(request_values)} -> "
        f"{max(request_values)}"
    )

    if completed_values:
        print(
            "Refund completion range: "
            f"{min(completed_values)} -> "
            f"{max(completed_values)}"
        )

    print(
        "Observation-tail refund requests: "
        f"{observation_tail_requests}"
    )
    print(
        "Unresolved requested refunds: "
        f"{status_counts['requested']}"
    )
    print(
        "Requested refund amount total: "
        f"{quantize_money(total_requested_amount)}"
    )
    print(
        "Completed refund amount total "
        "(subtracts from SO): "
        f"{quantize_money(total_completed_amount)}"
    )
    print(
        "Category refund event counts: "
        f"{dict(category_requested_counts)}"
    )
    print(
        "Category completed refund amounts: "
        f"{dict(category_completed_amounts)}"
    )
    print(
        "Maximum refund events per item: 1"
    )
    print(
        "Cumulative refund amount cap: passed."
    )
    print(
        "Database writes performed: no"
    )

    if refund_rows:
        print(
            f"First refund: {refund_rows[0]}"
        )
        print(
            f"Last refund: {refund_rows[-1]}"
        )

    print(
        "fact_refunds status-time "
        "constraints: passed."
    )
    print("Deterministic check: passed.")



def calculate_quality_review_engagement_multiplier(
    quality_score: Decimal,
    manifest: dict[str, Any],
) -> Decimal:
    """
    将商品质量分线性映射为评价参与度乘数。
    """
    mapping = manifest[
        "simulation_profiles"
    ][
        "product"
    ][
        "quality_mappings"
    ][
        "review_engagement"
    ]

    low_score = Decimal(
        str(mapping["low_quality_score"])
    )

    high_score = Decimal(
        str(mapping["high_quality_score"])
    )

    low_multiplier = Decimal(
        str(mapping["low_quality_multiplier"])
    )

    high_multiplier = Decimal(
        str(mapping["high_quality_multiplier"])
    )

    if high_score == low_score:
        raise ValueError(
            "评价参与度质量映射的"
            "高低质量分不能相同。"
        )

    bounded_score = min(
        max(quality_score, low_score),
        high_score,
    )

    position = (
        bounded_score - low_score
    ) / (
        high_score - low_score
    )

    multiplier = (
        low_multiplier
        + position
        * (
            high_multiplier
            - low_multiplier
        )
    )

    probability_config = manifest[
        "review_generation"
    ][
        "probability_model"
    ][
        "product_quality_engagement_multiplier"
    ]

    minimum_multiplier = Decimal(
        str(
            probability_config[
                "minimum"
            ]
        )
    )

    maximum_multiplier = Decimal(
        str(
            probability_config[
                "maximum"
            ]
        )
    )

    return min(
        max(
            multiplier,
            minimum_multiplier,
        ),
        maximum_multiplier,
    ).quantize(
        Decimal("0.000001"),
        rounding=ROUND_HALF_UP,
    )


def calculate_item_review_probability(
    item_row: dict[str, Any],
    order_row: dict[str, Any],
    customer_profiles: dict[
        str,
        CustomerSimulationProfile,
    ],
    product_profiles: dict[
        str,
        ProductSimulationProfile,
    ],
    manifest: dict[str, Any],
) -> tuple[
    Decimal,
    Decimal,
    Decimal,
]:
    """
    final probability
    = base
    × customer review propensity
    × product quality engagement
    """
    probability_model = manifest[
        "review_generation"
    ][
        "probability_model"
    ]

    base_probability = Decimal(
        str(
            probability_model[
                "base_item_review_probability"
            ]
        )
    )

    customer_multiplier = (
        customer_profiles[
            order_row["customer_code"]
        ].review_propensity_multiplier
    )

    customer_bounds = probability_model[
        "customer_review_propensity_multiplier"
    ]

    customer_multiplier = min(
        max(
            customer_multiplier,
            Decimal(
                str(
                    customer_bounds[
                        "minimum"
                    ]
                )
            ),
        ),
        Decimal(
            str(
                customer_bounds[
                    "maximum"
                ]
            )
        ),
    ).quantize(
        Decimal("0.000001"),
        rounding=ROUND_HALF_UP,
    )

    quality_multiplier = (
        calculate_quality_review_engagement_multiplier(
            quality_score=(
                product_profiles[
                    item_row["sku_code"]
                ].quality_score
            ),
            manifest=manifest,
        )
    )

    raw_probability = (
        base_probability
        * customer_multiplier
        * quality_multiplier
    )

    bounds = probability_model[
        "final_probability"
    ]

    final_probability = min(
        max(
            raw_probability,
            Decimal(
                str(bounds["minimum"])
            ),
        ),
        Decimal(
            str(bounds["maximum"])
        ),
    ).quantize(
        Decimal("0.000001"),
        rounding=ROUND_HALF_UP,
    )

    return (
        final_probability,
        customer_multiplier,
        quality_multiplier,
    )


def build_refund_lookup_by_item(
    refund_rows: list[
        dict[str, Any]
    ],
) -> dict[
    tuple[str, int],
    dict[str, Any],
]:
    """
    Day65 每个订单明细最多一条退款事件。
    """
    lookup: dict[
        tuple[str, int],
        dict[str, Any],
    ] = {}

    for refund in refund_rows:
        grain = (
            refund["order_code"],
            refund["line_number"],
        )

        if grain in lookup:
            raise ValueError(
                "评价生成发现同一订单明细"
                "存在多条退款事件："
                f"{grain}"
            )

        lookup[grain] = refund

    return lookup


def resolve_refund_state_at_review(
    refund_row: dict[str, Any] | None,
    reviewed_at: datetime,
) -> str:
    """
    仅使用 reviewed_at 时点已经发生的退款信息。

    规则：
    - 尚未申请：none
    - 已申请但尚未解决：requested
    - 已解决：使用 completed/rejected/cancelled
    """
    if refund_row is None:
        return "none"

    if (
        refund_row["refund_requested_at"]
        > reviewed_at
    ):
        return "none"

    resolved_at = refund_row[
        "refund_resolved_at"
    ]

    if (
        resolved_at is None
        or resolved_at > reviewed_at
    ):
        return "requested"

    final_status = refund_row[
        "refund_status"
    ]

    if final_status == "requested":
        return "requested"

    if final_status not in {
        "completed",
        "rejected",
        "cancelled",
    }:
        raise ValueError(
            "评价时点退款状态无效："
            f"{final_status}"
        )

    return final_status


def build_review_rows(
    order_rows: list[dict[str, Any]],
    item_rows: list[dict[str, Any]],
    refund_rows: list[dict[str, Any]],
    customer_profiles: dict[
        str,
        CustomerSimulationProfile,
    ],
    product_profiles: dict[
        str,
        ProductSimulationProfile,
    ],
    manifest: dict[str, Any],
    window: GenerationWindow,
) -> list[dict[str, Any]]:
    """
    生成评价事实暂存行。

    暂存 Grain：
    order_code × line_number

    正式写库时解析为 order_item_id。
    """
    config = manifest[
        "review_generation"
    ]

    delay_config = config[
        "review_delay_days"
    ]

    rating_model = config[
        "rating_model"
    ]

    sentiment_mapping = config[
        "sentiment"
    ][
        "rating_mapping"
    ]

    text_config = config[
        "text_generation"
    ]

    text_presence_probability = (
        text_config[
            "text_presence_probability"
        ]
    )

    templates = text_config[
        "templates"
    ]

    observation_end_ts = (
        datetime.combine(
            window.observation_end_date,
            datetime.max.time(),
        ).replace(
            microsecond=0
        )
    )

    order_lookup = {
        row["order_code"]: row
        for row in order_rows
    }

    refund_lookup = (
        build_refund_lookup_by_item(
            refund_rows
        )
    )

    rng = build_rng(
        manifest,
        "reviews",
    )

    rows: list[dict[str, Any]] = []

    for item in item_rows:
        order = order_lookup[
            item["order_code"]
        ]

        if (
            order["order_status"]
                != "delivered"
            or order["delivered_at"] is None
            or order["paid_at"] is None
        ):
            continue

        (
            review_probability,
            customer_review_multiplier,
            quality_engagement_multiplier,
        ) = calculate_item_review_probability(
            item_row=item,
            order_row=order,
            customer_profiles=(
                customer_profiles
            ),
            product_profiles=(
                product_profiles
            ),
            manifest=manifest,
        )

        if (
            Decimal(str(rng.random()))
            >= review_probability
        ):
            continue

        review_delay_days = rng.randint(
            delay_config["minimum"],
            delay_config["maximum"],
        )

        reviewed_at = (
            order["delivered_at"]
            + timedelta(
                days=review_delay_days
            )
        )

        if reviewed_at > observation_end_ts:
            continue

        grain = (
            item["order_code"],
            item["line_number"],
        )

        refund_row = refund_lookup.get(
            grain
        )

        refund_state = (
            resolve_refund_state_at_review(
                refund_row=refund_row,
                reviewed_at=reviewed_at,
            )
        )

        product_quality = (
            product_profiles[
                item["sku_code"]
            ].quality_score
        )

        customer_rating_bias = (
            customer_profiles[
                order["customer_code"]
            ].rating_bias
        )

        bias_bounds = rating_model[
            "customer_rating_bias"
        ]

        customer_rating_bias = min(
            max(
                customer_rating_bias,
                Decimal(
                    str(
                        bias_bounds[
                            "minimum"
                        ]
                    )
                ),
            ),
            Decimal(
                str(
                    bias_bounds[
                        "maximum"
                    ]
                )
            ),
        ).quantize(
            Decimal("0.000001"),
            rounding=ROUND_HALF_UP,
        )

        noise_config = rating_model[
            "random_noise"
        ]

        rating_random_noise = Decimal(
            str(
                rng.uniform(
                    noise_config[
                        "minimum"
                    ],
                    noise_config[
                        "maximum"
                    ],
                )
            )
        ).quantize(
            Decimal("0.000001"),
            rounding=ROUND_HALF_UP,
        )

        refund_penalty = Decimal(
            str(
                rating_model[
                    "refund_penalty_by_status"
                ][
                    refund_state
                ]
            )
        )

        raw_rating = (
            product_quality
            + customer_rating_bias
            + rating_random_noise
            + refund_penalty
        )

        rounded_rating = int(
            raw_rating.quantize(
                Decimal("1"),
                rounding=ROUND_HALF_UP,
            )
        )

        rating = min(
            max(
                rounded_rating,
                rating_model[
                    "minimum_rating"
                ],
            ),
            rating_model[
                "maximum_rating"
            ],
        )

        sentiment = (
            sentiment_mapping.get(rating)
            if isinstance(
                sentiment_mapping,
                dict,
            )
            else None
        )

        if sentiment is None:
            sentiment = sentiment_mapping.get(
                str(rating)
            )

        if sentiment not in {
            "positive",
            "neutral",
            "negative",
        }:
            raise ValueError(
                "rating 无法映射到合法"
                " sentiment："
                f"rating={rating}, "
                f"sentiment={sentiment!r}"
            )

        if (
            rng.random()
            < text_presence_probability
        ):
            sentiment_templates = (
                templates[sentiment]
            )

            review_text = rng.choice(
                sentiment_templates
            ).strip()

            if not review_text:
                raise ValueError(
                    "评价文本模板不能为空。"
                )
        else:
            review_text = None

        rows.append(
            {
                "order_code": item[
                    "order_code"
                ],
                "line_number": item[
                    "line_number"
                ],
                "sku_code": item[
                    "sku_code"
                ],
                "customer_code": order[
                    "customer_code"
                ],
                "product_category": item[
                    "product_category"
                ],
                "product_subcategory": item[
                    "product_subcategory"
                ],
                "reviewed_at": reviewed_at,
                "rating": rating,
                "review_text": review_text,
                "sentiment": sentiment,
                "refund_state_at_review": (
                    refund_state
                ),
                "review_probability": (
                    review_probability
                ),
                "customer_review_multiplier": (
                    customer_review_multiplier
                ),
                "quality_engagement_multiplier": (
                    quality_engagement_multiplier
                ),
                "product_quality_score": (
                    product_quality
                ),
                "customer_rating_bias": (
                    customer_rating_bias
                ),
                "rating_random_noise": (
                    rating_random_noise
                ),
                "refund_penalty": (
                    refund_penalty
                ),
                "raw_rating": (
                    raw_rating.quantize(
                        Decimal("0.000001"),
                        rounding=ROUND_HALF_UP,
                    )
                ),
            }
        )

    return rows


def validate_review_rows(
    review_rows: list[
        dict[str, Any]
    ],
    order_rows: list[dict[str, Any]],
    item_rows: list[dict[str, Any]],
    refund_rows: list[dict[str, Any]],
    customer_profiles: dict[
        str,
        CustomerSimulationProfile,
    ],
    product_profiles: dict[
        str,
        ProductSimulationProfile,
    ],
    manifest: dict[str, Any],
    window: GenerationWindow,
) -> None:
    """
    校验评价资格、时间、概率、退款时点状态、
    rating、sentiment、文本和确定性。
    """
    order_lookup = {
        row["order_code"]: row
        for row in order_rows
    }

    item_lookup = {
        (
            row["order_code"],
            row["line_number"],
        ): row
        for row in item_rows
    }

    refund_lookup = (
        build_refund_lookup_by_item(
            refund_rows
        )
    )

    config = manifest[
        "review_generation"
    ]

    delay_config = config[
        "review_delay_days"
    ]

    rating_model = config[
        "rating_model"
    ]

    sentiment_mapping = config[
        "sentiment"
    ][
        "rating_mapping"
    ]

    templates = config[
        "text_generation"
    ][
        "templates"
    ]

    allowed_templates = {
        sentiment: {
            template.strip()
            for template in values
        }
        for sentiment, values
        in templates.items()
    }

    probability_bounds = config[
        "probability_model"
    ][
        "final_probability"
    ]

    minimum_probability = Decimal(
        str(
            probability_bounds[
                "minimum"
            ]
        )
    )

    maximum_probability = Decimal(
        str(
            probability_bounds[
                "maximum"
            ]
        )
    )

    observation_end_ts = (
        datetime.combine(
            window.observation_end_date,
            datetime.max.time(),
        ).replace(
            microsecond=0
        )
    )

    grains: set[
        tuple[str, int]
    ] = set()

    for index, review in enumerate(
        review_rows
    ):
        grain = (
            review["order_code"],
            review["line_number"],
        )

        if grain in grains:
            raise ValueError(
                "同一订单明细生成了"
                "多条评价："
                f"{grain}"
            )

        grains.add(grain)

        item = item_lookup.get(grain)

        if item is None:
            raise ValueError(
                "评价引用不存在的订单明细："
                f"index={index}"
            )

        order = order_lookup[
            review["order_code"]
        ]

        if (
            order["order_status"]
                != "delivered"
            or order["delivered_at"] is None
            or order["paid_at"] is None
        ):
            raise ValueError(
                "评价引用不具备资格的"
                "订单明细："
                f"index={index}"
            )

        review_delay = (
            review["reviewed_at"]
            - order["delivered_at"]
        )

        if not (
            timedelta(
                days=delay_config[
                    "minimum"
                ]
            )
            <= review_delay
            <= timedelta(
                days=delay_config[
                    "maximum"
                ]
            )
        ):
            raise ValueError(
                "评价时间超出 Manifest "
                "延迟范围："
                f"index={index}, "
                f"delay={review_delay}"
            )

        if (
            review["reviewed_at"]
            > observation_end_ts
        ):
            raise ValueError(
                "评价时间超过观察窗口："
                f"index={index}"
            )

        (
            expected_probability,
            expected_customer_multiplier,
            expected_quality_multiplier,
        ) = calculate_item_review_probability(
            item_row=item,
            order_row=order,
            customer_profiles=(
                customer_profiles
            ),
            product_profiles=(
                product_profiles
            ),
            manifest=manifest,
        )

        if (
            review["review_probability"]
                != expected_probability
            or review[
                "customer_review_multiplier"
            ]
                != expected_customer_multiplier
            or review[
                "quality_engagement_multiplier"
            ]
                != expected_quality_multiplier
        ):
            raise ValueError(
                "评价概率上下文不一致："
                f"index={index}"
            )

        if not (
            minimum_probability
            <= review[
                "review_probability"
            ]
            <= maximum_probability
        ):
            raise ValueError(
                "评价概率超出最终边界："
                f"index={index}"
            )

        expected_refund_state = (
            resolve_refund_state_at_review(
                refund_row=(
                    refund_lookup.get(grain)
                ),
                reviewed_at=(
                    review["reviewed_at"]
                ),
            )
        )

        if (
            review["refund_state_at_review"]
            != expected_refund_state
        ):
            raise ValueError(
                "评价使用了错误的退款时点"
                "状态："
                f"index={index}, "
                f"expected="
                f"{expected_refund_state}, "
                "actual="
                f"{review['refund_state_at_review']}"
            )

        expected_penalty = Decimal(
            str(
                rating_model[
                    "refund_penalty_by_status"
                ][
                    expected_refund_state
                ]
            )
        )

        if (
            review["refund_penalty"]
            != expected_penalty
        ):
            raise ValueError(
                "评价退款惩罚不正确："
                f"index={index}"
            )

        expected_raw_rating = (
            review[
                "product_quality_score"
            ]
            + review[
                "customer_rating_bias"
            ]
            + review[
                "rating_random_noise"
            ]
            + expected_penalty
        ).quantize(
            Decimal("0.000001"),
            rounding=ROUND_HALF_UP,
        )

        if (
            review["raw_rating"]
            != expected_raw_rating
        ):
            raise ValueError(
                "评价原始评分公式不正确："
                f"index={index}"
            )

        expected_rating = min(
            max(
                int(
                    expected_raw_rating.quantize(
                        Decimal("1"),
                        rounding=ROUND_HALF_UP,
                    )
                ),
                rating_model[
                    "minimum_rating"
                ],
            ),
            rating_model[
                "maximum_rating"
            ],
        )

        if (
            review["rating"]
            != expected_rating
        ):
            raise ValueError(
                "评价整数评分不正确："
                f"index={index}"
            )

        expected_sentiment = (
            sentiment_mapping.get(
                expected_rating
            )
        )

        if expected_sentiment is None:
            expected_sentiment = (
                sentiment_mapping.get(
                    str(expected_rating)
                )
            )

        if (
            review["sentiment"]
            != expected_sentiment
        ):
            raise ValueError(
                "评价 sentiment 与 rating "
                "不一致："
                f"index={index}"
            )

        review_text = review[
            "review_text"
        ]

        if review_text is not None:
            if (
                not isinstance(
                    review_text,
                    str,
                )
                or not review_text.strip()
                or review_text
                    not in (
                        allowed_templates[
                            review[
                                "sentiment"
                            ]
                        ]
                    )
            ):
                raise ValueError(
                    "评价文本不是对应情感的"
                    "合法确定性模板："
                    f"index={index}"
                )

    repeated_rows = build_review_rows(
        order_rows=order_rows,
        item_rows=item_rows,
        refund_rows=refund_rows,
        customer_profiles=(
            customer_profiles
        ),
        product_profiles=(
            product_profiles
        ),
        manifest=manifest,
        window=window,
    )

    if review_rows != repeated_rows:
        raise ValueError(
            "评价事件确定性校验失败。"
        )


def preview_reviews(
    manifest: dict[str, Any],
) -> None:
    """
    预览评价事实，不写入数据库。
    """
    window = build_generation_window(
        manifest
    )

    with engine.connect() as connection:
        reference_data = load_reference_data(
            connection
        )

        validate_reference_data(
            reference_data=reference_data,
            manifest=manifest,
            window=window,
        )

        marketing_spend_rows = (
            load_marketing_spend_rows(
                connection
            )
        )

        transaction_counts = {
            table_name: (
                connection.execute(
                    text(
                        "SELECT COUNT(*) "
                        f"FROM beauty_bi_v2."
                        f"{table_name}"
                    )
                ).scalar_one()
            )
            for table_name in (
                "fact_orders",
                "fact_order_items",
                "fact_refunds",
                "fact_reviews",
                "fact_membership_tier_history",
            )
        }

    nonempty_tables = {
        table_name: count
        for table_name, count
        in transaction_counts.items()
        if count != 0
    }

    if nonempty_tables:
        raise RuntimeError(
            "评价 Preview 要求订单及"
            "下游事实表为空："
            f"{nonempty_tables}"
        )

    validate_marketing_spend_rows(
        rows=marketing_spend_rows,
        manifest=manifest,
        reference_data=reference_data,
        window=window,
    )

    customer_profiles = (
        build_customer_simulation_profiles(
            manifest=manifest,
            reference_data=reference_data,
        )
    )

    product_profiles = (
        build_product_simulation_profiles(
            manifest=manifest,
            reference_data=reference_data,
        )
    )

    validate_simulation_profiles(
        customer_profiles=customer_profiles,
        product_profiles=product_profiles,
        manifest=manifest,
        reference_data=reference_data,
    )

    daily_allocations = (
        build_daily_order_allocations(
            manifest=manifest,
            reference_data=reference_data,
            window=window,
            marketing_spend_rows=(
                marketing_spend_rows
            ),
        )
    )

    validate_daily_order_allocations(
        rows=daily_allocations,
        manifest=manifest,
        reference_data=reference_data,
        window=window,
        marketing_spend_rows=(
            marketing_spend_rows
        ),
    )

    order_rows = (
        build_order_header_event_rows(
            manifest=manifest,
            reference_data=reference_data,
            window=window,
            daily_allocations=(
                daily_allocations
            ),
            marketing_spend_rows=(
                marketing_spend_rows
            ),
            customer_profiles=(
                customer_profiles
            ),
        )
    )

    validate_order_header_event_rows(
        rows=order_rows,
        manifest=manifest,
        reference_data=reference_data,
        window=window,
        daily_allocations=(
            daily_allocations
        ),
        marketing_spend_rows=(
            marketing_spend_rows
        ),
        customer_profiles=(
            customer_profiles
        ),
    )

    (
        item_rows,
        enriched_order_rows,
    ) = build_order_item_rows_and_totals(
        order_rows=order_rows,
        manifest=manifest,
        reference_data=reference_data,
        product_profiles=product_profiles,
    )

    validate_order_item_rows_and_totals(
        item_rows=item_rows,
        enriched_order_rows=(
            enriched_order_rows
        ),
        original_order_rows=order_rows,
        manifest=manifest,
        reference_data=reference_data,
        product_profiles=product_profiles,
    )

    fulfillment_rows = (
        build_fulfillment_order_rows(
            order_rows=(
                enriched_order_rows
            ),
            manifest=manifest,
            reference_data=reference_data,
            window=window,
        )
    )

    validate_fulfillment_order_rows(
        rows=fulfillment_rows,
        source_order_rows=(
            enriched_order_rows
        ),
        manifest=manifest,
        reference_data=reference_data,
        window=window,
    )

    refund_rows = build_refund_rows(
        order_rows=fulfillment_rows,
        item_rows=item_rows,
        customer_profiles=(
            customer_profiles
        ),
        product_profiles=(
            product_profiles
        ),
        manifest=manifest,
        window=window,
    )

    validate_refund_rows(
        refund_rows=refund_rows,
        order_rows=fulfillment_rows,
        item_rows=item_rows,
        customer_profiles=(
            customer_profiles
        ),
        product_profiles=(
            product_profiles
        ),
        manifest=manifest,
        window=window,
    )

    review_rows = build_review_rows(
        order_rows=fulfillment_rows,
        item_rows=item_rows,
        refund_rows=refund_rows,
        customer_profiles=(
            customer_profiles
        ),
        product_profiles=(
            product_profiles
        ),
        manifest=manifest,
        window=window,
    )

    validate_review_rows(
        review_rows=review_rows,
        order_rows=fulfillment_rows,
        item_rows=item_rows,
        refund_rows=refund_rows,
        customer_profiles=(
            customer_profiles
        ),
        product_profiles=(
            product_profiles
        ),
        manifest=manifest,
        window=window,
    )

    eligible_order_codes = {
        row["order_code"]
        for row in fulfillment_rows
        if (
            row["order_status"]
                == "delivered"
            and row["delivered_at"]
                is not None
        )
    }

    eligible_item_count = sum(
        row["order_code"]
            in eligible_order_codes
        for row in item_rows
    )

    rating_counts = Counter(
        row["rating"]
        for row in review_rows
    )

    sentiment_counts = Counter(
        row["sentiment"]
        for row in review_rows
    )

    refund_state_counts = Counter(
        row["refund_state_at_review"]
        for row in review_rows
    )

    text_count = sum(
        row["review_text"] is not None
        for row in review_rows
    )

    reviewed_values = [
        row["reviewed_at"]
        for row in review_rows
    ]

    probabilities = [
        row["review_probability"]
        for row in review_rows
    ]

    category_review_counts = Counter(
        row["product_category"]
        for row in review_rows
    )

    category_rating_sum: (
        defaultdict[str, int]
    ) = defaultdict(int)

    for row in review_rows:
        category_rating_sum[
            row["product_category"]
        ] += row["rating"]

    category_average_rating = {
        category: (
            Decimal(total_rating)
            / Decimal(
                category_review_counts[
                    category
                ]
            )
        ).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )
        for category, total_rating
        in category_rating_sum.items()
    }

    average_by_refund_state: dict[
        str,
        Decimal,
    ] = {}

    for refund_state in sorted(
        refund_state_counts
    ):
        state_ratings = [
            row["rating"]
            for row in review_rows
            if (
                row[
                    "refund_state_at_review"
                ]
                == refund_state
            )
        ]

        average_by_refund_state[
            refund_state
        ] = (
            Decimal(
                sum(state_ratings)
            )
            / Decimal(
                len(state_ratings)
            )
        ).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )

    observation_tail_count = sum(
        (
            row["reviewed_at"].date()
            > window.business_end_date
        )
        for row in review_rows
    )

    print("review preview passed.")
    print(
        "Eligible delivered order items: "
        f"{eligible_item_count}"
    )
    print(
        "Generated reviews: "
        f"{len(review_rows)}"
    )
    print(
        "Review event rate: "
        f"{(Decimal(len(review_rows)) / Decimal(eligible_item_count) * Decimal('100')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)}%"
    )
    print(
        "Rating counts: "
        f"{dict(rating_counts)}"
    )
    print(
        "Sentiment counts: "
        f"{dict(sentiment_counts)}"
    )
    print(
        "Refund state at review counts: "
        f"{dict(refund_state_counts)}"
    )
    print(
        "Average rating by refund state: "
        f"{average_by_refund_state}"
    )
    print(
        "Reviews with text: "
        f"{text_count}"
    )
    print(
        "Reviews without text: "
        f"{len(review_rows) - text_count}"
    )
    print(
        "Review probability range: "
        f"{min(probabilities)} -> "
        f"{max(probabilities)}"
    )
    print(
        "Reviewed-at range: "
        f"{min(reviewed_values)} -> "
        f"{max(reviewed_values)}"
    )
    print(
        "Observation-tail reviews: "
        f"{observation_tail_count}"
    )
    print(
        "Category review counts: "
        f"{dict(category_review_counts)}"
    )
    print(
        "Category average ratings: "
        f"{category_average_rating}"
    )
    print(
        "Maximum reviews per item: 1"
    )
    print(
        "Future refund leakage count: 0"
    )
    print(
        "Live LLM calls: 0"
    )
    print(
        "Database writes performed: no"
    )

    if review_rows:
        print(
            f"First review: {review_rows[0]}"
        )
        print(
            f"Last review: {review_rows[-1]}"
        )

    print(
        "fact_reviews rating and "
        "sentiment constraints: passed."
    )
    print("Deterministic check: passed.")



def subtract_calendar_months(
    value: datetime,
    months: int,
) -> datetime:
    """
    从时间戳中减去固定数量的自然月。

    例如：
    2025-02-28 - 12 months = 2024-02-28
    2024-02-29 - 12 months = 2023-02-28
    """
    if (
        isinstance(months, bool)
        or not isinstance(months, int)
        or months <= 0
    ):
        raise ValueError(
            "months 必须是正整数。"
        )

    month_index = (
        value.year * 12
        + value.month
        - 1
        - months
    )

    target_year = month_index // 12
    target_month = month_index % 12 + 1

    target_day = min(
        value.day,
        calendar.monthrange(
            target_year,
            target_month,
        )[1],
    )

    return value.replace(
        year=target_year,
        month=target_month,
        day=target_day,
    )


def parse_membership_tiers(
    manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    将 Manifest 等级合同转换为按 rank 排序的 Decimal 结构。
    """
    tiers = [
        {
            "level": tier[
                "level"
            ].strip(),
            "rank": tier["rank"],
            "upgrade_threshold": (
                quantize_money(
                    Decimal(
                        str(
                            tier[
                                "upgrade_threshold"
                            ]
                        )
                    )
                )
            ),
            "retention_threshold": (
                quantize_money(
                    Decimal(
                        str(
                            tier[
                                "retention_threshold"
                            ]
                        )
                    )
                )
            ),
        }
        for tier in manifest[
            "membership_policy"
        ][
            "tiers"
        ]
    ]

    tiers.sort(
        key=lambda tier: tier["rank"]
    )

    return tiers


def select_membership_level(
    current_level: str,
    r12_valid_spend: Decimal,
    tiers: list[dict[str, Any]],
) -> tuple[str, str | None]:
    """
    根据升级门槛和当前等级保级门槛决定下一等级。

    返回：
    - next_level
    - change_type；等级不变时为 None
    """
    tier_lookup = {
        tier["level"]: tier
        for tier in tiers
    }

    current_tier = tier_lookup.get(
        current_level
    )

    if current_tier is None:
        raise ValueError(
            "当前会员等级不在 Manifest 中："
            f"{current_level!r}"
        )

    eligible_tier = tiers[0]

    for tier in tiers:
        if (
            r12_valid_spend
            >= tier[
                "upgrade_threshold"
            ]
        ):
            eligible_tier = tier
        else:
            break

    if (
        eligible_tier["rank"]
        > current_tier["rank"]
    ):
        return (
            eligible_tier["level"],
            "upgrade",
        )

    if (
        r12_valid_spend
        < current_tier[
            "retention_threshold"
        ]
    ):
        if (
            eligible_tier["rank"]
            >= current_tier["rank"]
        ):
            raise ValueError(
                "低于保级门槛时，"
                "降级目标 rank 不应高于或"
                "等于当前 rank。"
            )

        return (
            eligible_tier["level"],
            "downgrade",
        )

    return (
        current_level,
        None,
    )


def build_membership_spend_events(
    order_rows: list[dict[str, Any]],
    item_rows: list[dict[str, Any]],
    refund_rows: list[dict[str, Any]],
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    """
    构造会员 R12 引擎消费的支付与完成退款事件。

    支付金额按订单明细实付金额计入；
    完成退款按原订单明细回溯扣减。
    """
    order_lookup = {
        row["order_code"]: row
        for row in order_rows
    }

    item_lookup = {
        (
            row["order_code"],
            row["line_number"],
        ): row
        for row in item_rows
    }

    payment_events: list[
        dict[str, Any]
    ] = []

    for item in item_rows:
        order = order_lookup[
            item["order_code"]
        ]

        if (
            order["paid_at"] is None
            or order[
                "member_code_at_payment"
            ] is None
        ):
            continue

        payment_events.append(
            {
                "event_ts": order[
                    "paid_at"
                ],
                "member_code": order[
                    "member_code_at_payment"
                ],
                "order_code": item[
                    "order_code"
                ],
                "line_number": item[
                    "line_number"
                ],
                "amount": item[
                    "item_paid_amount"
                ],
            }
        )

    completed_refund_events: list[
        dict[str, Any]
    ] = []

    for refund in refund_rows:
        if (
            refund["refund_status"]
            != "completed"
        ):
            continue

        completed_at = refund[
            "refund_completed_at"
        ]

        if completed_at is None:
            raise ValueError(
                "completed 退款缺少"
                " refund_completed_at。"
            )

        grain = (
            refund["order_code"],
            refund["line_number"],
        )

        item = item_lookup.get(grain)

        if item is None:
            raise ValueError(
                "会员消费引擎无法解析"
                "退款订单明细："
                f"{grain}"
            )

        order = order_lookup[
            refund["order_code"]
        ]

        member_code = order[
            "member_code_at_payment"
        ]

        if member_code is None:
            continue

        completed_refund_events.append(
            {
                "event_ts": completed_at,
                "member_code": member_code,
                "order_code": refund[
                    "order_code"
                ],
                "line_number": refund[
                    "line_number"
                ],
                "amount": refund[
                    "refund_amount"
                ],
                "original_paid_at": (
                    order["paid_at"]
                ),
            }
        )

    payment_events.sort(
        key=lambda row: (
            row["event_ts"],
            row["order_code"],
            row["line_number"],
        )
    )

    completed_refund_events.sort(
        key=lambda row: (
            row["event_ts"],
            row["order_code"],
            row["line_number"],
        )
    )

    return (
        payment_events,
        completed_refund_events,
    )


def build_membership_evaluation_timestamps(
    window: GenerationWindow,
) -> list[datetime]:
    """
    从业务开始日至观察结束日，生成每日固定评估时间。
    """
    values: list[datetime] = []

    current_date = (
        window.business_start_date
    )

    while (
        current_date
        <= window.observation_end_date
    ):
        values.append(
            datetime.combine(
                current_date,
                window.tier_evaluation_time,
            )
        )

        current_date += timedelta(days=1)

    return values


def build_membership_tier_history_rows(
    order_rows: list[dict[str, Any]],
    item_rows: list[dict[str, Any]],
    refund_rows: list[dict[str, Any]],
    manifest: dict[str, Any],
    reference_data: ReferenceData,
    window: GenerationWindow,
) -> list[dict[str, Any]]:
    """
    按每日评估时点生成会员等级有效区间。

    事件边界：
    - paid_at < evaluated_at 的支付进入本次评估；
    - refund_completed_at < evaluated_at 的完成退款
      从本次评估开始影响 R12；
    - 原 paid_at 早于 rolling window 起点时，
      支付与其完成退款共同退出 R12。
    """
    policy = manifest[
        "membership_policy"
    ]

    initial_level = policy[
        "initial_assignment"
    ][
        "level"
    ].strip()

    rolling_months = policy[
        "rolling_window"
    ][
        "months"
    ]

    tiers = parse_membership_tiers(
        manifest
    )

    tier_lookup = {
        tier["level"]: tier
        for tier in tiers
    }

    if initial_level not in tier_lookup:
        raise ValueError(
            "初始会员等级不存在于 tiers："
            f"{initial_level}"
        )

    business_start_ts = (
        datetime.combine(
            window.business_start_date,
            datetime.min.time(),
        )
    )

    observation_end_ts = (
        datetime.combine(
            window.observation_end_date,
            datetime.max.time(),
        ).replace(
            microsecond=0
        )
    )

    account_lookup = {
        row["member_code"]: row
        for row in (
            reference_data.
            membership_accounts
        )
    }

    history_rows: list[
        dict[str, Any]
    ] = []

    current_level_by_member: dict[
        str,
        str,
    ] = {}

    current_row_index_by_member: dict[
        str,
        int,
    ] = {}

    initial_effective_from_by_member: (
        dict[str, datetime]
    ) = {}

    for account in sorted(
        reference_data.membership_accounts,
        key=lambda row: row["member_code"],
    ):
        member_code = account[
            "member_code"
        ]

        effective_from_ts = max(
            account["joined_at"],
            business_start_ts,
        )

        if (
            effective_from_ts
            > observation_end_ts
        ):
            raise ValueError(
                "会员初始等级开始时间超过"
                "观察窗口："
                f"member={member_code}, "
                f"effective_from="
                f"{effective_from_ts}"
            )

        history_rows.append(
            {
                "member_code": member_code,
                "member_level": (
                    initial_level
                ),
                "effective_from_ts": (
                    effective_from_ts
                ),
                "effective_to_ts": None,
                "evaluated_at": (
                    effective_from_ts
                ),
                "r12_valid_spend": (
                    Decimal("0.00")
                ),
                "change_type": "initial",
            }
        )

        current_level_by_member[
            member_code
        ] = initial_level

        current_row_index_by_member[
            member_code
        ] = len(history_rows) - 1

        initial_effective_from_by_member[
            member_code
        ] = effective_from_ts

    (
        payment_events,
        completed_refund_events,
    ) = build_membership_spend_events(
        order_rows=order_rows,
        item_rows=item_rows,
        refund_rows=refund_rows,
    )

    current_spend_by_member: (
        defaultdict[str, Decimal]
    ) = defaultdict(
        lambda: Decimal("0.00")
    )

    item_state: dict[
        tuple[str, int],
        dict[str, Any],
    ] = {}

    active_items_by_paid_at: list[
        tuple[
            datetime,
            str,
            int,
        ]
    ] = []

    payment_index = 0
    refund_index = 0
    active_item_head = 0

    evaluation_timestamps = (
        build_membership_evaluation_timestamps(
            window
        )
    )

    member_codes = sorted(
        account_lookup
    )

    for evaluated_at in (
        evaluation_timestamps
    ):
        while (
            payment_index
            < len(payment_events)
            and payment_events[
                payment_index
            ][
                "event_ts"
            ]
            < evaluated_at
        ):
            event = payment_events[
                payment_index
            ]

            grain = (
                event["order_code"],
                event["line_number"],
            )

            if grain in item_state:
                raise ValueError(
                    "会员消费引擎发现重复"
                    "支付明细事件："
                    f"{grain}"
                )

            item_state[grain] = {
                "member_code": event[
                    "member_code"
                ],
                "paid_at": event[
                    "event_ts"
                ],
                "gross_amount": event[
                    "amount"
                ],
                "completed_refund_amount": (
                    Decimal("0.00")
                ),
                "active_in_r12": True,
            }

            current_spend_by_member[
                event["member_code"]
            ] += event["amount"]

            active_items_by_paid_at.append(
                (
                    event["event_ts"],
                    event["order_code"],
                    event["line_number"],
                )
            )

            payment_index += 1

        while (
            refund_index
            < len(completed_refund_events)
            and completed_refund_events[
                refund_index
            ][
                "event_ts"
            ]
            < evaluated_at
        ):
            event = (
                completed_refund_events[
                    refund_index
                ]
            )

            grain = (
                event["order_code"],
                event["line_number"],
            )

            state = item_state.get(grain)

            if state is None:
                raise ValueError(
                    "完成退款早于对应支付"
                    "进入会员消费引擎："
                    f"{grain}"
                )

            state[
                "completed_refund_amount"
            ] += event["amount"]

            if (
                state[
                    "completed_refund_amount"
                ]
                > state["gross_amount"]
            ):
                raise ValueError(
                    "会员消费引擎中累计"
                    "完成退款超过实付金额："
                    f"{grain}"
                )

            if state["active_in_r12"]:
                current_spend_by_member[
                    state["member_code"]
                ] -= event["amount"]

            refund_index += 1

        rolling_start_ts = (
            subtract_calendar_months(
                evaluated_at,
                rolling_months,
            )
        )

        while (
            active_item_head
            < len(active_items_by_paid_at)
            and active_items_by_paid_at[
                active_item_head
            ][0]
            < rolling_start_ts
        ):
            (
                _,
                order_code,
                line_number,
            ) = active_items_by_paid_at[
                active_item_head
            ]

            grain = (
                order_code,
                line_number,
            )

            state = item_state[grain]

            if state["active_in_r12"]:
                net_amount = (
                    state["gross_amount"]
                    - state[
                        "completed_refund_amount"
                    ]
                )

                current_spend_by_member[
                    state["member_code"]
                ] -= net_amount

                state[
                    "active_in_r12"
                ] = False

            active_item_head += 1

        for member_code in member_codes:
            if (
                initial_effective_from_by_member[
                    member_code
                ]
                > evaluated_at
            ):
                continue

            r12_valid_spend = (
                quantize_money(
                    current_spend_by_member[
                        member_code
                    ]
                )
            )

            if r12_valid_spend < 0:
                if (
                    abs(r12_valid_spend)
                    <= Decimal("0.01")
                ):
                    r12_valid_spend = (
                        Decimal("0.00")
                    )
                else:
                    raise ValueError(
                        "会员 R12 有效消费"
                        "出现负数："
                        f"member={member_code}, "
                        f"evaluated_at="
                        f"{evaluated_at}, "
                        f"amount="
                        f"{r12_valid_spend}"
                    )

            current_level = (
                current_level_by_member[
                    member_code
                ]
            )

            (
                next_level,
                change_type,
            ) = select_membership_level(
                current_level=(
                    current_level
                ),
                r12_valid_spend=(
                    r12_valid_spend
                ),
                tiers=tiers,
            )

            if change_type is None:
                continue

            previous_index = (
                current_row_index_by_member[
                    member_code
                ]
            )

            previous_row = history_rows[
                previous_index
            ]

            if (
                previous_row[
                    "effective_to_ts"
                ]
                is not None
            ):
                raise ValueError(
                    "会员等级当前开放区间"
                    "已经被关闭："
                    f"member={member_code}"
                )

            if (
                evaluated_at
                <= previous_row[
                    "effective_from_ts"
                ]
            ):
                raise ValueError(
                    "会员等级变化时间必须"
                    "晚于当前区间开始时间："
                    f"member={member_code}, "
                    f"evaluated_at="
                    f"{evaluated_at}"
                )

            previous_row[
                "effective_to_ts"
            ] = evaluated_at

            history_rows.append(
                {
                    "member_code": (
                        member_code
                    ),
                    "member_level": (
                        next_level
                    ),
                    "effective_from_ts": (
                        evaluated_at
                    ),
                    "effective_to_ts": None,
                    "evaluated_at": (
                        evaluated_at
                    ),
                    "r12_valid_spend": (
                        r12_valid_spend
                    ),
                    "change_type": (
                        change_type
                    ),
                }
            )

            current_level_by_member[
                member_code
            ] = next_level

            current_row_index_by_member[
                member_code
            ] = len(history_rows) - 1

    return history_rows


def build_tier_history_lookup(
    history_rows: list[
        dict[str, Any]
    ],
) -> dict[
    str,
    list[dict[str, Any]],
]:
    lookup: dict[
        str,
        list[dict[str, Any]],
    ] = defaultdict(list)

    for row in history_rows:
        lookup[
            row["member_code"]
        ].append(row)

    for member_code in lookup:
        lookup[member_code].sort(
            key=lambda row: (
                row["effective_from_ts"]
            )
        )

    return dict(lookup)


def resolve_member_level_at_timestamp(
    member_code: str,
    event_ts: datetime,
    history_lookup: dict[
        str,
        list[dict[str, Any]],
    ],
) -> str:
    """
    按半开区间 [effective_from_ts, effective_to_ts)
    解析事件时点生效等级。
    """
    candidates = [
        row
        for row in history_lookup.get(
            member_code,
            [],
        )
        if (
            row["effective_from_ts"]
            <= event_ts
            and (
                row["effective_to_ts"]
                is None
                or event_ts
                    < row[
                        "effective_to_ts"
                    ]
            )
        )
    ]

    if len(candidates) != 1:
        raise ValueError(
            "支付时点必须且只能命中"
            "一个会员等级区间："
            f"member={member_code}, "
            f"event_ts={event_ts}, "
            f"matched={len(candidates)}"
        )

    return candidates[0][
        "member_level"
    ]


def attach_member_level_at_order(
    order_rows: list[dict[str, Any]],
    history_rows: list[
        dict[str, Any]
    ],
) -> list[dict[str, Any]]:
    """
    为订单附加支付时点会员等级快照。
    """
    history_lookup = (
        build_tier_history_lookup(
            history_rows
        )
    )

    enriched_rows: list[
        dict[str, Any]
    ] = []

    for order in order_rows:
        paid_at = order["paid_at"]

        member_code = order[
            "member_code_at_payment"
        ]

        if (
            paid_at is None
            or member_code is None
        ):
            member_level_at_order = None
        else:
            member_level_at_order = (
                resolve_member_level_at_timestamp(
                    member_code=member_code,
                    event_ts=paid_at,
                    history_lookup=(
                        history_lookup
                    ),
                )
            )

        enriched_rows.append(
            {
                **order,
                "member_level_at_order": (
                    member_level_at_order
                ),
            }
        )

    return enriched_rows


def validate_membership_tier_history_rows(
    history_rows: list[
        dict[str, Any]
    ],
    order_rows: list[dict[str, Any]],
    item_rows: list[dict[str, Any]],
    refund_rows: list[dict[str, Any]],
    manifest: dict[str, Any],
    reference_data: ReferenceData,
    window: GenerationWindow,
) -> None:
    """
    校验会员等级历史区间、变化方向、R12 与确定性。
    """
    expected_member_codes = {
        row["member_code"]
        for row in (
            reference_data.
            membership_accounts
        )
    }

    history_lookup = (
        build_tier_history_lookup(
            history_rows
        )
    )

    if (
        set(history_lookup)
        != expected_member_codes
    ):
        raise ValueError(
            "会员等级历史未完整覆盖"
            "会员账户。"
        )

    tiers = parse_membership_tiers(
        manifest
    )

    tier_lookup = {
        row["level"]: row
        for row in tiers
    }

    initial_level = manifest[
        "membership_policy"
    ][
        "initial_assignment"
    ][
        "level"
    ].strip()

    change_counts = Counter(
        row["change_type"]
        for row in history_rows
    )

    required_change_types = {
        "initial",
        "upgrade",
        "downgrade",
    }

    missing_change_types = (
        required_change_types
        - set(change_counts)
    )

    if missing_change_types:
        raise ValueError(
            "会员等级历史缺少 Day65 "
            "最小验收路径："
            f"{sorted(missing_change_types)}"
        )

    for member_code, rows in (
        history_lookup.items()
    ):
        if (
            rows[0]["change_type"]
            != "initial"
            or rows[0][
                "member_level"
            ]
            != initial_level
        ):
            raise ValueError(
                "会员第一条等级历史必须"
                "是最低等级 initial："
                f"member={member_code}"
            )

        if sum(
            row["change_type"] == "initial"
            for row in rows
        ) != 1:
            raise ValueError(
                "每个会员账户必须且只能"
                "有一条 initial："
                f"member={member_code}"
            )

        open_rows = [
            row
            for row in rows
            if (
                row["effective_to_ts"]
                is None
            )
        ]

        if len(open_rows) != 1:
            raise ValueError(
                "每个会员账户必须且只能"
                "有一个开放等级区间："
                f"member={member_code}, "
                f"open_count={len(open_rows)}"
            )

        for index, row in enumerate(rows):
            if (
                row["member_level"]
                not in tier_lookup
            ):
                raise ValueError(
                    "会员等级历史出现"
                    "未知等级："
                    f"member={member_code}"
                )

            if (
                row["r12_valid_spend"]
                < 0
            ):
                raise ValueError(
                    "会员等级历史 R12 "
                    "有效消费不能为负："
                    f"member={member_code}"
                )

            if (
                row["evaluated_at"]
                != row[
                    "effective_from_ts"
                ]
            ):
                raise ValueError(
                    "等级历史 evaluated_at "
                    "必须等于新区间开始时间："
                    f"member={member_code}"
                )

            if index == 0:
                continue

            previous_row = rows[
                index - 1
            ]

            if (
                previous_row[
                    "effective_to_ts"
                ]
                != row[
                    "effective_from_ts"
                ]
            ):
                raise ValueError(
                    "会员等级历史区间"
                    "不连续或发生重叠："
                    f"member={member_code}, "
                    f"index={index}"
                )

            previous_rank = tier_lookup[
                previous_row[
                    "member_level"
                ]
            ][
                "rank"
            ]

            current_rank = tier_lookup[
                row["member_level"]
            ][
                "rank"
            ]

            if (
                row["change_type"]
                == "upgrade"
                and current_rank
                    <= previous_rank
            ):
                raise ValueError(
                    "upgrade 的新等级 rank "
                    "必须更高："
                    f"member={member_code}"
                )

            if (
                row["change_type"]
                == "downgrade"
                and current_rank
                    >= previous_rank
            ):
                raise ValueError(
                    "downgrade 的新等级 rank "
                    "必须更低："
                    f"member={member_code}"
                )

    repeated_rows = (
        build_membership_tier_history_rows(
            order_rows=order_rows,
            item_rows=item_rows,
            refund_rows=refund_rows,
            manifest=manifest,
            reference_data=reference_data,
            window=window,
        )
    )

    if history_rows != repeated_rows:
        raise ValueError(
            "会员等级历史确定性校验失败。"
        )


def validate_member_level_at_order_rows(
    enriched_order_rows: list[
        dict[str, Any]
    ],
    source_order_rows: list[
        dict[str, Any]
    ],
    history_rows: list[
        dict[str, Any]
    ],
    window: GenerationWindow,
) -> int:
    """
    校验订单支付时点等级快照，并返回发生在同日评估前、
    且该会员当日发生等级变化的支付数量。
    """
    if len(enriched_order_rows) != len(
        source_order_rows
    ):
        raise ValueError(
            "附加会员等级后订单行数"
            "发生变化。"
        )

    source_lookup = {
        row["order_code"]: row
        for row in source_order_rows
    }

    history_lookup = (
        build_tier_history_lookup(
            history_rows
        )
    )

    change_by_member_and_date = {
        (
            row["member_code"],
            row["effective_from_ts"].date(),
        ): row
        for row in history_rows
        if row["change_type"]
            in {
                "upgrade",
                "downgrade",
            }
    }

    preserved_pre_evaluation_count = 0

    for index, order in enumerate(
        enriched_order_rows
    ):
        source_order = source_lookup[
            order["order_code"]
        ]

        for field_name, field_value in (
            source_order.items()
        ):
            if (
                order[field_name]
                != field_value
            ):
                raise ValueError(
                    "附加会员等级快照错误"
                    "修改了订单其他字段："
                    f"index={index}, "
                    f"field={field_name}"
                )

        paid_at = order["paid_at"]

        member_code = order[
            "member_code_at_payment"
        ]

        member_level = order[
            "member_level_at_order"
        ]

        if (
            paid_at is None
            or member_code is None
        ):
            if member_level is not None:
                raise ValueError(
                    "未支付或非会员订单的"
                    " member_level_at_order "
                    "必须为空："
                    f"index={index}"
                )

            continue

        expected_level = (
            resolve_member_level_at_timestamp(
                member_code=member_code,
                event_ts=paid_at,
                history_lookup=(
                    history_lookup
                ),
            )
        )

        if member_level != expected_level:
            raise ValueError(
                "订单会员等级快照与"
                "支付时点历史不一致："
                f"index={index}, "
                f"expected={expected_level}, "
                f"actual={member_level}"
            )

        evaluation_ts = datetime.combine(
            paid_at.date(),
            window.tier_evaluation_time,
        )

        change_row = (
            change_by_member_and_date.get(
                (
                    member_code,
                    paid_at.date(),
                )
            )
        )

        if (
            change_row is not None
            and paid_at < evaluation_ts
        ):
            if (
                member_level
                == change_row[
                    "member_level"
                ]
            ):
                raise ValueError(
                    "同日评估前支付错误使用了"
                    "评估后的新等级："
                    f"order={order['order_code']}"
                )

            preserved_pre_evaluation_count += 1

    return preserved_pre_evaluation_count


def preview_membership_tiers(
    manifest: dict[str, Any],
) -> None:
    """
    预览会员等级历史和订单支付时点等级快照，
    不写入数据库。
    """
    window = build_generation_window(
        manifest
    )

    with engine.connect() as connection:
        reference_data = load_reference_data(
            connection
        )

        validate_reference_data(
            reference_data=reference_data,
            manifest=manifest,
            window=window,
        )

        marketing_spend_rows = (
            load_marketing_spend_rows(
                connection
            )
        )

        transaction_counts = {
            table_name: (
                connection.execute(
                    text(
                        "SELECT COUNT(*) "
                        f"FROM beauty_bi_v2."
                        f"{table_name}"
                    )
                ).scalar_one()
            )
            for table_name in (
                "fact_orders",
                "fact_order_items",
                "fact_refunds",
                "fact_reviews",
                "fact_membership_tier_history",
            )
        }

    nonempty_tables = {
        table_name: count
        for table_name, count
        in transaction_counts.items()
        if count != 0
    }

    if nonempty_tables:
        raise RuntimeError(
            "会员等级 Preview 要求订单及"
            "下游事实表为空："
            f"{nonempty_tables}"
        )

    validate_marketing_spend_rows(
        rows=marketing_spend_rows,
        manifest=manifest,
        reference_data=reference_data,
        window=window,
    )

    customer_profiles = (
        build_customer_simulation_profiles(
            manifest=manifest,
            reference_data=reference_data,
        )
    )

    product_profiles = (
        build_product_simulation_profiles(
            manifest=manifest,
            reference_data=reference_data,
        )
    )

    validate_simulation_profiles(
        customer_profiles=customer_profiles,
        product_profiles=product_profiles,
        manifest=manifest,
        reference_data=reference_data,
    )

    daily_allocations = (
        build_daily_order_allocations(
            manifest=manifest,
            reference_data=reference_data,
            window=window,
            marketing_spend_rows=(
                marketing_spend_rows
            ),
        )
    )

    validate_daily_order_allocations(
        rows=daily_allocations,
        manifest=manifest,
        reference_data=reference_data,
        window=window,
        marketing_spend_rows=(
            marketing_spend_rows
        ),
    )

    order_rows = (
        build_order_header_event_rows(
            manifest=manifest,
            reference_data=reference_data,
            window=window,
            daily_allocations=(
                daily_allocations
            ),
            marketing_spend_rows=(
                marketing_spend_rows
            ),
            customer_profiles=(
                customer_profiles
            ),
        )
    )

    validate_order_header_event_rows(
        rows=order_rows,
        manifest=manifest,
        reference_data=reference_data,
        window=window,
        daily_allocations=(
            daily_allocations
        ),
        marketing_spend_rows=(
            marketing_spend_rows
        ),
        customer_profiles=(
            customer_profiles
        ),
    )

    (
        item_rows,
        enriched_order_rows,
    ) = build_order_item_rows_and_totals(
        order_rows=order_rows,
        manifest=manifest,
        reference_data=reference_data,
        product_profiles=product_profiles,
    )

    validate_order_item_rows_and_totals(
        item_rows=item_rows,
        enriched_order_rows=(
            enriched_order_rows
        ),
        original_order_rows=order_rows,
        manifest=manifest,
        reference_data=reference_data,
        product_profiles=product_profiles,
    )

    fulfillment_rows = (
        build_fulfillment_order_rows(
            order_rows=(
                enriched_order_rows
            ),
            manifest=manifest,
            reference_data=reference_data,
            window=window,
        )
    )

    validate_fulfillment_order_rows(
        rows=fulfillment_rows,
        source_order_rows=(
            enriched_order_rows
        ),
        manifest=manifest,
        reference_data=reference_data,
        window=window,
    )

    refund_rows = build_refund_rows(
        order_rows=fulfillment_rows,
        item_rows=item_rows,
        customer_profiles=(
            customer_profiles
        ),
        product_profiles=(
            product_profiles
        ),
        manifest=manifest,
        window=window,
    )

    validate_refund_rows(
        refund_rows=refund_rows,
        order_rows=fulfillment_rows,
        item_rows=item_rows,
        customer_profiles=(
            customer_profiles
        ),
        product_profiles=(
            product_profiles
        ),
        manifest=manifest,
        window=window,
    )

    history_rows = (
        build_membership_tier_history_rows(
            order_rows=fulfillment_rows,
            item_rows=item_rows,
            refund_rows=refund_rows,
            manifest=manifest,
            reference_data=reference_data,
            window=window,
        )
    )

    validate_membership_tier_history_rows(
        history_rows=history_rows,
        order_rows=fulfillment_rows,
        item_rows=item_rows,
        refund_rows=refund_rows,
        manifest=manifest,
        reference_data=reference_data,
        window=window,
    )

    orders_with_member_level = (
        attach_member_level_at_order(
            order_rows=fulfillment_rows,
            history_rows=history_rows,
        )
    )

    pre_evaluation_snapshot_count = (
        validate_member_level_at_order_rows(
            enriched_order_rows=(
                orders_with_member_level
            ),
            source_order_rows=(
                fulfillment_rows
            ),
            history_rows=history_rows,
            window=window,
        )
    )

    change_counts = Counter(
        row["change_type"]
        for row in history_rows
    )

    level_row_counts = Counter(
        row["member_level"]
        for row in history_rows
    )

    open_rows = [
        row
        for row in history_rows
        if row["effective_to_ts"] is None
    ]

    current_level_counts = Counter(
        row["member_level"]
        for row in open_rows
    )

    transition_counts = Counter()

    history_lookup = (
        build_tier_history_lookup(
            history_rows
        )
    )

    for rows in history_lookup.values():
        for previous_row, current_row in zip(
            rows,
            rows[1:],
        ):
            transition_counts[
                (
                    previous_row[
                        "member_level"
                    ],
                    current_row[
                        "member_level"
                    ],
                )
            ] += 1

    paid_member_orders = [
        row
        for row in orders_with_member_level
        if (
            row["paid_at"] is not None
            and row[
                "member_level_at_order"
            ] is not None
        )
    ]

    member_level_snapshot_counts = Counter(
        row["member_level_at_order"]
        for row in paid_member_orders
    )

    r12_change_values = [
        row["r12_valid_spend"]
        for row in history_rows
        if row["change_type"]
            != "initial"
    ]

    effective_from_values = [
        row["effective_from_ts"]
        for row in history_rows
    ]

    print(
        "membership tier preview passed."
    )
    print(
        "Membership accounts covered: "
        f"{len(history_lookup)}"
    )
    print(
        "Tier history rows: "
        f"{len(history_rows)}"
    )
    print(
        "Change-type counts: "
        f"{dict(change_counts)}"
    )
    print(
        "Tier history row counts by level: "
        f"{dict(level_row_counts)}"
    )
    print(
        "Current open-tier counts: "
        f"{dict(current_level_counts)}"
    )
    print(
        "Transition counts: "
        f"{dict(transition_counts)}"
    )
    print(
        "History effective-from range: "
        f"{min(effective_from_values)} -> "
        f"{max(effective_from_values)}"
    )

    if r12_change_values:
        print(
            "R12 spend at tier-change range: "
            f"{min(r12_change_values)} -> "
            f"{max(r12_change_values)}"
        )

    print(
        "Paid member orders with level snapshot: "
        f"{len(paid_member_orders)}"
    )
    print(
        "Member-level-at-order counts: "
        f"{dict(member_level_snapshot_counts)}"
    )
    print(
        "Pre-evaluation payment snapshots "
        "preserved: "
        f"{pre_evaluation_snapshot_count}"
    )
    print(
        "Non-member or unpaid orders with "
        "level snapshot: 0"
    )
    print(
        "Open tier intervals per account: 1"
    )
    print(
        "Overlapping tier intervals: 0"
    )
    print(
        "Initial / upgrade / downgrade "
        "paths: passed."
    )
    print(
        "Successful refunds affect next "
        "evaluation: passed."
    )
    print(
        "Database writes performed: no"
    )
    print(
        f"First history row: {history_rows[0]}"
    )
    print(
        f"Last history row: {history_rows[-1]}"
    )
    print(
        "member_level_at_order consistency: "
        "passed."
    )
    print("Deterministic check: passed.")



@dataclass(frozen=True)
class GeneratedTransactionBundle:
    """
    Day65 剩余五张交易事实表的完整暂存数据。
    """

    order_rows: tuple[dict[str, Any], ...]
    item_rows: tuple[dict[str, Any], ...]
    refund_rows: tuple[dict[str, Any], ...]
    review_rows: tuple[dict[str, Any], ...]
    tier_history_rows: tuple[
        dict[str, Any],
        ...,
    ]


def build_transaction_bundle(
    manifest: dict[str, Any],
    reference_data: ReferenceData,
    marketing_spend_rows: list[
        dict[str, Any]
    ],
    window: GenerationWindow,
) -> GeneratedTransactionBundle:
    """
    生成并校验 Day65 全部剩余交易事实。

    本函数不写数据库。
    """
    customer_profiles = (
        build_customer_simulation_profiles(
            manifest=manifest,
            reference_data=reference_data,
        )
    )

    product_profiles = (
        build_product_simulation_profiles(
            manifest=manifest,
            reference_data=reference_data,
        )
    )

    validate_simulation_profiles(
        customer_profiles=customer_profiles,
        product_profiles=product_profiles,
        manifest=manifest,
        reference_data=reference_data,
    )

    daily_allocations = (
        build_daily_order_allocations(
            manifest=manifest,
            reference_data=reference_data,
            window=window,
            marketing_spend_rows=(
                marketing_spend_rows
            ),
        )
    )

    validate_daily_order_allocations(
        rows=daily_allocations,
        manifest=manifest,
        reference_data=reference_data,
        window=window,
        marketing_spend_rows=(
            marketing_spend_rows
        ),
    )

    order_header_rows = (
        build_order_header_event_rows(
            manifest=manifest,
            reference_data=reference_data,
            window=window,
            daily_allocations=(
                daily_allocations
            ),
            marketing_spend_rows=(
                marketing_spend_rows
            ),
            customer_profiles=(
                customer_profiles
            ),
        )
    )

    validate_order_header_event_rows(
        rows=order_header_rows,
        manifest=manifest,
        reference_data=reference_data,
        window=window,
        daily_allocations=(
            daily_allocations
        ),
        marketing_spend_rows=(
            marketing_spend_rows
        ),
        customer_profiles=(
            customer_profiles
        ),
    )

    (
        item_rows,
        order_rows_with_amounts,
    ) = build_order_item_rows_and_totals(
        order_rows=order_header_rows,
        manifest=manifest,
        reference_data=reference_data,
        product_profiles=product_profiles,
    )

    validate_order_item_rows_and_totals(
        item_rows=item_rows,
        enriched_order_rows=(
            order_rows_with_amounts
        ),
        original_order_rows=(
            order_header_rows
        ),
        manifest=manifest,
        reference_data=reference_data,
        product_profiles=product_profiles,
    )

    fulfillment_rows = (
        build_fulfillment_order_rows(
            order_rows=(
                order_rows_with_amounts
            ),
            manifest=manifest,
            reference_data=reference_data,
            window=window,
        )
    )

    validate_fulfillment_order_rows(
        rows=fulfillment_rows,
        source_order_rows=(
            order_rows_with_amounts
        ),
        manifest=manifest,
        reference_data=reference_data,
        window=window,
    )

    refund_rows = build_refund_rows(
        order_rows=fulfillment_rows,
        item_rows=item_rows,
        customer_profiles=(
            customer_profiles
        ),
        product_profiles=(
            product_profiles
        ),
        manifest=manifest,
        window=window,
    )

    validate_refund_rows(
        refund_rows=refund_rows,
        order_rows=fulfillment_rows,
        item_rows=item_rows,
        customer_profiles=(
            customer_profiles
        ),
        product_profiles=(
            product_profiles
        ),
        manifest=manifest,
        window=window,
    )

    review_rows = build_review_rows(
        order_rows=fulfillment_rows,
        item_rows=item_rows,
        refund_rows=refund_rows,
        customer_profiles=(
            customer_profiles
        ),
        product_profiles=(
            product_profiles
        ),
        manifest=manifest,
        window=window,
    )

    validate_review_rows(
        review_rows=review_rows,
        order_rows=fulfillment_rows,
        item_rows=item_rows,
        refund_rows=refund_rows,
        customer_profiles=(
            customer_profiles
        ),
        product_profiles=(
            product_profiles
        ),
        manifest=manifest,
        window=window,
    )

    tier_history_rows = (
        build_membership_tier_history_rows(
            order_rows=fulfillment_rows,
            item_rows=item_rows,
            refund_rows=refund_rows,
            manifest=manifest,
            reference_data=reference_data,
            window=window,
        )
    )

    validate_membership_tier_history_rows(
        history_rows=tier_history_rows,
        order_rows=fulfillment_rows,
        item_rows=item_rows,
        refund_rows=refund_rows,
        manifest=manifest,
        reference_data=reference_data,
        window=window,
    )

    final_order_rows = (
        attach_member_level_at_order(
            order_rows=fulfillment_rows,
            history_rows=tier_history_rows,
        )
    )

    validate_member_level_at_order_rows(
        enriched_order_rows=(
            final_order_rows
        ),
        source_order_rows=(
            fulfillment_rows
        ),
        history_rows=tier_history_rows,
        window=window,
    )

    return GeneratedTransactionBundle(
        order_rows=tuple(
            final_order_rows
        ),
        item_rows=tuple(item_rows),
        refund_rows=tuple(refund_rows),
        review_rows=tuple(review_rows),
        tier_history_rows=tuple(
            tier_history_rows
        ),
    )


def _assert_database_rows_equal(
    expected_rows: list[
        dict[str, Any]
    ],
    actual_rows: list[
        dict[str, Any]
    ],
    entity_name: str,
) -> None:
    """
    对写库后的业务字段执行逐行比较。
    """
    if len(expected_rows) != len(
        actual_rows
    ):
        raise RuntimeError(
            f"{entity_name} 写后行数不一致："
            f"expected={len(expected_rows)}, "
            f"actual={len(actual_rows)}"
        )

    for index, (
        expected_row,
        actual_row,
    ) in enumerate(
        zip(
            expected_rows,
            actual_rows,
            strict=True,
        )
    ):
        if expected_row != actual_row:
            raise RuntimeError(
                f"{entity_name} 写后逐行比较失败："
                f"index={index}, "
                f"expected={expected_row}, "
                f"actual={actual_row}"
            )


def _canonical_order_rows(
    rows: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    return sorted(
        (
            {
                "order_code": row[
                    "order_code"
                ],
                "customer_code": row[
                    "customer_code"
                ],
                "channel_code": row[
                    "channel_code"
                ],
                "shipping_region_code": row[
                    "shipping_region_code"
                ],
                "campaign_code": row[
                    "campaign_code"
                ],
                "order_created_at": row[
                    "order_created_at"
                ],
                "paid_at": row["paid_at"],
                "delivered_at": row[
                    "delivered_at"
                ],
                "order_status": row[
                    "order_status"
                ],
                "member_level_at_order": (
                    row[
                        "member_level_at_order"
                    ]
                ),
                "order_list_amount": row[
                    "order_list_amount"
                ],
                "order_discount_amount": (
                    row[
                        "order_discount_amount"
                    ]
                ),
                "order_paid_amount": row[
                    "order_paid_amount"
                ],
            }
            for row in rows
        ),
        key=lambda row: row["order_code"],
    )


def _canonical_item_rows(
    rows: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    return sorted(
        (
            {
                "order_code": row[
                    "order_code"
                ],
                "sku_code": row[
                    "sku_code"
                ],
                "promotion_code": row[
                    "promotion_code"
                ],
                "quantity": row[
                    "quantity"
                ],
                "unit_list_price": row[
                    "unit_list_price"
                ],
                "unit_paid_price": row[
                    "unit_paid_price"
                ],
                "item_list_amount": row[
                    "item_list_amount"
                ],
                "item_discount_amount": (
                    row[
                        "item_discount_amount"
                    ]
                ),
                "item_paid_amount": row[
                    "item_paid_amount"
                ],
                "unit_cost_at_order": row[
                    "unit_cost_at_order"
                ],
                "item_cost_amount": row[
                    "item_cost_amount"
                ],
            }
            for row in rows
        ),
        key=lambda row: (
            row["order_code"],
            row["sku_code"],
        ),
    )


def _canonical_refund_rows(
    rows: Iterable[dict[str, Any]],
    item_lookup: dict[
        tuple[str, int],
        dict[str, Any],
    ],
) -> list[dict[str, Any]]:
    return sorted(
        (
            {
                "order_code": row[
                    "order_code"
                ],
                "sku_code": item_lookup[
                    (
                        row["order_code"],
                        row["line_number"],
                    )
                ][
                    "sku_code"
                ],
                "refund_requested_at": (
                    row[
                        "refund_requested_at"
                    ]
                ),
                "refund_completed_at": (
                    row[
                        "refund_completed_at"
                    ]
                ),
                "refund_status": row[
                    "refund_status"
                ],
                "refund_amount": row[
                    "refund_amount"
                ],
                "refund_quantity": row[
                    "refund_quantity"
                ],
                "refund_reason": row[
                    "refund_reason"
                ],
            }
            for row in rows
        ),
        key=lambda row: (
            row["order_code"],
            row["sku_code"],
        ),
    )


def _canonical_review_rows(
    rows: Iterable[dict[str, Any]],
    item_lookup: dict[
        tuple[str, int],
        dict[str, Any],
    ],
) -> list[dict[str, Any]]:
    return sorted(
        (
            {
                "order_code": row[
                    "order_code"
                ],
                "sku_code": item_lookup[
                    (
                        row["order_code"],
                        row["line_number"],
                    )
                ][
                    "sku_code"
                ],
                "reviewed_at": row[
                    "reviewed_at"
                ],
                "rating": row["rating"],
                "review_text": row[
                    "review_text"
                ],
                "sentiment": row[
                    "sentiment"
                ],
            }
            for row in rows
        ),
        key=lambda row: (
            row["order_code"],
            row["sku_code"],
        ),
    )


def _canonical_tier_rows(
    rows: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    return sorted(
        (
            {
                "member_code": row[
                    "member_code"
                ],
                "member_level": row[
                    "member_level"
                ],
                "effective_from_ts": row[
                    "effective_from_ts"
                ],
                "effective_to_ts": row[
                    "effective_to_ts"
                ],
                "evaluated_at": row[
                    "evaluated_at"
                ],
                "r12_valid_spend": row[
                    "r12_valid_spend"
                ],
                "change_type": row[
                    "change_type"
                ],
            }
            for row in rows
        ),
        key=lambda row: (
            row["member_code"],
            row["effective_from_ts"],
        ),
    )


def validate_transaction_target_state(
    connection: Connection,
    manifest: dict[str, Any],
    reference_data: ReferenceData,
    window: GenerationWindow,
) -> list[dict[str, Any]]:
    """
    正式写库前验证：
    - marketing spend 已完整写入；
    - 其余五张目标表为空。
    """
    marketing_spend_rows = (
        load_marketing_spend_rows(
            connection
        )
    )

    validate_marketing_spend_rows(
        rows=marketing_spend_rows,
        manifest=manifest,
        reference_data=reference_data,
        window=window,
    )

    target_counts = {
        table_name: (
            connection.execute(
                text(
                    "SELECT COUNT(*) "
                    f"FROM beauty_bi_v2."
                    f"{table_name}"
                )
            ).scalar_one()
        )
        for table_name in (
            "fact_orders",
            "fact_order_items",
            "fact_refunds",
            "fact_reviews",
            "fact_membership_tier_history",
        )
    }

    nonempty_targets = {
        table_name: count
        for table_name, count
        in target_counts.items()
        if count != 0
    }

    if nonempty_targets:
        raise RuntimeError(
            "正式交易 Seed 要求剩余五张"
            "事实表为空："
            f"{nonempty_targets}"
        )

    return marketing_spend_rows


def insert_transaction_bundle(
    bundle: GeneratedTransactionBundle,
    manifest: dict[str, Any],
    reference_data: ReferenceData,
    window: GenerationWindow,
) -> dict[str, int]:
    """
    在一个 PostgreSQL 事务中写入剩余五张事实表。

    任意异常都会由 engine.begin() 回滚整个事务。
    """
    customer_id_lookup = {
        row["customer_code"]:
            row["customer_id"]
        for row in reference_data.customers
    }

    channel_id_lookup = {
        row["channel_code"]:
            row["channel_id"]
        for row in reference_data.channels
    }

    region_id_lookup = {
        row["region_code"]:
            row["region_id"]
        for row in reference_data.regions
    }

    campaign_id_lookup = {
        row["campaign_code"]:
            row["campaign_id"]
        for row in reference_data.campaigns
    }

    product_id_lookup = {
        row["sku_code"]:
            row["product_id"]
        for row in reference_data.products
    }

    promotion_id_lookup = {
        row["promotion_code"]:
            row["promotion_id"]
        for row in reference_data.promotions
    }

    membership_id_lookup = {
        row["member_code"]:
            row["membership_account_id"]
        for row in (
            reference_data.
            membership_accounts
        )
    }

    generated_item_lookup = {
        (
            row["order_code"],
            row["line_number"],
        ): row
        for row in bundle.item_rows
    }

    order_insert_sql = text(
        """
        INSERT INTO beauty_bi_v2.fact_orders (
            order_code,
            customer_id,
            channel_id,
            shipping_region_id,
            campaign_id,
            order_created_at,
            paid_at,
            delivered_at,
            order_status,
            member_level_at_order,
            order_list_amount,
            order_discount_amount,
            order_paid_amount
        )
        VALUES (
            :order_code,
            :customer_id,
            :channel_id,
            :shipping_region_id,
            :campaign_id,
            :order_created_at,
            :paid_at,
            :delivered_at,
            :order_status,
            :member_level_at_order,
            :order_list_amount,
            :order_discount_amount,
            :order_paid_amount
        )
        """
    )

    item_insert_sql = text(
        """
        INSERT INTO
            beauty_bi_v2.fact_order_items (
                order_id,
                product_id,
                promotion_id,
                quantity,
                unit_list_price,
                unit_paid_price,
                item_list_amount,
                item_discount_amount,
                item_paid_amount,
                unit_cost_at_order,
                item_cost_amount
            )
        VALUES (
            :order_id,
            :product_id,
            :promotion_id,
            :quantity,
            :unit_list_price,
            :unit_paid_price,
            :item_list_amount,
            :item_discount_amount,
            :item_paid_amount,
            :unit_cost_at_order,
            :item_cost_amount
        )
        """
    )

    refund_insert_sql = text(
        """
        INSERT INTO beauty_bi_v2.fact_refunds (
            order_id,
            order_item_id,
            refund_requested_at,
            refund_completed_at,
            refund_status,
            refund_amount,
            refund_quantity,
            refund_reason
        )
        VALUES (
            :order_id,
            :order_item_id,
            :refund_requested_at,
            :refund_completed_at,
            :refund_status,
            :refund_amount,
            :refund_quantity,
            :refund_reason
        )
        """
    )

    review_insert_sql = text(
        """
        INSERT INTO beauty_bi_v2.fact_reviews (
            order_item_id,
            reviewed_at,
            rating,
            review_text,
            sentiment
        )
        VALUES (
            :order_item_id,
            :reviewed_at,
            :rating,
            :review_text,
            :sentiment
        )
        """
    )

    tier_insert_sql = text(
        """
        INSERT INTO
            beauty_bi_v2.
            fact_membership_tier_history (
                membership_account_id,
                member_level,
                effective_from_ts,
                effective_to_ts,
                evaluated_at,
                r12_valid_spend,
                change_type
            )
        VALUES (
            :membership_account_id,
            :member_level,
            :effective_from_ts,
            :effective_to_ts,
            :evaluated_at,
            :r12_valid_spend,
            :change_type
        )
        """
    )

    order_insert_rows = [
        {
            "order_code": row[
                "order_code"
            ],
            "customer_id": (
                customer_id_lookup[
                    row["customer_code"]
                ]
            ),
            "channel_id": (
                channel_id_lookup[
                    row["channel_code"]
                ]
            ),
            "shipping_region_id": (
                region_id_lookup[
                    row[
                        "shipping_region_code"
                    ]
                ]
            ),
            "campaign_id": (
                campaign_id_lookup[
                    row["campaign_code"]
                ]
                if row["campaign_code"]
                    is not None
                else None
            ),
            "order_created_at": row[
                "order_created_at"
            ],
            "paid_at": row["paid_at"],
            "delivered_at": row[
                "delivered_at"
            ],
            "order_status": row[
                "order_status"
            ],
            "member_level_at_order": (
                row[
                    "member_level_at_order"
                ]
            ),
            "order_list_amount": row[
                "order_list_amount"
            ],
            "order_discount_amount": (
                row[
                    "order_discount_amount"
                ]
            ),
            "order_paid_amount": row[
                "order_paid_amount"
            ],
        }
        for row in bundle.order_rows
    ]

    with engine.begin() as connection:
        # 在真正写入的同一事务中再次检查空表状态。
        current_reference_data = (
            load_reference_data(
                connection
            )
        )

        validate_reference_data(
            reference_data=(
                current_reference_data
            ),
            manifest=manifest,
            window=window,
        )

        validate_transaction_target_state(
            connection=connection,
            manifest=manifest,
            reference_data=(
                current_reference_data
            ),
            window=window,
        )

        connection.execute(
            order_insert_sql,
            order_insert_rows,
        )

        order_records = _read_rows(
            connection,
            """
            SELECT
                order_id,
                order_code
            FROM beauty_bi_v2.fact_orders
            ORDER BY order_code
            """,
        )

        order_id_lookup = {
            row["order_code"]:
                row["order_id"]
            for row in order_records
        }

        if len(order_id_lookup) != len(
            bundle.order_rows
        ):
            raise RuntimeError(
                "fact_orders 写入后"
                " order_id 映射数量不正确。"
            )

        item_insert_rows = [
            {
                "order_id": (
                    order_id_lookup[
                        row["order_code"]
                    ]
                ),
                "product_id": (
                    product_id_lookup[
                        row["sku_code"]
                    ]
                ),
                "promotion_id": (
                    promotion_id_lookup[
                        row[
                            "promotion_code"
                        ]
                    ]
                    if row[
                        "promotion_code"
                    ] is not None
                    else None
                ),
                "quantity": row[
                    "quantity"
                ],
                "unit_list_price": row[
                    "unit_list_price"
                ],
                "unit_paid_price": row[
                    "unit_paid_price"
                ],
                "item_list_amount": row[
                    "item_list_amount"
                ],
                "item_discount_amount": (
                    row[
                        "item_discount_amount"
                    ]
                ),
                "item_paid_amount": row[
                    "item_paid_amount"
                ],
                "unit_cost_at_order": row[
                    "unit_cost_at_order"
                ],
                "item_cost_amount": row[
                    "item_cost_amount"
                ],
            }
            for row in bundle.item_rows
        ]

        connection.execute(
            item_insert_sql,
            item_insert_rows,
        )

        item_records = _read_rows(
            connection,
            """
            SELECT
                item.order_item_id,
                orders.order_id,
                orders.order_code,
                product.sku_code
            FROM
                beauty_bi_v2.fact_order_items
                    AS item
            INNER JOIN
                beauty_bi_v2.fact_orders
                    AS orders
                ON orders.order_id =
                    item.order_id
            INNER JOIN
                beauty_bi_v2.dim_product
                    AS product
                ON product.product_id =
                    item.product_id
            ORDER BY
                orders.order_code,
                product.sku_code
            """,
        )

        item_id_lookup: dict[
            tuple[str, str],
            dict[str, Any],
        ] = {}

        for record in item_records:
            key = (
                record["order_code"],
                record["sku_code"],
            )

            if key in item_id_lookup:
                raise RuntimeError(
                    "fact_order_items 写后"
                    "出现重复 order_code × sku_code："
                    f"{key}"
                )

            item_id_lookup[key] = record

        if len(item_id_lookup) != len(
            bundle.item_rows
        ):
            raise RuntimeError(
                "fact_order_items 写入后"
                " order_item_id 映射数量不正确。"
            )

        refund_insert_rows: list[
            dict[str, Any]
        ] = []

        for row in bundle.refund_rows:
            item = generated_item_lookup[
                (
                    row["order_code"],
                    row["line_number"],
                )
            ]

            item_record = item_id_lookup[
                (
                    row["order_code"],
                    item["sku_code"],
                )
            ]

            refund_insert_rows.append(
                {
                    "order_id": (
                        order_id_lookup[
                            row["order_code"]
                        ]
                    ),
                    "order_item_id": (
                        item_record[
                            "order_item_id"
                        ]
                    ),
                    "refund_requested_at": (
                        row[
                            "refund_requested_at"
                        ]
                    ),
                    "refund_completed_at": (
                        row[
                            "refund_completed_at"
                        ]
                    ),
                    "refund_status": row[
                        "refund_status"
                    ],
                    "refund_amount": row[
                        "refund_amount"
                    ],
                    "refund_quantity": row[
                        "refund_quantity"
                    ],
                    "refund_reason": row[
                        "refund_reason"
                    ],
                }
            )

        if refund_insert_rows:
            connection.execute(
                refund_insert_sql,
                refund_insert_rows,
            )

        review_insert_rows: list[
            dict[str, Any]
        ] = []

        for row in bundle.review_rows:
            item = generated_item_lookup[
                (
                    row["order_code"],
                    row["line_number"],
                )
            ]

            item_record = item_id_lookup[
                (
                    row["order_code"],
                    item["sku_code"],
                )
            ]

            review_insert_rows.append(
                {
                    "order_item_id": (
                        item_record[
                            "order_item_id"
                        ]
                    ),
                    "reviewed_at": row[
                        "reviewed_at"
                    ],
                    "rating": row[
                        "rating"
                    ],
                    "review_text": row[
                        "review_text"
                    ],
                    "sentiment": row[
                        "sentiment"
                    ],
                }
            )

        if review_insert_rows:
            connection.execute(
                review_insert_sql,
                review_insert_rows,
            )

        tier_insert_rows = [
            {
                "membership_account_id": (
                    membership_id_lookup[
                        row["member_code"]
                    ]
                ),
                "member_level": row[
                    "member_level"
                ],
                "effective_from_ts": row[
                    "effective_from_ts"
                ],
                "effective_to_ts": row[
                    "effective_to_ts"
                ],
                "evaluated_at": row[
                    "evaluated_at"
                ],
                "r12_valid_spend": row[
                    "r12_valid_spend"
                ],
                "change_type": row[
                    "change_type"
                ],
            }
            for row in (
                bundle.tier_history_rows
            )
        ]

        connection.execute(
            tier_insert_sql,
            tier_insert_rows,
        )

        actual_order_rows = [
            dict(row)
            for row in connection.execute(
                text(
                    """
                    SELECT
                        orders.order_code,
                        customer.customer_code,
                        channel.channel_code,
                        region.region_code
                            AS shipping_region_code,
                        campaign.campaign_code,
                        orders.order_created_at,
                        orders.paid_at,
                        orders.delivered_at,
                        orders.order_status,
                        orders.member_level_at_order,
                        orders.order_list_amount,
                        orders.order_discount_amount,
                        orders.order_paid_amount
                    FROM
                        beauty_bi_v2.fact_orders
                            AS orders
                    INNER JOIN
                        beauty_bi_v2.dim_customer
                            AS customer
                        ON customer.customer_id =
                            orders.customer_id
                    INNER JOIN
                        beauty_bi_v2.dim_channel
                            AS channel
                        ON channel.channel_id =
                            orders.channel_id
                    INNER JOIN
                        beauty_bi_v2.dim_region
                            AS region
                        ON region.region_id =
                            orders.shipping_region_id
                    LEFT JOIN
                        beauty_bi_v2.dim_campaign
                            AS campaign
                        ON campaign.campaign_id =
                            orders.campaign_id
                    ORDER BY orders.order_code
                    """
                )
            ).mappings().all()
        ]

        expected_order_rows = (
            _canonical_order_rows(
                bundle.order_rows
            )
        )

        _assert_database_rows_equal(
            expected_rows=(
                expected_order_rows
            ),
            actual_rows=actual_order_rows,
            entity_name="fact_orders",
        )

        actual_item_rows = [
            dict(row)
            for row in connection.execute(
                text(
                    """
                    SELECT
                        orders.order_code,
                        product.sku_code,
                        promotion.promotion_code,
                        item.quantity,
                        item.unit_list_price,
                        item.unit_paid_price,
                        item.item_list_amount,
                        item.item_discount_amount,
                        item.item_paid_amount,
                        item.unit_cost_at_order,
                        item.item_cost_amount
                    FROM
                        beauty_bi_v2.
                        fact_order_items
                            AS item
                    INNER JOIN
                        beauty_bi_v2.fact_orders
                            AS orders
                        ON orders.order_id =
                            item.order_id
                    INNER JOIN
                        beauty_bi_v2.dim_product
                            AS product
                        ON product.product_id =
                            item.product_id
                    LEFT JOIN
                        beauty_bi_v2.dim_promotion
                            AS promotion
                        ON promotion.promotion_id =
                            item.promotion_id
                    ORDER BY
                        orders.order_code,
                        product.sku_code
                    """
                )
            ).mappings().all()
        ]

        expected_item_rows = (
            _canonical_item_rows(
                bundle.item_rows
            )
        )

        _assert_database_rows_equal(
            expected_rows=(
                expected_item_rows
            ),
            actual_rows=actual_item_rows,
            entity_name=(
                "fact_order_items"
            ),
        )

        actual_refund_rows = [
            dict(row)
            for row in connection.execute(
                text(
                    """
                    SELECT
                        orders.order_code,
                        product.sku_code,
                        refund.refund_requested_at,
                        refund.refund_completed_at,
                        refund.refund_status,
                        refund.refund_amount,
                        refund.refund_quantity,
                        refund.refund_reason
                    FROM
                        beauty_bi_v2.fact_refunds
                            AS refund
                    INNER JOIN
                        beauty_bi_v2.fact_orders
                            AS orders
                        ON orders.order_id =
                            refund.order_id
                    INNER JOIN
                        beauty_bi_v2.
                        fact_order_items
                            AS item
                        ON item.order_item_id =
                            refund.order_item_id
                    INNER JOIN
                        beauty_bi_v2.dim_product
                            AS product
                        ON product.product_id =
                            item.product_id
                    ORDER BY
                        orders.order_code,
                        product.sku_code
                    """
                )
            ).mappings().all()
        ]

        expected_refund_rows = (
            _canonical_refund_rows(
                rows=bundle.refund_rows,
                item_lookup=(
                    generated_item_lookup
                ),
            )
        )

        _assert_database_rows_equal(
            expected_rows=(
                expected_refund_rows
            ),
            actual_rows=actual_refund_rows,
            entity_name="fact_refunds",
        )

        actual_review_rows = [
            dict(row)
            for row in connection.execute(
                text(
                    """
                    SELECT
                        orders.order_code,
                        product.sku_code,
                        review.reviewed_at,
                        review.rating,
                        review.review_text,
                        review.sentiment
                    FROM
                        beauty_bi_v2.fact_reviews
                            AS review
                    INNER JOIN
                        beauty_bi_v2.
                        fact_order_items
                            AS item
                        ON item.order_item_id =
                            review.order_item_id
                    INNER JOIN
                        beauty_bi_v2.fact_orders
                            AS orders
                        ON orders.order_id =
                            item.order_id
                    INNER JOIN
                        beauty_bi_v2.dim_product
                            AS product
                        ON product.product_id =
                            item.product_id
                    ORDER BY
                        orders.order_code,
                        product.sku_code
                    """
                )
            ).mappings().all()
        ]

        expected_review_rows = (
            _canonical_review_rows(
                rows=bundle.review_rows,
                item_lookup=(
                    generated_item_lookup
                ),
            )
        )

        _assert_database_rows_equal(
            expected_rows=(
                expected_review_rows
            ),
            actual_rows=actual_review_rows,
            entity_name="fact_reviews",
        )

        actual_tier_rows = [
            dict(row)
            for row in connection.execute(
                text(
                    """
                    SELECT
                        account.member_code,
                        history.member_level,
                        history.effective_from_ts,
                        history.effective_to_ts,
                        history.evaluated_at,
                        history.r12_valid_spend,
                        history.change_type
                    FROM
                        beauty_bi_v2.
                        fact_membership_tier_history
                            AS history
                    INNER JOIN
                        beauty_bi_v2.
                        dim_membership_account
                            AS account
                        ON
                            account.
                            membership_account_id
                            =
                            history.
                            membership_account_id
                    ORDER BY
                        account.member_code,
                        history.effective_from_ts
                    """
                )
            ).mappings().all()
        ]

        expected_tier_rows = (
            _canonical_tier_rows(
                bundle.tier_history_rows
            )
        )

        _assert_database_rows_equal(
            expected_rows=(
                expected_tier_rows
            ),
            actual_rows=actual_tier_rows,
            entity_name=(
                "fact_membership_tier_history"
            ),
        )

        order_amount_mismatch_count = (
            connection.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM (
                        SELECT
                            orders.order_id,
                            orders.order_list_amount,
                            orders.order_discount_amount,
                            orders.order_paid_amount,
                            SUM(
                                item.item_list_amount
                            ) AS item_list_amount,
                            SUM(
                                item.item_discount_amount
                            ) AS item_discount_amount,
                            SUM(
                                item.item_paid_amount
                            ) AS item_paid_amount
                        FROM
                            beauty_bi_v2.fact_orders
                                AS orders
                        INNER JOIN
                            beauty_bi_v2.
                            fact_order_items
                                AS item
                            ON item.order_id =
                                orders.order_id
                        GROUP BY
                            orders.order_id,
                            orders.order_list_amount,
                            orders.
                                order_discount_amount,
                            orders.order_paid_amount
                    ) AS comparison
                    WHERE
                        order_list_amount
                            <> item_list_amount
                        OR order_discount_amount
                            <> item_discount_amount
                        OR order_paid_amount
                            <> item_paid_amount
                    """
                )
            ).scalar_one()
        )

        if order_amount_mismatch_count != 0:
            raise RuntimeError(
                "数据库订单头金额与"
                "明细汇总不一致："
                f"count="
                f"{order_amount_mismatch_count}"
            )

        invalid_refund_amount_count = (
            connection.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM
                        beauty_bi_v2.fact_refunds
                            AS refund
                    INNER JOIN
                        beauty_bi_v2.
                        fact_order_items
                            AS item
                        ON item.order_item_id =
                            refund.order_item_id
                    WHERE
                        refund.refund_amount
                            > item.item_paid_amount
                        OR refund.refund_quantity
                            > item.quantity
                    """
                )
            ).scalar_one()
        )

        if invalid_refund_amount_count != 0:
            raise RuntimeError(
                "数据库退款金额或数量"
                "超过订单明细上限："
                f"count="
                f"{invalid_refund_amount_count}"
            )

        paid_tail_count = (
            connection.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM
                        beauty_bi_v2.fact_orders
                    WHERE
                        paid_at
                            > :business_end_ts
                    """
                ),
                {
                    "business_end_ts": (
                        datetime.combine(
                            window.
                            business_end_date,
                            datetime.max.time(),
                        ).replace(
                            microsecond=0
                        )
                    )
                },
            ).scalar_one()
        )

        if paid_tail_count != 0:
            raise RuntimeError(
                "观察尾窗中出现新支付订单："
                f"count={paid_tail_count}"
            )

        delivered_after_observation_count = (
            connection.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM
                        beauty_bi_v2.fact_orders
                    WHERE
                        delivered_at
                            > :observation_end_ts
                    """
                ),
                {
                    "observation_end_ts": (
                        datetime.combine(
                            window.
                            observation_end_date,
                            datetime.max.time(),
                        ).replace(
                            microsecond=0
                        )
                    )
                },
            ).scalar_one()
        )

        if (
            delivered_after_observation_count
            != 0
        ):
            raise RuntimeError(
                "数据库存在观察窗口外"
                "送达事件："
                f"count="
                f"{delivered_after_observation_count}"
            )

        tier_open_interval_error_count = (
            connection.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM (
                        SELECT
                            membership_account_id
                        FROM
                            beauty_bi_v2.
                            fact_membership_tier_history
                        GROUP BY
                            membership_account_id
                        HAVING
                            COUNT(*) FILTER (
                                WHERE
                                    effective_to_ts
                                    IS NULL
                            ) <> 1
                    ) AS invalid_accounts
                    """
                )
            ).scalar_one()
        )

        if (
            tier_open_interval_error_count
            != 0
        ):
            raise RuntimeError(
                "数据库会员等级开放区间"
                "数量不正确："
                f"account_count="
                f"{tier_open_interval_error_count}"
            )

        tier_overlap_count = (
            connection.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM
                        beauty_bi_v2.
                        fact_membership_tier_history
                            AS left_row
                    INNER JOIN
                        beauty_bi_v2.
                        fact_membership_tier_history
                            AS right_row
                        ON
                            right_row.
                            membership_account_id
                            =
                            left_row.
                            membership_account_id
                        AND
                            right_row.
                            tier_history_id
                            >
                            left_row.
                            tier_history_id
                        AND
                            left_row.
                            effective_from_ts
                            <
                            COALESCE(
                                right_row.
                                effective_to_ts,
                                TIMESTAMP
                                    '9999-12-31'
                            )
                        AND
                            right_row.
                            effective_from_ts
                            <
                            COALESCE(
                                left_row.
                                effective_to_ts,
                                TIMESTAMP
                                    '9999-12-31'
                            )
                    """
                )
            ).scalar_one()
        )

        if tier_overlap_count != 0:
            raise RuntimeError(
                "数据库会员等级历史"
                "存在重叠区间："
                f"count={tier_overlap_count}"
            )

        final_counts = {
            table_name: (
                connection.execute(
                    text(
                        "SELECT COUNT(*) "
                        f"FROM beauty_bi_v2."
                        f"{table_name}"
                    )
                ).scalar_one()
            )
            for table_name in (
                "fact_marketing_spend",
                "fact_orders",
                "fact_order_items",
                "fact_refunds",
                "fact_reviews",
                "fact_membership_tier_history",
            )
        }

        expected_counts = {
            "fact_orders": len(
                bundle.order_rows
            ),
            "fact_order_items": len(
                bundle.item_rows
            ),
            "fact_refunds": len(
                bundle.refund_rows
            ),
            "fact_reviews": len(
                bundle.review_rows
            ),
            (
                "fact_membership_tier_history"
            ): len(
                bundle.tier_history_rows
            ),
        }

        for table_name, expected_count in (
            expected_counts.items()
        ):
            actual_count = final_counts[
                table_name
            ]

            if actual_count != expected_count:
                raise RuntimeError(
                    f"{table_name} 最终行数"
                    "不正确："
                    f"expected={expected_count}, "
                    f"actual={actual_count}"
                )

    return final_counts


def seed_transactions(
    manifest: dict[str, Any],
) -> None:
    """
    正式生成并原子写入 Day65 剩余五张事实表。
    """
    window = build_generation_window(
        manifest
    )

    with engine.connect() as connection:
        reference_data = load_reference_data(
            connection
        )

        validate_reference_data(
            reference_data=reference_data,
            manifest=manifest,
            window=window,
        )

        marketing_spend_rows = (
            validate_transaction_target_state(
                connection=connection,
                manifest=manifest,
                reference_data=reference_data,
                window=window,
            )
        )

    print(
        "Building complete Day65 "
        "transaction bundle..."
    )

    bundle = build_transaction_bundle(
        manifest=manifest,
        reference_data=reference_data,
        marketing_spend_rows=(
            marketing_spend_rows
        ),
        window=window,
    )

    print(
        "Transaction bundle validation passed."
    )
    print(
        "Generated counts: "
        f"orders={len(bundle.order_rows)}, "
        f"items={len(bundle.item_rows)}, "
        f"refunds={len(bundle.refund_rows)}, "
        f"reviews={len(bundle.review_rows)}, "
        "tier_history="
        f"{len(bundle.tier_history_rows)}"
    )

    final_counts = insert_transaction_bundle(
        bundle=bundle,
        manifest=manifest,
        reference_data=reference_data,
        window=window,
    )

    order_status_counts = Counter(
        row["order_status"]
        for row in bundle.order_rows
    )

    refund_status_counts = Counter(
        row["refund_status"]
        for row in bundle.refund_rows
    )

    rating_counts = Counter(
        row["rating"]
        for row in bundle.review_rows
    )

    tier_change_counts = Counter(
        row["change_type"]
        for row in (
            bundle.tier_history_rows
        )
    )

    print(
        "Day65 transaction database seed passed."
    )
    print(
        "Final table counts: "
        f"{final_counts}"
    )
    print(
        "Order status counts: "
        f"{dict(order_status_counts)}"
    )
    print(
        "Refund status counts: "
        f"{dict(refund_status_counts)}"
    )
    print(
        "Review rating counts: "
        f"{dict(rating_counts)}"
    )
    print(
        "Tier change counts: "
        f"{dict(tier_change_counts)}"
    )
    print(
        "Order amount aggregation check: passed."
    )
    print(
        "Refund item-order foreign-key check: "
        "passed."
    )
    print(
        "Review item uniqueness check: passed."
    )
    print(
        "Member-level-at-order check: passed."
    )
    print(
        "Tier interval overlap check: passed."
    )
    print(
        "Observation-tail boundary checks: passed."
    )
    print(
        "Database row comparisons: passed."
    )
    print(
        "Atomic transaction: committed."
    )
    print(
        "Schema isolation: beauty_bi_v2 only."
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Seed Beauty BI V2 transaction facts."
        )
    )

    parser.add_argument(
        "target",
        choices={
            "preflight",
            "marketing_spend_preview",
            "marketing_spend",
            "simulation_profiles_preview",
            "order_allocation_preview",
            "order_headers_preview",
            "order_items_preview",
            "fulfillment_preview",
            "refunds_preview",
            "reviews_preview",
            "membership_tiers_preview",
            "transactions_seed",
        },
        help=(
            "选择 Day65 交易生成目标。"
        ),
    )

    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    loaded_manifest = (
        load_and_validate_day65_manifest()
    )

    if args.target == "preflight":
        run_preflight(loaded_manifest)
    elif args.target == "marketing_spend_preview":
        preview_marketing_spend(loaded_manifest)
    elif args.target == "marketing_spend":
        seed_marketing_spend(loaded_manifest)
    elif args.target == "simulation_profiles_preview":
        preview_simulation_profiles(loaded_manifest)
    elif args.target == "order_allocation_preview":
        preview_order_allocation(loaded_manifest)
    elif args.target == "order_headers_preview":
        preview_order_headers(loaded_manifest)
    elif args.target == "order_items_preview":
        preview_order_items(loaded_manifest)
    elif args.target == "fulfillment_preview":
        preview_fulfillment(loaded_manifest)
    elif args.target == "refunds_preview":
        preview_refunds(loaded_manifest)
    elif args.target == "reviews_preview":
        preview_reviews(loaded_manifest)
    elif args.target == "membership_tiers_preview":
        preview_membership_tiers(loaded_manifest)
    elif args.target == "transactions_seed":
        seed_transactions(loaded_manifest)
