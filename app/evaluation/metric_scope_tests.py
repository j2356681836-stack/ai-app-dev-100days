from unittest.mock import patch

from app.semantic_layer.hybrid_search import search_metric
from app.semantic_layer.semantic_search_v2 import (
    search_metric_by_embedding,
)

def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(
            f"{message}\nExpected: {expected}\nActual: {actual}"
        )


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def extract_metric_names(result: dict) -> set[str]:
    items = (
        result.get("metrics")
        or result.get("suggestions")
        or result.get("options")
        or []
    )

    return {
        item.get("name") or item.get("metric_name")
        for item in items
        if item.get("name") or item.get("metric_name")
    }


def test_alias_only_returns_authorized_metric() -> None:
    result = search_metric(
        "哪个渠道销售额最高",
        allowed_metric_names={
            "channel_sales_amount",
        },
    )

    assert_equal(
        result.get("status"),
        "matched",
        "授权 Alias 指标应该正常命中。",
    )

    assert_equal(
        extract_metric_names(result),
        {"channel_sales_amount"},
        "Alias 结果只能包含授权指标。",
    )


def test_unauthorized_alias_is_not_returned() -> None:
    result = search_metric(
        "各渠道ROI排名",
        allowed_metric_names={
            "channel_sales_amount",
        },
    )

    names = extract_metric_names(result)

    assert_true(
        result.get("status") in {
            "matched",
            "needs_clarification",
        },
        "排除未授权 ROI 后，授权指标仍应正常完成检索。",
    )

    assert_equal(
        names,
        {"channel_sales_amount"},
        "结果应该只包含授权的渠道销售额指标。",
    )

    assert_true(
        "roi" not in names,
        "未授权 ROI 不得出现在结果中。",
    )


def test_empty_metric_scope_is_denied() -> None:
    result = search_metric(
        "哪个渠道销售额最高",
        allowed_metric_names=frozenset(),
    )

    assert_equal(
        result.get("status"),
        "access_denied",
        "空指标权限必须被拒绝。",
    )

    assert_equal(
        result.get("retryable"),
        False,
        "权限失败不得进入 Repair。",
    )


def test_embedding_candidates_are_authorized() -> None:
    allowed = {
        "order_count",
        "sales_quantity",
    }

    result = search_metric_by_embedding(
        "成交最多",
        allowed_metric_names=allowed,
    )

    names = {
        item["name"]
        for item in result.get("candidates", [])
    }

    assert_true(
        bool(names),
        "Embedding 应该返回至少一个授权候选。",
    )

    assert_true(
        names.issubset(allowed),
        "Embedding 全部候选不得超出授权集合。",
    )


def test_single_authorized_candidate_is_safe() -> None:
    result = search_metric(
        "最赚钱",
        allowed_metric_names={
            "roi",
        },
    )

    assert_true(
        result.get("status") in {
            "matched",
            "needs_clarification",
        },
        "单一授权候选必须安全返回，不能下标越界。",
    )

    assert_true(
        extract_metric_names(result).issubset({"roi"}),
        "单候选结果只能包含 ROI。",
    )


def test_clarification_does_not_leak_metrics() -> None:
    allowed = {
        "order_paid_amount",
        "item_sales_amount",
    }

    result = search_metric(
        "最赚钱",
        allowed_metric_names=allowed,
    )

    assert_equal(
        result.get("status"),
        "needs_clarification",
        "该案例应进入 Clarification，以验证候选重排后的权限边界。",
    )

    names = extract_metric_names(result)

    assert_true(
        bool(names),
        "Clarification 应至少返回一个授权候选。",
    )

    assert_true(
        names.issubset(allowed),
        "Clarification suggestions 不得泄漏未授权指标。",
    )

    trace_text = str(result.get("trace", {}))

    for forbidden_name in {
        "roi",
        "cac",
        "refund_rate",
        "channel_refund_rate",
    }:
        assert_true(
            forbidden_name not in trace_text,
            f"Trace 不得包含未授权指标 {forbidden_name}。",
        )


def test_single_low_score_candidate_clarification_is_safe() -> None:
    mock_embedding_result = {
        "status": "needs_clarification",
        "reason": "low_score",
        "method": "embedding",
        "question": "完全无关的问题",
        "top_metric": {
            "name": "roi",
            "chinese_name": "投资回报率",
            "score": 0.31,
        },
        "candidates": [
            {
                "name": "roi",
                "chinese_name": "投资回报率",
                "score": 0.31,
            }
        ],
        "is_confident": False,
    }

    with patch(
        "app.semantic_layer.hybrid_search."
        "search_metric_by_embedding",
        return_value=mock_embedding_result,
    ):
        result = search_metric(
            "完全无关的问题",
            allowed_metric_names={"roi"},
        )

    assert_equal(
        result.get("status"),
        "needs_clarification",
        "单一低分授权候选应安全进入 Clarification。",
    )

    assert_equal(
        extract_metric_names(result),
        {"roi"},
        "Clarification 只能包含唯一授权指标。",
    )

    embedding_trace = result["trace"]["embedding"]

    assert_equal(
        embedding_trace.get("top2"),
        None,
        "单候选场景的 top2 应为 None。",
    )

    assert_equal(
        embedding_trace.get("gap"),
        None,
        "单候选场景的 gap 应为 None。",
    )


def run_tests() -> None:
    tests = [
        test_alias_only_returns_authorized_metric,
        test_unauthorized_alias_is_not_returned,
        test_empty_metric_scope_is_denied,
        test_embedding_candidates_are_authorized,
        test_single_authorized_candidate_is_safe,
        test_single_low_score_candidate_clarification_is_safe,
        test_clarification_does_not_leak_metrics,
    ]

    passed = 0
    failed = 0

    for test in tests:
        print("=" * 80)
        print(f"Running: {test.__name__}")

        try:
            test()
            passed += 1
            print("[PASS]")
        except Exception as exc:
            failed += 1
            print("[FAIL]")
            print(exc)

    print("=" * 80)
    print("Metric Scope Test Summary")
    print(f"Total: {len(tests)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    run_tests()