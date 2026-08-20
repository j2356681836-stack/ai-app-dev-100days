from __future__ import annotations

from decimal import Decimal

from app.ui.decision_console_presenters_v2 import (
    build_chart_rows_v2,
    build_display_rows_v2,
    format_evidence_sufficiency_v2,
    format_metric_name_v2,
    normalize_scope_summary_v2,
)


def test_metric_name_is_localized() -> None:
    assert format_metric_name_v2("gmv") == "GMV"


def test_evidence_sufficiency_is_localized() -> None:
    assert (
        format_evidence_sufficiency_v2("sufficient_for_current_scope")
        == "当前范围证据充分"
    )


def test_scope_summary_is_shortened() -> None:
    preview, full = normalize_scope_summary_v2(
        "这是一个很长的范围说明。" * 20,
        preview_limit=20,
    )
    assert preview is not None
    assert full is not None
    assert preview.endswith("...")
    assert len(full) > len(preview)


def test_display_rows_are_localized_and_formatted() -> None:
    rows = (
        {"channel_name": "天猫旗舰店", "gmv": Decimal("2586549.37")},
    )
    formatted = build_display_rows_v2(rows)
    assert formatted == [{"渠道": "天猫旗舰店", "GMV": "2,586,549.37"}]


def test_chart_rows_preserve_numeric_value() -> None:
    rows = (
        {"channel_name": "天猫旗舰店", "gmv": Decimal("2586549.37")},
    )
    chart_rows = build_chart_rows_v2(rows)
    assert chart_rows == [{"渠道": "天猫旗舰店", "GMV": 2586549.37}]


TESTS = (
    test_metric_name_is_localized,
    test_evidence_sufficiency_is_localized,
    test_scope_summary_is_shortened,
    test_display_rows_are_localized_and_formatted,
    test_chart_rows_preserve_numeric_value,
)


def run_acceptance() -> None:
    print("Day89 Decision Console UI Presentation Acceptance")

    passed = 0
    failures: list[str] = []

    for test in TESTS:
        try:
            test()
            passed += 1
        except Exception as exc:  # noqa: BLE001
            failures.append(
                f"{test.__name__}: {type(exc).__name__}: {exc}"
            )

    print(f"Total: {len(TESTS)}")
    print(f"Passed: {passed}")
    print(f"Failed: {len(failures)}")

    for failure in failures:
        print(f"- {failure}")

    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    run_acceptance()
