from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from app.delivery import runtime_delivery_bridge_v2 as bridge
from app.semantic_layer import query_plan_v2_loader as loader


def test_query_plan_catalog_is_cached() -> None:
    loader.clear_query_plan_v2_catalog_cache()

    original_open = Path.open
    query_plan_reads = 0

    def counted_open(self, *args, **kwargs):
        nonlocal query_plan_reads
        if self.name == "query_plans.yaml":
            query_plan_reads += 1
        return original_open(self, *args, **kwargs)

    with patch.object(Path, "open", new=counted_open):
        first = loader.load_query_plan_v2_catalog()
        second = loader.load_query_plan_v2_catalog()
        assert first is second

        loader.get_query_plan_v2_by_name("gmv_overall_v2")
        loader.get_query_plan_v2_by_name("buyer_count_overall_v2")
        loader.get_query_plans_v2_by_metric("gmv")

    assert query_plan_reads == 1


def test_query_plan_cache_can_be_invalidated() -> None:
    loader.clear_query_plan_v2_catalog_cache()
    first = loader.load_query_plan_v2_catalog()

    loader.clear_query_plan_v2_catalog_cache()
    second = loader.load_query_plan_v2_catalog()

    assert first is not second
    assert first.query_plan_version == second.query_plan_version


def test_business_metric_catalog_and_snapshot_are_cached() -> None:
    bridge.clear_runtime_metric_metadata_cache_v2()

    original_read_text = Path.read_text
    business_metric_reads = 0

    def counted_read_text(self, *args, **kwargs):
        nonlocal business_metric_reads
        if self.name == "business_metrics.yaml":
            business_metric_reads += 1
        return original_read_text(self, *args, **kwargs)

    with patch.object(Path, "read_text", new=counted_read_text):
        gmv_first = bridge._load_metric_definition_v2("gmv")
        gmv_second = bridge._load_metric_definition_v2("gmv")
        buyer = bridge._load_metric_definition_v2("buyer_count")

    assert gmv_first is gmv_second
    assert buyer is not None
    assert business_metric_reads == 1


def test_metric_metadata_cache_can_be_invalidated() -> None:
    bridge.clear_runtime_metric_metadata_cache_v2()
    first = bridge._load_metric_definition_v2("gmv")

    bridge.clear_runtime_metric_metadata_cache_v2()
    second = bridge._load_metric_definition_v2("gmv")

    assert first is not second


TESTS = (
    test_query_plan_catalog_is_cached,
    test_query_plan_cache_can_be_invalidated,
    test_business_metric_catalog_and_snapshot_are_cached,
    test_metric_metadata_cache_can_be_invalidated,
)


def run_acceptance() -> None:
    passed = 0
    failed = 0

    print("=" * 80)
    print("Day93 Static Contract Cache Acceptance")
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
    print("Day93 Static Contract Cache Acceptance Summary")
    print(f"Total: {len(TESTS)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    run_acceptance()
