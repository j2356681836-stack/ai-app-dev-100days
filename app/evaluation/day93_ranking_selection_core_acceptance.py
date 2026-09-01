from __future__ import annotations

from decimal import Decimal

from app.delivery.ranking_answer_delivery_v1 import (
    RankingSelectionDirectionV1,
)


def _winner(
    rows,
    *,
    direction: RankingSelectionDirectionV1,
):
    values = tuple(Decimal(str(row[1])) for row in rows)
    target = (
        max(values)
        if direction == RankingSelectionDirectionV1.MAX
        else min(values)
    )
    return tuple(
        label
        for label, raw in rows
        if Decimal(str(raw)) == target
    ), target


def run_acceptance() -> None:
    passed = 0

    channels = (
        ("天猫旗舰店", "2586549.37"),
        ("抖音商城", "2465984.60"),
        ("京东旗舰店", "2179425.68"),
    )

    winners, value = _winner(
        channels,
        direction=RankingSelectionDirectionV1.MAX,
    )
    assert winners == ("天猫旗舰店",)
    assert value == Decimal("2586549.37")
    passed += 1

    refund = (
        ("A", "0.08"),
        ("B", "0.05"),
        ("C", "0.12"),
    )
    winners, value = _winner(
        refund,
        direction=RankingSelectionDirectionV1.MIN,
    )
    assert winners == ("B",)
    assert value == Decimal("0.05")
    passed += 1

    tie = (
        ("A", "100"),
        ("B", "100"),
        ("C", "90"),
    )
    winners, value = _winner(
        tie,
        direction=RankingSelectionDirectionV1.MAX,
    )
    assert winners == ("A", "B")
    assert value == Decimal("100")
    passed += 1

    print(
        "Day93 Ranking Selection Core Acceptance: "
        f"{passed}/3 PASS"
    )


if __name__ == "__main__":
    run_acceptance()
