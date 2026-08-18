from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, model_validator

from app.evaluation.judge_human_calibration_v2 import (
    BusinessDecisionDimensionV2,
)


class DimensionRubricRuleV2(BaseModel):
    """
    单个 Business Decision 维度的版本化评分标准。

    Rubric 是“评价尺子”，不是某一次 Judge / Human 的评分结果。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    dimension: BusinessDecisionDimensionV2
    pass_criteria: str
    partial_criteria: str
    fail_criteria: str
    owner_roles: tuple[str, ...]

    @model_validator(mode="after")
    def validate_rule(
        self,
    ) -> "DimensionRubricRuleV2":
        for field_name in (
            "pass_criteria",
            "partial_criteria",
            "fail_criteria",
        ):
            value = getattr(
                self,
                field_name,
            )
            if not value.strip():
                raise ValueError(
                    f"{field_name} 不能为空。"
                )

        if not self.owner_roles:
            raise ValueError(
                "Rubric dimension 至少需要一个 owner role。"
            )

        if any(
            not role.strip()
            for role in self.owner_roles
        ):
            raise ValueError(
                "owner_roles 不能包含空值。"
            )

        return self


class BusinessDecisionRubricV2(BaseModel):
    """
    版本化 Business Decision Evaluation Rubric。

    规则：
    - 历史版本不覆盖；
    - 新版本通过 supersedes 指向旧版本；
    - 历史 Evaluation 继续绑定当时使用的 rubric_version。
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    rubric_id: str = "business_decision_rubric"
    rubric_version: str
    effective_from: date

    supersedes: str | None = None
    change_reason: str

    dimensions: tuple[
        DimensionRubricRuleV2, ...
    ]

    @model_validator(mode="after")
    def validate_rubric(
        self,
    ) -> "BusinessDecisionRubricV2":
        if not self.rubric_version.strip():
            raise ValueError(
                "rubric_version 不能为空。"
            )

        if not self.change_reason.strip():
            raise ValueError(
                "change_reason 不能为空。"
            )

        expected = set(
            BusinessDecisionDimensionV2
        )
        actual = {
            item.dimension
            for item in self.dimensions
        }

        if actual != expected:
            raise ValueError(
                "Business Decision Rubric 必须覆盖完整六个维度。"
            )

        if len(self.dimensions) != len(actual):
            raise ValueError(
                "Rubric dimension 不能重复。"
            )

        return self


def _rule(
    *,
    dimension: BusinessDecisionDimensionV2,
    pass_criteria: str,
    partial_criteria: str,
    fail_criteria: str,
    owner_roles: tuple[str, ...],
) -> DimensionRubricRuleV2:
    return DimensionRubricRuleV2(
        dimension=dimension,
        pass_criteria=pass_criteria,
        partial_criteria=partial_criteria,
        fail_criteria=fail_criteria,
        owner_roles=owner_roles,
    )


BUSINESS_DECISION_RUBRIC_V1_0 = BusinessDecisionRubricV2(
    rubric_version="business_decision_rubric_v1_0",
    effective_from=date(2026, 8, 18),
    supersedes=None,
    change_reason=(
        "Day88 首版六维 Business Decision Evaluation Rubric。"
    ),
    dimensions=(
        _rule(
            dimension=(
                BusinessDecisionDimensionV2
                .FACTUAL_CORRECTNESS
            ),
            pass_criteria=(
                "事实陈述均能由当前受保护 Evidence 支持，"
                "且没有越过 Metric / Scope / Time 边界。"
            ),
            partial_criteria=(
                "核心事实基本有证据，但存在轻微遗漏、"
                "表达不完整或引用不足。"
            ),
            fail_criteria=(
                "存在无证据事实、错误数值、错误口径或越权事实。"
            ),
            owner_roles=(
                "metric_owner",
                "data_owner",
            ),
        ),
        _rule(
            dimension=(
                BusinessDecisionDimensionV2
                .DIAGNOSTIC_RELEVANCE
            ),
            pass_criteria=(
                "回答真正推进用户当前业务问题，"
                "而不是只重复查询结果。"
            ),
            partial_criteria=(
                "方向相关，但对业务问题的推进有限。"
            ),
            fail_criteria=(
                "回答与用户真正要解决的问题明显无关。"
            ),
            owner_roles=(
                "business_owner",
                "business_analyst",
            ),
        ),
        _rule(
            dimension=(
                BusinessDecisionDimensionV2
                .PRIORITIZATION
            ),
            pass_criteria=(
                "根据当前 Evidence 给出合理的调查优先级。"
            ),
            partial_criteria=(
                "给出调查方向，但排序依据不够充分。"
            ),
            fail_criteria=(
                "优先级缺乏 Evidence 支撑或明显不合理。"
            ),
            owner_roles=(
                "business_owner",
                "business_analyst",
            ),
        ),
        _rule(
            dimension=(
                BusinessDecisionDimensionV2
                .ACTIONABILITY
            ),
            pass_criteria=(
                "给出证据边界内明确、可执行的下一步。"
            ),
            partial_criteria=(
                "有下一步方向，但操作仍偏笼统。"
            ),
            fail_criteria=(
                "没有可执行建议，或建议要求越权 / 无证据操作。"
            ),
            owner_roles=(
                "business_owner",
                "business_analyst",
            ),
        ),
        _rule(
            dimension=(
                BusinessDecisionDimensionV2
                .EPISTEMIC_DISCIPLINE
            ),
            pass_criteria=(
                "严格区分 Fact / Contribution / Hypothesis / Unknown，"
                "不把相关或贡献写成原因，不把 NO_DATA 写成 0。"
            ),
            partial_criteria=(
                "总体保持认知边界，但存在轻微模糊措辞。"
            ),
            fail_criteria=(
                "把猜测写成事实、把 Contribution 写成 Cause，"
                "或明显夸大确定性。"
            ),
            owner_roles=(
                "evaluation_owner",
                "business_reviewer",
            ),
        ),
        _rule(
            dimension=(
                BusinessDecisionDimensionV2
                .EVIDENCE_SUFFICIENCY
            ),
            pass_criteria=(
                "回答正确表达当前证据是否充分，"
                "并与 EvidencePackDelivery 的 sufficiency 一致。"
            ),
            partial_criteria=(
                "基本承认证据边界，但充分度表达不够清楚。"
            ),
            fail_criteria=(
                "明显夸大证据充分度，或忽略关键 Evidence 缺口。"
            ),
            owner_roles=(
                "evaluation_owner",
                "business_reviewer",
            ),
        ),
    ),
)


BUSINESS_DECISION_RUBRIC_V2_0 = BusinessDecisionRubricV2(
    rubric_version="business_decision_rubric_v2_0",
    effective_from=date(2026, 8, 18),
    supersedes=(
        BUSINESS_DECISION_RUBRIC_V1_0
        .rubric_version
    ),
    change_reason=(
        "INS-OBS-001 Live Judge ↔ Human Calibration 暴露："
        "“业务规模最大”不能自动等价于“最值得优先调查”。"
        "V2 收紧 prioritization，使调查优先级必须与用户的 "
        "business objective 直接挂钩，并有比较性 Evidence 支撑。"
    ),
    dimensions=tuple(
        (
            _rule(
                dimension=rule.dimension,
                pass_criteria=(
                    "调查优先级与用户当前 business objective 直接相关，"
                    "并有 Evidence 说明该方向相较其他合法方向"
                    "更值得优先调查。"
                ),
                partial_criteria=(
                    "方向与问题相关且可以继续调查，"
                    "但排序主要依据规模、一般重要性或不充分 Evidence，"
                    "尚不能证明它最值得优先。"
                ),
                fail_criteria=(
                    "优先级没有 Evidence 支撑，"
                    "或与用户真正要解决的业务问题无关。"
                ),
                owner_roles=rule.owner_roles,
            )
            if (
                rule.dimension
                == BusinessDecisionDimensionV2.PRIORITIZATION
            )
            else rule
        )
        for rule in BUSINESS_DECISION_RUBRIC_V1_0.dimensions
    ),
)
