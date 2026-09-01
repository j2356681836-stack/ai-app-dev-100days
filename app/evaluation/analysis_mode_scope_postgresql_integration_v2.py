from __future__ import annotations

from datetime import date

from app.agents.investigation_contracts_v2 import AnalysisModeV2
from app.delivery.decision_console_runtime_v2 import (
    run_day89_local_investigation_v2,
)
from app.delivery.investigation_runtime_v2 import (
    build_day89_gmv_investigation_actions_v2,
)
from app.delivery.runtime_delivery_bridge_v2 import (
    RuntimeDeliveryBridgeStatusV2,
)


def main() -> None:
    seed = run_day89_local_investigation_v2(
        question="2025年上海地区GMV是多少？",
        reference_date=date.today(),
    )

    if seed.status != RuntimeDeliveryBridgeStatusV2.READY:
        raise AssertionError(
            f"Shanghai seed must be READY: {seed.status.value}; "
            f"{seed.message}"
        )

    if seed.requested_analysis_mode != AnalysisModeV2.FACT:
        raise AssertionError(
            "Shanghai GMV quick fact must resolve to FACT."
        )

    if (
        seed.requested_scope is None
        or "SHANGHAI"
        not in seed.requested_scope.region_codes
    ):
        raise AssertionError(
            "Shanghai Requested Scope must stay server-trusted."
        )

    actions = build_day89_gmv_investigation_actions_v2(
        delivery=seed.delivery,
        requested_scope=seed.requested_scope,
        include_category=True,
    )

    action_ids = tuple(
        action.action_id
        for action in actions
    )

    if "drill_region" in action_ids:
        raise AssertionError(
            "Region is already locked to SHANGHAI; "
            "drill_region must be removed."
        )

    if "drill_channel" not in action_ids:
        raise AssertionError(
            "Channel should remain a legal deeper dimension."
        )

    if "drill_category" not in action_ids:
        raise AssertionError(
            "Category should remain a legal deeper dimension."
        )

    print("Day93 Analysis Mode + Scope PostgreSQL Integration: PASS")
    print("Requested Analysis Mode: fact")
    print("Requested Region Scope: SHANGHAI")
    print(f"Remaining governed actions: {action_ids}")


if __name__ == "__main__":
    main()
