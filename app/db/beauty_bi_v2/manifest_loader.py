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



def _require_mapping(
    parent: dict[str, Any],
    field_name: str,
    field_path: str,
) -> dict[str, Any]:
    value = parent.get(field_name)

    if not isinstance(value, dict):
        raise ValueError(
            f"{field_path} 必须是字典。"
        )

    return value


def _require_fields(
    value: dict[str, Any],
    required_fields: set[str],
    field_path: str,
) -> None:
    missing_fields = required_fields - value.keys()

    if missing_fields:
        raise ValueError(
            f"{field_path} 缺少字段："
            f"{sorted(missing_fields)}"
        )


def _require_string(
    value: Any,
    field_path: str,
) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
    ):
        raise ValueError(
            f"{field_path} 必须是非空字符串。"
        )

    return value.strip()


def _require_bool(
    value: Any,
    field_path: str,
) -> bool:
    if not isinstance(value, bool):
        raise ValueError(
            f"{field_path} 必须是布尔值，"
            f"当前值为：{value!r}"
        )

    return value


def _require_number(
    value: Any,
    field_path: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
    minimum_inclusive: bool = True,
    maximum_inclusive: bool = True,
) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
    ):
        raise ValueError(
            f"{field_path} 必须是数值，"
            f"当前值为：{value!r}"
        )

    number = float(value)

    if minimum is not None:
        invalid = (
            number < minimum
            if minimum_inclusive
            else number <= minimum
        )

        if invalid:
            operator = ">=" if minimum_inclusive else ">"

            raise ValueError(
                f"{field_path} 必须 {operator} {minimum}，"
                f"当前值为：{value!r}"
            )

    if maximum is not None:
        invalid = (
            number > maximum
            if maximum_inclusive
            else number >= maximum
        )

        if invalid:
            operator = "<=" if maximum_inclusive else "<"

            raise ValueError(
                f"{field_path} 必须 {operator} {maximum}，"
                f"当前值为：{value!r}"
            )

    return number


def _require_positive_int(
    value: Any,
    field_path: str,
) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value <= 0
    ):
        raise ValueError(
            f"{field_path} 必须是正整数，"
            f"当前值为：{value!r}"
        )

    return value


def _require_exact(
    value: Any,
    expected_value: str,
    field_path: str,
) -> str:
    normalized_value = _require_string(
        value,
        field_path,
    )

    if normalized_value != expected_value:
        raise ValueError(
            f"Day65 当前要求 {field_path}="
            f"{expected_value!r}，"
            f"当前值为：{normalized_value!r}"
        )

    return normalized_value

def validate_membership_tier_policy(
    manifest: dict[str, Any],
) -> None:
    """
    验证 Day65 会员等级评估合同。

    主要检查：
    1. 每日评估频率和评估时间；
    2. 初始等级赋予策略；
    3. 等级字段、编码和顺序；
    4. 升级与保级门槛；
    5. 初始等级必须是最低等级。
    """
    policy = manifest.get("membership_policy")

    if not isinstance(policy, dict):
        raise ValueError(
            "Manifest 缺少有效的 membership_policy。"
        )

    evaluation_frequency = policy.get(
        "evaluation_frequency"
    )

    if evaluation_frequency != "daily":
        raise ValueError(
            "Day65 当前只支持 "
            "membership_policy.evaluation_frequency "
            "= daily，"
            f"当前值为：{evaluation_frequency!r}"
        )

    parse_manifest_time(
        policy.get("evaluation_time"),
        "membership_policy.evaluation_time",
    )

    initial_assignment = policy.get(
        "initial_assignment"
    )

    if not isinstance(initial_assignment, dict):
        raise ValueError(
            "membership_policy.initial_assignment "
            "必须是字典。"
        )

    required_initial_fields = {
        "level",
        "effective_from_strategy",
    }

    missing_initial_fields = (
        required_initial_fields
        - initial_assignment.keys()
    )

    if missing_initial_fields:
        raise ValueError(
            "membership_policy.initial_assignment "
            "缺少字段："
            f"{sorted(missing_initial_fields)}"
        )

    initial_level = initial_assignment["level"]

    if (
        not isinstance(initial_level, str)
        or not initial_level.strip()
    ):
        raise ValueError(
            "membership_policy.initial_assignment."
            "level 必须是非空字符串。"
        )

    initial_level = initial_level.strip()

    effective_from_strategy = initial_assignment[
        "effective_from_strategy"
    ]

    if (
        not isinstance(
            effective_from_strategy,
            str,
        )
        or not effective_from_strategy.strip()
    ):
        raise ValueError(
            "membership_policy.initial_assignment."
            "effective_from_strategy "
            "必须是非空字符串。"
        )

    effective_from_strategy = (
        effective_from_strategy.strip()
    )

    expected_effective_from_strategy = (
        "max_membership_joined_at_and_business_start"
    )

    if (
        effective_from_strategy
        != expected_effective_from_strategy
    ):
        raise ValueError(
            "Day65 当前只支持 "
            "membership_policy.initial_assignment."
            "effective_from_strategy="
            f"{expected_effective_from_strategy!r}，"
            f"当前值为：{effective_from_strategy!r}"
        )

    tiers = policy.get("tiers")

    if not isinstance(tiers, list) or not tiers:
        raise ValueError(
            "membership_policy.tiers "
            "必须是非空列表。"
        )

    required_tier_fields = {
        "level",
        "rank",
        "upgrade_threshold",
        "retention_threshold",
    }

    parsed_tiers: list[dict[str, Any]] = []
    levels: set[str] = set()
    ranks: set[int] = set()

    for index, tier in enumerate(tiers):
        field_prefix = (
            f"membership_policy.tiers[{index}]"
        )

        if not isinstance(tier, dict):
            raise ValueError(
                f"{field_prefix} 必须是字典。"
            )

        missing_fields = (
            required_tier_fields
            - tier.keys()
        )

        if missing_fields:
            raise ValueError(
                f"{field_prefix} 缺少字段："
                f"{sorted(missing_fields)}"
            )

        level = tier["level"]

        if (
            not isinstance(level, str)
            or not level.strip()
        ):
            raise ValueError(
                f"{field_prefix}.level "
                "必须是非空字符串。"
            )

        level = level.strip()

        if level in levels:
            raise ValueError(
                "membership_policy.tiers "
                "存在重复 level："
                f"{level!r}"
            )

        if len(level) > 50:
            raise ValueError(
                f"{field_prefix}.level "
                "超过数据库 VARCHAR(50) 长度："
                f"{level!r}"
            )

        rank = tier["rank"]

        if (
            isinstance(rank, bool)
            or not isinstance(rank, int)
            or rank <= 0
        ):
            raise ValueError(
                f"{field_prefix}.rank "
                "必须是正整数，"
                f"当前值为：{rank!r}"
            )

        if rank in ranks:
            raise ValueError(
                "membership_policy.tiers "
                "存在重复 rank："
                f"{rank}"
            )

        upgrade_threshold = tier[
            "upgrade_threshold"
        ]

        if (
            isinstance(upgrade_threshold, bool)
            or not isinstance(
                upgrade_threshold,
                (int, float),
            )
            or upgrade_threshold < 0
        ):
            raise ValueError(
                f"{field_prefix}.upgrade_threshold "
                "必须是非负数，"
                f"当前值为：{upgrade_threshold!r}"
            )

        retention_threshold = tier[
            "retention_threshold"
        ]

        if (
            isinstance(retention_threshold, bool)
            or not isinstance(
                retention_threshold,
                (int, float),
            )
            or retention_threshold < 0
        ):
            raise ValueError(
                f"{field_prefix}.retention_threshold "
                "必须是非负数，"
                f"当前值为：{retention_threshold!r}"
            )

        if (
            retention_threshold
            > upgrade_threshold
        ):
            raise ValueError(
                f"{field_prefix} 的保级门槛"
                "不能高于升级门槛："
                f"retention_threshold="
                f"{retention_threshold}, "
                f"upgrade_threshold="
                f"{upgrade_threshold}"
            )

        parsed_tiers.append(
            {
                "level": level,
                "rank": rank,
                "upgrade_threshold": (
                    upgrade_threshold
                ),
                "retention_threshold": (
                    retention_threshold
                ),
            }
        )

        levels.add(level)
        ranks.add(rank)

    parsed_tiers.sort(
        key=lambda tier: tier["rank"]
    )

    actual_ranks = [
        tier["rank"]
        for tier in parsed_tiers
    ]

    expected_ranks = list(
        range(1, len(parsed_tiers) + 1)
    )

    if actual_ranks != expected_ranks:
        raise ValueError(
            "membership_policy.tiers.rank "
            "必须从 1 开始连续递增："
            f"expected={expected_ranks}, "
            f"actual={actual_ranks}"
        )

    for lower_tier, higher_tier in zip(
        parsed_tiers,
        parsed_tiers[1:],
    ):
        if (
            higher_tier["upgrade_threshold"]
            <= lower_tier["upgrade_threshold"]
        ):
            raise ValueError(
                "会员等级升级门槛必须随 rank "
                "严格递增："
                f"{lower_tier['level']}="
                f"{lower_tier['upgrade_threshold']}, "
                f"{higher_tier['level']}="
                f"{higher_tier['upgrade_threshold']}"
            )

    lowest_tier = parsed_tiers[0]

    if lowest_tier["rank"] != 1:
        raise ValueError(
            "最低会员等级的 rank 必须为 1。"
        )

    if lowest_tier["upgrade_threshold"] != 0:
        raise ValueError(
            "最低会员等级的 upgrade_threshold "
            "必须为 0。"
        )

    if lowest_tier["retention_threshold"] != 0:
        raise ValueError(
            "最低会员等级的 retention_threshold "
            "必须为 0。"
        )

    if initial_level not in levels:
        raise ValueError(
            "membership_policy.initial_assignment."
            "level 不存在于 membership_policy.tiers："
            f"{initial_level!r}"
        )

    if initial_level != lowest_tier["level"]:
        raise ValueError(
            "初始会员等级必须是最低等级："
            f"initial_level={initial_level!r}, "
            "lowest_level="
            f"{lowest_tier['level']!r}"
        )



def validate_order_generation(
    manifest: dict[str, Any],
) -> None:
    """
    验证 Day65 订单生成合同。

    重点保护订单总量、日期分配、生命周期、明细分布、
    促销概率和金额公式，避免错误配置进入交易生成器。
    """
    config = manifest.get("order_generation")

    if not isinstance(config, dict):
        raise ValueError(
            "Manifest 缺少有效的 order_generation。"
        )

    _, profile = get_active_scale_profile(manifest)
    expected_orders = profile["expected_orders"]

    # 1. 订单编码与目标总量
    order_code = _require_mapping(
        config,
        "order_code",
        "order_generation.order_code",
    )
    _require_fields(
        order_code,
        {"prefix", "width"},
        "order_generation.order_code",
    )

    prefix = _require_string(
        order_code["prefix"],
        "order_generation.order_code.prefix",
    )
    width = _require_positive_int(
        order_code["width"],
        "order_generation.order_code.width",
    )

    if prefix != prefix.upper():
        raise ValueError(
            "order_generation.order_code.prefix "
            "必须使用大写稳定编码。"
        )

    if not prefix.replace("_", "").isalnum():
        raise ValueError(
            "order_generation.order_code.prefix "
            "只能包含字母、数字和下划线。"
        )

    if len(prefix) + width > 50:
        raise ValueError(
            "订单编码超过 fact_orders.order_code "
            "的 VARCHAR(50) 长度。"
        )

    if expected_orders > 10 ** width - 1:
        raise ValueError(
            "order_code.width 无法容纳当前 Profile "
            f"的订单数：{expected_orders}"
        )

    target_count = _require_mapping(
        config,
        "target_count",
        "order_generation.target_count",
    )
    _require_fields(
        target_count,
        {
            "source",
            "semantics",
            "exact_total_required",
        },
        "order_generation.target_count",
    )
    _require_exact(
        target_count["source"],
        "scale_profile.expected_orders",
        "order_generation.target_count.source",
    )
    _require_exact(
        target_count["semantics"],
        "fact_orders_total_rows",
        "order_generation.target_count.semantics",
    )

    if not _require_bool(
        target_count["exact_total_required"],
        (
            "order_generation.target_count."
            "exact_total_required"
        ),
    ):
        raise ValueError(
            "exact_total_required 必须为 true。"
        )

    # 2. 日期分配
    date_allocation = _require_mapping(
        config,
        "date_allocation",
        "order_generation.date_allocation",
    )
    _require_fields(
        date_allocation,
        {
            "strategy",
            "annual_weights",
            "weekday_multipliers",
            "holiday_multiplier",
            "campaign_family_multipliers",
            "deterministic_noise",
            "exact_total_reconciliation",
        },
        "order_generation.date_allocation",
    )
    _require_exact(
        date_allocation["strategy"],
        "weighted_exact_total",
        "order_generation.date_allocation.strategy",
    )

    annual_weights = date_allocation[
        "annual_weights"
    ]
    validate_probability_distribution(
        annual_weights,
        (
            "order_generation.date_allocation."
            "annual_weights"
        ),
    )

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

    normalized_years: set[int] = set()

    for raw_year in annual_weights:
        if isinstance(raw_year, bool):
            raise ValueError(
                "annual_weights 年份不能是布尔值。"
            )

        try:
            year = int(raw_year)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "annual_weights 包含非法年份："
                f"{raw_year!r}"
            ) from exc

        if year in normalized_years:
            raise ValueError(
                "annual_weights 标准化后存在"
                f"重复年份：{year}"
            )

        normalized_years.add(year)

    expected_years = set(
        range(
            business_start_date.year,
            business_end_date.year + 1,
        )
    )

    if normalized_years != expected_years:
        raise ValueError(
            "annual_weights 必须完整覆盖业务年份："
            f"expected={sorted(expected_years)}, "
            f"actual={sorted(normalized_years)}"
        )

    weekday_multipliers = date_allocation[
        "weekday_multipliers"
    ]

    if not isinstance(weekday_multipliers, dict):
        raise ValueError(
            "weekday_multipliers 必须是字典。"
        )

    expected_weekdays = {
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
    }

    if set(weekday_multipliers) != expected_weekdays:
        raise ValueError(
            "weekday_multipliers 必须完整覆盖七天。"
        )

    for weekday, multiplier in (
        weekday_multipliers.items()
    ):
        _require_number(
            multiplier,
            (
                "order_generation.date_allocation."
                f"weekday_multipliers.{weekday}"
            ),
            minimum=0,
            minimum_inclusive=False,
        )

    _require_number(
        date_allocation["holiday_multiplier"],
        (
            "order_generation.date_allocation."
            "holiday_multiplier"
        ),
        minimum=0,
        minimum_inclusive=False,
    )

    campaign_multipliers = date_allocation[
        "campaign_family_multipliers"
    ]

    if (
        not isinstance(campaign_multipliers, dict)
        or not campaign_multipliers
    ):
        raise ValueError(
            "campaign_family_multipliers "
            "必须是非空字典。"
        )

    major_campaign_families = {
        campaign["campaign_family"].strip()
        for campaign in manifest[
            "business_calendar"
        ]["campaigns"]
        if (
            campaign["campaign_type"].strip()
            == "major_promotion"
        )
    }

    if set(campaign_multipliers) != (
        major_campaign_families
    ):
        raise ValueError(
            "campaign_family_multipliers 必须与"
            " major_promotion 活动家族一致："
            f"expected={sorted(major_campaign_families)}, "
            f"actual={sorted(campaign_multipliers)}"
        )

    for family, multiplier in (
        campaign_multipliers.items()
    ):
        _require_number(
            multiplier,
            (
                "order_generation.date_allocation."
                "campaign_family_multipliers."
                f"{family}"
            ),
            minimum=0,
            minimum_inclusive=False,
        )

    noise = _require_mapping(
        date_allocation,
        "deterministic_noise",
        (
            "order_generation.date_allocation."
            "deterministic_noise"
        ),
    )
    _require_fields(
        noise,
        {
            "enabled",
            "minimum_multiplier",
            "maximum_multiplier",
        },
        (
            "order_generation.date_allocation."
            "deterministic_noise"
        ),
    )

    if not _require_bool(
        noise["enabled"],
        (
            "order_generation.date_allocation."
            "deterministic_noise.enabled"
        ),
    ):
        raise ValueError(
            "deterministic_noise.enabled 必须为 true。"
        )

    minimum_noise = _require_number(
        noise["minimum_multiplier"],
        (
            "order_generation.date_allocation."
            "deterministic_noise.minimum_multiplier"
        ),
        minimum=0,
        minimum_inclusive=False,
    )
    maximum_noise = _require_number(
        noise["maximum_multiplier"],
        (
            "order_generation.date_allocation."
            "deterministic_noise.maximum_multiplier"
        ),
        minimum=0,
        minimum_inclusive=False,
    )

    if minimum_noise > maximum_noise:
        raise ValueError(
            "minimum_multiplier 不能大于 "
            "maximum_multiplier。"
        )

    if not minimum_noise <= 1 <= maximum_noise:
        raise ValueError(
            "deterministic_noise 区间必须包含 1。"
        )

    reconciliation = _require_mapping(
        date_allocation,
        "exact_total_reconciliation",
        (
            "order_generation.date_allocation."
            "exact_total_reconciliation"
        ),
    )
    _require_exact(
        reconciliation.get("strategy"),
        "largest_remainder",
        (
            "order_generation.date_allocation."
            "exact_total_reconciliation.strategy"
        ),
    )

    # 3. 日内时间分布
    time_distribution = _require_mapping(
        config,
        "creation_time_distribution",
        (
            "order_generation."
            "creation_time_distribution"
        ),
    )
    _require_fields(
        time_distribution,
        {
            "strategy",
            "interval_semantics",
            "dayparts",
        },
        (
            "order_generation."
            "creation_time_distribution"
        ),
    )
    _require_exact(
        time_distribution["strategy"],
        "daypart_weighted",
        (
            "order_generation."
            "creation_time_distribution.strategy"
        ),
    )
    _require_exact(
        time_distribution["interval_semantics"],
        "half_open",
        (
            "order_generation."
            "creation_time_distribution."
            "interval_semantics"
        ),
    )

    dayparts = time_distribution["dayparts"]

    if not isinstance(dayparts, list) or not dayparts:
        raise ValueError(
            "creation_time_distribution.dayparts "
            "必须是非空列表。"
        )

    daypart_weights: dict[str, float] = {}
    parsed_dayparts: list[
        tuple[int, int, str]
    ] = []

    for index, daypart in enumerate(dayparts):
        field_path = (
            "order_generation."
            "creation_time_distribution."
            f"dayparts[{index}]"
        )

        if not isinstance(daypart, dict):
            raise ValueError(
                f"{field_path} 必须是字典。"
            )

        _require_fields(
            daypart,
            {
                "name",
                "start_hour",
                "end_hour",
                "weight",
            },
            field_path,
        )

        name = _require_string(
            daypart["name"],
            f"{field_path}.name",
        )

        if name in daypart_weights:
            raise ValueError(
                f"daypart name 不能重复：{name}"
            )

        start_hour = daypart["start_hour"]
        end_hour = daypart["end_hour"]

        for field_name, hour in {
            "start_hour": start_hour,
            "end_hour": end_hour,
        }.items():
            if (
                isinstance(hour, bool)
                or not isinstance(hour, int)
                or not 0 <= hour <= 24
            ):
                raise ValueError(
                    f"{field_path}.{field_name} "
                    "必须是 [0, 24] 内的整数。"
                )

        if start_hour >= end_hour:
            raise ValueError(
                f"{field_path} 必须满足 "
                "start_hour < end_hour。"
            )

        weight = _require_number(
            daypart["weight"],
            f"{field_path}.weight",
            minimum=0,
            maximum=1,
            minimum_inclusive=False,
        )

        daypart_weights[name] = weight
        parsed_dayparts.append(
            (start_hour, end_hour, name)
        )

    validate_probability_distribution(
        daypart_weights,
        (
            "order_generation."
            "creation_time_distribution."
            "dayparts.weight"
        ),
    )

    parsed_dayparts.sort(key=lambda item: item[0])

    if (
        parsed_dayparts[0][0] != 0
        or parsed_dayparts[-1][1] != 24
    ):
        raise ValueError(
            "dayparts 必须完整覆盖 [0, 24)。"
        )

    for previous, current in zip(
        parsed_dayparts,
        parsed_dayparts[1:],
    ):
        if previous[1] != current[0]:
            raise ValueError(
                "dayparts 必须连续且不能重叠："
                f"{previous[2]} -> {current[2]}"
            )

    # 4. 生命周期
    lifecycle = _require_mapping(
        config,
        "lifecycle",
        "order_generation.lifecycle",
    )
    _require_fields(
        lifecycle,
        {
            "initial_status",
            "successful_payment_probability",
            "payment_delay_minutes",
            "cancellation_delay_minutes",
            "unpaid_final_status",
            "paid_status_before_delivery",
            "delivered_status_after_delivery",
            "new_order_cutoff",
            "payment_completion_cutoff",
        },
        "order_generation.lifecycle",
    )

    expected_statuses = {
        "initial_status": "pending_payment",
        "unpaid_final_status": "cancelled",
        "paid_status_before_delivery": "paid",
        "delivered_status_after_delivery": (
            "delivered"
        ),
    }

    for field_name, expected_value in (
        expected_statuses.items()
    ):
        _require_exact(
            lifecycle[field_name],
            expected_value,
            f"order_generation.lifecycle.{field_name}",
        )

    payment_probability = _require_number(
        lifecycle[
            "successful_payment_probability"
        ],
        (
            "order_generation.lifecycle."
            "successful_payment_probability"
        ),
        minimum=0,
        maximum=1,
        minimum_inclusive=False,
        maximum_inclusive=False,
    )

    if (
        expected_orders * payment_probability < 1
        or expected_orders * (1 - payment_probability) < 1
    ):
        raise ValueError(
            "当前 payment probability 无法同时"
            "生成支付成功和取消订单。"
        )

    for delay_name in {
        "payment_delay_minutes",
        "cancellation_delay_minutes",
    }:
        delay = _require_mapping(
            lifecycle,
            delay_name,
            (
                "order_generation.lifecycle."
                f"{delay_name}"
            ),
        )
        _require_fields(
            delay,
            {"minimum", "maximum"},
            (
                "order_generation.lifecycle."
                f"{delay_name}"
            ),
        )
        minimum_delay = _require_positive_int(
            delay["minimum"],
            (
                "order_generation.lifecycle."
                f"{delay_name}.minimum"
            ),
        )
        maximum_delay = _require_positive_int(
            delay["maximum"],
            (
                "order_generation.lifecycle."
                f"{delay_name}.maximum"
            ),
        )

        if minimum_delay > maximum_delay:
            raise ValueError(
                f"{delay_name}.minimum "
                "不能大于 maximum。"
            )

    cutoff = _require_mapping(
        lifecycle,
        "new_order_cutoff",
        (
            "order_generation.lifecycle."
            "new_order_cutoff"
        ),
    )
    _require_exact(
        cutoff.get("source"),
        "generation.business_end_date",
        (
            "order_generation.lifecycle."
            "new_order_cutoff.source"
        ),
    )

    payment_cutoff = _require_mapping(
        lifecycle,
        "payment_completion_cutoff",
        (
            "order_generation.lifecycle."
            "payment_completion_cutoff"
        ),
    )
    _require_fields(
        payment_cutoff,
        {
            "source",
            "boundary",
            "overflow_behavior",
        },
        (
            "order_generation.lifecycle."
            "payment_completion_cutoff"
        ),
    )
    _require_exact(
        payment_cutoff["source"],
        "generation.business_end_date",
        (
            "order_generation.lifecycle."
            "payment_completion_cutoff.source"
        ),
    )
    _require_exact(
        payment_cutoff["boundary"],
        "end_of_day",
        (
            "order_generation.lifecycle."
            "payment_completion_cutoff.boundary"
        ),
    )
    _require_exact(
        payment_cutoff["overflow_behavior"],
        "cancel_order",
        (
            "order_generation.lifecycle."
            "payment_completion_cutoff."
            "overflow_behavior"
        ),
    )

    # 5. 实体选择
    entity_selection = _require_mapping(
        config,
        "entity_selection",
        "order_generation.entity_selection",
    )
    _require_fields(
        entity_selection,
        {
            "customer",
            "channel",
            "shipping_region",
            "campaign_attribution",
        },
        "order_generation.entity_selection",
    )

    customer = _require_mapping(
        entity_selection,
        "customer",
        (
            "order_generation.entity_selection."
            "customer"
        ),
    )
    _require_exact(
        customer.get("strategy"),
        "simulation_profile_weighted",
        (
            "order_generation.entity_selection."
            "customer.strategy"
        ),
    )

    for field_name in {
        "require_first_seen_before_order",
        "require_active_status",
    }:
        if not _require_bool(
            customer.get(field_name),
            (
                "order_generation.entity_selection."
                f"customer.{field_name}"
            ),
        ):
            raise ValueError(
                f"customer.{field_name} 必须为 true。"
            )

    channel = _require_mapping(
        entity_selection,
        "channel",
        (
            "order_generation.entity_selection."
            "channel"
        ),
    )
    _require_exact(
        channel.get("strategy"),
        "customer_preference_x_daily_context",
        (
            "order_generation.entity_selection."
            "channel.strategy"
        ),
    )

    if not _require_bool(
        channel.get("require_active_sales_channel"),
        (
            "order_generation.entity_selection."
            "channel.require_active_sales_channel"
        ),
    ):
        raise ValueError(
            "require_active_sales_channel 必须为 true。"
        )

    shipping_region = _require_mapping(
        entity_selection,
        "shipping_region",
        (
            "order_generation.entity_selection."
            "shipping_region"
        ),
    )
    _require_exact(
        shipping_region.get("strategy"),
        "customer_home_region_with_override",
        (
            "order_generation.entity_selection."
            "shipping_region.strategy"
        ),
    )

    shipping_distribution = (
        shipping_region.get("distribution")
    )
    validate_probability_distribution(
        shipping_distribution,
        (
            "order_generation.entity_selection."
            "shipping_region.distribution"
        ),
    )

    expected_shipping_keys = {
        "home_region",
        "same_region_group",
        "other_region",
    }

    if set(shipping_distribution) != (
        expected_shipping_keys
    ):
        raise ValueError(
            "shipping_region.distribution 字段不完整。"
        )

    attribution = _require_mapping(
        entity_selection,
        "campaign_attribution",
        (
            "order_generation.entity_selection."
            "campaign_attribution"
        ),
    )
    _require_exact(
        attribution.get("strategy"),
        "active_major_campaign_else_null",
        (
            "order_generation.entity_selection."
            "campaign_attribution.strategy"
        ),
    )

    attribution_probability = _require_number(
        attribution.get(
            "major_campaign_attribution_probability"
        ),
        (
            "order_generation.entity_selection."
            "campaign_attribution."
            "major_campaign_attribution_probability"
        ),
        minimum=0,
        maximum=1,
    )
    allow_null_campaign = _require_bool(
        attribution.get("allow_null_campaign"),
        (
            "order_generation.entity_selection."
            "campaign_attribution.allow_null_campaign"
        ),
    )

    if (
        attribution_probability < 1
        and not allow_null_campaign
    ):
        raise ValueError(
            "活动归因概率小于 1 时必须允许 "
            "campaign_id 为 null。"
        )

    # 6. 订单明细与促销
    item_generation = _require_mapping(
        config,
        "item_generation",
        "order_generation.item_generation",
    )
    _require_fields(
        item_generation,
        {
            "item_count_distribution",
            "quantity_distribution",
            "allow_duplicate_product_in_order",
            "product_selection",
            "promotion_application",
        },
        "order_generation.item_generation",
    )

    for distribution_name in {
        "item_count_distribution",
        "quantity_distribution",
    }:
        distribution = item_generation[
            distribution_name
        ]
        validate_probability_distribution(
            distribution,
            (
                "order_generation.item_generation."
                f"{distribution_name}"
            ),
        )

        for count in distribution:
            if (
                isinstance(count, bool)
                or not isinstance(count, int)
                or count <= 0
            ):
                raise ValueError(
                    f"{distribution_name} 的键"
                    "必须是正整数。"
                )

    if (
        max(
            item_generation[
                "item_count_distribution"
            ]
        )
        > profile["products"]
    ):
        raise ValueError(
            "单订单最大明细数不能超过商品总数。"
        )

    if _require_bool(
        item_generation[
            "allow_duplicate_product_in_order"
        ],
        (
            "order_generation.item_generation."
            "allow_duplicate_product_in_order"
        ),
    ):
        raise ValueError(
            "Day65 当前不允许同一订单重复商品。"
        )

    product_selection = _require_mapping(
        item_generation,
        "product_selection",
        (
            "order_generation.item_generation."
            "product_selection"
        ),
    )
    _require_exact(
        product_selection.get("strategy"),
        "simulation_profile_weighted",
        (
            "order_generation.item_generation."
            "product_selection.strategy"
        ),
    )

    for field_name in {
        "require_launch_before_order",
        "require_active_product",
    }:
        if not _require_bool(
            product_selection.get(field_name),
            (
                "order_generation.item_generation."
                f"product_selection.{field_name}"
            ),
        ):
            raise ValueError(
                f"product_selection.{field_name} "
                "必须为 true。"
            )

    promotion = _require_mapping(
        item_generation,
        "promotion_application",
        (
            "order_generation.item_generation."
            "promotion_application"
        ),
    )
    _require_fields(
        promotion,
        {
            "strategy",
            "probability_by_campaign_type",
            "maximum_promotions_per_item",
            "allow_no_promotion",
        },
        (
            "order_generation.item_generation."
            "promotion_application"
        ),
    )
    _require_exact(
        promotion["strategy"],
        "active_promotion_probability",
        (
            "order_generation.item_generation."
            "promotion_application.strategy"
        ),
    )

    promotion_probabilities = promotion[
        "probability_by_campaign_type"
    ]

    if (
        not isinstance(promotion_probabilities, dict)
        or set(promotion_probabilities)
        != {"always_on", "major_promotion"}
    ):
        raise ValueError(
            "probability_by_campaign_type 必须仅包含 "
            "always_on 和 major_promotion。"
        )

    for campaign_type, probability in (
        promotion_probabilities.items()
    ):
        _require_number(
            probability,
            (
                "order_generation.item_generation."
                "promotion_application."
                "probability_by_campaign_type."
                f"{campaign_type}"
            ),
            minimum=0,
            maximum=1,
        )

    if _require_positive_int(
        promotion["maximum_promotions_per_item"],
        (
            "order_generation.item_generation."
            "promotion_application."
            "maximum_promotions_per_item"
        ),
    ) != 1:
        raise ValueError(
            "maximum_promotions_per_item 必须为 1。"
        )

    if not _require_bool(
        promotion["allow_no_promotion"],
        (
            "order_generation.item_generation."
            "promotion_application."
            "allow_no_promotion"
        ),
    ):
        raise ValueError(
            "allow_no_promotion 必须为 true。"
        )

    # 7. 金额合同
    pricing = _require_mapping(
        config,
        "pricing",
        "order_generation.pricing",
    )
    _require_fields(
        pricing,
        {
            "unit_list_price_source",
            "unit_paid_price_strategy",
            "unit_cost_source",
            "decimal_places",
            "rounding_mode",
            "item_amount_formulas",
            "order_amount_strategy",
            "allow_negative_margin",
        },
        "order_generation.pricing",
    )

    expected_pricing_values = {
        "unit_list_price_source": (
            "dim_product.list_price"
        ),
        "unit_paid_price_strategy": (
            "promotion_discount_else_list_price"
        ),
        "unit_cost_source": (
            "hidden_product_simulation_profile"
        ),
        "rounding_mode": "ROUND_HALF_UP",
        "order_amount_strategy": "sum_order_items",
    }

    for field_name, expected_value in (
        expected_pricing_values.items()
    ):
        _require_exact(
            pricing[field_name],
            expected_value,
            f"order_generation.pricing.{field_name}",
        )

    if (
        isinstance(pricing["decimal_places"], bool)
        or not isinstance(
            pricing["decimal_places"],
            int,
        )
        or pricing["decimal_places"] != 2
    ):
        raise ValueError(
            "pricing.decimal_places 必须为 2。"
        )

    formulas = _require_mapping(
        pricing,
        "item_amount_formulas",
        (
            "order_generation.pricing."
            "item_amount_formulas"
        ),
    )

    expected_formulas = {
        "item_list_amount": (
            "unit_list_price_x_quantity"
        ),
        "item_paid_amount": (
            "unit_paid_price_x_quantity"
        ),
        "item_discount_amount": (
            "item_list_amount_minus_item_paid_amount"
        ),
        "item_cost_amount": (
            "unit_cost_at_order_x_quantity"
        ),
    }

    if set(formulas) != set(expected_formulas):
        raise ValueError(
            "item_amount_formulas 字段与"
            "当前金额合同不一致。"
        )

    for field_name, expected_value in (
        expected_formulas.items()
    ):
        _require_exact(
            formulas[field_name],
            expected_value,
            (
                "order_generation.pricing."
                f"item_amount_formulas.{field_name}"
            ),
        )

    _require_bool(
        pricing["allow_negative_margin"],
        (
            "order_generation.pricing."
            "allow_negative_margin"
        ),
    )

def validate_fulfillment_generation(
    manifest: dict[str, Any],
) -> None:
    """
    验证 Day65 履约生成合同。

    主要检查：
    1. 只有成功支付且未取消的订单进入履约；
    2. 发货、送达、偏远地区和活动拥堵延迟合法；
    3. 偏远地区与 major promotion 活动配置可解析；
    4. 履约最终状态与订单生命周期一致；
    5. 观察尾窗足以容纳最大履约延迟。
    """
    config = manifest.get("fulfillment_generation")

    if not isinstance(config, dict):
        raise ValueError(
            "Manifest 缺少有效的 "
            "fulfillment_generation。"
        )

    eligibility = _require_mapping(
        config,
        "eligibility",
        "fulfillment_generation.eligibility",
    )
    _require_fields(
        eligibility,
        {
            "require_successful_payment",
            "exclude_cancelled_orders",
        },
        "fulfillment_generation.eligibility",
    )

    for field_name in {
        "require_successful_payment",
        "exclude_cancelled_orders",
    }:
        if not _require_bool(
            eligibility[field_name],
            (
                "fulfillment_generation.eligibility."
                f"{field_name}"
            ),
        ):
            raise ValueError(
                "fulfillment_generation.eligibility."
                f"{field_name} 必须为 true。"
            )

    shipping_delay = _require_mapping(
        config,
        "shipping_delay_hours",
        "fulfillment_generation.shipping_delay_hours",
    )
    _require_fields(
        shipping_delay,
        {"minimum", "maximum"},
        "fulfillment_generation.shipping_delay_hours",
    )

    shipping_minimum = _require_positive_int(
        shipping_delay["minimum"],
        (
            "fulfillment_generation."
            "shipping_delay_hours.minimum"
        ),
    )
    shipping_maximum = _require_positive_int(
        shipping_delay["maximum"],
        (
            "fulfillment_generation."
            "shipping_delay_hours.maximum"
        ),
    )

    if shipping_minimum > shipping_maximum:
        raise ValueError(
            "shipping_delay_hours.minimum "
            "不能大于 maximum。"
        )

    delivery_delay = _require_mapping(
        config,
        "delivery_delay_days",
        "fulfillment_generation.delivery_delay_days",
    )
    _require_fields(
        delivery_delay,
        {"minimum", "maximum"},
        "fulfillment_generation.delivery_delay_days",
    )

    delivery_minimum = _require_positive_int(
        delivery_delay["minimum"],
        (
            "fulfillment_generation."
            "delivery_delay_days.minimum"
        ),
    )
    delivery_maximum = _require_positive_int(
        delivery_delay["maximum"],
        (
            "fulfillment_generation."
            "delivery_delay_days.maximum"
        ),
    )

    if delivery_minimum > delivery_maximum:
        raise ValueError(
            "delivery_delay_days.minimum "
            "不能大于 maximum。"
        )

    remote_delay = _require_mapping(
        config,
        "remote_region_extra_delay_days",
        (
            "fulfillment_generation."
            "remote_region_extra_delay_days"
        ),
    )
    _require_fields(
        remote_delay,
        {
            "enabled",
            "region_groups",
            "minimum",
            "maximum",
        },
        (
            "fulfillment_generation."
            "remote_region_extra_delay_days"
        ),
    )

    if not _require_bool(
        remote_delay["enabled"],
        (
            "fulfillment_generation."
            "remote_region_extra_delay_days.enabled"
        ),
    ):
        raise ValueError(
            "remote_region_extra_delay_days.enabled "
            "必须为 true。"
        )

    region_groups = remote_delay["region_groups"]

    if (
        not isinstance(region_groups, list)
        or not region_groups
    ):
        raise ValueError(
            "remote_region_extra_delay_days."
            "region_groups 必须是非空列表。"
        )

    normalized_region_groups: list[str] = []

    for index, region_group in enumerate(
        region_groups
    ):
        normalized_region_groups.append(
            _require_string(
                region_group,
                (
                    "fulfillment_generation."
                    "remote_region_extra_delay_days."
                    f"region_groups[{index}]"
                ),
            )
        )

    if len(set(normalized_region_groups)) != len(
        normalized_region_groups
    ):
        raise ValueError(
            "remote_region_extra_delay_days."
            "region_groups 不能重复。"
        )

    expected_remote_region_groups = {
        "northwest",
        "southwest",
        "northeast",
    }

    if set(normalized_region_groups) != (
        expected_remote_region_groups
    ):
        raise ValueError(
            "Day65 当前要求偏远地区组为："
            f"{sorted(expected_remote_region_groups)}，"
            "当前值为："
            f"{sorted(normalized_region_groups)}"
        )

    configured_region_groups = {
        region["region_group"].strip()
        for region in manifest[
            "fixed_dimensions"
        ]["regions"]
    }

    unknown_region_groups = (
        set(normalized_region_groups)
        - configured_region_groups
    )

    if unknown_region_groups:
        raise ValueError(
            "履约偏远地区组不存在于 "
            "fixed_dimensions.regions："
            f"{sorted(unknown_region_groups)}"
        )

    remote_minimum = _require_positive_int(
        remote_delay["minimum"],
        (
            "fulfillment_generation."
            "remote_region_extra_delay_days.minimum"
        ),
    )
    remote_maximum = _require_positive_int(
        remote_delay["maximum"],
        (
            "fulfillment_generation."
            "remote_region_extra_delay_days.maximum"
        ),
    )

    if remote_minimum > remote_maximum:
        raise ValueError(
            "remote_region_extra_delay_days.minimum "
            "不能大于 maximum。"
        )

    congestion = _require_mapping(
        config,
        "campaign_congestion",
        "fulfillment_generation.campaign_congestion",
    )
    _require_fields(
        congestion,
        {
            "enabled",
            (
                "extra_delay_probability_"
                "by_campaign_family"
            ),
            "extra_delay_days",
        },
        "fulfillment_generation.campaign_congestion",
    )

    if not _require_bool(
        congestion["enabled"],
        (
            "fulfillment_generation."
            "campaign_congestion.enabled"
        ),
    ):
        raise ValueError(
            "campaign_congestion.enabled 必须为 true。"
        )

    congestion_probabilities = congestion[
        "extra_delay_probability_by_campaign_family"
    ]

    if (
        not isinstance(congestion_probabilities, dict)
        or not congestion_probabilities
    ):
        raise ValueError(
            "extra_delay_probability_by_campaign_family "
            "必须是非空字典。"
        )

    major_campaign_families = {
        campaign["campaign_family"].strip()
        for campaign in manifest[
            "business_calendar"
        ]["campaigns"]
        if (
            campaign["campaign_type"].strip()
            == "major_promotion"
        )
    }

    if set(congestion_probabilities) != (
        major_campaign_families
    ):
        raise ValueError(
            "履约拥堵概率必须完整覆盖 "
            "major_promotion 活动家族："
            f"expected={sorted(major_campaign_families)}, "
            f"actual={sorted(congestion_probabilities)}"
        )

    for family, probability in (
        congestion_probabilities.items()
    ):
        _require_number(
            probability,
            (
                "fulfillment_generation."
                "campaign_congestion."
                "extra_delay_probability_by_"
                f"campaign_family.{family}"
            ),
            minimum=0,
            maximum=1,
        )

    congestion_delay = _require_mapping(
        congestion,
        "extra_delay_days",
        (
            "fulfillment_generation."
            "campaign_congestion.extra_delay_days"
        ),
    )
    _require_fields(
        congestion_delay,
        {"minimum", "maximum"},
        (
            "fulfillment_generation."
            "campaign_congestion.extra_delay_days"
        ),
    )

    congestion_minimum = _require_positive_int(
        congestion_delay["minimum"],
        (
            "fulfillment_generation."
            "campaign_congestion."
            "extra_delay_days.minimum"
        ),
    )
    congestion_maximum = _require_positive_int(
        congestion_delay["maximum"],
        (
            "fulfillment_generation."
            "campaign_congestion."
            "extra_delay_days.maximum"
        ),
    )

    if congestion_minimum > congestion_maximum:
        raise ValueError(
            "campaign_congestion.extra_delay_days."
            "minimum 不能大于 maximum。"
        )

    final_status = _require_mapping(
        config,
        "final_status",
        "fulfillment_generation.final_status",
    )
    _require_fields(
        final_status,
        {"delivered_event_status"},
        "fulfillment_generation.final_status",
    )
    _require_exact(
        final_status["delivered_event_status"],
        "delivered",
        (
            "fulfillment_generation.final_status."
            "delivered_event_status"
        ),
    )

    observation_window = _require_mapping(
        config,
        "observation_window",
        "fulfillment_generation.observation_window",
    )
    _require_fields(
        observation_window,
        {
            "allow_delivery_after_business_end",
            "maximum_timestamp_source",
            "incomplete_after_observation_end_status",
        },
        "fulfillment_generation.observation_window",
    )

    if not _require_bool(
        observation_window[
            "allow_delivery_after_business_end"
        ],
        (
            "fulfillment_generation."
            "observation_window."
            "allow_delivery_after_business_end"
        ),
    ):
        raise ValueError(
            "allow_delivery_after_business_end "
            "必须为 true。"
        )

    _require_exact(
        observation_window[
            "maximum_timestamp_source"
        ],
        "generation.event_observation_end_date",
        (
            "fulfillment_generation."
            "observation_window."
            "maximum_timestamp_source"
        ),
    )
    _require_exact(
        observation_window[
            "incomplete_after_observation_end_status"
        ],
        "paid",
        (
            "fulfillment_generation."
            "observation_window."
            "incomplete_after_observation_end_status"
        ),
    )

    order_lifecycle = manifest[
        "order_generation"
    ]["lifecycle"]

    if (
        order_lifecycle[
            "paid_status_before_delivery"
        ]
        != observation_window[
            "incomplete_after_observation_end_status"
        ]
    ):
        raise ValueError(
            "履约未完成状态必须与订单支付后、"
            "送达前状态一致。"
        )

    if (
        order_lifecycle[
            "delivered_status_after_delivery"
        ]
        != final_status["delivered_event_status"]
    ):
        raise ValueError(
            "履约送达状态必须与订单生命周期"
            "送达状态一致。"
        )

    generation = manifest["generation"]
    business_end_date = parse_manifest_date(
        generation["business_end_date"],
        "generation.business_end_date",
    )
    observation_end_date = parse_manifest_date(
        generation["event_observation_end_date"],
        "generation.event_observation_end_date",
    )

    maximum_delay = timedelta(
        hours=shipping_maximum,
        days=(
            delivery_maximum
            + remote_maximum
            + congestion_maximum
        ),
    )

    available_tail = (
        datetime.combine(
            observation_end_date,
            time(23, 59, 59),
        )
        - datetime.combine(
            business_end_date,
            time(23, 59, 59),
        )
    )

    if maximum_delay > available_tail:
        raise ValueError(
            "事件观察尾窗不足以容纳最大履约延迟："
            f"maximum_delay={maximum_delay}, "
            f"available_tail={available_tail}"
        )


def validate_refund_generation(
    manifest: dict[str, Any],
) -> None:
    """
    验证 Day65 退款生成合同。

    主要检查：
    1. 退款资格与每个订单明细的事件上限；
    2. 退款概率模型与概率边界；
    3. 退款申请、数量、金额和处理时序；
    4. 退款状态、原因及观察尾窗处理；
    5. SO 与会员 R12 只扣减 completed 退款。
    """
    config = _require_mapping(
        manifest,
        "refund_generation",
        "refund_generation",
    )

    _require_fields(
        config,
        {
            "eligibility",
            "probability_model",
            "request_delay_days",
            "quantity",
            "amount",
            "resolution",
            "reason_distribution",
            "observation_window",
            "business_effect",
        },
        "refund_generation",
    )

    eligibility = _require_mapping(
        config,
        "eligibility",
        "refund_generation.eligibility",
    )

    _require_fields(
        eligibility,
        {
            "require_successful_payment",
            "require_delivery",
            "exclude_cancelled_orders",
            "maximum_refund_events_per_order_item",
        },
        "refund_generation.eligibility",
    )

    for field_name in {
        "require_successful_payment",
        "require_delivery",
        "exclude_cancelled_orders",
    }:
        value = _require_bool(
            eligibility[field_name],
            (
                "refund_generation.eligibility."
                f"{field_name}"
            ),
        )

        if not value:
            raise ValueError(
                "Day65 退款生成要求 "
                "refund_generation.eligibility."
                f"{field_name}=true。"
            )

    maximum_events = _require_positive_int(
        eligibility[
            "maximum_refund_events_per_order_item"
        ],
        (
            "refund_generation.eligibility."
            "maximum_refund_events_per_order_item"
        ),
    )

    if maximum_events != 1:
        raise ValueError(
            "Day65 当前每个订单明细最多只生成"
            "一个退款事件，"
            "maximum_refund_events_per_order_item "
            f"必须为 1，当前值为：{maximum_events}"
        )

    probability_model = _require_mapping(
        config,
        "probability_model",
        "refund_generation.probability_model",
    )

    _require_fields(
        probability_model,
        {
            "strategy",
            "base_item_refund_probability",
            "quality_risk_multiplier",
            "customer_refund_propensity_multiplier",
            "deep_discount",
            "final_probability",
        },
        "refund_generation.probability_model",
    )

    _require_exact(
        probability_model["strategy"],
        "hidden_profile_multiplicative",
        "refund_generation.probability_model.strategy",
    )

    _require_number(
        probability_model[
            "base_item_refund_probability"
        ],
        (
            "refund_generation.probability_model."
            "base_item_refund_probability"
        ),
        minimum=0,
        maximum=1,
        minimum_inclusive=False,
        maximum_inclusive=False,
    )

    for field_name in {
        "quality_risk_multiplier",
        "customer_refund_propensity_multiplier",
    }:
        multiplier = _require_mapping(
            probability_model,
            field_name,
            (
                "refund_generation.probability_model."
                f"{field_name}"
            ),
        )

        _require_fields(
            multiplier,
            {"minimum", "maximum"},
            (
                "refund_generation.probability_model."
                f"{field_name}"
            ),
        )

        minimum = _require_number(
            multiplier["minimum"],
            (
                "refund_generation.probability_model."
                f"{field_name}.minimum"
            ),
            minimum=0,
            minimum_inclusive=False,
        )

        maximum = _require_number(
            multiplier["maximum"],
            (
                "refund_generation.probability_model."
                f"{field_name}.maximum"
            ),
            minimum=0,
            minimum_inclusive=False,
        )

        if minimum > maximum:
            raise ValueError(
                "退款概率乘数区间必须满足 "
                "minimum <= maximum："
                f"field={field_name}, "
                f"minimum={minimum}, maximum={maximum}"
            )

    deep_discount = _require_mapping(
        probability_model,
        "deep_discount",
        (
            "refund_generation.probability_model."
            "deep_discount"
        ),
    )

    _require_fields(
        deep_discount,
        {"threshold", "multiplier"},
        (
            "refund_generation.probability_model."
            "deep_discount"
        ),
    )

    _require_number(
        deep_discount["threshold"],
        (
            "refund_generation.probability_model."
            "deep_discount.threshold"
        ),
        minimum=0,
        maximum=1,
    )

    _require_number(
        deep_discount["multiplier"],
        (
            "refund_generation.probability_model."
            "deep_discount.multiplier"
        ),
        minimum=0,
        minimum_inclusive=False,
    )

    final_probability = _require_mapping(
        probability_model,
        "final_probability",
        (
            "refund_generation.probability_model."
            "final_probability"
        ),
    )

    _require_fields(
        final_probability,
        {"minimum", "maximum"},
        (
            "refund_generation.probability_model."
            "final_probability"
        ),
    )

    minimum_final_probability = _require_number(
        final_probability["minimum"],
        (
            "refund_generation.probability_model."
            "final_probability.minimum"
        ),
        minimum=0,
        maximum=1,
        minimum_inclusive=False,
    )

    maximum_final_probability = _require_number(
        final_probability["maximum"],
        (
            "refund_generation.probability_model."
            "final_probability.maximum"
        ),
        minimum=0,
        maximum=1,
        maximum_inclusive=False,
    )

    if (
        minimum_final_probability
        > maximum_final_probability
    ):
        raise ValueError(
            "退款最终概率区间必须满足 "
            "minimum <= maximum："
            f"minimum={minimum_final_probability}, "
            f"maximum={maximum_final_probability}"
        )

    request_delay = _require_mapping(
        config,
        "request_delay_days",
        "refund_generation.request_delay_days",
    )

    _require_fields(
        request_delay,
        {
            "minimum",
            "maximum",
            "timestamp_reference",
        },
        "refund_generation.request_delay_days",
    )

    minimum_request_delay = _require_positive_int(
        request_delay["minimum"],
        (
            "refund_generation.request_delay_days."
            "minimum"
        ),
    )

    maximum_request_delay = _require_positive_int(
        request_delay["maximum"],
        (
            "refund_generation.request_delay_days."
            "maximum"
        ),
    )

    if minimum_request_delay > maximum_request_delay:
        raise ValueError(
            "退款申请延迟必须满足 "
            "minimum <= maximum："
            f"minimum={minimum_request_delay}, "
            f"maximum={maximum_request_delay}"
        )

    _require_exact(
        request_delay["timestamp_reference"],
        "delivered_at",
        (
            "refund_generation.request_delay_days."
            "timestamp_reference"
        ),
    )

    quantity = _require_mapping(
        config,
        "quantity",
        "refund_generation.quantity",
    )

    _require_fields(
        quantity,
        {
            "strategy",
            "full_quantity_probability",
            "partial_quantity_strategy",
            "never_exceed_purchased_quantity",
        },
        "refund_generation.quantity",
    )

    _require_exact(
        quantity["strategy"],
        "partial_or_full",
        "refund_generation.quantity.strategy",
    )

    _require_number(
        quantity["full_quantity_probability"],
        (
            "refund_generation.quantity."
            "full_quantity_probability"
        ),
        minimum=0,
        maximum=1,
        minimum_inclusive=False,
        maximum_inclusive=False,
    )

    partial_quantity = _require_mapping(
        quantity,
        "partial_quantity_strategy",
        (
            "refund_generation.quantity."
            "partial_quantity_strategy"
        ),
    )

    _require_fields(
        partial_quantity,
        {"minimum", "maximum_source"},
        (
            "refund_generation.quantity."
            "partial_quantity_strategy"
        ),
    )

    minimum_partial_quantity = _require_positive_int(
        partial_quantity["minimum"],
        (
            "refund_generation.quantity."
            "partial_quantity_strategy.minimum"
        ),
    )

    if minimum_partial_quantity != 1:
        raise ValueError(
            "Day65 部分退款的最小数量必须为 1，"
            f"当前值为：{minimum_partial_quantity}"
        )

    _require_exact(
        partial_quantity["maximum_source"],
        "purchased_quantity_minus_one",
        (
            "refund_generation.quantity."
            "partial_quantity_strategy.maximum_source"
        ),
    )

    never_exceed_quantity = _require_bool(
        quantity[
            "never_exceed_purchased_quantity"
        ],
        (
            "refund_generation.quantity."
            "never_exceed_purchased_quantity"
        ),
    )

    if not never_exceed_quantity:
        raise ValueError(
            "refund_generation.quantity."
            "never_exceed_purchased_quantity "
            "必须为 true。"
        )

    amount = _require_mapping(
        config,
        "amount",
        "refund_generation.amount",
    )

    _require_fields(
        amount,
        {
            "source",
            "decimal_places",
            "rounding_mode",
            "never_exceed_item_paid_amount",
        },
        "refund_generation.amount",
    )

    _require_exact(
        amount["source"],
        "unit_paid_price_x_refund_quantity",
        "refund_generation.amount.source",
    )

    decimal_places = _require_positive_int(
        amount["decimal_places"],
        "refund_generation.amount.decimal_places",
    )

    if decimal_places != 2:
        raise ValueError(
            "退款金额必须保留两位小数，"
            f"当前 decimal_places={decimal_places}"
        )

    _require_exact(
        amount["rounding_mode"],
        "ROUND_HALF_UP",
        "refund_generation.amount.rounding_mode",
    )

    never_exceed_amount = _require_bool(
        amount["never_exceed_item_paid_amount"],
        (
            "refund_generation.amount."
            "never_exceed_item_paid_amount"
        ),
    )

    if not never_exceed_amount:
        raise ValueError(
            "refund_generation.amount."
            "never_exceed_item_paid_amount "
            "必须为 true。"
        )

    resolution = _require_mapping(
        config,
        "resolution",
        "refund_generation.resolution",
    )

    _require_fields(
        resolution,
        {
            "final_status_distribution",
            "delay_hours",
            "completed_timestamp_rule",
        },
        "refund_generation.resolution",
    )

    status_distribution = _require_mapping(
        resolution,
        "final_status_distribution",
        (
            "refund_generation.resolution."
            "final_status_distribution"
        ),
    )

    expected_final_statuses = {
        "completed",
        "rejected",
        "cancelled",
    }

    actual_final_statuses = set(
        status_distribution.keys()
    )

    if actual_final_statuses != expected_final_statuses:
        raise ValueError(
            "refund_generation.resolution."
            "final_status_distribution "
            "必须且只能包含 completed、rejected、"
            "cancelled："
            f"actual={sorted(actual_final_statuses)}"
        )

    validate_probability_distribution(
        status_distribution,
        (
            "refund_generation.resolution."
            "final_status_distribution"
        ),
    )

    for status, probability in (
        status_distribution.items()
    ):
        if probability <= 0:
            raise ValueError(
                "Day65 要求每种退款终态都能生成"
                "正样本，概率必须大于 0："
                f"status={status}, "
                f"probability={probability}"
            )

    resolution_delay = _require_mapping(
        resolution,
        "delay_hours",
        "refund_generation.resolution.delay_hours",
    )

    _require_fields(
        resolution_delay,
        {"minimum", "maximum"},
        "refund_generation.resolution.delay_hours",
    )

    minimum_resolution_delay = _require_positive_int(
        resolution_delay["minimum"],
        (
            "refund_generation.resolution."
            "delay_hours.minimum"
        ),
    )

    maximum_resolution_delay = _require_positive_int(
        resolution_delay["maximum"],
        (
            "refund_generation.resolution."
            "delay_hours.maximum"
        ),
    )

    if (
        minimum_resolution_delay
        > maximum_resolution_delay
    ):
        raise ValueError(
            "退款处理延迟必须满足 "
            "minimum <= maximum："
            f"minimum={minimum_resolution_delay}, "
            f"maximum={maximum_resolution_delay}"
        )

    completed_timestamp_rule = _require_mapping(
        resolution,
        "completed_timestamp_rule",
        (
            "refund_generation.resolution."
            "completed_timestamp_rule"
        ),
    )

    expected_timestamp_keys = {
        "completed",
        "rejected",
        "cancelled",
    }

    if (
        set(completed_timestamp_rule.keys())
        != expected_timestamp_keys
    ):
        raise ValueError(
            "refund_generation.resolution."
            "completed_timestamp_rule "
            "必须覆盖 completed、rejected、cancelled。"
        )

    _require_exact(
        completed_timestamp_rule["completed"],
        "resolution_timestamp",
        (
            "refund_generation.resolution."
            "completed_timestamp_rule.completed"
        ),
    )

    for status in {"rejected", "cancelled"}:
        if completed_timestamp_rule[status] is not None:
            raise ValueError(
                "非 completed 退款不能设置 "
                "refund_completed_at："
                f"status={status}, "
                "configured_rule="
                f"{completed_timestamp_rule[status]!r}"
            )

    reason_distribution = _require_mapping(
        config,
        "reason_distribution",
        "refund_generation.reason_distribution",
    )

    expected_reasons = {
        "quality_issue",
        "damaged_in_transit",
        "allergic_reaction",
        "wrong_item",
        "not_as_expected",
        "changed_mind",
        "other",
    }

    actual_reasons = set(
        reason_distribution.keys()
    )

    if actual_reasons != expected_reasons:
        raise ValueError(
            "refund_generation.reason_distribution "
            "必须使用冻结的退款原因集合："
            f"missing={sorted(expected_reasons - actual_reasons)}, "
            f"unknown={sorted(actual_reasons - expected_reasons)}"
        )

    validate_probability_distribution(
        reason_distribution,
        "refund_generation.reason_distribution",
    )

    for reason, probability in (
        reason_distribution.items()
    ):
        if len(reason) > 100:
            raise ValueError(
                "退款原因编码超过数据库 "
                "VARCHAR(100) 长度："
                f"{reason!r}"
            )

        if probability <= 0:
            raise ValueError(
                "Day65 要求每种退款原因都能生成"
                "正样本，概率必须大于 0："
                f"reason={reason}, "
                f"probability={probability}"
            )

    observation_window = _require_mapping(
        config,
        "observation_window",
        "refund_generation.observation_window",
    )

    _require_fields(
        observation_window,
        {
            "maximum_timestamp_source",
            "unresolved_after_observation_end",
        },
        "refund_generation.observation_window",
    )

    _require_exact(
        observation_window[
            "maximum_timestamp_source"
        ],
        "generation.event_observation_end_date",
        (
            "refund_generation.observation_window."
            "maximum_timestamp_source"
        ),
    )

    unresolved = _require_mapping(
        observation_window,
        "unresolved_after_observation_end",
        (
            "refund_generation.observation_window."
            "unresolved_after_observation_end"
        ),
    )

    _require_fields(
        unresolved,
        {
            "refund_status",
            "refund_completed_at",
        },
        (
            "refund_generation.observation_window."
            "unresolved_after_observation_end"
        ),
    )

    _require_exact(
        unresolved["refund_status"],
        "requested",
        (
            "refund_generation.observation_window."
            "unresolved_after_observation_end."
            "refund_status"
        ),
    )

    if unresolved["refund_completed_at"] is not None:
        raise ValueError(
            "观察窗口结束时尚未解决的退款"
            "不能设置 refund_completed_at。"
        )

    business_effect = _require_mapping(
        config,
        "business_effect",
        "refund_generation.business_effect",
    )

    _require_fields(
        business_effect,
        {
            "subtract_from_so_statuses",
            "subtract_from_membership_r12_statuses",
            "membership_effective_rule",
        },
        "refund_generation.business_effect",
    )

    for field_name in {
        "subtract_from_so_statuses",
        "subtract_from_membership_r12_statuses",
    }:
        statuses = business_effect[field_name]

        if (
            not isinstance(statuses, list)
            or statuses != ["completed"]
        ):
            raise ValueError(
                "Day65 当前只有 completed 退款"
                "可以扣减业务金额："
                "refund_generation.business_effect."
                f"{field_name} 必须为 ['completed']，"
                f"当前值为：{statuses!r}"
            )

    _require_exact(
        business_effect["membership_effective_rule"],
        "next_evaluation_after_refund_completion",
        (
            "refund_generation.business_effect."
            "membership_effective_rule"
        ),
    )

    membership_policy = _require_mapping(
        manifest,
        "membership_policy",
        "membership_policy",
    )

    valid_spend = _require_mapping(
        membership_policy,
        "valid_spend",
        "membership_policy.valid_spend",
    )

    subtract_successful_refunds = _require_bool(
        valid_spend.get(
            "subtract_successful_refunds"
        ),
        (
            "membership_policy.valid_spend."
            "subtract_successful_refunds"
        ),
    )

    if not subtract_successful_refunds:
        raise ValueError(
            "退款合同要求 membership_policy."
            "valid_spend.subtract_successful_refunds=true。"
        )

    _require_exact(
        valid_spend.get("refund_attribution"),
        "original_paid_date",
        (
            "membership_policy.valid_spend."
            "refund_attribution"
        ),
    )

    fulfillment = _require_mapping(
        manifest,
        "fulfillment_generation",
        "fulfillment_generation",
    )

    fulfillment_eligibility = _require_mapping(
        fulfillment,
        "eligibility",
        "fulfillment_generation.eligibility",
    )

    if not _require_bool(
        fulfillment_eligibility.get(
            "require_successful_payment"
        ),
        (
            "fulfillment_generation.eligibility."
            "require_successful_payment"
        ),
    ):
        raise ValueError(
            "退款依赖的履约合同必须要求支付成功。"
        )

    if not _require_bool(
        fulfillment_eligibility.get(
            "exclude_cancelled_orders"
        ),
        (
            "fulfillment_generation.eligibility."
            "exclude_cancelled_orders"
        ),
    ):
        raise ValueError(
            "退款依赖的履约合同必须排除取消订单。"
        )


def validate_review_generation(
    manifest: dict[str, Any],
) -> None:
    """
    验证 Day65 评价生成合同。

    主要检查：
    1. 评价资格与每个订单明细的评价上限；
    2. 评价概率、时间窗口和评分模型；
    3. 退款状态只能按 reviewed_at 时点生效；
    4. sentiment 必须由 rating 确定性映射；
    5. 文本模板不得调用实时 LLM；
    6. 观察窗口外的评价必须直接省略。
    """
    config = _require_mapping(
        manifest,
        "review_generation",
        "review_generation",
    )

    _require_fields(
        config,
        {
            "eligibility",
            "probability_model",
            "review_delay_days",
            "rating_model",
            "sentiment",
            "text_generation",
            "observation_window",
        },
        "review_generation",
    )

    eligibility = _require_mapping(
        config,
        "eligibility",
        "review_generation.eligibility",
    )

    _require_fields(
        eligibility,
        {
            "require_delivery",
            "exclude_cancelled_orders",
            "maximum_reviews_per_order_item",
        },
        "review_generation.eligibility",
    )

    for field_name in {
        "require_delivery",
        "exclude_cancelled_orders",
    }:
        value = _require_bool(
            eligibility[field_name],
            (
                "review_generation.eligibility."
                f"{field_name}"
            ),
        )

        if not value:
            raise ValueError(
                "Day65 评价生成要求 "
                "review_generation.eligibility."
                f"{field_name}=true。"
            )

    maximum_reviews = _require_positive_int(
        eligibility[
            "maximum_reviews_per_order_item"
        ],
        (
            "review_generation.eligibility."
            "maximum_reviews_per_order_item"
        ),
    )

    if maximum_reviews != 1:
        raise ValueError(
            "Day65 当前每个订单明细最多只生成"
            "一条评价，"
            "maximum_reviews_per_order_item "
            f"必须为 1，当前值为：{maximum_reviews}"
        )

    probability_model = _require_mapping(
        config,
        "probability_model",
        "review_generation.probability_model",
    )

    _require_fields(
        probability_model,
        {
            "strategy",
            "base_item_review_probability",
            "customer_review_propensity_multiplier",
            "product_quality_engagement_multiplier",
            "final_probability",
        },
        "review_generation.probability_model",
    )

    _require_exact(
        probability_model["strategy"],
        "hidden_profile_multiplicative",
        "review_generation.probability_model.strategy",
    )

    base_probability = _require_number(
        probability_model[
            "base_item_review_probability"
        ],
        (
            "review_generation.probability_model."
            "base_item_review_probability"
        ),
        minimum=0,
        maximum=1,
        minimum_inclusive=False,
        maximum_inclusive=False,
    )

    for field_name in {
        "customer_review_propensity_multiplier",
        "product_quality_engagement_multiplier",
    }:
        multiplier = _require_mapping(
            probability_model,
            field_name,
            (
                "review_generation.probability_model."
                f"{field_name}"
            ),
        )

        _require_fields(
            multiplier,
            {"minimum", "maximum"},
            (
                "review_generation.probability_model."
                f"{field_name}"
            ),
        )

        minimum = _require_number(
            multiplier["minimum"],
            (
                "review_generation.probability_model."
                f"{field_name}.minimum"
            ),
            minimum=0,
            minimum_inclusive=False,
        )

        maximum = _require_number(
            multiplier["maximum"],
            (
                "review_generation.probability_model."
                f"{field_name}.maximum"
            ),
            minimum=0,
            minimum_inclusive=False,
        )

        if minimum > maximum:
            raise ValueError(
                "评价概率乘数区间必须满足 "
                "minimum <= maximum："
                f"field={field_name}, "
                f"minimum={minimum}, maximum={maximum}"
            )

    final_probability = _require_mapping(
        probability_model,
        "final_probability",
        (
            "review_generation.probability_model."
            "final_probability"
        ),
    )

    _require_fields(
        final_probability,
        {"minimum", "maximum"},
        (
            "review_generation.probability_model."
            "final_probability"
        ),
    )

    minimum_probability = _require_number(
        final_probability["minimum"],
        (
            "review_generation.probability_model."
            "final_probability.minimum"
        ),
        minimum=0,
        maximum=1,
        minimum_inclusive=False,
    )

    maximum_probability = _require_number(
        final_probability["maximum"],
        (
            "review_generation.probability_model."
            "final_probability.maximum"
        ),
        minimum=0,
        maximum=1,
        maximum_inclusive=False,
    )

    if minimum_probability > maximum_probability:
        raise ValueError(
            "评价最终概率区间必须满足 "
            "minimum <= maximum："
            f"minimum={minimum_probability}, "
            f"maximum={maximum_probability}"
        )

    if not (
        minimum_probability
        <= base_probability
        <= maximum_probability
    ):
        raise ValueError(
            "基础评价概率必须位于最终概率截断区间内："
            f"base={base_probability}, "
            f"minimum={minimum_probability}, "
            f"maximum={maximum_probability}"
        )

    review_delay = _require_mapping(
        config,
        "review_delay_days",
        "review_generation.review_delay_days",
    )

    _require_fields(
        review_delay,
        {
            "minimum",
            "maximum",
            "timestamp_reference",
        },
        "review_generation.review_delay_days",
    )

    minimum_delay = _require_positive_int(
        review_delay["minimum"],
        "review_generation.review_delay_days.minimum",
    )

    maximum_delay = _require_positive_int(
        review_delay["maximum"],
        "review_generation.review_delay_days.maximum",
    )

    if minimum_delay > maximum_delay:
        raise ValueError(
            "评价延迟必须满足 minimum <= maximum："
            f"minimum={minimum_delay}, "
            f"maximum={maximum_delay}"
        )

    _require_exact(
        review_delay["timestamp_reference"],
        "delivered_at",
        (
            "review_generation.review_delay_days."
            "timestamp_reference"
        ),
    )

    rating_model = _require_mapping(
        config,
        "rating_model",
        "review_generation.rating_model",
    )

    _require_fields(
        rating_model,
        {
            "strategy",
            "product_quality_source",
            "customer_rating_bias",
            "random_noise",
            "refund_penalty_by_status",
            "refund_state_cutoff",
            "rounding_strategy",
            "minimum_rating",
            "maximum_rating",
        },
        "review_generation.rating_model",
    )

    _require_exact(
        rating_model["strategy"],
        (
            "hidden_quality_plus_customer_bias_"
            "and_event_signals"
        ),
        "review_generation.rating_model.strategy",
    )

    quality_source = _require_mapping(
        rating_model,
        "product_quality_source",
        (
            "review_generation.rating_model."
            "product_quality_source"
        ),
    )

    _require_fields(
        quality_source,
        {"source", "field"},
        (
            "review_generation.rating_model."
            "product_quality_source"
        ),
    )

    _require_exact(
        quality_source["source"],
        "hidden_product_simulation_profile",
        (
            "review_generation.rating_model."
            "product_quality_source.source"
        ),
    )

    _require_exact(
        quality_source["field"],
        "quality_score",
        (
            "review_generation.rating_model."
            "product_quality_source.field"
        ),
    )

    for field_name in {
        "customer_rating_bias",
        "random_noise",
    }:
        interval = _require_mapping(
            rating_model,
            field_name,
            (
                "review_generation.rating_model."
                f"{field_name}"
            ),
        )

        _require_fields(
            interval,
            {"minimum", "maximum"},
            (
                "review_generation.rating_model."
                f"{field_name}"
            ),
        )

        minimum = _require_number(
            interval["minimum"],
            (
                "review_generation.rating_model."
                f"{field_name}.minimum"
            ),
        )

        maximum = _require_number(
            interval["maximum"],
            (
                "review_generation.rating_model."
                f"{field_name}.maximum"
            ),
        )

        if minimum > maximum:
            raise ValueError(
                "评分偏差区间必须满足 "
                "minimum <= maximum："
                f"field={field_name}, "
                f"minimum={minimum}, maximum={maximum}"
            )

        if not minimum < 0 < maximum:
            raise ValueError(
                "Day65 评分偏差区间必须同时包含"
                "负向与正向变化："
                f"field={field_name}, "
                f"minimum={minimum}, maximum={maximum}"
            )

    refund_penalties = _require_mapping(
        rating_model,
        "refund_penalty_by_status",
        (
            "review_generation.rating_model."
            "refund_penalty_by_status"
        ),
    )

    expected_refund_statuses = {
        "none",
        "requested",
        "completed",
        "rejected",
        "cancelled",
    }

    actual_refund_statuses = set(
        refund_penalties.keys()
    )

    if actual_refund_statuses != expected_refund_statuses:
        raise ValueError(
            "review_generation.rating_model."
            "refund_penalty_by_status 必须覆盖 "
            "none、requested、completed、rejected、"
            "cancelled："
            f"missing={sorted(expected_refund_statuses - actual_refund_statuses)}, "
            f"unknown={sorted(actual_refund_statuses - expected_refund_statuses)}"
        )

    normalized_penalties: dict[str, float] = {}

    for status, raw_penalty in (
        refund_penalties.items()
    ):
        penalty = _require_number(
            raw_penalty,
            (
                "review_generation.rating_model."
                "refund_penalty_by_status."
                f"{status}"
            ),
            maximum=0,
        )

        normalized_penalties[status] = penalty

    if normalized_penalties["none"] != 0:
        raise ValueError(
            "没有退款事件时的评分惩罚必须为 0。"
        )

    if not (
        normalized_penalties["completed"]
        <= normalized_penalties["requested"]
        <= normalized_penalties["rejected"]
        <= normalized_penalties["cancelled"]
        <= normalized_penalties["none"]
    ):
        raise ValueError(
            "退款评分惩罚必须按业务严重程度递减："
            "completed <= requested <= rejected "
            "<= cancelled <= none。"
        )

    _require_exact(
        rating_model["refund_state_cutoff"],
        "reviewed_at",
        (
            "review_generation.rating_model."
            "refund_state_cutoff"
        ),
    )

    _require_exact(
        rating_model["rounding_strategy"],
        "nearest_integer",
        (
            "review_generation.rating_model."
            "rounding_strategy"
        ),
    )

    minimum_rating = _require_positive_int(
        rating_model["minimum_rating"],
        (
            "review_generation.rating_model."
            "minimum_rating"
        ),
    )

    maximum_rating = _require_positive_int(
        rating_model["maximum_rating"],
        (
            "review_generation.rating_model."
            "maximum_rating"
        ),
    )

    if minimum_rating != 1 or maximum_rating != 5:
        raise ValueError(
            "fact_reviews.rating 的 Day65 合同必须为 "
            "1 到 5："
            f"minimum={minimum_rating}, "
            f"maximum={maximum_rating}"
        )

    sentiment = _require_mapping(
        config,
        "sentiment",
        "review_generation.sentiment",
    )

    _require_fields(
        sentiment,
        {"strategy", "rating_mapping"},
        "review_generation.sentiment",
    )

    _require_exact(
        sentiment["strategy"],
        "deterministic_from_rating",
        "review_generation.sentiment.strategy",
    )

    rating_mapping = _require_mapping(
        sentiment,
        "rating_mapping",
        "review_generation.sentiment.rating_mapping",
    )

    expected_rating_mapping = {
        1: "negative",
        2: "negative",
        3: "neutral",
        4: "positive",
        5: "positive",
    }

    if rating_mapping != expected_rating_mapping:
        raise ValueError(
            "review_generation.sentiment.rating_mapping "
            "必须严格遵守 1-2 negative、3 neutral、"
            "4-5 positive："
            f"actual={rating_mapping!r}"
        )

    text_generation = _require_mapping(
        config,
        "text_generation",
        "review_generation.text_generation",
    )

    _require_fields(
        text_generation,
        {
            "strategy",
            "live_llm_allowed",
            "text_presence_probability",
            "templates",
        },
        "review_generation.text_generation",
    )

    _require_exact(
        text_generation["strategy"],
        "deterministic_template_by_sentiment",
        "review_generation.text_generation.strategy",
    )

    live_llm_allowed = _require_bool(
        text_generation["live_llm_allowed"],
        (
            "review_generation.text_generation."
            "live_llm_allowed"
        ),
    )

    if live_llm_allowed:
        raise ValueError(
            "Day65 synthetic review ground truth "
            "不允许调用实时 LLM。"
        )

    _require_number(
        text_generation[
            "text_presence_probability"
        ],
        (
            "review_generation.text_generation."
            "text_presence_probability"
        ),
        minimum=0,
        maximum=1,
        minimum_inclusive=False,
        maximum_inclusive=False,
    )

    templates = _require_mapping(
        text_generation,
        "templates",
        "review_generation.text_generation.templates",
    )

    expected_sentiments = {
        "positive",
        "neutral",
        "negative",
    }

    actual_sentiments = set(templates.keys())

    if actual_sentiments != expected_sentiments:
        raise ValueError(
            "review_generation.text_generation.templates "
            "必须且只能包含 positive、neutral、negative："
            f"missing={sorted(expected_sentiments - actual_sentiments)}, "
            f"unknown={sorted(actual_sentiments - expected_sentiments)}"
        )

    all_templates: set[str] = set()

    for sentiment_name in sorted(expected_sentiments):
        sentiment_templates = templates[
            sentiment_name
        ]

        if (
            not isinstance(sentiment_templates, list)
            or not sentiment_templates
        ):
            raise ValueError(
                "每个 sentiment 必须配置至少一个"
                "评价文本模板："
                f"sentiment={sentiment_name}"
            )

        normalized_templates: set[str] = set()

        for index, template in enumerate(
            sentiment_templates
        ):
            normalized_template = _require_string(
                template,
                (
                    "review_generation.text_generation."
                    f"templates.{sentiment_name}[{index}]"
                ),
            )

            if normalized_template in normalized_templates:
                raise ValueError(
                    "同一 sentiment 下不能配置重复模板："
                    f"sentiment={sentiment_name}, "
                    f"template={normalized_template!r}"
                )

            if normalized_template in all_templates:
                raise ValueError(
                    "评价文本模板不能跨 sentiment 重复："
                    f"template={normalized_template!r}"
                )

            normalized_templates.add(
                normalized_template
            )
            all_templates.add(normalized_template)

    observation_window = _require_mapping(
        config,
        "observation_window",
        "review_generation.observation_window",
    )

    _require_fields(
        observation_window,
        {
            "maximum_timestamp_source",
            "omit_review_after_observation_end",
        },
        "review_generation.observation_window",
    )

    _require_exact(
        observation_window[
            "maximum_timestamp_source"
        ],
        "generation.event_observation_end_date",
        (
            "review_generation.observation_window."
            "maximum_timestamp_source"
        ),
    )

    omit_after_window = _require_bool(
        observation_window[
            "omit_review_after_observation_end"
        ],
        (
            "review_generation.observation_window."
            "omit_review_after_observation_end"
        ),
    )

    if not omit_after_window:
        raise ValueError(
            "观察窗口之外的评价必须直接省略，"
            "omit_review_after_observation_end "
            "必须为 true。"
        )

    fulfillment = _require_mapping(
        manifest,
        "fulfillment_generation",
        "fulfillment_generation",
    )

    fulfillment_eligibility = _require_mapping(
        fulfillment,
        "eligibility",
        "fulfillment_generation.eligibility",
    )

    if not _require_bool(
        fulfillment_eligibility.get(
            "require_successful_payment"
        ),
        (
            "fulfillment_generation.eligibility."
            "require_successful_payment"
        ),
    ):
        raise ValueError(
            "评价依赖的履约合同必须要求支付成功。"
        )

    if not _require_bool(
        fulfillment_eligibility.get(
            "exclude_cancelled_orders"
        ),
        (
            "fulfillment_generation.eligibility."
            "exclude_cancelled_orders"
        ),
    ):
        raise ValueError(
            "评价依赖的履约合同必须排除取消订单。"
        )

    final_status = _require_mapping(
        fulfillment,
        "final_status",
        "fulfillment_generation.final_status",
    )

    _require_exact(
        final_status.get("delivered_event_status"),
        "delivered",
        (
            "fulfillment_generation.final_status."
            "delivered_event_status"
        ),
    )

    refund = _require_mapping(
        manifest,
        "refund_generation",
        "refund_generation",
    )

    resolution = _require_mapping(
        refund,
        "resolution",
        "refund_generation.resolution",
    )

    final_status_distribution = _require_mapping(
        resolution,
        "final_status_distribution",
        (
            "refund_generation.resolution."
            "final_status_distribution"
        ),
    )

    expected_refund_final_statuses = {
        "completed",
        "rejected",
        "cancelled",
    }

    if (
        set(final_status_distribution.keys())
        != expected_refund_final_statuses
    ):
        raise ValueError(
            "评价评分模型依赖的退款终态必须为 "
            "completed、rejected、cancelled。"
        )

    unresolved = _require_mapping(
        _require_mapping(
            refund,
            "observation_window",
            "refund_generation.observation_window",
        ),
        "unresolved_after_observation_end",
        (
            "refund_generation.observation_window."
            "unresolved_after_observation_end"
        ),
    )

    _require_exact(
        unresolved.get("refund_status"),
        "requested",
        (
            "refund_generation.observation_window."
            "unresolved_after_observation_end."
            "refund_status"
        ),
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



def validate_marketing_spend_generation(
    manifest: dict[str, Any],
) -> None:
    """
    验证 Day65 营销费用生成合同。

    主要检查：
    1. fact_marketing_spend 的唯一 Grain；
    2. 营销渠道、活动窗口与行生成策略；
    3. 渠道基础费用及日期乘数；
    4. 大促增量、确定性噪声与金额公式；
    5. 营销投入对订单需求的递减收益响应；
    6. 观察尾窗内不生成新的营销费用。
    """
    config = _require_mapping(
        manifest,
        "marketing_spend_generation",
        "marketing_spend_generation",
    )
    _require_fields(
        config,
        {
            "grain", "eligibility", "row_generation",
            "base_daily_spend_by_channel", "annual_multiplier",
            "weekday_multiplier", "holiday_multiplier",
            "campaign_incremental_multiplier", "deterministic_noise",
            "amount", "demand_response", "order_integration",
            "observation_window",
        },
        "marketing_spend_generation",
    )

    grain = _require_mapping(config, "grain", "marketing_spend_generation.grain")
    _require_fields(grain, {"fields", "require_unique"}, "marketing_spend_generation.grain")
    fields = grain["fields"]
    if fields != ["spend_date", "channel_code", "campaign_code"]:
        raise ValueError(
            "marketing_spend_generation.grain.fields 必须严格等于 "
            "['spend_date', 'channel_code', 'campaign_code']。"
        )
    if not _require_bool(grain["require_unique"], "marketing_spend_generation.grain.require_unique"):
        raise ValueError("营销费用 Grain 必须要求唯一。")

    eligibility = _require_mapping(config, "eligibility", "marketing_spend_generation.eligibility")
    _require_fields(
        eligibility,
        {"require_active_channel", "require_marketing_channel", "require_spend_date_within_campaign_window"},
        "marketing_spend_generation.eligibility",
    )
    for name in eligibility:
        if not _require_bool(eligibility[name], f"marketing_spend_generation.eligibility.{name}"):
            raise ValueError(f"marketing_spend_generation.eligibility.{name} 必须为 true。")

    row_generation = _require_mapping(config, "row_generation", "marketing_spend_generation.row_generation")
    _require_fields(row_generation, {"always_on", "major_promotion", "allow_multiple_campaigns_per_channel_date"}, "marketing_spend_generation.row_generation")
    _require_exact(
        _require_mapping(row_generation, "always_on", "marketing_spend_generation.row_generation.always_on").get("strategy"),
        "every_business_date_x_eligible_channel",
        "marketing_spend_generation.row_generation.always_on.strategy",
    )
    _require_exact(
        _require_mapping(row_generation, "major_promotion", "marketing_spend_generation.row_generation.major_promotion").get("strategy"),
        "active_campaign_date_x_eligible_channel",
        "marketing_spend_generation.row_generation.major_promotion.strategy",
    )
    if not _require_bool(row_generation["allow_multiple_campaigns_per_channel_date"], "marketing_spend_generation.row_generation.allow_multiple_campaigns_per_channel_date"):
        raise ValueError("大促期间必须允许同一渠道日期同时存在 always_on 与 major campaign。")

    eligible_channels = {
        channel["channel_code"].strip()
        for channel in manifest["fixed_dimensions"]["channels"]
        if channel["is_active"] and channel["is_marketing_channel"]
    }
    base_spend = _require_mapping(config, "base_daily_spend_by_channel", "marketing_spend_generation.base_daily_spend_by_channel")
    if set(base_spend) != eligible_channels:
        raise ValueError(
            "base_daily_spend_by_channel 必须完整且仅覆盖启用的营销渠道："
            f"expected={sorted(eligible_channels)}, actual={sorted(base_spend)}"
        )
    for code, value in base_spend.items():
        _require_number(value, f"marketing_spend_generation.base_daily_spend_by_channel.{code}", minimum=0, minimum_inclusive=False)

    generation = manifest["generation"]
    start_year = parse_manifest_date(generation["business_start_date"], "generation.business_start_date").year
    end_year = parse_manifest_date(generation["business_end_date"], "generation.business_end_date").year
    expected_years = set(range(start_year, end_year + 1))
    annual = _require_mapping(config, "annual_multiplier", "marketing_spend_generation.annual_multiplier")
    if set(annual) != expected_years:
        raise ValueError(
            "annual_multiplier 必须完整覆盖业务年份："
            f"expected={sorted(expected_years)}, actual={sorted(annual)}"
        )
    for year, value in annual.items():
        _require_number(value, f"marketing_spend_generation.annual_multiplier.{year}", minimum=0, minimum_inclusive=False)

    weekdays = {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}
    weekday = _require_mapping(config, "weekday_multiplier", "marketing_spend_generation.weekday_multiplier")
    if set(weekday) != weekdays:
        raise ValueError("weekday_multiplier 必须完整覆盖星期一至星期日。")
    for name, value in weekday.items():
        _require_number(value, f"marketing_spend_generation.weekday_multiplier.{name}", minimum=0, minimum_inclusive=False)
    _require_number(config["holiday_multiplier"], "marketing_spend_generation.holiday_multiplier", minimum=0, minimum_inclusive=False)

    major_families = {
        campaign["campaign_family"].strip()
        for campaign in manifest["business_calendar"]["campaigns"]
        if campaign["campaign_type"].strip() == "major_promotion"
    }
    campaign_multipliers = _require_mapping(config, "campaign_incremental_multiplier", "marketing_spend_generation.campaign_incremental_multiplier")
    if set(campaign_multipliers) != major_families:
        raise ValueError(
            "campaign_incremental_multiplier 必须完整覆盖 major promotion family："
            f"expected={sorted(major_families)}, actual={sorted(campaign_multipliers)}"
        )
    for family, value in campaign_multipliers.items():
        _require_number(value, f"marketing_spend_generation.campaign_incremental_multiplier.{family}", minimum=0, minimum_inclusive=False)

    noise = _require_mapping(config, "deterministic_noise", "marketing_spend_generation.deterministic_noise")
    _require_fields(noise, {"enabled", "minimum_multiplier", "maximum_multiplier"}, "marketing_spend_generation.deterministic_noise")
    if not _require_bool(noise["enabled"], "marketing_spend_generation.deterministic_noise.enabled"):
        raise ValueError("营销费用噪声必须启用确定性模式。")
    noise_min = _require_number(noise["minimum_multiplier"], "marketing_spend_generation.deterministic_noise.minimum_multiplier", minimum=0, minimum_inclusive=False)
    noise_max = _require_number(noise["maximum_multiplier"], "marketing_spend_generation.deterministic_noise.maximum_multiplier", minimum=0, minimum_inclusive=False)
    if noise_min > noise_max:
        raise ValueError("deterministic_noise.minimum_multiplier 不能大于 maximum_multiplier。")

    amount = _require_mapping(config, "amount", "marketing_spend_generation.amount")
    _require_fields(amount, {"formula", "always_on_campaign_component", "major_campaign_component_strategy", "decimal_places", "rounding_mode", "minimum_spend_amount"}, "marketing_spend_generation.amount")
    expected_formula = "base_daily_spend x annual_multiplier x weekday_multiplier x holiday_multiplier x campaign_component x deterministic_noise"
    actual_formula = " ".join(_require_string(amount["formula"], "marketing_spend_generation.amount.formula").split())
    if actual_formula != expected_formula:
        raise ValueError(f"marketing_spend_generation.amount.formula 不符合冻结合同：{actual_formula!r}")
    if _require_number(amount["always_on_campaign_component"], "marketing_spend_generation.amount.always_on_campaign_component") != 1.0:
        raise ValueError("always_on_campaign_component 必须为 1.00。")
    _require_exact(amount["major_campaign_component_strategy"], "one_plus_campaign_incremental_multiplier", "marketing_spend_generation.amount.major_campaign_component_strategy")
    if _require_positive_int(amount["decimal_places"], "marketing_spend_generation.amount.decimal_places") != 2:
        raise ValueError("营销费用金额必须保留 2 位小数。")
    _require_exact(amount["rounding_mode"], "ROUND_HALF_UP", "marketing_spend_generation.amount.rounding_mode")
    _require_number(amount["minimum_spend_amount"], "marketing_spend_generation.amount.minimum_spend_amount", minimum=0, minimum_inclusive=False)

    response = _require_mapping(config, "demand_response", "marketing_spend_generation.demand_response")
    _require_fields(response, {"enabled", "strategy", "input", "response_strength_by_channel", "formula", "minimum_demand_multiplier", "maximum_demand_multiplier"}, "marketing_spend_generation.demand_response")
    if not _require_bool(response["enabled"], "marketing_spend_generation.demand_response.enabled"):
        raise ValueError("marketing demand response 必须启用。")
    _require_exact(response["strategy"], "logarithmic_diminishing_returns", "marketing_spend_generation.demand_response.strategy")
    response_input = _require_mapping(response, "input", "marketing_spend_generation.demand_response.input")
    _require_fields(response_input, {"source", "baseline_source"}, "marketing_spend_generation.demand_response.input")
    _require_exact(response_input["source"], "total_daily_channel_spend", "marketing_spend_generation.demand_response.input.source")
    _require_exact(response_input["baseline_source"], "base_daily_spend_by_channel", "marketing_spend_generation.demand_response.input.baseline_source")
    strengths = _require_mapping(response, "response_strength_by_channel", "marketing_spend_generation.demand_response.response_strength_by_channel")
    if set(strengths) != eligible_channels:
        raise ValueError("response_strength_by_channel 必须完整覆盖启用的营销渠道。")
    for code, value in strengths.items():
        _require_number(value, f"marketing_spend_generation.demand_response.response_strength_by_channel.{code}", minimum=0, maximum=1, minimum_inclusive=False)
    expected_response_formula = "1 + response_strength x log1p( maximum( total_daily_channel_spend / base_daily_spend - 1, 0 ) )"
    actual_response_formula = " ".join(_require_string(response["formula"], "marketing_spend_generation.demand_response.formula").split())
    if actual_response_formula != expected_response_formula:
        raise ValueError("demand_response.formula 不符合冻结的对数递减收益合同。")
    demand_min = _require_number(response["minimum_demand_multiplier"], "marketing_spend_generation.demand_response.minimum_demand_multiplier", minimum=1)
    demand_max = _require_number(response["maximum_demand_multiplier"], "marketing_spend_generation.demand_response.maximum_demand_multiplier", minimum=1)
    if demand_min > demand_max:
        raise ValueError("minimum_demand_multiplier 不能大于 maximum_demand_multiplier。")

    integration = _require_mapping(config, "order_integration", "marketing_spend_generation.order_integration")
    _require_fields(integration, {"apply_to", "apply_before_exact_total_reconciliation", "persisted_outside_fact_marketing_spend"}, "marketing_spend_generation.order_integration")
    _require_exact(integration["apply_to"], "daily_channel_order_weight", "marketing_spend_generation.order_integration.apply_to")
    if not _require_bool(integration["apply_before_exact_total_reconciliation"], "marketing_spend_generation.order_integration.apply_before_exact_total_reconciliation"):
        raise ValueError("营销需求响应必须在订单精确总量回收前应用。")
    if _require_bool(integration["persisted_outside_fact_marketing_spend"], "marketing_spend_generation.order_integration.persisted_outside_fact_marketing_spend"):
        raise ValueError("营销需求乘数不能作为额外事实字段持久化。")

    observation = _require_mapping(config, "observation_window", "marketing_spend_generation.observation_window")
    _require_fields(observation, {"maximum_spend_date_source", "generate_spend_in_event_observation_tail"}, "marketing_spend_generation.observation_window")
    _require_exact(observation["maximum_spend_date_source"], "generation.business_end_date", "marketing_spend_generation.observation_window.maximum_spend_date_source")
    if _require_bool(observation["generate_spend_in_event_observation_tail"], "marketing_spend_generation.observation_window.generate_spend_in_event_observation_tail"):
        raise ValueError("2026-01 观察尾窗内不能生成新的营销费用。")


def validate_simulation_profiles(
    manifest: dict[str, Any],
) -> None:
    """
    验证 Day65 隐藏 simulation profile 合同。

    这些参数只用于确定性生成，不写入正式 BI 表。
    """
    config = _require_mapping(
        manifest,
        "simulation_profiles",
        "simulation_profiles",
    )
    _require_fields(
        config,
        {
            "customer",
            "product",
            "demand_context",
        },
        "simulation_profiles",
    )

    customer = _require_mapping(
        config,
        "customer",
        "simulation_profiles.customer",
    )
    _require_fields(
        customer,
        {
            "purchase_propensity",
            "primary_sales_channel",
            "refund_propensity",
            "review_propensity",
            "rating_bias",
        },
        "simulation_profiles.customer",
    )

    purchase_propensity = _require_mapping(
        customer,
        "purchase_propensity",
        (
            "simulation_profiles.customer."
            "purchase_propensity"
        ),
    )
    _require_fields(
        purchase_propensity,
        {
            "strategy",
            "lognormal_mu",
            "lognormal_sigma",
            "minimum_weight",
            "maximum_weight",
        },
        (
            "simulation_profiles.customer."
            "purchase_propensity"
        ),
    )
    _require_exact(
        purchase_propensity["strategy"],
        "lognormal_bounded",
        (
            "simulation_profiles.customer."
            "purchase_propensity.strategy"
        ),
    )
    _require_number(
        purchase_propensity["lognormal_mu"],
        (
            "simulation_profiles.customer."
            "purchase_propensity.lognormal_mu"
        ),
    )
    _require_number(
        purchase_propensity["lognormal_sigma"],
        (
            "simulation_profiles.customer."
            "purchase_propensity.lognormal_sigma"
        ),
        minimum=0,
        minimum_inclusive=False,
    )
    customer_weight_min = _require_number(
        purchase_propensity["minimum_weight"],
        (
            "simulation_profiles.customer."
            "purchase_propensity.minimum_weight"
        ),
        minimum=0,
        minimum_inclusive=False,
    )
    customer_weight_max = _require_number(
        purchase_propensity["maximum_weight"],
        (
            "simulation_profiles.customer."
            "purchase_propensity.maximum_weight"
        ),
        minimum=0,
        minimum_inclusive=False,
    )
    if customer_weight_min >= customer_weight_max:
        raise ValueError(
            "customer purchase propensity "
            "minimum_weight 必须小于 maximum_weight。"
        )

    channel_profile = _require_mapping(
        customer,
        "primary_sales_channel",
        (
            "simulation_profiles.customer."
            "primary_sales_channel"
        ),
    )
    _require_fields(
        channel_profile,
        {
            "strategy",
            "weights",
            "preferred_channel_multiplier",
            "non_preferred_channel_multiplier",
        },
        (
            "simulation_profiles.customer."
            "primary_sales_channel"
        ),
    )
    _require_exact(
        channel_profile["strategy"],
        "weighted_choice",
        (
            "simulation_profiles.customer."
            "primary_sales_channel.strategy"
        ),
    )

    active_sales_channels = {
        channel["channel_code"].strip()
        for channel in manifest[
            "fixed_dimensions"
        ]["channels"]
        if (
            channel["is_active"]
            and channel["is_sales_channel"]
        )
    }
    channel_weights = _require_mapping(
        channel_profile,
        "weights",
        (
            "simulation_profiles.customer."
            "primary_sales_channel.weights"
        ),
    )
    if set(channel_weights) != active_sales_channels:
        raise ValueError(
            "primary_sales_channel.weights 必须完整覆盖"
            "启用的销售渠道："
            f"expected={sorted(active_sales_channels)}, "
            f"actual={sorted(channel_weights)}"
        )
    weight_total = 0.0
    for channel_code, value in channel_weights.items():
        weight_total += _require_number(
            value,
            (
                "simulation_profiles.customer."
                "primary_sales_channel.weights."
                f"{channel_code}"
            ),
            minimum=0,
            maximum=1,
            minimum_inclusive=False,
        )
    if abs(weight_total - 1.0) > 1e-9:
        raise ValueError(
            "primary_sales_channel.weights 合计必须为 1："
            f"actual={weight_total}"
        )

    preferred_multiplier = _require_number(
        channel_profile[
            "preferred_channel_multiplier"
        ],
        (
            "simulation_profiles.customer."
            "primary_sales_channel."
            "preferred_channel_multiplier"
        ),
        minimum=0,
        minimum_inclusive=False,
    )
    non_preferred_multiplier = _require_number(
        channel_profile[
            "non_preferred_channel_multiplier"
        ],
        (
            "simulation_profiles.customer."
            "primary_sales_channel."
            "non_preferred_channel_multiplier"
        ),
        minimum=0,
        minimum_inclusive=False,
    )
    if preferred_multiplier <= non_preferred_multiplier:
        raise ValueError(
            "preferred_channel_multiplier 必须大于"
            " non_preferred_channel_multiplier。"
        )

    refund_propensity = _require_mapping(
        customer,
        "refund_propensity",
        (
            "simulation_profiles.customer."
            "refund_propensity"
        ),
    )
    _require_fields(
        refund_propensity,
        {
            "strategy",
            "minimum_multiplier",
            "maximum_multiplier",
        },
        (
            "simulation_profiles.customer."
            "refund_propensity"
        ),
    )
    _require_exact(
        refund_propensity["strategy"],
        "uniform",
        (
            "simulation_profiles.customer."
            "refund_propensity.strategy"
        ),
    )
    refund_min = _require_number(
        refund_propensity["minimum_multiplier"],
        (
            "simulation_profiles.customer."
            "refund_propensity.minimum_multiplier"
        ),
        minimum=0,
        minimum_inclusive=False,
    )
    refund_max = _require_number(
        refund_propensity["maximum_multiplier"],
        (
            "simulation_profiles.customer."
            "refund_propensity.maximum_multiplier"
        ),
        minimum=0,
        minimum_inclusive=False,
    )
    if refund_min >= refund_max:
        raise ValueError(
            "refund propensity minimum 必须小于 maximum。"
        )

    review_propensity = _require_mapping(
        customer,
        "review_propensity",
        (
            "simulation_profiles.customer."
            "review_propensity"
        ),
    )
    _require_fields(
        review_propensity,
        {
            "strategy",
            "minimum_multiplier",
            "maximum_multiplier",
        },
        (
            "simulation_profiles.customer."
            "review_propensity"
        ),
    )
    _require_exact(
        review_propensity["strategy"],
        "uniform",
        (
            "simulation_profiles.customer."
            "review_propensity.strategy"
        ),
    )
    review_min = _require_number(
        review_propensity["minimum_multiplier"],
        (
            "simulation_profiles.customer."
            "review_propensity.minimum_multiplier"
        ),
        minimum=0,
        minimum_inclusive=False,
    )
    review_max = _require_number(
        review_propensity["maximum_multiplier"],
        (
            "simulation_profiles.customer."
            "review_propensity.maximum_multiplier"
        ),
        minimum=0,
        minimum_inclusive=False,
    )
    if review_min >= review_max:
        raise ValueError(
            "review propensity minimum 必须小于 maximum。"
        )

    rating_bias = _require_mapping(
        customer,
        "rating_bias",
        "simulation_profiles.customer.rating_bias",
    )
    _require_fields(
        rating_bias,
        {
            "strategy",
            "minimum",
            "maximum",
        },
        "simulation_profiles.customer.rating_bias",
    )
    _require_exact(
        rating_bias["strategy"],
        "uniform",
        (
            "simulation_profiles.customer."
            "rating_bias.strategy"
        ),
    )
    rating_bias_min = _require_number(
        rating_bias["minimum"],
        (
            "simulation_profiles.customer."
            "rating_bias.minimum"
        ),
    )
    rating_bias_max = _require_number(
        rating_bias["maximum"],
        (
            "simulation_profiles.customer."
            "rating_bias.maximum"
        ),
    )
    if rating_bias_min >= rating_bias_max:
        raise ValueError(
            "rating_bias.minimum 必须小于 maximum。"
        )

    product = _require_mapping(
        config,
        "product",
        "simulation_profiles.product",
    )
    _require_fields(
        product,
        {
            "demand_weight",
            "quality_score",
            "unit_cost_ratio",
            "quality_mappings",
        },
        "simulation_profiles.product",
    )

    demand_weight = _require_mapping(
        product,
        "demand_weight",
        "simulation_profiles.product.demand_weight",
    )
    _require_fields(
        demand_weight,
        {
            "strategy",
            "lognormal_mu",
            "lognormal_sigma",
            "minimum_weight",
            "maximum_weight",
        },
        "simulation_profiles.product.demand_weight",
    )
    _require_exact(
        demand_weight["strategy"],
        "lognormal_bounded",
        (
            "simulation_profiles.product."
            "demand_weight.strategy"
        ),
    )
    _require_number(
        demand_weight["lognormal_mu"],
        (
            "simulation_profiles.product."
            "demand_weight.lognormal_mu"
        ),
    )
    _require_number(
        demand_weight["lognormal_sigma"],
        (
            "simulation_profiles.product."
            "demand_weight.lognormal_sigma"
        ),
        minimum=0,
        minimum_inclusive=False,
    )
    product_weight_min = _require_number(
        demand_weight["minimum_weight"],
        (
            "simulation_profiles.product."
            "demand_weight.minimum_weight"
        ),
        minimum=0,
        minimum_inclusive=False,
    )
    product_weight_max = _require_number(
        demand_weight["maximum_weight"],
        (
            "simulation_profiles.product."
            "demand_weight.maximum_weight"
        ),
        minimum=0,
        minimum_inclusive=False,
    )
    if product_weight_min >= product_weight_max:
        raise ValueError(
            "product demand minimum_weight "
            "必须小于 maximum_weight。"
        )

    quality_score = _require_mapping(
        product,
        "quality_score",
        "simulation_profiles.product.quality_score",
    )
    _require_fields(
        quality_score,
        {
            "strategy",
            "mean",
            "standard_deviation",
            "minimum",
            "maximum",
        },
        "simulation_profiles.product.quality_score",
    )
    _require_exact(
        quality_score["strategy"],
        "normal_bounded",
        (
            "simulation_profiles.product."
            "quality_score.strategy"
        ),
    )
    quality_mean = _require_number(
        quality_score["mean"],
        (
            "simulation_profiles.product."
            "quality_score.mean"
        ),
        minimum=1,
        maximum=5,
    )
    _require_number(
        quality_score["standard_deviation"],
        (
            "simulation_profiles.product."
            "quality_score.standard_deviation"
        ),
        minimum=0,
        minimum_inclusive=False,
    )
    quality_min = _require_number(
        quality_score["minimum"],
        (
            "simulation_profiles.product."
            "quality_score.minimum"
        ),
        minimum=1,
        maximum=5,
    )
    quality_max = _require_number(
        quality_score["maximum"],
        (
            "simulation_profiles.product."
            "quality_score.maximum"
        ),
        minimum=1,
        maximum=5,
    )
    if not quality_min < quality_mean < quality_max:
        raise ValueError(
            "quality_score 必须满足 "
            "minimum < mean < maximum。"
        )

    unit_cost_ratio = _require_mapping(
        product,
        "unit_cost_ratio",
        (
            "simulation_profiles.product."
            "unit_cost_ratio"
        ),
    )
    _require_fields(
        unit_cost_ratio,
        {
            "strategy",
            "minimum",
            "maximum",
        },
        (
            "simulation_profiles.product."
            "unit_cost_ratio"
        ),
    )
    _require_exact(
        unit_cost_ratio["strategy"],
        "uniform",
        (
            "simulation_profiles.product."
            "unit_cost_ratio.strategy"
        ),
    )
    cost_min = _require_number(
        unit_cost_ratio["minimum"],
        (
            "simulation_profiles.product."
            "unit_cost_ratio.minimum"
        ),
        minimum=0,
        maximum=1,
        minimum_inclusive=False,
        maximum_inclusive=False,
    )
    cost_max = _require_number(
        unit_cost_ratio["maximum"],
        (
            "simulation_profiles.product."
            "unit_cost_ratio.maximum"
        ),
        minimum=0,
        maximum=1,
        minimum_inclusive=False,
        maximum_inclusive=False,
    )
    if cost_min >= cost_max:
        raise ValueError(
            "unit_cost_ratio.minimum "
            "必须小于 maximum。"
        )

    quality_mappings = _require_mapping(
        product,
        "quality_mappings",
        (
            "simulation_profiles.product."
            "quality_mappings"
        ),
    )
    _require_fields(
        quality_mappings,
        {
            "refund_risk",
            "review_engagement",
        },
        (
            "simulation_profiles.product."
            "quality_mappings"
        ),
    )

    refund_risk = _require_mapping(
        quality_mappings,
        "refund_risk",
        (
            "simulation_profiles.product."
            "quality_mappings.refund_risk"
        ),
    )
    _require_fields(
        refund_risk,
        {
            "low_quality_score",
            "high_quality_score",
            "low_quality_multiplier",
            "high_quality_multiplier",
        },
        (
            "simulation_profiles.product."
            "quality_mappings.refund_risk"
        ),
    )
    refund_low_score = _require_number(
        refund_risk["low_quality_score"],
        (
            "simulation_profiles.product."
            "quality_mappings.refund_risk."
            "low_quality_score"
        ),
        minimum=quality_min,
        maximum=quality_max,
    )
    refund_high_score = _require_number(
        refund_risk["high_quality_score"],
        (
            "simulation_profiles.product."
            "quality_mappings.refund_risk."
            "high_quality_score"
        ),
        minimum=quality_min,
        maximum=quality_max,
    )
    refund_low_multiplier = _require_number(
        refund_risk["low_quality_multiplier"],
        (
            "simulation_profiles.product."
            "quality_mappings.refund_risk."
            "low_quality_multiplier"
        ),
        minimum=0,
        minimum_inclusive=False,
    )
    refund_high_multiplier = _require_number(
        refund_risk["high_quality_multiplier"],
        (
            "simulation_profiles.product."
            "quality_mappings.refund_risk."
            "high_quality_multiplier"
        ),
        minimum=0,
        minimum_inclusive=False,
    )
    if refund_low_score >= refund_high_score:
        raise ValueError(
            "refund_risk low_quality_score "
            "必须小于 high_quality_score。"
        )
    if refund_low_multiplier <= refund_high_multiplier:
        raise ValueError(
            "低质量商品的 refund risk multiplier "
            "必须高于高质量商品。"
        )

    review_engagement = _require_mapping(
        quality_mappings,
        "review_engagement",
        (
            "simulation_profiles.product."
            "quality_mappings.review_engagement"
        ),
    )
    _require_fields(
        review_engagement,
        {
            "low_quality_score",
            "high_quality_score",
            "low_quality_multiplier",
            "high_quality_multiplier",
        },
        (
            "simulation_profiles.product."
            "quality_mappings.review_engagement"
        ),
    )
    review_low_score = _require_number(
        review_engagement["low_quality_score"],
        (
            "simulation_profiles.product."
            "quality_mappings.review_engagement."
            "low_quality_score"
        ),
        minimum=quality_min,
        maximum=quality_max,
    )
    review_high_score = _require_number(
        review_engagement["high_quality_score"],
        (
            "simulation_profiles.product."
            "quality_mappings.review_engagement."
            "high_quality_score"
        ),
        minimum=quality_min,
        maximum=quality_max,
    )
    review_low_multiplier = _require_number(
        review_engagement["low_quality_multiplier"],
        (
            "simulation_profiles.product."
            "quality_mappings.review_engagement."
            "low_quality_multiplier"
        ),
        minimum=0,
        minimum_inclusive=False,
    )
    review_high_multiplier = _require_number(
        review_engagement["high_quality_multiplier"],
        (
            "simulation_profiles.product."
            "quality_mappings.review_engagement."
            "high_quality_multiplier"
        ),
        minimum=0,
        minimum_inclusive=False,
    )
    if review_low_score >= review_high_score:
        raise ValueError(
            "review_engagement low_quality_score "
            "必须小于 high_quality_score。"
        )
    if review_low_multiplier >= review_high_multiplier:
        raise ValueError(
            "高质量商品的 review engagement multiplier "
            "必须高于低质量商品。"
        )

    demand_context = _require_mapping(
        config,
        "demand_context",
        "simulation_profiles.demand_context",
    )
    _require_fields(
        demand_context,
        {
            "default_multiplier",
            "seasonal_rules",
            "region_rules",
            "maximum_combined_multiplier",
        },
        "simulation_profiles.demand_context",
    )
    default_multiplier = _require_number(
        demand_context["default_multiplier"],
        (
            "simulation_profiles.demand_context."
            "default_multiplier"
        ),
        minimum=0,
        minimum_inclusive=False,
    )
    maximum_combined_multiplier = _require_number(
        demand_context[
            "maximum_combined_multiplier"
        ],
        (
            "simulation_profiles.demand_context."
            "maximum_combined_multiplier"
        ),
        minimum=default_multiplier,
    )

    valid_categories = {
        item["category"].strip()
        for item in manifest[
            "product_generation"
        ]["subcategories"]
    }
    valid_region_groups = {
        item["region_group"].strip()
        for item in manifest[
            "fixed_dimensions"
        ]["regions"]
    }

    seasonal_rules = demand_context[
        "seasonal_rules"
    ]
    if (
        not isinstance(seasonal_rules, list)
        or not seasonal_rules
    ):
        raise ValueError(
            "simulation_profiles.demand_context."
            "seasonal_rules 必须是非空列表。"
        )

    seasonal_keys: set[
        tuple[str, tuple[int, ...]]
    ] = set()
    for index, rule in enumerate(
        seasonal_rules
    ):
        field_prefix = (
            "simulation_profiles.demand_context."
            f"seasonal_rules[{index}]"
        )
        if not isinstance(rule, dict):
            raise ValueError(
                f"{field_prefix} 必须是字典。"
            )
        _require_fields(
            rule,
            {
                "category",
                "months",
                "multiplier",
            },
            field_prefix,
        )
        category = _require_string(
            rule["category"],
            f"{field_prefix}.category",
        )
        if category not in valid_categories:
            raise ValueError(
                f"{field_prefix}.category 不存在："
                f"{category!r}"
            )
        months = rule["months"]
        if not isinstance(months, list) or not months:
            raise ValueError(
                f"{field_prefix}.months 必须是非空列表。"
            )
        normalized_months: list[int] = []
        for month_index, month in enumerate(
            months
        ):
            normalized_months.append(
                _require_positive_int(
                    month,
                    (
                        f"{field_prefix}.months"
                        f"[{month_index}]"
                    ),
                )
            )
        if any(
            month > 12
            for month in normalized_months
        ):
            raise ValueError(
                f"{field_prefix}.months 必须位于 1-12。"
            )
        if len(normalized_months) != len(
            set(normalized_months)
        ):
            raise ValueError(
                f"{field_prefix}.months 不能重复。"
            )
        rule_multiplier = _require_number(
            rule["multiplier"],
            f"{field_prefix}.multiplier",
            minimum=0,
            minimum_inclusive=False,
        )
        if (
            default_multiplier
            * rule_multiplier
            > maximum_combined_multiplier
        ):
            raise ValueError(
                f"{field_prefix}.multiplier "
                "超过 maximum_combined_multiplier。"
            )
        key = (
            category,
            tuple(sorted(normalized_months)),
        )
        if key in seasonal_keys:
            raise ValueError(
                "seasonal_rules 存在重复规则："
                f"{key}"
            )
        seasonal_keys.add(key)

    region_rules = demand_context[
        "region_rules"
    ]
    if (
        not isinstance(region_rules, list)
        or not region_rules
    ):
        raise ValueError(
            "simulation_profiles.demand_context."
            "region_rules 必须是非空列表。"
        )

    region_keys: set[
        tuple[str, tuple[str, ...]]
    ] = set()
    for index, rule in enumerate(
        region_rules
    ):
        field_prefix = (
            "simulation_profiles.demand_context."
            f"region_rules[{index}]"
        )
        if not isinstance(rule, dict):
            raise ValueError(
                f"{field_prefix} 必须是字典。"
            )
        _require_fields(
            rule,
            {
                "category",
                "region_groups",
                "multiplier",
            },
            field_prefix,
        )
        category = _require_string(
            rule["category"],
            f"{field_prefix}.category",
        )
        if category not in valid_categories:
            raise ValueError(
                f"{field_prefix}.category 不存在："
                f"{category!r}"
            )
        region_groups = rule[
            "region_groups"
        ]
        if (
            not isinstance(region_groups, list)
            or not region_groups
        ):
            raise ValueError(
                f"{field_prefix}.region_groups "
                "必须是非空列表。"
            )
        normalized_groups: list[str] = []
        for group_index, group in enumerate(
            region_groups
        ):
            normalized_group = _require_string(
                group,
                (
                    f"{field_prefix}.region_groups"
                    f"[{group_index}]"
                ),
            )
            if (
                normalized_group
                not in valid_region_groups
            ):
                raise ValueError(
                    f"{field_prefix}.region_groups "
                    "包含未知地区组："
                    f"{normalized_group!r}"
                )
            normalized_groups.append(
                normalized_group
            )
        if len(normalized_groups) != len(
            set(normalized_groups)
        ):
            raise ValueError(
                f"{field_prefix}.region_groups "
                "不能重复。"
            )
        rule_multiplier = _require_number(
            rule["multiplier"],
            f"{field_prefix}.multiplier",
            minimum=0,
            minimum_inclusive=False,
        )
        if (
            default_multiplier
            * rule_multiplier
            > maximum_combined_multiplier
        ):
            raise ValueError(
                f"{field_prefix}.multiplier "
                "超过 maximum_combined_multiplier。"
            )
        key = (
            category,
            tuple(sorted(normalized_groups)),
        )
        if key in region_keys:
            raise ValueError(
                "region_rules 存在重复规则："
                f"{key}"
            )
        region_keys.add(key)

    # 与退款/评价合同交叉校验，避免同一参数在两处漂移。
    refund_probability = manifest[
        "refund_generation"
    ][
        "probability_model"
    ]
    configured_refund_range = refund_probability[
        "customer_refund_propensity_multiplier"
    ]
    if (
        float(configured_refund_range["minimum"])
        != refund_min
        or float(configured_refund_range["maximum"])
        != refund_max
    ):
        raise ValueError(
            "simulation customer refund propensity "
            "必须与 refund_generation 保持一致。"
        )

    configured_quality_risk = refund_probability[
        "quality_risk_multiplier"
    ]
    if (
        float(configured_quality_risk["minimum"])
        != refund_high_multiplier
        or float(configured_quality_risk["maximum"])
        != refund_low_multiplier
    ):
        raise ValueError(
            "quality_mappings.refund_risk "
            "必须与 refund_generation 保持一致。"
        )

    review_probability = manifest[
        "review_generation"
    ][
        "probability_model"
    ]
    configured_review_range = review_probability[
        "customer_review_propensity_multiplier"
    ]
    if (
        float(configured_review_range["minimum"])
        != review_min
        or float(configured_review_range["maximum"])
        != review_max
    ):
        raise ValueError(
            "simulation customer review propensity "
            "必须与 review_generation 保持一致。"
        )

    configured_engagement = review_probability[
        "product_quality_engagement_multiplier"
    ]
    if (
        float(configured_engagement["minimum"])
        != review_low_multiplier
        or float(configured_engagement["maximum"])
        != review_high_multiplier
    ):
        raise ValueError(
            "quality_mappings.review_engagement "
            "必须与 review_generation 保持一致。"
        )

    configured_rating_bias = manifest[
        "review_generation"
    ][
        "rating_model"
    ][
        "customer_rating_bias"
    ]
    if (
        float(configured_rating_bias["minimum"])
        != rating_bias_min
        or float(configured_rating_bias["maximum"])
        != rating_bias_max
    ):
        raise ValueError(
            "simulation customer rating_bias "
            "必须与 review_generation 保持一致。"
        )



def validate_business_pattern_acceptance(
    manifest: dict[str, Any],
) -> None:
    """
    验证 Day66 P01-P09 正式 Acceptance Contract。

    该合同只冻结当前 small Profile 的业务规律宽区间，
    不代表 Dataset V2 已满足 Metadata、Golden Cases、
    Performance 或 AI 主链路回归要求。
    """
    contract = _require_mapping(
        manifest,
        "business_pattern_acceptance",
        "business_pattern_acceptance",
    )

    _require_fields(
        contract,
        {
            "contract_version",
            "scale_profile",
            "status",
            "thresholds_frozen",
            "target_schema",
            "all_patterns_required",
            "candidate_eligibility_after_pass",
            "patterns",
        },
        "business_pattern_acceptance",
    )

    versions = _require_mapping(
        manifest,
        "versions",
        "versions",
    )

    contract_version = _require_string(
        contract["contract_version"],
        "business_pattern_acceptance.contract_version",
    )

    configured_version = _require_string(
        versions.get("acceptance_contract_version"),
        "versions.acceptance_contract_version",
    )

    if contract_version != configured_version:
        raise ValueError(
            "Acceptance Contract 版本不一致："
            f"contract={contract_version!r}, "
            f"versions={configured_version!r}"
        )

    if contract["scale_profile"] != manifest[
        "generation"
    ]["scale_profile"]:
        raise ValueError(
            "business_pattern_acceptance.scale_profile "
            "必须与 generation.scale_profile 一致。"
        )

    _require_exact(
        contract["status"],
        "frozen",
        "business_pattern_acceptance.status",
    )

    if not _require_bool(
        contract["thresholds_frozen"],
        "business_pattern_acceptance.thresholds_frozen",
    ):
        raise ValueError(
            "Day66 正式 Acceptance 要求 thresholds_frozen=true。"
        )

    if contract["target_schema"] != manifest[
        "database"
    ]["target_schema"]:
        raise ValueError(
            "Acceptance target_schema 必须与 database.target_schema 一致。"
        )

    if not _require_bool(
        contract["all_patterns_required"],
        "business_pattern_acceptance.all_patterns_required",
    ):
        raise ValueError(
            "P01-P09 必须全部通过，all_patterns_required 必须为 true。"
        )

    if _require_bool(
        contract["candidate_eligibility_after_pass"],
        (
            "business_pattern_acceptance."
            "candidate_eligibility_after_pass"
        ),
    ):
        raise ValueError(
            "Day66 业务 Pattern 通过后仍不能直接成为 Candidate。"
        )

    acceptance_gate = _require_mapping(
        _require_mapping(
            manifest,
            "acceptance_gates",
            "acceptance_gates",
        ),
        "business_pattern_validation",
        "acceptance_gates.business_pattern_validation",
    )

    if not _require_bool(
        acceptance_gate.get("enabled"),
        "acceptance_gates.business_pattern_validation.enabled",
    ):
        raise ValueError(
            "business_pattern_validation gate 必须启用。"
        )

    _require_exact(
        acceptance_gate.get("validator"),
        "app.db.beauty_bi_v2.acceptance_observer",
        "acceptance_gates.business_pattern_validation.validator",
    )

    expected_patterns = {
        "P01": "customer_purchase_long_tail",
        "P02": "membership_r12_transition",
        "P03": "identity_channel_binding_overlap",
        "P04": "new_customer_scope_difference",
        "P05": "product_sales_long_tail",
        "P06": "season_region_demand",
        "P07": "marketing_diminishing_returns",
        "P08": "promotion_margin_tradeoff",
        "P09": "refund_review_quality_relation",
    }

    pattern_key_mapping = {
        "P01": "P01_customer_purchase_long_tail",
        "P02": "P02_membership_r12_transition",
        "P03": "P03_membership_customer_overlap",
        "P04": "P04_new_customer_scope_difference",
        "P05": "P05_product_sales_long_tail",
        "P06": "P06_season_region_demand",
        "P07": "P07_marketing_diminishing_returns",
        "P08": "P08_promotion_margin_tradeoff",
        "P09": "P09_refund_review_quality",
    }

    patterns = _require_mapping(
        contract,
        "patterns",
        "business_pattern_acceptance.patterns",
    )

    if set(patterns) != set(expected_patterns):
        raise ValueError(
            "business_pattern_acceptance.patterns 必须完整覆盖 P01-P09："
            f"actual={sorted(patterns)}"
        )

    business_patterns = _require_mapping(
        manifest,
        "business_patterns",
        "business_patterns",
    )

    allowed_operators = {
        "between",
        "minimum",
        "maximum",
        "equals",
        "not_equals",
    }

    global_check_ids: set[str] = set()

    for pattern_id, expected_validator in expected_patterns.items():
        pattern_path = (
            "business_pattern_acceptance.patterns."
            f"{pattern_id}"
        )
        pattern = _require_mapping(
            patterns,
            pattern_id,
            pattern_path,
        )
        _require_fields(
            pattern,
            {"validator_name", "checks"},
            pattern_path,
        )

        _require_exact(
            pattern["validator_name"],
            expected_validator,
            f"{pattern_path}.validator_name",
        )

        source_pattern_key = pattern_key_mapping[pattern_id]
        source_pattern = _require_mapping(
            business_patterns,
            source_pattern_key,
            f"business_patterns.{source_pattern_key}",
        )

        if not _require_bool(
            source_pattern.get("enabled"),
            f"business_patterns.{source_pattern_key}.enabled",
        ):
            raise ValueError(
                f"{source_pattern_key} 已配置正式 Gate，不能禁用。"
            )

        checks = pattern["checks"]
        if not isinstance(checks, list) or not checks:
            raise ValueError(
                f"{pattern_path}.checks 必须是非空列表。"
            )

        pattern_metrics: set[str] = set()

        for index, check in enumerate(checks):
            check_path = f"{pattern_path}.checks[{index}]"
            if not isinstance(check, dict):
                raise ValueError(
                    f"{check_path} 必须是字典。"
                )

            _require_fields(
                check,
                {"check_id", "metric", "operator"},
                check_path,
            )

            check_id = _require_string(
                check["check_id"],
                f"{check_path}.check_id",
            )
            metric = _require_string(
                check["metric"],
                f"{check_path}.metric",
            )
            operator = _require_string(
                check["operator"],
                f"{check_path}.operator",
            )

            if check_id in global_check_ids:
                raise ValueError(
                    f"Acceptance check_id 不能重复：{check_id}"
                )
            global_check_ids.add(check_id)

            if metric in pattern_metrics:
                raise ValueError(
                    f"同一 Pattern 不能重复检查 metric：{metric}"
                )
            pattern_metrics.add(metric)

            if operator not in allowed_operators:
                raise ValueError(
                    f"{check_path}.operator 不支持：{operator!r}"
                )

            if operator == "between":
                _require_fields(
                    check,
                    {"minimum", "maximum"},
                    check_path,
                )
                minimum = _require_number(
                    check["minimum"],
                    f"{check_path}.minimum",
                )
                maximum = _require_number(
                    check["maximum"],
                    f"{check_path}.maximum",
                )
                if minimum > maximum:
                    raise ValueError(
                        f"{check_path} 必须满足 minimum <= maximum。"
                    )

            elif operator == "minimum":
                _require_number(
                    check.get("minimum"),
                    f"{check_path}.minimum",
                )

            elif operator == "maximum":
                _require_number(
                    check.get("maximum"),
                    f"{check_path}.maximum",
                )

            else:
                if "expected" not in check:
                    raise ValueError(
                        f"{check_path}.expected 不能为空。"
                    )
                expected = check["expected"]
                if isinstance(expected, (dict, list)):
                    raise ValueError(
                        f"{check_path}.expected 必须是标量。"
                    )


def validate_day66_manifest(
    manifest: dict[str, Any],
) -> None:
    """
    验证 Day66：Day65 生成合同 + P01-P09 正式阈值合同。
    """
    validate_day65_manifest(manifest)
    validate_business_pattern_acceptance(manifest)


def validate_day65_manifest(
    manifest: dict[str, Any],
) -> None:
    """
    验证 Day65 当前已经冻结的 Manifest 合同。

    Day65 继承 Day64 的固定维度与身份合同，
    并增加隐藏画像、会员等级、订单、履约、退款、评价与营销费用生成合同。
    """
    validate_day64_manifest(manifest)
    validate_membership_tier_policy(manifest)
    validate_simulation_profiles(manifest)
    validate_order_generation(manifest)
    validate_fulfillment_generation(manifest)
    validate_refund_generation(manifest)
    validate_review_generation(manifest)
    validate_marketing_spend_generation(manifest)


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


def load_and_validate_day65_manifest(
    manifest_path: Path = MANIFEST_PATH,
) -> dict[str, Any]:
    """
    Day65 Transaction Seed 使用的统一
    Manifest 入口。
    """
    manifest = load_manifest(manifest_path)
    validate_day65_manifest(manifest)
    return manifest



def load_and_validate_day66_manifest(
    manifest_path: Path = MANIFEST_PATH,
) -> dict[str, Any]:
    """
    Day66 Formal Acceptance 使用的统一 Manifest 入口。
    """
    manifest = load_manifest(manifest_path)
    validate_day66_manifest(manifest)
    return manifest


if __name__ == "__main__":
    loaded_manifest = load_and_validate_day66_manifest()
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

    print("Day66 Manifest validation passed.")
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