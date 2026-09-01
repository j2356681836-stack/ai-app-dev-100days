import ast
import inspect
import textwrap

from app.agents.investigation_route_v2 import GeographyLevelV2
from app.delivery.investigation_runtime_v2 import (
    _day93_geography_action_v2,
    run_day93_geography_exploration_v2,
)


def test_exploration_uses_registered_deeper_query_plans() -> None:
    province = _day93_geography_action_v2(
        GeographyLevelV2.PROVINCE
    )
    city = _day93_geography_action_v2(
        GeographyLevelV2.CITY
    )

    province_args = {
        item.name: item.value
        for item in province.arguments
    }
    city_args = {
        item.name: item.value
        for item in city.arguments
    }

    assert (
        province_args["query_plan_name"]
        == "gmv_province_v2"
    )
    assert (
        city_args["query_plan_name"]
        == "gmv_city_v2"
    )

    print(
        "PASS: "
        "test_exploration_uses_registered_deeper_query_plans"
    )


def _called_function_names(fn) -> set[str]:
    """
    Inspect executable calls only.

    Do not scan raw source text because docstrings/comments may correctly
    mention forbidden Investigation concepts while the function does not
    actually invoke them.
    """
    source = textwrap.dedent(
        inspect.getsource(fn)
    )
    tree = ast.parse(source)

    names: set[str] = set()

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        target = node.func

        if isinstance(target, ast.Name):
            names.add(target.id)
        elif isinstance(target, ast.Attribute):
            names.add(target.attr)

    return names


def test_exploration_contract_is_separate_from_investigation_loop() -> None:
    calls = _called_function_names(
        run_day93_geography_exploration_v2
    )

    forbidden_calls = {
        "build_investigation_session_from_delivery_v2",
        "continue_investigation_session_v2",
        "advance_investigation_loop_v2",
        "run_one_investigation_step_v2",
        "merge_requested_scope_with_geography_focus_v2",
    }

    leaked = forbidden_calls.intersection(calls)

    assert not leaked, (
        "Exploration must stay outside the Investigation Loop; "
        f"unexpected calls={sorted(leaked)}"
    )

    # Exploration must still use the original trusted Requested Scope
    # and the normal governed query/evidence path.
    required_calls = {
        "_prepare_day89_trusted_binding_v2",
        "build_global_change_breakdown_delivery_v2",
    }

    missing = required_calls - calls

    assert not missing, (
        "Exploration is missing required governed execution/evidence calls: "
        f"{sorted(missing)}"
    )

    print(
        "PASS: "
        "test_exploration_contract_is_separate_from_investigation_loop"
    )


def main() -> None:
    test_exploration_uses_registered_deeper_query_plans()
    test_exploration_contract_is_separate_from_investigation_loop()


if __name__ == "__main__":
    main()
