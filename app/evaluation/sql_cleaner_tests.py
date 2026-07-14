from app.text_to_sql.sql_cleaner import clean_sql


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(
            f"{message}\n"
            f"Expected: {expected!r}\n"
            f"Actual: {actual!r}"
        )


def test_sql_without_semicolon() -> None:
    assert_equal(
        clean_sql("SELECT 1"),
        "SELECT 1;",
        "无分号 SQL 应补充一个结尾分号",
    )


def test_sql_with_single_semicolon() -> None:
    assert_equal(
        clean_sql("SELECT 1;"),
        "SELECT 1;",
        "单分号 SQL 应保持不变",
    )


def test_sql_with_double_semicolon() -> None:
    assert_equal(
        clean_sql("SELECT 1;;"),
        "SELECT 1;",
        "双分号 SQL 应规范化为一个分号",
    )


def test_sql_with_multiple_semicolons() -> None:
    assert_equal(
        clean_sql("SELECT 1;;;;"),
        "SELECT 1;",
        "多个结尾分号应规范化为一个分号",
    )


def test_markdown_sql_normalization() -> None:
    assert_equal(
        clean_sql("```sql\nSELECT 1;;\n```"),
        "SELECT 1;",
        "Markdown SQL 应移除代码围栏并规范化分号",
    )


def test_blank_sql() -> None:
    assert_equal(
        clean_sql("   "),
        "",
        "空白 SQL 应返回空字符串",
    )


def run_tests() -> None:
    tests = [
        test_sql_without_semicolon,
        test_sql_with_single_semicolon,
        test_sql_with_double_semicolon,
        test_sql_with_multiple_semicolons,
        test_markdown_sql_normalization,
        test_blank_sql,
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
        except Exception as exc:
            failed += 1
            print("❌ FAILED")
            print(exc)

    print("=" * 80)
    print("SQL Cleaner Test Summary")
    print(f"Total: {len(tests)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    run_tests()