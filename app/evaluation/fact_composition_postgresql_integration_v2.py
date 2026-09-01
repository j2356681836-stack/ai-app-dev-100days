from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.delivery.decision_console_runtime_v2 import (
    run_day89_local_investigation_v2,
)
from app.delivery.fact_composition_delivery_v2 import (
    FactCompositionDimensionV2,
    FactCompositionReconciliationStatusV2,
    FactCompositionStatusV2,
    fact_composition_available_dimensions_v2,
    run_day93_fact_composition_v2,
)
from app.delivery.runtime_delivery_bridge_v2 import (
    RuntimeDeliveryBridgeStatusV2,
)
from app.semantic_layer.analysis_mode_contract_v2 import (
    AnalysisModeV2,
)


QUESTION = "2025年上海地区GMV是多少？"
REFERENCE_DATE = date(2026, 8, 28)


def main() -> None:
    seed = run_day89_local_investigation_v2(
        question=QUESTION,
        reference_date=REFERENCE_DATE,
    )

    assert seed.status == RuntimeDeliveryBridgeStatusV2.READY, seed.message
    assert seed.requested_analysis_mode == AnalysisModeV2.FACT
    assert seed.requested_scope is not None
    assert seed.requested_scope.region_codes == frozenset({"SHANGHAI"})

    available = fact_composition_available_dimensions_v2(seed)
    assert available == (
        FactCompositionDimensionV2.CHANNEL,
        FactCompositionDimensionV2.CATEGORY,
    )

    results = [
        run_day93_fact_composition_v2(
            seed_result=seed,
            dimension=dimension,
        )
        for dimension in available
    ]

    for result in results:
        assert result.status == FactCompositionStatusV2.READY, result.message
        assert result.members
        assert result.released_row_count == len(result.members)
        assert (
            result.reconciliation_status
            == FactCompositionReconciliationStatusV2.RECONCILED
        )
        assert result.unexplained_remainder is not None
        assert abs(result.unexplained_remainder) <= Decimal("0.01")
        assert "SHANGHAI" in (result.scope_summary or "")

    channel, category = results

    assert channel.overall_value == category.overall_value
    assert channel.member_sum == channel.overall_value
    assert category.member_sum == category.overall_value

    print("PASS: 上海 Fact Seed = FACT + Requested Region SHANGHAI")
    print(
        "PASS: 可用构成维度 = channel + category；"
        "没有重复 region drill"
    )
    print(
        f"PASS: 渠道完整成员数 = {channel.released_row_count}; "
        "与 Overall 已对账"
    )
    print(
        f"PASS: 品类完整成员数 = {category.released_row_count}; "
        "与 Overall 已对账"
    )
    print("PASS: 两个独立维度反向验证同一个 Overall GMV")
    print("=" * 72)
    print("Fact Composition PostgreSQL Integration passed.")


if __name__ == "__main__":
    main()
