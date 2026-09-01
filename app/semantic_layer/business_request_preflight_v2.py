from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, model_validator

from app.semantic_layer.metric_loader_v2 import (
    search_metric_candidates_v2,
)


BUSINESS_REQUEST_PREFLIGHT_VERSION = (
    "business_request_preflight_v2_0"
)


class BusinessRequestPreflightOutcomeV2(str, Enum):
    CONTINUE = "continue"
    NEEDS_CLARIFICATION = "needs_clarification"
    UNSUPPORTED_CAPABILITY = "unsupported_capability"


class BusinessRequestPreflightDecisionV2(BaseModel):
    """
    自然语言业务问题进入 Semantic Planning 之前的薄边界。

    这里只回答：
    - 当前问题是否应该继续进入 Analytics Planning；
    - 是否缺少一个关键业务口径，需要先澄清；
    - 是否明确要求当前产品尚未提供的分析能力。

    不负责：
    - 选择 Metric；
    - 选择 Query Plan；
    - 解析时间；
    - 检查 Dataset 时间覆盖；
    - Governance / SQL / Result Protection。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    contract_version: str = BUSINESS_REQUEST_PREFLIGHT_VERSION
    outcome: BusinessRequestPreflightOutcomeV2
    reason_code: str | None = None
    user_message: str | None = None

    @model_validator(mode="after")
    def validate_decision(
        self,
    ) -> "BusinessRequestPreflightDecisionV2":
        if self.outcome == BusinessRequestPreflightOutcomeV2.CONTINUE:
            if self.reason_code is not None:
                raise ValueError(
                    "CONTINUE preflight must not carry reason_code."
                )
            if self.user_message is not None:
                raise ValueError(
                    "CONTINUE preflight must not carry user_message."
                )
            return self

        if not self.reason_code:
            raise ValueError(
                "Stopped preflight requires reason_code."
            )

        if not self.user_message or not self.user_message.strip():
            raise ValueError(
                "Stopped preflight requires user_message."
            )

        return self


def _normalize(text: str) -> str:
    return "".join(str(text).casefold().split())


def _contains_any(
    text: str,
    phrases: tuple[str, ...],
) -> bool:
    return any(phrase in text for phrase in phrases)


def _unsupported_capability_decision_v2(
    *,
    forecast_requested: bool,
    inventory_requested: bool,
) -> BusinessRequestPreflightDecisionV2:
    if forecast_requested and inventory_requested:
        reason_code = "unsupported_forecast_and_inventory_planning"
        message = (
            "这个问题暂不支持查询。"
            "目前可以分析已有的历史经营数据，"
            "但暂未提供 GMV 预测和库存规划能力。"
        )
    elif forecast_requested:
        reason_code = "unsupported_forecast"
        message = (
            "这个问题暂不支持查询。"
            "目前可以分析已有的历史经营数据，"
            "但暂未提供预测能力。"
        )
    else:
        reason_code = "unsupported_inventory_planning"
        message = (
            "这个问题暂不支持查询。"
            "目前可以分析已有的历史经营数据，"
            "但暂未提供库存规划或备货建议能力。"
        )

    return BusinessRequestPreflightDecisionV2(
        outcome=(
            BusinessRequestPreflightOutcomeV2
            .UNSUPPORTED_CAPABILITY
        ),
        reason_code=reason_code,
        user_message=message,
    )


def evaluate_business_request_preflight_v2(
    question: str,
) -> BusinessRequestPreflightDecisionV2:
    """
    评估 SQL 之前就应明确的产品能力边界。

    规则刻意保持窄：
    1. 明确 Forecast / Inventory Planning 需求才停为 Unsupported；
    2. “表现最好/最佳”这类评价语义，只有在问题同时要求
       维度比较且没有命中任何正式 Metric 时才要求澄清；
    3. 已明确 GMV / 订单数 / Buyer 等 Metric 的排名问题继续进入
       现有 Semantic / Query Plan 主链。

    这样不会把“当前还没覆盖的自然语言表达”全部错误归类为
    Unsupported，也不会因为数据库小就伪造不存在的预测能力。
    """
    q = _normalize(question)

    forecast_requested = _contains_any(
        q,
        (
            "预测",
            "预估未来",
            "预测未来",
            "forecast",
        ),
    )

    inventory_requested = _contains_any(
        q,
        (
            "库存规划",
            "库存计划",
            "准备多少库存",
            "备多少货",
            "备货",
            "补货建议",
            "安全库存",
            "inventoryplanning",
        ),
    )

    if forecast_requested or inventory_requested:
        return _unsupported_capability_decision_v2(
            forecast_requested=forecast_requested,
            inventory_requested=inventory_requested,
        )

    ranking_evaluation = _contains_any(
        q,
        (
            "表现最好",
            "表现最佳",
            "表现最优",
            "表现最差",
            "表现最弱",
            "最好的渠道",
            "最佳渠道",
            "最差的渠道",
            "最好的品类",
            "最佳品类",
            "最好的地区",
            "最佳地区",
        ),
    )

    dimension_comparison = _contains_any(
        q,
        (
            "渠道",
            "平台",
            "品类",
            "类目",
            "地区",
            "区域",
        ),
    )

    if ranking_evaluation and dimension_comparison:
        explicit_metric_matches = search_metric_candidates_v2(
            question
        )

        if not explicit_metric_matches:
            return BusinessRequestPreflightDecisionV2(
                outcome=(
                    BusinessRequestPreflightOutcomeV2
                    .NEEDS_CLARIFICATION
                ),
                reason_code="ambiguous_performance_metric",
                user_message=(
                    "“表现最好”需要先确定评价指标。"
                    "你希望按 GMV、订单数、购买人数，"
                    "还是其他业务指标进行比较？"
                ),
            )

    return BusinessRequestPreflightDecisionV2(
        outcome=BusinessRequestPreflightOutcomeV2.CONTINUE,
    )
