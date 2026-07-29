from __future__ import annotations

import hashlib
import json
from enum import Enum
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.semantic_layer.metric_loader_v2 import load_metrics_v2


METRIC_SIGNATURE_VERSION_V2 = "beauty_bi_v2_metric_signature_1"


class SignatureOperator(str, Enum):
    SUM = "sum"
    DISTINCT_COUNT = "distinct_count"
    QUALIFIED_COUNT = "qualified_count"
    DIVIDE = "divide"


class SemanticOperand(str, Enum):
    PAID_AMOUNT = "paid_amount"
    GROSS_MARGIN_AMOUNT = "gross_margin_amount"
    COMPLETED_REFUND_AMOUNT = "completed_refund_amount"
    MARKETING_SPEND = "marketing_spend"

    PAID_ORDER = "paid_order"
    PAID_UNITS = "paid_units"
    PAID_BUYER = "paid_buyer"

    GLOBAL_FIRST_PAID_CUSTOMER = "global_first_paid_customer"
    CHANNEL_FIRST_PAID_CUSTOMER = "channel_first_paid_customer"
    REPEAT_DISTINCT_PAID_DATE_CUSTOMER = (
        "repeat_distinct_paid_date_customer"
    )
    MULTI_PAID_ORDER_CUSTOMER = "multi_paid_order_customer"

    PAYMENT_TIME_MEMBER_PAID_AMOUNT = (
        "payment_time_member_paid_amount"
    )


class IntrinsicPartition(str, Enum):
    NONE = "none"
    CHANNEL = "channel"


class SemanticQualifier(str, Enum):
    PAID_ONLY = "paid_only"
    PRODUCT_COST_BASIS = "product_cost_basis"

    COMPLETED_REFUND_ONLY = "completed_refund_only"
    SALES_COHORT_ATTRIBUTION = "sales_cohort_attribution"

    DIRECT_RESPONSE_CHANNEL = "direct_response_channel"
    SAME_WINDOW_SALES_SPEND = "same_window_sales_spend"

    FULL_HISTORY_BRAND_FIRST_PAID = (
        "full_history_brand_first_paid"
    )
    FULL_HISTORY_CHANNEL_FIRST_PAID = (
        "full_history_channel_first_paid"
    )

    DISTINCT_PAID_DATES_GE_2 = "distinct_paid_dates_ge_2"
    PAID_ORDERS_GE_2 = "paid_orders_ge_2"

    PAYMENT_TIME_MEMBERSHIP_SNAPSHOT = (
        "payment_time_membership_snapshot"
    )


class MetricSemanticSignatureV2(BaseModel):
    """
    Machine-readable business identity for one V2 Metric.

    This contract deliberately contains NO query keywords, aliases,
    examples, embedding thresholds, SQL, tables, or Query Plan details.

    It describes business structure, not how to retrieve the metric.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    metric_name: str = Field(
        pattern=r"^[a-z][a-z0-9_]*$"
    )

    operator: SignatureOperator
    left_operand: SemanticOperand
    right_operand: SemanticOperand | None = None

    intrinsic_partition: IntrinsicPartition = (
        IntrinsicPartition.NONE
    )

    qualifiers: tuple[SemanticQualifier, ...] = ()

    @model_validator(mode="after")
    def validate_structure(
        self,
    ) -> "MetricSemanticSignatureV2":
        if self.operator == SignatureOperator.DIVIDE:
            if self.right_operand is None:
                raise ValueError(
                    "divide signature requires right_operand."
                )

            if self.left_operand == self.right_operand:
                raise ValueError(
                    "divide signature cannot use identical operands."
                )

        elif self.right_operand is not None:
            raise ValueError(
                "non-divide signature must not declare right_operand."
            )

        if len(self.qualifiers) != len(set(self.qualifiers)):
            raise ValueError(
                "semantic qualifiers must be unique."
            )

        operands = {
            self.left_operand,
            self.right_operand,
        }

        channel_structural_operands = {
            SemanticOperand.MARKETING_SPEND,
            SemanticOperand.CHANNEL_FIRST_PAID_CUSTOMER,
        }

        if (
            operands
            & channel_structural_operands
        ) and (
            self.intrinsic_partition
            != IntrinsicPartition.CHANNEL
        ):
            raise ValueError(
                "marketing/channel-first-paid structures "
                "require intrinsic_partition=channel."
            )

        if (
            SemanticQualifier.FULL_HISTORY_BRAND_FIRST_PAID
            in self.qualifiers
            and self.left_operand
            != SemanticOperand.GLOBAL_FIRST_PAID_CUSTOMER
        ):
            raise ValueError(
                "brand-first-paid qualifier requires "
                "global_first_paid_customer operand."
            )

        if (
            SemanticQualifier.FULL_HISTORY_CHANNEL_FIRST_PAID
            in self.qualifiers
            and (
                self.left_operand
                != SemanticOperand.CHANNEL_FIRST_PAID_CUSTOMER
                and self.right_operand
                != SemanticOperand.CHANNEL_FIRST_PAID_CUSTOMER
            )
        ):
            raise ValueError(
                "channel-first-paid qualifier requires "
                "channel_first_paid_customer operand."
            )

        if (
            SemanticQualifier.DISTINCT_PAID_DATES_GE_2
            in self.qualifiers
            and self.left_operand
            != SemanticOperand.REPEAT_DISTINCT_PAID_DATE_CUSTOMER
        ):
            raise ValueError(
                "distinct-paid-dates qualifier requires "
                "repeat_distinct_paid_date_customer numerator."
            )

        if (
            SemanticQualifier.PAID_ORDERS_GE_2
            in self.qualifiers
            and self.left_operand
            != SemanticOperand.MULTI_PAID_ORDER_CUSTOMER
        ):
            raise ValueError(
                "paid-orders-ge-2 qualifier requires "
                "multi_paid_order_customer operand."
            )

        if (
            SemanticQualifier.PAYMENT_TIME_MEMBERSHIP_SNAPSHOT
            in self.qualifiers
            and self.left_operand
            != SemanticOperand.PAYMENT_TIME_MEMBER_PAID_AMOUNT
        ):
            raise ValueError(
                "payment-time-membership qualifier requires "
                "payment_time_member_paid_amount numerator."
            )

        return self

    def structural_key(
        self,
    ) -> tuple[str, ...]:
        return (
            self.operator.value,
            self.left_operand.value,
            (
                ""
                if self.right_operand is None
                else self.right_operand.value
            ),
            self.intrinsic_partition.value,
            *sorted(
                qualifier.value
                for qualifier in self.qualifiers
            ),
        )


class MetricSignatureCatalogV2(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    signature_version: str
    dataset_name: str
    status: str
    signatures: tuple[
        MetricSemanticSignatureV2,
        ...
    ]

    @model_validator(mode="after")
    def validate_catalog(
        self,
    ) -> "MetricSignatureCatalogV2":
        if (
            self.signature_version
            != METRIC_SIGNATURE_VERSION_V2
        ):
            raise ValueError(
                "Unexpected Metric Signature V2 version."
            )

        if self.dataset_name != "beauty_bi_v2":
            raise ValueError(
                "Metric Signature Catalog dataset_name "
                "must be beauty_bi_v2."
            )

        names = [
            item.metric_name
            for item in self.signatures
        ]

        if len(names) != len(set(names)):
            raise ValueError(
                "Metric Signature metric_name values must be unique."
            )

        structural_keys = [
            item.structural_key()
            for item in self.signatures
        ]

        if len(structural_keys) != len(set(structural_keys)):
            duplicates: list[tuple[str, ...]] = []
            seen: set[tuple[str, ...]] = set()

            for key in structural_keys:
                if key in seen:
                    duplicates.append(key)
                seen.add(key)

            raise ValueError(
                "Metric Signature Catalog contains duplicate "
                f"business structures: {duplicates}"
            )

        return self


def _metric_signatures_v2_path() -> Path:
    project_root = Path(__file__).resolve().parents[2]

    return (
        project_root
        / "metadata"
        / "beauty_bi_v2"
        / "metric_signatures.yaml"
    )


def load_metric_signature_catalog_v2(
) -> MetricSignatureCatalogV2:
    path = _metric_signatures_v2_path()

    with path.open(
        "r",
        encoding="utf-8",
    ) as f:
        raw = yaml.safe_load(f)

    catalog = MetricSignatureCatalogV2.model_validate(
        raw
    )

    metric_names = {
        str(metric["name"])
        for metric in load_metrics_v2()
    }

    signature_names = {
        signature.metric_name
        for signature in catalog.signatures
    }

    if signature_names != metric_names:
        missing = sorted(
            metric_names
            - signature_names
        )
        extra = sorted(
            signature_names
            - metric_names
        )

        raise ValueError(
            "Metric Signature Catalog must match "
            "business_metrics.yaml exactly. "
            f"Missing={missing}; Extra={extra}"
        )

    return catalog


def get_metric_signature_v2(
    metric_name: str,
) -> MetricSemanticSignatureV2 | None:
    for signature in (
        load_metric_signature_catalog_v2().signatures
    ):
        if signature.metric_name == metric_name:
            return signature

    return None


def canonical_metric_signature_catalog_v2(
) -> bytes:
    catalog = load_metric_signature_catalog_v2()

    payload = {
        "signature_version": catalog.signature_version,
        "dataset_name": catalog.dataset_name,
        "status": catalog.status,
        "signatures": [
            signature.model_dump(
                mode="json"
            )
            for signature in sorted(
                catalog.signatures,
                key=lambda item: item.metric_name,
            )
        ],
    }

    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def metric_signature_catalog_fingerprint_v2(
) -> str:
    return hashlib.sha256(
        canonical_metric_signature_catalog_v2()
    ).hexdigest()


if __name__ == "__main__":
    catalog = load_metric_signature_catalog_v2()

    print(
        "Metric Signature Version:",
        catalog.signature_version,
    )
    print(
        "Metric Signatures:",
        len(catalog.signatures),
    )
    print(
        "Fingerprint:",
        metric_signature_catalog_fingerprint_v2(),
    )

    for signature in catalog.signatures:
        print(
            signature.metric_name,
            signature.structural_key(),
        )
