from datetime import date

from app.delivery.business_period_label_v2 import (
    format_business_period_label_v2,
)
from app.semantic_layer.time_comparison_contract_v2 import (
    TimeWindowReferenceV2,
)


def test_full_month_uses_business_month_label() -> None:
    label = format_business_period_label_v2(
        TimeWindowReferenceV2(
            start_date=date(2025, 10, 1),
            end_date=date(2025, 10, 31),
        )
    )
    assert label == "2025年10月"
    print("PASS: test_full_month_uses_business_month_label")


def test_non_month_window_keeps_explicit_dates() -> None:
    label = format_business_period_label_v2(
        TimeWindowReferenceV2(
            start_date=date(2025, 10, 1),
            end_date=date(2025, 10, 7),
        )
    )
    assert label == "2025-10-01 至 2025-10-07"
    print("PASS: test_non_month_window_keeps_explicit_dates")


def main() -> None:
    test_full_month_uses_business_month_label()
    test_non_month_window_keeps_explicit_dates()


if __name__ == "__main__":
    main()
