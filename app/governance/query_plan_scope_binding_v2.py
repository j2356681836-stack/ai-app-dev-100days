from __future__ import annotations

import json
from enum import Enum
from hashlib import sha256

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.governance.access_context import AccessContext
from app.governance.row_scope import (
    RowScopeDecision,
    ScopeDimension,
    plan_row_scope,
)
from app.governance.row_scope_binding import (
    ScopeBindingDecision,
    ScopedQueryContract,
    build_scoped_query_contract,
)
from app.semantic_layer.query_plan_v2_models import (
    QueryLogic,
    QueryPlanV2,
    ScopeMode,
    StagedQueryLogic,
)


_IDENTIFIER_PATTERN = r"^[A-Za-z_][A-Za-z0-9_]*$"


class QueryPlanScopeBindingStatusV2(str, Enum):
    BOUND = "bound"
    ROW_SCOPE_DENIED = "row_scope_denied"
    SCOPE_BINDING_DENIED = "scope_binding_denied"
    POST_SEQUENCE_SCOPE_NOT_READY = (
        "post_sequence_scope_not_ready"
    )
    GLOBAL_HISTORY_SCOPE_NOT_READY = (
        "global_history_scope_not_ready"
    )
    INVALID_PLAN_SCOPE_CONTRACT = (
        "invalid_plan_scope_contract"
    )


class ScopePredicatePlacementV2(BaseModel):
    """
    A governed Row Scope Predicate plus its trusted Query Plan location.

    stage_id=None means a non-staged QueryLogic.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    target_id: str = Field(
        pattern=_IDENTIFIER_PATTERN
    )
    stage_id: str | None = Field(
        default=None,
        pattern=_IDENTIFIER_PATTERN,
    )

    source_table: str = Field(
        pattern=_IDENTIFIER_PATTERN
    )
    dimension: ScopeDimension

    anchor_reference: str
    sql_fragment: str
    parameter_names: tuple[str, ...]


class QueryPlanScopeBindingContractV2(BaseModel):
    """
    Immutable wrapper connecting:

        QueryPlanV2
        -> RowScopePlan
        -> ScopedQueryContract
        -> trusted Query/Stage placement
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    request_id: str
    policy_version: str
    target_schema: str

    plan_name: str = Field(
        pattern=_IDENTIFIER_PATTERN
    )
    metric_name: str = Field(
        pattern=_IDENTIFIER_PATTERN
    )
    scope_mode: ScopeMode

    row_scope_plan_fingerprint: str = Field(
        pattern=r"^[0-9a-f]{64}$"
    )
    scoped_contract_fingerprint: str = Field(
        pattern=r"^[0-9a-f]{64}$"
    )

    scoped_query_contract: ScopedQueryContract
    placements: tuple[ScopePredicatePlacementV2, ...]

    contract_fingerprint: str = Field(
        pattern=r"^[0-9a-f]{64}$"
    )

    @model_validator(mode="after")
    def validate_contract(
        self,
    ) -> "QueryPlanScopeBindingContractV2":
        if self.scope_mode != ScopeMode.PREDICATE_SAFE:
            raise ValueError(
                "Current executable contract supports only "
                "predicate_safe Query Plans."
            )

        if (
            self.row_scope_plan_fingerprint
            != self.scoped_query_contract.plan_fingerprint
        ):
            raise ValueError(
                "Row Scope Plan fingerprint does not match "
                "Scoped Query Contract."
            )

        if (
            self.scoped_contract_fingerprint
            != self.scoped_query_contract.contract_fingerprint
        ):
            raise ValueError(
                "Scoped contract fingerprint mismatch."
            )

        if not self.placements:
            raise ValueError(
                "At least one Scope Predicate placement is required."
            )

        placement_keys = [
            (
                placement.target_id,
                placement.dimension,
            )
            for placement in self.placements
        ]

        if len(placement_keys) != len(
            set(placement_keys)
        ):
            raise ValueError(
                "Each target and Scope dimension may be "
                "placed only once."
            )

        predicate_keys = {
            (
                predicate.target_id,
                predicate.dimension,
            )
            for predicate in (
                self.scoped_query_contract.predicates
            )
        }

        if set(placement_keys) != predicate_keys:
            raise ValueError(
                "Placements must exactly cover Scoped Query "
                "Contract predicates."
            )

        return self


class QueryPlanScopeBindingDecisionV2(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    status: QueryPlanScopeBindingStatusV2
    allowed: bool

    plan_name: str
    scope_mode: ScopeMode

    contract: QueryPlanScopeBindingContractV2 | None = None

    row_scope_decision: RowScopeDecision | None = None
    scope_binding_decision: ScopeBindingDecision | None = None

    pre_sequence_dimensions: frozenset[
        ScopeDimension
    ] = frozenset()
    post_sequence_dimensions: frozenset[
        ScopeDimension
    ] = frozenset()

    detail: str | None = None

    @model_validator(mode="after")
    def validate_decision(
        self,
    ) -> "QueryPlanScopeBindingDecisionV2":
        if self.allowed:
            if (
                self.status
                != QueryPlanScopeBindingStatusV2.BOUND
            ):
                raise ValueError(
                    "Allowed decision must use status=BOUND."
                )

            if self.contract is None:
                raise ValueError(
                    "Allowed decision requires contract."
                )

            if self.detail is not None:
                raise ValueError(
                    "Allowed decision must not expose detail."
                )

            return self

        if (
            self.status
            == QueryPlanScopeBindingStatusV2.BOUND
        ):
            raise ValueError(
                "Denied decision cannot use status=BOUND."
            )

        if self.contract is not None:
            raise ValueError(
                "Denied decision must not expose contract."
            )

        if not self.detail:
            raise ValueError(
                "Denied decision requires detail."
            )

        return self


def _denied(
    plan: QueryPlanV2,
    *,
    status: QueryPlanScopeBindingStatusV2,
    detail: str,
    row_scope_decision: RowScopeDecision | None = None,
    scope_binding_decision: ScopeBindingDecision | None = None,
    pre_sequence_dimensions: frozenset[
        ScopeDimension
    ] = frozenset(),
    post_sequence_dimensions: frozenset[
        ScopeDimension
    ] = frozenset(),
) -> QueryPlanScopeBindingDecisionV2:
    return QueryPlanScopeBindingDecisionV2(
        status=status,
        allowed=False,
        plan_name=plan.name,
        scope_mode=plan.scope_contract.scope_mode,
        contract=None,
        row_scope_decision=row_scope_decision,
        scope_binding_decision=scope_binding_decision,
        pre_sequence_dimensions=pre_sequence_dimensions,
        post_sequence_dimensions=post_sequence_dimensions,
        detail=detail,
    )


def _target_stage_id(
    *,
    plan: QueryPlanV2,
    target_id: str,
) -> str | None:
    target = next(
        (
            item
            for item in plan.scope_contract.targets
            if item.target_id == target_id
        ),
        None,
    )

    if target is None:
        raise ValueError(
            f"Unknown ScopeTarget: {target_id}"
        )

    if isinstance(
        plan.query_logic,
        QueryLogic,
    ):
        alias_to_table = (
            plan.query_logic.alias_to_table()
        )

        for binding in target.table_aliases:
            if (
                alias_to_table.get(
                    binding.alias
                )
                != binding.table_name
            ):
                raise ValueError(
                    "ScopeTarget does not match simple "
                    "QueryLogic aliases. "
                    f"target={target_id}"
                )

        return None

    if not isinstance(
        plan.query_logic,
        StagedQueryLogic,
    ):
        raise ValueError(
            "Unsupported Query Logic type."
        )

    candidates: list[str] = []

    for stage in plan.query_logic.stages:
        physical_aliases = (
            stage.physical_alias_to_table()
        )

        matches = all(
            physical_aliases.get(
                binding.alias
            )
            == binding.table_name
            for binding in target.table_aliases
        )

        if matches:
            candidates.append(
                stage.stage_id
            )

    if len(candidates) != 1:
        raise ValueError(
            "ScopeTarget must map to exactly one trusted "
            "physical Query Stage. "
            f"target={target_id}, candidates={candidates}"
        )

    return candidates[0]


def _build_placements(
    *,
    plan: QueryPlanV2,
    scoped_contract: ScopedQueryContract,
) -> tuple[ScopePredicatePlacementV2, ...]:
    stage_by_target = {
        target.target_id: _target_stage_id(
            plan=plan,
            target_id=target.target_id,
        )
        for target in (
            plan.scope_contract.targets
        )
    }

    return tuple(
        ScopePredicatePlacementV2(
            target_id=predicate.target_id,
            stage_id=stage_by_target[
                predicate.target_id
            ],
            source_table=predicate.source_table,
            dimension=predicate.dimension,
            anchor_reference=(
                predicate.anchor_reference
            ),
            sql_fragment=predicate.sql_fragment,
            parameter_names=(
                predicate.parameter_names
            ),
        )
        for predicate in sorted(
            scoped_contract.predicates,
            key=lambda item: (
                item.target_id,
                item.dimension.value,
            ),
        )
    )


def _wrapper_fingerprint(
    *,
    plan: QueryPlanV2,
    scoped_contract: ScopedQueryContract,
    placements: tuple[
        ScopePredicatePlacementV2,
        ...,
    ],
) -> str:
    payload = {
        "request_id": scoped_contract.request_id,
        "policy_version": (
            scoped_contract.policy_version
        ),
        "target_schema": (
            scoped_contract.target_schema
        ),
        "plan_name": plan.name,
        "metric_name": plan.metric,
        "scope_mode": (
            plan.scope_contract.scope_mode.value
        ),
        "row_scope_plan_fingerprint": (
            scoped_contract.plan_fingerprint
        ),
        "scoped_contract_fingerprint": (
            scoped_contract.contract_fingerprint
        ),
        "placements": [
            {
                "target_id": placement.target_id,
                "stage_id": placement.stage_id,
                "source_table": (
                    placement.source_table
                ),
                "dimension": (
                    placement.dimension.value
                ),
                "anchor_reference": (
                    placement.anchor_reference
                ),
                "sql_fragment": (
                    placement.sql_fragment
                ),
                "parameter_names": list(
                    placement.parameter_names
                ),
            }
            for placement in placements
        ],
    }

    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode(
        "utf-8"
    )

    return sha256(
        encoded
    ).hexdigest()


def bind_query_plan_scope_v2(
    *,
    context: AccessContext,
    plan: QueryPlanV2,
) -> QueryPlanScopeBindingDecisionV2:
    """
    Connect a trusted Query Plan V2 to existing Row Scope controls.

    predicate_safe:
    - plan Row Scope from trusted source_tables and dimensions;
    - bind parameterized predicates using trusted ScopeTargets;
    - record the exact Query/Stage where each predicate belongs.

    global_history_required:
    - never reuse predicate_safe placement blindly;
    - expose pre/post sequencing diagnostics;
    - fail closed while post-sequence enforcement is not implemented.

    This function does not generate, mutate, or execute SQL.
    """
    scope = plan.scope_contract

    if scope.scope_mode == ScopeMode.GLOBAL_HISTORY_REQUIRED:
        history = scope.history_contract

        if history is None:
            return _denied(
                plan,
                status=(
                    QueryPlanScopeBindingStatusV2
                    .INVALID_PLAN_SCOPE_CONTRACT
                ),
                detail=(
                    "global_history_required Plan is missing "
                    "history_contract."
                ),
            )

        pre_dimensions = (
            history.pre_sequence_scope_dimensions()
        )
        post_dimensions = (
            history.post_sequence_scope_dimensions
        )

        if post_dimensions:
            return _denied(
                plan,
                status=(
                    QueryPlanScopeBindingStatusV2
                    .POST_SEQUENCE_SCOPE_NOT_READY
                ),
                detail=(
                    "The Query Plan requires Row Scope after "
                    "the true historical event has been "
                    "identified. Current Row Scope Binder only "
                    "binds trusted physical-source aliases, so "
                    "execution must fail closed."
                ),
                pre_sequence_dimensions=pre_dimensions,
                post_sequence_dimensions=post_dimensions,
            )

        return _denied(
            plan,
            status=(
                QueryPlanScopeBindingStatusV2
                .GLOBAL_HISTORY_SCOPE_NOT_READY
            ),
            detail=(
                "Global-history Scope requires a dedicated "
                "stage-aware executable contract."
            ),
            pre_sequence_dimensions=pre_dimensions,
            post_sequence_dimensions=post_dimensions,
        )

    row_scope_decision = plan_row_scope(
        context=context,
        source_tables=scope.source_tables,
        required_dimensions=(
            scope.required_dimensions
        ),
    )

    if not row_scope_decision.allowed:
        return _denied(
            plan,
            status=(
                QueryPlanScopeBindingStatusV2
                .ROW_SCOPE_DENIED
            ),
            detail=row_scope_decision.message,
            row_scope_decision=row_scope_decision,
        )

    row_scope_plan = row_scope_decision.plan

    if row_scope_plan is None:
        return _denied(
            plan,
            status=(
                QueryPlanScopeBindingStatusV2
                .INVALID_PLAN_SCOPE_CONTRACT
            ),
            detail=(
                "Allowed Row Scope Decision did not expose "
                "a RowScopePlan."
            ),
            row_scope_decision=row_scope_decision,
        )

    scope_binding_decision = (
        build_scoped_query_contract(
            plan=row_scope_plan,
            targets=scope.targets,
        )
    )

    if not scope_binding_decision.allowed:
        return _denied(
            plan,
            status=(
                QueryPlanScopeBindingStatusV2
                .SCOPE_BINDING_DENIED
            ),
            detail=scope_binding_decision.message,
            row_scope_decision=row_scope_decision,
            scope_binding_decision=(
                scope_binding_decision
            ),
        )

    scoped_contract = (
        scope_binding_decision.contract
    )

    if scoped_contract is None:
        return _denied(
            plan,
            status=(
                QueryPlanScopeBindingStatusV2
                .INVALID_PLAN_SCOPE_CONTRACT
            ),
            detail=(
                "Allowed Scope Binding Decision did not "
                "expose a ScopedQueryContract."
            ),
            row_scope_decision=row_scope_decision,
            scope_binding_decision=(
                scope_binding_decision
            ),
        )

    try:
        placements = _build_placements(
            plan=plan,
            scoped_contract=scoped_contract,
        )
    except ValueError as exc:
        return _denied(
            plan,
            status=(
                QueryPlanScopeBindingStatusV2
                .INVALID_PLAN_SCOPE_CONTRACT
            ),
            detail=str(
                exc
            ),
            row_scope_decision=row_scope_decision,
            scope_binding_decision=(
                scope_binding_decision
            ),
        )

    fingerprint = _wrapper_fingerprint(
        plan=plan,
        scoped_contract=scoped_contract,
        placements=placements,
    )

    contract = QueryPlanScopeBindingContractV2(
        request_id=scoped_contract.request_id,
        policy_version=(
            scoped_contract.policy_version
        ),
        target_schema=(
            scoped_contract.target_schema
        ),
        plan_name=plan.name,
        metric_name=plan.metric,
        scope_mode=scope.scope_mode,
        row_scope_plan_fingerprint=(
            scoped_contract.plan_fingerprint
        ),
        scoped_contract_fingerprint=(
            scoped_contract.contract_fingerprint
        ),
        scoped_query_contract=scoped_contract,
        placements=placements,
        contract_fingerprint=fingerprint,
    )

    return QueryPlanScopeBindingDecisionV2(
        status=(
            QueryPlanScopeBindingStatusV2.BOUND
        ),
        allowed=True,
        plan_name=plan.name,
        scope_mode=scope.scope_mode,
        contract=contract,
        row_scope_decision=row_scope_decision,
        scope_binding_decision=(
            scope_binding_decision
        ),
        pre_sequence_dimensions=frozenset(),
        post_sequence_dimensions=frozenset(),
        detail=None,
    )
