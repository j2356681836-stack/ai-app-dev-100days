"""
Compatibility sample for the Global History Contract.

The production candidate now lives in:
app.semantic_layer.channel_new_customer_query_plan_v2

This module intentionally re-exports the builder so the original
Global History contract tests keep exercising the production contract
instead of a duplicated sample implementation.
"""

from app.semantic_layer.channel_new_customer_query_plan_v2 import (
    build_channel_paid_new_customer_count_channel_plan,
)


__all__ = [
    "build_channel_paid_new_customer_count_channel_plan",
]


if __name__ == "__main__":
    plan = (
        build_channel_paid_new_customer_count_channel_plan()
    )

    history = (
        plan.scope_contract.history_contract
    )

    print("Global History Query Plan V2 Sample")
    print(f"Plan: {plan.name}")
    print(f"Scope mode: {plan.scope_contract.scope_mode.value}")
    print(
        "Pre-sequence dimensions:",
        sorted(
            item.value
            for item in (
                history.pre_sequence_scope_dimensions()
            )
        ),
    )
    print(
        "Post-sequence dimensions:",
        sorted(
            item.value
            for item in (
                history.post_sequence_scope_dimensions
            )
        ),
    )
