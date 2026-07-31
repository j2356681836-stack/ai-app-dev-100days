from __future__ import annotations

from app.semantic_layer.candidate_decision_narrowing_v2 import (
    narrow_clarification_candidates_v2,
)
from app.semantic_layer.candidate_decision_ranking_v2 import (
    apply_embedding_ranking_v2,
)
from app.semantic_layer.candidate_decision_v2 import (
    decide_metric_candidate_v2,
)
from app.semantic_layer.question_semantic_parser_v2 import (
    QuestionSemanticParseStatusV2,
    parse_question_semantics_v2,
)


QUESTIONS = (
    "把完成支付的商品金额累计起来",
    "每一笔成交订单平均包含多少件商品？",
    "各平台成交金额相对于同期推广花费是几倍",
    "平均消费大概是多少？",
    "成交金额平均到每一件卖出的商品上是多少？",
    "本期新客有多少？",
)


def _print_signature(result) -> None:
    if result.signature is None:
        print("Signature: None")
        return

    signature = result.signature

    print(
        "Signature:",
        {
            "operator": (
                None
                if signature.operator is None
                else signature.operator.value
            ),
            "left_operand": (
                None
                if signature.left_operand is None
                else signature.left_operand.value
            ),
            "right_operand": (
                None
                if signature.right_operand is None
                else signature.right_operand.value
            ),
            "intrinsic_partition": (
                None
                if signature.intrinsic_partition is None
                else signature.intrinsic_partition.value
            ),
            "qualifiers": [
                qualifier.value
                for qualifier in signature.qualifiers
            ],
        },
    )


def run_probe() -> None:
    print("=" * 80)
    print("Candidate Decision V2 Gate 3F Integration Probe")
    print("Questions:", len(QUESTIONS))

    for question in QUESTIONS:
        print("=" * 80)
        print("Question:", question)

        parsed = parse_question_semantics_v2(
            question
        )

        print(
            "Parser Status:",
            parsed.status.value,
        )
        _print_signature(
            parsed
        )

        if (
            parsed.status
            != QuestionSemanticParseStatusV2.PARSED
            or parsed.signature is None
        ):
            print(
                "Decision: skipped "
                "(parser did not return one single parsed signature)"
            )
            continue

        structural = decide_metric_candidate_v2(
            question_signature=parsed.signature
        )

        print(
            "Structural Decision:",
            {
                "status": structural.status.value,
                "metric_name": structural.metric_name,
                "candidates": list(
                    structural.candidates
                ),
            },
        )

        narrowed = narrow_clarification_candidates_v2(
            question=question,
            decision=structural,
        )

        print(
            "Narrowed Decision:",
            {
                "status": narrowed.status.value,
                "metric_name": narrowed.metric_name,
                "candidates": list(
                    narrowed.candidates
                ),
            },
        )

        ranked = apply_embedding_ranking_v2(
            question=question,
            decision=narrowed,
        )

        print(
            "Ranked Decision:",
            {
                "status": ranked.status.value,
                "metric_name": ranked.metric_name,
                "candidates": list(
                    ranked.candidates
                ),
                "ranking_applied": (
                    ranked.ranking_applied
                ),
                "ranking_method": (
                    ranked.ranking_method
                ),
            },
        )

    print("=" * 80)
    print("Gate 3F integration probe completed.")


if __name__ == "__main__":
    run_probe()
