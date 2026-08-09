from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app.governance.access_context import (
    AccessContext,
    AccessRole,
    OperationMode,
    SensitiveDataPolicy,
)
from app.governance.governance_runtime import (
    GovernanceRuntimeConfig,
)
from app.governance.governed_finalization import (
    FinalizationOutcome,
    FinalizationReason,
    GovernedFinalizationResult,
)
from app.governance.governed_analytics_service_v2 import (
    GovernedAnalyticsOutcomeV2,
    GovernedAnalyticsStopStageV2,
    execute_governed_analytics_v2,
)
from app.semantic_layer.query_plan_v2_loader import (
    load_query_plan_v2_catalog,
)
from app.text_to_sql.final_answer_v2 import (
    FinalAnswerStatusV2,
)


REFERENCE_DATE = date(2026, 8, 9)


def _context() -> AccessContext:
    catalog = load_query_plan_v2_catalog()

    return AccessContext(
        request_id="day79-ai-chain-service-tests",
        actor_id="day79-test-user",
        role=AccessRole.SCOPED_ANALYST,
        dataset_name="beauty_bi_v2",
        target_schema="beauty_bi_v2",
        operation_mode=OperationMode.OBSERVE_ADVISE,
        allowed_metrics=frozenset(
            plan.metric
            for plan in catalog.query_plans
        ),
        allowed_tables=frozenset(
            table
            for plan in catalog.query_plans
            for table in plan.resource_contract.required_tables
        ),
        allowed_columns=frozenset(
            column
            for plan in catalog.query_plans
            for column in plan.resource_contract.required_columns
        ),
        denied_columns=frozenset(),
        allowed_region_codes=frozenset(
            {"BEIJING", "SHANGHAI"}
        ),
        allowed_channel_codes=frozenset(
            {"JD", "TMALL"}
        ),
        sensitive_data_policy=SensitiveDataPolicy(),
        policy_version="day79_ai_chain_test_policy",
        scope_source="day79_ai_chain_test_fixture",
    )


def _runtime(path: Path) -> GovernanceRuntimeConfig:
    return GovernanceRuntimeConfig(
        result_tokenization_secret=(
            "day79-result-tokenization-secret"
        ),
        audit_secret="day79-audit-secret-long-enough",
        audit_log_path=path,
        create_parent_directory=True,
        fsync_enabled=False,
    )


def _gmv_llm_call(**kwargs) -> str:
    return json.dumps(
        {
            "operator": "sum",
            "left_operand": "paid_amount",
            "right_operand": None,
            "intrinsic_partition": None,
            "qualifiers": [],
        },
        ensure_ascii=False,
    )


def _roi_llm_call(**kwargs) -> str:
    return json.dumps(
        {
            "operator": "divide",
            "left_operand": "paid_amount",
            "right_operand": "marketing_spend",
            "intrinsic_partition": "channel",
            "qualifiers": [
                "same_window_sales_spend",
            ],
        },
        ensure_ascii=False,
    )


def _succeeded_gmv() -> GovernedFinalizationResult:
    return GovernedFinalizationResult(
        success=True,
        outcome=FinalizationOutcome.SUCCEEDED,
        reason_code=FinalizationReason.ALLOWED,
        message="Governed request finalized and rows released.",
        rows=(
            {
                "gmv": Decimal("11430211.41"),
            },
        ),
        row_count=1,
        blocked_stage=None,
        blocked_reason=None,
        audit_persisted=True,
        audit_event_id="day79-success-event",
        audit_event_fingerprint="a" * 64,
        audit_sequence_number=1,
        audit_record_hash="b" * 64,
        error_type=None,
        retryable=False,
    )


def _blocked_result() -> GovernedFinalizationResult:
    return GovernedFinalizationResult(
        success=False,
        outcome=FinalizationOutcome.BLOCKED,
        reason_code=(
            FinalizationReason.RESULT_PROTECTION_BLOCKED
        ),
        message="Governed request was blocked.",
        rows=(),
        row_count=0,
        blocked_stage="result_protection",
        blocked_reason="minimum_group_size_violation",
        audit_persisted=True,
        audit_event_id="day79-block-event",
        audit_event_fingerprint="c" * 64,
        audit_sequence_number=1,
        audit_record_hash="d" * 64,
        error_type="governance_blocked",
        retryable=False,
    )


def test_single_plan_success_reaches_final_answer() -> None:
    with TemporaryDirectory() as temp_dir:
        runtime = _runtime(
            Path(temp_dir) / "audit.jsonl"
        )

        with patch(
            "app.governance.governed_analytics_service_v2."
            "execute_governed_query_v2",
            return_value=_succeeded_gmv(),
        ) as executor:
            result = execute_governed_analytics_v2(
                context=_context(),
                question="2025年GMV是多少？",
                reference_date=REFERENCE_DATE,
                runtime_config=runtime,
                llm_call=_gmv_llm_call,
            )

        assert result.outcome == GovernedAnalyticsOutcomeV2.ANSWERED
        assert result.stop_stage is None
        assert result.metric_name == "gmv"
        assert result.plan_name == "gmv_overall_v2"
        assert result.envelope_fingerprint is not None
        assert result.compiled_contract_fingerprint is not None
        assert result.sql_fingerprint is not None
        assert result.final_answer_status == FinalAnswerStatusV2.ANSWERED
        assert "11,430,211.41" in result.user_message
        assert "BEIJING" in result.user_message
        assert "JD" in result.user_message
        assert executor.call_count == 1


def test_finalization_block_becomes_safe_user_block() -> None:
    with TemporaryDirectory() as temp_dir:
        runtime = _runtime(
            Path(temp_dir) / "audit.jsonl"
        )

        with patch(
            "app.governance.governed_analytics_service_v2."
            "execute_governed_query_v2",
            return_value=_blocked_result(),
        ):
            result = execute_governed_analytics_v2(
                context=_context(),
                question="2025年GMV是多少？",
                reference_date=REFERENCE_DATE,
                runtime_config=runtime,
                llm_call=_gmv_llm_call,
            )

        assert result.outcome == GovernedAnalyticsOutcomeV2.BLOCKED
        assert (
            result.stop_stage
            == GovernedAnalyticsStopStageV2.FINALIZATION
        )
        assert result.final_answer_status == FinalAnswerStatusV2.BLOCKED
        assert "数据保护策略" in result.user_message
        assert "11,430,211.41" not in result.user_message


def test_multiple_plan_request_stops_before_execution() -> None:
    with TemporaryDirectory() as temp_dir:
        runtime = _runtime(
            Path(temp_dir) / "audit.jsonl"
        )

        with patch(
            "app.governance.governed_analytics_service_v2."
            "execute_governed_query_v2",
        ) as executor:
            result = execute_governed_analytics_v2(
                context=_context(),
                question="分别按渠道和地区看2025年GMV",
                reference_date=REFERENCE_DATE,
                runtime_config=runtime,
                llm_call=_gmv_llm_call,
            )

        assert result.outcome == GovernedAnalyticsOutcomeV2.UNSUPPORTED
        assert (
            result.stop_stage
            == GovernedAnalyticsStopStageV2.ANALYTICS_PLANNING
        )
        assert "多 Query Plan" in result.user_message
        assert executor.call_count == 0


def test_scope_contract_failure_stops_before_compilation_execution() -> None:
    with TemporaryDirectory() as temp_dir:
        runtime = _runtime(
            Path(temp_dir) / "audit.jsonl"
        )

        with patch(
            "app.governance.governed_analytics_service_v2."
            "execute_governed_query_v2",
        ) as executor:
            result = execute_governed_analytics_v2(
                context=_context(),
                question=(
                    "同一统计周期内，各渠道每元营销投入"
                    "带来多少成交金额？"
                ),
                reference_date=REFERENCE_DATE,
                runtime_config=runtime,
                llm_call=_roi_llm_call,
            )

        assert result.metric_name == "roi"
        assert result.plan_name == "roi_channel_v2"
        assert result.outcome == GovernedAnalyticsOutcomeV2.BLOCKED
        assert (
            result.stop_stage
            == GovernedAnalyticsStopStageV2.GOVERNED_PLANNING
        )
        assert result.compilation_status is None
        assert result.sql_fingerprint is None
        assert executor.call_count == 0


TESTS = (
    test_single_plan_success_reaches_final_answer,
    test_finalization_block_becomes_safe_user_block,
    test_multiple_plan_request_stops_before_execution,
    test_scope_contract_failure_stops_before_compilation_execution,
)


def run_tests() -> None:
    passed = 0
    failed = 0

    print("=" * 80)
    print("Governed Analytics Service V2 Tests")
    print(f"Cases: {len(TESTS)}")

    for test in TESTS:
        print("=" * 80)
        print(test.__name__)

        try:
            test()
        except Exception as exc:
            failed += 1
            print("[FAIL]")
            print(f"{type(exc).__name__}: {exc}")
        else:
            passed += 1
            print("[PASS]")

    print("=" * 80)
    print("Governed Analytics Service V2 Summary")
    print(f"Total: {len(TESTS)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    run_tests()
