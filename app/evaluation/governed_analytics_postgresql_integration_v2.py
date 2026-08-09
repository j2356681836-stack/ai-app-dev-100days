from __future__ import annotations

import json
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app.evaluation.governed_query_execution_integration_v2 import (
    FIXED_TIME,
    INTEGRATION_EXECUTION_POLICY,
    REFERENCE_DATE,
    _integration_context,
    _runtime_config,
)
from app.governance.audit_sink import verify_audit_log
from app.governance.governed_analytics_service_v2 import (
    GovernedAnalyticsOutcomeV2,
    GovernedAnalyticsStopStageV2,
    execute_governed_analytics_v2,
)
from app.semantic_layer.analytics_planning_service_v2 import (
    AnalyticsPlanningStatusV2,
)
from app.text_to_sql.final_answer_v2 import (
    FinalAnswerStatusV2,
)


SUCCESS_QUESTION = "2025年GMV是多少？"
EMPTY_WINDOW_QUESTION = "上月GMV是多少？"
ROI_FAIL_CLOSED_QUESTION = (
    "同一统计周期内，各渠道每元营销投入带来多少成交金额？"
)
MULTI_PLAN_QUESTION = "分别按渠道和地区看2025年GMV"


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


def test_real_natural_language_gmv_reaches_safe_final_answer() -> None:
    """
    Full Day79 positive path:

    Natural language
    -> Semantic Decision
    -> Analytics Planning
    -> Governed Planning
    -> Compilation
    -> AST Enforcement
    -> real PostgreSQL
    -> Result Protection
    -> Audit Persistence
    -> Final Answer V2
    """
    context = _integration_context()

    with TemporaryDirectory() as tmp:
        from pathlib import Path

        audit_path = Path(tmp) / "audit.jsonl"

        result = execute_governed_analytics_v2(
            context=context,
            question=SUCCESS_QUESTION,
            reference_date=REFERENCE_DATE,
            runtime_config=_runtime_config(audit_path),
            llm_call=_gmv_llm_call,
            execution_policy=INTEGRATION_EXECUTION_POLICY,
            event_id="day79-real-ai-chain-success",
            occurred_at_utc=FIXED_TIME,
            written_at_utc=FIXED_TIME,
        )

        assert (
            result.outcome
            == GovernedAnalyticsOutcomeV2.ANSWERED
        ), (
            "Real AI-chain did not answer successfully. "
            f"outcome={result.outcome.value}, "
            f"stop_stage={getattr(result.stop_stage, 'value', None)}, "
            f"detail={result.detail}, "
            f"user_message={result.user_message}"
        )

        assert result.stop_stage is None
        assert (
            result.analytics_planning_status
            == AnalyticsPlanningStatusV2.PLANNED_SINGLE
        )
        assert result.metric_name == "gmv"
        assert result.plan_name == "gmv_overall_v2"

        assert result.envelope_fingerprint is not None
        assert result.compiled_contract_fingerprint is not None
        assert result.sql_fingerprint is not None

        assert result.finalization_outcome == "succeeded"
        assert (
            result.final_answer_status
            == FinalAnswerStatusV2.ANSWERED
        )

        # Day78 observed and accepted real Dataset V2 value.
        assert "11,430,211.41" in result.user_message

        # Final Answer must disclose the actual enforced scope.
        assert result.scope_summary is not None
        assert "SHANGHAI" in result.scope_summary
        assert "JD" in result.scope_summary
        assert "TMALL" in result.scope_summary
        assert "SHANGHAI" in result.user_message
        assert "JD" in result.user_message

        # Service boundary must not expose raw execution rows / raw SQL.
        dumped = result.model_dump(mode="json")
        assert "rows" not in dumped
        assert "sql" not in dumped

        verification = verify_audit_log(audit_path)

        assert verification.success
        assert verification.record_count == 1


def test_real_empty_window_is_blocked_not_answered_as_zero() -> None:
    """
    Real PostgreSQL returns:
        gmv=None
        __group_size=0

    Final Answer must preserve governance semantics:
    BLOCKED != zero and BLOCKED != ordinary no-data.
    """
    context = _integration_context()

    with TemporaryDirectory() as tmp:
        from pathlib import Path

        audit_path = Path(tmp) / "audit.jsonl"

        result = execute_governed_analytics_v2(
            context=context,
            question=EMPTY_WINDOW_QUESTION,
            reference_date=REFERENCE_DATE,
            runtime_config=_runtime_config(audit_path),
            llm_call=_gmv_llm_call,
            execution_policy=INTEGRATION_EXECUTION_POLICY,
            event_id="day79-real-ai-chain-empty-window",
            occurred_at_utc=FIXED_TIME,
            written_at_utc=FIXED_TIME,
        )

        assert (
            result.outcome
            == GovernedAnalyticsOutcomeV2.BLOCKED
        )
        assert (
            result.stop_stage
            == GovernedAnalyticsStopStageV2.FINALIZATION
        )
        assert result.metric_name == "gmv"
        assert result.plan_name == "gmv_overall_v2"
        assert result.finalization_outcome == "blocked"
        assert (
            result.final_answer_status
            == FinalAnswerStatusV2.BLOCKED
        )

        assert "数据保护策略" in result.user_message
        assert "GMV为 0" not in result.user_message
        assert "GMV为0" not in result.user_message
        assert "11,430,211.41" not in result.user_message

        verification = verify_audit_log(audit_path)

        assert verification.success
        assert verification.record_count == 1


def test_roi_scope_contract_fails_closed_before_database() -> None:
    """
    Known catalog fail-closed case:
    marketing spend currently lacks the Region path required to satisfy
    the active governed scope.

    The AI-chain must stop at Governed Planning rather than weaken the
    scope or execute a looser SQL statement.
    """
    context = _integration_context()

    with TemporaryDirectory() as tmp:
        from pathlib import Path

        audit_path = Path(tmp) / "audit.jsonl"

        with patch(
            "app.governance.governed_analytics_service_v2."
            "execute_governed_query_v2"
        ) as executor:
            result = execute_governed_analytics_v2(
                context=context,
                question=ROI_FAIL_CLOSED_QUESTION,
                reference_date=REFERENCE_DATE,
                runtime_config=_runtime_config(audit_path),
                llm_call=_roi_llm_call,
                execution_policy=INTEGRATION_EXECUTION_POLICY,
            )

        assert result.metric_name == "roi"
        assert result.plan_name == "roi_channel_v2"
        assert (
            result.outcome
            == GovernedAnalyticsOutcomeV2.BLOCKED
        )
        assert (
            result.stop_stage
            == GovernedAnalyticsStopStageV2.GOVERNED_PLANNING
        )

        assert result.compilation_status is None
        assert result.compiled_contract_fingerprint is None
        assert result.sql_fingerprint is None
        assert result.finalization_outcome is None
        assert result.final_answer_status is None

        executor.assert_not_called()
        assert not audit_path.exists()


def test_multi_plan_request_stops_before_database() -> None:
    """
    Day79 service-level contract supports only PLANNED_SINGLE.

    A valid PLANNED_MULTIPLE request is not a semantic failure, but it
    remains outside the current execution orchestration and must not
    silently execute only one of its plans.
    """
    context = _integration_context()

    with TemporaryDirectory() as tmp:
        from pathlib import Path

        audit_path = Path(tmp) / "audit.jsonl"

        with patch(
            "app.governance.governed_analytics_service_v2."
            "execute_governed_query_v2"
        ) as executor:
            result = execute_governed_analytics_v2(
                context=context,
                question=MULTI_PLAN_QUESTION,
                reference_date=REFERENCE_DATE,
                runtime_config=_runtime_config(audit_path),
                llm_call=_gmv_llm_call,
                execution_policy=INTEGRATION_EXECUTION_POLICY,
            )

        assert (
            result.analytics_planning_status
            == AnalyticsPlanningStatusV2.PLANNED_MULTIPLE
        )
        assert (
            result.outcome
            == GovernedAnalyticsOutcomeV2.UNSUPPORTED
        )
        assert (
            result.stop_stage
            == GovernedAnalyticsStopStageV2.ANALYTICS_PLANNING
        )

        assert result.metric_name == "gmv"
        assert result.plan_name is None
        assert result.governed_planning_status is None
        assert result.compilation_status is None
        assert result.sql_fingerprint is None
        assert result.finalization_outcome is None
        assert result.final_answer_status is None

        assert "多 Query Plan" in result.user_message

        executor.assert_not_called()
        assert not audit_path.exists()


TESTS = (
    test_real_natural_language_gmv_reaches_safe_final_answer,
    test_real_empty_window_is_blocked_not_answered_as_zero,
    test_roi_scope_contract_fails_closed_before_database,
    test_multi_plan_request_stops_before_database,
)


def run_acceptance() -> None:
    passed = 0
    failed = 0

    print("=" * 80)
    print(
        "Governed Analytics V2 PostgreSQL "
        "End-to-End Integration Acceptance"
    )
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
    print(
        "Governed Analytics V2 PostgreSQL "
        "End-to-End Integration Summary"
    )
    print(f"Total: {len(TESTS)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    run_acceptance()
