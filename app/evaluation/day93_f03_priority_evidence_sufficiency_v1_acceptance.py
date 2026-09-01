from __future__ import annotations

from decimal import Decimal

from app.delivery.decision_console_runtime_v2 import (
    _is_day93_refund_category_priority_question_v1,
)
from app.delivery.ranking_answer_delivery_v1 import (
    resolve_priority_intent_v1,
    select_refund_rate_priority_candidates_v1,
)


F03 = (
    "2025年各品类退款率中，哪个最值得优先关注？"
    "目前的数据能确认什么，不能确认什么？"
)


def run_acceptance() -> None:
    passed = 0

    assert resolve_priority_intent_v1(F03)
    passed += 1

    assert not resolve_priority_intent_v1(
        "2025年哪个品类退款率最高？"
    )
    passed += 1

    assert _is_day93_refund_category_priority_question_v1(
        F03
    )
    passed += 1

    assert not _is_day93_refund_category_priority_question_v1(
        "2025年哪个品类退款率最高？"
    )
    passed += 1

    selected = select_refund_rate_priority_candidates_v1(
        rows=(
            {
                "category": "彩妆",
                "refund_rate": Decimal("0.0771"),
            },
            {
                "category": "护肤",
                "refund_rate": Decimal("0.0758"),
            },
            {
                "category": "防晒",
                "refund_rate": Decimal("0.0745"),
            },
        ),
    )

    assert selected == (
        ("彩妆",),
        Decimal("0.0771"),
    )
    passed += 1

    tie = select_refund_rate_priority_candidates_v1(
        rows=(
            {
                "category": "彩妆",
                "refund_rate": Decimal("0.08"),
            },
            {
                "category": "护肤",
                "refund_rate": Decimal("0.08"),
            },
        ),
    )

    assert tie == (
        ("彩妆", "护肤"),
        Decimal("0.08"),
    )
    passed += 1

    print(
        "Day93 F03 Priority + Evidence Sufficiency V1 "
        f"Acceptance: {passed}/6 PASS"
    )


if __name__ == "__main__":
    run_acceptance()
