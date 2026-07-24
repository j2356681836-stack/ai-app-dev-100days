from pydantic import ValidationError

from app.governance.execution_budget import (
    BudgetErrorType,
    BudgetReason,
    ExecutionBudgetPolicy,
    TokenUsage,
    build_budget_policy_fingerprint,
    consume_retry,
    consume_step,
    consume_token_usage,
    create_initial_budget_state,
    remaining_completion_token_allowance,
    validate_retry_contract,
)


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(
            f"{message}\nExpected: {expected}\nActual: {actual}"
        )


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_policy_is_immutable() -> None:
    policy = ExecutionBudgetPolicy()

    try:
        policy.max_steps = 99
    except ValidationError:
        return

    raise AssertionError(
        "ExecutionBudgetPolicy must be immutable."
    )


def test_invalid_total_token_policy_is_rejected() -> None:
    try:
        ExecutionBudgetPolicy(
            max_prompt_tokens=100,
            max_completion_tokens=100,
            max_total_tokens=50,
        )
    except ValidationError:
        return

    raise AssertionError(
        "max_total_tokens cannot be smaller than "
        "individual limits."
    )


def test_initial_state_is_zeroed_and_bound() -> None:
    policy = ExecutionBudgetPolicy()
    state = create_initial_budget_state(policy)

    assert_equal(
        state.steps_used,
        0,
        "Initial steps must be zero.",
    )

    assert_equal(
        state.total_tokens_used,
        0,
        "Initial tokens must be zero.",
    )

    assert_equal(
        state.policy_fingerprint,
        build_budget_policy_fingerprint(policy),
        "State must bind to the active policy.",
    )


def test_step_consumption_succeeds_within_limit() -> None:
    policy = ExecutionBudgetPolicy(max_steps=2)
    state = create_initial_budget_state(policy)

    decision = consume_step(
        policy=policy,
        state=state,
        operation="parse_intent",
    )

    assert_equal(
        decision.allowed,
        True,
        "First step should be allowed.",
    )

    assert_equal(
        decision.state.steps_used,
        1,
        "Step count should increment.",
    )


def test_exact_step_limit_is_allowed() -> None:
    policy = ExecutionBudgetPolicy(max_steps=2)
    state = create_initial_budget_state(policy)

    first = consume_step(
        policy=policy,
        state=state,
        operation="step_1",
    )

    second = consume_step(
        policy=policy,
        state=first.state,
        operation="step_2",
    )

    assert_equal(
        second.allowed,
        True,
        "Exact step limit should be allowed.",
    )

    assert_equal(
        second.state.steps_used,
        2,
        "Exact step limit should be recorded.",
    )


def test_step_limit_exceeded_is_non_retryable() -> None:
    policy = ExecutionBudgetPolicy(max_steps=1)
    state = create_initial_budget_state(policy)

    first = consume_step(
        policy=policy,
        state=state,
        operation="step_1",
    )

    denied = consume_step(
        policy=policy,
        state=first.state,
        operation="step_2",
    )

    assert_equal(
        denied.allowed,
        False,
        "Step above limit must be denied.",
    )

    assert_equal(
        denied.error_type,
        BudgetErrorType.EXECUTION_BUDGET_ERROR,
        "Budget denial must use execution_budget_error.",
    )

    assert_equal(
        denied.reason_code,
        BudgetReason.STEP_LIMIT_EXCEEDED,
        "Step denial must use step_limit_exceeded.",
    )

    assert_equal(
        denied.retryable,
        False,
        "Step denial must not enter SQL Repair.",
    )


def test_retry_limit_is_enforced() -> None:
    policy = ExecutionBudgetPolicy(max_retries=1)
    state = create_initial_budget_state(policy)

    first = consume_retry(
        policy=policy,
        state=state,
    )

    denied = consume_retry(
        policy=policy,
        state=first.state,
    )

    assert_equal(
        first.allowed,
        True,
        "First retry should be allowed.",
    )

    assert_equal(
        denied.reason_code,
        BudgetReason.RETRY_LIMIT_EXCEEDED,
        "Second retry must be denied.",
    )


def test_token_usage_accumulates() -> None:
    policy = ExecutionBudgetPolicy(
        max_prompt_tokens=100,
        max_completion_tokens=50,
        max_total_tokens=150,
        max_completion_tokens_per_call=25,
    )

    state = create_initial_budget_state(policy)

    decision = consume_token_usage(
        policy=policy,
        state=state,
        usage=TokenUsage(
            prompt_tokens=40,
            completion_tokens=10,
            total_tokens=50,
        ),
        operation="sql_generation",
    )

    assert_equal(
        decision.allowed,
        True,
        "Usage within budget should be allowed.",
    )

    assert_equal(
        decision.state.total_tokens_used,
        50,
        "Total token usage should accumulate.",
    )


def test_prompt_token_limit_is_enforced() -> None:
    policy = ExecutionBudgetPolicy(
        max_prompt_tokens=40,
        max_completion_tokens=100,
        max_total_tokens=150,
        max_completion_tokens_per_call=100,
    )

    decision = consume_token_usage(
        policy=policy,
        state=create_initial_budget_state(policy),
        usage=TokenUsage(
            prompt_tokens=41,
            completion_tokens=1,
            total_tokens=42,
        ),
        operation="sql_generation",
    )

    assert_equal(
        decision.reason_code,
        BudgetReason.PROMPT_TOKEN_LIMIT_EXCEEDED,
        "Prompt overage must be classified correctly.",
    )

    assert_equal(
        decision.state.total_tokens_used,
        42,
        "Already consumed tokens must remain recorded.",
    )


def test_completion_token_limit_is_enforced() -> None:
    policy = ExecutionBudgetPolicy(
        max_prompt_tokens=100,
        max_completion_tokens=10,
        max_total_tokens=110,
        max_completion_tokens_per_call=10,
    )

    decision = consume_token_usage(
        policy=policy,
        state=create_initial_budget_state(policy),
        usage=TokenUsage(
            prompt_tokens=1,
            completion_tokens=11,
            total_tokens=12,
        ),
        operation="sql_repair",
    )

    assert_equal(
        decision.reason_code,
        (
            BudgetReason
            .COMPLETION_TOKEN_LIMIT_EXCEEDED
        ),
        "Completion overage must be classified correctly.",
    )


def test_total_token_limit_is_enforced() -> None:
    policy = ExecutionBudgetPolicy(
        max_prompt_tokens=100,
        max_completion_tokens=100,
        max_total_tokens=100,
        max_completion_tokens_per_call=100,
    )

    state = create_initial_budget_state(policy)

    first = consume_token_usage(
        policy=policy,
        state=state,
        usage=TokenUsage(
            prompt_tokens=40,
            completion_tokens=10,
            total_tokens=50,
        ),
        operation="sql_generation",
    )

    denied = consume_token_usage(
        policy=policy,
        state=first.state,
        usage=TokenUsage(
            prompt_tokens=40,
            completion_tokens=20,
            total_tokens=60,
        ),
        operation="sql_repair",
    )

    assert_equal(
        denied.reason_code,
        BudgetReason.TOTAL_TOKEN_LIMIT_EXCEEDED,
        "Cumulative total overage must be classified.",
    )

    assert_equal(
        denied.state.total_tokens_used,
        110,
        "Actual consumed total must remain recorded.",
    )


def test_invalid_token_usage_is_rejected() -> None:
    try:
        TokenUsage(
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=14,
        )
    except ValidationError:
        return

    raise AssertionError(
        "total_tokens smaller than prompt + completion "
        "must be rejected."
    )


def test_exhausted_budget_cannot_be_reused() -> None:
    policy = ExecutionBudgetPolicy(max_steps=1)
    state = create_initial_budget_state(policy)

    first = consume_step(
        policy=policy,
        state=state,
        operation="step_1",
    )

    denied = consume_step(
        policy=policy,
        state=first.state,
        operation="step_2",
    )

    reused = consume_retry(
        policy=policy,
        state=denied.state,
    )

    assert_equal(
        reused.reason_code,
        BudgetReason.BUDGET_ALREADY_EXHAUSTED,
        "Exhausted budget must fail closed.",
    )


def test_remaining_completion_allowance_is_bounded() -> None:
    policy = ExecutionBudgetPolicy(
        max_prompt_tokens=100,
        max_completion_tokens=30,
        max_total_tokens=100,
        max_completion_tokens_per_call=20,
    )

    state = create_initial_budget_state(policy)

    first = consume_token_usage(
        policy=policy,
        state=state,
        usage=TokenUsage(
            prompt_tokens=60,
            completion_tokens=15,
            total_tokens=75,
        ),
        operation="sql_generation",
    )

    remaining = remaining_completion_token_allowance(
        policy=policy,
        state=first.state,
    )

    assert_equal(
        remaining,
        15,
        "Allowance must respect completion and total remainder.",
    )


def test_retry_contract_alignment() -> None:
    policy = ExecutionBudgetPolicy(max_retries=1)

    allowed = validate_retry_contract(
        policy=policy,
        graph_max_retries=1,
    )

    denied = validate_retry_contract(
        policy=policy,
        graph_max_retries=2,
    )

    assert_equal(
        allowed.allowed,
        True,
        "Matching Graph retry contract should pass.",
    )

    assert_equal(
        denied.reason_code,
        BudgetReason.RETRY_CONTRACT_MISMATCH,
        "Graph retry limit above policy must fail.",
    )


def test_policy_fingerprint_is_stable_and_sensitive() -> None:
    first = ExecutionBudgetPolicy(max_steps=25)
    same = ExecutionBudgetPolicy(max_steps=25)
    changed = ExecutionBudgetPolicy(max_steps=26)

    assert_equal(
        build_budget_policy_fingerprint(first),
        build_budget_policy_fingerprint(same),
        "Equivalent policies need identical fingerprints.",
    )

    assert_true(
        build_budget_policy_fingerprint(first)
        != build_budget_policy_fingerprint(changed),
        "Policy changes must change the fingerprint.",
    )


def run_tests() -> None:
    tests = [
        test_policy_is_immutable,
        test_invalid_total_token_policy_is_rejected,
        test_initial_state_is_zeroed_and_bound,
        test_step_consumption_succeeds_within_limit,
        test_exact_step_limit_is_allowed,
        test_step_limit_exceeded_is_non_retryable,
        test_retry_limit_is_enforced,
        test_token_usage_accumulates,
        test_prompt_token_limit_is_enforced,
        test_completion_token_limit_is_enforced,
        test_total_token_limit_is_enforced,
        test_invalid_token_usage_is_rejected,
        test_exhausted_budget_cannot_be_reused,
        test_remaining_completion_allowance_is_bounded,
        test_retry_contract_alignment,
        test_policy_fingerprint_is_stable_and_sensitive,
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
    print("Execution Budget Test Summary")
    print(f"Total: {len(tests)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    run_tests()
