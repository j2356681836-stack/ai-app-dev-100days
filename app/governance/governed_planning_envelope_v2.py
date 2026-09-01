from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import date, datetime
from enum import Enum
from hashlib import sha256
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.governance.access_context import AccessContext
from app.governance.authorization import (
    AuthorizationDecision,
    authorize_metric,
    authorize_resources,
)
from app.governance.query_plan_scope_binding_v2 import (
    QueryPlanScopeBindingContractV2,
    QueryPlanScopeBindingDecisionV2,
    bind_query_plan_scope_v2,
)
from app.governance.sensitive_data import (
    ResultProtectionContract,
)
from app.semantic_layer.query_plan_v2_models import QueryPlanV2
from app.semantic_layer.requested_scope_resolution_v2 import (
    RequestedScopeResolutionV2,
)
from app.semantic_layer.time_window_binding_v2 import (
    TimeBindingContractV2,
    TimeBindingDecisionV2,
    bind_time_window_v2,
)
from app.semantic_layer.time_window_resolver_v2 import (
    TimeWindowResolutionV2,
)


_IDENTIFIER_PATTERN = r"^[A-Za-z_][A-Za-z0-9_]*$"
_FINGERPRINT_PATTERN = r"^[0-9a-f]{64}$"


class GovernedPlanningStatusV2(str, Enum):
    READY_FOR_COMPILATION = "ready_for_compilation"
    METRIC_AUTHORIZATION_DENIED = (
        "metric_authorization_denied"
    )
    RESOURCE_AUTHORIZATION_DENIED = (
        "resource_authorization_denied"
    )
    TIME_BINDING_NOT_READY = "time_binding_not_ready"
    SCOPE_BINDING_NOT_READY = "scope_binding_not_ready"
    INVALID_PLANNING_INPUT = "invalid_planning_input"


class GovernedPlanningBlockedStageV2(str, Enum):
    METRIC_AUTHORIZATION = "metric_authorization"
    RESOURCE_AUTHORIZATION = "resource_authorization"
    TIME_BINDING = "time_binding"
    SCOPE_BINDING = "scope_binding"
    INPUT_VALIDATION = "input_validation"


def _canonicalize(
    value: Any,
) -> Any:
    """
    Convert a nested Pydantic/Python payload into a deterministic
    JSON-compatible structure.

    Ordered lists/tuples keep their order.
    Sets/frozensets are sorted deterministically.
    """
    if isinstance(value, BaseModel):
        return _canonicalize(
            value.model_dump(
                mode="python"
            )
        )

    if isinstance(value, Mapping):
        return {
            str(key): _canonicalize(item)
            for key, item in sorted(
                value.items(),
                key=lambda pair: str(pair[0]),
            )
        }

    if isinstance(
        value,
        (
            set,
            frozenset,
        ),
    ):
        canonical_items = [
            _canonicalize(item)
            for item in value
        ]

        return sorted(
            canonical_items,
            key=lambda item: json.dumps(
                item,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
        )

    if isinstance(
        value,
        (
            list,
            tuple,
        ),
    ):
        return [
            _canonicalize(item)
            for item in value
        ]

    if isinstance(value, Enum):
        return value.value

    if isinstance(
        value,
        (
            date,
            datetime,
        ),
    ):
        return value.isoformat()

    return value


def _fingerprint(
    payload: Any,
) -> str:
    canonical = _canonicalize(
        payload
    )
    encoded = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode(
        "utf-8"
    )

    return sha256(
        encoded
    ).hexdigest()


def query_plan_fingerprint_v2(
    plan: QueryPlanV2,
) -> str:
    return _fingerprint(
        plan
    )


class GovernedPlanningEnvelopeV2(BaseModel):
    """
    Immutable pre-compilation governance contract.

    A SQL compiler may accept this object only after a
    GovernedPlanningDecisionV2 reports READY_FOR_COMPILATION.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    contract_version: str = "governed_planning_envelope_v2_0"

    request_id: str
    actor_id: str
    dataset_name: str = Field(
        pattern=_IDENTIFIER_PATTERN
    )
    target_schema: str = Field(
        pattern=_IDENTIFIER_PATTERN
    )

    plan_name: str = Field(
        pattern=_IDENTIFIER_PATTERN
    )
    metric_name: str = Field(
        pattern=_IDENTIFIER_PATTERN
    )
    result_grain: str = Field(
        pattern=_IDENTIFIER_PATTERN
    )

    query_plan: QueryPlanV2
    query_plan_fingerprint: str = Field(
        pattern=_FINGERPRINT_PATTERN
    )

    required_tables: frozenset[str]
    required_columns: frozenset[str]

    metric_authorization: AuthorizationDecision
    resource_authorization: AuthorizationDecision

    time_binding: TimeBindingContractV2
    requested_scope: RequestedScopeResolutionV2 | None = None
    scope_binding: QueryPlanScopeBindingContractV2
    result_protection_contract: ResultProtectionContract

    authorization_policy_version: str
    time_policy_name: str
    time_policy_version: str
    row_scope_policy_version: str

    notice_required: bool = False
    user_notice: str | None = None

    envelope_fingerprint: str = Field(
        pattern=_FINGERPRINT_PATTERN
    )

    @model_validator(mode="after")
    def validate_envelope(
        self,
    ) -> "GovernedPlanningEnvelopeV2":
        if not self.request_id:
            raise ValueError(
                "request_id cannot be empty."
            )

        if not self.actor_id:
            raise ValueError(
                "actor_id cannot be empty."
            )

        if self.plan_name != self.query_plan.name:
            raise ValueError(
                "plan_name must match query_plan.name."
            )

        if self.metric_name != self.query_plan.metric:
            raise ValueError(
                "metric_name must match query_plan.metric."
            )

        if self.result_grain != self.query_plan.result_grain:
            raise ValueError(
                "result_grain must match Query Plan."
            )

        expected_plan_fingerprint = (
            query_plan_fingerprint_v2(
                self.query_plan
            )
        )

        if (
            self.query_plan_fingerprint
            != expected_plan_fingerprint
        ):
            raise ValueError(
                "query_plan_fingerprint mismatch."
            )

        resources = (
            self.query_plan.resource_contract
        )

        if self.required_tables != resources.required_tables:
            raise ValueError(
                "required_tables must come directly from "
                "Query Plan resource_contract."
            )

        if self.required_columns != resources.required_columns:
            raise ValueError(
                "required_columns must come directly from "
                "Query Plan resource_contract."
            )

        if not self.metric_authorization.allowed:
            raise ValueError(
                "Envelope requires allowed metric authorization."
            )

        if not self.resource_authorization.allowed:
            raise ValueError(
                "Envelope requires allowed resource authorization."
            )

        authorization_versions = {
            self.metric_authorization.policy_version,
            self.resource_authorization.policy_version,
            self.authorization_policy_version,
        }

        if len(authorization_versions) != 1:
            raise ValueError(
                "Authorization policy versions must match."
            )

        if self.time_binding.plan_name != self.plan_name:
            raise ValueError(
                "Time Binding plan mismatch."
            )

        if self.time_binding.metric_name != self.metric_name:
            raise ValueError(
                "Time Binding metric mismatch."
            )

        if (
            self.time_policy_name
            != self.time_binding.policy_name
        ):
            raise ValueError(
                "time_policy_name mismatch."
            )

        if (
            self.time_policy_version
            != self.time_binding.policy_version
        ):
            raise ValueError(
                "time_policy_version mismatch."
            )

        if self.scope_binding.plan_name != self.plan_name:
            raise ValueError(
                "Scope Binding plan mismatch."
            )

        if self.scope_binding.metric_name != self.metric_name:
            raise ValueError(
                "Scope Binding metric mismatch."
            )

        if self.scope_binding.request_id != self.request_id:
            raise ValueError(
                "Scope Binding request_id mismatch."
            )

        if (
            self.row_scope_policy_version
            != self.scope_binding.policy_version
        ):
            raise ValueError(
                "row_scope_policy_version mismatch."
            )

        if (
            self.result_protection_contract
            != self.query_plan.result_contract
        ):
            raise ValueError(
                "Result Protection Contract must come directly "
                "from Query Plan."
            )

        if self.notice_required != self.time_binding.notice_required:
            raise ValueError(
                "notice_required must match Time Binding."
            )

        if self.user_notice != self.time_binding.user_notice:
            raise ValueError(
                "user_notice must match Time Binding."
            )

        if self.notice_required and not self.user_notice:
            raise ValueError(
                "notice_required=True requires user_notice."
            )

        if not self.notice_required and self.user_notice is not None:
            raise ValueError(
                "Non-required user_notice must be None."
            )

        expected_envelope_fingerprint = (
            _build_envelope_fingerprint(
                request_id=self.request_id,
                actor_id=self.actor_id,
                dataset_name=self.dataset_name,
                target_schema=self.target_schema,
                plan_name=self.plan_name,
                metric_name=self.metric_name,
                result_grain=self.result_grain,
                query_plan_fingerprint=(
                    self.query_plan_fingerprint
                ),
                required_tables=self.required_tables,
                required_columns=self.required_columns,
                authorization_policy_version=(
                    self.authorization_policy_version
                ),
                time_binding_fingerprint=(
                    self.time_binding.contract_fingerprint
                ),
                requested_scope=self.requested_scope,
                scope_binding_fingerprint=(
                    self.scope_binding.contract_fingerprint
                ),
                time_policy_name=self.time_policy_name,
                time_policy_version=self.time_policy_version,
                row_scope_policy_version=(
                    self.row_scope_policy_version
                ),
                notice_required=self.notice_required,
                user_notice=self.user_notice,
            )
        )

        if (
            self.envelope_fingerprint
            != expected_envelope_fingerprint
        ):
            raise ValueError(
                "envelope_fingerprint mismatch."
            )

        return self


class GovernedPlanningDecisionV2(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    status: GovernedPlanningStatusV2
    ready: bool

    plan_name: str
    metric_name: str

    blocked_stage: (
        GovernedPlanningBlockedStageV2
        | None
    ) = None
    detail: str | None = None
    retryable: bool = False

    metric_authorization: AuthorizationDecision | None = None
    resource_authorization: AuthorizationDecision | None = None
    time_binding_decision: TimeBindingDecisionV2 | None = None
    scope_binding_decision: (
        QueryPlanScopeBindingDecisionV2
        | None
    ) = None

    envelope: GovernedPlanningEnvelopeV2 | None = None

    @model_validator(mode="after")
    def validate_decision(
        self,
    ) -> "GovernedPlanningDecisionV2":
        if self.retryable:
            raise ValueError(
                "Governed planning decisions are not "
                "automatically retryable."
            )

        if self.ready:
            if (
                self.status
                != GovernedPlanningStatusV2
                .READY_FOR_COMPILATION
            ):
                raise ValueError(
                    "Ready decision must use "
                    "READY_FOR_COMPILATION."
                )

            if self.blocked_stage is not None:
                raise ValueError(
                    "Ready decision cannot expose blocked_stage."
                )

            if self.detail is not None:
                raise ValueError(
                    "Ready decision cannot expose detail."
                )

            if self.envelope is None:
                raise ValueError(
                    "Ready decision requires envelope."
                )

            if (
                self.metric_authorization is None
                or not self.metric_authorization.allowed
            ):
                raise ValueError(
                    "Ready decision requires allowed metric "
                    "authorization."
                )

            if (
                self.resource_authorization is None
                or not self.resource_authorization.allowed
            ):
                raise ValueError(
                    "Ready decision requires allowed resource "
                    "authorization."
                )

            if (
                self.time_binding_decision is None
                or not self.time_binding_decision.allowed
            ):
                raise ValueError(
                    "Ready decision requires allowed Time Binding."
                )

            if (
                self.scope_binding_decision is None
                or not self.scope_binding_decision.allowed
            ):
                raise ValueError(
                    "Ready decision requires allowed Scope Binding."
                )

            return self

        if (
            self.status
            == GovernedPlanningStatusV2
            .READY_FOR_COMPILATION
        ):
            raise ValueError(
                "Blocked decision cannot use "
                "READY_FOR_COMPILATION."
            )

        if self.blocked_stage is None:
            raise ValueError(
                "Blocked decision requires blocked_stage."
            )

        if not self.detail:
            raise ValueError(
                "Blocked decision requires detail."
            )

        if self.envelope is not None:
            raise ValueError(
                "Blocked decision must not expose envelope."
            )

        return self


def _build_envelope_fingerprint(
    *,
    request_id: str,
    actor_id: str,
    dataset_name: str,
    target_schema: str,
    plan_name: str,
    metric_name: str,
    result_grain: str,
    query_plan_fingerprint: str,
    required_tables: frozenset[str],
    required_columns: frozenset[str],
    authorization_policy_version: str,
    time_binding_fingerprint: str,
    requested_scope: RequestedScopeResolutionV2 | None,
    scope_binding_fingerprint: str,
    time_policy_name: str,
    time_policy_version: str,
    row_scope_policy_version: str,
    notice_required: bool,
    user_notice: str | None,
) -> str:
    return _fingerprint(
        {
            "contract_version": (
                "governed_planning_envelope_v2_0"
            ),
            "request_id": request_id,
            "actor_id": actor_id,
            "dataset_name": dataset_name,
            "target_schema": target_schema,
            "plan_name": plan_name,
            "metric_name": metric_name,
            "result_grain": result_grain,
            "query_plan_fingerprint": (
                query_plan_fingerprint
            ),
            "required_tables": required_tables,
            "required_columns": required_columns,
            "authorization_policy_version": (
                authorization_policy_version
            ),
            "time_binding_fingerprint": (
                time_binding_fingerprint
            ),
            **(
                {
                    "requested_scope": requested_scope,
                }
                if requested_scope is not None
                else {}
            ),
            "scope_binding_fingerprint": (
                scope_binding_fingerprint
            ),
            "time_policy_name": time_policy_name,
            "time_policy_version": time_policy_version,
            "row_scope_policy_version": (
                row_scope_policy_version
            ),
            "notice_required": notice_required,
            "user_notice": user_notice,
        }
    )


def _blocked(
    *,
    plan: QueryPlanV2,
    status: GovernedPlanningStatusV2,
    blocked_stage: GovernedPlanningBlockedStageV2,
    detail: str,
    metric_authorization: (
        AuthorizationDecision
        | None
    ) = None,
    resource_authorization: (
        AuthorizationDecision
        | None
    ) = None,
    time_binding_decision: (
        TimeBindingDecisionV2
        | None
    ) = None,
    scope_binding_decision: (
        QueryPlanScopeBindingDecisionV2
        | None
    ) = None,
) -> GovernedPlanningDecisionV2:
    return GovernedPlanningDecisionV2(
        status=status,
        ready=False,
        plan_name=plan.name,
        metric_name=plan.metric,
        blocked_stage=blocked_stage,
        detail=detail,
        retryable=False,
        metric_authorization=metric_authorization,
        resource_authorization=resource_authorization,
        time_binding_decision=time_binding_decision,
        scope_binding_decision=scope_binding_decision,
        envelope=None,
    )


def build_governed_planning_envelope_v2(
    *,
    context: AccessContext,
    plan: QueryPlanV2,
    time_resolution: TimeWindowResolutionV2,
    requested_scope: RequestedScopeResolutionV2 | None = None,
) -> GovernedPlanningDecisionV2:
    """
    Build the only pre-compilation contract that may cross the
    governance planning boundary.

    Order is fail-closed:
    1. metric authorization;
    2. table/column authorization;
    3. Time Binding;
    4. Row Scope Binding;
    5. immutable READY_FOR_COMPILATION envelope.

    Required resources are always read from QueryPlanV2.
    Callers cannot substitute a smaller resource declaration.
    """
    if (
        context.dataset_name != "beauty_bi_v2"
        or context.target_schema != "beauty_bi_v2"
    ):
        return _blocked(
            plan=plan,
            status=(
                GovernedPlanningStatusV2
                .INVALID_PLANNING_INPUT
            ),
            blocked_stage=(
                GovernedPlanningBlockedStageV2
                .INPUT_VALIDATION
            ),
            detail=(
                "Query Plan V2 currently requires "
                "dataset_name=beauty_bi_v2 and "
                "target_schema=beauty_bi_v2."
            ),
        )

    metric_authorization = authorize_metric(
        context,
        plan.metric,
    )

    if not metric_authorization.allowed:
        return _blocked(
            plan=plan,
            status=(
                GovernedPlanningStatusV2
                .METRIC_AUTHORIZATION_DENIED
            ),
            blocked_stage=(
                GovernedPlanningBlockedStageV2
                .METRIC_AUTHORIZATION
            ),
            detail=metric_authorization.message,
            metric_authorization=(
                metric_authorization
            ),
        )

    resources = plan.resource_contract

    resource_authorization = authorize_resources(
        context,
        required_tables=resources.required_tables,
        required_columns=resources.required_columns,
    )

    if not resource_authorization.allowed:
        return _blocked(
            plan=plan,
            status=(
                GovernedPlanningStatusV2
                .RESOURCE_AUTHORIZATION_DENIED
            ),
            blocked_stage=(
                GovernedPlanningBlockedStageV2
                .RESOURCE_AUTHORIZATION
            ),
            detail=resource_authorization.message,
            metric_authorization=(
                metric_authorization
            ),
            resource_authorization=(
                resource_authorization
            ),
        )

    time_binding_decision = bind_time_window_v2(
        plan=plan,
        resolution=time_resolution,
    )

    if not time_binding_decision.allowed:
        return _blocked(
            plan=plan,
            status=(
                GovernedPlanningStatusV2
                .TIME_BINDING_NOT_READY
            ),
            blocked_stage=(
                GovernedPlanningBlockedStageV2
                .TIME_BINDING
            ),
            detail=(
                time_binding_decision.detail
                or time_binding_decision.status.value
            ),
            metric_authorization=(
                metric_authorization
            ),
            resource_authorization=(
                resource_authorization
            ),
            time_binding_decision=(
                time_binding_decision
            ),
        )

    scope_binding_decision = (
        bind_query_plan_scope_v2(
            context=context,
            plan=plan,
            requested_scope=requested_scope,
        )
    )

    if not scope_binding_decision.allowed:
        return _blocked(
            plan=plan,
            status=(
                GovernedPlanningStatusV2
                .SCOPE_BINDING_NOT_READY
            ),
            blocked_stage=(
                GovernedPlanningBlockedStageV2
                .SCOPE_BINDING
            ),
            detail=(
                scope_binding_decision.detail
                or scope_binding_decision.status.value
            ),
            metric_authorization=(
                metric_authorization
            ),
            resource_authorization=(
                resource_authorization
            ),
            time_binding_decision=(
                time_binding_decision
            ),
            scope_binding_decision=(
                scope_binding_decision
            ),
        )

    time_contract = time_binding_decision.contract
    scope_contract = scope_binding_decision.contract

    if time_contract is None or scope_contract is None:
        return _blocked(
            plan=plan,
            status=(
                GovernedPlanningStatusV2
                .INVALID_PLANNING_INPUT
            ),
            blocked_stage=(
                GovernedPlanningBlockedStageV2
                .INPUT_VALIDATION
            ),
            detail=(
                "Allowed binding decision did not expose its "
                "required contract."
            ),
            metric_authorization=(
                metric_authorization
            ),
            resource_authorization=(
                resource_authorization
            ),
            time_binding_decision=(
                time_binding_decision
            ),
            scope_binding_decision=(
                scope_binding_decision
            ),
        )

    plan_fingerprint = query_plan_fingerprint_v2(
        plan
    )

    envelope_fingerprint = (
        _build_envelope_fingerprint(
            request_id=context.request_id,
            actor_id=context.actor_id,
            dataset_name=context.dataset_name,
            target_schema=context.target_schema,
            plan_name=plan.name,
            metric_name=plan.metric,
            result_grain=plan.result_grain,
            query_plan_fingerprint=plan_fingerprint,
            required_tables=resources.required_tables,
            required_columns=resources.required_columns,
            authorization_policy_version=(
                context.policy_version
            ),
            time_binding_fingerprint=(
                time_contract.contract_fingerprint
            ),
            requested_scope=requested_scope,
            scope_binding_fingerprint=(
                scope_contract.contract_fingerprint
            ),
            time_policy_name=(
                time_contract.policy_name
            ),
            time_policy_version=(
                time_contract.policy_version
            ),
            row_scope_policy_version=(
                scope_contract.policy_version
            ),
            notice_required=(
                time_contract.notice_required
            ),
            user_notice=time_contract.user_notice,
        )
    )

    envelope = GovernedPlanningEnvelopeV2(
        request_id=context.request_id,
        actor_id=context.actor_id,
        dataset_name=context.dataset_name,
        target_schema=context.target_schema,
        plan_name=plan.name,
        metric_name=plan.metric,
        result_grain=plan.result_grain,
        query_plan=plan,
        query_plan_fingerprint=plan_fingerprint,
        required_tables=resources.required_tables,
        required_columns=resources.required_columns,
        metric_authorization=metric_authorization,
        resource_authorization=resource_authorization,
        time_binding=time_contract,
        requested_scope=requested_scope,
        scope_binding=scope_contract,
        result_protection_contract=(
            plan.to_result_protection_contract()
        ),
        authorization_policy_version=(
            context.policy_version
        ),
        time_policy_name=(
            time_contract.policy_name
        ),
        time_policy_version=(
            time_contract.policy_version
        ),
        row_scope_policy_version=(
            scope_contract.policy_version
        ),
        notice_required=(
            time_contract.notice_required
        ),
        user_notice=time_contract.user_notice,
        envelope_fingerprint=(
            envelope_fingerprint
        ),
    )

    return GovernedPlanningDecisionV2(
        status=(
            GovernedPlanningStatusV2
            .READY_FOR_COMPILATION
        ),
        ready=True,
        plan_name=plan.name,
        metric_name=plan.metric,
        blocked_stage=None,
        detail=None,
        retryable=False,
        metric_authorization=metric_authorization,
        resource_authorization=resource_authorization,
        time_binding_decision=time_binding_decision,
        scope_binding_decision=(
            scope_binding_decision
        ),
        envelope=envelope,
    )
