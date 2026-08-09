from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator

from app.governance.governed_finalization import (
    FinalizationOutcome,
    FinalizationReason,
    GovernedFinalizationResult,
)
from app.governance.governed_planning_envelope_v2 import (
    GovernedPlanningEnvelopeV2,
)


class FinalAnswerStatusV2(str, Enum):
    ANSWERED = "answered"
    NO_DATA = "no_data"
    BLOCKED = "blocked"
    FAILED = "failed"


class ScopeDisclosureV2(BaseModel):
    """本次 SQL 实际绑定的授权数据范围。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    region_codes: tuple[str, ...] = ()
    channel_codes: tuple[str, ...] = ()
    summary: str


class FinalAnswerResultV2(BaseModel):
    """
    Dataset V2 最终回答合同。

    只有 GovernedFinalizationResult.SUCCEEDED 才能生成事实回答。
    Scope Disclosure 只来自已经进入 Governed Planning / SQL Contract
    的 Scope Binding，不重新解释用户自然语言。
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: FinalAnswerStatusV2
    answer: str

    metric_name: str
    plan_name: str
    result_grain: str

    scope_disclosure_required: bool
    scope_disclosure: ScopeDisclosureV2 | None = None

    finalization_outcome: FinalizationOutcome
    finalization_reason: FinalizationReason
    blocked_stage: str | None = None
    blocked_reason: str | None = None
    row_count: int = 0

    @model_validator(mode="after")
    def validate_contract(self) -> "FinalAnswerResultV2":
        if not self.answer.strip():
            raise ValueError("Final answer cannot be empty.")

        if self.scope_disclosure_required != (
            self.scope_disclosure is not None
        ):
            raise ValueError(
                "scope_disclosure_required must match disclosure presence."
            )

        expected = {
            FinalAnswerStatusV2.ANSWERED: FinalizationOutcome.SUCCEEDED,
            FinalAnswerStatusV2.NO_DATA: FinalizationOutcome.SUCCEEDED,
            FinalAnswerStatusV2.BLOCKED: FinalizationOutcome.BLOCKED,
            FinalAnswerStatusV2.FAILED: FinalizationOutcome.FAILED,
        }[self.status]

        if self.finalization_outcome != expected:
            raise ValueError(
                "Final answer status does not match finalization outcome."
            )

        if self.status == FinalAnswerStatusV2.ANSWERED:
            if self.row_count < 1:
                raise ValueError("ANSWERED requires released rows.")
        elif self.row_count != 0:
            raise ValueError(
                "NO_DATA / BLOCKED / FAILED cannot expose rows."
            )

        return self


_DIMENSION_LABELS = {
    "channel_name": "渠道",
    "region_name": "地区",
    "category": "品类",
    "product_name": "商品",
    "membership_tier": "会员等级",
}


def _format_value(value: Any) -> str:
    if value is None:
        return "NULL"

    if isinstance(value, bool):
        return "是" if value else "否"

    if isinstance(value, int):
        return f"{value:,}"

    if isinstance(value, (Decimal, float)):
        text = f"{value:,.4f}"
        return text.rstrip("0").rstrip(".")

    return str(value)


def _scope_values(
    envelope: GovernedPlanningEnvelopeV2,
) -> dict[str, tuple[str, ...]]:
    """
    从 immutable ScopedQueryContract 中恢复本次 SQL 实际使用的
    Region / Channel 参数值。
    """
    scoped = envelope.scope_binding.scoped_query_contract

    parameter_values = {
        parameter.name: parameter.value
        for parameter in scoped.parameters
    }

    collected: dict[str, set[str]] = {}

    for predicate in scoped.predicates:
        dimension = predicate.dimension.value
        values = collected.setdefault(dimension, set())

        for name in predicate.parameter_names:
            if name not in parameter_values:
                raise ValueError(
                    "Scope predicate references a missing parameter: "
                    f"{name}"
                )

            values.add(parameter_values[name])

    return {
        dimension: tuple(sorted(values))
        for dimension, values in collected.items()
    }


def _build_scope_disclosure(
    envelope: GovernedPlanningEnvelopeV2,
) -> ScopeDisclosureV2 | None:
    values = _scope_values(envelope)

    regions = values.get("region", ())
    channels = values.get("channel", ())

    parts: list[str] = []

    if regions:
        parts.append("地区代码：" + "、".join(regions))

    if channels:
        parts.append("渠道代码：" + "、".join(channels))

    if not parts:
        return None

    return ScopeDisclosureV2(
        region_codes=regions,
        channel_codes=channels,
        summary="；".join(parts),
    )


def _scope_prefix(
    disclosure: ScopeDisclosureV2 | None,
) -> str:
    if disclosure is None:
        return ""

    return (
        "基于本次实际执行的授权数据范围（"
        f"{disclosure.summary}），"
    )


def _time_notice_suffix(
    envelope: GovernedPlanningEnvelopeV2,
) -> str:
    if envelope.notice_required and envelope.user_notice:
        return f" {envelope.user_notice}"

    return ""


def _visible_fields(
    envelope: GovernedPlanningEnvelopeV2,
) -> tuple[str, ...]:
    return tuple(
        binding.output_field
        for binding in (
            envelope.query_plan.result_contract.field_bindings
        )
    )


def _render_success_rows(
    envelope: GovernedPlanningEnvelopeV2,
    rows: tuple[dict[str, Any], ...],
) -> str:
    visible_fields = _visible_fields(envelope)

    if not visible_fields:
        raise ValueError(
            "Query Plan Result Contract has no visible fields."
        )

    expected_fields = set(visible_fields)

    for row in rows:
        if set(row) != expected_fields:
            raise ValueError(
                "Released rows do not match Query Plan visible fields."
            )

    plan = envelope.query_plan

    if (
        envelope.result_grain == "overall"
        and len(visible_fields) == 1
        and len(rows) == 1
    ):
        return (
            f"{plan.chinese_name}为 "
            f"{_format_value(rows[0][visible_fields[0]])}。"
        )

    metric_field = (
        envelope.metric_name
        if envelope.metric_name in visible_fields
        else visible_fields[-1]
    )

    dimension_fields = tuple(
        field
        for field in visible_fields
        if field != metric_field
    )

    rendered: list[str] = []

    for row in rows:
        if dimension_fields:
            dimensions = "、".join(
                (
                    f"{_DIMENSION_LABELS.get(field, field)}="
                    f"{_format_value(row[field])}"
                )
                for field in dimension_fields
            )

            rendered.append(
                f"{dimensions}：{_format_value(row[metric_field])}"
            )
        else:
            rendered.append(
                "、".join(
                    f"{field}={_format_value(row[field])}"
                    for field in visible_fields
                )
            )

    return f"{plan.chinese_name}结果为：" + "；".join(rendered) + "。"


def _blocked_answer(
    finalization: GovernedFinalizationResult,
) -> str:
    if (
        finalization.reason_code
        == FinalizationReason.RESULT_PROTECTION_BLOCKED
    ):
        return (
            "该请求已完成受控查询，但结果因数据保护策略"
            "无法释放。"
        )

    if (
        finalization.reason_code
        == FinalizationReason.EXECUTION_BLOCKED
    ):
        return (
            "该请求未能在当前执行治理限制内完成，"
            "因此没有返回数据。"
        )

    if (
        finalization.reason_code
        == FinalizationReason.AUTHORIZATION_BLOCKED
    ):
        return (
            "当前请求未通过数据访问授权，"
            "因此没有返回数据。"
        )

    return "该请求已被治理策略阻断，因此没有返回数据。"


def generate_final_answer_v2(
    *,
    envelope: GovernedPlanningEnvelopeV2,
    finalization: GovernedFinalizationResult,
) -> FinalAnswerResultV2:
    """
    GovernedFinalizationResult -> user-facing Final Answer V2.

    Non-goals:
    - 不接受 GovernedExecutionResult；
    - 不读取 raw execution rows；
    - 不从 question 文本补 Region / Channel filter；
    - 不披露 denied scope universe；
    - 不做 LLM 自由总结。
    """
    if not isinstance(envelope, GovernedPlanningEnvelopeV2):
        raise TypeError(
            "envelope must be GovernedPlanningEnvelopeV2."
        )

    if not isinstance(finalization, GovernedFinalizationResult):
        raise TypeError(
            "finalization must be GovernedFinalizationResult."
        )

    disclosure = _build_scope_disclosure(envelope)

    common = {
        "metric_name": envelope.metric_name,
        "plan_name": envelope.plan_name,
        "result_grain": envelope.result_grain,
        "scope_disclosure_required": disclosure is not None,
        "scope_disclosure": disclosure,
        "finalization_outcome": finalization.outcome,
        "finalization_reason": finalization.reason_code,
        "blocked_stage": finalization.blocked_stage,
        "blocked_reason": finalization.blocked_reason,
        "row_count": finalization.row_count,
    }

    if finalization.outcome == FinalizationOutcome.SUCCEEDED:
        if finalization.row_count == 0:
            return FinalAnswerResultV2(
                status=FinalAnswerStatusV2.NO_DATA,
                answer=(
                    _scope_prefix(disclosure)
                    + "未查询到可释放的数据。"
                    + _time_notice_suffix(envelope)
                ),
                **common,
            )

        return FinalAnswerResultV2(
            status=FinalAnswerStatusV2.ANSWERED,
            answer=(
                _scope_prefix(disclosure)
                + _render_success_rows(
                    envelope,
                    finalization.rows,
                )
                + _time_notice_suffix(envelope)
            ),
            **common,
        )

    if finalization.outcome == FinalizationOutcome.BLOCKED:
        return FinalAnswerResultV2(
            status=FinalAnswerStatusV2.BLOCKED,
            answer=_blocked_answer(finalization),
            **common,
        )

    return FinalAnswerResultV2(
        status=FinalAnswerStatusV2.FAILED,
        answer="该请求未能安全完成，因此没有返回数据。",
        **common,
    )
