from __future__ import annotations

from datetime import date, datetime
from typing import Any

from langgraph.graph import END, START, StateGraph
from sqlalchemy.engine import Engine

from app.agents.governed_graph_nodes_v2 import (
    GovernedAnalystStateV2,
    analytics_planning_node,
    analytics_stop_node,
    ast_stop_node,
    budget_stop_node,
    compilation_stop_node,
    compile_query_plan_node,
    final_answer_node,
    finish_node,
    governed_execute_node,
    governed_planning_node,
    governed_planning_stop_node,
    load_query_plan_node,
    planning_contract_stop_node,
    resolve_time_node,
    route_analytics_planning,
    route_compilation,
    route_governed_execution,
    route_governed_planning,
    route_plan_load,
    route_runtime_ast_gate,
    route_time_resolution,
    runtime_ast_gate_node,
)
from app.governance.access_context import AccessContext
from app.governance.execution_budget import (
    ExecutionBudgetPolicy,
    ExecutionBudgetState,
    create_initial_budget_state,
)
from app.governance.execution_policy import GovernedExecutionPolicy
from app.governance.governance_runtime import GovernanceRuntimeConfig
from app.semantic_layer.question_semantic_parser_v2 import LLMCall


def build_governed_analyst_graph_v2():
    """
    Dataset V2 candidate Graph.

    Day80 Step 1 deliberately keeps this graph independent from the
    Day60 V1 Stable Graph.

    SQL Repair / Retry Budget routing is not part of this first step.
    """
    graph = StateGraph(
        GovernedAnalystStateV2
    )

    graph.add_node(
        "analytics_planning",
        analytics_planning_node,
    )
    graph.add_node(
        "load_query_plan",
        load_query_plan_node,
    )
    graph.add_node(
        "resolve_time",
        resolve_time_node,
    )
    graph.add_node(
        "governed_planning",
        governed_planning_node,
    )
    graph.add_node(
        "compile_query_plan",
        compile_query_plan_node,
    )
    graph.add_node(
        "runtime_ast_gate",
        runtime_ast_gate_node,
    )
    graph.add_node(
        "governed_execute",
        governed_execute_node,
    )
    graph.add_node(
        "final_answer",
        final_answer_node,
    )
    graph.add_node(
        "finish",
        finish_node,
    )

    graph.add_node(
        "budget_stop",
        budget_stop_node,
    )
    graph.add_node(
        "analytics_stop",
        analytics_stop_node,
    )
    graph.add_node(
        "planning_contract_stop",
        planning_contract_stop_node,
    )
    graph.add_node(
        "governed_planning_stop",
        governed_planning_stop_node,
    )
    graph.add_node(
        "compilation_stop",
        compilation_stop_node,
    )
    graph.add_node(
        "ast_stop",
        ast_stop_node,
    )

    graph.add_edge(
        START,
        "analytics_planning",
    )

    graph.add_conditional_edges(
        "analytics_planning",
        route_analytics_planning,
        {
            "load_query_plan": "load_query_plan",
            "analytics_stop": "analytics_stop",
            "budget_stop": "budget_stop",
        },
    )

    graph.add_conditional_edges(
        "load_query_plan",
        route_plan_load,
        {
            "resolve_time": "resolve_time",
            "planning_contract_stop": (
                "planning_contract_stop"
            ),
            "budget_stop": "budget_stop",
        },
    )

    graph.add_conditional_edges(
        "resolve_time",
        route_time_resolution,
        {
            "governed_planning": "governed_planning",
            "budget_stop": "budget_stop",
        },
    )

    graph.add_conditional_edges(
        "governed_planning",
        route_governed_planning,
        {
            "compile_query_plan": "compile_query_plan",
            "governed_planning_stop": (
                "governed_planning_stop"
            ),
            "budget_stop": "budget_stop",
        },
    )

    graph.add_conditional_edges(
        "compile_query_plan",
        route_compilation,
        {
            "runtime_ast_gate": "runtime_ast_gate",
            "compilation_stop": "compilation_stop",
            "budget_stop": "budget_stop",
        },
    )

    graph.add_conditional_edges(
        "runtime_ast_gate",
        route_runtime_ast_gate,
        {
            "governed_execute": "governed_execute",
            "ast_stop": "ast_stop",
            "budget_stop": "budget_stop",
        },
    )

    graph.add_conditional_edges(
        "governed_execute",
        route_governed_execution,
        {
            "final_answer": "final_answer",
            "budget_stop": "budget_stop",
        },
    )
    graph.add_edge(
        "final_answer",
        "finish",
    )

    for terminal in (
        "budget_stop",
        "analytics_stop",
        "planning_contract_stop",
        "governed_planning_stop",
        "compilation_stop",
        "ast_stop",
        "finish",
    ):
        graph.add_edge(
            terminal,
            END,
        )

    return graph.compile()


def ask_with_governed_graph_v2(
    *,
    context: AccessContext,
    question: str,
    reference_date: date,
    runtime_config: GovernanceRuntimeConfig,
    llm_call: LLMCall | None = None,
    execution_policy: GovernedExecutionPolicy | None = None,
    engine_override: Engine | None = None,
    budget_policy: ExecutionBudgetPolicy | None = None,
    budget_state: ExecutionBudgetState | None = None,
    event_id: str | None = None,
    occurred_at_utc: datetime | None = None,
    written_at_utc: datetime | None = None,
) -> dict[str, Any]:
    """
    Invoke the Dataset V2 candidate Graph.

    Public return boundary:
    - safe stage evidence and fingerprints are allowed;
    - raw SQL and raw database rows are not returned.
    """
    active_budget_policy = (
        budget_policy
        if budget_policy is not None
        else ExecutionBudgetPolicy()
    )
    active_budget_state = (
        budget_state
        if budget_state is not None
        else create_initial_budget_state(
            active_budget_policy
        )
    )

    app = build_governed_analyst_graph_v2()

    state = app.invoke(
        {
            "question": question,
            "context": context,
            "reference_date": reference_date,
            "runtime_config": runtime_config,
            "llm_call": llm_call,
            "execution_policy": execution_policy,
            "engine_override": engine_override,
            "budget_policy": active_budget_policy,
            "budget_state": active_budget_state,
            "event_id": event_id,
            "occurred_at_utc": occurred_at_utc,
            "written_at_utc": written_at_utc,
        }
    )

    return state.get(
        "result",
        {
            "success": False,
            "outcome": "failed",
            "stop_stage": "graph_runtime",
            "message": (
                "Governed Graph finished without a public result."
            ),
        },
    )
