from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.db.database import engine
from app.db.beauty_bi_v2.manifest_loader import (
    load_and_validate_day66_manifest,
)


TARGET_SCHEMA = "beauty_bi_v2"


@dataclass(frozen=True)
class PatternObservation:
    pattern_id: str
    validator_name: str
    actual_result: dict[str, Any]
    expected_condition: str
    direction_pass: bool
    failure_reason: str | None


def to_json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)

    if isinstance(value, (datetime, date, time)):
        return value.isoformat()

    if isinstance(value, UUID):
        return str(value)

    if isinstance(value, dict):
        return {
            str(key): to_json_value(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple, set)):
        return [
            to_json_value(item)
            for item in value
        ]

    return value


def read_one(
    connection: Connection,
    sql: str,
    parameters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row = connection.execute(
        text(sql),
        parameters or {},
    ).mappings().one()

    return dict(row)


def read_all(
    connection: Connection,
    sql: str,
    parameters: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in connection.execute(
            text(sql),
            parameters or {},
        ).mappings().all()
    ]


def validate_p01_preflight(
    connection: Connection,
) -> dict[str, int]:
    required_tables = (
        "dim_date",
        "dim_customer",
        "dim_membership_account",
        "dim_channel",
        "dim_product",
        "dim_region",
        "dim_campaign",
        "dim_promotion",
        "bridge_customer_membership",
        "fact_membership_channel_binding_history",
        "fact_membership_tier_history",
        "fact_marketing_spend",
        "fact_orders",
        "fact_order_items",
        "fact_refunds",
        "fact_reviews",
    )

    existing_rows = connection.execute(
        text(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = :schema_name
              AND table_name = ANY(:table_names)
            ORDER BY table_name
            """
        ),
        {
            "schema_name": TARGET_SCHEMA,
            "table_names": list(required_tables),
        },
    ).mappings().all()

    existing_tables = {
        row["table_name"]
        for row in existing_rows
    }

    missing_tables = sorted(
        set(required_tables) - existing_tables
    )

    if missing_tables:
        raise RuntimeError(
            "P01 observation 缺少所需表："
            f"{missing_tables}"
        )

    counts: dict[str, int] = {}

    for table_name in required_tables:
        counts[table_name] = connection.execute(
            text(
                f"""
                SELECT COUNT(*)
                FROM {TARGET_SCHEMA}.{table_name}
                """
            )
        ).scalar_one()

    empty_tables = [
        table_name
        for table_name, count in counts.items()
        if count == 0
    ]

    if empty_tables:
        raise RuntimeError(
            "P01 observation 发现空表："
            f"{empty_tables}"
        )

    return counts


def observe_p01(
    connection: Connection,
) -> PatternObservation:
    metrics = read_one(
        connection,
        """
        WITH paid_orders_by_customer AS (
            SELECT
                customer_id,
                COUNT(*) AS paid_order_count,
                SUM(order_paid_amount)
                    AS paid_order_amount
            FROM beauty_bi_v2.fact_orders
            WHERE paid_at IS NOT NULL
            GROUP BY customer_id
        ),
        customer_stats AS (
            SELECT
                customer.customer_id,
                customer.customer_code,
                COALESCE(
                    paid_orders.paid_order_count,
                    0
                ) AS paid_order_count,
                COALESCE(
                    paid_orders.paid_order_amount,
                    0
                ) AS paid_order_amount
            FROM beauty_bi_v2.dim_customer
                AS customer
            LEFT JOIN paid_orders_by_customer
                AS paid_orders
                ON paid_orders.customer_id =
                    customer.customer_id
        ),
        ranked_by_amount AS (
            SELECT
                customer_stats.*,
                ROW_NUMBER() OVER (
                    ORDER BY
                        paid_order_amount DESC,
                        customer_id
                ) AS amount_rank,
                COUNT(*) OVER ()
                    AS customer_count
            FROM customer_stats
        ),
        contribution AS (
            SELECT
                SUM(paid_order_amount)
                    AS total_paid_amount,
                SUM(paid_order_amount) FILTER (
                    WHERE amount_rank <= CEIL(
                        customer_count * 0.01
                    )
                ) AS top_1_percent_paid_amount,
                SUM(paid_order_amount) FILTER (
                    WHERE amount_rank <= CEIL(
                        customer_count * 0.10
                    )
                ) AS top_10_percent_paid_amount
            FROM ranked_by_amount
        )
        SELECT
            COUNT(*) AS total_customers,
            COUNT(*) FILTER (
                WHERE paid_order_count = 0
            ) AS no_purchase_customers,
            COUNT(*) FILTER (
                WHERE paid_order_count = 1
            ) AS one_order_customers,
            COUNT(*) FILTER (
                WHERE paid_order_count = 2
            ) AS two_order_customers,
            COUNT(*) FILTER (
                WHERE paid_order_count
                    BETWEEN 3 AND 5
            ) AS three_to_five_order_customers,
            COUNT(*) FILTER (
                WHERE paid_order_count
                    BETWEEN 6 AND 9
            ) AS six_to_nine_order_customers,
            COUNT(*) FILTER (
                WHERE paid_order_count >= 10
            ) AS ten_plus_order_customers,
            ROUND(
                (
                    COUNT(*) FILTER (
                        WHERE paid_order_count <= 2
                    )
                )::numeric
                / NULLIF(COUNT(*), 0),
                4
            ) AS zero_to_two_order_customer_share,
            ROUND(
                (
                    COUNT(*) FILTER (
                        WHERE paid_order_count >= 10
                    )
                )::numeric
                / NULLIF(COUNT(*), 0),
                4
            ) AS ten_plus_order_customer_share,
            ROUND(
                PERCENTILE_CONT(0.50)
                WITHIN GROUP (
                    ORDER BY paid_order_count
                )::numeric,
                2
            ) AS median_paid_order_count,
            ROUND(
                PERCENTILE_CONT(0.90)
                WITHIN GROUP (
                    ORDER BY paid_order_count
                )::numeric,
                2
            ) AS p90_paid_order_count,
            MAX(paid_order_count)
                AS maximum_paid_order_count,
            ROUND(
                contribution.top_1_percent_paid_amount
                / NULLIF(
                    contribution.total_paid_amount,
                    0
                ),
                4
            ) AS top_1_percent_paid_share,
            ROUND(
                contribution.top_10_percent_paid_amount
                / NULLIF(
                    contribution.total_paid_amount,
                    0
                ),
                4
            ) AS top_10_percent_paid_share
        FROM ranked_by_amount
        CROSS JOIN contribution
        GROUP BY
            contribution.total_paid_amount,
            contribution.top_1_percent_paid_amount,
            contribution.top_10_percent_paid_amount
        """,
    )

    failures: list[str] = []

    if metrics["no_purchase_customers"] <= 0:
        failures.append("没有未购买客户")

    if metrics["one_order_customers"] <= 0:
        failures.append("没有单次购买客户")

    if metrics["ten_plus_order_customers"] <= 0:
        failures.append("没有十次及以上购买客户")

    if (
        metrics["zero_to_two_order_customer_share"]
        is None
        or metrics[
            "ten_plus_order_customer_share"
        ] is None
        or metrics[
            "zero_to_two_order_customer_share"
        ]
        <= metrics[
            "ten_plus_order_customer_share"
        ]
    ):
        failures.append(
            "低频客户没有明显多于高频客户"
        )

    if (
        metrics["top_10_percent_paid_share"]
        is None
        or metrics[
            "top_10_percent_paid_share"
        ] <= Decimal("0.10")
    ):
        failures.append(
            "Top 10% 客户销售贡献未高于均匀基线"
        )

    if (
        metrics["maximum_paid_order_count"]
        is None
        or metrics["p90_paid_order_count"]
        is None
        or Decimal(
            metrics["maximum_paid_order_count"]
        )
        <= metrics["p90_paid_order_count"]
    ):
        failures.append(
            "最大购买频次没有高于 P90"
        )

    return PatternObservation(
        pattern_id="P01",
        validator_name=(
            "customer_purchase_long_tail"
        ),
        actual_result=to_json_value(metrics),
        expected_condition=(
            "存在未购买、单次购买和高频客户；"
            "低频客户明显多于高频客户；"
            "少量客户贡献高于均匀分布；"
            "正式数值阈值已在 Manifest 冻结；本结果仅为方向诊断。"
        ),
        direction_pass=not failures,
        failure_reason=(
            None
            if not failures
            else "; ".join(failures)
        ),
    )



def observe_p02(
    connection: Connection,
) -> PatternObservation:
    """
    P02 Membership R12 Transition。

    观察重点：
    - initial / upgrade / downgrade / unchanged 均存在；
    - 2024、2025 和观察尾窗都能看到合理事件；
    - 当前等级分布不是单一等级；
    - 历史区间只有一个开放区间且无重叠；
    - 订单支付时点等级快照与历史区间一致。
    """
    metrics = read_one(
        connection,
        """
        WITH account_count AS (
            SELECT COUNT(*) AS membership_accounts
            FROM
                beauty_bi_v2.
                dim_membership_account
        ),
        history_summary AS (
            SELECT
                COUNT(*) AS tier_history_rows,
                COUNT(*) FILTER (
                    WHERE change_type = 'initial'
                ) AS initial_count,
                COUNT(*) FILTER (
                    WHERE change_type = 'upgrade'
                ) AS upgrade_count,
                COUNT(*) FILTER (
                    WHERE change_type = 'downgrade'
                ) AS downgrade_count,
                COUNT(DISTINCT membership_account_id)
                    FILTER (
                        WHERE change_type = 'upgrade'
                    ) AS accounts_with_upgrade,
                COUNT(DISTINCT membership_account_id)
                    FILTER (
                        WHERE change_type = 'downgrade'
                    ) AS accounts_with_downgrade,
                COUNT(*) FILTER (
                    WHERE
                        change_type IN (
                            'upgrade',
                            'downgrade'
                        )
                        AND EXTRACT(
                            YEAR FROM evaluated_at
                        ) = 2024
                ) AS transitions_2024,
                COUNT(*) FILTER (
                    WHERE
                        change_type IN (
                            'upgrade',
                            'downgrade'
                        )
                        AND EXTRACT(
                            YEAR FROM evaluated_at
                        ) = 2025
                ) AS transitions_2025,
                COUNT(*) FILTER (
                    WHERE
                        change_type IN (
                            'upgrade',
                            'downgrade'
                        )
                        AND evaluated_at::date
                            BETWEEN
                                DATE '2026-01-01'
                                AND
                                DATE '2026-01-31'
                ) AS transitions_observation_tail
            FROM
                beauty_bi_v2.
                fact_membership_tier_history
        ),
        account_paths AS (
            SELECT
                membership_account_id,
                BOOL_OR(
                    change_type = 'upgrade'
                ) AS has_upgrade,
                BOOL_OR(
                    change_type = 'downgrade'
                ) AS has_downgrade,
                COUNT(*) AS history_count
            FROM
                beauty_bi_v2.
                fact_membership_tier_history
            GROUP BY membership_account_id
        ),
        path_summary AS (
            SELECT
                COUNT(*) FILTER (
                    WHERE history_count = 1
                ) AS unchanged_accounts,
                COUNT(*) FILTER (
                    WHERE
                        has_upgrade
                        AND has_downgrade
                ) AS accounts_with_both_directions
            FROM account_paths
        ),
        current_levels AS (
            SELECT
                COUNT(*) FILTER (
                    WHERE member_level = 'bronze'
                ) AS current_bronze,
                COUNT(*) FILTER (
                    WHERE member_level = 'silver'
                ) AS current_silver,
                COUNT(*) FILTER (
                    WHERE member_level = 'gold'
                ) AS current_gold,
                COUNT(*) FILTER (
                    WHERE member_level = 'platinum'
                ) AS current_platinum
            FROM
                beauty_bi_v2.
                fact_membership_tier_history
            WHERE effective_to_ts IS NULL
        ),
        open_interval_errors AS (
            SELECT COUNT(*) AS error_count
            FROM (
                SELECT membership_account_id
                FROM
                    beauty_bi_v2.
                    fact_membership_tier_history
                GROUP BY membership_account_id
                HAVING
                    COUNT(*) FILTER (
                        WHERE effective_to_ts IS NULL
                    ) <> 1
            ) AS invalid_accounts
        ),
        overlap_errors AS (
            SELECT COUNT(*) AS error_count
            FROM
                beauty_bi_v2.
                fact_membership_tier_history
                    AS left_row
            INNER JOIN
                beauty_bi_v2.
                fact_membership_tier_history
                    AS right_row
                ON
                    right_row.membership_account_id
                    =
                    left_row.membership_account_id
                AND
                    right_row.tier_history_id
                    >
                    left_row.tier_history_id
                AND
                    left_row.effective_from_ts
                    <
                    COALESCE(
                        right_row.effective_to_ts,
                        TIMESTAMP '9999-12-31'
                    )
                AND
                    right_row.effective_from_ts
                    <
                    COALESCE(
                        left_row.effective_to_ts,
                        TIMESTAMP '9999-12-31'
                    )
        ),
        snapshot_summary AS (
            SELECT
                COUNT(*) FILTER (
                    WHERE
                        orders.paid_at IS NOT NULL
                        AND
                        mapping.membership_account_id
                        IS NOT NULL
                ) AS paid_member_orders,
                COUNT(*) FILTER (
                    WHERE
                        orders.paid_at IS NOT NULL
                        AND
                        mapping.membership_account_id
                        IS NULL
                ) AS paid_nonmember_orders,
                COUNT(*) FILTER (
                    WHERE
                        orders.paid_at IS NOT NULL
                        AND (
                            (
                                mapping.membership_account_id
                                IS NULL
                                AND
                                orders.member_level_at_order
                                IS NOT NULL
                            )
                            OR
                            (
                                mapping.membership_account_id
                                IS NOT NULL
                                AND (
                                    history.tier_history_id
                                    IS NULL
                                    OR
                                    orders.member_level_at_order
                                    IS DISTINCT FROM
                                    history.member_level
                                )
                            )
                        )
                ) AS snapshot_error_count
            FROM beauty_bi_v2.fact_orders
                AS orders
            LEFT JOIN
                beauty_bi_v2.
                bridge_customer_membership
                    AS mapping
                ON
                    mapping.customer_id =
                    orders.customer_id
                AND
                    mapping.mapping_status =
                    'active'
                AND
                    mapping.effective_from_ts
                    <= orders.paid_at
                AND
                    (
                        mapping.effective_to_ts
                        IS NULL
                        OR orders.paid_at
                            < mapping.effective_to_ts
                    )
            LEFT JOIN
                beauty_bi_v2.
                fact_membership_tier_history
                    AS history
                ON
                    history.membership_account_id
                    =
                    mapping.membership_account_id
                AND
                    history.effective_from_ts
                    <= orders.paid_at
                AND
                    (
                        history.effective_to_ts
                        IS NULL
                        OR orders.paid_at
                            < history.effective_to_ts
                    )
        )
        SELECT
            account_count.membership_accounts,
            history_summary.tier_history_rows,
            history_summary.initial_count,
            history_summary.upgrade_count,
            history_summary.downgrade_count,
            path_summary.unchanged_accounts,
            history_summary.accounts_with_upgrade,
            history_summary.accounts_with_downgrade,
            path_summary.accounts_with_both_directions,
            history_summary.transitions_2024,
            history_summary.transitions_2025,
            history_summary.transitions_observation_tail,
            current_levels.current_bronze,
            current_levels.current_silver,
            current_levels.current_gold,
            current_levels.current_platinum,
            open_interval_errors.error_count
                AS open_interval_error_count,
            overlap_errors.error_count
                AS overlap_error_count,
            snapshot_summary.paid_member_orders,
            snapshot_summary.paid_nonmember_orders,
            snapshot_summary.snapshot_error_count
        FROM account_count
        CROSS JOIN history_summary
        CROSS JOIN path_summary
        CROSS JOIN current_levels
        CROSS JOIN open_interval_errors
        CROSS JOIN overlap_errors
        CROSS JOIN snapshot_summary
        """,
    )

    transition_rows = read_all(
        connection,
        """
        WITH ordered_history AS (
            SELECT
                membership_account_id,
                member_level,
                change_type,
                effective_from_ts,
                LAG(member_level) OVER (
                    PARTITION BY
                        membership_account_id
                    ORDER BY effective_from_ts
                ) AS previous_level
            FROM
                beauty_bi_v2.
                fact_membership_tier_history
        )
        SELECT
            previous_level,
            member_level AS current_level,
            change_type,
            COUNT(*) AS transition_count
        FROM ordered_history
        WHERE previous_level IS NOT NULL
        GROUP BY
            previous_level,
            member_level,
            change_type
        ORDER BY
            change_type,
            previous_level,
            member_level
        """,
    )

    metrics["transition_matrix"] = (
        transition_rows
    )

    failures: list[str] = []

    if (
        metrics["initial_count"]
        != metrics["membership_accounts"]
    ):
        failures.append(
            "initial 行数不等于会员账户数"
        )

    if metrics["upgrade_count"] <= 0:
        failures.append("缺少升级路径")

    if metrics["downgrade_count"] <= 0:
        failures.append("缺少降级路径")

    if metrics["unchanged_accounts"] <= 0:
        failures.append("缺少等级不变账户")

    if (
        metrics[
            "accounts_with_both_directions"
        ] <= 0
    ):
        failures.append(
            "没有同时经历升级和降级的账户"
        )

    if metrics["transitions_2024"] <= 0:
        failures.append(
            "2024 年没有等级迁移"
        )

    if metrics["transitions_2025"] <= 0:
        failures.append(
            "2025 年没有等级迁移"
        )

    current_level_counts = (
        metrics["current_bronze"],
        metrics["current_silver"],
        metrics["current_gold"],
        metrics["current_platinum"],
    )

    if any(
        value <= 0
        for value in current_level_counts
    ):
        failures.append(
            "当前等级分布未覆盖四个等级"
        )

    if (
        metrics[
            "open_interval_error_count"
        ] != 0
    ):
        failures.append(
            "会员开放等级区间数量错误"
        )

    if metrics["overlap_error_count"] != 0:
        failures.append(
            "会员等级历史存在重叠"
        )

    if metrics["snapshot_error_count"] != 0:
        failures.append(
            "支付时点会员等级快照不一致"
        )

    if metrics["paid_member_orders"] <= 0:
        failures.append(
            "没有会员支付订单"
        )

    if metrics["paid_nonmember_orders"] <= 0:
        failures.append(
            "没有非会员支付订单"
        )

    return PatternObservation(
        pattern_id="P02",
        validator_name=(
            "membership_r12_transition"
        ),
        actual_result=to_json_value(metrics),
        expected_condition=(
            "initial、upgrade、downgrade、"
            "unchanged 和双向迁移均存在；"
            "四个当前等级均有账户；"
            "历史区间无重叠且支付时点"
            "等级快照一致；正式数值阈值"
            "尚未冻结。"
        ),
        direction_pass=not failures,
        failure_reason=(
            None
            if not failures
            else "; ".join(failures)
        ),
    )



def observe_p03(
    connection: Connection,
) -> PatternObservation:
    """
    P03 Identity and Channel-binding Overlap。

    观察三个不同集合：
    1. customer 与 membership account 的身份映射；
    2. membership account 与 channel 的绑定关系；
    3. customer 在 channel 上的实际支付行为。

    这些集合应有交集，但不能完全重合。
    """
    metrics = read_one(
        connection,
        """
        WITH customer_sets AS (
            SELECT
                (
                    SELECT COUNT(*)
                    FROM beauty_bi_v2.dim_customer
                ) AS total_customers,

                (
                    SELECT COUNT(
                        DISTINCT customer_id
                    )
                    FROM
                        beauty_bi_v2.
                        bridge_customer_membership
                ) AS mapped_customers,

                (
                    SELECT COUNT(
                        DISTINCT orders.customer_id
                    )
                    FROM
                        beauty_bi_v2.fact_orders
                            AS orders
                    WHERE orders.paid_at IS NOT NULL
                ) AS paid_customers,

                (
                    SELECT COUNT(*)
                    FROM (
                        SELECT DISTINCT
                            orders.customer_id
                        FROM
                            beauty_bi_v2.fact_orders
                                AS orders
                        WHERE
                            orders.paid_at IS NOT NULL
                    ) AS paid
                    WHERE paid.customer_id NOT IN (
                        SELECT customer_id
                        FROM
                            beauty_bi_v2.
                            bridge_customer_membership
                    )
                ) AS paid_customers_without_mapping,

                (
                    SELECT COUNT(*)
                    FROM (
                        SELECT DISTINCT customer_id
                        FROM
                            beauty_bi_v2.
                            bridge_customer_membership
                    ) AS mapped
                    WHERE mapped.customer_id NOT IN (
                        SELECT DISTINCT customer_id
                        FROM
                            beauty_bi_v2.fact_orders
                        WHERE paid_at IS NOT NULL
                    )
                ) AS mapped_customers_without_purchase
        ),
        membership_sets AS (
            SELECT
                (
                    SELECT COUNT(*)
                    FROM
                        beauty_bi_v2.
                        dim_membership_account
                ) AS total_membership_accounts,

                (
                    SELECT COUNT(
                        DISTINCT membership_account_id
                    )
                    FROM
                        beauty_bi_v2.
                        bridge_customer_membership
                ) AS mapped_membership_accounts,

                (
                    SELECT COUNT(
                        DISTINCT mapping.
                            membership_account_id
                    )
                    FROM
                        beauty_bi_v2.fact_orders
                            AS orders
                    INNER JOIN
                        beauty_bi_v2.
                        bridge_customer_membership
                            AS mapping
                        ON
                            mapping.customer_id =
                            orders.customer_id
                        AND
                            mapping.effective_from_ts
                            <= orders.paid_at
                        AND
                            (
                                mapping.effective_to_ts
                                IS NULL
                                OR orders.paid_at
                                    <
                                    mapping.effective_to_ts
                            )
                    WHERE orders.paid_at IS NOT NULL
                ) AS membership_accounts_with_purchase
        ),
        binding_counts AS (
            SELECT
                account.membership_account_id,
                COUNT(
                    DISTINCT binding.channel_id
                ) AS channel_count
            FROM
                beauty_bi_v2.
                dim_membership_account
                    AS account
            LEFT JOIN
                beauty_bi_v2.
                fact_membership_channel_binding_history
                    AS binding
                ON
                    binding.membership_account_id
                    =
                    account.membership_account_id
            GROUP BY account.membership_account_id
        ),
        binding_summary AS (
            SELECT
                COUNT(*) FILTER (
                    WHERE channel_count = 0
                ) AS members_without_binding,

                COUNT(*) FILTER (
                    WHERE channel_count = 1
                ) AS single_channel_members,

                COUNT(*) FILTER (
                    WHERE channel_count > 1
                ) AS multi_channel_members,

                MAX(channel_count)
                    AS maximum_bound_channels
            FROM binding_counts
        ),
        member_order_binding AS (
            SELECT
                orders.order_id,
                orders.channel_id,
                mapping.membership_account_id,
                CASE
                    WHEN binding.binding_history_id
                        IS NOT NULL
                    THEN TRUE
                    ELSE FALSE
                END AS is_bound_at_payment
            FROM
                beauty_bi_v2.fact_orders
                    AS orders
            INNER JOIN
                beauty_bi_v2.
                bridge_customer_membership
                    AS mapping
                ON
                    mapping.customer_id =
                    orders.customer_id
                AND
                    mapping.effective_from_ts
                    <= orders.paid_at
                AND
                    (
                        mapping.effective_to_ts
                        IS NULL
                        OR orders.paid_at
                            <
                            mapping.effective_to_ts
                    )
            LEFT JOIN
                beauty_bi_v2.
                fact_membership_channel_binding_history
                    AS binding
                ON
                    binding.membership_account_id
                    =
                    mapping.membership_account_id
                AND
                    binding.channel_id =
                    orders.channel_id
                AND
                    binding.effective_from_ts
                    <= orders.paid_at
                AND
                    (
                        binding.effective_to_ts
                        IS NULL
                        OR orders.paid_at
                            <
                            binding.effective_to_ts
                    )
            WHERE orders.paid_at IS NOT NULL
        ),
        member_order_summary AS (
            SELECT
                COUNT(*) AS member_paid_orders,

                COUNT(*) FILTER (
                    WHERE is_bound_at_payment
                ) AS bound_channel_member_orders,

                COUNT(*) FILTER (
                    WHERE NOT is_bound_at_payment
                ) AS unbound_channel_member_orders,

                COUNT(DISTINCT channel_id)
                    FILTER (
                        WHERE is_bound_at_payment
                    )
                    AS channels_with_bound_orders,

                COUNT(DISTINCT channel_id)
                    FILTER (
                        WHERE NOT is_bound_at_payment
                    )
                    AS channels_with_unbound_orders
            FROM member_order_binding
        ),
        mapping_open_errors AS (
            SELECT COUNT(*) AS error_count
            FROM (
                SELECT
                    customer_id
                FROM
                    beauty_bi_v2.
                    bridge_customer_membership
                WHERE effective_to_ts IS NULL
                GROUP BY customer_id
                HAVING COUNT(*) > 1

                UNION ALL

                SELECT
                    membership_account_id
                FROM
                    beauty_bi_v2.
                    bridge_customer_membership
                WHERE effective_to_ts IS NULL
                GROUP BY membership_account_id
                HAVING COUNT(*) > 1
            ) AS invalid_open_mappings
        ),
        mapping_overlap_errors AS (
            SELECT COUNT(*) AS error_count
            FROM
                beauty_bi_v2.
                bridge_customer_membership
                    AS left_row
            INNER JOIN
                beauty_bi_v2.
                bridge_customer_membership
                    AS right_row
                ON
                    right_row.
                        customer_membership_id
                    >
                    left_row.
                        customer_membership_id
                AND (
                    right_row.customer_id
                        =
                        left_row.customer_id
                    OR
                    right_row.
                        membership_account_id
                        =
                        left_row.
                        membership_account_id
                )
                AND
                    left_row.effective_from_ts
                    <
                    COALESCE(
                        right_row.effective_to_ts,
                        TIMESTAMP '9999-12-31'
                    )
                AND
                    right_row.effective_from_ts
                    <
                    COALESCE(
                        left_row.effective_to_ts,
                        TIMESTAMP '9999-12-31'
                    )
        ),
        binding_overlap_errors AS (
            SELECT COUNT(*) AS error_count
            FROM
                beauty_bi_v2.
                fact_membership_channel_binding_history
                    AS left_row
            INNER JOIN
                beauty_bi_v2.
                fact_membership_channel_binding_history
                    AS right_row
                ON
                    right_row.binding_history_id
                    >
                    left_row.binding_history_id
                AND
                    right_row.
                        membership_account_id
                    =
                    left_row.
                        membership_account_id
                AND
                    right_row.channel_id
                    =
                    left_row.channel_id
                AND
                    left_row.effective_from_ts
                    <
                    COALESCE(
                        right_row.effective_to_ts,
                        TIMESTAMP '9999-12-31'
                    )
                AND
                    right_row.effective_from_ts
                    <
                    COALESCE(
                        left_row.effective_to_ts,
                        TIMESTAMP '9999-12-31'
                    )
        )
        SELECT
            customer_sets.total_customers,
            customer_sets.mapped_customers,
            (
                customer_sets.total_customers
                -
                customer_sets.mapped_customers
            ) AS customers_without_mapping,
            customer_sets.paid_customers,
            customer_sets.
                paid_customers_without_mapping,
            customer_sets.
                mapped_customers_without_purchase,

            membership_sets.
                total_membership_accounts,
            membership_sets.
                mapped_membership_accounts,
            (
                membership_sets.
                    total_membership_accounts
                -
                membership_sets.
                    mapped_membership_accounts
            ) AS membership_accounts_without_mapping,
            membership_sets.
                membership_accounts_with_purchase,
            (
                membership_sets.
                    total_membership_accounts
                -
                membership_sets.
                    membership_accounts_with_purchase
            ) AS membership_accounts_without_purchase,

            binding_summary.
                members_without_binding,
            binding_summary.
                single_channel_members,
            binding_summary.
                multi_channel_members,
            binding_summary.
                maximum_bound_channels,

            member_order_summary.
                member_paid_orders,
            member_order_summary.
                bound_channel_member_orders,
            member_order_summary.
                unbound_channel_member_orders,
            member_order_summary.
                channels_with_bound_orders,
            member_order_summary.
                channels_with_unbound_orders,

            ROUND(
                member_order_summary.
                    bound_channel_member_orders
                ::numeric
                /
                NULLIF(
                    member_order_summary.
                        member_paid_orders,
                    0
                ),
                4
            ) AS bound_member_order_share,

            mapping_open_errors.error_count
                AS mapping_open_error_count,
            mapping_overlap_errors.error_count
                AS mapping_overlap_count,
            binding_overlap_errors.error_count
                AS binding_overlap_count

        FROM customer_sets
        CROSS JOIN membership_sets
        CROSS JOIN binding_summary
        CROSS JOIN member_order_summary
        CROSS JOIN mapping_open_errors
        CROSS JOIN mapping_overlap_errors
        CROSS JOIN binding_overlap_errors
        """,
    )

    channel_rows = read_all(
        connection,
        """
        WITH member_orders AS (
            SELECT
                channel.channel_code,
                orders.order_id,
                CASE
                    WHEN binding.binding_history_id
                        IS NOT NULL
                    THEN TRUE
                    ELSE FALSE
                END AS is_bound_at_payment
            FROM
                beauty_bi_v2.fact_orders
                    AS orders
            INNER JOIN
                beauty_bi_v2.dim_channel
                    AS channel
                ON channel.channel_id =
                    orders.channel_id
            INNER JOIN
                beauty_bi_v2.
                bridge_customer_membership
                    AS mapping
                ON
                    mapping.customer_id =
                    orders.customer_id
                AND
                    mapping.effective_from_ts
                    <= orders.paid_at
                AND
                    (
                        mapping.effective_to_ts
                        IS NULL
                        OR orders.paid_at
                            <
                            mapping.effective_to_ts
                    )
            LEFT JOIN
                beauty_bi_v2.
                fact_membership_channel_binding_history
                    AS binding
                ON
                    binding.membership_account_id
                    =
                    mapping.membership_account_id
                AND
                    binding.channel_id =
                    orders.channel_id
                AND
                    binding.effective_from_ts
                    <= orders.paid_at
                AND
                    (
                        binding.effective_to_ts
                        IS NULL
                        OR orders.paid_at
                            <
                            binding.effective_to_ts
                    )
            WHERE orders.paid_at IS NOT NULL
        )
        SELECT
            channel_code,
            COUNT(*) AS member_paid_orders,
            COUNT(*) FILTER (
                WHERE is_bound_at_payment
            ) AS bound_member_orders,
            COUNT(*) FILTER (
                WHERE NOT is_bound_at_payment
            ) AS unbound_member_orders,
            ROUND(
                (
                    COUNT(*) FILTER (
                        WHERE is_bound_at_payment
                    )
                )::numeric
                / NULLIF(COUNT(*), 0),
                4
            ) AS bound_order_share
        FROM member_orders
        GROUP BY channel_code
        ORDER BY channel_code
        """,
    )

    metrics["member_orders_by_channel"] = (
        channel_rows
    )

    failures: list[str] = []

    if metrics["customers_without_mapping"] <= 0:
        failures.append(
            "所有 customer 都被映射为会员"
        )

    if (
        metrics[
            "membership_accounts_without_mapping"
        ] <= 0
    ):
        failures.append(
            "所有会员账户都已映射 customer"
        )

    if (
        metrics[
            "paid_customers_without_mapping"
        ] <= 0
    ):
        failures.append(
            "没有购买但未入会的 customer"
        )

    if (
        metrics[
            "mapped_customers_without_purchase"
        ] <= 0
    ):
        failures.append(
            "没有已映射但未购买的 customer"
        )

    if (
        metrics[
            "membership_accounts_without_purchase"
        ] <= 0
    ):
        failures.append(
            "没有尚未产生购买的会员账户"
        )

    if metrics["members_without_binding"] != 0:
        failures.append(
            "存在没有任何渠道绑定的会员账户"
        )

    if metrics["single_channel_members"] <= 0:
        failures.append(
            "没有单渠道绑定会员"
        )

    if metrics["multi_channel_members"] <= 0:
        failures.append(
            "没有多渠道绑定会员"
        )

    if metrics["bound_channel_member_orders"] <= 0:
        failures.append(
            "没有发生在有效绑定渠道的会员订单"
        )

    if metrics["unbound_channel_member_orders"] <= 0:
        failures.append(
            "没有发生在未绑定渠道的会员订单"
        )

    if (
        metrics["mapping_open_error_count"]
        != 0
    ):
        failures.append(
            "当前 customer-membership 映射不满足双向一对一"
        )

    if metrics["mapping_overlap_count"] != 0:
        failures.append(
            "customer-membership 历史存在重叠"
        )

    if metrics["binding_overlap_count"] != 0:
        failures.append(
            "会员渠道绑定历史存在重叠"
        )

    return PatternObservation(
        pattern_id="P03",
        validator_name=(
            "identity_channel_binding_overlap"
        ),
        actual_result=to_json_value(metrics),
        expected_condition=(
            "customer、membership account、"
            "channel binding 与实际购买集合"
            "有交集但不完全重合；"
            "单渠道与多渠道会员均存在；"
            "绑定与映射历史无重叠；"
            "正式数值阈值已在 Manifest 冻结；本结果仅为方向诊断。"
        ),
        direction_pass=not failures,
        failure_reason=(
            None
            if not failures
            else "; ".join(failures)
        ),
    )



def observe_p04(
    connection: Connection,
) -> PatternObservation:
    """
    P04 New-customer Scope Difference。

    口径：
    - 品牌支付新客：
      customer 的第一张已支付订单；
    - 渠道支付新客：
      customer 在某个 channel 的第一张已支付订单；
    - 渠道贡献品牌支付新客：
      品牌第一张已支付订单发生在哪个 channel。

    因此：
    渠道支付新客 >= 品牌支付新客，
    且两者的差额来自客户后续首次进入其他渠道。
    """
    metrics = read_one(
        connection,
        """
        WITH sequenced_paid_orders AS (
            SELECT
                orders.order_id,
                orders.customer_id,
                orders.channel_id,
                orders.paid_at,

                ROW_NUMBER() OVER (
                    PARTITION BY
                        orders.customer_id
                    ORDER BY
                        orders.paid_at,
                        orders.order_id
                ) AS brand_paid_sequence,

                ROW_NUMBER() OVER (
                    PARTITION BY
                        orders.customer_id,
                        orders.channel_id
                    ORDER BY
                        orders.paid_at,
                        orders.order_id
                ) AS channel_paid_sequence

            FROM beauty_bi_v2.fact_orders
                AS orders
            WHERE orders.paid_at IS NOT NULL
        ),
        customer_channel_counts AS (
            SELECT
                customer_id,
                COUNT(DISTINCT channel_id)
                    AS paid_channel_count
            FROM sequenced_paid_orders
            GROUP BY customer_id
        ),
        scope_totals AS (
            SELECT
                COUNT(*) FILTER (
                    WHERE brand_paid_sequence = 1
                ) AS brand_paid_new_customer_events,

                COUNT(*) FILTER (
                    WHERE channel_paid_sequence = 1
                ) AS channel_paid_new_customer_events,

                COUNT(*) FILTER (
                    WHERE
                        channel_paid_sequence = 1
                        AND
                        brand_paid_sequence = 1
                ) AS channel_contributed_brand_new_events,

                COUNT(*) FILTER (
                    WHERE
                        channel_paid_sequence = 1
                        AND
                        brand_paid_sequence > 1
                ) AS channel_new_not_brand_new_events,

                COUNT(DISTINCT customer_id)
                    AS paid_customers,

                COUNT(DISTINCT channel_id)
                    AS paid_sales_channels
            FROM sequenced_paid_orders
        ),
        channel_path_summary AS (
            SELECT
                COUNT(*) FILTER (
                    WHERE paid_channel_count = 1
                ) AS single_channel_paid_customers,

                COUNT(*) FILTER (
                    WHERE paid_channel_count > 1
                ) AS cross_channel_paid_customers,

                COUNT(*) FILTER (
                    WHERE paid_channel_count >= 3
                ) AS three_plus_channel_customers,

                MAX(paid_channel_count)
                    AS maximum_paid_channels
            FROM customer_channel_counts
        )
        SELECT
            scope_totals.
                brand_paid_new_customer_events,
            scope_totals.
                channel_paid_new_customer_events,
            scope_totals.
                channel_contributed_brand_new_events,
            scope_totals.
                channel_new_not_brand_new_events,
            scope_totals.paid_customers,
            scope_totals.paid_sales_channels,

            channel_path_summary.
                single_channel_paid_customers,
            channel_path_summary.
                cross_channel_paid_customers,
            channel_path_summary.
                three_plus_channel_customers,
            channel_path_summary.
                maximum_paid_channels,

            ROUND(
                scope_totals.
                    channel_paid_new_customer_events
                ::numeric
                /
                NULLIF(
                    scope_totals.
                        brand_paid_new_customer_events,
                    0
                ),
                4
            ) AS channel_to_brand_new_ratio,

            ROUND(
                scope_totals.
                    channel_new_not_brand_new_events
                ::numeric
                /
                NULLIF(
                    scope_totals.
                        channel_paid_new_customer_events,
                    0
                ),
                4
            ) AS channel_new_not_brand_new_share,

            ROUND(
                channel_path_summary.
                    cross_channel_paid_customers
                ::numeric
                /
                NULLIF(
                    scope_totals.paid_customers,
                    0
                ),
                4
            ) AS cross_channel_customer_share

        FROM scope_totals
        CROSS JOIN channel_path_summary
        """,
    )

    channel_rows = read_all(
        connection,
        """
        WITH sequenced_paid_orders AS (
            SELECT
                orders.order_id,
                orders.customer_id,
                orders.channel_id,
                orders.paid_at,

                ROW_NUMBER() OVER (
                    PARTITION BY
                        orders.customer_id
                    ORDER BY
                        orders.paid_at,
                        orders.order_id
                ) AS brand_paid_sequence,

                ROW_NUMBER() OVER (
                    PARTITION BY
                        orders.customer_id,
                        orders.channel_id
                    ORDER BY
                        orders.paid_at,
                        orders.order_id
                ) AS channel_paid_sequence

            FROM beauty_bi_v2.fact_orders
                AS orders
            WHERE orders.paid_at IS NOT NULL
        )
        SELECT
            channel.channel_code,

            COUNT(*) FILTER (
                WHERE
                    sequenced.
                    channel_paid_sequence = 1
            ) AS channel_paid_new_customers,

            COUNT(*) FILTER (
                WHERE
                    sequenced.
                    channel_paid_sequence = 1
                    AND
                    sequenced.
                    brand_paid_sequence = 1
            ) AS contributed_brand_new_customers,

            COUNT(*) FILTER (
                WHERE
                    sequenced.
                    channel_paid_sequence = 1
                    AND
                    sequenced.
                    brand_paid_sequence > 1
            ) AS channel_new_not_brand_new,

            COUNT(*) FILTER (
                WHERE
                    sequenced.
                    channel_paid_sequence = 1
            )
            -
            COUNT(*) FILTER (
                WHERE
                    sequenced.
                    channel_paid_sequence = 1
                    AND
                    sequenced.
                    brand_paid_sequence = 1
            ) AS scope_gap,

            ROUND(
                (
                    COUNT(*) FILTER (
                        WHERE
                            sequenced.
                            brand_paid_sequence = 1
                    )
                )::numeric
                /
                NULLIF(
                    COUNT(*),
                    0
                ),
                4
            ) AS brand_new_order_share,

            ROUND(
                (
                    COUNT(*) FILTER (
                        WHERE
                            sequenced.
                            channel_paid_sequence = 1
                    )
                )::numeric
                /
                NULLIF(
                    COUNT(*),
                    0
                ),
                4
            ) AS channel_new_order_share

        FROM sequenced_paid_orders
            AS sequenced
        INNER JOIN beauty_bi_v2.dim_channel
            AS channel
            ON channel.channel_id =
                sequenced.channel_id

        GROUP BY channel.channel_code
        ORDER BY channel.channel_code
        """,
    )

    metrics["by_channel"] = channel_rows

    failures: list[str] = []

    if (
        metrics[
            "brand_paid_new_customer_events"
        ]
        != metrics["paid_customers"]
    ):
        failures.append(
            "品牌支付新客数量不等于已支付客户数"
        )

    if (
        metrics[
            "channel_contributed_brand_new_events"
        ]
        != metrics[
            "brand_paid_new_customer_events"
        ]
    ):
        failures.append(
            "渠道贡献品牌新客合计不等于品牌新客"
        )

    if (
        metrics[
            "channel_paid_new_customer_events"
        ]
        != (
            metrics[
                "channel_contributed_brand_new_events"
            ]
            + metrics[
                "channel_new_not_brand_new_events"
            ]
        )
    ):
        failures.append(
            "渠道新客分解关系不成立"
        )

    if (
        metrics[
            "channel_paid_new_customer_events"
        ]
        <= metrics[
            "brand_paid_new_customer_events"
        ]
    ):
        failures.append(
            "渠道新客口径没有宽于品牌新客口径"
        )

    if (
        metrics[
            "channel_new_not_brand_new_events"
        ] <= 0
    ):
        failures.append(
            "没有渠道新客但非品牌新客事件"
        )

    if (
        metrics[
            "single_channel_paid_customers"
        ] <= 0
    ):
        failures.append(
            "没有单渠道支付客户"
        )

    if (
        metrics[
            "cross_channel_paid_customers"
        ] <= 0
    ):
        failures.append(
            "没有跨渠道支付客户"
        )

    if (
        metrics[
            "three_plus_channel_customers"
        ] <= 0
    ):
        failures.append(
            "没有三渠道及以上支付客户"
        )

    if (
        metrics["paid_sales_channels"]
        < 2
    ):
        failures.append(
            "可比较的支付渠道不足"
        )

    channel_scope_gaps = [
        row["scope_gap"]
        for row in channel_rows
    ]

    if not channel_scope_gaps:
        failures.append(
            "没有渠道级新客结果"
        )
    elif any(
        value <= 0
        for value in channel_scope_gaps
    ):
        failures.append(
            "至少一个渠道没有形成新客口径差异"
        )

    if any(
        (
            row[
                "channel_paid_new_customers"
            ]
            != (
                row[
                    "contributed_brand_new_customers"
                ]
                + row[
                    "channel_new_not_brand_new"
                ]
            )
        )
        for row in channel_rows
    ):
        failures.append(
            "渠道级新客分解关系不成立"
        )

    return PatternObservation(
        pattern_id="P04",
        validator_name=(
            "new_customer_scope_difference"
        ),
        actual_result=to_json_value(metrics),
        expected_condition=(
            "品牌支付新客、渠道支付新客和"
            "渠道贡献品牌支付新客口径可区分；"
            "渠道新客包含跨渠道扩张产生的"
            "非品牌新客事件；"
            "单渠道与跨渠道客户均存在；"
            "正式数值阈值已在 Manifest 冻结；本结果仅为方向诊断。"
        ),
        direction_pass=not failures,
        failure_reason=(
            None
            if not failures
            else "; ".join(failures)
        ),
    )



def observe_p05(
    connection: Connection,
) -> PatternObservation:
    """
    P05 Product Sales Long Tail。

    Grain：
        一行一个 active product。

    同时观察三种排名：
    - 销量 quantity；
    - 销售额 GMV；
    - 毛利 gross margin。

    三种排名不应完全重合，否则商品价格和成本结构
    对分析没有提供额外信息。
    """
    metrics = read_one(
        connection,
        """
        WITH product_stats AS (
            SELECT
                product.product_id,
                product.sku_code,
                product.category,
                product.subcategory,
                product.is_active,

                COALESCE(
                    SUM(item.quantity) FILTER (
                        WHERE orders.paid_at
                            IS NOT NULL
                    ),
                    0
                ) AS paid_quantity,

                COALESCE(
                    SUM(item.item_paid_amount) FILTER (
                        WHERE orders.paid_at
                            IS NOT NULL
                    ),
                    0
                ) AS gmv,

                COALESCE(
                    SUM(
                        item.item_paid_amount
                        - item.item_cost_amount
                    ) FILTER (
                        WHERE orders.paid_at
                            IS NOT NULL
                    ),
                    0
                ) AS gross_margin

            FROM beauty_bi_v2.dim_product
                AS product

            LEFT JOIN
                beauty_bi_v2.fact_order_items
                    AS item
                ON item.product_id =
                    product.product_id

            LEFT JOIN
                beauty_bi_v2.fact_orders
                    AS orders
                ON orders.order_id =
                    item.order_id

            GROUP BY
                product.product_id,
                product.sku_code,
                product.category,
                product.subcategory,
                product.is_active
        ),
        ranked AS (
            SELECT
                product_stats.*,

                ROW_NUMBER() OVER (
                    ORDER BY
                        paid_quantity DESC,
                        product_id
                ) AS quantity_rank,

                ROW_NUMBER() OVER (
                    ORDER BY
                        gmv DESC,
                        product_id
                ) AS gmv_rank,

                ROW_NUMBER() OVER (
                    ORDER BY
                        gross_margin DESC,
                        product_id
                ) AS margin_rank

            FROM product_stats
            WHERE is_active
        ),
        cutoff AS (
            SELECT
                CEIL(COUNT(*) * 0.10)::integer
                    AS top_10_percent_count
            FROM ranked
        ),
        totals AS (
            SELECT
                SUM(paid_quantity)
                    AS total_paid_quantity,
                SUM(gmv)
                    AS total_gmv,
                SUM(gross_margin)
                    AS total_gross_margin,

                SUM(paid_quantity) FILTER (
                    WHERE
                        quantity_rank
                        <= cutoff.
                            top_10_percent_count
                ) AS top_quantity,

                SUM(gmv) FILTER (
                    WHERE
                        gmv_rank
                        <= cutoff.
                            top_10_percent_count
                ) AS top_gmv,

                SUM(gross_margin) FILTER (
                    WHERE
                        margin_rank
                        <= cutoff.
                            top_10_percent_count
                ) AS top_gross_margin

            FROM ranked
            CROSS JOIN cutoff
            GROUP BY
                cutoff.top_10_percent_count
        ),
        top_sets AS (
            SELECT
                ARRAY(
                    SELECT sku_code
                    FROM ranked
                    ORDER BY
                        quantity_rank
                    LIMIT 10
                ) AS top_quantity_skus,

                ARRAY(
                    SELECT sku_code
                    FROM ranked
                    ORDER BY
                        gmv_rank
                    LIMIT 10
                ) AS top_gmv_skus,

                ARRAY(
                    SELECT sku_code
                    FROM ranked
                    ORDER BY
                        margin_rank
                    LIMIT 10
                ) AS top_margin_skus
        )
        SELECT
            COUNT(*) AS active_products,

            COUNT(*) FILTER (
                WHERE paid_quantity > 0
            ) AS active_products_with_sales,

            COUNT(*) FILTER (
                WHERE paid_quantity = 0
            ) AS active_products_without_sales,

            ROUND(
                (
                    COUNT(*) FILTER (
                        WHERE paid_quantity > 0
                    )
                )::numeric
                / NULLIF(COUNT(*), 0),
                4
            ) AS active_product_sales_coverage,

            MIN(paid_quantity) FILTER (
                WHERE paid_quantity > 0
            ) AS minimum_positive_quantity,

            ROUND(
                PERCENTILE_CONT(0.10)
                WITHIN GROUP (
                    ORDER BY paid_quantity
                )::numeric,
                2
            ) AS p10_paid_quantity,

            ROUND(
                PERCENTILE_CONT(0.50)
                WITHIN GROUP (
                    ORDER BY paid_quantity
                )::numeric,
                2
            ) AS median_paid_quantity,

            ROUND(
                PERCENTILE_CONT(0.90)
                WITHIN GROUP (
                    ORDER BY paid_quantity
                )::numeric,
                2
            ) AS p90_paid_quantity,

            MAX(paid_quantity)
                AS maximum_paid_quantity,

            ROUND(
                MAX(paid_quantity)::numeric
                /
                NULLIF(
                    PERCENTILE_CONT(0.50)
                    WITHIN GROUP (
                        ORDER BY paid_quantity
                    )::numeric,
                    0
                ),
                4
            ) AS maximum_to_median_quantity_ratio,

            ROUND(
                totals.top_quantity::numeric
                /
                NULLIF(
                    totals.total_paid_quantity,
                    0
                ),
                4
            ) AS top_10_percent_quantity_share,

            ROUND(
                totals.top_gmv
                /
                NULLIF(
                    totals.total_gmv,
                    0
                ),
                4
            ) AS top_10_percent_gmv_share,

            ROUND(
                totals.top_gross_margin
                /
                NULLIF(
                    totals.total_gross_margin,
                    0
                ),
                4
            ) AS top_10_percent_margin_share,

            top_sets.top_quantity_skus,
            top_sets.top_gmv_skus,
            top_sets.top_margin_skus

        FROM ranked
        CROSS JOIN totals
        CROSS JOIN top_sets
        GROUP BY
            totals.total_paid_quantity,
            totals.total_gmv,
            totals.total_gross_margin,
            totals.top_quantity,
            totals.top_gmv,
            totals.top_gross_margin,
            top_sets.top_quantity_skus,
            top_sets.top_gmv_skus,
            top_sets.top_margin_skus
        """,
    )

    unsold_product_rows = read_all(
        connection,
        """
        SELECT
            product.sku_code,
            product.product_name,
            product.category,
            product.subcategory,
            product.list_price,
            product.launch_date,
            product.is_active,

            COALESCE(
                SUM(item.quantity),
                0
            ) AS quoted_quantity,

            COALESCE(
                SUM(item.quantity) FILTER (
                    WHERE orders.paid_at IS NOT NULL
                ),
                0
            ) AS paid_quantity,

            COALESCE(
                SUM(item.quantity) FILTER (
                    WHERE orders.paid_at IS NULL
                ),
                0
            ) AS unpaid_or_cancelled_quantity,

            COUNT(DISTINCT item.order_id)
                AS quoted_order_count,

            COUNT(DISTINCT item.order_id)
                FILTER (
                    WHERE orders.paid_at IS NOT NULL
                ) AS paid_order_count,

            MIN(orders.order_created_at)
                AS first_quoted_at,

            MAX(orders.order_created_at)
                AS last_quoted_at

        FROM beauty_bi_v2.dim_product
            AS product

        LEFT JOIN
            beauty_bi_v2.fact_order_items
                AS item
            ON item.product_id =
                product.product_id

        LEFT JOIN
            beauty_bi_v2.fact_orders
                AS orders
            ON orders.order_id =
                item.order_id

        WHERE product.is_active

        GROUP BY
            product.product_id,
            product.sku_code,
            product.product_name,
            product.category,
            product.subcategory,
            product.list_price,
            product.launch_date,
            product.is_active

        HAVING
            COALESCE(
                SUM(item.quantity) FILTER (
                    WHERE orders.paid_at IS NOT NULL
                ),
                0
            ) = 0

        ORDER BY
            product.launch_date,
            product.sku_code
        """,
    )

    category_rows = read_all(
        connection,
        """
        SELECT
            product.category,

            COUNT(DISTINCT product.product_id)
                FILTER (
                    WHERE product.is_active
                ) AS active_products,

            SUM(item.quantity) FILTER (
                WHERE
                    orders.paid_at IS NOT NULL
                    AND product.is_active
            ) AS paid_quantity,

            ROUND(
                SUM(item.item_paid_amount) FILTER (
                    WHERE
                        orders.paid_at IS NOT NULL
                        AND product.is_active
                ),
                2
            ) AS gmv,

            ROUND(
                SUM(
                    item.item_paid_amount
                    - item.item_cost_amount
                ) FILTER (
                    WHERE
                        orders.paid_at IS NOT NULL
                        AND product.is_active
                ),
                2
            ) AS gross_margin

        FROM beauty_bi_v2.dim_product
            AS product

        LEFT JOIN
            beauty_bi_v2.fact_order_items
                AS item
            ON item.product_id =
                product.product_id

        LEFT JOIN
            beauty_bi_v2.fact_orders
                AS orders
            ON orders.order_id =
                item.order_id

        GROUP BY product.category
        ORDER BY product.category
        """,
    )

    quantity_set = set(
        metrics["top_quantity_skus"]
    )

    gmv_set = set(
        metrics["top_gmv_skus"]
    )

    margin_set = set(
        metrics["top_margin_skus"]
    )

    metrics[
        "quantity_gmv_top10_overlap_count"
    ] = len(
        quantity_set & gmv_set
    )

    metrics[
        "gmv_margin_top10_overlap_count"
    ] = len(
        gmv_set & margin_set
    )

    metrics[
        "quantity_margin_top10_overlap_count"
    ] = len(
        quantity_set & margin_set
    )

    metrics[
        "quantity_gmv_top10_exact_order_match"
    ] = (
        metrics["top_quantity_skus"]
        == metrics["top_gmv_skus"]
    )

    metrics[
        "gmv_margin_top10_exact_order_match"
    ] = (
        metrics["top_gmv_skus"]
        == metrics["top_margin_skus"]
    )

    metrics[
        "quantity_gmv_position_difference_count"
    ] = sum(
        quantity_sku != gmv_sku
        for quantity_sku, gmv_sku in zip(
            metrics["top_quantity_skus"],
            metrics["top_gmv_skus"],
        )
    )

    metrics[
        "gmv_margin_position_difference_count"
    ] = sum(
        gmv_sku != margin_sku
        for gmv_sku, margin_sku in zip(
            metrics["top_gmv_skus"],
            metrics["top_margin_skus"],
        )
    )

    metrics["unsold_active_products"] = (
        unsold_product_rows
    )

    metrics["by_category"] = (
        category_rows
    )

    failures: list[str] = []

    if metrics["active_products"] <= 1:
        failures.append(
            "活跃商品数量不足"
        )

    if (
        metrics[
            "active_product_sales_coverage"
        ] is None
        or metrics[
            "active_product_sales_coverage"
        ] < Decimal("0.95")
    ):
        failures.append(
            "活跃商品真实销售覆盖率低于观察方向下限"
        )

    if (
        metrics["minimum_positive_quantity"]
        is None
        or metrics[
            "minimum_positive_quantity"
        ] <= 0
    ):
        failures.append(
            "长尾商品没有正销量"
        )

    if (
        metrics["maximum_paid_quantity"]
        is None
        or metrics["p90_paid_quantity"]
        is None
        or Decimal(
            metrics["maximum_paid_quantity"]
        )
        <= metrics["p90_paid_quantity"]
    ):
        failures.append(
            "最大商品销量没有高于 P90"
        )

    if (
        metrics[
            "maximum_to_median_quantity_ratio"
        ] is None
        or metrics[
            "maximum_to_median_quantity_ratio"
        ] <= Decimal("1.00")
    ):
        failures.append(
            "商品销量分布没有形成头尾差异"
        )

    for field_name, label in (
        (
            "top_10_percent_quantity_share",
            "销量",
        ),
        (
            "top_10_percent_gmv_share",
            "GMV",
        ),
        (
            "top_10_percent_margin_share",
            "毛利",
        ),
    ):
        value = metrics[field_name]

        if (
            value is None
            or value <= Decimal("0.10")
        ):
            failures.append(
                f"Top 10% 商品{label}"
                "贡献未高于均匀基线"
            )

    if metrics[
        "quantity_gmv_top10_exact_order_match"
    ]:
        failures.append(
            "销量 Top10 与 GMV Top10 排名完全一致"
        )

    if metrics[
        "gmv_margin_top10_exact_order_match"
    ]:
        failures.append(
            "GMV Top10 与毛利 Top10 排名完全一致"
        )

    if len(category_rows) < 2:
        failures.append(
            "商品品类不足，无法比较"
        )

    return PatternObservation(
        pattern_id="P05",
        validator_name=(
            "product_sales_long_tail"
        ),
        actual_result=to_json_value(metrics),
        expected_condition=(
            "绝大多数活跃商品有真实销量，"
            "长尾商品保留少量订单；"
            "商品销量、GMV 和毛利形成头部"
            "集中与尾部分布；"
            "销量、GMV、毛利 Top 排名"
            "不完全重合；"
            "正式数值阈值已在 Manifest 冻结；本结果仅为方向诊断。"
        ),
        direction_pass=not failures,
        failure_reason=(
            None
            if not failures
            else "; ".join(failures)
        ),
    )



def observe_p06(
    connection: Connection,
) -> PatternObservation:
    """
    P06 Season and Region Demand。

    为避免大促和地区订单体量干扰：
    - 季节信号比较“品类月度销量占比”；
    - 地区信号比较“品类在地区组合中的销量占比”。

    防晒旺季：
        4、5、6、7、8 月。
    护肤秋冬：
        10、11、12、1、2 月。

    地区方向：
    - 防晒目标地区：
      south / east / southwest；
    - 护肤目标地区：
      north / northeast / northwest。
    """
    metrics = read_one(
        connection,
        """
        WITH paid_item_base AS (
            SELECT
                EXTRACT(
                    MONTH FROM orders.paid_at
                )::integer AS month_number,
                region.region_group,
                product.category,
                item.quantity

            FROM beauty_bi_v2.fact_order_items
                AS item

            INNER JOIN beauty_bi_v2.fact_orders
                AS orders
                ON orders.order_id =
                    item.order_id

            INNER JOIN beauty_bi_v2.dim_product
                AS product
                ON product.product_id =
                    item.product_id

            INNER JOIN beauty_bi_v2.dim_region
                AS region
                ON region.region_id =
                    orders.shipping_region_id

            WHERE orders.paid_at IS NOT NULL
        ),
        monthly_totals AS (
            SELECT
                month_number,
                SUM(quantity) AS total_quantity,
                SUM(quantity) FILTER (
                    WHERE category = '防晒'
                ) AS sunscreen_quantity,
                SUM(quantity) FILTER (
                    WHERE category = '护肤'
                ) AS skincare_quantity
            FROM paid_item_base
            GROUP BY month_number
        ),
        monthly_shares AS (
            SELECT
                month_number,
                total_quantity,
                COALESCE(
                    sunscreen_quantity,
                    0
                ) AS sunscreen_quantity,
                COALESCE(
                    skincare_quantity,
                    0
                ) AS skincare_quantity,

                COALESCE(
                    sunscreen_quantity,
                    0
                )::numeric
                /
                NULLIF(total_quantity, 0)
                    AS sunscreen_share,

                COALESCE(
                    skincare_quantity,
                    0
                )::numeric
                /
                NULLIF(total_quantity, 0)
                    AS skincare_share

            FROM monthly_totals
        ),
        season_summary AS (
            SELECT
                ROUND(
                    AVG(sunscreen_share) FILTER (
                        WHERE month_number
                            IN (4, 5, 6, 7, 8)
                    ),
                    6
                ) AS sunscreen_peak_avg_share,

                ROUND(
                    AVG(sunscreen_share) FILTER (
                        WHERE month_number
                            IN (10, 11, 12, 1, 2)
                    ),
                    6
                ) AS sunscreen_offseason_avg_share,

                ROUND(
                    (
                        AVG(sunscreen_share) FILTER (
                            WHERE month_number
                                IN (4, 5, 6, 7, 8)
                        )
                    )
                    /
                    NULLIF(
                        AVG(sunscreen_share) FILTER (
                            WHERE month_number
                                IN (10, 11, 12, 1, 2)
                        ),
                        0
                    ),
                    4
                ) AS sunscreen_peak_ratio,

                ROUND(
                    AVG(skincare_share) FILTER (
                        WHERE month_number
                            IN (10, 11, 12, 1, 2)
                    ),
                    6
                ) AS skincare_winter_avg_share,

                ROUND(
                    AVG(skincare_share) FILTER (
                        WHERE month_number
                            IN (4, 5, 6, 7, 8)
                    ),
                    6
                ) AS skincare_warm_avg_share,

                ROUND(
                    (
                        AVG(skincare_share) FILTER (
                            WHERE month_number
                                IN (10, 11, 12, 1, 2)
                        )
                    )
                    /
                    NULLIF(
                        AVG(skincare_share) FILTER (
                            WHERE month_number
                                IN (4, 5, 6, 7, 8)
                        ),
                        0
                    ),
                    4
                ) AS skincare_winter_ratio,

                SUM(sunscreen_quantity) FILTER (
                    WHERE month_number
                        IN (4, 5, 6, 7, 8)
                ) AS sunscreen_peak_quantity,

                SUM(sunscreen_quantity) FILTER (
                    WHERE month_number
                        IN (10, 11, 12, 1, 2)
                ) AS sunscreen_offseason_quantity,

                SUM(skincare_quantity) FILTER (
                    WHERE month_number
                        IN (10, 11, 12, 1, 2)
                ) AS skincare_winter_quantity,

                SUM(skincare_quantity) FILTER (
                    WHERE month_number
                        IN (4, 5, 6, 7, 8)
                ) AS skincare_warm_quantity,

                COUNT(*) FILTER (
                    WHERE sunscreen_quantity > 0
                ) AS sunscreen_nonzero_months,

                COUNT(*) FILTER (
                    WHERE skincare_quantity > 0
                ) AS skincare_nonzero_months

            FROM monthly_shares
        ),
        region_summary AS (
            SELECT
                ROUND(
                    (
                        SUM(quantity) FILTER (
                            WHERE
                                category = '防晒'
                                AND region_group IN (
                                    'south',
                                    'east',
                                    'southwest'
                                )
                        )
                    )::numeric
                    /
                    NULLIF(
                        SUM(quantity) FILTER (
                            WHERE region_group IN (
                                'south',
                                'east',
                                'southwest'
                            )
                        ),
                        0
                    ),
                    6
                ) AS sunscreen_target_region_share,

                ROUND(
                    (
                        SUM(quantity) FILTER (
                            WHERE
                                category = '防晒'
                                AND region_group NOT IN (
                                    'south',
                                    'east',
                                    'southwest'
                                )
                        )
                    )::numeric
                    /
                    NULLIF(
                        SUM(quantity) FILTER (
                            WHERE region_group NOT IN (
                                'south',
                                'east',
                                'southwest'
                            )
                        ),
                        0
                    ),
                    6
                ) AS sunscreen_other_region_share,

                ROUND(
                    (
                        (
                            SUM(quantity) FILTER (
                                WHERE
                                    category = '防晒'
                                    AND region_group IN (
                                        'south',
                                        'east',
                                        'southwest'
                                    )
                            )
                        )::numeric
                        /
                        NULLIF(
                            SUM(quantity) FILTER (
                                WHERE region_group IN (
                                    'south',
                                    'east',
                                    'southwest'
                                )
                            ),
                            0
                        )
                    )
                    /
                    NULLIF(
                        (
                            SUM(quantity) FILTER (
                                WHERE
                                    category = '防晒'
                                    AND region_group NOT IN (
                                        'south',
                                        'east',
                                        'southwest'
                                    )
                            )
                        )::numeric
                        /
                        NULLIF(
                            SUM(quantity) FILTER (
                                WHERE region_group NOT IN (
                                    'south',
                                    'east',
                                    'southwest'
                                )
                            ),
                            0
                        ),
                        0
                    ),
                    4
                ) AS sunscreen_region_ratio,

                ROUND(
                    (
                        SUM(quantity) FILTER (
                            WHERE
                                category = '护肤'
                                AND region_group IN (
                                    'north',
                                    'northeast',
                                    'northwest'
                                )
                        )
                    )::numeric
                    /
                    NULLIF(
                        SUM(quantity) FILTER (
                            WHERE region_group IN (
                                'north',
                                'northeast',
                                'northwest'
                            )
                        ),
                        0
                    ),
                    6
                ) AS skincare_target_region_share,

                ROUND(
                    (
                        SUM(quantity) FILTER (
                            WHERE
                                category = '护肤'
                                AND region_group NOT IN (
                                    'north',
                                    'northeast',
                                    'northwest'
                                )
                        )
                    )::numeric
                    /
                    NULLIF(
                        SUM(quantity) FILTER (
                            WHERE region_group NOT IN (
                                'north',
                                'northeast',
                                'northwest'
                            )
                        ),
                        0
                    ),
                    6
                ) AS skincare_other_region_share,

                ROUND(
                    (
                        (
                            SUM(quantity) FILTER (
                                WHERE
                                    category = '护肤'
                                    AND region_group IN (
                                        'north',
                                        'northeast',
                                        'northwest'
                                    )
                            )
                        )::numeric
                        /
                        NULLIF(
                            SUM(quantity) FILTER (
                                WHERE region_group IN (
                                    'north',
                                    'northeast',
                                    'northwest'
                                )
                            ),
                            0
                        )
                    )
                    /
                    NULLIF(
                        (
                            SUM(quantity) FILTER (
                                WHERE
                                    category = '护肤'
                                    AND region_group NOT IN (
                                        'north',
                                        'northeast',
                                        'northwest'
                                    )
                            )
                        )::numeric
                        /
                        NULLIF(
                            SUM(quantity) FILTER (
                                WHERE region_group NOT IN (
                                    'north',
                                    'northeast',
                                    'northwest'
                                )
                            ),
                            0
                        ),
                        0
                    ),
                    4
                ) AS skincare_region_ratio

            FROM paid_item_base
        )
        SELECT
            season_summary.*,
            region_summary.*
        FROM season_summary
        CROSS JOIN region_summary
        """,
    )

    monthly_rows = read_all(
        connection,
        """
        WITH paid_item_base AS (
            SELECT
                EXTRACT(
                    MONTH FROM orders.paid_at
                )::integer AS month_number,
                product.category,
                item.quantity
            FROM beauty_bi_v2.fact_order_items
                AS item
            INNER JOIN beauty_bi_v2.fact_orders
                AS orders
                ON orders.order_id =
                    item.order_id
            INNER JOIN beauty_bi_v2.dim_product
                AS product
                ON product.product_id =
                    item.product_id
            WHERE orders.paid_at IS NOT NULL
        ),
        monthly_totals AS (
            SELECT
                month_number,
                SUM(quantity) AS total_quantity,
                SUM(quantity) FILTER (
                    WHERE category = '防晒'
                ) AS sunscreen_quantity,
                SUM(quantity) FILTER (
                    WHERE category = '护肤'
                ) AS skincare_quantity
            FROM paid_item_base
            GROUP BY month_number
        )
        SELECT
            month_number,
            total_quantity,
            COALESCE(
                sunscreen_quantity,
                0
            ) AS sunscreen_quantity,
            COALESCE(
                skincare_quantity,
                0
            ) AS skincare_quantity,

            ROUND(
                COALESCE(
                    sunscreen_quantity,
                    0
                )::numeric
                /
                NULLIF(total_quantity, 0),
                6
            ) AS sunscreen_share,

            ROUND(
                COALESCE(
                    skincare_quantity,
                    0
                )::numeric
                /
                NULLIF(total_quantity, 0),
                6
            ) AS skincare_share

        FROM monthly_totals
        ORDER BY month_number
        """,
    )

    region_rows = read_all(
        connection,
        """
        WITH paid_item_base AS (
            SELECT
                region.region_group,
                product.category,
                item.quantity
            FROM beauty_bi_v2.fact_order_items
                AS item
            INNER JOIN beauty_bi_v2.fact_orders
                AS orders
                ON orders.order_id =
                    item.order_id
            INNER JOIN beauty_bi_v2.dim_product
                AS product
                ON product.product_id =
                    item.product_id
            INNER JOIN beauty_bi_v2.dim_region
                AS region
                ON region.region_id =
                    orders.shipping_region_id
            WHERE orders.paid_at IS NOT NULL
        )
        SELECT
            region_group,
            SUM(quantity) AS total_quantity,
            SUM(quantity) FILTER (
                WHERE category = '防晒'
            ) AS sunscreen_quantity,
            SUM(quantity) FILTER (
                WHERE category = '护肤'
            ) AS skincare_quantity,

            ROUND(
                (
                    SUM(quantity) FILTER (
                        WHERE category = '防晒'
                    )
                )::numeric
                /
                NULLIF(SUM(quantity), 0),
                6
            ) AS sunscreen_share,

            ROUND(
                (
                    SUM(quantity) FILTER (
                        WHERE category = '护肤'
                    )
                )::numeric
                /
                NULLIF(SUM(quantity), 0),
                6
            ) AS skincare_share

        FROM paid_item_base
        GROUP BY region_group
        ORDER BY region_group
        """,
    )

    metrics["by_month"] = monthly_rows
    metrics["by_region_group"] = region_rows

    failures: list[str] = []

    if (
        metrics["sunscreen_peak_ratio"]
        is None
        or metrics["sunscreen_peak_ratio"]
        <= Decimal("1.00")
    ):
        failures.append(
            "防晒春夏占比没有高于秋冬占比"
        )

    if (
        metrics["skincare_winter_ratio"]
        is None
        or metrics["skincare_winter_ratio"]
        <= Decimal("1.00")
    ):
        failures.append(
            "护肤秋冬占比没有高于暖季占比"
        )

    if (
        metrics["sunscreen_region_ratio"]
        is None
        or metrics["sunscreen_region_ratio"]
        <= Decimal("1.00")
    ):
        failures.append(
            "防晒目标地区偏好未体现"
        )

    if (
        metrics["skincare_region_ratio"]
        is None
        or metrics["skincare_region_ratio"]
        <= Decimal("1.00")
    ):
        failures.append(
            "护肤目标地区偏好未体现"
        )

    if (
        metrics["sunscreen_offseason_quantity"]
        is None
        or metrics["sunscreen_offseason_quantity"]
        <= 0
    ):
        failures.append(
            "防晒秋冬销量为空或为零"
        )

    if (
        metrics["skincare_warm_quantity"]
        is None
        or metrics["skincare_warm_quantity"]
        <= 0
    ):
        failures.append(
            "护肤暖季销量为空或为零"
        )

    if metrics["sunscreen_nonzero_months"] < 12:
        failures.append(
            "防晒没有覆盖全部月份"
        )

    if metrics["skincare_nonzero_months"] < 12:
        failures.append(
            "护肤没有覆盖全部月份"
        )

    if len(region_rows) < 2:
        failures.append(
            "地区组数量不足，无法比较"
        )

    if any(
        row["sunscreen_quantity"] in (None, 0)
        or row["skincare_quantity"] in (None, 0)
        for row in region_rows
    ):
        failures.append(
            "至少一个地区组出现机械式品类零销量"
        )

    return PatternObservation(
        pattern_id="P06",
        validator_name=(
            "season_region_demand"
        ),
        actual_result=to_json_value(metrics),
        expected_condition=(
            "防晒春夏销量占比高于秋冬，"
            "护肤秋冬销量占比高于暖季；"
            "防晒在 south/east/southwest "
            "更强，护肤在 north/northeast/"
            "northwest 更强；"
            "两个品类在全部月份和地区组"
            "均保留真实销量；"
            "正式数值阈值已在 Manifest 冻结；本结果仅为方向诊断。"
        ),
        direction_pass=not failures,
        failure_reason=(
            None
            if not failures
            else "; ".join(failures)
        ),
    )



def observe_p07(
    connection: Connection,
) -> PatternObservation:
    """
    P07 Marketing Diminishing Returns。

    Grain：
        一行一个 direct-response channel × spend_date。

    新客主口径：
        渠道支付新客，即 customer 在该 channel
        的第一张成功支付订单。

    同时输出渠道贡献品牌支付新客作为诊断，
    但不将两个新客口径混为同一指标。

    观察原则：
    - 每个直接响应渠道都应表现为：
      投放更高时订单更多；
    - 多数渠道应表现出订单和渠道新客的
      次线性响应；
    - 允许单个渠道在 small Profile 中有
      轻微随机越界，但效率保留比不得明显
      高于 1；
    - GMV / spend 应体现 ROI 变化；
    - 各渠道响应曲线不能完全相同。
    """
    channel_rows = read_all(
        connection,
        """
        WITH marketing_channels AS (
            SELECT DISTINCT channel_id
            FROM
                beauty_bi_v2.
                fact_marketing_spend
        ),
        sales_channels AS (
            SELECT DISTINCT channel_id
            FROM beauty_bi_v2.fact_orders
            WHERE paid_at IS NOT NULL
        ),
        direct_response_channels AS (
            SELECT channel_id
            FROM marketing_channels

            INTERSECT

            SELECT channel_id
            FROM sales_channels
        ),
        spend_by_day AS (
            SELECT
                spend.spend_date,
                spend.channel_id,
                SUM(spend.spend_amount)
                    AS marketing_spend
            FROM
                beauty_bi_v2.
                fact_marketing_spend
                    AS spend
            INNER JOIN direct_response_channels
                AS direct_channel
                ON direct_channel.channel_id =
                    spend.channel_id
            GROUP BY
                spend.spend_date,
                spend.channel_id
        ),
        sequenced_paid_orders AS (
            SELECT
                orders.order_id,
                orders.customer_id,
                orders.channel_id,
                orders.paid_at,
                orders.order_paid_amount,

                ROW_NUMBER() OVER (
                    PARTITION BY
                        orders.customer_id,
                        orders.channel_id
                    ORDER BY
                        orders.paid_at,
                        orders.order_id
                ) AS channel_paid_sequence,

                ROW_NUMBER() OVER (
                    PARTITION BY
                        orders.customer_id
                    ORDER BY
                        orders.paid_at,
                        orders.order_id
                ) AS brand_paid_sequence

            FROM beauty_bi_v2.fact_orders
                AS orders
            WHERE orders.paid_at IS NOT NULL
        ),
        orders_by_day AS (
            SELECT
                sequenced.paid_at::date
                    AS paid_date,
                sequenced.channel_id,

                COUNT(*) AS paid_orders,

                SUM(
                    sequenced.order_paid_amount
                ) AS gmv,

                COUNT(*) FILTER (
                    WHERE
                        sequenced.
                        channel_paid_sequence = 1
                ) AS channel_paid_new_customers,

                COUNT(*) FILTER (
                    WHERE
                        sequenced.
                        brand_paid_sequence = 1
                ) AS contributed_brand_new_customers

            FROM sequenced_paid_orders
                AS sequenced

            GROUP BY
                sequenced.paid_at::date,
                sequenced.channel_id
        ),
        daily_metrics AS (
            SELECT
                channel.channel_code,
                spend.spend_date,
                spend.marketing_spend,

                COALESCE(
                    orders.paid_orders,
                    0
                ) AS paid_orders,

                COALESCE(
                    orders.gmv,
                    0
                ) AS gmv,

                COALESCE(
                    orders.
                        channel_paid_new_customers,
                    0
                ) AS channel_paid_new_customers,

                COALESCE(
                    orders.
                        contributed_brand_new_customers,
                    0
                ) AS contributed_brand_new_customers

            FROM spend_by_day AS spend

            INNER JOIN beauty_bi_v2.dim_channel
                AS channel
                ON channel.channel_id =
                    spend.channel_id

            LEFT JOIN orders_by_day AS orders
                ON
                    orders.channel_id =
                    spend.channel_id
                AND
                    orders.paid_date =
                    spend.spend_date
        ),
        ranked_days AS (
            SELECT
                daily_metrics.*,

                NTILE(4) OVER (
                    PARTITION BY channel_code
                    ORDER BY
                        marketing_spend,
                        spend_date
                ) AS spend_quartile

            FROM daily_metrics
        ),
        channel_metrics_base AS (
            SELECT
                channel_code,
                COUNT(*) AS observation_days,

                ROUND(
                    CORR(
                        marketing_spend
                            ::double precision,
                        paid_orders
                            ::double precision
                    )::numeric,
                    4
                ) AS spend_order_correlation,

                ROUND(
                    CORR(
                        marketing_spend
                            ::double precision,
                        channel_paid_new_customers
                            ::double precision
                    )::numeric,
                    4
                ) AS spend_channel_new_correlation,

                ROUND(
                    CORR(
                        marketing_spend
                            ::double precision,
                        contributed_brand_new_customers
                            ::double precision
                    )::numeric,
                    4
                ) AS spend_brand_new_correlation,

                ROUND(
                    AVG(marketing_spend) FILTER (
                        WHERE spend_quartile = 1
                    ),
                    2
                ) AS low_spend_avg,

                ROUND(
                    AVG(marketing_spend) FILTER (
                        WHERE spend_quartile = 4
                    ),
                    2
                ) AS high_spend_avg,

                ROUND(
                    AVG(paid_orders) FILTER (
                        WHERE spend_quartile = 1
                    ),
                    4
                ) AS low_spend_avg_orders,

                ROUND(
                    AVG(paid_orders) FILTER (
                        WHERE spend_quartile = 4
                    ),
                    4
                ) AS high_spend_avg_orders,

                ROUND(
                    AVG(
                        channel_paid_new_customers
                    ) FILTER (
                        WHERE spend_quartile = 1
                    ),
                    4
                ) AS low_spend_avg_channel_new,

                ROUND(
                    AVG(
                        channel_paid_new_customers
                    ) FILTER (
                        WHERE spend_quartile = 4
                    ),
                    4
                ) AS high_spend_avg_channel_new,

                ROUND(
                    AVG(
                        contributed_brand_new_customers
                    ) FILTER (
                        WHERE spend_quartile = 1
                    ),
                    4
                ) AS low_spend_avg_brand_new,

                ROUND(
                    AVG(
                        contributed_brand_new_customers
                    ) FILTER (
                        WHERE spend_quartile = 4
                    ),
                    4
                ) AS high_spend_avg_brand_new,

                ROUND(
                    (
                        SUM(paid_orders) FILTER (
                            WHERE spend_quartile = 1
                        )
                    )::numeric
                    * 1000
                    /
                    NULLIF(
                        SUM(marketing_spend)
                            FILTER (
                                WHERE spend_quartile = 1
                            ),
                        0
                    ),
                    4
                ) AS low_spend_orders_per_1000,

                ROUND(
                    (
                        SUM(paid_orders) FILTER (
                            WHERE spend_quartile = 4
                        )
                    )::numeric
                    * 1000
                    /
                    NULLIF(
                        SUM(marketing_spend)
                            FILTER (
                                WHERE spend_quartile = 4
                            ),
                        0
                    ),
                    4
                ) AS high_spend_orders_per_1000,

                ROUND(
                    (
                        SUM(
                            channel_paid_new_customers
                        ) FILTER (
                            WHERE spend_quartile = 1
                        )
                    )::numeric
                    * 1000
                    /
                    NULLIF(
                        SUM(marketing_spend)
                            FILTER (
                                WHERE spend_quartile = 1
                            ),
                        0
                    ),
                    4
                ) AS low_spend_channel_new_per_1000,

                ROUND(
                    (
                        SUM(
                            channel_paid_new_customers
                        ) FILTER (
                            WHERE spend_quartile = 4
                        )
                    )::numeric
                    * 1000
                    /
                    NULLIF(
                        SUM(marketing_spend)
                            FILTER (
                                WHERE spend_quartile = 4
                            ),
                        0
                    ),
                    4
                ) AS high_spend_channel_new_per_1000,

                ROUND(
                    (
                        SUM(
                            contributed_brand_new_customers
                        ) FILTER (
                            WHERE spend_quartile = 1
                        )
                    )::numeric
                    * 1000
                    /
                    NULLIF(
                        SUM(marketing_spend)
                            FILTER (
                                WHERE spend_quartile = 1
                            ),
                        0
                    ),
                    4
                ) AS low_spend_brand_new_per_1000,

                ROUND(
                    (
                        SUM(
                            contributed_brand_new_customers
                        ) FILTER (
                            WHERE spend_quartile = 4
                        )
                    )::numeric
                    * 1000
                    /
                    NULLIF(
                        SUM(marketing_spend)
                            FILTER (
                                WHERE spend_quartile = 4
                            ),
                        0
                    ),
                    4
                ) AS high_spend_brand_new_per_1000,

                ROUND(
                    (
                        SUM(gmv) FILTER (
                            WHERE spend_quartile = 1
                        )
                    )
                    /
                    NULLIF(
                        SUM(marketing_spend)
                            FILTER (
                                WHERE spend_quartile = 1
                            ),
                        0
                    ),
                    4
                ) AS low_spend_gmv_per_spend,

                ROUND(
                    (
                        SUM(gmv) FILTER (
                            WHERE spend_quartile = 4
                        )
                    )
                    /
                    NULLIF(
                        SUM(marketing_spend)
                            FILTER (
                                WHERE spend_quartile = 4
                            ),
                        0
                    ),
                    4
                ) AS high_spend_gmv_per_spend

            FROM ranked_days
            GROUP BY channel_code
        )
        SELECT
            channel_code,
            observation_days,

            spend_order_correlation,
            spend_channel_new_correlation,
            spend_brand_new_correlation,

            low_spend_avg,
            high_spend_avg,

            low_spend_avg_orders,
            high_spend_avg_orders,

            low_spend_avg_channel_new,
            high_spend_avg_channel_new,

            low_spend_avg_brand_new,
            high_spend_avg_brand_new,

            low_spend_orders_per_1000,
            high_spend_orders_per_1000,

            low_spend_channel_new_per_1000,
            high_spend_channel_new_per_1000,

            low_spend_brand_new_per_1000,
            high_spend_brand_new_per_1000,

            low_spend_gmv_per_spend,
            high_spend_gmv_per_spend,

            ROUND(
                high_spend_avg
                /
                NULLIF(low_spend_avg, 0),
                4
            ) AS spend_multiplier,

            ROUND(
                high_spend_avg_orders
                /
                NULLIF(
                    low_spend_avg_orders,
                    0
                ),
                4
            ) AS order_multiplier,

            ROUND(
                high_spend_avg_channel_new
                /
                NULLIF(
                    low_spend_avg_channel_new,
                    0
                ),
                4
            ) AS channel_new_multiplier,

            ROUND(
                high_spend_avg_brand_new
                /
                NULLIF(
                    low_spend_avg_brand_new,
                    0
                ),
                4
            ) AS brand_new_multiplier,

            ROUND(
                (
                    high_spend_avg_orders
                    /
                    NULLIF(
                        low_spend_avg_orders,
                        0
                    )
                )
                /
                NULLIF(
                    high_spend_avg
                    /
                    NULLIF(low_spend_avg, 0),
                    0
                ),
                4
            ) AS order_response_elasticity,

            ROUND(
                (
                    high_spend_avg_channel_new
                    /
                    NULLIF(
                        low_spend_avg_channel_new,
                        0
                    )
                )
                /
                NULLIF(
                    high_spend_avg
                    /
                    NULLIF(low_spend_avg, 0),
                    0
                ),
                4
            ) AS channel_new_response_elasticity,

            ROUND(
                (
                    high_spend_avg_brand_new
                    /
                    NULLIF(
                        low_spend_avg_brand_new,
                        0
                    )
                )
                /
                NULLIF(
                    high_spend_avg
                    /
                    NULLIF(low_spend_avg, 0),
                    0
                ),
                4
            ) AS brand_new_response_elasticity,

            ROUND(
                high_spend_orders_per_1000
                /
                NULLIF(
                    low_spend_orders_per_1000,
                    0
                ),
                4
            ) AS order_efficiency_retention_ratio,

            ROUND(
                high_spend_channel_new_per_1000
                /
                NULLIF(
                    low_spend_channel_new_per_1000,
                    0
                ),
                4
            ) AS channel_new_efficiency_retention_ratio,

            ROUND(
                high_spend_brand_new_per_1000
                /
                NULLIF(
                    low_spend_brand_new_per_1000,
                    0
                ),
                4
            ) AS brand_new_efficiency_retention_ratio,

            ROUND(
                high_spend_gmv_per_spend
                /
                NULLIF(
                    low_spend_gmv_per_spend,
                    0
                ),
                4
            ) AS gmv_efficiency_retention_ratio

        FROM channel_metrics_base
        ORDER BY channel_code
        """,
    )

    excluded_rows = read_all(
        connection,
        """
        WITH marketing_channels AS (
            SELECT DISTINCT channel_id
            FROM
                beauty_bi_v2.
                fact_marketing_spend
        ),
        sales_channels AS (
            SELECT DISTINCT channel_id
            FROM beauty_bi_v2.fact_orders
            WHERE paid_at IS NOT NULL
        )
        SELECT
            channel.channel_code
        FROM marketing_channels
        INNER JOIN beauty_bi_v2.dim_channel
            AS channel
            ON channel.channel_id =
                marketing_channels.channel_id
        WHERE marketing_channels.channel_id
            NOT IN (
                SELECT channel_id
                FROM sales_channels
            )
        ORDER BY channel.channel_code
        """,
    )

    channel_count = len(channel_rows)
    majority_count = (
        channel_count // 2 + 1
        if channel_count
        else 0
    )

    order_elasticities = [
        row["order_response_elasticity"]
        for row in channel_rows
        if row["order_response_elasticity"]
        is not None
    ]

    metrics: dict[str, Any] = {
        "direct_response_channel_count":
            channel_count,
        "majority_channel_count":
            majority_count,
        "excluded_marketing_only_channels": [
            row["channel_code"]
            for row in excluded_rows
        ],
        "channels_high_spend_more_orders":
            sum(
                (
                    row["high_spend_avg_orders"]
                    is not None
                    and row["low_spend_avg_orders"]
                    is not None
                    and
                    row["high_spend_avg_orders"]
                    >
                    row["low_spend_avg_orders"]
                )
                for row in channel_rows
            ),
        "channels_high_spend_more_channel_new":
            sum(
                (
                    row[
                        "high_spend_avg_channel_new"
                    ] is not None
                    and row[
                        "low_spend_avg_channel_new"
                    ] is not None
                    and
                    row[
                        "high_spend_avg_channel_new"
                    ]
                    >
                    row[
                        "low_spend_avg_channel_new"
                    ]
                )
                for row in channel_rows
            ),
        "channels_strict_order_diminishing":
            sum(
                (
                    row[
                        "order_efficiency_retention_ratio"
                    ] is not None
                    and
                    Decimal("0")
                    <
                    row[
                        "order_efficiency_retention_ratio"
                    ]
                    <
                    Decimal("1")
                )
                for row in channel_rows
            ),
        "channels_order_within_noise_tolerance":
            sum(
                (
                    row[
                        "order_efficiency_retention_ratio"
                    ] is not None
                    and
                    Decimal("0")
                    <
                    row[
                        "order_efficiency_retention_ratio"
                    ]
                    <=
                    Decimal("1.05")
                )
                for row in channel_rows
            ),
        "channels_channel_new_diminishing":
            sum(
                (
                    row[
                        "channel_new_efficiency_retention_ratio"
                    ] is not None
                    and
                    Decimal("0")
                    <
                    row[
                        "channel_new_efficiency_retention_ratio"
                    ]
                    <
                    Decimal("1")
                )
                for row in channel_rows
            ),
        "channels_gmv_roi_decline":
            sum(
                (
                    row[
                        "gmv_efficiency_retention_ratio"
                    ] is not None
                    and
                    Decimal("0")
                    <
                    row[
                        "gmv_efficiency_retention_ratio"
                    ]
                    <
                    Decimal("1")
                )
                for row in channel_rows
            ),
        "order_response_curve_spread": (
            max(order_elasticities)
            - min(order_elasticities)
            if len(order_elasticities) >= 2
            else None
        ),
        "by_channel": channel_rows,
    }

    failures: list[str] = []

    if channel_count < 2:
        failures.append(
            "可比较的直接响应渠道不足"
        )

    for row in channel_rows:
        channel_code = row["channel_code"]

        if row["observation_days"] < 30:
            failures.append(
                f"{channel_code} 观察天数不足"
            )

        if (
            row["spend_order_correlation"]
            is None
            or row[
                "spend_order_correlation"
            ] <= Decimal("0")
        ):
            failures.append(
                f"{channel_code} 投放与订单"
                "没有正向相关"
            )

        if (
            row["high_spend_avg"]
            is None
            or row["low_spend_avg"]
            is None
            or row["high_spend_avg"]
            <= row["low_spend_avg"]
        ):
            failures.append(
                f"{channel_code} 投放四分位"
                "没有形成差异"
            )

        if (
            row["high_spend_avg_orders"]
            is None
            or row["low_spend_avg_orders"]
            is None
            or row[
                "high_spend_avg_orders"
            ] <= row[
                "low_spend_avg_orders"
            ]
        ):
            failures.append(
                f"{channel_code} 高投放日"
                "订单没有增加"
            )

        if (
            row[
                "order_efficiency_retention_ratio"
            ] is None
            or row[
                "order_efficiency_retention_ratio"
            ] <= Decimal("0")
            or row[
                "order_efficiency_retention_ratio"
            ] > Decimal("1.05")
        ):
            failures.append(
                f"{channel_code} 订单效率"
                "明显偏离非线性响应容差"
            )

    if (
        metrics[
            "channels_strict_order_diminishing"
        ] < majority_count
    ):
        failures.append(
            "多数渠道没有表现出订单边际递减"
        )

    if (
        metrics[
            "channels_high_spend_more_channel_new"
        ] < majority_count
    ):
        failures.append(
            "多数渠道高投放日没有带来更多渠道新客"
        )

    if (
        metrics[
            "channels_channel_new_diminishing"
        ] < majority_count
    ):
        failures.append(
            "多数渠道没有表现出渠道新客边际递减"
        )

    if (
        metrics["channels_gmv_roi_decline"]
        < majority_count
    ):
        failures.append(
            "多数渠道没有表现出 GMV ROI 下降"
        )

    if (
        metrics["order_response_curve_spread"]
        is None
        or metrics[
            "order_response_curve_spread"
        ] <= Decimal("0.02")
    ):
        failures.append(
            "各渠道订单响应曲线过于一致"
        )

    return PatternObservation(
        pattern_id="P07",
        validator_name=(
            "marketing_diminishing_returns"
        ),
        actual_result=to_json_value(metrics),
        expected_condition=(
            "所有直接响应渠道在高投放日有更多"
            "订单；多数渠道的订单与渠道支付新客"
            "呈次线性增长，GMV ROI 随投入提高"
            "而下降；允许单个渠道在 small Profile"
            "中出现不超过 5% 的轻微随机越界；"
            "各渠道响应曲线不完全相同；"
            "marketing-only 渠道不强行计算"
            "直接转化；正式数值阈值已在 Manifest 冻结；本结果仅为方向诊断。"
        ),
        direction_pass=not failures,
        failure_reason=(
            None
            if not failures
            else "; ".join(failures)
        ),
    )



def observe_p08(
    connection: Connection,
) -> PatternObservation:
    """
    P08 Promotion and Margin Trade-off。

    Grain：
    - 汇总层：PROMOTION / NO_PROMOTION；
    - 明细层：一行一个 promotion_code。

    关键口径：
    - GMV = SUM(item_paid_amount)；
    - 毛利额 = SUM(item_paid_amount - item_cost_amount)；
    - 毛利率 = 毛利额 / GMV；
    - 实际折扣深度 =
      SUM(item_discount_amount) / SUM(item_list_amount)。

    dim_promotion.discount_rate 表示支付价格系数，
    因此实际折扣越深，通常 discount_rate 越低。
    观察器主要使用交易事实中的实际折扣深度，
    避免只依赖配置字段。
    """
    summary = read_one(
        connection,
        """
        WITH paid_items AS (
            SELECT
                item.order_item_id,
                item.order_id,
                item.promotion_id,
                item.quantity,
                item.unit_list_price,
                item.unit_paid_price,
                item.item_list_amount,
                item.item_discount_amount,
                item.item_paid_amount,
                item.unit_cost_at_order,
                item.item_cost_amount,

                CASE
                    WHEN item.promotion_id IS NULL
                    THEN 'NO_PROMOTION'
                    ELSE 'PROMOTION'
                END AS promotion_group

            FROM beauty_bi_v2.fact_order_items
                AS item

            INNER JOIN beauty_bi_v2.fact_orders
                AS orders
                ON orders.order_id =
                    item.order_id

            WHERE orders.paid_at IS NOT NULL
        )
        SELECT
            COUNT(*) AS paid_item_rows,

            COUNT(*) FILTER (
                WHERE promotion_group =
                    'PROMOTION'
            ) AS promoted_item_rows,

            COUNT(*) FILTER (
                WHERE promotion_group =
                    'NO_PROMOTION'
            ) AS non_promoted_item_rows,

            COUNT(DISTINCT order_id) FILTER (
                WHERE promotion_group =
                    'PROMOTION'
            ) AS promoted_orders,

            COUNT(DISTINCT order_id) FILTER (
                WHERE promotion_group =
                    'NO_PROMOTION'
            ) AS non_promoted_orders,

            SUM(quantity) FILTER (
                WHERE promotion_group =
                    'PROMOTION'
            ) AS promoted_sales_quantity,

            SUM(quantity) FILTER (
                WHERE promotion_group =
                    'NO_PROMOTION'
            ) AS non_promoted_sales_quantity,

            ROUND(
                AVG(quantity) FILTER (
                    WHERE promotion_group =
                        'PROMOTION'
                ),
                4
            ) AS promoted_average_item_quantity,

            ROUND(
                AVG(quantity) FILTER (
                    WHERE promotion_group =
                        'NO_PROMOTION'
                ),
                4
            ) AS non_promoted_average_item_quantity,

            ROUND(
                SUM(item_list_amount) FILTER (
                    WHERE promotion_group =
                        'PROMOTION'
                ),
                2
            ) AS promoted_list_amount,

            ROUND(
                SUM(item_discount_amount) FILTER (
                    WHERE promotion_group =
                        'PROMOTION'
                ),
                2
            ) AS promoted_discount_amount,

            ROUND(
                SUM(item_paid_amount) FILTER (
                    WHERE promotion_group =
                        'PROMOTION'
                ),
                2
            ) AS promoted_gmv,

            ROUND(
                SUM(item_paid_amount) FILTER (
                    WHERE promotion_group =
                        'NO_PROMOTION'
                ),
                2
            ) AS non_promoted_gmv,

            ROUND(
                SUM(
                    item_paid_amount
                    - item_cost_amount
                ) FILTER (
                    WHERE promotion_group =
                        'PROMOTION'
                ),
                2
            ) AS promoted_gross_margin,

            ROUND(
                SUM(
                    item_paid_amount
                    - item_cost_amount
                ) FILTER (
                    WHERE promotion_group =
                        'NO_PROMOTION'
                ),
                2
            ) AS non_promoted_gross_margin,

            ROUND(
                SUM(
                    item_paid_amount
                    - item_cost_amount
                ) FILTER (
                    WHERE promotion_group =
                        'PROMOTION'
                )
                /
                NULLIF(
                    SUM(item_paid_amount) FILTER (
                        WHERE promotion_group =
                            'PROMOTION'
                    ),
                    0
                ),
                4
            ) AS promoted_margin_rate,

            ROUND(
                SUM(
                    item_paid_amount
                    - item_cost_amount
                ) FILTER (
                    WHERE promotion_group =
                        'NO_PROMOTION'
                )
                /
                NULLIF(
                    SUM(item_paid_amount) FILTER (
                        WHERE promotion_group =
                            'NO_PROMOTION'
                    ),
                    0
                ),
                4
            ) AS non_promoted_margin_rate,

            ROUND(
                SUM(item_discount_amount) FILTER (
                    WHERE promotion_group =
                        'PROMOTION'
                )
                /
                NULLIF(
                    SUM(item_list_amount) FILTER (
                        WHERE promotion_group =
                            'PROMOTION'
                    ),
                    0
                ),
                4
            ) AS promoted_effective_discount_depth,

            ROUND(
                SUM(item_discount_amount) FILTER (
                    WHERE promotion_group =
                        'NO_PROMOTION'
                )
                /
                NULLIF(
                    SUM(item_list_amount) FILTER (
                        WHERE promotion_group =
                            'NO_PROMOTION'
                    ),
                    0
                ),
                4
            ) AS non_promoted_effective_discount_depth,

            COUNT(*) FILTER (
                WHERE
                    item_list_amount
                    <>
                    unit_list_price * quantity
            ) AS list_formula_error_count,

            COUNT(*) FILTER (
                WHERE
                    item_paid_amount
                    <>
                    unit_paid_price * quantity
            ) AS paid_formula_error_count,

            COUNT(*) FILTER (
                WHERE
                    item_discount_amount
                    <>
                    item_list_amount
                    - item_paid_amount
            ) AS discount_formula_error_count,

            COUNT(*) FILTER (
                WHERE
                    item_cost_amount
                    <>
                    unit_cost_at_order * quantity
            ) AS cost_formula_error_count

        FROM paid_items
        """,
    )

    promotion_rows = read_all(
        connection,
        """
        WITH promotion_stats AS (
            SELECT
                promotion.promotion_code,
                promotion.promotion_name,
                promotion.promotion_type,
                promotion.discount_rate,
                promotion.target_member_level,
                promotion.start_date,
                promotion.end_date,

                COUNT(*) AS paid_item_rows,
                COUNT(DISTINCT item.order_id)
                    AS paid_orders,
                COUNT(DISTINCT item.product_id)
                    AS distinct_products,

                (
                    promotion.end_date
                    - promotion.start_date
                    + 1
                ) AS promotion_active_days,

                SUM(item.quantity)
                    AS sales_quantity,

                ROUND(
                    SUM(item.quantity)::numeric
                    /
                    NULLIF(
                        (
                            promotion.end_date
                            - promotion.start_date
                            + 1
                        ),
                        0
                    ),
                    4
                ) AS sales_quantity_per_active_day,

                ROUND(
                    AVG(item.quantity),
                    4
                ) AS average_item_quantity,

                ROUND(
                    SUM(item.item_list_amount),
                    2
                ) AS item_list_amount,

                ROUND(
                    SUM(item.item_discount_amount),
                    2
                ) AS discount_amount,

                ROUND(
                    SUM(item.item_paid_amount),
                    2
                ) AS gmv,

                ROUND(
                    SUM(item.item_cost_amount),
                    2
                ) AS cost_amount,

                ROUND(
                    SUM(
                        item.item_paid_amount
                        - item.item_cost_amount
                    ),
                    2
                ) AS gross_margin,

                ROUND(
                    SUM(item.item_paid_amount)
                    /
                    NULLIF(
                        (
                            promotion.end_date
                            - promotion.start_date
                            + 1
                        ),
                        0
                    ),
                    2
                ) AS gmv_per_active_day,

                ROUND(
                    SUM(
                        item.item_paid_amount
                        - item.item_cost_amount
                    )
                    /
                    NULLIF(
                        (
                            promotion.end_date
                            - promotion.start_date
                            + 1
                        ),
                        0
                    ),
                    2
                ) AS gross_margin_per_active_day,

                ROUND(
                    SUM(
                        item.item_paid_amount
                        - item.item_cost_amount
                    )
                    /
                    NULLIF(
                        SUM(item.quantity),
                        0
                    ),
                    4
                ) AS gross_margin_per_unit,

                ROUND(
                    SUM(
                        item.item_paid_amount
                        - item.item_cost_amount
                    )
                    /
                    NULLIF(
                        SUM(item.item_paid_amount),
                        0
                    ),
                    4
                ) AS gross_margin_rate,

                ROUND(
                    SUM(item.item_discount_amount)
                    /
                    NULLIF(
                        SUM(item.item_list_amount),
                        0
                    ),
                    4
                ) AS effective_discount_depth,

                COUNT(*) FILTER (
                    WHERE
                        orders.order_created_at::date
                        NOT BETWEEN
                            promotion.start_date
                            AND promotion.end_date
                ) AS pricing_date_window_error_count,

                COUNT(*) FILTER (
                    WHERE
                        orders.order_created_at::date
                        BETWEEN
                            promotion.start_date
                            AND promotion.end_date
                        AND
                        orders.paid_at::date
                        NOT BETWEEN
                            promotion.start_date
                            AND promotion.end_date
                ) AS payment_date_rollover_count,

                COUNT(*) FILTER (
                    WHERE
                        promotion.target_member_level
                        IS NOT NULL
                        AND
                        orders.member_level_at_order
                        IS DISTINCT FROM
                        promotion.target_member_level
                ) AS target_level_error_count

            FROM beauty_bi_v2.dim_promotion
                AS promotion

            LEFT JOIN
                beauty_bi_v2.fact_order_items
                    AS item
                ON item.promotion_id =
                    promotion.promotion_id

            LEFT JOIN beauty_bi_v2.fact_orders
                AS orders
                ON
                    orders.order_id =
                    item.order_id
                AND orders.paid_at IS NOT NULL

            WHERE orders.order_id IS NOT NULL

            GROUP BY
                promotion.promotion_id,
                promotion.promotion_code,
                promotion.promotion_name,
                promotion.promotion_type,
                promotion.discount_rate,
                promotion.target_member_level,
                promotion.start_date,
                promotion.end_date
        )
        SELECT *
        FROM promotion_stats
        ORDER BY promotion_code
        """,
    )

    comparison_rows = read_all(
        connection,
        """
        WITH paid_items AS (
            SELECT
                item.order_item_id,
                item.order_id,
                item.product_id,
                item.promotion_id,
                item.quantity,
                item.item_paid_amount,
                item.item_cost_amount,

                CASE
                    WHEN item.promotion_id IS NULL
                    THEN FALSE
                    ELSE TRUE
                END AS is_promoted

            FROM beauty_bi_v2.fact_order_items
                AS item

            INNER JOIN beauty_bi_v2.fact_orders
                AS orders
                ON orders.order_id =
                    item.order_id

            WHERE orders.paid_at IS NOT NULL
        ),
        product_comparison AS (
            SELECT
                product_id,

                SUM(quantity) FILTER (
                    WHERE is_promoted
                ) AS promoted_quantity,

                SUM(quantity) FILTER (
                    WHERE NOT is_promoted
                ) AS non_promoted_quantity,

                ROUND(
                    AVG(quantity) FILTER (
                        WHERE is_promoted
                    ),
                    4
                ) AS promoted_average_item_quantity,

                ROUND(
                    AVG(quantity) FILTER (
                        WHERE NOT is_promoted
                    ),
                    4
                ) AS non_promoted_average_item_quantity,

                ROUND(
                    SUM(
                        item_paid_amount
                        - item_cost_amount
                    ) FILTER (
                        WHERE is_promoted
                    )
                    /
                    NULLIF(
                        SUM(item_paid_amount) FILTER (
                            WHERE is_promoted
                        ),
                        0
                    ),
                    4
                ) AS promoted_margin_rate,

                ROUND(
                    SUM(
                        item_paid_amount
                        - item_cost_amount
                    ) FILTER (
                        WHERE NOT is_promoted
                    )
                    /
                    NULLIF(
                        SUM(item_paid_amount) FILTER (
                            WHERE NOT is_promoted
                        ),
                        0
                    ),
                    4
                ) AS non_promoted_margin_rate

            FROM paid_items
            GROUP BY product_id
        )
        SELECT
            COUNT(*) FILTER (
                WHERE
                    promoted_quantity IS NOT NULL
                    AND non_promoted_quantity
                        IS NOT NULL
            ) AS comparable_products,

            COUNT(*) FILTER (
                WHERE
                    promoted_average_item_quantity
                    >
                    non_promoted_average_item_quantity
            ) AS products_higher_quantity_with_promotion,

            COUNT(*) FILTER (
                WHERE
                    promoted_margin_rate
                    <
                    non_promoted_margin_rate
            ) AS products_lower_margin_rate_with_promotion,

            COUNT(*) FILTER (
                WHERE
                    promoted_average_item_quantity
                    >
                    non_promoted_average_item_quantity
                    AND
                    promoted_margin_rate
                    <
                    non_promoted_margin_rate
            ) AS products_quantity_up_margin_rate_down

        FROM product_comparison
        WHERE
            promoted_quantity IS NOT NULL
            AND non_promoted_quantity IS NOT NULL
        """,
    )

    product_comparison = (
        comparison_rows[0]
        if comparison_rows
        else {
            "comparable_products": 0,
            "products_higher_quantity_with_promotion": 0,
            "products_lower_margin_rate_with_promotion": 0,
            "products_quantity_up_margin_rate_down": 0,
        }
    )

    failures: list[str] = []

    if len(promotion_rows) < 2:
        failures.append(
            "有真实销售的促销方案不足"
        )

    if (
        summary["promoted_item_rows"] <= 0
        or summary["non_promoted_item_rows"] <= 0
    ):
        failures.append(
            "促销与非促销订单明细没有同时存在"
        )

    highest_quantity_code: str | None = None
    highest_gmv_code: str | None = None
    highest_margin_code: str | None = None
    highest_margin_rate_code: str | None = None
    highest_quantity_per_day_code: str | None = None
    highest_margin_per_day_code: str | None = None
    deepest_discount_code: str | None = None
    discount_margin_correlation: Any = None

    if promotion_rows:
        highest_quantity_code = max(
            promotion_rows,
            key=lambda row: (
                row["sales_quantity"],
                row["promotion_code"],
            ),
        )["promotion_code"]

        highest_gmv_code = max(
            promotion_rows,
            key=lambda row: (
                row["gmv"],
                row["promotion_code"],
            ),
        )["promotion_code"]

        highest_margin_code = max(
            promotion_rows,
            key=lambda row: (
                row["gross_margin"],
                row["promotion_code"],
            ),
        )["promotion_code"]

        highest_margin_rate_code = max(
            promotion_rows,
            key=lambda row: (
                row["gross_margin_rate"],
                row["promotion_code"],
            ),
        )["promotion_code"]

        highest_quantity_per_day_code = max(
            promotion_rows,
            key=lambda row: (
                row["sales_quantity_per_active_day"],
                row["promotion_code"],
            ),
        )["promotion_code"]

        highest_margin_per_day_code = max(
            promotion_rows,
            key=lambda row: (
                row["gross_margin_per_active_day"],
                row["promotion_code"],
            ),
        )["promotion_code"]

        deepest_discount_code = max(
            promotion_rows,
            key=lambda row: (
                row["effective_discount_depth"],
                row["promotion_code"],
            ),
        )["promotion_code"]

        discount_margin_row = read_one(
            connection,
            """
            WITH promotion_stats AS (
                SELECT
                    promotion.promotion_id,

                    (
                        SUM(item.item_discount_amount)
                        /
                        NULLIF(
                            SUM(item.item_list_amount),
                            0
                        )
                    )::double precision
                        AS effective_discount_depth,

                    (
                        SUM(
                            item.item_paid_amount
                            - item.item_cost_amount
                        )
                        /
                        NULLIF(
                            SUM(item.item_paid_amount),
                            0
                        )
                    )::double precision
                        AS gross_margin_rate

                FROM beauty_bi_v2.dim_promotion
                    AS promotion

                INNER JOIN
                    beauty_bi_v2.fact_order_items
                        AS item
                    ON item.promotion_id =
                        promotion.promotion_id

                INNER JOIN beauty_bi_v2.fact_orders
                    AS orders
                    ON
                        orders.order_id =
                        item.order_id
                    AND orders.paid_at IS NOT NULL

                GROUP BY promotion.promotion_id
            )
            SELECT
                ROUND(
                    CORR(
                        effective_discount_depth,
                        gross_margin_rate
                    )::numeric,
                    4
                ) AS correlation
            FROM promotion_stats
            """,
        )

        discount_margin_correlation = (
            discount_margin_row["correlation"]
        )

    if (
        summary["promoted_margin_rate"] is None
        or summary["non_promoted_margin_rate"]
        is None
        or summary["promoted_margin_rate"]
        >= summary["non_promoted_margin_rate"]
    ):
        failures.append(
            "促销没有体现整体毛利率让渡"
        )

    if (
        product_comparison[
            "products_higher_quantity_with_promotion"
        ] <= 0
    ):
        failures.append(
            "没有商品在促销下表现出更高购买数量"
        )

    if (
        product_comparison[
            "products_quantity_up_margin_rate_down"
        ] <= 0
    ):
        failures.append(
            "没有商品形成销量提升但毛利率下降"
        )

    # 不把累计销量冠军与累计毛利冠军相同直接判错。
    # 不同促销有效期长度差异很大，累计值会受到 exposure
    # duration 强烈影响；正式权衡检查使用毛利率、折扣深度
    # 和按有效天数归一化后的强度指标。

    if (
        highest_quantity_per_day_code is not None
        and highest_margin_rate_code is not None
        and highest_quantity_per_day_code
        == highest_margin_rate_code
    ):
        failures.append(
            "日均销量最强促销同时具有最高毛利率，"
            "促销权衡信号不足"
        )

    if (
        deepest_discount_code is not None
        and highest_margin_rate_code is not None
        and deepest_discount_code
        == highest_margin_rate_code
    ):
        failures.append(
            "折扣最深促销同时具有最高毛利率"
        )

    if (
        discount_margin_correlation is None
        or discount_margin_correlation
        >= Decimal("0")
    ):
        failures.append(
            "实际折扣深度与毛利率没有负向关系"
        )

    formula_error_count = sum(
        summary[field]
        for field in (
            "list_formula_error_count",
            "paid_formula_error_count",
            "discount_formula_error_count",
            "cost_formula_error_count",
        )
    )

    if formula_error_count != 0:
        failures.append(
            "订单明细金额公式存在错误"
        )

    pricing_date_window_errors = sum(
        row["pricing_date_window_error_count"]
        for row in promotion_rows
    )

    payment_date_rollovers = sum(
        row["payment_date_rollover_count"]
        for row in promotion_rows
    )

    target_level_errors = sum(
        row["target_level_error_count"]
        for row in promotion_rows
    )

    if pricing_date_window_errors != 0:
        failures.append(
            "促销定价日期超出促销有效期"
        )

    if target_level_errors != 0:
        failures.append(
            "会员定向促销与支付时点等级不一致"
        )

    actual_result: dict[str, Any] = {
        **summary,
        **product_comparison,
        "promotion_count_with_sales":
            len(promotion_rows),
        "highest_quantity_promotion":
            highest_quantity_code,
        "highest_gmv_promotion":
            highest_gmv_code,
        "highest_gross_margin_promotion":
            highest_margin_code,
        "highest_gross_margin_rate_promotion":
            highest_margin_rate_code,
        "highest_quantity_per_active_day_promotion":
            highest_quantity_per_day_code,
        "highest_gross_margin_per_active_day_promotion":
            highest_margin_per_day_code,
        "highest_quantity_same_as_highest_gross_margin_total":
            (
                highest_quantity_code is not None
                and highest_quantity_code
                == highest_margin_code
            ),
        "deepest_discount_promotion":
            deepest_discount_code,
        "discount_depth_margin_rate_correlation":
            discount_margin_correlation,
        "formula_error_count":
            formula_error_count,
        "promotion_pricing_date_window_error_count":
            pricing_date_window_errors,
        "promotion_payment_date_rollover_count":
            payment_date_rollovers,
        "promotion_target_level_error_count":
            target_level_errors,
        "by_promotion": promotion_rows,
    }

    return PatternObservation(
        pattern_id="P08",
        validator_name=(
            "promotion_margin_tradeoff"
        ),
        actual_result=to_json_value(
            actual_result
        ),
        expected_condition=(
            "促销与非促销交易同时存在；"
            "促销提升部分商品购买数量但让渡"
            "毛利率；实际折扣越深，毛利率"
            "整体越低；累计排名保留为诊断，"
            "正式权衡使用日均销售强度、毛利率"
            "和折扣深度；促销定价日期以"
            "order_created_at 为准；"
            "会员定向和订单明细"
            "金额公式正确；正式数值阈值"
            "尚未冻结。"
        ),
        direction_pass=not failures,
        failure_reason=(
            None
            if not failures
            else "; ".join(failures)
        ),
    )



def observe_p09(
    connection: Connection,
) -> PatternObservation:
    """
    P09 Refund, Review and Quality Relation。

    hidden quality_score 不写入正式 BI 表，因此验收不能
    直接读取生成器隐藏变量。这里通过可观察代理验证：

    - 低评分商品明细的完成退款率高于高评分；
    - 发生完成退款的评价平均分更低；
    - 商品平均评分与商品完成退款率负相关；
    - 低评分未退款、高评分退款、退款未评价等
      非机械案例必须同时存在。

    Refund 先聚合到 order_item Grain，避免未来支持多笔
    退款时与 Review Join 产生行数膨胀。
    """
    summary = read_one(
        connection,
        """
        WITH refund_by_item AS (
            SELECT
                order_item_id,
                BOOL_OR(
                    refund_status = 'completed'
                ) AS completed_refund,
                BOOL_OR(TRUE) AS any_refund,
                COUNT(*) AS refund_event_count
            FROM beauty_bi_v2.fact_refunds
            GROUP BY order_item_id
        ),
        item_outcomes AS (
            SELECT
                item.order_item_id,
                item.product_id,

                COALESCE(
                    refund.completed_refund,
                    FALSE
                ) AS completed_refund,

                COALESCE(
                    refund.any_refund,
                    FALSE
                ) AS any_refund,

                COALESCE(
                    refund.refund_event_count,
                    0
                ) AS refund_event_count,

                review.review_id,
                review.rating,
                review.sentiment,

                CASE
                    WHEN review.review_id IS NOT NULL
                    THEN TRUE
                    ELSE FALSE
                END AS has_review

            FROM beauty_bi_v2.fact_order_items
                AS item

            INNER JOIN beauty_bi_v2.fact_orders
                AS orders
                ON orders.order_id =
                    item.order_id

            LEFT JOIN refund_by_item
                AS refund
                ON refund.order_item_id =
                    item.order_item_id

            LEFT JOIN beauty_bi_v2.fact_reviews
                AS review
                ON review.order_item_id =
                    item.order_item_id

            WHERE orders.order_status =
                'delivered'
        )
        SELECT
            COUNT(*) AS delivered_item_rows,

            COUNT(*) FILTER (
                WHERE any_refund
            ) AS any_refund_items,

            COUNT(*) FILTER (
                WHERE completed_refund
            ) AS completed_refund_items,

            COUNT(*) FILTER (
                WHERE has_review
            ) AS reviewed_items,

            COUNT(*) FILTER (
                WHERE
                    has_review
                    AND NOT any_refund
            ) AS reviewed_without_refund,

            COUNT(*) FILTER (
                WHERE
                    completed_refund
                    AND NOT has_review
            ) AS completed_refund_without_review,

            COUNT(*) FILTER (
                WHERE
                    NOT any_refund
                    AND NOT has_review
            ) AS no_refund_no_review,

            COUNT(*) FILTER (
                WHERE
                    rating <= 2
                    AND completed_refund
            ) AS low_rating_with_completed_refund,

            COUNT(*) FILTER (
                WHERE
                    rating <= 2
                    AND NOT completed_refund
            ) AS low_rating_without_completed_refund,

            COUNT(*) FILTER (
                WHERE
                    rating >= 4
                    AND completed_refund
            ) AS high_rating_with_completed_refund,

            COUNT(*) FILTER (
                WHERE
                    rating >= 4
                    AND NOT any_refund
            ) AS high_rating_without_refund,

            ROUND(
                AVG(rating::numeric) FILTER (
                    WHERE
                        completed_refund
                        AND has_review
                ),
                4
            ) AS completed_refund_average_rating,

            ROUND(
                AVG(rating::numeric) FILTER (
                    WHERE
                        NOT any_refund
                        AND has_review
                ),
                4
            ) AS no_refund_average_rating,

            ROUND(
                (
                    COUNT(*) FILTER (
                        WHERE
                            rating <= 2
                            AND completed_refund
                    )
                )::numeric
                /
                NULLIF(
                    COUNT(*) FILTER (
                        WHERE rating <= 2
                    ),
                    0
                ),
                4
            ) AS low_rating_completed_refund_rate,

            ROUND(
                (
                    COUNT(*) FILTER (
                        WHERE
                            rating >= 4
                            AND completed_refund
                    )
                )::numeric
                /
                NULLIF(
                    COUNT(*) FILTER (
                        WHERE rating >= 4
                    ),
                    0
                ),
                4
            ) AS high_rating_completed_refund_rate,

            ROUND(
                (
                    COUNT(*) FILTER (
                        WHERE
                            completed_refund
                            AND has_review
                    )
                )::numeric
                /
                NULLIF(
                    COUNT(*) FILTER (
                        WHERE completed_refund
                    ),
                    0
                ),
                4
            ) AS completed_refund_review_coverage,

            ROUND(
                (
                    COUNT(*) FILTER (
                        WHERE
                            NOT any_refund
                            AND has_review
                    )
                )::numeric
                /
                NULLIF(
                    COUNT(*) FILTER (
                        WHERE NOT any_refund
                    ),
                    0
                ),
                4
            ) AS no_refund_review_coverage,

            COUNT(*) FILTER (
                WHERE
                    (
                        rating IN (1, 2)
                        AND sentiment
                            <> 'negative'
                    )
                    OR
                    (
                        rating = 3
                        AND sentiment
                            <> 'neutral'
                    )
                    OR
                    (
                        rating IN (4, 5)
                        AND sentiment
                            <> 'positive'
                    )
            ) AS sentiment_rating_error_count,

            COUNT(*) FILTER (
                WHERE refund_event_count > 1
            ) AS items_with_multiple_refund_events

        FROM item_outcomes
        """,
    )

    rating_rows = read_all(
        connection,
        """
        WITH refund_by_item AS (
            SELECT
                order_item_id,
                BOOL_OR(
                    refund_status = 'completed'
                ) AS completed_refund,
                BOOL_OR(TRUE) AS any_refund
            FROM beauty_bi_v2.fact_refunds
            GROUP BY order_item_id
        )
        SELECT
            review.rating,
            COUNT(*) AS reviewed_items,

            COUNT(*) FILTER (
                WHERE COALESCE(
                    refund.completed_refund,
                    FALSE
                )
            ) AS completed_refund_items,

            COUNT(*) FILTER (
                WHERE COALESCE(
                    refund.any_refund,
                    FALSE
                )
            ) AS any_refund_items,

            ROUND(
                (
                    COUNT(*) FILTER (
                        WHERE COALESCE(
                            refund.completed_refund,
                            FALSE
                        )
                    )
                )::numeric
                /
                NULLIF(COUNT(*), 0),
                4
            ) AS completed_refund_rate,

            ROUND(
                (
                    COUNT(*) FILTER (
                        WHERE COALESCE(
                            refund.any_refund,
                            FALSE
                        )
                    )
                )::numeric
                /
                NULLIF(COUNT(*), 0),
                4
            ) AS any_refund_rate

        FROM beauty_bi_v2.fact_reviews
            AS review

        LEFT JOIN refund_by_item
            AS refund
            ON refund.order_item_id =
                review.order_item_id

        GROUP BY review.rating
        ORDER BY review.rating
        """,
    )

    refund_status_rows = read_all(
        connection,
        """
        SELECT
            refund.refund_status,
            COUNT(*) AS refund_events,

            COUNT(review.review_id)
                AS reviewed_refund_events,

            ROUND(
                AVG(review.rating::numeric),
                4
            ) AS average_rating,

            ROUND(
                COUNT(review.review_id)::numeric
                /
                NULLIF(COUNT(*), 0),
                4
            ) AS review_coverage

        FROM beauty_bi_v2.fact_refunds
            AS refund

        LEFT JOIN beauty_bi_v2.fact_reviews
            AS review
            ON review.order_item_id =
                refund.order_item_id

        GROUP BY refund.refund_status
        ORDER BY refund.refund_status
        """,
    )

    product_relation = read_one(
        connection,
        """
        WITH refund_by_item AS (
            SELECT
                order_item_id,
                BOOL_OR(
                    refund_status = 'completed'
                ) AS completed_refund
            FROM beauty_bi_v2.fact_refunds
            GROUP BY order_item_id
        ),
        item_outcomes AS (
            SELECT
                item.order_item_id,
                item.product_id,
                review.rating,
                COALESCE(
                    refund.completed_refund,
                    FALSE
                ) AS completed_refund

            FROM beauty_bi_v2.fact_order_items
                AS item

            INNER JOIN beauty_bi_v2.fact_orders
                AS orders
                ON orders.order_id =
                    item.order_id

            LEFT JOIN refund_by_item
                AS refund
                ON refund.order_item_id =
                    item.order_item_id

            LEFT JOIN beauty_bi_v2.fact_reviews
                AS review
                ON review.order_item_id =
                    item.order_item_id

            WHERE orders.order_status =
                'delivered'
        ),
        product_stats AS (
            SELECT
                product_id,
                COUNT(*) AS delivered_items,
                COUNT(rating) AS reviewed_items,
                AVG(rating::numeric)
                    AS average_rating,
                AVG(
                    completed_refund::integer
                    ::numeric
                ) AS completed_refund_rate

            FROM item_outcomes
            GROUP BY product_id

            HAVING
                COUNT(*) >= 20
                AND COUNT(rating) >= 5
        ),
        product_ranks AS (
            SELECT
                product_stats.*,

                RANK() OVER (
                    ORDER BY average_rating
                )::numeric AS rating_rank,

                RANK() OVER (
                    ORDER BY completed_refund_rate
                )::numeric AS refund_rate_rank,

                NTILE(4) OVER (
                    ORDER BY
                        average_rating,
                        product_id
                ) AS rating_quartile

            FROM product_stats
        )
        SELECT
            COUNT(*) AS compared_products,

            ROUND(
                CORR(
                    average_rating,
                    completed_refund_rate
                )::numeric,
                4
            ) AS product_rating_refund_correlation,

            ROUND(
                CORR(
                    rating_rank,
                    refund_rate_rank
                )::numeric,
                4
            ) AS product_rating_refund_rank_correlation,

            ROUND(
                AVG(completed_refund_rate)
                    FILTER (
                        WHERE rating_quartile = 1
                    ),
                4
            ) AS lowest_rating_quartile_refund_rate,

            ROUND(
                AVG(completed_refund_rate)
                    FILTER (
                        WHERE rating_quartile = 4
                    ),
                4
            ) AS highest_rating_quartile_refund_rate,

            ROUND(
                (
                    AVG(completed_refund_rate)
                        FILTER (
                            WHERE rating_quartile = 1
                        )
                )
                /
                NULLIF(
                    AVG(completed_refund_rate)
                        FILTER (
                            WHERE rating_quartile = 4
                        ),
                    0
                ),
                4
            ) AS low_to_high_rating_quartile_refund_ratio

        FROM product_ranks
        """,
    )

    category_rows = read_all(
        connection,
        """
        WITH refund_by_item AS (
            SELECT
                order_item_id,
                BOOL_OR(
                    refund_status = 'completed'
                ) AS completed_refund
            FROM beauty_bi_v2.fact_refunds
            GROUP BY order_item_id
        ),
        item_outcomes AS (
            SELECT
                product.category,
                item.order_item_id,
                review.rating,
                COALESCE(
                    refund.completed_refund,
                    FALSE
                ) AS completed_refund

            FROM beauty_bi_v2.fact_order_items
                AS item

            INNER JOIN beauty_bi_v2.fact_orders
                AS orders
                ON orders.order_id =
                    item.order_id

            INNER JOIN beauty_bi_v2.dim_product
                AS product
                ON product.product_id =
                    item.product_id

            LEFT JOIN refund_by_item
                AS refund
                ON refund.order_item_id =
                    item.order_item_id

            LEFT JOIN beauty_bi_v2.fact_reviews
                AS review
                ON review.order_item_id =
                    item.order_item_id

            WHERE orders.order_status =
                'delivered'
        )
        SELECT
            category,
            COUNT(*) AS delivered_items,
            COUNT(rating) AS reviewed_items,

            ROUND(
                AVG(rating::numeric),
                4
            ) AS average_rating,

            ROUND(
                AVG(
                    completed_refund::integer
                    ::numeric
                ),
                4
            ) AS completed_refund_rate

        FROM item_outcomes
        GROUP BY category
        ORDER BY category
        """,
    )

    extreme_product_rows = read_all(
        connection,
        """
        WITH refund_by_item AS (
            SELECT
                order_item_id,
                BOOL_OR(
                    refund_status = 'completed'
                ) AS completed_refund
            FROM beauty_bi_v2.fact_refunds
            GROUP BY order_item_id
        ),
        product_stats AS (
            SELECT
                product.sku_code,
                product.product_name,
                product.category,

                COUNT(*) AS delivered_items,
                COUNT(review.rating)
                    AS reviewed_items,

                ROUND(
                    AVG(review.rating::numeric),
                    4
                ) AS average_rating,

                ROUND(
                    AVG(
                        COALESCE(
                            refund.completed_refund,
                            FALSE
                        )::integer::numeric
                    ),
                    4
                ) AS completed_refund_rate

            FROM beauty_bi_v2.fact_order_items
                AS item

            INNER JOIN beauty_bi_v2.fact_orders
                AS orders
                ON orders.order_id =
                    item.order_id

            INNER JOIN beauty_bi_v2.dim_product
                AS product
                ON product.product_id =
                    item.product_id

            LEFT JOIN refund_by_item
                AS refund
                ON refund.order_item_id =
                    item.order_item_id

            LEFT JOIN beauty_bi_v2.fact_reviews
                AS review
                ON review.order_item_id =
                    item.order_item_id

            WHERE orders.order_status =
                'delivered'

            GROUP BY
                product.product_id,
                product.sku_code,
                product.product_name,
                product.category

            HAVING
                COUNT(*) >= 20
                AND COUNT(review.rating) >= 5
        ),
        ranked AS (
            SELECT
                product_stats.*,

                ROW_NUMBER() OVER (
                    ORDER BY
                        average_rating,
                        sku_code
                ) AS low_rating_rank,

                ROW_NUMBER() OVER (
                    ORDER BY
                        average_rating DESC,
                        sku_code
                ) AS high_rating_rank

            FROM product_stats
        )
        SELECT
            CASE
                WHEN low_rating_rank <= 5
                THEN 'LOWEST_RATING'
                ELSE 'HIGHEST_RATING'
            END AS rating_group,
            sku_code,
            product_name,
            category,
            delivered_items,
            reviewed_items,
            average_rating,
            completed_refund_rate

        FROM ranked
        WHERE
            low_rating_rank <= 5
            OR high_rating_rank <= 5

        ORDER BY
            rating_group,
            average_rating,
            sku_code
        """,
    )

    duplicate_reviews = read_one(
        connection,
        """
        SELECT COUNT(*) AS duplicate_review_items
        FROM (
            SELECT order_item_id
            FROM beauty_bi_v2.fact_reviews
            GROUP BY order_item_id
            HAVING COUNT(*) > 1
        ) AS duplicates
        """,
    )["duplicate_review_items"]

    actual_result: dict[str, Any] = {
        **summary,
        **product_relation,
        "duplicate_review_items":
            duplicate_reviews,
        "refund_rate_by_rating":
            rating_rows,
        "review_by_refund_status":
            refund_status_rows,
        "by_category":
            category_rows,
        "extreme_rating_products":
            extreme_product_rows,
    }

    failures: list[str] = []

    for field_name, message in (
        (
            "low_rating_with_completed_refund",
            "没有低评分且完成退款案例",
        ),
        (
            "low_rating_without_completed_refund",
            "没有低评分但未完成退款案例",
        ),
        (
            "high_rating_with_completed_refund",
            "没有高评分但完成退款案例",
        ),
        (
            "completed_refund_without_review",
            "没有完成退款但未评价案例",
        ),
        (
            "no_refund_no_review",
            "没有既无退款也无评价案例",
        ),
        (
            "reviewed_without_refund",
            "没有有评价但无退款案例",
        ),
    ):
        if summary[field_name] <= 0:
            failures.append(message)

    if (
        summary["completed_refund_average_rating"]
        is None
        or summary["no_refund_average_rating"]
        is None
        or summary[
            "completed_refund_average_rating"
        ] >= summary[
            "no_refund_average_rating"
        ]
    ):
        failures.append(
            "完成退款评价平均分没有低于无退款评价"
        )

    if (
        summary[
            "low_rating_completed_refund_rate"
        ] is None
        or summary[
            "high_rating_completed_refund_rate"
        ] is None
        or summary[
            "low_rating_completed_refund_rate"
        ] <= summary[
            "high_rating_completed_refund_rate"
        ]
    ):
        failures.append(
            "低评分完成退款率没有高于高评分"
        )

    if product_relation["compared_products"] < 20:
        failures.append(
            "可比较商品数量不足"
        )

    if (
        product_relation[
            "product_rating_refund_correlation"
        ] is None
        or product_relation[
            "product_rating_refund_correlation"
        ] >= Decimal("0")
    ):
        failures.append(
            "商品平均评分与完成退款率未呈负相关"
        )

    if (
        product_relation[
            "product_rating_refund_rank_correlation"
        ] is None
        or product_relation[
            "product_rating_refund_rank_correlation"
        ] >= Decimal("0")
    ):
        failures.append(
            "商品评分排名与退款率排名未呈负相关"
        )

    if (
        product_relation[
            "lowest_rating_quartile_refund_rate"
        ] is None
        or product_relation[
            "highest_rating_quartile_refund_rate"
        ] is None
        or product_relation[
            "lowest_rating_quartile_refund_rate"
        ] <= product_relation[
            "highest_rating_quartile_refund_rate"
        ]
    ):
        failures.append(
            "低评分商品四分位退款率没有更高"
        )

    if summary["sentiment_rating_error_count"] != 0:
        failures.append(
            "rating 与 sentiment 映射不一致"
        )

    if duplicate_reviews != 0:
        failures.append(
            "同一订单明细存在重复评价"
        )

    return PatternObservation(
        pattern_id="P09",
        validator_name=(
            "refund_review_quality_relation"
        ),
        actual_result=to_json_value(
            actual_result
        ),
        expected_condition=(
            "低评分完成退款率高于高评分；"
            "完成退款评价平均分低于无退款评价；"
            "商品平均评分与完成退款率及其"
            "排名总体负相关；低评分未退款、"
            "高评分退款、退款未评价、无退款"
            "无评价等非机械案例同时存在；"
            "rating 与 sentiment 一致，评价"
            "Grain 正确；正式数值阈值已在 Manifest 冻结；本结果仅为方向诊断。"
        ),
        direction_pass=not failures,
        failure_reason=(
            None
            if not failures
            else "; ".join(failures)
        ),
    )



def _safe_ratio(
    numerator: Any,
    denominator: Any,
) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None

    return round(
        float(numerator) / float(denominator),
        6,
    )


def build_formal_metrics(
    observation: PatternObservation,
) -> dict[str, Any]:
    """
    将各 Pattern 的明细观察结果转换为 Manifest Gate
    可以直接检查的标量指标。
    """
    actual = observation.actual_result
    pattern_id = observation.pattern_id

    if pattern_id == "P01":
        return {
            "no_purchase_customer_share": _safe_ratio(
                actual["no_purchase_customers"],
                actual["total_customers"],
            ),
            "zero_to_two_order_customer_share": actual[
                "zero_to_two_order_customer_share"
            ],
            "ten_plus_order_customer_share": actual[
                "ten_plus_order_customer_share"
            ],
            "top_10_percent_paid_share": actual[
                "top_10_percent_paid_share"
            ],
            "maximum_to_p90_order_count_ratio": _safe_ratio(
                actual["maximum_paid_order_count"],
                actual["p90_paid_order_count"],
            ),
        }

    if pattern_id == "P02":
        return {
            "initial_count_matches_accounts": (
                actual["initial_count"]
                == actual["membership_accounts"]
            ),
            "unchanged_accounts": actual["unchanged_accounts"],
            "accounts_with_upgrade": actual["accounts_with_upgrade"],
            "accounts_with_downgrade": actual["accounts_with_downgrade"],
            "accounts_with_both_directions": actual[
                "accounts_with_both_directions"
            ],
            "transitions_2024": actual["transitions_2024"],
            "transitions_2025": actual["transitions_2025"],
            "transitions_observation_tail": actual[
                "transitions_observation_tail"
            ],
            "all_current_levels_positive": all(
                actual[field] > 0
                for field in (
                    "current_bronze",
                    "current_silver",
                    "current_gold",
                    "current_platinum",
                )
            ),
            "history_and_snapshot_errors_zero": all(
                actual[field] == 0
                for field in (
                    "open_interval_error_count",
                    "overlap_error_count",
                    "snapshot_error_count",
                )
            ),
        }

    if pattern_id == "P03":
        total_members = actual["total_membership_accounts"]
        return {
            "mapped_customer_share": _safe_ratio(
                actual["mapped_customers"],
                actual["total_customers"],
            ),
            "single_channel_member_share": _safe_ratio(
                actual["single_channel_members"],
                total_members,
            ),
            "multi_channel_member_share": _safe_ratio(
                actual["multi_channel_members"],
                total_members,
            ),
            "bound_member_order_share": actual[
                "bound_member_order_share"
            ],
            "required_overlap_cases_present": all(
                actual[field] > 0
                for field in (
                    "customers_without_mapping",
                    "membership_accounts_without_mapping",
                    "paid_customers_without_mapping",
                    "mapped_customers_without_purchase",
                    "membership_accounts_without_purchase",
                    "single_channel_members",
                    "multi_channel_members",
                    "bound_channel_member_orders",
                    "unbound_channel_member_orders",
                )
            ),
            "mapping_and_binding_errors_zero": all(
                actual[field] == 0
                for field in (
                    "members_without_binding",
                    "mapping_open_error_count",
                    "mapping_overlap_count",
                    "binding_overlap_count",
                )
            ),
        }

    if pattern_id == "P04":
        by_channel = actual["by_channel"]
        return {
            "channel_to_brand_new_ratio": actual[
                "channel_to_brand_new_ratio"
            ],
            "channel_new_not_brand_new_share": actual[
                "channel_new_not_brand_new_share"
            ],
            "cross_channel_customer_share": actual[
                "cross_channel_customer_share"
            ],
            "minimum_channel_scope_gap": min(
                row["scope_gap"] for row in by_channel
            ) if by_channel else None,
            "scope_invariants_valid": (
                actual["brand_paid_new_customer_events"]
                == actual["paid_customers"]
                == actual["channel_contributed_brand_new_events"]
                and actual["channel_paid_new_customer_events"]
                == (
                    actual["channel_contributed_brand_new_events"]
                    + actual["channel_new_not_brand_new_events"]
                )
                and all(
                    row["channel_paid_new_customers"]
                    == row["contributed_brand_new_customers"]
                    + row["channel_new_not_brand_new"]
                    for row in by_channel
                )
            ),
            "cross_channel_cases_present": (
                actual["single_channel_paid_customers"] > 0
                and actual["cross_channel_paid_customers"] > 0
                and actual["three_plus_channel_customers"] > 0
                and all(row["scope_gap"] > 0 for row in by_channel)
            ),
        }

    if pattern_id == "P05":
        return {
            "active_product_sales_coverage": actual[
                "active_product_sales_coverage"
            ],
            "active_products_without_sales": actual[
                "active_products_without_sales"
            ],
            "maximum_to_median_quantity_ratio": actual[
                "maximum_to_median_quantity_ratio"
            ],
            "top_10_percent_quantity_share": actual[
                "top_10_percent_quantity_share"
            ],
            "top_10_percent_gmv_share": actual[
                "top_10_percent_gmv_share"
            ],
            "top_10_percent_margin_share": actual[
                "top_10_percent_margin_share"
            ],
            "quantity_gmv_rank_not_identical": not actual[
                "quantity_gmv_top10_exact_order_match"
            ],
            "gmv_margin_rank_not_identical": not actual[
                "gmv_margin_top10_exact_order_match"
            ],
            "category_count": len(actual["by_category"]),
        }

    if pattern_id == "P06":
        return {
            "sunscreen_peak_ratio": actual["sunscreen_peak_ratio"],
            "skincare_winter_ratio": actual["skincare_winter_ratio"],
            "sunscreen_region_ratio": actual["sunscreen_region_ratio"],
            "skincare_region_ratio": actual["skincare_region_ratio"],
            "sunscreen_nonzero_months": actual[
                "sunscreen_nonzero_months"
            ],
            "skincare_nonzero_months": actual[
                "skincare_nonzero_months"
            ],
            "all_region_groups_nonzero": all(
                row["sunscreen_quantity"] not in (None, 0)
                and row["skincare_quantity"] not in (None, 0)
                for row in actual["by_region_group"]
            ),
        }

    if pattern_id == "P07":
        channel_count = actual["direct_response_channel_count"]
        by_channel = actual["by_channel"]
        return {
            "direct_response_channel_count": channel_count,
            "minimum_observation_days": min(
                row["observation_days"] for row in by_channel
            ) if by_channel else None,
            "minimum_spend_order_correlation": min(
                row["spend_order_correlation"] for row in by_channel
            ) if by_channel else None,
            "minimum_spend_channel_new_correlation": min(
                row["spend_channel_new_correlation"] for row in by_channel
            ) if by_channel else None,
            "high_spend_more_orders_share": _safe_ratio(
                actual["channels_high_spend_more_orders"],
                channel_count,
            ),
            "strict_order_diminishing_share": _safe_ratio(
                actual["channels_strict_order_diminishing"],
                channel_count,
            ),
            "order_within_noise_tolerance_share": _safe_ratio(
                actual["channels_order_within_noise_tolerance"],
                channel_count,
            ),
            "high_spend_more_channel_new_share": _safe_ratio(
                actual["channels_high_spend_more_channel_new"],
                channel_count,
            ),
            "channel_new_diminishing_share": _safe_ratio(
                actual["channels_channel_new_diminishing"],
                channel_count,
            ),
            "gmv_roi_decline_share": _safe_ratio(
                actual["channels_gmv_roi_decline"],
                channel_count,
            ),
            "maximum_order_efficiency_retention": max(
                row["order_efficiency_retention_ratio"]
                for row in by_channel
            ) if by_channel else None,
            "order_response_curve_spread": actual[
                "order_response_curve_spread"
            ],
            "marketing_only_channel_count": len(
                actual["excluded_marketing_only_channels"]
            ),
        }

    if pattern_id == "P08":
        comparable_products = actual["comparable_products"]
        return {
            "promotion_count_with_sales": actual[
                "promotion_count_with_sales"
            ],
            "promoted_margin_rate": actual["promoted_margin_rate"],
            "non_promoted_margin_rate": actual[
                "non_promoted_margin_rate"
            ],
            "margin_rate_gap": round(
                actual["non_promoted_margin_rate"]
                - actual["promoted_margin_rate"],
                6,
            ),
            "discount_depth_margin_rate_correlation": actual[
                "discount_depth_margin_rate_correlation"
            ],
            "product_tradeoff_share": _safe_ratio(
                actual["products_quantity_up_margin_rate_down"],
                comparable_products,
            ),
            "normalized_tradeoff_present": (
                actual[
                    "highest_quantity_per_active_day_promotion"
                ]
                != actual[
                    "highest_gross_margin_rate_promotion"
                ]
                and actual["deepest_discount_promotion"]
                != actual[
                    "highest_gross_margin_rate_promotion"
                ]
            ),
            "formula_and_contract_errors_zero": all(
                actual[field] == 0
                for field in (
                    "formula_error_count",
                    "promotion_pricing_date_window_error_count",
                    "promotion_target_level_error_count",
                )
            ),
        }

    if pattern_id == "P09":
        return {
            "compared_products": actual["compared_products"],
            "completed_refund_average_rating": actual[
                "completed_refund_average_rating"
            ],
            "no_refund_average_rating": actual[
                "no_refund_average_rating"
            ],
            "refund_no_refund_rating_gap": round(
                actual["no_refund_average_rating"]
                - actual["completed_refund_average_rating"],
                6,
            ),
            "low_rating_completed_refund_rate": actual[
                "low_rating_completed_refund_rate"
            ],
            "high_rating_completed_refund_rate": actual[
                "high_rating_completed_refund_rate"
            ],
            "product_rating_refund_correlation": actual[
                "product_rating_refund_correlation"
            ],
            "product_rating_refund_rank_correlation": actual[
                "product_rating_refund_rank_correlation"
            ],
            "low_to_high_rating_quartile_refund_ratio": actual[
                "low_to_high_rating_quartile_refund_ratio"
            ],
            "nonmechanical_cases_present": all(
                actual[field] > 0
                for field in (
                    "low_rating_with_completed_refund",
                    "low_rating_without_completed_refund",
                    "high_rating_with_completed_refund",
                    "completed_refund_without_review",
                    "no_refund_no_review",
                    "reviewed_without_refund",
                )
            ),
            "review_integrity_errors_zero": all(
                actual[field] == 0
                for field in (
                    "sentiment_rating_error_count",
                    "duplicate_review_items",
                )
            ),
        }

    raise ValueError(
        f"不支持的 Pattern ID：{pattern_id}"
    )


def evaluate_check(
    actual_value: Any,
    check: dict[str, Any],
) -> tuple[bool, str | None]:
    operator = check["operator"]

    if actual_value is None:
        return False, "actual value is null"

    if operator == "between":
        minimum = check["minimum"]
        maximum = check["maximum"]
        passed = minimum <= actual_value <= maximum
        reason = (
            None
            if passed
            else (
                f"expected {minimum} <= actual <= {maximum}, "
                f"actual={actual_value}"
            )
        )
        return passed, reason

    if operator == "minimum":
        minimum = check["minimum"]
        passed = actual_value >= minimum
        return (
            passed,
            None if passed else f"expected actual >= {minimum}, actual={actual_value}",
        )

    if operator == "maximum":
        maximum = check["maximum"]
        passed = actual_value <= maximum
        return (
            passed,
            None if passed else f"expected actual <= {maximum}, actual={actual_value}",
        )

    if operator == "equals":
        expected = check["expected"]
        passed = actual_value == expected
        return (
            passed,
            None if passed else f"expected actual == {expected!r}, actual={actual_value!r}",
        )

    if operator == "not_equals":
        expected = check["expected"]
        passed = actual_value != expected
        return (
            passed,
            None if passed else f"expected actual != {expected!r}, actual={actual_value!r}",
        )

    return False, f"unsupported operator: {operator}"


def evaluate_pattern_acceptance(
    observation: PatternObservation,
    pattern_contract: dict[str, Any],
) -> dict[str, Any]:
    formal_metrics = build_formal_metrics(observation)
    check_results: list[dict[str, Any]] = []
    failures: list[str] = []

    if not observation.direction_pass:
        failures.append(
            "direction observation failed: "
            f"{observation.failure_reason}"
        )

    for check in pattern_contract["checks"]:
        metric = check["metric"]
        actual_value = formal_metrics.get(metric)
        passed, reason = evaluate_check(actual_value, check)

        check_result = {
            "check_id": check["check_id"],
            "metric": metric,
            "operator": check["operator"],
            "actual": actual_value,
            "pass": passed,
        }

        for field in ("minimum", "maximum", "expected"):
            if field in check:
                check_result[field] = check[field]

        if reason is not None:
            check_result["failure_reason"] = reason
            failures.append(
                f"{check['check_id']}: {reason}"
            )

        check_results.append(check_result)

    return {
        "pattern_id": observation.pattern_id,
        "validator_name": observation.validator_name,
        "actual_result": {
            "formal_metrics": to_json_value(formal_metrics),
            "observation": observation.actual_result,
        },
        "expected_condition": pattern_contract["checks"],
        "check_results": check_results,
        "pass": not failures,
        "failure_reason": (
            None if not failures else "; ".join(failures)
        ),
    }


def run_acceptance(
    output_json: bool,
) -> int:
    manifest = load_and_validate_day66_manifest()
    contract = manifest["business_pattern_acceptance"]

    if TARGET_SCHEMA != contract["target_schema"]:
        raise RuntimeError(
            "Observer TARGET_SCHEMA 与 Manifest Acceptance "
            "Contract 不一致。"
        )

    with engine.connect() as connection:
        table_counts = validate_p01_preflight(connection)
        observations = [
            observe_p01(connection),
            observe_p02(connection),
            observe_p03(connection),
            observe_p04(connection),
            observe_p05(connection),
            observe_p06(connection),
            observe_p07(connection),
            observe_p08(connection),
            observe_p09(connection),
        ]

    results = [
        evaluate_pattern_acceptance(
            observation,
            contract["patterns"][observation.pattern_id],
        )
        for observation in observations
    ]

    passed_count = sum(result["pass"] for result in results)
    all_passed = passed_count == len(results)

    payload = {
        "mode": "formal_acceptance",
        "target_schema": TARGET_SCHEMA,
        "scale_profile": contract["scale_profile"],
        "contract_version": contract["contract_version"],
        "table_counts": table_counts,
        "final_thresholds_frozen": contract["thresholds_frozen"],
        "business_pattern_acceptance_pass": all_passed,
        "dataset_candidate_eligible": False,
        "candidate_block_reason": (
            "Metadata alignment, Golden Cases, Performance baseline "
            "and Dataset V2 AI-chain regression are not completed."
        ),
        "results": results,
    }

    if output_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if all_passed else 1

    print("Beauty BI V2 Day66 P01-P09 formal acceptance started.")
    print("Mode: formal_acceptance")
    print(f"Target schema: {TARGET_SCHEMA}")
    print(f"Scale profile: {contract['scale_profile']}")
    print(f"Contract version: {contract['contract_version']}")
    print(f"Table counts: {table_counts}")
    print()

    for result in results:
        status = "PASS" if result["pass"] else "FAIL"
        print(
            f"[{result['pattern_id']}] "
            f"{result['validator_name']}: {status}"
        )
        print(
            "formal_metrics="
            + json.dumps(
                result["actual_result"]["formal_metrics"],
                ensure_ascii=False,
                indent=2,
            )
        )
        print(
            "check_results="
            + json.dumps(
                result["check_results"],
                ensure_ascii=False,
                indent=2,
            )
        )
        if result["failure_reason"]:
            print(
                "failure_reason="
                f"{result['failure_reason']}"
            )
        print()

    print(
        "Formal acceptance summary: "
        f"{passed_count}/{len(results)} patterns passed."
    )
    print(
        "Business pattern acceptance: "
        + ("PASS" if all_passed else "FAIL")
    )
    print("Dataset candidate eligibility: NO")
    print(
        "Candidate block reason: Metadata alignment, Golden Cases, "
        "Performance baseline and Dataset V2 AI-chain regression "
        "are not completed."
    )
    print("Database writes performed: 0")

    return 0 if all_passed else 1


def run_observation(
    output_json: bool,
) -> int:
    with engine.connect() as connection:
        table_counts = validate_p01_preflight(
            connection
        )
        results = [
            observe_p01(connection),
            observe_p02(connection),
            observe_p03(connection),
            observe_p04(connection),
            observe_p05(connection),
            observe_p06(connection),
            observe_p07(connection),
            observe_p08(connection),
            observe_p09(connection),
        ]

    payload = {
        "mode": "observation",
        "target_schema": TARGET_SCHEMA,
        "table_counts": table_counts,
        "final_thresholds_frozen": True,
        "dataset_candidate_eligible": False,
        "results": [
            to_json_value(asdict(result))
            for result in results
        ],
    }

    if output_json:
        print(
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    print(
        "Beauty BI V2 Day66 "
        "P01-P09 observation started."
    )
    print(
        "Mode: observation "
        "(thresholds frozen; not final acceptance)"
    )
    print(
        f"Target schema: {TARGET_SCHEMA}"
    )
    print(
        f"Table counts: {table_counts}"
    )
    print()

    for result in results:
        status = (
            "DIRECTION PASS"
            if result.direction_pass
            else "DIRECTION FAIL"
        )

        print(
            f"[{result.pattern_id}] "
            f"{result.validator_name}: "
            f"{status}"
        )
        print(
            "actual_result="
            + json.dumps(
                result.actual_result,
                ensure_ascii=False,
                indent=2,
            )
        )
        print(
            "expected_condition="
            f"{result.expected_condition}"
        )

        if result.failure_reason:
            print(
                "failure_reason="
                f"{result.failure_reason}"
            )

        print()

    passed_count = sum(
        result.direction_pass
        for result in results
    )

    print(
        "Observation summary: "
        f"{passed_count}/{len(results)} "
        "direction checks passed."
    )
    print(
        "Final P01-P09 acceptance: "
        "NOT RUN."
    )
    print(
        "Dataset candidate eligibility: NO."
    )
    print(
        "Database writes performed: 0"
    )

    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate Beauty BI Dataset V2 "
            "P01-P09 business patterns."
        )
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="输出 JSON 格式结果。",
    )

    parser.add_argument(
        "--observation",
        action="store_true",
        help=(
            "只运行方向观察，不执行 Manifest "
            "正式阈值 Gate。"
        ),
    )

    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    if args.observation:
        raise SystemExit(
            run_observation(
                output_json=args.json,
            )
        )

    raise SystemExit(
        run_acceptance(
            output_json=args.json,
        )
    )
