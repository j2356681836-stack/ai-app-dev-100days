from __future__ import annotations

import os

from dotenv import load_dotenv

import app.evaluation.investigation_loop_failure_recovery_postgresql_v2 as target
from app.observability.langfuse_observability_v2 import (
    flush_langfuse_v2,
    langfuse_observability_enabled_v2,
    start_safe_span_v2,
    update_safe_observation_v2,
)


def run_failure_recovery_observability_probe_v2() -> None:
    """
    Day91 failure / recovery observability probe.

    复用既有 Day86 PostgreSQL failure-recovery integration test，
    不修改其业务断言与 failure/recovery 语义。

    观测目标：
    - 第一个 Tool 被 Governance Boundary 阻断；
    - Loop Control 输出 RECOVER；
    - 第二个合法 Tool 路径真实执行成功；
    - 最终 Loop Control 输出 STOP / EVIDENCE_SUFFICIENT。

    安全边界：
    - 不上传 SQL / SQL parameters / rows；
    - 不上传 question / AccessContext / Evidence payload；
    - blocked_reason 原始文本不上传；
    - 只记录既有 allowlist 中的 status / reason_code /
      directive / stop_reason / action_id 等结构化字段。
    """

    if not langfuse_observability_enabled_v2():
        raise RuntimeError(
            "Langfuse Observability 未开启或配置不完整。"
            "请先设置 LANGFUSE_OBSERVABILITY_ENABLED=true。"
        )

    original_advance = target.advance_investigation_loop_v2

    def observed_advance_investigation_loop_v2(
        **kwargs,
    ):
        observation = kwargs["observation"]

        with start_safe_span_v2(
            name="loop_control",
            stage="loop_control",
            action_id=observation.action_id,
            status=observation.status,
            retryable=observation.retryable,
            attempt_number=observation.attempt_number,
        ) as loop_span:
            transition = original_advance(
                **kwargs,
            )

            update_safe_observation_v2(
                loop_span,
                directive=(
                    transition.control_decision.directive
                ),
                stop_reason=(
                    transition.control_decision.stop_reason
                ),
            )

            return transition

    target.advance_investigation_loop_v2 = (
        observed_advance_investigation_loop_v2
    )

    try:
        with start_safe_span_v2(
            name="investigation_failure_recovery",
            stage="failure_recovery_probe",
            purpose="day91_failure_recovery_evidence",
        ):
            target.test_real_failure_recovers_to_alternative_postgresql_path()
    finally:
        target.advance_investigation_loop_v2 = (
            original_advance
        )


def main() -> None:
    load_dotenv(dotenv_path=".env")

    try:
        run_failure_recovery_observability_probe_v2()
        print(
            "Day91 Failure Recovery Observability Probe"
        )
        print("Status: PASS")
    finally:
        flush_langfuse_v2()

    print("LANGFUSE_FLUSH_OK")


if __name__ == "__main__":
    main()
