from __future__ import annotations

import json
import re
from datetime import date
from enum import Enum
from hashlib import sha256

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.semantic_layer.query_plan_v2_models import (
    QueryLogic,
    QueryPlanV2,
    ScopeMode,
    StagedQueryLogic,
)
from app.semantic_layer.time_window_resolver_v2 import (
    TimeWindowResolutionSourceV2,
    TimeWindowResolutionStatusV2,
    TimeWindowResolutionV2,
)


_IDENTIFIER_PATTERN = r"^[A-Za-z_][A-Za-z0-9_]*$"
_RESOURCE_COLUMN_PATTERN = (
    r"^[a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*$"
)
_ALIAS_COLUMN_PATTERN = (
    r"^[A-Za-z_][A-Za-z0-9_]*\."
    r"[A-Za-z_][A-Za-z0-9_]*$"
)

_ALIAS_COLUMN_FINDER = re.compile(
    r"\b[A-Za-z_][A-Za-z0-9_]*\."
    r"[A-Za-z_][A-Za-z0-9_]*\b"
)

_START_PARAMETER = "analysis_start_date"
_END_PARAMETER = "analysis_end_date"
_DEFAULT_PARAMETER_NAMES = (
    _START_PARAMETER,
    _END_PARAMETER,
)


class TimeBindingStatusV2(str, Enum):
    BOUND = "bound"
    RESOLUTION_NOT_READY = "resolution_not_ready"
    INVALID_PLAN_TIME_CONTRACT = (
        "invalid_plan_time_contract"
    )


class TimeApplicationModeV2(str, Enum):
    QUERY_LEVEL = "query_level"
    STAGED = "staged"
    GLOBAL_HISTORY = "global_history"


class TimePlacementSourceV2(str, Enum):
    TRUSTED_QUERY_ALIAS = "trusted_query_alias"
    DECLARED_STAGE_FILTER = "declared_stage_filter"
    TRUSTED_STAGE_ALIAS = "trusted_stage_alias"


class TimeParameterV2(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    name: str = Field(
        pattern=_IDENTIFIER_PATTERN
    )
    value: date


class TimeApplicationV2(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    stage_id: str | None = Field(
        default=None,
        pattern=_IDENTIFIER_PATTERN,
    )
    query_references: tuple[str, ...]
    placement_sources: tuple[
        TimePlacementSourceV2,
        ...,
    ]

    @model_validator(mode="after")
    def validate_application(
        self,
    ) -> "TimeApplicationV2":
        if not self.query_references:
            raise ValueError(
                "TimeApplication requires query_references."
            )

        if len(self.query_references) != len(
            set(self.query_references)
        ):
            raise ValueError(
                "query_references must be unique."
            )

        for reference in self.query_references:
            if not re.fullmatch(
                _ALIAS_COLUMN_PATTERN,
                reference,
            ):
                raise ValueError(
                    "query_references must use alias.column."
                )

        if not self.placement_sources:
            raise ValueError(
                "TimeApplication requires placement_sources."
            )

        if len(self.placement_sources) != len(
            set(self.placement_sources)
        ):
            raise ValueError(
                "placement_sources must be unique."
            )

        return self


class TimeBindingContractV2(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    plan_name: str = Field(
        pattern=_IDENTIFIER_PATTERN
    )
    metric_name: str = Field(
        pattern=_IDENTIFIER_PATTERN
    )

    application_mode: TimeApplicationModeV2

    resolution_source: (
        TimeWindowResolutionSourceV2
    )
    reference_date: date

    requested_start_date: date
    requested_end_date: date
    effective_start_date: date
    effective_end_date: date

    policy_name: str
    policy_version: str

    parameter_names: tuple[str, ...]
    parameters: tuple[TimeParameterV2, ...]

    declared_time_columns: tuple[str, ...]
    applications: tuple[TimeApplicationV2, ...]

    protected_history_stage_id: str | None = Field(
        default=None,
        pattern=_IDENTIFIER_PATTERN,
    )
    analysis_window_stage_id: str | None = Field(
        default=None,
        pattern=_IDENTIFIER_PATTERN,
    )

    notice_required: bool
    user_notice: str | None = None

    contract_fingerprint: str = Field(
        pattern=r"^[0-9a-f]{64}$"
    )

    @model_validator(mode="after")
    def validate_contract(
        self,
    ) -> "TimeBindingContractV2":
        if (
            self.requested_start_date
            > self.requested_end_date
        ):
            raise ValueError(
                "Requested time window is invalid."
            )

        if (
            self.effective_start_date
            > self.effective_end_date
        ):
            raise ValueError(
                "Effective time window is invalid."
            )

        if set(self.parameter_names) != set(
            _DEFAULT_PARAMETER_NAMES
        ):
            raise ValueError(
                "Time Binding V2 requires "
                "analysis_start_date and analysis_end_date."
            )

        if len(self.parameter_names) != len(
            set(self.parameter_names)
        ):
            raise ValueError(
                "parameter_names must be unique."
            )

        parameter_map = {
            parameter.name: parameter.value
            for parameter in self.parameters
        }

        if set(parameter_map) != set(
            self.parameter_names
        ):
            raise ValueError(
                "parameters must exactly cover parameter_names."
            )

        if (
            parameter_map[_START_PARAMETER]
            != self.effective_start_date
        ):
            raise ValueError(
                "analysis_start_date must equal "
                "effective_start_date."
            )

        if (
            parameter_map[_END_PARAMETER]
            != self.effective_end_date
        ):
            raise ValueError(
                "analysis_end_date must equal "
                "effective_end_date."
            )

        if not self.declared_time_columns:
            raise ValueError(
                "declared_time_columns cannot be empty."
            )

        if len(self.declared_time_columns) != len(
            set(self.declared_time_columns)
        ):
            raise ValueError(
                "declared_time_columns must be unique."
            )

        for column in self.declared_time_columns:
            if not re.fullmatch(
                _RESOURCE_COLUMN_PATTERN,
                column,
            ):
                raise ValueError(
                    "declared_time_columns must use "
                    "table.column."
                )

        if not self.applications:
            raise ValueError(
                "At least one time application is required."
            )

        if self.notice_required:
            if not self.user_notice:
                raise ValueError(
                    "notice_required=True requires user_notice."
                )
        elif self.user_notice is not None:
            raise ValueError(
                "Non-required user_notice must be None."
            )

        if (
            self.application_mode
            == TimeApplicationModeV2.GLOBAL_HISTORY
        ):
            if self.protected_history_stage_id is None:
                raise ValueError(
                    "Global-history binding requires "
                    "protected_history_stage_id."
                )

            if self.analysis_window_stage_id is None:
                raise ValueError(
                    "Global-history binding requires "
                    "analysis_window_stage_id."
                )

            application_stages = {
                application.stage_id
                for application in self.applications
            }

            if self.protected_history_stage_id in (
                application_stages
            ):
                raise ValueError(
                    "Analysis time cannot be applied to "
                    "the protected full-history stage."
                )

            if self.analysis_window_stage_id not in (
                application_stages
            ):
                raise ValueError(
                    "Declared analysis-window stage must "
                    "receive the time binding."
                )
        else:
            if self.protected_history_stage_id is not None:
                raise ValueError(
                    "Non-global binding cannot expose a "
                    "protected history stage."
                )

            if self.analysis_window_stage_id is not None:
                raise ValueError(
                    "Non-global binding cannot expose an "
                    "analysis-window stage."
                )

        return self


class TimeBindingDecisionV2(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    status: TimeBindingStatusV2
    allowed: bool
    plan_name: str
    contract: TimeBindingContractV2 | None = None
    detail: str | None = None

    @model_validator(mode="after")
    def validate_decision(
        self,
    ) -> "TimeBindingDecisionV2":
        if self.allowed:
            if self.status != TimeBindingStatusV2.BOUND:
                raise ValueError(
                    "Allowed decision must use BOUND."
                )

            if self.contract is None:
                raise ValueError(
                    "Allowed decision requires a contract."
                )

            if self.detail is not None:
                raise ValueError(
                    "Allowed decision must not expose detail."
                )

            return self

        if self.status == TimeBindingStatusV2.BOUND:
            raise ValueError(
                "Denied decision cannot use BOUND."
            )

        if self.contract is not None:
            raise ValueError(
                "Denied decision must not expose a contract."
            )

        if not self.detail:
            raise ValueError(
                "Denied decision requires detail."
            )

        return self


def _denied(
    plan: QueryPlanV2,
    *,
    status: TimeBindingStatusV2,
    detail: str,
) -> TimeBindingDecisionV2:
    return TimeBindingDecisionV2(
        status=status,
        allowed=False,
        plan_name=plan.name,
        contract=None,
        detail=detail,
    )


def _declared_time_columns(
    plan: QueryPlanV2,
) -> tuple[str, ...]:
    columns = (
        plan.semantic_contract.time_window_columns
    )

    if columns:
        return tuple(
            columns
        )

    return (
        plan.semantic_contract.date_attribution,
    )


def _references_in_text(
    text: str,
) -> tuple[str, ...]:
    return tuple(
        sorted(
            set(
                _ALIAS_COLUMN_FINDER.findall(
                    text
                )
            )
        )
    )


def _physical_reference_to_resource_column(
    *,
    reference: str,
    alias_to_table: dict[str, str],
) -> str | None:
    alias, column = reference.split(
        ".",
        1,
    )
    table = alias_to_table.get(
        alias
    )

    if table is None:
        return None

    return f"{table}.{column}"


def _merge_application(
    accumulator: dict[
        str | None,
        dict[str, set],
    ],
    *,
    stage_id: str | None,
    references: tuple[str, ...],
    source: TimePlacementSourceV2,
) -> None:
    current = accumulator.setdefault(
        stage_id,
        {
            "references": set(),
            "sources": set(),
        },
    )

    current["references"].update(
        references
    )
    current["sources"].add(
        source
    )


def _finalize_applications(
    accumulator: dict[
        str | None,
        dict[str, set],
    ],
) -> tuple[TimeApplicationV2, ...]:
    def sort_key(
        item: tuple[str | None, dict[str, set]],
    ) -> tuple[int, str]:
        stage_id, _ = item

        if stage_id is None:
            return (
                0,
                "",
            )

        return (
            1,
            stage_id,
        )

    return tuple(
        TimeApplicationV2(
            stage_id=stage_id,
            query_references=tuple(
                sorted(
                    payload["references"]
                )
            ),
            placement_sources=tuple(
                sorted(
                    payload["sources"],
                    key=lambda item: item.value,
                )
            ),
        )
        for stage_id, payload in sorted(
            accumulator.items(),
            key=sort_key,
        )
    )


def _bind_query_logic(
    plan: QueryPlanV2,
    declared_columns: tuple[str, ...],
) -> tuple[
    TimeApplicationModeV2,
    tuple[TimeApplicationV2, ...],
]:
    logic = plan.query_logic

    if not isinstance(
        logic,
        QueryLogic,
    ):
        raise TypeError(
            "Expected QueryLogic."
        )

    alias_to_table = logic.alias_to_table()
    accumulator: dict[
        str | None,
        dict[str, set],
    ] = {}

    for resource_column in declared_columns:
        table, column = resource_column.split(
            ".",
            1,
        )

        aliases = tuple(
            sorted(
                alias
                for alias, actual_table
                in alias_to_table.items()
                if actual_table == table
            )
        )

        if len(aliases) != 1:
            raise ValueError(
                "Simple QueryLogic requires exactly one "
                "trusted alias for each time table. "
                f"column={resource_column}, aliases={aliases}"
            )

        _merge_application(
            accumulator,
            stage_id=None,
            references=(
                f"{aliases[0]}.{column}",
            ),
            source=(
                TimePlacementSourceV2
                .TRUSTED_QUERY_ALIAS
            ),
        )

    return (
        TimeApplicationModeV2.QUERY_LEVEL,
        _finalize_applications(
            accumulator
        ),
    )


def _explicit_stage_applications(
    logic: StagedQueryLogic,
    *,
    parameter_names: tuple[str, ...],
) -> tuple[
    dict[str | None, dict[str, set]],
    frozenset[str],
]:
    accumulator: dict[
        str | None,
        dict[str, set],
    ] = {}
    covered_resource_columns: set[str] = set()

    tokens = tuple(
        f":{name}"
        for name in parameter_names
    )

    for stage in logic.stages:
        filter_text = stage.filter_text()

        if not all(
            token in filter_text
            for token in tokens
        ):
            continue

        references = _references_in_text(
            filter_text
        )

        if not references:
            raise ValueError(
                "A stage declares time parameters but "
                "contains no alias.column reference. "
                f"stage={stage.stage_id}"
            )

        _merge_application(
            accumulator,
            stage_id=stage.stage_id,
            references=references,
            source=(
                TimePlacementSourceV2
                .DECLARED_STAGE_FILTER
            ),
        )

        alias_to_table = (
            stage.physical_alias_to_table()
        )

        for reference in references:
            resource_column = (
                _physical_reference_to_resource_column(
                    reference=reference,
                    alias_to_table=alias_to_table,
                )
            )

            if resource_column is not None:
                covered_resource_columns.add(
                    resource_column
                )

    return (
        accumulator,
        frozenset(
            covered_resource_columns
        ),
    )


def _infer_missing_staged_columns(
    *,
    logic: StagedQueryLogic,
    missing_columns: tuple[str, ...],
    accumulator: dict[
        str | None,
        dict[str, set],
    ],
) -> None:
    for resource_column in missing_columns:
        table, column = resource_column.split(
            ".",
            1,
        )

        candidates: list[
            tuple[str, str]
        ] = []

        for stage in logic.stages:
            for alias, actual_table in (
                stage.physical_alias_to_table().items()
            ):
                if actual_table == table:
                    candidates.append(
                        (
                            stage.stage_id,
                            f"{alias}.{column}",
                        )
                    )

        if len(candidates) != 1:
            raise ValueError(
                "Staged QueryLogic cannot determine one "
                "trusted time placement. "
                f"column={resource_column}, "
                f"candidates={candidates}"
            )

        stage_id, reference = candidates[0]

        _merge_application(
            accumulator,
            stage_id=stage_id,
            references=(
                reference,
            ),
            source=(
                TimePlacementSourceV2
                .TRUSTED_STAGE_ALIAS
            ),
        )


def _bind_predicate_safe_staged_logic(
    plan: QueryPlanV2,
    declared_columns: tuple[str, ...],
) -> tuple[
    TimeApplicationModeV2,
    tuple[TimeApplicationV2, ...],
]:
    logic = plan.query_logic

    if not isinstance(
        logic,
        StagedQueryLogic,
    ):
        raise TypeError(
            "Expected StagedQueryLogic."
        )

    (
        accumulator,
        covered_columns,
    ) = _explicit_stage_applications(
        logic,
        parameter_names=(
            _DEFAULT_PARAMETER_NAMES
        ),
    )

    missing_columns = tuple(
        column
        for column in declared_columns
        if column not in covered_columns
    )

    _infer_missing_staged_columns(
        logic=logic,
        missing_columns=missing_columns,
        accumulator=accumulator,
    )

    return (
        TimeApplicationModeV2.STAGED,
        _finalize_applications(
            accumulator
        ),
    )


def _bind_global_history_logic(
    plan: QueryPlanV2,
    declared_columns: tuple[str, ...],
) -> tuple[
    TimeApplicationModeV2,
    tuple[TimeApplicationV2, ...],
    str,
    str,
    tuple[str, ...],
]:
    logic = plan.query_logic

    if not isinstance(
        logic,
        StagedQueryLogic,
    ):
        raise ValueError(
            "Global-history Plan must use "
            "StagedQueryLogic."
        )

    history = (
        plan.scope_contract.history_contract
    )

    if history is None:
        raise ValueError(
            "Global-history Plan is missing "
            "history_contract."
        )

    parameter_names = tuple(
        history.analysis_window_parameters
    )

    if set(parameter_names) != set(
        _DEFAULT_PARAMETER_NAMES
    ):
        raise ValueError(
            "Global-history Time Binding V2 requires "
            "analysis_start_date and analysis_end_date."
        )

    (
        accumulator,
        covered_columns,
    ) = _explicit_stage_applications(
        logic,
        parameter_names=parameter_names,
    )

    applications = _finalize_applications(
        accumulator
    )
    application_stage_ids = {
        application.stage_id
        for application in applications
    }

    if history.history_stage_id in (
        application_stage_ids
    ):
        raise ValueError(
            "Full-history stage contains analysis "
            "time parameters."
        )

    if history.analysis_window_stage_id not in (
        application_stage_ids
    ):
        raise ValueError(
            "Declared analysis-window stage does not "
            "contain the analysis time parameters."
        )

    for resource_column in declared_columns:
        table, _ = resource_column.split(
            ".",
            1,
        )

        if table in history.history_source_tables:
            continue

        if resource_column not in covered_columns:
            raise ValueError(
                "A non-history time column is not covered "
                "by a declared stage filter. "
                f"column={resource_column}"
            )

    return (
        TimeApplicationModeV2.GLOBAL_HISTORY,
        applications,
        history.history_stage_id,
        history.analysis_window_stage_id,
        parameter_names,
    )


def _build_fingerprint(
    *,
    plan: QueryPlanV2,
    resolution: TimeWindowResolutionV2,
    application_mode: TimeApplicationModeV2,
    parameter_names: tuple[str, ...],
    parameters: tuple[TimeParameterV2, ...],
    declared_time_columns: tuple[str, ...],
    applications: tuple[TimeApplicationV2, ...],
    protected_history_stage_id: str | None,
    analysis_window_stage_id: str | None,
) -> str:
    payload = {
        "plan_name": plan.name,
        "metric_name": plan.metric,
        "application_mode": application_mode.value,
        "resolution_source": (
            resolution.source.value
            if resolution.source is not None
            else None
        ),
        "reference_date": (
            resolution.reference_date.isoformat()
        ),
        "requested_start_date": (
            resolution.requested_start_date.isoformat()
        ),
        "requested_end_date": (
            resolution.requested_end_date.isoformat()
        ),
        "effective_start_date": (
            resolution.effective_start_date.isoformat()
        ),
        "effective_end_date": (
            resolution.effective_end_date.isoformat()
        ),
        "policy_name": resolution.policy_name,
        "policy_version": resolution.policy_version,
        "parameter_names": list(
            parameter_names
        ),
        "parameters": [
            {
                "name": parameter.name,
                "value": parameter.value.isoformat(),
            }
            for parameter in parameters
        ],
        "declared_time_columns": list(
            declared_time_columns
        ),
        "applications": [
            {
                "stage_id": application.stage_id,
                "query_references": list(
                    application.query_references
                ),
                "placement_sources": [
                    source.value
                    for source in (
                        application.placement_sources
                    )
                ],
            }
            for application in applications
        ],
        "protected_history_stage_id": (
            protected_history_stage_id
        ),
        "analysis_window_stage_id": (
            analysis_window_stage_id
        ),
        "notice_required": (
            resolution.notice_required
        ),
        "user_notice": resolution.user_notice,
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


def bind_time_window_v2(
    *,
    plan: QueryPlanV2,
    resolution: TimeWindowResolutionV2,
) -> TimeBindingDecisionV2:
    """
    Bind a resolved Time Window to a trusted Query Plan V2.

    This function:
    - binds deterministic parameter values;
    - records trusted query/stage placement;
    - protects Global History from early time filtering;
    - preserves the exact user notice produced by the Resolver.

    This function does not:
    - inspect database availability;
    - shrink a cross-fact window;
    - generate SQL;
    - execute SQL.
    """
    if (
        resolution.status
        != TimeWindowResolutionStatusV2.RESOLVED
    ):
        return _denied(
            plan,
            status=(
                TimeBindingStatusV2
                .RESOLUTION_NOT_READY
            ),
            detail=(
                "Time Window Resolution must be RESOLVED "
                "before binding."
            ),
        )

    required_resolution_values = (
        resolution.source,
        resolution.requested_start_date,
        resolution.requested_end_date,
        resolution.effective_start_date,
        resolution.effective_end_date,
    )

    if any(
        value is None
        for value in required_resolution_values
    ):
        return _denied(
            plan,
            status=(
                TimeBindingStatusV2
                .RESOLUTION_NOT_READY
            ),
            detail=(
                "Resolved Time Window is missing required "
                "date or source fields."
            ),
        )

    declared_columns = _declared_time_columns(
        plan
    )

    protected_history_stage_id = None
    analysis_window_stage_id = None
    parameter_names = (
        _DEFAULT_PARAMETER_NAMES
    )

    try:
        if (
            plan.scope_contract.scope_mode
            == ScopeMode.GLOBAL_HISTORY_REQUIRED
        ):
            (
                application_mode,
                applications,
                protected_history_stage_id,
                analysis_window_stage_id,
                parameter_names,
            ) = _bind_global_history_logic(
                plan,
                declared_columns,
            )
        elif isinstance(
            plan.query_logic,
            QueryLogic,
        ):
            (
                application_mode,
                applications,
            ) = _bind_query_logic(
                plan,
                declared_columns,
            )
        else:
            (
                application_mode,
                applications,
            ) = (
                _bind_predicate_safe_staged_logic(
                    plan,
                    declared_columns,
                )
            )
    except (
        TypeError,
        ValueError,
    ) as exc:
        return _denied(
            plan,
            status=(
                TimeBindingStatusV2
                .INVALID_PLAN_TIME_CONTRACT
            ),
            detail=str(
                exc
            ),
        )

    parameters = (
        TimeParameterV2(
            name=_START_PARAMETER,
            value=resolution.effective_start_date,
        ),
        TimeParameterV2(
            name=_END_PARAMETER,
            value=resolution.effective_end_date,
        ),
    )

    fingerprint = _build_fingerprint(
        plan=plan,
        resolution=resolution,
        application_mode=application_mode,
        parameter_names=parameter_names,
        parameters=parameters,
        declared_time_columns=declared_columns,
        applications=applications,
        protected_history_stage_id=(
            protected_history_stage_id
        ),
        analysis_window_stage_id=(
            analysis_window_stage_id
        ),
    )

    contract = TimeBindingContractV2(
        plan_name=plan.name,
        metric_name=plan.metric,
        application_mode=application_mode,
        resolution_source=resolution.source,
        reference_date=resolution.reference_date,
        requested_start_date=(
            resolution.requested_start_date
        ),
        requested_end_date=(
            resolution.requested_end_date
        ),
        effective_start_date=(
            resolution.effective_start_date
        ),
        effective_end_date=(
            resolution.effective_end_date
        ),
        policy_name=resolution.policy_name,
        policy_version=resolution.policy_version,
        parameter_names=parameter_names,
        parameters=parameters,
        declared_time_columns=declared_columns,
        applications=applications,
        protected_history_stage_id=(
            protected_history_stage_id
        ),
        analysis_window_stage_id=(
            analysis_window_stage_id
        ),
        notice_required=(
            resolution.notice_required
        ),
        user_notice=resolution.user_notice,
        contract_fingerprint=fingerprint,
    )

    return TimeBindingDecisionV2(
        status=TimeBindingStatusV2.BOUND,
        allowed=True,
        plan_name=plan.name,
        contract=contract,
        detail=None,
    )
