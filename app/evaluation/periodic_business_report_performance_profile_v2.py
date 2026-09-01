from __future__ import annotations

import threading
from collections import defaultdict
from datetime import date
from pathlib import Path
from time import perf_counter
from typing import Callable

from app.delivery import periodic_business_report_v2 as report_module
from app.delivery.decision_console_entry_v2 import (
    PeriodicReportCadenceV2,
)
from app.governance import audit_sink
from app.governance import governed_finalization
from app.governance import governed_query_execution_v2
from app.governance.governance_runtime import (
    load_governance_runtime_config,
)


ANCHOR_DATE = date(2025, 7, 31)


class TimingCollector:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._values: dict[str, list[float]] = defaultdict(list)
        self._labels: dict[str, list[tuple[str, float]]] = defaultdict(list)

    def add(
        self,
        category: str,
        elapsed: float,
        label: str | None = None,
    ) -> None:
        with self._lock:
            self._values[category].append(elapsed)
            if label is not None:
                self._labels[category].append((label, elapsed))

    def values(self, category: str) -> list[float]:
        with self._lock:
            return list(self._values.get(category, ()))

    def labels(self, category: str) -> list[tuple[str, float]]:
        with self._lock:
            return list(self._labels.get(category, ()))


def _summary(
    name: str,
    values: list[float],
) -> None:
    if not values:
        print(f"{name}: calls=0")
        return

    total = sum(values)
    print(
        f"{name}: calls={len(values)}; "
        f"total={total:.3f}s; "
        f"avg={total / len(values):.3f}s; "
        f"max={max(values):.3f}s"
    )


def _audit_log_stats(path: Path) -> tuple[int, int]:
    if not path.exists():
        return 0, 0

    size = path.stat().st_size

    with path.open("rb") as handle:
        records = sum(1 for _ in handle)

    return records, size


def run_profile() -> None:
    collector = TimingCollector()
    config = load_governance_runtime_config()

    before_records, before_bytes = _audit_log_stats(
        config.audit_log_path
    )

    original_metric_runner = (
        report_module._run_single_metric_v2
    )
    original_sql_runner = (
        governed_query_execution_v2.run_governed_sql
    )
    original_append = (
        governed_finalization.append_audit_event
    )
    original_verify = audit_sink.verify_audit_log

    def timed_metric_runner(
        *,
        spec,
        comparison,
        runtime_config,
        execution_policy,
    ):
        started = perf_counter()
        try:
            return original_metric_runner(
                spec=spec,
                comparison=comparison,
                runtime_config=runtime_config,
                execution_policy=execution_policy,
            )
        finally:
            collector.add(
                "metric",
                perf_counter() - started,
                spec.metric_name,
            )

    def timed_sql_runner(*args, **kwargs):
        started = perf_counter()
        try:
            return original_sql_runner(*args, **kwargs)
        finally:
            collector.add(
                "sql",
                perf_counter() - started,
            )

    def timed_verify(*args, **kwargs):
        started = perf_counter()
        try:
            return original_verify(*args, **kwargs)
        finally:
            collector.add(
                "audit_verify",
                perf_counter() - started,
            )

    def timed_append(*args, **kwargs):
        started = perf_counter()
        try:
            return original_append(*args, **kwargs)
        finally:
            # 包含等待 Audit lock 的时间。
            collector.add(
                "audit_append_wait_included",
                perf_counter() - started,
            )

    report_module._run_single_metric_v2 = (
        timed_metric_runner
    )
    governed_query_execution_v2.run_governed_sql = (
        timed_sql_runner
    )
    audit_sink.verify_audit_log = timed_verify
    governed_finalization.append_audit_event = timed_append

    try:
        print("=" * 100)
        print("Day93 Periodic Business Report Performance Profile")
        print("Cadence: monthly")
        print(f"Anchor: {ANCHOR_DATE.isoformat()}")
        print(
            "Audit before: "
            f"records={before_records}; "
            f"bytes={before_bytes}; "
            f"fsync_enabled={config.fsync_enabled}"
        )
        print("=" * 100)

        started = perf_counter()

        report = (
            report_module.run_day93_periodic_business_report_v2(
                cadence=PeriodicReportCadenceV2.MONTHLY,
                anchor_date=ANCHOR_DATE,
                runtime_config=config,
            )
        )

        wall = perf_counter() - started

    finally:
        report_module._run_single_metric_v2 = (
            original_metric_runner
        )
        governed_query_execution_v2.run_governed_sql = (
            original_sql_runner
        )
        audit_sink.verify_audit_log = original_verify
        governed_finalization.append_audit_event = (
            original_append
        )

    after_records, after_bytes = _audit_log_stats(
        config.audit_log_path
    )

    print()
    print("REPORT")
    print(f"status={report.status.value}")
    print(
        f"ready={report.ready_metric_count}; "
        f"failed={report.failed_metric_count}"
    )
    print(f"wall_seconds={wall:.3f}")

    print()
    print("STAGE TIMING")
    _summary("SQL execution", collector.values("sql"))
    _summary(
        "Audit hash-chain verification",
        collector.values("audit_verify"),
    )
    _summary(
        "Audit append (lock wait included)",
        collector.values("audit_append_wait_included"),
    )

    print()
    print("METRIC WALL TIME")
    metric_times = dict(
        collector.labels("metric")
    )
    for spec in report_module.PERIODIC_METRIC_REGISTRY_V2:
        elapsed = metric_times.get(spec.metric_name)
        print(
            f"{spec.metric_name}: "
            f"{elapsed:.3f}s"
            if elapsed is not None
            else f"{spec.metric_name}: -"
        )

    print()
    print(
        "Audit after: "
        f"records={after_records}; "
        f"bytes={after_bytes}; "
        f"new_records={after_records - before_records}; "
        f"new_bytes={after_bytes - before_bytes}"
    )

    verify_total = sum(
        collector.values("audit_verify")
    )
    sql_total = sum(
        collector.values("sql")
    )

    print()
    print("PROFILE HINT")
    if verify_total >= wall * 0.50:
        print(
            "Audit full-chain verification consumed >=50% of report "
            "wall time in serialized critical sections. "
            "Audit Sink is a primary optimization candidate."
        )
    elif sql_total >= wall * 1.50:
        print(
            "Aggregate SQL time is high but overlaps under concurrency. "
            "Inspect slow metric queries / database capacity next."
        )
    else:
        print(
            "Neither Audit verification nor SQL alone explains the wall "
            "time. Profile Governance/Delivery/Evidence stages next."
        )

    print("=" * 100)


if __name__ == "__main__":
    run_profile()
