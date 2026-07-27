from enum import Enum

from pydantic import BaseModel, ConfigDict, model_validator

from app.governance.row_scope import ScopeDimension
from app.semantic_layer.query_plan_v2_models import (
    QueryPlanV2,
    ScopeMode,
)


class GlobalHistoryScopeReason(str, Enum):
    ALLOWED = "allowed"
    NOT_GLOBAL_HISTORY_PLAN = "not_global_history_plan"
    POST_SEQUENCE_SCOPE_REQUIRED = (
        "post_sequence_scope_required"
    )


class GlobalHistoryScopeDecision(BaseModel):
    """
    Can the CURRENT physical-table Row Scope engine safely enforce this
    Global History plan before sequencing?

    This does not grant additional data access. If a required dimension
    must be applied after sequencing, current execution fails closed.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    allowed: bool
    reason_code: GlobalHistoryScopeReason
    message: str

    safe_pre_sequence_dimensions: frozenset[
        ScopeDimension
    ] = frozenset()

    unsupported_post_sequence_dimensions: frozenset[
        ScopeDimension
    ] = frozenset()

    retryable: bool = False

    @model_validator(mode="after")
    def validate_decision(self):
        if self.allowed:
            if (
                self.reason_code
                != GlobalHistoryScopeReason.ALLOWED
            ):
                raise ValueError(
                    "Allowed decision must use reason_code=allowed."
                )

            if self.unsupported_post_sequence_dimensions:
                raise ValueError(
                    "Allowed decision cannot contain unsupported "
                    "post-sequence dimensions."
                )
        else:
            if (
                self.reason_code
                == GlobalHistoryScopeReason.ALLOWED
            ):
                raise ValueError(
                    "Denied decision cannot use reason_code=allowed."
                )

        if self.retryable:
            raise ValueError(
                "Global History scope incompatibility is never retryable."
            )

        return self


def evaluate_global_history_scope(
    plan: QueryPlanV2,
) -> GlobalHistoryScopeDecision:
    """
    Fail closed when current Row Scope placement would change first-event
    identity.

    The current engine can inject predicates only against physical table
    targets before derived-stage sequencing. Therefore only dimensions
    explicitly proven safe by pre_sequence_scope_bindings are executable.
    """
    scope = plan.scope_contract

    if scope.scope_mode != ScopeMode.GLOBAL_HISTORY_REQUIRED:
        return GlobalHistoryScopeDecision(
            allowed=False,
            reason_code=(
                GlobalHistoryScopeReason
                .NOT_GLOBAL_HISTORY_PLAN
            ),
            message=(
                "The query plan does not require Global History "
                "sequencing."
            ),
            retryable=False,
        )

    history = scope.history_contract

    if history is None:
        raise ValueError(
            "Validated global_history_required plan "
            "must contain history_contract."
        )

    safe_dimensions = (
        history.pre_sequence_scope_dimensions()
    )

    unsafe_dimensions = (
        history.post_sequence_scope_dimensions
    )

    if unsafe_dimensions:
        return GlobalHistoryScopeDecision(
            allowed=False,
            reason_code=(
                GlobalHistoryScopeReason
                .POST_SEQUENCE_SCOPE_REQUIRED
            ),
            message=(
                "One or more required Row Scope dimensions "
                "must be applied after first-event sequencing, "
                "which the current physical-target scope engine "
                "cannot enforce safely."
            ),
            safe_pre_sequence_dimensions=(
                safe_dimensions
            ),
            unsupported_post_sequence_dimensions=(
                unsafe_dimensions
            ),
            retryable=False,
        )

    return GlobalHistoryScopeDecision(
        allowed=True,
        reason_code=GlobalHistoryScopeReason.ALLOWED,
        message=(
            "All required Row Scope dimensions are explicitly "
            "safe before Global History sequencing."
        ),
        safe_pre_sequence_dimensions=(
            safe_dimensions
        ),
        retryable=False,
    )
