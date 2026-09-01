from __future__ import annotations

from decimal import Decimal

from app.ui.decision_console_presenters_v2 import (
    build_chart_rows_v2,
    build_display_rows_v2,
    format_metric_name_v2,
)


def run_acceptance() -> None:
    passed = 0

    assert format_metric_name_v2("order_count") == "订单数"
    assert format_metric_name_v2("buyer_count") == "购买人数"
    assert format_metric_name_v2("refund_rate") == "退款率"
    passed += 1

    order_rows = build_display_rows_v2(
        (
            {
                "channel_name": "天猫旗舰店",
                "order_count": Decimal("4658"),
            },
        )
    )
    assert order_rows == [
        {
            "渠道": "天猫旗舰店",
            "订单数": "4,658",
        }
    ]
    passed += 1

    buyer_rows = build_display_rows_v2(
        (
            {
                "channel_name": "天猫旗舰店",
                "buyer_count": Decimal("2290"),
            },
        )
    )
    assert buyer_rows == [
        {
            "渠道": "天猫旗舰店",
            "购买人数": "2,290",
        }
    ]
    passed += 1

    refund_rows = build_display_rows_v2(
        (
            {
                "channel_name": "天猫旗舰店",
                "refund_rate": Decimal("0.1234"),
            },
        )
    )
    assert refund_rows == [
        {
            "渠道": "天猫旗舰店",
            "退款率": "12.34%",
        }
    ]
    passed += 1

    order_chart = build_chart_rows_v2(
        (
            {
                "channel_name": "天猫旗舰店",
                "order_count": Decimal("4658"),
            },
        )
    )
    assert order_chart == [
        {
            "渠道": "天猫旗舰店",
            "订单数": 4658.0,
        }
    ]
    passed += 1

    buyer_chart = build_chart_rows_v2(
        (
            {
                "channel_name": "天猫旗舰店",
                "buyer_count": Decimal("2290"),
            },
        )
    )
    assert buyer_chart == [
        {
            "渠道": "天猫旗舰店",
            "购买人数": 2290.0,
        }
    ]
    passed += 1

    print(
        "Day93 Business Metric Naming Repair Acceptance: "
        f"{passed}/6 PASS"
    )


if __name__ == "__main__":
    run_acceptance()
