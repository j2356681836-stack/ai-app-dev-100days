from __future__ import annotations

from datetime import date

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

    assert (
        seed.status
        == RuntimeDeliveryBridgeStatusV2.READY
    ), seed.message
    assert seed.requested_analysis_mode == AnalysisModeV2.FACT
    assert seed.requested_scope is not None
    assert (
        seed.requested_scope.region_codes
        == frozenset({"SHANGHAI"})
    )

    available = fact_composition_available_dimensions_v2(
        seed
    )

    assert available == (
        FactCompositionDimensionV2.PEOPLE,
        FactCompositionDimensionV2.CHANNEL,
        FactCompositionDimensionV2.CATEGORY,
    )

    results = {
        dimension: run_day93_fact_composition_v2(
            seed_result=seed,
            dimension=dimension,
        )
        for dimension in available
    }

    for dimension, result in results.items():
        assert (
            result.status
            == FactCompositionStatusV2.READY
        ), (
            f"{dimension.value}: {result.message}"
        )
        assert result.members
        assert (
            result.released_row_count
            == len(result.members)
        )
        assert (
            result.reconciliation_status
            == FactCompositionReconciliationStatusV2.RECONCILED
        ), (
            f"{dimension.value}: "
            f"remainder={result.unexplained_remainder}"
        )
        assert "SHANGHAI" in (
            result.scope_summary or ""
        )

    people = results[FactCompositionDimensionV2.PEOPLE]
    channel = results[FactCompositionDimensionV2.CHANNEL]
    category = results[FactCompositionDimensionV2.CATEGORY]

    assert (
        people.overall_value
        == channel.overall_value
        == category.overall_value
    )

    assert people.member_sum == people.overall_value
    assert channel.member_sum == channel.overall_value
    assert category.member_sum == category.overall_value

    people_labels = {
        item.member_label
        for item in people.members
    }
    assert "NON_MEMBER" in people_labels

    print("PASS: 上海 Fact Seed = FACT + Requested Region SHANGHAI")
    print(
        "PASS: 可用构成维度 = 人 / 场 / 货；"
        "没有重复 Region 构成"
    )
    print(
        f"PASS: 人｜支付时会员构成成员数 = "
        f"{people.released_row_count}"
    )
    print(
        f"PASS: 场｜渠道构成成员数 = "
        f"{channel.released_row_count}"
    )
    print(
        f"PASS: 货｜品类构成成员数 = "
        f"{category.released_row_count}"
    )
    print("PASS: 人 / 货 / 场三维均与同一 Overall GMV 对账")
    print("=" * 72)
    print(
        "Fact People Composition PostgreSQL Integration passed."
    )


if __name__ == "__main__":
    main()
