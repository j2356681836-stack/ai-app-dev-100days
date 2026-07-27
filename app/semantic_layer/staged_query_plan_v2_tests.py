from pydantic import ValidationError

from app.governance.access_context import (
    AccessContext,
    AccessRole,
    OperationMode,
    SensitiveDataPolicy,
)
from app.governance.authorization import (
    authorize_resources,
)
from app.governance.row_scope import (
    plan_row_scope,
)
from app.governance.row_scope_binding import (
    build_scoped_query_contract,
)
from app.governance.sensitive_data import (
    protect_result_rows,
)
from app.semantic_layer.query_plan_v2_models import (
    QueryPlanV2,
    StagedQueryLogic,
)
from app.semantic_layer.staged_query_plan_v2_sample import (
    build_repeat_customer_count_overall_plan,
)


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(
            f"{message}\nExpected: {expected}\nActual: {actual}"
        )


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def build_context(plan) -> AccessContext:
    return AccessContext(
        request_id="req-day73-staged-query-001",
        actor_id="analyst-001",
        role=AccessRole.SCOPED_ANALYST,
        dataset_name="beauty_bi_v2",
        target_schema="beauty_bi_v2",
        operation_mode=OperationMode.OBSERVE_ADVISE,
        allowed_metrics=frozenset(
            {"repeat_customer_count"}
        ),
        allowed_tables=plan.resource_contract.required_tables,
        allowed_columns=plan.resource_contract.required_columns,
        denied_columns=frozenset(),
        allowed_region_codes=frozenset(
            {"SOUTH", "EAST"}
        ),
        allowed_channel_codes=frozenset(
            {"TMALL", "JD"}
        ),
        sensitive_data_policy=SensitiveDataPolicy(),
        policy_version="governance_v1",
        scope_source="day73_staged_query_fixture",
    )


def plan_payload() -> dict:
    return build_repeat_customer_count_overall_plan().model_dump(
        mode="json"
    )


def test_repeat_plan_uses_staged_logic() -> None:
    plan = build_repeat_customer_count_overall_plan()

    assert_true(
        isinstance(plan.query_logic, StagedQueryLogic),
        "复购人数样板必须使用 StagedQueryLogic。",
    )

    assert_equal(
        len(plan.query_logic.stages),
        2,
        "复购人数应由客户汇总 Stage + Final Stage 组成。",
    )

    assert_equal(
        plan.query_logic.final_stage,
        "final",
        "最终输出必须来自 final Stage。",
    )


def test_stage_one_freezes_cross_day_semantics() -> None:
    plan = build_repeat_customer_count_overall_plan()

    stage = plan.query_logic.stages[0]

    assert_equal(
        stage.stage_id,
        "customer_purchase_summary",
        "第一阶段应构造 customer purchase summary。",
    )

    assert_equal(
        stage.group_by,
        ("fo.customer_id",),
        "第一阶段必须按 customer 聚合。",
    )

    purchase_day_expression = next(
        output.expression
        for output in stage.outputs
        if output.field == "purchase_day_count"
    )

    assert_equal(
        purchase_day_expression,
        "COUNT(DISTINCT CAST(fo.paid_at AS DATE))",
        "同日多单必须只计一个购买日。",
    )


def test_final_stage_counts_repeat_customers() -> None:
    plan = build_repeat_customer_count_overall_plan()

    final_stage = plan.query_logic.stages[-1]

    expression = next(
        output.expression
        for output in final_stage.outputs
        if output.field == "repeat_customer_count"
    )

    assert_true(
        "purchase_day_count >= 2" in expression,
        "复购客户必须至少有两个不同购买日。",
    )

    assert_equal(
        final_stage.hidden_control_fields[0].field,
        "__group_size",
        "Final Stage 必须保留 Minimum Group Size 控制字段。",
    )


def test_staged_plan_is_authorizable() -> None:
    plan = build_repeat_customer_count_overall_plan()
    context = build_context(plan)

    decision = authorize_resources(
        context,
        required_tables=plan.resource_contract.required_tables,
        required_columns=plan.resource_contract.required_columns,
    )

    assert_equal(
        decision.allowed,
        True,
        "Staged Plan 资源合同应直接进入 Day68 Authorization。",
    )


def test_staged_plan_builds_row_scope_contract() -> None:
    plan = build_repeat_customer_count_overall_plan()
    context = build_context(plan)

    scope_decision = plan_row_scope(
        context,
        source_tables=plan.scope_contract.source_tables,
        required_dimensions=plan.scope_contract.required_dimensions,
    )

    assert_equal(
        scope_decision.allowed,
        True,
        "Staged Plan 应能创建 RowScopePlan。",
    )

    binding = build_scoped_query_contract(
        scope_decision.plan,
        targets=plan.to_scope_targets(),
    )

    assert_equal(
        binding.allowed,
        True,
        "第一阶段 fact_orders alias 应能绑定真实 Scope Contract。",
    )

    assert_equal(
        len(binding.contract.predicates),
        2,
        "复购人数仍必须获得 Region + Channel Predicate。",
    )


def test_staged_result_contract_can_protect_rows() -> None:
    plan = build_repeat_customer_count_overall_plan()

    result = protect_result_rows(
        context=build_context(plan),
        rows=[
            {
                "repeat_customer_count": 25,
                "__group_size": 100,
            },
        ],
        contract=plan.result_contract,
    )

    assert_equal(
        result.success,
        True,
        "普通复购聚合结果应能通过 Result Protection。",
    )

    assert_equal(
        result.rows,
        (
            {"repeat_customer_count": 25},
        ),
        "__group_size 必须在最终结果中隐藏。",
    )


def test_forward_stage_reference_is_rejected() -> None:
    payload = plan_payload()

    payload["query_logic"]["stages"][0]["source"] = {
        "stage_id": "final",
        "alias": "future",
    }

    try:
        QueryPlanV2.model_validate(payload)
    except ValidationError:
        return

    raise AssertionError(
        "Stage 不得引用尚未声明的后续 Stage。"
    )


def test_duplicate_stage_id_is_rejected() -> None:
    payload = plan_payload()

    payload["query_logic"]["stages"][1]["stage_id"] = (
        "customer_purchase_summary"
    )
    payload["query_logic"]["final_stage"] = (
        "customer_purchase_summary"
    )

    try:
        QueryPlanV2.model_validate(payload)
    except ValidationError:
        return

    raise AssertionError(
        "重复 stage_id 必须拒绝。"
    )


def test_final_stage_must_be_last_declared_stage() -> None:
    payload = plan_payload()

    payload["query_logic"]["final_stage"] = (
        "customer_purchase_summary"
    )

    try:
        QueryPlanV2.model_validate(payload)
    except ValidationError:
        return

    raise AssertionError(
        "final_stage 不得指向非最后阶段。"
    )


def test_scope_alias_must_bind_physical_stage_alias() -> None:
    payload = plan_payload()

    payload["scope_contract"]["targets"][0][
        "table_aliases"
    ][0]["alias"] = "cps"

    try:
        QueryPlanV2.model_validate(payload)
    except ValidationError:
        return

    raise AssertionError(
        "ScopeTarget 不得绑定 derived-stage alias。"
    )


def test_final_outputs_must_match_result_bindings() -> None:
    payload = plan_payload()

    payload["result_contract"]["field_bindings"] = []

    try:
        QueryPlanV2.model_validate(payload)
    except ValidationError:
        return

    raise AssertionError(
        "Final Stage 输出必须与 Result Binding 完全一致。"
    )


def test_staged_plan_is_immutable() -> None:
    plan = build_repeat_customer_count_overall_plan()

    try:
        plan.query_logic.final_stage = "changed"
    except ValidationError:
        return

    raise AssertionError(
        "StagedQueryLogic 创建后必须不可修改。"
    )


def run_tests() -> None:
    tests = [
        test_repeat_plan_uses_staged_logic,
        test_stage_one_freezes_cross_day_semantics,
        test_final_stage_counts_repeat_customers,
        test_staged_plan_is_authorizable,
        test_staged_plan_builds_row_scope_contract,
        test_staged_result_contract_can_protect_rows,
        test_forward_stage_reference_is_rejected,
        test_duplicate_stage_id_is_rejected,
        test_final_stage_must_be_last_declared_stage,
        test_scope_alias_must_bind_physical_stage_alias,
        test_final_outputs_must_match_result_bindings,
        test_staged_plan_is_immutable,
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
    print("Staged Query Plan V2 Test Summary")
    print(f"Total: {len(tests)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    run_tests()
