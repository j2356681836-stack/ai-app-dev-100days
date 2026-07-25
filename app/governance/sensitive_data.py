import hashlib
import hmac
import json
import re
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from app.governance.access_context import AccessContext


_SAFE_OUTPUT_FIELD_PATTERN = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*$"
)

_SAFE_SOURCE_COLUMN_PATTERN = re.compile(
    r"^[a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*$"
)


class SensitiveDataCategory(str, Enum):
    ORDINARY = "ordinary"
    PSEUDONYMOUS_IDENTIFIER = (
        "pseudonymous_identifier"
    )
    DIRECT_IDENTIFIER = "direct_identifier"
    FREE_TEXT = "free_text"
    BUSINESS_CONFIDENTIAL = "business_confidential"


class ProtectionAction(str, Enum):
    ALLOW = "allow"
    TOKENIZE = "tokenize"
    REJECT = "reject"


class ResultShape(str, Enum):
    AGGREGATE = "aggregate"
    DETAIL = "detail"


class ProtectionReason(str, Enum):
    ALLOWED = "allowed"
    INVALID_PROTECTION_CONTRACT = (
        "invalid_protection_contract"
    )
    INVALID_RESULT_SHAPE = "invalid_result_shape"
    MISSING_TOKENIZATION_SECRET = (
        "missing_tokenization_secret"
    )
    DIRECT_IDENTIFIER_NOT_ALLOWED = (
        "direct_identifier_not_allowed"
    )
    FREE_TEXT_NOT_ALLOWED = "free_text_not_allowed"
    COST_DATA_NOT_ALLOWED = "cost_data_not_allowed"
    MINIMUM_GROUP_SIZE_NOT_PROVEN = (
        "minimum_group_size_not_proven"
    )
    MINIMUM_GROUP_SIZE_VIOLATION = (
        "minimum_group_size_violation"
    )


class ResultFieldBinding(BaseModel):
    """
    Query Plan / Metadata 提供的可信结果字段绑定。
    """

    model_config = ConfigDict(frozen=True)

    output_field: str
    source_columns: frozenset[str]
    category: SensitiveDataCategory
    token_namespace: str | None = None

    @model_validator(mode="after")
    def validate_field_binding(self):
        if not _SAFE_OUTPUT_FIELD_PATTERN.fullmatch(
            self.output_field
        ):
            raise ValueError(
                "output_field must be a safe SQL result identifier."
            )

        if not self.source_columns:
            raise ValueError(
                "source_columns cannot be empty."
            )

        invalid_source_columns = sorted(
            source_column
            for source_column in self.source_columns
            if (
                not isinstance(source_column, str)
                or not _SAFE_SOURCE_COLUMN_PATTERN.fullmatch(
                    source_column
                )
            )
        )

        if invalid_source_columns:
            raise ValueError(
                "source_columns must use safe table.column names: "
                f"{invalid_source_columns}"
            )

        if (
            self.category
            == SensitiveDataCategory.PSEUDONYMOUS_IDENTIFIER
        ):
            if (
                self.token_namespace is None
                or not self.token_namespace.strip()
            ):
                raise ValueError(
                    "Pseudonymous identifiers require "
                    "token_namespace."
                )
        elif self.token_namespace is not None:
            raise ValueError(
                "token_namespace is only valid for "
                "pseudonymous identifiers."
            )

        return self


class ResultProtectionContract(BaseModel):
    """
    单条查询结果的可信保护合同。
    """

    model_config = ConfigDict(frozen=True)

    field_bindings: tuple[ResultFieldBinding, ...]
    result_shape: ResultShape

    minimum_group_size_required: bool = False
    group_size_field: str | None = None

    policy_version: str = "result_protection_v1"

    @model_validator(mode="after")
    def validate_contract(self):
        if not self.field_bindings:
            raise ValueError(
                "field_bindings cannot be empty."
            )

        output_fields = [
            binding.output_field
            for binding in self.field_bindings
        ]

        if len(output_fields) != len(set(output_fields)):
            raise ValueError(
                "field_bindings cannot contain duplicate "
                "output_field values."
            )

        if (
            not self.policy_version
            or not self.policy_version.strip()
        ):
            raise ValueError(
                "policy_version cannot be empty."
            )

        if self.minimum_group_size_required:
            if (
                self.group_size_field is None
                or not _SAFE_OUTPUT_FIELD_PATTERN.fullmatch(
                    self.group_size_field
                )
            ):
                raise ValueError(
                    "A safe group_size_field is required when "
                    "minimum group size enforcement is enabled."
                )

            if self.group_size_field in set(output_fields):
                raise ValueError(
                    "group_size_field must be a hidden control "
                    "field, not a returned output field."
                )
        elif self.group_size_field is not None:
            raise ValueError(
                "group_size_field must be omitted when minimum "
                "group size enforcement is disabled."
            )

        return self


class AppliedFieldProtection(BaseModel):
    model_config = ConfigDict(frozen=True)

    output_field: str
    category: SensitiveDataCategory
    action: ProtectionAction


class ResultProtectionResult(BaseModel):
    """
    结果保护的结构化输出。
    """

    model_config = ConfigDict(frozen=True)

    success: bool
    rows: tuple[dict[str, Any], ...] = ()
    row_count: int = Field(default=0, ge=0)

    error_type: str | None = None
    reason_code: ProtectionReason
    message: str

    applied_protections: tuple[
        AppliedFieldProtection,
        ...
    ] = ()
    rejected_fields: frozenset[str] = Field(
        default_factory=frozenset
    )

    minimum_group_size_checked: bool = False
    minimum_observed_group_size: int | None = Field(
        default=None,
        ge=0,
    )

    contract_fingerprint: str
    protection_fingerprint: str

    policy_version: str
    retryable: bool = False

    @model_validator(mode="after")
    def validate_result(self):
        if self.success:
            if self.error_type is not None:
                raise ValueError(
                    "Successful protection cannot contain "
                    "error_type."
                )

            if self.reason_code != ProtectionReason.ALLOWED:
                raise ValueError(
                    "Successful protection must use reason=allowed."
                )

            if self.row_count != len(self.rows):
                raise ValueError(
                    "row_count must equal len(rows)."
                )
        else:
            if self.error_type != "result_protection_error":
                raise ValueError(
                    "Failed protection must use "
                    "result_protection_error."
                )

            if self.reason_code == ProtectionReason.ALLOWED:
                raise ValueError(
                    "Failed protection cannot use reason=allowed."
                )

            if self.rows or self.row_count != 0:
                raise ValueError(
                    "Failed protection must not return partial rows."
                )

        if self.retryable:
            raise ValueError(
                "Result protection failures must not be retryable."
            )

        return self


_V2_SENSITIVE_FIELD_CATALOG = MappingProxyType(
    {
        "dim_customer.customer_id": (
            SensitiveDataCategory.PSEUDONYMOUS_IDENTIFIER
        ),
        "dim_customer.customer_code": (
            SensitiveDataCategory.PSEUDONYMOUS_IDENTIFIER
        ),
        "dim_membership_account.membership_account_id": (
            SensitiveDataCategory.PSEUDONYMOUS_IDENTIFIER
        ),
        "dim_membership_account.member_code": (
            SensitiveDataCategory.PSEUDONYMOUS_IDENTIFIER
        ),
        "fact_orders.order_id": (
            SensitiveDataCategory.PSEUDONYMOUS_IDENTIFIER
        ),
        "fact_orders.order_code": (
            SensitiveDataCategory.PSEUDONYMOUS_IDENTIFIER
        ),
        "fact_orders.customer_id": (
            SensitiveDataCategory.PSEUDONYMOUS_IDENTIFIER
        ),
        "fact_order_items.order_item_id": (
            SensitiveDataCategory.PSEUDONYMOUS_IDENTIFIER
        ),
        "fact_order_items.order_id": (
            SensitiveDataCategory.PSEUDONYMOUS_IDENTIFIER
        ),
        "fact_refunds.refund_id": (
            SensitiveDataCategory.PSEUDONYMOUS_IDENTIFIER
        ),
        "fact_refunds.order_id": (
            SensitiveDataCategory.PSEUDONYMOUS_IDENTIFIER
        ),
        "fact_refunds.order_item_id": (
            SensitiveDataCategory.PSEUDONYMOUS_IDENTIFIER
        ),
        "fact_reviews.review_id": (
            SensitiveDataCategory.PSEUDONYMOUS_IDENTIFIER
        ),
        "fact_reviews.order_item_id": (
            SensitiveDataCategory.PSEUDONYMOUS_IDENTIFIER
        ),
        "fact_reviews.review_text": (
            SensitiveDataCategory.FREE_TEXT
        ),
        "fact_refunds.refund_reason": (
            SensitiveDataCategory.FREE_TEXT
        ),
        "fact_order_items.unit_cost_at_order": (
            SensitiveDataCategory.BUSINESS_CONFIDENTIAL
        ),
        "fact_order_items.item_cost_amount": (
            SensitiveDataCategory.BUSINESS_CONFIDENTIAL
        ),
        "fact_marketing_spend.spend_amount": (
            SensitiveDataCategory.BUSINESS_CONFIDENTIAL
        ),
        "fact_membership_tier_history.r12_valid_spend": (
            SensitiveDataCategory.BUSINESS_CONFIDENTIAL
        ),
        "fact_refunds.refund_amount": (
            SensitiveDataCategory.BUSINESS_CONFIDENTIAL
        ),
    }
)


def get_v2_sensitive_field_catalog(
) -> Mapping[str, SensitiveDataCategory]:
    return _V2_SENSITIVE_FIELD_CATALOG


def classify_v2_source_column(
    source_column: str,
) -> SensitiveDataCategory:
    return _V2_SENSITIVE_FIELD_CATALOG.get(
        source_column,
        SensitiveDataCategory.ORDINARY,
    )


def build_raw_field_binding(
    *,
    output_field: str,
    source_column: str,
    token_namespace: str | None = None,
) -> ResultFieldBinding:
    category = classify_v2_source_column(source_column)

    return ResultFieldBinding(
        output_field=output_field,
        source_columns=frozenset({source_column}),
        category=category,
        token_namespace=(
            token_namespace
            if category
            == SensitiveDataCategory.PSEUDONYMOUS_IDENTIFIER
            else None
        ),
    )


def build_contract_fingerprint(
    contract: ResultProtectionContract,
) -> str:
    payload = {
        "field_bindings": [
            {
                "output_field": binding.output_field,
                "source_columns": sorted(
                    binding.source_columns
                ),
                "category": binding.category.value,
                "token_namespace": binding.token_namespace,
            }
            for binding in contract.field_bindings
        ],
        "result_shape": contract.result_shape.value,
        "minimum_group_size_required": (
            contract.minimum_group_size_required
        ),
        "group_size_field": contract.group_size_field,
        "policy_version": contract.policy_version,
    }

    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )

    return hashlib.sha256(
        serialized.encode("utf-8")
    ).hexdigest()


def build_protection_fingerprint(
    *,
    context: AccessContext,
    contract: ResultProtectionContract,
) -> str:
    payload = {
        "contract_fingerprint": (
            build_contract_fingerprint(contract)
        ),
        "access_policy_version": context.policy_version,
        "allow_direct_identifiers": (
            context.sensitive_data_policy
            .allow_direct_identifiers
        ),
        "allow_free_text": (
            context.sensitive_data_policy.allow_free_text
        ),
        "allow_cost_data": (
            context.sensitive_data_policy.allow_cost_data
        ),
        "minimum_group_size": (
            context.sensitive_data_policy.minimum_group_size
        ),
    }

    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )

    return hashlib.sha256(
        serialized.encode("utf-8")
    ).hexdigest()


def _failure(
    *,
    context: AccessContext,
    contract: ResultProtectionContract,
    reason_code: ProtectionReason,
    message: str,
    rejected_fields: Sequence[str] = (),
    minimum_group_size_checked: bool = False,
    minimum_observed_group_size: int | None = None,
) -> ResultProtectionResult:
    return ResultProtectionResult(
        success=False,
        rows=(),
        row_count=0,
        error_type="result_protection_error",
        reason_code=reason_code,
        message=message,
        applied_protections=(),
        rejected_fields=frozenset(rejected_fields),
        minimum_group_size_checked=(
            minimum_group_size_checked
        ),
        minimum_observed_group_size=(
            minimum_observed_group_size
        ),
        contract_fingerprint=(
            build_contract_fingerprint(contract)
        ),
        protection_fingerprint=(
            build_protection_fingerprint(
                context=context,
                contract=contract,
            )
        ),
        policy_version=contract.policy_version,
        retryable=False,
    )


def _resolve_action(
    *,
    context: AccessContext,
    binding: ResultFieldBinding,
) -> ProtectionAction:
    category = binding.category
    policy = context.sensitive_data_policy

    if category == SensitiveDataCategory.ORDINARY:
        return ProtectionAction.ALLOW

    if (
        category
        == SensitiveDataCategory.PSEUDONYMOUS_IDENTIFIER
    ):
        return ProtectionAction.TOKENIZE

    if category == SensitiveDataCategory.DIRECT_IDENTIFIER:
        return (
            ProtectionAction.ALLOW
            if policy.allow_direct_identifiers
            else ProtectionAction.REJECT
        )

    if category == SensitiveDataCategory.FREE_TEXT:
        return (
            ProtectionAction.ALLOW
            if policy.allow_free_text
            else ProtectionAction.REJECT
        )

    if category == SensitiveDataCategory.BUSINESS_CONFIDENTIAL:
        return (
            ProtectionAction.ALLOW
            if policy.allow_cost_data
            else ProtectionAction.REJECT
        )

    return ProtectionAction.REJECT


def _reason_for_rejected_category(
    category: SensitiveDataCategory,
) -> ProtectionReason:
    if category == SensitiveDataCategory.DIRECT_IDENTIFIER:
        return ProtectionReason.DIRECT_IDENTIFIER_NOT_ALLOWED

    if category == SensitiveDataCategory.FREE_TEXT:
        return ProtectionReason.FREE_TEXT_NOT_ALLOWED

    if category == SensitiveDataCategory.BUSINESS_CONFIDENTIAL:
        return ProtectionReason.COST_DATA_NOT_ALLOWED

    return ProtectionReason.INVALID_PROTECTION_CONTRACT


def _tokenize_value(
    *,
    value: Any,
    secret: str,
    namespace: str,
) -> str:
    message = (
        f"{namespace}\x1f{type(value).__name__}\x1f{value}"
    ).encode("utf-8")

    digest = hmac.new(
        secret.encode("utf-8"),
        message,
        hashlib.sha256,
    ).hexdigest()

    return f"TOK_{digest[:20]}"


def protect_result_rows(
    *,
    context: AccessContext,
    rows: Sequence[Mapping[str, Any]],
    contract: ResultProtectionContract,
    tokenization_secret: str | None = None,
) -> ResultProtectionResult:
    bindings_by_field = {
        binding.output_field: binding
        for binding in contract.field_bindings
    }

    expected_fields = set(bindings_by_field)
    expected_result_fields = set(expected_fields)

    if contract.minimum_group_size_required:
        expected_result_fields.add(
            contract.group_size_field  # type: ignore[arg-type]
        )

    normalized_rows: list[dict[str, Any]] = []

    for raw_row in rows:
        if not isinstance(raw_row, Mapping):
            return _failure(
                context=context,
                contract=contract,
                reason_code=(
                    ProtectionReason.INVALID_RESULT_SHAPE
                ),
                message="Every result row must be a mapping.",
            )

        row = dict(raw_row)
        actual_fields = set(row)

        if actual_fields != expected_result_fields:
            return _failure(
                context=context,
                contract=contract,
                reason_code=(
                    ProtectionReason.INVALID_RESULT_SHAPE
                ),
                message=(
                    "Result fields do not exactly match the "
                    "trusted protection contract."
                ),
                rejected_fields=sorted(
                    actual_fields.symmetric_difference(
                        expected_result_fields
                    )
                ),
            )

        normalized_rows.append(row)

    applied_protections: list[
        AppliedFieldProtection
    ] = []

    for binding in contract.field_bindings:
        action = _resolve_action(
            context=context,
            binding=binding,
        )

        applied_protections.append(
            AppliedFieldProtection(
                output_field=binding.output_field,
                category=binding.category,
                action=action,
            )
        )

        if action == ProtectionAction.REJECT:
            return _failure(
                context=context,
                contract=contract,
                reason_code=(
                    _reason_for_rejected_category(
                        binding.category
                    )
                ),
                message=(
                    "One or more result fields are not allowed "
                    "by the sensitive data policy."
                ),
                rejected_fields=(
                    binding.output_field,
                ),
            )

    tokenized_bindings = [
        binding
        for binding in contract.field_bindings
        if (
            binding.category
            == SensitiveDataCategory.PSEUDONYMOUS_IDENTIFIER
        )
    ]

    has_tokenizable_values = any(
        row.get(binding.output_field) is not None
        for row in normalized_rows
        for binding in tokenized_bindings
    )

    if has_tokenizable_values:
        if (
            tokenization_secret is None
            or len(tokenization_secret) < 16
        ):
            return _failure(
                context=context,
                contract=contract,
                reason_code=(
                    ProtectionReason.MISSING_TOKENIZATION_SECRET
                ),
                message=(
                    "A tokenization secret of at least 16 "
                    "characters is required."
                ),
                rejected_fields=(
                    binding.output_field
                    for binding in tokenized_bindings
                ),
            )

    minimum_observed_group_size = None

    if contract.minimum_group_size_required:
        group_size_field = contract.group_size_field
        group_sizes: list[int] = []

        for row in normalized_rows:
            group_size = row.get(group_size_field)

            if (
                isinstance(group_size, bool)
                or not isinstance(group_size, int)
                or group_size < 0
            ):
                return _failure(
                    context=context,
                    contract=contract,
                    reason_code=(
                        ProtectionReason
                        .MINIMUM_GROUP_SIZE_NOT_PROVEN
                    ),
                    message=(
                        "Minimum group size could not be proven "
                        "from the governed control field."
                    ),
                    minimum_group_size_checked=True,
                )

            group_sizes.append(group_size)

        minimum_observed_group_size = (
            min(group_sizes)
            if group_sizes
            else None
        )

        if (
            minimum_observed_group_size is not None
            and minimum_observed_group_size
            < context.sensitive_data_policy.minimum_group_size
        ):
            return _failure(
                context=context,
                contract=contract,
                reason_code=(
                    ProtectionReason
                    .MINIMUM_GROUP_SIZE_VIOLATION
                ),
                message=(
                    "One or more aggregate groups are smaller "
                    "than the configured minimum group size."
                ),
                minimum_group_size_checked=True,
                minimum_observed_group_size=(
                    minimum_observed_group_size
                ),
            )

    protected_rows: list[dict[str, Any]] = []

    for row in normalized_rows:
        protected_row: dict[str, Any] = {}

        for binding in contract.field_bindings:
            value = row[binding.output_field]
            action = _resolve_action(
                context=context,
                binding=binding,
            )

            if (
                action == ProtectionAction.TOKENIZE
                and value is not None
            ):
                protected_row[binding.output_field] = (
                    _tokenize_value(
                        value=value,
                        secret=tokenization_secret or "",
                        namespace=(
                            binding.token_namespace or ""
                        ),
                    )
                )
            else:
                protected_row[binding.output_field] = value

        protected_rows.append(protected_row)

    return ResultProtectionResult(
        success=True,
        rows=tuple(protected_rows),
        row_count=len(protected_rows),
        error_type=None,
        reason_code=ProtectionReason.ALLOWED,
        message="Result protection completed.",
        applied_protections=tuple(applied_protections),
        rejected_fields=frozenset(),
        minimum_group_size_checked=(
            contract.minimum_group_size_required
        ),
        minimum_observed_group_size=(
            minimum_observed_group_size
        ),
        contract_fingerprint=(
            build_contract_fingerprint(contract)
        ),
        protection_fingerprint=(
            build_protection_fingerprint(
                context=context,
                contract=contract,
            )
        ),
        policy_version=contract.policy_version,
        retryable=False,
    )
