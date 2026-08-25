from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.agents.evidence_pack_v2 import EvidenceTypeV2
from app.delivery.decision_console_view_v2 import (
    _build_fact_metric_value_v2,
)
from app.semantic_layer.time_comparison_contract_v2 import (
    TimeWindowReferenceV2,
)


WINDOW = TimeWindowReferenceV2(
    start_date=date(2025, 1, 1),
    end_date=date(2025, 12, 31),
)


def _delivery(
    *,
    result_grain: str = "overall",
    comparison=None,
    field_names=("gmv",),
    rows=({"gmv": Decimal("11430211.41")},),
):
    scope = SimpleNamespace(
        metric_name="gmv",
        result_grain=result_grain,
        analysis_window=WINDOW,
        comparison=comparison,
    )

    protected = SimpleNamespace(
        field_names=field_names,
        rows=rows,
        row_count=len(rows),
    )

    provenance = SimpleNamespace(
        metric_name="gmv",
        result_grain=result_grain,
        analysis_window=WINDOW,
    )

    record = SimpleNamespace(
        evidence_type=EvidenceTypeV2.GOVERNED_QUERY_RESULT,
        provenance=provenance,
        protected_result=protected,
        reference=SimpleNamespace(
            evidence_id="ev_fact_gmv",
        ),
    )

    pack = SimpleNamespace(
        analysis_scope=scope,
        evidence_records=(record,),
    )

    return SimpleNamespace(
        evidence_pack=pack,
    )


def test_overall_single_metric_is_projected() -> None:
    result = _build_fact_metric_value_v2(
        delivery=_delivery(),
    )

    assert result is not None
    assert result.metric_name == "gmv"
    assert result.value == Decimal("11430211.41")
    assert result.analysis_window == WINDOW
    assert result.evidence_id == "ev_fact_gmv"


def test_breakdown_result_is_not_projected_as_scalar() -> None:
    result = _build_fact_metric_value_v2(
        delivery=_delivery(
            result_grain="channel",
        ),
    )

    assert result is None


def test_multi_field_result_is_not_projected_as_scalar() -> None:
    result = _build_fact_metric_value_v2(
        delivery=_delivery(
            field_names=("channel_name", "gmv"),
            rows=(
                {
                    "channel_name": "TMALL",
                    "gmv": Decimal("100"),
                },
            ),
        ),
    )

    assert result is None


def test_comparison_scope_does_not_create_fact_scalar() -> None:
    result = _build_fact_metric_value_v2(
        delivery=_delivery(
            comparison=SimpleNamespace(),
        ),
    )

    assert result is None


TESTS = (
    test_overall_single_metric_is_projected,
    test_breakdown_result_is_not_projected_as_scalar,
    test_multi_field_result_is_not_projected_as_scalar,
    test_comparison_scope_does_not_create_fact_scalar,
)


def run_tests() -> None:
    passed = 0
    failed = 0

    for test in TESTS:
        print("=" * 80)
        print(f"Running: {test.__name__}")

        try:
            test()
            passed += 1
            print("[PASS]")
        except Exception as exc:
            failed += 1
            print("[FAIL]")
            print(f"{type(exc).__name__}: {exc}")

    print("=" * 80)
    print("Decision Console FACT KPI Projection V2 Test Summary")
    print(f"Total: {len(TESTS)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    run_tests()
