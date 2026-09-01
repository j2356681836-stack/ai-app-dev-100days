from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import yaml

from app.delivery.ranking_answer_delivery_v1 import (
    MetricRankingPreferenceV1,
    RankingIntentV1,
    RankingSelectionDirectionV1,
    _selection_direction_v1,
    load_metric_ranking_preference_v1,
    resolve_ranking_intent_v1,
)
from app.ui.decision_console_presenters_v2 import (
    build_display_rows_v2,
    format_business_metric_value_v2,
    format_metric_name_v2,
)


def run_acceptance() -> None:
    passed = 0

    assert (
        resolve_ranking_intent_v1(
            "2025年哪一个渠道表现最好？"
        )
        == RankingIntentV1.BEST
    )
    assert (
        resolve_ranking_intent_v1(
            "2025年哪个品类退款率最高？"
        )
        == RankingIntentV1.HIGHEST
    )
    assert (
        resolve_ranking_intent_v1(
            "2025年哪个渠道退款率最低？"
        )
        == RankingIntentV1.LOWEST
    )
    passed += 1

    metadata = yaml.safe_load(
        open(
            "metadata/beauty_bi_v2/business_metrics.yaml",
            "r",
            encoding="utf-8",
        )
    )

    assert (
        load_metric_ranking_preference_v1(
            metadata_catalog=metadata,
            metric_name="gmv",
        )
        == MetricRankingPreferenceV1.HIGHER_IS_BETTER
    )
    assert (
        load_metric_ranking_preference_v1(
            metadata_catalog=metadata,
            metric_name="refund_rate",
        )
        == MetricRankingPreferenceV1.LOWER_IS_BETTER
    )
    passed += 1

    assert (
        _selection_direction_v1(
            intent=RankingIntentV1.BEST,
            preference=MetricRankingPreferenceV1.HIGHER_IS_BETTER,
        )
        == RankingSelectionDirectionV1.MAX
    )
    assert (
        _selection_direction_v1(
            intent=RankingIntentV1.BEST,
            preference=MetricRankingPreferenceV1.LOWER_IS_BETTER,
        )
        == RankingSelectionDirectionV1.MIN
    )
    assert (
        _selection_direction_v1(
            intent=RankingIntentV1.HIGHEST,
            preference=MetricRankingPreferenceV1.LOWER_IS_BETTER,
        )
        == RankingSelectionDirectionV1.MAX
    )
    passed += 1

    assert format_metric_name_v2("gmv") == "GMV"
    assert format_metric_name_v2("order_count") == "订单数"
    assert format_metric_name_v2("buyer_count") == "购买人数"
    passed += 1

    rows = build_display_rows_v2(
        (
            {
                "channel_name": "天猫旗舰店",
                "gmv": Decimal("2586549.37"),
            },
        )
    )
    assert rows == [
        {
            "渠道": "天猫旗舰店",
            "GMV": "2,586,549.37",
        }
    ]
    passed += 1

    assert (
        format_business_metric_value_v2(
            "order_count",
            Decimal("4658"),
        )
        == "4,658"
    )
    assert (
        format_business_metric_value_v2(
            "refund_rate",
            Decimal("0.1234"),
        )
        == "12.34%"
    )
    passed += 1

    order_metric = next(
        item
        for item in metadata["metrics"]
        if item["name"] == "order_count"
    )
    assert order_metric["chinese_name"] == "订单数"
    assert "交易量" in order_metric["aliases"]
    passed += 1

    print(
        "Day93 Ranking Answer Delivery V1 Acceptance: "
        f"{passed}/7 PASS"
    )


if __name__ == "__main__":
    run_acceptance()
