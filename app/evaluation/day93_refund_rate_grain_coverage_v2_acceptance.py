from __future__ import annotations

from app.governance.sensitive_data import (
    SensitiveDataCategory,
)
from app.semantic_layer.query_plan_v2_catalog_builder import (
    build_query_plan_v2_catalog,
)
from app.semantic_layer.query_plan_v2_models import (
    StagedQueryLogic,
)


def run_acceptance() -> None:
    passed = 0

    catalog = build_query_plan_v2_catalog()

    assert len(catalog.query_plans) == 59
    passed += 1

    refund_plans = tuple(
        plan
        for plan in catalog.query_plans
        if plan.metric == "refund_rate"
    )

    assert {
        plan.result_grain
        for plan in refund_plans
    } == {
        "overall",
        "channel",
        "region",
        "category",
    }
    assert len(refund_plans) == 4
    passed += 1

    for plan in refund_plans:
        assert isinstance(
            plan.query_logic,
            StagedQueryLogic,
        )

        first_stage = plan.query_logic.stages[0]

        refund_join = next(
            join
            for join in first_stage.joins
            if getattr(join, "table", None)
            == "fact_refunds"
        )
        assert refund_join.join_type == "left"

        expression = next(
            output.expression
            for output in first_stage.outputs
            if output.field
            == "completed_refund_amount"
        )
        assert "SUM(fr.refund_amount) FILTER" in expression
        assert "fr.refund_status = 'completed'" in expression
    passed += 1

    expected_dimension_fields = {
        "overall": None,
        "channel": "channel_name",
        "region": "region_name",
        "category": "category",
    }

    for plan in refund_plans:
        final_fields = {
            output.field
            for output in plan.query_logic.stages[-1].outputs
        }

        dimension_field = expected_dimension_fields[
            plan.result_grain
        ]

        assert "refund_rate" in final_fields

        if dimension_field is not None:
            assert dimension_field in final_fields
    passed += 1

    for plan in refund_plans:
        binding = next(
            item
            for item in plan.result_contract.field_bindings
            if item.output_field == "refund_rate"
        )
        assert (
            binding.category
            == SensitiveDataCategory
            .AGGREGATED_BUSINESS_CONFIDENTIAL
        )
        assert plan.result_contract.minimum_group_size_required
        assert plan.result_contract.group_size_field == "__group_size"
    passed += 1

    assert sum(
        isinstance(
            plan.query_logic,
            StagedQueryLogic,
        )
        for plan in catalog.query_plans
    ) == 17
    passed += 1

    print(
        "Day93 Refund Rate Grain Coverage V2 Acceptance: "
        f"{passed}/6 PASS"
    )


if __name__ == "__main__":
    run_acceptance()
