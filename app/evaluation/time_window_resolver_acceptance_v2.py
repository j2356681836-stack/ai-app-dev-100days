from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.semantic_layer.time_window_resolver_v2 import (
    TimeExpressionTypeV2,
    TimeWindowResolutionSourceV2,
    TimeWindowResolutionStatusV2,
    resolve_time_window_v2,
)


REFERENCE_DATE = date(2026, 8, 3)


@dataclass(frozen=True)
class Case:
    case_id: str
    question: str
    expected_status: TimeWindowResolutionStatusV2
    reference_date: date = REFERENCE_DATE
    expected_source: TimeWindowResolutionSourceV2 | None = None
    expected_type: TimeExpressionTypeV2 | None = None
    requested_start: date | None = None
    requested_end: date | None = None
    effective_start: date | None = None
    effective_end: date | None = None
    notice_required: bool = False
    notice: str | None = None


CASES = (
    Case(
        "TWV2-001",
        "各渠道GMV",
        TimeWindowResolutionStatusV2.RESOLVED,
        expected_source=TimeWindowResolutionSourceV2.DEFAULT_POLICY,
        expected_type=TimeExpressionTypeV2.DEFAULT_THREE_MONTHS,
        requested_start=date(2026, 5, 4),
        requested_end=REFERENCE_DATE,
        effective_start=date(2026, 5, 4),
        effective_end=REFERENCE_DATE,
        notice_required=True,
        notice=(
            "未检测到明确的时间范围。"
            "本次按默认策略查询最近3个月："
            "2026-05-04 至 2026-08-03。"
        ),
    ),
    Case(
        "TWV2-002",
        "各渠道GMV",
        TimeWindowResolutionStatusV2.RESOLVED,
        reference_date=date(2026, 5, 31),
        expected_source=TimeWindowResolutionSourceV2.DEFAULT_POLICY,
        expected_type=TimeExpressionTypeV2.DEFAULT_THREE_MONTHS,
        requested_start=date(2026, 3, 1),
        requested_end=date(2026, 5, 31),
        effective_start=date(2026, 3, 1),
        effective_end=date(2026, 5, 31),
        notice_required=True,
        notice=(
            "未检测到明确的时间范围。"
            "本次按默认策略查询最近3个月："
            "2026-03-01 至 2026-05-31。"
        ),
    ),
    Case(
        "TWV2-003",
        "本月各渠道GMV",
        TimeWindowResolutionStatusV2.RESOLVED,
        expected_source=TimeWindowResolutionSourceV2.EXPLICIT,
        expected_type=TimeExpressionTypeV2.CURRENT_MONTH,
        requested_start=date(2026, 8, 1),
        requested_end=REFERENCE_DATE,
        effective_start=date(2026, 8, 1),
        effective_end=REFERENCE_DATE,
    ),
    Case(
        "TWV2-004",
        "上月各渠道GMV",
        TimeWindowResolutionStatusV2.RESOLVED,
        expected_source=TimeWindowResolutionSourceV2.EXPLICIT,
        expected_type=TimeExpressionTypeV2.PREVIOUS_MONTH,
        requested_start=date(2026, 7, 1),
        requested_end=date(2026, 7, 31),
        effective_start=date(2026, 7, 1),
        effective_end=date(2026, 7, 31),
    ),
    Case(
        "TWV2-005",
        "上周GMV",
        TimeWindowResolutionStatusV2.RESOLVED,
        expected_source=TimeWindowResolutionSourceV2.EXPLICIT,
        expected_type=TimeExpressionTypeV2.PREVIOUS_WEEK,
        requested_start=date(2026, 7, 27),
        requested_end=date(2026, 8, 2),
        effective_start=date(2026, 7, 27),
        effective_end=date(2026, 8, 2),
    ),
    Case(
        "TWV2-006",
        "近30天GMV",
        TimeWindowResolutionStatusV2.RESOLVED,
        expected_source=TimeWindowResolutionSourceV2.EXPLICIT,
        expected_type=TimeExpressionTypeV2.ROLLING_DAYS,
        requested_start=date(2026, 7, 5),
        requested_end=REFERENCE_DATE,
        effective_start=date(2026, 7, 5),
        effective_end=REFERENCE_DATE,
    ),
    Case(
        "TWV2-007",
        "最近三个月GMV",
        TimeWindowResolutionStatusV2.RESOLVED,
        expected_source=TimeWindowResolutionSourceV2.EXPLICIT,
        expected_type=TimeExpressionTypeV2.ROLLING_MONTHS,
        requested_start=date(2026, 5, 4),
        requested_end=REFERENCE_DATE,
        effective_start=date(2026, 5, 4),
        effective_end=REFERENCE_DATE,
    ),
    Case(
        "TWV2-008",
        "2026年7月GMV",
        TimeWindowResolutionStatusV2.RESOLVED,
        expected_source=TimeWindowResolutionSourceV2.EXPLICIT,
        expected_type=TimeExpressionTypeV2.EXPLICIT_MONTH,
        requested_start=date(2026, 7, 1),
        requested_end=date(2026, 7, 31),
        effective_start=date(2026, 7, 1),
        effective_end=date(2026, 7, 31),
    ),
    Case(
        "TWV2-009",
        "2026年GMV",
        TimeWindowResolutionStatusV2.RESOLVED,
        expected_source=TimeWindowResolutionSourceV2.EXPLICIT,
        expected_type=TimeExpressionTypeV2.EXPLICIT_YEAR,
        requested_start=date(2026, 1, 1),
        requested_end=date(2026, 12, 31),
        effective_start=date(2026, 1, 1),
        effective_end=REFERENCE_DATE,
        notice_required=True,
        notice=(
            "所指定周期尚未结束，"
            "本次查询截止到参考日期："
            "2026-01-01 至 2026-08-03。"
        ),
    ),
    Case(
        "TWV2-010",
        "2026年5月1日至2026年5月31日GMV",
        TimeWindowResolutionStatusV2.RESOLVED,
        expected_source=TimeWindowResolutionSourceV2.EXPLICIT,
        expected_type=TimeExpressionTypeV2.EXPLICIT_DATE_RANGE,
        requested_start=date(2026, 5, 1),
        requested_end=date(2026, 5, 31),
        effective_start=date(2026, 5, 1),
        effective_end=date(2026, 5, 31),
    ),
    Case("TWV2-011", "本月和上月GMV", TimeWindowResolutionStatusV2.AMBIGUOUS),
    Case("TWV2-012", "2026年7月至8月GMV", TimeWindowResolutionStatusV2.UNSUPPORTED),
    Case("TWV2-013", "近期GMV", TimeWindowResolutionStatusV2.UNSUPPORTED),
    Case("TWV2-014", "2027年1月GMV", TimeWindowResolutionStatusV2.UNSUPPORTED),
    Case(
        "TWV2-015",
        "上季度ROI",
        TimeWindowResolutionStatusV2.RESOLVED,
        expected_source=TimeWindowResolutionSourceV2.EXPLICIT,
        expected_type=TimeExpressionTypeV2.PREVIOUS_QUARTER,
        requested_start=date(2026, 4, 1),
        requested_end=date(2026, 6, 30),
        effective_start=date(2026, 4, 1),
        effective_end=date(2026, 6, 30),
    ),
)


def evaluate(case: Case) -> tuple[bool, str]:
    result = resolve_time_window_v2(
        case.question,
        reference_date=case.reference_date,
    )
    checks = (
        ("status", case.expected_status, result.status),
        ("source", case.expected_source, result.source),
        ("expression_type", case.expected_type, result.expression_type),
        ("requested_start", case.requested_start, result.requested_start_date),
        ("requested_end", case.requested_end, result.requested_end_date),
        ("effective_start", case.effective_start, result.effective_start_date),
        ("effective_end", case.effective_end, result.effective_end_date),
        ("notice_required", case.notice_required, result.notice_required),
        ("notice", case.notice, result.user_notice),
    )
    problems = [
        f"{field} expected={expected!r} actual={actual!r}"
        for field, expected, actual in checks
        if expected != actual
    ]
    return (not problems, "; ".join(problems) if problems else "ok")


def run_acceptance() -> None:
    passed = 0
    failed = 0
    print("=" * 80)
    print("Time Window Resolver V2 Acceptance")
    print(f"Reference Date: {REFERENCE_DATE}")
    print(f"Cases: {len(CASES)}")

    for case in CASES:
        print("=" * 80)
        print(f"{case.case_id}: {case.question}")
        try:
            ok, detail = evaluate(case)
        except Exception as exc:
            ok = False
            detail = f"exception: {type(exc).__name__}: {exc}"
        if ok:
            passed += 1
            print("[PASS]")
        else:
            failed += 1
            print("[FAIL]")
            print(detail)

    print("=" * 80)
    print("Time Window Resolver V2 Acceptance Summary")
    print(f"Total: {len(CASES)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    run_acceptance()
