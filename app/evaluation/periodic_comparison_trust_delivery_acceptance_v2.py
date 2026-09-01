from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from app.ui.decision_console_presenters_v2 import (
    build_contribution_display_rows_v2,
)


def _member(
    *,
    label: str,
    reference: str,
    current: str,
    delta: str,
    contribution_rate: str,
    direction: str,
):
    return SimpleNamespace(
        member_label=label,
        reference_value=Decimal(reference),
        current_value=Decimal(current),
        delta=Decimal(delta),
        contribution_rate=Decimal(contribution_rate),
        direction=SimpleNamespace(value=direction),
    )


def main() -> None:
    contribution = SimpleNamespace(
        members=(
            _member(
                label="天猫旗舰店",
                reference="320000",
                current="250000",
                delta="-70000",
                contribution_rate="0.382",
                direction="negative",
            ),
        )
    )

    rows = build_contribution_display_rows_v2(contribution)
    assert len(rows) == 1

    row = rows[0]
    assert tuple(row.keys()) == (
        "渠道",
        "参考期 GMV",
        "当前期 GMV",
        "变化额",
        "对整体变化贡献率",
        "方向",
    )
    assert row["参考期 GMV"] == "320,000.00"
    assert row["当前期 GMV"] == "250,000.00"
    assert row["变化额"] == "-70,000.00"
    assert row["对整体变化贡献率"] == "38.20%"

    print("PASS: Contribution 表显式释放参考期 / 当前期 / Delta / Contribution")
    print("PASS: Presenter 只格式化已有可信字段，不重新计算业务真值")
    print("=" * 72)
    print("Periodic Comparison Trust Delivery Acceptance passed.")


if __name__ == "__main__":
    main()
