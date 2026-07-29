from __future__ import annotations

import re
from enum import Enum

from pydantic import (
    BaseModel,
    ConfigDict,
)

from app.semantic_layer.metric_loader_v2 import (
    search_metric_candidates_v2,
)
from app.semantic_layer.query_plan_v2_loader import (
    get_query_plan_v2_by_name,
    get_query_plans_v2_by_metric,
)


class MetricResolutionStatus(str, Enum):
    MATCHED = "matched"
    NEEDS_CLARIFICATION = "needs_clarification"
    UNSUPPORTED = "unsupported"


class PlanResolutionStatus(str, Enum):
    SELECTED = "selected"
    NOT_APPLICABLE = "not_applicable"
    UNSUPPORTED_SHAPE = "unsupported_shape"


class DecisionResultGrain(str, Enum):
    OVERALL = "overall"
    CHANNEL = "channel"
    REGION = "region"
    CATEGORY = "category"


class DecisionRankingType(str, Enum):
    TOP1 = "top1"
    TOPN = "topn"
    RANKING = "ranking"
    UNKNOWN = "unknown"


class DecisionSortDirection(str, Enum):
    ASC = "asc"
    DESC = "desc"


class MetricResolutionV2(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    status: MetricResolutionStatus
    metric_name: str | None = None
    candidates: tuple[str, ...] = ()
    method: str
    matched_text: str | None = None


class IntentResolutionV2(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    result_grain: DecisionResultGrain | None
    limit: int | None
    ranking_type: DecisionRankingType
    sort_direction: DecisionSortDirection | None


class PlanResolutionV2(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    status: PlanResolutionStatus
    plan_name: str | None = None


class DecisionResolutionV2(BaseModel):
    """
    Day74 Candidate Decision Baseline。

    只回答：
        Question
        → Metric
        → Result Grain / Ranking Shape
        → Query Plan

    不负责：
        SQL
        Database
        Answer
        AccessContext
        Governance Enforcement
        Graph Routing
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    question: str
    metric: MetricResolutionV2
    intent: IntentResolutionV2
    plan: PlanResolutionV2


_CHINESE_NUMBER_MAP = {
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}


def _contains_any(
    question: str,
    phrases: tuple[str, ...],
) -> bool:
    return any(
        phrase in question
        for phrase in phrases
    )


def _resolve_semantic_metric_rule(
    question: str,
) -> MetricResolutionV2 | None:
    """
    只处理正式 aliases 无法覆盖、但业务语义非常稳定的通用表达。

    规则按“概念族”写，不按 Golden Case ID / 完整问题写，
    避免把 Development Set 变成 if-question 特例库。
    """

    # Repeat Rate：报告周期口径 vs Cohort 口径必须分开。
    #
    # 当前 repeat_customer_rate 的合同是：
    #   analysis period 内，至少跨两个不同支付日期购买的客户
    #   / analysis period buyer_count
    #
    # 它不是：
    #   新客首购后 30 / 60 / 90 天复购率
    #   cohort retention / repurchase
    #
    # 因此先拦截 cohort 特征，再允许普通“复购率”映射。
    if "复购率" in question:
        cohort_window = re.search(
            r"(?<!\d)(\d{1,3})\s*(天|日|周|个月|月)",
            question,
        )

        cohort_semantics = (
            cohort_window is not None
            or _contains_any(
                question,
                (
                    "新客复购",
                    "首购后",
                    "首单后",
                    "首次购买后",
                    "cohort",
                    "留存",
                ),
            )
        )

        if cohort_semantics:
            return MetricResolutionV2(
                status=MetricResolutionStatus.UNSUPPORTED,
                candidates=(),
                method="semantic_rule",
                matched_text="unsupported_cohort_repeat_rate",
            )

        return MetricResolutionV2(
            status=MetricResolutionStatus.MATCHED,
            metric_name="repeat_customer_rate",
            candidates=(),
            method="semantic_rule",
            matched_text="period_repeat_rate",
        )

    # 未限定口径的“新客”必须澄清品牌 vs 渠道。
    if (
        "新客" in question
        and "品牌" not in question
        and "渠道" not in question
    ):
        return MetricResolutionV2(
            status=MetricResolutionStatus.NEEDS_CLARIFICATION,
            candidates=(
                "brand_paid_new_customer_count",
                "channel_paid_new_customer_count",
            ),
            method="semantic_rule",
            matched_text="新客",
        )

    # AUS：每笔 / 每单交易金额。
    if (
        _contains_any(
            question,
            (
                "每单多少钱",
                "每笔多少钱",
                "每单金额",
                "每笔金额",
            ),
        )
        and not _contains_any(
            question,
            (
                "几件",
                "件数",
            ),
        )
    ):
        return MetricResolutionV2(
            status=MetricResolutionStatus.MATCHED,
            metric_name="aus",
            method="semantic_rule",
            matched_text="per_transaction_amount",
        )

    # IPT：平均一单购买多少件。
    if _contains_any(
        question,
        (
            "每单买几件",
            "每单几件",
            "一单买几件",
            "一单几件",
        ),
    ):
        return MetricResolutionV2(
            status=MetricResolutionStatus.MATCHED,
            metric_name="ipt",
            method="semantic_rule",
            matched_text="items_per_transaction",
        )

    # 两单及以上口径优先于宽泛“复购”表达。
    if _contains_any(
        question,
        (
            "两单及以上",
            "两单以上",
            "2单及以上",
            "2单以上",
            "下过两单",
            "多单客户",
            "多订单客户",
        ),
    ):
        return MetricResolutionV2(
            status=MetricResolutionStatus.MATCHED,
            metric_name="multi_order_customer_count",
            method="semantic_rule",
            matched_text="multi_order_customer",
        )

    # 明确“不同日期 / 跨日”的复购人数。
    if (
        _contains_any(
            question,
            (
                "不同日期",
                "跨日",
                "不同购买日",
                "跨购买日",
            ),
        )
        and _contains_any(
            question,
            (
                "客户",
                "人数",
                "人",
            ),
        )
        and "率" not in question
    ):
        return MetricResolutionV2(
            status=MetricResolutionStatus.MATCHED,
            metric_name="repeat_customer_count",
            method="semantic_rule",
            matched_text="cross_day_repeat_customer",
        )

    return None


def resolve_metric_v2(
    question: str,
) -> MetricResolutionV2:
    """
    Metric Resolution 顺序：

    1. 明确的业务歧义 / 通用语义规则；
    2. V2 name / chinese_name / aliases；
    3. 没有命中则 unsupported。

    当前 baseline 不使用 Embedding。
    """

    semantic_rule = _resolve_semantic_metric_rule(
        question
    )

    if semantic_rule is not None:
        return semantic_rule

    candidates = search_metric_candidates_v2(
        question
    )

    if not candidates:
        return MetricResolutionV2(
            status=MetricResolutionStatus.UNSUPPORTED,
            candidates=(),
            method="rule",
            matched_text=None,
        )

    if len(candidates) == 1:
        item = candidates[0]

        return MetricResolutionV2(
            status=MetricResolutionStatus.MATCHED,
            metric_name=item["name"],
            candidates=(),
            method="rule",
            matched_text=item["matched_text"],
        )

    return MetricResolutionV2(
        status=MetricResolutionStatus.NEEDS_CLARIFICATION,
        candidates=tuple(
            item["name"]
            for item in candidates
        ),
        method="rule",
        matched_text=None,
    )


def resolve_result_grain_v2(
    question: str,
) -> DecisionResultGrain:
    """
    Result Grain 与底层 Metric grain 分离。

    当前 P0 Result Grain：
    overall / channel / region / category

    这里只判断“结果按什么维度返回”，
    不把华东/天猫等过滤值误当成 Result Grain。
    """

    if _contains_any(
        question,
        (
            "渠道",
            "平台",
        ),
    ):
        return DecisionResultGrain.CHANNEL

    if _contains_any(
        question,
        (
            "地区",
            "区域",
        ),
    ):
        return DecisionResultGrain.REGION

    if _contains_any(
        question,
        (
            "品类",
            "类目",
        ),
    ):
        return DecisionResultGrain.CATEGORY

    return DecisionResultGrain.OVERALL


def resolve_limit_v2(
    question: str,
) -> int | None:
    top_match = re.search(
        r"top\s*(\d+)",
        question,
        re.IGNORECASE,
    )

    if top_match:
        return int(top_match.group(1))

    front_digit_match = re.search(
        r"前\s*(\d+)",
        question,
    )

    if front_digit_match:
        return int(front_digit_match.group(1))

    front_chinese_match = re.search(
        r"前\s*([一二三四五六七八九十])",
        question,
    )

    if front_chinese_match:
        return _CHINESE_NUMBER_MAP[
            front_chinese_match.group(1)
        ]

    amount_digit_match = re.search(
        r"(\d+)\s*(个|名|家|条|种|类|款|渠道|品类|地区)",
        question,
    )

    if amount_digit_match:
        return int(amount_digit_match.group(1))

    amount_chinese_match = re.search(
        r"([一二两三四五六七八九十])\s*"
        r"(个|名|家|条|种|类|款|渠道|品类|地区)",
        question,
    )

    if amount_chinese_match:
        return _CHINESE_NUMBER_MAP[
            amount_chinese_match.group(1)
        ]

    if _contains_any(
        question,
        (
            "最高",
            "最低",
            "最大",
            "最小",
            "最多",
            "最少",
            "第一",
            "最好",
            "最差",
        ),
    ):
        return 1

    return None


def resolve_sort_direction_v2(
    question: str,
) -> DecisionSortDirection | None:
    if _contains_any(
        question,
        (
            "最低",
            "最小",
            "最少",
            "从低到高",
            "升序",
        ),
    ):
        return DecisionSortDirection.ASC

    if _contains_any(
        question,
        (
            "最高",
            "最大",
            "最多",
            "从高到低",
            "降序",
        ),
    ):
        return DecisionSortDirection.DESC

    return None


def resolve_ranking_type_v2(
    question: str,
    limit: int | None,
) -> DecisionRankingType:
    if limit == 1:
        return DecisionRankingType.TOP1

    if limit is not None and limit > 1:
        return DecisionRankingType.TOPN

    if _contains_any(
        question,
        (
            "排名",
            "排行",
            "排序",
        ),
    ):
        return DecisionRankingType.RANKING

    return DecisionRankingType.UNKNOWN


def resolve_intent_shape_v2(
    question: str,
) -> IntentResolutionV2:
    limit = resolve_limit_v2(question)

    return IntentResolutionV2(
        result_grain=resolve_result_grain_v2(
            question
        ),
        limit=limit,
        ranking_type=resolve_ranking_type_v2(
            question,
            limit,
        ),
        sort_direction=resolve_sort_direction_v2(
            question
        ),
    )


def select_query_plan_v2(
    *,
    metric: MetricResolutionV2,
    intent: IntentResolutionV2,
) -> PlanResolutionV2:
    """
    Metric + Result Grain → exact V2 Query Plan。

    一个 metric 可以有多个 Plan，
    因此禁止使用“取第一条 Plan”的 V1 假设。
    """

    if metric.status != MetricResolutionStatus.MATCHED:
        return PlanResolutionV2(
            status=PlanResolutionStatus.NOT_APPLICABLE,
            plan_name=None,
        )

    plans = get_query_plans_v2_by_metric(
        metric.metric_name
    )

    matching = [
        plan
        for plan in plans
        if plan.result_grain == intent.result_grain.value
    ]

    if not matching:
        return PlanResolutionV2(
            status=PlanResolutionStatus.UNSUPPORTED_SHAPE,
            plan_name=None,
        )

    if len(matching) > 1:
        names = [
            plan.name
            for plan in matching
        ]

        raise ValueError(
            "Query Plan V2 Catalog contains multiple "
            "plans for the same metric/result_grain: "
            f"metric={metric.metric_name}, "
            f"grain={intent.result_grain.value}, "
            f"plans={names}"
        )

    return PlanResolutionV2(
        status=PlanResolutionStatus.SELECTED,
        plan_name=matching[0].name,
    )


def resolve_final_sort_direction_v2(
    *,
    intent: IntentResolutionV2,
    plan: PlanResolutionV2,
) -> IntentResolutionV2:
    """
    生成最终排序方向。

    优先级：
    1. 用户显式排序方向；
    2. 已选 Query Plan 的 default_sort.direction；
    3. None。

    仅在 Top1 / TopN / Ranking 场景回填 Plan 默认排序。
    普通单值查询即使 Plan Contract 存在 default_sort，
    也不需要把它暴露成实际排序意图。
    """

    if intent.sort_direction is not None:
        return intent

    if intent.ranking_type not in {
        DecisionRankingType.TOP1,
        DecisionRankingType.TOPN,
        DecisionRankingType.RANKING,
    }:
        return intent

    if (
        plan.status != PlanResolutionStatus.SELECTED
        or plan.plan_name is None
    ):
        return intent

    query_plan = get_query_plan_v2_by_name(
        plan.plan_name
    )

    if query_plan is None:
        raise ValueError(
            "Selected Query Plan disappeared from V2 Catalog: "
            f"{plan.plan_name}"
        )

    default_direction = (
        query_plan.default_sort.direction
    )

    return intent.model_copy(
        update={
            "sort_direction": (
                DecisionSortDirection(
                    default_direction
                )
            )
        }
    )


def resolve_decision_v2(
    question: str,
) -> DecisionResolutionV2:
    """
    Dataset V2 Deterministic Decision Baseline。
    """
    metric = resolve_metric_v2(question)
    intent = resolve_intent_shape_v2(question)
    plan = select_query_plan_v2(
        metric=metric,
        intent=intent,
    )

    final_intent = resolve_final_sort_direction_v2(
        intent=intent,
        plan=plan,
    )

    return DecisionResolutionV2(
        question=question,
        metric=metric,
        intent=final_intent,
        plan=plan,
    )


if __name__ == "__main__":
    questions = [
        "各渠道GMV排名",
        "哪个品类毛利率最高？",
        "今年新客多少？",
        "平均每单多少钱？",
        "平均每单买几件？",
        "至少在两个不同日期购买过的客户有多少？",
        "下过两单及以上的客户有多少？",
        "各地区ROI排名",
    ]

    for question in questions:
        print("=" * 80)
        print(question)
        print(
            resolve_decision_v2(
                question
            ).model_dump(
                mode="json"
            )
        )
