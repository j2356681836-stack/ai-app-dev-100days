import argparse
import json
import math
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

from sqlalchemy import event
from sqlalchemy.engine import Engine

from app.db.governed_database import (
    get_governed_engine,
    load_governed_database_config,
)
from app.db.governed_sql_runner import run_governed_sql
from app.governance.execution_policy import (
    GovernedExecutionPolicy,
    GovernedExecutionResult,
)


DEFAULT_CONCURRENCY_LEVELS = (10, 25, 50)
DEFAULT_QUERY = (
    "SELECT COUNT(*) AS order_count "
    "FROM beauty_bi_v2.fact_orders"
)


@dataclass
class PoolObserver:
    active: int = 0
    peak_active: int = 0

    def __post_init__(self) -> None:
        self._lock = threading.Lock()

    def on_checkout(self, *args: Any) -> None:
        with self._lock:
            self.active += 1
            self.peak_active = max(
                self.peak_active,
                self.active,
            )

    def on_checkin(self, *args: Any) -> None:
        with self._lock:
            self.active = max(0, self.active - 1)


def _percentile(
    values: list[float],
    percentile: float,
) -> float:
    if not values:
        return 0.0

    ordered = sorted(values)

    if len(ordered) == 1:
        return ordered[0]

    position = (
        (len(ordered) - 1)
        * percentile
    )
    lower = math.floor(position)
    upper = math.ceil(position)

    if lower == upper:
        return ordered[lower]

    fraction = position - lower

    return (
        ordered[lower]
        + (ordered[upper] - ordered[lower])
        * fraction
    )


def _single_request(
    *,
    barrier: threading.Barrier,
    engine: Engine,
    policy: GovernedExecutionPolicy,
) -> GovernedExecutionResult:
    barrier.wait()

    return run_governed_sql(
        DEFAULT_QUERY,
        policy=policy,
        engine_override=engine,
    )


def _run_wave(
    *,
    concurrency: int,
    engine: Engine,
    policy: GovernedExecutionPolicy,
) -> dict[str, Any]:
    barrier = threading.Barrier(concurrency)
    observer = PoolObserver()
    checkout_listener = observer.on_checkout
    checkin_listener = observer.on_checkin

    event.listen(
        engine.pool,
        "checkout",
        checkout_listener,
    )
    event.listen(
        engine.pool,
        "checkin",
        checkin_listener,
    )

    started_at = perf_counter()

    try:
        with ThreadPoolExecutor(
            max_workers=concurrency,
            thread_name_prefix=(
                f"day72-load-{concurrency}"
            ),
        ) as executor:
            futures = [
                executor.submit(
                    _single_request,
                    barrier=barrier,
                    engine=engine,
                    policy=policy,
                )
                for _ in range(concurrency)
            ]

            results = [
                future.result()
                for future in as_completed(futures)
            ]
    finally:
        event.remove(
            engine.pool,
            "checkout",
            checkout_listener,
        )
        event.remove(
            engine.pool,
            "checkin",
            checkin_listener,
        )

    wall_time_ms = max(
        0.0,
        (perf_counter() - started_at) * 1_000,
    )

    latencies = [
        result.execution_time_ms
        for result in results
    ]

    error_counts = Counter(
        result.error_type.value
        for result in results
        if result.error_type is not None
    )

    success_count = sum(
        1
        for result in results
        if result.success
    )
    failure_count = len(results) - success_count

    return {
        "concurrency": concurrency,
        "request_count": len(results),
        "successful_requests": success_count,
        "failed_requests": failure_count,
        "error_rate": (
            failure_count / len(results)
            if results
            else 0.0
        ),
        "latency_p50_ms": _percentile(
            latencies,
            0.50,
        ),
        "latency_p95_ms": _percentile(
            latencies,
            0.95,
        ),
        "latency_max_ms": max(
            latencies,
            default=0.0,
        ),
        "wall_time_ms": wall_time_ms,
        "throughput_requests_per_second": (
            len(results) / (wall_time_ms / 1_000)
            if wall_time_ms > 0
            else 0.0
        ),
        "peak_checked_out_connections": (
            observer.peak_active
        ),
        "error_counts": dict(
            sorted(error_counts.items())
        ),
    }


def _aggregate_level(
    *,
    concurrency: int,
    waves: list[dict[str, Any]],
) -> dict[str, Any]:
    total_requests = sum(
        wave["request_count"]
        for wave in waves
    )
    success_count = sum(
        wave["successful_requests"]
        for wave in waves
    )
    failure_count = sum(
        wave["failed_requests"]
        for wave in waves
    )

    error_counts: Counter[str] = Counter()

    for wave in waves:
        error_counts.update(
            wave["error_counts"]
        )

    return {
        "concurrency": concurrency,
        "rounds": len(waves),
        "total_requests": total_requests,
        "successful_requests": success_count,
        "failed_requests": failure_count,
        "error_rate": (
            failure_count / total_requests
            if total_requests
            else 0.0
        ),
        "latency_p50_ms_mean_of_waves": (
            sum(
                wave["latency_p50_ms"]
                for wave in waves
            ) / len(waves)
            if waves
            else 0.0
        ),
        "latency_p95_ms_mean_of_waves": (
            sum(
                wave["latency_p95_ms"]
                for wave in waves
            ) / len(waves)
            if waves
            else 0.0
        ),
        "latency_max_ms": max(
            (
                wave["latency_max_ms"]
                for wave in waves
            ),
            default=0.0,
        ),
        "throughput_requests_per_second_mean": (
            sum(
                wave[
                    "throughput_requests_per_second"
                ]
                for wave in waves
            ) / len(waves)
            if waves
            else 0.0
        ),
        "peak_checked_out_connections": max(
            (
                wave[
                    "peak_checked_out_connections"
                ]
                for wave in waves
            ),
            default=0,
        ),
        "error_counts": dict(
            sorted(error_counts.items())
        ),
        "waves": waves,
    }


def _run_warmup(
    *,
    count: int,
    engine: Engine,
    policy: GovernedExecutionPolicy,
) -> None:
    for index in range(1, count + 1):
        result = run_governed_sql(
            DEFAULT_QUERY,
            policy=policy,
            engine_override=engine,
        )

        if not result.success:
            error_type = (
                result.error_type.value
                if result.error_type is not None
                else "unknown"
            )
            raise RuntimeError(
                "Warmup query failed "
                f"at attempt {index}: {error_type}"
            )


def run_load_test(
    *,
    concurrency_levels: tuple[int, ...],
    rounds: int,
    warmup: int,
    report_dir: Path,
) -> int:
    db_config = (
        load_governed_database_config()
    )
    engine = get_governed_engine()

    policy = GovernedExecutionPolicy(
        statement_timeout_ms=5_000,
        max_rows=10,
    )

    print("=" * 80)
    print("Day72 Minimum Load Test")
    print(
        "Pool: "
        f"size={db_config.pool_size}, "
        f"max_overflow={db_config.max_overflow}, "
        f"pool_timeout={db_config.pool_timeout_seconds}s"
    )
    print(
        "Theoretical max checked-out connections: "
        f"{db_config.pool_size + db_config.max_overflow}"
    )
    print(f"Warmup requests: {warmup}")
    print(f"Rounds per concurrency level: {rounds}")
    print(f"Query: {DEFAULT_QUERY}")

    _run_warmup(
        count=warmup,
        engine=engine,
        policy=policy,
    )

    levels: list[dict[str, Any]] = []

    for concurrency in concurrency_levels:
        print("=" * 80)
        print(
            f"Concurrency: {concurrency}"
        )

        waves = []

        for round_number in range(
            1,
            rounds + 1,
        ):
            wave = _run_wave(
                concurrency=concurrency,
                engine=engine,
                policy=policy,
            )
            waves.append(wave)

            print(
                f"Round {round_number}: "
                f"success={wave['successful_requests']}/"
                f"{wave['request_count']}, "
                f"error_rate={wave['error_rate']:.2%}, "
                f"p50={wave['latency_p50_ms']:.2f}ms, "
                f"p95={wave['latency_p95_ms']:.2f}ms, "
                f"max={wave['latency_max_ms']:.2f}ms, "
                f"peak_conn={wave['peak_checked_out_connections']}"
            )

            if wave["error_counts"]:
                print(
                    "Errors: "
                    f"{wave['error_counts']}"
                )

        aggregate = _aggregate_level(
            concurrency=concurrency,
            waves=waves,
        )
        levels.append(aggregate)

        print(
            "Aggregate: "
            f"requests={aggregate['total_requests']}, "
            f"error_rate={aggregate['error_rate']:.2%}, "
            f"mean_p50="
            f"{aggregate['latency_p50_ms_mean_of_waves']:.2f}ms, "
            f"mean_p95="
            f"{aggregate['latency_p95_ms_mean_of_waves']:.2f}ms, "
            f"max={aggregate['latency_max_ms']:.2f}ms, "
            f"peak_conn="
            f"{aggregate['peak_checked_out_connections']}"
        )

    report_dir.mkdir(
        parents=True,
        exist_ok=True,
    )
    timestamp = datetime.now(
        timezone.utc
    ).strftime("%Y%m%dT%H%M%SZ")
    report_path = report_dir / (
        f"governance_load_test_{timestamp}.json"
    )

    payload = {
        "generated_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "query": DEFAULT_QUERY,
        "rounds": rounds,
        "warmup": warmup,
        "database_runtime": {
            "pool_size": db_config.pool_size,
            "max_overflow": (
                db_config.max_overflow
            ),
            "pool_timeout_seconds": (
                db_config.pool_timeout_seconds
            ),
            "pool_recycle_seconds": (
                db_config.pool_recycle_seconds
            ),
            "theoretical_max_checked_out_connections": (
                db_config.pool_size
                + db_config.max_overflow
            ),
        },
        "execution_policy": {
            "statement_timeout_ms": (
                policy.statement_timeout_ms
            ),
            "max_rows": policy.max_rows,
            "policy_version": (
                policy.policy_version
            ),
        },
        "levels": levels,
    }

    report_path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("=" * 80)
    print(f"Report: {report_path}")

    unexpected_failures = sum(
        level["failed_requests"]
        for level in levels
    )

    return 1 if unexpected_failures else 0


def main() -> int:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--concurrency",
        nargs="+",
        type=int,
        default=list(
            DEFAULT_CONCURRENCY_LEVELS
        ),
        help=(
            "Concurrent request levels. "
            "Default: 10 25 50"
        ),
    )
    parser.add_argument(
        "--rounds",
        type=int,
        default=3,
        help=(
            "Waves per concurrency level. "
            "Default: 3"
        ),
    )
    parser.add_argument(
        "--warmup",
        type=int,
        default=3,
        help=(
            "Sequential warmup requests. "
            "Default: 3"
        ),
    )
    parser.add_argument(
        "--report-dir",
        default="docs/evaluation",
        help="JSON report directory.",
    )

    args = parser.parse_args()

    if any(
        value <= 0
        for value in args.concurrency
    ):
        raise SystemExit(
            "Concurrency values must be positive."
        )

    if args.rounds <= 0:
        raise SystemExit(
            "--rounds must be positive."
        )

    if args.warmup < 0:
        raise SystemExit(
            "--warmup cannot be negative."
        )

    return run_load_test(
        concurrency_levels=tuple(
            args.concurrency
        ),
        rounds=args.rounds,
        warmup=args.warmup,
        report_dir=Path(args.report_dir),
    )


if __name__ == "__main__":
    raise SystemExit(main())
