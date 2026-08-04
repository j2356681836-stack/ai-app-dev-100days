from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TimeWindowResolutionStatusV2(str, Enum):
    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    UNSUPPORTED = "unsupported"


class TimeWindowResolutionSourceV2(str, Enum):
    EXPLICIT = "explicit"
    DEFAULT_POLICY = "default_policy"


class TimeExpressionTypeV2(str, Enum):
    DEFAULT_THREE_MONTHS = "default_three_months"
    EXPLICIT_DATE_RANGE = "explicit_date_range"
    EXPLICIT_MONTH = "explicit_month"
    EXPLICIT_YEAR = "explicit_year"
    CURRENT_MONTH = "current_month"
    PREVIOUS_MONTH = "previous_month"
    CURRENT_WEEK = "current_week"
    PREVIOUS_WEEK = "previous_week"
    CURRENT_QUARTER = "current_quarter"
    PREVIOUS_QUARTER = "previous_quarter"
    CURRENT_YEAR = "current_year"
    PREVIOUS_YEAR = "previous_year"
    TODAY = "today"
    YESTERDAY = "yesterday"
    ROLLING_DAYS = "rolling_days"
    ROLLING_MONTHS = "rolling_months"


class TimeWindowPolicyV2(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    policy_name: str = "default_three_calendar_months"
    policy_version: str = "time_window_policy_v2_0"
    default_lookback_months: int = Field(default=3, ge=1, le=24)

    @model_validator(mode="after")
    def validate_policy(self) -> "TimeWindowPolicyV2":
        if not self.policy_name.strip() or not self.policy_version.strip():
            raise ValueError("Time policy identity cannot be empty.")
        return self


DEFAULT_TIME_WINDOW_POLICY_V2 = TimeWindowPolicyV2()


class TimeWindowEvidenceV2(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    matched_text: str
    start: int
    end: int
    rule: str


class TimeWindowResolutionV2(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: TimeWindowResolutionStatusV2
    source: TimeWindowResolutionSourceV2 | None = None
    expression_type: TimeExpressionTypeV2 | None = None
    reference_date: date

    requested_start_date: date | None = None
    requested_end_date: date | None = None
    effective_start_date: date | None = None
    effective_end_date: date | None = None

    policy_name: str
    policy_version: str
    evidence: tuple[TimeWindowEvidenceV2, ...] = ()
    adjustment_reasons: tuple[str, ...] = ()
    notice_required: bool = False
    user_notice: str | None = None
    error: str | None = None

    @model_validator(mode="after")
    def validate_contract(self) -> "TimeWindowResolutionV2":
        if self.status == TimeWindowResolutionStatusV2.RESOLVED:
            required = (
                self.source,
                self.expression_type,
                self.requested_start_date,
                self.requested_end_date,
                self.effective_start_date,
                self.effective_end_date,
            )
            if any(value is None for value in required):
                raise ValueError("RESOLVED time result is incomplete.")
            if self.requested_start_date > self.requested_end_date:
                raise ValueError("Requested time range is reversed.")
            if self.effective_start_date > self.effective_end_date:
                raise ValueError("Effective time range is reversed.")
            if (
                self.source == TimeWindowResolutionSourceV2.DEFAULT_POLICY
                and not self.notice_required
            ):
                raise ValueError("Default time requires a user notice.")
            if self.notice_required != bool(self.user_notice):
                raise ValueError("notice_required and user_notice disagree.")
            if self.error is not None:
                raise ValueError("RESOLVED time result cannot contain error.")
            return self

        if any(
            value is not None
            for value in (
                self.source,
                self.expression_type,
                self.requested_start_date,
                self.requested_end_date,
                self.effective_start_date,
                self.effective_end_date,
                self.user_notice,
            )
        ):
            raise ValueError("Non-RESOLVED time result exposes resolved fields.")
        if self.notice_required:
            raise ValueError("Non-RESOLVED time result cannot require notice.")
        if not self.error:
            raise ValueError("Non-RESOLVED time result requires error.")
        return self


@dataclass(frozen=True)
class _Candidate:
    start: int
    end: int
    text: str
    rule: str
    expression_type: TimeExpressionTypeV2
    start_date: date
    end_date: date


_CHINESE_NUMBERS = {
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
    "十一": 11,
    "十二": 12,
}

_DATE_RANGE_RE = re.compile(
    r"(?P<y1>\d{4})[年/-](?P<m1>\d{1,2})[月/-](?P<d1>\d{1,2})日?"
    r"\s*(?:至|到|~|～)\s*"
    r"(?P<y2>\d{4})[年/-](?P<m2>\d{1,2})[月/-](?P<d2>\d{1,2})日?"
)
_MONTH_RE = re.compile(r"(?<!\d)(?P<year>\d{4})年(?P<month>\d{1,2})月(?!\d)")
_YEAR_RE = re.compile(r"(?<!\d)(?P<year>\d{4})年(?!\d)")
_ROLLING_RE = re.compile(
    r"(?:近|最近|过去)\s*"
    r"(?P<number>\d+|十一|十二|十|[一二两三四五六七八九])\s*"
    r"(?P<unit>天|日|个月|月)"
)
_UNSUPPORTED_RE = re.compile(
    r"近期|最近一段时间|前段时间|年初|月初|至今|以来|截至|"
    r"\d{4}年\d{1,2}月至\d{1,2}月|\d{1,2}月至\d{1,2}月"
)
_GENERIC_HINT_RE = re.compile(
    r"\d{4}年|\d{1,2}月|\d{1,2}日|本月|上月|本周|上周|"
    r"本季度|上季度|今年|去年|本年|上年|今天|今日|昨天|昨日|"
    r"近|最近|过去|季度|半年|日期|时间范围|期间|周期"
)

_FIXED_RULES = (
    (re.compile(r"本月"), "current_month", TimeExpressionTypeV2.CURRENT_MONTH),
    (re.compile(r"上月"), "previous_month", TimeExpressionTypeV2.PREVIOUS_MONTH),
    (re.compile(r"本周"), "current_week", TimeExpressionTypeV2.CURRENT_WEEK),
    (re.compile(r"上周"), "previous_week", TimeExpressionTypeV2.PREVIOUS_WEEK),
    (re.compile(r"本季度"), "current_quarter", TimeExpressionTypeV2.CURRENT_QUARTER),
    (re.compile(r"上季度"), "previous_quarter", TimeExpressionTypeV2.PREVIOUS_QUARTER),
    (re.compile(r"今年|本年"), "current_year", TimeExpressionTypeV2.CURRENT_YEAR),
    (re.compile(r"去年|上年"), "previous_year", TimeExpressionTypeV2.PREVIOUS_YEAR),
    (re.compile(r"今天|今日"), "today", TimeExpressionTypeV2.TODAY),
    (re.compile(r"昨天|昨日"), "yesterday", TimeExpressionTypeV2.YESTERDAY),
)


def _last_day(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def _month_start(value: date) -> date:
    return date(value.year, value.month, 1)


def _shift_months_clamped(value: date, months: int) -> date:
    month_index = value.year * 12 + value.month - 1 + months
    year, zero_month = divmod(month_index, 12)
    month = zero_month + 1
    return date(year, month, min(value.day, _last_day(year, month)))


def _quarter_start(value: date) -> date:
    return date(value.year, ((value.month - 1) // 3) * 3 + 1, 1)


def _parse_positive_integer(raw: str) -> int | None:
    value = int(raw) if raw.isdigit() else _CHINESE_NUMBERS.get(raw)
    return value if value is not None and value > 0 else None


def _fixed_period(
    expression_type: TimeExpressionTypeV2,
    reference_date: date,
) -> tuple[date, date]:
    if expression_type == TimeExpressionTypeV2.CURRENT_MONTH:
        return _month_start(reference_date), reference_date
    if expression_type == TimeExpressionTypeV2.PREVIOUS_MONTH:
        current_start = _month_start(reference_date)
        previous_start = _month_start(_shift_months_clamped(current_start, -1))
        return previous_start, current_start - timedelta(days=1)
    if expression_type == TimeExpressionTypeV2.CURRENT_WEEK:
        return reference_date - timedelta(days=reference_date.weekday()), reference_date
    if expression_type == TimeExpressionTypeV2.PREVIOUS_WEEK:
        current_start = reference_date - timedelta(days=reference_date.weekday())
        return current_start - timedelta(days=7), current_start - timedelta(days=1)
    if expression_type == TimeExpressionTypeV2.CURRENT_QUARTER:
        return _quarter_start(reference_date), reference_date
    if expression_type == TimeExpressionTypeV2.PREVIOUS_QUARTER:
        current_start = _quarter_start(reference_date)
        return _quarter_start(_shift_months_clamped(current_start, -3)), current_start - timedelta(days=1)
    if expression_type == TimeExpressionTypeV2.CURRENT_YEAR:
        return date(reference_date.year, 1, 1), reference_date
    if expression_type == TimeExpressionTypeV2.PREVIOUS_YEAR:
        year = reference_date.year - 1
        return date(year, 1, 1), date(year, 12, 31)
    if expression_type == TimeExpressionTypeV2.TODAY:
        return reference_date, reference_date
    if expression_type == TimeExpressionTypeV2.YESTERDAY:
        value = reference_date - timedelta(days=1)
        return value, value
    raise ValueError(f"Unsupported fixed expression: {expression_type}")


def _remove_contained(candidates: list[_Candidate]) -> tuple[_Candidate, ...]:
    ordered = sorted(candidates, key=lambda item: (item.start, -(item.end - item.start), item.rule))
    retained: list[_Candidate] = []
    for candidate in ordered:
        if any(
            other.start <= candidate.start
            and other.end >= candidate.end
            and (other.start < candidate.start or other.end > candidate.end)
            for other in ordered
        ):
            continue
        if not any(
            existing.start == candidate.start
            and existing.end == candidate.end
            and existing.start_date == candidate.start_date
            and existing.end_date == candidate.end_date
            for existing in retained
        ):
            retained.append(candidate)
    return tuple(sorted(retained, key=lambda item: (item.start, item.end, item.rule)))


def _collect_candidates(text: str, reference_date: date) -> tuple[_Candidate, ...]:
    candidates: list[_Candidate] = []

    for match in _DATE_RANGE_RE.finditer(text):
        try:
            start_date = date(int(match.group("y1")), int(match.group("m1")), int(match.group("d1")))
            end_date = date(int(match.group("y2")), int(match.group("m2")), int(match.group("d2")))
        except ValueError:
            continue
        candidates.append(_Candidate(match.start(), match.end(), match.group(0), "explicit_date_range", TimeExpressionTypeV2.EXPLICIT_DATE_RANGE, start_date, end_date))

    for match in _MONTH_RE.finditer(text):
        year, month = int(match.group("year")), int(match.group("month"))
        try:
            start_date = date(year, month, 1)
            end_date = date(year, month, _last_day(year, month))
        except ValueError:
            continue
        candidates.append(_Candidate(match.start(), match.end(), match.group(0), "explicit_calendar_month", TimeExpressionTypeV2.EXPLICIT_MONTH, start_date, end_date))

    for match in _YEAR_RE.finditer(text):
        year = int(match.group("year"))
        candidates.append(_Candidate(match.start(), match.end(), match.group(0), "explicit_calendar_year", TimeExpressionTypeV2.EXPLICIT_YEAR, date(year, 1, 1), date(year, 12, 31)))

    for match in _ROLLING_RE.finditer(text):
        amount = _parse_positive_integer(match.group("number"))
        if amount is None:
            continue
        unit = match.group("unit")
        if unit in {"天", "日"}:
            if amount > 3660:
                continue
            start_date = reference_date - timedelta(days=amount - 1)
            expression_type = TimeExpressionTypeV2.ROLLING_DAYS
            rule = "rolling_inclusive_days"
        else:
            if amount > 120:
                continue
            start_date = _shift_months_clamped(reference_date, -amount) + timedelta(days=1)
            expression_type = TimeExpressionTypeV2.ROLLING_MONTHS
            rule = "rolling_calendar_months_open_start_closed_end"
        candidates.append(_Candidate(match.start(), match.end(), match.group(0), rule, expression_type, start_date, reference_date))

    for pattern, rule, expression_type in _FIXED_RULES:
        for match in pattern.finditer(text):
            start_date, end_date = _fixed_period(expression_type, reference_date)
            candidates.append(_Candidate(match.start(), match.end(), match.group(0), rule, expression_type, start_date, end_date))

    return _remove_contained(candidates)


def _evidence(candidate: _Candidate) -> TimeWindowEvidenceV2:
    return TimeWindowEvidenceV2(
        matched_text=candidate.text,
        start=candidate.start,
        end=candidate.end,
        rule=candidate.rule,
    )


def _failure(
    *,
    status: TimeWindowResolutionStatusV2,
    reference_date: date,
    policy: TimeWindowPolicyV2,
    error: str,
    evidence: tuple[TimeWindowEvidenceV2, ...] = (),
) -> TimeWindowResolutionV2:
    return TimeWindowResolutionV2(
        status=status,
        reference_date=reference_date,
        policy_name=policy.policy_name,
        policy_version=policy.policy_version,
        evidence=evidence,
        error=error,
    )


def _default_resolution(
    reference_date: date,
    policy: TimeWindowPolicyV2,
) -> TimeWindowResolutionV2:
    start_date = _shift_months_clamped(
        reference_date,
        -policy.default_lookback_months,
    ) + timedelta(days=1)
    notice = (
        "未检测到明确的时间范围。"
        f"本次按默认策略查询最近{policy.default_lookback_months}个月："
        f"{start_date.isoformat()} 至 {reference_date.isoformat()}。"
    )
    return TimeWindowResolutionV2(
        status=TimeWindowResolutionStatusV2.RESOLVED,
        source=TimeWindowResolutionSourceV2.DEFAULT_POLICY,
        expression_type=TimeExpressionTypeV2.DEFAULT_THREE_MONTHS,
        reference_date=reference_date,
        requested_start_date=start_date,
        requested_end_date=reference_date,
        effective_start_date=start_date,
        effective_end_date=reference_date,
        policy_name=policy.policy_name,
        policy_version=policy.policy_version,
        notice_required=True,
        user_notice=notice,
    )


def _resolve_candidate(
    candidate: _Candidate,
    reference_date: date,
    policy: TimeWindowPolicyV2,
) -> TimeWindowResolutionV2:
    if candidate.start_date > candidate.end_date:
        return _failure(
            status=TimeWindowResolutionStatusV2.UNSUPPORTED,
            reference_date=reference_date,
            policy=policy,
            evidence=(_evidence(candidate),),
            error="The requested time range starts after it ends.",
        )
    if candidate.start_date > reference_date:
        return _failure(
            status=TimeWindowResolutionStatusV2.UNSUPPORTED,
            reference_date=reference_date,
            policy=policy,
            evidence=(_evidence(candidate),),
            error="The requested time range is entirely after reference_date.",
        )

    effective_end = min(candidate.end_date, reference_date)
    adjusted = effective_end != candidate.end_date
    notice = None
    reasons: tuple[str, ...] = ()
    if adjusted:
        reasons = ("future_boundary_clamped_to_reference_date",)
        notice = (
            "所指定周期尚未结束，"
            "本次查询截止到参考日期："
            f"{candidate.start_date.isoformat()} 至 {effective_end.isoformat()}。"
        )

    return TimeWindowResolutionV2(
        status=TimeWindowResolutionStatusV2.RESOLVED,
        source=TimeWindowResolutionSourceV2.EXPLICIT,
        expression_type=candidate.expression_type,
        reference_date=reference_date,
        requested_start_date=candidate.start_date,
        requested_end_date=candidate.end_date,
        effective_start_date=candidate.start_date,
        effective_end_date=effective_end,
        policy_name=policy.policy_name,
        policy_version=policy.policy_version,
        evidence=(_evidence(candidate),),
        adjustment_reasons=reasons,
        notice_required=adjusted,
        user_notice=notice,
    )


def resolve_time_window_v2(
    question: str,
    *,
    reference_date: date,
    policy: TimeWindowPolicyV2 = DEFAULT_TIME_WINDOW_POLICY_V2,
) -> TimeWindowResolutionV2:
    """
    Resolve the user-facing analysis window.

    This layer does not inspect data availability, choose Query Plan stages,
    or generate SQL. It never calls date.today(); reference_date is explicit.
    """
    text = str(question).strip()

    unsupported = _UNSUPPORTED_RE.search(text)
    if unsupported:
        return _failure(
            status=TimeWindowResolutionStatusV2.UNSUPPORTED,
            reference_date=reference_date,
            policy=policy,
            evidence=(TimeWindowEvidenceV2(
                matched_text=unsupported.group(0),
                start=unsupported.start(),
                end=unsupported.end(),
                rule="unsupported_time_expression",
            ),),
            error="The question contains a time expression that cannot be resolved safely.",
        )

    candidates = _collect_candidates(text, reference_date)
    if len(candidates) > 1:
        return _failure(
            status=TimeWindowResolutionStatusV2.AMBIGUOUS,
            reference_date=reference_date,
            policy=policy,
            evidence=tuple(_evidence(item) for item in candidates),
            error="The question contains more than one distinct time window.",
        )
    if len(candidates) == 1:
        return _resolve_candidate(candidates[0], reference_date, policy)

    hint = _GENERIC_HINT_RE.search(text)
    if hint:
        return _failure(
            status=TimeWindowResolutionStatusV2.UNSUPPORTED,
            reference_date=reference_date,
            policy=policy,
            evidence=(TimeWindowEvidenceV2(
                matched_text=hint.group(0),
                start=hint.start(),
                end=hint.end(),
                rule="unresolved_time_hint",
            ),),
            error="A time hint was detected but could not be resolved safely.",
        )

    return _default_resolution(reference_date, policy)
