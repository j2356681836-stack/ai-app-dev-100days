from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from app.agents.investigation_contracts_v2 import (
    ToolContractV2,
    ToolFailureCodeV2,
    ToolIdentityV2,
)
from app.delivery.runtime_delivery_bridge_v2 import (
    ApprovedGovernedQueryToolBindingV2,
    RuntimeDeliveryBridgeStatusV2,
    invoke_governed_graph_delivery_v2,
)
from app.evaluation.business_decision_observed_postgresql_v2 import (
    EXECUTION_POLICY,
    _integration_context,
    _runtime_config,
)


QUESTION = "2025年各渠道 GMV 是多少？"
REFERENCE_DATE = date(2026, 8, 18)
FIXED_TIME = datetime(
    2026,
    8,
    19,
    9,
    30,
    tzinfo=timezone.utc,
)


def _approved_binding() -> ApprovedGovernedQueryToolBindingV2:
    tool = ToolContractV2(
        identity=ToolIdentityV2(
            name="governed_gmv_channel_query",
            version="dataset_v2",
            purpose="查询授权范围内的渠道 GMV。",
        ),
        input_schema_name="GovernedInvestigationInputV2",
        output_schema_name="GovernedFinalizationResult",
        required_permissions=(
            "metric_access",
            "data_scope",
        ),
        execution_policy_reference=(
            "governed_execution_policy_v2"
        ),
        failure_semantics=(
            ToolFailureCodeV2.INVALID_INPUT,
            ToolFailureCodeV2.UNAUTHORIZED,
            ToolFailureCodeV2.UNSUPPORTED,
            ToolFailureCodeV2.TIMEOUT,
            ToolFailureCodeV2.NO_DATA,
            ToolFailureCodeV2.EXECUTION_FAILURE,
        ),
        executor_binding="execute_governed_query_v2",
    )

    return ApprovedGovernedQueryToolBindingV2(
        plan_name="gmv_channel_v2",
        tool_contract=tool,
    )


def test_real_graph_builds_day89_delivery() -> None:
    context = _integration_context()

    with TemporaryDirectory() as tmp:
        audit_path = (
            Path(tmp)
            / "day89_runtime_delivery_bridge_audit.jsonl"
        )

        result = invoke_governed_graph_delivery_v2(
            context=context,
            question=QUESTION,
            reference_date=REFERENCE_DATE,
            runtime_config=_runtime_config(audit_path),
            approved_tool_binding=_approved_binding(),
            execution_policy=EXECUTION_POLICY,
            event_id="day89-runtime-delivery-bridge-001",
            occurred_at_utc=FIXED_TIME,
            written_at_utc=FIXED_TIME,
        )

        assert result.status == RuntimeDeliveryBridgeStatusV2.READY
        assert result.delivery is not None
        assert result.console_view is not None
        assert result.executive_brief is not None

        delivery = result.delivery
        view = result.console_view
        brief = result.executive_brief

        assert delivery.evidence_pack.analysis_scope.metric_name == "gmv"
        assert delivery.evidence_pack.analysis_scope.result_grain == "channel"
        assert len(delivery.evidence_pack.evidence_records) == 1

        record = delivery.evidence_pack.evidence_records[0]
        assert record.protected_result is not None
        assert record.protected_result.rows
        assert record.protected_result.field_names == (
            "channel_name",
            "gmv",
        )

        assert view.breakdown is not None
        assert view.breakdown.rows == record.protected_result.rows
        assert view.evidence_drawer.records[0].audit_event_id is not None

        assert brief.request_subject == QUESTION
        assert brief.metric_name == "gmv"
        assert brief.confirmed_facts

        # Bridge 的 public result 仍然不能出现 raw SQL / rows。
        dumped = str(result.safe_runtime_result).lower()
        assert "select " not in dumped
        assert " from " not in dumped
        assert "rows" not in result.safe_runtime_result

        # Delivery 中允许的是 Result Protection 后的 rows。
        assert "__group_size" not in record.protected_result.field_names


TESTS = (
    test_real_graph_builds_day89_delivery,
)


def run_acceptance() -> None:
    passed = 0
    failures: list[str] = []

    print("Day89 Runtime Delivery Bridge PostgreSQL Integration")
    print(f"Total: {len(TESTS)}")

    for test in TESTS:
        try:
            test()
            passed += 1
        except Exception as exc:  # noqa: BLE001
            failures.append(
                f"{test.__name__}: "
                f"{type(exc).__name__}: {exc}"
            )

    print()
    print("Day89 Runtime Delivery Bridge Integration Summary")
    print(f"Passed: {passed}")
    print(f"Failed: {len(failures)}")

    for failure in failures:
        print(f"- {failure}")

    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    run_acceptance()
