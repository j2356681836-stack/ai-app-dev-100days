from enum import Enum
import re

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.governance.row_scope import ScopeDimension
from app.governance.row_scope_binding import ScopeTarget
from app.governance.sensitive_data import ResultProtectionContract


_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_RESOURCE_COLUMN_RE = re.compile(
    r"^[a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*$"
)
_ALIAS_COLUMN_RE = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*$"
)


class ScopeMode(str, Enum):
    PREDICATE_SAFE = "predicate_safe"
    GLOBAL_HISTORY_REQUIRED = "global_history_required"


class QuerySource(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    table: str = Field(pattern=r"^[a-z_][a-z0-9_]*$")
    alias: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")


class JoinCondition(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    left: str
    right: str

    @model_validator(mode="after")
    def validate_references(self):
        for value in (self.left, self.right):
            if not _ALIAS_COLUMN_RE.fullmatch(value):
                raise ValueError(
                    "Join references must use alias.column format."
                )

        return self


class QueryJoin(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    table: str = Field(pattern=r"^[a-z_][a-z0-9_]*$")
    alias: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    join_type: str = Field(pattern=r"^(inner|left)$")
    conditions: tuple[JoinCondition, ...]

    @model_validator(mode="after")
    def validate_join(self):
        if not self.conditions:
            raise ValueError("QueryJoin.conditions cannot be empty.")

        return self


class QueryOutput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    field: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    expression: str

    @model_validator(mode="after")
    def validate_expression(self):
        if not self.expression.strip():
            raise ValueError("Output expression cannot be empty.")

        return self


class HiddenControlField(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    field: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    expression: str
    semantics: str

    @model_validator(mode="after")
    def validate_control_field(self):
        if not self.expression.strip():
            raise ValueError(
                "Hidden control expression cannot be empty."
            )

        if not self.semantics.strip():
            raise ValueError(
                "Hidden control semantics cannot be empty."
            )

        return self


class QueryLogic(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    base_source: QuerySource
    joins: tuple[QueryJoin, ...] = ()
    group_by: tuple[str, ...] = ()
    outputs: tuple[QueryOutput, ...]
    hidden_control_fields: tuple[HiddenControlField, ...] = ()

    @model_validator(mode="after")
    def validate_logic(self):
        aliases = [self.base_source.alias]
        aliases.extend(join.alias for join in self.joins)

        if len(aliases) != len(set(aliases)):
            raise ValueError(
                "Query aliases must be unique within a query plan."
            )

        output_fields = [output.field for output in self.outputs]

        if not output_fields:
            raise ValueError("At least one visible output is required.")

        if len(output_fields) != len(set(output_fields)):
            raise ValueError(
                "Visible output fields must be unique."
            )

        hidden_fields = [
            field.field
            for field in self.hidden_control_fields
        ]

        if len(hidden_fields) != len(set(hidden_fields)):
            raise ValueError(
                "Hidden control fields must be unique."
            )

        overlap = set(output_fields) & set(hidden_fields)

        if overlap:
            raise ValueError(
                "Hidden control fields cannot also be visible outputs."
            )

        for reference in self.group_by:
            if not _ALIAS_COLUMN_RE.fullmatch(reference):
                raise ValueError(
                    "group_by entries must use alias.column format."
                )

        return self

    def alias_to_table(self) -> dict[str, str]:
        bindings = {
            self.base_source.alias: self.base_source.table,
        }

        for join in self.joins:
            bindings[join.alias] = join.table

        return bindings

    def query_tables(self) -> frozenset[str]:
        return frozenset(self.alias_to_table().values())

    def visible_output_fields(self) -> frozenset[str]:
        return frozenset(
            output.field
            for output in self.outputs
        )

    def hidden_output_fields(self) -> frozenset[str]:
        return frozenset(
            field.field
            for field in self.hidden_control_fields
        )

    def all_join_conditions(self) -> tuple[JoinCondition, ...]:
        return tuple(
            condition
            for join in self.joins
            for condition in join.conditions
        )


class QueryStageType(str, Enum):
    AGGREGATE = "aggregate"
    PROJECT = "project"
    FILTER = "filter"


class StageSource(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    table: str | None = Field(
        default=None,
        pattern=r"^[a-z_][a-z0-9_]*$",
    )
    stage_id: str | None = Field(
        default=None,
        pattern=r"^[A-Za-z_][A-Za-z0-9_]*$",
    )
    alias: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")

    @model_validator(mode="after")
    def validate_source(self):
        declared = (
            self.table is not None,
            self.stage_id is not None,
        )

        if sum(declared) != 1:
            raise ValueError(
                "StageSource must declare exactly one of "
                "table or stage_id."
            )

        return self

    def is_physical_table(self) -> bool:
        return self.table is not None


class StageJoin(BaseModel):
    """
    Join a current stage to an earlier derived stage.

    This is intentionally separate from QueryJoin:
    - QueryJoin binds a physical table.
    - StageJoin binds an earlier trusted QueryStage output.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    stage_id: str = Field(
        pattern=r"^[A-Za-z_][A-Za-z0-9_]*$"
    )
    alias: str = Field(
        pattern=r"^[A-Za-z_][A-Za-z0-9_]*$"
    )
    join_type: str = Field(pattern=r"^(inner|left)$")
    conditions: tuple[JoinCondition, ...]

    @model_validator(mode="after")
    def validate_join(self):
        if not self.conditions:
            raise ValueError(
                "StageJoin.conditions cannot be empty."
            )

        return self


class QueryStage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    stage_id: str = Field(
        pattern=r"^[A-Za-z_][A-Za-z0-9_]*$"
    )
    stage_type: QueryStageType
    source: StageSource
    joins: tuple[QueryJoin | StageJoin, ...] = ()
    filters: tuple[str, ...] = ()
    group_by: tuple[str, ...] = ()
    having: tuple[str, ...] = ()
    outputs: tuple[QueryOutput, ...]
    hidden_control_fields: tuple[HiddenControlField, ...] = ()

    @model_validator(mode="after")
    def validate_stage(self):
        aliases = [self.source.alias]
        aliases.extend(join.alias for join in self.joins)

        if len(aliases) != len(set(aliases)):
            raise ValueError(
                f"Stage {self.stage_id} aliases must be unique."
            )

        output_fields = [
            output.field
            for output in self.outputs
        ]

        if not output_fields:
            raise ValueError(
                f"Stage {self.stage_id} must expose at least one output."
            )

        if len(output_fields) != len(set(output_fields)):
            raise ValueError(
                f"Stage {self.stage_id} output fields must be unique."
            )

        hidden_fields = [
            field.field
            for field in self.hidden_control_fields
        ]

        if len(hidden_fields) != len(set(hidden_fields)):
            raise ValueError(
                f"Stage {self.stage_id} hidden fields must be unique."
            )

        overlap = set(output_fields) & set(hidden_fields)

        if overlap:
            raise ValueError(
                f"Stage {self.stage_id} hidden fields cannot also "
                "be visible outputs."
            )

        for reference in self.group_by:
            if not _ALIAS_COLUMN_RE.fullmatch(reference):
                raise ValueError(
                    "stage group_by entries must use "
                    "alias.column format."
                )

        if any(
            not item.strip()
            for item in (*self.filters, *self.having)
        ):
            raise ValueError(
                f"Stage {self.stage_id} filters/having cannot be empty."
            )

        return self

    def physical_alias_to_table(self) -> dict[str, str]:
        bindings = {}

        if self.source.table is not None:
            bindings[self.source.alias] = self.source.table

        for join in self.joins:
            if isinstance(join, QueryJoin):
                bindings[join.alias] = join.table

        return bindings

    def all_aliases(self) -> frozenset[str]:
        aliases = {self.source.alias}
        aliases.update(join.alias for join in self.joins)
        return frozenset(aliases)

    def physical_tables(self) -> frozenset[str]:
        return frozenset(
            self.physical_alias_to_table().values()
        )

    def filter_text(self) -> str:
        return " ".join(
            (
                *self.filters,
                *self.having,
            )
        )


class StagedQueryLogic(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    stages: tuple[QueryStage, ...]
    final_stage: str = Field(
        pattern=r"^[A-Za-z_][A-Za-z0-9_]*$"
    )

    @model_validator(mode="after")
    def validate_stages(self):
        if not self.stages:
            raise ValueError(
                "StagedQueryLogic.stages cannot be empty."
            )

        stage_ids = [
            stage.stage_id
            for stage in self.stages
        ]

        if len(stage_ids) != len(set(stage_ids)):
            raise ValueError(
                "Staged Query stage_id values must be unique."
            )

        if self.final_stage != stage_ids[-1]:
            raise ValueError(
                "final_stage must reference the last declared stage."
            )

        known_stage_ids: set[str] = set()
        known_stage_outputs: dict[
            str,
            frozenset[str],
        ] = {}
        all_aliases: list[str] = []

        for stage in self.stages:
            if stage.source.stage_id is not None:
                if stage.source.stage_id not in known_stage_ids:
                    raise ValueError(
                        "Derived stage sources may only reference "
                        "an earlier declared stage. "
                        f"stage={stage.stage_id}, "
                        f"source_stage={stage.source.stage_id}"
                    )

            for join in stage.joins:
                if isinstance(join, StageJoin):
                    if join.stage_id not in known_stage_ids:
                        raise ValueError(
                            "StageJoin may only reference an earlier "
                            "declared stage. "
                            f"stage={stage.stage_id}, "
                            f"joined_stage={join.stage_id}"
                        )

            local_aliases = stage.all_aliases()

            for join in stage.joins:
                for condition in join.conditions:
                    for reference in (
                        condition.left,
                        condition.right,
                    ):
                        alias, column = reference.split(".", 1)

                        if alias not in local_aliases:
                            raise ValueError(
                                "Stage join condition references an "
                                "alias outside the current stage. "
                                f"stage={stage.stage_id}, "
                                f"reference={reference}"
                            )

                        derived_fields = None

                        if (
                            stage.source.stage_id is not None
                            and alias == stage.source.alias
                        ):
                            derived_fields = (
                                known_stage_outputs[
                                    stage.source.stage_id
                                ]
                            )
                        else:
                            for stage_join in stage.joins:
                                if (
                                    isinstance(
                                        stage_join,
                                        StageJoin,
                                    )
                                    and alias
                                    == stage_join.alias
                                ):
                                    derived_fields = (
                                        known_stage_outputs[
                                            stage_join.stage_id
                                        ]
                                    )
                                    break

                        if (
                            derived_fields is not None
                            and column not in derived_fields
                        ):
                            raise ValueError(
                                "Derived stage join reference must "
                                "use an output field exposed by the "
                                "referenced stage. "
                                f"stage={stage.stage_id}, "
                                f"reference={reference}"
                            )

            known_stage_ids.add(stage.stage_id)
            known_stage_outputs[
                stage.stage_id
            ] = frozenset(
                output.field
                for output in stage.outputs
            )

            all_aliases.extend(stage.all_aliases())

        if len(all_aliases) != len(set(all_aliases)):
            raise ValueError(
                "Aliases must be unique across all staged query stages."
            )

        return self

    def final_stage_contract(self) -> QueryStage:
        return self.stages[-1]

    def alias_to_table(self) -> dict[str, str]:
        bindings: dict[str, str] = {}

        for stage in self.stages:
            bindings.update(
                stage.physical_alias_to_table()
            )

        return bindings

    def derived_alias_fields(
        self,
    ) -> dict[str, frozenset[str]]:
        stage_outputs = {
            stage.stage_id: frozenset(
                output.field
                for output in stage.outputs
            )
            for stage in self.stages
        }

        bindings: dict[
            str,
            frozenset[str],
        ] = {}

        for stage in self.stages:
            if stage.source.stage_id is not None:
                bindings[stage.source.alias] = (
                    stage_outputs[
                        stage.source.stage_id
                    ]
                )

            for join in stage.joins:
                if isinstance(join, StageJoin):
                    bindings[join.alias] = (
                        stage_outputs[join.stage_id]
                    )

        return bindings

    def query_tables(self) -> frozenset[str]:
        return frozenset(
            self.alias_to_table().values()
        )

    def visible_output_fields(self) -> frozenset[str]:
        return frozenset(
            output.field
            for output in self.final_stage_contract().outputs
        )

    def hidden_output_fields(self) -> frozenset[str]:
        return frozenset(
            field.field
            for field in (
                self.final_stage_contract()
                .hidden_control_fields
            )
        )

    def all_join_conditions(self) -> tuple[JoinCondition, ...]:
        return tuple(
            condition
            for stage in self.stages
            for join in stage.joins
            for condition in join.conditions
        )


class SemanticContract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    date_attribution: str
    metric_expression: str
    base_filters: tuple[str, ...] = ()
    time_window_columns: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_semantics(self):
        if not _RESOURCE_COLUMN_RE.fullmatch(
            self.date_attribution
        ):
            raise ValueError(
                "date_attribution must use table.column format."
            )

        if not self.metric_expression.strip():
            raise ValueError(
                "metric_expression cannot be empty."
            )

        if any(
            not item.strip()
            for item in self.base_filters
        ):
            raise ValueError(
                "base_filters cannot contain empty values."
            )

        invalid_time_columns = [
            column
            for column in self.time_window_columns
            if not _RESOURCE_COLUMN_RE.fullmatch(
                column
            )
        ]

        if invalid_time_columns:
            raise ValueError(
                "time_window_columns must use "
                "table.column format."
            )

        if len(self.time_window_columns) != len(
            set(self.time_window_columns)
        ):
            raise ValueError(
                "time_window_columns must be unique."
            )

        if (
            self.time_window_columns
            and self.date_attribution
            not in self.time_window_columns
        ):
            raise ValueError(
                "date_attribution must be included in "
                "time_window_columns when a cross-source "
                "time-window contract is declared."
            )

        return self


class ResourceContract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    required_tables: frozenset[str]
    required_columns: frozenset[str]

    @model_validator(mode="after")
    def validate_resources(self):
        if not self.required_tables:
            raise ValueError(
                "required_tables cannot be empty."
            )

        if not self.required_columns:
            raise ValueError(
                "required_columns cannot be empty."
            )

        invalid_tables = sorted(
            table
            for table in self.required_tables
            if not (
                isinstance(table, str)
                and re.fullmatch(
                    r"[a-z_][a-z0-9_]*",
                    table,
                )
            )
        )

        if invalid_tables:
            raise ValueError(
                f"Invalid required table names: {invalid_tables}"
            )

        invalid_columns = sorted(
            column
            for column in self.required_columns
            if not (
                isinstance(column, str)
                and _RESOURCE_COLUMN_RE.fullmatch(column)
            )
        )

        if invalid_columns:
            raise ValueError(
                "required_columns must use table.column format: "
                f"{invalid_columns}"
            )

        column_tables = {
            column.split(".", 1)[0]
            for column in self.required_columns
        }

        undeclared_tables = (
            column_tables - self.required_tables
        )

        if undeclared_tables:
            raise ValueError(
                "Every required column table must also be declared "
                "in required_tables: "
                f"{sorted(undeclared_tables)}"
            )

        return self


class HistoryScopeBinding(BaseModel):
    """
    A Row Scope dimension that is semantically safe before sequencing.

    partition_reference must be part of sequence_partition_by. This makes
    the safety claim explicit: applying this scope cannot merge/remove
    events across the identity partition used to determine the first event.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    dimension: ScopeDimension
    partition_reference: str

    @model_validator(mode="after")
    def validate_partition_reference(self):
        if not _ALIAS_COLUMN_RE.fullmatch(
            self.partition_reference
        ):
            raise ValueError(
                "partition_reference must use alias.column format."
            )

        return self


class GlobalHistoryContract(BaseModel):
    """
    Structural contract for first-event / sequence metrics.

    The history stage determines the true event from full relevant history.
    The analysis window is allowed only at a later stage.

    Row Scope dimensions are split into:
    - pre_sequence_scope_bindings:
      safe before sequencing because the scoped field is part of the
      sequence identity partition.
    - post_sequence_scope_dimensions:
      unsafe before sequencing and therefore require a later enforcement
      capability. Until such enforcement exists, execution must fail closed.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    history_stage_id: str = Field(
        pattern=r"^[A-Za-z_][A-Za-z0-9_]*$"
    )
    analysis_window_stage_id: str = Field(
        pattern=r"^[A-Za-z_][A-Za-z0-9_]*$"
    )

    history_source_tables: frozenset[str]

    sequence_partition_by: tuple[str, ...]
    sequence_order_by: tuple[str, ...]

    pre_sequence_scope_bindings: tuple[
        HistoryScopeBinding, ...
    ] = ()

    post_sequence_scope_dimensions: frozenset[
        ScopeDimension
    ] = frozenset()

    analysis_window_parameters: tuple[str, ...] = (
        "analysis_start_date",
        "analysis_end_date",
    )

    @model_validator(mode="after")
    def validate_history_contract(self):
        if (
            self.history_stage_id
            == self.analysis_window_stage_id
        ):
            raise ValueError(
                "history_stage_id and analysis_window_stage_id "
                "must be different stages."
            )

        if not self.history_source_tables:
            raise ValueError(
                "history_source_tables cannot be empty."
            )

        if not self.sequence_partition_by:
            raise ValueError(
                "sequence_partition_by cannot be empty."
            )

        if not self.sequence_order_by:
            raise ValueError(
                "sequence_order_by cannot be empty."
            )

        for reference in (
            *self.sequence_partition_by,
            *self.sequence_order_by,
        ):
            if not _ALIAS_COLUMN_RE.fullmatch(reference):
                raise ValueError(
                    "History sequence references must use "
                    "alias.column format."
                )

        if len(self.sequence_partition_by) != len(
            set(self.sequence_partition_by)
        ):
            raise ValueError(
                "sequence_partition_by must be unique."
            )

        if len(self.sequence_order_by) != len(
            set(self.sequence_order_by)
        ):
            raise ValueError(
                "sequence_order_by must be unique."
            )

        binding_dimensions = [
            binding.dimension
            for binding in (
                self.pre_sequence_scope_bindings
            )
        ]

        if len(binding_dimensions) != len(
            set(binding_dimensions)
        ):
            raise ValueError(
                "Each pre-sequence Scope dimension "
                "may be declared only once."
            )

        for binding in (
            self.pre_sequence_scope_bindings
        ):
            if (
                binding.partition_reference
                not in self.sequence_partition_by
            ):
                raise ValueError(
                    "Pre-sequence Scope is safe only when its "
                    "partition_reference is part of "
                    "sequence_partition_by."
                )

        pre_dimensions = frozenset(
            binding_dimensions
        )

        overlap = (
            pre_dimensions
            & self.post_sequence_scope_dimensions
        )

        if overlap:
            raise ValueError(
                "A Scope dimension cannot be both pre-sequence "
                "and post-sequence."
            )

        if not self.analysis_window_parameters:
            raise ValueError(
                "analysis_window_parameters cannot be empty."
            )

        if len(self.analysis_window_parameters) != len(
            set(self.analysis_window_parameters)
        ):
            raise ValueError(
                "analysis_window_parameters must be unique."
            )

        for parameter in (
            self.analysis_window_parameters
        ):
            if not _IDENTIFIER_RE.fullmatch(parameter):
                raise ValueError(
                    "analysis_window_parameters must be "
                    "safe identifiers."
                )

        return self

    def pre_sequence_scope_dimensions(
        self,
    ) -> frozenset[ScopeDimension]:
        return frozenset(
            binding.dimension
            for binding in (
                self.pre_sequence_scope_bindings
            )
        )


class ScopeContract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    scope_mode: ScopeMode
    source_tables: frozenset[str]
    required_dimensions: frozenset[ScopeDimension]
    targets: tuple[ScopeTarget, ...]
    history_contract: GlobalHistoryContract | None = None

    @model_validator(mode="after")
    def validate_scope_contract(self):
        if not self.source_tables:
            raise ValueError(
                "scope source_tables cannot be empty."
            )

        if not self.required_dimensions:
            raise ValueError(
                "required_dimensions cannot be empty."
            )

        if not self.targets:
            raise ValueError(
                "At least one ScopeTarget is required."
            )

        target_ids = [
            target.target_id
            for target in self.targets
        ]

        if len(target_ids) != len(set(target_ids)):
            raise ValueError(
                "ScopeTarget target_id values must be unique."
            )

        target_sources = {
            target.source_table
            for target in self.targets
        }

        missing = self.source_tables - target_sources
        extra = target_sources - self.source_tables

        if missing or extra:
            raise ValueError(
                "ScopeTarget sources must exactly cover "
                "scope source_tables. "
                f"missing={sorted(missing)}, extra={sorted(extra)}"
            )

        if self.scope_mode == ScopeMode.PREDICATE_SAFE:
            if self.history_contract is not None:
                raise ValueError(
                    "predicate_safe ScopeContract cannot declare "
                    "a GlobalHistoryContract."
                )

            return self

        if self.history_contract is None:
            raise ValueError(
                "global_history_required ScopeContract must "
                "declare history_contract."
            )

        history = self.history_contract

        if not history.history_source_tables.issubset(
            self.source_tables
        ):
            raise ValueError(
                "history_source_tables must be a subset of "
                "scope source_tables."
            )

        pre_dimensions = (
            history.pre_sequence_scope_dimensions()
        )
        post_dimensions = (
            history.post_sequence_scope_dimensions
        )

        declared_dimensions = (
            pre_dimensions | post_dimensions
        )

        if declared_dimensions != self.required_dimensions:
            missing_dimensions = (
                self.required_dimensions
                - declared_dimensions
            )
            extra_dimensions = (
                declared_dimensions
                - self.required_dimensions
            )

            raise ValueError(
                "Global History pre/post Scope dimensions must "
                "exactly cover required_dimensions. "
                f"missing={sorted(item.value for item in missing_dimensions)}, "
                f"extra={sorted(item.value for item in extra_dimensions)}"
            )

        return self


class SortContract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    field: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    direction: str = Field(pattern=r"^(asc|desc)$")


class QueryPlanV2(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    metric: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    chinese_name: str
    query_type: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    result_grain: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    description: str

    semantic_contract: SemanticContract
    query_logic: QueryLogic | StagedQueryLogic
    resource_contract: ResourceContract
    scope_contract: ScopeContract
    result_contract: ResultProtectionContract
    default_sort: SortContract

    @model_validator(mode="after")
    def validate_cross_contract_consistency(self):
        if not self.chinese_name.strip():
            raise ValueError("chinese_name cannot be empty.")

        if not self.description.strip():
            raise ValueError("description cannot be empty.")

        resources = self.resource_contract

        if (
            self.semantic_contract.date_attribution
            not in resources.required_columns
        ):
            raise ValueError(
                "date_attribution must be declared in "
                "required_columns."
            )

        undeclared_time_columns = (
            set(
                self.semantic_contract
                .time_window_columns
            )
            - resources.required_columns
        )

        if undeclared_time_columns:
            raise ValueError(
                "time_window_columns must be declared in "
                "required_columns: "
                f"{sorted(undeclared_time_columns)}"
            )

        query_tables = self.query_logic.query_tables()
        missing_query_tables = (
            query_tables - resources.required_tables
        )

        if missing_query_tables:
            raise ValueError(
                "All query_logic tables must be declared in "
                "required_tables: "
                f"{sorted(missing_query_tables)}"
            )

        if not self.scope_contract.source_tables.issubset(
            resources.required_tables
        ):
            raise ValueError(
                "scope source_tables must be declared in "
                "required_tables."
            )

        alias_to_table = self.query_logic.alias_to_table()

        for target in self.scope_contract.targets:
            for binding in target.table_aliases:
                actual_table = alias_to_table.get(binding.alias)

                if actual_table != binding.table_name:
                    raise ValueError(
                        "ScopeTarget alias binding must match "
                        "query_logic. "
                        f"target={target.target_id}, "
                        f"alias={binding.alias}, "
                        f"declared={binding.table_name}, "
                        f"actual={actual_table}"
                    )

        visible_outputs = (
            self.query_logic.visible_output_fields()
        )

        bound_outputs = {
            binding.output_field
            for binding in self.result_contract.field_bindings
        }

        if visible_outputs != bound_outputs:
            raise ValueError(
                "Visible query outputs must exactly match "
                "ResultFieldBinding output fields."
            )

        for binding in self.result_contract.field_bindings:
            undeclared_sources = (
                binding.source_columns
                - resources.required_columns
            )

            if undeclared_sources:
                raise ValueError(
                    "ResultFieldBinding source columns must be "
                    "declared in required_columns: "
                    f"{sorted(undeclared_sources)}"
                )

        hidden_fields = (
            self.query_logic.hidden_output_fields()
        )

        if self.result_contract.minimum_group_size_required:
            if (
                self.result_contract.group_size_field
                not in hidden_fields
            ):
                raise ValueError(
                    "group_size_field must be declared as a hidden "
                    "control field in query_logic."
                )

        if self.default_sort.field not in visible_outputs:
            raise ValueError(
                "default_sort.field must refer to a visible output."
            )

        self._validate_join_resource_references(
            alias_to_table=alias_to_table,
        )

        self._validate_global_history_contract()

        return self

    def _validate_global_history_contract(
        self,
    ) -> None:
        scope = self.scope_contract

        if (
            scope.scope_mode
            != ScopeMode.GLOBAL_HISTORY_REQUIRED
        ):
            return

        if not isinstance(
            self.query_logic,
            StagedQueryLogic,
        ):
            raise ValueError(
                "global_history_required plans must use "
                "StagedQueryLogic."
            )

        history = scope.history_contract

        if history is None:
            raise ValueError(
                "Global History contract is missing."
            )

        stages = {
            stage.stage_id: stage
            for stage in self.query_logic.stages
        }

        history_stage = stages.get(
            history.history_stage_id
        )
        window_stage = stages.get(
            history.analysis_window_stage_id
        )

        if history_stage is None:
            raise ValueError(
                "history_stage_id must reference a declared "
                "QueryStage."
            )

        if window_stage is None:
            raise ValueError(
                "analysis_window_stage_id must reference a "
                "declared QueryStage."
            )

        stage_order = {
            stage.stage_id: index
            for index, stage in enumerate(
                self.query_logic.stages
            )
        }

        if (
            stage_order[history.history_stage_id]
            >= stage_order[
                history.analysis_window_stage_id
            ]
        ):
            raise ValueError(
                "The full-history sequencing stage must execute "
                "before the analysis-window stage."
            )

        if not history.history_source_tables.issubset(
            history_stage.physical_tables()
        ):
            raise ValueError(
                "history_source_tables must be physically read "
                "by the declared history stage."
            )

        history_aliases = (
            history_stage.all_aliases()
        )

        for reference in (
            *history.sequence_partition_by,
            *history.sequence_order_by,
        ):
            alias, _ = reference.split(".", 1)

            if alias not in history_aliases:
                raise ValueError(
                    "History sequence references must belong "
                    "to the history stage. "
                    f"reference={reference}"
                )

        history_filter_text = (
            history_stage.filter_text()
        )
        window_filter_text = (
            window_stage.filter_text()
        )

        for parameter in (
            history.analysis_window_parameters
        ):
            token = f":{parameter}"

            if token in history_filter_text:
                raise ValueError(
                    "Analysis-window parameters cannot be "
                    "applied in the full-history sequencing stage. "
                    f"parameter={parameter}"
                )

            if token not in window_filter_text:
                raise ValueError(
                    "The declared analysis-window stage must "
                    "apply every analysis-window parameter. "
                    f"parameter={parameter}"
                )

    def _validate_join_resource_references(
        self,
        *,
        alias_to_table: dict[str, str],
    ) -> None:
        derived_alias_fields = {}

        if isinstance(
            self.query_logic,
            StagedQueryLogic,
        ):
            derived_alias_fields = (
                self.query_logic
                .derived_alias_fields()
            )

        for condition in self.query_logic.all_join_conditions():
            for reference in (
                condition.left,
                condition.right,
            ):
                alias, column = reference.split(".", 1)
                table = alias_to_table.get(alias)

                if table is not None:
                    resource_column = (
                        f"{table}.{column}"
                    )

                    if (
                        resource_column
                        not in self.resource_contract
                        .required_columns
                    ):
                        raise ValueError(
                            "Join column must be declared in "
                            "required_columns: "
                            f"{resource_column}"
                        )

                    continue

                derived_fields = (
                    derived_alias_fields.get(alias)
                )

                if derived_fields is None:
                    raise ValueError(
                        "Join reference uses an unknown alias: "
                        f"{reference}"
                    )

                if column not in derived_fields:
                    raise ValueError(
                        "Join reference uses a field not exposed "
                        "by the referenced derived stage: "
                        f"{reference}"
                    )

    def to_scope_targets(self) -> tuple[ScopeTarget, ...]:
        return self.scope_contract.targets

    def to_result_protection_contract(
        self,
    ) -> ResultProtectionContract:
        return self.result_contract


class QueryPlanCatalogV2(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    query_plan_version: str
    dataset_name: str
    metadata_version: str
    target_schema: str
    status: str
    query_plans: tuple[QueryPlanV2, ...]

    @model_validator(mode="after")
    def validate_catalog(self):
        expected = {
            "query_plan_version": "beauty_bi_query_plan_v2_0",
            "dataset_name": "beauty_bi_v2",
            "metadata_version": "beauty_bi_metadata_v2_0",
            "target_schema": "beauty_bi_v2",
            "status": "draft",
        }

        actual = {
            "query_plan_version": self.query_plan_version,
            "dataset_name": self.dataset_name,
            "metadata_version": self.metadata_version,
            "target_schema": self.target_schema,
            "status": self.status,
        }

        if actual != expected:
            raise ValueError(
                "Query Plan V2 catalog identity mismatch. "
                f"Expected={expected}, Actual={actual}"
            )

        if not self.query_plans:
            raise ValueError(
                "query_plans cannot be empty."
            )

        names = [
            plan.name
            for plan in self.query_plans
        ]

        if len(names) != len(set(names)):
            raise ValueError(
                "Query Plan names must be unique."
            )

        return self
