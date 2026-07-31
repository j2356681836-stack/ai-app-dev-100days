from __future__ import annotations

from dataclasses import dataclass
from typing import AbstractSet

from app.semantic_layer.semantic_decision_service_v2 import (
    SemanticDecisionStatusV2,
    resolve_semantic_decision_v2,
)


@dataclass(frozen=True)
class AcceptanceCaseV2:
    case_id: str
    question: str
    expected_status: SemanticDecisionStatusV2
    expected_metric_name: str | None = None
    expected_candidates: frozenset[str] | None = None
    allowed_metric_names: AbstractSet[str] | None = None


CASES = (
    AcceptanceCaseV2(
        case_id="SDA-001",
        question="把完成支付的商品金额累计起来",
        expected_status=SemanticDecisionStatusV2.MATCHED,
        expected_metric_name="gmv",
    ),
    AcceptanceCaseV2(
        case_id="SDA-002",
        question="每一笔成交订单平均包含多少件商品？",
        expected_status=SemanticDecisionStatusV2.MATCHED,
        expected_metric_name="ipt",
    ),
    AcceptanceCaseV2(
        case_id="SDA-003",
        question="各平台成交金额相对于同期推广花费是几倍",
        expected_status=SemanticDecisionStatusV2.MATCHED,
        expected_metric_name="roi",
    ),
    AcceptanceCaseV2(
        case_id="SDA-004",
        question="平均消费大概是多少？",
        expected_status=SemanticDecisionStatusV2.NEEDS_CLARIFICATION,
        expected_candidates=frozenset(
            {
                "spending_per_buyer",
                "aus",
            }
        ),
    ),
    AcceptanceCaseV2(
        case_id="SDA-005",
        question="本期新客有多少？",
        expected_status=SemanticDecisionStatusV2.NEEDS_CLARIFICATION,
        expected_candidates=frozenset(
            {
                "brand_paid_new_customer_count",
                "channel_paid_new_customer_count",
            }
        ),
    ),
    AcceptanceCaseV2(
        case_id="SDA-006",
        question="成交金额平均到每一件卖出的商品上是多少？",
        expected_status=SemanticDecisionStatusV2.UNSUPPORTED,
    ),
    AcceptanceCaseV2(
        case_id="SDA-007",
        question="同时看成交金额和订单数",
        expected_status=SemanticDecisionStatusV2.MULTIPLE_INTENTS,
    ),
    AcceptanceCaseV2(
        case_id="SDA-008",
        question="把完成支付的商品金额累计起来",
        expected_status=SemanticDecisionStatusV2.UNSUPPORTED,
        allowed_metric_names={
            "buyer_count",
            "order_count",
        },
    ),
)


def _evaluate_case(
    case: AcceptanceCaseV2,
) -> tuple[bool, str]:
    result = resolve_semantic_decision_v2(
        question=case.question,
        allowed_metric_names=case.allowed_metric_names,
    )

    problems: list[str] = []

    if result.status != case.expected_status:
        problems.append(
            f"status expected={case.expected_status.value} "
            f"actual={result.status.value}"
        )

    if (
        case.expected_metric_name is not None
        and result.metric_name != case.expected_metric_name
    ):
        problems.append(
            f"metric expected={case.expected_metric_name} "
            f"actual={result.metric_name}"
        )

    if case.expected_candidates is not None:
        actual_candidates = frozenset(
            result.candidates
        )

        if actual_candidates != case.expected_candidates:
            problems.append(
                "candidates expected="
                f"{sorted(case.expected_candidates)} "
                "actual="
                f"{sorted(actual_candidates)}"
            )

    if (
        result.status
        != SemanticDecisionStatusV2.MATCHED
        and result.metric_name is not None
    ):
        problems.append(
            "non-MATCHED result must not expose metric_name"
        )

    if (
        result.status
        != SemanticDecisionStatusV2.NEEDS_CLARIFICATION
        and result.ranking_applied
    ):
        problems.append(
            "embedding ranking must only be applied to clarification"
        )

    if problems:
        return False, "; ".join(problems)

    return True, "ok"


def run_acceptance() -> None:
    passed = 0
    failed = 0

    print("=" * 80)
    print(
        "Semantic Decision V2 Final Acceptance / Regression"
    )
    print(
        f"Cases: {len(CASES)}"
    )

    for case in CASES:
        print("=" * 80)
        print(
            f"{case.case_id}: {case.question}"
        )

        try:
            ok, detail = _evaluate_case(
                case
            )
        except Exception as exc:
            ok = False
            detail = (
                f"exception: {type(exc).__name__}: {exc}"
            )

        if ok:
            passed += 1
            print("[PASS]")
        else:
            failed += 1
            print("[FAIL]")
            print(detail)

    print("=" * 80)
    print(
        "Semantic Decision V2 Final Acceptance Summary"
    )
    print(
        f"Total: {len(CASES)}"
    )
    print(
        f"Passed: {passed}"
    )
    print(
        f"Failed: {failed}"
    )

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    run_acceptance()
