from __future__ import annotations

import threading
import time
from unittest.mock import patch

from app.delivery import periodic_business_report_v2 as module
from app.delivery.periodic_business_report_v2 import (
    PERIODIC_METRIC_MAX_WORKERS,
    PERIODIC_METRIC_REGISTRY_V2,
    PeriodicMetricSnapshotV2,
    PeriodicMetricStatusV2,
    _run_periodic_metrics_bounded_v2,
)
from app.delivery.decision_console_runtime_v2 import (
    build_monthly_mom_comparison_v2,
)


class _DummyRuntimeConfig:
    pass


def _not_ready_snapshot(spec):
    return PeriodicMetricSnapshotV2(
        spec=spec,
        status=PeriodicMetricStatusV2.NOT_READY,
        message="acceptance fake result",
    )


def test_worker_limit_is_four() -> None:
    assert PERIODIC_METRIC_MAX_WORKERS == 4


def test_bounded_concurrency_and_deterministic_order() -> None:
    comparison = build_monthly_mom_comparison_v2(
        anchor_date=module.date(2025, 7, 31)
    )

    lock = threading.Lock()
    active = 0
    peak = 0
    completion_order: list[str] = []

    # 让越靠后的任务越快结束，强制制造 completion order
    # 与 Registry order 不一致的场景。
    delays = {
        spec.metric_name: (
            0.06
            - (index % 4) * 0.01
        )
        for index, spec in enumerate(
            PERIODIC_METRIC_REGISTRY_V2
        )
    }

    def fake_runner(
        *,
        spec,
        comparison,
        runtime_config,
        execution_policy,
    ):
        nonlocal active, peak

        with lock:
            active += 1
            peak = max(peak, active)

        try:
            time.sleep(delays[spec.metric_name])
            return _not_ready_snapshot(spec)
        finally:
            with lock:
                completion_order.append(spec.metric_name)
                active -= 1

    with patch.object(
        module,
        "_run_single_metric_v2",
        side_effect=fake_runner,
    ):
        snapshots = _run_periodic_metrics_bounded_v2(
            comparison=comparison,
            runtime_config=_DummyRuntimeConfig(),
            execution_policy=None,
        )

    registry_order = [
        spec.metric_name
        for spec in PERIODIC_METRIC_REGISTRY_V2
    ]
    result_order = [
        snapshot.spec.metric_name
        for snapshot in snapshots
    ]

    assert peak > 1, "没有观察到真实并发。"
    assert peak <= PERIODIC_METRIC_MAX_WORKERS
    assert result_order == registry_order
    assert completion_order != registry_order


def test_invalid_worker_count_fails_closed() -> None:
    comparison = build_monthly_mom_comparison_v2(
        anchor_date=module.date(2025, 7, 31)
    )

    try:
        _run_periodic_metrics_bounded_v2(
            comparison=comparison,
            runtime_config=_DummyRuntimeConfig(),
            execution_policy=None,
            max_workers=0,
        )
    except ValueError as exc:
        assert "max_workers" in str(exc)
    else:
        raise AssertionError("max_workers=0 应显式失败。")


TESTS = (
    test_worker_limit_is_four,
    test_bounded_concurrency_and_deterministic_order,
    test_invalid_worker_count_fails_closed,
)


def run_acceptance() -> None:
    passed = 0
    failed = 0

    print("=" * 80)
    print("Day93 Periodic Bounded Concurrency Acceptance")
    print(f"Cases: {len(TESTS)}")

    for test in TESTS:
        try:
            test()
        except Exception as exc:
            failed += 1
            print(f"[FAIL] {test.__name__}")
            print(f"{type(exc).__name__}: {exc}")
        else:
            passed += 1
            print(f"[PASS] {test.__name__}")

    print("=" * 80)
    print("Day93 Periodic Bounded Concurrency Acceptance Summary")
    print(f"Total: {len(TESTS)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    run_acceptance()
