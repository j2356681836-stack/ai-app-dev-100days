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


def main() -> None:
    print("=" * 96)
    print("Day93 F01 Full Composition PostgreSQL Verification")

    seed = run_day89_local_investigation_v2(
        question="2025年一共有多少笔成功支付订单？",
        reference_date=date.today(),
    )

    print("Seed status:", seed.status.value)

    assert seed.status == RuntimeDeliveryBridgeStatusV2.READY
    assert seed.console_view is not None
    assert seed.console_view.fact_metric is not None

    fact = seed.console_view.fact_metric

    print(
        "Seed:",
        fact.metric_name,
        fact.value,
        fact.analysis_window,
    )

    assert fact.metric_name == "order_count"

    available = fact_composition_available_dimensions_v2(
        seed
    )

    print(
        "Available:",
        [item.value for item in available],
    )

    assert available == (
        FactCompositionDimensionV2.PEOPLE,
        FactCompositionDimensionV2.CHANNEL,
        FactCompositionDimensionV2.REGION,
    )

    results = []

    for dimension in available:
        result = run_day93_fact_composition_v2(
            seed_result=seed,
            dimension=dimension,
        )
        results.append(result)

        print("-" * 96)
        print(
            dimension.value,
            "status=",
            result.status.value,
            "plan=",
            result.plan_name,
        )

        for member in result.members:
            print(
                member.rank,
                member.member_label,
                member.value,
                member.share,
            )

        print(
            "overall=",
            result.overall_value,
            "member_sum=",
            result.member_sum,
            "remainder=",
            result.unexplained_remainder,
            "reconciliation=",
            (
                result.reconciliation_status.value
                if result.reconciliation_status is not None
                else None
            ),
        )

        assert result.status == FactCompositionStatusV2.READY
        assert result.overall_value == fact.value
        assert (
            result.reconciliation_status
            == FactCompositionReconciliationStatusV2.RECONCILED
        )

    people = results[0]

    assert [
        member.member_label
        for member in people.members
    ] == [
        "OLD_PLATINUM",
        "OLD_GOLD",
        "OLD_SILVER",
        "OLD_BRONZE",
        "OLD_NON_MEMBER",
        "NEW_CUSTOMER",
    ]

    assert people.ranking_summary_enabled is False

    print("=" * 96)
    print("F01 Full Composition PostgreSQL Verification completed.")


if __name__ == "__main__":
    main()
