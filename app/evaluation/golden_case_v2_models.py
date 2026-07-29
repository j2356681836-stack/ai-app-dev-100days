from __future__ import annotations

from enum import Enum

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)


class GoldenCaseSplit(str, Enum):
    DEVELOPMENT = "development"
    REGRESSION = "regression"
    LOCKED_HOLDOUT = "locked_holdout"
    ADVERSARIAL = "adversarial"


class GoldenCaseCategory(str, Enum):
    CANONICAL = "canonical"
    PARAPHRASE = "paraphrase"
    AMBIGUITY = "ambiguity"
    GRAIN_SELECTION = "grain_selection"
    UNSUPPORTED_SEMANTICS = "unsupported_semantics"
    GOVERNANCE = "governance"


class MetricDecisionStatus(str, Enum):
    MATCHED = "matched"
    NEEDS_CLARIFICATION = "needs_clarification"
    UNSUPPORTED = "unsupported"


class PlanDecisionStatus(str, Enum):
    SELECTED = "selected"
    NOT_APPLICABLE = "not_applicable"
    UNSUPPORTED_SHAPE = "unsupported_shape"


class GovernanceOutcome(str, Enum):
    ALLOWED = "allowed"
    DENIED = "denied"
    NOT_EVALUATED = "not_evaluated"


class ResultGrain(str, Enum):
    OVERALL = "overall"
    CHANNEL = "channel"
    REGION = "region"
    CATEGORY = "category"


class RankingType(str, Enum):
    TOP1 = "top1"
    TOPN = "topn"
    RANKING = "ranking"
    UNKNOWN = "unknown"


class SortDirection(str, Enum):
    ASC = "asc"
    DESC = "desc"


class ScopeDimension(str, Enum):
    REGION = "region"
    CHANNEL = "channel"


class ExpectedMetricDecision(BaseModel):
    """
    Golden Case 对 Metric Resolution 的期望。

    matched:
        metric_name 必须唯一确定。

    needs_clarification:
        不允许提前指定最终 metric；
        acceptable_candidates 至少包含两个可接受候选。

    unsupported:
        表示问题本身不属于当前 V2 Metric Contract。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    status: MetricDecisionStatus
    metric_name: str | None = None
    acceptable_candidates: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_metric_decision(
        self,
    ) -> "ExpectedMetricDecision":
        candidates = self.acceptable_candidates

        if len(candidates) != len(set(candidates)):
            raise ValueError(
                "acceptable_candidates must be unique."
            )

        if self.status == MetricDecisionStatus.MATCHED:
            if not self.metric_name:
                raise ValueError(
                    "matched metric decision requires metric_name."
                )

            if candidates:
                raise ValueError(
                    "matched metric decision must not declare "
                    "acceptable_candidates."
                )

            return self

        if self.metric_name is not None:
            raise ValueError(
                f"{self.status.value} metric decision must not "
                "preselect metric_name."
            )

        if (
            self.status
            == MetricDecisionStatus.NEEDS_CLARIFICATION
        ):
            if len(candidates) < 2:
                raise ValueError(
                    "needs_clarification requires at least two "
                    "acceptable_candidates."
                )

            return self

        if candidates:
            raise ValueError(
                "unsupported metric decision must not declare "
                "acceptable_candidates."
            )

        return self


class ExpectedIntentDecision(BaseModel):
    """
    Golden Case 对自然语言业务形状的期望。

    result_grain:
        最终结果按什么 Grain 返回。

    scope_dimensions:
        问题是否同时要求 Region / Channel 过滤范围。
        这与 result_grain 是两个独立概念。

    例如：
        “华东销售额”
        result_grain = overall
        scope_dimensions = {region}

        “华东各渠道 ROI”
        result_grain = channel
        scope_dimensions = {region}
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    result_grain: ResultGrain | None = None
    scope_dimensions: frozenset[ScopeDimension] = frozenset()

    limit: int | None = Field(
        default=None,
        ge=1,
    )

    ranking_type: RankingType | None = None
    sort_direction: SortDirection | None = None

    @model_validator(mode="after")
    def validate_ranking_shape(
        self,
    ) -> "ExpectedIntentDecision":
        if self.ranking_type == RankingType.TOP1:
            if self.limit != 1:
                raise ValueError(
                    "top1 intent requires limit=1."
                )

        if self.ranking_type == RankingType.TOPN:
            if self.limit is None or self.limit <= 1:
                raise ValueError(
                    "topn intent requires limit > 1."
                )

        if self.ranking_type == RankingType.RANKING:
            if self.limit is not None:
                raise ValueError(
                    "ranking intent must not declare a limit."
                )

        return self


class ExpectedPlanDecision(BaseModel):
    """
    Golden Case 对 Query Plan Selection 的期望。

    selected:
        已找到唯一可用 V2 Query Plan。

    not_applicable:
        上游尚未形成唯一 Metric，例如需要 clarification。

    unsupported_shape:
        Metric 已识别，但当前 V2 Catalog 没有该结果 Grain /
        Query Shape。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    status: PlanDecisionStatus
    plan_name: str | None = None

    @model_validator(mode="after")
    def validate_plan_decision(
        self,
    ) -> "ExpectedPlanDecision":
        if self.status == PlanDecisionStatus.SELECTED:
            if not self.plan_name:
                raise ValueError(
                    "selected plan decision requires plan_name."
                )
            return self

        if self.plan_name is not None:
            raise ValueError(
                f"{self.status.value} plan decision must not "
                "declare plan_name."
            )

        return self


class ExpectedGovernanceDecision(BaseModel):
    """
    Golden Case 对 Governance Decision 的期望。

    allowed:
        Query Contract 在当前测试 AccessContext 下允许。

    denied:
        正确 fail-closed。
        reason_code 必须明确，避免把任意失败都算 PASS。

    not_evaluated:
        当前 Case 不负责验证 Governance，
        或上游没有选出可执行 Query Plan。
        是否进入 Governance 必须由具体 Evaluation Fixture /
        AccessContext 决定，不能由 Plan Selection 自动推导。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    outcome: GovernanceOutcome
    reason_code: str | None = None

    @model_validator(mode="after")
    def validate_governance_decision(
        self,
    ) -> "ExpectedGovernanceDecision":
        if self.outcome == GovernanceOutcome.DENIED:
            if not self.reason_code:
                raise ValueError(
                    "denied governance decision requires reason_code."
                )
            return self

        if self.reason_code is not None:
            raise ValueError(
                f"{self.outcome.value} governance decision must not "
                "declare reason_code."
            )

        return self


class GoldenCaseV2(BaseModel):
    """
    Day74 Dataset V2 Decision Evaluation Contract.

    该合同评估的是：

        Question
        → Metric Decision
        → Intent / Result Grain
        → Query Plan Selection
        → Governance Outcome

    它不执行 SQL，也不验证最终数据库结果。
    SQL / PostgreSQL / Answer Regression 留给 Day75。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    case_id: str = Field(
        min_length=1,
        pattern=r"^[a-z0-9][a-z0-9_-]*$",
    )

    split: GoldenCaseSplit
    category: GoldenCaseCategory

    question: str = Field(
        min_length=1,
    )
    description: str = ""

    expected_metric: ExpectedMetricDecision
    expected_intent: ExpectedIntentDecision
    expected_plan: ExpectedPlanDecision
    expected_governance: ExpectedGovernanceDecision

    @model_validator(mode="after")
    def validate_decision_chain(
        self,
    ) -> "GoldenCaseV2":
        metric_status = self.expected_metric.status
        plan_status = self.expected_plan.status
        governance = self.expected_governance.outcome

        if (
            metric_status
            != MetricDecisionStatus.MATCHED
        ):
            if plan_status != PlanDecisionStatus.NOT_APPLICABLE:
                raise ValueError(
                    "non-matched metric decision requires "
                    "plan status=not_applicable."
                )

            if governance != GovernanceOutcome.NOT_EVALUATED:
                raise ValueError(
                    "non-matched metric decision requires "
                    "governance outcome=not_evaluated."
                )

            return self

        if plan_status == PlanDecisionStatus.NOT_APPLICABLE:
            raise ValueError(
                "matched metric decision cannot use "
                "plan status=not_applicable."
            )

        if (
            plan_status
            == PlanDecisionStatus.UNSUPPORTED_SHAPE
        ):
            if governance != GovernanceOutcome.NOT_EVALUATED:
                raise ValueError(
                    "unsupported query shape must stop before "
                    "governance evaluation."
                )

            return self

        if self.expected_intent.result_grain is None:
            raise ValueError(
                "selected query plan requires expected result_grain."
            )

        # Query Plan Selection 与 Governance Evaluation 分层。
        #
        # selected plan 只证明 Metric + Result Grain 可以唯一映射
        # 到一个 V2 Query Contract。
        #
        # 是否进行 Governance Evaluation 取决于具体测试是否提供
        # AccessContext / Governance Fixture，因此语义类 Golden Case
        # 可以合法使用 not_evaluated。
        return self


class GoldenCaseCatalogV2(BaseModel):
    """
    可一次加载一组 Day74 Golden Cases。

    Catalog 本身不决定 split；
    每个 Case 自己声明 development / regression /
    locked_holdout / adversarial。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    version: str = "golden_case_v2_0"
    dataset_name: str = "beauty_bi_v2"
    cases: tuple[GoldenCaseV2, ...]

    @model_validator(mode="after")
    def validate_catalog(
        self,
    ) -> "GoldenCaseCatalogV2":
        if not self.cases:
            raise ValueError(
                "GoldenCaseCatalogV2 requires at least one case."
            )

        case_ids = [
            case.case_id
            for case in self.cases
        ]

        if len(case_ids) != len(set(case_ids)):
            raise ValueError(
                "GoldenCaseV2 case_id values must be unique."
            )

        return self
