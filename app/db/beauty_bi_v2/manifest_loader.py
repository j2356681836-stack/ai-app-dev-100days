from pathlib import Path
from typing import Any
from datetime import date, datetime,  time, timedelta

import yaml


MANIFEST_PATH = Path(__file__).with_name("dataset_manifest.yaml")


def load_manifest(
    manifest_path: Path = MANIFEST_PATH,
) -> dict[str, Any]:
    """
    读取原始 Dataset Manifest。

    当前函数只负责：
    1. 检查文件是否存在；
    2. 解析 YAML；
    3. 检查根节点是否为字典。
    """
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"Dataset Manifest 不存在：{manifest_path}"
        )

    with manifest_path.open(
        "r",
        encoding="utf-8",
    ) as file:
        manifest = yaml.safe_load(file)

    if not isinstance(manifest, dict):
        raise ValueError(
            "Dataset Manifest 根节点必须是字典。"
        )

    return manifest


def get_active_scale_profile(
    manifest: dict[str, Any],
) -> tuple[str, dict[str, int]]:
    """
    读取当前激活的 Scale Profile。
    """
    try:
        profile_name = manifest[
            "generation"
        ][
            "scale_profile"
        ]
    except KeyError as exc:
        raise ValueError(
            "Manifest 缺少 generation.scale_profile。"
        ) from exc

    if not isinstance(profile_name, str):
        raise ValueError(
            "generation.scale_profile 必须是字符串。"
        )

    scale_profiles = manifest.get("scale_profiles")

    if not isinstance(scale_profiles, dict):
        raise ValueError(
            "Manifest 缺少有效的 scale_profiles。"
        )

    if profile_name not in scale_profiles:
        raise ValueError(
            f"Scale Profile 不存在：{profile_name}"
        )

    profile = scale_profiles[profile_name]

    if not isinstance(profile, dict):
        raise ValueError(
            f"Scale Profile {profile_name} 必须是字典。"
        )

    required_fields = {
        "customers",
        "membership_accounts",
        "products",
        "expected_orders",
    }

    missing_fields = required_fields - profile.keys()

    if missing_fields:
        raise ValueError(
            "Scale Profile 缺少字段："
            f"{sorted(missing_fields)}"
        )

    for field_name in required_fields:
        value = profile[field_name]

        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or value <= 0
        ):
            raise ValueError(
                f"scale_profiles.{profile_name}."
                f"{field_name} 必须是正整数，"
                f"当前值为：{value!r}"
            )

    return profile_name, profile


def parse_manifest_date(
    value: Any,
    field_name: str,
) -> date:
    """
    将 Manifest 日期解析为 date。

    yaml.safe_load() 可能把未加引号的日期直接解析为 date，
    因此同时兼容 date 和 ISO 字符串。
    """
    if isinstance(value, date):
        return value

    if not isinstance(value, str):
        raise ValueError(
            f"{field_name} 必须是 ISO 日期字符串，"
            f"当前值为：{value!r}"
        )

    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(
            f"{field_name} 不是合法 ISO 日期：{value!r}"
        ) from exc


def parse_manifest_datetime(
    value: Any,
    field_name: str,
) -> datetime:
    """
    将 Manifest 时间戳解析为 datetime。

    当前 dim_campaign.status_cutoff 对应 PostgreSQL
    TIMESTAMP，因此不允许带时区信息。
    """
    if isinstance(value, datetime):
        parsed_value = value
    elif isinstance(value, date):
        raise ValueError(
            f"{field_name} 必须包含具体时间，"
            f"不能只有日期：{value!r}"
        )
    elif isinstance(value, str):
        try:
            parsed_value = datetime.fromisoformat(
                value
            )
        except ValueError as exc:
            raise ValueError(
                f"{field_name} 不是合法 ISO 时间戳："
                f"{value!r}"
            ) from exc
    else:
        raise ValueError(
            f"{field_name} 必须是 ISO 时间戳，"
            f"当前值为：{value!r}"
        )

    if parsed_value.tzinfo is not None:
        raise ValueError(
            f"{field_name} 不能包含时区信息，"
            "因为 dim_campaign.status_cutoff "
            "使用 PostgreSQL TIMESTAMP。"
        )

    return parsed_value


def parse_manifest_time(
    value: Any,
    field_name: str,
) -> time:
    """
    将 Manifest 时间解析为 time。

    当前 joined_at 对应 PostgreSQL TIMESTAMP，
    因此这里只接受不包含时区的本地时间。
    """
    if isinstance(value, time):
        parsed_value = value
    elif isinstance(value, str):
        try:
            parsed_value = time.fromisoformat(
                value
            )
        except ValueError as exc:
            raise ValueError(
                f"{field_name} 不是合法 ISO 时间："
                f"{value!r}"
            ) from exc
    else:
        raise ValueError(
            f"{field_name} 必须是 ISO 时间字符串，"
            f"当前值为：{value!r}"
        )

    if parsed_value.tzinfo is not None:
        raise ValueError(
            f"{field_name} 不能包含时区信息，"
            "因为 dim_membership_account.joined_at "
            "使用 PostgreSQL TIMESTAMP。"
        )

    return parsed_value


def validate_day64_calendar(
    manifest: dict[str, Any],
) -> None:
    """
    验证 Day64 日期范围和固定节假日区间。
    """
    generation = manifest.get("generation")

    if not isinstance(generation, dict):
        raise ValueError(
            "Manifest 缺少有效的 generation。"
        )

    business_start_date = parse_manifest_date(
        generation.get("business_start_date"),
        "generation.business_start_date",
    )

    business_end_date = parse_manifest_date(
        generation.get("business_end_date"),
        "generation.business_end_date",
    )

    observation_end_date = parse_manifest_date(
        generation.get("event_observation_end_date"),
        "generation.event_observation_end_date",
    )

    if not (
        business_start_date
        <= business_end_date
        <= observation_end_date
    ):
        raise ValueError(
            "日期范围必须满足："
            "business_start_date <= business_end_date "
            "<= event_observation_end_date。"
        )

    business_calendar = manifest.get(
        "business_calendar"
    )

    if not isinstance(business_calendar, dict):
        raise ValueError(
            "Manifest 缺少有效的 business_calendar。"
        )

    holidays = business_calendar.get("holidays")

    if not isinstance(holidays, dict):
        raise ValueError(
            "business_calendar.holidays 必须是字典。"
        )

    if holidays.get("source") != "fixed_config":
        raise ValueError(
            "Day64 当前只支持 holidays.source "
            "= fixed_config。"
        )

    periods = holidays.get("periods")

    if not isinstance(periods, list) or not periods:
        raise ValueError(
            "business_calendar.holidays.periods "
            "必须是非空列表。"
        )

    parsed_periods = []

    for index, period in enumerate(periods):
        field_prefix = (
            "business_calendar.holidays."
            f"periods[{index}]"
        )

        if not isinstance(period, dict):
            raise ValueError(
                f"{field_prefix} 必须是字典。"
            )

        holiday_name = period.get("holiday_name")

        if (
            not isinstance(holiday_name, str)
            or not holiday_name.strip()
        ):
            raise ValueError(
                f"{field_prefix}.holiday_name "
                "必须是非空字符串。"
            )

        period_start = parse_manifest_date(
            period.get("start_date"),
            f"{field_prefix}.start_date",
        )

        period_end = parse_manifest_date(
            period.get("end_date"),
            f"{field_prefix}.end_date",
        )

        if period_start > period_end:
            raise ValueError(
                f"{field_prefix} 的 start_date "
                "不能晚于 end_date。"
            )

        if not (
            business_start_date
            <= period_start
            <= period_end
            <= observation_end_date
        ):
            raise ValueError(
                f"{field_prefix} 超出 dim_date "
                "生成范围。"
            )

        parsed_periods.append(
            (
                period_start,
                period_end,
                holiday_name.strip(),
            )
        )

    parsed_periods.sort(key=lambda item: item[0])

    for previous, current in zip(
        parsed_periods,
        parsed_periods[1:],
    ):
        previous_start, previous_end, previous_name = (
            previous
        )
        current_start, current_end, current_name = current

        if current_start <= previous_end:
            raise ValueError(
                "节假日区间发生重叠："
                f"{previous_name} "
                f"[{previous_start}, {previous_end}] 与 "
                f"{current_name} "
                f"[{current_start}, {current_end}]。"
            )


def validate_campaigns(
    manifest: dict[str, Any],
) -> None:
    """
    验证固定活动配置。

    主要检查：
    1. 活动字段和稳定编码；
    2. 活动日期边界；
    3. status_cutoff 早于活动开始日零点；
    4. campaign_code 和 campaign_name 唯一；
    5. always_on 活动完整覆盖业务日期，
       且每个业务日期只能命中一个 always_on。
    """
    business_calendar = manifest.get(
        "business_calendar"
    )

    if not isinstance(business_calendar, dict):
        raise ValueError(
            "Manifest 缺少有效的 business_calendar。"
        )

    campaigns = business_calendar.get(
        "campaigns"
    )

    if not isinstance(campaigns, list) or not campaigns:
        raise ValueError(
            "business_calendar.campaigns "
            "必须是非空列表。"
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

    generation = manifest["generation"]

    business_start_date = parse_manifest_date(
        generation["business_start_date"],
        "generation.business_start_date",
    )

    business_end_date = parse_manifest_date(
        generation["business_end_date"],
        "generation.business_end_date",
    )

    campaign_codes: set[str] = set()
    campaign_names: set[str] = set()

    family_types: dict[str, str] = {}

    parsed_campaigns: list[
        dict[str, Any]
    ] = []

    for index, campaign in enumerate(campaigns):
        field_prefix = (
            f"business_calendar.campaigns[{index}]"
        )

        if not isinstance(campaign, dict):
            raise ValueError(
                f"{field_prefix} 必须是字典。"
            )

        missing_fields = (
            required_fields - campaign.keys()
        )

        if missing_fields:
            raise ValueError(
                f"{field_prefix} 缺少字段："
                f"{sorted(missing_fields)}"
            )

        for field_name in string_fields:
            value = campaign[field_name]

            if (
                not isinstance(value, str)
                or not value.strip()
            ):
                raise ValueError(
                    f"{field_prefix}.{field_name} "
                    "必须是非空字符串。"
                )

        campaign_code = campaign[
            "campaign_code"
        ].strip()

        campaign_family = campaign[
            "campaign_family"
        ].strip()

        campaign_name = campaign[
            "campaign_name"
        ].strip()

        campaign_type = campaign[
            "campaign_type"
        ].strip()

        objective = campaign[
            "objective"
        ].strip()

        if campaign_code != campaign_code.upper():
            raise ValueError(
                f"{field_prefix}.campaign_code "
                "必须使用大写稳定编码："
                f"{campaign_code!r}"
            )

        normalized_code = campaign_code.replace(
            "_",
            "",
        )

        if not normalized_code.isalnum():
            raise ValueError(
                f"{field_prefix}.campaign_code "
                "只能包含字母、数字和下划线："
                f"{campaign_code!r}"
            )

        if campaign_family != campaign_family.upper():
            raise ValueError(
                f"{field_prefix}.campaign_family "
                "必须使用大写稳定编码："
                f"{campaign_family!r}"
            )

        normalized_family = (
            campaign_family.replace("_", "")
        )

        if not normalized_family.isalnum():
            raise ValueError(
                f"{field_prefix}.campaign_family "
                "只能包含字母、数字和下划线："
                f"{campaign_family!r}"
            )

        if campaign_code in campaign_codes:
            raise ValueError(
                "campaign_code 不能重复："
                f"{campaign_code}"
            )

        if campaign_name in campaign_names:
            raise ValueError(
                "campaign_name 不能重复："
                f"{campaign_name}"
            )

        if (
            campaign_type
            not in allowed_campaign_types
        ):
            raise ValueError(
                f"{field_prefix}.campaign_type "
                "不在允许范围内："
                f"{campaign_type!r}"
            )

        start_date = parse_manifest_date(
            campaign["start_date"],
            f"{field_prefix}.start_date",
        )

        end_date = parse_manifest_date(
            campaign["end_date"],
            f"{field_prefix}.end_date",
        )

        status_cutoff = parse_manifest_datetime(
            campaign["status_cutoff"],
            f"{field_prefix}.status_cutoff",
        )

        if start_date > end_date:
            raise ValueError(
                f"{field_prefix} 的 start_date "
                "不能晚于 end_date。"
            )

        if not (
            business_start_date
            <= start_date
            <= end_date
            <= business_end_date
        ):
            raise ValueError(
                f"{field_prefix} 超出业务日期范围："
                f"{start_date} -> {end_date}"
            )

        campaign_start_timestamp = (
            datetime.combine(
                start_date,
                datetime.min.time(),
            )
        )

        if status_cutoff >= campaign_start_timestamp:
            raise ValueError(
                f"{field_prefix}.status_cutoff "
                "必须早于活动开始日零点："
                f"status_cutoff={status_cutoff}, "
                "campaign_start="
                f"{campaign_start_timestamp}"
            )

        existing_family_type = family_types.get(
            campaign_family
        )

        if (
            existing_family_type is not None
            and existing_family_type
            != campaign_type
        ):
            raise ValueError(
                "同一 campaign_family 不能出现"
                "不同 campaign_type："
                f"campaign_family={campaign_family}, "
                f"existing_type={existing_family_type}, "
                f"current_type={campaign_type}"
            )

        family_types[
            campaign_family
        ] = campaign_type

        campaign_codes.add(campaign_code)
        campaign_names.add(campaign_name)

        parsed_campaigns.append(
            {
                "campaign_code": campaign_code,
                "campaign_family": (
                    campaign_family
                ),
                "campaign_name": campaign_name,
                "campaign_type": campaign_type,
                "start_date": start_date,
                "end_date": end_date,
                "status_cutoff": status_cutoff,
                "objective": objective,
            }
        )

    always_on_campaigns = [
        campaign
        for campaign in parsed_campaigns
        if campaign["campaign_type"] == "always_on"
    ]

    if not always_on_campaigns:
        raise ValueError(
            "至少需要一个 always_on campaign，"
            "用于承载普通日期营销费用。"
        )

    current_date = business_start_date

    while current_date <= business_end_date:
        matched_always_on_campaigns = [
            campaign
            for campaign in always_on_campaigns
            if (
                campaign["start_date"]
                <= current_date
                <= campaign["end_date"]
            )
        ]

        if len(matched_always_on_campaigns) == 0:
            raise ValueError(
                "业务日期没有 always_on campaign "
                "覆盖："
                f"{current_date}"
            )

        if len(matched_always_on_campaigns) > 1:
            matched_codes = [
                campaign["campaign_code"]
                for campaign
                in matched_always_on_campaigns
            ]

            raise ValueError(
                "业务日期同时命中多个 always_on "
                "campaign："
                f"date={current_date}, "
                f"campaigns={matched_codes}"
            )

        current_date += timedelta(days=1)


def validate_probability_distribution(
    distribution: dict[Any, Any],
    distribution_name: str,
) -> None:
    """
    检查概率分布：

    1. 必须是非空字典；
    2. 每个概率必须在 [0, 1]；
    3. 概率合计必须约等于 1。
    """
    if not isinstance(distribution, dict) or not distribution:
        raise ValueError(
            f"{distribution_name} 必须是非空字典。"
        )

    for key, probability in distribution.items():
        if (
            isinstance(probability, bool)
            or not isinstance(probability, (int, float))
        ):
            raise ValueError(
                f"{distribution_name}[{key!r}] "
                f"必须是数值，当前值为：{probability!r}"
            )

        if not 0 <= probability <= 1:
            raise ValueError(
                f"{distribution_name}[{key!r}] "
                f"必须位于 [0, 1]，当前值为：{probability}"
            )

    total = sum(distribution.values())

    if abs(total - 1.0) > 1e-9:
        raise ValueError(
            f"{distribution_name} 概率合计必须为 1，"
            f"当前合计为：{total}"
        )


def validate_day64_manifest(
    manifest: dict[str, Any],
) -> None:
    """
    验证 Day64 Fixed Dimensions & Identity Seed
    当前真正依赖的 Manifest 配置。
    """
    validate_day64_calendar(manifest)
    validate_campaigns(manifest)
    validate_fixed_regions(manifest)
    validate_customer_generation(manifest)
    validate_fixed_channels(manifest)
    validate_membership_generation(manifest)
    validate_identity_mapping_generation(manifest)
    validate_channel_binding_generation(manifest)
    validate_fixed_promotions(manifest)
    validate_product_generation(manifest)

    _, profile = get_active_scale_profile(manifest)

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

    if (
        isinstance(mapped_customer_ratio, bool)
        or not isinstance(mapped_customer_ratio, (int, float))
        or not 0 <= mapped_customer_ratio <= 1
    ):
        raise ValueError(
            "mapped_customer_ratio 必须是 [0, 1] "
            f"范围内的数值，当前值为：{mapped_customer_ratio!r}"
        )

    validate_probability_distribution(
        parameters["membership_status_distribution"],
        "membership_status_distribution",
    )

    validate_probability_distribution(
        parameters["channel_binding_count_distribution"],
        "channel_binding_count_distribution",
    )

    mapped_customer_count = round(
        profile["customers"] * mapped_customer_ratio
    )

    if mapped_customer_count > profile["membership_accounts"]:
        raise ValueError(
            "customer-membership 映射数量不能超过 "
            "membership account 数量："
            f"mapped_customer_count={mapped_customer_count}, "
            "membership_accounts="
            f"{profile['membership_accounts']}"
        )


def validate_fixed_regions(
    manifest: dict[str, Any],
) -> None:
    """
    验证固定地区维度配置。
    """
    fixed_dimensions = manifest.get(
        "fixed_dimensions"
    )

    if not isinstance(fixed_dimensions, dict):
        raise ValueError(
            "Manifest 缺少有效的 fixed_dimensions。"
        )

    regions = fixed_dimensions.get("regions")

    if not isinstance(regions, list) or not regions:
        raise ValueError(
            "fixed_dimensions.regions 必须是非空列表。"
        )

    required_fields = {
        "region_code",
        "region_name",
        "province_name",
        "region_group",
        "city_tier",
    }

    allowed_region_groups = {
        "north",
        "east",
        "south",
        "central",
        "southwest",
        "northeast",
        "northwest",
    }

    allowed_city_tiers = {
        "tier_1",
        "tier_2",
        "tier_3",
    }

    region_codes: set[str] = set()
    region_names: set[str] = set()
    actual_region_groups: set[str] = set()
    actual_city_tiers: set[str] = set()

    for index, region in enumerate(regions):
        field_prefix = (
            f"fixed_dimensions.regions[{index}]"
        )

        if not isinstance(region, dict):
            raise ValueError(
                f"{field_prefix} 必须是字典。"
            )

        missing_fields = (
            required_fields - region.keys()
        )

        if missing_fields:
            raise ValueError(
                f"{field_prefix} 缺少字段："
                f"{sorted(missing_fields)}"
            )

        for field_name in required_fields:
            value = region[field_name]

            if (
                not isinstance(value, str)
                or not value.strip()
            ):
                raise ValueError(
                    f"{field_prefix}.{field_name} "
                    "必须是非空字符串。"
                )

        region_code = region[
            "region_code"
        ].strip()

        region_name = region[
            "region_name"
        ].strip()

        region_group = region[
            "region_group"
        ].strip()

        city_tier = region[
            "city_tier"
        ].strip()

        if region_code != region_code.upper():
            raise ValueError(
                f"{field_prefix}.region_code "
                "必须使用大写稳定编码："
                f"{region_code!r}"
            )

        normalized_code = region_code.replace(
            "_",
            "",
        )

        if not normalized_code.isalnum():
            raise ValueError(
                f"{field_prefix}.region_code "
                "只能包含字母、数字和下划线："
                f"{region_code!r}"
            )

        if region_code in region_codes:
            raise ValueError(
                "region_code 不能重复："
                f"{region_code}"
            )

        if region_name in region_names:
            raise ValueError(
                "region_name 不能重复："
                f"{region_name}"
            )

        if region_group not in allowed_region_groups:
            raise ValueError(
                f"{field_prefix}.region_group "
                "不在允许范围内："
                f"{region_group!r}"
            )

        if city_tier not in allowed_city_tiers:
            raise ValueError(
                f"{field_prefix}.city_tier "
                "不在允许范围内："
                f"{city_tier!r}"
            )

        region_codes.add(region_code)
        region_names.add(region_name)
        actual_region_groups.add(region_group)
        actual_city_tiers.add(city_tier)

    missing_region_groups = (
        allowed_region_groups
        - actual_region_groups
    )

    if missing_region_groups:
        raise ValueError(
            "地区配置未覆盖全部 region_group："
            f"{sorted(missing_region_groups)}"
        )

    missing_city_tiers = (
        allowed_city_tiers
        - actual_city_tiers
    )

    if missing_city_tiers:
        raise ValueError(
            "地区配置未覆盖全部 city_tier："
            f"{sorted(missing_city_tiers)}"
        )


def validate_fixed_channels(
    manifest: dict[str, Any],
) -> None:
    """
    验证固定渠道维度配置，并检查它与
    P03 会员渠道绑定数量是否兼容。
    """
    fixed_dimensions = manifest.get(
        "fixed_dimensions"
    )

    if not isinstance(fixed_dimensions, dict):
        raise ValueError(
            "Manifest 缺少有效的 fixed_dimensions。"
        )

    channels = fixed_dimensions.get("channels")

    if not isinstance(channels, list) or not channels:
        raise ValueError(
            "fixed_dimensions.channels "
            "必须是非空列表。"
        )

    required_fields = {
        "channel_code",
        "channel_name",
        "channel_type",
        "is_sales_channel",
        "is_marketing_channel",
        "is_active",
        "supports_membership_binding",
    }

    allowed_channel_types = {
        "owned_ecommerce",
        "marketplace",
        "social_commerce",
        "social_media",
    }

    channel_codes: set[str] = set()
    channel_names: set[str] = set()

    active_sales_channel_count = 0
    active_marketing_channel_count = 0
    active_membership_binding_channel_count = 0

    for index, channel in enumerate(channels):
        field_prefix = (
            f"fixed_dimensions.channels[{index}]"
        )

        if not isinstance(channel, dict):
            raise ValueError(
                f"{field_prefix} 必须是字典。"
            )

        missing_fields = (
            required_fields - channel.keys()
        )

        if missing_fields:
            raise ValueError(
                f"{field_prefix} 缺少字段："
                f"{sorted(missing_fields)}"
            )

        for field_name in {
            "channel_code",
            "channel_name",
            "channel_type",
        }:
            value = channel[field_name]

            if (
                not isinstance(value, str)
                or not value.strip()
            ):
                raise ValueError(
                    f"{field_prefix}.{field_name} "
                    "必须是非空字符串。"
                )

        for field_name in {
            "is_sales_channel",
            "is_marketing_channel",
            "is_active",
            "supports_membership_binding",
        }:
            value = channel[field_name]

            if not isinstance(value, bool):
                raise ValueError(
                    f"{field_prefix}.{field_name} "
                    "必须是布尔值 true 或 false，"
                    f"当前值为：{value!r}"
                )

        channel_code = channel[
            "channel_code"
        ].strip()

        channel_name = channel[
            "channel_name"
        ].strip()

        channel_type = channel[
            "channel_type"
        ].strip()

        is_sales_channel = channel[
            "is_sales_channel"
        ]

        is_marketing_channel = channel[
            "is_marketing_channel"
        ]

        is_active = channel["is_active"]

        supports_membership_binding = channel[
            "supports_membership_binding"
        ]

        if supports_membership_binding and not is_active:
            raise ValueError(
                f"{field_prefix} 已停用，不能继续支持会员绑定。"
            )

        if channel_code != channel_code.upper():
            raise ValueError(
                f"{field_prefix}.channel_code "
                "必须使用大写稳定编码："
                f"{channel_code!r}"
            )

        normalized_code = channel_code.replace(
            "_",
            "",
        )

        if not normalized_code.isalnum():
            raise ValueError(
                f"{field_prefix}.channel_code "
                "只能包含字母、数字和下划线："
                f"{channel_code!r}"
            )

        if channel_code in channel_codes:
            raise ValueError(
                "channel_code 不能重复："
                f"{channel_code}"
            )

        if channel_name in channel_names:
            raise ValueError(
                "channel_name 不能重复："
                f"{channel_name}"
            )

        if channel_type not in allowed_channel_types:
            raise ValueError(
                f"{field_prefix}.channel_type "
                "不在允许范围内："
                f"{channel_type!r}"
            )

        if not (
            is_sales_channel
            or is_marketing_channel
        ):
            raise ValueError(
                f"{field_prefix} 至少必须是销售渠道"
                "或营销渠道之一。"
            )

        if is_sales_channel and is_active:
            active_sales_channel_count += 1

        if is_marketing_channel and is_active:
            active_marketing_channel_count += 1

        if supports_membership_binding and is_active:
            active_membership_binding_channel_count += 1

        channel_codes.add(channel_code)
        channel_names.add(channel_name)

    if active_sales_channel_count == 0:
        raise ValueError(
            "至少需要一个启用的销售渠道。"
        )

    if active_marketing_channel_count == 0:
        raise ValueError(
            "至少需要一个启用的营销渠道。"
        )

    if active_membership_binding_channel_count == 0:
        raise ValueError(
            "当前会员生成规则要求每个会员账户"
            "至少绑定一个渠道，因此至少需要一个"
            "启用且支持会员绑定的渠道。"
        )

    binding_distribution = manifest[
        "business_patterns"
    ][
        "P03_membership_customer_overlap"
    ][
        "parameters"
    ][
        "channel_binding_count_distribution"
    ]

    binding_counts: list[int] = []

    for raw_count in binding_distribution.keys():
        if (
            isinstance(raw_count, bool)
            or not isinstance(raw_count, int)
            or raw_count <= 0
        ):
            raise ValueError(
                "channel_binding_count_distribution "
                "的键必须是正整数，"
                f"当前值为：{raw_count!r}"
            )

        binding_counts.append(raw_count)

    max_binding_count = max(binding_counts)

    if (
        max_binding_count
        > active_membership_binding_channel_count
    ):
        raise ValueError(
            "会员最大渠道绑定数量超过有效会员绑定渠道数："
            f"max_binding_count={max_binding_count}, "
            "active_membership_binding_channel_count="
            f"{active_membership_binding_channel_count}"
        )


def validate_fixed_promotions(
    manifest: dict[str, Any],
) -> None:
    """
    验证固定促销配置，并检查促销与 Campaign、
    会员等级配置之间的一致性。

    当前 P0 规则：
    1. product_discount 对应 always_on Campaign；
    2. campaign_price 对应 major_promotion Campaign；
    3. 促销日期与对应 Campaign 日期完全一致；
    4. membership_policy.tiers 为空时，
       target_member_level 必须为 null。
    """
    fixed_dimensions = manifest.get(
        "fixed_dimensions"
    )

    if not isinstance(fixed_dimensions, dict):
        raise ValueError(
            "Manifest 缺少有效的 fixed_dimensions。"
        )

    promotions = fixed_dimensions.get(
        "promotions"
    )

    if (
        not isinstance(promotions, list)
        or not promotions
    ):
        raise ValueError(
            "fixed_dimensions.promotions "
            "必须是非空列表。"
        )

    required_fields = {
        "promotion_code",
        "promotion_name",
        "promotion_type",
        "discount_rate",
        "start_date",
        "end_date",
        "target_member_level",
        "campaign_code",
        "is_active",
    }

    allowed_promotion_types = {
        "product_discount",
        "campaign_price",
    }

    expected_campaign_types = {
        "product_discount": "always_on",
        "campaign_price": "major_promotion",
    }

    generation = manifest["generation"]

    business_start_date = parse_manifest_date(
        generation["business_start_date"],
        "generation.business_start_date",
    )

    business_end_date = parse_manifest_date(
        generation["business_end_date"],
        "generation.business_end_date",
    )

    campaigns = manifest[
        "business_calendar"
    ][
        "campaigns"
    ]

    campaign_lookup: dict[
        str,
        dict[str, Any],
    ] = {}

    for index, campaign in enumerate(campaigns):
        campaign_code = campaign[
            "campaign_code"
        ].strip()

        campaign_lookup[campaign_code] = {
            "campaign_type": campaign[
                "campaign_type"
            ].strip(),
            "start_date": parse_manifest_date(
                campaign["start_date"],
                (
                    "business_calendar."
                    f"campaigns[{index}].start_date"
                ),
            ),
            "end_date": parse_manifest_date(
                campaign["end_date"],
                (
                    "business_calendar."
                    f"campaigns[{index}].end_date"
                ),
            ),
        }

    membership_policy = manifest.get(
        "membership_policy"
    )

    if not isinstance(membership_policy, dict):
        raise ValueError(
            "Manifest 缺少有效的 membership_policy。"
        )

    tiers = membership_policy.get("tiers")

    if not isinstance(tiers, list):
        raise ValueError(
            "membership_policy.tiers 必须是列表。"
        )

    valid_member_levels: set[str] = set()

    for index, tier in enumerate(tiers):
        field_prefix = (
            f"membership_policy.tiers[{index}]"
        )

        if not isinstance(tier, dict):
            raise ValueError(
                f"{field_prefix} 必须是字典。"
            )

        level = tier.get("level")

        if (
            not isinstance(level, str)
            or not level.strip()
        ):
            raise ValueError(
                f"{field_prefix}.level "
                "必须是非空字符串。"
            )

        normalized_level = level.strip()

        if normalized_level in valid_member_levels:
            raise ValueError(
                "membership_policy.tiers "
                "存在重复 level："
                f"{normalized_level}"
            )

        valid_member_levels.add(
            normalized_level
        )

    promotion_codes: set[str] = set()
    promotion_names: set[str] = set()

    actual_type_counts: dict[str, int] = {
        "product_discount": 0,
        "campaign_price": 0,
    }

    for index, promotion in enumerate(
        promotions
    ):
        field_prefix = (
            f"fixed_dimensions.promotions[{index}]"
        )

        if not isinstance(promotion, dict):
            raise ValueError(
                f"{field_prefix} 必须是字典。"
            )

        missing_fields = (
            required_fields - promotion.keys()
        )

        if missing_fields:
            raise ValueError(
                f"{field_prefix} 缺少字段："
                f"{sorted(missing_fields)}"
            )

        for field_name in {
            "promotion_code",
            "promotion_name",
            "promotion_type",
            "campaign_code",
        }:
            value = promotion[field_name]

            if (
                not isinstance(value, str)
                or not value.strip()
            ):
                raise ValueError(
                    f"{field_prefix}.{field_name} "
                    "必须是非空字符串。"
                )

        promotion_code = promotion[
            "promotion_code"
        ].strip()

        promotion_name = promotion[
            "promotion_name"
        ].strip()

        promotion_type = promotion[
            "promotion_type"
        ].strip()

        campaign_code = promotion[
            "campaign_code"
        ].strip()

        if promotion_code != promotion_code.upper():
            raise ValueError(
                f"{field_prefix}.promotion_code "
                "必须使用大写稳定编码："
                f"{promotion_code!r}"
            )

        normalized_code = promotion_code.replace(
            "_",
            "",
        )

        if not normalized_code.isalnum():
            raise ValueError(
                f"{field_prefix}.promotion_code "
                "只能包含字母、数字和下划线："
                f"{promotion_code!r}"
            )

        if promotion_code == "NO_PROMOTION":
            raise ValueError(
                "不能创建 NO_PROMOTION 维度记录；"
                "未使用促销应由 promotion_id IS NULL "
                "表达。"
            )

        if promotion_code in promotion_codes:
            raise ValueError(
                "promotion_code 不能重复："
                f"{promotion_code}"
            )

        if promotion_name in promotion_names:
            raise ValueError(
                "promotion_name 不能重复："
                f"{promotion_name}"
            )

        if (
            promotion_type
            not in allowed_promotion_types
        ):
            raise ValueError(
                f"{field_prefix}.promotion_type "
                "不在允许范围内："
                f"{promotion_type!r}"
            )

        discount_rate = promotion[
            "discount_rate"
        ]

        if (
            isinstance(discount_rate, bool)
            or not isinstance(
                discount_rate,
                (int, float),
            )
            or not 0 < discount_rate < 1
        ):
            raise ValueError(
                f"{field_prefix}.discount_rate "
                "必须是 (0, 1) 范围内的数值，"
                f"当前值为：{discount_rate!r}"
            )

        start_date = parse_manifest_date(
            promotion["start_date"],
            f"{field_prefix}.start_date",
        )

        end_date = parse_manifest_date(
            promotion["end_date"],
            f"{field_prefix}.end_date",
        )

        if start_date > end_date:
            raise ValueError(
                f"{field_prefix} 的 start_date "
                "不能晚于 end_date。"
            )

        if not (
            business_start_date
            <= start_date
            <= end_date
            <= business_end_date
        ):
            raise ValueError(
                f"{field_prefix} 超出业务日期范围："
                f"{start_date} -> {end_date}"
            )

        if campaign_code not in campaign_lookup:
            raise ValueError(
                f"{field_prefix}.campaign_code "
                "不存在于 business_calendar.campaigns："
                f"{campaign_code}"
            )

        campaign = campaign_lookup[
            campaign_code
        ]

        expected_campaign_type = (
            expected_campaign_types[
                promotion_type
            ]
        )

        if (
            campaign["campaign_type"]
            != expected_campaign_type
        ):
            raise ValueError(
                f"{field_prefix} 的促销类型与 "
                "Campaign 类型不匹配："
                f"promotion_type={promotion_type}, "
                "campaign_type="
                f"{campaign['campaign_type']}, "
                "expected_campaign_type="
                f"{expected_campaign_type}"
            )

        if (
            start_date
            != campaign["start_date"]
            or end_date
            != campaign["end_date"]
        ):
            raise ValueError(
                f"{field_prefix} 的日期必须与对应 "
                "Campaign 完全一致："
                "promotion="
                f"{start_date} -> {end_date}, "
                "campaign="
                f"{campaign['start_date']} -> "
                f"{campaign['end_date']}"
            )

        target_member_level = promotion[
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
                    f"{field_prefix}."
                    "target_member_level "
                    "必须为 null 或非空字符串。"
                )

            normalized_member_level = (
                target_member_level.strip()
            )

            if (
                normalized_member_level
                not in valid_member_levels
            ):
                raise ValueError(
                    f"{field_prefix}."
                    "target_member_level "
                    "不存在于 membership_policy.tiers："
                    f"{normalized_member_level!r}"
                )

        is_active = promotion["is_active"]

        if not isinstance(is_active, bool):
            raise ValueError(
                f"{field_prefix}.is_active "
                "必须是布尔值 true 或 false。"
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

    if (
        actual_type_counts["product_discount"]
        == 0
    ):
        raise ValueError(
            "至少需要一个 product_discount "
            "促销方案。"
        )

    if (
        actual_type_counts["campaign_price"]
        == 0
    ):
        raise ValueError(
            "至少需要一个 campaign_price "
            "促销方案。"
        )


def validate_product_generation(
    manifest: dict[str, Any],
) -> None:
    """
    验证商品维度生成配置。
    """
    config = manifest.get("product_generation")

    if not isinstance(config, dict):
        raise ValueError(
            "Manifest 缺少有效的 product_generation。"
        )

    sku_prefix = config.get("sku_prefix")

    if (
        not isinstance(sku_prefix, str)
        or not sku_prefix.strip()
    ):
        raise ValueError(
            "product_generation.sku_prefix "
            "必须是非空字符串。"
        )

    sku_prefix = sku_prefix.strip()

    if sku_prefix != sku_prefix.upper():
        raise ValueError(
            "product_generation.sku_prefix "
            "必须使用大写稳定编码。"
        )

    normalized_prefix = sku_prefix.replace("_", "")

    if not normalized_prefix.isalnum():
        raise ValueError(
            "product_generation.sku_prefix "
            "只能包含字母、数字和下划线。"
        )

    brands = config.get("brands")

    if not isinstance(brands, list) or not brands:
        raise ValueError(
            "product_generation.brands "
            "必须是非空列表。"
        )

    normalized_brands: list[str] = []

    for index, brand in enumerate(brands):
        if (
            not isinstance(brand, str)
            or not brand.strip()
        ):
            raise ValueError(
                "product_generation.brands"
                f"[{index}] 必须是非空字符串。"
            )

        normalized_brand = brand.strip()

        if normalized_brand != normalized_brand.upper():
            raise ValueError(
                "商品品牌编码必须使用大写："
                f"{normalized_brand!r}"
            )

        normalized_brands.append(normalized_brand)

    if len(set(normalized_brands)) != len(
        normalized_brands
    ):
        raise ValueError(
            "product_generation.brands "
            "不能包含重复品牌。"
        )

    active_ratio = config.get("active_ratio")

    if (
        isinstance(active_ratio, bool)
        or not isinstance(active_ratio, (int, float))
        or not 0 <= active_ratio <= 1
    ):
        raise ValueError(
            "product_generation.active_ratio "
            "必须是 [0, 1] 范围内的数值。"
        )

    launch_cohorts = config.get("launch_cohorts")

    if (
        not isinstance(launch_cohorts, list)
        or not launch_cohorts
    ):
        raise ValueError(
            "product_generation.launch_cohorts "
            "必须是非空列表。"
        )

    cohort_names: set[str] = set()
    cohort_ratios: dict[str, float] = {}
    parsed_cohorts: list[
        tuple[date, date, str]
    ] = []

    business_end_date = parse_manifest_date(
        manifest["generation"]["business_end_date"],
        "generation.business_end_date",
    )

    for index, cohort in enumerate(launch_cohorts):
        field_prefix = (
            f"product_generation.launch_cohorts[{index}]"
        )

        if not isinstance(cohort, dict):
            raise ValueError(
                f"{field_prefix} 必须是字典。"
            )

        required_fields = {
            "cohort_name",
            "ratio",
            "start_date",
            "end_date",
        }

        missing_fields = (
            required_fields - cohort.keys()
        )

        if missing_fields:
            raise ValueError(
                f"{field_prefix} 缺少字段："
                f"{sorted(missing_fields)}"
            )

        cohort_name = cohort["cohort_name"]

        if (
            not isinstance(cohort_name, str)
            or not cohort_name.strip()
        ):
            raise ValueError(
                f"{field_prefix}.cohort_name "
                "必须是非空字符串。"
            )

        cohort_name = cohort_name.strip()

        if cohort_name in cohort_names:
            raise ValueError(
                "launch cohort 名称不能重复："
                f"{cohort_name}"
            )

        ratio = cohort["ratio"]

        if (
            isinstance(ratio, bool)
            or not isinstance(ratio, (int, float))
            or ratio <= 0
            or ratio > 1
        ):
            raise ValueError(
                f"{field_prefix}.ratio "
                "必须是 (0, 1] 范围内的数值。"
            )

        start_date = parse_manifest_date(
            cohort["start_date"],
            f"{field_prefix}.start_date",
        )

        end_date = parse_manifest_date(
            cohort["end_date"],
            f"{field_prefix}.end_date",
        )

        if start_date > end_date:
            raise ValueError(
                f"{field_prefix} 的 start_date "
                "不能晚于 end_date。"
            )

        if end_date > business_end_date:
            raise ValueError(
                f"{field_prefix} 的商品上市区间 "
                "不能晚于 business_end_date。"
            )

        cohort_names.add(cohort_name)
        cohort_ratios[cohort_name] = ratio
        parsed_cohorts.append(
            (start_date, end_date, cohort_name)
        )

    validate_probability_distribution(
        cohort_ratios,
        "product_generation.launch_cohorts.ratio",
    )

    parsed_cohorts.sort(key=lambda item: item[0])

    for previous, current in zip(
        parsed_cohorts,
        parsed_cohorts[1:],
    ):
        previous_start, previous_end, previous_name = (
            previous
        )
        current_start, current_end, current_name = current

        if current_start <= previous_end:
            raise ValueError(
                "商品上市批次区间发生重叠："
                f"{previous_name} "
                f"[{previous_start}, {previous_end}] 与 "
                f"{current_name} "
                f"[{current_start}, {current_end}]。"
            )

    subcategories = config.get("subcategories")

    if (
        not isinstance(subcategories, list)
        or not subcategories
    ):
        raise ValueError(
            "product_generation.subcategories "
            "必须是非空列表。"
        )

    subcategory_keys: set[tuple[str, str]] = set()
    subcategory_weights: dict[str, float] = {}

    required_subcategory_fields = {
        "category",
        "subcategory",
        "weight",
        "list_price_min",
        "list_price_max",
    }

    for index, item in enumerate(subcategories):
        field_prefix = (
            f"product_generation.subcategories[{index}]"
        )

        if not isinstance(item, dict):
            raise ValueError(
                f"{field_prefix} 必须是字典。"
            )

        missing_fields = (
            required_subcategory_fields
            - item.keys()
        )

        if missing_fields:
            raise ValueError(
                f"{field_prefix} 缺少字段："
                f"{sorted(missing_fields)}"
            )

        category = item["category"]
        subcategory = item["subcategory"]

        for field_name, value in {
            "category": category,
            "subcategory": subcategory,
        }.items():
            if (
                not isinstance(value, str)
                or not value.strip()
            ):
                raise ValueError(
                    f"{field_prefix}.{field_name} "
                    "必须是非空字符串。"
                )

        category = category.strip()
        subcategory = subcategory.strip()

        pair = (category, subcategory)

        if pair in subcategory_keys:
            raise ValueError(
                "商品品类与子品类组合不能重复："
                f"{pair}"
            )

        weight = item["weight"]

        if (
            isinstance(weight, bool)
            or not isinstance(weight, (int, float))
            or weight <= 0
            or weight > 1
        ):
            raise ValueError(
                f"{field_prefix}.weight "
                "必须是 (0, 1] 范围内的数值。"
            )

        price_min = item["list_price_min"]
        price_max = item["list_price_max"]

        for field_name, value in {
            "list_price_min": price_min,
            "list_price_max": price_max,
        }.items():
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or value <= 0
            ):
                raise ValueError(
                    f"{field_prefix}.{field_name} "
                    "必须是大于 0 的数值。"
                )

        if price_min > price_max:
            raise ValueError(
                f"{field_prefix} 的 list_price_min "
                "不能大于 list_price_max。"
            )

        subcategory_keys.add(pair)

        distribution_key = (
            f"{category}/{subcategory}"
        )

        subcategory_weights[
            distribution_key
        ] = weight

    validate_probability_distribution(
        subcategory_weights,
        "product_generation.subcategories.weight",
    )

    _, profile = get_active_scale_profile(manifest)

    product_count = profile["products"]

    if product_count < len(subcategories):
        raise ValueError(
            "当前 Profile 的商品数少于子品类数，"
            "无法保证每个子品类至少生成一个 SKU："
            f"products={product_count}, "
            f"subcategories={len(subcategories)}"
        )


def validate_customer_generation(
    manifest: dict[str, Any],
) -> None:
    """
    验证客户维度生成配置。

    主要检查：
    1. customer_code 编码规则；
    2. customer_status 概率分布；
    3. first_seen 批次、日期和比例；
    4. home_region 城市等级权重；
    5. 当前 Profile 客户数量与编码容量兼容。
    """
    config = manifest.get(
        "customer_generation"
    )

    if not isinstance(config, dict):
        raise ValueError(
            "Manifest 缺少有效的 "
            "customer_generation。"
        )

    required_fields = {
        "customer_code_prefix",
        "customer_code_width",
        "customer_status_distribution",
        "first_seen_cohorts",
        "home_region_distribution",
    }

    missing_fields = (
        required_fields - config.keys()
    )

    if missing_fields:
        raise ValueError(
            "customer_generation 缺少字段："
            f"{sorted(missing_fields)}"
        )

    customer_code_prefix = config[
        "customer_code_prefix"
    ]

    if (
        not isinstance(customer_code_prefix, str)
        or not customer_code_prefix.strip()
    ):
        raise ValueError(
            "customer_generation."
            "customer_code_prefix "
            "必须是非空字符串。"
        )

    customer_code_prefix = (
        customer_code_prefix.strip()
    )

    if (
        customer_code_prefix
        != customer_code_prefix.upper()
    ):
        raise ValueError(
            "customer_generation."
            "customer_code_prefix "
            "必须使用大写稳定编码。"
        )

    normalized_prefix = (
        customer_code_prefix.replace("_", "")
    )

    if not normalized_prefix.isalnum():
        raise ValueError(
            "customer_generation."
            "customer_code_prefix "
            "只能包含字母、数字和下划线。"
        )

    customer_code_width = config[
        "customer_code_width"
    ]

    if (
        isinstance(customer_code_width, bool)
        or not isinstance(
            customer_code_width,
            int,
        )
        or customer_code_width <= 0
    ):
        raise ValueError(
            "customer_generation."
            "customer_code_width "
            "必须是正整数。"
        )

    # dim_customer.customer_code 是 VARCHAR(50)。
    if (
        len(customer_code_prefix)
        + customer_code_width
        > 50
    ):
        raise ValueError(
            "customer_code_prefix 与 "
            "customer_code_width 组合后"
            "超过 dim_customer.customer_code "
            "的 VARCHAR(50) 长度。"
        )

    _, profile = get_active_scale_profile(
        manifest
    )

    customer_count = profile["customers"]

    maximum_customer_number = (
        10 ** customer_code_width - 1
    )

    if customer_count > maximum_customer_number:
        raise ValueError(
            "customer_code_width 无法容纳"
            "当前 Profile 的客户数量："
            f"customers={customer_count}, "
            "maximum_customer_number="
            f"{maximum_customer_number}"
        )

    status_distribution = config[
        "customer_status_distribution"
    ]

    if (
        not isinstance(
            status_distribution,
            dict,
        )
        or not status_distribution
    ):
        raise ValueError(
            "customer_generation."
            "customer_status_distribution "
            "必须是非空字典。"
        )

    for status, probability in (
        status_distribution.items()
    ):
        if (
            not isinstance(status, str)
            or not status.strip()
        ):
            raise ValueError(
                "customer_status_distribution "
                "的状态名称必须是非空字符串："
                f"{status!r}"
            )

        if (
            isinstance(probability, bool)
            or not isinstance(
                probability,
                (int, float),
            )
            or probability <= 0
        ):
            raise ValueError(
                "customer_status_distribution "
                "中的概率必须大于 0："
                f"status={status!r}, "
                f"probability={probability!r}"
            )

    validate_probability_distribution(
        status_distribution,
        (
            "customer_generation."
            "customer_status_distribution"
        ),
    )

    first_seen_cohorts = config[
        "first_seen_cohorts"
    ]

    if (
        not isinstance(
            first_seen_cohorts,
            list,
        )
        or not first_seen_cohorts
    ):
        raise ValueError(
            "customer_generation."
            "first_seen_cohorts "
            "必须是非空列表。"
        )

    cohort_required_fields = {
        "cohort_name",
        "ratio",
        "start_date",
        "end_date",
    }

    cohort_names: set[str] = set()
    cohort_ratios: dict[str, float] = {}

    parsed_cohorts: list[
        tuple[date, date, str]
    ] = []

    business_end_date = parse_manifest_date(
        manifest[
            "generation"
        ][
            "business_end_date"
        ],
        "generation.business_end_date",
    )

    for index, cohort in enumerate(
        first_seen_cohorts
    ):
        field_prefix = (
            "customer_generation."
            f"first_seen_cohorts[{index}]"
        )

        if not isinstance(cohort, dict):
            raise ValueError(
                f"{field_prefix} 必须是字典。"
            )

        missing_cohort_fields = (
            cohort_required_fields
            - cohort.keys()
        )

        if missing_cohort_fields:
            raise ValueError(
                f"{field_prefix} 缺少字段："
                f"{sorted(missing_cohort_fields)}"
            )

        cohort_name = cohort["cohort_name"]

        if (
            not isinstance(cohort_name, str)
            or not cohort_name.strip()
        ):
            raise ValueError(
                f"{field_prefix}.cohort_name "
                "必须是非空字符串。"
            )

        cohort_name = cohort_name.strip()

        if cohort_name in cohort_names:
            raise ValueError(
                "first_seen cohort 名称不能重复："
                f"{cohort_name}"
            )

        ratio = cohort["ratio"]

        if (
            isinstance(ratio, bool)
            or not isinstance(
                ratio,
                (int, float),
            )
            or ratio <= 0
            or ratio > 1
        ):
            raise ValueError(
                f"{field_prefix}.ratio "
                "必须是 (0, 1] 范围内的数值。"
            )

        # 确保当前 Profile 下每个已配置批次
        # 至少能够生成一名客户。
        if customer_count * ratio < 1:
            raise ValueError(
                f"{field_prefix}.ratio 太小，"
                "当前 Profile 下无法保证"
                "该批次生成客户："
                f"customers={customer_count}, "
                f"ratio={ratio}"
            )

        start_date = parse_manifest_date(
            cohort["start_date"],
            f"{field_prefix}.start_date",
        )

        end_date = parse_manifest_date(
            cohort["end_date"],
            f"{field_prefix}.end_date",
        )

        if start_date > end_date:
            raise ValueError(
                f"{field_prefix} 的 start_date "
                "不能晚于 end_date。"
            )

        # legacy 客户可以早于业务数据窗口出现，
        # 但不能晚于交易数据生成结束日。
        if end_date > business_end_date:
            raise ValueError(
                f"{field_prefix}.end_date "
                "不能晚于 business_end_date："
                f"end_date={end_date}, "
                f"business_end_date="
                f"{business_end_date}"
            )

        cohort_names.add(cohort_name)
        cohort_ratios[cohort_name] = ratio

        parsed_cohorts.append(
            (
                start_date,
                end_date,
                cohort_name,
            )
        )

    validate_probability_distribution(
        cohort_ratios,
        (
            "customer_generation."
            "first_seen_cohorts.ratio"
        ),
    )

    parsed_cohorts.sort(
        key=lambda item: item[0]
    )

    for previous, current in zip(
        parsed_cohorts,
        parsed_cohorts[1:],
    ):
        (
            previous_start,
            previous_end,
            previous_name,
        ) = previous

        (
            current_start,
            current_end,
            current_name,
        ) = current

        if current_start <= previous_end:
            raise ValueError(
                "客户 first_seen 批次区间发生重叠："
                f"{previous_name} "
                f"[{previous_start}, {previous_end}] 与 "
                f"{current_name} "
                f"[{current_start}, {current_end}]。"
            )

    home_region_distribution = config[
        "home_region_distribution"
    ]

    if not isinstance(
        home_region_distribution,
        dict,
    ):
        raise ValueError(
            "customer_generation."
            "home_region_distribution "
            "必须是字典。"
        )

    if (
        home_region_distribution.get(
            "strategy"
        )
        != "city_tier_weighted"
    ):
        raise ValueError(
            "Day64 当前只支持 "
            "home_region_distribution.strategy "
            "= city_tier_weighted。"
        )

    if (
        home_region_distribution.get(
            "within_tier_strategy"
        )
        != "uniform"
    ):
        raise ValueError(
            "Day64 当前只支持 "
            "home_region_distribution."
            "within_tier_strategy = uniform。"
        )

    city_tier_weights = (
        home_region_distribution.get(
            "city_tier_weights"
        )
    )

    if (
        not isinstance(
            city_tier_weights,
            dict,
        )
        or not city_tier_weights
    ):
        raise ValueError(
            "home_region_distribution."
            "city_tier_weights "
            "必须是非空字典。"
        )

    for city_tier, probability in (
        city_tier_weights.items()
    ):
        if (
            not isinstance(city_tier, str)
            or not city_tier.strip()
        ):
            raise ValueError(
                "city_tier_weights 的键"
                "必须是非空字符串："
                f"{city_tier!r}"
            )

        if (
            isinstance(probability, bool)
            or not isinstance(
                probability,
                (int, float),
            )
            or probability <= 0
        ):
            raise ValueError(
                "city_tier_weights 的概率"
                "必须大于 0："
                f"city_tier={city_tier!r}, "
                f"probability={probability!r}"
            )

    validate_probability_distribution(
        city_tier_weights,
        (
            "customer_generation."
            "home_region_distribution."
            "city_tier_weights"
        ),
    )

    regions = manifest[
        "fixed_dimensions"
    ][
        "regions"
    ]

    configured_region_tiers = {
        region["city_tier"].strip()
        for region in regions
    }

    weighted_region_tiers = {
        city_tier.strip()
        for city_tier
        in city_tier_weights.keys()
    }

    if (
        weighted_region_tiers
        != configured_region_tiers
    ):
        missing_tiers = (
            configured_region_tiers
            - weighted_region_tiers
        )

        unknown_tiers = (
            weighted_region_tiers
            - configured_region_tiers
        )

        raise ValueError(
            "city_tier_weights 必须与 "
            "fixed_dimensions.regions 中的 "
            "city_tier 完全一致："
            f"missing_tiers={sorted(missing_tiers)}, "
            f"unknown_tiers={sorted(unknown_tiers)}"
        )


def validate_membership_generation(
    manifest: dict[str, Any],
) -> None:
    """
    验证会员账户维度生成配置。

    主要检查：
    1. member_code 编码和容量；
    2. joined_at 批次、比例与日期；
    3. 日内入会时间窗口；
    4. 首次入会渠道权重；
    5. 渠道必须启用并支持会员绑定；
    6. P03 会员状态及绑定策略兼容性。
    """
    config = manifest.get(
        "membership_generation"
    )

    if not isinstance(config, dict):
        raise ValueError(
            "Manifest 缺少有效的 "
            "membership_generation。"
        )

    required_fields = {
        "member_code_prefix",
        "member_code_width",
        "joined_at_cohorts",
        "joined_time_window",
        "join_channel_weights",
    }

    missing_fields = (
        required_fields - config.keys()
    )

    if missing_fields:
        raise ValueError(
            "membership_generation 缺少字段："
            f"{sorted(missing_fields)}"
        )

    member_code_prefix = config[
        "member_code_prefix"
    ]

    if (
        not isinstance(member_code_prefix, str)
        or not member_code_prefix.strip()
    ):
        raise ValueError(
            "membership_generation."
            "member_code_prefix "
            "必须是非空字符串。"
        )

    member_code_prefix = (
        member_code_prefix.strip()
    )

    if (
        member_code_prefix
        != member_code_prefix.upper()
    ):
        raise ValueError(
            "membership_generation."
            "member_code_prefix "
            "必须使用大写稳定编码。"
        )

    normalized_prefix = (
        member_code_prefix.replace("_", "")
    )

    if not normalized_prefix.isalnum():
        raise ValueError(
            "membership_generation."
            "member_code_prefix "
            "只能包含字母、数字和下划线。"
        )

    member_code_width = config[
        "member_code_width"
    ]

    if (
        isinstance(member_code_width, bool)
        or not isinstance(
            member_code_width,
            int,
        )
        or member_code_width <= 0
    ):
        raise ValueError(
            "membership_generation."
            "member_code_width "
            "必须是正整数。"
        )

    if (
        len(member_code_prefix)
        + member_code_width
        > 50
    ):
        raise ValueError(
            "member_code_prefix 与 "
            "member_code_width 组合后"
            "超过 dim_membership_account."
            "member_code 的 VARCHAR(50) 长度。"
        )

    _, profile = get_active_scale_profile(
        manifest
    )

    membership_account_count = profile[
        "membership_accounts"
    ]

    maximum_member_number = (
        10 ** member_code_width - 1
    )

    if (
        membership_account_count
        > maximum_member_number
    ):
        raise ValueError(
            "member_code_width 无法容纳"
            "当前 Profile 的会员账户数量："
            "membership_accounts="
            f"{membership_account_count}, "
            "maximum_member_number="
            f"{maximum_member_number}"
        )

    joined_at_cohorts = config[
        "joined_at_cohorts"
    ]

    if (
        not isinstance(
            joined_at_cohorts,
            list,
        )
        or not joined_at_cohorts
    ):
        raise ValueError(
            "membership_generation."
            "joined_at_cohorts "
            "必须是非空列表。"
        )

    cohort_required_fields = {
        "cohort_name",
        "ratio",
        "start_date",
        "end_date",
    }

    cohort_names: set[str] = set()
    cohort_ratios: dict[str, float] = {}

    parsed_cohorts: list[
        tuple[date, date, str]
    ] = []

    business_end_date = parse_manifest_date(
        manifest[
            "generation"
        ][
            "business_end_date"
        ],
        "generation.business_end_date",
    )

    for index, cohort in enumerate(
        joined_at_cohorts
    ):
        field_prefix = (
            "membership_generation."
            f"joined_at_cohorts[{index}]"
        )

        if not isinstance(cohort, dict):
            raise ValueError(
                f"{field_prefix} 必须是字典。"
            )

        missing_cohort_fields = (
            cohort_required_fields
            - cohort.keys()
        )

        if missing_cohort_fields:
            raise ValueError(
                f"{field_prefix} 缺少字段："
                f"{sorted(missing_cohort_fields)}"
            )

        cohort_name = cohort["cohort_name"]

        if (
            not isinstance(cohort_name, str)
            or not cohort_name.strip()
        ):
            raise ValueError(
                f"{field_prefix}.cohort_name "
                "必须是非空字符串。"
            )

        cohort_name = cohort_name.strip()

        if cohort_name in cohort_names:
            raise ValueError(
                "joined_at cohort 名称不能重复："
                f"{cohort_name}"
            )

        ratio = cohort["ratio"]

        if (
            isinstance(ratio, bool)
            or not isinstance(
                ratio,
                (int, float),
            )
            or ratio <= 0
            or ratio > 1
        ):
            raise ValueError(
                f"{field_prefix}.ratio "
                "必须是 (0, 1] 范围内的数值。"
            )

        if (
            membership_account_count
            * ratio
            < 1
        ):
            raise ValueError(
                f"{field_prefix}.ratio 太小，"
                "当前 Profile 下无法保证"
                "该批次生成会员账户："
                "membership_accounts="
                f"{membership_account_count}, "
                f"ratio={ratio}"
            )

        start_date = parse_manifest_date(
            cohort["start_date"],
            f"{field_prefix}.start_date",
        )

        end_date = parse_manifest_date(
            cohort["end_date"],
            f"{field_prefix}.end_date",
        )

        if start_date > end_date:
            raise ValueError(
                f"{field_prefix} 的 start_date "
                "不能晚于 end_date。"
            )

        # legacy 会员允许在 2024 年以前入会，
        # 但所有入会时间必须不晚于业务结束日。
        if end_date > business_end_date:
            raise ValueError(
                f"{field_prefix}.end_date "
                "不能晚于 business_end_date："
                f"end_date={end_date}, "
                "business_end_date="
                f"{business_end_date}"
            )

        cohort_names.add(cohort_name)
        cohort_ratios[cohort_name] = ratio

        parsed_cohorts.append(
            (
                start_date,
                end_date,
                cohort_name,
            )
        )

    validate_probability_distribution(
        cohort_ratios,
        (
            "membership_generation."
            "joined_at_cohorts.ratio"
        ),
    )

    parsed_cohorts.sort(
        key=lambda item: item[0]
    )

    for previous, current in zip(
        parsed_cohorts,
        parsed_cohorts[1:],
    ):
        (
            previous_start,
            previous_end,
            previous_name,
        ) = previous

        (
            current_start,
            current_end,
            current_name,
        ) = current

        if current_start <= previous_end:
            raise ValueError(
                "会员 joined_at 批次区间发生重叠："
                f"{previous_name} "
                f"[{previous_start}, {previous_end}] 与 "
                f"{current_name} "
                f"[{current_start}, {current_end}]。"
            )

    joined_time_window = config[
        "joined_time_window"
    ]

    if not isinstance(
        joined_time_window,
        dict,
    ):
        raise ValueError(
            "membership_generation."
            "joined_time_window "
            "必须是字典。"
        )

    required_time_fields = {
        "start_time",
        "end_time",
    }

    missing_time_fields = (
        required_time_fields
        - joined_time_window.keys()
    )

    if missing_time_fields:
        raise ValueError(
            "membership_generation."
            "joined_time_window 缺少字段："
            f"{sorted(missing_time_fields)}"
        )

    start_time = parse_manifest_time(
        joined_time_window["start_time"],
        (
            "membership_generation."
            "joined_time_window.start_time"
        ),
    )

    end_time = parse_manifest_time(
        joined_time_window["end_time"],
        (
            "membership_generation."
            "joined_time_window.end_time"
        ),
    )

    if start_time > end_time:
        raise ValueError(
            "joined_time_window.start_time "
            "不能晚于 end_time："
            f"{start_time} -> {end_time}"
        )

    join_channel_weights = config[
        "join_channel_weights"
    ]

    if (
        not isinstance(
            join_channel_weights,
            dict,
        )
        or not join_channel_weights
    ):
        raise ValueError(
            "membership_generation."
            "join_channel_weights "
            "必须是非空字典。"
        )

    normalized_channel_weights: dict[
        str,
        float,
    ] = {}

    for channel_code, probability in (
        join_channel_weights.items()
    ):
        if (
            not isinstance(channel_code, str)
            or not channel_code.strip()
        ):
            raise ValueError(
                "join_channel_weights 的渠道编码"
                "必须是非空字符串："
                f"{channel_code!r}"
            )

        normalized_channel_code = (
            channel_code.strip()
        )

        if (
            normalized_channel_code
            != normalized_channel_code.upper()
        ):
            raise ValueError(
                "join_channel_weights 的渠道编码"
                "必须使用大写稳定编码："
                f"{normalized_channel_code!r}"
            )

        if (
            isinstance(probability, bool)
            or not isinstance(
                probability,
                (int, float),
            )
            or probability <= 0
        ):
            raise ValueError(
                "join_channel_weights 中的权重"
                "必须大于 0："
                f"channel_code="
                f"{normalized_channel_code}, "
                f"probability={probability!r}"
            )

        if (
            membership_account_count
            * probability
            < 1
        ):
            raise ValueError(
                "join_channel_weights 权重太小，"
                "当前 Profile 下无法保证"
                "该渠道生成会员账户："
                f"channel_code="
                f"{normalized_channel_code}, "
                "membership_accounts="
                f"{membership_account_count}, "
                f"probability={probability}"
            )

        normalized_channel_weights[
            normalized_channel_code
        ] = probability

    if (
        len(normalized_channel_weights)
        != len(join_channel_weights)
    ):
        raise ValueError(
            "join_channel_weights 存在"
            "标准化后重复的 channel_code。"
        )

    validate_probability_distribution(
        normalized_channel_weights,
        (
            "membership_generation."
            "join_channel_weights"
        ),
    )

    channels = manifest[
        "fixed_dimensions"
    ][
        "channels"
    ]

    channel_lookup = {
        channel["channel_code"].strip():
            channel
        for channel in channels
    }

    for channel_code in (
        normalized_channel_weights
    ):
        if channel_code not in channel_lookup:
            raise ValueError(
                "join_channel_weights 引用了"
                "不存在的渠道："
                f"{channel_code}"
            )

        channel = channel_lookup[
            channel_code
        ]

        if not channel["is_active"]:
            raise ValueError(
                "首次入会渠道必须处于启用状态："
                f"{channel_code}"
            )

        if not channel[
            "supports_membership_binding"
        ]:
            raise ValueError(
                "首次入会渠道必须支持会员绑定："
                f"{channel_code}"
            )

    p03_parameters = manifest[
        "business_patterns"
    ][
        "P03_membership_customer_overlap"
    ][
        "parameters"
    ]

    status_distribution = p03_parameters[
        "membership_status_distribution"
    ]

    if (
        not isinstance(
            status_distribution,
            dict,
        )
        or not status_distribution
    ):
        raise ValueError(
            "P03 membership_status_distribution "
            "必须是非空字典。"
        )

    allowed_statuses = {
        "active",
        "inactive",
    }

    normalized_statuses: set[str] = set()

    for status, probability in (
        status_distribution.items()
    ):
        if (
            not isinstance(status, str)
            or not status.strip()
        ):
            raise ValueError(
                "membership_status_distribution "
                "的状态名称必须是非空字符串："
                f"{status!r}"
            )

        normalized_status = status.strip()

        if normalized_status not in allowed_statuses:
            raise ValueError(
                "P0 会员账户状态只允许 "
                "active 和 inactive："
                f"{normalized_status!r}"
            )

        if len(normalized_status) > 50:
            raise ValueError(
                "会员状态超过数据库 "
                "VARCHAR(50) 长度："
                f"{normalized_status!r}"
            )

        if (
            isinstance(probability, bool)
            or not isinstance(
                probability,
                (int, float),
            )
            or probability <= 0
        ):
            raise ValueError(
                "membership_status_distribution "
                "中的概率必须大于 0："
                f"status={normalized_status!r}, "
                f"probability={probability!r}"
            )

        if (
            membership_account_count
            * probability
            < 1
        ):
            raise ValueError(
                "membership_status_distribution "
                "的概率太小，当前 Profile 下"
                "无法生成该状态："
                f"status={normalized_status!r}, "
                "membership_accounts="
                f"{membership_account_count}, "
                f"probability={probability}"
            )

        normalized_statuses.add(
            normalized_status
        )

    if normalized_statuses != allowed_statuses:
        raise ValueError(
            "P0 membership_status_distribution "
            "必须同时配置 active 和 inactive："
            f"actual={sorted(normalized_statuses)}"
        )

    validate_probability_distribution(
        status_distribution,
        (
            "business_patterns."
            "P03_membership_customer_overlap."
            "parameters."
            "membership_status_distribution"
        ),
    )

    for field_name in {
        "require_join_channel_binding",
        "inactive_account_open_binding_allowed",
    }:
        value = p03_parameters.get(
            field_name
        )

        if not isinstance(value, bool):
            raise ValueError(
                "P03 "
                f"{field_name} 必须是布尔值，"
                f"当前值为：{value!r}"
            )

    if (
        p03_parameters[
            "require_join_channel_binding"
        ]
        and not normalized_channel_weights
    ):
        raise ValueError(
            "require_join_channel_binding=true 时，"
            "必须配置至少一个首次入会渠道。"
        )


def validate_identity_mapping_generation(
    manifest: dict[str, Any],
) -> None:
    """
    验证 customer-membership 身份映射生成配置。

    当前 Day64 P0 规则：
    1. customer 与 membership account 一对一映射；
    2. 使用固定随机种子进行确定性洗牌；
    3. 映射开始时间不得早于任一实体出现时间；
    4. 所有初始映射均为开放、有效状态。
    """
    config = manifest.get(
        "identity_mapping_generation"
    )

    if not isinstance(config, dict):
        raise ValueError(
            "Manifest 缺少有效的 "
            "identity_mapping_generation。"
        )

    required_fields = {
        "pairing_strategy",
        "effective_from_strategy",
        "effective_to_strategy",
        "mapping_status",
    }

    missing_fields = (
        required_fields - config.keys()
    )

    if missing_fields:
        raise ValueError(
            "identity_mapping_generation "
            "缺少字段："
            f"{sorted(missing_fields)}"
        )

    for field_name in required_fields:
        value = config[field_name]

        if (
            not isinstance(value, str)
            or not value.strip()
        ):
            raise ValueError(
                "identity_mapping_generation."
                f"{field_name} 必须是非空字符串。"
            )

    pairing_strategy = config[
        "pairing_strategy"
    ].strip()

    effective_from_strategy = config[
        "effective_from_strategy"
    ].strip()

    effective_to_strategy = config[
        "effective_to_strategy"
    ].strip()

    mapping_status = config[
        "mapping_status"
    ].strip()

    if (
        pairing_strategy
        != "deterministic_one_to_one_shuffle"
    ):
        raise ValueError(
            "Day64 当前只支持 "
            "identity_mapping_generation."
            "pairing_strategy = "
            "deterministic_one_to_one_shuffle。"
        )

    if (
        effective_from_strategy
        != (
            "max_customer_first_seen_"
            "and_member_joined_at"
        )
    ):
        raise ValueError(
            "Day64 当前只支持 "
            "identity_mapping_generation."
            "effective_from_strategy = "
            "max_customer_first_seen_"
            "and_member_joined_at。"
        )

    if effective_to_strategy != "open":
        raise ValueError(
            "Day64 当前只支持 "
            "identity_mapping_generation."
            "effective_to_strategy = open。"
        )

    if mapping_status != "active":
        raise ValueError(
            "Day64 当前初始身份映射的 "
            "mapping_status 必须为 active。"
        )

    # bridge_customer_membership.mapping_status
    # 是 VARCHAR(50)。
    if len(mapping_status) > 50:
        raise ValueError(
            "identity_mapping_generation."
            "mapping_status 超过数据库 "
            "VARCHAR(50) 长度。"
        )

    generation = manifest.get(
        "generation"
    )

    if not isinstance(generation, dict):
        raise ValueError(
            "Manifest 缺少有效的 generation。"
        )

    deterministic_mode = generation.get(
        "deterministic_mode"
    )

    if not isinstance(
        deterministic_mode,
        bool,
    ):
        raise ValueError(
            "generation.deterministic_mode "
            "必须是布尔值。"
        )

    if not deterministic_mode:
        raise ValueError(
            "deterministic_one_to_one_shuffle "
            "要求 generation.deterministic_mode "
            "= true。"
        )

    random_seed = generation.get(
        "random_seed"
    )

    if (
        isinstance(random_seed, bool)
        or not isinstance(random_seed, int)
    ):
        raise ValueError(
            "deterministic_one_to_one_shuffle "
            "要求 generation.random_seed "
            "为整数。"
        )

    _, profile = get_active_scale_profile(
        manifest
    )

    p03_parameters = manifest[
        "business_patterns"
    ][
        "P03_membership_customer_overlap"
    ][
        "parameters"
    ]

    mapped_customer_ratio = p03_parameters[
        "mapped_customer_ratio"
    ]

    if (
        isinstance(mapped_customer_ratio, bool)
        or not isinstance(
            mapped_customer_ratio,
            (int, float),
        )
        or not (
            0
            <= mapped_customer_ratio
            <= 1
        )
    ):
        raise ValueError(
            "P03 mapped_customer_ratio "
            "必须是 [0, 1] 范围内的数值。"
        )

    mapped_customer_count = round(
        profile["customers"]
        * mapped_customer_ratio
    )

    if mapped_customer_count <= 0:
        raise ValueError(
            "Day64 当前要求生成至少一条 "
            "customer-membership 映射："
            f"mapped_customer_count="
            f"{mapped_customer_count}"
        )

    if (
        mapped_customer_count
        > profile["customers"]
    ):
        raise ValueError(
            "映射数量不能超过客户数量："
            f"mapped_customer_count="
            f"{mapped_customer_count}, "
            f"customers={profile['customers']}"
        )

    if (
        mapped_customer_count
        > profile["membership_accounts"]
    ):
        raise ValueError(
            "映射数量不能超过会员账户数量："
            f"mapped_customer_count="
            f"{mapped_customer_count}, "
            "membership_accounts="
            f"{profile['membership_accounts']}"
        )

    # 当前策略是一对一映射，因此 3000 对关系
    # 必须分别使用 3000 个不同客户和会员账户。
    maximum_one_to_one_mapping_count = min(
        profile["customers"],
        profile["membership_accounts"],
    )

    if (
        mapped_customer_count
        > maximum_one_to_one_mapping_count
    ):
        raise ValueError(
            "一对一映射数量超过可配对上限："
            f"mapped_customer_count="
            f"{mapped_customer_count}, "
            "maximum_one_to_one_mapping_count="
            f"{maximum_one_to_one_mapping_count}"
        )

    if (
        effective_to_strategy == "open"
        and mapping_status != "active"
    ):
        raise ValueError(
            "开放的身份映射必须使用 "
            "mapping_status=active。"
        )


def validate_channel_binding_generation(
    manifest: dict[str, Any],
) -> None:
    """
    验证会员渠道绑定历史生成合同。

    当前 Day64 P0 规则：
    1. 首次入会渠道必须包含在绑定渠道中；
    2. 其他渠道无放回选择；
    3. 首次入会渠道从 joined_at 生效；
    4. 其他渠道在 joined_at 到业务结束时间之间生效；
    5. active 账户保留开放绑定；
    6. inactive 账户不允许保留开放绑定；
    7. 绑定数量不能超过可绑定渠道数量。
    """
    config = manifest.get(
        "channel_binding_generation"
    )

    if not isinstance(config, dict):
        raise ValueError(
            "Manifest 缺少有效的 "
            "channel_binding_generation。"
        )

    required_fields = {
        "channel_selection_strategy",
        "join_channel_effective_from_strategy",
        "additional_channel_effective_from_strategy",
        "active_account_effective_to_strategy",
        "inactive_account_effective_to_strategy",
        "inactive_account_min_close_delay_seconds",
        "binding_status_by_membership_status",
        "binding_source_by_channel_role",
    }

    missing_fields = (
        required_fields - config.keys()
    )

    if missing_fields:
        raise ValueError(
            "channel_binding_generation "
            "缺少字段："
            f"{sorted(missing_fields)}"
        )

    expected_strategies = {
        "channel_selection_strategy": (
            "include_join_channel_then_"
            "uniform_without_replacement"
        ),
        "join_channel_effective_from_strategy": (
            "membership_joined_at"
        ),
        "additional_channel_effective_from_strategy": (
            "uniform_between_joined_at_"
            "and_business_end"
        ),
        "active_account_effective_to_strategy": (
            "open"
        ),
        "inactive_account_effective_to_strategy": (
            "uniform_after_latest_binding_"
            "until_observation_end"
        ),
    }

    for field_name, expected_value in (
        expected_strategies.items()
    ):
        actual_value = config[field_name]

        if (
            not isinstance(actual_value, str)
            or not actual_value.strip()
        ):
            raise ValueError(
                "channel_binding_generation."
                f"{field_name} 必须是非空字符串。"
            )

        actual_value = actual_value.strip()

        if actual_value != expected_value:
            raise ValueError(
                "Day64 当前不支持 "
                "channel_binding_generation."
                f"{field_name}={actual_value!r}，"
                f"当前要求：{expected_value!r}"
            )

    close_delay_seconds = config[
        "inactive_account_min_close_delay_seconds"
    ]

    if (
        isinstance(close_delay_seconds, bool)
        or not isinstance(
            close_delay_seconds,
            int,
        )
        or close_delay_seconds <= 0
    ):
        raise ValueError(
            "channel_binding_generation."
            "inactive_account_min_close_delay_seconds "
            "必须是正整数。"
        )

    parameters = manifest[
        "business_patterns"
    ][
        "P03_membership_customer_overlap"
    ][
        "parameters"
    ]

    require_join_channel_binding = (
        parameters.get(
            "require_join_channel_binding"
        )
    )

    if not isinstance(
        require_join_channel_binding,
        bool,
    ):
        raise ValueError(
            "P03 require_join_channel_binding "
            "必须是布尔值。"
        )

    if not require_join_channel_binding:
        raise ValueError(
            "当前渠道选择策略要求 "
            "P03 require_join_channel_binding=true。"
        )

    inactive_open_allowed = parameters.get(
        "inactive_account_open_binding_allowed"
    )

    if not isinstance(
        inactive_open_allowed,
        bool,
    ):
        raise ValueError(
            "P03 "
            "inactive_account_open_binding_allowed "
            "必须是布尔值。"
        )

    if inactive_open_allowed:
        raise ValueError(
            "当前 inactive 账户关闭策略要求 "
            "inactive_account_open_binding_allowed=false。"
        )

    binding_count_distribution = parameters[
        "channel_binding_count_distribution"
    ]

    if (
        not isinstance(
            binding_count_distribution,
            dict,
        )
        or not binding_count_distribution
    ):
        raise ValueError(
            "P03 channel_binding_count_distribution "
            "必须是非空字典。"
        )

    binding_counts: list[int] = []

    for binding_count in (
        binding_count_distribution.keys()
    ):
        if (
            isinstance(binding_count, bool)
            or not isinstance(binding_count, int)
            or binding_count <= 0
        ):
            raise ValueError(
                "channel_binding_count_distribution "
                "的键必须是正整数："
                f"{binding_count!r}"
            )

        binding_counts.append(binding_count)

    validate_probability_distribution(
        binding_count_distribution,
        (
            "business_patterns."
            "P03_membership_customer_overlap."
            "parameters."
            "channel_binding_count_distribution"
        ),
    )

    bindable_channels = [
        channel
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

    bindable_channel_codes = {
        channel["channel_code"].strip()
        for channel in bindable_channels
    }

    if not bindable_channel_codes:
        raise ValueError(
            "当前渠道绑定生成规则要求至少一个"
            "启用且支持会员绑定的渠道。"
        )

    maximum_binding_count = max(
        binding_counts
    )

    if (
        maximum_binding_count
        > len(bindable_channel_codes)
    ):
        raise ValueError(
            "会员最大绑定渠道数超过"
            "可绑定渠道数量："
            f"maximum_binding_count="
            f"{maximum_binding_count}, "
            "bindable_channel_count="
            f"{len(bindable_channel_codes)}"
        )

    join_channel_codes = {
        channel_code.strip()
        for channel_code in manifest[
            "membership_generation"
        ][
            "join_channel_weights"
        ].keys()
    }

    invalid_join_channel_codes = (
        join_channel_codes
        - bindable_channel_codes
    )

    if invalid_join_channel_codes:
        raise ValueError(
            "首次入会渠道中存在不能用于"
            "会员绑定的渠道："
            f"{sorted(invalid_join_channel_codes)}"
        )

    status_mapping = config[
        "binding_status_by_membership_status"
    ]

    if not isinstance(status_mapping, dict):
        raise ValueError(
            "binding_status_by_membership_status "
            "必须是字典。"
        )

    expected_status_mapping = {
        "active": "active",
        "inactive": "inactive",
    }

    if status_mapping != expected_status_mapping:
        raise ValueError(
            "Day64 当前要求 "
            "binding_status_by_membership_status="
            f"{expected_status_mapping}，"
            f"当前值为：{status_mapping}"
        )

    membership_statuses = set(
        parameters[
            "membership_status_distribution"
        ].keys()
    )

    if (
        set(status_mapping.keys())
        != membership_statuses
    ):
        raise ValueError(
            "渠道绑定状态映射必须覆盖"
            "全部会员账户状态："
            f"membership_statuses="
            f"{sorted(membership_statuses)}, "
            "mapping_statuses="
            f"{sorted(status_mapping.keys())}"
        )

    source_mapping = config[
        "binding_source_by_channel_role"
    ]

    if not isinstance(source_mapping, dict):
        raise ValueError(
            "binding_source_by_channel_role "
            "必须是字典。"
        )

    expected_source_mapping = {
        "join_channel": "join_channel",
        "additional_channel": (
            "additional_channel"
        ),
    }

    if source_mapping != expected_source_mapping:
        raise ValueError(
            "Day64 当前要求 "
            "binding_source_by_channel_role="
            f"{expected_source_mapping}，"
            f"当前值为：{source_mapping}"
        )

    for field_name, value in {
        **status_mapping,
        **source_mapping,
    }.items():
        if (
            not isinstance(value, str)
            or not value.strip()
        ):
            raise ValueError(
                "渠道绑定状态或来源"
                "必须是非空字符串："
                f"{field_name}={value!r}"
            )

        if len(value.strip()) > 50:
            raise ValueError(
                "渠道绑定状态或来源超过"
                "数据库 VARCHAR(50) 长度："
                f"{field_name}={value!r}"
            )

    generation = manifest[
        "generation"
    ]

    business_end_date = parse_manifest_date(
        generation["business_end_date"],
        "generation.business_end_date",
    )

    observation_end_date = parse_manifest_date(
        generation[
            "event_observation_end_date"
        ],
        (
            "generation."
            "event_observation_end_date"
        ),
    )

    business_end_ts = datetime.combine(
        business_end_date,
        time(23, 59, 59),
    )

    observation_end_ts = datetime.combine(
        observation_end_date,
        time(23, 59, 59),
    )

    if (
        observation_end_ts
        - business_end_ts
        < timedelta(
            seconds=close_delay_seconds
        )
    ):
        raise ValueError(
            "事件观察窗口不足以关闭"
            "inactive 账户的渠道绑定："
            f"business_end_ts={business_end_ts}, "
            "observation_end_ts="
            f"{observation_end_ts}, "
            "minimum_delay_seconds="
            f"{close_delay_seconds}"
        )

    joined_end_time = parse_manifest_time(
        manifest[
            "membership_generation"
        ][
            "joined_time_window"
        ][
            "end_time"
        ],
        (
            "membership_generation."
            "joined_time_window.end_time"
        ),
    )

    latest_possible_joined_at = max(
        datetime.combine(
            parse_manifest_date(
                cohort["end_date"],
                (
                    "membership_generation."
                    "joined_at_cohorts.end_date"
                ),
            ),
            joined_end_time,
        )
        for cohort in manifest[
            "membership_generation"
        ][
            "joined_at_cohorts"
        ]
    )

    if latest_possible_joined_at > business_end_ts:
        raise ValueError(
            "最晚可能的会员入会时间"
            "晚于业务结束时间，"
            "无法生成 additional channel "
            "绑定开始时间："
            "latest_possible_joined_at="
            f"{latest_possible_joined_at}, "
            f"business_end_ts={business_end_ts}"
        )


def load_and_validate_day64_manifest(
    manifest_path: Path = MANIFEST_PATH,
) -> dict[str, Any]:
    """
    Day64 Seed 使用的统一 Manifest 入口。
    """
    manifest = load_manifest(manifest_path)
    validate_day64_manifest(manifest)
    return manifest


if __name__ == "__main__":
    loaded_manifest = load_and_validate_day64_manifest()
    profile_name, profile = get_active_scale_profile(
        loaded_manifest
    )

    parameters = loaded_manifest[
        "business_patterns"
    ][
        "P03_membership_customer_overlap"
    ][
        "parameters"
    ]

    mapped_customer_count = round(
        profile["customers"]
        * parameters["mapped_customer_ratio"]
    )

    unmapped_customer_count = (
        profile["customers"]
        - mapped_customer_count
    )

    membership_only_count = (
        profile["membership_accounts"]
        - mapped_customer_count
    )

    print("Day64 Manifest validation passed.")
    print(f"Active profile: {profile_name}")
    print(f"Profile values: {profile}")
    print(
        "Mapped customer-membership pairs: "
        f"{mapped_customer_count}"
    )
    print(
        "Customers without membership mapping: "
        f"{unmapped_customer_count}"
    )
    print(
        "Membership accounts without customer mapping: "
        f"{membership_only_count}"
    )