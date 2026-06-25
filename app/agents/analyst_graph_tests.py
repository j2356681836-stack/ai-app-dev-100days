from app.agents.analyst_graph import ask_with_graph


def assert_equal(actual, expected, message: str):
    if actual != expected:
        raise AssertionError(
            f"{message}\nExpected: {expected}\nActual: {actual}"
        )


def test_llm_metric_path():
    """
    普通指标路径：
    渠道销售额 → matched → continue_pipeline → LLM SQL
    """
    result = ask_with_graph("哪个渠道销售额最高")

    assert_equal(
        result.get("success"),
        True,
        "普通指标路径应该成功",
    )

    assert_equal(
        result.get("status"),
        "completed",
        "普通指标路径状态应该是 completed",
    )

    assert_equal(
        result.get("generation_method"),
        "llm",
        "渠道销售额当前应走 LLM SQL 路径",
    )

    assert result.get("answer"), "普通指标路径应该返回 answer"


def test_template_metric_path():
    """
    复杂指标路径：
    ROI → matched → continue_pipeline → Template SQL
    """
    result = ask_with_graph("各渠道ROI排名")

    assert_equal(
        result.get("success"),
        True,
        "ROI 路径应该成功",
    )

    assert_equal(
        result.get("status"),
        "completed",
        "ROI 路径状态应该是 completed",
    )

    assert_equal(
        result.get("generation_method"),
        "template",
        "ROI 当前应走 Template SQL 路径",
    )

    assert result.get("answer"), "ROI 路径应该返回 answer"


def test_clarification_path():
    """
    歧义问题路径：
    最赚钱 → needs_clarification → clarification branch
    """
    result = ask_with_graph("最赚钱")

    assert_equal(
        result.get("success"),
        False,
        "歧义问题不应该直接成功",
    )

    assert_equal(
        result.get("status"),
        "needs_clarification",
        "歧义问题应该进入 clarification 分支",
    )

    assert result.get("message"), "clarification 分支应该返回 message"

    suggestions = result.get("suggestions", [])
    assert suggestions, "clarification 分支应该返回候选指标 suggestions"


def run_tests():
    tests = [
        test_llm_metric_path,
        test_template_metric_path,
        test_clarification_path,
    ]

    passed = 0
    failed = 0

    for test in tests:
        print("=" * 80)
        print(f"Running: {test.__name__}")

        try:
            test()
            passed += 1
            print("✅ PASSED")
        except Exception as e:
            failed += 1
            print("❌ FAILED")
            print(e)

    print("=" * 80)
    print("Analyst Graph Test Summary")
    print(f"Total: {len(tests)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    run_tests()