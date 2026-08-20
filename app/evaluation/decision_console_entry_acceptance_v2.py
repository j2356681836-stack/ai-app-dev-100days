from __future__ import annotations

from datetime import date

from pydantic import ValidationError

from app.delivery.decision_console_entry_v2 import (
    ENTRY_CONTRACT_VERSION,
    DecisionConsoleEntryModeV2,
    DecisionConsoleEntryRequestV2,
    PeriodicReportCadenceV2,
)


EXPECTED_VERSION = "decision_console_entry_v2_0"


def test_valid_investigation_entry_passes() -> None:
    request = DecisionConsoleEntryRequestV2(
        entry_mode=DecisionConsoleEntryModeV2.INVESTIGATION,
        question="为什么 7 月 GMV 同比下降？",
    )

    assert request.entry_mode == DecisionConsoleEntryModeV2.INVESTIGATION
    assert request.question == "为什么 7 月 GMV 同比下降？"
    assert request.report_cadence is None
    assert request.report_anchor_date is None


def test_blank_investigation_question_fails() -> None:
    try:
        DecisionConsoleEntryRequestV2(
            entry_mode=DecisionConsoleEntryModeV2.INVESTIGATION,
            question="   ",
        )
    except ValidationError:
        return

    raise AssertionError(
        "INVESTIGATION blank question must fail."
    )


def test_investigation_cannot_carry_report_fields() -> None:
    try:
        DecisionConsoleEntryRequestV2(
            entry_mode=DecisionConsoleEntryModeV2.INVESTIGATION,
            question="分析 GMV。",
            report_cadence=PeriodicReportCadenceV2.MONTHLY,
            report_anchor_date=date(2026, 8, 1),
        )
    except ValidationError:
        return

    raise AssertionError(
        "INVESTIGATION cannot carry periodic report fields."
    )


def test_valid_periodic_report_entry_passes() -> None:
    request = DecisionConsoleEntryRequestV2(
        entry_mode=DecisionConsoleEntryModeV2.PERIODIC_REPORT,
        report_cadence=PeriodicReportCadenceV2.MONTHLY,
        report_anchor_date=date(2026, 8, 1),
    )

    assert request.entry_mode == DecisionConsoleEntryModeV2.PERIODIC_REPORT
    assert request.question is None
    assert request.report_cadence == PeriodicReportCadenceV2.MONTHLY
    assert request.report_anchor_date == date(2026, 8, 1)


def test_periodic_report_requires_cadence() -> None:
    try:
        DecisionConsoleEntryRequestV2(
            entry_mode=DecisionConsoleEntryModeV2.PERIODIC_REPORT,
            report_anchor_date=date(2026, 8, 1),
        )
    except ValidationError:
        return

    raise AssertionError(
        "PERIODIC_REPORT without cadence must fail."
    )


def test_periodic_report_requires_anchor_date() -> None:
    try:
        DecisionConsoleEntryRequestV2(
            entry_mode=DecisionConsoleEntryModeV2.PERIODIC_REPORT,
            report_cadence=PeriodicReportCadenceV2.WEEKLY,
        )
    except ValidationError:
        return

    raise AssertionError(
        "PERIODIC_REPORT without anchor_date must fail."
    )


def test_periodic_report_cannot_carry_question() -> None:
    try:
        DecisionConsoleEntryRequestV2(
            entry_mode=DecisionConsoleEntryModeV2.PERIODIC_REPORT,
            question="顺便分析一下。",
            report_cadence=PeriodicReportCadenceV2.DAILY,
            report_anchor_date=date(2026, 8, 19),
        )
    except ValidationError:
        return

    raise AssertionError(
        "PERIODIC_REPORT cannot carry investigation question."
    )


TESTS = (
    test_valid_investigation_entry_passes,
    test_blank_investigation_question_fails,
    test_investigation_cannot_carry_report_fields,
    test_valid_periodic_report_entry_passes,
    test_periodic_report_requires_cadence,
    test_periodic_report_requires_anchor_date,
    test_periodic_report_cannot_carry_question,
)


def run_acceptance() -> None:
    print("Day89 Decision Console Entry Contract Preflight")
    print(f"Version: {ENTRY_CONTRACT_VERSION}")

    if ENTRY_CONTRACT_VERSION != EXPECTED_VERSION:
        raise SystemExit(
            "Decision Console Entry Contract version is stale: "
            f"expected={EXPECTED_VERSION}; "
            f"actual={ENTRY_CONTRACT_VERSION}"
        )

    passed = 0
    failures: list[str] = []

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
    print("Day89 Decision Console Entry Contract Acceptance Summary")
    print(f"Total: {len(TESTS)}")
    print(f"Passed: {passed}")
    print(f"Failed: {len(failures)}")

    for failure in failures:
        print(f"- {failure}")

    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    run_acceptance()
